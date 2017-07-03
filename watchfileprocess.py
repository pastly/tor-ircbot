from pbprocess import PBProcess
from signalstuff import *
import subprocess
import time
from random import random

class WatchFileProcess(PBProcess):
    def __init__(self, fname, type, global_state):
        PBProcess.__init__(self, self._enter)
        self._fname = fname
        self._type = type
        self.update_global_state(global_state)

    def _enter(self):
        log = self._log_proc
        log.notice('Started WatchFileProcess {} {} instance'.format(
            self._type, self._fname))
        set_signals(self._ss, *get_default_signals(self._ss))
        sub = subprocess.Popen(['tail','-F','-n','0',self._fname],
            stdout=subprocess.PIPE,
            bufsize=1)
        pop_signals_from_stack(self._ss)
        while not self._is_shutting_down.is_set():
            line_ = sub.stdout.readline()
            try:
                line = line_.decode('utf8')
                line = line[:-1]
                if len(line): log.debug(line)
            except UnicodeDecodeError:
                log.warn('Can\'t decode line, so ignoring: {}'.format(line_))
                continue
        sub.terminate()
        log.notice('Stopping tail process for {}'.format(self._fname))

    def _shutdown(self):
        log = self._log_proc
        if log: log.notice('WatchFileProcess {} {} going away'.format(
            self._type, self._fname))
        return

    def update_global_state(self, gs):
        self._log_proc = gs['procs']['log']
        self._is_shutting_down = gs['events']['is_shutting_down']
        self._ss = gs['signal_stack']
        if self._log_proc:
            self._log_proc.info(
                'WatchFileProcess {} {} updated state'.format(
                    self._type, self._fname))
