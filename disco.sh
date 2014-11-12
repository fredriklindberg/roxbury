#!/bin/bash

pulse() {
	echo "1" > "/sys/class/gpio/gpio$1/value"
	sleep 1
	echo "0" > "/sys/class/gpio/gpio$1/value"
}

PLAYER_PID=/var/run/roxbury-snd.pid
ON=23
OFF=24


if [ "$1" == "on" ]; then
	pulse $ON
	kill -USR1 $(cat /var/run/roxbury-snd.pid)
elif [ "$1" == "off" ]; then
	pulse $OFF
	kill -USR1 $(cat /var/run/roxbury-snd.pid)
else
	echo "Usage $0 on|off"
fi
