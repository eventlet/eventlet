import errno
import struct

import eventlet
from eventlet import event
from eventlet.green import httplib
from eventlet.green import socket
from eventlet import websocket

from tests.wsgi_test import _TestBase


# demo app
def handle(ws):
    if ws.path == '/echo':
        while True:
            m = ws.wait()
            if m is None:
                break
            ws.send(m)
    elif ws.path == '/range':
        for i in xrange(10):
            ws.send("msg %d" % i)
            eventlet.sleep(0.01)
    elif ws.path == '/error':
        # some random socket error that we shouldn't normally get
        raise socket.error(errno.ENOTSOCK)
    else:
        ws.close()

wsapp = websocket.WebSocketWSGI(handle)


class TestWebSocket(_TestBase):
    TEST_TIMEOUT = 5

    def set_site(self):
        self.site = wsapp

    def test_incomplete_headers_13(self):
        headers = dict(kv.split(': ') for kv in [
                "Upgrade: websocket",
                # NOTE: intentionally no connection header
                "Host: localhost:%s" % self.port,
                "Origin: http://localhost:%s" % self.port,
                "Sec-WebSocket-Version: 13", ])
        http = httplib.HTTPConnection('localhost', self.port)
        http.request("GET", "/echo", headers=headers)
        resp = http.getresponse()

        self.assertEqual(resp.status, 400)
        self.assertEqual(resp.getheader('connection'), 'close')
        self.assertEqual(resp.read(), '')

        # Now, miss off key
        headers = dict(kv.split(': ') for kv in [
                "Upgrade: websocket",
                "Connection: Upgrade",
                "Host: localhost:%s" % self.port,
                "Origin: http://localhost:%s" % self.port,
                "Sec-WebSocket-Version: 13", ])
        http = httplib.HTTPConnection('localhost', self.port)
        http.request("GET", "/echo", headers=headers)
        resp = http.getresponse()

        self.assertEqual(resp.status, 400)
        self.assertEqual(resp.getheader('connection'), 'close')
        self.assertEqual(resp.read(), '')

    def test_correct_upgrade_request_13(self):
        connect = [
                "GET /echo HTTP/1.1",
                "Upgrade: websocket",
                "Connection: Upgrade",
                "Host: localhost:%s" % self.port,
                "Origin: http://localhost:%s" % self.port,
                "Sec-WebSocket-Version: 13",
                "Sec-WebSocket-Key: d9MXuOzlVQ0h+qRllvSCIg==", ]
        sock = eventlet.connect(
            ('localhost', self.port))

        sock.sendall('\r\n'.join(connect) + '\r\n\r\n')
        result = sock.recv(1024)
        ## The server responds the correct Websocket handshake
        self.assertEqual(result,
                         '\r\n'.join(['HTTP/1.1 101 Switching Protocols',
                                      'Upgrade: websocket',
                                      'Connection: Upgrade',
                                      'Sec-WebSocket-Accept: ywSyWXCPNsDxLrQdQrn5RFNRfBU=\r\n\r\n', ]))

    def test_send_recv_13(self):
        connect = [
                "GET /echo HTTP/1.1",
                "Upgrade: websocket",
                "Connection: Upgrade",
                "Host: localhost:%s" % self.port,
                "Origin: http://localhost:%s" % self.port,
                "Sec-WebSocket-Version: 13",
                "Sec-WebSocket-Key: d9MXuOzlVQ0h+qRllvSCIg==", ]
        sock = eventlet.connect(
            ('localhost', self.port))

        sock.sendall('\r\n'.join(connect) + '\r\n\r\n')
        first_resp = sock.recv(1024)
        ws = websocket.RFC6455WebSocket(sock, {}, client=True)
        ws.send('hello')
        assert ws.wait() == 'hello'
        ws.send('hello world!\x01')
        ws.send(u'hello world again!')
        assert ws.wait() == 'hello world!\x01'
        assert ws.wait() == u'hello world again!'
        ws.close()
        eventlet.sleep(0.01)

    def test_breaking_the_connection_13(self):
        error_detected = [False]
        done_with_request = event.Event()
        site = self.site
        def error_detector(environ, start_response):
            try:
                try:
                    return site(environ, start_response)
                except:
                    error_detected[0] = True
                    raise
            finally:
                done_with_request.send(True)
        self.site = error_detector
        self.spawn_server()
        connect = [
                "GET /echo HTTP/1.1",
                "Upgrade: websocket",
                "Connection: Upgrade",
                "Host: localhost:%s" % self.port,
                "Origin: http://localhost:%s" % self.port,
                "Sec-WebSocket-Version: 13",
                "Sec-WebSocket-Key: d9MXuOzlVQ0h+qRllvSCIg==", ]
        sock = eventlet.connect(
            ('localhost', self.port))
        sock.sendall('\r\n'.join(connect) + '\r\n\r\n')
        resp = sock.recv(1024)  # get the headers
        sock.close()  # close while the app is running
        done_with_request.wait()
        self.assert_(not error_detected[0])

    def test_client_closing_connection_13(self):
        error_detected = [False]
        done_with_request = event.Event()
        site = self.site
        def error_detector(environ, start_response):
            try:
                try:
                    return site(environ, start_response)
                except:
                    error_detected[0] = True
                    raise
            finally:
                done_with_request.send(True)
        self.site = error_detector
        self.spawn_server()
        connect = [
                "GET /echo HTTP/1.1",
                "Upgrade: websocket",
                "Connection: Upgrade",
                "Host: localhost:%s" % self.port,
                "Origin: http://localhost:%s" % self.port,
                "Sec-WebSocket-Version: 13",
                "Sec-WebSocket-Key: d9MXuOzlVQ0h+qRllvSCIg==", ]
        sock = eventlet.connect(
            ('localhost', self.port))
        sock.sendall('\r\n'.join(connect) + '\r\n\r\n')
        resp = sock.recv(1024)  # get the headers
        closeframe = struct.pack('!BBIH', 1 << 7 | 8, 1 << 7 | 2, 0, 1000)
        sock.sendall(closeframe)  # "Close the connection" packet.
        done_with_request.wait()
        self.assert_(not error_detected[0])

    def test_client_invalid_packet_13(self):
        error_detected = [False]
        done_with_request = event.Event()
        site = self.site
        def error_detector(environ, start_response):
            try:
                try:
                    return site(environ, start_response)
                except:
                    error_detected[0] = True
                    raise
            finally:
                done_with_request.send(True)
        self.site = error_detector
        self.spawn_server()
        connect = [
                "GET /echo HTTP/1.1",
                "Upgrade: websocket",
                "Connection: Upgrade",
                "Host: localhost:%s" % self.port,
                "Origin: http://localhost:%s" % self.port,
                "Sec-WebSocket-Version: 13",
                "Sec-WebSocket-Key: d9MXuOzlVQ0h+qRllvSCIg==", ]
        sock = eventlet.connect(
            ('localhost', self.port))
        sock.sendall('\r\n'.join(connect) + '\r\n\r\n')
        resp = sock.recv(1024)  # get the headers
        sock.sendall('\x07\xff') # Weird packet.
        done_with_request.wait()
        self.assert_(not error_detected[0])
