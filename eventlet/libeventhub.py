"""\
@file libeventhub.py

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
import socket
import errno
import traceback
from time import sleep

from eventlet import greenlib
from eventlet.runloop import RunLoop, Timer

import greenlet

try:
    # use rel if it's available
    import rel
    rel.initialize()
    rel.override()
except ImportError:
    pass


import event


class Hub(object):
    def __init__(self):
        self.readers = {}
        self.writers = {}
        self.interrupted = False

        self.runloop = RunLoop(self.wait)

        self.greenlet = None
        event.init()
        
        signal = event.signal(2, self.raise_keyboard_interrupt)
        signal.add()

    def stop(self):
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
        if read:
            evt = event.read(fileno, read, fileno)
            evt.add()
            self.readers[fileno] = evt, read

        if write:
            evt = event.write(fileno, write, fileno)
            evt.add()
            self.writers[fileno] = evt, write
        
    def remove_descriptor(self, fileno):
        for queue in (self.readers, self.writers):
            tpl = queue.pop(fileno, None)
            if tpl is not None:
                tpl[0].delete()

    def exc_descriptor(self, fileno):
        for queue in (self.readers, self.writers):
            tpl = queue.pop(fileno, None)
            if tpl is not None:
                evt, cb = tpl
                evt.delete()
                cb(fileno)

    def squelch_exception(self, fileno, exc_info):
        traceback.print_exception(*exc_info)
        print >>sys.stderr, "Removing descriptor: %r" % (fileno,)
        try:
            self.remove_descriptor(fileno)
        except Exception, e:
            print >>sys.stderr, "Exception while removing descriptor! %r" % (e,)
        
    def raise_keyboard_interrupt(self):
        self.interrupted = True
            
    def wait(self, seconds=None):
        if self.interrupted:
            raise KeyboardInterrupt()  

        if not self.readers and not self.writers:
            if seconds:
                sleep(seconds)
            return
        
        timer = event.timeout(seconds, lambda: None)
        timer.add()

        status = event.loop()
        if status == -1:
            raise RuntimeError("does this ever happen?")

