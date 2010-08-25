import os
import sys
from eventlet.hubs import get_hub
__import__('eventlet.green._socket_nodns')
__socket = sys.modules['eventlet.green._socket_nodns']
globals().update(dict([(var, getattr(__socket, var))
                       for var in dir(__socket) 
                       if not var.startswith('__')]))
               
__all__     = __socket.__all__
__patched__ = __socket.__patched__ + ['gethostbyname', 'getaddrinfo']


greendns = None
if os.environ.get("EVENTLET_NO_GREENDNS",'').lower() != "yes":
    try:
        from eventlet.support import greendns
    except ImportError:
        pass

if greendns:
    gethostbyname = greendns.gethostbyname
    getaddrinfo = greendns.getaddrinfo
    gethostbyname_ex = greendns.gethostbyname_ex
    getnameinfo = greendns.getnameinfo
    __patched__ + ['gethostbyname_ex', 'getnameinfo']


