import os

import eventlet
from eventlet import backdoor
from eventlet.green import socket
import tests


def _print_hi(read, write):
    write("print('hi')\n")
    assert read() == "hi\n"
    assert read(4) == ">>> "


def _interact_close(server_thread, client, interact=_print_hi):
    f = client.makefile('rw')

    def read(n=None):
        buf = f.readline() if n is None else f.read(n)
        print("#", repr(buf))
        return buf

    def write(data):
        f.write(data)
        f.flush()

    assert 'Python' in read()
    read()  # build info
    read()  # help info
    assert 'InteractiveConsole' in read()
    assert read(4) == ">>> "

    interact(read, write)

    f.close()
    client.close()
    server_thread.kill()
    # wait for the console to discover that it's dead
    eventlet.sleep(0.1)


def _listen_connect(address, family=socket.AF_INET):
    listener = eventlet.listen(address, family=family)
    server_thread = eventlet.spawn(backdoor.backdoor_server, listener)
    client_sock = eventlet.connect(listener.getsockname(), family=family)
    return listener, server_thread, client_sock


class BackdoorTest(tests.LimitedTestCase):
    def test_server(self):
        _, server, client = _listen_connect(('localhost', 0))
        _interact_close(server, client)

    @tests.skip_if_no_ipv6
    def test_server_on_ipv6_socket(self):
        _, server, client = _listen_connect(('::', 0), socket.AF_INET6)
        _interact_close(server, client)

    def test_server_on_unix_socket(self):
        SOCKET_PATH = '/tmp/eventlet_backdoor_test.socket'
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        _, server, client = _listen_connect(SOCKET_PATH, socket.AF_UNIX)
        _interact_close(server, client)

    def test_quick_client_disconnect(self):
        listener, server, client1 = _listen_connect(("localhost", 0))
        client1.close()
        # can still reconnect; server is running
        client2 = eventlet.connect(listener.getsockname())
        client2.close()
        server.kill()
        # wait for the console to discover that it's dead
        eventlet.sleep(0.1)

    def test_multiline(self):
        _, server, client = _listen_connect(("localhost", 0))

        def multiline(read, write):
            write("print('1')\nprint('2')\nif True:\n    print('yes')\n\nprint('3')\n")
            assert read() == "1\n"
            assert read() == "2\n"
            assert read() == "... ... yes\n"
            assert read() == "3\n"
            assert read(4) == ">>> "

        _interact_close(server, client, interact=multiline)
