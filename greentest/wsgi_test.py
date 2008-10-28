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

import cgi

from eventlet import api
from eventlet import wsgi
from eventlet import processes
from eventlet import util

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


util.wrap_socket_with_coroutine_socket()


from eventlet import tests


def hello_world(env, start_response):
    if env['PATH_INFO'] == 'notexist':
        start_response('404 Not Found', [('Content-type', 'text/plain')])
        return ["not found"]
        
    start_response('200 OK', [('Content-type', 'text/plain')])
    return ["hello world"]


def chunked_app(env, start_response):
    start_response('200 OK', [('Content-type', 'text/plain')])
    yield "this"
    yield "is"
    yield "chunked"


def big_chunks(env, start_response):
    start_response('200 OK', [('Content-type', 'text/plain')])
    line = 'a' * 8192
    for x in range(10):
        yield line


class Site(object):
    def __init__(self):
        self.application = hello_world

    def __call__(self, env, start_response):
        return self.application(env, start_response)


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
    fd = sock.makefile()
    response_line = fd.readline()
    if not response_line:
        raise ConnectionClosed
    raw_headers = fd.readuntil('\r\n\r\n').strip()
    #print "R", response_line, raw_headers
    headers = dict()
    for x in raw_headers.split('\r\n'):
        #print "X", x
        key, value = x.split(': ', 1)
        headers[key.lower()] = value

    if CONTENT_LENGTH in headers:
        num = int(headers[CONTENT_LENGTH])
        body = fd.read(num)
        #print body
    else:
        body = None

    return response_line, headers, body


class TestHttpd(tests.TestCase):
    mode = 'static'
    def setUp(self):
        self.logfile = StringIO()
        self.site = Site()
        self.killer = api.spawn(
            wsgi.server,
            api.tcp_listener(('0.0.0.0', 12346)), self.site, max_size=128, log=self.logfile)

    def tearDown(self):
        api.kill(self.killer)

    def test_001_server(self):
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))
        
        fd = sock.makefile()
        fd.write('GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
        result = fd.read()
        fd.close()
        ## The server responds with the maximum version it supports
        self.assert_(result.startswith('HTTP'), result)
        self.assert_(result.endswith('hello world'))

    def test_002_keepalive(self):
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))
            
        fd = sock.makefile()
        fd.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        read_http(sock)
        fd.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        read_http(sock)
        fd.close()

    def test_003_passing_non_int_to_read(self):
        # This should go in greenio_test
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))
        
        fd = sock.makefile()
        fd.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        cancel = api.exc_after(1, RuntimeError)
        self.assertRaises(TypeError, fd.read, "This shouldn't work")
        cancel.cancel()
        fd.close()

    def test_004_close_keepalive(self):
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))

        fd = sock.makefile()
        fd.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        read_http(sock)
        fd.write('GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        read_http(sock)
        fd.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        self.assertRaises(ConnectionClosed, read_http, sock)
        fd.close()

    def skip_test_005_run_apachebench(self):
        url = 'http://localhost:12346/'
        # ab is apachebench
        out = processes.Process(tests.find_command('ab'),
                                ['-c','64','-n','1024', '-k', url])
        print out.read()

    def test_006_reject_long_urls(self):
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))
        path_parts = []
        for ii in range(3000):
            path_parts.append('path')
        path = '/'.join(path_parts)
        request = 'GET /%s HTTP/1.0\r\nHost: localhost\r\n\r\n' % path
        fd = sock.makefile()
        fd.write(request)
        result = fd.readline()
        status = result.split(' ')[1]
        self.assertEqual(status, '414')
        fd.close()
        
    def test_007_get_arg(self):
        # define a new handler that does a get_arg as well as a read_body
        def new_app(env, start_response):
            body = env['wsgi.input'].read()
            a = cgi.parse_qs(body).get('a', [1])[0]
            start_response('200 OK', [('Content-type', 'text/plain')])
            return ['a is %s, body is %s' % (a, body)]
        self.site.application = new_app
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))
        request = '\r\n'.join((
            'POST / HTTP/1.0', 
            'Host: localhost', 
            'Content-Length: 3', 
            '',
            'a=a'))
        fd = sock.makefile()
        fd.write(request)
        
        # send some junk after the actual request
        fd.write('01234567890123456789')
        reqline, headers, body = read_http(sock)
        self.assertEqual(body, 'a is a, body is a=a')
        fd.close()
        
    def test_008_correctresponse(self):
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))
        
        fd = sock.makefile()
        fd.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        response_line_200,_,_ = read_http(sock)
        fd.write('GET /notexist HTTP/1.1\r\nHost: localhost\r\n\r\n')
        response_line_404,_,_ = read_http(sock)
        fd.write('GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        response_line_test,_,_ = read_http(sock)
        self.assertEqual(response_line_200,response_line_test)
        fd.close()

    def test_009_chunked_response(self):
        self.site.application = chunked_app
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))
        
        fd = sock.makefile()
        fd.write('GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        self.assert_('Transfer-Encoding: chunked' in fd.read())

    def test_010_no_chunked_http_1_0(self):
        self.site.application = chunked_app
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))
        
        fd = sock.makefile()
        fd.write('GET / HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        self.assert_('Transfer-Encoding: chunked' not in fd.read())

    def test_011_multiple_chunks(self):
        self.site.application = big_chunks
        sock = api.connect_tcp(
            ('127.0.0.1', 12346))
        
        fd = sock.makefile()
        fd.write('GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        headers = fd.readuntil('\r\n\r\n')
        self.assert_('Transfer-Encoding: chunked' in headers)
        chunks = 0
        chunklen = int(fd.readline(), 16)
        while chunklen:
            chunks += 1
            chunk = fd.read(chunklen)
            fd.readline()
            chunklen = int(fd.readline(), 16)
        self.assert_(chunks > 1)

if __name__ == '__main__':
    tests.main()
