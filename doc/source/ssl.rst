Using SSL With Eventlet
========================

Eventlet makes it easy to use non-blocking SSL sockets. If you're using Python 3.7 or later, you're all set, eventlet wraps the built-in ssl module.

In either case, the ``green`` modules handle SSL sockets transparently, just like their standard counterparts.  As an example, :mod:`eventlet.green.urllib2` can be used to fetch https urls in as non-blocking a fashion as you please::

    from eventlet.green.urllib.request import urlopen
    from eventlet import spawn
    bodies = [spawn(urlopen, url)
         for url in ("https://secondlife.com","https://google.com")]
    for b in bodies:
        print(b.wait().read())


PyOpenSSL
----------

:mod:`eventlet.green.OpenSSL` has exactly the same interface as pyOpenSSL_ `(docs) <http://pyopenssl.sourceforge.net/pyOpenSSL.html/>`_, and works in all versions of Python.  This module is much more powerful than :func:`socket.ssl`, and may have some advantages over :mod:`ssl`, depending on your needs.

For testing purpose first create self-signed certificate using following commands ::

    $ openssl genrsa 1024 > server.key
    $ openssl req -new -x509 -nodes -sha1 -days 365 -key server.key > server.cert

Keep these Private key and Self-signed certificate in same directory as `server.py` and `client.py` for simplicity sake.

Here's an example of a server (`server.py`) ::

    from eventlet.green import socket
    from eventlet.green.OpenSSL import SSL

    # insecure context, only for example purposes
    context = SSL.Context(SSL.SSLv23_METHOD)
    # Pass server's private key created
    context.use_privatekey_file('server.key')
    # Pass self-signed certificate created
    context.use_certificate_file('server.cert')

    # create underlying green socket and wrap it in ssl
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection = SSL.Connection(context, sock)

    # configure as server
    connection.set_accept_state()
    connection.bind(('127.0.0.1', 8443))
    connection.listen(50)

    # accept one client connection then close up shop
    client_conn, addr = connection.accept()
    print(client_conn.read(100))
    client_conn.shutdown()
    client_conn.close()
    connection.close()

Here's an example of a client (`client.py`) ::

    import socket
    # Create socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Connect to server
    s.connect(('127.0.0.1', 8443))
    sslSocket = socket.ssl(s)
    print repr(sslSocket.server())
    print repr(sslSocket.issuer())
    sslSocket.write('Hello secure socket\n')
    # Close client
    s.close()

Running example::

In first terminal

    $ python server.py

In another terminal

    $ python client.py

.. _pyOpenSSL: https://launchpad.net/pyopenssl
