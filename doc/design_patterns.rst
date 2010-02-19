.. _design-patterns:

Design Patterns
=================

There are a bunch of basic patterns that Eventlet usage falls into.  Here are a few examples that show their basic structure.

Client-side pattern
--------------------

The canonical client-side example is a web crawler.  This use case is given a list of urls and wants to retrieve their bodies for later processing.  Here is a very simple example::


  urls = ["http://www.google.com/intl/en_ALL/images/logo.gif",
         "https://wiki.secondlife.com/w/images/secondlife.jpg",
         "http://us.i1.yimg.com/us.yimg.com/i/ww/beta/y3.gif"]
  
  import eventlet
  from eventlet.green import urllib2  

  def fetch(url):
      return urllib2.urlopen(url).read()
  
  pool = eventlet.GreenPool()
  for body in pool.imap(fetch, urls):
      print "got body", len(body)

There is a slightly more complex version of this in the :ref:`web crawler example <web_crawler_example>`.  Here's a tour of the interesting lines in this crawler. 

``from eventlet.green import urllib2`` is how you import a cooperatively-yielding version of urllib2.  It is the same in all respects to the standard version, except that it uses green sockets for its communication.  This is an example of the :ref:`import-green` pattern.

``pool = eventlet.GreenPool()`` constructs a :class:`GreenPool <eventlet.greenpool.GreenPool>` of a thousand green threads.  Using a pool is good practice because it provides an upper limit on the amount of work that this crawler will be doing simultaneously, which comes in handy when the input data changes dramatically.

``for body in pool.imap(fetch, urls):`` iterates over the results of calling the fetch function in parallel.  :meth:`imap <eventlet.greenpool.GreenPool.imap>` makes the function calls in parallel, and the results are returned in the order that they were executed.


Server-side pattern
--------------------

Here's a simple server-side example, a simple echo server::
    
    import eventlet
    from eventlet.green import socket
    
    def handle(client):
        while True:
            c = client.recv(1)
            if not c: break
            client.sendall(c)
    
    server = socket.socket()
    server.bind(('0.0.0.0', 6000))
    server.listen(50)
    pool = eventlet.GreenPool(10000)
    while True:
        new_sock, address = server.accept()
        pool.spawn_n(handle, new_sock)

The file :ref:`echo server example <echo_server_example>` contains a somewhat more robust and complex version of this example.

``from eventlet.green import socket`` imports eventlet's socket module, which is just like the regular socket module, but cooperatively yielding.

``pool = eventlet.GreenPool(10000)`` creates a pool of green threads that could handle ten thousand clients.  

``pool.spawn_n(handle, new_sock)`` launches a green thread to handle the new client.  The accept loop doesn't care about the return value of the ``handle`` function, so it uses :meth:`spawn_n <eventlet.greenpool.GreenPool.spawn_n>`, instead of :meth:`spawn <eventlet.greenpool.GreenPool.spawn>`.

