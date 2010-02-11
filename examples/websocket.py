import collections
from eventlet import wsgi

class WebSocketApp(object):
    def __init__(self, handler):
        self.handler = handler
    
    def verify_client(self, ws):
        pass

    def __call__(self, environ, start_response):
        if not (environ['HTTP_CONNECTION'] == 'Upgrade' and
            environ['HTTP_UPGRADE'] == 'WebSocket'):
            # need to check a few more things here for true compliance
            print 'Invalid websocket handshake'
            start_response('400 Bad Request', [('Connection','close')])
            return []
                    
        sock = environ['eventlet.input'].get_socket()
        ws = WebSocket(sock, 
            environ.get('HTTP_ORIGIN'),
            environ.get('HTTP_WEBSOCKET_PROTOCOL'),
            environ.get('PATH_INFO'))
        self.verify_client(ws)
        handshake_reply = ("HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
                   "Upgrade: WebSocket\r\n"
                   "Connection: Upgrade\r\n"
                   "WebSocket-Origin: %s\r\n\r\n" % ws.origin)
        sock.sendall(handshake_reply)
        self.handler(ws)
        # use this undocumented feature of eventlet.wsgi to ensure that it
        # doesn't barf on the fact that we didn't call start_response
        return wsgi.ALREADY_HANDLED

def parse_messages(buf):
    """ Parses for messages in the buffer *buf*.  It is assumed that
    the buffer contains the start character for a message, but that it
    may contain only part of the rest of the message. NOTE: only understands
    lengthless messages for now.
    
    Returns an array of messages, and the buffer remainder that didn't contain 
    any full messages."""
    msgs = []
    end_idx = 0
    while buf:
        assert ord(buf[0]) == 0, "Don't understand how to parse this type of message: %r" % buf
        end_idx = buf.find("\xFF")
        if end_idx == -1:
            break
        msgs.append(buf[1:end_idx].decode('utf-8', 'replace'))
        buf = buf[end_idx+1:]
    return msgs, buf
        
def format_message(message):
    # TODO support iterable messages
    if isinstance(message, unicode):
        message = message.encode('utf-8')
    elif not isinstance(message, str):
        message = str(message)
    packed = "\x00%s\xFF" % message
    return packed


class WebSocket(object):
    def __init__(self, sock, origin, protocol, path):
        self.sock = sock
        self.origin = origin
        self.protocol = protocol
        self.path = path
        self._buf = ""
        self._msgs = collections.deque()
    
    def send(self, message):
        packed = format_message(message)
        self.sock.sendall(packed)
            
    def wait(self):
        while not self._msgs:
            # no parsed messages, must mean buf needs more data
            delta = self.sock.recv(1024)
            if delta == '':
                return ''
            self._buf += delta
            msgs, self._buf = parse_messages(self._buf)
            self._msgs.extend(msgs)
        return self._msgs.popleft()
        
        
if __name__ == "__main__":
    def echo(ws):
        while True:
            m = ws.wait()
            if m == '':
                break
            print "echoing", m
            ws.send(m)
        
    app = WebSocketApp(echo)
    from eventlet.green import socket
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR, 1)
    listener.bind(('localhost', 7000))
    listener.listen(500)
    wsgi.server(listener, app)