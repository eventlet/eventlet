"""\
@file httpc.py
@author Donovan Preston

Copyright (c) 2005-2006, Donovan Preston
Copyright (c) 2007, Linden Research, Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import datetime
import httplib
import os.path
import os
import time
import urlparse


from mx import DateTime


_old_HTTPConnection = httplib.HTTPConnection
_old_HTTPSConnection = httplib.HTTPSConnection


HTTP_TIME_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'


to_http_time = lambda t: time.strftime(HTTP_TIME_FORMAT, time.gmtime(t))
def from_http_time(t, defaultdate=None):
    return int(DateTime.Parser.DateTimeFromString(
        t, defaultdate=defaultdate).gmticks())

def host_and_port_from_url(url):
    """@brief Simple function to get host and port from an http url.
    @return Returns host, port and port may be None.
    """
    host = None
    port = None
    parsed_url = urlparse.urlparse(url)
    try:
        host, port = parsed_url[1].split(':')
    except ValueError:
        host = parsed_url[1].split(':')
    return host, port


def better_putrequest(self, method, url, skip_host=0):
    self.method = method
    self.path = url
    self.old_putrequest(method, url, skip_host)


class HttpClient(httplib.HTTPConnection):
    """A subclass of httplib.HTTPConnection which works around a bug
    in the interaction between eventlet sockets and httplib. httplib relies
    on gc to close the socket, causing the socket to be closed too early.

    This is an awful hack and the bug should be fixed properly ASAP.
    """
    def __init__(self, host, port=None, strict=None):
        _old_HTTPConnection.__init__(self, host, port, strict)

    def close(self):
        pass

    old_putrequest = httplib.HTTPConnection.putrequest
    putrequest = better_putrequest

class HttpsClient(httplib.HTTPSConnection):
    """A subclass of httplib.HTTPSConnection which works around a bug
    in the interaction between eventlet sockets and httplib. httplib relies
    on gc to close the socket, causing the socket to be closed too early.

    This is an awful hack and the bug should be fixed properly ASAP.
    """
    def close(self):
        pass
    old_putrequest = httplib.HTTPSConnection.putrequest
    putrequest = better_putrequest


def wrap_httplib_with_httpc():
    """Replace httplib's implementations of these classes with our enhanced ones.

    Needed to work around code that uses httplib directly."""
    httplib.HTTP._connection_class = httplib.HTTPConnection = HttpClient
    httplib.HTTPS._connection_class = httplib.HTTPSConnection = HttpsClient



class FileScheme(object):
    """Retarded scheme to local file wrapper."""
    host = '<file>'
    port = '<file>'
    reason = '<none>'

    def __init__(self, location):
        pass

    def request(self, method, fullpath, body='', headers=None):
        self.status = 200
        self.msg = ''
        self.path = fullpath.split('?')[0]
        self.method = method = method.lower()
        assert method in ('get', 'put', 'delete')
        if method == 'delete':
            try:
                os.remove(self.path)
            except OSError:
                pass  # don't complain if already deleted
        elif method == 'put':
            try:
                f = file(self.path, 'w')
                f.write(body)
                f.close()
            except IOError, e:
                self.status = 500
                self.raise_connection_error()
        elif method == 'get':
            if not os.path.exists(self.path):
                self.status = 404
                self.raise_connection_error(NotFound)

    def connect(self):
        pass

    def getresponse(self):
        return self

    def getheader(self, header):
        if header == 'content-length':
            try:
                return os.path.getsize(self.path)
            except OSError:
                return 0

    def read(self, howmuch=None):
        if self.method == 'get':
            try:
                fl = file(self.path, 'r')
                if howmuch is None:
                    return fl.read()
                else:
                    return fl.read(howmuch)
            except IOError:
                self.status = 500
                self.raise_connection_error()
        return ''

    def raise_connection_error(self, klass=None):
        if klass is None:
            klass=ConnectionError
        raise klass(
            self.method, self.host, self.port,
            self.path, self.status, self.reason, '')


class ConnectionError(Exception):
    """Detailed exception class for reporting on http connection problems.

    There are lots of subclasses so you can use closely-specified
    exception clauses."""
    def __init__(self, method, host, port, path, status, reason, body,
                 instance=None, connection=None, url='', headers={},
                 dumper=None, loader=None, use_proxy=False, ok=None,
                 response_headers={}, req_body=''):
        self.method = method
        self.host = host
        self.port = port
        self.path = path
        self.status = status
        self.reason = reason
        self.body = body
        self.instance = instance
        self.connection = connection
        self.url = url
        self.headers = headers
        self.dumper = dumper
        self.loader = loader
        self.use_proxy = use_proxy
        self.ok = ok
        self.response_headers = response_headers
        self.req_body = req_body
        Exception.__init__(self)

    def location(self):
        return self.response_headers.get('location')
        
    def expired(self):
        # 14.21 Expires
        #
        # HTTP/1.1 clients and caches MUST treat other invalid date
        # formats, especially including the value "0", as in the past
        # (i.e., "already expired").
        expires = from_http_time(instance.response_headers.get('expires', '0'),
                                 defaultdate=DateTime.Epoch)
        return time.time() > expires

    def __repr__(self):
        return "ConnectionError(%r, %r, %r, %r, %r, %r, %r)" % (
            self.method, self.host, self.port,
            self.path, self.status, self.reason, self.body)

    __str__ = __repr__


class UnparseableResponse(ConnectionError):
    """Raised when a loader cannot parse the response from the server."""
    def __init__(self, content_type, response):
        self.content_type = content_type
        self.response = response
        Exception.__init__(self)

    def __repr__(self):
        return "UnparseableResponse(%r, %r)" % (
            self.content_type, self.response)

    __str__ = __repr__


class Accepted(ConnectionError):
    """ 202 Accepted """
    pass


class Retriable(ConnectionError):
    def retry_method(self):
        return self.method

    def retry_url(self):
        return self.location() or self.url()

    def retry_(self):
        url = self.retry_url()
        return self.instance.request_(
            connect(url, self.use_proxy), self.retry_method(), url,
            self.req_body, self.headers, self.dumper, self.loader,
            self.use_proxy, self.ok)
                                      
    def retry(self):
        return self.retry_()[-1]


class MovedPermanently(Retriable):
    """ 301 Moved Permanently """
    pass


class Found(Retriable):
    """ 302 Found """

    pass


class SeeOther(Retriable):
    """ 303 See Other """

    def retry_method(self):
        return 'GET'

    
class NotModified(ConnectionError):
    """ 304 Not Modified """
    pass

        
class BadRequest(ConnectionError):
    """ 400 Bad Request """
    pass


class Forbidden(ConnectionError):
    """ 403 Forbidden """
    pass


class NotFound(ConnectionError):
    """ 404 Not Found """
    pass


class Gone(ConnectionError):
    """ 410 Gone """
    pass


class InternalServerError(ConnectionError):
    """ 500 Internal Server Error """
    pass


status_to_error_map = {
    202: Accepted,
    301: MovedPermanently,
    302: Found,
    303: SeeOther,
    304: NotModified,
    400: BadRequest,
    403: Forbidden,
    404: NotFound,
    410: Gone,
    500: InternalServerError,
}

scheme_to_factory_map = {
    'http': HttpClient,
    'https': HttpsClient,
    'file': FileScheme,
}


def make_connection(scheme, location, use_proxy):
    """ Create a connection object to a host:port.

    @param scheme Protocol, scheme, whatever you want to call it.  http, file, https are currently supported.
    @param location Hostname and port number, formatted as host:port or http://host:port if you're so inclined.
    @param use_proxy Connect to a proxy instead of the actual location.  Uses environment variables to decide where the proxy actually lives.
    """
    if use_proxy:
        if "http_proxy" in os.environ:
            location = os.environ["http_proxy"]
        elif "ALL_PROXY" in os.environ:
            location = os.environ["ALL_PROXY"]
        else:
            location = "localhost:3128" #default to local squid

    # run a little heuristic to see if location is an url, and if so parse out the hostpart
    if location.startswith('http'):
        _scheme, location, path, parameters, query, fragment = urlparse.urlparse(location)
            
    result = scheme_to_factory_map[scheme](location)
    result.connect()
    return result


def connect(url, use_proxy=False):
    """ Create a connection object to the host specified in a url.  Convenience function for make_connection."""
    scheme, location, path, params, query, id = urlparse.urlparse(url)
    return make_connection(scheme, location, use_proxy)


def make_safe_loader(loader):
    def safe_loader(what):
        try:
            return loader(what)
        except Exception, e:
            return None
    return safe_loader


class HttpSuite(object):
    def __init__(self, dumper, loader, fallback_content_type):
        self.dumper = dumper
        self.loader = loader
        self.fallback_content_type = fallback_content_type

    def request_(self, connection, method, url, body='', headers=None, dumper=None, loader=None, use_proxy=False, ok=None):
        """Make an http request to a url, for internal use mostly.

        @param connection The connection (as returned by make_connection) to use for the request.
        @param method HTTP method
        @param url Full url to make request on.
        @param body HTTP body, if necessary for the method.  Can be any object, assuming an appropriate dumper is also provided.
        @param headers Dict of header name to header value
        @param dumper Method that formats the body as a string.
        @param loader Method that converts the response body into an object.
        @param use_proxy Set to True if the connection is to a proxy.
        @param ok Set of valid response statuses.  If the returned status is not in this list, an exception is thrown.
        """
        if ok is None:
            ok = (200, 201, 204)
        if headers is None:
            headers = {}
        if not use_proxy:
            scheme, location, path, params, query, id = urlparse.urlparse(url)
            url = path
            if query:
                url += "?" + query
        else:
            scheme, location, path, params, query, id = urlparse.urlparse(url)
            headers.update({ "host" : location })
            if scheme == 'file':
                use_proxy = False

        orig_body = body
        if method in ('PUT', 'POST'):
            if dumper is not None:
                body = dumper(body)
            # don't set content-length header because httplib does it
            # for us in _send_request
        else:
            body = ''

        response, body = self._get_response_body(connection, method, url,
                                                 body, headers, ok, dumper,
                                                 loader, use_proxy, orig_body)
        
        if loader is not None:
            try:
                body = loader(body)
            except Exception, e:
                raise UnparseableResponse(loader, body)

        return response.status, response.msg, body

    def _get_response_body(self, connection, method, url, body, headers, ok,
                           dumper, loader, use_proxy, orig_body):
        connection.request(method, url, body, headers)
        response = connection.getresponse()
        if response.status not in ok:
            klass = status_to_error_map.get(response.status, ConnectionError)
            raise klass(
                method=connection.method,
                host=connection.host,
                port=connection.port,
                path=connection.path,
                status=response.status,
                reason=response.reason,
                body=response.read(),
                instance=self,
                connection=connection,
                url=url,
                headers=headers,
                dumper=dumper,
                loader=loader,
                use_proxy=use_proxy,
                ok=ok,
                response_headers=response.msg.dict,
                req_body=orig_body)

        return response, response.read()
        
    def request(self, *args, **kwargs):
        return self.request_(*args, **kwargs)[-1]

    def head_(self, url, headers=None, use_proxy=False, ok=None):
        return self.request_(connect(url, use_proxy), method='HEAD', url=url,
                             body='', headers=headers, use_proxy=use_proxy,
                             ok=ok)

    def head(self, *args, **kwargs):
        return self.head_(*args, **kwargs)[-1]

    def get_(self, url, headers=None, use_proxy=False, ok=None):
        #import pdb; pdb.Pdb().set_trace()
        if headers is None:
            headers = {}
        return self.request_(connect(url, use_proxy), method='GET', url=url,
                             body='', headers=headers, loader=self.loader,
                             use_proxy=use_proxy, ok=ok)

    def get(self, *args, **kwargs):
        return self.get_(*args, **kwargs)[-1]

    def put_(self, url, data, headers=None, content_type=None, ok=None):
        if headers is None:
            headers = {}
        if content_type is None:
            headers['content-type'] = self.fallback_content_type
        else:
            headers['content-type'] = content_type
        return self.request_(connect(url), method='PUT', url=url, body=data,
                             headers=headers, dumper=self.dumper,
                             loader=make_safe_loader(self.loader), ok=ok)

    def put(self, *args, **kwargs):
        return self.put_(*args, **kwargs)[-1]

    def delete_(self, url, ok=None):
        return request_(connect(url), method='DELETE', url=url, ok=ok)

    def delete(self, *args, **kwargs):
        return self.delete_(*args, **kwargs)[-1]

    def post_(self, url, data='', headers=None, content_type=None, ok=None):
        if headers is None:
            headers = {}
        if 'content-type' in headers:
            if content_type is None:
                headers['content-type'] = self.fallback_content_type
            else:
                headers['content-type'] = content_type
        return self.request_(connect(url), method='POST', url=url, body=data,
                             headers=headers, dumper=self.dumper,
                             loader=self.loader, ok=ok)

    def post(self, *args, **kwargs):
        return self.post_(*args, **kwargs)[-1]


def make_suite(dumper, loader, fallback_content_type):
    """ Return a tuple of methods for making http requests with automatic bidirectional formatting with a particular content-type."""
    suite = HttpSuite(dumper, loader, fallback_content_type)
    return suite.get, suite.put, suite.delete, suite.post


suite = HttpSuite(str, None, 'text/plain')
delete = suite.delete
delete_ = suite.delete_
get = suite.get
get_ = suite.get_
head = suite.head
head_ = suite.head_
post = suite.post
post_ = suite.post_
put = suite.put
put_ = suite.put_
request = suite.request
request_ = suite.request_
