from datetime import datetime
from queue import Empty, Queue
from pbthread import PBThread

class LogThread(PBThread):
    def __init__(self, global_state, error=None, warn=None, notice=None,
        info=None, debug=None, overwrite=[]):
        PBThread.__init__(self, self._enter)

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

        self._message_queue = Queue(10000)
        self.update_global_state(global_state)

    def _enter(self):
        self.notice('Started LogThread instance')
        for l in self._logs:
            log = self._logs[l]
            if log['fname']:
                print('opening {} for {}'.format(log['fname'], l))
                # buffering=1 means line-based buffering
                log['fd'] = open(log['fname'], log['mode'], buffering=1)
        while True:
            try:
                ts, level, s = self._message_queue.get(timeout=5)
            except Empty:
                if self._is_shutting_down.is_set():
                    return self._shutdown()
            else:
                fd = LogThread._get_fd(self._logs, level)
                if fd: LogThread._log_file(fd, ts, level, s)

    def flush(self):
        for l in self._logs:
            log = self._logs[l]
            if log['fd']: log['fd'].flush()

    def _shutdown(self):
        fd = LogThread._get_fd(self._logs, 'notice')
        if fd: LogThread._log_file(fd, datetime.now(),
            'notice', 'LogThread going away')
        self.flush()
        for l in self._logs:
            log = self._logs[l]
            if log['fd']: log['fd'].close()
            log['fd'] = None
        return

    def _get_fd(logs, level):
        found_the_level = False
        possibilities = ['error', 'warn', 'notice', 'info', 'debug']
        for p in possibilities:
            if level == p: found_the_level = True
            if found_the_level and logs[p]['fd']: return logs[p]['fd']
        return None
        

    def _log_file(fd, ts, level, s):
        assert fd
        fd.write('[{}] [{}] {}\n'.format(ts, level, s))

    def _add_to_queue(self, s, level):
        ts = datetime.now()
        self._message_queue.put( (ts, level, s) )
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

    def update_global_state(self, gs):
        self._is_shutting_down = gs['events']['is_shutting_down']
        fd = LogThread._get_fd(self._logs, 'info')
        if fd: LogThread._log_file(fd, datetime.now(),
            'info', 'LogThread updated state')