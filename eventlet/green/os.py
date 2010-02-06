os_orig = __import__("os")
import errno
import socket

from eventlet import greenio
from eventlet import greenthread
from eventlet import hubs

for var in dir(os_orig):
    exec "%s = os_orig.%s" % (var, var)

def fdopen(*args, **kw):
    """fdopen(fd [, mode='r' [, bufsize]]) -> file_object
    
    Return an open file object connected to a file descriptor."""
    return greenio.GreenPipe(os_orig.fdopen(*args, **kw))

def read(fd, n):
    """read(fd, buffersize) -> string
    
    Read a file descriptor."""
    while True:
        try:
            return os_orig.read(fd, n)
        except (OSError, IOError), e:
            if e[0] != errno.EAGAIN:
                raise
        except socket.error, e:
            if e[0] == errno.EPIPE:
                return ''
            raise
        hubs.trampoline(fd, read=True)

def write(fd, st):
    """write(fd, string) -> byteswritten
    
    Write a string to a file descriptor.
    """
    while True:
        try:
            return os_orig.write(fd, st)
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

def waitpid(pid, options):
    """waitpid(...)
    waitpid(pid, options) -> (pid, status)
    
    Wait for completion of a given child process."""
    if options & os.WNOHANG != 0:
        return os_orig.waitpid(pid, options)
    else:
        new_options = options | os.WNOHANG
        while True:
            rpid, status = os_orig.waitpid(pid, new_options)
            if status >= 0:
                return rpid, status
            greenthread.sleep(0.01)

# TODO: open