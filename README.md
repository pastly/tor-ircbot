# About

This bot requires [`ii`][ii], a suckless tool.

`main.py` is a python3 script. It runs a shit ton of threads. This has made a
lot of people very angry and been widely regarded as a bad move.

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
