#!/usr/bin/env python3
# python stuff
import os
import signal
import time
from configparser import ConfigParser
from multiprocessing import Event
# my stuff
from signalstuff import *
from logprocess import LogProcess
from watchfileprocess import WatchFileProcess
from chanopprocess import ChanOpProcess
from iiwatchdogprocess import IIWatchdogProcess

def share_gs(gs, procs):
    for proc in procs:
        if proc: proc.update_global_state(gs)

def main():
    config_file = 'config.ini'
    gs = {
        'procs': {
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
    gs['signal_stack'] = add_current_signals_to_stack([])
    gs['signal_stack'] = set_signals(gs['signal_stack'],
        sigint, sigterm,  sighup)
    gs['signal_stack'] = set_signals(gs['signal_stack'],
        signal.SIG_IGN,
        signal.SIG_IGN,
        signal.SIG_IGN)
    gs['conf'].read(config_file)

    server_dir = os.path.join(
        gs['conf']['ii']['ircdir'],gs['conf']['ii']['server'])
    channel_name = gs['conf']['ii']['channel']

    gs['procs']['log'] = LogProcess(gs,
        debug=os.path.join(server_dir, channel_name, 'debug.log'),
        overwrite=[])
    gs['procs']['chan_op'] = ChanOpProcess(gs)
    gs['procs']['watch_chan'] = WatchFileProcess(
        os.path.join(server_dir, channel_name, 'out'), 'chan', gs)
    gs['procs']['watch_serv'] = WatchFileProcess(
        os.path.join(server_dir, 'out'), 'serv', gs)
    gs['procs']['watch_priv'] = WatchFileProcess(
        os.path.join(server_dir, 'pastly_bot', 'out'), 'priv', gs)
    gs['procs']['ii_watchdog'] = IIWatchdogProcess(gs)
    for p in gs['procs']:
        proc = gs['procs'][p]
        if proc: proc.start()

    gs['signal_stack'] = pop_signals_from_stack(gs['signal_stack'])

    share_gs(gs, [ gs['procs'][p] for p in gs['procs'] ])
    while True:
        time.sleep(10.0)

if __name__=='__main__':
    main()
