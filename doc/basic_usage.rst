Basic Usage
===========

Eventlet is built around the concept of green threads (i.e. coroutines) that are launched to do network-related work.  Green threads differ from normal threads in two main ways:
* Green threads are so cheap they are nearly free.  You do not have to conserve green threads like you would normal threads.  In general, there will be at least one green thread per network connection.  Switching between them is quite efficient.
* Green threads cooperatively yield to each other instead of preemptively being scheduled.  The major advantage from this behavior is that shared data structures don't need locks, because only if a yield is explicitly called can another green thread have access to the data structure.  It is also possible to inspect communication primitives such as queues to see if they have any data or waiting green threads, something that is not possible with preemptive threads.

There are a bunch of basic patterns that Eventlet usage falls into.  One is the client pattern, which makes a bunch of requests to servers and processes the responses.  Another is the server pattern, where an application holds open a socket and processes requests that are incoming on it.  These two patterns involve somewhat different usage of Eventlet's primitives, so here are a few examples to show them off.

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
  
  pool = eventlet.GreenPool(200)
  for body in pool.imap(fetch, urls):
      print "got body", len(body)

There is a slightly more complex version of this in the file ``examples/webcrawler.py`` in the source distribution.  Here's a tour of the interesting lines in this crawler. 

``from eventlet.green import urllib2`` is how you import a cooperatively-yielding version of urllib2.  It is the same in all respects to the standard version, except that it uses green sockets for its communication.

``pool = eventlet.GreenPool(200)`` constructs a pool of 200 green threads.  Using a pool is good practice because it provides an upper limit on the amount of work that this crawler will be doing simultaneously, which comes in handy when the input data changes dramatically.

``for body in pool.imap(fetch, urls):`` iterates over the results of calling the fetch function in parallel.  :meth:`imap <eventlet.parallel.GreenPool.imap>` makes the function calls in parallel, and the results are returned in the order that they were executed.


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

The file ``examples/echoserver.py`` contains a somewhat more robust and complex version of this example.

``from eventlet.green import socket`` imports eventlet's socket module, which is just like the regular socket module, but cooperatively yielding.

``pool = eventlet.GreenPool(10000)`` creates a pool of green threads that could handle ten thousand clients.  

``pool.spawn_n(handle, new_sock)`` launches a green thread to handle the new client.  The accept loop doesn't care about the return value of the handle function, so it uses :meth:`spawn_n <eventlet.parallel.GreenPool.spawn_n>`, instead of :meth:`spawn <eventlet.parallel.GreenPool.spawn>`.  This is a little bit more efficient.



.. _using_standard_library_with_eventlet:

Using the Standard Library with Eventlet
----------------------------------------

.. automethod:: eventlet.util::wrap_socket_with_coroutine_socket

Eventlet's socket object, whose implementation can be found in the
:mod:`eventlet.greenio` module, is designed to match the interface of the
standard library :mod:`socket` object. However, it is often useful to be able to
use existing code which uses :mod:`socket` directly without modifying it to use the
eventlet apis. To do this, one must call
:func:`~eventlet.util.wrap_socket_with_coroutine_socket`. It is only necessary
to do this once, at the beginning of the program, and it should be done before
any socket objects which will be used are created. At some point we may decide
to do this automatically upon import of eventlet; if you have an opinion about
whether this is a good or a bad idea, please let us know.

.. automethod:: eventlet.util::wrap_select_with_coroutine_select

Some code which is written in a multithreaded style may perform some tricks,
such as calling :mod:`select` with only one file descriptor and a timeout to
prevent the operation from being unbounded. For this specific situation there
is :func:`~eventlet.util.wrap_select_with_coroutine_select`; however it's
always a good idea when trying any new library with eventlet to perform some
tests to ensure eventlet is properly able to multiplex the operations. If you
find a library which appears not to work, please mention it on the mailing list
to find out whether someone has already experienced this and worked around it,
or whether the library needs to be investigated and accommodated. One idea
which could be implemented would add a file mapping between common module names
and corresponding wrapper functions, so that eventlet could automatically
execute monkey patch functions based on the modules that are imported.
