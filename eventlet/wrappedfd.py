"""\
@file wrappedfd.py
@author Bob Ippolito

Copyright (c) 2005-2006, Bob Ippolito
Copyright (c) 2007, Linden Research, Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
from eventlet.api import trampoline, get_hub
from eventlet import util

BUFFER_SIZE = 4096

import socket, errno


def higher_order_recv(recv_func):
    def recv(self, buflen):
        buf = self.recvbuffer
        if buf:
            chunk, self.recvbuffer = buf[:buflen], buf[buflen:]
            return chunk
        fd = self.fd
        bytes = recv_func(fd, buflen)
        while bytes is None:
            try:
                trampoline(fd, read=True)
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
        count = send_func(self.fd, data)
        if not count:
            return 0
        self.sendcount += count
        return count
    return send



class RefCount(object):
    def __init__(self):
        self._count = 1

    def increment(self):
        self._count += 1

    def decrement(self):
        self._count -= 1
        assert self._count >= 0

    def is_referenced(self):
        return self._count > 0

class wrapped_fd(object):
    newlines = '\r\n'
    mode = 'wb+'
    is_secure = False

    def __init__(self, fd, refcount = None):
        self._closed = False
        self.fd = fd
        self._fileno = fd.fileno()
        self.recvbuffer = ''
        self.recvcount = 0
        self.sendcount = 0
        self._refcount = refcount
        if refcount is None:
            self._refcount = RefCount()

    def getpeername(self, *args, **kw):
        fn = self.getpeername = self.fd.getpeername
        return fn(*args, **kw)

    def getsockname(self, *args, **kw):
        fn = self.getsockname = self.fd.getsockname
        return fn(*args, **kw)

    def listen(self, *args, **kw):
        fn = self.listen = self.fd.listen
        return fn(*args, **kw)

    def bind(self, *args, **kw):
        fn = self.bind = self.fd.bind
        return fn(*args, **kw)

    def getsockopt(self, *args, **kw):
        fn = self.getsockopt = self.fd.getsockopt
        return fn(*args, **kw)

    def setsockopt(self, *args, **kw):
        fn = self.setsockopt = self.fd.setsockopt
        return fn(*args, **kw)

    def connect_ex(self, *args, **kw):
        fn = self.connect_ex = self.fd.connect_ex
        return fn(*args, **kw)

    def fileno(self, *args, **kw):
        fn = self.fileno = self.fd.fileno
        return fn(*args, **kw)

    def setblocking(self, *args, **kw):
        fn = self.setblocking = self.fd.setblocking
        return fn(*args, **kw)

    def close(self, *args, **kw):
        if self._closed:
            return
        self._refcount.decrement()
        if self._refcount.is_referenced():
            return
        self._closed = True
        fn = self.close = self.fd.close
        try:
            res = fn(*args, **kw)
        finally:
            # This will raise socket.error(32, 'Broken pipe') if there's
            # a caller waiting on trampoline (e.g. server on .accept())
            get_hub().exc_descriptor(self._fileno)
        return res

    def accept(self):
        fd = self.fd
        while True:
            res = util.socket_accept(fd)
            if res is not None:
                client, addr = res
                util.set_nonblocking(client)
                return type(self)(client), addr
            trampoline(fd, read=True, write=True)

    def connect(self, address):
        fd = self.fd
        connect = util.socket_connect
        while not connect(fd, address):
            trampoline(fd, read=True, write=True)

    recv = higher_order_recv(util.socket_recv)

    def recvfrom(self, *args):
        trampoline(self.fd, read=True)
        return self.fd.recvfrom(*args)

    send = higher_order_send(util.socket_send)

    def sendto(self, *args):
        trampoline(self.fd, write=True)
        return self.fd.sendto(*args)

    def sendall(self, data):
        fd = self.fd
        tail = self.send(data)
        while tail < len(data):
            trampoline(self.fd, write=True)
            tail += self.send(data[tail:])

    def write(self, data):
        return self.sendall(data)
    
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
                d = self.recv(BUFFER_SIZE)
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
            d = self.recv(BUFFER_SIZE)
            if not d:
                break
            buf += d
        chunk, self.recvbuffer = buf[:size], buf[size:]
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
        
    def read(self, size=None):
        if size is not None and not isinstance(size, (int, long)):
            raise TypeError('Expecting an int or long for size, got %s: %s' % (type(size), repr(size)))
        buf, self.recvbuffer = self.recvbuffer, ''
        lst = [buf]
        if size is None:
            while True:
                d = self.recv(BUFFER_SIZE)
                if not d:
                    break
                lst.append(d)
        else:
            buflen = len(buf)
            while buflen < size:
                d = self.recv(BUFFER_SIZE)
                if not d:
                    break
                buflen += len(d)
                lst.append(d)
            else:
                d = lst[-1]
                overbite = buflen - size
                if overbite:
                    lst[-1], self.recvbuffer = d[:-overbite], d[-overbite:]
                else:
                    lst[-1], self.recvbuffer = d, ''
        return ''.join(lst)

    def makefile(self, *args, **kw):
        self._refcount.increment()
        return type(self)(self.fd, refcount = self._refcount)


class wrapped_file(wrapped_fd):
    recv = higher_order_recv(util.file_recv)

    send = higher_order_send(util.file_send)

    def flush(self):
        fn = self.flush = self.fd.flush
        return fn()
