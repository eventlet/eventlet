"""\
@file greenlib.py
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
import itertools

import greenlet

from eventlet import tls

__all__ = [
    'switch', 'kill', 'tracked_greenlets',
    'greenlet_id', 'greenlet_dict', 'GreenletContext',
    'tracked_greenlet',
]

try:
    reversed
except NameError:
    def reversed(something):
        for x in something[::-1]:
            yield x

_threadlocal = tls.local()

def tracked_greenlet():
    """
    Returns a greenlet that has a greenlet-local dictionary and can be
    used with GreenletContext and enumerated with tracked_greenlets
    """
    return greenlet.greenlet(greenlet_body)

class GreenletContextManager(object):
    """
    Per-thread manager for GreenletContext.  Created lazily on registration
    """
    def __new__(cls, *args, **kw):
        dct = greenlet_dict()
        self = dct.get('greenlet_context', None)
        if self is not None:
            return self
        self = super(GreenletContextManager, cls).__new__(cls, *args, **kw)
        dct['greenlet_context'] = self
        self.contexts = []
        return self

    def add_context(self, ctx):
        fn = getattr(ctx, '_swap_in', None)
        if fn is not None:
            fn()
        self.contexts.append(ctx)

    def remove_context(self, ctx):
        try:
            idx = self.contexts.index(ctx)
        except ValueError:
            return
        else:
            del self.contexts[idx]
        fn = getattr(ctx, '_swap_out', None)
        if fn is not None:
            fn()
        fn = getattr(ctx, '_finalize', None)
        if fn is not None:
            fn()

    def swap_in(self):
        for ctx in self.contexts:
            fn = getattr(ctx, '_swap_in', None)
            if fn is not None:
                fn()

    def swap_out(self):
        for ctx in reversed(self.contexts):
            fn = getattr(ctx, '_swap_out', None)
            if fn is not None:
                fn()

    def finalize(self):
        for ctx in reversed(self.contexts):
            fn = getattr(ctx, '_swap_out', None)
            if fn is not None:
                fn()
            fn = getattr(ctx, '_finalize', None)
            if fn is not None:
                fn()
        del self.contexts[:]
        try:
            del greenlet_dict()['greenlet_context']
        except KeyError:
            pass

class GreenletContext(object):
    """
    A context manager to be triggered when a specific tracked greenlet is
    swapped in, swapped out, or finalized.

    To use, subclass and override the swap_in, swap_out, and/or finalize
    methods, for example::
        
        import greenlib
        from greenlib import greenlet_id, tracked_greenlet, switch

        class NotifyContext(greenlib.GreenletContext):

            def swap_in(self):
                print "swap_in"

            def swap_out(self):
                print "swap_out"

            def finalize(self):
                print "finalize"

        def another_greenlet():
            print "another_greenlet"

        def notify_demo():
            print "starting"
            NotifyContext().register()
            switch(tracked_greenlet(), (another_greenlet,))
            print "finishing"
            # we could have kept the NotifyContext object
            # to unregister it here but finalization of all
            # contexts is implicit when the greenlet returns

        t = tracked_greenlet()
        switch(t, (notify_demo,))

    The output should be:

        starting
        swap_in
        swap_out
        another_greenlet
        swap_in
        finishing
        swap_out
        finalize
    
    """
    _balance = 0
    
    def _swap_in(self):
        if self._balance != 0:
            raise RuntimeError("balance != 0: %r" % (self._balance,))
        self._balance = self._balance + 1
        fn = getattr(self, 'swap_in', None)
        if fn is not None:
            fn()

    def _swap_out(self):
        if self._balance != 1:
            raise RuntimeError("balance != 1: %r" % (self._balance,))
        self._balance = self._balance - 1
        fn = getattr(self, 'swap_out', None)
        if fn is not None:
            fn()

    def register(self):
        GreenletContextManager().add_context(self)

    def unregister(self):
        GreenletContextManager().remove_context(self)

    def _finalize(self):
        fn = getattr(self, 'finalize', None)
        if fn is not None:
            fn()


def kill(g):
    """
    Kill the given greenlet if it is alive by sending it a GreenletExit.
    
    Note that of any other exception is raised, it will pass-through!
    """
    if not g:
        return
    kill_exc = greenlet.GreenletExit()
    try:
        try:
            g.parent = greenlet.getcurrent()
        except ValueError:
            pass
        try:
            switch(g, exc=kill_exc)
        except SwitchingToDeadGreenlet:
            pass
    except greenlet.GreenletExit, e:
        if e is not kill_exc:
            raise

def tracked_greenlets():
    """
    Return a list of greenlets tracked in this thread.  Tracked greenlets
    use greenlet_body() to ensure that they have greenlet-local storage.
    """
    try:
        return _threadlocal.greenlets.keys()
    except AttributeError:
        return []

def greenlet_id():
    """
    Get the id of the current tracked greenlet, returns None if the
    greenlet is not tracked.
    """
    try:
        d = greenlet_dict()
    except RuntimeError:
        return None
    return d['greenlet_id']

def greenlet_dict():
    """
    Return the greenlet local storage for this greenlet.  Raises RuntimeError
    if this greenlet is not tracked.
    """
    self = greenlet.getcurrent()
    try:
        return _threadlocal.greenlets[self]
    except (AttributeError, KeyError):
        raise RuntimeError("greenlet %r is not tracked" % (self,))

def _greenlet_context(dct=None):
    if dct is None:
        try:
            dct = greenlet_dict()
        except RuntimeError:
            return None
    return dct.get('greenlet_context', None)

def _greenlet_context_call(name, dct=None):
    ctx = _greenlet_context(dct)
    fn = getattr(ctx, name, None)
    if fn is not None:
        fn()

def greenlet_body(value, exc):
    """
    Track the current greenlet during the execution of the given callback,
    normally you would use tracked_greenlet() to get a greenlet that uses this.

    Greenlets using this body must be greenlib.switch()'ed to
    """
    from eventlet import api
    if exc is not None:
        if isinstance(exc, tuple):
            raise exc[0], exc[1], exc[2]
        raise exc
    cb, args = value[0], value[1:]
    try:
        greenlets = _threadlocal.greenlets
    except AttributeError:
        greenlets = _threadlocal.greenlets = {}
    else:
        if greenlet.getcurrent() in greenlets:
            raise RuntimeError("greenlet_body can not be called recursively!")
    try:
        greenlet_id = _threadlocal.next_greenlet_id.next()
    except AttributeError:
        greenlet_id = 1
        _threadlocal.next_greenlet_id = itertools.count(2)
    cur = greenlet.getcurrent()
    greenlets[cur] = {'greenlet_id': greenlet_id}
    try:
        return cb(*args)
    finally:
        _greenlet_context_call('finalize')
        greenlets.pop(cur, None)
        api.get_hub().cancel_timers(cur, quiet=True)


class SwitchingToDeadGreenlet(RuntimeError):
    pass


def switch(other=None, value=None, exc=None):
    """
    Switch to another greenlet, passing value or exception
    """
    self = greenlet.getcurrent()
    if other is None:
        other = self.parent
    if other is None:
        other = self
    if not (other or hasattr(other, 'run')):
        raise SwitchingToDeadGreenlet("Switching to dead greenlet %r %r %r" % (other, value, exc))
    _greenlet_context_call('swap_out')
    sys.exc_clear()  # don't pass along exceptions to the other coroutine
    try:
        rval = other.switch(value, exc)
        if not rval or not other:
            res, exc = rval, None
        else:
            res, exc = rval
    except:
        res, exc = None, sys.exc_info()
    _greenlet_context_call('swap_in')
    # *NOTE: we don't restore exc_info, so don't switch inside an
    # exception handler and then call sys.exc_info() or use bare
    # raise.  Instead, explicitly save off the exception before
    # switching.  We need an extension that allows us to restore the
    # exception state at this point because vanilla Python doesn't
    # allow that.
    if isinstance(exc, tuple):
        typ, exc, tb = exc
        raise typ, exc, tb
    elif exc is not None:
        raise exc
    
    return res
