__ssl = __import__('ssl')

for attr in dir(__ssl):
    exec "%s = __ssl.%s" % (attr, attr)

import errno
import time

from eventlet.api import trampoline, getcurrent
from thread import get_ident
from eventlet.greenio import set_nonblocking, GreenSocket, SOCKET_CLOSED, CONNECT_ERR, CONNECT_SUCCESS
orig_socket = __import__('socket')
socket = orig_socket.socket


class GreenSSLSocket(__ssl.SSLSocket):
    """ This is a green version of the SSLSocket class from the ssl module added 
    in 2.6.  For documentation on it, please see the Python standard
    documentation."""
    # we are inheriting from SSLSocket because its constructor calls 
    # do_handshake whose behavior we wish to override
    def __init__(self, sock, *args, **kw):
        if not isinstance(sock, GreenSocket):
            sock = GreenSocket(sock)

        self.act_non_blocking = sock.act_non_blocking
        self.timeout = sock.timeout
        super(GreenSSLSocket, self).__init__(sock.fd, *args, **kw)
        del sock
        
        # the superclass initializer trashes the methods so...
        self.send = lambda data, flags=0: GreenSSLSocket.send(self, data, flags)
        self.sendto = lambda data, addr, flags=0: GreenSSLSocket.sendto(self, data, addr, flags)
        self.recv = lambda buflen=1024, flags=0: GreenSSLSocket.recv(self, buflen, flags)
        self.recvfrom = lambda addr, buflen=1024, flags=0: GreenSSLSocket.recvfrom(self, addr, buflen, flags)
        self.recv_into = lambda buffer, nbytes=None, flags=0: GreenSSLSocket.recv_into(self, buffer, nbytes, flags)
        self.recvfrom_into = lambda buffer, nbytes=None, flags=0: GreenSSLSocket.recvfrom_into(self, buffer, nbytes, flags)
        
    def settimeout(self, timeout):
        self.timeout = timeout
        
    def gettimeout(self):
        return self.timeout
    
    setblocking = GreenSocket.setblocking

    def _call_trampolining(self, func, *a, **kw):
        if self.act_non_blocking:
            return func(*a, **kw)
        else:
            while True:
                try:
                    return func(*a, **kw)
                except SSLError, exc:
                    if exc[0] == SSL_ERROR_WANT_READ:
                        trampoline(self.fileno(), 
                                   read=True, 
                                   timeout=self.gettimeout(), 
                                   timeout_exc=SSLError)
                    elif exc[0] == SSL_ERROR_WANT_WRITE:
                        trampoline(self.fileno(), 
                                   write=True, 
                                   timeout=self.gettimeout(), 
                                   timeout_exc=SSLError)
                    else:
                        raise

        
    def write(self, data):
        """Write DATA to the underlying SSL channel.  Returns
        number of bytes of DATA actually transmitted."""
        return self._call_trampolining(
            super(GreenSSLSocket, self).write, data)

    def read(self, len=1024):
        """Read up to LEN bytes and return them.
        Return zero-length string on EOF."""
        return self._call_trampolining(
            super(GreenSSLSocket, self).read,len)

    def send (self, data, flags=0):
        # *NOTE: gross, copied code from ssl.py becase it's not factored well enough to be used as-is
        if self._sslobj:
            if flags != 0:
                raise ValueError(
                    "non-zero flags not allowed in calls to send() on %s" %
                    self.__class__)
            while True:
                try:
                    v = self._sslobj.write(data)
                except SSLError, x:
                    if x.args[0] == SSL_ERROR_WANT_READ:
                        return 0
                    elif x.args[0] == SSL_ERROR_WANT_WRITE:
                        return 0
                    else:
                        raise
                else:
                    return v
        else:
            while True:
                try:
                    return socket.send(self, data, flags)
                except orig_socket.error, e:
                    if self.act_non_blocking:
                        raise
                    if e[0] == errno.EWOULDBLOCK or \
                       e[0] == errno.ENOTCONN:
                        return 0
                    raise

    def sendto (self, data, addr, flags=0):
        # *NOTE: gross, copied code from ssl.py becase it's not factored well enough to be used as-is
        if self._sslobj:
            raise ValueError("sendto not allowed on instances of %s" %
                             self.__class__)
        else:
            trampoline(self.fileno(), write=True, timeout_exc=orig_socket.timeout)
            return socket.sendto(self, data, addr, flags)

    def sendall (self, data, flags=0):
        # *NOTE: gross, copied code from ssl.py becase it's not factored well enough to be used as-is
        if self._sslobj:
            if flags != 0:
                raise ValueError(
                    "non-zero flags not allowed in calls to sendall() on %s" %
                    self.__class__)
            amount = len(data)
            count = 0
            while (count < amount):
                v = self.send(data[count:])
                count += v
            return amount
        else:
            while True:
                try:
                    return socket.sendall(self, buflen, flags)
                except orig_socket.error, e:
                    if self.act_non_blocking:
                        raise
                    if e[0] == errno.EWOULDBLOCK:
                        trampoline(self.fileno(), write=True, 
                                   timeout=self.gettimeout(), timeout_exc=orig_socket.timeout)
                    if e[0] in SOCKET_CLOSED:
                        return ''
                    raise

    def recv(self, buflen=1024, flags=0):
        # *NOTE: gross, copied code from ssl.py becase it's not factored well enough to be used as-is
        if self._sslobj:
            if flags != 0:
                raise ValueError(
                    "non-zero flags not allowed in calls to recv() on %s" %
                    self.__class__)
            read = self.read(buflen)
            return read
        else:
            while True:
                try:
                    return socket.recv(self, buflen, flags)
                except orig_socket.error, e:
                    if self.act_non_blocking:
                        raise
                    if e[0] == errno.EWOULDBLOCK:
                        trampoline(self.fileno(), read=True, 
                                   timeout=self.gettimeout(), timeout_exc=orig_socket.timeout)
                    if e[0] in SOCKET_CLOSED:
                        return ''
                    raise

        
    def recv_into (self, buffer, nbytes=None, flags=0):
        if not self.act_non_blocking:
            trampoline(self.fileno(), read=True, timeout=self.gettimeout(), timeout_exc=orig_socket.timeout)
        return super(GreenSSLSocket, self).recv_into(buffer, nbytes, flags)

    def recvfrom (self, addr, buflen=1024, flags=0):
        if not self.act_non_blocking:
            trampoline(self.fileno(), read=True, timeout=self.gettimeout(), timeout_exc=orig_socket.timeout)
        return super(GreenSSLSocket, self).recvfrom(addr, buflen, flags)
        
    def recvfrom_into (self, buffer, nbytes=None, flags=0):
        if not self.act_non_blocking:
            trampoline(self.fileno(), read=True, timeout=self.gettimeout(), timeout_exc=orig_socket.timeout)
        return super(GreenSSLSocket, self).recvfrom_into(buffer, nbytes, flags)

    def unwrap(self):
        return GreenSocket(super(GreenSSLSocket, self).unwrap())

    def do_handshake(self):    
        """Perform a TLS/SSL handshake."""
        return self._call_trampolining(
            super(GreenSSLSocket, self).do_handshake)

    def _socket_connect(self, addr):
        real_connect = socket.connect
        if self.act_non_blocking:
            return real_connect(self, addr)
        else:
            # *NOTE: gross, copied code from greenio because it's not factored
            # well enough to reuse
            if self.gettimeout() is None:
                while True:
                    try:
                        return real_connect(self, addr)
                    except orig_socket.error, exc:
                        if exc[0] in CONNECT_ERR:
                            trampoline(self.fileno(), write=True)
                        elif exc[0] in CONNECT_SUCCESS:
                            return
                        else:
                            raise
            else:
                end = time.time() + self.gettimeout()
                while True:
                    try:
                        real_connect(self, addr)
                    except orig_socket.error, exc:
                        if exc[0] in CONNECT_ERR:
                            trampoline(self.fileno(), write=True, 
                                       timeout=end-time.time(), timeout_exc=orig_socket.timeout)
                        elif exc[0] in CONNECT_SUCCESS:
                            return
                        else:
                            raise
                    if time.time() >= end:
                        raise orig_socket.timeout
    

    def connect(self, addr):
        """Connects to remote ADDR, and then wraps the connection in
        an SSL channel."""
        # *NOTE: grrrrr copied this code from ssl.py because of the reference
        # to socket.connect which we don't want to call directly
        if self._sslobj:
            raise ValueError("attempt to connect already-connected SSLSocket!")
        self._socket_connect(addr)
        self._sslobj = _ssl.sslwrap(self._sock, False, self.keyfile, self.certfile,
                                    self.cert_reqs, self.ssl_version,
                                    self.ca_certs)
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
                except orig_socket.error, e:
                    if e[0] != errno.EWOULDBLOCK:
                        raise
                    trampoline(self.fileno(), read=True, timeout=self.gettimeout(),
                                   timeout_exc=orig_socket.timeout)

        new_ssl = type(self)(newsock,
                          keyfile=self.keyfile,
                          certfile=self.certfile,
                          server_side=True,
                          cert_reqs=self.cert_reqs,
                          ssl_version=self.ssl_version,
                          ca_certs=self.ca_certs,
                          do_handshake_on_connect=self.do_handshake_on_connect,
                          suppress_ragged_eofs=self.suppress_ragged_eofs)
        return (new_ssl, addr)

                               
SSLSocket = GreenSSLSocket

def wrap_socket(sock, keyfile=None, certfile=None,
                server_side=False, cert_reqs=CERT_NONE,
                ssl_version=PROTOCOL_SSLv23, ca_certs=None,
                do_handshake_on_connect=True,
                suppress_ragged_eofs=True):
    return GreenSSLSocket(sock, keyfile=keyfile, certfile=certfile,
                     server_side=server_side, cert_reqs=cert_reqs,
                     ssl_version=ssl_version, ca_certs=ca_certs,
                     do_handshake_on_connect=do_handshake_on_connect,
                     suppress_ragged_eofs=suppress_ragged_eofs)


def sslwrap_simple(sock, keyfile=None, certfile=None):
    """A replacement for the old socket.ssl function.  Designed
    for compability with Python 2.5 and earlier.  Will disappear in
    Python 3.0."""
    ssl_sock = GreenSSLSocket(sock, 0, keyfile, certfile, CERT_NONE,
                              PROTOCOL_SSLv23, None)
    return ssl_sock
