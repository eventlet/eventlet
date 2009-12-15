import unittest
from eventlet import api

if hasattr(api._threadlocal, 'hub'):
    from eventlet.green import socket
else:
    import socket

class TestSocketErrors(unittest.TestCase):
    
    def test_connection_refused(self):
        # open and close a dummy server to find an unused port
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]
        server.close()
        del server
        s = socket.socket()
        try:
            s.connect(('127.0.0.1', port))
            self.fail("Shouldn't have connected")
        except socket.error, ex:
            code, text = ex.args
            assert code in [111, 61, 10061], (code, text)
            assert 'refused' in text.lower(), (code, text)

if __name__=='__main__':
    unittest.main()
