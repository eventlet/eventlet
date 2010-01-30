Eventlet
====================================

Eventlet is a networking library written in Python. It achieves high scalability by using `non-blocking io <http://en.wikipedia.org/wiki/Asynchronous_I/O#Select.28.2Fpoll.29_loops>`_ while at the same time retaining high programmer usability by using `coroutines <http://en.wikipedia.org/wiki/Coroutine>`_ to make the non-blocking io operations appear blocking at the source code level.

Eventlet is different from other event-based frameworks out there because it doesn't require you to restructure your code to use it.  You don't have to rewrite your code to use callbacks, and you don't have to replace your main() method with some sort of dispatch method.  You can just sprinkle eventlet on top.

Simple Example
-------------------

This is a simple web crawler that fetches a bunch of urls concurrently.

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
      

Contents
=========

.. toctree::
   :maxdepth: 2

   basic_usage
   examples
   ssl
   threading
   hubs
   testing
   history

   modules
   
   authors

License
---------
Eventlet is made available under the terms of the open source `MIT license <http://www.opensource.org/licenses/mit-license.php>`_

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
