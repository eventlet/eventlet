"""\
@file kqueuehub.py
@author Donovan Preston

Copyright (c) 2006-2007, Linden Research, Inc.
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
import select
import kqueue
import traceback
from errno import EBADF

from eventlet import greenlib
from eventlet.runloop import RunLoop, Timer

import greenlet

class Hub(object):
    def __init__(self):
        self.runloop = RunLoop(self.wait)
        self.descriptor_queue = {}
        self.descriptors = {}
        self.greenlet = None
        self.kfd = None

    def stop(self):
        self.process_queue()
        self.descriptors, self.descriptor_queue = self.descriptor_queue, {}
        os.close(self.kfd)
        self.kfd = None
        self.runloop.abort()
        if self.greenlet is not greenlet.getcurrent():
            self.switch()

    def schedule_call(self, *args, **kw):
        return self.runloop.schedule_call(*args, **kw)

    def switch(self):
        if not self.greenlet:
            self.greenlet = greenlib.tracked_greenlet()
            args = ((self.runloop.run,),)
        else:
            args = ()
        try:
            greenlet.getcurrent().parent = self.greenlet
        except ValueError:
            pass
        return greenlib.switch(self.greenlet, *args)

    def add_descriptor(self, fileno, read=None, write=None, exc=None):
        self.descriptor_queue[fileno] = read, write, exc
        
    def remove_descriptor(self, fileno):
        self.descriptor_queue[fileno] = None, None, None

    def exc_descriptor(self, fileno):
        # We must handle two cases here, the descriptor
        # may be changing or removing its exc handler
        # in the queue, or it may be waiting on the queue.
        exc = None
        try:
            exc = self.descriptor_queue[fileno][2]
        except KeyError:
            try:
                exc = self.descriptors[fileno][2]
            except KeyError:
                pass
        if exc is not None:
            try:
                exc()
            except self.runloop.SYSTEM_EXCEPTIONS:
                self.squelch_exception(fileno, sys.exc_info())

    def squelch_exception(self, fileno, exc_info):
        traceback.print_exception(*exc_info)
        print >>sys.stderr, "Removing descriptor: %r" % (fileno,)
        try:
            self.remove_descriptor(fileno)
        except Exception, e:
            print >>sys.stderr, "Exception while removing descriptor! %r" % (e,)

    def process_queue(self):
        if self.kfd is None:
            self.kfd = kqueue.kqueue()
        d = self.descriptors

        E_R = kqueue.EVFILT_READ
        E_W = kqueue.EVFILT_WRITE
        E = kqueue.Event
        E_ADD = kqueue.EV_ADD
        E_DEL = kqueue.EV_DELETE
        
        kevent = kqueue.kevent
        kfd = self.kfd
        for fileno, rwe in self.descriptor_queue.iteritems():
            read, write, exc = rwe
            if read is None and write is None and exc is None:
                try:
                    read, write, exc = d.pop(fileno)
                except KeyError:
                    pass
                else:
                    l = []
                    if read is not None:
                        l.append(E(fileno, E_R, E_DEL))
                    if write is not None:
                        l.append(E(fileno, E_W, E_DEL))
                    if l:
                        try:
                            kevent(kfd, l, 0, 0)
                        except OSError, e:
                            if e[0] != EBADF:
                                raise
            else:
                l = []
                try:
                    oldr, oldw, olde = d[fileno]
                except KeyError:
                    pass
                else:
                    if oldr is not None:
                        if read is None:
                            l.append(E(fileno, E_R, E_DEL))
                        else:
                            read = None
                    if oldw is not None:
                        if write is None:
                            l.append(E(fileno, E_W, E_DEL))
                        else:
                            write = None
                if read is not None:
                    l.append(E(fileno, E_R, E_ADD))
                if write is not None:
                    l.append(E(fileno, E_W, E_ADD))
                if l:
                    try:
                        kevent(kfd, l, 0, 0)
                    except OSError, e:
                        if e[0] != EBADF:
                            raise
                        try:
                            del d[fileno]
                        except KeyError:
                            pass
                        if exc is not None:
                            try:
                                exc(fileno)
                            except SYSTEM_EXCEPTIONS:
                                raise
                            except:
                                self.squelch_exception(fileno, sys.exc_info())
                        continue
                d[fileno] = rwe
        self.descriptor_queue.clear()
        
    def wait(self, seconds=None):

        self.process_queue()

        if seconds is not None:
            seconds *= 1000000000.0
        dct = self.descriptors
        events = kqueue.kevent(self.kfd, [], len(dct), seconds)

        SYSTEM_EXCEPTIONS = self.runloop.SYSTEM_EXCEPTIONS

        E_R = kqueue.EVFILT_READ
        E_W = kqueue.EVFILT_WRITE
        E_EOF = kqueue.EV_EOF

        for e in events:
            fileno = e.ident
            event = e.filter

            try:
                read, write, exc = dct[fileno]
            except KeyError:
                continue

            if read is not None and event == E_R:
                try:
                    read(fileno)
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())
            elif exc is not None and e.fflags & E_EOF:
                try:
                    exc(fileno)
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())

            if write is not None and event == E_W:
                try:
                    write(fileno)
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())
