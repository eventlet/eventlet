# Test the green/ssl.py in monkey patch environment
import eventlet
import tests
import socket
import ssl


class SSLWithMonkeyPatchTest(tests.LimitedTestCase):
    def test_green_ssl_socket_init(self):
        sock = ssl.wrap_socket(
            socket.socket(socket.AF_INET, socket.SOCK_STREAM),
            tests.private_key_file,
            tests.certificate_file
        )
        assert sock is not None
        #assert type(sock) == eventlet.green.ssl.GreenSSLSocket
