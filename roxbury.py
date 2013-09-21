#!/usr/bin/env python
# ----------------------------------------------------------------------------
# "THE BEER-WARE LICENSE" (Revision 42):
# <fli@shapeshifter.se> wrote this file. As long as you retain this notice you
# can do whatever you want with this stuff. If we meet some day, and you think
# this stuff is worth it, you can buy me a beer in return Fredrik Lindberg
# ----------------------------------------------------------------------------
#

import sys
import time
import signal

# Requires avbin
import pyglet

player = pyglet.media.Player()
player.eos_action = 'loop'

# Play/pause with kill -USR1, for debugging.
def sighandler(sig, frame):
    player.pause() if player.playing else player.play()

def main(args):
    if len(args) < 2:
        print "Usage {0} <file.mp3>".format(args[0])
        return 1

    signal.signal(signal.SIGUSR1, sighandler)

    source = pyglet.media.load(args[1])
    player.queue(source)

    while True:
        player.dispatch_events()
        time.sleep(0.05)
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
