"""\
@file httpd_test.py
@author Donovan Preston

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


from eventlet import api
from eventlet import httpd
from eventlet import processes
from eventlet import util


util.wrap_socket_with_coroutine_socket()


from eventlet import tests


class Site(object):
    def handle_request(self, req):
        req.write('hello world')

    def adapt(self, obj, req):
        req.write(str(obj))


CONTENT_LENGTH = 'content-length'


"""
HTTP/1.1 200 OK
Date: foo
Content-length: 11

hello world
"""

class ConnectionClosed(Exception):
    pass


def read_http(sock):
    response_line = sock.readline()
    if not response_line:
        raise ConnectionClosed
    raw_headers = sock.readuntil('\r\n\r\n').strip()
    #print "R", response_line, raw_headers
    headers = dict()
    for x in raw_headers.split('\r\n'):
        #print "X", x
        key, value = x.split(': ', 1)
        headers[key.lower()] = value

    if CONTENT_LENGTH in headers:
        num = int(headers[CONTENT_LENGTH])
        body = sock.read(num)
        #print body


class TestHttpd(tests.TestCase):
    mode = 'static'
    def setUp(self):
        self.killer = api.spawn(
            httpd.server, api.tcp_listener(('0.0.0.0', 12346)), Site(), max_size=128)

    def tearDown(self):
        api.kill(self.killer)

    def test_001_server(self):
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))

        sock.write('GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
        result = sock.read()
        sock.close()
        ## The server responds with the maximum version it supports
        self.assert_(result.startswith('HTTP'), result)
        self.assert_(result.endswith('hello world'))

    def test_002_keepalive(self):
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))

        sock.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        read_http(sock)
        sock.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        read_http(sock)
        sock.close()

    def test_003_passing_non_int_to_read(self):
        # This should go in test_wrappedfd
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))

        sock.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        cancel = api.exc_after(1, RuntimeError)
        self.assertRaises(TypeError, sock.read, "This shouldn't work")
        cancel.cancel()
        sock.close()

    def test_004_close_keepalive(self):
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))

        sock.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        read_http(sock)
        sock.write('GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        read_http(sock)
        sock.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        self.assertRaises(ConnectionClosed, read_http, sock)
        sock.close()

    def test_005_run_apachebench(self):
        url = 'http://localhost:12346/'
        # ab is apachebench
        out = processes.Process(tests.find_command('ab'),
                                ['-c','64','-n','1024', '-k', url])
        print out.read()


if __name__ == '__main__':
    tests.main()
