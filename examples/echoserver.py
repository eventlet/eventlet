#! /usr/bin/env python
"""\
Simple server that listens on port 6000 and echos back every input to
the client.  To try out the server, start it up by running this file.

Connect to it with:
  telnet localhost 6000

You terminate your connection by terminating telnet (typically Ctrl-]
and then 'quit')
"""

import eventlet
from eventlet.green import socket

def handle(reader, writer):
    print "client connected"
    while True:
        # pass through every non-eof line
        x = reader.readline()
        if not x: break
        writer.write(x)
        writer.flush()
        print "echoed", x,
    print "client disconnected"

print "server socket listening on port 6000"
server = socket.socket()
server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', 6000))
server.listen(50)
pool = eventlet.GreenPool(10000)
while True:
    try:
        new_sock, address = server.accept()
        print "accepted", address
        pool.spawn_n(handle, new_sock.makefile('r'), new_sock.makefile('w'))
    except (SystemExit, KeyboardInterrupt):
        break
