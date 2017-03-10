#!/usr/bin/env bash

IRCDIR="$(pwd)/ircdir"
SERVER="yl4kw6oetvyxhar3.onion"
NICK="oftc_bot"
PASS="js9YooPHCUbURC5nx4jqApywb6Nsk2p54AhVevZh"
ZNC_SERVER_NAME="oftc"
WATCH_CHANNELS=( "#pastly_test" )

PASS=$PASS ii -i "$IRCDIR" -s "$SERVER" -n "$NICK/$ZNC_SERVER_NAME" -k "PASS" -f "$NICK" &
sleep 3

######
# Don't rejoin channels while the host name leakage still hasn't been fixed
# It might only be printed locally though
######
#for CHAN in "${WATCH_CHANNELS[@]}"
#do
#       echo "/join $CHAN" > "$IRCDIR/$SERVER/in"
#       sleep 1
#       ./bot.py "$IRCDIR/$SERVER" "$CHAN" &
#done

