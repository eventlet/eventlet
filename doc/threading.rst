Threads
========

Eventlet is thread-safe and can be used in conjunction with normal Python threads.  The way this works is that coroutines are confined to their 'parent' Python thread.  It's like each thread contains its own little world of coroutines that can switch between themselves but not between coroutines in other threads.

.. image:: /images/threading_illustration.png

You can only communicate cross-thread using the "real" thread primitives and pipes.  Fortunately, there's little reason to use threads for concurrency when you're already using coroutines.

The vast majority of the times you'll want to use threads are to wrap some operation that is not "green", such as a C library that uses its own OS calls to do socket operations.  The :mod:`~eventlet.tpool` module is provided to make these uses simpler.

The optional :ref:`pyevent hub <understanding_hubs>` is not compatible with threads.

Tpool - Simple thread pool
---------------------------

The simplest thing to do with :mod:`~eventlet.tpool` is to :func:`~eventlet.tpool.execute` a function with it.  The function will be run in a random thread in the pool, while the calling coroutine blocks on its completion::

 >>> import thread
 >>> from eventlet import tpool
 >>> def my_func(starting_ident):
 ...     print("running in new thread:", starting_ident != thread.get_ident())
 ...
 >>> tpool.execute(my_func, thread.get_ident())
 running in new thread: True

By default there are 20 threads in the pool, but you can configure this by setting the environment variable ``EVENTLET_THREADPOOL_SIZE`` to the desired pool size before importing tpool.

Alternatively you can also set the number of threads in the pool to any value
after importing tpool using the ``set_num_threads`` method as long as you
haven't called the ``execute`` method.  If the ``execute`` method has already
been called, only increases to the thread pool size will take immediate effect,
lower values will not take effect until we kill all the existing threads with a
call to ``killall``.

.. automodule:: eventlet.tpool
	:members:
