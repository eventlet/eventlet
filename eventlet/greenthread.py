import sys

from eventlet import event
from eventlet import hubs
from eventlet import timer
from eventlet.support import greenlets as greenlet

__all__ = ['getcurrent', 'sleep', 'spawn', 'spawn_n', 'call_after_global', 'call_after_local', 'GreenThread'] 

getcurrent = greenlet.getcurrent

def kill(g, *throw_args):
    """Terminates the target greenthread by raising an exception into it.
    By default, this exception is GreenletExit, but a specific exception
    may be specified in the *throw_args*.
    """
    hub = hubs.get_hub()
    hub.schedule_call_global(0, g.throw, *throw_args)
    if getcurrent() is not hub.greenlet:
        sleep(0)


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
    hub = hubs.get_hub()
    assert hub.greenlet is not greenlet.getcurrent(), 'do not call blocking functions from the mainloop'
    timer = hub.schedule_call_global(seconds, greenlet.getcurrent().switch)
    try:
        hub.switch()
    finally:
        timer.cancel()
        

def spawn(func, *args, **kwargs):
    """Create a green thread to run func(*args, **kwargs).  Returns a 
    GreenThread object which you can use to get the results of the call.
    """
    hub = hubs.get_hub()
    g = GreenThread(hub.greenlet)
    hub.schedule_call_global(0, g.switch, func, args, kwargs)
    return g
    
    
def _main_wrapper(func, args, kwargs):
    # function that gets around the fact that greenlet.switch
    # doesn't accept keyword arguments
    return func(*args, **kwargs)


def spawn_n(func, *args, **kwargs):
    """Same as spawn, but returns a greenlet object from which it is not 
    possible to retrieve the results.  This is slightly faster than spawn; it is
    fastest if there are no keyword arguments."""
    return _spawn_n(0, func, args, kwargs)[1]


def call_after_global(seconds, func, *args, **kwargs):
    """Schedule *function* to be called after *seconds* have elapsed.
    The function will be scheduled even if the current greenlet has exited.

    *seconds* may be specified as an integer, or a float if fractional seconds
    are desired. The *function* will be called with the given *args* and
    keyword arguments *kwargs*, and will be executed within the main loop's
    coroutine.

    Its return value is discarded. Any uncaught exception will be logged."""
    return _spawn_n(seconds, func, args, kwargs)[0]
    

def call_after_local(seconds, function, *args, **kwargs):
    """Schedule *function* to be called after *seconds* have elapsed.
    The function will NOT be called if the current greenlet has exited.

    *seconds* may be specified as an integer, or a float if fractional seconds
    are desired. The *function* will be called with the given *args* and
    keyword arguments *kwargs*, and will be executed within the main loop's
    coroutine.

    Its return value is discarded. Any uncaught exception will be logged.
    """
    hub = hubs.get_hub()
    g = greenlet.greenlet(_main_wrapper, parent=hub.greenlet)
    t = hub.schedule_call_local(seconds, g.switch, function, args, kwargs)
    return t


call_after = call_after_local

class TimeoutError(Exception):
    """Exception raised if an asynchronous operation times out"""
    pass

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
    if seconds is None:  # dummy argument, do nothing
        return timer.Timer(seconds, lambda: None)
    hub = hubs.get_hub()
    return hub.schedule_call_local(seconds, getcurrent().throw, *throw_args)


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


def _spawn_n(seconds, func, args, kwargs):
    hub = hubs.get_hub()
    if kwargs:
        g = greenlet.greenlet(_main_wrapper, parent=hub.greenlet)
        t = hub.schedule_call_global(seconds, g.switch, func, args, kwargs)
    else:
        g = greenlet.greenlet(func, parent=hub.greenlet)
        t = hub.schedule_call_global(seconds, g.switch, *args)
    return t, g


class GreenThread(greenlet.greenlet):
    def __init__(self, parent):
        greenlet.greenlet.__init__(self, self.main, parent)
        self._exit_event = event.Event()

    def wait(self):
        return self._exit_event.wait()
        
    def link(self, func, *curried_args, **curried_kwargs):
        """ Set up a function to be called with the results of the GreenThread.
        
        The function must have the following signature:
          def f(result=None, exc=None, [curried args/kwargs]):
        """
        self._exit_funcs = getattr(self, '_exit_funcs', [])
        self._exit_funcs.append((func, curried_args, curried_kwargs))
        
    def main(self, function, args, kwargs):
        try:
            result = function(*args, **kwargs)
        except:
            self._exit_event.send_exception(*sys.exc_info())
            # ca and ckw are the curried function arguments
            for f, ca, ckw in getattr(self, '_exit_funcs', []):
                f(exc=sys.exc_info(), *ca, **ckw)
            raise
        else:
            self._exit_event.send(result)
            for f, ca, ckw in getattr(self, '_exit_funcs', []):
                f(result, *ca, **ckw)
                
    def kill(self):
        return kill(self)