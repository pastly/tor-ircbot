from pbthread import PBThread
import subprocess


class WatchFileThread(PBThread):
    def __init__(self, fname, type, global_state, channel_name=None, *args,
                 **kwargs):
        # if <type> == 'chan', then <channel_name> must be given. Otherwise,
        # it must not be given
        if type == 'chan':
            assert channel_name is not None
            name = 'WatchFile-{}'.format(channel_name)
        else:
            assert channel_name is None
            name = 'WatchFile-{}'.format(type)
        PBThread.__init__(self, self._enter, *args, name=name, **kwargs)
        self._fname = fname
        self._type = type
        self._channel_name = channel_name
        self.update_global_state(global_state)

    def _enter(self):
        log = self._log
        log.notice('Started WatchFileThread', self._type, self._fname,
                   'instance')
        sub = subprocess.Popen('tail -F -n 0 {}'.format(self._fname).split(),
                               stdout=subprocess.PIPE, bufsize=1)
        while not self._is_shutting_down.is_set():
            log = self._log
            line_ = sub.stdout.readline()
            try:
                line = line_.decode('utf8')
                line = line[:-1]
                if not len(line):
                    continue
                if self._type == 'chan':
                    assert self._channel_name in self._chanop_threads
                    t = self._chanop_threads[self._channel_name]
                    t.recv_line(self._type, line)
                else:
                    for t in self._chanop_threads:
                        self._chanop_threads[t].recv_line(self._type, line)
                if self._command_thread:
                    self._command_thread.recv_line(self._type, line)
                # if len(line): log.debug("[{}] {}".format(self._type, line))
            except UnicodeDecodeError:
                log.warn('Can\'t decode line, so ignoring:', line_)
                continue
        sub.terminate()
        log.notice('Stopping tail process for', self._fname)

    def _shutdown(self):
        log = self._log
        if log:
            log.notice('WatchFileThread', self._type, self._fname,
                       'going away')
        return

    def update_global_state(self, gs):
        self._log = gs['log']
        chanop_threads = gs['threads']['chan_ops']
        if self._type == 'chan':
            assert self._channel_name in chanop_threads
        self._chanop_threads = gs['threads']['chan_ops']
        self._command_thread = gs['threads']['command_listener']
        self._is_shutting_down = gs['events']['is_shutting_down']
        if self._log:
            self._log.info('WatchFileThread', self._type, self._fname,
                           'updated state')
