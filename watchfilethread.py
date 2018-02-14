from pbthread import PBThread
import subprocess


class WatchFileThread(PBThread):
    def __init__(self, fname, source, global_state, channel_name=None, *args,
                 **kwargs):
        # if <source> == 'chan' or 'comm', then <channel_name> must be given.
        # Otherwise, it must not be given
        assert source in ['chan', 'comm', 'serv', 'priv']
        if source in ['chan', 'comm']:
            assert channel_name is not None
            name = 'WatchFile-{}'.format(channel_name)
        else:
            assert channel_name is None
            name = 'WatchFile-{}'.format(source)
        PBThread.__init__(self, self._enter, *args, name=name, **kwargs)
        self._fname = fname
        self._source = source
        self._channel_name = channel_name
        self.update_global_state(global_state)

    def _enter(self):
        log = self._log
        log.info('Started WatchFileThread', self._source, self._fname,
                   'instance')
        sub = subprocess.Popen('tail -F -n 0 {}'.format(self._fname).split(),
                               stdout=subprocess.PIPE, bufsize=1)
        while not self._end_event.is_set():
            log = self._log
            line_ = sub.stdout.readline()
            try:
                line = line_.decode('utf8')
                line = line[:-1]
                if not len(line):
                    continue
                if self._source == 'chan':
                    assert self._channel_name in self._chanop_threads
                    t = self._chanop_threads[self._channel_name]
                    t.recv_line(self._source, line)
                else:
                    for t in self._chanop_threads:
                        self._chanop_threads[t].recv_line(self._source, line)
                if self._command_thread:
                    self._command_thread.recv_line(self._source, line)
                # if len(line): log.debug("[{}] {}".format(self._source, line))
            except UnicodeDecodeError:
                log.warn('Can\'t decode line, so ignoring:', line_)
                continue
        sub.terminate()
        log.info('Stopping tail process for', self._fname)
        return self._shutdown()

    def _shutdown(self):
        log = self._log
        if log:
            log.info(
                'WatchFileThread', self._source, self._fname, 'going away')
        return

    def update_global_state(self, gs):
        self._log = gs['log']
        chanop_threads = gs['threads']['chan_ops']
        if self._source == 'chan':
            assert self._channel_name in chanop_threads
        self._chanop_threads = gs['threads']['chan_ops']
        self._command_thread = gs['threads']['command_listener']
        self._end_event = gs['events']['kill_watches']
        if self._log:
            self._log.info('WatchFileThread', self._source, self._fname,
                           'updated state')
