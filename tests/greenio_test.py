import array
import errno
import eventlet
import fcntl
import gc
import os
import shutil
import socket as _orig_sock
import sys
import tempfile

from nose.tools import eq_

from eventlet import event, greenio, debug
from eventlet.hubs import get_hub
from eventlet.green import select, socket, time, ssl
from eventlet.support import capture_stderr, get_errno, six
import tests


if six.PY3:
    buffer = memoryview


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


def using_epoll_hub(_f):
    try:
        return 'epolls' in type(get_hub()).__module__
    except Exception:
        return False


def using_kqueue_hub(_f):
    try:
        return 'kqueue' in type(get_hub()).__module__
    except Exception:
        return False


class TestGreenSocket(tests.LimitedTestCase):
    def assertWriteToClosedFileRaises(self, fd):
        if sys.version_info[0] < 3:
            # 2.x socket._fileobjects are odd: writes don't check
            # whether the socket is closed or not, and you get an
            # AttributeError during flush if it is closed
            fd.write(b'a')
            self.assertRaises(Exception, fd.flush)
        else:
            # 3.x io write to closed file-like pbject raises ValueError
            self.assertRaises(ValueError, fd.write, b'a')

    def test_connect_timeout(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.1)
        gs = greenio.GreenSocket(s)
        try:
            gs.connect(('192.0.2.1', 80))
            self.fail("socket.timeout not raised")
        except socket.timeout as e:
            assert hasattr(e, 'args')
            self.assertEqual(e.args[0], 'timed out')
        except socket.error as e:
            # unreachable is also a valid outcome
            if not get_errno(e) in (errno.EHOSTUNREACH, errno.ENETUNREACH):
                raise

    def test_accept_timeout(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('', 0))
        s.listen(50)

        s.settimeout(0.1)
        gs = greenio.GreenSocket(s)
        try:
            gs.accept()
            self.fail("socket.timeout not raised")
        except socket.timeout as e:
            assert hasattr(e, 'args')
            self.assertEqual(e.args[0], 'timed out')

    def test_connect_ex_timeout(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.1)
        gs = greenio.GreenSocket(s)
        e = gs.connect_ex(('192.0.2.1', 80))
        if e not in (errno.EHOSTUNREACH, errno.ENETUNREACH):
            self.assertEqual(e, errno.EAGAIN)

    def test_recv_timeout(self):
        listener = greenio.GreenSocket(socket.socket())
        listener.bind(('', 0))
        listener.listen(50)

        evt = event.Event()

        def server():
            # accept the connection in another greenlet
            sock, addr = listener.accept()
            evt.wait()

        gt = eventlet.spawn(server)

        addr = listener.getsockname()

        client = greenio.GreenSocket(socket.socket())
        client.settimeout(0.1)

        client.connect(addr)

        try:
            client.recv(8192)
            self.fail("socket.timeout not raised")
        except socket.timeout as e:
            assert hasattr(e, 'args')
            self.assertEqual(e.args[0], 'timed out')

        evt.send()
        gt.wait()

    def test_recvfrom_timeout(self):
        gs = greenio.GreenSocket(
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
        gs.settimeout(.1)
        gs.bind(('', 0))

        try:
            gs.recvfrom(8192)
            self.fail("socket.timeout not raised")
        except socket.timeout as e:
            assert hasattr(e, 'args')
            self.assertEqual(e.args[0], 'timed out')

    def test_recvfrom_into_timeout(self):
        buf = array.array('B')

        gs = greenio.GreenSocket(
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
        gs.settimeout(.1)
        gs.bind(('', 0))

        try:
            gs.recvfrom_into(buf)
            self.fail("socket.timeout not raised")
        except socket.timeout as e:
            assert hasattr(e, 'args')
            self.assertEqual(e.args[0], 'timed out')

    def test_recv_into_timeout(self):
        buf = array.array('B')

        listener = greenio.GreenSocket(socket.socket())
        listener.bind(('', 0))
        listener.listen(50)

        evt = event.Event()

        def server():
            # accept the connection in another greenlet
            sock, addr = listener.accept()
            evt.wait()

        gt = eventlet.spawn(server)

        addr = listener.getsockname()

        client = greenio.GreenSocket(socket.socket())
        client.settimeout(0.1)

        client.connect(addr)

        try:
            client.recv_into(buf)
            self.fail("socket.timeout not raised")
        except socket.timeout as e:
            assert hasattr(e, 'args')
            self.assertEqual(e.args[0], 'timed out')

        evt.send()
        gt.wait()

    def test_send_timeout(self):
        self.reset_timeout(2)
        listener = bufsized(eventlet.listen(('', 0)))

        evt = event.Event()

        def server():
            # accept the connection in another greenlet
            sock, addr = listener.accept()
            sock = bufsized(sock)
            evt.wait()

        gt = eventlet.spawn(server)

        addr = listener.getsockname()

        client = bufsized(greenio.GreenSocket(socket.socket()))
        client.connect(addr)
        try:
            client.settimeout(0.00001)
            msg = b"A" * 100000  # large enough number to overwhelm most buffers

            total_sent = 0
            # want to exceed the size of the OS buffer so it'll block in a
            # single send
            for x in range(10):
                total_sent += client.send(msg)
            self.fail("socket.timeout not raised")
        except socket.timeout as e:
            assert hasattr(e, 'args')
            self.assertEqual(e.args[0], 'timed out')

        evt.send()
        gt.wait()

    def test_sendall_timeout(self):
        listener = greenio.GreenSocket(socket.socket())
        listener.bind(('', 0))
        listener.listen(50)

        evt = event.Event()

        def server():
            # accept the connection in another greenlet
            sock, addr = listener.accept()
            evt.wait()

        gt = eventlet.spawn(server)

        addr = listener.getsockname()

        client = greenio.GreenSocket(socket.socket())
        client.settimeout(0.1)
        client.connect(addr)

        try:
            msg = b"A" * (8 << 20)

            # want to exceed the size of the OS buffer so it'll block
            client.sendall(msg)
            self.fail("socket.timeout not raised")
        except socket.timeout as e:
            assert hasattr(e, 'args')
            self.assertEqual(e.args[0], 'timed out')

        evt.send()
        gt.wait()

    def test_close_with_makefile(self):
        def accept_close_early(listener):
            # verify that the makefile and the socket are truly independent
            # by closing the socket prior to using the made file
            try:
                conn, addr = listener.accept()
                fd = conn.makefile('wb')
                conn.close()
                fd.write(b'hello\n')
                fd.close()
                self.assertWriteToClosedFileRaises(fd)
                self.assertRaises(socket.error, conn.send, b'b')
            finally:
                listener.close()

        def accept_close_late(listener):
            # verify that the makefile and the socket are truly independent
            # by closing the made file and then sending a character
            try:
                conn, addr = listener.accept()
                fd = conn.makefile('wb')
                fd.write(b'hello')
                fd.close()
                conn.send(b'\n')
                conn.close()
                self.assertWriteToClosedFileRaises(fd)
                self.assertRaises(socket.error, conn.send, b'b')
            finally:
                listener.close()

        def did_it_work(server):
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(('127.0.0.1', server.getsockname()[1]))
            fd = client.makefile('rb')
            client.close()
            assert fd.readline() == b'hello\n'
            assert fd.read() == b''
            fd.close()

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', 0))
        server.listen(50)
        killer = eventlet.spawn(accept_close_early, server)
        did_it_work(server)
        killer.wait()

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', 0))
        server.listen(50)
        killer = eventlet.spawn(accept_close_late, server)
        did_it_work(server)
        killer.wait()

    def test_del_closes_socket(self):
        def accept_once(listener):
            # delete/overwrite the original conn
            # object, only keeping the file object around
            # closing the file object should close everything
            try:
                conn, addr = listener.accept()
                conn = conn.makefile('wb')
                conn.write(b'hello\n')
                conn.close()
                gc.collect()
                self.assertWriteToClosedFileRaises(conn)
            finally:
                listener.close()

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', 0))
        server.listen(50)
        killer = eventlet.spawn(accept_once, server)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(('127.0.0.1', server.getsockname()[1]))
        fd = client.makefile('rb')
        client.close()
        assert fd.read() == b'hello\n'
        assert fd.read() == b''

        killer.wait()

    def test_full_duplex(self):
        large_data = b'*' * 10 * min_buf_size()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        listener.listen(50)
        bufsized(listener)

        def send_large(sock):
            sock.sendall(large_data)

        def read_large(sock):
            result = sock.recv(len(large_data))
            while len(result) < len(large_data):
                result += sock.recv(len(large_data))
            self.assertEqual(result, large_data)

        def server():
            (sock, addr) = listener.accept()
            sock = bufsized(sock)
            send_large_coro = eventlet.spawn(send_large, sock)
            eventlet.sleep(0)
            result = sock.recv(10)
            expected = b'hello world'
            while len(result) < len(expected):
                result += sock.recv(10)
            self.assertEqual(result, expected)
            send_large_coro.wait()

        server_evt = eventlet.spawn(server)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(('127.0.0.1', listener.getsockname()[1]))
        bufsized(client)
        large_evt = eventlet.spawn(read_large, client)
        eventlet.sleep(0)
        client.sendall(b'hello world')
        server_evt.wait()
        large_evt.wait()
        client.close()

    def test_sendall(self):
        # test adapted from Marcus Cavanaugh's email
        # it may legitimately take a while, but will eventually complete
        self.timer.cancel()
        second_bytes = 10

        def test_sendall_impl(many_bytes):
            bufsize = max(many_bytes // 15, 2)

            def sender(listener):
                (sock, addr) = listener.accept()
                sock = bufsized(sock, size=bufsize)
                sock.sendall(b'x' * many_bytes)
                sock.sendall(b'y' * second_bytes)

            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("", 0))
            listener.listen(50)
            sender_coro = eventlet.spawn(sender, listener)
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(('127.0.0.1', listener.getsockname()[1]))
            bufsized(client, size=bufsize)
            total = 0
            while total < many_bytes:
                data = client.recv(min(many_bytes - total, many_bytes // 10))
                if not data:
                    break
                total += len(data)

            total2 = 0
            while total < second_bytes:
                data = client.recv(second_bytes)
                if not data:
                    break
                total2 += len(data)

            sender_coro.wait()
            client.close()

        for how_many in (1000, 10000, 100000, 1000000):
            test_sendall_impl(how_many)

    def test_wrap_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', 0))
        sock.listen(50)
        ssl.wrap_socket(sock)

    def test_timeout_and_final_write(self):
        # This test verifies that a write on a socket that we've
        # stopped listening for doesn't result in an incorrect switch
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', 0))
        server.listen(50)
        bound_port = server.getsockname()[1]

        def sender(evt):
            s2, addr = server.accept()
            wrap_wfile = s2.makefile('wb')

            eventlet.sleep(0.02)
            wrap_wfile.write(b'hi')
            s2.close()
            evt.send(b'sent via event')

        evt = event.Event()
        eventlet.spawn(sender, evt)
        # lets the socket enter accept mode, which
        # is necessary for connect to succeed on windows
        eventlet.sleep(0)
        try:
            # try and get some data off of this pipe
            # but bail before any is sent
            eventlet.Timeout(0.01)
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(('127.0.0.1', bound_port))
            wrap_rfile = client.makefile()
            wrap_rfile.read(1)
            self.fail()
        except eventlet.TimeoutError:
            pass

        result = evt.wait()
        self.assertEqual(result, b'sent via event')
        server.close()
        client.close()

    @tests.skip_with_pyevent
    def test_raised_multiple_readers(self):
        debug.hub_prevent_multiple_readers(True)

        def handle(sock, addr):
            sock.recv(1)
            sock.sendall(b"a")
            raise eventlet.StopServe()

        listener = eventlet.listen(('127.0.0.1', 0))
        eventlet.spawn(eventlet.serve, listener, handle)

        def reader(s):
            s.recv(1)

        s = eventlet.connect(('127.0.0.1', listener.getsockname()[1]))
        a = eventlet.spawn(reader, s)
        eventlet.sleep(0)
        self.assertRaises(RuntimeError, s.recv, 1)
        s.sendall(b'b')
        a.wait()

    @tests.skip_with_pyevent
    @tests.skip_if(using_epoll_hub)
    @tests.skip_if(using_kqueue_hub)
    def test_closure(self):
        def spam_to_me(address):
            sock = eventlet.connect(address)
            while True:
                try:
                    sock.sendall(b'hello world')
                except socket.error as e:
                    if get_errno(e) == errno.EPIPE:
                        return
                    raise

        server = eventlet.listen(('127.0.0.1', 0))
        sender = eventlet.spawn(spam_to_me, server.getsockname())
        client, address = server.accept()
        server.close()

        def reader():
            try:
                while True:
                    data = client.recv(1024)
                    assert data
            except socket.error as e:
                # we get an EBADF because client is closed in the same process
                # (but a different greenthread)
                if get_errno(e) != errno.EBADF:
                    raise

        def closer():
            client.close()

        reader = eventlet.spawn(reader)
        eventlet.spawn_n(closer)
        reader.wait()
        sender.wait()

    def test_invalid_connection(self):
        # find an unused port by creating a socket then closing it
        listening_socket = eventlet.listen(('127.0.0.1', 0))
        port = listening_socket.getsockname()[1]
        listening_socket.close()
        self.assertRaises(socket.error, eventlet.connect, ('127.0.0.1', port))

    def test_zero_timeout_and_back(self):
        listen = eventlet.listen(('', 0))
        # Keep reference to server side of socket
        server = eventlet.spawn(listen.accept)
        client = eventlet.connect(listen.getsockname())

        client.settimeout(0.05)
        # Now must raise socket.timeout
        self.assertRaises(socket.timeout, client.recv, 1)

        client.settimeout(0)
        # Now must raise socket.error with EAGAIN
        try:
            client.recv(1)
            assert False
        except socket.error as e:
            assert get_errno(e) == errno.EAGAIN

        client.settimeout(0.05)
        # Now socket.timeout again
        self.assertRaises(socket.timeout, client.recv, 1)
        server.wait()

    def test_default_nonblocking(self):
        sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        flags = fcntl.fcntl(sock1.fd.fileno(), fcntl.F_GETFL)
        assert flags & os.O_NONBLOCK

        sock2 = socket.socket(sock1.fd)
        flags = fcntl.fcntl(sock2.fd.fileno(), fcntl.F_GETFL)
        assert flags & os.O_NONBLOCK

    def test_dup_nonblocking(self):
        sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        flags = fcntl.fcntl(sock1.fd.fileno(), fcntl.F_GETFL)
        assert flags & os.O_NONBLOCK

        sock2 = sock1.dup()
        flags = fcntl.fcntl(sock2.fd.fileno(), fcntl.F_GETFL)
        assert flags & os.O_NONBLOCK

    def test_skip_nonblocking(self):
        sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        fd = sock1.fd.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        flags = fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
        assert flags & os.O_NONBLOCK == 0

        sock2 = socket.socket(sock1.fd, set_nonblocking=False)
        flags = fcntl.fcntl(sock2.fd.fileno(), fcntl.F_GETFL)
        assert flags & os.O_NONBLOCK == 0

    def test_sockopt_interface(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) == b'\000'
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def test_socketpair_select(self):
        # https://github.com/eventlet/eventlet/pull/25
        s1, s2 = socket.socketpair()
        assert select.select([], [s1], [], 0) == ([], [s1], [])
        assert select.select([], [s1], [], 0) == ([], [s1], [])

    def test_shutdown_safe(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.close()
        # should not raise
        greenio.shutdown_safe(sock)


def test_get_fileno_of_a_socket_works():
    class DummySocket(object):
        def fileno(self):
            return 123
    assert select.get_fileno(DummySocket()) == 123


def test_get_fileno_of_an_int_works():
    assert select.get_fileno(123) == 123


expected_get_fileno_type_error_message = (
    'Expected int or long, got <%s \'str\'>' % ('type' if six.PY2 else 'class'))


def test_get_fileno_of_wrong_type_fails():
    try:
        select.get_fileno('foo')
    except TypeError as ex:
        assert str(ex) == expected_get_fileno_type_error_message
    else:
        assert False, 'Expected TypeError not raised'


def test_get_fileno_of_a_socket_with_fileno_returning_wrong_type_fails():
    class DummySocket(object):
        def fileno(self):
            return 'foo'
    try:
        select.get_fileno(DummySocket())
    except TypeError as ex:
        assert str(ex) == expected_get_fileno_type_error_message
    else:
        assert False, 'Expected TypeError not raised'


class TestGreenPipe(tests.LimitedTestCase):
    @tests.skip_on_windows
    def setUp(self):
        super(self.__class__, self).setUp()
        self.tempdir = tempfile.mkdtemp('_green_pipe_test')

    def tearDown(self):
        shutil.rmtree(self.tempdir)
        super(self.__class__, self).tearDown()

    def test_pipe(self):
        r, w = os.pipe()
        rf = greenio.GreenPipe(r, 'rb')
        wf = greenio.GreenPipe(w, 'wb', 0)

        def sender(f, content):
            for ch in map(six.int2byte, six.iterbytes(content)):
                eventlet.sleep(0.0001)
                f.write(ch)
            f.close()

        one_line = b"12345\n"
        eventlet.spawn(sender, wf, one_line * 5)
        for i in range(5):
            line = rf.readline()
            eventlet.sleep(0.01)
            self.assertEqual(line, one_line)
        self.assertEqual(rf.readline(), b'')

    def test_pipe_read(self):
        # ensure that 'readline' works properly on GreenPipes when data is not
        # immediately available (fd is nonblocking, was raising EAGAIN)
        # also ensures that readline() terminates on '\n' and '\r\n'
        r, w = os.pipe()

        r = greenio.GreenPipe(r, 'rb')
        w = greenio.GreenPipe(w, 'wb')

        def writer():
            eventlet.sleep(.1)

            w.write(b'line\n')
            w.flush()

            w.write(b'line\r\n')
            w.flush()

        gt = eventlet.spawn(writer)

        eventlet.sleep(0)

        line = r.readline()
        self.assertEqual(line, b'line\n')

        line = r.readline()
        self.assertEqual(line, b'line\r\n')

        gt.wait()

    def test_pipe_writes_large_messages(self):
        r, w = os.pipe()

        r = greenio.GreenPipe(r, 'rb')
        w = greenio.GreenPipe(w, 'wb')

        large_message = b"".join([1024 * six.int2byte(i) for i in range(65)])

        def writer():
            w.write(large_message)
            w.close()

        gt = eventlet.spawn(writer)

        for i in range(65):
            buf = r.read(1024)
            expected = 1024 * six.int2byte(i)
            self.assertEqual(
                buf, expected,
                "expected=%r..%r, found=%r..%r iter=%d"
                % (expected[:4], expected[-4:], buf[:4], buf[-4:], i))
        gt.wait()

    def test_seek_on_buffered_pipe(self):
        f = greenio.GreenPipe(self.tempdir + "/TestFile", 'wb+', 1024)
        self.assertEqual(f.tell(), 0)
        f.seek(0, 2)
        self.assertEqual(f.tell(), 0)
        f.write(b'1234567890')
        f.seek(0, 2)
        self.assertEqual(f.tell(), 10)
        f.seek(0)
        value = f.read(1)
        self.assertEqual(value, b'1')
        self.assertEqual(f.tell(), 1)
        value = f.read(1)
        self.assertEqual(value, b'2')
        self.assertEqual(f.tell(), 2)
        f.seek(0, 1)
        self.assertEqual(f.readline(), b'34567890')
        f.seek(-5, 1)
        self.assertEqual(f.readline(), b'67890')
        f.seek(0)
        self.assertEqual(f.readline(), b'1234567890')
        f.seek(0, 2)
        self.assertEqual(f.readline(), b'')

    def test_truncate(self):
        f = greenio.GreenPipe(self.tempdir + "/TestFile", 'wb+', 1024)
        f.write(b'1234567890')
        f.truncate(9)
        self.assertEqual(f.tell(), 9)


class TestGreenIoLong(tests.LimitedTestCase):
    TEST_TIMEOUT = 10  # the test here might take a while depending on the OS

    @tests.skip_with_pyevent
    def test_multiple_readers(self, clibufsize=False):
        debug.hub_prevent_multiple_readers(False)
        recvsize = 2 * min_buf_size()
        sendsize = 10 * recvsize

        # test that we can have multiple coroutines reading
        # from the same fd.  We make no guarantees about which one gets which
        # bytes, but they should both get at least some
        def reader(sock, results):
            while True:
                data = sock.recv(recvsize)
                if not data:
                    break
                results.append(data)

        results1 = []
        results2 = []
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        listener.listen(50)

        def server():
            (sock, addr) = listener.accept()
            sock = bufsized(sock)
            try:
                c1 = eventlet.spawn(reader, sock, results1)
                c2 = eventlet.spawn(reader, sock, results2)
                try:
                    c1.wait()
                    c2.wait()
                finally:
                    c1.kill()
                    c2.kill()
            finally:
                sock.close()

        server_coro = eventlet.spawn(server)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(('127.0.0.1', listener.getsockname()[1]))
        if clibufsize:
            bufsized(client, size=sendsize)
        else:
            bufsized(client)
        client.sendall(b'*' * sendsize)
        client.close()
        server_coro.wait()
        listener.close()
        assert len(results1) > 0
        assert len(results2) > 0
        debug.hub_prevent_multiple_readers()

    @tests.skipped  # by rdw because it fails but it's not clear how to make it pass
    @tests.skip_with_pyevent
    def test_multiple_readers2(self):
        self.test_multiple_readers(clibufsize=True)


class TestGreenIoStarvation(tests.LimitedTestCase):
    # fixme: this doesn't succeed, because of eventlet's predetermined
    # ordering.  two processes, one with server, one with client eventlets
    # might be more reliable?

    TEST_TIMEOUT = 300  # the test here might take a while depending on the OS

    @tests.skipped  # by rdw, because it fails but it's not clear how to make it pass
    @tests.skip_with_pyevent
    def test_server_starvation(self, sendloops=15):
        recvsize = 2 * min_buf_size()
        sendsize = 10000 * recvsize

        results = [[] for i in range(5)]

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        listener.listen(50)

        base_time = time.time()

        def server(my_results):
            sock, addr = listener.accept()

            datasize = 0

            t1 = None
            t2 = None
            try:
                while True:
                    data = sock.recv(recvsize)
                    if not t1:
                        t1 = time.time() - base_time
                    if not data:
                        t2 = time.time() - base_time
                        my_results.append(datasize)
                        my_results.append((t1, t2))
                        break
                    datasize += len(data)
            finally:
                sock.close()

        def client():
            pid = os.fork()
            if pid:
                return pid

            client = _orig_sock.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(('127.0.0.1', port))

            bufsized(client, size=sendsize)

            for i in range(sendloops):
                client.sendall(b'*' * sendsize)
            client.close()
            os._exit(0)

        clients = []
        servers = []
        for r in results:
            servers.append(eventlet.spawn(server, r))
        for r in results:
            clients.append(client())

        for s in servers:
            s.wait()
        for c in clients:
            os.waitpid(c, 0)

        listener.close()

        # now test that all of the server receive intervals overlap, and
        # that there were no errors.
        for r in results:
            assert len(r) == 2, "length is %d not 2!: %s\n%s" % (len(r), r, results)
            assert r[0] == sendsize * sendloops
            assert len(r[1]) == 2
            assert r[1][0] is not None
            assert r[1][1] is not None

        starttimes = sorted(r[1][0] for r in results)
        endtimes = sorted(r[1][1] for r in results)
        runlengths = sorted(r[1][1] - r[1][0] for r in results)

        # assert that the last task started before the first task ended
        # (our no-starvation condition)
        assert starttimes[-1] < endtimes[0], \
            "Not overlapping: starts %s ends %s" % (starttimes, endtimes)

        maxstartdiff = starttimes[-1] - starttimes[0]

        assert maxstartdiff * 2 < runlengths[0], \
            "Largest difference in starting times more than twice the shortest running time!"
        assert runlengths[0] * 2 > runlengths[-1], \
            "Longest runtime more than twice as long as shortest!"


def test_set_nonblocking():
    sock = _orig_sock.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fileno = sock.fileno()
    orig_flags = fcntl.fcntl(fileno, fcntl.F_GETFL)
    assert orig_flags & os.O_NONBLOCK == 0
    greenio.set_nonblocking(sock)
    new_flags = fcntl.fcntl(fileno, fcntl.F_GETFL)
    assert new_flags == (orig_flags | os.O_NONBLOCK)


def test_socket_del_fails_gracefully_when_not_fully_initialized():
    # Regression introduced in da87716714689894f23d0db7b003f26d97031e83, reported in:
    # * GH #137 https://github.com/eventlet/eventlet/issues/137
    # * https://bugs.launchpad.net/oslo.messaging/+bug/1369999

    class SocketSubclass(socket.socket):

        def __init__(self):
            pass

    with capture_stderr() as err:
        SocketSubclass()

    assert err.getvalue() == ''


def test_double_close_219():
    tests.run_isolated('greenio_double_close_219.py')
