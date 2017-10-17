import sys
from eventlet import patcher
from eventlet.green import ftplib
from eventlet.green import httplib
from eventlet.green import socket
from eventlet.green import ssl
from eventlet.green import time
from eventlet.green import urllib

_canonical_name = 'urllib2'
patcher.inject(
    _canonical_name,
    globals(),
    ('httplib', httplib),
    ('socket', socket),
    ('ssl', ssl),
    ('time', time),
    ('urllib', urllib))

FTPHandler.ftp_open = patcher.patch_function(FTPHandler.ftp_open, ('ftplib', ftplib))

_MISSING = object()
module_imported = sys.modules.get(_canonical_name, patcher.original(_canonical_name))
_current_module = sys.modules[__name__]
_keep_names = (
    'URLError',
    'HTTPError',
)
for k in _keep_names:
    v = getattr(module_imported, k, _MISSING)
    if v is not _MISSING:
        setattr(_current_module, k, v)
del _canonical_name, _current_module, _keep_names, k, v, module_imported, patcher, sys
