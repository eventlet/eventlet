# Derived from:
# https://www.piware.de/2011/01/creating-an-https-server-in-python/
# but using ssl.SSLContext.wrap_socket() instead of deprecated ssl.wrap_socket()

try:
    # Python 3
    from http.server import HTTPServer, BaseHTTPRequestHandler
except ImportError:
    # Python 2
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler

from multiprocessing import Process, Event, Queue
import os
import ssl
import socket
import subprocess
import sys
import tempfile


class Error(Exception):
    pass


class Server(HTTPServer):
    # This flag is on by default in HTTPServer. But don't share our port --
    # produces inexplicable transient results!
    allow_reuse_address = False


class TestRequestHandler(BaseHTTPRequestHandler):
    """
    This subclass of BaseHTTPRequestHandler simply provides dummy responses.
    """
    def do_HEAD(self):
        self.answer(False)

    def do_GET(self):
        self.answer(True)

    def answer(self, withdata=True):
        response = b"""\
============================================================================
-------------------------------- IT WORKS! ---------------------------------
============================================================================
"""
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        if withdata:
            self.wfile.write(response)


def create_cert(certfile, keyfile):
    # Get the Common Name as our FQDN
    fqdn = socket.getfqdn()
    # https://stackoverflow.com/a/41366949
    command = ['openssl', 'req', '-x509', '-newkey', 'rsa:4096',
               '-sha256', '-days', '30', '-nodes',
               '-keyout', keyfile, '-out', certfile,
               '-subj', u'/CN={}'.format(fqdn),
               ]
    subjectAltName = u'subjectAltName=DNS:{},IP:127.0.0.1'.format(fqdn)
    # Unfortunately, as of 2019-09-12, we can't (yet) count on the shorthand form:
    # command.extend(['-addext', subjectAltName])
    # so create a separate config file
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as config:
        config_name = config.name
        config_data = u"""\
[req]
distinguished_name=req
[san]
{}
""".format(subjectAltName)
        config.write(config_data)

    try:
        command.extend(['-extensions', 'san', '-config', config_name])
        print(' '.join(command))
        subprocess.check_call(command)
    except Exception:
        print('config data:')
        print(config_data)
        raise
    finally:
        os.remove(config_name)


def serve(portqueue, stop):
    # Binding to port 0 requests the OS to select an unused port
    httpd = Server(('localhost', 0), TestRequestHandler)
    # tell parent process which port was selected
    portqueue.put(httpd.server_port)

    chandle, certfile = tempfile.mkstemp(suffix='-cert.pem')
    os.close(chandle)
    khandle, keyfile = tempfile.mkstemp(suffix='-key.pem')
    os.close(khandle)
    try:
        # populate the certfile and keyfile
        create_cert(certfile=certfile, keyfile=keyfile)
        # set up to convert to an HTTPS server
        # We need an SSLContext instance because ssl.wrap_socket() is
        # deprecated in favor of SSLContext.wrap_socket(). But it is
        # recommended that you use create_default_context() instead of
        # directly instantiating SSLContext yourself. Specifying CLIENT_AUTH
        # means this will be a server-side SSLContext, which is admittedly
        # confusing.
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    finally:
        print(u'Removing:\n{}\n{}'.format(certfile, keyfile))
        os.remove(certfile)
        os.remove(keyfile)

    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    print(u'Listening on {}:{}'.format('localhost', httpd.server_port))

    # SocketServer.BaseServer.handle_request() honors a 'timeout'
    # attribute, if it's set to something other than None.
    # We pick 0.5 seconds because that's the default poll timeout for
    # BaseServer.serve_forever().
    httpd.timeout = 0.5
    # Frequently check whether parent process says it's time to quit
    while not stop.is_set():
        # Setting server_inst.timeout is what keeps this handle_request()
        # call from blocking "forever." Interestingly, looping over
        # handle_request() with a timeout is very like the implementation
        # of serve_forever(). We just check a different flag to break out.
        httpd.handle_request()


def client(port):
    # importantly, we don't monkey_patch() socket until AFTER launching the
    # server process
    import eventlet
    # This monkey_patch() call alone drives Issue #526
    eventlet.monkey_patch(socket=True)
    import requests

    response = requests.get(u'https://localhost:{}/whatevah'.format(port), verify=False)
    response.raise_for_status()
    print(response.text)


def main():
    # server stuff: get a Queue by which the server process will send the port
    # number back to us, and an Event by which we can tell it to stop.
    portqueue = Queue()
    stop = Event()
    server = Process(target=serve, args=(portqueue, stop))
    server.start()
    port = portqueue.get()

    # client stuff
    try:
        client(port)
    finally:
        # once the client is done, tell the server to stop
        stop.set()
        # then wait for it to do so -- but not TOO long
        server.join(5)
        # If a problem develops during the SSL handshake, it hangs the
        # server's handle_request() call, so we never return to the loop to
        # check stop.is_set(). In that case, just kill the child process.
        # Interestingly, join(timeout) doesn't return any indication as to
        # whether the join() succeeded or timed out -- have to check
        # is_alive().
        if server.is_alive():
            server.terminate()
            print(u'Server forcibly terminated')
        else:
            print(u'Server gracefully terminated')


if __name__ == "__main__":
    try:
        sys.exit(main(*sys.argv[1:]))
    except Error as err:
        sys.exit(str(err))
