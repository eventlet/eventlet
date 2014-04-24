# package is named tests, not test, so it won't be confused with test in stdlib
from __future__ import print_function

import errno
import gc
import os
try:
    import resource
except ImportError:
    resource = None
import signal
import subprocess
import sys
import unittest
import warnings

import eventlet
from eventlet import tpool


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
            print(("Skipping {0}".format(func.__name__)))
        skipme.__name__ = func.__name__
        return skipme


def skip_if(condition):
    """ Decorator that skips a test if the *condition* evaluates True.
    *condition* can be a boolean or a callable that accepts one argument.
    The callable will be called with the function to be decorated, and
    should return True to skip the test.
    """
    def skipped_wrapper(func):
        def wrapped(*a, **kw):
            if isinstance(condition, bool):
                result = condition
            else:
                result = condition(func)
            if result:
                return skipped(func)(*a, **kw)
            else:
                return func(*a, **kw)
        wrapped.__name__ = func.__name__
        return wrapped
    return skipped_wrapper


def skip_unless(condition):
    """ Decorator that skips a test if the *condition* does not return True.
    *condition* can be a boolean or a callable that accepts one argument.
    The callable will be called with the  function to be decorated, and
    should return True if the condition is satisfied.
    """
    def skipped_wrapper(func):
        def wrapped(*a, **kw):
            if isinstance(condition, bool):
                result = condition
            else:
                result = condition(func)
            if not result:
                return skipped(func)(*a, **kw)
            else:
                return func(*a, **kw)
        wrapped.__name__ = func.__name__
        return wrapped
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
    return skip_if(sys.platform.startswith('win'))(func)


def skip_if_no_itimer(func):
    """ Decorator that skips a test if the `itimer` module isn't found """
    has_itimer = False
    try:
        import itimer
        has_itimer = True
    except ImportError:
        pass
    return skip_unless(has_itimer)(func)


def skip_if_no_ssl(func):
    """ Decorator that skips a test if SSL is not available."""
    try:
        import eventlet.green.ssl
        return func
    except ImportError:
        try:
            import eventlet.green.OpenSSL
            return func
        except ImportError:
            return skipped(func)


class TestIsTakingTooLong(Exception):
    """ Custom exception class to be raised when a test's runtime exceeds a limit. """
    pass


class LimitedTestCase(unittest.TestCase):
    """ Unittest subclass that adds a timeout to all tests.  Subclasses must
    be sure to call the LimitedTestCase setUp and tearDown methods.  The default
    timeout is 1 second, change it by setting TEST_TIMEOUT to the desired
    quantity."""

    TEST_TIMEOUT = 1

    def setUp(self):
        self.previous_alarm = None
        self.timer = eventlet.Timeout(self.TEST_TIMEOUT,
                                      TestIsTakingTooLong(self.TEST_TIMEOUT))

    def reset_timeout(self, new_timeout):
        """Changes the timeout duration; only has effect during one test.
        `new_timeout` can be int or float.
        """
        self.timer.cancel()
        self.timer = eventlet.Timeout(new_timeout,
                                      TestIsTakingTooLong(new_timeout))

    def set_alarm(self, new_timeout):
        """Call this in the beginning of your test if you expect busy loops.
        Only has effect during one test.
        `new_timeout` must be int.
        """
        def sig_alarm_handler(sig, frame):
            # Could arm previous alarm but test is failed anyway
            # seems to be no point in restoring previous state.
            raise TestIsTakingTooLong(new_timeout)

        self.previous_alarm = (
            signal.signal(signal.SIGALRM, sig_alarm_handler),
            signal.alarm(new_timeout),
        )

    def tearDown(self):
        self.timer.cancel()
        if self.previous_alarm:
            signal.signal(signal.SIGALRM, self.previous_alarm[0])
            signal.alarm(self.previous_alarm[1])

        tpool.killall()
        gc.collect()
        eventlet.sleep(0)
        verify_hub_empty()

    def assert_less_than(self, a, b, msg=None):
        if msg:
            self.assert_(a < b, msg)
        else:
            self.assert_(a < b, "%s not less than %s" % (a, b))

    assertLessThan = assert_less_than

    def assert_less_than_equal(self, a, b, msg=None):
        if msg:
            self.assert_(a <= b, msg)
        else:
            self.assert_(a <= b, "%s not less than or equal to %s" % (a, b))

    assertLessThanEqual = assert_less_than_equal


def check_idle_cpu_usage(duration, allowed_part):
    if resource is None:
        # TODO: use https://code.google.com/p/psutil/
        from nose.plugins.skip import SkipTest
        raise SkipTest('CPU usage testing not supported (`import resource` failed)')

    r1 = resource.getrusage(resource.RUSAGE_SELF)
    eventlet.sleep(duration)
    r2 = resource.getrusage(resource.RUSAGE_SELF)
    utime = r2.ru_utime - r1.ru_utime
    stime = r2.ru_stime - r1.ru_stime
    assert utime + stime < duration * allowed_part, \
        "CPU usage over limit: user %.0f%% sys %.0f%% allowed %.0f%%" % (
            utime / duration * 100, stime / duration * 100,
            allowed_part * 100)


def verify_hub_empty():
    from eventlet import hubs
    hub = hubs.get_hub()
    num_readers = len(hub.get_readers())
    num_writers = len(hub.get_writers())
    num_timers = hub.get_timers_count()
    assert num_readers == 0 and num_writers == 0, "Readers: %s Writers: %s" % (num_readers, num_writers)


def find_command(command):
    for dir in os.getenv('PATH', '/usr/bin:/usr/sbin').split(os.pathsep):
        p = os.path.join(dir, command)
        if os.access(p, os.X_OK):
            return p
    raise IOError(errno.ENOENT, 'Command not found: %r' % command)


def silence_warnings(func):
    def wrapper(*args, **kw):
        warnings.simplefilter('ignore', DeprecationWarning)
        try:
            return func(*args, **kw)
        finally:
            warnings.simplefilter('default', DeprecationWarning)
    wrapper.__name__ = func.__name__
    return wrapper


def get_database_auth():
    """Retrieves a dict of connection parameters for connecting to test databases.

    Authentication parameters are highly-machine specific, so
    get_database_auth gets its information from either environment
    variables or a config file.  The environment variable is
    "EVENTLET_DB_TEST_AUTH" and it should contain a json object.  If
    this environment variable is present, it's used and config files
    are ignored.  If it's not present, it looks in the local directory
    (tests) and in the user's home directory for a file named
    ".test_dbauth", which contains a json map of parameters to the
    connect function.
    """
    import os
    retval = {
        'MySQLdb': {'host': 'localhost', 'user': 'root', 'passwd': ''},
        'psycopg2': {'user': 'test'},
    }
    try:
        import json
    except ImportError:
        try:
            import simplejson as json
        except ImportError:
            print("No json implementation, using baked-in db credentials.")
            return retval

    if 'EVENTLET_DB_TEST_AUTH' in os.environ:
        return json.loads(os.environ.get('EVENTLET_DB_TEST_AUTH'))

    files = [os.path.join(os.path.dirname(__file__), '.test_dbauth'),
             os.path.join(os.path.expanduser('~'), '.test_dbauth')]
    for f in files:
        try:
            auth_utf8 = json.load(open(f))
            # Have to convert unicode objects to str objects because
            # mysqldb is dum. Using a doubly-nested list comprehension
            # because we know that the structure is a two-level dict.
            return dict(
                [(str(modname), dict(
                    [(str(k), str(v)) for k, v in connectargs.items()]))
                 for modname, connectargs in auth_utf8.items()])
        except IOError:
            pass
    return retval


def run_python(path):
    if not path.endswith('.py'):
        path += '.py'
    path = os.path.abspath(path)
    dir_ = os.path.dirname(path)
    new_env = os.environ.copy()
    new_env['PYTHONPATH'] = os.pathsep.join(sys.path + [dir_])
    p = subprocess.Popen(
        [sys.executable, path],
        env=new_env,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    output, _ = p.communicate()
    return output


certificate_file = os.path.join(os.path.dirname(__file__), 'test_server.crt')
private_key_file = os.path.join(os.path.dirname(__file__), 'test_server.key')
