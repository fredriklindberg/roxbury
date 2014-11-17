#!/bin/bash

puts() {
	echo "$1"
	logger "roxbury.sh: $1"
}

init() {
	puts "Initializing gpio $1 (output)"
	echo "$1" > "/sys/class/gpio/export"
	echo "out" > "/sys/class/gpio/gpio$1/direction"
	echo "0" > "/sys/class/gpio/gpio$1/value"
}

pulse() {
	puts "Sending pulse to gpio $1"
	echo "1" > "/sys/class/gpio/gpio$1/value"
	sleep 1
	echo "0" > "/sys/class/gpio/gpio$1/value"
}

door() {
	local file="/sys/class/gpio/gpio$IN/value"

	if [ ! -e $file ]; then
		puts "fatal, door input file missing"
		exit 1
	fi

	cat "$file"
}


ON=23
OFF=24
IN=17
OPEN=1

init $ON
init $OFF

state="off"

puts "Entering main loop"
while [ 1 ]; do
	if [ "$(door $IN)" == "$OPEN" ] && [ "$state" == "off" ]; then
		puts "Door now open"
		pulse $ON
		state="on"
	elif [ "$(door $IN)" != "$OPEN" ] && [ "$state" == "on" ]; then
		puts "Door now closed"
		pulse $OFF
		state="off"
	fi

	sleep 0.5
done
