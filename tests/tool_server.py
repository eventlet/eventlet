__test__ = False

import contextlib
from functools import partial
import os
import ssl
from http.server import BaseHTTPRequestHandler

import eventlet

tls_dir = os.path.join(os.path.dirname(__file__), "tls")
CA_CERTS = os.path.join(tls_dir, "ca.pem")
CLIENT_PEM = os.path.join(tls_dir, "client.pem")
SERVER_PEM = os.path.join(tls_dir, "server.pem")
SERVER_KEY = os.path.join(tls_dir, "server.key")
SERVER_CHAIN = os.path.join(tls_dir, "server_chain.pem")


class ServerGracefulStop(Exception):
    pass


def server_listener(accept, consume, timeout, tls_skip_errors):
    while True:
        try:
            client, client_address = accept()
        except ServerGracefulStop as e:
            return
        except ssl.SSLError as e:
            if e.reason in tls_skip_errors:
                return
            raise

        client.settimeout(timeout)
        consume(client, client_address)


DEFAULT_TLS_SKIP_ERRORS = ("TLSV1_ALERT_UNKNOWN_CA",)


@contextlib.contextmanager
def tcp_server(
    fun,
    bind=("localhost", 0),
    timeout=1,
    tls=False,
    tls_skip_errors=DEFAULT_TLS_SKIP_ERRORS,
    pool_size=50,
):
    listener_thread = None
    pool = eventlet.GreenPool(pool_size)
    consume = partial(pool.spawn, fun)

    sock = eventlet.listen(bind)
    try:
        server_addr = sock.getsockname()
        server_addr = (bind[0], server_addr[1])
        if tls:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH, cafile=CA_CERTS)
            ssl_context.load_cert_chain(SERVER_CHAIN)
            sock = ssl_context.wrap_socket(sock, server_side=True)

        listener_thread = pool.spawn(server_listener, sock.accept, consume, timeout, tls_skip_errors)
        yield server_addr
        listener_thread.kill(ServerGracefulStop())
    finally:
        sock.close()
        if listener_thread is not None:
            listener_thread.kill()
        pool.waitall()


@contextlib.contextmanager
def http_server(fun, scheme="", tls=False, **kwargs):
    assert scheme in (
        "",
        "http",
        "https",
    ), 'tests.server_socket: invalid scheme="{}"'.format(scheme)

    if scheme == "":
        scheme = "https" if tls else "http"

    class RequestHandler(BaseHTTPRequestHandler):
        def log_request(self, code="-", size="-"):
            pass

        def _dispatch(self):
            return fun(self)

        def __getattribute__(self, name: str):
            if name.startswith("do_"):
                return self._dispatch
            return super().__getattribute__(name)

    def wrap(client, addr):
        RequestHandler(client, addr, None)

    with tcp_server(wrap, tls=tls, **kwargs) as addr:
        yield "{scheme}://{host}:{port}/".format(scheme=scheme, host=addr[0], port=addr[1])


def http_server_const(status_code=200, body=b"", **kwargs):
    def fun(r: BaseHTTPRequestHandler):
        r.send_response(status_code)
        r.send_header("content-length", str(len(body)))
        r.end_headers()
        r.wfile.write(body)

    return http_server(fun, **kwargs)
