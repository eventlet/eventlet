from tests import skipped, LimitedTestCase, skip_unless
from unittest import main
from eventlet import api, util, coros, greenio
import socket
import os

certificate_file = os.path.join(os.path.dirname(__file__), 'test_server.crt')
private_key_file = os.path.join(os.path.dirname(__file__), 'test_server.key')

class SSLTest(LimitedTestCase):
    def test_duplex_response(self):
        def serve(listener):
            sock, addr = listener.accept()
            stuff = sock.read(8192)
            sock.write('response')
  
        sock = api.ssl_listener(('127.0.0.1', 0), certificate_file, private_key_file)
        server_coro = coros.execute(serve, sock)
        
        client = util.wrap_ssl(api.connect_tcp(('127.0.0.1', sock.getsockname()[1])))
        client.write('line 1\r\nline 2\r\n\r\n')
        self.assertEquals(client.read(8192), 'response')
        server_coro.wait()
        
    def test_ssl_close(self):
        def serve(listener):
            sock, addr = listener.accept()
            stuff = sock.read(8192)
            try:
                self.assertEquals("", sock.read(8192))
            except greenio.SSL.ZeroReturnError:
                pass
  
        sock = api.ssl_listener(('127.0.0.1', 0), certificate_file, private_key_file)
        server_coro = coros.execute(serve, sock)
        
        raw_client = api.connect_tcp(('127.0.0.1', sock.getsockname()[1]))
        client = util.wrap_ssl(raw_client)
        client.write('X')
        greenio.shutdown_safe(client)
        client.close()
        server_coro.wait()


class SocketSSLTest(LimitedTestCase):
    @skip_unless(hasattr(socket, 'ssl'))
    def test_greensslobject(self):
        import warnings
        # disabling socket.ssl warnings because we're testing it here
        warnings.filterwarnings(action = 'ignore',
                        message='.*socket.ssl.*',
                        category=DeprecationWarning)

        def serve(listener):
            sock, addr = listener.accept()
            sock.write('content')
            greenio.shutdown_safe(sock)
            sock.close()
        listener = api.ssl_listener(('', 0), 
                                    certificate_file, 
                                    private_key_file)
        killer = api.spawn(serve, listener)
        from eventlet.green.socket import ssl
        client = ssl(api.connect_tcp(('localhost', listener.getsockname()[1])))
        self.assertEquals(client.read(1024), 'content')
        self.assertEquals(client.read(1024), '')

        
if __name__ == '__main__':
    main()
