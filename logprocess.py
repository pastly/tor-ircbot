from datetime import datetime
from multiprocessing import Queue
from queue import Empty
from pbprocess import PBProcess

class LogProcess(PBProcess):
    def __init__(self, global_state, error=None, warn=None, notice=None,
        info=None, debug=None, overwrite=[]):
        PBProcess.__init__(self, self.__enter)

        self._message_queue = Queue(10000)
        self._gs = global_state

        self._logs = {}
        for level, fname in ('debug', debug), \
            ('info', info), \
            ('notice', notice), \
            ('warn', warn), \
            ('error', error):
            self._logs[level] = {
                'fname': fname,
                'mode': 'w' if level in overwrite else 'a',
                'fd': None
            }

        self.notice('Created LogProcess instance')

    def __enter(self):
        for l in self._logs:
            log = self._logs[l]
            if log['fname']:
                print('opening {} for {}'.format(log['fname'], l))
                # buffering=1 means line-based buffering
                log['fd'] = open(log['fname'], log['mode'], buffering=1)
        while True:
            try:
                level, s = self._message_queue.get(timeout=0.1)
            except Empty:
                if self._gs['events']['is_shutting_down'].is_set():
                    fd = LogProcess._get_fd(self._logs, 'notice')
                    if fd: LogProcess._log_file(fd,
                        'notice',
                        'LogProcess going away')
                    self.flush()
                    for l in self._logs:
                        log = self._logs[l]
                        if log['fd']: log['fd'].close()
                        log['fd'] = None
                    return
            else:
                fd = LogProcess._get_fd(self._logs, level)
                if fd: LogProcess._log_file(fd, level, s)

    def flush(self):
        for l in self._logs:
            log = self._logs[l]
            if log['fd']: log['fd'].flush()

    def _get_fd(logs, level):
        found_the_level = False
        possibilities = ['error', 'warn', 'notice', 'info', 'debug']
        for p in possibilities:
            if level == p: found_the_level = True
            if found_the_level and logs[p]['fd']: return logs[p]['fd']
        return None
        

    def _log_file(fd, level, s):
        assert fd
        ts = datetime.now()
        fd.write('[{}] [{}] {}\n'.format(ts, level, s))

    def _add_to_queue(self, s, level):
        self._message_queue.put( (level, s) )
    def debug(self, s, level='debug'):
        self._add_to_queue(s, level)
    def info(self, s, level='info'):
        self._add_to_queue(s, level)
    def notice(self, s, level='notice'):
        self._add_to_queue(s, level)
    def warn(self, s, level='warn'):
        self._add_to_queue(s, level)
    def error(self, s, level='error'):
        self._add_to_queue(s, level)
