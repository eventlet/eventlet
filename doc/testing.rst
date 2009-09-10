Testing Eventlet
================

Eventlet is tested using `Nose <http://somethingaboutorange.com/mrl/projects/nose/>`_.  To run tests, simply install nose, and then, in the eventlet tree, do:

.. code-block:: sh

  $ nosetests

That's it!  The output from running nose is the same as unittest's output, if the entire directory was one big test file.  It tends to emit a lot of tracebacks from a few noisy tests, but they still pass.

Many tests are skipped based on environmental factors; for example, it makes no sense to test Twisted-specific functionality when Twisted is not installed.  These are printed as S's during execution, and in the summary printed after the tests run it will tell you how many were skipped.


Standard Library Tests
----------------------

Eventlet provides for the ability to test itself with the standard Python networking tests.  This verifies that the libraries it wraps work at least as well as the standard ones do.  The directory tests/stdlib contains a bunch of stubs that import the standard lib tests from your system and run them.  If you do not have any tests in your python distribution, they'll simply fail to import.

Run the standard library tests with nose; simply do:

.. code-block:: sh

  $ cd tests/
  $ nosetests stdlib
  
That should get you started.  Note that most of the test failures are caused by `Nose issue 162 <http://code.google.com/p/python-nose/issues/detail?id=162>`_, which incorrectly identifies helper methods as test cases.  Therefore, ignore any failure for the reason ``TypeError: foo() takes exactly N arguments (2 given)``, and sit tight until a version of Nose is released that fixes the issue.