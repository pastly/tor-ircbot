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
        self._log_thread = gs['threads']['log']
        self._operator_action_thread = gs['threads']['op_action']
        self._out_msg_thread = gs['threads']['out_message']
        self._conf = gs['conf']
        self._is_shutting_down = gs['events']['is_shutting_down']
        self._banned_patterns = []
        if 'pats' in self._conf['banned_patterns']:
            for p in json.loads(self._conf['banned_patterns']['pats']):
                self._banned_patterns.append(re.compile(p))
                if self._log_thread: self._log_thread.debug(p)
        if self._log_thread:
            self._log_thread.info('ChanOpThread updated state')

    def _enter(self):
        log = self._log_thread
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
                self._proc_ctrl_msg(speaker, words)
            elif speaker[0] != '<' or speaker[-1] != '>':
                log.debug('Ignoring weird speaker: {}'.format(speaker))
                continue
            else:
                speaker = speaker[1:-1].lower()
                self._proc_chan_msg(speaker, words)

    def _proc_ctrl_msg(self, speaker, words):
        assert speaker == '-!-'
        channel_name = self._conf['ii']['channel']
        log = self._log_thread
        oat = self._operator_action_thread
        if ' '.join(words[1:3]) == 'changed mode/{}'.format(channel_name):
            who = words[0]
            mode = words[4]
            arg = words[5] if len(words) >= 6 else None
            if mode == '+o' and arg == 'pastly_bot': oat.set_opped(True)
            if mode == '-o' and arg == 'pastly_bot': oat.set_opped(False)
        else:
            log.debug('Ignoring ctrl msg:',' '.join(words))

    def _proc_chan_msg(self, speaker, words):
        log = self._log_thread
        oat = self._operator_action_thread
        out_msg = self._out_msg_thread
        log.debug('<{}> {}'.format(speaker, ' '.join(words)))
        if self._contains_banned_pattern(words):
            oat.temporary_mute(enabled=True)
            log.notice('{} said a banned pattern'.format(speaker))

    def _contains_banned_pattern(self, words):
        words = ' '.join([ w.lower() for w in words ])
        for bp in self._banned_patterns:
            if bp.search(words): return True
        return False

    def _shutdown(self):
        log = self._log_thread
        log.notice('ChanOpThread going away')

    def recv_line(self, type, line):
        self._message_queue.put( (type, line) )
