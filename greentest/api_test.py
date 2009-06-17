# @author Donovan Preston
#
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

import os
import os.path
from unittest import TestCase, main

from eventlet import api
from eventlet import greenio
from eventlet import util


def check_hub():
    # Clear through the descriptor queue
    api.sleep(0)
    api.sleep(0)
    hub = api.get_hub()
    for nm in 'get_readers', 'get_writers', 'get_excs':
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
                fd = conn.makeGreenFile()
                conn.close()
                fd.write('hello\n')
                fd.close()
            finally:
                listenfd.close()

        server = api.tcp_listener(('0.0.0.0', 0))
        api.spawn(accept_once, server)

        client = api.connect_tcp(('127.0.0.1', server.getsockname()[1]))
        fd = client.makeGreenFile()
        client.close()
        assert fd.readline() == 'hello\n'

        assert fd.read() == ''
        fd.close()

        check_hub()

    def test_connect_ssl(self):
        def accept_once(listenfd):
            try:
                conn, addr = listenfd.accept()
                fl = conn.makeGreenFile('w')
                fl.write('hello\r\n')
                fl.close()
                conn.close()
            finally:
                listenfd.close()

        server = api.ssl_listener(('0.0.0.0', 0),
                                  self.certificate_file,
                                  self.private_key_file)
        api.spawn(accept_once, server)

        client = util.wrap_ssl(
            api.connect_tcp(('127.0.0.1', server.getsockname()[1])))
        client = client.makeGreenFile()

        assert client.readline() == 'hello\r\n'
        assert client.read() == ''
        client.close()

    def test_server(self):
        connected = []
        server = api.tcp_listener(('0.0.0.0', 0))
        bound_port = server.getsockname()[1]

        def accept_twice((conn, addr)):
            connected.append(True)
            conn.close()
            if len(connected) == 2:
                server.close()

        api.call_after(0, api.connect_tcp, ('127.0.0.1', bound_port))
        api.call_after(0, api.connect_tcp, ('127.0.0.1', bound_port))
        try:
            api.tcp_server(server, accept_twice)
        except:
            api.sleep(0.1)
            raise

        assert len(connected) == 2
        check_hub()

    def test_001_trampoline_timeout(self):
        server = api.tcp_listener(('0.0.0.0', 0))
        bound_port = server.getsockname()[1]

        try:
            desc = greenio.GreenSocket(util.tcp_socket())
            desc.connect(('127.0.0.1', bound_port))
            api.trampoline(desc, read=True, write=False, timeout=0.1)
        except api.TimeoutError:
            pass # test passed
        else:
            assert False, "Didn't timeout"

        check_hub()

    def test_timeout_cancel(self):
        server = api.tcp_listener(('0.0.0.0', 0))
        bound_port = server.getsockname()[1]

        def client_connected((conn, addr)):
            conn.close()

        def go():
            client = util.tcp_socket()

            desc = greenio.GreenSocket(client)
            desc.connect(('127.0.0.1', bound_port))
            try:
                api.trampoline(desc, read=True, write=True, timeout=0.1)
            except api.TimeoutError:
                assert False, "Timed out"

            server.close()
            client.close()

        api.call_after(0, go)

        api.tcp_server(server, client_connected)

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
        named_foo = api.named('api_test.Foo')
        self.assertEquals(
            named_foo.__name__,
            "Foo")

    def test_naming_missing_class(self):
        self.assertRaises(
            ImportError, api.named, 'this_name_should_hopefully_not_exist.Foo')

    def test_timeout_and_final_write(self):
        # This test verifies that a write on a socket that we've
        # stopped listening for doesn't result in an incorrect switch
        rpipe, wpipe = os.pipe()
        rfile = os.fdopen(rpipe,"r",0)
        wrap_rfile = greenio.GreenPipe(rfile)
        wfile = os.fdopen(wpipe,"w",0)
        wrap_wfile = greenio.GreenPipe(wfile)

        def sender(evt):
            api.sleep(0.02)
            wrap_wfile.write('hi')
            evt.send('sent via event')

        from eventlet import coros
        evt = coros.event()
        api.spawn(sender, evt)
        try:
            # try and get some data off of this pipe
            # but bail before any is sent
            api.exc_after(0.01, api.TimeoutError)
            _c = wrap_rfile.read(1)
            self.fail()
        except api.TimeoutError:
            pass

        result = evt.wait()
        self.assertEquals(result, 'sent via event')


class Foo(object):
    pass


if __name__ == '__main__':
    main()

