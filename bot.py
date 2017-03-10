#!/usr/bin/env python3
import sys
import subprocess
import signal
from datetime import datetime

nick_prefixes = ['@','+']
mention_limit = 10
server_dir = None
channel_name = None
server_out = None
channel_out = None
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

mention_suffixes = [':',',','!']

def usage(prog_name):
    print(prog_name,"<root-ii-server-dir> <channel>")

def log_debug(s):
    assert debug_fd
    debug_fd.write("[{}] {}\n".format(datetime.now(),s))

def log_notice(s):
    assert notice_fd
    notice_fd.write("[{}] {}\n".format(datetime.now(),s))

def log_warn(s):
    return log_notice(s)

def log_error(s):
    return log_notice(s)

def sigint(signum, stack_frame):
    global server_out
    global channel_out
    global notice_fd
    global debug_fd
    if server_out: server_out.terminate()
    if channel_out: channel_out.terminate()
    server_out, channel_out = None, None
    if notice_fd:
        log_notice("Shutting down bot due to signal")
    notice_fd.close()
    if debug_fd:
        debug_fd.close()
    notice_fd, debug_fd = None, None
    exit(0)

def sighup(signum, stack_frame):
    if notice_fd: notice_fd.flush()
    if debug_fd: debug_fd.flush()

def akick(nick, reason=None):
    with open(server_dir+'/in','w') as server_in:
        if not reason:
            log_notice('akicking {}'.format(nick))
            server_in.write('/privmsg chanserv akick {} add {}!*@*\n'.format(
                channel_name, nick))
        else:
            log_notice('akicking {} for {}'.format(nick, reason))
            server_in.write('/privmsg chanserv akick {} add {}!*@* {}\n'.format(
                channel_name, nick, reason))

def is_highlight_spam(words, members):
    words = [ w.lower() for w in words ]
    words = [ w for w in words if w not in common_words ]
    matches = set()
    for match in [ w for w in words if w in members ]:
        matches.add(match)
    for suff in mention_suffixes:
        for match in [ m for m in members if m+suff in words]:
            matches.add(match)
    num_nicks = len(matches)
    log_debug("{} nicks mentioned".format(num_nicks))
    if num_nicks > mention_limit: return True
    return False

def contains_banned_word(words):
    words = [ w.lower() for w in words ]
    for banned_word in banned_words:
        if banned_word in words: return True
    return False

def num_needles_in_haystack(hay, needles):
    found = set()
    for h in hay:
        if h in needles: found.add(h)
    return len(found)

def get_all_members():
    global server_out
    members = set()
    server_out = subprocess.Popen(['tail','-F','-n','0',server_dir+'/out'],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    with open(server_dir+'/in', 'w') as server_in:
        server_in.write('/names '+channel_name+'\n')
    while True:
        line = server_out.stdout.readline().decode('utf8')
        tokens = line.split()
        if tokens[2] in ['@', '='] and tokens[3] == channel_name:
            nicks = tokens[4:]
            for n in nicks:
                if n[0] in nick_prefixes: members.add(n[1:])
                else: members.add(n)
        elif tokens[2] == channel_name and tokens[3] == 'End' and \
            tokens[5] == '/NAMES':
            break
    server_out.terminate()
    server_out = None
    return members

def main(s_dir, c_name):
    global members
    global server_dir
    global channel_name
    global channel_out
    global notice_fd
    global debug_fd
    members = set()
    server_dir = s_dir
    channel_name = c_name
    channel_out = subprocess.Popen(
        ['tail','-F','-n','0',server_dir+'/'+channel_name+'/out'],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    notice_fd = open(server_dir+'/'+channel_name+'/notice.log', 'a')
    debug_fd = open(server_dir+'/'+channel_name+'/debug.log', 'a')
    log_notice("Starting up bot")
    members = get_all_members()
    log_debug("Starting members: {}".format(len(members)))
    while True:
        line = channel_out.stdout.readline().decode('utf8')
        #print(line)
        tokens = line.split()
        speaker = tokens[2]
        if speaker == '-!-':
            if tokens[4] == 'has' and tokens[5] == 'left':
                nick = tokens[3].split('(')[0]
                log_debug('{} left'.format(nick))
                members = set([ m for m in members if m != nick ])
            elif tokens[4] == 'has' and tokens[5] == 'joined':
                nick = tokens[3].split('(')[0]
                log_debug('{} joined'.format(nick))
                members.add(nick)
            # nick changes come in on server_out, not channel_out
            #elif tokens[4] == 'changed' and tokens[5] == 'nick' and tokens[6] == 'to':
            #    old_nick, new_nick = tokens[3], tokens[7]
            #    members = set([ m for m in members if m != old_nick ])
            #    members.add(new_nick)
            #    log_debug("{} changed to {}".format(old_nick, new_nick))
            else:
                log_debug("Ignoring unknown -!- message: {}".format(
                    ' '.join(tokens[3:])))
            continue
        if speaker[0] != '<' or speaker[-1] != '>':
            log_warn("Ignoring line with speaker {}".format(speaker))
            continue
        # remove < and >
        speaker = speaker[1:]
        speaker = speaker[:-1]
        # remove @
        if speaker[0] in nick_prefixes: speaker = speaker[1:]
        words = tokens[3:]
        if is_highlight_spam(words, members):
            akick(speaker, "highlight spam")
        if contains_banned_word(words):
            akick(speaker)
        #print(speaker+':',words)
        log_debug(speaker+': '+' '.join(words))
        #log_debug(str(members))
        #print(members)

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
