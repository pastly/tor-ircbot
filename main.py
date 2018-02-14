#!/usr/bin/env python3
# python stuff
import os
import time
import json
from configparser import ConfigParser
from threading import Event
# my stuff
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


def create_threads(gs):
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

    if 'general' in gs['conf'] and 'command_channel' in gs['conf']['general']:
        comm_chan = gs['conf']['general']['command_channel']
        gs['threads']['watch_comm'] = WatchFileThread(
            os.path.join(server_dir, comm_chan, 'out'), 'comm', gs,
            channel_name=comm_chan)

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
                    thread[thread_].update_global_state(gs)
                    thread[thread_].start()
        else:
            if not thread.is_alive():
                thread.update_global_state(gs)
                thread.start()
    return gs


def destroy_threads(gs):
    gs['events']['kill_heartbeat'].set()
    gs['log'].notice('Waiting for heartbeat thread ...')
    gs['threads']['heart'].join()

    gs['events']['kill_command_listener'].set()
    gs['log'].notice('Waiting for command listener threads ..')
    gs['threads']['command_listener'].join()

    gs['events']['kill_watches'].set()
    gs['log'].notice('Waiting for watch file threads ...')
    for t in gs['threads']['watch_chans']:
        gs['threads']['watch_chans'][t].join()
    gs['threads']['watch_serv'].join()
    gs['threads']['watch_priv'].join()
    gs['threads']['watch_comm'].join()

    gs['events']['kill_chanops'].set()
    gs['log'].notice('Waiting for chan op threads ...')
    for t in gs['threads']['chan_ops']:
        gs['threads']['chan_ops'][t].join()

    gs['events']['kill_opactions'].set()
    gs['log'].notice('Waiting for operator action threads ...')
    for t in gs['threads']['op_actions']:
        gs['threads']['op_actions'][t].join()

    if gs['threads']['log_to_masters'] is not None:
        gs['events']['kill_logtomasters'].set()
        gs['log'].notice('Waiting for log to masters thread ...')
        gs['threads']['log_to_masters'].join()

    gs['events']['kill_outmessage'].set()
    gs['log'].notice('Waiting for out message thread ...')
    gs['threads']['out_message'].join()

    gs['events']['kill_iiwatchdog'].set()
    gs['log'].notice('Waiting for ii watchdog thread ...')
    gs['threads']['ii_watchdog'].join()
    return gs


def main():
    config_file = 'config.ini'
    gs = {
        'threads': {
            'watch_chans': {},
            'watch_serv': None,
            'watch_priv': None,
            'watch_comm': None,
            'chan_ops': {},
            'command_listener': None,
            'ii_watchdog': None,
            'op_actions': {},
            'out_message': None,
            'log_to_masters': None,
            'heart': None,
        },
        'events': {
            'kill_command_listener': Event(),
            'kill_chanops': Event(),
            'kill_opactions': Event(),
            'kill_watches': Event(),
            'kill_iiwatchdog': Event(),
            'kill_outmessage': Event(),
            'kill_heartbeat': Event(),
            'kill_logtomasters': Event(),
        },
        'conf': ConfigParser(),
        'log': None,
    }

    gs['conf'].read(config_file)
    gs = create_threads(gs)
    gs['log']('All started and ready to go. I can\'t wait to help!')
    try:
        while True:
            time.sleep(300)
    except KeyboardInterrupt:
        pass
    gs = destroy_threads(gs)
    gs['log']('Bye bye :( If you see this, tell my wife I love her')


if __name__ == '__main__':
    main()
