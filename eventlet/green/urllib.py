urllib = __import__('urllib')
for var in dir(urllib):
    exec "%s = urllib.%s" % (var, var)

# import the following to be a better drop-in replacement
__import_lst = ['__all__', '__version__', 'MAXFTPCACHE', 'ContentTooShortError',
                'ftpcache', '_noheaders', 'noheaders', 'addbase', 'addclosehook',
                'addinfo', 'addinfourl', '_is_unicode', 'toBytes', '_hextochr',
                'always_safe', 'getproxies_environment', 'proxy_bypass']

for var in __import_lst:
    exec "%s = urllib.%s" % (var, var)

from eventlet.green import socket
import os
from eventlet.green import time
import sys
from urlparse import urljoin as basejoin

# Shortcut for basic usage
_urlopener = None
def urlopen(url, data=None, proxies=None):
    """urlopen(url [, data]) -> open file-like object"""
    global _urlopener
    if proxies is not None:
        opener = FancyURLopener(proxies=proxies)
    elif not _urlopener:
        opener = FancyURLopener()
        _urlopener = opener
    else:
        opener = _urlopener
    if data is None:
        return opener.open(url)
    else:
        return opener.open(url, data)
def urlretrieve(url, filename=None, reporthook=None, data=None):
    global _urlopener
    if not _urlopener:
        _urlopener = FancyURLopener()
    return _urlopener.retrieve(url, filename, reporthook, data)
def urlcleanup():
    if _urlopener:
        _urlopener.cleanup()

class URLopener(urllib.URLopener):

    def open_http(self, url, data=None):
        """Use HTTP protocol."""
        from eventlet.green import httplib
        user_passwd = None
        proxy_passwd= None
        if isinstance(url, str):
            host, selector = splithost(url)
            if host:
                user_passwd, host = splituser(host)
                host = unquote(host)
            realhost = host
        else:
            host, selector = url
            # check whether the proxy contains authorization information
            proxy_passwd, host = splituser(host)
            # now we proceed with the url we want to obtain
            urltype, rest = splittype(selector)
            url = rest
            user_passwd = None
            if urltype.lower() != 'http':
                realhost = None
            else:
                realhost, rest = splithost(rest)
                if realhost:
                    user_passwd, realhost = splituser(realhost)
                if user_passwd:
                    selector = "%s://%s%s" % (urltype, realhost, rest)
                if proxy_bypass(realhost):
                    host = realhost

            #print "proxy via http:", host, selector
        if not host: raise IOError, ('http error', 'no host given')

        if proxy_passwd:
            import base64
            proxy_auth = base64.b64encode(proxy_passwd).strip()
        else:
            proxy_auth = None

        if user_passwd:
            import base64
            auth = base64.b64encode(user_passwd).strip()
        else:
            auth = None
        h = httplib.HTTP(host)
        if data is not None:
            h.putrequest('POST', selector)
            h.putheader('Content-Type', 'application/x-www-form-urlencoded')
            h.putheader('Content-Length', '%d' % len(data))
        else:
            h.putrequest('GET', selector)
        if proxy_auth: h.putheader('Proxy-Authorization', 'Basic %s' % proxy_auth)
        if auth: h.putheader('Authorization', 'Basic %s' % auth)
        if realhost: h.putheader('Host', realhost)
        for args in self.addheaders: h.putheader(*args)
        h.endheaders()
        if data is not None:
            h.send(data)
        errcode, errmsg, headers = h.getreply()
        if errcode == -1:
            # something went wrong with the HTTP status line
            raise IOError, ('http protocol error', 0,
                            'got a bad status line', None)
        fp = h.getfile()
        if errcode == 200:
            return addinfourl(fp, headers, "http:" + url)
        else:
            if data is None:
                return self.http_error(url, fp, errcode, errmsg, headers)
            else:
                return self.http_error(url, fp, errcode, errmsg, headers, data)

    if hasattr(socket, "ssl"):
        def open_https(self, url, data=None):
            """Use HTTPS protocol."""
            from eventlet.green import httplib
            user_passwd = None
            proxy_passwd = None
            if isinstance(url, str):
                host, selector = splithost(url)
                if host:
                    user_passwd, host = splituser(host)
                    host = unquote(host)
                realhost = host
            else:
                host, selector = url
                # here, we determine, whether the proxy contains authorization information
                proxy_passwd, host = splituser(host)
                urltype, rest = splittype(selector)
                url = rest
                user_passwd = None
                if urltype.lower() != 'https':
                    realhost = None
                else:
                    realhost, rest = splithost(rest)
                    if realhost:
                        user_passwd, realhost = splituser(realhost)
                    if user_passwd:
                        selector = "%s://%s%s" % (urltype, realhost, rest)
                #print "proxy via https:", host, selector
            if not host: raise IOError, ('https error', 'no host given')
            if proxy_passwd:
                import base64
                proxy_auth = base64.b64encode(proxy_passwd).strip()
            else:
                proxy_auth = None
            if user_passwd:
                import base64
                auth = base64.b64encode(user_passwd).strip()
            else:
                auth = None
            h = httplib.HTTPS(host, 0,
                              key_file=self.key_file,
                              cert_file=self.cert_file)
            if data is not None:
                h.putrequest('POST', selector)
                h.putheader('Content-Type',
                            'application/x-www-form-urlencoded')
                h.putheader('Content-Length', '%d' % len(data))
            else:
                h.putrequest('GET', selector)
            if proxy_auth: h.putheader('Proxy-Authorization', 'Basic %s' % proxy_auth)
            if auth: h.putheader('Authorization', 'Basic %s' % auth)
            if realhost: h.putheader('Host', realhost)
            for args in self.addheaders: h.putheader(*args)
            h.endheaders()
            if data is not None:
                h.send(data)
            errcode, errmsg, headers = h.getreply()
            if errcode == -1:
                # something went wrong with the HTTP status line
                raise IOError, ('http protocol error', 0,
                                'got a bad status line', None)
            fp = h.getfile()
            if errcode == 200:
                return addinfourl(fp, headers, "https:" + url)
            else:
                if data is None:
                    return self.http_error(url, fp, errcode, errmsg, headers)
                else:
                    return self.http_error(url, fp, errcode, errmsg, headers,
                                           data)

    def open_gopher(self, url):
        """Use Gopher protocol."""
        if not isinstance(url, str):
            raise IOError, ('gopher error', 'proxy support for gopher protocol currently not implemented')
        from eventlet.green import gopherlib
        host, selector = splithost(url)
        if not host: raise IOError, ('gopher error', 'no host given')
        host = unquote(host)
        type, selector = splitgophertype(selector)
        selector, query = splitquery(selector)
        selector = unquote(selector)
        if query:
            query = unquote(query)
            fp = gopherlib.send_query(selector, query, host)
        else:
            fp = gopherlib.send_selector(selector, host)
        return addinfourl(fp, noheaders(), "gopher:" + url)

    def open_local_file(self, url):
        """Use local file."""
        import mimetypes, mimetools, email.Utils
        try:
            from cStringIO import StringIO
        except ImportError:
            from StringIO import StringIO
        host, file = splithost(url)
        localname = url2pathname(file)
        try:
            stats = os.stat(localname)
        except OSError, e:
            raise IOError(e.errno, e.strerror, e.filename)
        size = stats.st_size
        modified = email.Utils.formatdate(stats.st_mtime, usegmt=True)
        mtype = mimetypes.guess_type(url)[0]
        headers = mimetools.Message(StringIO(
            'Content-Type: %s\nContent-Length: %d\nLast-modified: %s\n' %
            (mtype or 'text/plain', size, modified)))
        if not host:
            urlfile = file
            if file[:1] == '/':
                urlfile = 'file://' + file
            return addinfourl(open(localname, 'rb'),
                              headers, urlfile)
        host, port = splitport(host)
        if not port \
           and socket.gethostbyname(host) in (localhost(), thishost()):
            urlfile = file
            if file[:1] == '/':
                urlfile = 'file://' + file
            return addinfourl(open(localname, 'rb'),
                              headers, urlfile)
        raise IOError, ('local file error', 'not on local host')

    def open_ftp(self, url):
        """Use FTP protocol."""
        if not isinstance(url, str):
            raise IOError, ('ftp error', 'proxy support for ftp protocol currently not implemented')
        import mimetypes, mimetools
        try:
            from cStringIO import StringIO
        except ImportError:
            from StringIO import StringIO
        host, path = splithost(url)
        if not host: raise IOError, ('ftp error', 'no host given')
        host, port = splitport(host)
        user, host = splituser(host)
        if user: user, passwd = splitpasswd(user)
        else: passwd = None
        host = unquote(host)
        user = unquote(user or '')
        passwd = unquote(passwd or '')
        host = socket.gethostbyname(host)
        if not port:
            from eventlet.green import ftplib
            port = ftplib.FTP_PORT
        else:
            port = int(port)
        path, attrs = splitattr(path)
        path = unquote(path)
        dirs = path.split('/')
        dirs, file = dirs[:-1], dirs[-1]
        if dirs and not dirs[0]: dirs = dirs[1:]
        if dirs and not dirs[0]: dirs[0] = '/'
        key = user, host, port, '/'.join(dirs)
        # XXX thread unsafe!
        if len(self.ftpcache) > MAXFTPCACHE:
            # Prune the cache, rather arbitrarily
            for k in self.ftpcache.keys():
                if k != key:
                    v = self.ftpcache[k]
                    del self.ftpcache[k]
                    v.close()
        try:
            if not key in self.ftpcache:
                self.ftpcache[key] = \
                    ftpwrapper(user, passwd, host, port, dirs)
            if not file: type = 'D'
            else: type = 'I'
            for attr in attrs:
                attr, value = splitvalue(attr)
                if attr.lower() == 'type' and \
                   value in ('a', 'A', 'i', 'I', 'd', 'D'):
                    type = value.upper()
            (fp, retrlen) = self.ftpcache[key].retrfile(file, type)
            mtype = mimetypes.guess_type("ftp:" + url)[0]
            headers = ""
            if mtype:
                headers += "Content-Type: %s\n" % mtype
            if retrlen is not None and retrlen >= 0:
                headers += "Content-Length: %d\n" % retrlen
            headers = mimetools.Message(StringIO(headers))
            return addinfourl(fp, headers, "ftp:" + url)
        except ftperrors(), msg:
            raise IOError, ('ftp error', msg), sys.exc_info()[2]

# this one is copied verbatim
class FancyURLopener(URLopener):
    """Derived class with handlers for errors we can handle (perhaps)."""

    def __init__(self, *args, **kwargs):
        URLopener.__init__(self, *args, **kwargs)
        self.auth_cache = {}
        self.tries = 0
        self.maxtries = 10

    def http_error_default(self, url, fp, errcode, errmsg, headers):
        """Default error handling -- don't raise an exception."""
        return addinfourl(fp, headers, "http:" + url)

    def http_error_302(self, url, fp, errcode, errmsg, headers, data=None):
        """Error 302 -- relocated (temporarily)."""
        self.tries += 1
        if self.maxtries and self.tries >= self.maxtries:
            if hasattr(self, "http_error_500"):
                meth = self.http_error_500
            else:
                meth = self.http_error_default
            self.tries = 0
            return meth(url, fp, 500,
                        "Internal Server Error: Redirect Recursion", headers)
        result = self.redirect_internal(url, fp, errcode, errmsg, headers,
                                        data)
        self.tries = 0
        return result

    def redirect_internal(self, url, fp, errcode, errmsg, headers, data):
        if 'location' in headers:
            newurl = headers['location']
        elif 'uri' in headers:
            newurl = headers['uri']
        else:
            return
        void = fp.read()
        fp.close()
        # In case the server sent a relative URL, join with original:
        newurl = basejoin(self.type + ":" + url, newurl)
        return self.open(newurl)

    def http_error_301(self, url, fp, errcode, errmsg, headers, data=None):
        """Error 301 -- also relocated (permanently)."""
        return self.http_error_302(url, fp, errcode, errmsg, headers, data)

    def http_error_303(self, url, fp, errcode, errmsg, headers, data=None):
        """Error 303 -- also relocated (essentially identical to 302)."""
        return self.http_error_302(url, fp, errcode, errmsg, headers, data)

    def http_error_307(self, url, fp, errcode, errmsg, headers, data=None):
        """Error 307 -- relocated, but turn POST into error."""
        if data is None:
            return self.http_error_302(url, fp, errcode, errmsg, headers, data)
        else:
            return self.http_error_default(url, fp, errcode, errmsg, headers)

    def http_error_401(self, url, fp, errcode, errmsg, headers, data=None):
        """Error 401 -- authentication required.
        This function supports Basic authentication only."""
        if not 'www-authenticate' in headers:
            URLopener.http_error_default(self, url, fp,
                                         errcode, errmsg, headers)
        stuff = headers['www-authenticate']
        import re
        match = re.match('[ \t]*([^ \t]+)[ \t]+realm="([^"]*)"', stuff)
        if not match:
            URLopener.http_error_default(self, url, fp,
                                         errcode, errmsg, headers)
        scheme, realm = match.groups()
        if scheme.lower() != 'basic':
            URLopener.http_error_default(self, url, fp,
                                         errcode, errmsg, headers)
        name = 'retry_' + self.type + '_basic_auth'
        if data is None:
            return getattr(self,name)(url, realm)
        else:
            return getattr(self,name)(url, realm, data)

    def http_error_407(self, url, fp, errcode, errmsg, headers, data=None):
        """Error 407 -- proxy authentication required.
        This function supports Basic authentication only."""
        if not 'proxy-authenticate' in headers:
            URLopener.http_error_default(self, url, fp,
                                         errcode, errmsg, headers)
        stuff = headers['proxy-authenticate']
        import re
        match = re.match('[ \t]*([^ \t]+)[ \t]+realm="([^"]*)"', stuff)
        if not match:
            URLopener.http_error_default(self, url, fp,
                                         errcode, errmsg, headers)
        scheme, realm = match.groups()
        if scheme.lower() != 'basic':
            URLopener.http_error_default(self, url, fp,
                                         errcode, errmsg, headers)
        name = 'retry_proxy_' + self.type + '_basic_auth'
        if data is None:
            return getattr(self,name)(url, realm)
        else:
            return getattr(self,name)(url, realm, data)

    def retry_proxy_http_basic_auth(self, url, realm, data=None):
        host, selector = splithost(url)
        newurl = 'http://' + host + selector
        proxy = self.proxies['http']
        urltype, proxyhost = splittype(proxy)
        proxyhost, proxyselector = splithost(proxyhost)
        i = proxyhost.find('@') + 1
        proxyhost = proxyhost[i:]
        user, passwd = self.get_user_passwd(proxyhost, realm, i)
        if not (user or passwd): return None
        proxyhost = quote(user, safe='') + ':' + quote(passwd, safe='') + '@' + proxyhost
        self.proxies['http'] = 'http://' + proxyhost + proxyselector
        if data is None:
            return self.open(newurl)
        else:
            return self.open(newurl, data)

    def retry_proxy_https_basic_auth(self, url, realm, data=None):
        host, selector = splithost(url)
        newurl = 'https://' + host + selector
        proxy = self.proxies['https']
        urltype, proxyhost = splittype(proxy)
        proxyhost, proxyselector = splithost(proxyhost)
        i = proxyhost.find('@') + 1
        proxyhost = proxyhost[i:]
        user, passwd = self.get_user_passwd(proxyhost, realm, i)
        if not (user or passwd): return None
        proxyhost = quote(user, safe='') + ':' + quote(passwd, safe='') + '@' + proxyhost
        self.proxies['https'] = 'https://' + proxyhost + proxyselector
        if data is None:
            return self.open(newurl)
        else:
            return self.open(newurl, data)

    def retry_http_basic_auth(self, url, realm, data=None):
        host, selector = splithost(url)
        i = host.find('@') + 1
        host = host[i:]
        user, passwd = self.get_user_passwd(host, realm, i)
        if not (user or passwd): return None
        host = quote(user, safe='') + ':' + quote(passwd, safe='') + '@' + host
        newurl = 'http://' + host + selector
        if data is None:
            return self.open(newurl)
        else:
            return self.open(newurl, data)

    def retry_https_basic_auth(self, url, realm, data=None):
        host, selector = splithost(url)
        i = host.find('@') + 1
        host = host[i:]
        user, passwd = self.get_user_passwd(host, realm, i)
        if not (user or passwd): return None
        host = quote(user, safe='') + ':' + quote(passwd, safe='') + '@' + host
        newurl = 'https://' + host + selector
        if data is None:
            return self.open(newurl)
        else:
            return self.open(newurl, data)

    def get_user_passwd(self, host, realm, clear_cache = 0):
        key = realm + '@' + host.lower()
        if key in self.auth_cache:
            if clear_cache:
                del self.auth_cache[key]
            else:
                return self.auth_cache[key]
        user, passwd = self.prompt_user_passwd(host, realm)
        if user or passwd: self.auth_cache[key] = (user, passwd)
        return user, passwd

    def prompt_user_passwd(self, host, realm):
        """Override this in a GUI environment!"""
        import getpass
        try:
            user = raw_input("Enter username for %s at %s: " % (realm,
                                                                host))
            passwd = getpass.getpass("Enter password for %s in %s at %s: " %
                (user, realm, host))
            return user, passwd
        except KeyboardInterrupt:
            print
            return None, None


# Utility functions

_localhost = None
def localhost():
    """Return the IP address of the magic hostname 'localhost'."""
    global _localhost
    if _localhost is None:
        _localhost = socket.gethostbyname('localhost')
    return _localhost

_thishost = None
def thishost():
    """Return the IP address of the current host."""
    global _thishost
    if _thishost is None:
        _thishost = socket.gethostbyname(socket.gethostname())
    return _thishost

_ftperrors = None
def ftperrors():
    """Return the set of errors raised by the FTP class."""
    global _ftperrors
    if _ftperrors is None:
        from eventlet.green import ftplib
        _ftperrors = ftplib.all_errors
    return _ftperrors


# Utility classes

class ftpwrapper(urllib.ftpwrapper):
    """Class used by open_ftp() for cache of open FTP connections."""

    def init(self):
        from eventlet.green import ftplib
        self.busy = 0
        self.ftp = ftplib.FTP()
        self.ftp.connect(self.host, self.port)
        self.ftp.login(self.user, self.passwd)
        for dir in self.dirs:
            self.ftp.cwd(dir)

    def retrfile(self, file, type):
        from eventlet.green import ftplib
        self.endtransfer()
        if type in ('d', 'D'): cmd = 'TYPE A'; isdir = 1
        else: cmd = 'TYPE ' + type; isdir = 0
        try:
            self.ftp.voidcmd(cmd)
        except ftplib.all_errors:
            self.init()
            self.ftp.voidcmd(cmd)
        conn = None
        if file and not isdir:
            # Try to retrieve as a file
            try:
                cmd = 'RETR ' + file
                conn = self.ftp.ntransfercmd(cmd)
            except ftplib.error_perm, reason:
                if str(reason)[:3] != '550':
                    raise IOError, ('ftp error', reason), sys.exc_info()[2]
        if not conn:
            # Set transfer mode to ASCII!
            self.ftp.voidcmd('TYPE A')
            # Try a directory listing
            if file: cmd = 'LIST ' + file
            else: cmd = 'LIST'
            conn = self.ftp.ntransfercmd(cmd)
        self.busy = 1
        # Pass back both a suitably decorated object and a retrieval length
        return (addclosehook(conn[0].makefile('rb'),
                             self.endtransfer), conn[1])

# Test and time quote() and unquote()
def test1():
    s = ''
    for i in range(256): s = s + chr(i)
    s = s*4
    t0 = time.time()
    qs = quote(s)
    uqs = unquote(qs)
    t1 = time.time()
    if uqs != s:
        print 'Wrong!'
    print repr(s)
    print repr(qs)
    print repr(uqs)
    print round(t1 - t0, 3), 'sec'


def reporthook(blocknum, blocksize, totalsize):
    # Report during remote transfers
    print "Block number: %d, Block size: %d, Total size: %d" % (
        blocknum, blocksize, totalsize)

# Test program
def test(args=[]):
    if not args:
        args = [
            '/etc/passwd',
            'file:/etc/passwd',
            'file://localhost/etc/passwd',
            'ftp://ftp.gnu.org/pub/README',
##          'gopher://gopher.micro.umn.edu/1/',
            'http://www.python.org/index.html',
            ]
        if hasattr(URLopener, "open_https"):
            args.append('https://synergy.as.cmu.edu/~geek/')
    try:
        for url in args:
            print '-'*10, url, '-'*10
            fn, h = urlretrieve(url, None, reporthook)
            print fn
            if h:
                print '======'
                for k in h.keys(): print k + ':', h[k]
                print '======'
            fp = open(fn, 'rb')
            data = fp.read()
            del fp
            if '\r' in data:
                table = string.maketrans("", "")
                data = data.translate(table, "\r")
            print data
            fn, h = None, None
        print '-'*40
    finally:
        urlcleanup()

def main():
    import getopt, sys
    try:
        opts, args = getopt.getopt(sys.argv[1:], "th")
    except getopt.error, msg:
        print msg
        print "Use -h for help"
        return
    t = 0
    for o, a in opts:
        if o == '-t':
            t = t + 1
        if o == '-h':
            print "Usage: python urllib.py [-t] [url ...]"
            print "-t runs self-test;",
            print "otherwise, contents of urls are printed"
            return
    if t:
        if t > 1:
            test1()
        test(args)
    else:
        if not args:
            print "Use -h for help"
        for url in args:
            print urlopen(url).read(),

# Run test program when run as a script
if __name__ == '__main__':
    main()
