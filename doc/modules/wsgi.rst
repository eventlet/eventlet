:mod:`wsgi` -- WSGI server
===========================

The wsgi module provides a simple an easy way to start an event-driven 
`WSGI <http://wsgi.org/wsgi/>`_ server.  This can serve as an embedded
web server in an application, or as the basis for a more full-featured web
server package.  One such package is `Spawning <http://pypi.python.org/pypi/Spawning/>`_.

To launch a wsgi server, simply create a socket and call :func:`eventlet.wsgi.server` with it::

    from eventlet import wsgi
    from eventlet.green import socket
    
    def hello_world(env, start_response):
        start_response('200 OK', [('Content-Type', 'text/plain')])
        return ['Hello, World!\r\n']
    
    sock = socket.socket()
    sock.bind(('', 8090))
    sock.listen(500)
    
    wsgi.server(sock, hello_world)


You can find a slightly more elaborate version of this code in the file
``examples/wsgi.py``.

.. automodule:: eventlet.wsgi
	:members:
