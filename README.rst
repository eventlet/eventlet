Warning
=======

**New usages of eventlet are now heavily discouraged! Please read the
following.**

Eventlet was created almost 18 years ago, at a time where async
features were absent from the CPython stdlib. With time eventlet evolved and
CPython too, but since several years the maintenance activity of eventlet
decreased leading to a growing gap between eventlet and the CPython
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
cases; see `Migrating off of Eventlet`_. Only new features related to the migration
solution will be accepted.

If you have questions concerning maintenance goals or concerning
the migration do not hesitate to `open a new issue`_, we will be happy to
answer them.

.. _asyncio: https://docs.python.org/3/library/asyncio.html
.. _open a new issue: https://github.com/eventlet/eventlet/issues/new
.. _Migrating off of Eventlet: https://eventlet.readthedocs.io/en/latest/asyncio/migration.html#migration-guide

Eventlet
========

.. image:: https://img.shields.io/pypi/v/eventlet
    :target: https://pypi.org/project/eventlet/

.. image:: https://img.shields.io/github/actions/workflow/status/eventlet/eventlet/test.yaml?branch=master
    :target: https://github.com/eventlet/eventlet/actions?query=workflow%3Atest+branch%3Amaster

.. image:: https://codecov.io/gh/eventlet/eventlet/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/eventlet/eventlet


Eventlet is a concurrent networking library for Python that allows you to change how you run your code, not how you write it.

It uses epoll or libevent for highly scalable non-blocking I/O.  Coroutines ensure that the developer uses a blocking style of programming that is similar to threading, but provide the benefits of non-blocking I/O.  The event dispatch is implicit, which means you can easily use Eventlet from the Python interpreter, or as a small part of a larger application.

It's easy to get started using Eventlet, and easy to convert existing
applications to use it.  Start off by looking at the `examples`_,
`common design patterns`_, and the list of `basic API primitives`_.

.. _examples: https://eventlet.readthedocs.io/en/latest/examples.html
.. _common design patterns: https://eventlet.readthedocs.io/en/latest/design_patterns.html
.. _basic API primitives: https://eventlet.readthedocs.io/en/latest/basic_usage.html


Getting Eventlet
================

The easiest way to get Eventlet is to use pip::

  pip install -U eventlet

To install latest development version once::

  pip install -U https://github.com/eventlet/eventlet/archive/master.zip


Building the Docs Locally
=========================

To build a complete set of HTML documentation::

  tox -e docs

The built html files can be found in doc/build/html afterward.

Supported Python versions
=========================

Python 3.8-3.13 are currently supported.
