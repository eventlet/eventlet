from OpenSSL import SSL as orig_SSL
from OpenSSL.SSL import *
from eventlet.common import get_errno
from eventlet import greenio
from eventlet.hubs import trampoline
import socket

class GreenConnection(greenio.GreenSocket):
    """ Nonblocking wrapper for SSL.Connection objects.
    """
    def __init__(self, ctx, sock=None):
        if sock is not None:
            fd = orig_SSL.Connection(ctx, sock)
        else:
            # if we're given a Connection object directly, use it;
            # this is used in the inherited accept() method
            fd = ctx
        super(ConnectionType, self).__init__(fd)
        self.sock = self
        
    def close(self):
        super(GreenConnection, self).close()
    
    def do_handshake(self):
        """ Perform an SSL handshake (usually called after renegotiate or one of 
        set_accept_state or set_accept_state). This can raise the same exceptions as 
        send and recv. """
        if self.act_non_blocking:
            return self.fd.do_handshake()
        while True:
            try:
                return self.fd.do_handshake()
            except WantReadError:
                trampoline(self.fd.fileno(), 
                           read=True, 
                           timeout=self.gettimeout(), 
                           timeout_exc=socket.timeout)
            except WantWriteError:
                trampoline(self.fd.fileno(), 
                           write=True, 
                           timeout=self.gettimeout(), 
                           timeout_exc=socket.timeout)
                           
    def dup(self):
        raise NotImplementedError("Dup not supported on SSL sockets")
        
    def get_app_data(self, *args, **kw):
        fn = self.get_app_data = self.fd.get_app_data
        return fn(*args, **kw)

    def set_app_data(self, *args, **kw):
        fn = self.set_app_data = self.fd.set_app_data
        return fn(*args, **kw)        
    
    def get_cipher_list(self, *args, **kw):
        fn = self.get_cipher_list = self.fd.get_cipher_list
        return fn(*args, **kw)
        
    def get_context(self, *args, **kw):
        fn = self.get_context = self.fd.get_context
        return fn(*args, **kw)
    
    def get_peer_certificate(self, *args, **kw):
        fn = self.get_peer_certificate = self.fd.get_peer_certificate
        return fn(*args, **kw)
        
    def makefile(self, mode='r', bufsize=-1):
        raise NotImplementedError("Makefile not supported on SSL sockets")  
        
    def pending(self, *args, **kw):
        fn = self.pending = self.fd.pending
        return fn(*args, **kw)      

    def read(self, size):
        """Works like a blocking call to SSL_read(), whose behavior is 
        described here:  http://www.openssl.org/docs/ssl/SSL_read.html"""
        if self.act_non_blocking:
            return self.fd.read(size)
        while True:
            try:
                return self.fd.read(size)
            except WantReadError:
                trampoline(self.fd.fileno(), 
                           read=True, 
                           timeout=self.gettimeout(), 
                           timeout_exc=socket.timeout)
            except WantWriteError:
                trampoline(self.fd.fileno(), 
                           write=True, 
                           timeout=self.gettimeout(), 
                           timeout_exc=socket.timeout)
            except SysCallError, e:
                if get_errno(e) == -1 or get_errno(e) > 0:
                    return ''
            
    recv = read
    
    def renegotiate(self, *args, **kw):
        fn = self.renegotiate = self.fd.renegotiate
        return fn(*args, **kw)  

    def write(self, data):
        """Works like a blocking call to SSL_write(), whose behavior is 
        described here:  http://www.openssl.org/docs/ssl/SSL_write.html"""
        if not data:
            return 0 # calling SSL_write() with 0 bytes to be sent is undefined
        if self.act_non_blocking:
            return self.fd.write(data)
        while True:
            try:
                return self.fd.write(data)
            except WantReadError:
                trampoline(self.fd.fileno(), 
                           read=True, 
                           timeout=self.gettimeout(), 
                           timeout_exc=socket.timeout)
            except WantWriteError:
                trampoline(self.fd.fileno(), 
                           write=True, 
                           timeout=self.gettimeout(), 
                           timeout_exc=socket.timeout)
                           
    send = write
    
    def sendall(self, data):
        """Send "all" data on the connection. This calls send() repeatedly until
        all data is sent. If an error occurs, it's impossible to tell how much data
        has been sent.

        No return value."""
        tail = self.send(data)
        while tail < len(data):
            tail += self.send(data[tail:])
            
    def set_accept_state(self, *args, **kw):
        fn = self.set_accept_state = self.fd.set_accept_state
        return fn(*args, **kw)

    def set_connect_state(self, *args, **kw):
        fn = self.set_connect_state = self.fd.set_connect_state
        return fn(*args, **kw)
        
    def shutdown(self):
        if self.act_non_blocking:
            return self.fd.shutdown()
        while True:
            try:
                return self.fd.shutdown()
            except WantReadError:
                trampoline(self.fd.fileno(), 
                           read=True, 
                           timeout=self.gettimeout(), 
                           timeout_exc=socket.timeout)
            except WantWriteError:
                trampoline(self.fd.fileno(), 
                           write=True, 
                           timeout=self.gettimeout(), 
                           timeout_exc=socket.timeout)


    def get_shutdown(self, *args, **kw):
        fn = self.get_shutdown = self.fd.get_shutdown
        return fn(*args, **kw)
        
    def set_shutdown(self, *args, **kw):
        fn = self.set_shutdown = self.fd.set_shutdown
        return fn(*args, **kw)

    def sock_shutdown(self, *args, **kw):
        fn = self.sock_shutdown = self.fd.sock_shutdown
        return fn(*args, **kw)
        
    def state_string(self, *args, **kw):
        fn = self.state_string = self.fd.state_string
        return fn(*args, **kw)
    
    def want_read(self, *args, **kw):
        fn = self.want_read = self.fd.want_read
        return fn(*args, **kw)

    def want_write(self, *args, **kw):
        fn = self.want_write = self.fd.want_write
        return fn(*args, **kw)

Connection = ConnectionType = GreenConnection

del greenio
