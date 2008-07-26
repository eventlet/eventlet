"""\
@file wsgi.py
@author Bob Ippolito

Copyright (c) 2005-2006, Bob Ippolito
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

import errno
import os
import sys
import time
import traceback
import urllib
import socket
import SocketServer
import BaseHTTPServer

from eventlet import api
from eventlet.httpdate import format_date_time
from eventlet import coros


DEFAULT_MAX_SIMULTANEOUS_REQUESTS = 1024


DEFAULT_MAX_HTTP_VERSION = 'HTTP/1.1'


class Input(object):
    def __init__(self, rfile, content_length, wfile=None, wfile_line=None):
        self.rfile = rfile
        if content_length is not None:
            content_length = int(content_length)
        self.content_length = content_length

        self.wfile = wfile
        self.wfile_line = wfile_line

        self.position = 0

    def _do_read(self, reader, length=None):
        if self.wfile is not None:
            ## 100 Continue
            self.wfile.write(self.wfile_line)
            self.wfile = None
            self.wfile_line = None

        if length is None and self.content_length is not None:
            length = self.content_length - self.position
        if length and length > self.content_length - self.position:
            length = self.content_length - self.position
        if not length:
            return ''
        read = reader(length)
        self.position += len(read)
        return read

    def read(self, length=None):
        return self._do_read(self.rfile.read, length)

    def readline(self):
        return self._do_read(self.rfile.readline)

    def readlines(self, hint=None):
        return self._do_read(self.rfile.readlines, hint)

    def __iter__(self):
        return iter(self.read())


MAX_REQUEST_LINE = 8192


class HttpProtocol(BaseHTTPServer.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def handle_one_request(self):
        if self.server.max_http_version:
            self.protocol_version = self.server.max_http_version

        try:
            self.raw_requestline = self.rfile.readline(MAX_REQUEST_LINE)
            if len(self.raw_requestline) == MAX_REQUEST_LINE:
                self.wfile.write(
                    "HTTP/1.0 414 Request URI Too Long\r\nConnection: close\r\nContent-length: 0\r\n\r\n")
                self.close_connection = 1
                return
        except socket.error, e:
            if e[0] != errno.EBADF:
                raise
            self.raw_requestline = ''
    
        if not self.raw_requestline:
            self.close_connection = 1
            return

        if not self.parse_request():
            return

        self.environ = self.get_environ()
        self.application = self.server.app
        try:
            self.server.outstanding_requests += 1
            try:
                self.handle_one_response()
            except socket.error, e:
                # Broken pipe, connection reset by peer
                if e[0] in (32, 54):
                    pass
                else:
                    raise
        finally:
            self.server.outstanding_requests -= 1

    def handle_one_response(self):
        start = time.time()
        headers_set = []
        headers_sent = []
        # set of lowercase header names that were sent
        header_dict = {}

        wfile = self.wfile
        num_blocks = None
        result = None
        use_chunked = False
        length = [0]
        status_code = [200]

        def write(data, _write=wfile.write):
            towrite = []
            if not headers_set:
                raise AssertionError("write() before start_response()")
            elif not headers_sent:
                status, response_headers = headers_set
                headers_sent.append(1)
                for k, v in response_headers:
                    header_dict[k.lower()] = k
                towrite.append('%s %s\r\n' % (self.protocol_version, status))
                for header in response_headers:
                    towrite.append('%s: %s\r\n' % header)

                # send Date header?
                if 'date' not in header_dict:
                    towrite.append('Date: %s\r\n' % (format_date_time(time.time()),))
                if num_blocks is not None:
                    if 'content-length' not in header_dict:
                        towrite.append('Content-Length: %s\r\n' % (len(''.join(result)),))
                elif use_chunked:
                    towrite.append('Transfer-Encoding: chunked\r\n')
                else:
                    towrite.append('Connection: close\r\n')
                    self.close_connection = 1
                towrite.append('\r\n')

            if use_chunked:
                ## Write the chunked encoding
                towrite.append("%x\r\n%s\r\n" % (len(data), data))
            else:
                towrite.append(data)
            joined = ''.join(towrite)
            length[0] = length[0] + len(joined)
            _write(joined)

        def start_response(status, response_headers, exc_info=None):
            status_code[0] = status.split()[0]
            if exc_info:
                try:
                    if headers_sent:
                        # Re-raise original exception if headers sent
                        raise exc_info[0], exc_info[1], exc_info[2]
                finally:
                    # Avoid dangling circular ref
                    exc_info = None

            capitalized_headers = [('-'.join([x.capitalize() for x in key.split('-')]), value)
                                   for key, value in response_headers]

            headers_set[:] = [status, capitalized_headers]
            return write

        try:
            result = self.application(self.environ, start_response)
        except Exception, e:
            exc = ''.join(traceback.format_exception(*sys.exc_info()))
            print exc
            if not headers_set:
                start_response("500 Internal Server Error", [('Content-type', 'text/plain')])
                write(exc)
                return

        try:
            num_blocks = len(result)
        except (TypeError, AttributeError, NotImplementedError):
            if self.request_version == 'HTTP/1.1':
                use_chunked = True
        try:
            try:
                towrite = []
                try:
                    for data in result:
                        if data:
                            towrite.append(data)
                            if use_chunked and sum(map(len, towrite)) > 4096:
                                write(''.join(towrite))
                                del towrite[:]
                except Exception, e:
                    exc = traceback.format_exc()
                    print exc
                    if not headers_set:
                        start_response("500 Internal Server Error", [('Content-type', 'text/plain')])
                        write(exc)
                        return
    
                if towrite:
                    write(''.join(towrite))
                if not headers_sent:
                    write('')
                if use_chunked:
                    wfile.write('0\r\n\r\n')
            except Exception, e:
                traceback.print_exc()
        finally:
            if hasattr(result, 'close'):
                result.close()
            if self.environ['eventlet.input'].position < self.environ.get('CONTENT_LENGTH', 0):
                ## Read and discard body
                self.environ['eventlet.input'].read()
            finish = time.time()

            self.server.log_message('%s - - [%s] "%s" %s %s %.6f\n' % (
                self.address_string(),
                self.log_date_time_string(),
                self.requestline,
                status_code[0],
                length[0],
                finish - start))

    def get_environ(self):
        env = self.server.get_environ()
        env['REQUEST_METHOD'] = self.command
        env['SCRIPT_NAME'] = ''

        if '?' in self.path:
            path, query = self.path.split('?', 1)
        else:
            path, query = self.path, ''
        env['PATH_INFO'] = urllib.unquote(path)
        env['QUERY_STRING'] = query

        if self.headers.typeheader is None:
            env['CONTENT_TYPE'] = self.headers.type
        else:
            env['CONTENT_TYPE'] = self.headers.typeheader

        length = self.headers.getheader('content-length')
        if length:
            env['CONTENT_LENGTH'] = length
        env['SERVER_PROTOCOL'] = 'HTTP/1.0'

        host, port = self.request.getsockname()
        env['SERVER_NAME'] = host
        env['SERVER_PORT'] = str(port)
        env['REMOTE_ADDR'] = self.client_address[0]
        env['GATEWAY_INTERFACE'] = 'CGI/1.1'

        for h in self.headers.headers:
            k, v = h.split(':', 1)
            k = k.replace('-', '_').upper()
            v = v.strip()
            if k in env:
                continue
            envk = 'HTTP_' + k
            if envk in env:
                env[envk] += ',' + v
            else:
                env[envk] = v

        if env.get('HTTP_EXPECT') == '100-continue':
            wfile = self.wfile
            wfile_line = 'HTTP/1.1 100 Continue\r\n\r\n'
        else:
            wfile = None
            wfile_line = None
        env['wsgi.input'] = env['eventlet.input'] = Input(
            self.rfile, length, wfile=wfile, wfile_line=wfile_line)

        return env

    def finish(self):
        BaseHTTPServer.BaseHTTPRequestHandler.finish(self)
        self.connection.close()


class Server(BaseHTTPServer.HTTPServer):
    def __init__(self, socket, address, app, log=None, environ=None, max_http_version=None, protocol=HttpProtocol):
        self.outstanding_requests = 0
        self.socket = socket
        self.address = address
        if log:
            self.log = log
        else:
            self.log = sys.stderr
        self.app = app
        self.environ = environ
        self.max_http_version = max_http_version      
        self.protocol = protocol
        self.pid = os.getpid()

    def get_environ(self):
        socket = self.socket
        d = {
            'wsgi.errors': sys.stderr,
            'wsgi.version': (1, 0),
            'wsgi.multithread': True,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'wsgi.url_scheme': 'http',
        }
        if self.environ is not None:
            d.update(self.environ)
        return d

    def process_request(self, (socket, address)):
        proto = self.protocol(socket, address, self)
        proto.handle()

    def log_message(self, message):
        self.log.write(message + '\n')


def server(sock, site, log=None, environ=None, max_size=None, max_http_version=DEFAULT_MAX_HTTP_VERSION, protocol=HttpProtocol, server_event=None):
    serv = Server(sock, sock.getsockname(), site, log, environ=None, max_http_version=max_http_version, protocol=protocol)
    if server_event is not None:
        server_event.send(serv)
    if max_size is None:
        max_size = DEFAULT_MAX_SIMULTANEOUS_REQUESTS
    pool = coros.CoroutinePool(max_size=max_size)
    try:
        host, port = sock.getsockname()
        port = ':%s' % (port, )
        if sock.is_secure:
            scheme = 'https'
            if port == ':443':
                port = ''
        else:
            scheme = 'http'
            if port == ':80':
                port = ''

        print "(%s) wsgi starting up on %s://%s%s/" % (os.getpid(), scheme, host, port)
        while True:
            try:
                try:
                    client_socket = sock.accept()
                except socket.error, e:
                    if e[0] != errno.EPIPE and e[0] != errno.EBADF:
                        raise
                pool.execute_async(serv.process_request, client_socket)
            except KeyboardInterrupt:
                api.get_hub().remove_descriptor(sock.fileno())
                print "wsgi exiting"
                break
    finally:
        try:
            sock.close()
        except socket.error, e:
            if e[0] != errno.EPIPE:
                raise

