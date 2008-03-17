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
import time
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
        self.logfile = StringIO()
        self.victim = api.spawn(httpd.server,
                                api.tcp_listener(('0.0.0.0', 31337)),
                                self.site_class(),
                                log=self.logfile,
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
        self.assertEquals(body, '')
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
        
        
class RedirectSite(BasicSite):
    response_code = 301

    def handle_request(self, req):
        if req.path().startswith('/redirect/'):
            url = ('http://' + req.get_header('host') +
                   req.uri().replace('/redirect/', '/'))
            req.response(self.response_code, headers={'location': url},
                         body='')
            return
        return Site.handle_request(self, req)

class Site301(RedirectSite):
    pass


class Site302(BasicSite):
    def handle_request(self, req):
        if req.path().startswith('/expired/'):
            url = ('http://' + req.get_header('host') +
                   req.uri().replace('/expired/', '/'))
            headers = {'location': url, 'expires': '0'}
            req.response(302, headers=headers, body='')
            return
        if req.path().startswith('/expires/'):
            url = ('http://' + req.get_header('host') +
                   req.uri().replace('/expires/', '/'))
            expires = time.time() + (100 * 24 * 60 * 60)
            headers = {'location': url, 'expires': httpc.to_http_time(expires)}
            req.response(302, headers=headers, body='')
            return
        return Site.handle_request(self, req)


class Site303(RedirectSite):
    response_code = 303


class Site307(RedirectSite):
    response_code = 307


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


class TestHttpc302(TestBase, tests.TestCase):
    site_class = Site302

    def test_get_expired(self):
        try:
            httpc.get(self.base_url() + 'expired/hello')
            self.assert_(False)
        except httpc.Found, err:
            response = err.retry()
        self.assertEquals(response, 'hello world')

    def test_get_expires(self):
        try:
            httpc.get(self.base_url() + 'expires/hello')
            self.assert_(False)
        except httpc.Found, err:
            response = err.retry()
        self.assertEquals(response, 'hello world')


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


class TestHttpc307(TestBase, tests.TestCase):
    site_class = Site307

    def base_url(self):
        return 'http://localhost:31337/redirect/'

    def test_post(self):
        data = 'hello world'
        try:
            response = httpc.post(self.base_url() + 'hello', data=data)
            self.assert_(False)
        except httpc.TemporaryRedirect, err:
            response = err.retry()
        self.assertEquals(response, data)


class Site500(BasicSite):
    def handle_request(self, req):
        req.response(500, body="screw you world")
        return


class Site500(BasicSite):
    def handle_request(self, req):
        req.response(500, body="screw you world")
        return


class TestHttpc500(TestBase, tests.TestCase):
    site_class = Site500

    def base_url(self):
        return 'http://localhost:31337/'

    def test_get(self):
        data = 'screw you world'
        try:
            response = httpc.get(self.base_url())
            self.fail()
        except httpc.InternalServerError, e:
            self.assertEquals(e.params.response_body, data)
            self.assert_(str(e).count(data))
            self.assert_(repr(e).count(data))


class Site504(BasicSite):
    def handle_request(self, req):
        req.response(504, body="screw you world")

            
class TestHttpc504(TestBase, tests.TestCase):
    site_class = Site504

    def base_url(self):
        return 'http://localhost:31337/'

    def test_post(self):
        # Simply ensure that a 504 status code results in a
        # GatewayTimeout.  Don't bother retrying.
        data = 'hello world'
        self.assertRaises(httpc.GatewayTimeout,
                          lambda: httpc.post(self.base_url(), data=data))


class TestHttpTime(tests.TestCase):
    rfc1123_time = 'Sun, 06 Nov 1994 08:49:37 GMT'
    rfc850_time  = 'Sunday, 06-Nov-94 08:49:37 GMT'
    asctime_time = 'Sun Nov  6 08:49:37 1994'
    secs_since_epoch = 784111777
    def test_to_http_time(self):
        self.assertEqual(self.rfc1123_time, httpc.to_http_time(self.secs_since_epoch))
    
    def test_from_http_time(self):
        for formatted in (self.rfc1123_time, self.rfc850_time, self.asctime_time):
            ticks = httpc.from_http_time(formatted, 0)
            self.assertEqual(ticks, self.secs_since_epoch)

if __name__ == '__main__':
    tests.main()
