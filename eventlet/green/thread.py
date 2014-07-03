"""Implements the standard thread module, using greenthreads."""

from eventlet.support.six.moves import _thread as __thread
from eventlet.support import greenlets as greenlet
from eventlet import greenthread
from eventlet.semaphore import Semaphore as LockType


__patched__ = ['get_ident', 'start_new_thread', 'start_new', 'allocate_lock',
               'allocate', 'exit', 'interrupt_main', 'stack_size', '_local',
               'LockType', '_count']

error = __thread.error
__threadcount = 0


def _count():
    return __threadcount


main_ident = __thread.get_ident()
main_green = id(greenlet.getcurrent())


def get_ident(gr=None):
    if gr is None:
        idt = id(greenlet.getcurrent())
    else:
        idt = id(gr)
    if idt == main_green:
        return main_ident
    return idt


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

try:
    _set_sentinel = __thread._set_sentinel
except AttributeError:
    pass
try:
    TIMEOUT_MAX = __thread.TIMEOUT_MAX
except AttributeError:
    pass


if hasattr(__thread, 'stack_size'):
    __original_stack_size__ = __thread.stack_size
    def stack_size(size=None):
        if size is None:
            return __original_stack_size__()
        if size > __original_stack_size__():
            return __original_stack_size__(size)
        else:
            pass
            # not going to decrease stack_size, because otherwise other greenlets in this thread will suffer

from eventlet.corolocal import local as _local
