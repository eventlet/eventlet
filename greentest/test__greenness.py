"""Test than modules in eventlet.green package are indeed green.
To do that spawn green server and then access it using green socket.
If either operation would actuallu block the whole script would block and timeout.
"""
import unittest
from greentest import test_support
from eventlet.green import urllib2, BaseHTTPServer
from eventlet.api import spawn, kill

port = 18341

def start_http_server():
    server_address = ('', port)
    BaseHTTPServer.BaseHTTPRequestHandler.protocol_version = "HTTP/1.0"
    httpd = BaseHTTPServer.HTTPServer(server_address, BaseHTTPServer.BaseHTTPRequestHandler)
    sa = httpd.socket.getsockname()
    #print "Serving HTTP on", sa[0], "port", sa[1], "..."
    httpd.request_count = 0
    def serve():
        while 1:
            httpd.handle_request()
            httpd.request_count += 1
    return spawn(serve), httpd

class TestGreenness(unittest.TestCase):

    def setUp(self):
        self.gthread, self.server = start_http_server()
        #print 'Spawned the server'

    def tearDown(self):
        self.server.server_close()
        kill(self.gthread)

    def test_urllib2(self):
        self.assertEqual(self.server.request_count, 0)
        try:
            urllib2.urlopen('http://127.0.0.1:%s' % port)
            assert False, 'should not get there'
        except urllib2.HTTPError, ex:
            assert ex.code == 501, `ex`
        self.assertEqual(self.server.request_count, 1)

if __name__ == '__main__':
    test_support.run_unittest(TestGreenness)
