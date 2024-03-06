:mod:`backdoor` -- Python interactive interpreter within a running process
===============================================================================

The backdoor module is convenient for inspecting the state of a long-running process.  It supplies the normal Python interactive interpreter in a way that does not block the normal operation of the application.  This can be useful for debugging, performance tuning, or simply learning about how things behave in situ.

In the application, spawn a greenthread running backdoor_server on a listening socket::

    eventlet.spawn(backdoor.backdoor_server, eventlet.listen(('localhost', 3000)), locals())

When this is running, the backdoor is accessible via telnet to the specified port.

.. code-block:: sh

  $ telnet localhost 3000
  (python version, build info)
  Type "help", "copyright", "credits" or "license" for more information.
  >>> import myapp
  >>> dir(myapp)
  ['__all__', '__doc__', '__name__', 'myfunc']
  >>>

The backdoor cooperatively yields to the rest of the application between commands, so on a running server continuously serving requests, you can observe the internal state changing between interpreter commands.

This backdoor can also be interactivelly created on any running eventlet based process by sending ``USR1`` `signal <https://www.man7.org/linux/man-pages/man7/signal.7.html>`_ to the process you want to attach. Only available on `UNIX like platforms <https://docs.python.org/3/library/signal.html#signal.SIGUSR1>`_.

Example:

.. code-block::sh
   $ kill -e SIGUSER1 <pid>

Where ``<pid>`` is the process identifier of the process you want to attachby using the backdoor. Launching backdoor this way can allow to debug production running process based on eventlet.

The backdoor can be closed by sending the ``USR2`` `signal <https://www.man7.org/linux/man-pages/man7/signal.7.html>`_ to the process to which you provisouly started the backdoor, example:

.. code-block::sh
   $ kill -e SIGUSER1 <pid>

Avoiding you to let run this backdoor indefinitely.

.. automodule:: eventlet.backdoor
	:members:
