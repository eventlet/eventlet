# Copyright (c) 2005-2006, Bob Ippolito
# Copyright (c) 2007, Linden Research, Inc.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from eventlet.api import trampoline, get_hub
from eventlet import util


BUFFER_SIZE = 4096

import errno
import os
import socket
from socket import socket as _original_socket
import time


from errno import EWOULDBLOCK, EAGAIN


__all__ = ['GreenSocket', 'GreenFile', 'GreenPipe']

def higher_order_recv(recv_func):
    def recv(self, buflen):
        if self.act_non_blocking:
            return self.fd.recv(buflen)
        buf = self.recvbuffer
        if buf:
            chunk, self.recvbuffer = buf[:buflen], buf[buflen:]
            return chunk
        fd = self.fd
        bytes = recv_func(fd, buflen)
        if self.gettimeout():
            end = time.time()+self.gettimeout()
        else:
            end = None
        timeout = None
        while bytes is None:
            try:
                if end:
                    timeout = end - time.time()
                trampoline(fd, read=True, timeout=timeout, timeout_exc=socket.timeout)
            except socket.timeout:
                raise
            except socket.error, e:
                if e[0] == errno.EPIPE:
                    bytes = ''
                else:
                    raise
            else:
                bytes = recv_func(fd, buflen)
        self.recvcount += len(bytes)
        return bytes
    return recv


def higher_order_send(send_func):
    def send(self, data):
        if self.act_non_blocking:
            return self.fd.send(data)
        count = send_func(self.fd, data)
        if not count:
            return 0
        self.sendcount += count
        return count
    return send


CONNECT_ERR = (errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK)
CONNECT_SUCCESS = (0, errno.EISCONN)
def socket_connect(descriptor, address):
    err = descriptor.connect_ex(address)
    if err in CONNECT_ERR:
        return None
    if err not in CONNECT_SUCCESS:
        raise socket.error(err, errno.errorcode[err])
    return descriptor


def socket_accept(descriptor):
    try:
        return descriptor.accept()
    except socket.error, e:
        if e[0] == errno.EWOULDBLOCK:
            return None
        raise


def socket_send(descriptor, data):
    try:
        return descriptor.send(data)
    except socket.error, e:
        if e[0] == errno.EWOULDBLOCK or e[0] == errno.ENOTCONN:
            return 0
        raise
    except util.SSL.WantWriteError:
        return 0
    except util.SSL.WantReadError:
        return 0

# winsock sometimes throws ENOTCONN
SOCKET_CLOSED = (errno.ECONNRESET, errno.ENOTCONN, errno.ESHUTDOWN)
def socket_recv(descriptor, buflen):
    try:
        return descriptor.recv(buflen)
    except socket.error, e:
        if e[0] == errno.EWOULDBLOCK:
            return None
        if e[0] in SOCKET_CLOSED:
            return ''
        raise
    except util.SSL.WantReadError:
        return None
    except util.SSL.ZeroReturnError:
        return ''
    except util.SSL.SysCallError, e:
        if e[0] == -1 or e[0] > 0:
            return ''
        raise


def file_recv(fd, buflen):
    try:
        return fd.read(buflen)
    except IOError, e:
        if e[0] == EAGAIN:
            return None
        return ''
    except socket.error, e:
        if e[0] == errno.EPIPE:
            return ''
        raise


def file_send(fd, data):
    try:
        fd.write(data)
        fd.flush()
        return len(data)
    except IOError, e:
        if e[0] == EAGAIN:
            return 0
    except ValueError, e:
        written = 0
    except socket.error, e:
        if e[0] == errno.EPIPE:
            written = 0


def set_nonblocking(fd):
    try:
        setblocking = fd.setblocking
    except AttributeError:
        # This version of Python predates socket.setblocking()
        import fcntl
        fileno = fd.fileno()
        flags = fcntl.fcntl(fileno, fcntl.F_GETFL)
        fcntl.fcntl(fileno, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    else:
        # socket supports setblocking()
        setblocking(0)


class GreenSocket(object):
    is_secure = False
    timeout = None
    def __init__(self, family_or_realsock=socket.AF_INET, *args, **kwargs):
        if isinstance(family_or_realsock, (int, long)):
            fd = _original_socket(family_or_realsock, *args, **kwargs)
        else:
            fd = family_or_realsock
            assert not args, args
            assert not kwargs, kwargs

        set_nonblocking(fd)
        self.fd = fd
        self._fileno = fd.fileno()
        self.sendcount = 0
        self.recvcount = 0
        self.recvbuffer = ''
        self.closed = False
        self.timeout = socket.getdefaulttimeout()

        # when client calls setblocking(0) or settimeout(0) the socket must
        # act non-blocking
        self.act_non_blocking = False

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
            trampoline(fd, read=True, timeout=self.gettimeout(), timeout_exc=socket.timeout)

    def bind(self, *args, **kw):
        fn = self.bind = self.fd.bind
        return fn(*args, **kw)

    def close(self, *args, **kw):
        if self.closed:
            return
        self.closed = True
        if self.is_secure:
            # *NOTE: This is not quite the correct SSL shutdown sequence.
            # We should actually be checking the return value of shutdown.
            # Note also that this is not the same as calling self.shutdown().
            self.fd.shutdown()

        fn = self.close = self.fd.close
        try:
            res = fn(*args, **kw)
        finally:
            # This will raise socket.error(32, 'Broken pipe') if there's
            # a caller waiting on trampoline (e.g. server on .accept())
            get_hub().exc_descriptor(self._fileno)
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
                    raise socket.timeout
                trampoline(fd, write=True, timeout=end-time.time(), timeout_exc=socket.timeout)

    def connect_ex(self, address):
        if self.act_non_blocking:
            return self.fd.connect_ex(address)
        fd = self.fd
        if self.gettimeout() is None:
            while not socket_connect(fd, address):
                try:
                    trampoline(fd, write=True, timeout_exc=socket.timeout)
                except socket.error, ex:
                    return ex[0]
        else:
            end = time.time() + self.gettimeout()
            while True:
                if socket_connect(fd, address):
                    return 0
                if time.time() >= end:
                    raise socket.timeout
                try:
                    trampoline(fd, write=True, timeout=end-time.time(), timeout_exc=socket.timeout)
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
        return GreenFile(self.dup())

    recv = higher_order_recv(socket_recv)

    def recvfrom(self, *args):
        if not self.act_non_blocking:
            trampoline(self.fd, read=True, timeout=self.gettimeout(), timeout_exc=socket.timeout)
        return self.fd.recvfrom(*args)

    def recvfrom_into(self, *args):
        if not self.act_non_blocking:
            trampoline(self.fd, read=True, timeout=self.gettimeout(), timeout_exc=socket.timeout)
        return self.fd.recvfrom_into(*args)

    def recv_into(self, *args):
        if not self.act_non_blocking:
            trampoline(self.fd, read=True, timeout=self.gettimeout(), timeout_exc=socket.timeout)
        return self.fd.recv_into(*args)

    send = higher_order_send(socket_send)

    def sendall(self, data):
        fd = self.fd
        tail = self.send(data)
        while tail < len(data):
            trampoline(self.fd, write=True, timeout_exc=socket.timeout)
            tail += self.send(data[tail:])

    def sendto(self, *args):
        trampoline(self.fd, write=True, timeout_exc=socket.timeout)
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
        if self.is_secure:
            fn = self.shutdown = self.fd.sock_shutdown
        else:
            fn = self.shutdown = self.fd.shutdown
        return fn(*args, **kw)

    def settimeout(self, howlong):
        if howlong is None:
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

def read(self, size=None):
    if size is not None and not isinstance(size, (int, long)):
        raise TypeError('Expecting an int or long for size, got %s: %s' % (type(size), repr(size)))
    buf, self.sock.recvbuffer = self.sock.recvbuffer, ''
    lst = [buf]
    if size is None:
        while True:
            d = self.sock.recv(BUFFER_SIZE)
            if not d:
                break
            lst.append(d)
    else:
        buflen = len(buf)
        while buflen < size:
            d = self.sock.recv(BUFFER_SIZE)
            if not d:
                break
            buflen += len(d)
            lst.append(d)
        else:
            d = lst[-1]
            overbite = buflen - size
            if overbite:
                lst[-1], self.sock.recvbuffer = d[:-overbite], d[-overbite:]
            else:
                lst[-1], self.sock.recvbuffer = d, ''
    return ''.join(lst)


class GreenFile(object):
    newlines = '\r\n'
    mode = 'wb+'

    def __init__(self, fd):
        if isinstance(fd, GreenSocket):
            set_nonblocking(fd.fd)
        else:
            set_nonblocking(fd)
        self.sock = fd
        self.closed = False

    def close(self):
        self.sock.close()
        self.closed = True

    def fileno(self):
        return self.sock.fileno()

    # TODO next

    def flush(self):
        pass

    def write(self, data):
        return self.sock.sendall(data)

    def readuntil(self, terminator, size=None):
        buf, self.sock.recvbuffer = self.sock.recvbuffer, ''
        checked = 0
        if size is None:
            while True:
                found = buf.find(terminator, checked)
                if found != -1:
                    found += len(terminator)
                    chunk, self.sock.recvbuffer = buf[:found], buf[found:]
                    return chunk
                checked = max(0, len(buf) - (len(terminator) - 1))
                d = self.sock.recv(BUFFER_SIZE)
                if not d:
                    break
                buf += d
            return buf
        while len(buf) < size:
            found = buf.find(terminator, checked)
            if found != -1:
                found += len(terminator)
                chunk, self.sock.recvbuffer = buf[:found], buf[found:]
                return chunk
            checked = len(buf)
            d = self.sock.recv(BUFFER_SIZE)
            if not d:
                break
            buf += d
        chunk, self.sock.recvbuffer = buf[:size], buf[size:]
        return chunk

    def readline(self, size=None):
        return self.readuntil(self.newlines, size=size)

    def __iter__(self):
        return self.xreadlines()

    def readlines(self, size=None):
        return list(self.xreadlines(size=size))

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

    read = read


class GreenPipeSocket(GreenSocket):
    """ This is a weird class that looks like a socket but expects a file descriptor as an argument instead of a socket.
    """
    recv = higher_order_recv(file_recv)

    send = higher_order_send(file_send)


class GreenPipe(GreenFile):
    def __init__(self, fd):
        set_nonblocking(fd)
        self.fd = GreenPipeSocket(fd)
        super(GreenPipe, self).__init__(self.fd)

    def recv(self, *args, **kw):
        fn = self.recv = self.fd.recv
        return fn(*args, **kw)

    def send(self, *args, **kw):
        fn = self.send = self.fd.send
        return fn(*args, **kw)

    def flush(self):
        self.fd.fd.flush()



class RefCount(object):
    """ Reference counting class only to be used with GreenSSL objects """
    def __init__(self):
        self._count = 1

    def increment(self):
        self._count += 1

    def decrement(self):
        self._count -= 1
        assert self._count >= 0

    def is_referenced(self):
        return self._count > 0


class GreenSSL(GreenSocket):
    def __init__(self, fd, refcount = None):
        GreenSocket.__init__(self, fd)
        self.sock = self
        self._refcount = refcount
        if refcount is None:
            self._refcount = RefCount()

    read = read
    
    def sendall(self, data):
        # overriding sendall because ssl sockets behave badly when asked to 
        # send empty strings; 'normal' sockets don't have a problem
        if not data:
            return
        super(GreenSSL, self).sendall(data)

    def write(self, data):
        try:
            return self.sendall(data)
        except util.SSL.Error, ex:
            raise socket.sslerror(str(ex))

    def server(self):
        return self.fd.server()

    def issuer(self):
        return self.fd.issuer()

    def dup(self):
        raise NotImplementedError("Dup not supported on SSL sockets")

    def makefile(self, *args, **kw):
        self._refcount.increment()
        return GreenFile(type(self)(self.fd, refcount = self._refcount))
        
    makeGreenFile = makefile

    def close(self):
        self._refcount.decrement()
        if self._refcount.is_referenced():
            return
        super(GreenSSL, self).close()


    

def socketpair(*args):
    one, two = socket.socketpair(*args)
    return GreenSocket(one), GreenSocket(two)


def fromfd(*args):
    return GreenSocket(socket.fromfd(*args))
    
