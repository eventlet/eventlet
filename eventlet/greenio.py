from eventlet.hubs import trampoline
from eventlet.hubs import get_hub

BUFFER_SIZE = 4096

import errno
import os
import socket
from socket import socket as _original_socket
import sys
import time
import warnings


from errno import EWOULDBLOCK, EAGAIN


__all__ = ['GreenSocket', 'GreenPipe', 'shutdown_safe']

CONNECT_ERR = set((errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK))
CONNECT_SUCCESS = set((0, errno.EISCONN))

def socket_connect(descriptor, address):
    """
    Attempts to connect to the address, returns the descriptor if it succeeds,
    returns None if it needs to trampoline, and raises any exceptions.
    """
    err = descriptor.connect_ex(address)
    if err in CONNECT_ERR:
        return None
    if err not in CONNECT_SUCCESS:
        raise socket.error(err, errno.errorcode[err])
    return descriptor


def socket_accept(descriptor):
    """
    Attempts to accept() on the descriptor, returns a client,address tuple 
    if it succeeds; returns None if it needs to trampoline, and raises 
    any exceptions.
    """
    try:
        return descriptor.accept()
    except socket.error, e:
        if e[0] == errno.EWOULDBLOCK:
            return None
        raise
        

if sys.platform[:3]=="win":
    # winsock sometimes throws ENOTCONN
    SOCKET_BLOCKING = set((errno.EWOULDBLOCK,))
    SOCKET_CLOSED = set((errno.ECONNRESET, errno.ENOTCONN, errno.ESHUTDOWN))
else:
    # oddly, on linux/darwin, an unconnected socket is expected to block,
    # so we treat ENOTCONN the same as EWOULDBLOCK
    SOCKET_BLOCKING = set((errno.EWOULDBLOCK, errno.ENOTCONN))
    SOCKET_CLOSED = set((errno.ECONNRESET, errno.ESHUTDOWN, errno.EPIPE))


def set_nonblocking(fd):
    """
    Sets the descriptor to be nonblocking.  Works on many file-like
    objects as well as sockets.  Only sockets can be nonblocking on 
    Windows, however.
    """
    try:
        setblocking = fd.setblocking
    except AttributeError:
        # fd has no setblocking() method. It could be that this version of
        # Python predates socket.setblocking(). In that case, we can still set
        # the flag "by hand" on the underlying OS fileno using the fcntl
        # module.
        try:
            import fcntl
        except ImportError:
            # Whoops, Windows has no fcntl module. This might not be a socket
            # at all, but rather a file-like object with no setblocking()
            # method. In particular, on Windows, pipes don't support
            # non-blocking I/O and therefore don't have that method. Which
            # means fcntl wouldn't help even if we could load it.
            raise NotImplementedError("set_nonblocking() on a file object "
                                      "with no setblocking() method "
                                      "(Windows pipes don't support non-blocking I/O)")
        # We managed to import fcntl.
        fileno = fd.fileno()
        flags = fcntl.fcntl(fileno, fcntl.F_GETFL)
        fcntl.fcntl(fileno, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    else:
        # socket supports setblocking()
        setblocking(0)


try:
    from socket import _GLOBAL_DEFAULT_TIMEOUT
except ImportError:
    _GLOBAL_DEFAULT_TIMEOUT = object()
    

class GreenSocket(object):
    """
    Green version of socket.socket class, that is intended to be 100%
    API-compatible.
    """
    timeout = None
    def __init__(self, family_or_realsock=socket.AF_INET, *args, **kwargs):
        if isinstance(family_or_realsock, (int, long)):
            fd = _original_socket(family_or_realsock, *args, **kwargs)
        else:
            fd = family_or_realsock
            assert not args, args
            assert not kwargs, kwargs

        # import timeout from other socket, if it was there
        try:
            self.timeout = fd.gettimeout() or socket.getdefaulttimeout()
        except AttributeError:
            self.timeout = socket.getdefaulttimeout()
        
        set_nonblocking(fd)
        self.fd = fd
        self.closed = False
        # when client calls setblocking(0) or settimeout(0) the socket must
        # act non-blocking
        self.act_non_blocking = False
        
    @property
    def _sock(self):
        return self

    @property
    def family(self):
        return self.fd.family

    @property
    def type(self):
        return self.fd.type

    @property
    def proto(self):
        return self.fd.proto

    def accept(self):
        if self.act_non_blocking:
            return self.fd.accept()
        fd = self.fd
        while True:
            res = socket_accept(fd)
            if res is not None:
                client, addr = res
                set_nonblocking(client)
                return type(self)(client), addr
            trampoline(fd, read=True, timeout=self.gettimeout(),
                           timeout_exc=socket.timeout)

    def bind(self, *args, **kw):
        fn = self.bind = self.fd.bind
        return fn(*args, **kw)

    def close(self, *args, **kw):
        if self.closed:
            return
        self.closed = True
        res = self.fd.close()
        return res

    def connect(self, address):
        if self.act_non_blocking:
            return self.fd.connect(address)
        fd = self.fd
        if self.gettimeout() is None:
            while not socket_connect(fd, address):
                trampoline(fd, write=True, timeout_exc=socket.timeout)
        else:
            end = time.time() + self.gettimeout()
            while True:
                if socket_connect(fd, address):
                    return
                if time.time() >= end:
                    raise socket.timeout("timed out")
                trampoline(fd, write=True, timeout=end-time.time(), timeout_exc=socket.timeout('timed out'))

    def connect_ex(self, address):
        if self.act_non_blocking:
            return self.fd.connect_ex(address)
        fd = self.fd
        if self.gettimeout() is None:
            while not socket_connect(fd, address):
                try:
                    trampoline(fd, write=True, timeout_exc=socket.timeout('timed out'))
                except socket.error, ex:
                    return ex[0]
        else:
            end = time.time() + self.gettimeout()
            while True:
                if socket_connect(fd, address):
                    return 0
                if time.time() >= end:
                    raise socket.timeout("timed out")
                try:
                    trampoline(fd, write=True, timeout=end-time.time(), timeout_exc=socket.timeout('timed out'))
                except socket.error, ex:
                    return ex[0]

    def dup(self, *args, **kw):
        sock = self.fd.dup(*args, **kw)
        set_nonblocking(sock)
        newsock = type(self)(sock)
        newsock.settimeout(self.timeout)
        return newsock

    def fileno(self, *args, **kw):
        fn = self.fileno = self.fd.fileno
        return fn(*args, **kw)

    def getpeername(self, *args, **kw):
        fn = self.getpeername = self.fd.getpeername
        return fn(*args, **kw)

    def getsockname(self, *args, **kw):
        fn = self.getsockname = self.fd.getsockname
        return fn(*args, **kw)

    def getsockopt(self, *args, **kw):
        fn = self.getsockopt = self.fd.getsockopt
        return fn(*args, **kw)

    def listen(self, *args, **kw):
        fn = self.listen = self.fd.listen
        return fn(*args, **kw)

    def makefile(self, mode='r', bufsize=-1):
        return socket._fileobject(self.dup(), mode, bufsize)

    def makeGreenFile(self, mode='r', bufsize=-1):
        warnings.warn("makeGreenFile has been deprecated, please use "
            "makefile instead", DeprecationWarning, stacklevel=2)
        return self.makefile(mode, bufsize)

    def recv(self, buflen, flags=0):
        fd = self.fd
        if self.act_non_blocking:
            return fd.recv(buflen, flags)
        while True:
            try:
                return fd.recv(buflen, flags)
            except socket.error, e:
                if e[0] in SOCKET_BLOCKING:
                    pass
                elif e[0] in SOCKET_CLOSED:
                    return ''
                else:
                    raise
            trampoline(fd, 
                read=True, 
                timeout=self.timeout, 
                timeout_exc=socket.timeout('timed out'))

    def recvfrom(self, *args):
        if not self.act_non_blocking:
            trampoline(self.fd, read=True, timeout=self.gettimeout(), timeout_exc=socket.timeout('timed out'))
        return self.fd.recvfrom(*args)

    def recvfrom_into(self, *args):
        if not self.act_non_blocking:
            trampoline(self.fd, read=True, timeout=self.gettimeout(), timeout_exc=socket.timeout('timed out'))
        return self.fd.recvfrom_into(*args)

    def recv_into(self, *args):
        if not self.act_non_blocking:
            trampoline(self.fd, read=True, timeout=self.gettimeout(), timeout_exc=socket.timeout('timed out'))
        return self.fd.recv_into(*args)

    def send(self, data, flags=0):
        fd = self.fd
        if self.act_non_blocking:
            return fd.send(data, flags)
        try:
            return fd.send(data, flags)
        except socket.error, e:
            if e[0] in SOCKET_BLOCKING:
                return 0
            raise

    def sendall(self, data, flags=0):
        fd = self.fd
        tail = self.send(data, flags)
        len_data = len(data)
        while tail < len_data:
            trampoline(fd, 
                write=True, 
                timeout=self.timeout, 
                timeout_exc=socket.timeout('timed out'))
            tail += self.send(data[tail:], flags)

    def sendto(self, *args):
        trampoline(self.fd, write=True, timeout_exc=socket.timeout('timed out'))
        return self.fd.sendto(*args)

    def setblocking(self, flag):
        if flag:
            self.act_non_blocking = False
            self.timeout = None
        else:
            self.act_non_blocking = True
            self.timeout = 0.0

    def setsockopt(self, *args, **kw):
        fn = self.setsockopt = self.fd.setsockopt
        return fn(*args, **kw)

    def shutdown(self, *args, **kw):
        fn = self.shutdown = self.fd.shutdown
        return fn(*args, **kw)

    def settimeout(self, howlong):
        if howlong is None or howlong == _GLOBAL_DEFAULT_TIMEOUT:
            self.setblocking(True)
            return
        try:
            f = howlong.__float__
        except AttributeError:
            raise TypeError('a float is required')
        howlong = f()
        if howlong < 0.0:
            raise ValueError('Timeout value out of range')
        if howlong == 0.0:
            self.setblocking(howlong)
        else:
            self.timeout = howlong

    def gettimeout(self):
        return self.timeout


class GreenPipe(object):
    """ GreenPipe is a cooperatively-yielding wrapper around OS pipes.
    """
    newlines = '\r\n'
    def __init__(self, fd):
        set_nonblocking(fd)
        self.fd = fd
        self.closed = False
        self.recvbuffer = ''
        
    def close(self):
        self.fd.close()
        self.closed = True
        
    def fileno(self):
        return self.fd.fileno()

    def _recv(self, buflen):
        fd = self.fd
        buf = self.recvbuffer
        if buf:
            chunk, self.recvbuffer = buf[:buflen], buf[buflen:]
            return chunk
        while True:
            try:
                return fd.read(buflen)
            except IOError, e:
                if e[0] != EAGAIN:
                    return ''
            except socket.error, e:
                if e[0] == errno.EPIPE:
                    return ''
                raise
            trampoline(fd, read=True)


    def read(self, size=None):
        """read at most size bytes, returned as a string."""
        accum = ''
        while True:
            if size is None:
                recv_size = BUFFER_SIZE
            else:
                recv_size = size - len(accum)
            chunk =  self._recv(recv_size)
            accum += chunk
            if chunk == '':
                return accum
            if size is not None and len(accum) >= size:
                return accum

    def write(self, data):
        fd = self.fd
        while True:
            try:
                fd.write(data)
                fd.flush()
                return len(data)
            except IOError, e:
                if e[0] != EAGAIN:
                    raise
            except ValueError, e:
                # what's this for?
                pass
            except socket.error, e:
                if e[0] != errno.EPIPE:
                    raise
            trampoline(fd, write=True)

    def flush(self):
        pass
        
    def readuntil(self, terminator, size=None):
        buf, self.recvbuffer = self.recvbuffer, ''
        checked = 0
        if size is None:
            while True:
                found = buf.find(terminator, checked)
                if found != -1:
                    found += len(terminator)
                    chunk, self.recvbuffer = buf[:found], buf[found:]
                    return chunk
                checked = max(0, len(buf) - (len(terminator) - 1))
                d = self.fd.read(BUFFER_SIZE)
                if not d:
                    break
                buf += d
            return buf
        while len(buf) < size:
            found = buf.find(terminator, checked)
            if found != -1:
                found += len(terminator)
                chunk, self.recvbuffer = buf[:found], buf[found:]
                return chunk
            checked = len(buf)
            d = self.fd.read(BUFFER_SIZE)
            if not d:
                break
            buf += d
        chunk, self.recvbuffer = buf[:size], buf[size:]
        return chunk
        
    def readline(self, size=None):
        return self.readuntil(self.newlines, size=size)

    def __iter__(self):
        return self.xreadlines()

    def xreadlines(self, size=None):
        if size is None:
            while True:
                line = self.readline()
                if not line:
                    break
                yield line
        else:
            while size > 0:
                line = self.readline(size)
                if not line:
                    break
                yield line
                size -= len(line)

    def writelines(self, lines):
        for line in lines:
            self.write(line)


# import SSL module here so we can refer to greenio.SSL.exceptionclass
try:
    from OpenSSL import SSL
except ImportError:
    # pyOpenSSL not installed, define exceptions anyway for convenience
    class SSL(object):
        class WantWriteError(object):
            pass
        
        class WantReadError(object):
            pass
        
        class ZeroReturnError(object):
            pass
        
        class SysCallError(object):
            pass
    

def shutdown_safe(sock):
    """ Shuts down the socket. This is a convenience method for
    code that wants to gracefully handle regular sockets, SSL.Connection 
    sockets from PyOpenSSL and ssl.SSLSocket objects from Python 2.6
    interchangeably.  Both types of ssl socket require a shutdown() before
    close, but they have different arity on their shutdown method.
    
    Regular sockets don't need a shutdown before close, but it doesn't hurt.
    """
    try:
        try:
            # socket, ssl.SSLSocket
            return sock.shutdown(socket.SHUT_RDWR)
        except TypeError:
            # SSL.Connection
            return sock.shutdown()
    except socket.error, e:
        # we don't care if the socket is already closed;
        # this will often be the case in an http server context
        if e[0] != errno.ENOTCONN:
            raise
            
            
def connect(addr, family=socket.AF_INET, bind=None):
    """Convenience function for opening client sockets.
    
    :param addr: Address of the server to connect to.  For TCP sockets, this is a (host, port) tuple.
    :param family: Socket family, optional.  See :mod:`socket` documentation for available families.
    :param bind: Local address to bind to, optional.
    :return: The connected green socket object.
    """
    sock = GreenSocket(family, socket.SOCK_STREAM)
    if bind is not None:
        sock.bind(bind)
    sock.connect(addr)
    return sock
    
    
def listen(addr, family=socket.AF_INET, backlog=50):
    """Convenience function for opening server sockets.  This
    socket can be used in an ``accept()`` loop.

    Sets SO_REUSEADDR on the socket to save on annoyance.
    
    :param addr: Address to listen on.  For TCP sockets, this is a (host, port)  tuple.
    :param family: Socket family, optional.  See :mod:`socket` documentation for available families.
    :param backlog: The maximum number of queued connections. Should be at least 1; the maximum value is system-dependent.
    :return: The listening green socket object.
    """
    sock = GreenSocket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(addr)
    sock.listen(backlog)
    return sock


def wrap_ssl(sock, keyfile=None, certfile=None, server_side=False,
    cert_reqs=None, ssl_version=None, ca_certs=None, 
    do_handshake_on_connect=True, suppress_ragged_eofs=True):
    """Convenience function for converting a regular socket into an SSL 
    socket.  Has the same interface as :func:`ssl.wrap_socket`, but 
    works on 2.5 or earlier, using PyOpenSSL.

    The preferred idiom is to call wrap_ssl directly on the creation
    method, e.g., ``wrap_ssl(connect(addr))`` or 
    ``wrap_ssl(listen(addr), server_side=True)``. This way there is
    no "naked" socket sitting around to accidentally corrupt the SSL
    session.
    
    :return Green SSL object.
    """
    pass


def serve(sock, handle, concurrency=1000):
    """Runs a server on the supplied socket.  Calls the function 
    *handle* in a separate greenthread for every incoming request. 
    This function blocks the calling greenthread; it won't return until 
    the server completes.  If you desire an immediate return,
    spawn a new greenthread for :func:`serve`.
    
    The *handle* function must raise an EndServerException to 
    gracefully terminate the server -- that's the only way to get the 
    server() function to return.  Any other uncaught exceptions raised
    in *handle* are raised as exceptions from :func:`serve`, so be 
    sure to do a good job catching exceptions that your application 
    raises.  The return value of *handle* is ignored.

    The value in *concurrency* controls the maximum number of 
    greenthreads that will be open at any time handling requests.  When 
    the server hits the concurrency limit, it stops accepting new 
    connections until the existing ones complete.
    """
    pass
    
