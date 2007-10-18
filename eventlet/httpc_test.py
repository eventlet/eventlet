"""\
@file httpd_test.py
@author Bryan O'Sullivan

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
from eventlet import httpc
from eventlet import httpd
from eventlet import processes
from eventlet import util
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


util.wrap_socket_with_coroutine_socket()


from eventlet import tests


class Site(object):
    def handle_get(self, req):
        req.set_header('x-get', 'hello')
        resp = StringIO()
        pairs = req.get_query_pairs()
        if pairs:
            for k,v in pairs:
                resp.write(k + '=' + v + '\n')
        else:
            resp.write('hello world')
        req.write(resp.getvalue())

    def handle_post(self, req):
        req.set_header('x-post', 'hello')
        req.write(req.read_body())

    def handle_request(self, req):
        return getattr(self, 'handle_%s' % req.method().lower())(req)

    def adapt(self, obj, req):
        req.write(str(obj))


class TestHttpc(tests.TestCase):
    def setUp(self):
        self.victim = api.spawn(httpd.server,
                                api.tcp_listener(('0.0.0.0', 31337)),
                                Site(),
                                max_size=128)

    def tearDown(self):
        api.kill(self.victim)

    def test_get(self):
        response = httpc.get('http://localhost:31337/')
        self.assert_(response == 'hello world')

    def test_get_(self):
        status, msg, body = httpc.get_('http://localhost:31337/')
        self.assert_(status == 200)
        self.assert_(msg.dict['x-get'] == 'hello')
        self.assert_(body == 'hello world')

    def test_get_query(self):
        response = httpc.get('http://localhost:31337/?foo=bar&foo=quux')
        self.assert_(response == 'foo=bar\nfoo=quux\n')

    def test_post_(self):
        data = 'qunge'
        status, msg, body = httpc.post_('http://localhost:31337/', data=data)
        self.assert_(status == 200)
        self.assert_(msg.dict['x-post'] == 'hello')
        self.assert_(body == data)
        

if __name__ == '__main__':
    tests.main()
