from pbthread import PBThread
import subprocess
import time


class LogToMastersThread(PBThread):
    ''' watches a file for log messages, and then sends them to an IRC
    channel '''
    def __init__(self, fname, global_state, *args, **kwargs):
        name = 'LogToMasters'
        PBThread.__init__(self, self._enter, *args, name=name, **kwargs)
        self._fname = fname
        self.update_global_state(global_state)

    def _enter(self):
        log = self._log
        omt = self._out_msg_thread
        log.info('Started LogToMastersThread', self._fname, 'instance')
        sub = subprocess.Popen('tail -F -n 0 {}'.format(self._fname).split(),
                               stdout=subprocess.PIPE, bufsize=1)
        while not self._end_event.is_set():
            line_ = sub.stdout.readline()
            try:
                line = line_.decode('utf8')
                line = line[:-1]
                if not len(line):
                    continue
                omt.add(omt.privmsg,
                        [self._channel, line],
                        {'log_it': False},
                        priority=time.time()+300)
            except UnicodeDecodeError:
                log.warn('Can\'t decode line, so ignoring', line_)
                continue
        sub.terminate()
        log.info('Stopping tail process for', self._fname)
        return self._shutdown()

    def _shutdown(self):
        log = self._log
        if log:
            log.info('LogToMastersThread', self._fname, 'going away')
        return

    def update_global_state(self, gs):
        self._log = gs['log']
        self._channel = gs['conf']['log']['out_channel']
        self._end_event = gs['events']['kill_logtomasters']
        self._out_msg_thread = gs['threads']['out_message']
        if self._log:
            self._log.info('LogToMastersThread', self._fname, 'updated state')
