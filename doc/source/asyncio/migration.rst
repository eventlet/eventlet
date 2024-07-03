.. _migration-guide:

Migrating off of Eventlet
=========================

There are two main use cases for Eventlet:

1. As a required networking framework, much like one would use ``asyncio``,
   ``trio``, or older frameworks like ``Twisted`` and ``tornado``.

2. As an optional, pluggable backend that allows swapping out blocking APIs
   for an event loop, transparently, without changing any code.
   This is how Celery and Gunicorn use eventlet.

Pretending to look like a blocking API while actually using an event loop
underneath requires exact emulation of an ever-changing and ever-increasing
API footprint, which is fundamentally unsustainable for a volunteer-driven
open source project.
This is why Eventlet is discouraging new users.

**Most of this document will focus on the first use case: Eventlet as the sole
networking framework.**
For this use case, we recommend migrating to Python's ``asyncio``, and we are
providing infrastructure that will make this much easier, and allow for
*gradual* migration.

For the second use case, we believe this is a fundamentally unsustainable
approach and encourage the upstream frameworks to come up with different
solutions.

Step 1. Switch to the ``asyncio`` Hub
-------------------------------------

Eventlet has different pluggable networking event loops.
By switching the event loop to use ``asyncio``, you enable running ``asyncio``
and Eventlet code in the same thread in the same process.

To do so, set the ``EVENTLET_HUB`` environment variable to ``asyncio`` before
starting your Eventlet program.
For example, if you start your program with a shell script, you can do
``export EVENTLET_HUB=asyncio``.

Alternatively, you can explicitly specify the ``asyncio`` hub at startup,
before monkey patching or any other setup work::

  import eventlet.hubs
  eventlet.hubs.use_hub("eventlet.hubs.asyncio")

Step 2. Migrate code to ``asyncio``
-----------------------------------

Now that you're running Eventlet on top of ``asyncio``, you can use some new
APIs to call from Eventlet code into ``asyncio``, and vice-versa.

To call ``asyncio`` code from Eventlet code, you can wrap a coroutine (or
anything you can ``await``) into an Eventlet ``GreenThread``.
For example, if you want to make a HTTP request from Eventlet, you can use
the ``asyncio``-based ``aiohttp`` library::

    import aiohttp
    from eventlet.asyncio import spawn_for_awaitable

    async def request():
        async with aiohttp.ClientSession() as session:
            url = "https://example.com"
            async with session.get(url) as response:
                html = await response.text()
                return html


    # This makes a coroutine; typically you'd ``await`` it:
    coro = request()

    # You can wrap this coroutine with an Eventlet GreenThread, similar to
    # ``evenlet.spawn()``:
    gthread = spawn_for_awaitable(request())

    # And then get its result, the body of https://example.com:
    result = gthread.wait()

In the other direction, any ``eventlet.greenthread.GreenThread`` can be
``await``-ed in ``async`` functions.
In other words ``async`` functions can call into Eventlet code::

    def blocking_eventlet_api():
        eventlet.sleep(1)
        # do some other pseudo-blocking work
        # ...
        return 12

    async def my_async_func():
        gthread = eventlet.spawn(blocking_eventlet_api)
        # In normal Eventlet code we'd call gthread.wait(), but since this is an
        # async function we'll want to await instead:
        result = await gthread
        # result is now 12
        # ...

Cancellation of ``asyncio.Future`` and killing of ``eventlet.GreenThread``
should propagate between the two.

Using these two APIs, with more to come, you can gradually migrate portions of
your application or library to ``asyncio``.
Calls to blocking APIs like ``urlopen()`` or ``requests.get()`` can get
replaced with calls to ``aiohttp``, for example.

Depending on your Eventlet usage, during your migration, you may have to
deprecate CLI options that are related to Eventlet, we invite the reader
to take a look to :ref:`manage-your-deprecations`.

The `awesome-asyncio <https://github.com/timofurrer/awesome-asyncio>`_ github
repository propose a curated list of awesome Python asyncio frameworks,
libraries, software and resources. Do not hesitate to take a look at it.
You may find candidates compatible with asyncio that can allow you to replace
some of your actual underlying libraries.

Step 3. Drop Eventlet altogether
--------------------------------

Eventually you won't be relying on Eventlet at all: all your code will be
``asyncio``-based.
At this point you can drop Eventlet and switch to running the ``asyncio``
loop directly.

Known limitations and work in progress
--------------------------------------

In general, ``async`` functions and Eventlet green threads are two separate
universes that just happen to be able to call each other.

In ``async`` functions:

* Eventlet thread locals probably won't work correctly.
* ``evenlet.greenthread.getcurrent()`` won't give the result you expect.
* ``eventlet`` locks and queues won't work if used directly.
* Eventlet multiple readers are not supported, and so using
  ``eventtlet.debug.hub_prevent_multiple_readers`` neither.

In Eventlet greenlets:

* ``asyncio`` locks won't work if used directly.

We expect to add more migration and integration APIs over time as we learn
more about what works, common idioms, and requirements for migration.
You can track progress in the
`GitHub issue <https://github.com/eventlet/eventlet/issues/868>`_, and file
new issues if you have problems.

Alternatives
------------

If you really want to continue with Eventlet's pretend-to-be-blocking
approach, you can use `gevent <https://www.gevent.org/>`_.
But keep in mind that the same technical issues that make Eventlet maintenance
unsustainable over the long term also apply to Gevent.
