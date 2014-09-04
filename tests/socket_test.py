from eventlet.green import socket


def test_create_connection_error():
    try:
        socket.create_connection(('192.0.2.1', 80), timeout=0.1)
    except (IOError, OSError):
        pass
