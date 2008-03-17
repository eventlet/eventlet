"""\
@file echoserver.py

Simple server that listens on port 6000 and echos back every input to
the client.  To try out the server, start it up by running this file.

Connect to it with:
  telnet localhost 6000

You terminate your connection by terminating telnet (typically Ctrl-]
and then 'quit')

Copyright (c) 2007, Linden Research, Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

from eventlet import api

def handle_socket(client):
    print "client connected"
    while True:
        # pass through every non-eof line
        x = client.readline()
        if not x: break
        client.write(x)
        print "echoed", x
    print "client disconnected"

# server socket listening on port 6000
server = api.tcp_listener(('0.0.0.0', 6000))
while True:
    new_sock, address = server.accept()
    # handle every new connection with a new coroutine
    api.spawn(handle_socket, new_sock)

server.close()
