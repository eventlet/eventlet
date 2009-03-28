__socket = __import__('socket')
for var in __socket.__all__:
    exec "%s = __socket.%s" % (var, var)
_fileobject = __socket._fileobject

from eventlet.api import get_hub
from eventlet.greenio import GreenSocket as socket, GreenSSL as _GreenSSL
from eventlet.greenio import socketpair, fromfd

def fromfd(*args):
    return socket(__socket.fromfd(*args))

def gethostbyname(name):
    if getattr(get_hub(), 'uses_twisted_reactor', None):
        globals()['gethostbyname'] = _gethostbyname_twisted
    else:
        globals()['gethostbyname'] = _gethostbyname_tpool
    return globals()['gethostbyname'](name)

def _gethostbyname_twisted(name):
    from twisted.internet import reactor
    from eventlet.twistedutil import block_on as _block_on
    return _block_on(reactor.resolve(name))

def _gethostbyname_tpool(name):
    from eventlet import tpool
    return tpool.execute(
        __socket.gethostbyname, name)

#     def getaddrinfo(*args, **kw):
#         return tpool.execute(
#             __socket.getaddrinfo, *args, **kw)
# 
# XXX there're few more blocking functions in socket
# XXX having a hub-independent way to access thread pool would be nice


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
