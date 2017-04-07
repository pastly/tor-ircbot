from datetime import datetime
from multiprocessing import Lock
class PastlyLogger:
    def __init__(self, error=None, warn=None, notice=None,
        info=None, debug=None, overwrite=[]):

        # buffering=1 means line-based buffering
        if error:
            self.error_fd = open(error, 'w' if 'error' in overwrite else 'a',
                buffering=1)
            self.error_fd_mutex = Lock()
        else:
            self.error_fd = None
            self.error_fd_mutex = None
        if warn:
            self.warn_fd = open(warn, 'w' if 'warn' in overwrite else 'a',
                buffering=1)
            self.warn_fd_mutex = Lock()
        else:
            self.warn_fd = None
            self.warn_fd_mutex = None
        if notice:
            self.notice_fd = open(notice, 'w' if 'notice' in overwrite else 'a',
                buffering=1)
            self.notice_fd_mutex = Lock()
        else:
            self.notice_fd = None
            self.notice_fd_mutex = None
        if info:
            self.info_fd = open(info, 'w' if 'info' in overwrite else 'a',
                buffering=1)
            self.info_fd_mutex = Lock()
        else:
            self.info_fd = None
            self.info_fd_mutex = None
        if debug:
            self.debug_fd = open(debug, 'w' if 'debug' in overwrite else 'a',
                buffering=1)
            self.debug_fd_mutex = Lock()
        else:
            self.debug_fd = None
            self.debug_fd_mutex = None

        self.debug('Creating PastlyLogger instance')

    def __del__(self):
        self.debug('Deleting PastlyLogger instance')
        self.flush()
        if self.error_fd: self.error_fd.close()
        if self.warn_fd: self.warn_fd.close()
        if self.notice_fd: self.notice_fd.close()
        if self.info_fd: self.info_fd.close()
        if self.debug_fd: self.debug_fd.close()
        self.error_fd, self.warn_fd = None, None
        self.notice_fd, self.info_fd, self.debug_fd = None, None, None
        if self.error_fd_mutex:
            if not self.error_fd_mutex.acquire(block=False):
                self.error_fd_mutex.release()
        if self.warn_fd_mutex:
            if not self.warn_fd_mutex.acquire(block=False):
                self.warn_fd_mutex.release()
        if self.notice_fd_mutex:
            if not self.notice_fd_mutex.acquire(block=False):
                self.notice_fd_mutex.release()
        if self.info_fd_mutex:
            if not self.info_fd_mutex.acquire(block=False):
                self.info_fd_mutex.release()
        if self.debug_fd_mutex:
            if not self.debug_fd_mutex.acquire(block=False):
                self.debug_fd_mutex.release()

    def _log_file(fd, lock, s, level):
        assert fd
        lock.acquire()
        ts = datetime.now()
        fd.write('[{}] [{}] {}\n'.format(ts, level, s))
        lock.release()

    def flush(self):
        if self.error_fd: self.error_fd.flush()
        if self.warn_fd: self.warn_fd.flush()
        if self.notice_fd: self.notice_fd.flush()
        if self.info_fd: self.info_fd.flush()
        if self.debug_fd: self.debug_fd.flush()

    def debug(self, s, level='debug'):
        if self.debug_fd: return PastlyLogger._log_file(
            self.debug_fd, self.debug_fd_mutex, s, level)
        return None

    def info(self, s, level='info'):
        if self.info_fd: return PastlyLogger._log_file(
            self.info_fd, self.info_fd_mutex, s, level)
        else: return self.debug(s, level)

    def notice(self, s, level='notice'):
        if self.notice_fd: return PastlyLogger._log_file(
            self.notice_fd, self.notice_fd_mutex, s, level)
        else: return self.info(s, level)

    def warn(self, s, level='warn'):
        if self.warn_fd: return PastlyLogger._log_file(
            self.warn_fd, self.warn_fd_mutex, s, level)
        else: return self.notice(s, level)

    def error(self, s, level='error'):
        if self.error_fd: return PastlyLogger._log_file(
            self.error_fd, self.error_fd_mutex, s, level)
        else: return self.warn(s, level)
