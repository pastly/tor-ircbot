import json
import re
import time
from queue import Empty, Queue
from threading import Event
from member import Member, MemberList
from pbtimer import fire_one_off_event, RepeatedTimer
from pbthread import PBThread
from tokenbucket import token_bucket


class ChanOpThread(PBThread):

    non_nick_punctuation = [':', ', ', '!', '?']
    nick_prefixes = ['@', '+']
    non_nick_punctuation.extend(nick_prefixes)
    common_words = \
        ['the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 'it',
         'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at', 'this',
         'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she', 'or',
         'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their', 'what',
         'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which', 'go', 'me',
         'when', 'make', 'can', 'like', 'time', 'no', 'just', 'him', 'know',
         'take', 'people', 'into', 'year', 'your', 'good', 'some', 'could',
         'them', 'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come',
         'its', 'over', 'thnk', 'also', 'back', 'after', 'use', 'two', 'how',
         'our', 'work', 'first', 'well', 'way', 'even', 'new', 'want',
         'because', 'any', 'these', 'give', 'day', 'most', 'us']

    def __init__(self, global_state, channel_name):
        PBThread.__init__(self, self._enter,
                          name='ChanOp-{}'.format(channel_name))
        self._message_queue = Queue(100)
        self._members = MemberList()
        self._is_getting_members = Event()
        self._channel_name = channel_name
        self.update_global_state(global_state)
        if 'masters' not in self._conf['general']:
            self._masters = []
        else:
            self._masters = json.loads(self._conf['general']['masters'])
        self._highlight_spam_token_bucket = token_bucket(
            int(self._conf['highlight_spam']['long_mention_limit']),
            float(self._conf['highlight_spam']['long_mention_limit_seconds']) /
            float(self._conf['highlight_spam']['long_mention_limit']))
        self._highlight_spam_token_bucket_state = None
        self._message_flood_token_bucket_func = token_bucket(
            int(self._conf['flood']['message_limit']),
            float(self._conf['flood']['message_limit_seconds']) /
            float(self._conf['flood']['message_limit']))
        self._message_flood_burst_token_bucket_func = token_bucket(
            int(self._conf['flood']['burst_message_limit']),
            float(self._conf['flood']['burst_message_limit_seconds']) /
            float(self._conf['flood']['burst_message_limit']))
        self._message_flood_token_bucket_states = {}

    @property
    def channel_name(self):
        return self._channel_name

    @property
    def members(self):
        return self._members

    def update_global_state(self, gs):
        self._log = gs['log']
        assert self._channel_name in gs['threads']['op_actions']
        t = gs['threads']['op_actions'][self._channel_name]
        self._operator_action_thread = t
        self._out_msg_thread = gs['threads']['out_message']
        self._heart_thread = gs['threads']['heart']
        self._conf = gs['conf']
        self._end_event = gs['events']['kill_chanops']
        self._banned_patterns = []
        if 'pats' in self._conf['banned_patterns']:
            for p in json.loads(self._conf['banned_patterns']['pats']):
                self._banned_patterns.append(re.compile(p))
        self._soapbox_patterns = []
        self._soapbox_reason = ''
        if 'pats' in self._conf['soapbox_patterns']:
            self._soapbox_reason = self._conf['soapbox_patterns']['reason']
            for p in json.loads(self._conf['soapbox_patterns']['pats']):
                p = p.replace('/', ' */ *')
                p = p.replace('-', ' *- *')
                p = p.replace('.', ' *\\. *')
                self._soapbox_patterns.append(re.compile(p, re.IGNORECASE))
        if self._log:
            self._log.info('ChanOpThread updated state')

    def _enter(self):
        log = self._log
        log.info('Started ChanOpThread instance')
        fire_one_off_event(5, self._update_members_event_callback)
        self._update_members_event = RepeatedTimer(
            60*60*8,
            self._update_members_event_callback)
        while not self._end_event.is_set():
            source, line = "", ""
            try:
                source, line = self._message_queue.get(timeout=1)
            except Empty:
                if self._end_event.is_set():
                    return self._shutdown()
            if source not in ['chan', 'serv']:
                continue
            if not len(line):
                continue
            tokens = line.split()
            speaker = tokens[2]
            words = tokens[3:]
            if speaker == '-!-':
                self._proc_ctrl_msg(speaker, words)
            elif speaker == self._channel_name:
                if ' '.join(words) == 'End of /WHO list.':
                    self._is_getting_members.clear()
                elif self._is_getting_members.is_set():
                    user, host, server, nick, unknown1, unknown2 = words[0:6]
                    self._add_member(nick, user, host)
            elif speaker[0] != '<' or speaker[-1] != '>':
                # if speaker starts with '#', then ignore it. It's a channel
                # and we end up spamming our logs when updating member lists
                # when moderating many channels
                if speaker[0] == '#':
                    continue
                log.debug('Ignoring weird speaker: {}'.format(speaker))
            else:
                speaker = speaker[1:-1].lower()
                self._proc_chan_msg(speaker, words)

    def _proc_ctrl_msg(self, speaker, words):
        assert speaker == '-!-'
        log = self._log
        oat = self._operator_action_thread
        channel_name = self._channel_name
        if ' '.join(words[1:3]) == 'changed mode/{}'.format(channel_name):
            # who = words[0]
            mode = words[4]
            arg = words[5] if len(words) >= 6 else None
            if mode == '+o' and arg == 'TorModBot':
                oat.set_opped(True)
            if mode == '-o' and arg == 'TorModBot':
                oat.set_opped(False)
        elif ' '.join(words[1:4]) == 'has joined {}'.format(channel_name):
            s = words[0]
            nick = s.split('(')[0]
            user = s.split('(')[1].split('@')[0]
            host = s.split('@')[1].split(')')[0]
            self._members.add(nick, user, host)
            log.info('Added (join)', '{}!{}@{} ({})'
                     .format(nick, user, host, len(self._members)))
            self._heart_thread.event_add_nick()
        elif ' '.join(words[1:4]) == 'has left {}'.format(channel_name):
            s = words[0]
            nick = s.split('(')[0]
            self._members.remove(nick)
            log.info('Removed (left) {} ({})'.format(nick, len(self._members)))
            self._heart_thread.event_del_nick()
        elif ' '.join(words[1:3]) == 'has quit':
            s = words[0]
            nick = s.split('(')[0]
            if self._members.contains(nick):
                self._members.remove(nick)
                log.info('Removed (quit) {} ({})'.format(
                    nick, len(self._members)))
                self._heart_thread.event_del_nick()
            if nick in self._message_flood_token_bucket_states:
                self._message_flood_token_bucket_states.pop(nick)
        elif ' '.join(words[1:4]) == 'changed nick to':
            from_nick = words[0]
            to_nick = words[4]
            log.info(from_nick, 'changing to', to_nick)
            self._heart_thread.event_change_nick()
            if not self._members.contains(from_nick):
                log.info('Do not have a member with nick', from_nick)
            else:
                mem = self._members[from_nick]
                mem.set(nick=to_nick)
            if from_nick in self._message_flood_token_bucket_states:
                self._message_flood_token_bucket_states[to_nick] = \
                    self._message_flood_token_bucket_states[from_nick]
                self._message_flood_token_bucket_states.pop(from_nick)
        else:
            log.debug('Ignoring ctrl msg:', ' '.join(words))

    def _proc_chan_msg(self, speaker, words):
        log = self._log
        oat = self._operator_action_thread
        log.debug('<{}> {}'.format(speaker, ' '.join(words)))
        self._heart_thread.event_chan_msg()
        if self._contains_banned_pattern(words):
            oat.temporary_mute(enabled=True)
            log.notice('{} said a banned pattern'.format(speaker))
            if self._members.contains(speaker):
                mem = self._members[speaker]
                self.chanserv_quiet_add(
                    '{}!*@*'.format(mem.nick), 'banned pattern (auto)')
                self.chanserv_quiet_add(
                    '*!*@{}'.format(mem.host), 'banned pattern (auto)')
            else:
                self.chanserv_quiet_add(
                    '{}!*@*'.format(speaker), 'banned pattern (auto)')
        elif self._contains_soapbox_pattern(words):
            log.notice('{} seems to be using us as a soapbox'.format(speaker))
            r = self._soapbox_reason
            if self._members.contains(speaker):
                mem = self._members[speaker]
                self.chanserv_akick_add(
                    '{}!*@*'.format(mem.nick), '{} (soapboxing) (auto)'.format(r))
                self.chanserv_akick_add(
                    '*!*@{}'.format(mem.host), '{} (soapboxing) (auto)'.format(r))
            else:
                self.chanserv_akick_add(
                    '{}!*@*'.format(speaker), '{} (soapboxing) (auto)'.format(r))
            oat.set_chan_mode('+R', 'soapboxing (auto)')
        elif self._is_highlight_spam(words):
            oat.temporary_mute(enabled=True)
            log.notice('{} highlight spammed'.format(speaker))
            if self._members.contains(speaker):
                mem = self._members[speaker]
                self.chanserv_akick_add(
                    '{}!*@*'.format(mem.nick), 'mass highlight spam (auto)')
                self.chanserv_akick_add(
                    '*!*@{}'.format(mem.host), 'mass highlight spam (auto)')
            else:
                self.chanserv_akick_add(
                    '{}!*@*'.format(speaker), 'mass highlight spam (auto)')
        elif self._is_slow_highlight_spam(words):
            oat.temporary_mute(enabled=True)
            log.notice('The channel is being highlight spammed slowly. '
                       'Kicking', speaker)
            if self._members.contains(speaker):
                mem = self._members[speaker]
                self.chanserv_akick_add(
                    '{}!*@*'.format(mem.nick), 'slow highlight spam (auto)')
                self.chanserv_akick_add(
                    '*!*@{}'.format(mem.host), 'slow highlight spam (auto)')
            else:
                self.chanserv_akick_add(
                    '{}!*@*'.format(speaker), 'slow highlight spam (auto)')
        elif self._is_speaker_flooding(speaker):
            log.notice(speaker, 'has said too much recently. Kicking.')
            oat.kick_nick(speaker, 'flooding (auto)')
            oat.set_chan_mode('+R', 'flooding (auto)')

    def _contains_banned_pattern(self, words):
        # words = ' '.join([ w.lower() for w in words ])
        for bp in self._banned_patterns:
            # if bp.search(words): return True
            if bp.search(' '.join(words)):
                return True
        return False

    def _contains_soapbox_pattern(self, words):
        # words = ' '.join([ w.lower() for w in words ])
        for bp in self._soapbox_patterns:
            # if bp.search(words): return True
            if bp.search(' '.join(words)):
                return True
        return False

    def _find_mentioned_nicks(self, words):
        mems = self._members
        matches = set()
        words = [w.lower() for w in words]
        words = [w for w in words if w not in ChanOpThread.common_words]
        matches = set()
        # first try straight nick mentions with no prefix/suffix obfuscation
        for match in [w for w in words if mems.contains(w)]:
            matches.add(match)
        # then try removing leading/trailing punctuation from words and see if
        # they then start to look like nicks. Not all punctuation is illegal
        punc = ''.join(ChanOpThread.non_nick_punctuation)
        for word in words:
            word = word.lstrip(punc).rstrip(punc)
            if mems.contains(word):
                matches.add(word)
        return matches

    def _is_highlight_spam(self, words):
        log = self._log
        limit = int(self._conf['highlight_spam']['mention_limit'])
        matches = self._find_mentioned_nicks(words)
        log.debug("{} nicks mentioned".format(len(matches)))
        return len(matches) > limit

    def _is_slow_highlight_spam(self, words):
        tb = self._highlight_spam_token_bucket
        tb_state = self._highlight_spam_token_bucket_state
        matches = self._find_mentioned_nicks(words)
        for match in matches:
            wait_time, tb_state = tb(tb_state)
            self._highlight_spam_token_bucket_state = tb_state
            if wait_time > 0:
                return True
        return False

    def _is_speaker_flooding(self, speaker):
        if speaker in self._masters:
            return False
        log = self._log
        tb_flood_func = self._message_flood_token_bucket_func
        tb_flood_burst_func = self._message_flood_burst_token_bucket_func
        tb_states = self._message_flood_token_bucket_states
        if speaker not in tb_states:
            tb_states[speaker] = {
                'last_message': 0,
                'flood_state': None,
                'flood_burst_state': None,
            }
        now = time.time()
        # there's code to support having a burst token bucket and a regular
        # token bucet, but for now just use the regular token bucket. Trust
        # that OFTC and Floodserv will handle bursts of messages.
        # if now - tb_states[speaker]['last_message'] > 1:
        #     wait_time, new_state = tb_flood_func(
        #         tb_states[speaker]['flood_state'])
        #     tb_states[speaker]['flood_state'] = new_state
        #     log.debug('REGLR', wait_time, new_state)
        # else:
        #     wait_time, new_state = tb_flood_burst_func(
        #         tb_states[speaker]['flood_burst_state'])
        #     tb_states[speaker]['flood_burst_state'] = new_state
        #     log.debug('BURST', wait_time, new_state)
        wait_time, new_state = tb_flood_func(tb_states[speaker]['flood_state'])
        tb_states[speaker]['flood_state'] = new_state
        tb_states[speaker]['last_message'] = now
        log.debug('Flood TB: wait={} state={}'.format(wait_time, new_state))
        return wait_time > 0

    def _update_members_event_callback(self):
        self._members = MemberList()
        out_msg = self._out_msg_thread
        out_msg.add(self._ask_for_new_members)

    def _ask_for_new_members(self):
        log = self._log
        out_msg = self._out_msg_thread
        channel_name = self._channel_name
        log.info('Clearing members set. Asking for members again.')
        self._is_getting_members.set()
        out_msg.add(out_msg.servmsg, ['/who {}'.format(channel_name)])

    def _add_member(self, nick, user=None, host=None):
        log = self._log
        old_len = len(self._members)
        self._members.add(nick, user, host)
        log.info('Added {} ({})'
                 .format(Member(nick, user, host), len(self._members)))
        if len(self._members) <= old_len:
            log.warn('Adding {} to members didn\'t inc length'.format(nick))

    def chanserv_akick_add(self, mask, reason='', master=None):
        ''' Can be called from any thread, including this one '''
        self._heart_thread.event_add_akick()
        # Reason is included when chanserv akicks, so unlike
        # self.chanserv_quiet_add, we don't need to send NOTICE to room
        #
        # Now privately log the reason, but add the nick of the master who told
        # us to add this akick
        log_str = 'akicking {} because {}'.format(mask, reason)
        log_str += '' if not master else ' (by {})'.format(master)
        self._log.notice(log_str)
        # Finally actually send the akick command
        return self._chanserv('akick', 'add', mask, reason)

    def chanserv_akick_del(self, mask):
        ''' Can be called from any thread, including this one '''
        self._heart_thread.event_del_akick()
        return self._chanserv('akick', 'del', mask, reason='')

    def chanserv_quiet_add(self, mask, reason='', master=None):
        ''' Can be called from any thread, including this one '''
        self._heart_thread.event_add_quiet()
        log_str = 'quieting {} because {}'.format(mask, reason)
        # Reason isn't included when chanserv quiets, so send NOTICE to room
        omt = self._out_msg_thread
        omt.add(omt.notice, [self._channel_name, log_str])
        # And privately log the same reason, but add the nick of the master
        # who told us to add this quiet
        log_str += '' if not master else ' (by {})'.format(master)
        self._log.notice(log_str)
        # Finally actually send the quiet command
        return self._chanserv('quiet', 'add', mask, reason)

    def chanserv_quiet_del(self, mask):
        ''' Can be called from any thread, including this one '''
        self._heart_thread.event_del_quiet()
        return self._chanserv('quiet', 'del', mask, reason='')

    def _chanserv(self, chanserv_list, action, mask, reason):
        ''' Can be called from any thread, including this one '''
        assert chanserv_list in ['akick', 'quiet']
        assert action in ['add', 'del']
        log = self._log
        if len(reason) < 1 and action not in ['del']:
            log.warn('Must give reason for', action, 'to/from', chanserv_list)
            return
        omt = self._out_msg_thread
        message = '{l} {c} {a} {m} {r}'.format(
            l=chanserv_list, c=self._channel_name, a=action, m=mask, r=reason)
        omt.add(omt.privmsg, ['chanserv', message], {'log_it': True})

    def _shutdown(self):
        log = self._log
        self._update_members_event.stop()
        log.info('ChanOpThread going away')

    def recv_line(self, source, line):
        self._message_queue.put((source, line))
