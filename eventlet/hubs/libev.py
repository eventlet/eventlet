"""\
@file libev.py

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

import ev as libev


class Hub(hub.BaseHub):
    def __init__(self, clock=time.time):
        super(Hub, self).__init__(clock)
        self.interrupted = False
        self._evloop = libev.default_loop()

        sig = libev.Signal(signal.SIGINT, self._evloop, self.signal_received, signal.SIGINT)
        sig.start()

    def add_descriptor(self, fileno, read=None, write=None, exc=None):
        if read:
            evt = libev.Io(fileno, libev.EV_READ, self._evloop, read, fileno)
            evt.start()
            self.readers[fileno] = evt, read

        if write:
            evt = libev.Io(fileno, libev.EV_WRITE, self._evloop, write, fileno)
            evt.start()
            self.writers[fileno] = evt, write

        if exc:
            self.excs[fileno] = exc

        self.waiters_by_greenlet[greenlet.getcurrent()] = fileno

    def remove_descriptor(self, fileno):
        for queue in (self.readers, self.writers):
            tpl = queue.pop(fileno, None)
            if tpl is not None:
                tpl[0].stop()
        self.excs.pop(fileno, None)
        self.waiters_by_greenlet.pop(greenlet.getcurrent(), None)

    def abort(self):
        super(Hub, self).abort()
        self._evloop.unloop()

    def signal_received(self, signal):
        # can't do more than set this flag here because the pyevent callback
        # mechanism swallows exceptions raised here, so we have to raise in 
        # the 'main' greenlet (in wait()) to kill the program
        self.interrupted = True
        self._evloop.unloop()

    def wait(self, seconds=None):
        # this timeout will cause us to return from the dispatch() call
        # when we want to
        timer = libev.Timer(seconds, 0, self._evloop, lambda *args: None)
        timer.start()

        try:
            status = self._evloop.loop()
        except self.SYSTEM_EXCEPTIONS:
            self.interrupted = True
        except:
            self.squelch_exception(-1, sys.exc_info())

        # we are explicitly ignoring the status because in our experience it's
        # harmless and there's nothing meaningful we could do with it anyway

        timer.stop()

        # raise any signals that deserve raising
        if self.interrupted:
            self.interrupted = False
            raise KeyboardInterrupt() 

    def add_timer(self, timer):
        # store the pyevent timer object so that we can cancel later
        eventtimer = libev.Timer(timer.seconds, 0, self._evloop, timer)
        timer.impltimer = eventtimer
        eventtimer.start()
        self.track_timer(timer)

    def timer_finished(self, timer):
        try:
            timer.impltimer.stop()
            del timer.impltimer
        # XXX might this raise other errors?
        except (AttributeError, TypeError):
            pass
        finally:
            super(Hub, self).timer_finished(timer)

    def timer_canceled(self, timer):
        """ Cancels the underlying libevent timer. """
        try:
            timer.impltimer.stop()
            del timer.impltimer
        except (AttributeError, TypeError):
            pass
        finally:
            super(Hub, self).timer_canceled(timer)
