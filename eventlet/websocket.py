import collections
import errno
import logging
import re
import socket
import string
import struct

from base64 import b64encode, b64decode
try:
    from hashlib import md5, sha1
except ImportError:
    from md5 import md5
    from sha import sha as sha1

from socket import error as SocketError

from eventlet import pools, sleep, wsgi
from eventlet.support import get_errno

log = logging.getLogger(__name__)


__all__ = ['WebSocketWSGI', 'WebSocket', 'WS_KEY']

#: Magic WebSocket key
WS_KEY = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

ACCEPTABLE_CLIENT_ERRORS = set((errno.ECONNRESET, errno.EPIPE))

class WebSocketWSGI(object):
    """
    Wraps a websocket handler function in a WSGI application.

    Use it like this::

      @websocket.WebSocketWSGI
      def my_handler(ws):
          from_browser = ws.wait()
          ws.send("from server")

    The single argument to the function will be an instance of :class:`WebSocket`.
    To close the socket, simply return from the function.

    .. note:: Server will log the websocket request at the time of closure.
    """

    #: Supported WebSocket protocols. Can be overridden in subclasses.
    supported_protocols = ('ws',)

    #: Supported WebSocket extensions. Can be overridden in subclasses.
    supported_extensions = ()

    def __init__(self, handler):
        self.handler = handler

    def verify_client(self, ws):
        pass

    def _get_key_value(self, key_value):
        if not key_value:
            return
        key_number = int(re.sub("\\D", "", key_value))
        spaces = re.subn(" ", "", key_value)[1]
        if key_number % spaces != 0:
            return
        part = key_number / spaces
        return part

    def __call__(self, environ, start_response):
        http_connection = environ.get('HTTP_CONNECTION', '')
        http_upgrade = environ.get('HTTP_UPGRADE', '')
        if not (http_connection.lower() == 'upgrade' and
                http_upgrade.lower() == 'websocket'):
            log.warning('Incorrect HTTP_CONNECTION/HTTP_UPGRADE headers: %r/%r',
                        http_connection,
                        http_upgrade)
            # TODO: need to check a few more things here for true compliance
            start_response('400 Bad Request', [('Connection', 'close')])
            return []

        sock = environ['eventlet.input'].get_socket()

        version = environ.get('HTTP_SEC_WEBSOCKET_VERSION')
        if not version and 'HTTP_SEC_WEBSOCKET_KEY1' in environ:
            version = 76

        if version == 76:
            WebSocketClass = Hixie76WebSocket
        else:
            WebSocketClass = RFCWebSocket

        log.debug('Selected websocket class %r', WebSocketClass)

        ws = WebSocketClass(sock, environ)

        handshake_reply = (
            "HTTP/1.1 101 WebSocket Protocol Handshake\r\n"
            "Upgrade: WebSocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Origin: %s\r\n" % (
                environ.get('HTTP_ORIGIN'),
            )
        )

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

        handshake_reply += 'Sec-WebSocket-Location: %s\r\n' % (location,)

        subprotocols = [s.strip()
            for s in environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', '').split(',')]
        ws_protocols = [s for s in subprotocols if s in self.supported_protocols]
        if ws_protocols:
            handshake_reply += 'Sec-WebSocket-Protocol: %s\r\n' % ', '.join(ws_protocols)

        supported_extensions = []
        extensions = [e.strip()
            for e in environ.get('HTTP_SEC_WEBSOCKET_EXTENSIONS', '').split(',')]
        ws_extensions = [e for w in extensions if e in self.supported_extensions]
        if ws_extensions:
            handshake_reply += 'Sec-WebSocket-Extensions: %s\r\n' % ', '.join(ws_extensions)
        key = environ.get('HTTP_SEC_WEBSOCKET_KEY')
        if key:
            ws_key = b64decode(key)
            if len(ws_key) != 16:
                start_response('400 Bad Request', [('Connection','close')])
                return []

            handshake_reply +=  (
                "Sec-WebSocket-Accept: %s\r\n\r\n"
                 % (
                    b64encode(sha1(key + WS_KEY).digest())
                )
            )
        else:
            try:
                key1 = self._extract_number(environ['HTTP_SEC_WEBSOCKET_KEY1'])
                key2 = self._extract_number(environ['HTTP_SEC_WEBSOCKET_KEY2'])
            except KeyError, e:
                log.warning('Missing header: %s', e)
                start_response('400 Bad Request', [('Connection', 'close')])
                return []

            # There's no content-length header in the request, but it has 8
            # bytes of data.
            environ['wsgi.input'].content_length = 8
            key3 = environ['wsgi.input'].read(8)
            key = struct.pack(">II", key1, key2) + key3
            response = md5(key).digest()

            handshake_reply += "\r\n%s" % (response,)

        sock.sendall(handshake_reply)

        try:
            self.handler(ws)
        except socket.error, e:
            if get_errno(e) not in ACCEPTABLE_CLIENT_ERRORS:
                raise

        # Make sure we send the closing frame
        ws._send_closing_frame(ignore_send_errors=True)
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
    and forth with the browser.
    """

    websocket_closed = False
    _buf = ''

    def __init__(self, socket, environ):
        """
        :param socket: The eventlet socket
        :type socket: :class:`eventlet.greenio.GreenSocket`
        :param environ: The wsgi environment
        """
        self.socket = socket

        #: The full WSGI environment for this request.
        self.environ = environ

        self._msgs = collections.deque()
        self._sendlock = pools.TokenPool(1)

    @property
    def path(self):
        """Gets the path value of the request. (:class:`string` | :class:`None`)

        This is the same as the WSGI PATH_INFO variable, but more convenient.
        """
        return self.environ.get('PATH_INFO')

    @property
    def protocol(self):
        """Gets the value of the Websocket-Protocol header. (:class:`string` | :class:`None`)"""
        return self.environ.get('HTTP_WEBSOCKET_PROTOCOL')

    @property
    def origin(self):
        """Gets the value of the 'Origin' header. (:class:`string` | :class:`None`)"""
        return self.environ.get('HTTP_ORIGIN')

    def _parse_messages(self):
        """ Parses for messages in the buffer *buf*.  It is assumed that
        the buffer contains the start character for a message, but that it
        may contain only part of the rest of the message.

        .. note:: Partial message will be left in the buffer.
        :rtype: iterable<message>
        """
        raise NotImplementedError()

    def send(self, message):
        """Send a message to the browser.  

        *message* should be convertable to a string; unicode objects should be
        encodable as utf-8.  Raises socket.error with errno of 32
        (broken pipe) if the socket has already been closed by the client."""
        packed = self._pack_message(message)
        # if two greenthreads are trying to send at the same time
        # on the same socket, sendlock prevents interleaving and corruption
        t = self._sendlock.get()
        try:
            self.socket.sendall(packed)
        finally:
            self._sendlock.put(t)

    def wait(self):
        """Waits for and deserializes messages.

        :rtype: :class:`Message` | :class:`None`
        :returns: a single message; the oldest not yet processed. If the client has
            already closed the connection, returns None. This is different from normal
            socket behavior because the empty string is a valid websocket message.

        """
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


    def _pack_message(self, message):
        raise NotImplementedError()

    def close(self):
        """Forcibly close the websocket; generally it is preferable to
        return from the handler method."""
        self._send_closing_frame()
        self.socket.shutdown(True)
        self.socket.close()

    def _send_closing_frame(self, ignore_send_errors=False):
        """Sends the closing frame to the client, if required."""
        raise NotImplementedError()


class RFCWebSocket(WebSocket):
    def encode_hybi(self, buf, opcode, base64=False):
        """ Encode a HyBi style WebSocket frame.
        Optional opcode:
            0x0 - continuation
            0x1 - text frame (base64 encode buf)
            0x2 - binary frame (use raw buf)
            0x8 - connection close
            0x9 - ping
            0xA - pong
        """
        if base64:
            buf = b64encode(buf)

        b1 = 0x80 | (opcode & 0x0f) # FIN + opcode
        payload_len = len(buf)
        if payload_len <= 125:
            header = struct.pack('>BB', b1, payload_len)
        elif payload_len > 125 and payload_len < 65536:
            header = struct.pack('>BBH', b1, 126, payload_len)
        elif payload_len >= 65536:
            header = struct.pack('>BBQ', b1, 127, payload_len)

        log.debug("Encoded: %r", header + buf)

        return header + buf, len(header), 0

    def decode_hybi(self, buf, base64=False):
        """ Decode HyBi style WebSocket packets.
        Returns:
            {'fin'          : 0_or_1,
             'opcode'       : number,
             'mask'         : 32_bit_number,
             'hlen'         : header_bytes_number,
             'length'       : payload_bytes_number,
             'payload'      : decoded_buffer,
             'left'         : bytes_left_number,
             'close_code'   : number,
             'close_reason' : string}
        """

        f = {'fin'          : 0,
             'opcode'       : 0,   
             'mask'         : 0,
             'hlen'         : 2,
             'length'       : 0,
             'payload'      : None,
             'left'         : 0,
             'close_code'   : None,
             'close_reason' : None}

        blen = len(buf)
        f['left'] = blen

        if blen < f['hlen']:
            return f # Incomplete frame header

        b1, b2 = struct.unpack_from(">BB", buf)
        f['opcode'] = b1 & 0x0f
        f['fin'] = (b1 & 0x80) >> 7
        has_mask = (b2 & 0x80) >> 7

        f['length'] = b2 & 0x7f

        if f['length'] == 126:
            f['hlen'] = 4
            if blen < f['hlen']:
                return f # Incomplete frame header
            (f['length'],) = struct.unpack_from('>xxH', buf)
        elif f['length'] == 127:
            f['hlen'] = 10
            if blen < f['hlen']:
                return f # Incomplete frame header
            (f['length'],) = struct.unpack_from('>xxQ', buf)

        full_len = f['hlen'] + has_mask * 4 + f['length']

        if blen < full_len: # Incomplete frame
            return f # Incomplete frame header

        # Number of bytes that are part of the next frame(s)
        f['left'] = blen - full_len

        # Process 1 frame
        if has_mask:
            # unmask payload
            f['mask'] = buf[f['hlen']:f['hlen']+4]
            b = c = ''
            if f['length'] >= 4:
                data = struct.unpack('<I', buf[f['hlen']:f['hlen']+4])[0]
                of1 = f['hlen']+4
                b = ''
                for i in xrange(0, int(f['length']/4)):
                    mask = struct.unpack('<I', buf[of1+4*i:of1+4*(i+1)])[0]
                    b += struct.pack('I', data ^ mask)

            if f['length'] % 4:
                l = f['length'] % 4
                of1 = f['hlen']
                of2 = full_len - l
                c = ''
                for i in range(0, l):
                    mask = struct.unpack('B', buf[of1 + i])[0]
                    data = struct.unpack('B', buf[of2 + i])[0]
                    c += chr(data ^ mask)

            f['payload'] = b + c
        else:
            log.debug("Unmasked frame: %r", buf)
            f['payload'] = buf[(f['hlen'] + has_mask * 4):full_len]

        if base64 and f['opcode'] in [1, 2]:
            try:
                f['payload'] = b64decode(f['payload'])
            except:
                log.debug("Exception while b64decoding buffer: %r", buf)
                raise

        if f['opcode'] == 0x08:
            if f['length'] >= 2:
                f['close_code'] = struct.unpack_from(">H", f['payload'])
            if f['length'] > 3:
                f['close_reason'] = f['payload'][2:]

        return f

    def _parse_messages(self):
        msgs = []
        end_idx = 0
        buf = self._buf
        while buf:
            frame = self.decode_hybi(buf, base64=False)
            log.debug("Received buf: %r, frame: %s", buf, frame)

            if frame['payload'] == None:
                break
            else:
                if frame['opcode'] == 0x8: # connection close
                    self.websocket_closed = True
                    break
                else:
                    msgs.append(frame['payload']);
                    if frame['left']:
                        buf = buf[-frame['left']:]
                    else:
                        buf = ''


        self._buf = buf
        return msgs

    def _pack_message(self, message):
        packed, lenhead, lentail = self.encode_hybi(message, opcode=0x01, base64=False)
        return packed

    def _send_closing_frame(self, ignore_send_errors=False):
        if not self.websocket_closed:
            msg = ''
            buf, h, t = self.encode_hybi(msg, opcode=0x08, base64=False)

            try:
                self.socket.sendall(buf)
            except SocketError:
                if not ignore_send_errors: #pragma NO COVER
                    raise

            self.websocket_closed = True


class Hixie76WebSocket(WebSocket):
    def _pack_message(self, message):
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

    def _send_closing_frame(self, ignore_send_errors=False):
        """Sends the closing frame to the client, if required."""
        if not self.websocket_closed:

            try:
                self.socket.sendall("\xff\x00")
            except SocketError:
                if not ignore_send_errors: #pragma NO COVER
                    raise

            self.websocket_closed = True
