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
import operator
import threading
from optparse import OptionParser
from ConfigParser import RawConfigParser

# python-magic
import magic

# Gstreamer python bindings
import pygst
import gst
import gobject

class Triggers(object):
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Triggers, cls).__new__(cls, *args, **kwargs)
            cls._instance._triggers = {}
        return cls._instance

    def get(self, type, args={}):
        key = str(sorted(args.iteritems(), key=operator.itemgetter(1)))

        if type not in self._triggers:
            self._triggers[type] = {}

        if key not in self._triggers[type]:
            self._triggers[type][key] = Trigger.factory(type, args)

        return self._triggers[type][key]

    def stop(self):
        for type in self._triggers:
            for key in self._triggers[type]:
                self._triggers[type][key].stop()
                self._triggers[type][key] = {}

class Trigger(object):
    @staticmethod
    def factory(type, args={}):
        if type == "signal":
            return Trigger_signal(args)
        elif type == "gpio":
            return Trigger_gpio(args)
        elif type == "random":
            return Trigger_random(args)

    def __init__(self):
        self._roxbury = Roxbury()

        self._monitor = threading.Thread(target=self.monitor)
        self._monitor_running = True
        self._monitor.start()

        self._runcond = threading.Condition()
        if getattr(self, "run", None):
            self._tid = threading.Thread(target=self.run)
            self._running = True
            self._tid.start()
        else:
            self._tid = None

    def stop(self):
        self._roxbury.stop()
        self._monitor_running = False
        self._monitor.join()
        self._running = False
        self._runcond.acquire()
        self._runcond.notifyAll()
        self._runcond.release()
        if self._tid:
            self._tid.join()

    @property
    def roxbury(self):
        return self._roxbury
    @roxbury.setter
    def roxbury(self, value):
        self._roxbury = value

    def add_playlist(self, playlist):
        self._roxbury.playlist.add(playlist)

    def monitor(self):
        while self._monitor_running:
            self._roxbury.poll()
            time.sleep(0.1)

class Trigger_signal(Trigger):

    _signals = {
        'sigusr1' : signal.SIGUSR1,
        'sigusr2' : signal.SIGUSR2,
    }

    _keys = ['toggle', 'next']

    def __init__(self, args):

        for key in args:
            if key not in self._keys:
                continue
            value = args[key].lower()
            if value not in self._signals:
                continue
            signal = self._signals[value]
            sig = Signal(signal)
            sig.add(self.__getattribute__("_"+key))

        super(Trigger_signal, self).__init__()

    def _toggle(self, arg):
        self._roxbury.toggle()

    def _next(self, arg):
        self._roxbury.next()

class Trigger_gpio(Trigger):

    def __init__(self, args):
        path = args["path"]

        file = open(path, 'r')
        self._p = select.poll()
        self._p.register(file, select.POLLPRI | select.POLLERR)

        super(Trigger_gpio, self).__init__()

    def run(self):
        while self._running:
            ready = self._p.poll(500)
            try:
                if len(ready) > 0:
                    (fd, event) = ready[0]
                    value = os.read(fd, 1)
                    if int(value) == 1:
                        self._roxbury.play()
                    else:
                        self._roxbury.pause()
                    os.lseek(fd, 0, os.SEEK_SET)
            except:
                ''

class Trigger_random(Trigger):

    _delay = 1.0
    def __init__(self, args):
        if "delay" in args:
            self._delay = float(args["delay"])

        prob = args["dice"].split("/")
        self._dice = int(prob[1])
        self._eyes = int(prob[0])

        super(Trigger_random, self).__init__()

    def run(self):
        while self._running:
            roll = random.randint(1, self._dice)
            if roll <= self._eyes and not self._roxbury.playing:
                self._roxbury.continuous = False
                self._roxbury.play()
            self._runcond.acquire()
            self._runcond.wait(self._delay)

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

    _keys = ["min", "hour", "wday", "mday", "month"]

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
        self._at["wday"] = self._parse(self._cron["wday"], 1, 7)
        self._at["mday"] = self._parse(self._cron["mday"], 1, 31)
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
        if not cur.tm_mday in self._at["mday"]:
            return False
        if not (cur.tm_wday + 1) in self._at["wday"]:
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
        self._parents = []

    def playable(self):
        return os.path.exists(self._path)

    def next(self):
        return self;

    def playlists(self):
        return self._parents

    def __str__(self):
        return self._path

class Playlist(object):
    def __init__(self, path=None):
        self._list = []
        self._pos = 0
        self._parents = []
        self._schedule = None
        self._shuffle = False
        if path:
            self._parse(path)

    def __str__(self):
        return str(self._list)

    def _parse(self, path):
        cfg = RawConfigParser(allow_no_value=True)
        cfg.optionxform = str
        cfg.read(path)

        def parse_trigger(str):
            val = str.split(" ")
            args = dict(map(lambda x: (x.split("=")[0], x.split("=")[1]), val[2:]))
            trigger = Triggers().get(val[1], args)
            trigger.roxbury = Players().get(val[0])
            return trigger

        for key in cfg.defaults():
            value = cfg.defaults()[key]
            if key == "shuffle" and value == "true":
                self._shuffle = True
            if key[:7] == "trigger":
                trigger = parse_trigger(value)
                trigger.add_playlist(self)

        for section in cfg.sections():
            pl = Playlist()
            for (key, value) in cfg.items(section):
                if not value:
                    pl.add(key)
                if key == "cron":
                    pl.schedule(value)
                if key == "shuffle" and value == "true":
                    pl._shuffle = True
                if key[:7] == "trigger":
                    trigger = parse_trigger(value)
                    trigger.add_playlist(pl)

            self.add(pl)

    def schedule(self, cron):
        self._schedule = Schedule(cron)

    def add(self, obj):
        if type(obj) is Music or type(obj) is Playlist:
            p = obj
        else:
            p = Playable(obj)

        self._list.append(p)
        p._parents.append(self);

    def playable(self):
        if self._schedule:
            return self._schedule.ok()
        return True

    def _advance(self):
        self._pos = (self._pos + 1) % len(self._list)
        if self._pos == 0 and len(self._parents) > 0:
            for parent in self._parents:
                parent._advance()

    def next(self):
        if len(self._list) == 0:
            return None
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

class Players(object):
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Players, cls).__new__(cls, *args, **kwargs)
            cls._instance._players = {}
        return cls._instance

    def get(self, id):
        if id not in self._players:
            self._players[id] = Roxbury()
        return self._players[id]

class Roxbury(object):
    def __init__(self, playlist=None):
        self._playlist = playlist if playlist else Playlist()
        self._file = None
        self._continuous = True
        self.playing = False
        self._pl = gst.element_factory_make("playbin2", "player")
        self.bus = bus = self._pl.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)

    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_EOS:
            self._pl.set_state(gst.STATE_NULL)
            self.playing = False
            self.next()
            if self._continuous:
                self.play()
        elif t == gst.MESSAGE_ERROR:
            err, debug = message.parse_error()
            syslog.syslog(syslog.LOG_ERR, "{0}".format(err))
            syslog.syslog(syslog.LOG_DEBUG, "{0}".format(debug))
            self.stop()

    def poll(self):
        if self.bus.peek() != None:
            self.bus.poll(gst.MESSAGE_EOS | gst.MESSAGE_ERROR, 0)

    @property
    def continuous(self):
        return self._continuous
    @continuous.setter
    def continuous(self, value):
        self._continuous = value

    @property
    def playlist(self):
        return self._playlist

    def next(self):
        self._file = self._playlist.next()
        was_playing = self.playing
        if was_playing:
            self.stop()
        self._pl.set_property('uri',
            'file://' + os.path.abspath(str(self._file)))
        if was_playing:
            self.play()

    def play(self):
        if not self._file or not all(map(lambda x: x.playable(), self._file.playlists())):
            self.stop()
            self.next()
            if not self._file:
                return
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
    _instances = {}
    def __new__(cls, *args, **kwargs):
        signo = args[0]
        if signo not in cls._instances:
            cls._instances[signo] = super(Signal, cls).__new__(cls, *args, **kwargs)
            cls._instances[signo]._list = []
            signal.signal(signo, cls._instances[signo].handler)
        return cls._instances[signo]

    def __init__(self, signo):
        ''

    def add(self, callback, argument=None):
        self._list.append((callback, argument))

    def handler(self, sig, frame):
        for (cb, arg) in self._list:
            cb(arg)

def main(fd, args):
    parser = OptionParser(usage="%prog [options] file1 [file2]")
    (opts, files) = parser.parse_args()

    if len(files) < 1:
        print "You need to specify at least one music file or playlist"
        return 0

    random.seed()

    triggers = Triggers()
    playlist = Playlist()
    for file in files:
        playlist.add(file)

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
        time.sleep(0.5)

    triggers.stop()
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
        syslog.syslog("Got SIGTERM/SIGINT, shutting down all processes")
        os.kill(pid, signal.SIGTERM)
        running[0] = False

    sigterm = Signal(signal.SIGTERM)
    sigterm.add(stop)
    sigint = Signal(signal.SIGINT)
    sigint.add(stop)

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
