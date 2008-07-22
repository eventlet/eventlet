"""\
@file timer.py
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
from eventlet.api import get_hub

""" If true, captures a stack trace for each timer when constructed.  This is
useful for debugging leaking timers, to find out where the timer was set up. """
_g_debug = False

class Timer(object):
    #__slots__ = ['seconds', 'tpl', 'called', 'cancelled', 'scheduled_time', 'greenlet', 'traceback', 'impltimer']
    def __init__(self, seconds, cb, *args, **kw):
        """Create a timer.
            seconds: The minimum number of seconds to wait before calling
            cb: The callback to call when the timer has expired
            *args: The arguments to pass to cb
            **kw: The keyword arguments to pass to cb

        This timer will not be run unless it is scheduled in a runloop by
        calling timer.schedule() or runloop.add_timer(timer).
        """
        self.cancelled = False
        self.seconds = seconds
        self.tpl = cb, args, kw
        self.called = False
        if _g_debug:
            import traceback, cStringIO
            self.traceback = cStringIO.StringIO()
            traceback.print_stack(file=self.traceback)

    def __repr__(self):
        secs = getattr(self, 'seconds', None)
        cb, args, kw = getattr(self, 'tpl', (None, None, None))
        retval =  "Timer(%s, %s, *%s, **%s)" % (
            secs, cb, args, kw)
        if _g_debug and hasattr(self, 'traceback'):
            retval += '\n' + self.traceback.getvalue()
        return retval

    def copy(self):
        cb, args, kw = self.tpl
        return self.__class__(self.seconds, cb, *args, **kw)

    def schedule(self):
        """Schedule this timer to run in the current runloop.
        """
        self.called = False
        self.scheduled_time = get_hub().add_timer(self)
        return self

    def __call__(self, *args):
        if not self.called:
            self.called = True
            cb, args, kw = self.tpl
            try:
                cb(*args, **kw)
            finally:
                get_hub().timer_finished(self)

    def cancel(self):
        """Prevent this timer from being called. If the timer has already
        been called, has no effect.
        """
        self.cancelled = True
        self.called = True
        get_hub().timer_canceled(self)
