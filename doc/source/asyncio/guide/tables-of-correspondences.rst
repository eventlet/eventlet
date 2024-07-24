.. _tables-of-correspondences:

The Tables of Correspondences
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The goal of the tables of correspondences is to bind the common use cases of
Eventlet (see ref:`design-patterns`) to turnkey alternatives.

This document define two tables, a patterns based table, and a hierarchy
of tiers based table. Each table is a representation that can help
you to identify the available alternatives at your disposal to remove such or
such Eventlet usages depending on a given context.

The goal of these tables is helping you to identify the complexity of adopting
a replacement solution or an other.

.. _the-patterns-based-table:

The Patterns Based Table
~~~~~~~~~~~~~~~~~~~~~~~~

This table of correspondences is be based on the main Eventlet
:ref:`design patterns <design-patterns>` (server, client, dispatch).

This table invites the persons in charge of the migration to think in terms
of common patterns. Most people using Eventlet can identify themselves into
one of these three patterns categories.

+---------------------+--------------------------------+----------------------------------------------------------+
| Eventlet Patterns   | Eventlet features              | Available Alternatives                                   |
+=====================+================================+================================+=========================+
| 1. **Server**       |                                | **Asynchronous**               | **Synchronous**         |
|                     |                                +--------------------------------+-------------------------+
|                     | eventlet.listen,               | aiohttp.web.Application,       | http.server.*HTTPServer |
|                     | eventlet.green.socket,         | async (for|with),              |                         |
|                     | eventlet.green.http.server,    | await,                         |                         |
|                     | eventlet.green.*Server,        | asyncio.start_server()         |                         |
|                     | eventlet.websocket,            | StreamReader/StreamWriter,     |                         |
|                     | eventlet.wsgi                  | asyncio.open_connection(),     |                         |
|                     | eventlet.GreenPool,            | awaitlet*                      |                         |
|                     |                                |                                |                         |
+---------------------+--------------------------------+--------------------------------+-------------------------+
| 2. **Client**       | eventlet.green.urllib*,        | asyncio.run(),                 | http.client,            |
|                     | eventlet.greenpool             | aiohttp.ClientSession,         | urllib.request          |
|                     |                                | http.client                    |                         |
|                     |                                | urllib.request                 |                         |
|                     |                                | async (for|with), await,       |                         |
|                     |                                | awaitlet*                      |                         |
|                     |                                |                                |                         |
+---------------------+--------------------------------+--------------------------------+-------------------------+
| 3. **Dispatch**     | eventlet.listen,               | asyncio.Future,                | http.client,            |
|                     | eventlet.GreenPile             | futurist.Future,               | urllib.request,         |
|                     |                                | concurrent.futures.Executor    | http.server.*HTTPServer |
|                     |                                | aiohttp.web.Application,       |                         |
|                     |                                | async (for|with), await        |                         |
|                     |                                | http.server.HTTPServer,        |                         |
|                     |                                | http.server.TreadingHTTPServer |                         |
|                     |                                | asyncio.start_server()         |                         |
|                     |                                | StreamReader, StreamWriter,    |                         |
|                     |                                | asyncio.open_connection(),     |                         |
|                     |                                | asyncio.run(),                 |                         |
|                     |                                | aiohttp.ClientSession,         |                         |
|                     |                                | http.client                    |                         |
|                     |                                | urllib.request                 |                         |
|                     |                                | async (for|with), await,       |                         |
|                     |                                | awaitlet*                      |                         |
|                     |                                |                                |                         |
+---------------------+--------------------------------+--------------------------------+-------------------------+

.. _the-hierarchy-of-tiers-based-table:

The Hierarchy of Tiers Based Table
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This table invites the reader to think in terms of task and coroutine. This
table is based on a hierarchy of tiers based on the different concepts brought
by Asyncio. Each tier is built on the specification of the previous level.

To provide replacement to existing features of Eventlet, we think it is much
more useful to think about the use cases being arranged in a hierarchy, rather
than a flat list.

This way of representing the correspondences is inspired from the book
`Using Asyncio in Python <https://www.oreilly.com/library/view/using-asyncio-in/9781492075325/>`_.

Each tier is related to a level of abstraction. The first tiers are
the most abstract layers. The last tiers reflect low level mechanisms.

Asyncio target two main audiences:
    * end-users developers who want to make applications using asyncio
    * framework developers who want to make frameworks and libraries that
      end-users developers can use in their applications

+---------------------+--------------------------------+--------------------------------+
| Hierarchy of tiers  | Eventlet features              | Available alternatives         |
+=====================+================================+================================+
| 1. **coroutines**   | eventlet.GreenPool,            | async def, async with,         |
|                     | eventlet.tpool,                | async for, await, awaitlet*    |
|                     | eventlet.spawn,                |                                |
|                     | eventlet.spawn_n,              |                                |
|                     | eventlet.spawn_after           |                                |
+---------------------+--------------------------------+--------------------------------+
| 2. **event loop**   | eventlet.greenthread.spawn*    | asyncio.run(),                 |
|                     |                                | BaseEventLoop                  |
+---------------------+--------------------------------+--------------------------------+
| 3. **Futures**      |                                | asyncio.Future,                |
|                     |                                | futurist.Future,               |
|                     |                                | concurrent.futures.Executor    |
+---------------------+--------------------------------+--------------------------------+
| 4. **Tasks**        | eventlet.GreenPool.spawn,      | asyncio.Task,                  |
|                     | eventlet.pools                 | asyncio.create_task()          |
+---------------------+--------------------------------+--------------------------------+
| 5. **Subprocess &** | eventlet.GreenPool.spawn,      | run_in_executor(),             |
|    **threads:**     | eventlet.greenthread.spawn*    | asyncio.subprocess,            |
|                     | eventlet.tpool,                | cotyledon.Service,             |
|                     | eventlet.spawn,                | futurist.Future,               |
|                     | eventlet.spawn_n,              | concurrent.futures.Executor    |
|                     | eventlet.spawn_after           | threading.Thread,              |
|                     |                                | futurist.ThreadPoolExecutor    |
+---------------------+--------------------------------+--------------------------------+
| 6. **Tools**        | eventlet.green.Queue           | asyncio.Queue, queue.Queue,    |
|                     | eventlet.lock                  | asyncio.Lock, threading.Lock   |
|                     | eventlet.timeout               | asyncio.timeout, threading..., |
|                     | eventlet.semaphore             | asyncio.Semaphore,             |
|                     |                                | threading.Semaphore            |
+---------------------+--------------------------------+--------------------------------+
| 7. **_Network**     |                                | BaseTransport                  |
| **(transport)**     |                                |                                |
+---------------------+--------------------------------+--------------------------------+
| 8. **Network**      | eventlet.green.SocketServer    | Protocol                       |
| **(TCP & UDP):**    |                                |                                |
+---------------------+--------------------------------+--------------------------------+
| 9. **Network**      | eventlet.green.BaseHTTPServer, | StreamReader, StreamWriter,    |
| **(streams):**      | eventlet.green.httplib         | asyncio.open_connection(),     |
|                     | eventlet.websocket             | asyncio.start_server(),        |
|                     | eventlet.wsgi                  | http.server.HTTPServer,        |
|                     | eventlet.support.greendns      | http.server.TreadingHTTPServer |
|                     |                                | dnspython                      |
+---------------------+--------------------------------+--------------------------------+

The previous table voluntarily ignores some Eventlet concepts like
``eventlet.patcher``, ``eventlet.hubs``, which have no meaning outside of the
Eventlet context. The previous table also voluntarily ignores green
representations of third party modules like ``eventlet.zmq``.

We should notice that finally many subsets of Eventlet features may match
many tiers, depending on their usages. By example the ``eventlet.tpool``
which is present in tiers 1 and 5. That's due to the fact that Eventlet only
reason in terms of greenlet.
