# package is named tests, not test, so it won't be confused with test in stdlib
import sys
import os
import errno
import unittest

def skipped(func):
    """ Decorator that marks a function as skipped.  Uses nose's SkipTest exception
    if installed.  Without nose, this will count skipped tests as passing tests."""
    try:
        from nose.plugins.skip import SkipTest
        def skipme(*a, **k):
            raise SkipTest()
        skipme.__name__ = func.__name__
        return skipme
    except ImportError:
        # no nose, we'll just skip the test ourselves
        def skipme(*a, **k):
            print "Skipping", func.__name__
        skipme.__name__ = func.__name__
        return skipme


def skip_unless_requirement(requirement):
    """ Decorator that skips a test if the *requirement* does not return True.
    *requirement* is a callable that accepts one argument, the function to be decorated, 
    and returns True if the requirement is satisfied.
    """
    def skipped_wrapper(func):        
        if not requirement(func):
            return skipped(func)
        else:
            return func
    return skipped_wrapper


def requires_twisted(func):
    """ Decorator that skips a test if Twisted is not present."""
    def requirement(_f):
        from eventlet.api import get_hub
        try:
            return 'Twisted' in type(get_hub()).__name__
        except Exception:
            return False
    return skip_unless_requirement(requirement)(func)
    
    
def skip_with_libevent(func):
    """ Decorator that skips a test if we're using the libevent hub."""
    def requirement(_f):
        from eventlet.api import get_hub
        return not('libevent' in type(get_hub()).__module__)
    return skip_unless_requirement(requirement)(func)


class TestIsTakingTooLong(Exception):
    """ Custom exception class to be raised when a test's runtime exceeds a limit. """
    pass


class LimitedTestCase(unittest.TestCase):
    """ Unittest subclass that adds a timeout to all tests.  Subclasses must
    be sure to call the LimitedTestCase setUp and tearDown methods.  The default 
    timeout is 1 second, change it by setting self.TEST_TIMEOUT to the desired
    quantity."""
    
    TEST_TIMEOUT = 1
    def setUp(self):
        from eventlet import api
        self.timer = api.exc_after(self.TEST_TIMEOUT, 
                                   TestIsTakingTooLong(self.TEST_TIMEOUT))

    def tearDown(self):
        self.timer.cancel()


def find_command(command):
    for dir in os.getenv('PATH', '/usr/bin:/usr/sbin').split(os.pathsep):
        p = os.path.join(dir, command)
        if os.access(p, os.X_OK):
            return p
    raise IOError(errno.ENOENT, 'Command not found: %r' % command)

