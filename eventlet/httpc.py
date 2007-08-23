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


from mx.DateTime import Parser


_old_HTTPConnection = httplib.HTTPConnection
_old_HTTPSConnection = httplib.HTTPSConnection


HTTP_TIME_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'


to_http_time = lambda t: time.strftime(HTTP_TIME_FORMAT, time.gmtime(t))
from_http_time = lambda t: int(Parser.DateTimeFromString(t).gmticks())

def host_and_port_from_url(url):
    """@brief Simple function to get host and port from an http url.
    @return Returns host, port and port may be None.
    """
    host = None
    port = None
    #print url
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


def wrap_httplib_with_httpc():
    httplib.HTTP._connection_class = httplib.HTTPConnection = HttpClient
    httplib.HTTPS._connection_class = httplib.HTTPSConnection = HttpsClient


class HttpsClient(httplib.HTTPSConnection):
    def close(self):
        pass
    old_putrequest = httplib.HTTPSConnection.putrequest
    putrequest = better_putrequest


class FileScheme(object):
    """Retarded scheme to local file wrapper."""
    host = '<file>'
    port = '<file>'
    reason = '<none>'

    def __init__(self, location):
        pass

    def request(self, method, fullpath, body='', headers=None):
        self.status = 200
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
    def __init__(self, method, host, port, path, status, reason, body):
        self.method = method
        self.host = host
        self.port = port
        self.path = path
        self.status = status
        self.reason = reason
        self.body = body
        Exception.__init__(self)

    def __repr__(self):
        return "ConnectionError(%r, %r, %r, %r, %r, %r, %r)" % (
            self.method, self.host, self.port,
            self.path, self.status, self.reason, self.body)

    __str__ = __repr__


class UnparseableResponse(ConnectionError):
    def __init__(self, content_type, response):
        self.content_type = content_type
        self.response = response
        Exception.__init__(self)

    def __repr__(self):
        return "UnparseableResponse(%r, %r)" % (
            self.content_type, self.response)

    __str__ = __repr__


class Accepted(ConnectionError):
    pass

        
class NotFound(ConnectionError):
    pass


class Forbidden(ConnectionError):
    pass


class InternalServerError(ConnectionError):
    pass


class Gone(ConnectionError):
    pass


status_to_error_map = {
    500: InternalServerError,
    410: Gone,
    404: NotFound,
    403: Forbidden,
    202: Accepted,
}

scheme_to_factory_map = {
    'http': HttpClient,
    'https': HttpsClient,
    'file': FileScheme,
}


def make_connection(scheme, location, use_proxy):
    if use_proxy:
        if "http_proxy" in os.environ:
            location = os.environ["http_proxy"]
        elif "ALL_PROXY" in os.environ:
            location = os.environ["ALL_PROXY"]
        else:
            location = "localhost:3128" #default to local squid

    # run a little heuristic to see if it's an url, and if so parse out the hostpart
    if location.startswith('http'):
        _scheme, location, path, parameters, query, fragment = urlparse.urlparse(location)
            
    result = scheme_to_factory_map[scheme](location)
    result.connect()
    return result


def connect(url, use_proxy=False):
    scheme, location, path, params, query, id = urlparse.urlparse(url)
    return make_connection(scheme, location, use_proxy)


def request(connection, method, url, body='', headers=None, dumper=None, loader=None, use_proxy=False, verbose=False, ok=None):
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


    if dumper is not None:
        body = dumper(body)
        headers['content-length'] = len(body)

    connection.request(method, url, body, headers)
    response = connection.getresponse()
    if (response.status not in ok):
        klass = status_to_error_map.get(response.status, ConnectionError)
        raise klass(
            connection.method, connection.host, connection.port,
            connection.path, response.status, response.reason, response.read())

    body = response.read()

    if loader is None:
        return body

    try:
        body = loader(body)
    except Exception, e:
        raise UnparseableResponse(loader, body)

    if verbose:
        return response.status, response.msg, body
    return body


def make_suite(dumper, loader, fallback_content_type):
    def get(url, headers=None, use_proxy=False, verbose=False, ok=None):
        #import pdb; pdb.Pdb().set_trace()
        if headers is None:
            headers = {}
        connection = connect(url)
        return request(connection, 'GET', url, '', headers, None, loader, use_proxy, verbose, ok)

    def put(url, data, headers=None, content_type=None, verbose=False, ok=None):
        if headers is None:
            headers = {}
        if content_type is not None:
            headers['content-type'] = content_type
        else:
            headers['content-type'] = fallback_content_type
        connection = connect(url)
        return request(connection, 'PUT', url, data, headers, dumper, loader, verbose=verbose, ok=ok)

    def delete(url, verbose=False, ok=None):
        return request(connect(url), 'DELETE', url, verbose=verbose, ok=ok)

    def post(url, data='', headers=None, content_type=None, verbose=False, ok=None):
        connection = connect(url)
        if headers is None:
            headers = {}
        if 'content-type' not in headers:
            if content_type is not None:
                headers['content-type'] = content_type
            else:
                headers['content-type'] = fallback_content_type
        return request(connect(url), 'POST', url, data, headers, dumper, loader, verbose=verbose, ok=ok)

    return get, put, delete, post


get, put, delete, post = make_suite(str, None, 'text/plain')


