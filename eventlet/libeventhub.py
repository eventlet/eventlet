"""\
@file libeventhub.py

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

import bisect
import sys
import socket
import errno
import traceback
import time

from eventlet import greenlib
from eventlet.timer import Timer
from eventlet import hub

import greenlet

try:
    # use rel if it's available
    import rel
    rel.initialize()
    rel.override()
except ImportError:
    pass

import event


class Hub(hub.Hub):
    SYSTEM_EXCEPTIONS = (KeyboardInterrupt, SystemExit)
    
    def __init__(self, clock=time.time):
        super(Hub, self).__init__(clock)
        self.interrupted = False
        event.init()
        
        # catch SIGINT
        signal = event.signal(2, self.signal_received, 2)
        signal.add()


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
        
    def signal_received(self, signal):
        self.interrupted = True
            
    def wait(self, seconds=None):
        if self.interrupted:
            raise KeyboardInterrupt()  
        
        timer = event.timeout(seconds, lambda: None)
        timer.add()

        status = event.loop()
        if status == -1:
            raise RuntimeError("does this ever happen?")

        timer.delete()

    def add_timer(self, timer):
        event.timeout(timer.seconds, timer).add()

