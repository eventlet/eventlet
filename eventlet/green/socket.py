__socket = __import__('socket')
for var in __socket.__all__:
    exec "%s = __socket.%s" % (var, var)

from eventlet.hubs import get_hub
from eventlet.greenio import GreenSocket as socket
from eventlet.greenio import SSL as _SSL  # for exceptions
from eventlet.greenio import _GLOBAL_DEFAULT_TIMEOUT
from eventlet.greenio import _fileobject

os = __import__('os')
import sys
import warnings

__patched__ = ['fromfd', 'socketpair', 'gethostbyname', 'getaddrinfo',
               'create_connection', 'ssl', 'socket']

try:
    __original_fromfd__ = __socket.fromfd
    def fromfd(*args):
        return socket(__original_fromfd__(*args))
except AttributeError:
    pass

try:
    __original_socketpair__ = __socket.socketpair
    def socketpair(*args):
        one, two = __original_socketpair__(*args)
        return socket(one), socket(two)
except AttributeError:
    pass

__original_gethostbyname__ = __socket.gethostbyname
# the thread primitives on Darwin have some bugs that make
# it undesirable to use tpool for hostname lookups
_can_use_tpool = (
    os.environ.get("EVENTLET_TPOOL_DNS",'').lower() == "yes"
    and not sys.platform.startswith('darwin'))
def _gethostbyname_twisted(name):
    from twisted.internet import reactor
    from eventlet.twistedutil import block_on as _block_on
    return _block_on(reactor.resolve(name))

def _gethostbyname_tpool(name):
    from eventlet import tpool
    return tpool.execute(
        __original_gethostbyname__, name)

if getattr(get_hub(), 'uses_twisted_reactor', None):
    gethostbyname = _gethostbyname_twisted
elif _can_use_tpool:
    gethostbyname = _gethostbyname_tpool
else:
    gethostbyname = __original_gethostbyname__


__original_getaddrinfo__ = __socket.getaddrinfo
def _getaddrinfo_tpool(*args, **kw):
    from eventlet import tpool
    return tpool.execute(
        __original_getaddrinfo__, *args, **kw)

if _can_use_tpool:
    getaddrinfo = _getaddrinfo_tpool
else:
    getaddrinfo = __original_getaddrinfo__


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


def _convert_to_sslerror(ex):
    """ Transliterates SSL.SysCallErrors to socket.sslerrors"""
    return sslerror((ex.args[0], ex.args[1]))


class GreenSSLObject(object):
    """ Wrapper object around the SSLObjects returned by socket.ssl, which have a
    slightly different interface from SSL.Connection objects. """
    def __init__(self, green_ssl_obj):
        """ Should only be called by a 'green' socket.ssl """
        self.connection = green_ssl_obj
        try:
            # if it's already connected, do the handshake
            self.connection.getpeername()
        except:
            pass
        else:
            try:
                self.connection.do_handshake()
            except _SSL.SysCallError, e:
                raise _convert_to_sslerror(e)

    def read(self, n=1024):
        """If n is provided, read n bytes from the SSL connection, otherwise read
        until EOF. The return value is a string of the bytes read."""
        try:
            return self.connection.read(n)
        except _SSL.ZeroReturnError:
            return ''
        except _SSL.SysCallError, e:
            raise _convert_to_sslerror(e)

    def write(self, s):
        """Writes the string s to the on the object's SSL connection.
        The return value is the number of bytes written. """
        try:
            return self.connection.write(s)
        except _SSL.SysCallError, e:
            raise _convert_to_sslerror(e)

    def server(self):
        """ Returns a string describing the server's certificate. Useful for debugging
        purposes; do not parse the content of this string because its format can't be
        parsed unambiguously. """
        return str(self.connection.get_peer_certificate().get_subject())

    def issuer(self):
        """Returns a string describing the issuer of the server's certificate. Useful
        for debugging purposes; do not parse the content of this string because its
        format can't be parsed unambiguously."""
        return str(self.connection.get_peer_certificate().get_issuer())


try:
    try:
        # >= Python 2.6
        from eventlet.green import ssl as ssl_module
        sslerror = __socket.sslerror
        __socket.ssl
        def ssl(sock, certificate=None, private_key=None):
            warnings.warn("socket.ssl() is deprecated.  Use ssl.wrap_socket() instead.",
                          DeprecationWarning, stacklevel=2)
            return ssl_module.sslwrap_simple(sock, private_key, certificate)
    except ImportError:
        # <= Python 2.5 compatibility
        sslerror = __socket.sslerror
        __socket.ssl
        def ssl(sock, certificate=None, private_key=None):
            from eventlet import util
            wrapped = util.wrap_ssl(sock, certificate, private_key)
            return GreenSSLObject(wrapped)
except AttributeError:
    # if the real socket module doesn't have the ssl method or sslerror
    # exception, we can't emulate them
    pass
