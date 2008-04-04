"""\
@file util.py
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

import os
import fcntl
import socket
import select
import errno

try:
    from OpenSSL import SSL
except ImportError:
    class SSL(object):
        class WantWriteError(object):
            pass

        class WantReadError(object):
            pass

        class ZeroReturnError(object):
            pass

        class SysCallError(object):
            pass


def g_log(*args):
    import sys
    import greenlet
    from eventlet.greenlib import greenlet_id
    g_id = greenlet_id()
    if g_id is None:
        if greenlet.getcurrent().parent is None:
            ident = 'greenlet-main'
        else:
            g_id = id(greenlet.getcurrent())
            if g_id < 0:
                g_id += 1 + ((sys.maxint + 1) << 1)
            ident = '%08X' % (g_id,)
    else:
        ident = 'greenlet-%d' % (g_id,)
    print >>sys.stderr, '[%s] %s' % (ident, ' '.join(map(str, args)))

CONNECT_ERR = (errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK)
CONNECT_SUCCESS = (0, errno.EISCONN)
def socket_connect(descriptor, address):
    err = descriptor.connect_ex(address)
    if err in CONNECT_ERR:
        return None
    if err not in CONNECT_SUCCESS:
        raise socket.error(err, errno.errorcode[err])
    return descriptor

__original_socket__ = socket.socket


def tcp_socket():
    s = __original_socket__(socket.AF_INET, socket.SOCK_STREAM)
    set_nonblocking(s)
    return s


__original_ssl__ = socket.ssl


def wrap_ssl(sock, certificate=None, private_key=None):
    from OpenSSL import SSL
    from eventlet import wrappedfd, util
    context = SSL.Context(SSL.SSLv23_METHOD)
    print certificate, private_key
    if certificate is not None:
        context.use_certificate_file(certificate)
    if private_key is not None:
        context.use_privatekey_file(private_key)
    context.set_verify(SSL.VERIFY_NONE, lambda *x: True)

    ## TODO only do this on client sockets? how?
    connection = SSL.Connection(context, sock)
    connection.set_connect_state()
    return wrappedfd.wrapped_fd(connection)


def wrap_socket_with_coroutine_socket():
    def new_socket(*args, **kw):
        from eventlet import wrappedfd
        s = __original_socket__(*args, **kw)
        set_nonblocking(s)
        return wrappedfd.wrapped_fd(s)
    socket.socket = new_socket

    socket.ssl = wrap_ssl


__original_select__ = select.select


def fake_select(r, w, e, timeout):
    """This is to cooperate with people who are trying to do blocking
    reads with a timeout. This only works if r, w, and e aren't
    bigger than len 1, and if either r or w is populated.

    Install this with wrap_select_with_coroutine_select,
    which makes the global select.select into fake_select.
    """
    from eventlet import api

    assert len(r) <= 1
    assert len(w) <= 1
    assert len(e) <= 1

    if w and r:
        raise RuntimeError('fake_select doesn\'t know how to do that yet')

    try:
        if r:
            api.trampoline(r[0], read=True, timeout=timeout)
            return r, [], []
        else:
            api.trampoline(w[0], write=True, timeout=timeout)
            return [], w, []
    except api.TimeoutError, e:
        return [], [], []
    except:
        return [], [], e


def wrap_select_with_coroutine_select():
    select.select = fake_select


def socket_bind_and_listen(descriptor, addr=('', 0), backlog=50):
    set_reuse_addr(descriptor)
    descriptor.bind(addr)
    descriptor.listen(backlog)
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
        if e[0] == errno.EWOULDBLOCK:
            return 0
        raise
    except SSL.WantWriteError:
        return 0
    except SSL.WantReadError:
        return 0
    # trap this error
    except SSL.SysCallError, e:
        (ssl_errno, ssl_errstr) = e
        if ssl_errno == -1 or ssl_errno > 0:
            raise socket.error(errno.ECONNRESET, errno.errorcode[errno.ECONNRESET])
        raise

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
    except SSL.WantReadError:
        return None
    except SSL.ZeroReturnError:
        return ''
    except SSL.SysCallError, e:
        (ssl_errno, ssl_errstr) = e
        if ssl_errno == -1 or ssl_errno > 0:
            raise socket.error(errno.ECONNRESET, errno.errorcode[errno.ECONNRESET])
        raise

def file_recv(fd, buflen):
    try:
        return fd.read(buflen)
    except IOError, e:
        if e[0] == errno.EAGAIN:
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
        if e[0] == errno.EAGAIN:
            return 0
    except ValueError, e:
        written = 0
    except socket.error, e:
        if e[0] == errno.EPIPE:
            written = 0


def set_reuse_addr(descriptor):
    try:
        descriptor.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            descriptor.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) | 1,
        )
    except socket.error:
        pass
    
def set_nonblocking(descriptor):
    if hasattr(descriptor, 'setblocking'):
        # socket
        descriptor.setblocking(0)
    else:
        # fd
        if hasattr(descriptor, 'fileno'):
            fd = descriptor.fileno()
        else:
            fd = descriptor
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    return descriptor

