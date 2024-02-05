Warning
=======

**New usages of eventlet are now heavily discouraged! Please read the
following.**

Eventlet was created almost 18 years ago, at a time where async
features were absent from the CPython stdlib. With time eventlet evolved and
CPython too, but since several years the maintenance activity of eventlet
dicreased leading to a growing gap between eventlet and the CPython
implementation.

This gap is now too high and can lead you to unexpected side effects and bugs
in your applications.

Eventlet now follows a new maintenance policy. **Only maintenance for
stability and bug fixing** will be provided. **No new features will be
accepted**, except those related to the asyncio migration. **Usages in new
projects are discouraged**. **Our goal is to plan the retirement of eventlet**
and to give you ways to move away from eventlet.

If you are looking for a library to manage async network programming,
and if you do not yet use eventlet, then, we encourage you to use `asyncio`_,
which is the official async library of the CPython stdlib.

If you already use eventlet, we hope to enable migration to asyncio for some use
cases; see :ref:`migration-guide`. Only new features related to the migration
solution will be accepted.

If you have questions concerning maintenance goals or concerning
the migration do not hesitate to `open a new issue`_, we will be happy to
answer them.

.. _asyncio: https://docs.python.org/3/library/asyncio.html
.. _open a new issue: https://github.com/eventlet/eventlet/issues/new

Eventlet Documentation
======================

Code talks!  This is a simple web crawler that fetches a bunch of urls concurrently:

.. code-block:: python

    urls = [
        "http://www.google.com/intl/en_ALL/images/logo.gif",
        "http://python.org/images/python-logo.gif",
        "http://us.i1.yimg.com/us.yimg.com/i/ww/beta/y3.gif",
    ]

    import eventlet
    from eventlet.green.urllib.request import urlopen

    def fetch(url):
        return urlopen(url).read()

    pool = eventlet.GreenPool()
    for body in pool.imap(fetch, urls):
        print("got body", len(body))

Supported Python versions
=========================

Currently supporting CPython 3.7+.


Contents
=========

.. toctree::
   :maxdepth: 2

   migration
   basic_usage
   design_patterns
   patching
   examples
   ssl
   threading
   zeromq
   hubs
   testing
   environment

   modules

   process
   authors
   history

License
---------
Eventlet is made available under the terms of the open source `MIT license <http://www.opensource.org/licenses/mit-license.php>`_

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
