#!/usr/bin/env python3
# python stuff
import signal
import time
from multiprocessing import Event
# my stuff
from signalstuff import *
from logprocess import LogProcess
from watchfileprocess import WatchFileProcess
from chanopprocess import ChanOpProcess

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
            'chan_op': None,
        },
        'events': {
            'is_shutting_down': Event(),
        },
        'signal_stack': [],
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

    gs['procs']['log'] = LogProcess(gs,
        debug='/dev/stdout', overwrite=['debug'])
    gs['procs']['chan_op'] = ChanOpProcess(gs)
    gs['procs']['watch_chan'] = WatchFileProcess('chan.txt', 'chan', gs)
    gs['procs']['watch_serv'] = WatchFileProcess('serv.txt', 'serv', gs)
    gs['procs']['watch_priv'] = WatchFileProcess('priv.txt', 'priv', gs)
    for p in gs['procs']:
        proc = gs['procs'][p]
        if proc: proc.start()

    gs['signal_stack'] = pop_signals_from_stack(gs['signal_stack'])

    share_gs(gs, [ gs['procs'][p] for p in gs['procs'] ])
    while True:
        time.sleep(10.0)

if __name__=='__main__':
    main()
