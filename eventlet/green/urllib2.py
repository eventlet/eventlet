urllib2 = __import__('urllib2')
for var in dir(urllib2):
    exec "%s = urllib2.%s" % (var, var)

# import the following to be a better drop-in replacement
__import_lst = ['__version__', '__cut_port_re', '_parse_proxy']

for var in __import_lst:
    exec "%s = getattr(urllib2, %r, None)" % (var, var)

for x in ('urlopen', 'install_opener', 'build_opener', 'HTTPHandler', 'HTTPSHandler',
          'HTTPCookieProcessor', 'FileHandler', 'FTPHandler', 'CacheFTPHandler', 'GopherError'):
    globals().pop(x, None)

from eventlet.green import httplib
import mimetools
import os
from eventlet.green import socket
import sys
from eventlet.green import time

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from eventlet.green.urllib import (unwrap, unquote, splittype, splithost, quote,
     addinfourl, splitport, splitquery,
     splitattr, ftpwrapper, noheaders, splituser, splitpasswd, splitvalue)

# support for FileHandler, proxies via environment variables
from eventlet.green.urllib import localhost, url2pathname, getproxies

_opener = None
def urlopen(url, data=None):
    global _opener
    if _opener is None:
        _opener = build_opener()
    return _opener.open(url, data)

def install_opener(opener):
    global _opener
    _opener = opener

def build_opener(*handlers):
    import types
    def isclass(obj):
        return isinstance(obj, types.ClassType) or hasattr(obj, "__bases__")

    opener = OpenerDirector()
    default_classes = [ProxyHandler, UnknownHandler, HTTPHandler,
                       HTTPDefaultErrorHandler, HTTPRedirectHandler,
                       FTPHandler, FileHandler, HTTPErrorProcessor]
    if hasattr(httplib, 'HTTPS'):
        default_classes.append(HTTPSHandler)
    skip = set()
    for klass in default_classes:
        for check in handlers:
            if isclass(check):
                if issubclass(check, klass):
                    skip.add(klass)
            elif isinstance(check, klass):
                skip.add(klass)
    for klass in skip:
        default_classes.remove(klass)

    for klass in default_classes:
        opener.add_handler(klass())

    for h in handlers:
        if isclass(h):
            h = h()
        opener.add_handler(h)
    return opener

class HTTPHandler(urllib2.HTTPHandler):

    def http_open(self, req):
        return self.do_open(httplib.HTTPConnection, req)

    http_request = AbstractHTTPHandler.do_request_

if hasattr(urllib2, 'HTTPSHandler'):
    class HTTPSHandler(urllib2.HTTPSHandler):

        def https_open(self, req):
            return self.do_open(httplib.HTTPSConnection, req)

        https_request = AbstractHTTPHandler.do_request_

class HTTPCookieProcessor(urllib2.HTTPCookieProcessor):
    def __init__(self, cookiejar=None):
        from eventlet.green import cookielib
        if cookiejar is None:
            cookiejar = cookielib.CookieJar()
        self.cookiejar = cookiejar

class FileHandler(urllib2.FileHandler):

    def get_names(self):
        if FileHandler.names is None:
            try:
                FileHandler.names = (socket.gethostbyname('localhost'),
                                    socket.gethostbyname(socket.gethostname()))
            except socket.gaierror:
                FileHandler.names = (socket.gethostbyname('localhost'),)
        return FileHandler.names

    def open_local_file(self, req):
        import email.Utils
        import mimetypes
        host = req.get_host()
        file = req.get_selector()
        localfile = url2pathname(file)
        stats = os.stat(localfile)
        size = stats.st_size
        modified = email.Utils.formatdate(stats.st_mtime, usegmt=True)
        mtype = mimetypes.guess_type(file)[0]
        headers = mimetools.Message(StringIO(
            'Content-type: %s\nContent-length: %d\nLast-modified: %s\n' %
            (mtype or 'text/plain', size, modified)))
        if host:
            host, port = splitport(host)
        if not host or \
           (not port and socket.gethostbyname(host) in self.get_names()):
            return addinfourl(open(localfile, 'rb'),
                              headers, 'file:'+file)
        raise URLError('file not on local host')

class FTPHandler(urllib2.FTPHandler):
    def ftp_open(self, req):
        from eventlet.green import ftplib
        import mimetypes
        host = req.get_host()
        if not host:
            raise IOError, ('ftp error', 'no host given')
        host, port = splitport(host)
        if port is None:
            port = ftplib.FTP_PORT
        else:
            port = int(port)

        # username/password handling
        user, host = splituser(host)
        if user:
            user, passwd = splitpasswd(user)
        else:
            passwd = None
        host = unquote(host)
        user = unquote(user or '')
        passwd = unquote(passwd or '')

        try:
            host = socket.gethostbyname(host)
        except socket.error, msg:
            raise URLError(msg)
        path, attrs = splitattr(req.get_selector())
        dirs = path.split('/')
        dirs = map(unquote, dirs)
        dirs, file = dirs[:-1], dirs[-1]
        if dirs and not dirs[0]:
            dirs = dirs[1:]
        try:
            fw = self.connect_ftp(user, passwd, host, port, dirs)
            type = file and 'I' or 'D'
            for attr in attrs:
                attr, value = splitvalue(attr)
                if attr.lower() == 'type' and \
                   value in ('a', 'A', 'i', 'I', 'd', 'D'):
                    type = value.upper()
            fp, retrlen = fw.retrfile(file, type)
            headers = ""
            mtype = mimetypes.guess_type(req.get_full_url())[0]
            if mtype:
                headers += "Content-type: %s\n" % mtype
            if retrlen is not None and retrlen >= 0:
                headers += "Content-length: %d\n" % retrlen
            sf = StringIO(headers)
            headers = mimetools.Message(sf)
            return addinfourl(fp, headers, req.get_full_url())
        except ftplib.all_errors, msg:
            raise IOError, ('ftp error', msg), sys.exc_info()[2]

    def connect_ftp(self, user, passwd, host, port, dirs):
        fw = ftpwrapper(user, passwd, host, port, dirs)
##        fw.ftp.set_debuglevel(1)
        return fw

class CacheFTPHandler(FTPHandler):
    # XXX would be nice to have pluggable cache strategies
    # XXX this stuff is definitely not thread safe
    def __init__(self):
        self.cache = {}
        self.timeout = {}
        self.soonest = 0
        self.delay = 60
        self.max_conns = 16

    def setTimeout(self, t):
        self.delay = t

    def setMaxConns(self, m):
        self.max_conns = m

    def connect_ftp(self, user, passwd, host, port, dirs):
        key = user, host, port, '/'.join(dirs)
        if key in self.cache:
            self.timeout[key] = time.time() + self.delay
        else:
            self.cache[key] = ftpwrapper(user, passwd, host, port, dirs)
            self.timeout[key] = time.time() + self.delay
        self.check_cache()
        return self.cache[key]

    def check_cache(self):
        # first check for old ones
        t = time.time()
        if self.soonest <= t:
            for k, v in self.timeout.items():
                if v < t:
                    self.cache[k].close()
                    del self.cache[k]
                    del self.timeout[k]
        self.soonest = min(self.timeout.values())

        # then check the size
        if len(self.cache) == self.max_conns:
            for k, v in self.timeout.items():
                if v == self.soonest:
                    del self.cache[k]
                    del self.timeout[k]
                    break
            self.soonest = min(self.timeout.values())

class GopherHandler(BaseHandler):
    def gopher_open(self, req):
        # XXX can raise socket.error
        from eventlet.green import gopherlib  # this raises DeprecationWarning in 2.5
        host = req.get_host()
        if not host:
            raise GopherError('no host given')
        host = unquote(host)
        selector = req.get_selector()
        type, selector = splitgophertype(selector)
        selector, query = splitquery(selector)
        selector = unquote(selector)
        if query:
            query = unquote(query)
            fp = gopherlib.send_query(selector, query, host)
        else:
            fp = gopherlib.send_selector(selector, host)
        return addinfourl(fp, noheaders(), req.get_full_url())

