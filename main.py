#!/usr/bin/env python3
# python stuff
import signal
import time
from multiprocessing import Event
# my stuff
from signalstuff import *
from logprocess import LogProcess
from watchfileprocess import WatchFileProcess

def main():
    global_state = {
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
        global_state['events']['is_shutting_down'].set()
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

    global_state['procs']['log'] = LogProcess(global_state,
        debug='/dev/stdout', overwrite=['debug']).start()
    global_state['procs']['watch_chan'] = WatchFileProcess('chan.txt',
        global_state)
    global_state['procs']['watch_serv'] = WatchFileProcess('serv.txt',
        global_state)
    global_state['procs']['watch_priv'] = WatchFileProcess('priv.txt',
        global_state)
    global_state['procs']['watch_chan'].start()
    #global_state['procs']['watch_serv'].start()
    #global_state['procs']['watch_priv'].start()

    signal_stack = pop_signals_from_stack(signal_stack)

    while True:
        time.sleep(10.0)

if __name__=='__main__':
    main()
