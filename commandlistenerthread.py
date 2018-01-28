from pbthread import PBThread
from queue import Empty, Queue
import json
class CommandListenerThread(PBThread):
    def __init__(self, global_state):
        PBThread.__init__(self, self._enter, name='CommandListener')
        self._message_queue = Queue(100)
        self.update_global_state(global_state)

    def update_global_state(self, gs):
        self._log = gs['log']
        self._out_msg_thread = gs['threads']['out_message']
        self._operator_action_thread = gs['threads']['op_action']
        self._conf = gs['conf']
        self._is_shutting_down = gs['events']['is_shutting_down']
        if 'masters' not in self._conf['general']:
            self._log.warn('No masters are configured so the '
                'CommandListenerThread will likely be useless and you won\'t '
                'be able to control the bot via IRC private messages.')
            self._masters = []
        else:
            self._masters = json.loads(self._conf['general']['masters'])
            self._log.info('Configured masters: {}'.format(
                ', '.join(self._masters)))
        if self._log:
            self._log.info('CommandListenerThread updated state')

    def _enter(self):
        log = self._log
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
                omt = self._out_msg_thread
                omt.add(omt.pong, [speaker])
                continue
            elif words[0].lower() == 'mode':
                self._proc_mode_msg(speaker, words)
                continue
            elif words[0].lower() == 'kick':
                self._proc_kick_msg(speaker, words)
                continue
            else:
                omt = self._out_msg_thread
                omt.add(omt.privmsg, [speaker, 'I don\'t understand'])
                continue

    def _proc_mode_msg(self, speaker, words):
        assert words[0].lower() == 'mode'
        assert speaker in self._masters
        mode_str = ' '.join(words[1:])
        self._operator_action_thread.set_chan_mode(mode_str,
            '{} said so'.format(speaker))

    def _proc_kick_msg(self, speaker, words):
        assert words[0].lower() == 'kick'
        assert speaker in self._masters
        if len(words) != 2:
            self._log.warn('Don\'t know how to kick "{}". Just give one '
                    'name'.format(' '.join(words[1:])))
            return
        nick = words[1]
        self._operator_action_thread.kick_nick(nick)

    def _shutdown(self):
        log = self._log
        log.notice('CommandListenerThread going away')

    def recv_line(self, type, line):
        self._message_queue.put( (type, line) )
