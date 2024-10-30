.. _asyncio-compatibility:

Asyncio compatibility in eventlet
#################################

It should be possible to:

* Run eventlet and asyncio in the same thread.
* Allow asyncio and eventlet to interact: eventlet code can use asyncio-based libraries, asyncio-based code can get results out of eventlet.

If this works, it would allow migrating from eventlet to asyncio in a gradual manner both within and across projects:

1. Within an OpenStack library, code could be a mixture of asyncio and eventlet code.
   This means migration doesn't have to be done in one stop, neither in libraries nor in the applications that depend on them.
2. Even when an OpenStack library fully migrates to asyncio, it will still be usable by anything that is still running on eventlet.

Prior art
=========

* Gevent has a similar model to eventlet.
  There exists an integration between gevent and asyncio that follows model proposed below: https://pypi.org/project/asyncio-gevent/
* Twisted can run on top of the asyncio event loop.
  Separately, it includes utilities for mapping its `Deferred` objects (similar to a JavaScript Promise) to the async/await model introduced in newer versions in Python 3, and in the opposite direction it added support for turning async/await functions into `Deferred`s.
  In an eventlet context, `GreenThread` would need a similar former of integration to Twisted's `Deferred`.

Part 1: Implementing asyncio/eventlet interoperability
======================================================

There are three different parts involved in integrating eventlet and asyncio for purposes

1. Create a hub that runs on asyncio
------------------------------------

Like many networking frameworks, eventlet has pluggable event loops, in this case called a "hub". Typically hubs wrap system APIs like `select()` and `epoll()`, but there also used to be a hub that ran on Twisted.
Creating a hub that runs on top of the asyncio event loop should be fairly straightforward.

Once this is done, eventlet and asyncio code can run in the same process and the same thread, but they would still have difficulties talking to each other.
This latter requirement requires additional work, as covered by the next two items.

2. Calling `async def` functions from eventlet
----------------------------------------------

The goal is to allow something like this:

.. code::

    import aiohttp
    from eventlet_asyncio import future_to_greenlet  # hypothetical API
    
    async def get_url_body(url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.text()
    
    def eventlet_code():
        green_thread = future_to_greenlet(get_url_body("https://example.com"))
        return green_thread.wait()

The code would presumably be similar to https://github.com/gfmio/asyncio-gevent/blob/main/asyncio_gevent/future_to_greenlet.py

3. Calling eventlet code from asyncio
-------------------------------------

The goal is to allow something like this:

.. code::

    from urllib.request import urlopen
    from eventlet import spawn
    from eventlet_asyncio import greenlet_to_future  # hypothetical API
    
    def get_url_body(url):
        # Looks blocking, but actually isn't
        return urlopen(url).read()
    
    # This would likely be common pattern, so could be implemented as decorator...
    async def asyncio_code():
        greenlet = eventlet.spawn(get_url_body, "https://example.com")
        future = greenlet_to_future(greenlet)
        return await future

The code would presumably be similar to https://github.com/gfmio/asyncio-gevent/blob/main/asyncio_gevent/future_to_greenlet.py

4. Limitations and potential unexpected behavior
------------------------------------------------

``concurrent.futures.thread`` just uses normal threads, not Eventlet's special threads.
Similarly, `asyncio.to_thread() <https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread>`_
specifically requires regular blocking code, it won't work correctly with Eventlet code.

Multiple readers are not supported by the Asyncio hub.

Part 2: How a port would work on a technical level
==================================================

Porting a library
=================

1. Usage of eventlet-based APIs would be replaced with usage of asyncio APIs.
   For example, `urllib` or `requests` might be replaced with `aiohttp <https://docs.aiohttp.org/en/stable/>`_.
   The interoperability above can be used to make sure this continues to work with eventlet-based APIs.

   The `awesome-asyncio <https://github.com/timofurrer/awesome-asyncio>`_ github repository propose a curated list of awesome
   Python asyncio frameworks, libraries, software and resources. Do not hesitate to take a look at it. You may find
   candidates compatible with asyncio that can allow you to replace some of your actual underlying libraries.
2. Over time, APIs would need be migrated to be `async` function, but in the intermediate time frame a standard `def` can still be used, again using the interoperability layer above.
3. Eventually all "blocking" APIs have been removed, at which point everything can be switched to `async def` and `await`, including external API, and the library will no longer depend on eventlet.

Porting an application
======================

An application would need to install the asyncio hub before kicking off eventlet.
Beyond that porting would be the same as a library.

Once all libraries are purely asyncio-based, eventlet usage can be removed and an asyncio loop run instead.
