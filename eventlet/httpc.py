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

import copy
import datetime
import httplib
import os.path
import os
import time
import urlparse


_old_HTTPConnection = httplib.HTTPConnection
_old_HTTPSConnection = httplib.HTTPSConnection


HTTP_TIME_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
to_http_time = lambda t: time.strftime(HTTP_TIME_FORMAT, time.gmtime(t))

try:

    from mx import DateTime
    def from_http_time(t, defaultdate=None):
        return int(DateTime.Parser.DateTimeFromString(
            t, defaultdate=defaultdate).gmticks())
except ImportError:
    import calendar
    parse_formats = (HTTP_TIME_FORMAT, # RFC 1123
                    '%A, %d-%b-%y %H:%M:%S GMT',  # RFC 850
                    '%a %b %d %H:%M:%S %Y') # asctime
    def from_http_time(t, defaultdate=None):
        for parser in parse_formats:
            try:
                return calendar.timegm(time.strptime(t, parser))
            except ValueError:
                continue
        return defaultdate     


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


def better_putrequest(self, method, url, skip_host=0, skip_accept_encoding=0):
    self.method = method
    self.path = url
    try:
        # Python 2.4 and above
        self.old_putrequest(method, url, skip_host, skip_accept_encoding)
    except TypeError:
        # Python 2.3 and below
        self.old_putrequest(method, url, skip_host)


class HttpClient(httplib.HTTPConnection):
    """A subclass of httplib.HTTPConnection that provides a better
    putrequest that records the method and path on the request object.
    """
    def __init__(self, host, port=None, strict=None):
        _old_HTTPConnection.__init__(self, host, port, strict)

    old_putrequest = httplib.HTTPConnection.putrequest
    putrequest = better_putrequest

class HttpsClient(httplib.HTTPSConnection):
    """A subclass of httplib.HTTPSConnection that provides a better
    putrequest that records the method and path on the request object.
    """
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
        raise klass(_Params('file://' + self.path, self.method))

    def close(self):
        """We're challenged here, and read the whole file rather than
        integrating with this lib. file object already out of scope at this
        point"""
        pass

class _Params(object):
    def __init__(self, url, method, body='', headers=None, dumper=None,
                 loader=None, use_proxy=False, ok=(), aux=None):
        '''
        @param connection The connection (as returned by make_connection) to use for the request.
        @param method HTTP method
        @param url Full url to make request on.
        @param body HTTP body, if necessary for the method.  Can be any object, assuming an appropriate dumper is also provided.
        @param headers Dict of header name to header value
        @param dumper Method that formats the body as a string.
        @param loader Method that converts the response body into an object.
        @param use_proxy Set to True if the connection is to a proxy.
        @param ok Set of valid response statuses.  If the returned status is not in this list, an exception is thrown.
        '''
        self.instance = None
        self.url = url
        self.path = url
        self.method = method
        self.body = body
        if headers is None:
            self.headers = {}
        else:
            self.headers = headers
        self.dumper = dumper
        self.loader = loader
        self.use_proxy = use_proxy
        self.ok = ok or (200, 201, 204)
        self.orig_body = body
        self.aux = aux


class _LocalParams(_Params):
    def __init__(self, params, **kwargs):
        self._delegate = params
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    def __getattr__(self, key):
        if key == '__setstate__': return
        return getattr(self._delegate, key)

    def __reduce__(self):
        params = copy.copy(self._delegate)
        kwargs = copy.copy(self.__dict__)
        assert(kwargs.has_key('_delegate'))
        del kwargs['_delegate']
        if hasattr(params,'aux'): del params.aux
        return (_LocalParams,(params,),kwargs)

    def __setitem__(self, k, item):
        setattr(self, k, item)

class ConnectionError(Exception):
    """Detailed exception class for reporting on http connection problems.

    There are lots of subclasses so you can use closely-specified
    exception clauses."""
    def __init__(self, params):
        self.params = params
        Exception.__init__(self)

    def location(self):
        return self.params.response.msg.dict.get('location')
        
    def expired(self):
        # 14.21 Expires
        #
        # HTTP/1.1 clients and caches MUST treat other invalid date
        # formats, especially including the value "0", as in the past
        # (i.e., "already expired").
        expires = from_http_time(
            self.params.response_headers.get('expires', '0'),
            defaultdate=DateTime.Epoch)
        return time.time() > expires

    def __repr__(self):
        response = self.params.response
        return "%s(url=%r, method=%r, status=%r, reason=%r, body=%r)" % (
            self.__class__.__name__, self.params.url, self.params.method,
            response.status, response.reason, self.params.body)

    __str__ = __repr__


class UnparseableResponse(ConnectionError):
    """Raised when a loader cannot parse the response from the server."""
    def __init__(self, content_type, response, url):
        self.content_type = content_type
        self.response = response
        self.url = url
        Exception.__init__(self)

    def __repr__(self):
        return "Could not parse the data at the URL %r of content-type %r\nData:\n%s" % (
            self.url, self.content_type, self.response)

    __str__ = __repr__


class Accepted(ConnectionError):
    """ 202 Accepted """
    pass


class Retriable(ConnectionError):
    def retry_method(self):
        return self.params.method

    def retry_url(self):
        return self.location() or self.url()

    def retry_(self):
        params = _LocalParams(self.params,
            url=self.retry_url(),
            method=self.retry_method())
        return self.params.instance.request_(params)
                                      
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


class TemporaryRedirect(Retriable):
    """ 307 Temporary Redirect """
    pass

        
class BadRequest(ConnectionError):
    """ 400 Bad Request """
    pass
        
class Unauthorized(ConnectionError):
    """ 401 Unauthorized """
    pass
        
class PaymentRequired(ConnectionError):
    """ 402 Payment Required """
    pass


class Forbidden(ConnectionError):
    """ 403 Forbidden """
    pass


class NotFound(ConnectionError):
    """ 404 Not Found """
    pass

class RequestTimeout(ConnectionError):
    """ 408 RequestTimeout """
    pass


class Gone(ConnectionError):
    """ 410 Gone """
    pass

class LengthRequired(ConnectionError):
    """ 411 Length Required """
    pass

class RequestEntityTooLarge(ConnectionError):
    """ 413 Request Entity Too Large """
    pass

class RequestURITooLong(ConnectionError):
    """ 414 Request-URI Too Long """
    pass

class UnsupportedMediaType(ConnectionError):
    """ 415 Unsupported Media Type """
    pass

class RequestedRangeNotSatisfiable(ConnectionError):
    """ 416 Requested Range Not Satisfiable """
    pass

class ExpectationFailed(ConnectionError):
    """ 417 Expectation Failed """
    pass

class NotImplemented(ConnectionError):
    """ 501 Not Implemented """
    pass

class ServiceUnavailable(Retriable):
    """ 503 Service Unavailable """
    def url(self):
        return self.params._delegate.url


class GatewayTimeout(Retriable):
    """ 504 Gateway Timeout """
    def url(self):
        return self.params._delegate.url

class HTTPVersionNotSupported(ConnectionError):
    """ 505 HTTP Version Not Supported """
    pass

class InternalServerError(ConnectionError):
    """ 500 Internal Server Error """
    def __repr__(self):
        try:
            import simplejson
            traceback = simplejson.loads(self.params.response_body)
        except:
            try:
                from indra.base import llsd
                traceback = llsd.parse(self.params.response_body)
            except:
                traceback = self.params.response_body
        if(isinstance(traceback, dict)
            and 'stack-trace' in traceback
            and 'description' in traceback):
            body = traceback
            traceback = "Traceback (most recent call last):\n"
            for frame in body['stack-trace']:
                traceback += '  File "%s", line %s, in %s\n' % (
                    frame['filename'], frame['lineno'], frame['method'])
                for line in frame['code']:
                    if line['lineno'] == frame['lineno']:
                        traceback += '    %s' % (line['line'].lstrip(), )
                        break
            traceback += body['description']
        return "The server raised an exception from our request:\n%s %s\n%s %s\n%s" % (
            self.params.method, self.params.url, self.params.response.status, self.params.response.reason, traceback)
    __str__ = __repr__



status_to_error_map = {
    202: Accepted,
    301: MovedPermanently,
    302: Found,
    303: SeeOther,
    304: NotModified,
    307: TemporaryRedirect,
    400: BadRequest,
    401: Unauthorized,
    402: PaymentRequired,
    403: Forbidden,
    404: NotFound,
    408: RequestTimeout,
    410: Gone,
    411: LengthRequired,
    413: RequestEntityTooLarge,
    414: RequestURITooLong,
    415: UnsupportedMediaType,
    416: RequestedRangeNotSatisfiable,
    417: ExpectationFailed,
    500: InternalServerError,
    501: NotImplemented,
    503: ServiceUnavailable,
    504: GatewayTimeout,
    505: HTTPVersionNotSupported,
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
    scheme, location = urlparse.urlparse(url)[:2]
    return make_connection(scheme, location, use_proxy)


def make_safe_loader(loader):
    if not callable(loader):
        return loader
    def safe_loader(what):
        try:
            return loader(what)
        except Exception:
            import traceback
            traceback.print_exc()
            return None
    return safe_loader


class HttpSuite(object):
    def __init__(self, dumper, loader, fallback_content_type):
        self.dumper = dumper
        self.loader = loader
        self.fallback_content_type = fallback_content_type

    def request_(self, params, connection=None):
        '''Make an http request to a url, for internal use mostly.'''

        params = _LocalParams(params, instance=self)

        (scheme, location, path, parameters, query,
         fragment) = urlparse.urlparse(params.url)

        if params.use_proxy:
            if scheme == 'file':
                params.use_proxy = False
            else:
                params.headers['host'] = location

        if not params.use_proxy:
            params.path = path
            if query:
                params.path += '?' + query

        params.orig_body = params.body

        if params.method in ('PUT', 'POST'):
            if self.dumper is not None:
                params.body = self.dumper(params.body)
            # don't set content-length header because httplib does it
            # for us in _send_request
        else:
            params.body = ''

        params.response, params.response_body = self._get_response_body(params, connection)
        response, body = params.response, params.response_body
        
        if self.loader is not None:
            try:
                body = make_safe_loader(self.loader(body))
            except KeyboardInterrupt:
                raise
            except Exception, e:
                raise UnparseableResponse(self.loader, body, params.url)

        return response.status, response.msg, body

    def _check_status(self, params):
        response = params.response
        if response.status not in params.ok:
            klass = status_to_error_map.get(response.status, ConnectionError)
            raise klass(params)

    def _get_response_body(self, params, connection):
        if connection is None:
            connection = connect(params.url, params.use_proxy)
        connection.request(params.method, params.path, params.body,
                           params.headers)
        params.response = connection.getresponse()
        params.response_body = params.response.read()
        connection.close()
        self._check_status(params)

        return params.response, params.response_body
        
    def request(self, params, connection=None):
        return self.request_(params, connection=connection)[-1]

    def head_(
        self, url, headers=None, use_proxy=False,
        ok=None, aux=None, connection=None):
        return self.request_(
            _Params(
                url, 'HEAD', headers=headers,
                loader=self.loader, dumper=self.dumper,
                use_proxy=use_proxy, ok=ok, aux=aux),
            connection)

    def head(self, *args, **kwargs):
        return self.head_(*args, **kwargs)[-1]

    def get_(
        self, url, headers=None, use_proxy=False, ok=None,
        aux=None, connection=None):
        if headers is None:
            headers = {}
        headers['accept'] = self.fallback_content_type+';q=1,*/*;q=0'
        return self.request_(
            _Params(
                url, 'GET', headers=headers,
                loader=self.loader, dumper=self.dumper,
                use_proxy=use_proxy, ok=ok, aux=aux),
            connection)

    def get(self, *args, **kwargs):
        return self.get_(*args, **kwargs)[-1]

    def put_(self, url, data, headers=None, content_type=None, ok=None,
             aux=None, connection=None):
        if headers is None:
            headers = {}
        if 'content-type' not in headers:
            if content_type is None:
                headers['content-type'] = self.fallback_content_type
            else:
                headers['content-type'] = content_type
        headers['accept'] = headers['content-type']+';q=1,*/*;q=0'
        return self.request_(
            _Params(
                url, 'PUT', body=data, headers=headers,
                loader=self.loader, dumper=self.dumper,
                ok=ok, aux=aux),
            connection)

    def put(self, *args, **kwargs):
        return self.put_(*args, **kwargs)[-1]

    def delete_(self, url, ok=None, aux=None, connection=None):
        return self.request_(
            _Params(
                url, 'DELETE', loader=self.loader,
                dumper=self.dumper, ok=ok, aux=aux),
            connection)

    def delete(self, *args, **kwargs):
        return self.delete_(*args, **kwargs)[-1]

    def post_(
        self, url, data='', headers=None, content_type=None,ok=None,
        aux=None, connection=None):
        if headers is None:
            headers = {}
        if 'content-type' not in headers:
            if content_type is None:
                headers['content-type'] = self.fallback_content_type
            else:
                headers['content-type'] = content_type
        headers['accept'] = headers['content-type']+';q=1,*/*;q=0'
        return self.request_(
            _Params(
                url, 'POST', body=data,
                headers=headers, loader=self.loader,
                dumper=self.dumper, ok=ok, aux=aux),
            connection)

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
