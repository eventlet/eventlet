from __future__ import absolute_import
import socket
import socket as __socket
from socket import *
_fileobject = __socket._fileobject

from eventlet.api import get_hub
from eventlet.greenio import GreenSocket as socket, GreenSSL as _GreenSSL

def fromfd(*args):
    return socket(__socket.fromfd(*args))

if type(get_hub()).__name__ == 'TwistedHub':
    from eventlet.twisteds.util import block_on as _block_on
    def gethostbyname(name):
        from twisted.internet import reactor
        return _block_on(reactor.resolve(name))
else:
    from eventlet import tpool
    def gethostbyname(*args, **kw):
        return tpool.execute(
            __socket.gethostbyname, *args, **kw)

    def getaddrinfo(*args, **kw):
        return tpool.execute(
            __socket.getaddrinfo, *args, **kw)

# XXX there're few more blocking functions in socket
# XXX having a hub-independent way to access thread pool would be nice

def socketpair(family=None, type=SOCK_STREAM, proto=0):
    if family is None:
        try:
            family = AF_UNIX
        except AttributeError:
            family = AF_INET

    a, b = __socket.socketpair(family, type, proto)
    return socket(a), socket(b)


_GLOBAL_DEFAULT_TIMEOUT = object()

def create_connection(address, timeout=_GLOBAL_DEFAULT_TIMEOUT):
    """Connect to *address* and return the socket object.

    Convenience function.  Connect to *address* (a 2-tuple ``(host,
    port)``) and return the socket object.  Passing the optional
    *timeout* parameter will set the timeout on the socket instance
    before attempting to connect.  If no *timeout* is supplied, the
    global default timeout setting returned by :func:`getdefaulttimeout`
    is used.
    """

    msg = "getaddrinfo returns an empty list"
    host, port = address
    for res in getaddrinfo(host, port, 0, SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        sock = None
        try:
            sock = socket(af, socktype, proto)
            if timeout is not _GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            sock.connect(sa)
            return sock

        except error, msg:
            if sock is not None:
                sock.close()

    raise error, msg


def ssl(sock, certificate=None, private_key=None):
    from OpenSSL import SSL
    context = SSL.Context(SSL.SSLv23_METHOD)
    if certificate is not None:
        context.use_certificate_file(certificate)
    if private_key is not None:
        context.use_privatekey_file(private_key)
    context.set_verify(SSL.VERIFY_NONE, lambda *x: True)

    ## TODO only do this on client sockets? how?
    connection = SSL.Connection(context, sock)
    connection.set_connect_state()
    return _GreenSSL(connection)
