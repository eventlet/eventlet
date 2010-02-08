Examples
========

Here are a bunch of small example programs that use Eventlet.  All of these examples can be found in the ``examples`` directory of a source copy of Eventlet.

.. _web_crawler_example:

Web Crawler
------------

.. literalinclude:: ../examples/webcrawler.py

.. _wsgi_server_example:

WSGI Server
------------

.. literalinclude:: ../examples/wsgi.py

.. _echo_server_example:

Echo Server
-----------

.. literalinclude:: ../examples/echoserver.py

.. _socket_connect_example:

Socket Connect
--------------

.. literalinclude:: ../examples/connect.py

.. _chat_server_example:

Multi-User Chat Server
-----------------------

This is a little different from the echo server, in that it broadcasts the 
messages to all participants, not just the sender.
        
.. literalinclude:: ../examples/chat_server.py