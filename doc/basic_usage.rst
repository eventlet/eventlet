Basic Usage
===========

Most of the APIs required for basic eventlet usage are exported by the eventlet.api module.

Here are some basic functions that manipulate coroutines.

.. automethod:: eventlet.api::spawn

.. automethod:: eventlet.api::sleep

.. automethod:: eventlet.api::call_after

.. automethod:: eventlet.api::exc_after

Socket Functions
-----------------

.. |socket| replace:: ``socket.socket``
.. _socket: http://docs.python.org/library/socket.html#socket-objects
.. |select| replace:: ``select.select``
.. _select: http://docs.python.org/library/select.html


Eventlet provides convenience functions that return green sockets. The green
socket objects have the same interface as the standard library |socket|_
object, except they will automatically cooperatively yield control to other
eligible coroutines instead of blocking. Eventlet also has the ability to
monkey patch the standard library |socket|_ object so that code which uses
it will also automatically cooperatively yield; see
:ref:`using_standard_library_with_eventlet`.

.. automethod:: eventlet.api::tcp_listener

.. automethod:: eventlet.api::connect_tcp

.. automethod:: eventlet.api::ssl_listener


.. _using_standard_library_with_eventlet:

Using the Standard Library with Eventlet
----------------------------------------

.. automethod:: eventlet.util::wrap_socket_with_coroutine_socket

Eventlet's socket object, whose implementation can be found in the
:mod:`eventlet.greenio` module, is designed to match the interface of the
standard library |socket|_ object. However, it is often useful to be able to
use existing code which uses |socket|_ directly without modifying it to use the
eventlet apis. To do this, one must call
:func:`~eventlet.util.wrap_socket_with_coroutine_socket`. It is only necessary
to do this once, at the beginning of the program, and it should be done before
any socket objects which will be used are created. At some point we may decide
to do this automatically upon import of eventlet; if you have an opinion about
whether this is a good or a bad idea, please let us know.

.. automethod:: eventlet.util::wrap_select_with_coroutine_select

Some code which is written in a multithreaded style may perform some tricks,
such as calling |select|_ with only one file descriptor and a timeout to
prevent the operation from being unbounded. For this specific situation there
is :func:`~eventlet.util.wrap_select_with_coroutine_select`; however it's
always a good idea when trying any new library with eventlet to perform some
tests to ensure eventlet is properly able to multiplex the operations. If you
find a library which appears not to work, please mention it on the mailing list
to find out whether someone has already experienced this and worked around it,
or whether the library needs to be investigated and accommodated. One idea
which could be implemented would add a file mapping between common module names
and corresponding wrapper functions, so that eventlet could automatically
execute monkey patch functions based on the modules that are imported.
