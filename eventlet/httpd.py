"""\
@file httpd.py
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

import cgi
import errno
import socket
import sys
import time
import urllib
import socket
import traceback
import BaseHTTPServer

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from eventlet import api
from eventlet import coros


DEFAULT_MAX_HTTP_VERSION = 'HTTP/1.1'

USE_ACCESS_LOG = True


CONNECTION_CLOSED = (errno.EPIPE, errno.ECONNRESET)


class ErrorResponse(Exception):
    _responses = BaseHTTPServer.BaseHTTPRequestHandler.responses

    def __init__(self, code, reason_phrase=None, headers=None, body=None):
        Exception.__init__(self, reason_phrase)
        self.code = code
        if reason_phrase is None:
            self.reason = self._responses[code][0]
        else:
            self.reason = reason_phrase
        self.headers = headers
        if body is None:
            self.body = self._responses[code][1]
        else:
            self.body = body


class Request(object):
    _method = None
    _path = None
    _responsecode = 200
    _reason_phrase = None
    _request_started = False
    _chunked = False
    _producer_adapters = {}
    depth = 0
    def __init__(self, protocol, method, path, headers):
        self.context = {}
        self.request_start_time = time.time()
        self.site = protocol.server.site
        self.protocol = protocol
        self._method = method
        if '?' in path:
            self._path, self._query = path.split('?', 1)
            self._query = self._query.replace('&amp;', '&')
        else:
            self._path, self._query = path, None
        self._incoming_headers = headers
        self._outgoing_headers = dict()

    def response(self, code, reason_phrase=None, headers=None, body=None):
        """Change the response code. This will not be sent until some
        data is written; last call to this method wins. Default is
        200 if this is not called.
        """
        self._responsecode = code
        self._reason_phrase = reason_phrase
        self.protocol.set_response_code(self, code, reason_phrase)
        if headers is not None:
            try:
                headers = headers.iteritems()
            except AttributeError:
                pass
            for key, value in headers:
                self.set_header(key, value)
        if body is not None:
            self.write(body)

    def is_okay(self):
        return 200 <= self._responsecode <= 299

    def full_url(self):
        path = self.path()
        query = self.query()
        if query:
            path = path + '?' + query

        via = self.get_header('via', '')
        if via.strip():
            next_part = iter(via.split()).next

            received_protocol = next_part()
            received_by = next_part()
            if received_by.endswith(','):
                received_by = received_by[:-1]
            else:
                comment = ''
                while not comment.endswith(','):
                    try:
                        comment += next_part()
                    except StopIteration:
                        comment += ','
                        break
                comment = comment[:-1]
        else:
            received_by = self.get_header('host')

        return '%s://%s%s' % (self.request_protocol(), received_by, path)

    def begin_response(self, length="-"):
        """Begin the response, and return the initial response text
        """
        self._request_started = True
        request_time = time.time() - self.request_start_time

        code = self._responsecode
        proto = self.protocol

        if USE_ACCESS_LOG:
            proto.server.write_access_log_line(
                proto.client_address[0],
                time.strftime("%d/%b/%Y %H:%M:%S"),
                proto.requestline,
                code,
                length,
                request_time)

        if self._reason_phrase is not None:
            message = self._reason_phrase.split("\n")[0]
        elif code in proto.responses:
            message = proto.responses[code][0]
        else:
            message = ''
        if proto.request_version == 'HTTP/0.9':
            return []

        response_lines = proto.generate_status_line()

        if not self._outgoing_headers.has_key('connection'):
            con = self.get_header('connection')
            if con is None and proto.request_version == 'HTTP/1.0':
                con = 'close'
            if con is not None:
                self.set_header('connection', con)

        for key, value in self._outgoing_headers.items():
            key = '-'.join([x.capitalize() for x in key.split('-')])
            response_lines.append("%s: %s" % (key, value))

        response_lines.append("")
        return response_lines

    def write(self, obj):
        """Writes an arbitrary object to the response, using
        the sitemap's adapt method to convert it to bytes.
        """
        if isinstance(obj, str):
            self._write_bytes(obj)
        elif isinstance(obj, unicode):
            # use utf8 encoding for now, *TODO support charset negotiation
            # Content-Type: text/html; charset=utf-8
            ctype = self._outgoing_headers.get('content-type', 'text/html')
            ctype = ctype + '; charset=utf-8'
            self._outgoing_headers['content-type'] = ctype
            self._write_bytes(obj.encode('utf8'))
        else:
            self.site.adapt(obj, self)
        
    def _write_bytes(self, data):
        """Write all the data of the response.
        Can be called just once.
        """
        if self._request_started:
            print "Request has already written a response:"
            traceback.print_stack()
            return

        self._outgoing_headers['content-length'] = len(data)

        response_lines = self.begin_response(len(data))
        response_lines.append(data)
        self.protocol.wfile.write("\r\n".join(response_lines))
        if hasattr(self.protocol.wfile, 'flush'):
            self.protocol.wfile.flush()

    def method(self):
        return self._method

    def path(self):
        return self._path

    def path_segments(self):
        return [urllib.unquote_plus(x) for x in self._path.split('/')[1:]]

    def query(self):
        return self._query

    def uri(self):
        if self._query:
            return '%s?%s' % (
                self._path, self._query)
        return self._path

    def get_headers(self):
        return self._incoming_headers

    def get_header(self, header_name, default=None):
        return self.get_headers().get(header_name.lower(), default)

    def get_query_pairs(self):
        if not hasattr(self, '_split_query'):
            if self._query is None:
                self._split_query = ()
            else:
                spl = self._query.split('&')
                spl = [x.split('=', 1) for x in spl if x]
                self._split_query = []
                for query in spl:
                    if len(query) == 1:
                        key = query[0]
                        value = ''
                    else:
                        key, value = query
                    self._split_query.append((urllib.unquote_plus(key), urllib.unquote_plus(value)))

        return self._split_query

    def get_queries_generator(self, name):
        """Generate all query parameters matching the given name.
        """
        for key, value in self.get_query_pairs():
            if key == name or not name:
                yield value

    get_queries = lambda self, name: list(self.get_queries_generator)

    def get_query(self, name, default=None):
        try:
            return self.get_queries_generator(name).next()
        except StopIteration:
            return default

    def get_arg_list(self, name):
        return self.get_field_storage().getlist(name)

    def get_arg(self, name, default=None):
        return self.get_field_storage().getfirst(name, default)

    def get_field_storage(self):
        if not hasattr(self, '_field_storage'):
            if self.method() == 'GET':
                data = ''
            if self._query:
                data = self._query
            else:
                data = self.read_body()
            fl = StringIO(data)
            ## Allow our resource to provide the FieldStorage instance for
            ## customization purposes.
            headers = self.get_headers()
            environ = dict(
                REQUEST_METHOD='POST',
                QUERY_STRING=self._query or '')

            self._field_storage = cgi.FieldStorage(fl, headers, environ=environ)

        return self._field_storage

    def set_header(self, key, value):
        if key.lower() == 'connection' and value.lower() == 'close':
            self.protocol.close_connection = 1
        self._outgoing_headers[key.lower()] = value
    __setitem__ = set_header

    def get_outgoing_header(self, key):
        return self._outgoing_headers[key.lower()]

    def has_outgoing_header(self, key):
        return self._outgoing_headers.has_key(key.lower())

    def socket(self):
        return self.protocol.socket

    def error(self, response=None, body=None, log_traceback=True):
        if log_traceback:
            traceback.print_exc(file=self.log)
        if response is None:
            response = 500
        if body is None:
            typ, val, tb = sys.exc_info() 
            body = dict(type=str(typ), error=True, reason=str(val))
        self.response(response)
        if(type(body) is str and not self.response_written()):
            self.write(body)
            return
        try:
            produce(body, self)
        except Exception, e:
            traceback.print_exc(file=self.log)
            if not self.response_written():
                self.write('Internal Server Error')

    def not_found(self):
        self.error(404, 'Not Found\n', log_traceback=False)

    def raw_body(self):
        if not hasattr(self, '_cached_body'):
            self.read_body()
        return self._cached_body

    def read_body(self):
        """ Returns the string body that was read off the request, or
        the empty string if there was no request body.

        Requires a content-length header.  Caches the body so multiple
        calls to read_body() are free.
        """
        if not hasattr(self, '_cached_body'):
            length = self.get_header('content-length')
            if length:
                length = int(length)
            if length:
                self._cached_body = self.protocol.rfile.read(length)
            else:
                self._cached_body = ''
        return self._cached_body            

    def parsed_body(self):
        """ Returns the parsed version of the body, using the
        content-type header to select from the parsers on the site
        object.

        If no parser is found, returns the string body from
        read_body().  Caches the parsed body so multiple calls to
        parsed_body() are free.
        """
        if not hasattr(self, '_cached_parsed_body'):
            body = self.read_body()
            if hasattr(self.site, 'parsers'):
                ct = self.get_header('content-type')
                parser = self.site.parsers.get(ct)
                    
                if parser is not None:
                    body = parser(body)
                else:
                    ex = ValueError("Could not find parser for content-type: %s" % ct)
                    ex.body = body
                    raise ex
                self._cached_parsed_body = body
        return self._cached_parsed_body

    def override_body(self, body):
        if not hasattr(self, '_cached_parsed_body'):
            self.read_body() ## Read and discard body
        self._cached_parsed_body = body

    def response_written(self):
        ## TODO change badly named variable
        return self._request_started

    def request_version(self):
        return self.protocol.request_version

    def request_protocol(self):
        if self.protocol.is_secure:
            return "https"
        return "http"

    def server_address(self):
        return self.protocol.server.address

    def __repr__(self):
        return "<Request %s %s>" % (
            getattr(self, '_method'), getattr(self, '_path'))

DEFAULT_TIMEOUT = 300

# This value was chosen because apache 2 has a default limit of 8190.
# I believe that slightly smaller number is because apache does not
# count the \r\n.
MAX_REQUEST_LINE = 8192

class Timeout(RuntimeError):
    pass

class HttpProtocol(BaseHTTPServer.BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        self.rfile = self.wfile = request.makefile()
        self.is_secure = request.is_secure
        request.close()  # close this now so that when rfile and wfile are closed, the socket gets closed
        self.client_address = client_address
        self.server = server
        self.set_response_code(None, 200, None)
        self.protocol_version = server.max_http_version

    def close(self):
        self.rfile.close()
        self.wfile.close()

    def set_response_code(self, request, code, message):
        self._code = code
        if message is not None:
            self._message = message.split("\n")[0]
        elif code in self.responses:
            self._message = self.responses[code][0]
        else:
            self._message = ''

    def generate_status_line(self):
        return [
            "%s %d %s" % (
                self.protocol_version, self._code, self._message)]

    def write_bad_request(self, status, reason):
        self.set_response_code(self, status, reason)
        self.wfile.write(''.join(self.generate_status_line()))
        self.wfile.write('\r\nServer: %s\r\n' % self.version_string())
        self.wfile.write('Date: %s\r\n' % self.date_time_string())
        self.wfile.write('Content-Length: 0\r\n\r\n')

    def handle(self):
        self.close_connection = 0

        timeout = DEFAULT_TIMEOUT
        while not self.close_connection:
            if timeout == 0:
                break
            cancel = api.exc_after(timeout, Timeout)
            try:
                self.raw_requestline = self.rfile.readline(MAX_REQUEST_LINE)
                if self.raw_requestline is not None:
                    if len(self.raw_requestline) == MAX_REQUEST_LINE:
                        # Someone sent a request line which is too
                        # large. Be helpful and tell them.
                        self.write_bad_request(414, 'Request-URI Too Long')
                        self.close_connection = True
                        continue
            except socket.error, e:
                if e[0] in CONNECTION_CLOSED:
                    self.close_connection = True
                    cancel.cancel()
                    continue
            except Timeout:
                self.close_connection = True
                continue
            except Exception, e:
                try:
                    if e[0][0][0].startswith('SSL'):
                        print "SSL Error:", e[0][0]
                        self.close_connection = True
                        cancel.cancel()
                        continue
                except Exception, f:
                    print "Exception in ssl test:",f
                    pass
                raise e
            cancel.cancel()

            if not self.raw_requestline or not self.parse_request():
                self.close_connection = True
                continue

            self.set_response_code(None, 200, None)
            request = Request(self, self.command, self.path, self.headers)
            request.set_header('Server', self.version_string())
            request.set_header('Date', self.date_time_string())
            try:
                timeout = int(request.get_header('keep-alive', timeout))
            except TypeError, ValueError:
                pass

            try:
                try:
                    try:
                        self.server.site.handle_request(request)
                    except ErrorResponse, err:
                        request.response(code=err.code,
                                         reason_phrase=err.reason,
                                         headers=err.headers,
                                         body=err.body)
                finally:                            
                    # clean up any timers that might have been left around by the handling code
                    api.get_hub().cancel_timers(api.getcurrent())
                    
                # throw an exception if it failed to write a body
                if not request.response_written():
                    raise NotImplementedError("Handler failed to write response to request: %s" % request)
                
                if not hasattr(self, '_cached_body'):
                    try:
                        request.read_body() ## read & discard body
                    except:
                        pass
                
            except socket.error, e:
                # Broken pipe, connection reset by peer
                if e[0] in CONNECTION_CLOSED:
                    #print "Remote host closed connection before response could be sent"
                    pass
                else:
                    raise
            except Exception, e:
                self.server.log_message("Exception caught in HttpRequest.handle():\n")
                self.server.log_exception(*sys.exc_info())
                if not request.response_written():
                    request.response(500)
                    request.write('Internal Server Error')
                self.close()
                raise e # can't do a plain raise since exc_info might have been cleared
        self.close()


class Server(BaseHTTPServer.HTTPServer):
    def __init__(self, socket, address, site, log, max_http_version=DEFAULT_MAX_HTTP_VERSION):
        self.socket = socket
        self.address = address
        self.site = site
        self.max_http_version = max_http_version
        if log:
            self.log = log
            if hasattr(log, 'info'):
                log.write = log.info
        else:
            self.log = self

    def write(self, something):
        sys.stdout.write('%s' % (something, )); sys.stdout.flush()

    def log_message(self, message):
        self.log.write(message)

    def log_exception(self, type, value, tb):
        self.log.write(''.join(traceback.format_exception(type, value, tb)))

    def write_access_log_line(self, *args):
        """Write a line to the access.log. Arguments:
        client_address, date_time, requestline, code, size, request_time
        """
        self.log.write(
            '%s - - [%s] "%s" %s %s %.6f\n' % args)


def server(sock, site, log=None, max_size=512, serv=None, max_http_version=DEFAULT_MAX_HTTP_VERSION):
    pool = coros.CoroutinePool(max_size=max_size)
    if serv is None:
        serv = Server(sock, sock.getsockname(), site, log, max_http_version=max_http_version)
    try:
        serv.log.write("httpd starting up on %s\n" % (sock.getsockname(), ))
        while True:
            try:
                new_sock, address = sock.accept()
                proto = HttpProtocol(new_sock, address, serv)
                pool.execute_async(proto.handle)
                api.sleep(0)   # sleep to allow other coros to run
            except KeyboardInterrupt:
                api.get_hub().remove_descriptor(sock.fileno())
                serv.log.write("httpd exiting\n")
                break
    finally:
        try:
            sock.close()
        except socket.error:
            pass


if __name__ == '__main__':
    class TestSite(object):
        def handle_request(self, req):
            req.write('hello')

    server(
        api.tcp_listener(('127.0.0.1', 8080)),
        TestSite())

