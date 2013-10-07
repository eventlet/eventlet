import socket
import sys
import warnings


__original_socket__ = socket.socket
def tcp_socket():
    warnings.warn("eventlet.util.tcp_socket is deprecated. "
        "Please use the standard socket technique for this instead: "
        "sock = socket.socket()",
        DeprecationWarning, stacklevel=2)
    s = __original_socket__(socket.AF_INET, socket.SOCK_STREAM)
    return s


# if ssl is available, use eventlet.green.ssl for our ssl implementation
from eventlet.green import ssl
def wrap_ssl(sock, certificate=None, private_key=None, server_side=False):
    warnings.warn("eventlet.util.wrap_ssl is deprecated. "
        "Please use the eventlet.green.ssl.wrap_socket()",
        DeprecationWarning, stacklevel=2)
    return ssl.wrap_socket(
        sock,
        keyfile=private_key,
        certfile=certificate,
        server_side=server_side,
    )


def wrap_socket_with_coroutine_socket(use_thread_pool=None):
    warnings.warn("eventlet.util.wrap_socket_with_coroutine_socket() is now "
        "eventlet.patcher.monkey_patch(all=False, socket=True)",
        DeprecationWarning, stacklevel=2)
    from eventlet import patcher
    patcher.monkey_patch(all=False, socket=True)


def wrap_pipes_with_coroutine_pipes():
    warnings.warn("eventlet.util.wrap_pipes_with_coroutine_pipes() is now "
        "eventlet.patcher.monkey_patch(all=False, os=True)",
        DeprecationWarning, stacklevel=2)
    from eventlet import patcher
    patcher.monkey_patch(all=False, os=True)


def wrap_select_with_coroutine_select():
    warnings.warn("eventlet.util.wrap_select_with_coroutine_select() is now "
        "eventlet.patcher.monkey_patch(all=False, select=True)",
        DeprecationWarning, stacklevel=2)
    from eventlet import patcher
    patcher.monkey_patch(all=False, select=True)


def wrap_threading_local_with_coro_local():
    """
    monkey patch ``threading.local`` with something that is greenlet aware.
    Since greenlets cannot cross threads, so this should be semantically
    identical to ``threadlocal.local``
    """
    warnings.warn("eventlet.util.wrap_threading_local_with_coro_local() is now "
        "eventlet.patcher.monkey_patch(all=False, thread=True) -- though"
        "note that more than just _local is patched now.",
        DeprecationWarning, stacklevel=2)

    from eventlet import patcher
    patcher.monkey_patch(all=False, thread=True)


def socket_bind_and_listen(descriptor, addr=('', 0), backlog=50):
    warnings.warn("eventlet.util.socket_bind_and_listen is deprecated."
        "Please use the standard socket methodology for this instead:"
        "sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR, 1)"
        "sock.bind(addr)"
        "sock.listen(backlog)",
        DeprecationWarning, stacklevel=2)
    set_reuse_addr(descriptor)
    descriptor.bind(addr)
    descriptor.listen(backlog)
    return descriptor


def set_reuse_addr(descriptor):
    warnings.warn("eventlet.util.set_reuse_addr is deprecated."
        "Please use the standard socket methodology for this instead:"
        "sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR, 1)",
        DeprecationWarning, stacklevel=2)
    try:
        descriptor.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            descriptor.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) | 1)
    except socket.error:
        pass
