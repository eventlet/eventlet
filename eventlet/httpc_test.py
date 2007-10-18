"""\
@file httpc_test.py
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
    def __init__(self):
        self.stuff = {'hello': 'hello world'}

    def handle_get(self, req):
        req.set_header('x-get', 'hello')
        resp = StringIO()
        pairs = req.get_query_pairs()
        path = req.path().lstrip('/')
        try:
            resp.write(self.stuff[path])
        except KeyError:
            req.response(404, body='Not found')
            return
        if pairs:
            for k,v in pairs:
                resp.write(k + '=' + v + '\n')
        req.write(resp.getvalue())

    def handle_put(self, req):
        req.set_header('x-put', 'hello')
        path = req.path().lstrip('/')
        if not path:
            req.response(400, body='')
            return
        if path in self.stuff:
            req.response(204)
        else:
            req.response(201)
        self.stuff[path] = req.read_body()
        req.write('')
        
    def handle_delete(self, req):
        req.set_header('x-delete', 'hello')
        path = req.path().lstrip('/')
        if not path:
            req.response(400, body='')
            return
        try:
            del self.stuff[path]
            req.response(204)
        except KeyError:
            req.response(404)
        req.write('')

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

    def test_get_bad_uri(self):
        self.assertRaises(httpc.ConnectionError,
                          lambda: httpc.get('http://localhost:31337/b0gu5'))

    def test_get(self):
        response = httpc.get('http://localhost:31337/hello')
        self.assert_(response == 'hello world')

    def test_get_(self):
        status, msg, body = httpc.get_('http://localhost:31337/hello')
        self.assert_(status == 200)
        self.assert_(msg.dict['x-get'] == 'hello')
        self.assert_(body == 'hello world')

    def test_get_query(self):
        response = httpc.get('http://localhost:31337/hello?foo=bar&foo=quux')
        self.assert_(response == 'hello worldfoo=bar\nfoo=quux\n')

    def test_post_(self):
        data = 'qunge'
        status, msg, body = httpc.post_('http://localhost:31337/', data=data)
        self.assert_(status == 200)
        self.assert_(msg.dict['x-post'] == 'hello')
        self.assert_(body == data)

    def test_post(self):
        data = 'qunge'
        self.assert_(httpc.post('http://localhost:31337/', data=data) == data)

    def test_put_bad_uri(self):
        self.assertRaises(
            httpc.ConnectionError,
            lambda: httpc.put('http://localhost:31337/', data=''))

    def test_put_empty(self):
        httpc.put('http://localhost:31337/empty', data='')
        self.assert_(httpc.get('http://localhost:31337/empty') == '')

    def test_put_nonempty(self):
        data = 'nonempty'
        httpc.put('http://localhost:31337/nonempty', data=data)
        self.assert_(httpc.get('http://localhost:31337/nonempty') == data)

    def test_put_01_create(self):
        data = 'goodbye world'
        status, msg, body = httpc.put_('http://localhost:31337/goodbye',
                                       data=data)
        self.assert_(status == 201)
        self.assert_(msg.dict['x-put'] == 'hello')
        self.assert_(body is None)
        self.assert_(httpc.get('http://localhost:31337/goodbye') == data)

    def test_put_02_modify(self):
        self.test_put_01_create()
        data = 'i really mean goodbye'
        status = httpc.put_('http://localhost:31337/goodbye', data=data)[0]
        self.assert_(status == 204)
        self.assert_(httpc.get('http://localhost:31337/goodbye') == data)

    def test_delete_(self):
        httpc.put('http://localhost:31337/killme', data='killme')
        status, msg, body = httpc.delete_('http://localhost:31337/killme')
        self.assert_(status == 204)
        self.assertRaises(
            httpc.ConnectionError,
            lambda: httpc.get('http://localhost:31337/killme'))

    def test_delete(self):
        httpc.put('http://localhost:31337/killme', data='killme')
        self.assert_(httpc.delete('http://localhost:31337/killme') == '')
        self.assertRaises(
            httpc.ConnectionError,
            lambda: httpc.get('http://localhost:31337/killme'))

    def test_delete_bad_uri(self):
        self.assertRaises(
            httpc.ConnectionError,
            lambda: httpc.delete('http://localhost:31337/b0gu5'))
        
        
if __name__ == '__main__':
    tests.main()
