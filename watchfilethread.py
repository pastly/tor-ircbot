from pbthread import PBThread
import subprocess


class WatchFileThread(PBThread):
    def __init__(self, fname, type, global_state, *args, **kwargs):
        PBThread.__init__(self, self._enter, *args,
                          name='WatchFile-{}'.format(type), **kwargs)
        self._fname = fname
        self._type = type
        self.update_global_state(global_state)

    def _enter(self):
        log = self._log
        log.notice('Started WatchFileThread {} {} instance'.format(
            self._type, self._fname))
        sub = subprocess.Popen(['tail', '-F', '-n', '0', self._fname],
                               stdout=subprocess.PIPE,
                               bufsize=1)
        while not self._is_shutting_down.is_set():
            line_ = sub.stdout.readline()
            try:
                line = line_.decode('utf8')
                line = line[:-1]
                if not len(line):
                    continue
                if self._chanop_thread:
                    self._chanop_thread.recv_line(self._type, line)
                if self._command_thread:
                    self._command_thread.recv_line(self._type, line)
                # if len(line): log.debug("[{}] {}".format(self._type, line))
            except UnicodeDecodeError:
                log.warn('Can\'t decode line, so ignoring: {}'.format(line_))
                continue
        sub.terminate()
        log.notice('Stopping tail process for {}'.format(self._fname))

    def _shutdown(self):
        log = self._log
        if log:
            log.notice('WatchFileThread {} {} going away'.format(
                       self._type, self._fname))
        return

    def update_global_state(self, gs):
        self._log = gs['log']
        self._chanop_thread = gs['threads']['chan_op']
        self._command_thread = gs['threads']['command_listener']
        self._is_shutting_down = gs['events']['is_shutting_down']
        if self._log:
            self._log.info(
                'WatchFileThread {} {} updated state'.format(
                    self._type, self._fname))
