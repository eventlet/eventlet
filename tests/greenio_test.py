# Copyright (c) 2006-2007, Linden Research, Inc.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from tests import skipped, LimitedTestCase
from unittest import main
from eventlet import api, util, coros, proc
import os
import socket


def bufsized(sock, size=1):
    """ Resize both send and receive buffers on a socket.
    Useful for testing trampoline.  Returns the socket.
    
    >>> import socket
    >>> sock = bufsized(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    """
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, size)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, size)
    return sock


class TestGreenIo(LimitedTestCase):
    def test_close_with_makefile(self):
        def accept_close_early(listener):
            # verify that the makefile and the socket are truly independent
            # by closing the socket prior to using the made file
            try:
                conn, addr = listener.accept()
                fd = conn.makeGreenFile()
                conn.close()
                fd.write('hello\n')
                fd.close()
                self.assertRaises(socket.error, fd.write, 'a')
                self.assertRaises(socket.error, conn.send, 'b')
            finally:
                listener.close()

        def accept_close_late(listener):
            # verify that the makefile and the socket are truly independent
            # by closing the made file and then sending a character
            try:
                conn, addr = listener.accept()
                fd = conn.makeGreenFile()
                fd.write('hello')
                fd.close()
                conn.send('\n')
                conn.close()
                self.assertRaises(socket.error, fd.write, 'a')
                self.assertRaises(socket.error, conn.send, 'b')
            finally:
                listener.close()
                
        def did_it_work(server):
            client = api.connect_tcp(('127.0.0.1', server.getsockname()[1]))
            fd = client.makeGreenFile()
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
                conn = conn.makeGreenFile()
                conn.write('hello\n')
                conn.close()
                self.assertRaises(socket.error, conn.write, 'a')
            finally:
                listener.close()
        server = api.tcp_listener(('0.0.0.0', 0))
        killer = coros.execute(accept_once, server)
        client = api.connect_tcp(('127.0.0.1', server.getsockname()[1]))
        fd = client.makeGreenFile()
        client.close()
        assert fd.read() == 'hello\n'    
        assert fd.read() == ''
        
        killer.wait()
     
    def test_full_duplex(self):
        large_data = '*' * 10
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
        # test adapted from Brian Brunswick's email
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
        
    def test_multiple_readers(self):
        # test that we can have multiple coroutines reading
        # from the same fd.  We make no guarantees about which one gets which
        # bytes, but they should both get at least some
        def reader(sock, results):
            while True:
                data = sock.recv(1)
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
        client.sendall('*' * 10)
        client.close()
        server_coro.wait()
        listener.close()
        
        self.assert_(len(results1) > 0)
        self.assert_(len(results2) > 0)


class SSLTest(LimitedTestCase):
    def test_duplex_response(self):
        def serve(listener):
            sock, addr = listener.accept()
            stuff = sock.read(8192)
            sock.write('response')
  
        certificate_file = os.path.join(os.path.dirname(__file__), 'test_server.crt')
        private_key_file = os.path.join(os.path.dirname(__file__), 'test_server.key')
        sock = api.ssl_listener(('', 4201), certificate_file, private_key_file)
        server_coro = coros.execute(serve, sock)
        
        client = util.wrap_ssl(api.connect_tcp(('localhost', 4201)))
        client.write('line 1\r\nline 2\r\n\r\n')
        self.assertEquals(client.read(8192), 'response')
        server_coro.wait()
                
if __name__ == '__main__':
    main()
