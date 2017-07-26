#!/usr/bin/env python3
# python stuff
import os
import signal
import time
from configparser import ConfigParser
from threading import Event
# my stuff
from signalstuff import *
from tokenbucket import token_bucket
from logthread import LogThread
from watchfilethread import WatchFileThread
from chanopthread import ChanOpThread
from commandlistenerthread import CommandListenerThread
from iiwatchdogthread import IIWatchdogThread
from operatoractionthread import OperatorActionThread
from outboundmessagethread import OutboundMessageThread

def main():
    config_file = 'config.ini'
    gs = {
        'threads': {
            'log': None,
            'watch_chan': None,
            'watch_serv': None,
            'watch_priv': None,
            'chan_op': None,
            'command_listener': None,
            'ii_watchdog': None,
            'op_action': None,
            'out_message': None,
        },
        'events': {
            'is_shutting_down': Event(),
            'is_operator': Event(),
        },
        'signal_stack': [],
        'conf': ConfigParser(),
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
        gs['conf']['ii']['ircdir'],gs['conf']['ii']['server'])
    channel_name = gs['conf']['ii']['channel']

    gs['threads']['log'] = LogThread(gs,
        #debug=os.path.join(server_dir, channel_name, 'debug.log'),
        #overwrite=[])
        debug='/dev/stdout',
        overwrite=['debug'])
    gs['threads']['out_message'] = OutboundMessageThread(gs, long_timeout=5,
        time_between_actions_func=token_bucket(5, 0.505))
    gs['threads']['op_action'] = OperatorActionThread(gs)
    gs['threads']['chan_op'] = ChanOpThread(gs)
    gs['threads']['command_listener'] = CommandListenerThread(gs)
    gs['threads']['watch_chan'] = WatchFileThread(
        os.path.join(server_dir, channel_name, 'out'), 'chan', gs)
    gs['threads']['watch_serv'] = WatchFileThread(
        os.path.join(server_dir, 'out'), 'serv', gs)
    gs['threads']['watch_priv'] = WatchFileThread(
        os.path.join(server_dir, 'pastly_bot', 'out'), 'priv', gs)
    gs['threads']['ii_watchdog'] = IIWatchdogThread(gs)
    for t in gs['threads']:
        thread = gs['threads'][t]
        if thread: thread.start()

    # must add current signals to the beginning of the stack as we need to keep
    # track of what the default signals are
    gs['signal_stack'] = add_current_signals_to_stack([])
    gs['signal_stack'] = set_signals(gs['signal_stack'], sigint, sigterm, sighup)

    while True:
        time.sleep(10.0)

if __name__=='__main__':
    main()
