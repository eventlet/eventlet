# package is named tests, not test, so it won't be confused with test in stdlib
import sys
import os
import errno
import unittest

# convenience for importers
main = unittest.main

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


def skip_if(condition):
    """ Decorator that skips a test if the *condition* evaluates True.
    *condition* can be a boolean or a callable that accepts one argument.
    The callable will be called with the function to be decorated, and 
    should return True to skip the test.
    """
    def skipped_wrapper(func):
        if isinstance(condition, bool):
            result = condition
        else:
            result = condition(func)
        if result:
            return skipped(func)
        else:
            return func
    return skipped_wrapper


def skip_unless(condition):
    """ Decorator that skips a test if the *condition* does not return True.
    *condition* can be a boolean or a callable that accepts one argument.
    The callable will be called with the  function to be decorated, and 
    should return True if the condition is satisfied.
    """    
    def skipped_wrapper(func):
        if isinstance(condition, bool):
            result = condition
        else:
            result = condition(func)
        if not result:
            return skipped(func)
        else:
            return func
    return skipped_wrapper


def requires_twisted(func):
    """ Decorator that skips a test if Twisted is not present."""
    def requirement(_f):
        from eventlet.hubs import get_hub
        try:
            return 'Twisted' in type(get_hub()).__name__
        except Exception:
            return False
    return skip_unless(requirement)(func)
    

def using_pyevent(_f):
    from eventlet.hubs import get_hub
    return 'pyevent' in type(get_hub()).__module__
    
def skip_with_pyevent(func):
    """ Decorator that skips a test if we're using the pyevent hub."""
    return skip_if(using_pyevent)(func)


def skip_on_windows(func):
    """ Decorator that skips a test on Windows."""
    import sys
    return skip_if(sys.platform.startswith('win'))(func)


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
        import eventlet
        self.timer = eventlet.Timeout(self.TEST_TIMEOUT, 
                                      TestIsTakingTooLong(self.TEST_TIMEOUT))

    def tearDown(self):
        self.timer.cancel()


def verify_hub_empty():
    from eventlet import hubs
    hub = hubs.get_hub()
    num_readers = len(hub.get_readers())
    num_writers = len(hub.get_writers())
    num_timers = len(hub.get_timers_count())
    assert num_readers == 0 and num_writers == 0, "Readers: %s Writers: %s" % (num_readers, num_writers)


def find_command(command):
    for dir in os.getenv('PATH', '/usr/bin:/usr/sbin').split(os.pathsep):
        p = os.path.join(dir, command)
        if os.access(p, os.X_OK):
            return p
    raise IOError(errno.ENOENT, 'Command not found: %r' % command)

