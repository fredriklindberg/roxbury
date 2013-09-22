#!/usr/bin/env python
# ----------------------------------------------------------------------------
# "THE BEER-WARE LICENSE" (Revision 42):
# <fli@shapeshifter.se> wrote this file. As long as you retain this notice you
# can do whatever you want with this stuff. If we meet some day, and you think
# this stuff is worth it, you can buy me a beer in return Fredrik Lindberg
# ----------------------------------------------------------------------------
#

import os
import sys
import time
import signal
import select
from optparse import OptionParser

# Gstreamer python bindings
import pygst
import gst
import gobject

class Roxbury(object):
    def __init__(self, files):
        self._files = files
        self._pos = 0
        self.playing = False
        self._pl = gst.element_factory_make("playbin2", "player")
        self.next()
        self.bus = bus = self._pl.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)

    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_EOS:
            self._pl.set_state(gst.STATE_NULL)
            self.next()
            self.play()
        elif t == gst.MESSAGE_ERROR:
            self.stop()
            err, debug = message.parse_error()
            print "Error: %s" % err

    def poll(self):
        self.bus.poll(gst.MESSAGE_ANY, 0)

    def next(self):
        file = self._files[self._pos]
        self._pl.set_property('uri',
            'file://' + os.path.abspath(self._files[self._pos]))
        self._pos = (self._pos + 1) % len(self._files)

    def play(self):
        self.playing = True
        self._pl.set_state(gst.STATE_PLAYING)

    def stop(self):
        self.playing = False
        self._pl.set_state(gst.STATE_NULL)

    def pause(self):
        self.playing = False
        self._pl.set_state(gst.STATE_PAUSED)

    def toggle(self):
        self.play() if not self.playing else self.pause()

class Signal(object):
    def __init__(self, signo):
        self._list = []
        signal.signal(signo, self.handler)

    def add(self, callback, argument=None):
        self._list.append((callback, argument))

    def handler(self, sig, frame):
        for (cb, arg) in self._list:
            cb(arg)

def main(args):
    parser = OptionParser(usage="%prog [options] file1.mp3 [file2.mp3]")
    parser.add_option("-p", "--poll", dest="gpio", default=None,
                  help="GPIO poll")
    (opts, files) = parser.parse_args()

    if len(files) < 1:
        print "You need to specify at least one music file"
        return 1

    p = select.poll()
    if opts.gpio:
        file = open(opts.gpio, 'r')
        p.register(file, select.POLLPRI | select.POLLERR)

    roxbury = Roxbury(files)

    sigusr1 = Signal(signal.SIGUSR1)
    sigusr1.add((lambda x: roxbury.toggle()))

    roxbury.play()

    while True:
        roxbury.poll()
        ready = p.poll(0.5)
        if len(ready) > 0:
            (fd, event) = ready[0]
            value = os.read(fd, 1)
            roxbury.play() if int(value) == 1 else roxbury.pause()
            os.lseek(fd, 0, os.SEEK_SET)

    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
