import collections
import errno

import eventlet
from eventlet import semaphore
from eventlet import wsgi
from eventlet.green import socket
from eventlet.support import get_errno

ACCEPTABLE_CLIENT_ERRORS = set((errno.ECONNRESET, errno.EPIPE))

class WebSocketWSGI(object):
    """This is a WSGI application that serves up websocket connections.
    """
    def __init__(self, handler):
        self.handler = handler

    def __call__(self, environ, start_response):
        if not (environ.get('HTTP_CONNECTION') == 'Upgrade' and
                environ.get('HTTP_UPGRADE') == 'WebSocket'):
            # need to check a few more things here for true compliance
            start_response('400 Bad Request', [('Connection','close')])
            return []

        sock = environ['eventlet.input'].get_socket()
        ws = WebSocket(sock, environ)
        handshake_reply = ("HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
                           "Upgrade: WebSocket\r\n"
                           "Connection: Upgrade\r\n"
                           "WebSocket-Origin: %s\r\n"
                           "WebSocket-Location: ws://%s%s\r\n\r\n" % (
                                environ.get('HTTP_ORIGIN'),
                                environ.get('HTTP_HOST'),
                                environ.get('PATH_INFO')))
        sock.sendall(handshake_reply)
        try:
            self.handler(ws)
        except socket.error, e:
            if get_errno(e) not in ACCEPTABLE_CLIENT_ERRORS:
                raise
        # use this undocumented feature of eventlet.wsgi to ensure that it
        # doesn't barf on the fact that we didn't call start_response
        return wsgi.ALREADY_HANDLED


class WebSocket(object):
    """The object representing the server side of a websocket.
    
    The primary way to interact with a WebSocket object is to call
    :meth:`send` and :meth:`wait` in order to pass messages back and
    forth with the client.  Also available are the following properties:
    
    path
        The path value of the request.  This is the same as the WSGI PATH_INFO variable.
    protocol
        The value of the Websocket-Protocol header.
    origin
        The value of the 'Origin' header.
    environ
        The full WSGI environment for this request.
    """
    def __init__(self, sock, environ):
        """
        :param socket: The eventlet socket
        :type socket: :class:`eventlet.greenio.GreenSocket`
        :param environ: The wsgi environment
        """
        self.socket = sock
        self.origin = environ.get('HTTP_ORIGIN')
        self.protocol = environ.get('HTTP_WEBSOCKET_PROTOCOL')
        self.path = environ.get('PATH_INFO')
        self.environ = environ
        self._buf = ""
        self._msgs = collections.deque()
        self._sendlock = semaphore.Semaphore()

    @staticmethod
    def pack_message(message):
        """Pack the message inside ``00`` and ``FF``

        As per the dataframing section (5.3) for the websocket spec
        """
        if isinstance(message, unicode):
            message = message.encode('utf-8')
        elif not isinstance(message, str):
            message = str(message)
        packed = "\x00%s\xFF" % message
        return packed

    def parse_messages(self):
        """ Parses for messages in the buffer *buf*.  It is assumed that
        the buffer contains the start character for a message, but that it
        may contain only part of the rest of the message. NOTE: only understands
        lengthless messages for now.

        Returns an array of messages, and the buffer remainder that
        didn't contain any full messages."""
        msgs = []
        end_idx = 0
        buf = self._buf
        while buf:
            assert ord(buf[0]) == 0, "Don't understand how to parse this type of message: %r" % buf
            end_idx = buf.find("\xFF")
            if end_idx == -1: #pragma NO COVER
                break
            msgs.append(buf[1:end_idx].decode('utf-8', 'replace'))
            buf = buf[end_idx+1:]
        self._buf = buf
        return msgs
    
    def send(self, message):
        """Send a message to the client.  *message* should be
        convertable to a string; unicode objects should be encodable
        as utf-8."""
        packed = self.pack_message(message)
        # if two greenthreads are trying to send at the same time
        # on the same socket, sendlock prevents interleaving and corruption
        self._sendlock.acquire()
        try:
            self.socket.sendall(packed)
        finally:
            self._sendlock.release()

    def wait(self):
        """Waits for and deserializes messages. Returns a single
        message; the oldest not yet processed."""
        while not self._msgs:
            # no parsed messages, must mean buf needs more data
            delta = self.socket.recv(8096)
            if delta == '':
                return None
            self._buf += delta
            msgs = self.parse_messages()
            self._msgs.extend(msgs)
        return self._msgs.popleft()

    def close(self):
        """Forcibly close the websocket; generally it is preferable to
        return from the handler method."""
        self.socket.shutdown(True)
        self.socket.close()

