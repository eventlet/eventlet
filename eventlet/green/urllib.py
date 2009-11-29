from eventlet import patcher
from eventlet.green import socket
from eventlet.green import time
from eventlet.green import httplib
from eventlet.green import ftplib

to_patch = [('socket', socket), ('httplib', httplib),
            ('time', time), ('ftplib', ftplib)]
try:
    from eventlet.green import ssl
    to_patch.append(('ssl', ssl))
except ImportError:
    pass
    
patcher.inject('urllib', globals(), *to_patch)

URLopener.open_http = patcher.patch_function(URLopener.open_http, ('httplib', httplib))
if hasattr(URLopener, 'open_https'):
    URLopener.open_https = patcher.patch_function(URLopener.open_https, ('httplib', httplib))

URLopener.open_ftp = patcher.patch_function(URLopener.open_ftp, ('ftplib', ftplib))
ftpwrapper.init = patcher.patch_function(ftpwrapper.init, ('ftplib', ftplib))
ftpwrapper.retrfile = patcher.patch_function(ftpwrapper.retrfile, ('ftplib', ftplib))

del patcher

# Run test program when run as a script
if __name__ == '__main__':
    main()
