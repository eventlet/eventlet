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
            import support.stacklesspypys
            support.stacklesspypys.emulate()
            greenlet = sys.modules['greenlet']
        except ImportError:
            try:
                import support.stacklesss
                support.stacklesss.emulate()
                greenlet = sys.modules['greenlet']                
            except ImportError, e:
                raise ImportError("Unable to find an implementation of greenlet.")


from eventlet import greenlib, tls

__all__ = [
    'call_after', 'exc_after', 'getcurrent', 'get_default_hub', 'get_hub',
    'GreenletExit', 'kill', 'sleep', 'spawn', 'spew', 'switch',
    'ssl_listener', 'tcp_listener', 'tcp_server', 'trampoline',
    'unspew', 'use_hub', 'with_timeout',
]


class TimeoutError(Exception):
    """Exception raised if an asynchronous operation times out"""
    pass

_threadlocal = tls.local()

def tcp_listener(address):
    """
    Listen on the given (ip, port) *address* with a TCP socket.
    Returns a socket object on which one should call ``accept()`` to
    accept a connection on the newly bound socket.

    Generally, the returned socket will be passed to ``tcp_server()``,
    which accepts connections forever and spawns greenlets for
    each incoming connection.
    """
    from eventlet import greenio, util
    socket = greenio.GreenSocket(util.tcp_socket())
    util.socket_bind_and_listen(socket, address)
    return socket

def ssl_listener(address, certificate, private_key):
    """Listen on the given (ip, port) *address* with a TCP socket that
    can do SSL.

    *certificate* and *private_key* should be the filenames of the appropriate
    certificate and private key files to use with the SSL socket.

    Returns a socket object on which one should call ``accept()`` to
    accept a connection on the newly bound socket.

    Generally, the returned socket will be passed to ``tcp_server()``,
    which accepts connections forever and spawns greenlets for
    each incoming connection.
    """
    from eventlet import util
    socket = util.wrap_ssl(util.tcp_socket(), certificate, private_key)
    util.socket_bind_and_listen(socket, address)
    socket.is_secure = True
    return socket

def connect_tcp(address, localaddr=None):
    """
    Create a TCP connection to address (host, port) and return the socket.
    Optionally, bind to localaddr (host, port) first.
    """
    from eventlet import greenio, util
    desc = greenio.GreenSocket(util.tcp_socket())
    if localaddr is not None:
        desc.bind(localaddr)
    desc.connect(address)
    return desc

def tcp_server(listensocket, server, *args, **kw):
    """
    Given a socket, accept connections forever, spawning greenlets
    and executing *server* for each new incoming connection.
    When *listensocket* is closed, the ``tcp_server()`` greenlet will end.

    listensocket
        The socket from which to accept connections.
    server
        The callable to call when a new connection is made.
    \*args
        The positional arguments to pass to *server*.
    \*\*kw
        The keyword arguments to pass to *server*.
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

def trampoline(fd, read=False, write=False, timeout=None):
    """Suspend the current coroutine until the given socket object or file
    descriptor is ready to *read*, ready to *write*, or the specified
    *timeout* elapses, depending on arguments specified.

    To wait for *fd* to be ready to read, pass *read* ``=True``; ready to
    write, pass *write* ``=True``. To specify a timeout, pass the *timeout*
    argument in seconds.

    If the specified *timeout* elapses before the socket is ready to read or
    write, ``TimeoutError`` will be raised instead of ``trampoline()``
    returning normally.
    """
    t = None
    hub = get_hub()
    self = greenlet.getcurrent()
    fileno = getattr(fd, 'fileno', lambda: fd)()
    def _do_close(fn):
        hub.remove_descriptor(fn)
        greenlib.switch(self, exc=socket.error(32, 'Broken pipe'))
    def _do_timeout():
        hub.remove_descriptor(fileno)
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


def spawn(function, *args, **kwds):
    """Create a new coroutine, or cooperative thread of control, within which
    to execute *function*.

    The *function* will be called with the given *args* and keyword arguments
    *kwds* and will remain in control unless it cooperatively yields by
    calling a socket method or ``sleep()``.

    ``spawn()`` returns control to the caller immediately, and *function* will
    be called in a future main loop iteration.

    An uncaught exception in *function* or any child will terminate the new
    coroutine with a log message.
    """
    # killable
    t = None
    g = greenlib.tracked_greenlet()
    t = get_hub().schedule_call(0, _spawn, g)
    greenlib.switch(g, (_spawn_startup, function, args, kwds, t.cancel))
    return g


kill = greenlib.kill


def call_after(seconds, function, *args, **kwds):
    """Schedule *function* to be called after *seconds* have elapsed.
    
    *seconds* may be specified as an integer, or a float if fractional seconds
    are desired. The *function* will be called with the given *args* and
    keyword arguments *kwds*, and will be executed within the main loop's
    coroutine.

    Its return value is discarded. Any uncaught exception will be logged.
    """
    # cancellable
    def startup():
        g = greenlib.tracked_greenlet()
        greenlib.switch(g, (_spawn_startup, function, args, kwds))
        greenlib.switch(g)
    return get_hub().schedule_call(seconds, startup)


def with_timeout(seconds, func, *args, **kwds):
    """Wrap a call to some (yielding) function with a timeout; if the called
    function fails to return before the timeout, cancel it and return a flag
    value.
    
    seconds
      (int or float) seconds before timeout occurs
    func
      the callable to execute with a timeout; must be one of the functions
      that implicitly or explicitly yields
    \*args, \*\*kwds
      (positional, keyword) arguments to pass to *func*
    timeout_value=
      value to return if timeout occurs (default raise ``TimeoutError``)
      
    **Returns**:

    Value returned by *func* if *func* returns before *seconds*, else
    *timeout_value* if provided, else raise ``TimeoutError``

    **Raises**:

    Any exception raised by *func*, and ``TimeoutError`` if *func* times out
    and no ``timeout_value`` has been provided.
    
    **Example**::
    
      data = with_timeout(30, httpc.get, 'http://www.google.com/', timeout_value="")

    Here *data* is either the result of the ``get()`` call, or the empty string if
    it took too long to return. Any exception raised by the ``get()`` call is
    passed through to the caller.
    """
    # Recognize a specific keyword argument, while also allowing pass-through
    # of any other keyword arguments accepted by func. Use pop() so we don't
    # pass timeout_value through to func().
    has_timeout_value = "timeout_value" in kwds
    timeout_value = kwds.pop("timeout_value", None)
    timeout = exc_after(seconds, TimeoutError())
    try:
        try:
            return func(*args, **kwds)
        except TimeoutError:
            if has_timeout_value:
                return timeout_value
            raise
    finally:
        timeout.cancel()

def exc_after(seconds, exception_object):
    """Schedule *exception_object* to be raised into the current coroutine
    after *seconds* have elapsed.

    This only works if the current coroutine is yielding, and is generally
    used to set timeouts after which a network operation or series of
    operations will be canceled.

    Returns a timer object with a ``cancel()`` method which should be used to
    prevent the exception if the operation completes successfully.

    See also ``with_timeout()`` that encapsulates the idiom below.

    Example::

        def read_with_timeout():
            timer = api.exc_after(30, RuntimeError()) 
            try: 
                httpc.get('http://www.google.com/') 
            except RuntimeError: 
                print "Timed out!"
            else: 
                timer.cancel()
    """
    hub = get_hub()
    return call_after(seconds, hub.exc_greenlet, getcurrent(), exception_object)


def get_default_hub():
    """Select the default hub implementation based on what multiplexing
    libraries are installed. Tries libevent first, then poll, then select.
    """
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
        import eventlet.hubs.selects
        return eventlet.hubs.selects


def use_hub(mod=None):
    """Use the module *mod*, containing a class called Hub, as the
    event hub. Usually not required; the default hub is usually fine.
    """
    if mod is None:
        mod = get_default_hub()
    if hasattr(_threadlocal, 'hub'):
        del _threadlocal.hub
    if hasattr(mod, 'Hub'):
        _threadlocal.Hub = mod.Hub
    else:
        _threadlocal.Hub = mod

def get_hub():
    """Get the current event hub singleton object.
    """
    try:
        hub = _threadlocal.hub
    except AttributeError:
        try:
            _threadlocal.Hub
        except AttributeError:
            use_hub()
        hub = _threadlocal.hub = _threadlocal.Hub()
    return hub


def sleep(seconds=0):
    """Yield control to another eligible coroutine until at least *seconds* have 
    elapsed.

    *seconds* may be specified as an integer, or a float if fractional seconds
    are desired. Calling sleep with *seconds* of 0 is the canonical way of
    expressing a cooperative yield. For example, if one is looping over a
    large list performing an expensive calculation without calling any socket
    methods, it's a good idea to call ``sleep(0)`` occasionally; otherwise
    nothing else will run.
    """
    hub = get_hub()
    hub.schedule_call(seconds, greenlib.switch, greenlet.getcurrent())
    hub.switch()


switch = greenlib.switch
local_dict = greenlib.greenlet_dict
getcurrent = greenlet.getcurrent
GreenletExit = greenlet.GreenletExit


class Spew(object):
    """
    """
    def __init__(self, trace_names=None, show_values=True):
        self.trace_names = trace_names
        self.show_values = show_values

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
                if not self.show_values:
                    return self
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


def spew(trace_names=None, show_values=False):
    """Install a trace hook which writes incredibly detailed logs
    about what code is being executed to stdout.
    """
    sys.settrace(Spew(trace_names, show_values))


def unspew():
    """Remove the trace hook installed by spew.
    """
    sys.settrace(None)

                                                
def named(name):
    """Return an object given its name.

    The name uses a module-like syntax, eg::

      os.path.join

    or::

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

