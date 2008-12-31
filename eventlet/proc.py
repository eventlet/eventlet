# Copyright (c) 2008 Denis Bilenko
#
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

"""Advanced coroutine control.

This module provides means to spawn, kill and link coroutines. Linking is an
act of subscribing to the coroutine's result, either in form of return value
or unhandled exception.

To create a linkable coroutine use spawn function provided by this module:

>>> def demofunc(x, y):
...    return x / y

>>> p = spawn(demofunc, 6, 2)

The return value of spawn is an instance of Proc class that you can "link":

  * p.link(obj) - notify obj when the coroutine is finished

What does "notify" means here depends on the type of `obj': a callable is
simply called, an event or a queue is notified using send/send_exception
methods and if `obj' is another greenlet it's killed with LinkedExited
exception.

Here's an example:
>>> event = coros.event()
>>> p.link(event)
>>> event.wait()
3

Now, even though `p' is finished it's still possible to link it. In this
case the notification is performed immediatelly:

>>> p.link() # without an argument provided, links to the current greenlet
Traceback (most recent call last):
 ...
LinkedCompleted: linked proc 'demofunc' completed successfully

There are also link_return and link_raise methods that only deliver a return
value and an unhandled exception respectively (plain `link' deliver both).
Suppose we want to spawn a "child" greenlet to do an important part of the task,
but it it fails then there's no way to complete the task so the "parent" must
fail as well; `link_raise' is useful here:

>>> p = spawn(demofunc, 1, 0)
>>> p.link_raise()
>>> api.sleep(0.01)
Traceback (most recent call last):
 ...
LinkedFailed: linked proc 'demofunc' failed with ZeroDivisionError

One application of linking is `wait' function: link to a bunch of coroutines
and wait for all them to complete. Such function is provided by this module.
"""
import sys
from weakref import WeakKeyDictionary, ref
from inspect import getargspec

from eventlet import api, coros

# XXX works with CancellingTimersGreenlet but won't work with greenlet.greenlet (because of weakref)

__all__ = ['LinkedExited',
           'LinkedFailed',
           'LinkedCompleted',
           'LinkedKilled',
           'ProcKilled',
           'wait',
           'Proc',
           'spawn',
           'spawn_link',
           'spawn_link_return',
           'spawn_link_raise']

class LinkedExited(api.GreenletExit):
    """linked proc %r exited"""

    def __init__(self, msg=None, name=None):
        self.name = name
        if not msg:
            msg = self.__doc__ % self.name
        api.GreenletExit.__init__(self, msg)

#     def __str__(self):
#         msg = api.GreenletExit.__str__(self)
#         return msg or (self.__doc__ % self.name)

class LinkedFailed(LinkedExited):
    """linked proc %r failed"""

    def __init__(self, name, typ, _value=None, _tb=None):
        #msg = '%s with %s: %s' % (self.__doc__ % self.name, typ.__name__, value)
        msg = '%s with %s' % ((self.__doc__ % name), typ.__name__)
        LinkedExited.__init__(self, msg, name)

class LinkedCompleted(LinkedExited):
    """linked proc %r completed successfully"""

class LinkedKilled(LinkedCompleted):
    """linked proc %r was killed"""
    # This is a subclass of LinkedCompleted, because GreenletExit is returned,
    # not re-raised.

class ProcKilled(api.GreenletExit):
    """this proc was killed"""

def wait(linkable_or_list, trap_errors=False):
    if hasattr(linkable_or_list, 'link'):
        event = coros.event()
        linkable_or_list.link(event)
        try:
            return event.wait()
        except Exception:
            if trap_errors:
                return
            raise
    queue = coros.queue()
    results = [None] * len(linkable_or_list)
    for (index, linkable) in enumerate(linkable_or_list):
        linkable.link(decorate_send(queue, index), weak=False)
    count = 0
    while count < len(linkable_or_list):
        try:
            index, value = queue.wait()
        except Exception:
            if not trap_errors:
                raise
        else:
            results[index] = value
        count += 1
    return results

class decorate_send(object):
    #__slots__ = ['_event', '_tag', '__weakref__']

    def __init__(self, event, tag):
        self._event = event
        self._tag = tag

    def __getattr__(self, name):
        assert name != '_event'
        return getattr(self._event, name)

    def send(self, value):
        self._event.send((self._tag, value))


greenlet_class = api.CancellingTimersGreenlet # greenlet.greenlet
_NOT_USED = object()

def spawn_greenlet(function, *args):
    """Create a new greenlet that will run `function(*args)'.
    The current greenlet won't be unscheduled. Keyword arguments aren't
    supported (limitation of greenlet), use api.spawn to work around that.
    """
    g = greenlet_class(function)
    g.parent = api.get_hub().greenlet
    api.get_hub().schedule_call_global(0, g.switch, *args)
    return g

class Proc(object):

    def __init__(self, name=None):
        self.greenlet_ref = None
        self._receivers = WeakKeyDictionary()
        self._result = _NOT_USED
        self._exc = None
        self._kill_exc = None
        self.name = name

    @classmethod
    def spawn(cls, function, *args, **kwargs):
        """Return a new Proc instance that is scheduled to execute
        function(*args, **kwargs) upon the next hub iteration.
        """
        proc = cls()
        proc.run(function, *args, **kwargs)
        return proc

    def run(self, function, *args, **kwargs):
        """Create a new greenlet to execute `function(*args, **kwargs)'.
        Newly created greenlet is scheduled upon the next hub iteration, so
        the current greenlet won't be unscheduled.
        """
        assert self.greenlet_ref is None, "'run' can only be called once per instance"
        g = spawn_greenlet(self._run, function, args, kwargs)
        self.greenlet_ref = ref(g)
        if self.name is None:
            self.name = getattr(function, '__name__', None)
        if self.name is None:
            self.name = getattr(type(function), '__name__', '<unknown>')
        # return timer from schedule_call_global here?

    def _run(self, function, args, kwargs):
        """Execute *function* and send its result to receivers. If function
        raises GreenletExit it's trapped and treated as a regular value.
        """
        try:
            result = function(*args, **kwargs)
        except api.GreenletExit, ex:
            self._result = ex
            self._kill_exc = LinkedKilled(name=self.name)
            self._deliver_result()
        except:
            self._result = None
            self._exc = sys.exc_info()
            self._kill_exc = LinkedFailed(self.name, *sys.exc_info())
            self._deliver_exception()
            raise # let mainloop log the exception
        else:
            self._result = result
            self._kill_exc = LinkedCompleted(name=self.name)
            self._deliver_result()

    # spawn_later/run_later can be also implemented here

    @property
    def greenlet(self):
        if self.greenlet_ref is not None:
            return self.greenlet_ref()

    @property
    def ready(self):
        return self._result is not _NOT_USED

    def __nonzero__(self):
        if self.ready:
            # greenlet's function may already finish yet the greenlet is still alive
            # delivering the result to receivers (if some of send methods were blocking)
            # we consider such greenlet finished
            return False
        # otherwise bool(proc) is the same as bool(greenlet)
        if self.greenlet is not None:
            return bool(self.greenlet)

    def _repr_helper(self):
        klass = type(self).__name__
        if self.greenlet is not None and self.greenlet.dead:
            dead = '(dead)'
        else:
            dead = ''
        result = ''
        if self._result is not _NOT_USED:
            if self._exc is None:
                result = ' result=%r' % self._result
            else:
                result = ' failed'
        return '%s greenlet=%r%s rcvrs=%s%s' % (klass, self.greenlet, dead, len(self._receivers), result)

    def __repr__(self):
        return '<%s>' % (self._repr_helper())

    def kill(self, *throw_args):
        """Raise ProcKilled exception (a subclass of GreenletExit) in this
        greenlet that will cause it to die. When this function returns,
        the greenlet is usually dead, unless it catched GreenletExit.
        """
        greenlet = self.greenlet
        if greenlet is not None and not self.ready:
            if not throw_args:
                throw_args = (ProcKilled, )
            return api.kill(greenlet, *throw_args)

    def link_return(self, listener=None, weak=None):
        """Establish a link between this Proc and `listener' (the current
        greenlet by default), such that `listener' will receive a notification
        when this Proc exits cleanly or killed with GreenletExit or a subclass.

        Any previous link is discarded, so calling link_return and then
        link_raise is not the same as calling link.

        See `link' function for more details.
        """
        if listener is None:
            listener = api.getcurrent()
        if listener is self:
            raise ValueError("Linking to self is pointless")
        if self._result is not _NOT_USED and self._exc is not None:
            return
        deliverer = _get_deliverer_for_value(listener, weak)
        if self._result is not _NOT_USED:
            deliverer.deliver_value(listener, self._result, self._kill_exc)
        else:
            self._receivers[listener] = deliverer

    # add link_completed link_killed ?

    def link_raise(self, listener=None, weak=None):
        """Establish a link between this Proc and `listener' (the current
        greenlet by default), such that `listener' will receive a notification
        when this Proc exits because of unhandled exception. Note, that
        unhandled GreenletExit (or a subclass) is a special case and and will
        not be re-raised. No link will be established if the Proc has already
        exited cleanly or was killed.

        Any previous link is discarded, so calling link_return and then
        link_raise is not the same as calling link.

        See `link' function for more details.
        """
        if listener is None:
            listener = api.getcurrent()
        if listener is self:
            raise ValueError("Linking to self is pointless")
        if self._result is not _NOT_USED and self._exc is None:
            return
        deliverer = _get_deliverer_for_error(listener, weak)
        if self._result is not _NOT_USED:
            deliverer.deliver_error(listener, self._exc, self._kill_exc)
        else:
            self._receivers[listener] = deliverer

    def link(self, listener=None, weak=None):
        """Establish a link between this Proc and `listener' (the current
        greenlet by default), such that `listener' will receive a notification
        when this Proc exits.

        The can be only one link from this Proc to `listener'. A new link
        discards a previous link if there was one. After the notification is
        performed the link is no longer needed and is removed.

        How a notification is delivered depends on the type of `listener':

        1. If `listener' is an event or a queue or something else with 
           send/send_exception methods, these are used to deliver the result.

        2. If `listener' is a Proc or a greenlet or something else with
           throw method then it's used to raise a subclass of LinkedExited;
           whichever subclass is used depends on how this Proc died.
        
        3. If `listener' is a callable, it is called with one argument if this
           greenlet exits cleanly or with 3 arguments (typ, val, tb) if this
           greenlet dies because of an unhandled exception.

        Note that the subclasses of GreenletExit are delivered as return values.

        If `weak' is True, Proc stores the strong reference to the listener;
        if `weak' is False, then a weakref is used and no new references to
        the `listener' are created. Such link will disappear when `listener'
        disappers.
        if `weak' argument is not provided or is None then weak link is
        created unless it's impossible to do so or `listener' is callable.

        To ignore unhandled exceptions use `link_return' method. To receive only
        the exception and not return values or GreenletExits use `link_raise' method.
        Note, that GreenletExit is treated specially and is delivered as a value,
        not as an exception (i.e. send method is used to deliver it and not
        send_exception).
        """
        if listener is None:
            listener = api.getcurrent()
        if listener is self:
            raise ValueError("Linking to self is pointless")
        deliverer = _get_deliverer_for_any(listener, weak)
        if self._result is not _NOT_USED:
            if self._exc is None:
                deliverer.deliver_value(listener, self._result, self._kill_exc)
            else:
                deliverer.deliver_error(listener, self._exc, self._kill_exc)
        else:
            self._receivers[listener] = deliverer

    # XXX check how many arguments listener accepts: for link must be one or 3
    # for link_return must be 1, for link_raise must be 3, toherwise raise TypeError
    

    def unlink(self, listener=None):
        if listener is None:
            listener = api.getcurrent()
        self._receivers.pop(listener, None)

    def __enter__(self):
        self.link()

    def __exit__(self, *args):
        self.unlink()

    # add send/send_exception here

    def wait(self):
        if self._result is _NOT_USED:
            event = coros.event()
            self.link(event)
            return event.wait()
        elif self._exc is None:
            return self._result
        else:
            api.getcurrent().throw(*self._exc)

    def poll(self, notready=None):
        if self._result is not _NOT_USED:
            if self._exc is None:
                return self._result
            else:
                api.getcurrent().throw(*self._exc)
        return notready

    def _deliver_result(self):
        while self._receivers:
            listener, deliverer = self._receivers.popitem()
            try:
                deliverer.deliver_value(listener, self._result, self._kill_exc)
            except:
                # this greenlet has to die so that the error is logged by the hub
                # spawn a new greenlet to finish the job
                if self._receivers:
                    spawn(self._deliver_result)
                raise

    def _deliver_exception(self):
        while self._receivers:
            listener, deliverer = self._receivers.popitem()
            try:
                deliverer.deliver_error(listener, self._exc, self._kill_exc)
            except:
                # this greenlet has to die so that the exception will be logged
                # the original exception is, however, lost
                # spawn a new greenlet to finish the job
                if self._receivers:
                    spawn_greenlet(self._deliver_exception)
                raise

# XXX the following is not exactly object-oriented
# XXX add __deliver_error__ and __deliver_result__ methods to event, queue, Proc?
# would still need special cases for callback and greenlet
# QQQ add __call__ to event (and queue) such that it can be treated as callable by link()?
# QQQ add better yet, add send/send_exception to Proc

def argnum(func):
    """Return minimal and maximum number of args that func can accept
    >>> (0, sys.maxint) == argnum(lambda *args: None)
    True
    >>> argnum(lambda x: None)
    (1, 1)
    >>> argnum(lambda x, y, z=5, a=6: None)
    (2, 4)
    """
    args, varargs, varkw, defaults = getargspec(func)
    if varargs is not None:
        return 0, sys.maxint
    return len(args)-len(defaults or []), len(args)

def _get_deliverer_for_value(listener, weak):
    if hasattr(listener, 'send'):
        return _deliver_value_to_event(listener, weak)
    elif hasattr(listener, 'greenlet_ref'):
        return _deliver_value_to_proc(listener, weak)
    elif hasattr(listener, 'throw'):
        return _deliver_value_to_greenlet(listener, weak)
    elif callable(listener):
        min, max = argnum(listener)
        if min <= 1 <= max:
            return _deliver_value_to_callback(listener, weak)
        raise TypeError('function must support one argument: %r' % listener)
    else:
        raise TypeError('Cannot link to %r' % (listener, )) 

def _get_deliverer_for_error(listener, weak):
    if hasattr(listener, 'send_exception'):
        return _deliver_error_to_event(listener, weak)
    elif hasattr(listener, 'greenlet_ref'):
        return _deliver_error_to_proc(listener, weak)
    elif hasattr(listener, 'throw'):
        return _deliver_error_to_greenlet(listener, weak)
    elif callable(listener):
        min, max = argnum(listener)
        if min <= 3 <= max:
            return _deliver_error_to_callback(listener, weak)
        raise TypeError('function must support three arguments: %r' % listener)
    else:
        raise TypeError('Cannot link to %r' % (listener, )) 

def _get_deliverer_for_any(listener, weak):
    if hasattr(listener, 'send') and hasattr(listener, 'send_exception'):
        return _deliver_to_event(listener, weak)
    elif hasattr(listener, 'greenlet_ref'):
        return _deliver_to_proc(listener, weak)
    elif hasattr(listener, 'throw'):
        return _deliver_to_greenlet(listener, weak)
    elif callable(listener):
        min, max = argnum(listener)
        if min <= 1 and 3 <= max:
            return _deliver_to_callback(listener, weak)
        raise TypeError('function must support one or three arguments: %r' % listener)
    else:
        raise TypeError('Cannot link to %r' % (listener, ))

noop = staticmethod(lambda *args: None)

class _base:
    weak = True

    def __new__(cls, listener, weak):
        if weak is None:
            weak = cls.weak
        if weak:
            return cls
        return cls(listener)

    def __init__(self, listener, weak):
        assert not weak, 'for weak links just return the class object, no need for an instance'
        self._hold_ref = listener

class _deliver_to_callback(_base):
    weak = False

    @staticmethod
    def deliver_value(callback, value, _):
        callback(value)

    @staticmethod
    def deliver_error(callback, throw_args, _):
        callback(*throw_args)

class _deliver_value_to_callback(_deliver_to_callback):
    deliver_error = noop

class _deliver_error_to_callback(_deliver_to_callback):
    deliver_value = noop

class _deliver_to_event(_base):

    @staticmethod
    def deliver_value(event, value, _):
        event.send(value)

    @staticmethod
    def deliver_error(event, throw_args, _):
        event.send_exception(*throw_args)

class _deliver_value_to_event(_deliver_to_event):
    deliver_error = noop

class _deliver_error_to_event(_deliver_to_event):
    deliver_value = noop

def _deliver_kill_exc_to_greenlet(greenlet, _, kill_exc):
    if greenlet is api.getcurrent():
        raise kill_exc
    elif greenlet is not None:
        if greenlet.dead:
            return
        # if greenlet was not started, we still want to schedule throw
        # BUG: if greenlet was unlinked must not throw
        api.get_hub().schedule_call_global(0, greenlet.throw, kill_exc)

class _deliver_to_greenlet(_base):
    deliver_value = staticmethod(_deliver_kill_exc_to_greenlet)
    deliver_error = staticmethod(_deliver_kill_exc_to_greenlet)

class _deliver_value_to_greenlet(_deliver_to_greenlet):
    deliver_error = noop

class _deliver_error_to_greenlet(_deliver_to_greenlet):
    deliver_value = noop

def _deliver_kill_exc_to_proc(proc, _, kill_exc):
    _deliver_kill_exc_to_greenlet(proc.greenlet, _, kill_exc)

class _deliver_to_proc(_base):
    deliver_value = staticmethod(_deliver_kill_exc_to_proc)
    deliver_error = staticmethod(_deliver_kill_exc_to_proc)

class _deliver_value_to_proc(_deliver_to_proc):
    deliver_error = noop

class _deliver_error_to_proc(_deliver_to_proc):
    deliver_value = noop


spawn = Proc.spawn

def spawn_link(function, *args, **kwargs):
    p = spawn(function, *args, **kwargs)
    p.link()
    return p

def spawn_link_return(function, *args, **kwargs):
    p = spawn(function, *args, **kwargs)
    p.link_return()
    return p

def spawn_link_raise(function, *args, **kwargs):
    p = spawn(function, *args, **kwargs)
    p.link_raise()
    return p


class Pool(object):

    linkable_class = Proc

    def __init__(self, limit):
        self.semaphore = coros.Semaphore(limit)

    def allocate(self):
        self.semaphore.acquire()
        g = self.linkable_class()
        g.link(lambda *_args: self.semaphore.release())
        return g

# not fully supports all types of listeners
def forward(queue, listener, tag):
    while True:
        try:
            result = queue.wait()
        except Exception:
            listener.send_exception(*sys.exc_info())
        else:
            listener.send((tag, result))

# class Supervisor(object):
#     max_restarts=3
#     max_restarts_period=30
# 
#     def __init__(self, max_restarts=None, max_restarts_period=None):
#         if max_restarts is not None:
#             self.max_restarts = max_restarts
#         if max_restarts_period is not None:
#             self.max_restarts_period = max_restarts_period
# 
    #def spawn_child(self, function, *args, **kwargs):
#    def supervise(self, proc, max_restarts, max_restarts_period, restarts_delay):



if __name__=='__main__':
    import doctest
    doctest.testmod()
