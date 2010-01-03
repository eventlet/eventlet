from tests import skipped, LimitedTestCase, skip_with_pyevent, TestIsTakingTooLong
from unittest import main
from eventlet import api, util, coros, proc, greenio, hubs
from eventlet.green.socket import GreenSSLObject
import errno
import os
import socket
import sys

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

def bufsized(sock, size=1):
    """ Resize both send and receive buffers on a socket.
    Useful for testing trampoline.  Returns the socket.
    
    >>> import socket
    >>> sock = bufsized(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    """
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, size)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, size)
    return sock

def min_buf_size():
    """Return the minimum buffer size that the platform supports."""
    test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1)
    return test_sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)

class TestGreenIo(LimitedTestCase):
    def test_connect_timeout(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.1)
        gs = greenio.GreenSocket(s)
        try:
            self.assertRaises(socket.timeout, gs.connect, ('192.0.2.1', 80))
        except socket.error, e:
            # unreachable is also a valid outcome
            if e[0] != errno.EHOSTUNREACH:
                raise

    def test_close_with_makefile(self):
        def accept_close_early(listener):
            # verify that the makefile and the socket are truly independent
            # by closing the socket prior to using the made file
            try:
                conn, addr = listener.accept()
                fd = conn.makefile()
                conn.close()
                fd.write('hello\n')
                fd.close()
                # socket._fileobjects are odd: writes don't check
                # whether the socket is closed or not, and you get an
                # AttributeError during flush if it is closed
                fd.write('a')
                self.assertRaises(Exception, fd.flush)
                self.assertRaises(socket.error, conn.send, 'b')
            finally:
                listener.close()

        def accept_close_late(listener):
            # verify that the makefile and the socket are truly independent
            # by closing the made file and then sending a character
            try:
                conn, addr = listener.accept()
                fd = conn.makefile()
                fd.write('hello')
                fd.close()
                conn.send('\n')
                conn.close()
                fd.write('a')
                self.assertRaises(Exception, fd.flush)
                self.assertRaises(socket.error, conn.send, 'b')
            finally:
                listener.close()
                
        def did_it_work(server):
            client = api.connect_tcp(('127.0.0.1', server.getsockname()[1]))
            fd = client.makefile()
            client.close()
            assert fd.readline() == 'hello\n'    
            assert fd.read() == ''
            fd.close()
            
        server = api.tcp_listener(('0.0.0.0', 0))
        killer = coros.execute(accept_close_early, server)
        did_it_work(server)
        killer.wait()
        
        server = api.tcp_listener(('0.0.0.0', 0))
        killer = coros.execute(accept_close_late, server)
        did_it_work(server)
        killer.wait()
    
    def test_del_closes_socket(self):
        def accept_once(listener):
            # delete/overwrite the original conn
            # object, only keeping the file object around
            # closing the file object should close everything
            try:
                conn, addr = listener.accept()
                conn = conn.makefile()
                conn.write('hello\n')
                conn.close()
                conn.write('a')
                self.assertRaises(Exception, conn.flush)
            finally:
                listener.close()
        server = api.tcp_listener(('0.0.0.0', 0))
        killer = coros.execute(accept_once, server)
        client = api.connect_tcp(('127.0.0.1', server.getsockname()[1]))
        fd = client.makefile()
        client.close()
        assert fd.read() == 'hello\n'    
        assert fd.read() == ''
        
        killer.wait()
     
    def test_full_duplex(self):
        large_data = '*' * 10 * min_buf_size()
        listener = bufsized(api.tcp_listener(('127.0.0.1', 0)))

        def send_large(sock):
            sock.sendall(large_data)
            
        def read_large(sock):
            result = sock.recv(len(large_data))
            expected = 'hello world'
            while len(result) < len(large_data):
                result += sock.recv(len(large_data))
            self.assertEquals(result, large_data)

        def server():
            (sock, addr) = listener.accept()
            sock = bufsized(sock)
            send_large_coro = coros.execute(send_large, sock)
            api.sleep(0)
            result = sock.recv(10)
            expected = 'hello world'
            while len(result) < len(expected):
                result += sock.recv(10)
            self.assertEquals(result, expected)
            send_large_coro.wait()
                
        server_evt = coros.execute(server)
        client = bufsized(api.connect_tcp(('127.0.0.1', 
                                           listener.getsockname()[1])))
        large_evt = coros.execute(read_large, client)
        api.sleep(0)
        client.sendall('hello world')
        server_evt.wait()
        large_evt.wait()
        client.close()
     
    def test_sendall(self):
        # test adapted from Marcus Cavanaugh's email
        # it may legitimately take a while, but will eventually complete
        self.timer.cancel()
        second_bytes = 10
        def test_sendall_impl(many_bytes):
            bufsize = max(many_bytes/15, 2)
            def sender(listener):
                (sock, addr) = listener.accept()
                sock = bufsized(sock, size=bufsize)
                sock.sendall('x'*many_bytes)
                sock.sendall('y'*second_bytes)
            
            listener = api.tcp_listener(("", 0))
            sender_coro = proc.spawn(sender, listener)
            client = bufsized(api.connect_tcp(('localhost', 
                                               listener.getsockname()[1])),
                              size=bufsize)
            total = 0
            while total < many_bytes:
                data = client.recv(min(many_bytes - total, many_bytes/10))
                if data == '':
                    break
                total += len(data)
            
            total2 = 0
            while total < second_bytes:
                data = client.recv(second_bytes)
                if data == '':
                    break
                total2 += len(data)
    
            sender_coro.wait()
            client.close()
        
        for bytes in (1000, 10000, 100000, 1000000):
            test_sendall_impl(bytes)
        
    @skip_with_pyevent
    def test_multiple_readers(self):
        recvsize = 2 * min_buf_size()
        sendsize = 10 * recvsize
        if recvsize > 100:
            # reset the timer because we're going to be taking
            # longer to send all this extra data
            self.timer.cancel()
            self.timer = api.exc_after(10, TestIsTakingTooLong(10))
        
        # test that we can have multiple coroutines reading
        # from the same fd.  We make no guarantees about which one gets which
        # bytes, but they should both get at least some
        def reader(sock, results):
            while True:
                data = sock.recv(recvsize)
                if data == '':
                    break
                results.append(data)
            
        results1 = []
        results2 = []
        listener = api.tcp_listener(('127.0.0.1', 0))
        def server():
            (sock, addr) = listener.accept()
            sock = bufsized(sock)
            try:
                c1 = proc.spawn(reader, sock, results1)
                c2 = proc.spawn(reader, sock, results2)
                c1.wait()
                c2.wait()
            finally:
                c1.kill()
                c2.kill()
                sock.close()

        server_coro = proc.spawn(server)
        client = bufsized(api.connect_tcp(('127.0.0.1', 
                                           listener.getsockname()[1])))
        client.sendall('*' * sendsize)
        client.close()
        server_coro.wait()
        listener.close()
        self.assert_(len(results1) > 0)
        self.assert_(len(results2) > 0)
        
    def test_wrap_socket(self):
        try:
            import ssl
        except ImportError:
            pass  # pre-2.6
        else:
            sock = api.tcp_listener(('127.0.0.1', 0))
            ssl_sock = ssl.wrap_socket(sock)
            
    def test_exception_squelching(self):
        return  # exception squelching disabled for now (greenthread doesn't 
        # re-raise exceptions to the hub)
        server = api.tcp_listener(('0.0.0.0', 0))
        client = api.connect_tcp(('127.0.0.1', server.getsockname()[1]))
        client_2, addr = server.accept()
        
        def hurl(s):
            s.recv(1)
            {}[1]  # keyerror

        fake = StringIO()
        orig = sys.stderr
        sys.stderr = fake
        try:
            api.spawn(hurl, client_2)            
            api.sleep(0)
            client.send(' ')
            api.sleep(0)
        finally:
            sys.stderr = orig
        self.assert_('Traceback' in fake.getvalue(), 
            "Traceback not in:\n" + fake.getvalue())
                        
if __name__ == '__main__':
    main()
