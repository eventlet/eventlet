Basic Usage
=============

Eventlet is built around the concept of green threads (i.e. coroutines, we use the terms interchangeably) that are launched to do network-related work.  Green threads differ from normal threads in two main ways:

* Green threads are so cheap they are nearly free.  You do not have to conserve green threads like you would normal threads.  In general, there will be at least one green thread per network connection.
* Green threads cooperatively yield to each other instead of preemptively being scheduled.  The major advantage from this behavior is that shared data structures don't need locks, because only if a yield is explicitly called can another green thread have access to the data structure.  It is also possible to inspect primitives such as queues to see if they have any pending data.

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

``from eventlet.green import urllib2`` is how you import a cooperatively-yielding version of urllib2.  It is the same in all respects to the standard version, except that it uses green sockets for its communication.

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


Primary API
===========

The design goal for Eventlet's API is simplicity and readability.  You should be able to read its code and understand what it's doing.  Fewer lines of code are preferred over excessively clever implementations.  Like Python itself, there should be only one right way to do something with Eventlet!

Though Eventlet has many modules, much of the most-used stuff is accessible simply by doing ``import eventlet``

.. function:: eventlet.spawn(func, *args, **kw)
   
   This launches a greenthread to call *func*.  Spawning off multiple greenthreads gets work done in parallel.  The return value from ``spawn`` is a :class:`greenthread.GreenThread` object, which can be used to retrieve the return value of *func*.  See :func:`greenthread.spawn` for more details.
   
.. function:: eventlet.spawn_n(func, *args, **kw)
   
   The same as :func:`spawn`, but it's not possible to retrieve the return value.  This makes execution faster.  See :func:`greenthread.spawn_n` for more details.

.. function:: eventlet.sleep(seconds)

    Suspends the current greenthread and allows others a chance to process.  See :func:`greenthread.sleep` for more details.

.. class:: eventlet.GreenPool

   Pools control concurrency.  It's very common in applications to want to consume only a finite amount of memory, or to restrict the amount of connections that one part of the code holds open so as to leave more for the rest, or to behave consistently in the face of unpredictable input data.  GreenPools provide this control.  See :class:`greenpool.GreenPool` for more on how to use these.

.. class:: eventlet.GreenPile

    Sister class to the GreenPool, GreenPile objects represent chunks of work.  In essence a GreenPile is an iterator that can be stuffed with work, and the results read out later. See :class:`greenpool.GreenPile` for more details.
    
.. class:: eventlet.Queue

    Queues are a fundamental construct for communicating data between execution units.  Eventlet's Queue class is used to communicate between greenthreads, and provides a bunch of useful features for doing that.  See :class:`queue.Queue` for more details.
    
These are the basic primitives of Eventlet; there are a lot more out there in the other Eventlet modules; check out the :doc:`modules`.


Green Libraries
----------------

The package ``eventlet.green`` contains libraries that have the same interfaces as common standard ones, but they are modified to behave well with green threads.  This can be preferable than monkeypatching in many circumstances, because it may be necessary to interoperate with some module that needs the standard libraries unmolested, or simply because it's good engineering practice to be able to understand how a file behaves based simply on its contents.

To use green libraries, simply import the desired module from ``eventlet.green``::

  from eventlet.green import socket
  from eventlet.green import threading
  from eventlet.green import asyncore
  
That's all there is to it!


Monkeypatching the Standard Library
----------------------------------------

.. automethod:: eventlet.util::wrap_socket_with_coroutine_socket

Eventlet's socket object, whose implementation can be found in the
:mod:`eventlet.greenio` module, is designed to match the interface of the
standard library :mod:`socket` object. However, it is often useful to be able to
use existing code which uses :mod:`socket` directly without modifying it to use the eventlet apis. To do this, one must call :func:`~eventlet.util.wrap_socket_with_coroutine_socket`. It is only necessary
to do this once, at the beginning of the program, and it should be done before
any socket objects which will be used are created.

.. automethod:: eventlet.util::wrap_select_with_coroutine_select

Some code which is written in a multithreaded style may perform some tricks,
such as calling :mod:`select` with only one file descriptor and a timeout to
prevent the operation from being unbounded. For this specific situation there
is :func:`~eventlet.util.wrap_select_with_coroutine_select`; however it's
always a good idea when trying any new library with eventlet to perform some
tests to ensure eventlet is properly able to multiplex the operations.
