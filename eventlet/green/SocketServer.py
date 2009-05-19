__import_lst = ['__all__', '__version__', 'BaseServer', 'TCPServer', 'UDPServer', 'ForkingMixIn',
                'ThreadingMixIn', 'BaseRequestHandler', 'StreamRequestHandler', 'DatagramRequestHandler']
__SocketServer = __import__('SocketServer')
for var in __import_lst:
    exec "%s = __SocketServer.%s" % (var, var)


# QQQ ForkingMixIn should be fixed to use green waitpid?

from eventlet.green import socket

class TCPServer(TCPServer):

    def __init__(self, server_address, RequestHandlerClass):
        """Constructor.  May be extended, do not override."""
        BaseServer.__init__(self, server_address, RequestHandlerClass)
        self.socket = socket.socket(self.address_family,
                                    self.socket_type)
        self.server_bind()
        self.server_activate()

class UDPServer(UDPServer):

    def __init__(self, server_address, RequestHandlerClass):
        """Constructor.  May be extended, do not override."""
        BaseServer.__init__(self, server_address, RequestHandlerClass)
        self.socket = socket.socket(self.address_family,
                                    self.socket_type)
        self.server_bind()
        self.server_activate()

class ThreadingMixIn(ThreadingMixIn):

    def process_request(self, request, client_address):
        """Start a new thread to process the request."""
        from eventlet.green import threading
        t = threading.Thread(target = self.process_request_thread,
                             args = (request, client_address))
        if self.daemon_threads:
            t.setDaemon (1)
        t.start()

class ForkingUDPServer(ForkingMixIn, UDPServer): pass
class ForkingTCPServer(ForkingMixIn, TCPServer): pass

class ThreadingUDPServer(ThreadingMixIn, UDPServer): pass
class ThreadingTCPServer(ThreadingMixIn, TCPServer): pass

if hasattr(socket, 'AF_UNIX'):

    class UnixStreamServer(TCPServer):
        address_family = socket.AF_UNIX

    class UnixDatagramServer(UDPServer):
        address_family = socket.AF_UNIX

    class ThreadingUnixStreamServer(ThreadingMixIn, UnixStreamServer): pass
    class ThreadingUnixDatagramServer(ThreadingMixIn, UnixDatagramServer): pass

