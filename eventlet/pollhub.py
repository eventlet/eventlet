"""\
@file pollhub.py
@author Bob Ippolito

Copyright (c) 2005-2006, Bob Ippolito
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
import select
import socket
import errno
import traceback
from time import sleep

from eventlet import greenlib
from eventlet.runloop import RunLoop, Timer

import greenlet

EXC_MASK = select.POLLERR | select.POLLHUP | select.POLLNVAL
READ_MASK = select.POLLIN
WRITE_MASK = select.POLLOUT

class Hub(object):
    def __init__(self):
        self.runloop = RunLoop(self.wait)
        self.descriptor_queue = {}
        self.descriptors = {}
        self.greenlet = None
        self.poll = select.poll()

    def stop(self):
        self.process_queue()
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
        if fileno in self.descriptor_queue:
            oread, owrite, oexc = self.descriptor_queue[fileno]
            read, write, exc = read or oread, write or owrite, exc or oexc
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
                exc(fileno)
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
        d = self.descriptors
        reg = self.poll.register
        unreg = self.poll.unregister
        rm = READ_MASK
        wm = WRITE_MASK
        for fileno, rwe in self.descriptor_queue.iteritems():
            read, write, exc = rwe
            if read is None and write is None and exc is None:
                try:
                    del d[fileno]
                except KeyError:
                    pass
                else:
                    try:
                        unreg(fileno)
                    except socket.error:
#                        print "squelched socket err on unreg", fileno
                        pass
            else:
                mask = 0
                if read is not None:
                    mask |= rm
                if write is not None:
                    mask |= wm
                oldmask = 0
                try:
                    oldr, oldw, olde = d[fileno]
                except KeyError:
                    pass
                else:
                    if oldr is not None:
                        oldmask |= rm
                    if oldw is not None:
                        oldmask |= wm
                if mask != oldmask:
                    reg(fileno, mask)
                d[fileno] = rwe
        self.descriptor_queue.clear()
        
    def wait(self, seconds=None):
        self.process_queue()

        if not self.descriptors:
            if seconds:
                sleep(seconds)
            return
        try:
            presult = self.poll.poll(seconds * 1000.0)
        except select.error, e:
            if e.args[0] == errno.EINTR:
                return
            raise
        SYSTEM_EXCEPTIONS = self.runloop.SYSTEM_EXCEPTIONS
        dct = self.descriptors

        for fileno, event in presult:
            try:
                read, write, exc = dct[fileno]
            except KeyError:
                continue

            if read is not None and event & READ_MASK:
                try:
                    read(fileno)
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())
            elif exc is not None and event & EXC_MASK:
                try:
                    exc(fileno)
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())

            if write is not None and event & WRITE_MASK:
                try:
                    write(fileno)
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())
