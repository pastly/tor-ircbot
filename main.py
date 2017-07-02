#!/usr/bin/env python3
# python stuff
import signal
import time
from multiprocessing import Event
# my stuff
from signalstuff import *
from logprocess import LogProcess
from watchfileprocess import WatchFileProcess

def share_gs(gs, procs):
    for proc in procs:
        if proc: proc.update_global_state(gs)

def main():
    gs = {
        'procs': {
            'log': None,
            'watch_chan': None,
            'watch_serv': None,
            'watch_priv': None,
        },
        'events': {
            'is_shutting_down': Event(),
        },
    }

    def sigint(signum, stack_frame):
        gs['events']['is_shutting_down'].set()
        exit(0)
    def sigterm(signum, stack_frame):
        return sigint(signum, stack_frame)
    def sighup(signum, stack_frame):
        pass

    signal_stack = add_current_signals_to_stack([])
    signal_stack = set_signals(signal_stack, sigint, sigterm,  sighup)
    signal_stack = set_signals(signal_stack,
        signal.SIG_IGN,
        signal.SIG_IGN,
        signal.SIG_IGN)

    gs['procs']['log'] = LogProcess(gs,
        debug='/dev/stdout', overwrite=['debug'])
    gs['procs']['watch_chan'] = WatchFileProcess('chan.txt', gs)
    for p in gs['procs']:
        proc = gs['procs'][p]
        if proc: proc.start()

    signal_stack = pop_signals_from_stack(signal_stack)

    share_gs(gs, [ gs['procs'][p] for p in gs['procs'] ])
    while True:
        time.sleep(10.0)

if __name__=='__main__':
    main()
