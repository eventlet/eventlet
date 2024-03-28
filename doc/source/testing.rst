.. _testing-eventlet:

Testing Eventlet
================

Eventlet is tested using `Pytest <https://pytest/>`_.  To run tests, simply install pytest, and then, in the eventlet tree, do:

.. code-block:: sh

  $ pytest

That's it!

Many tests are skipped based on environmental factors; for example, it makes no sense to test kqueue-specific functionality when your OS does not support it.  These are printed as S's during execution, and in the summary printed after the tests run it will tell you how many were skipped.

Doctests
--------

To run the doctests included in many of the eventlet modules, use this command:

.. code-block :: sh

  $ pytest --doctest-modules eventlet/

The doctests currently `do not pass <https://github.com/eventlet/eventlet/issues/837>`_.


Testing Eventlet Hubs
---------------------

When you run the tests, Eventlet will use the most appropriate hub for the current platform to do its dispatch.  It's sometimes useful when making changes to Eventlet to test those changes on hubs other than the default.  You can do this with the ``EVENTLET_HUB`` environment variable.

.. code-block:: sh

 $ EVENTLET_HUB=epolls pytest

See :ref:`understanding_hubs` for the full list of hubs.


Writing Tests
-------------

What follows are some notes on writing tests, in no particular order.

The filename convention when writing a test for module `foo` is to name the test `foo_test.py`.  We don't yet have a convention for tests that are of finer granularity, but a sensible one might be `foo_class_test.py`.

If you are writing a test that involves a client connecting to a spawned server, it is best to not use a hardcoded port because that makes it harder to parallelize tests.  Instead bind the server to 0, and then look up its port when connecting the client, like this::

  server_sock = eventlet.listener(('127.0.0.1', 0))
  client_sock = eventlet.connect(('localhost', server_sock.getsockname()[1]))

Coverage
--------

Coverage.py is an awesome tool for evaluating how much code was exercised by unit tests.  pytest supports it pytest-cov is installed, so it's easy to generate coverage reports for eventlet.  Here's how:

.. code-block:: sh

 pytest --cov=eventlet

After running the tests to completion, this will emit a huge wodge of module names and line numbers.  For some reason, the ``--cover-inclusive`` option breaks everything rather than serving its purpose of limiting the coverage to the local files, so don't use that.

The html option is quite useful because it generates nicely-formatted HTML files that are much easier to read than line-number soup.  Here's a command that generates the annotation, dumping the html files into a directory called "cover":

.. code-block:: sh

  coverage html -d cover --omit='tempmod,<console>,tests'

(``tempmod`` and ``console`` are omitted because they get thrown away at the completion of their unit tests and coverage.py isn't smart enough to detect this.)
