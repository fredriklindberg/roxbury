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
import syslog
import random
import time
from optparse import OptionParser
from ConfigParser import RawConfigParser

# python-magic
import magic

# Gstreamer python bindings
import pygst
import gst
import gobject

class Schedule(object):
    _months = {
        "jan" : 1, "feb" : 2,
        "mar" : 3, "apr" : 4,
        "may" : 5, "jun" : 6,
        "jul" : 7, "aug" : 8,
        "sep" : 9, "oct" : 10,
        "nov" : 11, "dec" : 12,
    }

    _days = {
        "mon" : 1,
        "tue" : 2,
        "wed" : 3,
        "thu" : 4,
        "fri" : 5,
        "sat" : 6,
        "sun" : 7,
    }

    _keys = ["min", "hour", "day", "month"]

    def __init__(self, at):
        self._cron = {}
        for key in self._keys:
            self._cron[key] = "*"

        tmp = at.split()
        for i in xrange(0, min(len(self._keys), len(tmp))):
            self._cron[self._keys[i]] = tmp[i]

        self._at = {}
        self._at["min"] = self._parse(self._cron["min"], 0, 59)
        self._at["hour"] = self._parse(self._cron["hour"], 0, 23)
        self._at["day"] = self._parse(self._cron["day"], 1, 7)
        self._at["month"] = self._parse(self._cron["month"], 1, 12)

    def _parse(self, str, min, max):

        def to_num(x):
            key = x[0:3].lower()
            if x.isdigit():
                return int(key)
            elif self._months.has_key(key):
                return self._months[key]
            elif self._days.has_key(key):
                return self._days[key]
            else:
                return None

        result = []
        if str == '*':
            return xrange(min, max+1)
        else:
            for x in str.split(','):
                y = x.split('-')
                if len(y) == 1:
                    result.append(to_num(y[0]))
                elif len(y) == 2:
                    result = result + range(to_num(y[0]), to_num(y[1])+1)
        return result

    def ok(self):
        cur = time.localtime()

        if not cur.tm_mon in self._at["month"]:
            return False
        if not (cur.tm_wday + 1) in self._at["day"]:
            return False
        if not cur.tm_hour in self._at["hour"]:
            return False
        if not cur.tm_min in self._at["min"]:
            return False
        return True

class Playable(object):
    def __new__(cls, path):
        mime = magic.from_file(path, mime=True)
        if mime == 'text/plain':
            return Playlist(path)
        else:
            return Music(path)

class Music(object):
    def __init__(self, path=''):
        self._path = path

    def playable(self):
        return os.path.exists(self._path)

    def next(self):
        return self;

    def __str__(self):
        return self._path

class Playlist(object):
    def __init__(self, path=None):
        self._list = []
        self._pos = 0
        self._parent = None
        self._schedule = None
        self._shuffle = False
        if path:
            self._parse(path)

    def __str__(self):
        return self._list

    def _parse(self, path):
        cfg = RawConfigParser(allow_no_value=True)
        cfg.optionxform = str
        cfg.read(path)

        for key in cfg.defaults():
            value = cfg.defaults()[key]
            if key == "shuffle" and value == "true":
                self._shuffle = True

        for section in cfg.sections():
            pl = Playlist()
            for (key, value) in cfg.items(section):
                if not value:
                    pl.add(key)
                if key == "cron":
                    pl.schedule(value)
                if key == "shuffle" and value == "true":
                    pl._shuffle = True

            self.add(pl)

    def schedule(self, cron):
        self._schedule = Schedule(cron)

    def add(self, obj):
        if type(obj) is Music or type(obj) is Playlist:
            p = obj
        else:
            p = Playable(obj)

        self._list.append(p)
        p._parent = self;

    def playable(self):
        if self._schedule:
            return self._schedule.ok()
        return True

    def _advance(self):
        self._pos = (self._pos + 1) % len(self._list)
        if self._pos == 0 and self._parent:
            self._parent._advance()

    def next(self):
        if self._pos == 0 and self._shuffle:
            random.shuffle(self._list)

        next = self._list[self._pos]
        if next.playable():
            if type(next) is Music:
                self._advance()
            return next.next()
        else:
            self._advance()
            return self.next()

class Roxbury(object):
    def __init__(self, playlist):
        self._playlist = playlist
        self._file = None
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
            err, debug = message.parse_error()
            syslog.syslog(syslog.LOG_ERR, "{0}".format(err))
            syslog.syslog(syslog.LOG_DEBUG, "{0}".format(debug))
            self.stop()

    def poll(self):
        self.bus.poll(gst.MESSAGE_ANY, 0)

    def next(self):
        self._file = str(self._playlist.next())
        was_playing = self.playing
        if was_playing:
            self.stop()
        self._pl.set_property('uri',
            'file://' + os.path.abspath(self._file))
        if was_playing:
            self.play()

    def play(self):
        self.playing = True
        self._pl.set_state(gst.STATE_PLAYING)
        syslog.syslog("Playing {0}".format(self._file))

    def stop(self):
        self.playing = False
        self._pl.set_state(gst.STATE_NULL)
        syslog.syslog("Playpack stopped")

    def pause(self):
        self.playing = False
        self._pl.set_state(gst.STATE_PAUSED)
        syslog.syslog("Playback paused")

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

def main(fd, args):
    parser = OptionParser(usage="%prog [options] file1 [file2]")
    parser.add_option("-p", "--poll", dest="gpio", default=None,
                  help="GPIO poll")
    (opts, files) = parser.parse_args()

    if len(files) < 1:
        print "You need to specify at least one music file or playlist"
        return 0

    random.seed()

    playlist = Playlist()
    for file in files:
        playlist.add(file)

    p = None
    if opts.gpio:
        p = select.poll()
        file = open(opts.gpio, 'r')
        p.register(file, select.POLLPRI | select.POLLERR)

    roxbury = Roxbury(playlist)

    sigusr1 = Signal(signal.SIGUSR1)
    sigusr1.add((lambda x: roxbury.toggle()))

    sigusr2 = Signal(signal.SIGUSR2)
    sigusr2.add((lambda x: roxbury.next()))

    running = [True]
    def stop(x):
        syslog.syslog("Got SIGTERM/SIGINT, shutting down player")
        running[0] = False

    sigterm = Signal(signal.SIGTERM)
    sigterm.add(stop)
    sigint = Signal(signal.SIGINT)
    sigint.add(stop)

    syslog.syslog("Ready to dance")

    while running[0]:
        if fd:
            print >>fd, "emilio"
            fd.flush()
        roxbury.poll()
        if p:
            ready = p.poll(0.5)
            try:
                if len(ready) > 0:
                    (gpio_fd, event) = ready[0]
                    value = os.read(gpio_fd, 1)
                    roxbury.play() if int(value) == 1 else roxbury.pause()
                    os.lseek(gpio_fd, 0, os.SEEK_SET)
            except:
                ''
        else:
            time.sleep(0.5)

    return 0

def watchdog():
    r,w = os.pipe()
    r = os.fdopen(r, 'r', 0)
    w = os.fdopen(w, 'w', 0)

    pid = os.fork()
    if pid < 0:
        print "Fork failed"
        sys.exit(-1)
    elif pid == 0:
        sys.exit(main(w, sys.argv))

    running = [True]
    restart = False
    def stop(x):
        syslog.syslog("Got SIGTERM/SIGINT, shutting down watchdog")
        running[0] = False

    sigterm = Signal(signal.SIGTERM)
    sigterm.add(stop)
    sigint = Signal(signal.SIGINT)
    sigint.add(stop)
    signal.signal(signal.SIGUSR1, signal.SIG_IGN)
    signal.signal(signal.SIGUSR2, signal.SIG_IGN)

    while running[0]:
        try:
            rr,rw,re = select.select([r], [], [], 2.5)
            if len(rr) > 0:
                r.readline()
            elif len(rr) == 0:
                (wpid, ret) = os.waitpid(pid, os.WNOHANG)
                if wpid == 0 or (wpid != 0 and ret != 0):
                    os.kill(pid, signal.SIGKILL)
                    restart = True
                    syslog.syslog("Not enough ass-grabbing, resetting")
                running[0] = False
                break
        except:
            ''

    r.close()
    try:
        os.waitpid(pid, os.WNOHANG)
    except:
        ''
    return restart

if __name__ == '__main__':
    restart = True
    while restart:
        restart = watchdog()
