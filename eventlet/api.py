import errno
import sys
import socket
import string
import linecache
import inspect
import threading

from eventlet.support import greenlets as greenlet

import warnings

__all__ = [
    'call_after', 'exc_after', 'getcurrent', 'get_default_hub', 'get_hub',
    'GreenletExit', 'kill', 'sleep', 'spawn', 'spew', 'switch',
    'ssl_listener', 'tcp_listener', 'trampoline',
    'unspew', 'use_hub', 'with_timeout', 'timeout']


def switch(coro, result=None, exc=None):
    if exc is not None:
        return coro.throw(exc)
    return coro.switch(result)

Greenlet = greenlet.greenlet

class TimeoutError(Exception):
    """Exception raised if an asynchronous operation times out"""
    pass

_threadlocal = threading.local()

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
    hub = get_hub()
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


def _spawn_startup(cb, args, kw, cancel=None):
    try:
        greenlet.getcurrent().parent.switch()
        cancel = None
    finally:
        if cancel is not None:
            cancel()
    return cb(*args, **kw)

def _spawn(g):
    g.parent = greenlet.getcurrent()
    g.switch()


def spawn(function, *args, **kwds):
    """Create a new coroutine, or cooperative thread of control, within which
    to execute *function*.

    The *function* will be called with the given *args* and keyword arguments
    *kwds* and will remain in control unless it cooperatively yields by
    calling a socket method or ``sleep()``.

    :func:`spawn` returns control to the caller immediately, and *function*
    will be called in a future main loop iteration.

    An uncaught exception in *function* or any child will terminate the new
    coroutine with a log message.
    """
    # killable
    t = None
    g = Greenlet(_spawn_startup)
    t = get_hub().schedule_call_global(0, _spawn, g)
    g.switch(function, args, kwds, t.cancel)
    return g

def kill(g, *throw_args):
    get_hub().schedule_call_global(0, g.throw, *throw_args)
    if getcurrent() is not get_hub().greenlet:
        sleep(0)

def call_after_global(seconds, function, *args, **kwds):
    """Schedule *function* to be called after *seconds* have elapsed.
    The function will be scheduled even if the current greenlet has exited.

    *seconds* may be specified as an integer, or a float if fractional seconds
    are desired. The *function* will be called with the given *args* and
    keyword arguments *kwds*, and will be executed within the main loop's
    coroutine.

    Its return value is discarded. Any uncaught exception will be logged.
    """
    # cancellable
    def startup():
        g = Greenlet(_spawn_startup)
        g.switch(function, args, kwds)
        g.switch()
    t = get_hub().schedule_call_global(seconds, startup)
    return t

def call_after_local(seconds, function, *args, **kwds):
    """Schedule *function* to be called after *seconds* have elapsed.
    The function will NOT be called if the current greenlet has exited.

    *seconds* may be specified as an integer, or a float if fractional seconds
    are desired. The *function* will be called with the given *args* and
    keyword arguments *kwds*, and will be executed within the main loop's
    coroutine.

    Its return value is discarded. Any uncaught exception will be logged.
    """
    # cancellable
    def startup():
        g = Greenlet(_spawn_startup)
        g.switch(function, args, kwds)
        g.switch()
    t = get_hub().schedule_call_local(seconds, startup)
    return t

# for compatibility with original eventlet API
call_after = call_after_local

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

def with_timeout(seconds, func, *args, **kwds):
    """Wrap a call to some (yielding) function with a timeout; if the called
    function fails to return before the timeout, cancel it and return a flag
    value.

    :param seconds: seconds before timeout occurs
    :type seconds: int or float
    :param func: the callable to execute with a timeout; must be one of the
      functions that implicitly or explicitly yields
    :param \*args: positional arguments to pass to *func*
    :param \*\*kwds: keyword arguments to pass to *func*
    :param timeout_value: value to return if timeout occurs (default raise
      :class:`~eventlet.api.TimeoutError`)

    :rtype: Value returned by *func* if *func* returns before *seconds*, else
      *timeout_value* if provided, else raise ``TimeoutError``

    :exception TimeoutError: if *func* times out and no ``timeout_value`` has
      been provided.
    :exception *any*: Any exception raised by *func*

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
    error = TimeoutError()
    timeout = exc_after(seconds, error)
    try:
        try:
            return func(*args, **kwds)
        except TimeoutError, ex:
            if ex is error and has_timeout_value:
                return timeout_value
            raise
    finally:
        timeout.cancel()


def exc_after(seconds, *throw_args):
    """Schedule an exception to be raised into the current coroutine
    after *seconds* have elapsed.

    This only works if the current coroutine is yielding, and is generally
    used to set timeouts after which a network operation or series of
    operations will be canceled.

    Returns a :class:`~eventlet.timer.Timer` object with a
    :meth:`~eventlet.timer.Timer.cancel` method which should be used to
    prevent the exception if the operation completes successfully.

    See also :func:`~eventlet.api.with_timeout` that encapsulates the idiom below.

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
    return call_after(seconds, getcurrent().throw, *throw_args)


def get_default_hub():
    """Select the default hub implementation based on what multiplexing
    libraries are installed. Tries twistedr if a twisted reactor is imported,
    then poll, then select.
    """    
    
    # libevent hub disabled for now because it is not thread-safe
    #try:
    #    import eventlet.hubs.libevent
    #    return eventlet.hubs.libevent
    #except:
    #    pass

    if 'twisted.internet.reactor' in sys.modules:
        from eventlet.hubs import twistedr
        return twistedr

    try:
        import eventlet.hubs.epolls
        return eventlet.hubs.epolls
    except ImportError:
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
    if isinstance(mod, str):
        mod = __import__('eventlet.hubs.' + mod, globals(), locals(), ['Hub'])
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
    are desired. Calling :func:`~eventlet.api.sleep` with *seconds* of 0 is the
    canonical way of expressing a cooperative yield. For example, if one is
    looping over a large list performing an expensive calculation without
    calling any socket methods, it's a good idea to call ``sleep(0)``
    occasionally; otherwise nothing else will run.
    """
    hub = get_hub()
    assert hub.greenlet is not greenlet.getcurrent(), 'do not call blocking functions from the mainloop'
    timer = hub.schedule_call_global(seconds, greenlet.getcurrent().switch)
    try:
        hub.switch()
    finally:
        timer.cancel()


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

