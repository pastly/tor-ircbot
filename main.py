#!/usr/bin/env python3
# python stuff
import os
import signal
import time
from configparser import ConfigParser
from threading import Event
# my stuff
from signalstuff import *
from logthread import LogThread
from watchfilethread import WatchFileThread
#from chanopprocess import ChanOpProcess
#from iiwatchdogprocess import IIWatchdogProcess

#def share_gs(gs, threads):
#    for proc in threads:
#        if proc: proc.update_global_state(gs)

def main():
    config_file = 'config.ini'
    gs = {
        'threads': {
            'log': None,
            'watch_chan': None,
            'watch_serv': None,
            'watch_priv': None,
            'chan_op': None,
            'ii_watchdog': None,
        },
        'events': {
            'is_shutting_down': Event(),
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

    # must add current signals to the beginning of the stack as we need to keep
    # track of what the default signals are
    #gs['signal_stack'] = add_current_signals_to_stack([])
    #gs['signal_stack'] = set_signals(gs['signal_stack'],
    #    sigint, sigterm,  sighup)
    #gs['signal_stack'] = set_signals(gs['signal_stack'],
    #    signal.SIG_IGN,
    #    signal.SIG_IGN,
    #    signal.SIG_IGN)
    gs['conf'].read(config_file)

    server_dir = os.path.join(
        gs['conf']['ii']['ircdir'],gs['conf']['ii']['server'])
    channel_name = gs['conf']['ii']['channel']

    gs['threads']['log'] = LogThread(gs,
        #debug=os.path.join(server_dir, channel_name, 'debug.log'),
        #overwrite=[])
        debug='/dev/stdout',
        overwrite=['debug'])
    #gs['threads']['chan_op'] = ChanOpProcess(gs)
    gs['threads']['watch_chan'] = WatchFileThread(
        #os.path.join(server_dir, channel_name, 'out'), 'chan', gs)
        'chan.txt', 'chan', gs)
    #gs['threads']['watch_serv'] = WatchFileProcess(
    #    os.path.join(server_dir, 'out'), 'serv', gs)
    #gs['threads']['watch_priv'] = WatchFileProcess(
    #    os.path.join(server_dir, 'pastly_bot', 'out'), 'priv', gs)
    #gs['threads']['ii_watchdog'] = IIWatchdogProcess(gs)
    for t in gs['threads']:
        thread = gs['threads'][t]
        if thread: thread.start()

    #gs['signal_stack'] = pop_signals_from_stack(gs['signal_stack'])

    gs['signal_stack'] = add_current_signals_to_stack([])
    gs['signal_stack'] = set_signals(gs['signal_stack'], sigint, sigterm, sighup)

    #share_gs(gs, [ gs['threads'][p] for p in gs['threads'] ])
    while True:
        time.sleep(10.0)

if __name__=='__main__':
    main()
