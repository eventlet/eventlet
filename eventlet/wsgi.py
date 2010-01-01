import errno
import os
import sys
import time
import traceback

from eventlet.green import urllib
from eventlet.green import socket
from eventlet.green import BaseHTTPServer
from eventlet.pool import Pool

import greenio

DEFAULT_MAX_SIMULTANEOUS_REQUESTS = 1024
DEFAULT_MAX_HTTP_VERSION = 'HTTP/1.1'
MAX_REQUEST_LINE = 8192
MINIMUM_CHUNK_SIZE = 4096

__all__ = ['server', 'format_date_time']

# Weekday and month names for HTTP date/time formatting; always English!
_weekdayname = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_monthname = [None, # Dummy so we can use 1-based month numbers
              "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def format_date_time(timestamp):
    """Formats a unix timestamp into an HTTP standard string."""
    year, month, day, hh, mm, ss, wd, y, z = time.gmtime(timestamp)
    return "%s, %02d %3s %4d %02d:%02d:%02d GMT" % (
        _weekdayname[wd], day, _monthname[month], year, hh, mm, ss
    )

class Input(object):
    def __init__(self, 
                 rfile, 
                 content_length, 
                 wfile=None, 
                 wfile_line=None,
                 chunked_input=False):
                 
        self.rfile = rfile
        if content_length is not None:
            content_length = int(content_length)
        self.content_length = content_length

        self.wfile = wfile
        self.wfile_line = wfile_line

        self.position = 0
        self.chunked_input = chunked_input
        self.chunk_length = -1

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
        try:
            read = reader(length)
        except greenio.SSL.ZeroReturnError:
            read = ''
        self.position += len(read)
        return read

    def _chunked_read(self, rfile, length=None):
        if self.wfile is not None:
            ## 100 Continue
            self.wfile.write(self.wfile_line)
            self.wfile = None
            self.wfile_line = None

        response = []
        try:
            if length is None:
                if self.chunk_length > self.position:
                    response.append(rfile.read(self.chunk_length - self.position))
                while self.chunk_length != 0:
                    self.chunk_length = int(rfile.readline(), 16)
                    response.append(rfile.read(self.chunk_length))
                    rfile.readline()
            else:
                while length > 0 and self.chunk_length != 0:
                    if self.chunk_length > self.position:
                        response.append(rfile.read(
                                min(self.chunk_length - self.position, length)))
                        length -= len(response[-1])
                        self.position += len(response[-1])
                        if self.chunk_length == self.position:
                            rfile.readline()
                    else:
                        self.chunk_length = int(rfile.readline(), 16)
                        self.position = 0
        except greenio.SSL.ZeroReturnError:
            pass
        return ''.join(response)

    def read(self, length=None):
        if self.chunked_input:
            return self._chunked_read(self.rfile, length)
        return self._do_read(self.rfile.read, length)

    def readline(self, size=None):
        return self._do_read(self.rfile.readline)

    def readlines(self, hint=None):
        return self._do_read(self.rfile.readlines, hint)

    def __iter__(self):
        return iter(self.read())


class HttpProtocol(BaseHTTPServer.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    minimum_chunk_size = MINIMUM_CHUNK_SIZE
    
    def setup(self):
        # overriding SocketServer.setup to correctly handle SSL.Connection objects
        conn = self.connection = self.request
        try:
            self.rfile = conn.makefile('rb', self.rbufsize)
            self.wfile = conn.makefile('wb', self.wbufsize)
        except (AttributeError, NotImplementedError):
            if hasattr(conn, 'send') and hasattr(conn, 'recv'):
                # it's an SSL.Connection
                self.rfile = socket._fileobject(conn, "rb", self.rbufsize)
                self.wfile = socket._fileobject(conn, "wb", self.wbufsize)
            else:
                # it's a SSLObject, or a martian
                raise NotImplementedError("wsgi.py doesn't support sockets "\
                                          "of type %s" % type(conn))

    def handle_one_request(self):
        if self.server.max_http_version:
            self.protocol_version = self.server.max_http_version

        if self.rfile.closed:
            self.close_connection = 1
            return

        try:
            self.raw_requestline = self.rfile.readline(MAX_REQUEST_LINE)
            if len(self.raw_requestline) == MAX_REQUEST_LINE:
                self.wfile.write(
                    "HTTP/1.0 414 Request URI Too Long\r\nConnection: close\r\nContent-length: 0\r\n\r\n")
                self.close_connection = 1
                return
        except greenio.SSL.ZeroReturnError:
            self.raw_requestline = ''
        except socket.error, e:
            if e[0] != errno.EBADF and e[0] != 10053:
                raise
            self.raw_requestline = ''

        if not self.raw_requestline:
            self.close_connection = 1
            return

        if not self.parse_request():
            return

        content_length = self.headers.getheader('content-length')
        if content_length:
            try:
                int(content_length)
            except ValueError:
                self.wfile.write(
                    "HTTP/1.0 400 Bad Request\r\n"
                    "Connection: close\r\nContent-length: 0\r\n\r\n")
                self.close_connection = 1
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

        wfile = self.wfile
        result = None
        use_chunked = [False]
        length = [0]
        status_code = [200]

        def write(data, _writelines=wfile.writelines):
            towrite = []
            if not headers_set:
                raise AssertionError("write() before start_response()")
            elif not headers_sent:
                status, response_headers = headers_set
                headers_sent.append(1)
                header_list = [header[0].lower() for header in response_headers]
                towrite.append('%s %s\r\n' % (self.protocol_version, status))
                for header in response_headers:
                    towrite.append('%s: %s\r\n' % header)

                # send Date header?
                if 'date' not in header_list:
                    towrite.append('Date: %s\r\n' % (format_date_time(time.time()),))
                if self.request_version == 'HTTP/1.0':
                    if self.headers.get('Connection', "").lower() == 'keep-alive':
                        towrite.append('Connection: keep-alive\r\n')
                        self.close_connection = 0
                    else:
                        towrite.append('Connection: close\r\n')
                        self.close_connection = 1
                elif 'content-length' not in header_list:
                    use_chunked[0] = True
                    towrite.append('Transfer-Encoding: chunked\r\n')
                towrite.append('\r\n')

            if use_chunked[0]:
                ## Write the chunked encoding
                towrite.append("%x\r\n%s\r\n" % (len(data), data))
            else:
                towrite.append(data)
            try:
                _writelines(towrite)
                length[0] = length[0] + sum(map(len, towrite))
            except UnicodeEncodeError:
                print "Encountered unicode while attempting to write wsgi response: ", [x for x in towrite if isinstance(x, unicode)]
                traceback.print_exc()
                _writelines(
                    ["HTTP/1.0 500 Internal Server Error\r\n",
                    "Connection: close\r\n",
                    "Content-type: text/plain\r\n",
                    "Content-length: 98\r\n",
                    "\r\n",
                    "Internal Server Error: wsgi application passed a unicode object to the server instead of a string."])

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
            try:
                result = self.application(self.environ, start_response)
                if not headers_sent and hasattr(result, '__len__') and \
                        'Content-Length' not in [h for h, v in headers_set[1]]:
                    headers_set[1].append(('Content-Length', str(sum(map(len, result)))))
                towrite = []
                towrite_size = 0
                for data in result:
                    towrite.append(data)
                    towrite_size += len(data)
                    if towrite_size >= self.minimum_chunk_size:
                        write(''.join(towrite))
                        towrite = []
                        towrite_size = 0
                if towrite:
                    write(''.join(towrite))
                if not headers_sent or use_chunked[0]:
                    write('')
            except Exception, e:
                self.close_connection = 1
                exc = traceback.format_exc()
                print exc
                if not headers_set:
                    start_response("500 Internal Server Error", [('Content-type', 'text/plain')])
                    write(exc)
        finally:
            if hasattr(result, 'close'):
                result.close()
            if self.environ['eventlet.input'].position < self.environ.get('CONTENT_LENGTH', 0):
                ## Read and discard body
                self.environ['eventlet.input'].read()
            finish = time.time()

            self.server.log_message('%s - - [%s] "%s" %s %s %.6f' % (
                self.get_client_ip(),
                self.log_date_time_string(),
                self.requestline,
                status_code[0],
                length[0],
                finish - start))
                
    def get_client_ip(self):
        client_ip = self.client_address[0]
        if self.server.log_x_forwarded_for:
            forward = self.headers.get('X-Forwarded-For', '').replace(' ', '')
            if forward:
                client_ip = "%s,%s" % (forward, client_ip)
        return client_ip

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
        chunked = env.get('HTTP_TRANSFER_ENCODING', '').lower() == 'chunked'
        env['wsgi.input'] = env['eventlet.input'] = Input(
            self.rfile, length, wfile=wfile, wfile_line=wfile_line,
            chunked_input=chunked)

        return env

    def finish(self):
        BaseHTTPServer.BaseHTTPRequestHandler.finish(self)
        greenio.shutdown_safe(self.connection)
        self.connection.close()


class Server(BaseHTTPServer.HTTPServer):
    def __init__(self, 
                 socket, 
                 address, 
                 app, 
                 log=None, 
                 environ=None, 
                 max_http_version=None, 
                 protocol=HttpProtocol, 
                 minimum_chunk_size=None,
                 log_x_forwarded_for=True):
                 
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
        if minimum_chunk_size is not None:
            protocol.minimum_chunk_size = minimum_chunk_size
        self.log_x_forwarded_for = log_x_forwarded_for

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


def server(sock, site, 
           log=None, 
           environ=None, 
           max_size=None,
           max_http_version=DEFAULT_MAX_HTTP_VERSION, 
           protocol=HttpProtocol,
           server_event=None, 
           minimum_chunk_size=None,
           log_x_forwarded_for=True,
           custom_pool=None):
    """  Start up a `WSGI <http://wsgi.org/wsgi/>`_ server handling requests from the supplied server 
    socket.  This function loops forever.
    
    :param sock: Server socket, must be already bound to a port and listening.
    :param site: WSGI application function.
    :param log: File-like object that logs should be written to.  If not specified, sys.stderr is used.
    :param environ: Additional parameters that go into the environ dictionary of every request.
    :param max_size: Maximum number of client connections opened at any time by this server.
    :param protocol: Protocol class.  Deprecated.
    :param server_event: Used to collect the Server object.  Deprecated.
    :param minimum_chunk_size: Minimum size for http chunks, which can be used to improve performance of applications which yield many small strings, though it technically violates the WSGI spec.
    :param log_x_forwarded_for: If True (the default), logs all ip addresses found in the x-forwarded-for header in addition to the actual client ip address.
    """

    serv = Server(sock, sock.getsockname(), 
                  site, log, 
                  environ=None, 
                  max_http_version=max_http_version, 
                  protocol=protocol, 
                  minimum_chunk_size=minimum_chunk_size,
                  log_x_forwarded_for=log_x_forwarded_for)
    if server_event is not None:
        server_event.send(serv)
    if max_size is None:
        max_size = DEFAULT_MAX_SIMULTANEOUS_REQUESTS
    if custom_pool is not None:
        pool = custom_pool
    else:
        pool = Pool(max_size=max_size)
    try:
        host, port = sock.getsockname()
        port = ':%s' % (port, )
        if hasattr(sock, 'do_handshake'):
            scheme = 'https'
            if port == ':443':
                port = ''
        else:
            scheme = 'http'
            if port == ':80':
                port = ''

        serv.log.write("(%s) wsgi starting up on %s://%s%s/\n" % (os.getpid(), scheme, host, port))
        while True:
            try:
                try:
                    client_socket = sock.accept()
                except socket.error, e:
                    if e[0] != errno.EPIPE and e[0] != errno.EBADF:
                        raise
                pool.execute_async(serv.process_request, client_socket)
            except (KeyboardInterrupt, SystemExit):
                serv.log.write("wsgi exiting\n")
                break
    finally:
        try:
            greenio.shutdown_safe(sock)
            sock.close()
        except socket.error, e:
            if e[0] != errno.EPIPE:
                traceback.print_exc()

