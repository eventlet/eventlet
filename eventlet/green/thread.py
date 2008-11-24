"""implements standard module 'thread' with greenlets"""
from __future__ import absolute_import
import thread as thread_module
from eventlet.support import greenlet
from eventlet.api import spawn
from eventlet.coros import semaphore as LockType

error = thread_module.error

def get_ident(gr=None):
    if gr is None:
        return id(greenlet.getcurrent())
    else:
        return id(gr)

def start_new_thread(function, args=(), kwargs={}):
    g = spawn(function, *args, **kwargs)
    return get_ident(g)

def allocate_lock():
    return LockType(1)

def exit():
    raise greenlet.GreenletExit

def stack_size(size=None):
    if size is None:
        return thread_module.stack_size()
    if size > thread_module.stack_size():
        return thread_module.stack_size(size)
    else:
        pass
        # not going to decrease stack_size, because otherwise other greenlets in this thread will suffer

# XXX interrupt_main
