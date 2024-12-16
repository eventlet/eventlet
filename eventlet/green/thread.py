"""Implements the standard thread module, using greenthreads."""
import _thread as __thread
from eventlet.support import greenlets as greenlet
from eventlet import greenthread
from eventlet.timeout import with_timeout
from eventlet.lock import Lock
import sys


__patched__ = ['Lock', 'LockType', '_ThreadHandle', '_count',
               '_get_main_thread_ident', '_local', '_make_thread_handle',
               'allocate', 'allocate_lock', 'exit', 'get_ident',
               'interrupt_main', 'stack_size', 'start_joinable_thread',
               'start_new', 'start_new_thread']

error = __thread.error
LockType = Lock
__threadcount = 0

if hasattr(__thread, "_is_main_interpreter"):
    _is_main_interpreter = __thread._is_main_interpreter


def _set_sentinel():
    # TODO this is a dummy code, reimplementing this may be needed:
    # https://hg.python.org/cpython/file/b5e9bc4352e1/Modules/_threadmodule.c#l1203
    return allocate_lock()


TIMEOUT_MAX = __thread.TIMEOUT_MAX


def _count():
    return __threadcount


def get_ident(gr=None):
    if gr is None:
        return id(greenlet.getcurrent())
    else:
        return id(gr)


def __thread_body(func, args, kwargs):
    global __threadcount
    __threadcount += 1
    try:
        func(*args, **kwargs)
    finally:
        __threadcount -= 1


class _ThreadHandle:
    def __init__(self, greenthread=None):
        self._greenthread = greenthread
        self._done = False

    def _set_done(self):
        self._done = True

    def is_done(self):
        if self._greenthread is not None:
            return self._greenthread.dead
        return self._done

    @property
    def ident(self):
        return get_ident(self._greenthread)

    def join(self, timeout=None):
        if not hasattr(self._greenthread, "wait"):
            return
        if timeout is not None:
            return with_timeout(timeout, self._greenthread.wait)
        return self._greenthread.wait()


def _make_thread_handle(ident):
    greenthread = greenlet.getcurrent()
    assert ident == get_ident(greenthread)
    return _ThreadHandle(greenthread=greenthread)


def __spawn_green(function, args=(), kwargs=None, joinable=False):
    if ((3, 4) <= sys.version_info < (3, 13)
            and getattr(function, '__module__', '') == 'threading'
            and hasattr(function, '__self__')):
        # In Python 3.4-3.12, threading.Thread uses an internal lock
        # automatically released when the python thread state is deleted.
        # With monkey patching, eventlet uses green threads without python
        # thread state, so the lock is not automatically released.
        #
        # Wrap _bootstrap_inner() to release explicitly the thread state lock
        # when the thread completes.
        thread = function.__self__
        bootstrap_inner = thread._bootstrap_inner

        def wrap_bootstrap_inner():
            try:
                bootstrap_inner()
            finally:
                # The lock can be cleared (ex: by a fork())
                if getattr(thread, "_tstate_lock", None) is not None:
                    thread._tstate_lock.release()

        thread._bootstrap_inner = wrap_bootstrap_inner

    kwargs = kwargs or {}
    spawn_func = greenthread.spawn if joinable else greenthread.spawn_n
    return spawn_func(__thread_body, function, args, kwargs)


def start_joinable_thread(function, handle=None, daemon=True):
    g = __spawn_green(function, joinable=True)
    if handle is None:
        handle = _ThreadHandle(greenthread=g)
    else:
        handle._greenthread = g
    return handle


def start_new_thread(function, args=(), kwargs=None):
    g = __spawn_green(function, args=args, kwargs=kwargs)
    return get_ident(g)


start_new = start_new_thread


def _get_main_thread_ident():
    greenthread = greenlet.getcurrent()
    while greenthread.parent is not None:
        greenthread = greenthread.parent
    return get_ident(greenthread)


def allocate_lock(*a):
    return LockType(1)


allocate = allocate_lock


def exit():
    raise greenlet.GreenletExit


exit_thread = __thread.exit_thread


def interrupt_main():
    curr = greenlet.getcurrent()
    if curr.parent and not curr.parent.dead:
        curr.parent.throw(KeyboardInterrupt())
    else:
        raise KeyboardInterrupt()


if hasattr(__thread, 'stack_size'):
    __original_stack_size__ = __thread.stack_size

    def stack_size(size=None):
        if size is None:
            return __original_stack_size__()
        if size > __original_stack_size__():
            return __original_stack_size__(size)
        else:
            pass
            # not going to decrease stack_size, because otherwise other greenlets in
            # this thread will suffer

from eventlet.corolocal import local as _local

if hasattr(__thread, 'daemon_threads_allowed'):
    daemon_threads_allowed = __thread.daemon_threads_allowed

if hasattr(__thread, '_shutdown'):
    _shutdown = __thread._shutdown
