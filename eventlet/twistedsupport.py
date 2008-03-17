"""\
@file twistedsupport.py
@author Donovan Preston

Copyright (c) 2005-2006, Donovan Preston
Copyright (c) 2007, Linden Research, Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import sys
import traceback

from eventlet import api
from eventlet import timer

from twisted.internet import posixbase
from twisted.internet.interfaces import IReactorFDSet

try:
    from zope.interface import implements
    _working = True
except ImportError:
    _working = False
    def implements(*args, **kw):
        pass


class TwistedTimer(object):
    def __init__(self, timer):
        self.timer = timer

    def cancel(self):
        self.timer.cancel()

    def getTime(self):
        return self.timer.scheduled_time

    def delay(self, seconds):
        hub = api.get_hub()
        new_time = hub.clock() - self.timer_scheduled_time + seconds
        self.timer.cancel()
        cb, args, kw = self.timer.tpl
        self.timer = hub.schedule_call(new_time, cb, *args, **kw)

    def reset(self, new_time):
        self.timer.cancel()
        cb, args, kw = self.timer.tpl
        self.timer = api.get_hub().schedule_call(new_time, cb, *args, **kw)

    def active(self):
        return not self.timer.called


class EventletReactor(posixbase.PosixReactorBase):
    implements(IReactorFDSet)

    def __init__(self, *args, **kw):
        self._readers = {}
        self._writers = {}
        posixbase.PosixReactorBase.__init__(self, *args, **kw)

    def callLater(self, func, *args, **kw):
        return TwistedTimer(api.call_after(func, *args, **kw))

    def run(self):
        self.running = True
        self._stopper = api.call_after(sys.maxint / 1000.0, lambda: None)
        ## schedule a call way in the future, and cancel it in stop?
        api.get_hub().runloop.run()

    def stop(self):
        self._stopper.cancel()
        posixbase.PosixReactorBase.stop(self)
        api.get_hub().remove_descriptor(self._readers.keys()[0])
        api.get_hub().runloop.abort()

    def addReader(self, reader):
        fileno = reader.fileno()
        self._readers[fileno] = reader
        api.get_hub().add_descriptor(fileno, read=self._got_read)

    def _got_read(self, fileno):
        self._readers[fileno].doRead()

    def addWriter(self, writer):
        fileno = writer.fileno()
        self._writers[fileno] = writer
        api.get_hub().add_descriptor(fileno, write=self._got_write)

    def _got_write(self, fileno):
        self._writers[fileno].doWrite()

    def removeReader(self, reader):
        fileno = reader.fileno()
        if fileno in self._readers:
            self._readers.pop(fileno)
        api.get_hub().remove_descriptor(fileno)

    def removeWriter(self, writer):
        fileno = writer.fileno()
        if fileno in self._writers:
            self._writers.pop(fileno)
        api.get_hub().remove_descriptor(fileno)

    def removeAll(self):
        return self._removeAll(self._readers.values(), self._writers.values())


def emulate():
    if not _working:
        raise RuntimeError, "Can't use twistedsupport because zope.interface is not installed."
    reactor = EventletReactor()
    from twisted.internet.main import installReactor
    installReactor(reactor)


__all__ = ['emulate']

