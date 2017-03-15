#!/usr/bin/env python3
import selectors
import os
import signal
import subprocess
import sys
from configparser import ConfigParser
from datetime import datetime
from pastlylogger import PastlyLogger
from repeatedtimer import RepeatedTimer
from threading import Thread, Event

selector = selectors.DefaultSelector()
log = None

config = ConfigParser()
config.read('config.ini')

# need to be all lowercase
masters = ['pastly']

is_shutting_down = Event()
nick_prefixes = ['@','+']
mention_limit = 10
members = set()
#members_lock = Lock()
server_dir = None
channel_name = None
ii_process = None
server_out_process = None
channel_out_process = None
privmsg_out_process = None
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

# True if successful
def set_mention_limit(value):
    global mention_limit
    if len(value) != 1:
        log.warn('Ignorning mention_limit: {}'.format(value))
        return False
    value = value[0]
    try:
        value = int(value)
    except (TypeError, ValueError):
        log.warn('Ignoring non-int mention_limit: {}'.format(value))
        return False
    mention_limit = value
    return True

def get_mention_limit():
    return mention_limit

# True if successful
def set_update_members_interval(value):
    if len(value) != 1:
        log.warn('Ignoring update_members_interval: {}'.format(value))
        return False
    value = value[0]
    try:
        value = int(value)
    except (TypeError, ValueError):
        log.warn('Ignoring non-int update_members_interval: {}'.format(value))
    if value <= 0: value = 0
    update_members_event.interval = value
    update_members_event.stop()
    if value > 0: update_members_event.start()
    return True

def get_update_members_interval():
    return update_members_event.interval

options = {
    'mention_limit': (set_mention_limit, get_mention_limit),
    'update_members_interval':
        (set_update_members_interval, get_update_members_interval),
}

def usage(prog_name):
    print(prog_name,"<root-ii-server-dir> <channel>")

def sigint(signum, stack_frame):
    global ii_process
    global server_out_process
    global channel_out_process
    global privmsg_out_process
    global update_members_event
    log.notice("Shutting down bot due to signal")
    is_shutting_down.set()
    if ii_process:
        try: ii_process.terminate()
        except ProcessLookupError: pass
    if server_out_process: server_out_process.terminate()
    if channel_out_process: channel_out_process.terminate()
    if privmsg_out_process: privmsg_out_process.terminate()
    ii_process = None
    server_out_process, channel_out_process = None, None
    privmsg_out_process = None
    if update_members_event: update_members_event.stop()
    update_members_event = None
    exit(0)

def sighup(signum, stack_frame):
    if server_out_process: server_out_process.stdout.flush()
    if channel_out_process: channel_out_process.stdout.flush()
    if privmsg_out_process: privmsg_out_process.stdout.flush()
    log.flush()

def privmsg(nick, message):
    with open(server_dir+'/in', 'w') as server_in:
        server_in.write('/privmsg {} {}\n'.format(nick, message))

def ping(nick):
    return privmsg(nick, 'pong')

def akick(nick, reason=None):
    if not reason:
        log.notice('akicking {}'.format(nick))
        privmsg('chanserv', 'akick {} add {}!*@*\n'.format(
            channel_name, nick))
    else:
        log.notice('akicking {} for {}'.format(nick, reason))
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
    log.debug("{} nicks mentioned".format(len(matches)))
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
        log.warn('Adding {} to members didn\'t increase length'.format(nick))
    #members_lock.release()

def member_remove(nick):
    global members
    #members_lock.acquire()
    old_len = len(members)
    members.discard(nick.lower())
    if len(members) >= old_len:
        log.warn('Removing {} from members didn\'t decrease length'.format(
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
        log.debug('{} --> {}'.format(old_nick, new_nick))
    #members_lock.release()

def set_option(option, value):
    if option not in options:
        log.warn('Ignoring unknown option: {}'.format(option))
        return False
    return options[option][0](value)

def get_option(option):
    if option not in options:
        log.warn('Ignoring unknown option: {}'.format(option))
        return None
    return options[option][1]()

def server_out_process_read_event(fd, mask):
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
            log.debug('{} quit ({})'.format(nick,len(members)))
            #members_lock.release()
        else:
            log.warn('Ignorning unknown server ctrl message: {}'.format(
                ' '.join(words)))
    elif speaker in ['@','=']:
        if words[0] == channel_name:
            for w in words[1:]:
                if w[0] in nick_prefixes: member_add(w[1:])
                else: member_add(w)
            #members_lock.acquire()
            log.debug('Got {} more names. {} total'.format(len(words[1:]),
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
            log.debug('Ignoring unrecognized server ctrl message coming from '+
                '{}: {}'.format(channel_name, ' '.join(words)))
    else:
        log.warn('Ignoring server ctrl message with unknown speaker: {}'.format(
            speaker))

def channel_out_process_read_event(fd, mask):
    line = fd.readline().decode('utf8')
    tokens = line.split()
    speaker = tokens[2]
    words = tokens[3:]
    if speaker == '-!-':
        if ' '.join(words[1:3]) == 'has left':
            nick = words[0].split('(')[0]
            member_remove(nick)
            #members_lock.acquire()
            log.debug('{} left ({})'.format(nick,len(members)))
            #members_lock.release()
        elif ' '.join(words[1:3]) == 'has joined':
            nick = words[0].split('(')[0]
            member_add(nick)
            #members_lock.acquire()
            log.debug('{} joined ({})'.format(nick,len(members)))
            #members_lock.release()
        else:
            log.warn('Ignoring unknown channel ctrl message: {}'.format(
                ' '.join(words)))
    elif speaker[0] != '<' or speaker[-1] != '>':
        log.debug('Ignoring channel message with weird speaker: {}'.format(
            speaker))
    else:
        speaker = speaker[1:-1].lower()
        log.debug('<{}> {}'.format(speaker, ' '.join(words)))
        if is_highlight_spam(words):
            akick(speaker, 'highlight spam')
            member_remove(speaker)

def privmsg_out_process_read_event(fd, mask):
    line = fd.readline().decode('utf8')
    tokens = line.split()
    speaker = tokens[2]
    words = tokens[3:]
    if speaker[0] != '<' or speaker[-1] != '>':
        log.warn('Ignoring privmsg with weird speaker: {}'.format(speaker))
        return
    speaker = speaker[1:-1].lower()
    if speaker not in masters:
        log.warn('Ignoring privmsg from non-master: {}'.format(speaker))
        return
    if ' '.join(words) == 'ping':
        log.debug('master {} pinged us'.format(speaker))
        ping(speaker)
    elif words[0] == 'set':
        if len(words) < 3:
            log.warn('Ignoring bad set command from {}: {}'.format(
                speaker, ' '.join(words)))
            return
        if not set_option(words[1], words[2:]):
            privmsg(speaker, 'Failed to set {} to {}'.format(
                words[1], ' '.join(words[2:])))
        else:
            log.notice('{} set {} to {}'.format(
                speaker, words[1], ' '.join(words[2:])))
            privmsg(speaker, '{} is {}'.format(words[1], get_option(words[1])))
    elif words[0] == 'get':
        if len(words) != 2:
            log.warn('Ignoring bad get command from {}: {}'.format(
                speaker, ' '.join(words)))
            return
        value = get_option(words[1])
        privmsg(speaker, '{} is {}'.format(words[1], value))
    elif words[0] == 'options':
        privmsg(speaker, ' '.join(options))
    else:
        log.debug('master {} said "{}" but we don\'t have a response'.format(
            speaker, ' '.join(words)))

def ask_for_new_members():
    global members
    log.debug('Clearing members set. Asking for members again')
    #members_lock.acquire()
    members = set()
    #members_lock.release()
    with open('{}/in'.format(server_dir), 'w') as server_in:
        server_in.write('/names {}\n'.format(channel_name))

def update_members_event_callback():
    ask_for_new_members()

def prepare_ircdir():
    os.makedirs(os.path.join(server_dir,channel_name), exist_ok=True)

def ii_thread():
    global ii_process
    assert not ii_process
    prepare_ircdir()
    nick = config['ii']['nick']
    server = config['ii']['server']
    port = config['ii']['port']
    server_pass = config['ii']['server_pass']
    ircdir = config['ii']['ircdir']
    while True:
        if log: log.notice('(Re)Starting ii process')
        ii_process = subprocess.Popen(
            ['ii','-i',ircdir,'-s',server,'-p',port,'-n',nick,'-k','PASS'],
            env={'PATH': '/usr/local/bin:$PATH', 'PASS': server_pass},
        )
        ii_process.wait()
        log.warn('ii process went away')
        if is_shutting_down.wait(5): break
    log.notice('Stopping ii process for good')

def main():
    global server_dir
    global channel_name
    global server_out_process
    global channel_out_process
    global privmsg_out_process
    global update_members_event
    global log

    server_dir = os.path.join(config['ii']['ircdir'],config['ii']['server'])
    channel_name = config['ii']['channel']

    t = Thread(target=ii_thread, name='ii watchdog')
    t.start()

    # bufsize=1 means line-based buffering. Perfect for IRC :)
    server_out_process = subprocess.Popen(
        ['tail','-F','-n','0','{}/out'.format(server_dir)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        bufsize=1)
    channel_out_process = subprocess.Popen(
        ['tail','-F','-n','0','{}/{}/out'.format(server_dir,channel_name)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        bufsize=1)
    privmsg_out_process = subprocess.Popen(
        ['tail','-F','-n','0','{}/pastly_bot/out'.format(
        server_dir,channel_name)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        bufsize=1)


    log = PastlyLogger(
        debug='{}/{}/debug.log'.format(server_dir, channel_name),
    )
    log.notice("Starting up bot")

    update_members_event_callback()


    selector.register(server_out_process.stdout, selectors.EVENT_READ,
        server_out_process_read_event)
    selector.register(channel_out_process.stdout, selectors.EVENT_READ,
        channel_out_process_read_event)
    selector.register(privmsg_out_process.stdout, selectors.EVENT_READ,
        privmsg_out_process_read_event)

    update_members_event = RepeatedTimer(3600, update_members_event_callback)
    while True:
        events = selector.select()
        for key, mask in events:
            callback = key.data
            callback(key.fileobj, mask)

if __name__=='__main__':
    signal.signal(signal.SIGINT, sigint)
    signal.signal(signal.SIGTERM, sigint)
    signal.signal(signal.SIGHUP, sighup)
    main()
