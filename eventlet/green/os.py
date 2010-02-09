os_orig = __import__("os")
import errno
import socket

from eventlet import greenio
from eventlet import greenthread
from eventlet import hubs

__patched__ = ['fdopen', 'read', 'write', 'wait', 'waitpid']

for var in dir(os_orig):
    exec "%s = os_orig.%s" % (var, var)

__original_fdopen__ = os_orig.fdopen
def fdopen(*args, **kw):
    """fdopen(fd [, mode='r' [, bufsize]]) -> file_object
    
    Return an open file object connected to a file descriptor."""
    return greenio.GreenPipe(__original_fdopen__(*args, **kw))

__original_read__ = os_orig.read
def read(fd, n):
    """read(fd, buffersize) -> string
    
    Read a file descriptor."""
    while True:
        try:
            return __original_read__(fd, n)
        except (OSError, IOError), e:
            if e[0] != errno.EAGAIN:
                raise
        except socket.error, e:
            if e[0] == errno.EPIPE:
                return ''
            raise
        hubs.trampoline(fd, read=True)

__original_write__ = os_orig.write
def write(fd, st):
    """write(fd, string) -> byteswritten
    
    Write a string to a file descriptor.
    """
    while True:
        try:
            return __original_write__(fd, st)
        except (OSError, IOError), e:
            if e[0] != errno.EAGAIN:
                raise
        except socket.error, e:
            if e[0] != errno.EPIPE:
                raise
        hubs.trampoline(fd, write=True)
    
def wait():
    """wait() -> (pid, status)
    
    Wait for completion of a child process."""
    return waitpid(0,0)

__original_waitpid__ = os_orig.waitpid
def waitpid(pid, options):
    """waitpid(...)
    waitpid(pid, options) -> (pid, status)
    
    Wait for completion of a given child process."""
    if options & os.WNOHANG != 0:
        return __original_waitpid__(pid, options)
    else:
        new_options = options | os.WNOHANG
        while True:
            rpid, status = __original_waitpid__(pid, new_options)
            if status >= 0:
                return rpid, status
            greenthread.sleep(0.01)

# TODO: open