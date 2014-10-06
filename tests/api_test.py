import os
import socket
from unittest import TestCase, main

import eventlet
from eventlet import greenio, hubs, greenthread, spawn
from eventlet.green import ssl
from tests import skip_if_no_ssl


def check_hub():
    # Clear through the descriptor queue
    eventlet.sleep(0)
    eventlet.sleep(0)
    hub = hubs.get_hub()
    for nm in 'get_readers', 'get_writers':
        dct = getattr(hub, nm)()
        assert not dct, "hub.%s not empty: %s" % (nm, dct)
    # Stop the runloop (unless it's twistedhub which does not support that)
    if not getattr(hub, 'uses_twisted_reactor', None):
        hub.abort(True)
        assert not hub.running


class TestApi(TestCase):

    certificate_file = os.path.join(os.path.dirname(__file__), 'test_server.crt')
    private_key_file = os.path.join(os.path.dirname(__file__), 'test_server.key')

    def test_tcp_listener(self):
        socket = eventlet.listen(('0.0.0.0', 0))
        assert socket.getsockname()[0] == '0.0.0.0'
        socket.close()

        check_hub()

    def test_connect_tcp(self):
        def accept_once(listenfd):
            try:
                conn, addr = listenfd.accept()
                fd = conn.makefile(mode='wb')
                conn.close()
                fd.write(b'hello\n')
                fd.close()
            finally:
                listenfd.close()

        server = eventlet.listen(('0.0.0.0', 0))
        eventlet.spawn_n(accept_once, server)

        client = eventlet.connect(('127.0.0.1', server.getsockname()[1]))
        fd = client.makefile('rb')
        client.close()
        assert fd.readline() == b'hello\n'

        assert fd.read() == b''
        fd.close()

        check_hub()

    @skip_if_no_ssl
    def test_connect_ssl(self):
        def accept_once(listenfd):
            try:
                conn, addr = listenfd.accept()
                conn.write(b'hello\r\n')
                greenio.shutdown_safe(conn)
                conn.close()
            finally:
                greenio.shutdown_safe(listenfd)
                listenfd.close()

        server = eventlet.wrap_ssl(
            eventlet.listen(('0.0.0.0', 0)),
            self.private_key_file,
            self.certificate_file,
            server_side=True
        )
        eventlet.spawn_n(accept_once, server)

        raw_client = eventlet.connect(('127.0.0.1', server.getsockname()[1]))
        client = ssl.wrap_socket(raw_client)
        fd = socket._fileobject(client, 'rb', 8192)

        assert fd.readline() == b'hello\r\n'
        try:
            self.assertEqual(b'', fd.read(10))
        except greenio.SSL.ZeroReturnError:
            # if it's a GreenSSL object it'll do this
            pass
        greenio.shutdown_safe(client)
        client.close()

        check_hub()

    def test_001_trampoline_timeout(self):
        server_sock = eventlet.listen(('127.0.0.1', 0))
        bound_port = server_sock.getsockname()[1]

        def server(sock):
            client, addr = sock.accept()
            eventlet.sleep(0.1)
        server_evt = spawn(server, server_sock)
        eventlet.sleep(0)
        try:
            desc = eventlet.connect(('127.0.0.1', bound_port))
            hubs.trampoline(desc, read=True, write=False, timeout=0.001)
        except eventlet.TimeoutError:
            pass  # test passed
        else:
            assert False, "Didn't timeout"

        server_evt.wait()
        check_hub()

    def test_timeout_cancel(self):
        server = eventlet.listen(('0.0.0.0', 0))
        bound_port = server.getsockname()[1]

        done = [False]

        def client_closer(sock):
            while True:
                (conn, addr) = sock.accept()
                conn.close()

        def go():
            desc = eventlet.connect(('127.0.0.1', bound_port))
            try:
                hubs.trampoline(desc, read=True, timeout=0.1)
            except eventlet.TimeoutError:
                assert False, "Timed out"

            server.close()
            desc.close()
            done[0] = True

        greenthread.spawn_after_local(0, go)

        server_coro = eventlet.spawn(client_closer, server)
        while not done[0]:
            eventlet.sleep(0)
        eventlet.kill(server_coro)

        check_hub()

    def test_killing_dormant(self):
        DELAY = 0.1
        state = []

        def test():
            try:
                state.append('start')
                eventlet.sleep(DELAY)
            except:
                state.append('except')
                # catching GreenletExit
                pass
            # when switching to hub, hub makes itself the parent of this greenlet,
            # thus after the function's done, the control will go to the parent
            eventlet.sleep(0)
            state.append('finished')

        g = eventlet.spawn(test)
        eventlet.sleep(DELAY / 2)
        self.assertEqual(state, ['start'])
        eventlet.kill(g)
        # will not get there, unless switching is explicitly scheduled by kill
        self.assertEqual(state, ['start', 'except'])
        eventlet.sleep(DELAY)
        self.assertEqual(state, ['start', 'except', 'finished'])

    def test_nested_with_timeout(self):
        def func():
            return eventlet.with_timeout(0.2, eventlet.sleep, 2, timeout_value=1)

        try:
            eventlet.with_timeout(0.1, func)
            self.fail(u'Expected TimeoutError')
        except eventlet.TimeoutError:
            pass


class Foo(object):
    pass


if __name__ == '__main__':
    main()
