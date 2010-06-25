import os
import sys
from eventlet.hubs import get_hub
__import__('eventlet.green._socket_nodns')
__socket = sys.modules['eventlet.green._socket_nodns']
for var in __socket.__all__:
    exec "%s = __socket.%s" % (var, var)
# these are desired but are not in __all__
_GLOBAL_DEFAULT_TIMEOUT = __socket._GLOBAL_DEFAULT_TIMEOUT
_fileobject = __socket._fileobject
try:
    ssl = __socket.ssl
except AttributeError:
    pass
__all__     = __socket.__all__
__patched__ = __socket.__patched__ + ['gethostbyname', 'getaddrinfo']


greendns = None
if os.environ.get("EVENTLET_NO_GREENDNS",'').lower() != "yes":
    try:
        from eventlet.support import greendns
    except ImportError:
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
    __patched__ + ['gethostbyname_ex', 'getnameinfo']


