import os
import sys
from eventlet.hubs import get_hub
__import__('eventlet.green._socket_nodns')
__socket = sys.modules['eventlet.green._socket_nodns']
globals().update(dict([(var, getattr(__socket, var))
                       for var in dir(__socket)
                       if not var.startswith('__')]))

__all__     = __socket.__all__
__patched__ = __socket.__patched__ + ['gethostbyname', 'getaddrinfo', 'create_connection',]


greendns = None
if os.environ.get("EVENTLET_NO_GREENDNS",'').lower() != "yes":
    try:
        from eventlet.support import greendns
    except ImportError, ex:
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
elif greendns:
    gethostbyname = greendns.gethostbyname
elif _can_use_tpool:
    gethostbyname = _gethostbyname_tpool
else:
    gethostbyname = __original_gethostbyname__


__original_getaddrinfo__ = __socket.getaddrinfo
def _getaddrinfo_tpool(*args, **kw):
    from eventlet import tpool
    return tpool.execute(
        __original_getaddrinfo__, *args, **kw)

if greendns:
    getaddrinfo = greendns.getaddrinfo
elif _can_use_tpool:
    getaddrinfo = _getaddrinfo_tpool
else:
    getaddrinfo = __original_getaddrinfo__

if greendns:
    gethostbyname_ex = greendns.gethostbyname_ex
    getnameinfo = greendns.getnameinfo
    __patched__ = __patched__ + ['gethostbyname_ex', 'getnameinfo']

def create_connection(address, 
                      timeout=_GLOBAL_DEFAULT_TIMEOUT, 
                      source_address=None):
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
            if source_address:
                sock.bind(source_address)
            sock.connect(sa)
            return sock

        except error, msg:
            if sock is not None:
                sock.close()

    raise error, msg


