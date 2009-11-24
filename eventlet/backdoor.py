import socket
import sys
import errno
from code import InteractiveConsole

from eventlet import api
from eventlet.support import greenlets

try:
    sys.ps1
except AttributeError:
    sys.ps1 = '>>> '
try:
    sys.ps2
except AttributeError:
    sys.ps2 = '... '


class SocketConsole(greenlets.greenlet):
    def __init__(self, desc, hostport, locals):
        self.hostport = hostport
        self.locals = locals
        # mangle the socket
        self.desc = desc
        readline = desc.readline
        self.old = {}
        self.fixups = {
            'softspace': 0,
            'isatty': lambda: True,
            'flush': lambda: None,
            'readline': lambda *a: readline(*a).replace('\r\n', '\n'),
        }
        for key, value in self.fixups.iteritems():
            if hasattr(desc, key):
                self.old[key] = getattr(desc, key)
            setattr(desc, key, value)

        greenlets.greenlet.__init__(self)

    def run(self):
        try:
            console = InteractiveConsole(self.locals)
            console.interact()
        finally:
            self.switch_out()
            self.finalize()

    def switch(self, *args, **kw):
        self.saved = sys.stdin, sys.stderr, sys.stdout
        sys.stdin = sys.stdout = sys.stderr = self.desc
        greenlets.greenlet.switch(self, *args, **kw)

    def switch_out(self):
        sys.stdin, sys.stderr, sys.stdout = self.saved

    def finalize(self):
        # restore the state of the socket
        for key in self.fixups:
            try:
                value = self.old[key]
            except KeyError:
                delattr(self.desc, key)
            else:
                setattr(self.desc, key, value)
        self.fixups.clear()
        self.old.clear()
        self.desc = None
        print "backdoor closed to %s:%s" % self.hostport


def backdoor_server(server, locals=None):
    """ Runs a backdoor server on the socket, accepting connections and 
    running backdoor consoles for each client that connects.
    """
    print "backdoor server listening on %s:%s" % server.getsockname()
    try:
        try:
            while True:
                socketpair = server.accept()
                backdoor(socketpair, locals)
        except socket.error, e:
            # Broken pipe means it was shutdown
            if e[0] != errno.EPIPE:
                raise
    finally:
        server.close()


def backdoor((conn, addr), locals=None):
    """Sets up an interactive console on a socket with a connected client.  
    This does not block the caller, as it spawns a new greenlet to handle 
    the console.
    """
    host, port = addr
    print "backdoor to %s:%s" % (host, port)
    fl = conn.makeGreenFile("rw")
    fl.newlines = '\n'
    greenlet = SocketConsole(fl, (host, port), locals)
    hub = api.get_hub()
    hub.schedule_call_global(0, greenlet.switch)


if __name__ == '__main__':
    backdoor_server(api.tcp_listener(('127.0.0.1', 9000)), {})

