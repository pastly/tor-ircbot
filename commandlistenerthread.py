from queue import Empty, Queue
from pbthread import PBThread
import json
class CommandListenerThread(PBThread):
    def __init__(self, global_state):
        PBThread.__init__(self, self._enter)
        self._message_queue = Queue(100)
        self.update_global_state(global_state)

    def update_global_state(self, gs):
        self._log_thread = gs['threads']['log']
        self._out_msg_thread = gs['threads']['out_message']
        self._conf = gs['conf']
        self._is_shutting_down = gs['events']['is_shutting_down']
        if 'masters' not in self._conf['general']:
            self._log_thread.warn('No masters are configured so the '
                'CommandListenerThread will likely be useless and you won\'t '
                'be able to control the bot via IRC private messages.')
        else:
            self._masters = json.loads(self._conf['general']['masters'])
            self._log_thread.info('Configured masters: {}'.format(
                ', '.join(self._masters)))
        if self._log_thread:
            self._log_thread.info('CommandListenerThread updated state')

    def _enter(self):
        log = self._log_thread
        log.notice('Started CommandListenerThread instance')
        while not self._is_shutting_down.is_set():
            type, line = "", ""
            try: type, line = self._message_queue.get(timeout=1)
            except Empty:
                if self._is_shutting_down.is_set():
                    return self._shutdown()
            if not len(line): continue
            if type != 'priv': continue 
            tokens = line.split()
            # the speaker is token at index 2, then remove leading '<', then
            # remove trailing '>'
            speaker = tokens[2][1:][:-1]
            words = tokens[3:]
            if speaker not in self._masters:
                log.notice('Ignoring privmsg from non-master {}'.format(
                    speaker))
                continue
            if ' '.join(words).lower() == 'ping':
                self._out_msg_thread.pong(speaker)

    def _shutdown(self):
        log = self._log_thread
        log.notice('CommandListenerThread going away')

    def recv_line(self, type, line):
        self._message_queue.put( (type, line) )
