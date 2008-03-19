"""\
@file api.py
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
import socket
import string
import linecache
import inspect
import traceback

try:
    import greenlet
except ImportError:
    try:
        import support.pylib
        support.pylib.emulate()
        greenlet = sys.modules['greenlet']
    except ImportError:
        try:
            import support.stackless
            support.stackless.emulate()
            greenlet = sys.modules['greenlet']
        except ImportError:
            raise ImportError("Unable to find an implementation of greenlet.")

from eventlet import greenlib, tls

__all__ = [
    'use_hub', 'get_hub', 'sleep', 'spawn', 'kill',
    'call_after', 'exc_after', 'trampoline', 'tcp_listener', 'tcp_server',
    'with_timeout',
]


class TimeoutError(Exception):
    pass

_threadlocal = tls.local()

def tcp_listener(address):
    """
    Listen on the given (ip, port) address with a TCP socket.
    Returns a socket object which one should call accept() on to
    accept a connection on the newly bound socket.

    Generally, the returned socket will be passed to tcp_server,
    which accepts connections forever and spawns greenlets for
    each incoming connection.
    """
    from eventlet import greenio, util
    socket = greenio.GreenSocket(util.tcp_socket())
    util.socket_bind_and_listen(socket, address)
    return socket

def ssl_listener(address, certificate, private_key):
    """Listen on the given (ip, port) address with a TCP socket that
    can do SSL.

    Returns a socket object which one should call accept() on to
    accept a connection on the newly bound socket.

    Generally, the returned socket will be passed to tcp_server,
    which accepts connections forever and spawns greenlets for
    each incoming connection.
    """
    from eventlet import util
    socket = util.wrap_ssl(util.tcp_socket(), certificate, private_key)
    util.socket_bind_and_listen(socket, address)
    socket.is_secure = True
    return socket

def connect_tcp(address):
    """
    Create a TCP connection to address (host, port) and return the socket.
    """
    from eventlet import greenio, util
    desc = greenio.GreenSocket(util.tcp_socket())
    desc.connect(address)
    return desc

def tcp_server(listensocket, server, *args, **kw):
    """
    Given a socket, accept connections forever, spawning greenlets
    and executing "server" for each new incoming connection.
    When listensocket is closed, the tcp_server greenlet will end.

    listensocket:
        The socket to accept connections from.

    server:
        The callable to call when a new connection is made.

    *args:
        The arguments to pass to the call to server.

    **kw:
        The keyword arguments to pass to the call to server.
    """
    try:
        try:
            while True:
                spawn(server, listensocket.accept(), *args, **kw)
        except socket.error, e:
            # Broken pipe means it was shutdown
            if e[0] != 32:
                raise
    finally:
        listensocket.close()

def trampoline(fd, read=None, write=None, timeout=None):
    t = None
    hub = get_hub()
    self = greenlet.getcurrent()
    fileno = getattr(fd, 'fileno', lambda: fd)()
    def _do_close(fn):
        hub.remove_descriptor(fn)
        greenlib.switch(self, exc=socket.error(32, 'Broken pipe'))
    def _do_timeout(fn):
        hub.remove_descriptor(fn)
        greenlib.switch(self, exc=TimeoutError())
    def cb(_fileno):
        if t is not None:
            t.cancel()
        hub.remove_descriptor(fileno)
        greenlib.switch(self, fd)
    if timeout is not None:
        t = hub.schedule_call(timeout, _do_timeout)
    hub.add_descriptor(fileno, read and cb, write and cb, _do_close)
    return hub.switch()

def _spawn_startup(cb, args, kw, cancel=None):
    try:
        greenlib.switch(greenlet.getcurrent().parent)
        cancel = None
    finally:
        if cancel is not None:
            cancel()
    return cb(*args, **kw)

def _spawn(g):
    g.parent = greenlet.getcurrent()
    greenlib.switch(g)


def spawn(cb, *args, **kw):
    # killable
    t = None
    g = greenlib.tracked_greenlet()
    t = get_hub().schedule_call(0, _spawn, g)
    greenlib.switch(g, (_spawn_startup, cb, args, kw, t.cancel))
    return g

kill = greenlib.kill

def call_after(seconds, cb, *args, **kw):
    # cancellable
    def startup():
        g = greenlib.tracked_greenlet()
        greenlib.switch(g, (_spawn_startup, cb, args, kw))
        greenlib.switch(g)
    return get_hub().schedule_call(seconds, startup)


def with_timeout(seconds, func, *args, **kwds):
    """Wrap a call to some (yielding) function with a timeout; if the called
    function fails to return before the timeout, cancel it and return a flag
    value.
    
    *seconds*
      (int or float) seconds before timeout occurs
    *func*
      the callable to execute with a timeout; must be one of the functions
      that implicitly or explicitly yields
    *\*args*, *\*\*kwds*
      (positional, keyword) arguments to pass to *func*
    *timeout_value=*
      value to return if timeout occurs (default None)
      
    **Returns**:

    Value returned by *func* if *func* returns before *seconds*, else *timeout_value*

    **Raises**:

    Any exception raised by *func*, except ``TimeoutError``
    
    **Example**::
    
      data = with_timeout(30, httpc.get, 'http://www.google.com/', timeout_value="")
      # Here data is either the result of the get() call, or the empty string if
      # it took too long to return. Any exception raised by the get() call is
      # passed through to the caller.
    """
    # Recognize a specific keyword argument, while also allowing pass-through
    # of any other keyword arguments accepted by func. Use pop() so we don't
    # pass timeout_value through to func().
    timeout_value = kwds.pop("timeout_value", None)
    timeout = api.exc_after(time, TimeoutError()) 
    try:
        try:
            return func(*args, **kwds)
        except TimeoutError:
            return timeout_value
    finally:
        timeout.cancel()

def exc_after(seconds, exc):
    return call_after(seconds, switch, getcurrent(), None, exc)


def get_default_hub():        
    try:
        import eventlet.hubs.libevent
        return eventlet.hubs.libevent
    except ImportError:
        pass

    import select
    if hasattr(select, 'poll'):
        import eventlet.hubs.poll
        return eventlet.hubs.poll
    else:
        import eventlet.hubs.selecthub
        return eventlet.hubs.selecthub


def use_hub(mod=None):
    if mod is None:
        mod = get_default_hub()
    if hasattr(_threadlocal, 'hub'):
        del _threadlocal.hub
    if hasattr(mod, 'Hub'):
        _threadlocal.Hub = mod.Hub
    else:
        _threadlocal.Hub = mod

def get_hub():
    try:
        hub = _threadlocal.hub
    except AttributeError:
        try:
            _threadlocal.Hub
        except AttributeError:
            use_hub()
        hub = _threadlocal.hub = _threadlocal.Hub()
    return hub


def sleep(timeout=0):
    hub = get_hub()
    hub.schedule_call(timeout, greenlib.switch, greenlet.getcurrent())
    hub.switch()


switch = greenlib.switch
getcurrent = greenlet.getcurrent
GreenletExit = greenlet.GreenletExit


class Spew(object):
    def __init__(self, trace_names=None):
        self.trace_names = trace_names

    def __call__(self, frame, event, arg):
        if event == 'line':
            lineno = frame.f_lineno
            if '__file__' in frame.f_globals:
                filename = frame.f_globals['__file__']
                if (filename.endswith('.pyc') or
                    filename.endswith('.pyo')):
                    filename = filename[:-1]
                name = frame.f_globals['__name__']
                line = linecache.getline(filename, lineno)
            else:
                name = '[unknown]'
                try:
                    src = inspect.getsourcelines(frame)
                    line = src[lineno]
                except IOError:
                    line = 'Unknown code named [%s].  VM instruction #%d' % (
                        frame.f_code.co_name, frame.f_lasti)
            if self.trace_names is None or name in self.trace_names:
                print '%s:%s: %s' % (name, lineno, line.rstrip())
                details = '\t'
                tokens = line.translate(
                    string.maketrans(' ,.()', '\0' * 5)).split('\0')
                for tok in tokens:
                    if tok in frame.f_globals:
                        details += '%s=%r ' % (tok, frame.f_globals[tok])
                    if tok in frame.f_locals:
                        details += '%s=%r ' % (tok, frame.f_locals[tok])
                if details.strip():
                    print details
        return self


def spew(trace_names=None):
    sys.settrace(Spew(trace_names))


def unspew():
    sys.settrace(None)

                                                
def named(name):
    """Return an object given its name. The name uses a module-like
syntax, eg:
    os.path.join
    or
    mulib.mu.Resource
    """
    toimport = name
    obj = None
    while toimport:
        try:
            obj = __import__(toimport)
            break
        except ImportError, err:
            # print 'Import error on %s: %s' % (toimport, err)  # debugging spam
            toimport = '.'.join(toimport.split('.')[:-1])
    if obj is None:
        raise ImportError('%s could not be imported' % (name, ))
    for seg in name.split('.')[1:]:
        try:
            obj = getattr(obj, seg)
        except AttributeError:
            dirobj = dir(obj)
            dirobj.sort()
            raise AttributeError('attribute %r missing from %r (%r) %r' % (
                seg, obj, dirobj, name))
    return obj

