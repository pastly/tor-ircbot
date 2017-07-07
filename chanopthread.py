import json
import re
from queue import Empty, Queue
from pbthread import PBThread

class ChanOpThread(PBThread):
    def __init__(self, global_state):
        PBThread.__init__(self, self._enter)
        self._message_queue = Queue(100)
        self.update_global_state(global_state)
    
    def update_global_state(self, gs):
        self._log_proc = gs['threads']['log']
        self._conf = gs['conf']
        self._is_shutting_down = gs['events']['is_shutting_down']
        self._banned_patterns = []
        if 'pats' in self._conf['banned_patterns']:
            for p in json.loads(self._conf['banned_patterns']['pats']):
                self._banned_patterns.append(re.compile(p))
                if self._log_proc: self._log_proc.debug(p)
        if self._log_proc:
            self._log_proc.info('ChanOpThread updated state')

    def _enter(self):
        log = self._log_proc
        log.notice('Started ChanOpThread instance')
        while not self._is_shutting_down.is_set():
            type, line = "", ""
            try:
                type, line = self._message_queue.get(timeout=1)
            except Empty:
                if self._is_shutting_down.is_set():
                    return self._shutdown()
            if type != 'chan': continue
            if not len(line): continue
            tokens = line.split()
            speaker = tokens[2]
            words = tokens[3:]
            if speaker == '-!-':
                log.debug('Ignoring for now: {}'.format(line))
                continue
            elif speaker[0] != '<' or speaker[-1] != '>':
                log.debug('Ignoring weird speaker: {}'.format(speaker))
                continue
            else:
                speaker = speaker[1:-1].lower()
                self._proc_chan_msg(speaker, words)

    def _proc_chan_msg(self, speaker, words):
        log = self._log_proc
        log.debug('<{}> {}'.format(speaker, ' '.join(words)))
        if self._contains_banned_pattern(words):
            log.notice('{} said a banned pattern'.format(speaker))

    def _contains_banned_pattern(self, words):
        words = ' '.join([ w.lower() for w in words ])
        for bp in self._banned_patterns:
            if bp.search(words): return True
        return False

    def _shutdown(self):
        log = self._log_proc
        log.notice('ChanOpThread going away')

    def recv_line(self, type, line):
        self._message_queue.put( (type, line) )
