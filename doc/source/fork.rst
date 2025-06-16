fork() without execve()
=======================

``fork()`` is a way to make a clone of a process.
Most subprocesses replace the child process with a new executable, wiping out all memory from the parent process.
A ``fork()ed`` subprocess can choose not to do this, and preserve data from the parent process.
(Technically this is ``fork()`` without ``execve()``.)

This is a terrible idea, as it can cause deadlocks, memory corruption, and crashes.

For backwards compatibility, Eventlet *tries* to work in this case, but this is very much not guaranteed and your program may suffer from deadlocks, memory corruption, and crashes.
This is even more so when using the ``asyncio`` hub, as that requires even more questionable interventions to "work".

This is not a problem with Eventlet.
It's a fundamental problem with ``fork()`` applicable to pretty much every Python program.

Below are some common reasons you might be using ``fork()`` without knowing it, and what you can do about it.

``multiprocessing``
------------------

On Linux, on Python 3.13 earlier, the standard library ``multiprocessing`` library uses ``fork()`` by default.
To fix this, switch to the ``"spawn"`` method (the default in Python 3.14 and later) as `documented here <https://docs.python.org/3.13/library/multiprocessing.html#contexts-and-start-methods>`.


``oslo.service``
----------------

There are alternative ways of running services that do not use ``fork()``.
See the documentation.
