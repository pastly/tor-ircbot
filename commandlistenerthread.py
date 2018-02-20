from pbthread import PBThread
from queue import Empty, Queue
import json
import random
import time
import helpdocumentation as helpdocu


class CommandListenerThread(PBThread):
    valid_masks = ['nick', 'nick*', '*nick', '*nick*',
                   'user', 'user*', '*user', '*user*',
                   'host', 'host*', '*host', '*host*']

    pong_msgs = ['pong', 'PONG', 'POOOONG!!!!', 'JFC pong', 'Please stop :\'(',
                 'WTF do you want from me?', 'What did I do to deserve this?',
                 'moo', 'ACK', 'RST', 'I wish I was as cool as you <3',
                 'P O N G spells pong!']

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
        self._end_event = gs['events']['kill_command_listener']
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
        self._command_channel = None
        if 'general' in self._conf and \
                'command_channel' in self._conf['general']:
            self._command_channel = self._conf['general']['command_channel']
        if self._log:
            self._log.info('CommandListenerThread updated state')

    def _enter(self):
        log = self._log
        log.info('Started CommandListenerThread instance')
        while not self._end_event.is_set():
            source, line = "", ""
            try:
                source, line = self._message_queue.get(timeout=1)
            except Empty:
                if self._end_event.is_set():
                    return self._shutdown()
            if not len(line):
                continue
            if source not in ['priv', 'comm']:
                continue
            if source == 'comm' and self._command_channel is None:
                log.warn('Got command from command channel, but no command '
                         'channel known. Ignoring.')
                continue
            tokens = line.split()
            # the speaker is token at index 2, then remove leading '<', then
            # remove trailing '>'
            speaker = tokens[2][1:][:-1]
            words = tokens[3:]
            if len(words) < 1:
                continue
            if words[0][0] == '#':
                # ignore explicit non-commands (comments)
                continue
            if speaker not in self._masters:
                # we get a lot of privmsges from -!- for some reason
                if speaker == '!':
                    continue
                log.notice('Ignoring command/privmsg from non-master',
                           speaker)
                continue
            if ' '.join(words).lower() == 'ping':
                self._proc_ping_msg(source, speaker, words)
                continue
            elif words[0].lower() == 'help':
                self._proc_help_msg(source, speaker, words)
            elif words[0].lower() == 'mode':
                self._proc_mode_msg(source, speaker, words)
                continue
            elif words[0].lower() == 'kick':
                self._proc_kick_msg(source, speaker, words)
                continue
            elif words[0].lower() in ['akick', 'quiet']:
                self._proc_akick_or_quiet_msg(source, speaker, words)
                continue
            elif words[0].lower() in ['match']:
                self._proc_match_msg(source, speaker, words)
                continue
            else:
                self._notify_impl(source, speaker, 'I don\'t understand')
                continue

    def _proc_help_msg(self, source, speaker, words):
        assert words[0].lower() == 'help'
        resp = helpdocu.get_help_response(' '.join(words))
        resp_lines = resp.split('\n')
        for line in resp_lines:
            self._notify_impl(source, speaker, line)

    def _notify_impl(self, source, speaker, msg):
        assert source in ['priv', 'comm']
        omt = self._out_msg_thread
        if source == 'priv':
            target = speaker
        else:
            msg = '{}: {}'.format(speaker, msg)
            target = self._command_channel
        omt.add(omt.privmsg, [target, msg], priority=time.time()+300)

    def _notify_okay(self, source, speaker, *ok):
        if not ok:
            ok = 'OK'
        else:
            ok = ' '.join([str(m) for m in ok])
        return self._notify_impl(source, speaker, ok)

    def _notify_warn(self, source, speaker, *warn_msg):
        warn_msg = ' '.join([str(m) for m in warn_msg])
        warn_msg = '(W) {}'.format(warn_msg)
        return self._notify_impl(source, speaker, warn_msg)

    def _notify_error(self, source, speaker, *error_msg):
        error_msg = ' '.join([str(m) for m in error_msg])
        error_msg = '(E) {}'.format(error_msg)
        return self._notify_impl(source, speaker, error_msg)

    def _proc_ping_msg(self, source, speaker, words):
        assert source in ['priv', 'comm']
        assert ' '.join(words).lower() == 'ping'
        omt = self._out_msg_thread
        pong = random.choice(CommandListenerThread.pong_msgs)
        if source == 'priv':
            omt.add(omt.privmsg, [speaker, pong])
        else:
            chan = self._command_channel
            msg = '{}: {}'.format(speaker, pong)
            omt.add(omt.privmsg, [chan, msg])

    def _proc_match_msg(self, source, speaker, words):
        assert words[0].lower() == 'match'
        assert speaker in self._masters
        if len(words) != 2:
            self._notify_error(source, speaker, 'bad MATCH command')
            self._proc_help_msg(source, speaker, 'help match'.split())
            return
        nick = words[1]
        member = None
        # First search all channels for a member that has the given nick
        for chan in self._channel_names:
            if chan not in self._chan_op_threads:
                self._notify_warn(source, speaker, 'cannot find chanop thread '
                                  'for channel', chan)
                continue
            chanop_thread = self._chan_op_threads[chan]
            if member is None and chanop_thread.members.contains(nick):
                member = chanop_thread.members[nick]
                break
        # Give up if we didn't find the nick
        if not member:
            self._notify_error(source, speaker, 'cannot find', nick, 'in '
                               'our moderated channels')
            return
        # Get and sort matches based on whether they matched the username or
        # the hostname
        matches = {'user': {}, 'host': {}}
        for chan in self._channel_names:
            # Get all matches in this channel
            chanop_thread = self._chan_op_threads[chan]
            match_user, match_host = chanop_thread.members.matches(
                user=member.user, host=member.host)
            for match in match_user:
                # Ignore it if it IS the nick we are asking about
                if match.nick == member.nick:
                    continue
                if match.nick not in matches['user']:
                    matches['user'][match.nick] = set()
                # Remember that this matched nick is in this chan
                matches['user'][match.nick].add(chan)
            for match in match_host:
                # Ignore it if it IS the nick we are asking about
                if match.nick == member.nick:
                    continue
                if match.nick not in matches['host']:
                    matches['host'][match.nick] = set()
                # Remember that this matched nick is in this chan
                matches['host'][match.nick].add(chan)
        # Now log what we found
        if len(matches['user']) > 0:
            self._notify_impl(
                source, speaker,
                'Match on {}\'s user: ({})'.format(member.nick, member.user))
            for nick in matches['user']:
                chans = ' '.join(matches['user'][nick])
                self._notify_impl(
                    source, speaker,
                    '    {}: ({})'.format(nick, chans))
        if len(matches['host']) > 0:
            self._notify_impl(
                source, speaker,
                'Match on {}\'s host: ({})'.format(member.nick, member.host))
            for nick in matches['host']:
                chans = ' '.join(matches['host'][nick])
                self._notify_impl(
                    source, speaker,
                    '    {}: ({})'.format(nick, chans))
        if len(matches['user']) < 1 and len(matches['host']) < 1:
            self._notify_impl(source, speaker,
                              '{} is unique'.format(str(member)))

    def _proc_mode_msg(self, source, speaker, words):
        assert words[0].lower() == 'mode'
        assert speaker in self._masters
        # expecting 'mode #channel +Rb foobar!*@*' or similar
        # so must be at least 3 words
        if len(words) < 3:
            self._notify_error(source, speaker, 'bad MODE command')
            self._proc_help_msg(source, speaker, 'help mode'.split())
            return
        channel = words[1]
        mode_str = ' '.join(words[2:])
        if channel != 'all':
            if channel not in self._channel_names:
                self._notify_error(source, speaker, 'not moderating channel',
                                   channel)
                return
            if channel not in self._operator_action_threads:
                self._notify_error(source, speaker, 'cannot find operator '
                                   'action thread for channel', channel)
                return
            oat = self._operator_action_threads[channel]
            oat.set_chan_mode(mode_str, '{} said so'.format(speaker))
        else:
            for channel in self._operator_action_threads:
                oat = self._operator_action_threads[channel]
                oat.set_chan_mode(mode_str, '{} said so'.format(speaker))
        self._notify_okay(source, speaker)

    def _proc_kick_msg(self, source, speaker, words):
        assert words[0].lower() == 'kick'
        assert speaker in self._masters
        # expecting 'kick #channel foobar' or similar
        # so must be at least 3 words
        if len(words) != 3:
            self._notify_error(source, speaker, 'bad KICK command')
            self._proc_help_msg(source, speaker, 'help kick'.split())
            return
        channel = words[1]
        nick = words[2]
        if channel != 'all':
            if channel not in self._channel_names:
                self._notify_error(source, speaker, 'not moderating channel',
                                   channel)
                return
            if channel not in self._operator_action_threads:
                self._notify_error(source, speaker, 'cannot find operator '
                                   'action thread for channel', channel)
                return
            oat = self._operator_action_threads[channel]
            oat.kick_nick(nick, '{} said so'.format(speaker))
        else:
            for channel in self._operator_action_threads:
                oat = self._operator_action_threads[channel]
                oat.kick_nick(nick, '{} said so'.format(speaker))
        self._notify_okay(source, speaker)

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

    def _send_akick_or_quiet_msg(self, source, speaker,
                                 chan, verb, nick, masks, reason):
        assert chan in self._chan_op_threads
        assert verb in ['akick', 'quiet']
        for mask in masks:
            assert mask in CommandListenerThread.valid_masks
        thread = self._chan_op_threads[chan]
        if not thread.members.contains(nick):
            self._notify_warn(
                source, speaker, 'Channel', chan, 'doesn\'t have nick', nick,
                'so ignoring masks and just {}ing the nick'.format(verb))
            nick = '{}!*@*'.format(nick)
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

    def _proc_akick_or_quiet_msg(self, source, speaker, words):
        assert words[0].lower() in ['quiet', 'akick']
        assert speaker in self._masters
        if len(words) < 5:
            self._notify_error(source, speaker,
                               'Bad {} command'.format(words[0].upper()))
            self._proc_help_msg(source, speaker, ['help', words[0].lower()])
            return
        verb, channel, nick, masks, *reason = words
        if channel not in self._chan_op_threads and channel != 'all':
            self._notify_error(source, speaker, 'Unknown channel', channel)
            return
        verb = verb.lower()
        masks = masks.split(',')
        valid_masks = [m for m in masks
                       if m in CommandListenerThread.valid_masks]
        if len(valid_masks) < 1:
            self._notify_error(source, speaker, 'No valid masks in', masks)
            self._proc_help_msg(source, speaker, ['help', verb, 'mask'])
            return
        for m in [m for m in masks if m not in valid_masks]:
            self._notify_warn(
                source, speaker, m, 'is not a valid mask. Ignoring it.')
        masks = valid_masks
        reason = ' '.join(reason) + ' ({}) (by {})'.format(nick, speaker)
        if channel == 'all':
            for chan in self._chan_op_threads:
                self._send_akick_or_quiet_msg(source, speaker,
                                              chan, verb, nick, masks, reason)
        else:
            self._send_akick_or_quiet_msg(source, speaker,
                                          channel, verb, nick, masks, reason)
        self._notify_okay(source, speaker)

    def _shutdown(self):
        log = self._log
        log.info('CommandListenerThread going away')

    def recv_line(self, source, line):
        self._message_queue.put((source, line))
