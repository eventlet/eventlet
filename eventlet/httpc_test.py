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

    def adapt(self, obj, req):
        req.write(str(obj))

    def handle_request(self, req):
        return getattr(self, 'handle_%s' % req.method().lower())(req)


class BasicSite(Site):
    def handle_get(self, req):
        req.set_header('x-get', 'hello')
        resp = StringIO()
        path = req.path().lstrip('/')
        try:
            resp.write(self.stuff[path])
        except KeyError:
            req.response(404, body='Not found')
            return
        for k,v in req.get_query_pairs():
            resp.write(k + '=' + v + '\n')
        req.write(resp.getvalue())

    def handle_head(self, req):
        req.set_header('x-head', 'hello')
        path = req.path().lstrip('/')
        try:
            req.write('')
        except KeyError:
            req.response(404, body='Not found')

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


class TestBase(object):
    site_class = BasicSite

    def base_url(self):
        return 'http://localhost:31337/'

    def setUp(self):
        self.victim = api.spawn(httpd.server,
                                api.tcp_listener(('0.0.0.0', 31337)),
                                self.site_class(),
                                max_size=128)

    def tearDown(self):
        api.kill(self.victim)


class TestHttpc(TestBase, tests.TestCase):
    def test_get_bad_uri(self):
        self.assertRaises(httpc.NotFound,
                          lambda: httpc.get(self.base_url() + 'b0gu5'))

    def test_get(self):
        response = httpc.get(self.base_url() + 'hello')
        self.assertEquals(response, 'hello world')

    def test_get_(self):
        status, msg, body = httpc.get_(self.base_url() + 'hello')
        self.assertEquals(status, 200)
        self.assertEquals(msg.dict['x-get'], 'hello')
        self.assertEquals(body, 'hello world')

    def test_get_query(self):
        response = httpc.get(self.base_url() + 'hello?foo=bar&foo=quux')
        self.assertEquals(response, 'hello worldfoo=bar\nfoo=quux\n')

    def test_head_(self):
        status, msg, body = httpc.head_(self.base_url() + 'hello')
        self.assertEquals(status, 200)
        self.assertEquals(msg.dict['x-head'], 'hello')
        self.assertEquals(body, '')

    def test_head(self):
        self.assertEquals(httpc.head(self.base_url() + 'hello'), '')

    def test_post_(self):
        data = 'qunge'
        status, msg, body = httpc.post_(self.base_url() + '', data=data)
        self.assertEquals(status, 200)
        self.assertEquals(msg.dict['x-post'], 'hello')
        self.assertEquals(body, data)

    def test_post(self):
        data = 'qunge'
        self.assertEquals(httpc.post(self.base_url() + '', data=data),
                          data)

    def test_put_bad_uri(self):
        self.assertRaises(
            httpc.BadRequest,
            lambda: httpc.put(self.base_url() + '', data=''))

    def test_put_empty(self):
        httpc.put(self.base_url() + 'empty', data='')
        self.assertEquals(httpc.get(self.base_url() + 'empty'), '')

    def test_put_nonempty(self):
        data = 'nonempty'
        httpc.put(self.base_url() + 'nonempty', data=data)
        self.assertEquals(httpc.get(self.base_url() + 'nonempty'), data)

    def test_put_01_create(self):
        data = 'goodbye world'
        status, msg, body = httpc.put_(self.base_url() + 'goodbye',
                                       data=data)
        self.assertEquals(status, 201)
        self.assertEquals(msg.dict['x-put'], 'hello')
        self.assertEquals(body, None)
        self.assertEquals(httpc.get(self.base_url() + 'goodbye'), data)

    def test_put_02_modify(self):
        self.test_put_01_create()
        data = 'i really mean goodbye'
        status = httpc.put_(self.base_url() + 'goodbye', data=data)[0]
        self.assertEquals(status, 204)
        self.assertEquals(httpc.get(self.base_url() + 'goodbye'), data)

    def test_delete_(self):
        httpc.put(self.base_url() + 'killme', data='killme')
        status, msg, body = httpc.delete_(self.base_url() + 'killme')
        self.assertEquals(status, 204)
        self.assertRaises(
            httpc.NotFound,
            lambda: httpc.get(self.base_url() + 'killme'))

    def test_delete(self):
        httpc.put(self.base_url() + 'killme', data='killme')
        self.assertEquals(httpc.delete(self.base_url() + 'killme'), '')
        self.assertRaises(
            httpc.NotFound,
            lambda: httpc.get(self.base_url() + 'killme'))

    def test_delete_bad_uri(self):
        self.assertRaises(
            httpc.NotFound,
            lambda: httpc.delete(self.base_url() + 'b0gu5'))
        
        
class Site301(BasicSite):
    def handle_request(self, req):
        if req.path().startswith('/redirect/'):
            url = ('http://' + req.get_header('host') +
                   req.uri().replace('/redirect/', '/'))
            req.response(301, headers={'location': url}, body='')
            return
        return Site.handle_request(self, req)


class Site303(BasicSite):
    def handle_request(self, req):
        if req.path().startswith('/redirect/'):
            url = ('http://' + req.get_header('host') +
                   req.uri().replace('/redirect/', '/'))
            req.response(303, headers={'location': url}, body='')
            return
        return Site.handle_request(self, req)


class TestHttpc301(TestBase, tests.TestCase):
    site_class = Site301

    def base_url(self):
        return 'http://localhost:31337/redirect/'

    def test_get(self):
        try:
            httpc.get(self.base_url() + 'hello')
            self.assert_(False)
        except httpc.MovedPermanently, err:
            response = err.retry()
        self.assertEquals(response, 'hello world')
    
    def test_post(self):
        data = 'qunge'
        try:
            response = httpc.post(self.base_url() + '', data=data)
            self.assert_(False)
        except httpc.MovedPermanently, err:
            response = err.retry()
        self.assertEquals(response, data)


class TestHttpc303(TestBase, tests.TestCase):
    site_class = Site303

    def base_url(self):
        return 'http://localhost:31337/redirect/'

    def test_post(self):
        data = 'hello world'
        try:
            response = httpc.post(self.base_url() + 'hello', data=data)
            self.assert_(False)
        except httpc.SeeOther, err:
            response = err.retry()
        self.assertEquals(response, data)


if __name__ == '__main__':
    tests.main()
