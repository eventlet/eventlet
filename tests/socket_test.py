import eventlet
from eventlet.green import socket


def test_create_connection_error():
    try:
        socket.create_connection(('192.0.2.1', 80), timeout=0.1)
    except (IOError, OSError):
        pass


def test_recv_type():
    # https://github.com/eventlet/eventlet/issues/245
    # socket recv returning multiple data types
    # For this test to work, client and server have to be in separate
    # processes or OS threads. Just running two greenthreads gives
    # false test pass.
    threading = eventlet.patcher.original('threading')
    addr = []

    def server():
        sock = eventlet.listen(('127.0.0.1', 0))
        addr[:] = sock.getsockname()
        eventlet.sleep(0.2)

    server_thread = threading.Thread(target=server)
    server_thread.start()
    eventlet.sleep(0.1)
    sock = eventlet.connect(tuple(addr))
    s = sock.recv(1)
    assert isinstance(s, bytes)
