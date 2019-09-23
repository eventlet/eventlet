__ssl = __import__('ssl')

from eventlet.patcher import slurp_properties
slurp_properties(__ssl, globals(), srckeys=dir(__ssl))

import sys
from eventlet import greenio, hubs
from eventlet.greenio import (
    set_nonblocking, GreenSocket, CONNECT_ERR, CONNECT_SUCCESS,
)
from eventlet.hubs import trampoline, IOClosed
from eventlet.support import get_errno, PY33
import six
from contextlib import contextmanager

orig_socket = __import__('socket')
socket = orig_socket.socket
timeout_exc = SSLError

__patched__ = [
    'SSLSocket', 'SSLContext', 'wrap_socket', 'sslwrap_simple',
    'create_default_context', '_create_default_https_context']

_original_sslsocket = __ssl.SSLSocket
_original_wrap_socket = __ssl.wrap_socket
_original_sslcontext = getattr(__ssl, 'SSLContext', None)
_is_under_py_3_7 = sys.version_info < (3, 7)


@contextmanager
def _original_ssl_context(*args, **kwargs):
    tmp_sslcontext = _original_wrap_socket.__globals__.get('SSLContext', None)
    tmp_sslsocket = _original_sslsocket._create.__globals__.get('SSLSocket', None)
    _original_sslsocket._create.__globals__['SSLSocket'] = _original_sslsocket
    _original_wrap_socket.__globals__['SSLContext'] = _original_sslcontext
    try:
        yield
    finally:
        _original_wrap_socket.__globals__['SSLContext'] = tmp_sslcontext
        _original_sslsocket._create.__globals__['SSLSocket'] = tmp_sslsocket


class GreenSSLSocket(_original_sslsocket):
    """ This is a green version of the SSLSocket class from the ssl module added
    in 2.6.  For documentation on it, please see the Python standard
    documentation.

    Python nonblocking ssl objects don't give errors when the other end
    of the socket is closed (they do notice when the other end is shutdown,
    though).  Any write/read operations will simply hang if the socket is
    closed from the other end.  There is no obvious fix for this problem;
    it appears to be a limitation of Python's ssl object implementation.
    A workaround is to set a reasonable timeout on the socket using
    settimeout(), and to close/reopen the connection when a timeout
    occurs at an unexpected juncture in the code.
    """
    if _is_under_py_3_7:
        # Issue #526: In Python 3.7, SSLSocket._create() instantiates
        # GreenSSLContext.sslsocket_class -- in other words, this class,
        # GreenSSLSocket -- by calling its __new__() and then SSLSocket's base
        # class (socket's) __init__(), passing only family, type, proto and
        # fileno. Importantly, it lets sock default to None! SSLSocket does not
        # override the default object.__new__() Try not overriding it in this
        # class either.
        def __new__(cls, sock=None, keyfile=None, certfile=None,
                    server_side=False, cert_reqs=CERT_NONE,
                    ssl_version=PROTOCOL_SSLv23, ca_certs=None,
                    do_handshake_on_connect=True, *args, **kw):
            return super(GreenSSLSocket, cls).__new__(cls)

    else:
        # The following override is cloned-and-edited from Python 3.7.4's
        # ssl.SSLSocket._create() method. This is admittedly vulnerable to any
        # future upstream maintenance to SSLSocket._create(), or indeed any
        # SSLSocket method that interacts with instance creation. Better
        # solutions are invited!!
        @classmethod
        def _create(cls, sock, server_side=False, do_handshake_on_connect=True,
                    suppress_ragged_eofs=True, server_hostname=None,
                    context=None, session=None):
            if sock.getsockopt(SOL_SOCKET, SO_TYPE) != SOCK_STREAM:
                raise NotImplementedError("only stream sockets are supported")
            if server_side:
                if server_hostname:
                    raise ValueError("server_hostname can only be specified "
                                     "in client mode")
                if session is not None:
                    raise ValueError("session can only be specified in "
                                     "client mode")
            if context.check_hostname and not server_hostname:
                raise ValueError("check_hostname requires server_hostname")

            kwargs = dict(
                family=sock.family, type=sock.type, proto=sock.proto,
                fileno=sock.fileno()
            )
            self = cls.__new__(cls, **kwargs)
            ##################
            # This diverges from ssl.SSLSocket._create(), which calls
            # super(SSLSocket, self).__init__(**kwargs). For reasons we don't
            # understand, without this override, that call reaches
            # SSLSocket.__init__(), which unconditionally raises TypeError
            # because you're supposed to use wrap_socket() instead of directly
            # constructing SSLSocket. Since SSLSocket is derived from socket,
            # super(SSLSocket, self).__init__ is intended to reference
            # socket.__init__. Use an old-style base-class call instead.
            socket.__init__(self, **kwargs)
            # copied from __init__() below
            self.act_non_blocking = sock.act_non_blocking
            ##################
            self.settimeout(sock.gettimeout())
            sock.detach()

            self._context = context
            self._session = session
            self._closed = False
            self._sslobj = None
            self.server_side = server_side
            self.server_hostname = context._encode_hostname(server_hostname)
            self.do_handshake_on_connect = do_handshake_on_connect
            self.suppress_ragged_eofs = suppress_ragged_eofs

            # See if we are connected
            try:
                self.getpeername()
            except OSError as e:
                if e.errno != errno.ENOTCONN:
                    raise
                connected = False
            else:
                connected = True

            self._connected = connected
            if connected:
                # create the SSL object
                try:
                    self._sslobj = self._context._wrap_socket(
                        self, server_side, self.server_hostname,
                        owner=self, session=self._session,
                    )
                    if do_handshake_on_connect:
                        timeout = self.gettimeout()
                        if timeout == 0.0:
                            # non-blocking
                            raise ValueError("do_handshake_on_connect should not be specified for non-blocking sockets")
                        self.do_handshake()
                except (OSError, ValueError):
                    self.close()
                    raise
            return self

    # we are inheriting from SSLSocket because its constructor calls
    # do_handshake whose behavior we wish to override
    def __init__(self, sock, keyfile=None, certfile=None,
                 server_side=False, cert_reqs=CERT_NONE,
                 ssl_version=PROTOCOL_SSLv23, ca_certs=None,
                 do_handshake_on_connect=True, *args, **kw):
        if not isinstance(sock, GreenSocket):
            sock = GreenSocket(sock)
        self.act_non_blocking = sock.act_non_blocking

        if six.PY2:
            # On Python 2 SSLSocket constructor queries the timeout, it'd break without
            # this assignment
            self._timeout = sock.gettimeout()

        if _is_under_py_3_7:
            # nonblocking socket handshaking on connect got disabled so let's pretend it's disabled
            # even when it's on
            super(GreenSSLSocket, self).__init__(
                sock.fd, keyfile, certfile, server_side, cert_reqs, ssl_version,
                ca_certs, do_handshake_on_connect and six.PY2, *args, **kw)
        # the superclass initializer trashes the methods so we remove
        # the local-object versions of them and let the actual class
        # methods shine through
        # Note: This for Python 2
        try:
            for fn in orig_socket._delegate_methods:
                delattr(self, fn)
        except AttributeError:
            pass

        if six.PY3:
            # Python 3 SSLSocket construction process overwrites the timeout so restore it
            self._timeout = sock.gettimeout()

            # it also sets timeout to None internally apparently (tested with 3.4.2)
            _original_sslsocket.settimeout(self, 0.0)
            assert _original_sslsocket.gettimeout(self) == 0.0

            # see note above about handshaking
            self.do_handshake_on_connect = do_handshake_on_connect
            if do_handshake_on_connect and self._connected:
                self.do_handshake()

    def settimeout(self, timeout):
        self._timeout = timeout

    def gettimeout(self):
        return self._timeout

    def setblocking(self, flag):
        if flag:
            self.act_non_blocking = False
            self._timeout = None
        else:
            self.act_non_blocking = True
            self._timeout = 0.0

    def _call_trampolining(self, func, *a, **kw):
        if self.act_non_blocking:
            return func(*a, **kw)
        else:
            while True:
                try:
                    return func(*a, **kw)
                except SSLError as exc:
                    if get_errno(exc) == SSL_ERROR_WANT_READ:
                        trampoline(self,
                                   read=True,
                                   timeout=self.gettimeout(),
                                   timeout_exc=timeout_exc('timed out'))
                    elif get_errno(exc) == SSL_ERROR_WANT_WRITE:
                        trampoline(self,
                                   write=True,
                                   timeout=self.gettimeout(),
                                   timeout_exc=timeout_exc('timed out'))
                    else:
                        raise

    def write(self, data):
        """Write DATA to the underlying SSL channel.  Returns
        number of bytes of DATA actually transmitted."""
        return self._call_trampolining(
            super(GreenSSLSocket, self).write, data)

    def read(self, *args, **kwargs):
        """Read up to LEN bytes and return them.
        Return zero-length string on EOF."""
        try:
            return self._call_trampolining(
                super(GreenSSLSocket, self).read, *args, **kwargs)
        except IOClosed:
            return b''

    def send(self, data, flags=0):
        if self._sslobj:
            return self._call_trampolining(
                super(GreenSSLSocket, self).send, data, flags)
        else:
            trampoline(self, write=True, timeout_exc=timeout_exc('timed out'))
            return socket.send(self, data, flags)

    def sendto(self, data, addr, flags=0):
        # *NOTE: gross, copied code from ssl.py becase it's not factored well enough to be used as-is
        if self._sslobj:
            raise ValueError("sendto not allowed on instances of %s" %
                             self.__class__)
        else:
            trampoline(self, write=True, timeout_exc=timeout_exc('timed out'))
            return socket.sendto(self, data, addr, flags)

    def sendall(self, data, flags=0):
        # *NOTE: gross, copied code from ssl.py becase it's not factored well enough to be used as-is
        if self._sslobj:
            if flags != 0:
                raise ValueError(
                    "non-zero flags not allowed in calls to sendall() on %s" %
                    self.__class__)
            amount = len(data)
            count = 0
            data_to_send = data
            while (count < amount):
                v = self.send(data_to_send)
                count += v
                if v == 0:
                    trampoline(self, write=True, timeout_exc=timeout_exc('timed out'))
                else:
                    data_to_send = data[count:]
            return amount
        else:
            while True:
                try:
                    return socket.sendall(self, data, flags)
                except orig_socket.error as e:
                    if self.act_non_blocking:
                        raise
                    erno = get_errno(e)
                    if erno in greenio.SOCKET_BLOCKING:
                        trampoline(self, write=True,
                                   timeout=self.gettimeout(), timeout_exc=timeout_exc('timed out'))
                    elif erno in greenio.SOCKET_CLOSED:
                        return ''
                    raise

    def recv(self, buflen=1024, flags=0):
        return self._base_recv(buflen, flags, into=False)

    def recv_into(self, buffer, nbytes=None, flags=0):
        # Copied verbatim from CPython
        if buffer and nbytes is None:
            nbytes = len(buffer)
        elif nbytes is None:
            nbytes = 1024
        # end of CPython code

        return self._base_recv(nbytes, flags, into=True, buffer_=buffer)

    def _base_recv(self, nbytes, flags, into, buffer_=None):
        if into:
            plain_socket_function = socket.recv_into
        else:
            plain_socket_function = socket.recv

        # *NOTE: gross, copied code from ssl.py becase it's not factored well enough to be used as-is
        if self._sslobj:
            if flags != 0:
                raise ValueError(
                    "non-zero flags not allowed in calls to %s() on %s" %
                    plain_socket_function.__name__, self.__class__)
            if into:
                read = self.read(nbytes, buffer_)
            else:
                read = self.read(nbytes)
            return read
        else:
            while True:
                try:
                    args = [self, nbytes, flags]
                    if into:
                        args.insert(1, buffer_)
                    return plain_socket_function(*args)
                except orig_socket.error as e:
                    if self.act_non_blocking:
                        raise
                    erno = get_errno(e)
                    if erno in greenio.SOCKET_BLOCKING:
                        try:
                            trampoline(
                                self, read=True,
                                timeout=self.gettimeout(), timeout_exc=timeout_exc('timed out'))
                        except IOClosed:
                            return b''
                    elif erno in greenio.SOCKET_CLOSED:
                        return b''
                    raise

    def recvfrom(self, addr, buflen=1024, flags=0):
        if not self.act_non_blocking:
            trampoline(self, read=True, timeout=self.gettimeout(),
                       timeout_exc=timeout_exc('timed out'))
        return super(GreenSSLSocket, self).recvfrom(addr, buflen, flags)

    def recvfrom_into(self, buffer, nbytes=None, flags=0):
        if not self.act_non_blocking:
            trampoline(self, read=True, timeout=self.gettimeout(),
                       timeout_exc=timeout_exc('timed out'))
        return super(GreenSSLSocket, self).recvfrom_into(buffer, nbytes, flags)

    def unwrap(self):
        return GreenSocket(self._call_trampolining(
            super(GreenSSLSocket, self).unwrap))

    def do_handshake(self):
        """Perform a TLS/SSL handshake."""
        return self._call_trampolining(
            super(GreenSSLSocket, self).do_handshake)

    def _socket_connect(self, addr):
        real_connect = socket.connect
        if self.act_non_blocking:
            return real_connect(self, addr)
        else:
            clock = hubs.get_hub().clock
            # *NOTE: gross, copied code from greenio because it's not factored
            # well enough to reuse
            if self.gettimeout() is None:
                while True:
                    try:
                        return real_connect(self, addr)
                    except orig_socket.error as exc:
                        if get_errno(exc) in CONNECT_ERR:
                            trampoline(self, write=True)
                        elif get_errno(exc) in CONNECT_SUCCESS:
                            return
                        else:
                            raise
            else:
                end = clock() + self.gettimeout()
                while True:
                    try:
                        real_connect(self, addr)
                    except orig_socket.error as exc:
                        if get_errno(exc) in CONNECT_ERR:
                            trampoline(
                                self, write=True,
                                timeout=end - clock(), timeout_exc=timeout_exc('timed out'))
                        elif get_errno(exc) in CONNECT_SUCCESS:
                            return
                        else:
                            raise
                    if clock() >= end:
                        raise timeout_exc('timed out')

    def connect(self, addr):
        """Connects to remote ADDR, and then wraps the connection in
        an SSL channel."""
        # *NOTE: grrrrr copied this code from ssl.py because of the reference
        # to socket.connect which we don't want to call directly
        if self._sslobj:
            raise ValueError("attempt to connect already-connected SSLSocket!")
        self._socket_connect(addr)
        server_side = False
        try:
            sslwrap = _ssl.sslwrap
        except AttributeError:
            # sslwrap was removed in 3.x and later in 2.7.9
            if six.PY2:
                sslobj = self._context._wrap_socket(self._sock, server_side, ssl_sock=self)
            else:
                context = self.context if PY33 else self._context
                sslobj = context._wrap_socket(self, server_side)
        else:
            sslobj = sslwrap(self._sock, server_side, self.keyfile, self.certfile,
                             self.cert_reqs, self.ssl_version,
                             self.ca_certs, *self.ciphers)

        try:
            # This is added in Python 3.5, http://bugs.python.org/issue21965
            SSLObject
        except NameError:
            self._sslobj = sslobj
        else:
            if _is_under_py_3_7:
                self._sslobj = SSLObject(sslobj, owner=self)
            else:
                self._sslobj = sslobj

        if self.do_handshake_on_connect:
            self.do_handshake()

    def accept(self):
        """Accepts a new connection from a remote client, and returns
        a tuple containing that new connection wrapped with a server-side
        SSL channel, and the address of the remote client."""
        # RDW grr duplication of code from greenio
        if self.act_non_blocking:
            newsock, addr = socket.accept(self)
        else:
            while True:
                try:
                    newsock, addr = socket.accept(self)
                    set_nonblocking(newsock)
                    break
                except orig_socket.error as e:
                    if get_errno(e) not in greenio.SOCKET_BLOCKING:
                        raise
                    trampoline(self, read=True, timeout=self.gettimeout(),
                               timeout_exc=timeout_exc('timed out'))

        new_ssl = type(self)(
            newsock,
            keyfile=self.keyfile,
            certfile=self.certfile,
            server_side=True,
            cert_reqs=self.cert_reqs,
            ssl_version=self.ssl_version,
            ca_certs=self.ca_certs,
            do_handshake_on_connect=False,
            suppress_ragged_eofs=self.suppress_ragged_eofs)
        return (new_ssl, addr)

    def dup(self):
        raise NotImplementedError("Can't dup an ssl object")


SSLSocket = GreenSSLSocket


def wrap_socket(sock, *a, **kw):
    return GreenSSLSocket(sock, *a, **kw)


if hasattr(__ssl, 'sslwrap_simple'):
    def sslwrap_simple(sock, keyfile=None, certfile=None):
        """A replacement for the old socket.ssl function.  Designed
        for compatibility with Python 2.5 and earlier.  Will disappear in
        Python 3.0."""
        ssl_sock = GreenSSLSocket(sock, keyfile=keyfile, certfile=certfile,
                                  server_side=False,
                                  cert_reqs=CERT_NONE,
                                  ssl_version=PROTOCOL_SSLv23,
                                  ca_certs=None)
        return ssl_sock


if hasattr(__ssl, 'SSLContext'):
    _original_sslcontext = __ssl.SSLContext

    class GreenSSLContext(_original_sslcontext):
        __slots__ = ()

        # As of Python 3.7, SSLContext.wrap_socket() instantiates its
        # sslsocket_class instead of hard-coding SSLSocket. Set that
        # unconditionally; it's ineffective but harmless for older versions.
        sslsocket_class = GreenSSLSocket

        if _is_under_py_3_7:
            # Because of the above, only override SSLContext.wrap_socket() for
            # older versions.
            def wrap_socket(self, sock, *a, **kw):
                # Issue https://github.com/eventlet/eventlet/issues/526:
                # Python 3.7's ssl.wrap_socket() no longer has a _context param.
                return GreenSSLSocket(sock, *a, _context=self, **kw)

        # https://github.com/eventlet/eventlet/issues/371
        # Thanks to Gevent developers for sharing patch to this problem.
        if hasattr(_original_sslcontext.options, 'setter'):
            # In 3.6, these became properties. They want to access the
            # property __set__ method in the superclass, and they do so by using
            # super(SSLContext, SSLContext). But we rebind SSLContext when we monkey
            # patch, which causes infinite recursion.
            # https://github.com/python/cpython/commit/328067c468f82e4ec1b5c510a4e84509e010f296
            @_original_sslcontext.options.setter
            def options(self, value):
                super(_original_sslcontext, _original_sslcontext).options.__set__(self, value)

            @_original_sslcontext.verify_flags.setter
            def verify_flags(self, value):
                super(_original_sslcontext, _original_sslcontext).verify_flags.__set__(self, value)

            @_original_sslcontext.verify_mode.setter
            def verify_mode(self, value):
                super(_original_sslcontext, _original_sslcontext).verify_mode.__set__(self, value)

    SSLContext = GreenSSLContext

    if hasattr(__ssl, 'create_default_context'):
        _original_create_default_context = __ssl.create_default_context

        def green_create_default_context(*a, **kw):
            # We can't just monkey-patch on the green version of `wrap_socket`
            # on to SSLContext instances, but SSLContext.create_default_context
            # does a bunch of work. Rather than re-implementing it all, just
            # switch out the __class__ to get our `wrap_socket` implementation
            context = _original_create_default_context(*a, **kw)
            context.__class__ = GreenSSLContext
            return context

        create_default_context = green_create_default_context
        _create_default_https_context = green_create_default_context
