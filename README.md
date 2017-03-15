# WARNING

`start.sh` needs to be scrubbed from commit history before sharing code.

Also check for pastly's nickserv password (and pastly_bot's while you're at it).

Look for mentions of the string 'pastly' too, why don't you.

# About

This bot requires [`ii`][ii], a suckless tool. Right now it expects ii to be in
`/usr/local/bin`, sorry. Look for that path in `bot.py` and change if needed :/

`bot.py` is a python3 script. It runs two threads: a main thread and a thread
for watching over `ii`. The `ii` thread starts `ii` and makes sure it is
restarted in the event of failure not caused by the bot shutting down.

It also starts some subprocesses that `tail` important output files in `ii`'s
`ircdir`. The main event loop consists of waiting for new lines in these output
files and handling them as they come in.

# Logging

I like the way Tor does logging, so I took some of Tor's ideas and implemented
logging in a separate class. The keyword args to the contructor are filenames
for the various log levels. The log levels are, in this order:

1. error
2. warn
3. notice
4. info
5. debug

Log levels cascade: if you specify a file for notice and for debug, notice will
get all error, warn, and notice log lines while debug will get info and debug
log lines.

Logging to an IRC channel or to private messages is planned but not implemented
yet due to flooding issues in naive implementations.

[ii]: http://tools.suckless.org/ii/
