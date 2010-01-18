import errno
import sys
import socket
import string
import linecache
import inspect
import warnings

from eventlet.support import greenlets as greenlet
from eventlet.hubs import get_hub as get_hub_, get_default_hub as get_default_hub_, use_hub as use_hub_
from eventlet import greenthread
from eventlet import debug

__all__ = [
    'call_after', 'exc_after', 'getcurrent', 'get_default_hub', 'get_hub',
    'GreenletExit', 'kill', 'sleep', 'spawn', 'spew', 'switch',
    'ssl_listener', 'tcp_listener', 'trampoline',
    'unspew', 'use_hub', 'with_timeout', 'timeout']

def get_hub(*a, **kw):
    warnings.warn("eventlet.api.get_hub has moved to eventlet.hubs.get_hub",
        DeprecationWarning, stacklevel=2)
    return get_hub_(*a, **kw)    
def get_default_hub(*a, **kw):
    warnings.warn("eventlet.api.get_default_hub has moved to"
        " eventlet.hubs.get_default_hub",
        DeprecationWarning, stacklevel=2)
    return get_default_hub_(*a, **kw)
def use_hub(*a, **kw):
    warnings.warn("eventlet.api.use_hub has moved to eventlet.hubs.use_hub",
        DeprecationWarning, stacklevel=2)
    return use_hub_(*a, **kw)
    

def switch(coro, result=None, exc=None):
    if exc is not None:
        return coro.throw(exc)
    return coro.switch(result)

Greenlet = greenlet.greenlet


def tcp_listener(address, backlog=50):
    """
    Listen on the given ``(ip, port)`` *address* with a TCP socket.  Returns a
    socket object on which one should call ``accept()`` to accept a connection
    on the newly bound socket.
    """
    from eventlet import greenio, util
    socket = greenio.GreenSocket(util.tcp_socket())
    util.socket_bind_and_listen(socket, address, backlog=backlog)
    return socket

def ssl_listener(address, certificate, private_key):
    """Listen on the given (ip, port) *address* with a TCP socket that
    can do SSL.  Primarily useful for unit tests, don't use in production.

    *certificate* and *private_key* should be the filenames of the appropriate
    certificate and private key files to use with the SSL socket.

    Returns a socket object on which one should call ``accept()`` to
    accept a connection on the newly bound socket.
    """
    from eventlet import util
    socket = util.wrap_ssl(util.tcp_socket(), certificate, private_key, True)
    util.socket_bind_and_listen(socket, address)
    return socket

def connect_tcp(address, localaddr=None):
    """
    Create a TCP connection to address ``(host, port)`` and return the socket.
    Optionally, bind to localaddr ``(host, port)`` first.
    """
    from eventlet import greenio, util
    desc = greenio.GreenSocket(util.tcp_socket())
    if localaddr is not None:
        desc.bind(localaddr)
    desc.connect(address)
    return desc

TimeoutError = greenthread.TimeoutError

def trampoline(fd, read=None, write=None, timeout=None, timeout_exc=TimeoutError):
    """Suspend the current coroutine until the given socket object or file
    descriptor is ready to *read*, ready to *write*, or the specified
    *timeout* elapses, depending on arguments specified.

    To wait for *fd* to be ready to read, pass *read* ``=True``; ready to
    write, pass *write* ``=True``. To specify a timeout, pass the *timeout*
    argument in seconds.

    If the specified *timeout* elapses before the socket is ready to read or
    write, *timeout_exc* will be raised instead of ``trampoline()``
    returning normally.
    """
    t = None
    hub = get_hub_()
    current = greenlet.getcurrent()
    assert hub.greenlet is not current, 'do not call blocking functions from the mainloop'
    assert not (read and write), 'not allowed to trampoline for reading and writing'
    fileno = getattr(fd, 'fileno', lambda: fd)()
    def cb(d):
        current.switch()
    if timeout is not None:
        t = hub.schedule_call_global(timeout, current.throw, timeout_exc)
    try:
        if read:
            listener = hub.add(hub.READ, fileno, cb)
        if write:
            listener = hub.add(hub.WRITE, fileno, cb)
        try:
            return hub.switch()
        finally:
            hub.remove(listener)
    finally:
        if t is not None:
            t.cancel()


spawn = greenthread.spawn
spawn_n = greenthread.spawn_n


kill = greenthread.kill

call_after = greenthread.call_after
call_after_local = greenthread.call_after_local
call_after_global = greenthread.call_after_global


class _SilentException:
    pass

class FakeTimer(object):
    def cancel(self):
        pass

class timeout(object):
    """Raise an exception in the block after timeout.
    
    Example::

     with timeout(10):
         urllib2.open('http://example.com')

    Assuming code block is yielding (i.e. gives up control to the hub),
    an exception provided in *exc* argument will be raised
    (:class:`~eventlet.api.TimeoutError` if *exc* is omitted)::
    
     try:
         with timeout(10, MySpecialError, error_arg_1):
             urllib2.open('http://example.com')
     except MySpecialError, e:
         print "special error received"


    When *exc* is ``None``, code block is interrupted silently.
    """

    def __init__(self, seconds, *throw_args):
        self.seconds = seconds
        if seconds is None:
            return
        if not throw_args:
            self.throw_args = (TimeoutError(), )
        elif throw_args == (None, ):
            self.throw_args = (_SilentException(), )
        else:
            self.throw_args = throw_args

    def __enter__(self):
        if self.seconds is None:
            self.timer = FakeTimer()
        else:
            self.timer = exc_after(self.seconds, *self.throw_args)
        return self.timer

    def __exit__(self, typ, value, tb):
        self.timer.cancel()
        if typ is _SilentException and value in self.throw_args:
            return True

with_timeout = greenthread.with_timeout

exc_after = greenthread.exc_after  
    
sleep = greenthread.sleep

getcurrent = greenlet.getcurrent
GreenletExit = greenlet.GreenletExit

spew = debug.spew
unspew = debug.unspew


def named(name):
    """Return an object given its name.

    The name uses a module-like syntax, eg::

      os.path.join

    or::

      mulib.mu.Resource
    """
    toimport = name
    obj = None
    import_err_strings = []
    while toimport:
        try:
            obj = __import__(toimport)
            break
        except ImportError, err:
            # print 'Import error on %s: %s' % (toimport, err)  # debugging spam
            import_err_strings.append(err.__str__())
            toimport = '.'.join(toimport.split('.')[:-1])
    if obj is None:
        raise ImportError('%s could not be imported.  Import errors: %r' % (name, import_err_strings))
    for seg in name.split('.')[1:]:
        try:
            obj = getattr(obj, seg)
        except AttributeError:
            dirobj = dir(obj)
            dirobj.sort()
            raise AttributeError('attribute %r missing from %r (%r) %r.  Import errors: %r' % (
                seg, obj, dirobj, name, import_err_strings))
    return obj

