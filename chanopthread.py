import json
import re
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
        self._highlight_spam_token_bucket = token_bucket(
            int(self._conf['highlight_spam']['long_mention_limit']),
            float(self._conf['highlight_spam']['long_mention_limit_seconds']) /
            float(self._conf['highlight_spam']['long_mention_limit']))
        self._highlight_spam_token_bucket_state = None

    def update_global_state(self, gs):
        self._log = gs['log']
        assert self._channel_name in gs['threads']['op_actions']
        t = gs['threads']['op_actions'][self._channel_name]
        self._operator_action_thread = t
        self._out_msg_thread = gs['threads']['out_message']
        self._conf = gs['conf']
        self._is_shutting_down = gs['events']['is_shutting_down']
        self._banned_patterns = []
        if 'pats' in self._conf['banned_patterns']:
            for p in json.loads(self._conf['banned_patterns']['pats']):
                self._banned_patterns.append(re.compile(p))
                if self._log:
                    self._log.debug(p)
        if self._log:
            self._log.info('ChanOpThread updated state')

    def _enter(self):
        log = self._log
        log.notice('Started ChanOpThread instance')
        fire_one_off_event(5, self._update_members_event_callback)
        self._update_members_event = RepeatedTimer(
            60*60*8,
            self._update_members_event_callback)
        while not self._is_shutting_down.is_set():
            type, line = "", ""
            try:
                type, line = self._message_queue.get(timeout=1)
            except Empty:
                if self._is_shutting_down.is_set():
                    return self._shutdown()
            if type not in ['chan', 'serv']:
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
                log.debug('Ignoring weird speaker: {}'.format(speaker))
            else:
                speaker = speaker[1:-1].lower()
                self._proc_chan_msg(speaker, words)

    def _proc_ctrl_msg(self, speaker, words):
        assert speaker == '-!-'
        log = self._log
        oat = self._operator_action_thread
        channel_name = self._channel_name
        if ' '.join(words[1:3]) == \
                'changed mode/{}'.format(channel_name):
            # who = words[0]
            mode = words[4]
            arg = words[5] if len(words) >= 6 else None
            if mode == '+o' and arg == 'kist':
                oat.set_opped(True)
            if mode == '-o' and arg == 'kist':
                oat.set_opped(False)
        elif ' '.join(words[1:4]) == 'has joined {}'.format(channel_name):
            s = words[0]
            nick = s.split('(')[0]
            user = s.split('(')[1].split('@')[0]
            host = s.split('@')[1].split(')')[0]
            self._members.add(nick, user, host)
            log.info('Added (join)', '{}!{}@{} ({})'
                     .format(nick, user, host, len(self._members)))
        elif ' '.join(words[1:4]) == 'has left {}'.format(channel_name):
            s = words[0]
            nick = s.split('(')[0]
            self._members.remove(nick)
            log.info('Removed (left) {} ({})'.format(nick, len(self._members)))
        elif ' '.join(words[1:3]) == 'has quit':
            s = words[0]
            nick = s.split('(')[0]
            if self._members.contains(nick):
                self._members.remove(nick)
                log.info('Removed (quit) {} ({})'.format(nick,
                                                         len(self._members)))
        else:
            log.debug('Ignoring ctrl msg:', ' '.join(words))

    def _proc_chan_msg(self, speaker, words):
        log = self._log
        oat = self._operator_action_thread
        log.debug('<{}> {}'.format(speaker, ' '.join(words)))
        if self._contains_banned_pattern(words):
            oat.temporary_mute(enabled=True)
            log.notice('{} said a banned pattern'.format(speaker))
            if self._members.contains(speaker):
                mem = self._members[speaker]
                oat.set_chan_mode('+qq {}!*@* *!*@{}'
                                  .format(mem.nick, mem.host),
                                  'banned pattern')
            else:
                oat.set_chan_mode('+q {}!*@*'.format(speaker),
                                  'banned pattern')
        elif self._is_highlight_spam(words):
            oat.temporary_mute(enabled=True)
            log.notice('{} highlight spammed'.format(speaker))
            if self._members.contains(speaker):
                mem = self._members[speaker]
                oat.set_chan_mode('+bb {}!*@* *!*@{}'
                                  .format(mem.nick, mem.host),
                                  'mass highlight spam')
                oat.kick_nick(mem.nick)
            else:
                oat.set_chan_mode('+b {}!*@*'.format(speaker),
                                  'mass highlight spam')
                oat.kick_nick(speaker)
        elif self._is_slow_highlight_spam(words):
            oat.temporary_mute(enabled=True)
            log.notice('The channel is being highlight spammed slowly. '
                       'Kicking', speaker)
            oat.kick_nick(speaker)
            if self._members.contains(speaker):
                mem = self._members[speaker]
                oat.set_chan_mode('+bb {}!*@* *!*@{}'
                                  .format(mem.nick, mem.host),
                                  '(automatic action)')
            else:
                oat.set_chan_mode('+b {}!*@*'.format(speaker),
                                  '(automatic action)')

    def _contains_banned_pattern(self, words):
        # words = ' '.join([ w.lower() for w in words ])
        for bp in self._banned_patterns:
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
        log = self._log
        tb = self._highlight_spam_token_bucket
        tb_state = self._highlight_spam_token_bucket_state
        matches = self._find_mentioned_nicks(words)
        for match in matches:
            wait_time, tb_state = tb(tb_state)
            self._highlight_spam_token_bucket_state = tb_state
            log.debug(wait_time, tb_state)
            if wait_time > 0:
                return True
        return False

    def _update_members_event_callback(self):
        self._members = MemberList()
        out_msg = self._out_msg_thread
        out_msg.add(self._ask_for_new_members)

    def _ask_for_new_members(self):
        log = self._log
        out_msg = self._out_msg_thread
        channel_name = self._channel_name
        log.notice('Clearing members set. Asking for members again.')
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

    def _shutdown(self):
        log = self._log
        self._update_members_event.stop()
        log.notice('ChanOpThread going away')

    def recv_line(self, type, line):
        self._message_queue.put((type, line))
