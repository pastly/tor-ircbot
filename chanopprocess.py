from multiprocessing import Queue
from queue import Empty
from pbprocess import PBProcess

class ChanOpProcess(PBProcess):
    def __init__(self, global_state):
        PBProcess.__init__(self, self._enter)
        self._message_queue = Queue(100)
        self.update_global_state(global_state)
    
    def update_global_state(self, gs):
        self._log_proc = gs['procs']['log']
        self._is_shutting_down = gs['events']['is_shutting_down']
        if self._log_proc:
            self._log_proc.info('ChanOpProcess updated state')

    def _enter(self):
        log = self._log_proc
        log.notice('Started ChanOpProcess instance')
        while not self._is_shutting_down.is_set():
            type, line = "", ""
            try:
                type, line = self._message_queue.get(timeout=1)
            except Empty:
                if self._is_shutting_down.is_set():
                    return self._shutdown()
            if not len(line): continue
            tokens = line.split()
            speaker = tokens[2]
            words = tokens[3:]
            log.debug('<{}> {}'.format(speaker, words))


    def _shutdown(self):
        log = self._log_proc
        log.notice('ChanOpProcess going away')

    def recv_line(self, type, line):
        self._message_queue.put( (type, line) )
