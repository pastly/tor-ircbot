from pbthread import PBThread
from queue import Empty, Queue
import json


class CommandListenerThread(PBThread):
    valid_masks = ['nick', 'nick*', '*nick', '*nick*',
                   'user', 'user*', '*user', '*user*',
                   'host', 'host*', '*host', '*host*']

    def __init__(self, global_state):
        PBThread.__init__(self, self._enter, name='CommandListener')
        self._message_queue = Queue(100)
        self.update_global_state(global_state)

    def update_global_state(self, gs):
        self._log = gs['log']
        self._out_msg_thread = gs['threads']['out_message']
        self._chan_op_threads = gs['threads']['chan_ops']
        self._operator_action_threads = gs['threads']['op_actions']
        self._conf = gs['conf']
        self._is_shutting_down = gs['events']['is_shutting_down']
        if 'masters' not in self._conf['general']:
            self._log.warn('No masters are configured so the '
                           'CommandListenerThread will likely be useless and '
                           'you won\'t be able to control the bot via IRC '
                           'private messages.')
            self._masters = []
        else:
            self._masters = json.loads(self._conf['general']['masters'])
            self._log.info('Configured masters: {}'.format(
                ', '.join(self._masters)))
        self._channel_names = json.loads(self._conf['ii']['channels'])
        if self._log:
            self._log.info('CommandListenerThread updated state')

    def _enter(self):
        log = self._log
        log.info('Started CommandListenerThread instance')
        while not self._is_shutting_down.is_set():
            type, line = "", ""
            try:
                type, line = self._message_queue.get(timeout=1)
            except Empty:
                if self._is_shutting_down.is_set():
                    return self._shutdown()
            if not len(line):
                continue
            if type != 'priv':
                continue
            omt = self._out_msg_thread
            tokens = line.split()
            # the speaker is token at index 2, then remove leading '<', then
            # remove trailing '>'
            speaker = tokens[2][1:][:-1]
            words = tokens[3:]
            if len(words) < 1:
                continue
            if words[0] == '#' or words[0][0] == '#':
                # ignore explicit non-commands (comments)
                continue
            if speaker not in self._masters:
                # we get a lot of privmsges from -!- for some reason
                if speaker == '!':
                    continue
                log.notice('Ignoring privmsg from non-master {}'.format(
                    speaker))
                continue
            if ' '.join(words).lower() == 'ping':
                omt.add(omt.pong, [speaker])
                continue
            elif words[0].lower() == 'mode':
                # expecting 'mode #channel +Rb foobar!*@*' or similar
                # so must be at least 3 words
                if len(words) < 3:
                    omt.add(omt.privmsg, [speaker, 'bad MODE command'])
                    continue
                self._proc_mode_msg(speaker, words)
                continue
            elif words[0].lower() == 'kick':
                # expecting 'kick #channel foobar' or similar
                # so must be at least 3 words
                if len(words) < 3:
                    omt.add(omt.privmsg, [speaker, 'bad KICK command'])
                    continue
                self._proc_kick_msg(speaker, words)
                continue
            elif words[0].lower() in ['akick', 'quiet']:
                self._proc_akick_or_quiet_msg(speaker, words)
                continue
            else:
                omt.add(omt.privmsg, [speaker, 'I don\'t understand'])
                continue

    def _proc_mode_msg(self, speaker, words):
        assert words[0].lower() == 'mode'
        assert speaker in self._masters
        omt = self._out_msg_thread
        channel = words[1]
        mode_str = ' '.join(words[2:])
        if channel != 'all':
            if channel not in self._channel_names:
                omt.add(omt.privmsg,
                        [speaker, 'not moderating channel {}'.format(channel)])
                return
            if channel not in self._operator_action_threads:
                omt.add(omt.privmsg,
                        [speaker, 'cannot find operator action thread for '
                            'channel {}'.format(channel)])
                return
            oat = self._operator_action_threads[channel]
            oat.set_chan_mode(mode_str, '{} said so'.format(speaker))
        else:
            for channel in self._operator_action_threads:
                oat = self._operator_action_threads[channel]
                oat.set_chan_mode(mode_str, '{} said so'.format(speaker))

    def _proc_kick_msg(self, speaker, words):
        assert words[0].lower() == 'kick'
        assert speaker in self._masters
        omt = self._out_msg_thread
        if len(words) != 3:
            self._log.warn('Don\'t know how to kick "{}". Just give one '
                           'name'.format(' '.join(words[1:])))
            return
        channel = words[1]
        nick = words[2]
        if channel != 'all':
            if channel not in self._channel_names:
                omt.add(omt.privmsg,
                        [speaker, 'not moderating channel {}'.format(channel)])
                return
            if channel not in self._operator_action_threads:
                omt.add(omt.privmsg,
                        [speaker, 'cannot find operator action thread for '
                            'channel {}'.format(channel)])
                return
            oat = self._operator_action_threads[channel]
            oat.kick_nick(nick, '{} said so'.format(speaker))
        else:
            for channel in self._operator_action_threads:
                oat = self._operator_action_threads[channel]
                oat.kick_nick(nick, '{} said so'.format(speaker))

    def _calculate_mask(self, mem, mask):
        assert mask in CommandListenerThread.valid_masks
        if mask == 'nick':
            return '{}!*@*'.format(mem.nick)
        elif mask == 'nick*':
            return '{}*!*@*'.format(mem.nick)
        elif mask == '*nick':
            return '*{}!*@*'.format(mem.nick)
        elif mask == '*nick*':
            return '*{}*!*@*'.format(mem.nick)
        elif mask == 'user':
            return '*!{}@*'.format(mem.user)
        elif mask == 'user*':
            return '*!{}*@*'.format(mem.user)
        elif mask == '*user':
            return '*!*{}@*'.format(mem.user)
        elif mask == '*user*':
            return '*!*{}*@*'.format(mem.user)
        elif mask == 'host':
            return '*!*@{}'.format(mem.host)
        elif mask == 'host*':
            return '*!*@{}*'.format(mem.host)
        elif mask == '*host':
            return '*!*@*{}'.format(mem.host)
        return '*!*@*{}*'.format(mem.host)

    def _send_akick_or_quiet_msg(self, chan, verb, nick, masks, reason):
        assert chan in self._chan_op_threads
        assert verb in ['akick', 'quiet']
        for mask in masks:
            assert mask in CommandListenerThread.valid_masks
        log = self._log
        thread = self._chan_op_threads[chan]
        if not thread.members.contains(nick):
            log.warn('Channel', chan, 'doesn\'t have nick', nick,
                     'so ignoring masks and just akicking/quieting the nick')
            if verb == 'akick':
                thread.chanserv_akick_add(nick, reason)
            else:
                thread.chanserv_quiet_add(nick, reason)
            return
        mem = thread.members[nick]
        for mask_ in masks:
            mask = self._calculate_mask(mem, mask_)
            if verb == 'akick':
                thread.chanserv_akick_add(mask, reason)
            else:
                thread.chanserv_quiet_add(mask, reason)

    def _proc_akick_or_quiet_msg(self, speaker, words):
        assert words[0].lower() in ['quiet', 'akick']
        assert speaker in self._masters
        omt = self._out_msg_thread
        if len(words) < 5:
            omt.add(omt.privmsg,
                    [speaker,
                     'Bad command. <akick|quiet> <chan> <nick> <masks> '
                     '<reason>'])
            return
        verb, channel, nick, masks, *reason = words
        verb = verb.lower()
        masks = masks.split(',')
        valid_masks = [m for m in masks
                       if m in CommandListenerThread.valid_masks]
        if len(valid_masks) < 1:
            omt.add(omt.privmsg,
                    [speaker, 'No valid masks in: {}'.format(masks)])
            return
        masks = valid_masks
        reason = ' '.join(reason) + ' ({})'.format(speaker)
        if channel not in self._chan_op_threads and channel != 'all':
            omt.add(omt.privmsg,
                    [speaker,
                     'Unknown channel {}'.format(channel)])
            return
        if channel == 'all':
            for chan in self._chan_op_threads:
                self._send_akick_or_quiet_msg(chan, verb, nick, masks, reason)
        else:
            self._send_akick_or_quiet_msg(channel, verb, nick, masks, reason)

    def _shutdown(self):
        log = self._log
        log.info('CommandListenerThread going away')

    def recv_line(self, type, line):
        self._message_queue.put((type, line))
