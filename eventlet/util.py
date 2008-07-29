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
import select
import socket
import sys
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


__original_socket__ = socket.socket
__original_gethostbyname__ = socket.gethostbyname
__original_getaddrinfo__ = socket.getaddrinfo
__original_fromfd__ = socket.fromfd

def tcp_socket():
    s = __original_socket__(socket.AF_INET, socket.SOCK_STREAM)
    return s


try:
    __original_ssl__ = socket.ssl
except AttributeError:
    __original_ssl__ = None


def wrap_ssl(sock, certificate=None, private_key=None):
    from OpenSSL import SSL
    from eventlet import greenio, util
    context = SSL.Context(SSL.SSLv23_METHOD)
    if certificate is not None:
        context.use_certificate_file(certificate)
    if private_key is not None:
        context.use_privatekey_file(private_key)
    context.set_verify(SSL.VERIFY_NONE, lambda *x: True)

    ## TODO only do this on client sockets? how?
    connection = SSL.Connection(context, sock)
    connection.set_connect_state()
    return greenio.GreenSSL(connection)


socket_already_wrapped = False
def wrap_socket_with_coroutine_socket(use_thread_pool=True):
    global socket_already_wrapped
    if socket_already_wrapped:
        return

    def new_socket(*args, **kw):
        from eventlet import greenio
        return greenio.GreenSocket(__original_socket__(*args, **kw))
    socket.socket = new_socket

    socket.ssl = wrap_ssl

    if use_thread_pool:
        from eventlet import tpool
        def new_gethostbyname(*args, **kw):
            return tpool.execute(
                __original_gethostbyname__, *args, **kw)
        socket.gethostbyname = new_gethostbyname

        def new_getaddrinfo(*args, **kw):
            return tpool.execute(
                __original_getaddrinfo__, *args, **kw)
        socket.getaddrinfo = new_getaddrinfo

    def new_fromfd(*args, **kw):
        from eventlet import greenio
        return greenio.GreenSocket(__original_fromfd__(*args, **kw))
    socket.fromfd = new_fromfd

    socket_already_wrapped = True


__original_fdopen__ = os.fdopen
__original_read__ = os.read
__original_write__ = os.write
__original_waitpid__ = os.waitpid
__original_fork__ = os.fork
## TODO wrappings for popen functions? not really needed since Process object exists?


pipes_already_wrapped = False
def wrap_pipes_with_coroutine_pipes():
    from eventlet import processes ## Make sure the signal handler is installed
    global pipes_already_wrapped
    if pipes_already_wrapped:
        return
    def new_fdopen(*args, **kw):
        from eventlet import greenio
        return greenio.GreenPipe(__original_fdopen__(*args, **kw))
    def new_read(fd, *args, **kw):
        from eventlet import api
        api.trampoline(fd, read=True)
        return __original_read__(fd, *args, **kw)
    def new_write(fd, *args, **kw):
        from eventlet import api
        api.trampoline(fd, write=True)
        return __original_write__(fd, *args, **kw)
    def new_fork(*args, **kwargs):
        pid = __original_fork__()
        if pid:
            processes._add_child_pid(pid)
        return pid
    def new_waitpid(pid, options):
        from eventlet import processes
        evt = processes.CHILD_EVENTS.get(pid)
        if not evt:
            return 0, 0
        if options == os.WNOHANG:
            if evt.ready():
                return pid, evt.wait()
            return 0, 0
        elif options:
            return __original_waitpid__(pid, result)
        return pid, evt.wait()
    os.fdopen = new_fdopen
    os.read = new_read
    os.write = new_write
    os.fork = new_fork
    os.waitpid = new_waitpid

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


try:
    import threading
    __original_threadlocal__ = threading.local
except ImportError:
    pass


def wrap_threading_local_with_coro_local():
    """monkey patch threading.local with something that is
    greenlet aware. Since greenlets cannot cross threads,
    so this should be semantically identical to threadlocal.local
    """
    from eventlet import api
    def get_ident():
        return id(api.getcurrent())

    class local(object):
        def __init__(self):
            self.__dict__['__objs'] = {}
    
        def __getattr__(self, attr, g=get_ident):
            try:
                return self.__dict__['__objs'][g()][attr]
            except KeyError:
                raise AttributeError(
                    "No variable %s defined for the thread %s"
                    % (attr, g()))
    
        def __setattr__(self, attr, value, g=get_ident):
            self.__dict__['__objs'].setdefault(g(), {})[attr] = value
    
        def __delattr__(self, attr, g=get_ident):
            try:
                del self.__dict__['__objs'][g()][attr]
            except KeyError:
                raise AttributeError(
                    "No variable %s defined for thread %s"
                    % (attr, g()))

    threading.local = local


def socket_bind_and_listen(descriptor, addr=('', 0), backlog=50):
    set_reuse_addr(descriptor)
    descriptor.bind(addr)
    descriptor.listen(backlog)
    return descriptor


def set_reuse_addr(descriptor):
    try:
        descriptor.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            descriptor.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) | 1,
        )
    except socket.error:
        pass

