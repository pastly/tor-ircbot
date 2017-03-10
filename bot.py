#!/usr/bin/env python3
import selectors
import signal
import subprocess
import sys
from datetime import datetime

selector = selectors.DefaultSelector()

nick_prefixes = ['@','+']
mention_limit = 1
server_dir = None
channel_name = None
server_out = None
channel_out = None
privmsg_out = None
notice_fd = None
debug_fd = None

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

def usage(prog_name):
    print(prog_name,"<root-ii-server-dir> <channel>")

def log(fd, level, s):
    assert fd
    ts = datetime.now()
    fd.write('[{}] [{}] {}\n'.format(ts, level, s))

def log_debug(s):
    assert debug_fd
    return log(debug_fd, 'debug', s)

def log_notice(s):
    assert notice_fd
    return log(notice_fd, 'notice', s)

def log_warn(s):
    return log_notice(s)

def log_error(s):
    return log_notice(s)

def sigint(signum, stack_frame):
    global server_out
    global channel_out
    global privmsg_out
    global notice_fd
    global debug_fd
    if server_out: server_out.terminate()
    if channel_out: channel_out.terminate()
    if privmsg_out: privmsg_out.terminate()
    server_out, channel_out, privmsg_out = None, None, None
    if notice_fd:
        log_notice("Shutting down bot due to signal")
        notice_fd.close()
    if debug_fd:
        debug_fd.close()
    notice_fd, debug_fd = None, None
    exit(0)

def sighup(signum, stack_frame):
    if server_out: server_out.stdout.flush()
    if channel_out: channel_out.stdout.flush()
    if privmsg_out: privmsg_out.stdout.flush()
    if notice_fd: notice_fd.flush()
    if debug_fd: debug_fd.flush()

def akick(nick, reason=None):
    with open(server_dir+'/in','w') as server_in:
        if not reason:
            log_notice('akicking {}'.format(nick))
            #server_in.write('/privmsg chanserv akick {} add {}!*@*\n'.format(
            #    channel_name, nick))
        else:
            log_notice('akicking {} for {}'.format(nick, reason))
            #server_in.write('/privmsg chanserv akick {} add {}!*@* {}\n'.format(
            #    channel_name, nick, reason))

def is_highlight_spam(words):
    words = [ w.lower() for w in words ]
    words = [ w for w in words if w not in common_words ]
    matches = set()
    # first try straight nick mentions with no prefix/suffix obfuscation
    for match in [ w for w in words if w in members ]:
        matches.add(match)
    if len(matches) > mention_limit: return True
    # then try removing leading/trailing punctuation from words and see if
    # they then start to look like nicks. Not all punctuation is illegal
    punc = ''.join(non_nick_punctuation)
    for word in words:
        word = word.lstrip(punc).rstrip(punc)
        if word in members: matches.add(word)
    log_debug("{} nicks mentioned".format(len(matches)))
    if len(matches) > mention_limit: return True
    return False

def contains_banned_word(words):
    words = [ w.lower() for w in words ]
    for banned_word in banned_words:
        if banned_word in words: return True
    return False

def get_all_members():
    members = set()
    with open('{}/in'.format(server_dir), 'w') as server_in:
        server_in.write('/names {}\n'.format(channel_name))
    while True:
        line = server_out.stdout.readline().decode('utf8')
        tokens = line.split()
        # check if line is one that lists nicks in our channel. Starts with @ or
        #  =, then our channel name, then some nicks
        if tokens[2] in ['@', '='] and tokens[3] == channel_name:
            nicks = tokens[4:]
            # some nicks have prefixes for ops. Remove those prefixes
            for n in nicks:
                if n[0] in nick_prefixes: members.add(n[1:])
                else: members.add(n)
        # stop when we've found the end of the list
        elif tokens[2] == channel_name and tokens[3] == 'End' and \
            tokens[5] == '/NAMES':
            break
    return members

def member_add(nick):
    global members
    old_len = len(members)
    members.add(nick.lower())
    if len(members) <= old_len:
        log_warn('Adding {} to members didn\'t increase length'.format(nick))

def member_remove(nick):
    global members
    old_len = len(members)
    members.discard(nick.lower())
    if len(members) >= old_len:
        log_warn('Removing {} from members didn\'t decrease length'.format(
            nick))

def member_changed_nick(old_nick, new_nick):
    global members
    old_nick = old_nick.lower()
    new_nick = new_nick.lower()
    # we only want to add the new nick if the old nick was in our set
    old_len = len(members)
    member_remove(old_nick)
    if len(members) < old_len:
        member_add(new_nick)
        log_debug('{} --> {}'.format(old_nick, new_nick))

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
            log_debug('{} quit ({})'.format(nick,len(members)))
        else:
            log_warn('Ignorning unknown server ctrl message: {}'.format(
                ' '.join(words)))
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
            log_debug('{} left ({})'.format(nick,len(members)))
        elif ' '.join(words[1:3]) == 'has joined':
            nick = words[0].split('(')[0]
            member_add(nick)
            log_debug('{} joined ({})'.format(nick,len(members)))
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
    log_debug('privmsg: '+' '.join(tokens))

def main(s_dir, c_name):
    global members
    global server_dir
    global channel_name
    global server_out
    global channel_out
    global privmsg_out
    global notice_fd
    global debug_fd
    members = set()
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
    notice_fd = open('{}/{}/notice.log'.format(server_dir,channel_name), 'a')
    debug_fd = open('{}/{}/debug.log'.format(server_dir,channel_name), 'a')

    log_notice("Starting up bot")
    members = get_all_members()
    log_debug(members)
    log_debug("Starting members: {}".format(len(members)))

    selector.register(server_out.stdout, selectors.EVENT_READ,
        server_out_read_event)
    selector.register(channel_out.stdout, selectors.EVENT_READ,
        channel_out_read_event)
    selector.register(privmsg_out.stdout, selectors.EVENT_READ,
        privmsg_out_read_event)

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
