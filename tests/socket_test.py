import eventlet
from eventlet.green import socket
try:
    from eventlet.support import greendns
    has_greendns = True
except ImportError:
    has_greendns = False
from tests import skip_if


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


@skip_if(not has_greendns)
def test_dns_methods_are_green():
    assert socket.gethostbyname is greendns.gethostbyname
    assert socket.gethostbyname_ex is greendns.gethostbyname_ex
    assert socket.getaddrinfo is greendns.getaddrinfo
    assert socket.getnameinfo is greendns.getnameinfo


def test_socket_api_family():
    # It was named family_or_realsock
    # https://github.com/eventlet/eventlet/issues/319
    socket.socket(family=socket.AF_INET)
