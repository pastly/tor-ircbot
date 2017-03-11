#!/usr/bin/env python3
import selectors
import signal
import subprocess
import sys
from datetime import datetime
from repeatedtimer import RepeatedTimer
#from threading import Lock

selector = selectors.DefaultSelector()

# need to be all lowercase
masters = ['pastly']

nick_prefixes = ['@','+']
mention_limit = 10
members = set()
#members_lock = Lock()
server_dir = None
channel_name = None
server_out = None
channel_out = None
privmsg_out = None
debug_fd = None
notice_fd = None
warn_fd = None
error_fd = None
update_members_event = None

banned_words = \
[]

common_words = \
['the','be','to','of','and','a','in','that','have','i','it','for','not','on',
'with','he','as','you','do','at','this','but','his','by','from','they','we',
'say','her','she','or','an','will','my','one','all','would','there','their',
'what','so','up','out','if','about','who','get','which','go','me','when',
'make','can','like','time','no','just','him','know','take','people','into',
'year','your','good','some','could','them','see','other','than','then','now',
'look','only','come','its','over','thnk','also','back','after','use','two',
'how','our','work','first','well','way','even','new','want','because','any',
'these','give','day','most','us']

non_nick_punctuation = [':',',','!','?']
non_nick_punctuation.extend(nick_prefixes)

def usage(prog_name):
    print(prog_name,"<root-ii-server-dir> <channel>")

def log(fd, s, level):
    assert fd
    ts = datetime.now()
    fd.write('[{}] [{}] {}\n'.format(ts, level, s))

def log_debug(s, level='debug'):
    if debug_fd:
        return log(debug_fd, s, level)
    return None

def log_notice(s, level='notice'):
    if notice_fd:
        return log(notice_fd, s, level)
    else:
        return log_debug(s, level)

def log_warn(s, level='warn'):
    if warn_fd:
        return log(warn_fd, s, level)
    else:
        return log_notice(s, level)

def log_error(s, level='error'):
    if error_fd:
        return log(error_fd, s, level)
    else:
        return log_warn(s, level)

def sigint(signum, stack_frame):
    global server_out
    global channel_out
    global privmsg_out
    global debug_fd
    global notice_fd
    global warn_fd
    global error_fd
    global update_members_event
    log_notice("Shutting down bot due to signal")
    if server_out: server_out.terminate()
    if channel_out: channel_out.terminate()
    if privmsg_out: privmsg_out.terminate()
    server_out, channel_out, privmsg_out = None, None, None
    if debug_fd: debug_fd.close()
    if notice_fd: notice_fd.close()
    if warn_fd: warn_fd.close()
    if error_fd: error_fd.close()
    debug_fd, notice_fd, warn_fd, error_fd = None, None, None, None
    if update_members_event: update_members_event.stop()
    update_members_event = None
    exit(0)

def sighup(signum, stack_frame):
    if server_out: server_out.stdout.flush()
    if channel_out: channel_out.stdout.flush()
    if privmsg_out: privmsg_out.stdout.flush()
    if debug_fd: debug_fd.flush()
    if notice_fd: notice_fd.flush()
    if warn_fd: warn_fd.flush()
    if error_fd: error_fd.flush()

def privmsg(nick, message):
    with open(server_dir+'/in', 'w') as server_in:
        server_in.write('/privmsg {} {}\n'.format(nick, message))

def ping(nick):
    return privmsg(nick, 'pong')

def akick(nick, reason=None):
    if not reason:
        log_notice('akicking {}'.format(nick))
        privmsg('chanserv', 'akick {} add {}!*@*\n'.format(
            channel_name, nick))
    else:
        log_notice('akicking {} for {}'.format(nick, reason))
        privmsg('chanserv', 'akick {} add {}!*@* {}\n'.format(
            channel_name, nick, reason))

def is_highlight_spam(words):
    words = [ w.lower() for w in words ]
    words = [ w for w in words if w not in common_words ]
    #members_lock.acquire()
    members_ = members # grab local copy in order to not hold lock
    #members_lock.release()
    matches = set()
    # first try straight nick mentions with no prefix/suffix obfuscation
    for match in [ w for w in words if w in members_ ]:
        matches.add(match)
    if len(matches) > mention_limit: return True
    # then try removing leading/trailing punctuation from words and see if
    # they then start to look like nicks. Not all punctuation is illegal
    punc = ''.join(non_nick_punctuation)
    for word in words:
        word = word.lstrip(punc).rstrip(punc)
        if word in members_: matches.add(word)
    log_debug("{} nicks mentioned".format(len(matches)))
    if len(matches) > mention_limit: return True
    return False

def contains_banned_word(words):
    words = [ w.lower() for w in words ]
    for banned_word in banned_words:
        if banned_word in words: return True
    return False

def member_add(nick):
    global members
    #members_lock.acquire()
    old_len = len(members)
    members.add(nick.lower())
    if len(members) <= old_len:
        log_warn('Adding {} to members didn\'t increase length'.format(nick))
    #members_lock.release()

def member_remove(nick):
    global members
    #members_lock.acquire()
    old_len = len(members)
    members.discard(nick.lower())
    if len(members) >= old_len:
        log_warn('Removing {} from members didn\'t decrease length'.format(
            nick))
    #members_lock.release()

def member_changed_nick(old_nick, new_nick):
    global members
    #members_lock.acquire()
    old_nick = old_nick.lower()
    new_nick = new_nick.lower()
    # we only want to add the new nick if the old nick was in our set
    old_len = len(members)
    member_remove(old_nick)
    if len(members) < old_len:
        member_add(new_nick)
        log_debug('{} --> {}'.format(old_nick, new_nick))
    #members_lock.release()

def server_out_read_event(fd, mask):
    line = fd.readline().decode('utf8')
    tokens = line.split()
    speaker = tokens[2]
    words = tokens[3:]
    if speaker == '-!-':
        if ' '.join(words[1:4]) == 'changed nick to':
            old_nick = words[0]
            new_nick = words[4]
            member_changed_nick(old_nick, new_nick)
        elif ' '.join(words[1:3]) == 'has quit':
            nick = words[0].split('(')[0]
            member_remove(nick)
            #members_lock.acquire()
            log_debug('{} quit ({})'.format(nick,len(members)))
            #members_lock.release()
        else:
            log_warn('Ignorning unknown server ctrl message: {}'.format(
                ' '.join(words)))
    elif speaker in ['@','=']:
        if words[0] == channel_name:
            for w in words[1:]:
                if w[0] in nick_prefixes: member_add(w[1:])
                else: member_add(w)
            #members_lock.acquire()
            log_debug('Got {} more names. {} total'.format(len(words[1:]),
                len(members)))
            #members_lock.release()
    elif speaker == channel_name:
        # this is __probably__ just telling us we've reached the end of the
        # /NAMES list, but since I don't know what's going to get added after
        # 6 months after writing this comment, I think logging in this condition
        # would be smart
        if ' '.join(words) == 'End of /NAMES list.':
            pass
        else:
            log_debug('Ignoring unrecognized server ctrl message coming from '+
                '{}: {}'.format(channel_name, ' '.join(words)))
    else:
        log_warn('Ignoring server ctrl message with unknown speaker: {}'.format(
            speaker))

def channel_out_read_event(fd, mask):
    line = fd.readline().decode('utf8')
    tokens = line.split()
    speaker = tokens[2]
    words = tokens[3:]
    if speaker == '-!-':
        if ' '.join(words[1:3]) == 'has left':
            nick = words[0].split('(')[0]
            member_remove(nick)
            #members_lock.acquire()
            log_debug('{} left ({})'.format(nick,len(members)))
            #members_lock.release()
        elif ' '.join(words[1:3]) == 'has joined':
            nick = words[0].split('(')[0]
            member_add(nick)
            #members_lock.acquire()
            log_debug('{} joined ({})'.format(nick,len(members)))
            #members_lock.release()
        else:
            log_warn('Ignoring unknown channel ctrl message: {}'.format(
                ' '.join(words)))
    elif speaker[0] != '<' or speaker[-1] != '>':
        log_debug('Ignoring channel message with weird speaker: {}'.format(
            speaker))
    else:
        speaker = speaker[1:-1].lower()
        log_debug('{}: {}'.format(speaker, ' '.join(words)))
        if is_highlight_spam(words):
            akick(speaker, 'highlight spam')

def privmsg_out_read_event(fd, mask):
    line = fd.readline().decode('utf8')
    tokens = line.split()
    speaker = tokens[2]
    words = tokens[3:]
    if speaker[0] != '<' or speaker[-1] != '>':
        log_warn('Ignoring privmsg with weird speaker: {}'.format(speaker))
        return
    speaker = speaker[1:-1].lower()
    if speaker not in masters:
        log_warn('Ignoring privmsg from non-master: {}'.format(speaker))
        return
    if ' '.join(words) == 'ping':
        log_debug('master {} pinged us'.format(speaker))
        ping(speaker)
    else:
        log_debug('master {} said "{}" but we don\'t have a response'.format(
            speaker, ' '.join(words)))

def ask_for_new_members():
    global members
    log_debug('Clearing members set. Asking for members again')
    #members_lock.acquire()
    members = set()
    #members_lock.release()
    with open('{}/in'.format(server_dir), 'w') as server_in:
        server_in.write('/names {}\n'.format(channel_name))

def update_members_event_callback():
    ask_for_new_members()

def main(s_dir, c_name):
    global server_dir
    global channel_name
    global server_out
    global channel_out
    global privmsg_out
    global debug_fd
    global notice_fd
    global warn_fd
    global error_fd
    global update_members_event
    server_dir = s_dir
    channel_name = c_name
    server_out = subprocess.Popen(
        ['tail','-F','-n','0','{}/out'.format(server_dir)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    channel_out = subprocess.Popen(
        ['tail','-F','-n','0','{}/{}/out'.format(server_dir,channel_name)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    privmsg_out = subprocess.Popen(
        ['tail','-F','-n','0','{}/pastly_bot/out'.format(
        server_dir,channel_name)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    debug_fd = open('{}/{}/debug.log'.format(server_dir,channel_name), 'a')
    #notice_fd = open('{}/{}/notice.log'.format(server_dir,channel_name), 'a')
    #warn_fd = open('{}/{}/warn.log'.format(server_dir,channel_name), 'a')
    #error_fd = open('{}/{}/error.log'.format(server_dir,channel_name), 'a')

    log_notice("Starting up bot")
    update_members_event_callback()

    selector.register(server_out.stdout, selectors.EVENT_READ,
        server_out_read_event)
    selector.register(channel_out.stdout, selectors.EVENT_READ,
        channel_out_read_event)
    selector.register(privmsg_out.stdout, selectors.EVENT_READ,
        privmsg_out_read_event)

    update_members_event = RepeatedTimer(300, update_members_event_callback)
    while True:
        events = selector.select()
        for key, mask in events:
            callback = key.data
            callback(key.fileobj, mask)

if __name__=='__main__':
    signal.signal(signal.SIGINT, sigint)
    signal.signal(signal.SIGTERM, sigint)
    signal.signal(signal.SIGHUP, sighup)
    if len(sys.argv) < 3:
        usage(sys.argv[0])
        exit(1)
    server_dir = sys.argv[1]
    channel_name = sys.argv[2]
    main(server_dir, channel_name)
