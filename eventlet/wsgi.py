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

import sys
import time
import urllib
import socket
import cStringIO
import SocketServer
import BaseHTTPServer

from eventlet import api
from eventlet.httpdate import format_date_time

class HttpProtocol(BaseHTTPServer.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        self.server.log_message("%s - - [%s] %s" % (
            self.address_string(),
            self.log_date_time_string(),
            format % args))

    def handle_one_request(self):
        self.raw_requestline = self.rfile.readline()
    
        if not self.raw_requestline:
            self.close_connection = 1
            return

        if not self.parse_request():
            return

        self.environ = self.get_environ()
        try:
            self.handle_one_response()
        except socket.error, e:
            # Broken pipe, connection reset by peer
            if e[0] in (32, 54):
                pass
            else:
                raise

    def handle_one_response(self):
        headers_set = []
        headers_sent = []
        # set of lowercase header names that were sent
        header_dict = {}

        wfile = self.wfile
        num_blocks = None
        
        def write(data, _write=wfile.write):
            if not headers_set:
                raise AssertionError("write() before start_response()")
            elif not headers_sent:
                status, response_headers = headers_set
                headers_sent.append(1)
                for k, v in response_headers:
                    header_dict[k.lower()] = k
                _write('HTTP/1.0 %s\r\n' % status)
                # send Date header?
                if 'date' not in header_dict:
                    _write('Date: %s\r\n' % (format_date_time(time.time()),))
                if 'content-length' not in header_dict and num_blocks == 1:
                    _write('Content-Length: %s\r\n' % (len(data),))
                for header in response_headers:
                    _write('%s: %s\r\n' % header)
                _write('\r\n')
            _write(data)
                
        def start_request(status, response_headers, exc_info=None):
            if exc_info:
                try:
                    if headers_sent:
                        # Re-raise original exception if headers sent
                        raise exc_info[0], exc_info[1], exc_info[2]
                finally:
                    # Avoid dangling circular ref
                    exc_info = None
            elif headers_set:
                raise AssertionError("Headers already set!")

            headers_set[:] = [status, response_headers]
            return write

        result = self.server.app(self.environ, start_request)
        try:
            num_blocks = len(result)
        except (TypeError, AttributeError, NotImplementedError):
            pass
            
        try:
            for data in result:
                if data:
                    write(data)
            if not headers_sent:
                write('')
        finally:
            if hasattr(result, 'close'):
                result.close()

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

        return env

    def finish(self):
        # Override SocketServer.StreamRequestHandler.finish because
        # we only need to call close on the socket, not the makefile'd things
        
        self.request.close()


class Server(BaseHTTPServer.HTTPServer):
    def __init__(self, socket, address, app, log, environ=None):
        self.socket = socket
        self.address = address
        if log:
            self.log = log
            log.write = log.info
        else:
            self.log = sys.stderr
        self.app = app
        self.environ = environ

    def get_environ(self):
        socket = self.socket
        d = {
            'wsgi.input': socket,
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
        proto = HttpProtocol(socket, address, self)

    def log_message(self, message):
        self.log.write(message + '\n')


def server(socket, site, log=None, environ=None):
    serv = Server(socket, socket.getsockname(), site, log, environ=None)
    try:
        print "wsgi starting up on", socket.getsockname()
        while True:
            try:
                api.spawn(serv.process_request, socket.accept())
            except KeyboardInterrupt:
                api.get_hub().remove_descriptor(socket.fileno())
                print "wsgi exiting"
                break
    finally:
        socket.close()
