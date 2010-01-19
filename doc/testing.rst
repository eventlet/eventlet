Testing Eventlet
================

Eventlet is tested using `Nose <http://somethingaboutorange.com/mrl/projects/nose/>`_.  To run tests, simply install nose, and then, in the eventlet tree, do:

.. code-block:: sh

  $ python setup.py test
  
If you want access to all the nose plugins via command line, you can run:

.. code-block:: sh

  $ python setup.py nosetests

Lastly, you can just use nose directly if you want:

.. code-block:: sh

  $ nosetests

That's it!  The output from running nose is the same as unittest's output, if the entire directory was one big test file.  It tends to emit a lot of tracebacks from a few noisy tests, but they still pass.

Many tests are skipped based on environmental factors; for example, it makes no sense to test Twisted-specific functionality when Twisted is not installed.  These are printed as S's during execution, and in the summary printed after the tests run it will tell you how many were skipped.

Doctests
--------

To run the doctests included in many of the eventlet modules, use this command:

.. code-block :: sh

  $ nosetests --with-doctest eventlet/*.py
  
Currently there are 14 doctests.

Standard Library Tests
----------------------

Eventlet provides for the ability to test itself with the standard Python networking tests.  This verifies that the libraries it wraps work at least as well as the standard ones do.  The directory tests/stdlib contains a bunch of stubs that import the standard lib tests from your system and run them.  If you do not have any tests in your python distribution, they'll simply fail to import.

There's a convenience module called all.py designed to handle the impedance mismatch between Nose and the standard tests:

.. code-block:: sh

  $ nosetests tests/stdlib/all.py
  
That will run all the tests, though the output will be a little weird because it will look like Nose is running about 20 tests, each of which consists of a bunch of sub-tests.  Not all test modules are present in all versions of Python, so there will be an occasional printout of "Not importing %s, it doesn't exist in this installation/version of Python".


Testing Eventlet Hubs
---------------------

When you run the tests, Eventlet will use the most appropriate hub for the current platform to do its dispatch.  It's sometimes useful when making changes to Eventlet to test those changes on hubs other than the default.  You can do this with the eventlethub nose plugin.  The plugin is not installed in your system, so in order to get Nose to see it, we have to call a wrapper script instead of Nose:

.. code-block:: sh

 $ python tests/nosewrapper.py --with-eventlethub --hub=selects
 
``nosewrapper.py`` takes exactly the same arguments as nosetests, and behaves exactly the same way.  Here's what the two arguments mean:

* ``--with-eventlethub`` enables the eventlethub plugin.
* ``--hub=HUB`` specifies which Eventlet hub to use during the tests.

If you wish to run tests against a particular Twisted reactor, use ``--reactor=REACTOR`` instead of ``--hub``.  The full list of eventlet hubs is currently:

* poll
* selects
* pyevent  (requires pyevent installed on your system)

Writing Tests
-------------

What follows are some notes on writing tests, in no particular order.

The filename convention when writing a test for module `foo` is to name the test `foo_test.py`.  We don't yet have a convention for tests that are of finer granularity, but a sensible one might be `foo_class_test.py`.

If you are writing a test that involves a client connecting to a spawned server, it is best to not use a hardcoded port because that makes it harder to parallelize tests.  Instead bind the server to 0, and then look up its port when connecting the client, like this::

  server_sock = api.tcp_listener(('127.0.0.1', 0))
  client_sock = api.connect_tcp(('localhost', server_sock.getsockname()[1]))
  
Coverage
--------

Coverage.py is an awesome tool for evaluating how much code was exercised by unit tests.  Nose supports it if both are installed, so it's easy to generate coverage reports for eventlet.  Here's how:

.. code-block:: sh

 nosetests --with-coverage --cover-package=eventlet
 
After running the tests to completion, this will emit a huge wodge of module names and line numbers.  For some reason, the ``--cover-inclusive`` option breaks everything rather than serving its purpose of limiting the coverage to the local files, so don't use that.

The annotate option is quite useful because it generates annotated source files that are much easier to read than line-number soup.  Here's a command that runs the annotation, dumping the annotated files into a directory called "annotated":

.. code-block:: sh

 coverage annotate -d annotated --omit='tempmod,<console>'
 
(``tempmod`` and ``console`` are omitted because they gets thrown away at the completion of their unit tests and coverage.py isn't smart enough to detect this)