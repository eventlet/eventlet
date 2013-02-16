import base64
import collections
import errno
from random import Random
import string
import struct
import sys
import time
from socket import error as SocketError

try:
    from hashlib import md5, sha1
except ImportError: #pragma NO COVER
    from md5 import md5
    from sha import sha as sha1

import eventlet
from eventlet import semaphore
from eventlet import wsgi
from eventlet.green import socket
from eventlet.support import get_errno

ACCEPTABLE_CLIENT_ERRORS = set((errno.ECONNRESET, errno.EPIPE))

__all__ = ["WebSocketWSGI", "WebSocket"]
PROTOCOL_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


class WebSocketWSGI(object):
    """Wraps a websocket handler function in a WSGI application.

    Use it like this::

      @websocket.WebSocketWSGI
      def my_handler(ws):
          from_browser = ws.wait()
          ws.send("from server")

    The single argument to the function will be an instance of
    :class:`WebSocket`.  To close the socket, simply return from the
    function.  Note that the server will log the websocket request at
    the time of closure.
    """
    def __init__(self, handler):
        self.handler = handler
        self.mask_frames = False
        self.protocol_version = None

    def __call__(self, environ, start_response):
        if not (environ.get('HTTP_CONNECTION') == 'Upgrade' and
                environ.get('HTTP_UPGRADE') in ('WebSocket', 'websocket')):
            # need to check a few more things here for true compliance
            start_response('400 Bad Request', [('Connection','close')])
            return []
    
        # See if they sent the new-format headers
        hybi_version = environ.get('HTTP_SEC_WEBSOCKET_VERSION', None)
        if hybi_version is not None:
            if hybi_version != '13':
                start_response('426 Upgrade Required',
                               [('Connection', 'close'),
                                ('Sec-WebSocket-Version', '13')])
                return []
            self.protocol_version = int(hybi_version)
            if 'HTTP_SEC_WEBSOCKET_KEY' not in environ:
                # That's bad.
                start_response('400 Bad Request', [('Connection','close')])
                return []
            # TODO: handle Origin (Sec-Websocket-Origin for <=8)
            #       (An unaccepted origin is a 403 Forbidden response.)
            #protocols = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', None)
            #if protocols:
            #    protocols = [i.strip() for i in protocols.split(',')]
            #extensions = environ.get('HTTP_SEC_WEBSOCKET_EXTENSIONS', None)
            #if extensions:
            #    extensions = [i.strip() for i in extensions.split(',')]
        if 'HTTP_SEC_WEBSOCKET_KEY1' in environ:
            self.protocol_version = 76
            if 'HTTP_SEC_WEBSOCKET_KEY2' not in environ:
                # That's bad.
                start_response('400 Bad Request', [('Connection','close')])
                return []
        else:
            self.protocol_version = 75

        # Get the underlying socket and wrap a WebSocket class around it
        sock = environ['eventlet.input'].get_socket()
        if hybi_version is not None:
            ws = RFC6455WebSocket(sock, environ, self.protocol_version)
        else:
            ws = WebSocket(sock, environ, self.protocol_version)
        
        # If it's new-version, we need to work out our challenge response
        if hybi_version is not None:
            key = environ['HTTP_SEC_WEBSOCKET_KEY']
            response = base64.b64encode(sha1(key + PROTOCOL_GUID).digest())
        elif self.protocol_version == 76:
            key1 = self._extract_number(environ['HTTP_SEC_WEBSOCKET_KEY1'])
            key2 = self._extract_number(environ['HTTP_SEC_WEBSOCKET_KEY2'])
            # There's no content-length header in the request, but it has 8
            # bytes of data.
            environ['wsgi.input'].content_length = 8
            key3 = environ['wsgi.input'].read(8)
            key = struct.pack(">II", key1, key2) + key3
            response = md5(key).digest()
        
        # Start building the response
        scheme = 'ws'
        if environ.get('wsgi.url_scheme') == 'https':
            scheme = 'wss'
        location = '%s://%s%s%s' % (
            scheme,
            environ.get('HTTP_HOST'), 
            environ.get('SCRIPT_NAME'), 
            environ.get('PATH_INFO')
        )
        qs = environ.get('QUERY_STRING')
        if qs is not None:
            location += '?' + qs
        if hybi_version is not None:
            handshake_reply = ("HTTP/1.1 101 Switching Protocols\r\n"
                               "Upgrade: websocket\r\n"
                               "Connection: Upgrade\r\n"
                               "Sec-WebSocket-Accept: %s\r\n\r\n"
                               % (response, ))
        elif self.protocol_version == 75:
            handshake_reply = ("HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
                               "Upgrade: WebSocket\r\n"
                               "Connection: Upgrade\r\n"
                               "WebSocket-Origin: %s\r\n"
                               "WebSocket-Location: %s\r\n\r\n" % (
                    environ.get('HTTP_ORIGIN'),
                    location))
        elif self.protocol_version == 76:
            handshake_reply = ("HTTP/1.1 101 WebSocket Protocol Handshake\r\n"
                               "Upgrade: WebSocket\r\n"
                               "Connection: Upgrade\r\n"
                               "Sec-WebSocket-Origin: %s\r\n"
                               "Sec-WebSocket-Protocol: %s\r\n"
                               "Sec-WebSocket-Location: %s\r\n"
                               "\r\n%s"% (
                    environ.get('HTTP_ORIGIN'),
                    environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', 'default'),
                    location,
                    response))
        else: #pragma NO COVER
            raise ValueError("Unknown WebSocket protocol version.") 
        
        sock.sendall(handshake_reply)
        try:
            self.handler(ws)
        except socket.error, e:
            if get_errno(e) not in ACCEPTABLE_CLIENT_ERRORS:
                raise
        # Make sure we send the closing frame
        ws._send_closing_frame(True)
        # use this undocumented feature of eventlet.wsgi to ensure that it
        # doesn't barf on the fact that we didn't call start_response
        return wsgi.ALREADY_HANDLED

    def _extract_number(self, value):
        """
        Utility function which, given a string like 'g98sd  5[]221@1', will
        return 9852211. Used to parse the Sec-WebSocket-Key headers.
        """
        out = ""
        spaces = 0
        for char in value:
            if char in string.digits:
                out += char
            elif char == " ":
                spaces += 1
        return int(out) / spaces

class WebSocket(object):
    """A websocket object that handles the details of
    serialization/deserialization to the socket.
    
    The primary way to interact with a :class:`WebSocket` object is to
    call :meth:`send` and :meth:`wait` in order to pass messages back
    and forth with the browser.  Also available are the following
    properties:
    
    path
        The path value of the request.  This is the same as the WSGI PATH_INFO variable, but more convenient.
    protocol
        The value of the Websocket-Protocol header.
    origin
        The value of the 'Origin' header.
    environ
        The full WSGI environment for this request.

    """
    def __init__(self, sock, environ, version=76):
        """
        :param socket: The eventlet socket
        :type socket: :class:`eventlet.greenio.GreenSocket`
        :param environ: The wsgi environment
        :param version: The WebSocket spec version to follow (default is 76)
        """
        self.socket = sock
        self.origin = environ.get('HTTP_ORIGIN')
        self.protocol = environ.get('HTTP_WEBSOCKET_PROTOCOL')
        self.path = environ.get('PATH_INFO')
        self.environ = environ
        self.version = version
        self.websocket_closed = False
        self._buf = ""
        self._msgs = collections.deque()
        self._sendlock = semaphore.Semaphore()

    @staticmethod
    def _pack_message(message):
        """Pack the message inside ``00`` and ``FF``

        As per the dataframing section (5.3) for the websocket spec
        """
        if isinstance(message, unicode):
            message = message.encode('utf-8')
        elif not isinstance(message, str):
            message = str(message)
        packed = "\x00%s\xFF" % message
        return packed

    def _parse_messages(self):
        """ Parses for messages in the buffer *buf*.  It is assumed that
        the buffer contains the start character for a message, but that it
        may contain only part of the rest of the message.

        Returns an array of messages, and the buffer remainder that
        didn't contain any full messages."""
        msgs = []
        end_idx = 0
        buf = self._buf
        while buf:
            frame_type = ord(buf[0])
            if frame_type == 0:
                # Normal message.
                end_idx = buf.find("\xFF")
                if end_idx == -1: #pragma NO COVER
                    break
                msgs.append(buf[1:end_idx].decode('utf-8', 'replace'))
                buf = buf[end_idx+1:]
            elif frame_type == 255:
                # Closing handshake.
                assert ord(buf[1]) == 0, "Unexpected closing handshake: %r" % buf
                self.websocket_closed = True
                break
            else:
                raise ValueError("Don't understand how to parse this type of message: %r" % buf)
        self._buf = buf
        return msgs
    
    def send(self, message):
        """Send a message to the browser.  
        
        *message* should be convertable to a string; unicode objects should be
        encodable as utf-8.  Raises socket.error with errno of 32
        (broken pipe) if the socket has already been closed by the client."""
        packed = self._pack_message(message)
        # if two greenthreads are trying to send at the same time
        # on the same socket, sendlock prevents interleaving and corruption
        self._sendlock.acquire()
        try:
            self.socket.sendall(packed)
        finally:
            self._sendlock.release()

    def wait(self):
        """Waits for and deserializes messages. 
        
        Returns a single message; the oldest not yet processed. If the client
        has already closed the connection, returns None.  This is different
        from normal socket behavior because the empty string is a valid
        websocket message."""
        while not self._msgs:
            # Websocket might be closed already.
            if self.websocket_closed:
                return None
            # no parsed messages, must mean buf needs more data
            delta = self.socket.recv(8096)
            if delta == '':
                return None
            self._buf += delta
            msgs = self._parse_messages()
            self._msgs.extend(msgs)
        return self._msgs.popleft()

    def _send_closing_frame(self, ignore_send_errors=False):
        """Sends the closing frame to the client, if required."""
        if self.version == 76 and not self.websocket_closed:
            try:
                self.socket.sendall("\xff\x00")
            except SocketError:
                # Sometimes, like when the remote side cuts off the connection,
                # we don't care about this.
                if not ignore_send_errors: #pragma NO COVER
                    raise
            self.websocket_closed = True

    def close(self):
        """Forcibly close the websocket; generally it is preferable to
        return from the handler method."""
        self._send_closing_frame()
        self.socket.shutdown(True)
        self.socket.close()


class ConnectionClosedError(Exception):
    pass


class FailedConnectionError(Exception):
    def __init__(self, status, message):
        super(FailedConnectionError, self).__init__(status, message)
        self.message = message
        self.status = status


class ProtocolError(ValueError):
    pass


class RFC6455WebSocket(WebSocket):
    def __init__(self, sock, environ, version=13):
        super(RFC6455WebSocket, self).__init__(sock, environ, version)
        self.iterator = self._iter_frames()

    def _get_bytes(self, numbytes):
        data = ''
        while len(data) < numbytes:
            d = self.socket.recv(numbytes - len(data))
            if not d:
                break
            data = data + d
        if len(data) < numbytes:
            raise ConnectionClosedError()
        return data

    @staticmethod
    def _apply_mask(data, mask, length=None):
        if length is None:
            length = len(data)
        count = xrange(length)
        return ''.join(chr(ord(data[i]) ^ mask[i % 4]) for i in count)

    def _handle_control_frame(self, opcode, data):
        if opcode == 8:  # connection close
            status = struct.unpack_from('!H', data)
            self.close(close_data=(status, ''))
            raise ConnectionClosedError()
        elif opcode == 9:  # ping
            self.send(data, control_code=0xA)
        elif opcode == 0xA:  # pong
            pass
        else:
            raise FailedConnectionError(
                1002, "Unknown control frame received.")

    def _iter_frames(self):
        fragments = []
        fragment_opcode = None
        try:
            while True:
                finished, opcode, data = self._recv_frame()
                if opcode & 8:
                    # allow multiplexed control codes
                    self._handle_control_frame(opcode, data)
                    continue
                if fragments:
                    if opcode:
                        raise FailedConnectionError(
                            1002,
                            "Received a non-continuation opcode within"
                            " fragmented message.")
                else:
                    if not opcode:
                        raise FailedConnectionError(
                            1002,
                            "Received continuation opcode with no previous"
                            " fragments received.")
                    fragment_opcode = opcode
                fragments.append(data)
                if finished:
                    data, fragments = ''.join(fragments), []
                    if fragment_opcode == 1:  # text frame
                        try:
                            data = data.decode('utf-8')
                        except UnicodeDecodeError:
                            raise FailedConnectionError(
                                1002, "Text data must be valid utf-8")
                    yield data
        except FailedConnectionError:
            exc_typ, exc_val, exc_tb = sys.exc_info()
            self.close(close_data=(exc_val.status, exc_val.message))
        except ConnectionClosedError:
            return

    def _recv_frame(self):
        recv = self._get_bytes
        header = recv(2)
        a, b = struct.unpack('!BB', header)
        finished = a >> 7 == 1
        rsv123 = a >> 4 & 7
        if rsv123:
            # must be zero
            raise FailedConnectionError(
                1002,
                "RSV1, RSV2, RSV3: MUST be 0 unless an extension is"
                " negotiated that defines meanings for non-zero values.")
        opcode = a & 15
        if opcode not in (0, 1, 2, 8, 9, 0xA):
            raise FailedConnectionError(1002, "Unknown opcode received.")
        masked = b & 128 == 128
        if not masked:
            raise FailedConnectionError(1002, "A client MUST mask all frames"
                                        " that it sends to the server")
        length = b & 127
        if opcode & 8:
            if not finished:
                raise FailedConnectionError(1002, "Control frames must not"
                                            " be fragmented.")
            if length > 125:
                raise FailedConnectionError(
                    1002,
                    "All control frames MUST have a payload length of 125"
                    " bytes or less")
        if length == 126:
            length = struct.unpack('!H', recv(2))[0]
        elif length == 127:
            length = struct.unpack('!Q', recv(8))[0]
        if masked:
            mask = struct.unpack('!BBBB', recv(4))
        data = recv(length)
        if masked:
            data = self._apply_mask(data, mask, length)
        return finished, opcode, data

    @staticmethod
    def _pack_message(message, masked=False,
                      continuation=False, final=True, control_code=None):
        is_text = False
        if isinstance(message, unicode):
            message = message.encode('utf-8')
            is_text = True
        length = len(message)
        if not length:
            # no point masking empty data
            masked = False
        if control_code:
            if control_code not in (8, 9, 0xA):
                raise ProtocolError('Unknown control opcode.')
            if continuation or not final:
                raise ProtocolError('Control frame cannot be a fragment.')
            if length > 125:
                raise ProtocolError('Control frame data too large (>125).')
            header = struct.pack('!B', control_code | 1 << 7)
        else:
            opcode = 0 if continuation else (1 if is_text else 2)
            header = struct.pack('!B', opcode | (1 << 7 if final else 0))
        lengthdata = 1 << 7 if masked else 0
        if length > 65535:
            lengthdata = struct.pack('!BQ', lengthdata | 127, length)
        elif length > 125:
            lengthdata = struct.pack('!BH', lengthdata | 126, length)
        else:
            lengthdata = struct.pack('!B', lengthdata | length)
        if masked:
            # NOTE: RFC6455 states:
            # A server MUST NOT mask any frames that it sends to the client
            rand = Random(time.time())
            mask = map(rand.getrandbits, (8, ) * 4)
            message = RFC6455WebSocket._apply_mask(message, mask, length)
            maskdata = struct.pack('!BBBB', *mask)
        else:
            maskdata = ''
        return ''.join((header, lengthdata, maskdata, message))

    def wait(self):
        for i in self.iterator:
            return i

    def _send(self, frame):
        self._sendlock.acquire()
        try:
            self.socket.sendall(frame)
        finally:
            self._sendlock.release()

    def send(self, message, **kw):
        payload = self._pack_message(message, **kw)
        self._send(payload)

    def _send_closing_frame(self, close_data=None, ignore_send_errors=False):
        if close_data is not None:
            status, msg = close_data
            if isinstance(msg, unicode):
                msg = msg.encode('utf-8')
            data = struct.pack('!H', status) + msg
        else:
            data = ''
        self.send(data, control_code=8)
