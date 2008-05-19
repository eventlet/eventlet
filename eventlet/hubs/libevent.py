"""\
@file libevent.py

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
import signal
import sys
import socket
import errno
import traceback
import time

from eventlet import greenlib
from eventlet.timer import Timer
from eventlet.hubs import hub

import greenlet

# XXX for debugging only
#raise ImportError()

try:
    # use rel if available
    import rel
    rel.initialize()
    rel.override()
except ImportError:
    # don't have rel, but might still have libevent
    pass
    
import event


class Hub(hub.BaseHub):    
    def __init__(self, clock=time.time):
        super(Hub, self).__init__(clock)
        self.interrupted = False
        event.init()
        
        sig = event.signal(signal.SIGINT, self.signal_received, signal.SIGINT)
        sig.add()


    def add_descriptor(self, fileno, read=None, write=None, exc=None):
        if read:
            evt = event.read(fileno, read, fileno)
            evt.add()
            self.readers[fileno] = evt, read

        if write:
            evt = event.write(fileno, write, fileno)
            evt.add()
            self.writers[fileno] = evt, write
            
        if exc:
            self.excs[fileno] = exc
        
    def remove_descriptor(self, fileno):
        for queue in (self.readers, self.writers):
            tpl = queue.pop(fileno, None)
            if tpl is not None:
                tpl[0].delete()
        self.excs.pop(fileno, None)
        
    def abort(self):
        super(Hub, self).abort()
        event.abort()
        
    def signal_received(self, signal):
        # can't do more than set this flag here because the pyevent callback
        # mechanism swallows exceptions raised here, so we have to raise in 
        # the 'main' greenlet (in wait()) to kill the program
        self.interrupted = True
        event.abort()
            
    def wait(self, seconds=None):
        # this timeout will cause us to return from the dispatch() call
        # when we want to
        timer = event.timeout(seconds, lambda: None)
        timer.add()

        status = event.dispatch()
        # we are explicitly ignoring the status because in our experience it's
        # harmless and there's nothing meaningful we could do with it anyway
                
        timer.delete()
        
        # raise any signals that deserve raising
        if self.interrupted:
            self.interrupted = False
            raise KeyboardInterrupt() 

    def add_timer(self, timer):
        # store the pyevent timer object so that we can cancel later
        eventtimer = event.timeout(timer.seconds, timer)
        timer.impltimer = eventtimer
        eventtimer.add()
        self.track_timer(timer)
        
    def timer_canceled(self, timer):
        """ Cancels the underlying libevent timer. """
        try:
            timer.impltimer.delete()
        except AttributeError:
            pass

