"""implements standard module 'thread' with greenlets"""
__thread = __import__('thread')
from eventlet.support import greenlets as greenlet
from eventlet.api import spawn
from eventlet.coros import Semaphore as LockType

error = __thread.error

def get_ident(gr=None):
    if gr is None:
        return id(greenlet.getcurrent())
    else:
        return id(gr)

def start_new_thread(function, args=(), kwargs={}):
    g = spawn(function, *args, **kwargs)
    return get_ident(g)
    
start_new = start_new_thread

def allocate_lock():
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
    def stack_size(size=None):
        if size is None:
            return __thread.stack_size()
        if size > __thread.stack_size():
            return __thread.stack_size(size)
        else:
            pass
            # not going to decrease stack_size, because otherwise other greenlets in this thread will suffer

from eventlet.corolocal import local as _local