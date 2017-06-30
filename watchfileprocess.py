from pbprocess import PBProcess
import time
from random import random

class WatchFileProcess(PBProcess):
    def __init__(self, fname, global_state=None):
        PBProcess.__init__(self, self.__enter)
        self._fname = fname
        self._gs = global_state

    def __enter(self):
        log = self._gs['procs']['log']
        while True:
            if log:
                log.debug('WFP for {} reporting in!'.format(self._fname))
                time.sleep(random()*0.1)
            if self._gs['events']['is_shutting_down'].is_set():
                log.notice('WatchFileProcess {} going away'.format(self._fname))
                return
