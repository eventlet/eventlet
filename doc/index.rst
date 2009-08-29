Eventlet
====================================

Eventlet is a networking library written in Python. It achieves high scalability by using `non-blocking io <http://en.wikipedia.org/wiki/Asynchronous_I/O#Select.28.2Fpoll.29_loops>`_ while at the same time retaining high programmer usability by using `coroutines <http://en.wikipedia.org/wiki/Coroutine>`_ to make the non-blocking io operations appear blocking at the source code level.

Eventlet is different from all the other event-based frameworks out there because it doesn't require you to restructure your code to use it.  You don't have to rewrite your code to use callbacks, and you don't have to replace your main() method with some sort of dispatch method.  You can just sprinkle eventlet on top of your normal-looking code.

Web Crawler Example
-------------------

This is a simple web "crawler" that fetches a bunch of urls using a coroutine pool.  It has as much concurrency (i.e. pages being fetched simultaneously) as coroutines in the pool (in our example, 4).

::

  urls = ["http://www.google.com/intl/en_ALL/images/logo.gif",
         "http://wiki.secondlife.com/w/images/secondlife.jpg",
         "http://us.i1.yimg.com/us.yimg.com/i/ww/beta/y3.gif"]
  
  import time
  from eventlet import coros
  
  # this imports a special version of the urllib2 module that uses non-blocking IO
  from eventlet.green import urllib2
  
  def fetch(url):
      print "%s fetching %s" % (time.asctime(), url)
      data = urllib2.urlopen(url)
      print "%s fetched %s" % (time.asctime(), data)
  
  pool = coros.CoroutinePool(max_size=4)
  waiters = []
  for url in urls:
      waiters.append(pool.execute(fetch, url))
  
  # wait for all the coroutines to come back before exiting the process
  for waiter in waiters:
      waiter.wait()
      

Contents
=========

.. toctree::
   :maxdepth: 2

   basic_usage
   chat_server_example
   threading
   history

   modules

Requirements
------------

Eventlet runs on Python version 2.4 or greater, with the following dependencies:

* `Greenlet <http://cheeseshop.python.org/pypi/greenlet>`_
* `pyOpenSSL <http://pyopenssl.sourceforge.net/>`_


Areas That Need Work
--------------------

* Not enough test coverage -- the goal is 100%, but we are not there yet.
* Not tested on Windows
 
 * There are probably some simple Unix dependencies we introduced by accident.  If you're running Eventlet on Windows and run into errors, let us know.
 * The eventlet.processes module is known to not work on Windows.


License
---------
Eventlet is made available under the terms of the open source MIT license below.

**EVENTLET**

Copyright (c) 2005-2006, Bob Ippolito
Copyright (c) 2007, Linden Research, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
	
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
	
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
