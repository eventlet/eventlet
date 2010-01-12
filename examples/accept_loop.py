"""This is a simple echo server that demonstrates an accept loop.  To use it, 
run this script and then run 'telnet localhost 6011' in a different terminal.

If you send an empty line to the echo server it will close the connection while
leaving the server running.  If you send the word "shutdown" to the echo server
it will gracefully exit, terminating any other open connections.

The actual accept loop logic is fully contained within the run_accept_loop 
function.  Everything else is setup.
"""

from eventlet.green import socket
from eventlet.api import spawn

class Acceptor(object):
    def __init__(self, port=6011):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR, 1)
        self.sock.bind(('localhost', port))
        self.sock.listen(50)
        self.sock.settimeout(0.5)
        self.done = False
    
    def run_accept_loop(self):
        while not self.done:
            try:
                spawn(self.handle_one_client, self.sock.accept())
            except socket.timeout:
                pass
            
    def handle_one_client(self, sockpair):
        sock, addr = sockpair
        print "Accepted client", addr
        fd = sock.makefile()
        line = fd.readline()
        while line.strip():
            fd.write(line)
            fd.flush()
            if line.startswith("shutdown"):
                self.done = True
                print "Received shutdown"
                break
            line = fd.readline()
        print "Done with client", addr

if __name__ == "__main__":
    a = Acceptor()
    a.run_accept_loop()
    print "Exiting"