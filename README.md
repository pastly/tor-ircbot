start.sh first starts ii. Then it joins each configured channel and starts the
up for each channel (if uncommented).

There's seems to be an issue with the bot's real hostname leaking when it joins
a channel it is already a part of. So channels need to be joined manually. I
need to confirm whether or not it is only printed locally.

ii: http://tools.suckless.org/ii/

Files with credentials:

- start.sh
