#!/usr/bin/env python3
import os
import signal
import subprocess
# python stuff
from configparser import ConfigParser
from multiprocessing import Event, Process, Queue
from threading import Timer
from time import time
from queue import Empty
from random import randint
# custom stuff
from actionqueue import ActionQueue
from member import Member, MemberList
from pastlylogger import PastlyLogger
from repeatedtimer import RepeatedTimer
from tokenbucket import token_bucket

# TODO: make 'word in MemberList' work but having __iter__ return keys

log = None

config_file = 'config.ini'
config = ConfigParser()
config.read(config_file)

# need to be all lowercase XXX: still true?
# people that can PM the bot
masters = ['pastly']

# booleans for inter-thread signaling
is_shutting_down = Event()
is_getting_members = Event()
is_operator = Event()
# chars that could come before a nick but are not part of the nick
nick_prefixes = ['@','+']
members = MemberList()
# action queue for the main process's main loop
main_action_queue = ActionQueue(long_timeout=60)
# action queue for a process for handling outgoing messages
outbound_message_queue = ActionQueue(long_timeout=5,
    time_between_actions_func=token_bucket(5, 0.505))
# a process that waits for outbound messages that should be sent while we have
# operator status. It is created the first time we need ops, and lives as long
# as we need it, and then dies when we haven't needed it for some timeout.
as_operator = None
# a queue for the above process to accept messages on
as_operator_queue = Queue()
server_dir = None
channel_name = None
update_members_event = None

default_sigint = signal.getsignal(signal.SIGINT)
default_sigterm = signal.getsignal(signal.SIGTERM)
default_sighup = signal.getsignal(signal.SIGHUP)

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

mask_keywords = {
    'nick': '{}!*@*',
    '*nick': '*{}!*@*',
    'nick*': '{}*!*@*',
    '*nick*': '*{}*!*@*',
    'user': '*!{}@*',
    '*user': '*!*{}@*',
    'user*': '*!{}*@*',
    '*user*': '*!*{}*@*',
    'host': '*!*@{}',
    '*host': '*!*@*{}',
    'host*': '*!*@{}*',
    '*host*': '*!*@*{}*',
}

processes = []

non_nick_punctuation = [':',',','!','?']
non_nick_punctuation.extend(nick_prefixes)

# True if successful
def set_mention_limit(value):
    if len(value) != 1:
        log.warn('Ignorning mention_limit: {}'.format(value))
        return False
    value = value[0]
    try:
        _ = int(value)
    except (TypeError, ValueError):
        log.warn('Ignoring non-int mention_limit: {}'.format(value))
        return False
    config['highlight_spam']['mention_limit'] = value
    return True

def get_mention_limit():
    return int(config['highlight_spam']['mention_limit'])

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
        return False
    if value <= 0: value = 0
    config['general']['update_members_interval'] = str(value)
    update_members_event.interval = value
    update_members_event.stop()
    if value > 0: update_members_event.start()
    return True

def get_update_members_interval():
    return update_members_event.interval

# True if successful
def set_enforce_highlight_spam(value):
    if len(value) != 1:
        log.warn('Ignoring enforce_highlight_spam: {}'.format(value))
        return False
    value = value[0]
    try:
        if value == 'True': value = True
        elif value == 'False': value = False
        else:
            log.warn('Ignoring non-bool enforce_highlight_spam: {}'.format(
                value))
            return False
    except (TypeError, ValueError):
        log.warn('Ignoring non-bool enforce_highlight_spam: {}'.format(value))
        return False
    config['highlight_spam']['enabled'] = str(value)
    return True

def get_enforce_highlight_spam():
    return config.getboolean('highlight_spam', 'enabled', fallback=False)

# Each key is an option that can be set
# Each value is a tuple of (func_to_set_opt, func_to_get_opt)
#
# The setter must take a single argument and return True if it was set
# successfully. Otherwise return False.
#
# The convention in this file is for the single value argument in the setters to
# be a list of strings. If one value is expected, len(list) should equal 1.
# If ints are required, try casting to int and cleanly return False on error.
# See set_update_members_interval for an example of both these things.
options = {
    'mention_limit': (set_mention_limit, get_mention_limit),
    'update_members_interval':
        (set_update_members_interval, get_update_members_interval),
    'enforce_highlight_spam':
        (set_enforce_highlight_spam, get_enforce_highlight_spam),
}

def set_ignore_signals():
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

def set_default_signals():
    signal.signal(signal.SIGINT, default_sigint)
    signal.signal(signal.SIGTERM, default_sigterm)
    signal.signal(signal.SIGHUP, default_sighup)

def set_our_signals():
    signal.signal(signal.SIGINT, sigint)
    signal.signal(signal.SIGTERM, sigint)
    signal.signal(signal.SIGHUP, sighup)

def sigint(signum, stack_frame):
    print('Shutting down cleanly due to signal. Some processes might take '
        'a few seconds to fully quit.\n'
        'Wait a minute before forcfully killing us. :( It could be messy')
    log.notice("Shutting down bot due to signal")
    is_shutting_down.set()
    if update_members_event: update_members_event.stop()
    exit(0)

def sighup(signum, stack_frame):
    #for p in processes: p.stdout.flush()
    #log.flush()
    pass

# should only be called from outbound_message_queue
def servmsg(message):
    with open(server_dir+'/in', 'w') as server_in:
        server_in.write('{}\n'.format(message))

def privmsg(nick, message):
    servmsg('/privmsg {} {}'.format(nick, message))

def ping(nick):
    privmsg(nick, 'pong')

# must be called from as_operator_process
def chanserv_add_to_list(action, mask, reason=None):
    if not reason:
        log.notice('{}ing {}'.format(action, mask))
        outbound_message_queue.add(privmsg, [
            'chanserv', '{} {} add {}'.format(action, channel_name, mask)
        ])
    else:
        log.notice('{}ing {} for {}'.format(action, mask, reason))
        outbound_message_queue.add(privmsg, [
            'chanserv', '{} {} add {} {}'.format(
            action, channel_name, mask, reason)
        ])

# must be called from as_operator_process
def akick(mask, reason=None):
    chanserv_add_to_list('akick', mask, reason)

# must be called from as_operator_process
def quiet(mask, reason=None):
    chanserv_add_to_list('quiet', mask, reason)

def is_highlight_spam(words):
    words = [ w.lower() for w in words ]
    words = [ w for w in words if w not in common_words ]
    matches = set()
    # first try straight nick mentions with no prefix/suffix obfuscation
    for match in [ w for w in words if members.contains(w) ]:
        matches.add(match)
    if len(matches) > get_mention_limit(): return True
    # then try removing leading/trailing punctuation from words and see if
    # they then start to look like nicks. Not all punctuation is illegal
    punc = ''.join(non_nick_punctuation)
    for word in words:
        word = word.lstrip(punc).rstrip(punc)
        if members.contains(word): matches.add(word)
    log.debug("{} nicks mentioned".format(len(matches)))
    if len(matches) > get_mention_limit(): return True
    return False

def contains_banned_word(words):
    words = [ w.lower() for w in words ]
    for banned_word in banned_words:
        if banned_word in words: return True
    return False

# must be called from the main process
def perform_with_ops(func, args=None, kwargs=None):
    global as_operator
    if as_operator == None or not as_operator.is_alive():
        set_ignore_signals()
        as_operator = Process(target=as_operator_process)
        as_operator.start()
        set_our_signals()
    as_operator_queue.put( (func, args, kwargs) )

def member_add(nick, user=None, host=None):
    old_len = len(members)
    members.add(nick, user, host)
    if len(members) <= old_len:
        log.warn('Adding {} to members didn\'t increase length'.format(nick))

def member_remove(nick):
    old_len = len(members)
    members.discard(nick)
    if len(members) >= old_len:
        log.warn('Removing {} from members didn\'t decrease length'.format(
            nick))

def member_changed_nick(old_nick, new_nick):
    member = members[old_nick]
    if not member:
        log.warn('Don\'t know about {}; can\'t change nick to {}'.format(
            old_nick, new_nick))
        return
    member.set(nick=new_nick)
    log.debug('{} --> {}'.format(old_nick, new_nick))

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

def save_config(filename):
    with open(filename, 'w') as f:
        config.write(f)

# must be called from the main process
def server_out_process_line(line):
    if not len(line): return
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
            log.info('{} quit ({})'.format(nick,len(members)))
        else:
            log.debug('Ignorning unknown server ctrl message: {}'.format(
                ' '.join(words)))
    elif speaker == channel_name:
        if ' '.join(words) == 'End of /WHO list.':
            is_getting_members.clear()
        elif len(words) >= 7 and is_getting_members.is_set():
            # should be output from a /WHO #channel_name query
            user, host, server, nick, unknown1, unknown2 = words[0:6]
            member_add(nick, user=user, host=host)
            log.info('Adding {} ({})'.format(nick, len(members)))
    else:
        log.debug('Ignoring server ctrl message with unknown speaker: {}'.format(
            speaker))

# must be called from the main process
def channel_out_process_line(line):
    if not len(line): return
    tokens = line.split()
    speaker = tokens[2]
    words = tokens[3:]
    if speaker == '-!-':
        if ' '.join(words[1:3]) == 'has left':
            nick = words[0].split('(')[0]
            member_remove(nick)
            log.info('{} left ({})'.format(nick,len(members)))
        elif ' '.join(words[1:3]) == 'has joined':
            full_member = words[0]
            try:
                nick = full_member.split('(')[0]
                user = full_member.split('(')[1].split('@')[0]
                host = full_member.split('@')[1].split(')')[0]
            except IndexError:
                log.error('Couldn\'t parse nick/user/host: {}'.format(
                    full_member))
                return
            member_add(nick, user, host)
            log.info('{} joined ({})'.format(nick,len(members)))
        elif ' '.join(words[1:3]) == 'changed mode/{}'.format(channel_name):
            who = words[0]
            mode = words[4]
            arg = words[5] if len(words) >= 6 else None
            if mode == '+o' and arg == 'pastly_bot':
                is_operator.set()
            elif mode == '-o' and arg == 'pastly_bot':
                is_operator.clear()
            return
        else:
            log.debug('Ignoring unknown channel ctrl message: {}'.format(
                ' '.join(words)))
    elif speaker[0] != '<' or speaker[-1] != '>':
        log.debug('Ignoring channel message with weird speaker: {}'.format(
            speaker))
    else:
        speaker = speaker[1:-1].lower()
        log.debug('<{}> {}'.format(speaker, ' '.join(words)))
        if get_enforce_highlight_spam() and is_highlight_spam(words):
            akick(speaker, 'highlight spam')

# must be called from the main process
def privmsg_out_process_line(line):
    if not len(line): return
    tokens = line.split()
    speaker = tokens[2]
    words = tokens[3:]
    if speaker[0] != '<' or speaker[-1] != '>':
        log.info('Ignoring privmsg with weird speaker: {}'.format(speaker))
        return
    speaker = speaker[1:-1].lower()
    if speaker not in masters:
        log.warn('Ignoring privmsg from non-master: {}'.format(speaker))
        return
    if ' '.join(words).lower() == 'ping':
        log.info('master {} pinged us'.format(speaker))
        outbound_message_queue.add(ping, [speaker])
        return
    elif words[0].lower() == 'set':
        if len(words) < 3:
            outbound_message_queue.add(privmsg,
                [speaker, 'set <option> <value>'])
            return
        if not set_option(words[1], words[2:]):
            outbound_message_queue.add(privmsg, [speaker,
                'Failed to set {} to {}'.format(words[1], ' '.join(words[2:]))])
            return
        else:
            log.notice('{} set {} to {}'.format(
                speaker, words[1], ' '.join(words[2:])))
            outbound_message_queue.add(privmsg,
                [speaker, '{} is {}'.format(words[1], get_option(words[1]))])
            return
    elif words[0].lower() == 'get':
        if len(words) != 2:
            outbound_message_queue.add(privmsg, [speaker, 'get <option>'])
            return
        value = get_option(words[1])
        outbound_message_queue.add(privmsg,
            [speaker, '{} is {}'.format(words[1], value)])
        return
    elif words[0].lower() == 'options':
        outbound_message_queue.add(privmsg, [speaker, ' '.join(options)])
    elif words[0].lower() == 'save':
        if len(words) != 2:
            outbound_message_queue.add(privmsg, [speaker, 'save config'])
            return
        if words[1].lower() == 'config':
            save_config(config_file)
            outbound_message_queue.add(privmsg, [speaker, 'saved config'])
            log.notice('{} saved config to {}'.format(speaker, config_file))
        return
    elif words[0].lower() == 'match':
        if len(words) != 3:
            outbound_message_queue.add(privmsg, [speaker,
                'match <nick> <\'user\'|\'host\'|\'both\'>'])
            return
        nick = words[1]
        if not members.contains(nick):
            outbound_message_queue.add(privmsg,
                [speaker, '{} not in members'.format(nick)])
            log.info('{} asked to match {}, but couldn\'t find nick'.format(
                speaker, nick))
            return
        search_user, search_host = False, False
        if words[2].lower() == 'user': search_user = True
        elif words[2].lower() == 'host': search_host = True
        elif words[2].lower() == 'both': search_user, search_host = True, True
        if not search_user and not search_host:
            outbound_message_queue.add(privmsg,
                [speaker, 'need to match {}\'s user, host, or both'.format(
                nick)])
            return
        omq = outbound_message_queue
        if search_user:
            user = members[nick].user
            matches = members.matches(user=user)
            matches = [ m for m in matches if m.nick.lower() != nick.lower() ]
            if len(matches) < 1:
                omq.add(privmsg, [speaker, 'Just {}'.format(members[nick])])
            else:
                omq.add(privmsg,
                    [speaker, 'Members matching {}\'s user:'.format(nick)])
                for m in matches:
                    omq.add(privmsg, [speaker, '\t{}'.format(m)])
        if search_host:
            host = members[nick].host
            matches = members.matches(host=host)
            matches = [ m for m in matches if m.nick.lower() != nick.lower() ]
            if len(matches) < 1:
                omq.add(privmsg, [speaker, 'Just {}'.format(members[nick])])
            else:
                omq.add(privmsg,
                    [speaker, 'Members matching {}\'s host:'.format(nick)])
                for m in matches:
                    omq.add(privmsg, [speaker, '\t{}'.format(m)])
        return
    elif words[0].lower() == 'info':
        if len(words) != 2:
            outbound_message_queue.add(privmsg, [speaker, 'info <nick>'])
            return
        nick = words[1]
        member = members[nick]
        if not member:
            outbound_message_queue.add(privmsg,
                [speaker, '{} not found'.format(nick)])
            return
        outbound_message_queue.add(privmsg, [speaker, member])
        return
    elif words[0].lower() == 'mode':
        if len(words) != 2 and len(words) != 3:
            outbound_message_queue.add(privmsg,
                [speaker, 'mode <+|-><R|l|i> [var]'])
            return
        flag = words[1]
        arg = None
        if len(words) == 3: arg = words[2]
        # Generic sanity check
        if len(flag) != 2 or flag[0] not in ['+', '-'] or \
            flag[1] not in ['R', 'l', 'i']:
            outbound_message_queue.add(privmsg,
                [speaker, 'Invalid mode command'])
            return
        # Make sure most flags don't have an argument
        if flag[1] in ['R', 'i'] and arg != None:
            outbound_message_queue.add(privmsg,
                [speaker, '{} can\'t have arg'])
            return
        # +l requires an argument
        if flag == '+l' and arg == None:
            outbound_message_queue.add(privmsg,
                [speaker, '+l requires int arg'])
            return
        # +l's argument must be an int
        elif flag == '+l':
            try: arg = int(arg)
            except (TypeError, ValueError):
                outbound_message_queue.add(privmsg,
                    [speaker, '+l requires int arg'])
                return
        # -l can't have an argument
        if flag == '-l' and arg != None:
            outbound_message_queue.add(privmsg, [speaker, '-l can\'t have arg'])
            return
        # condense flag (and arg) into command
        if arg != None: command = '{} {}'.format(flag, arg)
        else: command = flag
        # send it!
        perform_with_ops(servmsg, ['/mode {} {}'.format(channel_name, command)])
        # log it!
        log.notice('{} setting mode {}'.format(speaker, command))
        return
    elif words[0].lower() in ['ban', 'quiet', 'akick']:
        if len(words) < 4:
            outbound_message_queue.add(privmsg, [speaker,
                'quiet/akick <nick> <mask-kw>[,<mask-kw>] <reason>'])
            return
        nick = words[1]
        member = members[nick]
        if not member:
            outbound_message_queue.add(privmsg, [speaker, 'couldn\'t find {}'.format(nick)])
            return
        action = words[0].lower()
        reason = ' '.join(words[3:])
        if action == 'ban': action = 'akick'
        omq = outbound_message_queue
        for mask_kw in set(words[2].split(',')):
            if mask_kw not in mask_keywords:
                omq.add(privmsg, [speaker,
                    'ignoring unknown mask keyword {}'.format(mask_kw)], priority=time()+10)
                continue
            mask = mask_keywords[mask_kw]
            if 'nick' in mask_kw: mask = mask.format(member.nick)
            elif 'user' in mask_kw: mask = mask.format(member.user)
            elif 'host' in mask_kw: mask = mask.format(member.host)
            if action == 'akick': perform_with_ops(akick, [mask, reason])
            elif action == 'quiet': perform_with_ops(quiet, [mask, reason])
            else: log.warn('can\'t do {} and should\'ve caught it before now'.format(action))
        return
    else:
        log.debug('master {} said "{}" but we don\'t have a response'.format(
            speaker, ' '.join(words)))
        return

# must be called from the main process
def log_to_masters(string):
    string = str(string)
    if not len(string): return
    if string[-1] == '\n': string = string[:-1]
    for m in masters:
        outbound_message_queue.add(privmsg, [m, string], priority=time()+60)

# should only be called from outbound_message_queue
def ask_for_new_members():
    log.debug('Clearing members set. Asking for members again')
    is_getting_members.set()
    servmsg('/who {}'.format(channel_name))

# Must be called from the main process so the correct copy of members is updated
# a RepeatedTimer calls this every now and then, and it runs in a thread of the
# main process. It can be called manually, but you must do so from the main
# process.
def update_members_event_callback():
    global members
    members = MemberList()
    outbound_message_queue.add(ask_for_new_members)

def prepare_ircdir():
    os.makedirs(os.path.join(server_dir,channel_name), exist_ok=True)

# governing function for a subprocess to watch over a sub-subprocess running ii
def ii_process():
    prepare_ircdir()
    ii_bin = config['ii']['path']
    nick = config['ii']['nick']
    server = config['ii']['server']
    port = config['ii']['port']
    server_pass = config['ii']['server_pass']
    ircdir = config['ii']['ircdir']
    while True:
        log.notice('(Re)Starting ii process')
        set_default_signals()
        ii = subprocess.Popen(
            [ii_bin,'-i',ircdir,'-s',server,'-p',port,'-n',nick,'-k','PASS'],
            env={'PASS': server_pass},
        )
        set_ignore_signals()
        # the following loop continues until we are shutting down entirely or
        # the ii sub-sub process goes away
        while not is_shutting_down.wait(5):
            # if we aren't shutting down and we have a return code,
            # then we need to restart the process. First exit this loop
            if ii.poll() != None:
                log.debug('ii process went away')
                break
        # if we have a return code from the ii sub-sub process, we just exited
        # the above loop and should restart this loop and thus restart the ii
        # process.
        if ii.poll() != None:
            continue
        # if we get to here, then we are shutting down and should just throw it
        # all away.
        if is_shutting_down.is_set():
            log.notice('Stopping ii process for good')
            ii.terminate()
            break

# governing function for a subprocess to manage a queue of messages to send to
# the IRCd
def outbound_message_queue_process():
    log.notice('Starting outbound message queue process')
    while not is_shutting_down.is_set():
        outbound_message_queue.loop_once()
    log.notice('Stopping outbound message queue process')

# governing function for a subprocess to tail a file in a sub-subprocess.
# To do the actual processing of the line, schedule the given function handler
# for execution in the main process with the line as an argument
def tail_file_process(filename, line_function_handler):
    log.notice('Starting process to tail {}'.format(filename))
    set_default_signals()
    # bufsize=1 to get line-based buffering
    # universal_newlines=True would get us text mode, but someone out there has
    # non-unicode bytes in their away message. To handle crap like that, we just
    # get the bytes, and try to convert to a string afterwards.
    sub = subprocess.Popen(
        ['tail','-F','-n','0',filename],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        bufsize=1)
    set_ignore_signals()
    while not is_shutting_down.is_set():
        line_ = sub.stdout.readline()
        try:
            line = line_.decode('utf8')
        except UnicodeDecodeError:
            log.warn('Can\'t decode line, so ignoring: {}'.format(line_))
            continue
        main_action_queue.add(line_function_handler, [line])
    sub.terminate()
    log.notice('Stopping process to tail {}'.format(filename))

# governing function that waits for actions that should be executed as an
# operator, makes sure we have op, and then sends the command off to the
# outbound message queue process. It also deops us if we go a long time without
# performing an op command.
def as_operator_process():
    log.notice('Starting operator action process')
    outbound_message_queue.add(privmsg,
        ['chanserv', 'op {} {}'.format(channel_name, 'pastly_bot')],
        priority=time()-10)
    if not is_operator.wait(timeout=5):
        log.error('Asked for operator, but didn\'t get it before timeout. '
            'Giving up on the operator thread')
        log.notice('Stopping operator action process')
        return
    while not is_shutting_down.is_set():
        try: item = as_operator_queue.get(timeout=randint(30,90))
        except Empty: item = None
        if item == None: break
        func, args, kwargs = item
        outbound_message_queue.add(func, args, kwargs, priority=time()-10)
    outbound_message_queue.add(privmsg,
        ['chanserv', 'deop {} {}'.format(channel_name, 'pastly_bot')])
    log.notice('Stopping operator action process')


# must be called from the main process
# call a function in a thread of the main process in interval seconds
def fire_one_off_event(interval, func, args=None):
    return Timer(interval, func, args=args).start()

def main():
    global server_dir
    global channel_name
    global update_members_event
    global log

    server_dir = os.path.join(config['ii']['ircdir'],config['ii']['server'])
    channel_name = config['ii']['channel']

    log = PastlyLogger(
        debug='{}/{}/debug.log'.format(server_dir, channel_name),
        #notice='{}/log_to_masters'.format(server_dir),
    )
    log.notice("Starting up bot")

    # ignore signals before starting the processes that we actually manage
    # closely
    set_ignore_signals()

    processes.append(Process(target=ii_process))
    processes.append(Process(target=outbound_message_queue_process))

    processes.append(Process(target=tail_file_process,
        args=['{}/out'.format(server_dir),
        server_out_process_line]))
    processes.append(Process(target=tail_file_process,
        args=['{}/{}/out'.format(server_dir, channel_name),
        channel_out_process_line]))
    processes.append(Process(target=tail_file_process,
        args=['{}/pastly_bot/out'.format(server_dir),
        privmsg_out_process_line]))
    processes.append(Process(target=tail_file_process,
        args=['{}/log_to_masters'.format(server_dir),
        log_to_masters]))

    for p in processes: p.start()

    # go back to our super special signals now that we are done starting our
    # sub processes
    set_our_signals()

    fire_one_off_event(5, update_members_event_callback)

    update_members_event = RepeatedTimer(
        config.getint('general', 'update_members_interval', fallback=60*60*8),
        update_members_event_callback)

    while True:
        main_action_queue.loop_once()


if __name__=='__main__':
    main()
