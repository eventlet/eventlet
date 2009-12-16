import os
import os.path
import socket
from unittest import TestCase, main

from eventlet import api
from eventlet import greenio
from eventlet import util


def check_hub():
    # Clear through the descriptor queue
    api.sleep(0)
    api.sleep(0)
    hub = api.get_hub()
    for nm in 'get_readers', 'get_writers':
        dct = getattr(hub, nm)()
        assert not dct, "hub.%s not empty: %s" % (nm, dct)
    # Stop the runloop (unless it's twistedhub which does not support that)
    if not getattr(api.get_hub(), 'uses_twisted_reactor', None):
        api.get_hub().abort()
        api.sleep(0)
        ### ??? assert not api.get_hub().running


class TestApi(TestCase):
    mode = 'static'

    certificate_file = os.path.join(os.path.dirname(__file__), 'test_server.crt')
    private_key_file = os.path.join(os.path.dirname(__file__), 'test_server.key')

    def test_tcp_listener(self):
        socket = api.tcp_listener(('0.0.0.0', 0))
        assert socket.getsockname()[0] == '0.0.0.0'
        socket.close()

        check_hub()

    def test_connect_tcp(self):
        def accept_once(listenfd):
            try:
                conn, addr = listenfd.accept()
                fd = conn.makefile()
                conn.close()
                fd.write('hello\n')
                fd.close()
            finally:
                listenfd.close()

        server = api.tcp_listener(('0.0.0.0', 0))
        api.spawn(accept_once, server)

        client = api.connect_tcp(('127.0.0.1', server.getsockname()[1]))
        fd = client.makefile()
        client.close()
        assert fd.readline() == 'hello\n'

        assert fd.read() == ''
        fd.close()

        check_hub()

    def test_connect_ssl(self):
        def accept_once(listenfd):
            try:
                conn, addr = listenfd.accept()
                conn.write('hello\r\n')
                greenio.shutdown_safe(conn)
                conn.close()
            finally:
                greenio.shutdown_safe(listenfd)
                listenfd.close()

        server = api.ssl_listener(('0.0.0.0', 0),
                                  self.certificate_file,
                                  self.private_key_file)
        api.spawn(accept_once, server)

        raw_client = api.connect_tcp(('127.0.0.1', server.getsockname()[1]))
        client = util.wrap_ssl(raw_client)
        fd = socket._fileobject(client, 'rb', 8192)

        assert fd.readline() == 'hello\r\n'
        try:
            self.assertEquals('', fd.read(10))
        except greenio.SSL.ZeroReturnError:
            # if it's a GreenSSL object it'll do this
            pass
        greenio.shutdown_safe(client)
        client.close()
        
        check_hub()

    def test_001_trampoline_timeout(self):
        from eventlet import coros
        server_sock = api.tcp_listener(('127.0.0.1', 0))
        bound_port = server_sock.getsockname()[1]
        def server(sock):
            client, addr = sock.accept()
            api.sleep(0.1)
        server_evt = coros.execute(server, server_sock)
        api.sleep(0)
        try:
            desc = greenio.GreenSocket(util.tcp_socket())
            desc.connect(('127.0.0.1', bound_port))
            api.trampoline(desc, read=True, write=False, timeout=0.001)
        except api.TimeoutError:
            pass # test passed
        else:
            assert False, "Didn't timeout"

        server_evt.wait()
        check_hub()

    def test_timeout_cancel(self):
        server = api.tcp_listener(('0.0.0.0', 0))
        bound_port = server.getsockname()[1]

        done = [False]
        def client_closer(sock):
            while True:
                (conn, addr) = sock.accept()
                conn.close()

        def go():
            client = util.tcp_socket()

            desc = greenio.GreenSocket(client)
            desc.connect(('127.0.0.1', bound_port))
            try:
                api.trampoline(desc, read=True, timeout=0.1)
            except api.TimeoutError:
                assert False, "Timed out"

            server.close()
            client.close()
            done[0] = True

        api.call_after(0, go)

        server_coro = api.spawn(client_closer, server)
        while not done[0]:
            api.sleep(0)
        api.kill(server_coro)

        check_hub()

    if not getattr(api.get_hub(), 'uses_twisted_reactor', None):
        def test_explicit_hub(self):
            oldhub = api.get_hub()
            try:
                api.use_hub(Foo)
                assert isinstance(api.get_hub(), Foo), api.get_hub()
            finally:
                api._threadlocal.hub = oldhub
            check_hub()

    def test_named(self):
        named_foo = api.named('tests.api_test.Foo')
        self.assertEquals(
            named_foo.__name__,
            "Foo")

    def test_naming_missing_class(self):
        self.assertRaises(
            ImportError, api.named, 'this_name_should_hopefully_not_exist.Foo')

    def test_timeout_and_final_write(self):
        # This test verifies that a write on a socket that we've
        # stopped listening for doesn't result in an incorrect switch
        server = api.tcp_listener(('127.0.0.1', 0))
        bound_port = server.getsockname()[1]
        
        def sender(evt):
            s2, addr = server.accept()
            wrap_wfile = s2.makefile()
            
            api.sleep(0.02)
            wrap_wfile.write('hi')
            s2.close()
            evt.send('sent via event')

        from eventlet import coros
        evt = coros.Event()
        api.spawn(sender, evt)
        api.sleep(0)  # lets the socket enter accept mode, which
                      # is necessary for connect to succeed on windows
        try:
            # try and get some data off of this pipe
            # but bail before any is sent
            api.exc_after(0.01, api.TimeoutError)
            client = api.connect_tcp(('127.0.0.1', bound_port))
            wrap_rfile = client.makefile()
            _c = wrap_rfile.read(1)
            self.fail()
        except api.TimeoutError:
            pass

        result = evt.wait()
        self.assertEquals(result, 'sent via event')
        server.close()
        client.close()
        
        
    def test_killing_dormant(self):
        DELAY = 0.1
        state = []
        def test():
            try:
                state.append('start')
                api.sleep(DELAY)
            except:
                state.append('except')
                # catching GreenletExit
                pass
            # when switching to hub, hub makes itself the parent of this greenlet,
            # thus after the function's done, the control will go to the parent
            # QQQ why the first sleep is not enough?
            api.sleep(0)
            state.append('finished')
        g = api.spawn(test)
        api.sleep(DELAY/2)
        assert state == ['start'], state
        api.kill(g)
        # will not get there, unless switching is explicitly scheduled by kill
        assert state == ['start', 'except'], state
        api.sleep(DELAY)
        assert state == ['start', 'except', 'finished'], state

    def test_nested_with_timeout(self):
        def func():
            return api.with_timeout(0.2, api.sleep, 2, timeout_value=1)
        self.assertRaises(api.TimeoutError, api.with_timeout, 0.1, func)




class Foo(object):
    pass


if __name__ == '__main__':
    main()

