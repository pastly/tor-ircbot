#!/usr/bin/env python3
# python stuff
import os
import time
import json
from configparser import ConfigParser
from threading import Event
# my stuff
import signalstuff as ss
from tokenbucket import token_bucket
from watchfilethread import WatchFileThread
from logtomastersthread import LogToMastersThread
from chanopthread import ChanOpThread
from commandlistenerthread import CommandListenerThread
from iiwatchdogthread import IIWatchdogThread
from operatoractionthread import OperatorActionThread
from outboundmessagethread import OutboundMessageThread
from heartbeatthread import HeartbeatThread
from pastlylogger import PastlyLogger


def main():
    config_file = 'config.ini'
    gs = {
        'threads': {
            'watch_chans': {},
            'watch_serv': None,
            'watch_priv': None,
            'chan_ops': {},
            'command_listener': None,
            'ii_watchdog': None,
            'op_actions': {},
            'out_message': None,
            'log_to_masters': None,
            'heart': None,
        },
        'events': {
            'is_shutting_down': Event(),
        },
        'signal_stack': [],
        'conf': ConfigParser(),
        'log': None,
    }

    def sigint(signum, stack_frame):
        gs['events']['is_shutting_down'].set()
        exit(0)

    def sigterm(signum, stack_frame):
        return sigint(signum, stack_frame)

    def sighup(signum, stack_frame):
        pass

    gs['conf'].read(config_file)

    server_dir = os.path.join(
        gs['conf']['ii']['ircdir'], gs['conf']['ii']['server'])

    if 'log' in gs['conf'] and \
            'in_file' in gs['conf']['log'] and \
            'out_channel' in gs['conf']['log']:
        fname = gs['conf']['log']['in_file']
        gs['log'] = PastlyLogger(
            debug='/dev/stdout', notice=fname,
            overwrite=['debug'], log_threads=True, default='notice')
    else:
        gs['log'] = PastlyLogger(
            debug='/dev/stdout', overwrite=['debug'],
            log_threads=True, default='notice')

    channel_names = json.loads(gs['conf']['ii']['channels'])

    gs['threads']['heart'] = HeartbeatThread(gs)

    gs['threads']['out_message'] = \
        OutboundMessageThread(gs, long_timeout=5,
                              time_between_actions_func=token_bucket(5, 0.505))

    for channel_name in channel_names:
        gs['threads']['op_actions'][channel_name] = \
            OperatorActionThread(gs, channel_name)

    for channel_name in channel_names:
        gs['threads']['chan_ops'][channel_name] = \
            ChanOpThread(gs, channel_name)

    gs['threads']['command_listener'] = CommandListenerThread(gs)

    for channel_name in channel_names:
        gs['threads']['watch_chans'][channel_name] = WatchFileThread(
            os.path.join(server_dir, channel_name, 'out'), 'chan', gs,
            channel_name=channel_name)

    gs['threads']['watch_serv'] = WatchFileThread(
        os.path.join(server_dir, 'out'), 'serv', gs)

    gs['threads']['watch_priv'] = WatchFileThread(
        os.path.join(server_dir, 'kist', 'out'), 'priv', gs)

    if 'log' in gs['conf'] and \
            'in_file' in gs['conf']['log'] and \
            'out_channel' in gs['conf']['log']:
        gs['threads']['log_to_masters'] = LogToMastersThread(
            gs['conf']['log']['in_file'], gs)

    gs['threads']['ii_watchdog'] = IIWatchdogThread(gs)

    gs['threads']['ii_watchdog'].start()
    time.sleep(2)
    for t in gs['threads']:
        thread = gs['threads'][t]
        if thread is None:
            continue
        if isinstance(thread, dict):
            for thread_ in thread:
                if not thread[thread_].is_alive():
                    thread[thread_].start()
        else:
            if not thread.is_alive():
                thread.start()

    # must add current signals to the beginning of the stack as we need to keep
    # track of what the default signals are
    gs['signal_stack'] = ss.add_current_signals_to_stack([])
    gs['signal_stack'] = ss.set_signals(gs['signal_stack'],
                                        sigint, sigterm, sighup)

    while True:
        time.sleep(10.0)


if __name__ == '__main__':
    main()
