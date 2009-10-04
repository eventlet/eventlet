import unittest
from eventlet import api

if hasattr(api._threadlocal, 'hub'):
    from eventlet.green import socket
else:
    import socket

class TestSocketErrors(unittest.TestCase):
    
    def test_connection_refused(self):
        s = socket.socket()
        try:
            s.connect(('127.0.0.1', 81))
        except socket.error, ex:
            code, text = ex.args
            assert code in [111, 61], (code, text)
            assert 'refused' in text.lower(), (code, text)

if __name__=='__main__':
    unittest.main()
