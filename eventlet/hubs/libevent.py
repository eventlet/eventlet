# Copyright (c) 2007, Linden Research, Inc.
# Copyright (c) 2009 Denis Bilenko
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import sys
import time
import traceback
import event

from eventlet import api


class event_wrapper(object):

    def __init__(self, impl):
        self.impl = impl

    def __repr__(self):
        if self.impl is not None:
            return repr(self.impl)
        else:
            return object.__repr__(self)

    def __str__(self):
        if self.impl is not None:
            return str(self.impl)
        else:
            return object.__str__(self)

    def cancel(self):
        if self.impl is not None:
            self.impl.delete()
            self.impl = None


class LocalTimer(event_wrapper):

    def __init__(self, cb, args, kwargs):
        self.tpl =  cb, args, kwargs
        self.greenlet = api.getcurrent()
        # 'impl' attribute must be set to libevent's timeout instance

    def __call__(self):
        if self.greenlet:
            cb, args, kwargs = self.tpl
            cb(*args, **kwargs)


class Hub(object):

    SYSTEM_EXCEPTIONS = (KeyboardInterrupt, SystemExit, api.GreenletExit)

    def __init__(self, clock=time.time):
        event.init()
        self.clock = clock
        self.readers = {}
        self.writers = {}
        self.excs = {}
        self.greenlet = api.Greenlet(self.run)
        self.exc_info = None
        self.signal(2, lambda signalnum, frame: self.greenlet.parent.throw(KeyboardInterrupt))

    def switch(self):
        cur = api.getcurrent()
        assert cur is not self.greenlet, 'Cannot switch to MAINLOOP from MAINLOOP'
        switch_out = getattr(cur, 'switch_out', None)
        if switch_out is not None:
            try:
                switch_out()
            except:
                traceback.print_exception(*sys.exc_info())
        if self.greenlet.dead:
            self.greenlet = api.Greenlet(self.run)
        try:
            api.getcurrent().parent = self.greenlet
        except ValueError:
            pass
        return self.greenlet.switch()
 
    def run(self):
        while True:
            try:
                event.dispatch()
                break
            except api.GreenletExit:
                break
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                if self.exc_info is not None:
                    self.schedule_call_global(0, api.getcurrent().parent.throw, *self.exc_info)
                    self.exc_info = None
                else:
                    traceback.print_exc()

    def abort(self):
        # schedule an exception, because otherwise dispatch() will not exit if
        # there are timeouts scheduled
        self.schedule_call_global(0, self.greenlet.throw, api.GreenletExit)
        event.abort()

    @property
    def running(self):
        return bool(self.greenlet)

    def add_descriptor(self, fileno, read=None, write=None, exc=None):
        if read:
            evt = event.read(fileno, read, fileno)
            self.readers[fileno] = evt, read

        if write:
            evt = event.write(fileno, write, fileno)
            self.writers[fileno] = evt, write

        if exc:
            self.excs[fileno] = exc

        return fileno

    def signal(self, signalnum, handler):
        def wrapper():
            try:
                handler(signalnum, None)
            except:
                self.exc_info = sys.exc_info()
                event.abort()
        return event_wrapper(event.signal(signalnum, wrapper))

    def remove_descriptor(self, fileno):
        for queue in (self.readers, self.writers):
            tpl = queue.pop(fileno, None)
            if tpl is not None:
                tpl[0].delete()
        self.excs.pop(fileno, None)

    def schedule_call_local(self, seconds, cb, *args, **kwargs):
        timer = LocalTimer(cb, args, kwargs)
        event_timeout = event.timeout(seconds, timer)
        timer.impl = event_timeout
        return timer

    schedule_call = schedule_call_local

    def schedule_call_global(self, seconds, cb, *args, **kwargs):
        event_timeout = event.timeout(seconds, lambda : cb(*args, **kwargs) and None)
        return event_wrapper(event_timeout)

    def exc_descriptor(self, fileno):
        exc = self.excs.get(fileno)
        if exc is not None:
            try:
                exc(fileno)
            except:
                traceback.print_exc()

    def timer_finished(self, t): pass
    def timer_canceled(self, t): pass

    def get_readers(self):
        return self.readers

    def get_writers(self):
        return self.writers

    def get_excs(self):
        return self.excs

