import sys
from eventlet.green import socket
from eventlet.green import SocketServer

__import_lst = ['DEFAULT_ERROR_MESSAGE', '_quote_html', '__version__', '__all__', 'BaseHTTPRequestHandler']
__BaseHTTPServer = __import__('BaseHTTPServer')
for var in __import_lst:
    exec "%s = __BaseHTTPServer.%s" % (var, var)


class HTTPServer(SocketServer.TCPServer):

    allow_reuse_address = 1    # Seems to make sense in testing environment

    def server_bind(self):
        """Override server_bind to store the server name."""
        SocketServer.TCPServer.server_bind(self)
        host, port = self.socket.getsockname()[:2]
        self.server_name = socket.getfqdn(host)
        self.server_port = port


class BaseHTTPRequestHandler(BaseHTTPRequestHandler):

   def address_string(self):
        host, port = self.client_address[:2]
        return socket.getfqdn(host)


def test(HandlerClass = BaseHTTPRequestHandler,
         ServerClass = HTTPServer, protocol="HTTP/1.0"):
    """Test the HTTP request handler class.

    This runs an HTTP server on port 8000 (or the first command line
    argument).

    """

    if sys.argv[1:]:
        port = int(sys.argv[1])
    else:
        port = 8000
    server_address = ('', port)

    HandlerClass.protocol_version = protocol
    httpd = ServerClass(server_address, HandlerClass)

    sa = httpd.socket.getsockname()
    print "Serving HTTP on", sa[0], "port", sa[1], "..."
    httpd.serve_forever()


if __name__ == '__main__':
    test()
