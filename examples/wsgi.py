"""This is a simple example of running a wsgi application with eventlet.
For a more fully-featured server which supports multiple processes,
multiple threads, and graceful code reloading, see:

http://pypi.python.org/pypi/Spawning/
"""

from eventlet import wsgi
from eventlet.green import socket

def hello_world(env, start_response):
    if env['PATH_INFO'] != '/':
        start_response('404 Not Found', [('Content-Type', 'text/plain')])
        return ['Not Found\r\n']
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return ['Hello, World!\r\n']
        
sock = socket.socket()
sock.bind(('', 8090))
sock.listen(500)

wsgi.server(sock, hello_world)
