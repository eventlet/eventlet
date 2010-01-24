import os
import select
import socket
import errno

from eventlet import greenio

def g_log(*args):
    import sys
    from eventlet.support import greenlets as greenlet
    g_id = id(greenlet.getcurrent())
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
try:
    __original_fromfd__ = socket.fromfd
    __original_fork__ = os.fork
except AttributeError:
    # Windows
    __original_fromfd__ = None
    __original_fork__ = None

def tcp_socket():
    s = __original_socket__(socket.AF_INET, socket.SOCK_STREAM)
    return s

try:
    # if ssl is available, use eventlet.green.ssl for our ssl implementation
    from eventlet.green import ssl
    def wrap_ssl(sock, certificate=None, private_key=None, server_side=False):
        return ssl.wrap_socket(sock,
            keyfile=private_key, certfile=certificate,
            server_side=server_side, cert_reqs=ssl.CERT_NONE,
            ssl_version=ssl.PROTOCOL_SSLv23, ca_certs=None,
            do_handshake_on_connect=True,
            suppress_ragged_eofs=True) 
except ImportError:
    # if ssl is not available, use PyOpenSSL
    def wrap_ssl(sock, certificate=None, private_key=None, server_side=False):
        try:
            from eventlet.green.OpenSSL import SSL
        except ImportError:
            raise ImportError("To use SSL with Eventlet, you must install PyOpenSSL or use Python 2.6 or later.")
        context = SSL.Context(SSL.SSLv23_METHOD)
        if certificate is not None:
            context.use_certificate_file(certificate)
        if private_key is not None:
            context.use_privatekey_file(private_key)
        context.set_verify(SSL.VERIFY_NONE, lambda *x: True)
    
        connection = SSL.Connection(context, sock)
        if server_side:
            connection.set_accept_state()
        else:
            connection.set_connect_state()
        return connection

socket_already_wrapped = False
def wrap_socket_with_coroutine_socket(use_thread_pool=None):
    global socket_already_wrapped
    if socket_already_wrapped:
        return

    import eventlet.green.socket
    socket.socket = eventlet.green.socket.socket
    socket.ssl = eventlet.green.socket.ssl
    try:
        import ssl as _ssl
        from eventlet.green import ssl
        _ssl.wrap_socket = ssl.wrap_socket
    except ImportError:
        pass

    if use_thread_pool is None:
        # if caller doesn't specify, use the environment variable
        # to decide whether to use tpool or not
        use_thread_pool = os.environ.get("EVENTLET_TPOOL_GETHOSTBYNAME",
                                         '').lower() == "yes"
    if use_thread_pool:
        try:
            from eventlet import tpool
            def new_gethostbyname(*args, **kw):
                return tpool.execute(
                    __original_gethostbyname__, *args, **kw)
            socket.gethostbyname = new_gethostbyname

            def new_getaddrinfo(*args, **kw):
                return tpool.execute(
                    __original_getaddrinfo__, *args, **kw)
            socket.getaddrinfo = new_getaddrinfo
        except ImportError:
            pass # Windows

    if __original_fromfd__ is not None:
        def new_fromfd(*args, **kw):
            return greenio.GreenSocket(__original_fromfd__(*args, **kw))
        socket.fromfd = new_fromfd

    socket_already_wrapped = True


__original_fdopen__ = os.fdopen
__original_read__ = os.read
__original_write__ = os.write
__original_waitpid__ = os.waitpid
## TODO wrappings for popen functions? not really needed since Process object exists?


pipes_already_wrapped = False
def wrap_pipes_with_coroutine_pipes():
    from eventlet import processes ## Make sure the signal handler is installed
    global pipes_already_wrapped
    if pipes_already_wrapped:
        return
    def new_fdopen(*args, **kw):
        return greenio.GreenPipe(__original_fdopen__(*args, **kw))
    def new_read(fd, *args, **kw):
        from eventlet import hubs
        try:
            hubs.trampoline(fd, read=True)
        except socket.error, e:
            if e[0] == errno.EPIPE:
                return ''
            else:
                raise
        return __original_read__(fd, *args, **kw)
    def new_write(fd, *args, **kw):
        from eventlet import hubs
        hubs.trampoline(fd, write=True)
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
            return __original_waitpid__(pid, options)
        return pid, evt.wait()
    os.fdopen = new_fdopen
    os.read = new_read
    os.write = new_write
    if __original_fork__ is not None:
        os.fork = new_fork
    os.waitpid = new_waitpid

__original_select__ = select.select

def wrap_select_with_coroutine_select():
    from eventlet.green import select as greenselect
    select.select = greenselect.select


try:
    import threading
    __original_threadlocal__ = threading.local
except ImportError:
    pass


def wrap_threading_local_with_coro_local():
    """
    monkey patch ``threading.local`` with something that is greenlet aware.
    Since greenlets cannot cross threads, so this should be semantically
    identical to ``threadlocal.local``
    """
    from eventlet import api
    from eventlet.corolocal import local
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
            descriptor.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) | 1)
    except socket.error:
        pass

