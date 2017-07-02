from pbprocess import PBProcess
import time
from random import random

class WatchFileProcess(PBProcess):
    def __init__(self, fname, global_state):
        PBProcess.__init__(self, self._enter)
        self._fname = fname
        self.update_global_state(global_state)

    def _enter(self):
        log = self._log_proc
        log.notice('Started WatchFileProcess {} instance'.format(self._fname))
        while True:
            if log:
                log.debug('WFP for {} reporting in!'.format(self._fname))
                time.sleep(random()*2)
            if self._is_shutting_down.is_set():
                return self._shutdown()

    def _shutdown(self):
        log = self._log_proc
        if log: log.notice('WatchFileProcess {} going away'.format(self._fname))
        return

    def update_global_state(self, gs):
        self._log_proc = gs['procs']['log']
        self._is_shutting_down = gs['events']['is_shutting_down']
        if self._log_proc:
            self._log_proc.info(
                'WatchFileProcess {} updated state'.format(self._fname))
