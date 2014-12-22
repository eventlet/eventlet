import cgi
import collections
import errno
import os
import signal
import socket
import sys
import traceback
import unittest

import eventlet
from eventlet import debug
from eventlet import event
from eventlet.green import socket as greensocket
from eventlet.green import ssl
from eventlet.green import subprocess
from eventlet import greenio
from eventlet import greenthread
from eventlet import support
from eventlet.support import bytes_to_str, capture_stderr, six
from eventlet import tpool
from eventlet import wsgi

import tests


certificate_file = os.path.join(os.path.dirname(__file__), 'test_server.crt')
private_key_file = os.path.join(os.path.dirname(__file__), 'test_server.key')


HttpReadResult = collections.namedtuple(
    'HttpReadResult',
    'status headers_lower body headers_original')


def hello_world(env, start_response):
    if env['PATH_INFO'] == 'notexist':
        start_response('404 Not Found', [('Content-type', 'text/plain')])
        return [b"not found"]

    start_response('200 OK', [('Content-type', 'text/plain')])
    return [b"hello world"]


def chunked_app(env, start_response):
    start_response('200 OK', [('Content-type', 'text/plain')])
    yield b"this"
    yield b"is"
    yield b"chunked"


def chunked_fail_app(environ, start_response):
    """http://rhodesmill.org/brandon/2013/chunked-wsgi/
    """
    headers = [('Content-Type', 'text/plain')]
    start_response('200 OK', headers)

    # We start streaming data just fine.
    yield b"The dwarves of yore made mighty spells,"
    yield b"While hammers fell like ringing bells"

    # Then the back-end fails!
    try:
        1 / 0
    except Exception:
        start_response('500 Error', headers, sys.exc_info())
        return

    # So rest of the response data is not available.
    yield b"In places deep, where dark things sleep,"
    yield b"In hollow halls beneath the fells."


def big_chunks(env, start_response):
    start_response('200 OK', [('Content-type', 'text/plain')])
    line = b'a' * 8192
    for x in range(10):
        yield line


def use_write(env, start_response):
    if env['PATH_INFO'] == '/a':
        write = start_response('200 OK', [('Content-type', 'text/plain'),
                                          ('Content-Length', '5')])
        write(b'abcde')
    if env['PATH_INFO'] == '/b':
        write = start_response('200 OK', [('Content-type', 'text/plain')])
        write(b'abcde')
    return []


def chunked_post(env, start_response):
    start_response('200 OK', [('Content-type', 'text/plain')])
    if env['PATH_INFO'] == '/a':
        return [env['wsgi.input'].read()]
    elif env['PATH_INFO'] == '/b':
        return [x for x in iter(lambda: env['wsgi.input'].read(4096), b'')]
    elif env['PATH_INFO'] == '/c':
        return [x for x in iter(lambda: env['wsgi.input'].read(1), b'')]


def already_handled(env, start_response):
    start_response('200 OK', [('Content-type', 'text/plain')])
    return wsgi.ALREADY_HANDLED


class Site(object):
    def __init__(self):
        self.application = hello_world

    def __call__(self, env, start_response):
        return self.application(env, start_response)


class IterableApp(object):

    def __init__(self, send_start_response=False, return_val=wsgi.ALREADY_HANDLED):
        self.send_start_response = send_start_response
        self.return_val = return_val
        self.env = {}

    def __call__(self, env, start_response):
        self.env = env
        if self.send_start_response:
            start_response('200 OK', [('Content-type', 'text/plain')])
        return self.return_val


class IterableSite(Site):
    def __call__(self, env, start_response):
        it = self.application(env, start_response)
        for i in it:
            yield i


CONTENT_LENGTH = 'content-length'


"""
HTTP/1.1 200 OK
Date: foo
Content-length: 11

hello world
"""


def recvall(socket_):
    result = b''
    while True:
        chunk = socket_.recv()
        result += chunk
        if chunk == b'':
            break

    return result


class ConnectionClosed(Exception):
    pass


def send_expect_close(sock, buf):
    # Some tests will induce behavior that causes the remote end to
    # close the connection before all of the data has been written.
    # With small kernel buffer sizes, this can cause an EPIPE error.
    # Since the test expects an early close, this can be ignored.
    try:
        sock.sendall(buf)
    except socket.error as exc:
        if support.get_errno(exc) != errno.EPIPE:
            raise


def read_http(sock):
    fd = sock.makefile('rb')
    try:
        response_line = bytes_to_str(fd.readline().rstrip(b'\r\n'))
    except socket.error as exc:
        # TODO find out whether 54 is ok here or not, I see it when running tests
        # on Python 3
        if support.get_errno(exc) in (10053, 54):
            raise ConnectionClosed
        raise
    if not response_line:
        raise ConnectionClosed(response_line)

    header_lines = []
    while True:
        line = fd.readline()
        if line == b'\r\n':
            break
        else:
            header_lines.append(line)

    headers_original = {}
    headers_lower = {}
    for x in header_lines:
        x = x.strip()
        if not x:
            continue
        key, value = bytes_to_str(x).split(':', 1)
        key = key.rstrip()
        value = value.lstrip()
        key_lower = key.lower()
        # FIXME: Duplicate headers are allowed as per HTTP RFC standard,
        # the client and/or intermediate proxies are supposed to treat them
        # as a single header with values concatenated using space (' ') delimiter.
        assert key_lower not in headers_lower, "header duplicated: {0}".format(key)
        headers_original[key] = value
        headers_lower[key_lower] = value

    content_length_str = headers_lower.get(CONTENT_LENGTH.lower(), '')
    if content_length_str:
        num = int(content_length_str)
        body = fd.read(num)
    else:
        # read until EOF
        body = fd.read()

    result = HttpReadResult(
        status=response_line,
        headers_lower=headers_lower,
        body=body,
        headers_original=headers_original)
    return result


class _TestBase(tests.LimitedTestCase):
    def setUp(self):
        super(_TestBase, self).setUp()
        self.logfile = six.StringIO()
        self.site = Site()
        self.killer = None
        self.set_site()
        self.spawn_server()

    def tearDown(self):
        greenthread.kill(self.killer)
        eventlet.sleep(0)
        super(_TestBase, self).tearDown()

    def spawn_server(self, **kwargs):
        """Spawns a new wsgi server with the given arguments using
        :meth:`spawn_thread`.

        Sets self.port to the port of the server
        """
        new_kwargs = dict(max_size=128,
                          log=self.logfile,
                          site=self.site)
        new_kwargs.update(kwargs)

        if 'sock' not in new_kwargs:
            new_kwargs['sock'] = eventlet.listen(('localhost', 0))

        self.port = new_kwargs['sock'].getsockname()[1]
        self.spawn_thread(wsgi.server, **new_kwargs)

    def spawn_thread(self, target, **kwargs):
        """Spawns a new greenthread using specified target and arguments.

        Kills any previously-running server and sets self.killer to the
        greenthread running the target.
        """
        eventlet.sleep(0)  # give previous server a chance to start
        if self.killer:
            greenthread.kill(self.killer)

        self.killer = eventlet.spawn_n(target, **kwargs)

    def set_site(self):
        raise NotImplementedError


class TestHttpd(_TestBase):
    def set_site(self):
        self.site = Site()

    def test_001_server(self):
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
        fd.flush()
        result = fd.read()
        fd.close()
        # The server responds with the maximum version it supports
        assert result.startswith(b'HTTP'), result
        assert result.endswith(b'hello world'), result

    def test_002_keepalive(self):
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('wb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fd.flush()
        read_http(sock)
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fd.flush()
        read_http(sock)
        fd.close()
        sock.close()

    def test_003_passing_non_int_to_read(self):
        # This should go in greenio_test
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fd.flush()
        cancel = eventlet.Timeout(1, RuntimeError)
        self.assertRaises(TypeError, fd.read, "This shouldn't work")
        cancel.cancel()
        fd.close()

    def test_004_close_keepalive(self):
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('wb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fd.flush()
        read_http(sock)
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        fd.flush()
        read_http(sock)
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fd.flush()
        self.assertRaises(ConnectionClosed, read_http, sock)
        fd.close()

    @tests.skipped
    def test_005_run_apachebench(self):
        url = 'http://localhost:12346/'
        # ab is apachebench
        subprocess.call(
            [tests.find_command('ab'), '-c', '64', '-n', '1024', '-k', url],
            stdout=subprocess.PIPE)

    def test_006_reject_long_urls(self):
        sock = eventlet.connect(
            ('localhost', self.port))
        path_parts = []
        for ii in range(3000):
            path_parts.append('path')
        path = '/'.join(path_parts)
        request = 'GET /%s HTTP/1.0\r\nHost: localhost\r\n\r\n' % path
        send_expect_close(sock, request.encode())
        fd = sock.makefile('rb')
        result = fd.readline()
        if result:
            # windows closes the socket before the data is flushed,
            # so we never get anything back
            status = result.split(b' ')[1]
            self.assertEqual(status, b'414')
        fd.close()

    def test_007_get_arg(self):
        # define a new handler that does a get_arg as well as a read_body
        def new_app(env, start_response):
            body = bytes_to_str(env['wsgi.input'].read())
            a = cgi.parse_qs(body).get('a', [1])[0]
            start_response('200 OK', [('Content-type', 'text/plain')])
            return [six.b('a is %s, body is %s' % (a, body))]

        self.site.application = new_app
        sock = eventlet.connect(
            ('localhost', self.port))
        request = '\r\n'.join((
            'POST / HTTP/1.0',
            'Host: localhost',
            'Content-Length: 3',
            '',
            'a=a'))
        fd = sock.makefile('wb')
        fd.write(request.encode())
        fd.flush()

        # send some junk after the actual request
        fd.write(b'01234567890123456789')
        result = read_http(sock)
        self.assertEqual(result.body, b'a is a, body is a=a')
        fd.close()

    def test_008_correctresponse(self):
        sock = eventlet.connect(('localhost', self.port))

        fd = sock.makefile('wb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fd.flush()
        result_200 = read_http(sock)
        fd.write(b'GET /notexist HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fd.flush()
        read_http(sock)
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fd.flush()
        result_test = read_http(sock)
        self.assertEqual(result_200.status, result_test.status)
        fd.close()
        sock.close()

    def test_009_chunked_response(self):
        self.site.application = chunked_app
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        fd.flush()
        assert b'Transfer-Encoding: chunked' in fd.read()

    def test_010_no_chunked_http_1_0(self):
        self.site.application = chunked_app
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        fd.flush()
        assert b'Transfer-Encoding: chunked' not in fd.read()

    def test_011_multiple_chunks(self):
        self.site.application = big_chunks
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        fd.flush()
        headers = b''
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                headers += line
        assert b'Transfer-Encoding: chunked' in headers
        chunks = 0
        chunklen = int(fd.readline(), 16)
        while chunklen:
            chunks += 1
            fd.read(chunklen)
            fd.readline()  # CRLF
            chunklen = int(fd.readline(), 16)
        assert chunks > 1
        response = fd.read()
        # Require a CRLF to close the message body
        self.assertEqual(response, b'\r\n')

    @tests.skip_if_no_ssl
    def test_012_ssl_server(self):
        def wsgi_app(environ, start_response):
            start_response('200 OK', {})
            return [environ['wsgi.input'].read()]

        certificate_file = os.path.join(os.path.dirname(__file__), 'test_server.crt')
        private_key_file = os.path.join(os.path.dirname(__file__), 'test_server.key')

        server_sock = eventlet.wrap_ssl(eventlet.listen(('localhost', 0)),
                                        certfile=certificate_file,
                                        keyfile=private_key_file,
                                        server_side=True)
        self.spawn_server(sock=server_sock, site=wsgi_app)

        sock = eventlet.connect(('localhost', self.port))
        sock = eventlet.wrap_ssl(sock)
        sock.write(
            b'POST /foo HTTP/1.1\r\nHost: localhost\r\n'
            b'Connection: close\r\nContent-length:3\r\n\r\nabc')
        result = recvall(sock)
        assert result.endswith(b'abc')

    @tests.skip_if_no_ssl
    def test_013_empty_return(self):
        def wsgi_app(environ, start_response):
            start_response("200 OK", [])
            return [b""]

        certificate_file = os.path.join(os.path.dirname(__file__), 'test_server.crt')
        private_key_file = os.path.join(os.path.dirname(__file__), 'test_server.key')
        server_sock = eventlet.wrap_ssl(eventlet.listen(('localhost', 0)),
                                        certfile=certificate_file,
                                        keyfile=private_key_file,
                                        server_side=True)
        self.spawn_server(sock=server_sock, site=wsgi_app)

        sock = eventlet.connect(('localhost', server_sock.getsockname()[1]))
        sock = eventlet.wrap_ssl(sock)
        sock.write(b'GET /foo HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        result = recvall(sock)
        assert result[-4:] == b'\r\n\r\n'

    def test_014_chunked_post(self):
        self.site.application = chunked_post
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write('PUT /a HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n'
                 'Transfer-Encoding: chunked\r\n\r\n'
                 '2\r\noh\r\n4\r\n hai\r\n0\r\n\r\n'.encode())
        fd.flush()
        while True:
            if fd.readline() == b'\r\n':
                break
        response = fd.read()
        assert response == b'oh hai', 'invalid response %s' % response

        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write('PUT /b HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n'
                 'Transfer-Encoding: chunked\r\n\r\n'
                 '2\r\noh\r\n4\r\n hai\r\n0\r\n\r\n'.encode())
        fd.flush()
        while True:
            if fd.readline() == b'\r\n':
                break
        response = fd.read()
        assert response == b'oh hai', 'invalid response %s' % response

        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write('PUT /c HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n'
                 'Transfer-Encoding: chunked\r\n\r\n'
                 '2\r\noh\r\n4\r\n hai\r\n0\r\n\r\n'.encode())
        fd.flush()
        while True:
            if fd.readline() == b'\r\n':
                break
        response = fd.read(8192)
        assert response == b'oh hai', 'invalid response %s' % response

    def test_015_write(self):
        self.site.application = use_write
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('wb')
        fd.write(b'GET /a HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        fd.flush()
        result1 = read_http(sock)
        assert 'content-length' in result1.headers_lower

        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('wb')
        fd.write(b'GET /b HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        fd.flush()
        result2 = read_http(sock)
        assert 'transfer-encoding' in result2.headers_lower
        assert result2.headers_lower['transfer-encoding'] == 'chunked'

    def test_016_repeated_content_length(self):
        """content-length header was being doubled up if it was set in
        start_response and could also be inferred from the iterator
        """
        def wsgi_app(environ, start_response):
            start_response('200 OK', [('Content-Length', '7')])
            return [b'testing']
        self.site.application = wsgi_app
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'GET /a HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        fd.flush()
        header_lines = []
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                header_lines.append(line)
        self.assertEqual(1, len(
            [l for l in header_lines if l.lower().startswith(b'content-length')]))

    @tests.skip_if_no_ssl
    def test_017_ssl_zeroreturnerror(self):

        def server(sock, site, log):
            try:
                serv = wsgi.Server(sock, sock.getsockname(), site, log)
                client_socket = sock.accept()
                serv.process_request(client_socket)
                return True
            except Exception:
                traceback.print_exc()
                return False

        def wsgi_app(environ, start_response):
            start_response('200 OK', [])
            return [environ['wsgi.input'].read()]

        certificate_file = os.path.join(os.path.dirname(__file__), 'test_server.crt')
        private_key_file = os.path.join(os.path.dirname(__file__), 'test_server.key')

        sock = eventlet.wrap_ssl(
            eventlet.listen(('localhost', 0)),
            certfile=certificate_file, keyfile=private_key_file,
            server_side=True)
        server_coro = eventlet.spawn(server, sock, wsgi_app, self.logfile)

        client = eventlet.connect(('localhost', sock.getsockname()[1]))
        client = eventlet.wrap_ssl(client)
        client.write(b'X')  # non-empty payload so that SSL handshake occurs
        greenio.shutdown_safe(client)
        client.close()

        success = server_coro.wait()
        assert success

    def test_018_http_10_keepalive(self):
        # verify that if an http/1.0 client sends connection: keep-alive
        # that we don't close the connection
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('wb')
        fd.write(b'GET / HTTP/1.0\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n')
        fd.flush()

        result1 = read_http(sock)
        assert 'connection' in result1.headers_lower
        self.assertEqual('keep-alive', result1.headers_lower['connection'])
        # repeat request to verify connection is actually still open
        fd.write(b'GET / HTTP/1.0\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n')
        fd.flush()
        result2 = read_http(sock)
        assert 'connection' in result2.headers_lower
        self.assertEqual('keep-alive', result2.headers_lower['connection'])
        sock.close()

    def test_019_fieldstorage_compat(self):
        def use_fieldstorage(environ, start_response):
            cgi.FieldStorage(fp=environ['wsgi.input'], environ=environ)
            start_response('200 OK', [('Content-type', 'text/plain')])
            return [b'hello!']

        self.site.application = use_fieldstorage
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('rwb')
        fd.write('POST / HTTP/1.1\r\n'
                 'Host: localhost\r\n'
                 'Connection: close\r\n'
                 'Transfer-Encoding: chunked\r\n\r\n'
                 '2\r\noh\r\n'
                 '4\r\n hai\r\n0\r\n\r\n'.encode())
        fd.flush()
        assert b'hello!' in fd.read()

    def test_020_x_forwarded_for(self):
        request_bytes = (
            b'GET / HTTP/1.1\r\nHost: localhost\r\n'
            + b'X-Forwarded-For: 1.2.3.4, 5.6.7.8\r\n\r\n'
        )

        sock = eventlet.connect(('localhost', self.port))
        sock.sendall(request_bytes)
        sock.recv(1024)
        sock.close()
        assert '1.2.3.4,5.6.7.8,127.0.0.1' in self.logfile.getvalue()

        # turning off the option should work too
        self.logfile = six.StringIO()
        self.spawn_server(log_x_forwarded_for=False)

        sock = eventlet.connect(('localhost', self.port))
        sock.sendall(request_bytes)
        sock.recv(1024)
        sock.close()
        assert '1.2.3.4' not in self.logfile.getvalue()
        assert '5.6.7.8' not in self.logfile.getvalue()
        assert '127.0.0.1' in self.logfile.getvalue()

    def test_socket_remains_open(self):
        greenthread.kill(self.killer)
        server_sock = eventlet.listen(('localhost', 0))
        server_sock_2 = server_sock.dup()
        self.spawn_server(sock=server_sock_2)
        # do a single req/response to verify it's up
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
        fd.flush()
        result = fd.read(1024)
        fd.close()
        assert result.startswith(b'HTTP'), result
        assert result.endswith(b'hello world'), result

        # shut down the server and verify the server_socket fd is still open,
        # but the actual socketobject passed in to wsgi.server is closed
        greenthread.kill(self.killer)
        eventlet.sleep(0)  # make the kill go through
        try:
            server_sock_2.accept()
            # shouldn't be able to use this one anymore
        except socket.error as exc:
            self.assertEqual(support.get_errno(exc), errno.EBADF)
        self.spawn_server(sock=server_sock)
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
        fd.flush()
        result = fd.read(1024)
        fd.close()
        assert result.startswith(b'HTTP'), result
        assert result.endswith(b'hello world'), result

    def test_021_environ_clobbering(self):
        def clobberin_time(environ, start_response):
            for environ_var in [
                    'wsgi.version', 'wsgi.url_scheme',
                    'wsgi.input', 'wsgi.errors', 'wsgi.multithread',
                    'wsgi.multiprocess', 'wsgi.run_once', 'REQUEST_METHOD',
                    'SCRIPT_NAME', 'RAW_PATH_INFO', 'PATH_INFO', 'QUERY_STRING',
                    'CONTENT_TYPE', 'CONTENT_LENGTH', 'SERVER_NAME', 'SERVER_PORT',
                    'SERVER_PROTOCOL']:
                environ[environ_var] = None
            start_response('200 OK', [('Content-type', 'text/plain')])
            return []
        self.site.application = clobberin_time
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write('GET / HTTP/1.1\r\n'
                 'Host: localhost\r\n'
                 'Connection: close\r\n'
                 '\r\n\r\n'.encode())
        fd.flush()
        assert b'200 OK' in fd.read()

    def test_022_custom_pool(self):
        # just test that it accepts the parameter for now
        # TODO(waitall): test that it uses the pool and that you can waitall() to
        # ensure that all clients finished
        p = eventlet.GreenPool(5)
        self.spawn_server(custom_pool=p)

        # this stuff is copied from test_001_server, could be better factored
        sock = eventlet.connect(
            ('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
        fd.flush()
        result = fd.read()
        fd.close()
        assert result.startswith(b'HTTP'), result
        assert result.endswith(b'hello world'), result

    def test_023_bad_content_length(self):
        sock = eventlet.connect(
            ('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.0\r\nHost: localhost\r\nContent-length: argh\r\n\r\n')
        fd.flush()
        result = fd.read()
        fd.close()
        assert result.startswith(b'HTTP'), result
        assert b'400 Bad Request' in result, result
        assert b'500' not in result, result

    def test_024_expect_100_continue(self):
        def wsgi_app(environ, start_response):
            if int(environ['CONTENT_LENGTH']) > 1024:
                start_response('417 Expectation Failed', [('Content-Length', '7')])
                return [b'failure']
            else:
                text = environ['wsgi.input'].read()
                start_response('200 OK', [('Content-Length', str(len(text)))])
                return [text]
        self.site.application = wsgi_app
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'PUT / HTTP/1.1\r\nHost: localhost\r\nContent-length: 1025\r\n'
                 b'Expect: 100-continue\r\n\r\n')
        fd.flush()
        result = read_http(sock)
        self.assertEqual(result.status, 'HTTP/1.1 417 Expectation Failed')
        self.assertEqual(result.body, b'failure')
        fd.write(
            b'PUT / HTTP/1.1\r\nHost: localhost\r\nContent-length: 7\r\n'
            b'Expect: 100-continue\r\n\r\ntesting')
        fd.flush()
        header_lines = []
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                header_lines.append(line)
        assert header_lines[0].startswith(b'HTTP/1.1 100 Continue')
        header_lines = []
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                header_lines.append(line)
        assert header_lines[0].startswith(b'HTTP/1.1 200 OK')
        assert fd.read(7) == b'testing'
        fd.close()
        sock.close()

    def test_024a_expect_100_continue_with_headers(self):
        def wsgi_app(environ, start_response):
            if int(environ['CONTENT_LENGTH']) > 1024:
                start_response('417 Expectation Failed', [('Content-Length', '7')])
                return [b'failure']
            else:
                environ['wsgi.input'].set_hundred_continue_response_headers(
                    [('Hundred-Continue-Header-1', 'H1'),
                     ('Hundred-Continue-Header-2', 'H2'),
                     ('Hundred-Continue-Header-k', 'Hk')])
                text = environ['wsgi.input'].read()
                start_response('200 OK', [('Content-Length', str(len(text)))])
                return [text]
        self.site.application = wsgi_app
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'PUT / HTTP/1.1\r\nHost: localhost\r\nContent-length: 1025\r\n'
                 b'Expect: 100-continue\r\n\r\n')
        fd.flush()
        result = read_http(sock)
        self.assertEqual(result.status, 'HTTP/1.1 417 Expectation Failed')
        self.assertEqual(result.body, b'failure')
        fd.write(
            b'PUT / HTTP/1.1\r\nHost: localhost\r\nContent-length: 7\r\n'
            b'Expect: 100-continue\r\n\r\ntesting')
        fd.flush()
        header_lines = []
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                header_lines.append(line.strip())
        assert header_lines[0].startswith(b'HTTP/1.1 100 Continue')
        headers = dict((k, v) for k, v in (h.split(b': ', 1) for h in header_lines[1:]))
        assert b'Hundred-Continue-Header-1' in headers
        assert b'Hundred-Continue-Header-2' in headers
        assert b'Hundred-Continue-Header-K' in headers
        self.assertEqual(b'H1', headers[b'Hundred-Continue-Header-1'])
        self.assertEqual(b'H2', headers[b'Hundred-Continue-Header-2'])
        self.assertEqual(b'Hk', headers[b'Hundred-Continue-Header-K'])
        header_lines = []
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                header_lines.append(line)
        assert header_lines[0].startswith(b'HTTP/1.1 200 OK')
        self.assertEqual(fd.read(7), b'testing')
        fd.close()
        sock.close()

    def test_024b_expect_100_continue_with_headers_multiple_chunked(self):
        def wsgi_app(environ, start_response):
            environ['wsgi.input'].set_hundred_continue_response_headers(
                [('Hundred-Continue-Header-1', 'H1'),
                 ('Hundred-Continue-Header-2', 'H2')])
            text = environ['wsgi.input'].read()

            environ['wsgi.input'].set_hundred_continue_response_headers(
                [('Hundred-Continue-Header-3', 'H3')])
            environ['wsgi.input'].send_hundred_continue_response()

            text += environ['wsgi.input'].read()

            start_response('200 OK', [('Content-Length', str(len(text)))])
            return [text]
        self.site.application = wsgi_app
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'PUT /a HTTP/1.1\r\n'
                 b'Host: localhost\r\nConnection: close\r\n'
                 b'Transfer-Encoding: chunked\r\n'
                 b'Expect: 100-continue\r\n\r\n')
        fd.flush()

        # Expect 1st 100-continue response
        header_lines = []
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                header_lines.append(line.strip())
        assert header_lines[0].startswith(b'HTTP/1.1 100 Continue')
        headers = dict((k, v) for k, v in (h.split(b': ', 1)
                                           for h in header_lines[1:]))
        assert b'Hundred-Continue-Header-1' in headers
        assert b'Hundred-Continue-Header-2' in headers
        self.assertEqual(b'H1', headers[b'Hundred-Continue-Header-1'])
        self.assertEqual(b'H2', headers[b'Hundred-Continue-Header-2'])

        # Send message 1
        fd.write(b'5\r\nfirst\r\n8\r\n message\r\n0\r\n\r\n')
        fd.flush()

        # Expect a 2nd 100-continue response
        header_lines = []
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                header_lines.append(line.strip())
        assert header_lines[0].startswith(b'HTTP/1.1 100 Continue')
        headers = dict((k, v) for k, v in (h.split(b': ', 1)
                                           for h in header_lines[1:]))
        assert b'Hundred-Continue-Header-3' in headers
        self.assertEqual(b'H3', headers[b'Hundred-Continue-Header-3'])

        # Send message 2
        fd.write(b'8\r\n, second\r\n8\r\n message\r\n0\r\n\r\n')
        fd.flush()

        # Expect final 200-OK
        header_lines = []
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                header_lines.append(line.strip())
        assert header_lines[0].startswith(b'HTTP/1.1 200 OK')

        self.assertEqual(fd.read(29), b'first message, second message')
        fd.close()
        sock.close()

    def test_024c_expect_100_continue_with_headers_multiple_nonchunked(self):
        def wsgi_app(environ, start_response):

            environ['wsgi.input'].set_hundred_continue_response_headers(
                [('Hundred-Continue-Header-1', 'H1'),
                 ('Hundred-Continue-Header-2', 'H2')])
            text = environ['wsgi.input'].read(13)

            environ['wsgi.input'].set_hundred_continue_response_headers(
                [('Hundred-Continue-Header-3', 'H3')])
            environ['wsgi.input'].send_hundred_continue_response()

            text += environ['wsgi.input'].read(16)

            start_response('200 OK', [('Content-Length', str(len(text)))])
            return [text]

        self.site.application = wsgi_app
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'PUT /a HTTP/1.1\r\n'
                 b'Host: localhost\r\nConnection: close\r\n'
                 b'Content-Length: 29\r\n'
                 b'Expect: 100-continue\r\n\r\n')
        fd.flush()

        # Expect 1st 100-continue response
        header_lines = []
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                header_lines.append(line.strip())
        assert header_lines[0].startswith(b'HTTP/1.1 100 Continue')
        headers = dict((k, v) for k, v in (h.split(b': ', 1)
                                           for h in header_lines[1:]))
        assert b'Hundred-Continue-Header-1' in headers
        assert b'Hundred-Continue-Header-2' in headers
        self.assertEqual(b'H1', headers[b'Hundred-Continue-Header-1'])
        self.assertEqual(b'H2', headers[b'Hundred-Continue-Header-2'])

        # Send message 1
        fd.write(b'first message')
        fd.flush()

        # Expect a 2nd 100-continue response
        header_lines = []
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                header_lines.append(line.strip())
        assert header_lines[0].startswith(b'HTTP/1.1 100 Continue')
        headers = dict((k, v) for k, v in (h.split(b': ', 1)
                                           for h in header_lines[1:]))
        assert b'Hundred-Continue-Header-3' in headers
        self.assertEqual(b'H3', headers[b'Hundred-Continue-Header-3'])

        # Send message 2
        fd.write(b', second message\r\n')
        fd.flush()

        # Expect final 200-OK
        header_lines = []
        while True:
            line = fd.readline()
            if line == b'\r\n':
                break
            else:
                header_lines.append(line.strip())
        assert header_lines[0].startswith(b'HTTP/1.1 200 OK')

        self.assertEqual(fd.read(29), b'first message, second message')
        fd.close()
        sock.close()

    def test_025_accept_errors(self):
        debug.hub_exceptions(True)
        listener = greensocket.socket()
        listener.bind(('localhost', 0))
        # NOT calling listen, to trigger the error
        with capture_stderr() as log:
            self.spawn_server(sock=listener)
            eventlet.sleep(0)  # need to enter server loop
            try:
                eventlet.connect(('localhost', self.port))
                self.fail("Didn't expect to connect")
            except socket.error as exc:
                self.assertEqual(support.get_errno(exc), errno.ECONNREFUSED)

        log_content = log.getvalue()
        assert 'Invalid argument' in log_content, log_content
        debug.hub_exceptions(False)

    def test_026_log_format(self):
        self.spawn_server(log_format="HI %(request_line)s HI")
        sock = eventlet.connect(('localhost', self.port))
        sock.sendall(b'GET /yo! HTTP/1.1\r\nHost: localhost\r\n\r\n')
        sock.recv(1024)
        sock.close()
        assert '\nHI GET /yo! HTTP/1.1 HI\n' in self.logfile.getvalue(), self.logfile.getvalue()

    def test_close_chunked_with_1_0_client(self):
        # verify that if we return a generator from our app
        # and we're not speaking with a 1.1 client, that we
        # close the connection
        self.site.application = chunked_app
        sock = eventlet.connect(('localhost', self.port))

        sock.sendall(b'GET / HTTP/1.0\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n')

        result = read_http(sock)
        self.assertEqual(result.headers_lower['connection'], 'close')
        self.assertNotEqual(result.headers_lower.get('transfer-encoding'), 'chunked')
        self.assertEqual(result.body, b"thisischunked")

    def test_minimum_chunk_size_parameter_leaves_httpprotocol_class_member_intact(self):
        start_size = wsgi.HttpProtocol.minimum_chunk_size

        self.spawn_server(minimum_chunk_size=start_size * 2)
        sock = eventlet.connect(('localhost', self.port))
        sock.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        read_http(sock)

        self.assertEqual(wsgi.HttpProtocol.minimum_chunk_size, start_size)
        sock.close()

    def test_error_in_chunked_closes_connection(self):
        # From http://rhodesmill.org/brandon/2013/chunked-wsgi/
        self.spawn_server(minimum_chunk_size=1)

        self.site.application = chunked_fail_app
        sock = eventlet.connect(('localhost', self.port))

        sock.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')

        result = read_http(sock)
        self.assertEqual(result.status, 'HTTP/1.1 200 OK')
        self.assertEqual(result.headers_lower.get('transfer-encoding'), 'chunked')
        expected_body = (
            b'27\r\nThe dwarves of yore made mighty spells,\r\n'
            b'25\r\nWhile hammers fell like ringing bells\r\n')
        self.assertEqual(result.body, expected_body)

        # verify that socket is closed by server
        self.assertEqual(sock.recv(1), b'')

    def test_026_http_10_nokeepalive(self):
        # verify that if an http/1.0 client sends connection: keep-alive
        # and the server doesn't accept keep-alives, we close the connection
        self.spawn_server(keepalive=False)
        sock = eventlet.connect(
            ('localhost', self.port))

        sock.sendall(b'GET / HTTP/1.0\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n')
        result = read_http(sock)
        self.assertEqual(result.headers_lower['connection'], 'close')

    def test_027_keepalive_chunked(self):
        self.site.application = chunked_post
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('wb')
        common_suffix = (
            b'Host: localhost\r\nTransfer-Encoding: chunked\r\n\r\n' +
            b'10\r\n0123456789abcdef\r\n0\r\n\r\n')
        fd.write(b'PUT /a HTTP/1.1\r\n' + common_suffix)
        fd.flush()
        read_http(sock)
        fd.write(b'PUT /b HTTP/1.1\r\n' + common_suffix)
        fd.flush()
        read_http(sock)
        fd.write(b'PUT /c HTTP/1.1\r\n' + common_suffix)
        fd.flush()
        read_http(sock)
        fd.write(b'PUT /a HTTP/1.1\r\n' + common_suffix)
        fd.flush()
        read_http(sock)
        sock.close()

    @tests.skip_if_no_ssl
    def test_028_ssl_handshake_errors(self):
        errored = [False]

        def server(sock):
            try:
                wsgi.server(sock=sock, site=hello_world, log=self.logfile)
                errored[0] = 'SSL handshake error caused wsgi.server to exit.'
            except greenthread.greenlet.GreenletExit:
                pass
            except Exception as e:
                errored[0] = 'SSL handshake error raised exception %s.' % e
                raise
        for data in ('', 'GET /non-ssl-request HTTP/1.0\r\n\r\n'):
            srv_sock = eventlet.wrap_ssl(
                eventlet.listen(('localhost', 0)),
                certfile=certificate_file, keyfile=private_key_file,
                server_side=True)
            port = srv_sock.getsockname()[1]
            g = eventlet.spawn_n(server, srv_sock)
            client = eventlet.connect(('localhost', port))
            if data:  # send non-ssl request
                client.sendall(data.encode())
            else:  # close sock prematurely
                client.close()
            eventlet.sleep(0)  # let context switch back to server
            assert not errored[0], errored[0]
            # make another request to ensure the server's still alive
            try:
                client = ssl.wrap_socket(eventlet.connect(('localhost', port)))
                client.write(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
                result = recvall(client)
                assert result.startswith(b'HTTP'), result
                assert result.endswith(b'hello world')
            except ImportError:
                pass  # TODO(openssl): should test with OpenSSL
            greenthread.kill(g)

    def test_029_posthooks(self):
        posthook1_count = [0]
        posthook2_count = [0]

        def posthook1(env, value, multiplier=1):
            self.assertEqual(env['local.test'], 'test_029_posthooks')
            posthook1_count[0] += value * multiplier

        def posthook2(env, value, divisor=1):
            self.assertEqual(env['local.test'], 'test_029_posthooks')
            posthook2_count[0] += value / divisor

        def one_posthook_app(env, start_response):
            env['local.test'] = 'test_029_posthooks'
            if 'eventlet.posthooks' not in env:
                start_response('500 eventlet.posthooks not supported',
                               [('Content-Type', 'text/plain')])
            else:
                env['eventlet.posthooks'].append(
                    (posthook1, (2,), {'multiplier': 3}))
                start_response('200 OK', [('Content-Type', 'text/plain')])
            yield b''
        self.site.application = one_posthook_app
        sock = eventlet.connect(('localhost', self.port))
        fp = sock.makefile('rwb')
        fp.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fp.flush()
        self.assertEqual(fp.readline(), b'HTTP/1.1 200 OK\r\n')
        fp.close()
        sock.close()
        self.assertEqual(posthook1_count[0], 6)
        self.assertEqual(posthook2_count[0], 0)

        def two_posthook_app(env, start_response):
            env['local.test'] = 'test_029_posthooks'
            if 'eventlet.posthooks' not in env:
                start_response('500 eventlet.posthooks not supported',
                               [('Content-Type', 'text/plain')])
            else:
                env['eventlet.posthooks'].append(
                    (posthook1, (4,), {'multiplier': 5}))
                env['eventlet.posthooks'].append(
                    (posthook2, (100,), {'divisor': 4}))
                start_response('200 OK', [('Content-Type', 'text/plain')])
            yield b''
        self.site.application = two_posthook_app
        sock = eventlet.connect(('localhost', self.port))
        fp = sock.makefile('rwb')
        fp.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fp.flush()
        self.assertEqual(fp.readline(), b'HTTP/1.1 200 OK\r\n')
        fp.close()
        sock.close()
        self.assertEqual(posthook1_count[0], 26)
        self.assertEqual(posthook2_count[0], 25)

    def test_030_reject_long_header_lines(self):
        sock = eventlet.connect(('localhost', self.port))
        request = 'GET / HTTP/1.0\r\nHost: localhost\r\nLong: %s\r\n\r\n' % \
            ('a' * 10000)
        send_expect_close(sock, request.encode())
        result = read_http(sock)
        self.assertEqual(result.status, 'HTTP/1.0 400 Header Line Too Long')

    def test_031_reject_large_headers(self):
        sock = eventlet.connect(('localhost', self.port))
        headers = ('Name: %s\r\n' % ('a' * 7000,)) * 20
        request = 'GET / HTTP/1.0\r\nHost: localhost\r\n%s\r\n\r\n' % headers
        send_expect_close(sock, request.encode())
        result = read_http(sock)
        self.assertEqual(result.status, 'HTTP/1.0 400 Headers Too Large')

    def test_032_wsgi_input_as_iterable(self):
        # https://bitbucket.org/eventlet/eventlet/issue/150
        # env['wsgi.input'] returns a single byte at a time
        # when used as an iterator
        g = [0]

        def echo_by_iterating(env, start_response):
            start_response('200 OK', [('Content-type', 'text/plain')])
            for chunk in env['wsgi.input']:
                g[0] += 1
                yield chunk

        self.site.application = echo_by_iterating
        upload_data = b'123456789abcdef' * 100
        request = (
            'POST / HTTP/1.0\r\n'
            'Host: localhost\r\n'
            'Content-Length: %i\r\n\r\n%s'
        ) % (len(upload_data), bytes_to_str(upload_data))
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(request.encode())
        fd.flush()
        result = read_http(sock)
        self.assertEqual(result.body, upload_data)
        fd.close()
        self.assertEqual(g[0], 1)

    def test_zero_length_chunked_response(self):
        def zero_chunked_app(env, start_response):
            start_response('200 OK', [('Content-type', 'text/plain')])
            yield b""

        self.site.application = zero_chunked_app
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        fd.flush()
        response = fd.read().split(b'\r\n')
        headers = []
        while True:
            h = response.pop(0)
            headers.append(h)
            if h == b'':
                break
        assert b'Transfer-Encoding: chunked' in b''.join(headers), headers
        # should only be one chunk of zero size with two blank lines
        # (one terminates the chunk, one terminates the body)
        self.assertEqual(response, [b'0', b'', b''])

    def test_configurable_url_length_limit(self):
        self.spawn_server(url_length_limit=20000)
        sock = eventlet.connect(
            ('localhost', self.port))
        path = 'x' * 15000
        request = 'GET /%s HTTP/1.0\r\nHost: localhost\r\n\r\n' % path
        fd = sock.makefile('rwb')
        fd.write(request.encode())
        fd.flush()
        result = fd.readline()
        if result:
            # windows closes the socket before the data is flushed,
            # so we never get anything back
            status = result.split(b' ')[1]
            self.assertEqual(status, b'200')
        fd.close()

    def test_aborted_chunked_post(self):
        read_content = event.Event()
        blew_up = [False]

        def chunk_reader(env, start_response):
            try:
                content = env['wsgi.input'].read(1024)
            except IOError:
                blew_up[0] = True
                content = b'ok'
            read_content.send(content)
            start_response('200 OK', [('Content-Type', 'text/plain')])
            return [content]
        self.site.application = chunk_reader
        expected_body = 'a bunch of stuff'
        data = "\r\n".join(['PUT /somefile HTTP/1.0',
                            'Transfer-Encoding: chunked',
                            '',
                            'def',
                            expected_body])
        # start PUT-ing some chunked data but close prematurely
        sock = eventlet.connect(('127.0.0.1', self.port))
        sock.sendall(data.encode())
        sock.close()
        # the test passes if we successfully get here, and read all the data
        # in spite of the early close
        self.assertEqual(read_content.wait(), b'ok')
        assert blew_up[0]

    def test_exceptions_close_connection(self):
        def wsgi_app(environ, start_response):
            raise RuntimeError("intentional error")
        self.site.application = wsgi_app
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fd.flush()
        result = read_http(sock)
        self.assertEqual(result.status, 'HTTP/1.1 500 Internal Server Error')
        self.assertEqual(result.headers_lower['connection'], 'close')
        assert 'transfer-encoding' not in result.headers_lower

    def test_unicode_raises_error(self):
        def wsgi_app(environ, start_response):
            start_response("200 OK", [])
            yield u"oh hai"
            yield u"non-encodable unicode: \u0230"
        self.site.application = wsgi_app
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        fd.flush()
        result = read_http(sock)
        self.assertEqual(result.status, 'HTTP/1.1 500 Internal Server Error')
        self.assertEqual(result.headers_lower['connection'], 'close')
        assert b'unicode' in result.body

    def test_path_info_decoding(self):
        def wsgi_app(environ, start_response):
            start_response("200 OK", [])
            yield six.b("decoded: %s" % environ['PATH_INFO'])
            yield six.b("raw: %s" % environ['RAW_PATH_INFO'])
        self.site.application = wsgi_app
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('rwb')
        fd.write(b'GET /a*b@%40%233 HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        fd.flush()
        result = read_http(sock)
        self.assertEqual(result.status, 'HTTP/1.1 200 OK')
        assert b'decoded: /a*b@@#3' in result.body
        assert b'raw: /a*b@%40%233' in result.body

    def test_ipv6(self):
        try:
            sock = eventlet.listen(('::1', 0), family=socket.AF_INET6)
        except (socket.gaierror, socket.error):  # probably no ipv6
            return
        log = six.StringIO()
        # first thing the server does is try to log the IP it's bound to

        def run_server():
            try:
                wsgi.server(sock=sock, log=log, site=Site())
            except ValueError:
                log.write(b'broken')

        self.spawn_thread(run_server)

        logval = log.getvalue()
        while not logval:
            eventlet.sleep(0.0)
            logval = log.getvalue()
        if 'broked' in logval:
            self.fail('WSGI server raised exception with ipv6 socket')

    def test_debug(self):
        self.spawn_server(debug=False)

        def crasher(env, start_response):
            raise RuntimeError("intentional crash")
        self.site.application = crasher

        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('wb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fd.flush()
        result1 = read_http(sock)
        self.assertEqual(result1.status, 'HTTP/1.1 500 Internal Server Error')
        self.assertEqual(result1.body, b'')
        self.assertEqual(result1.headers_lower['connection'], 'close')
        assert 'transfer-encoding' not in result1.headers_lower

        # verify traceback when debugging enabled
        self.spawn_server(debug=True)
        self.site.application = crasher
        sock = eventlet.connect(('localhost', self.port))
        fd = sock.makefile('wb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        fd.flush()
        result2 = read_http(sock)
        self.assertEqual(result2.status, 'HTTP/1.1 500 Internal Server Error')
        assert b'intentional crash' in result2.body, result2.body
        assert b'RuntimeError' in result2.body, result2.body
        assert b'Traceback' in result2.body, result2.body
        self.assertEqual(result2.headers_lower['connection'], 'close')
        assert 'transfer-encoding' not in result2.headers_lower

    def test_client_disconnect(self):
        """Issue #95 Server must handle disconnect from client in the middle of response
        """
        def long_response(environ, start_response):
            start_response('200 OK', [('Content-Length', '9876')])
            yield b'a' * 9876

        server_sock = eventlet.listen(('localhost', 0))
        self.port = server_sock.getsockname()[1]
        server = wsgi.Server(server_sock, server_sock.getsockname(), long_response,
                             log=self.logfile)

        def make_request():
            sock = eventlet.connect(server_sock.getsockname())
            sock.send(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
            sock.close()

        request_thread = eventlet.spawn(make_request)
        server_conn = server_sock.accept()
        # Next line must not raise IOError -32 Broken pipe
        server.process_request(server_conn)
        request_thread.wait()
        server_sock.close()

    def test_server_connection_timeout_exception(self):
        # Handle connection socket timeouts
        # https://bitbucket.org/eventlet/eventlet/issue/143/
        # Runs tests.wsgi_test_conntimeout in a separate process.
        testcode_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'wsgi_test_conntimeout.py')
        output = tests.run_python(testcode_path)
        sections = output.split(b"SEPERATOR_SENTINEL")
        # first section is empty
        self.assertEqual(3, len(sections), output)
        # if the "BOOM" check fails, it's because our timeout didn't happen
        # (if eventlet stops using file.readline() to read HTTP headers,
        # for instance)
        for runlog in sections[1:]:
            debug = False if "debug set to: False" in runlog else True
            if debug:
                self.assertTrue("timed out" in runlog)
            self.assertTrue("BOOM" in runlog)
            self.assertFalse("Traceback" in runlog)

    def test_server_socket_timeout(self):
        self.spawn_server(socket_timeout=0.1)
        sock = eventlet.connect(('localhost', self.port))
        sock.send(b'GET / HTTP/1.1\r\n')
        eventlet.sleep(0.1)
        try:
            read_http(sock)
            assert False, 'Expected ConnectionClosed exception'
        except ConnectionClosed:
            pass

    def test_disable_header_name_capitalization(self):
        # Disable HTTP header name capitalization
        #
        # https://github.com/eventlet/eventlet/issues/80
        random_case_header = ('eTAg', 'TAg-VAluE')

        def wsgi_app(environ, start_response):
            start_response('200 oK', [random_case_header])
            return [b'']

        self.spawn_server(site=wsgi_app, capitalize_response_headers=False)

        sock = eventlet.connect(('localhost', self.port))
        sock.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        result = read_http(sock)
        sock.close()
        self.assertEqual(result.status, 'HTTP/1.1 200 oK')
        self.assertEqual(result.headers_lower[random_case_header[0].lower()], random_case_header[1])
        self.assertEqual(result.headers_original[random_case_header[0]], random_case_header[1])


def read_headers(sock):
    fd = sock.makefile('rb')
    try:
        response_line = fd.readline()
    except socket.error as exc:
        if support.get_errno(exc) == 10053:
            raise ConnectionClosed
        raise
    if not response_line:
        raise ConnectionClosed

    header_lines = []
    while True:
        line = fd.readline()
        if line == b'\r\n':
            break
        else:
            header_lines.append(line)
    headers = dict()
    for x in header_lines:
        x = x.strip()
        if not x:
            continue
        key, value = x.split(b': ', 1)
        assert key.lower() not in headers, "%s header duplicated" % key
        headers[bytes_to_str(key.lower())] = bytes_to_str(value)
    return bytes_to_str(response_line), headers


class IterableAlreadyHandledTest(_TestBase):
    def set_site(self):
        self.site = IterableSite()

    def get_app(self):
        return IterableApp(True)

    def test_iterable_app_keeps_socket_open_unless_connection_close_sent(self):
        self.site.application = self.get_app()
        sock = eventlet.connect(
            ('localhost', self.port))

        fd = sock.makefile('rwb')
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')

        fd.flush()
        response_line, headers = read_headers(sock)
        self.assertEqual(response_line, 'HTTP/1.1 200 OK\r\n')
        assert 'connection' not in headers
        fd.write(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        fd.flush()
        result = read_http(sock)
        self.assertEqual(result.status, 'HTTP/1.1 200 OK')
        self.assertEqual(result.headers_lower.get('transfer-encoding'), 'chunked')
        self.assertEqual(result.body, b'0\r\n\r\n')  # Still coming back chunked


class ProxiedIterableAlreadyHandledTest(IterableAlreadyHandledTest):
    # same thing as the previous test but ensuring that it works with tpooled
    # results as well as regular ones
    @tests.skip_with_pyevent
    def get_app(self):
        return tpool.Proxy(super(ProxiedIterableAlreadyHandledTest, self).get_app())

    def tearDown(self):
        tpool.killall()
        super(ProxiedIterableAlreadyHandledTest, self).tearDown()


class TestChunkedInput(_TestBase):
    dirt = ""
    validator = None

    def application(self, env, start_response):
        input = env['wsgi.input']
        response = []

        pi = env["PATH_INFO"]

        if pi == "/short-read":
            d = input.read(10)
            response = [d]
        elif pi == "/lines":
            for x in input:
                response.append(x)
        elif pi == "/ping":
            input.read()
            response.append(b"pong")
        elif pi.startswith("/yield_spaces"):
            if pi.endswith('override_min'):
                env['eventlet.minimum_write_chunk_size'] = 1
            self.yield_next_space = False

            def response_iter():
                yield b' '
                num_sleeps = 0
                while not self.yield_next_space and num_sleeps < 200:
                    eventlet.sleep(.01)
                    num_sleeps += 1

                yield b' '

            start_response('200 OK',
                           [('Content-Type', 'text/plain'),
                            ('Content-Length', '2')])
            return response_iter()
        else:
            raise RuntimeError("bad path")

        start_response('200 OK', [('Content-Type', 'text/plain')])
        return response

    def connect(self):
        return eventlet.connect(('localhost', self.port))

    def set_site(self):
        self.site = Site()
        self.site.application = self.application

    def chunk_encode(self, chunks, dirt=None):
        if dirt is None:
            dirt = self.dirt

        b = ""
        for c in chunks:
            b += "%x%s\r\n%s\r\n" % (len(c), dirt, c)
        return b

    def body(self, dirt=None):
        return self.chunk_encode(["this", " is ", "chunked", "\nline",
                                  " 2", "\n", "line3", ""], dirt=dirt)

    def ping(self, fd):
        fd.sendall(b"GET /ping HTTP/1.1\r\n\r\n")
        self.assertEqual(read_http(fd).body, b"pong")

    def test_short_read_with_content_length(self):
        body = self.body()
        req = "POST /short-read HTTP/1.1\r\ntransfer-encoding: Chunked\r\n" \
              "Content-Length:1000\r\n\r\n" + body

        fd = self.connect()
        fd.sendall(req.encode())
        self.assertEqual(read_http(fd).body, b"this is ch")

        self.ping(fd)
        fd.close()

    def test_short_read_with_zero_content_length(self):
        body = self.body()
        req = "POST /short-read HTTP/1.1\r\ntransfer-encoding: Chunked\r\n" \
              "Content-Length:0\r\n\r\n" + body
        fd = self.connect()
        fd.sendall(req.encode())
        self.assertEqual(read_http(fd).body, b"this is ch")

        self.ping(fd)
        fd.close()

    def test_short_read(self):
        body = self.body()
        req = "POST /short-read HTTP/1.1\r\ntransfer-encoding: Chunked\r\n\r\n" + body

        fd = self.connect()
        fd.sendall(req.encode())
        self.assertEqual(read_http(fd).body, b"this is ch")

        self.ping(fd)
        fd.close()

    def test_dirt(self):
        body = self.body(dirt="; here is dirt\0bla")
        req = "POST /ping HTTP/1.1\r\ntransfer-encoding: Chunked\r\n\r\n" + body

        fd = self.connect()
        fd.sendall(req.encode())
        self.assertEqual(read_http(fd).body, b"pong")

        self.ping(fd)
        fd.close()

    def test_chunked_readline(self):
        body = self.body()
        req = "POST /lines HTTP/1.1\r\nContent-Length: %s\r\n" \
              "transfer-encoding: Chunked\r\n\r\n%s" % (len(body), body)

        fd = self.connect()
        fd.sendall(req.encode())
        self.assertEqual(read_http(fd).body, b'this is chunked\nline 2\nline3')
        fd.close()

    def test_chunked_readline_wsgi_override_minimum_chunk_size(self):

        fd = self.connect()
        fd.sendall(b"POST /yield_spaces/override_min HTTP/1.1\r\nContent-Length: 0\r\n\r\n")

        resp_so_far = b''
        with eventlet.Timeout(.1):
            while True:
                one_byte = fd.recv(1)
                resp_so_far += one_byte
                if resp_so_far.endswith(b'\r\n\r\n'):
                    break
            self.assertEqual(fd.recv(1), b' ')
        try:
            with eventlet.Timeout(.1):
                fd.recv(1)
        except eventlet.Timeout:
            pass
        else:
            assert False
        self.yield_next_space = True

        with eventlet.Timeout(.1):
            self.assertEqual(fd.recv(1), b' ')

    def test_chunked_readline_wsgi_not_override_minimum_chunk_size(self):

        fd = self.connect()
        fd.sendall(b"POST /yield_spaces HTTP/1.1\r\nContent-Length: 0\r\n\r\n")

        resp_so_far = b''
        try:
            with eventlet.Timeout(.1):
                while True:
                    one_byte = fd.recv(1)
                    resp_so_far += one_byte
                    if resp_so_far.endswith(b'\r\n\r\n'):
                        break
                self.assertEqual(fd.recv(1), b' ')
        except eventlet.Timeout:
            pass
        else:
            assert False

    def test_close_before_finished(self):
        got_signal = []

        def handler(*args):
            got_signal.append(1)
            raise KeyboardInterrupt()

        signal.signal(signal.SIGALRM, handler)
        signal.alarm(1)

        try:
            body = '4\r\nthi'
            req = "POST /short-read HTTP/1.1\r\ntransfer-encoding: Chunked\r\n\r\n" + body

            fd = self.connect()
            fd.sendall(req.encode())
            fd.close()
            eventlet.sleep(0.0)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, signal.SIG_DFL)

        assert not got_signal, "caught alarm signal. infinite loop detected."


if __name__ == '__main__':
    unittest.main()
