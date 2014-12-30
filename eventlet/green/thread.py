"""Implements the standard thread module, using greenthreads."""
from eventlet.support.six.moves import _thread as __thread
from eventlet.support import greenlets as greenlet, six
from eventlet import greenthread
from eventlet.semaphore import Semaphore as LockType


__patched__ = ['get_ident', 'start_new_thread', 'start_new', 'allocate_lock',
               'allocate', 'exit', 'interrupt_main', 'stack_size', '_local',
               'LockType', '_count']

error = __thread.error
__threadcount = 0


if six.PY3:
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


def start_new_thread(function, args=(), kwargs=None):
    kwargs = kwargs or {}
    g = greenthread.spawn_n(__thread_body, function, args, kwargs)
    return get_ident(g)


start_new = start_new_thread


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
