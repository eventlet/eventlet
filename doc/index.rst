Eventlet
====================================

Eventlet is a networking library written in Python. It achieves high scalability by using `non-blocking io <http://en.wikipedia.org/wiki/Asynchronous_I/O#Select.28.2Fpoll.29_loops>`_ while at the same time retaining high programmer usability by using `coroutines <http://en.wikipedia.org/wiki/Coroutine>`_ to make the non-blocking io operations appear blocking at the source code level.

Web Crawler Example
--------

This is a simple web "crawler" that fetches a bunch of urls using a coroutine pool.  It has as much concurrency (i.e. pages being fetched simultaneously) as coroutines in the pool.

::

  urls = ["http://www.google.com/intl/en_ALL/images/logo.gif",
         "http://wiki.secondlife.com/w/images/secondlife.jpg",
         "http://us.i1.yimg.com/us.yimg.com/i/ww/beta/y3.gif"]
  
  import time
  from eventlet import coros, httpc, util
  
  # replace socket with a cooperative coroutine socket because httpc
  # uses httplib, which uses socket.  Removing this serializes the http
  # requests, because the standard socket is blocking.
  util.wrap_socket_with_coroutine_socket()
  
  def fetch(url):
      # we could do something interesting with the result, but this is
      # example code, so we'll just report that we did it
      print "%s fetching %s" % (time.asctime(), url)
      httpc.get(url)
      print "%s fetched %s" % (time.asctime(), url)
  
  pool = coros.CoroutinePool(max_size=4)
  waiters = []
  for url in urls:
      waiters.append(pool.execute(fetch, url))
  
  # wait for all the coroutines to come back before exiting the process
  for waiter in waiters:
      waiter.wait()

Requirements
------------

Eventlet runs on Python version 2.4 or greater, with the following dependencies:

* `Greenlet <http://cheeseshop.python.org/pypi/greenlet>`_
* `pyOpenSSL <http://pyopenssl.sourceforge.net/>`_

Areas That Need Work
-----------

* Not enough test coverage -- the goal is 100%, but we are not there yet.
* Not tested on Windows
 
 * There are probably some simple Unix dependencies we introduced by accident.  If you're running Eventlet on Windows and run into errors, let us know.
 * The eventlet.processes module is known to not work on Windows.

History
--------

Eventlet began life as Donovan Preston was talking to Bob Ippolito about coroutine-based non-blocking networking frameworks in Python. Most non-blocking frameworks require you to run the "main loop" in order to perform all network operations, but Donovan wondered if a library written using a trampolining style could get away with transparently running the main loop any time i/o was required, stopping the main loop once no more i/o was scheduled. Bob spent a few days during PyCon 2006 writing a proof-of-concept. He named it eventlet, after the coroutine implementation it used, `greenlet <http://cheeseshop.python.org/pypi/greenlet greenlet>`_. Donovan began using eventlet as a light-weight network library for his spare-time project `Pavel <http://soundfarmer.com/Pavel/trunk/ Pavel>`_, and also began writing some unittests.

* http://svn.red-bean.com/bob/eventlet/trunk/

When Donovan started at Linden Lab in May of 2006, he added eventlet as an svn external in the indra/lib/python directory, to be a dependency of the yet-to-be-named backbone project (at the time, it was named restserv). However, including eventlet as an svn external meant that any time the externally hosted project had hosting issues, Linden developers were not able to perform svn updates. Thus, the eventlet source was imported into the linden source tree at the same location, and became a fork.

Bob Ippolito has ceased working on eventlet and has stated his desire for Linden to take it's fork forward to the open source world as "the" eventlet.



Contents:

.. toctree::
   :maxdepth: 2

   modules.rst

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


License
---------
Eventlet is made available under the terms of the open source MIT license below.

**EVENTLET**

Copyright (c) 2005-2006, Bob Ippolito
Copyright (c) 2007, Linden Research, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
	
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
	
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

