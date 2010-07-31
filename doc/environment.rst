.. _env_vars:

Environment Variables
======================

Eventlet's behavior can be controlled by a few environment variables.
These are only for the advanced user.

EVENTLET_HUB 

   Used to force Eventlet to use the specified hub instead of the
   optimal one.  See :ref:`understanding_hubs` for the list of
   acceptable hubs and what they mean (note that picking a hub not on
   the list will silently fail).  Equivalent to calling
   :meth:`eventlet.hubs.use_hub` at the beginning of the program.

EVENTLET_THREADPOOL_SIZE

   The size of the threadpool in :mod:`~eventlet.tpool`.  This is an
   environment variable because tpool constructs its pool on first
   use, so any control of the pool size needs to happen before then.

EVENTLET_TPOOL_DNS 

   If set to 'yes', uses :func:`eventlet.tpool.execute` to call
   :func:`~socket.gethostbyname` and :func:`~socket.getaddrinfo`,
   making them appear non-blocking.  This environment variable is
   ignored on OS X.
