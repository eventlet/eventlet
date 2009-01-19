# Copyright (c) 2008-2009 AG Projects
# Author: Denis Bilenko
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

This module provides means to spawn, kill and link coroutines. Linking means
subscribing to the coroutine's result, either in form of return value or
unhandled exception.

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

>>> p.link()
>>> api.sleep(0)
Traceback (most recent call last):
 ...
LinkedCompleted: '<function demofunc at 0x...>' completed successfully

(Without an argument, link is created to the current greenlet)

There are also link_value and link_exception methods that only deliver a return
value and an unhandled exception respectively (plain `link' deliver both).
Suppose we want to spawn a greenlet to do an important part of the task; if it
fails then there's no way to complete the task so the parent must fail as well;
`link_exception' is useful here:

>>> p = spawn(demofunc, 1, 0)
>>> p.link_exception()
>>> api.sleep(0.01)
Traceback (most recent call last):
 ...
LinkedFailed: '<function demofunc at 0x...>' failed with ZeroDivisionError

One application of linking is `waitall' function: link to a bunch of coroutines
and wait for all them to complete. Such function is provided by this module.
"""
import sys
from eventlet import api, coros

__all__ = ['LinkedExited',
           'LinkedFailed',
           'LinkedCompleted',
           'LinkedKilled',
           'ProcExit',
           'wait',
           'Proc',
           'spawn',
           'spawn_link',
           'spawn_link_value',
           'spawn_link_exception']

class LinkedExited(Exception):
    """Raised when a linked proc exits"""
    msg = "%r exited"

    def __init__(self, name=None, msg=None):
        self.name = name
        if msg is None:
            msg = self.msg % self.name
        api.GreenletExit.__init__(self, msg)

class LinkedFailed(LinkedExited):
    """Raised when a linked proc dies because of unhandled exception"""
    msg = "%r failed with %s"

    def __init__(self, name, typ, value=None, tb=None):
        msg = self.msg % (name, typ.__name__)
        LinkedExited.__init__(self, name, msg)

class LinkedCompleted(LinkedExited):
    """Raised when a linked proc finishes the execution cleanly"""

    msg = "%r completed successfully"

class LinkedKilled(LinkedFailed):
    """Raised when a linked proc dies because of unhandled GreenletExit
    (i.e. it was killed)
    """
    msg = """%r was killed with %s"""

def getLinkedFailed(name, typ, value=None, tb=None):
    if issubclass(typ, api.GreenletExit):
        return LinkedKilled(name, typ, value, tb)
    return LinkedFailed(name, typ, value, tb)


class ProcExit(api.GreenletExit):
    """Raised when this proc is killed."""

SUCCESS, FAILURE = range(2)

class Link(object):

    def __init__(self, listener):
        self.listener = listener

    def _fire(self, source, tag, result):
        if tag is SUCCESS:
            self._fire_value(source, result)
        elif tag is FAILURE:
            self._fire_exception(source, result)
        else:
            raise RuntimeError('invalid arguments to _fire: %r %s %r %r' % (self, source, tag, result))

    __call__ = _fire

class LinkToEvent(Link):

    def _fire_value(self, source, value):
        self.listener.send(value)

    def _fire_exception(self, source, throw_args):
        self.listener.send_exception(*throw_args)

class LinkToGreenlet(Link):

    def _fire_value(self, source, value):
        self.listener.throw(LinkedCompleted(source))

    def _fire_exception(self, source, throw_args):
        self.listener.throw(getLinkedFailed(source, *throw_args))

class LinkToCallable(Link):

    def _fire_value(self, source, value):
        self.listener(value)

    def _fire_exception(self, source, throw_args):
        self.listener(*throw_args)

def waitall(lst, trap_errors=False):
    queue = coros.queue()
    results = [None] * len(lst)
    for (index, linkable) in enumerate(lst):
        linkable.link(decorate_send(queue, index))
    count = 0
    while count < len(lst):
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

    def __init__(self, event, tag):
        self._event = event
        self._tag = tag

    def __repr__(self):
        params = (type(self).__name__, self._tag, self._event)
        return '<%s tag=%r event=%r>' % params

    def __getattr__(self, name):
        assert name != '_event'
        return getattr(self._event, name)

    def send(self, value):
        self._event.send((self._tag, value))


_NOT_USED = object()

def spawn_greenlet(function, *args):
    """Create a new greenlet that will run `function(*args)'.
    The current greenlet won't be unscheduled. Keyword arguments aren't
    supported (limitation of greenlet), use spawn() to work around that.
    """
    g = api.Greenlet(function)
    g.parent = api.get_hub().greenlet
    api.get_hub().schedule_call_global(0, g.switch, *args)
    return g

class Source(object):
    """Maintain a set of links to the listeners. Delegate the sent value or
    the exception to all of them.

    To set up a link, use link_value, link_exception or link method. The
    latter establishes both "value" and "exception" link. It is possible to
    link to events, queues, greenlets and callables.

    >>> source = Source()
    >>> event = coros.event()
    >>> source.link(event)

    Once source's send or send_exception method is called, all the listeners
    with the right type of link will be notified ("right type" means that
    exceptions won't be delivered to "value" links and values won't be
    delivered to "exception" links). Once link has been fired it is removed.

    Notifying listeners is performed in the MAINLOOP greenlet. As such it
    must not block or call any functions that block. Under the hood notifying
    a link means executing a callback, see Link class for details. Notification
    must not attempt to switch to the hub, i.e. call any of blocking functions.

    >>> source.send('hello')
    >>> event.wait()
    'hello'

    Any error happened while sending will be logged as a regular unhandled
    exception. This won't prevent other links from being fired.

    There 3 kinds of listeners supported:

     1. If `listener' is a greenlet (regardless if it's a raw greenlet or an
        extension like Proc), a subclass of LinkedExited exception is raised
        in it.

     2. If `listener' is something with send/send_exception methods (event,
        queue, Source but not Proc) the relevant method is called.

     3. If `listener' is a callable, it is called with 3 arguments (see Link class
        for details).
    """

    def __init__(self, name=None):
        self.name = name
        self._value_links = {}
        self._exception_links = {}
        self._result = _NOT_USED
        self._exc = None

    def _repr_helper(self):
        result = []
        result.append(repr(self.name))
        if self._result is not _NOT_USED:
            if self._exc is None:
                result.append('result=%r' % self._result)
            else:
                result.append('raised=%s' % getattr(self._exc[0], '__name__', self._exc[0]))
        if self._value_links or self._exception_links:
            result.append('{%s:%s}' % (len(self._value_links),
                                       len(self._exception_links)))
        return result

    def __repr__(self):
        klass = type(self).__name__
        return '<%s %s>' % (klass, ' '.join(self._repr_helper()))

    def ready(self):
        return self._result is not _NOT_USED

    def link_value(self, listener=None, link=None):
        if self.ready() and self._exc is not None:
            return
        if listener is None:
            listener = api.getcurrent()
        if link is None:
            link = self.getLink(listener)
        self._value_links[listener] = link
        if self._result is not _NOT_USED:
            self.send(self._result)

    def link_exception(self, listener=None, link=None):
        if self._result is not _NOT_USED and self._exc is None:
            return
        if listener is None:
            listener = api.getcurrent()
        if link is None:
            link = self.getLink(listener)
        self._exception_links[listener] = link
        if self._result is not _NOT_USED:
            self.send_exception(*self._exc)

    def link(self, listener=None, link=None):
        if listener is None:
            listener = api.getcurrent()
        if link is None:
            link = self.getLink(listener)
        self._value_links[listener] = link
        self._exception_links[listener] = link
        if self._result is not _NOT_USED:
            if self._exc is None:
                self.send(self._result)
            else:
                self.send_exception(*self._exc)

    def unlink(self, listener=None):
        if listener is None:
            listener = api.getcurrent()
        self._value_links.pop(listener, None)
        self._exception_links.pop(listener, None)

    @staticmethod
    def getLink(listener):
        if hasattr(listener, 'throw'):
            return LinkToGreenlet(listener)
        if hasattr(listener, 'send'):
            return LinkToEvent(listener)
        elif callable(listener):
            return LinkToCallable(listener)
        else:
            raise TypeError("Don't know how to link to %r" % (listener, ))

    def send(self, value):
        self._result = value
        self._exc = None
        api.get_hub().schedule_call_global(0, self._do_send, self._value_links.items(),
                                           SUCCESS, value, self._value_links)

    def send_exception(self, *throw_args):
        self._result = None
        self._exc = throw_args
        api.get_hub().schedule_call_global(0, self._do_send, self._exception_links.items(),
                                           FAILURE, throw_args, self._exception_links)

    def _do_send(self, links, tag, value, consult):
        while links:
            listener, link = links.pop()
            try:
                if listener in consult:
                    try:
                        link(self.name, tag, value)
                    finally:
                        consult.pop(listener, None)
            except:
                api.get_hub().schedule_call_global(0, self._do_send, links, tag, value, consult)
                raise

    def wait(self, timeout=None, *throw_args):
        """Wait until send() or send_exception() is called or `timeout' has
        expired. Return the argument of send or raise the argument of
        send_exception. If timeout has expired, None is returned.

        The arguments, when provided, specify how many seconds to wait and what
        to do when timeout has expired. They are treated the same way as
        api.timeout treats them.
        """
        if self._result is not _NOT_USED:
            if self._exc is None:
                return self._result
            else:
                api.getcurrent().throw(*self._exc)
        if timeout==0:
            return
        if timeout is not None:
            timer = api.timeout(timeout, *throw_args)
            timer.__enter__()
            EXC = True
        try:
            try:
                event = coros.event()
                self.link(event)
                try:
                    return event.wait()
                finally:
                    self.unlink(event)
            except:
                EXC = False
                if timeout is None or not timer.__exit__(*sys.exc_info()):
                    raise
        finally:
            if timeout is not None and EXC:
                timer.__exit__(None, None, None)


class Proc(Source):
    """A linkable coroutine based on Source.
    Upon completion, delivers coroutine's result to the listeners.
    """

    def __init__(self, name=None):
        self.greenlet = None
        Source.__init__(self, name)

    def _repr_helper(self):
        if self.greenlet is not None and self.greenlet.dead:
            dead = '(dead)'
        else:
            dead = ''
        return ['%r%s' % (self.greenlet, dead)] + Source._repr_helper(self)

    def __repr__(self):
        klass = type(self).__name__
        return '<%s %s>' % (klass, ' '.join(self._repr_helper()))

    def __nonzero__(self):
        if self.ready():
            # with current _run this does not makes any difference
            # still, let keep it there
            return False
        # otherwise bool(proc) is the same as bool(greenlet)
        if self.greenlet is not None:
            return bool(self.greenlet)

    @property
    def dead(self):
        return self.ready() or self.greenlet.dead

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
        The created greenlet is scheduled to run upon the next hub iteration.
        """
        assert self.greenlet is None, "'run' can only be called once per instance"
        if self.name is None:
            self.name = str(function)
        self.greenlet = spawn_greenlet(self._run, function, args, kwargs)

    def _run(self, function, args, kwargs):
        """Internal top level function.
        Execute *function* and send its result to the listeners.
        """
        try:
            result = function(*args, **kwargs)
        except:
            self.send_exception(*sys.exc_info())
            raise # let mainloop log the exception
        else:
            self.send(result)

    def throw(self, *throw_args):
        """Used internally to raise the exception.

        Behaves exactly like greenlet's 'throw' with the exception that ProcExit
        is raised by default. Do not use this function as it leaves the current
        greenlet unscheduled forever. Use kill() method instead.
        """
        if not self.dead:
            if not throw_args:
                throw_args = (ProcExit, )
            self.greenlet.throw(*throw_args)

    def kill(self, *throw_args):
        """Raise an exception in the greenlet. Unschedule the current greenlet
        so that this Proc can handle the exception (or die).

        The exception can be specified with throw_args. By default, ProcExit is
        raised.
        """
        if not self.dead:
            if not throw_args:
                throw_args = (ProcExit, )
            api.get_hub().schedule_call_global(0, self.greenlet.throw, *throw_args)
            if api.getcurrent() is not api.get_hub().greenlet:
                api.sleep(0)

spawn = Proc.spawn

def spawn_link(function, *args, **kwargs):
    p = spawn(function, *args, **kwargs)
    p.link()
    return p

def spawn_link_value(function, *args, **kwargs):
    p = spawn(function, *args, **kwargs)
    p.link_value()
    return p

def spawn_link_exception(function, *args, **kwargs):
    p = spawn(function, *args, **kwargs)
    p.link_exception()
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


if __name__=='__main__':
    import doctest
    doctest.testmod()
