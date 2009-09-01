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
from eventlet.hubs.hub import BaseHub, FdListener, READ, WRITE


class event_wrapper(object):

    def __init__(self, impl=None, seconds=None):
        self.impl = impl
        self.seconds = seconds

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


class Hub(BaseHub):

    SYSTEM_EXCEPTIONS = (KeyboardInterrupt, SystemExit)

    def __init__(self, clock=time.time):
        super(Hub,self).__init__(clock)
        event.init()
        
        self.signal_exc_info = None
        self.signal(2, lambda signalnum, frame: self.greenlet.parent.throw(KeyboardInterrupt))
        self.events_to_add = []
        
    def closed(self, fd):
        pass

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

    def dispatch(self):
        loop = event.loop
        while True:
            for e in self.events_to_add:
                if e is not None and e.impl is not None and e.seconds is not None:
                    e.impl.add(e.seconds)
                    e.seconds = None
            self.events_to_add = []
            result = loop()

            if getattr(event, '__event_exc', None) is not None:
                # only have to do this because of bug in event.loop
                t = getattr(event, '__event_exc')
                setattr(event, '__event_exc', None)
                assert getattr(event, '__event_exc') is None
                raise t[0], t[1], t[2]

            if result != 0:
                return result

    def run(self):
        while True:
            try:
                self.dispatch()
            except api.GreenletExit:
                break
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                if self.signal_exc_info is not None:
                    self.schedule_call_global(0, api.getcurrent().parent.throw, *self.signal_exc_info)
                    self.signal_exc_info = None
                else:
                    traceback.print_exc()

    def abort(self):
        self.schedule_call_global(0, self.greenlet.throw, api.GreenletExit)

    def _getrunning(self):
        return bool(self.greenlet)
    
    def _setrunning(self, value):
        pass  # exists for compatibility with BaseHub
    running = property(_getrunning, _setrunning)

    def add(self, evtype, fileno, cb):
        if evtype is READ:
            evt = event.read(fileno, cb, fileno)
        elif evtype is WRITE:
            evt = event.write(fileno, cb, fileno)
            
        listener = FdListener(evtype, fileno, evt)
        self.listeners[evtype].setdefault(fileno, []).append(listener)
        return listener

    def signal(self, signalnum, handler):
        def wrapper():
            try:
                handler(signalnum, None)
            except:
                self.signal_exc_info = sys.exc_info()
                event.abort()
        return event_wrapper(event.signal(signalnum, wrapper))
    
    def remove(self, listener):
        super(Hub, self).remove(listener)
        listener.cb.delete()
      
    def remove_descriptor(self, fileno):
        for lcontainer in self.listeners.itervalues():
            l_list = lcontainer.pop(fileno, None)
            for listener in l_list:
                try:
                    listener.cb.delete()
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    traceback.print_exc()
                    
    def schedule_call_local(self, seconds, cb, *args, **kwargs):
        current = api.getcurrent()
        if current is self.greenlet:
            return self.schedule_call_global(seconds, cb, *args, **kwargs)
        event_impl = event.event(_scheduled_call_local, (cb, args, kwargs, current))
        wrapper = event_wrapper(event_impl, seconds=seconds)
        self.events_to_add.append(wrapper)
        return wrapper

    schedule_call = schedule_call_local

    def schedule_call_global(self, seconds, cb, *args, **kwargs):
        event_impl = event.event(_scheduled_call, (cb, args, kwargs))
        wrapper = event_wrapper(event_impl, seconds=seconds)
        self.events_to_add.append(wrapper)
        return wrapper
        
    def _version_info(self):
        baseversion = event.__version__
        return baseversion


def _scheduled_call(event_impl, handle, evtype, arg):
    cb, args, kwargs = arg
    try:
        cb(*args, **kwargs)
    finally:
        event_impl.delete()

def _scheduled_call_local(event_impl, handle, evtype, arg):
    cb, args, kwargs, caller_greenlet = arg
    try:
        if not caller_greenlet.dead:
            cb(*args, **kwargs)
    finally:
        event_impl.delete()

