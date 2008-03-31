"""\
@file selecthub.py
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
import errno
import traceback
import time
from bisect import insort, bisect_left

from eventlet import greenlib
from eventlet import util
from eventlet.runloop import RunLoop, Timer

import greenlet

class Hub(object):
    def __init__(self):
        self.runloop = RunLoop(self.wait)
        self.readers = {}
        self.writers = {}
        self.excs = {}
        self.descriptors = {}
        self.descriptor_queue = {}
        self.greenlet = None

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
                exc = self.excs[fileno]
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
        readers = self.readers
        writers = self.writers
        excs = self.excs
        descriptors = self.descriptors
        for fileno, rwe in self.descriptor_queue.iteritems():
            read, write, exc = rwe
            if read is None and write is None and exc is None:
                try:
                    del descriptors[fileno]
                except KeyError:
                    continue
                try:
                    del readers[fileno]
                except KeyError:
                    pass
                try:
                    del writers[fileno]
                except KeyError:
                    pass
                try:
                    del excs[fileno]
                except KeyError:
                    pass
            else:
                if read is not None:
                    readers[fileno] = read
                else:
                    try:
                        del readers[fileno]
                    except KeyError:
                        pass
                if write is not None:
                    writers[fileno] = write
                else:
                    try:
                        del writers[fileno]
                    except KeyError:
                        pass
                if exc is not None:
                    excs[fileno] = exc
                else:
                    try:
                        del excs[fileno]
                    except KeyError:
                        pass
                descriptors[fileno] = rwe
        self.descriptor_queue.clear()
    
    def wait(self, seconds=None):
        self.process_queue()
        if not self.descriptors:
            if seconds:
                time.sleep(seconds)
            return
        readers = self.readers
        writers = self.writers
        excs = self.excs
        try:
            r, w, ig = util.__original_select__(readers.keys(), writers.keys(), [], seconds)
        except select.error, e:
            if e.args[0] == errno.EINTR:
                return
            raise
        SYSTEM_EXCEPTIONS = self.runloop.SYSTEM_EXCEPTIONS
        for observed, events in ((readers, r), (writers, w)):
            for fileno in events:
                try:
                    observed[fileno](fileno)
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())
