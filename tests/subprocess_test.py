import eventlet
from eventlet.green import subprocess
import eventlet.patcher
from nose.plugins.skip import SkipTest
import os
import sys
import time
original_subprocess = eventlet.patcher.original('subprocess')


def test_subprocess_wait():
    # https://bitbucket.org/eventlet/eventlet/issue/89
    # In Python 3.3 subprocess.Popen.wait() method acquired `timeout`
    # argument.
    # RHEL backported it to their Python 2.6 package.
    p = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(0.5)"])
    ok = False
    t1 = time.time()
    try:
        p.wait(timeout=0.1)
    except subprocess.TimeoutExpired:
        ok = True
    tdiff = time.time() - t1
    assert ok == True, 'did not raise subprocess.TimeoutExpired'
    assert 0.1 <= tdiff <= 0.2, 'did not stop within allowed time'


def test_communicate_with_poll():
    # https://github.com/eventlet/eventlet/pull/24
    # `eventlet.green.subprocess.Popen.communicate()` was broken
    # in Python 2.7 because the usage of the `select` module was moved from
    # `_communicate` into two other methods `_communicate_with_select`
    # and `_communicate_with_poll`. Link to 2.7's implementation:
    # http://hg.python.org/cpython/file/2145593d108d/Lib/subprocess.py#l1255
    if getattr(original_subprocess.Popen, '_communicate_with_poll', None) is None:
        raise SkipTest('original subprocess.Popen does not have _communicate_with_poll')

    p = subprocess.Popen(
        [sys.executable, '-c', 'import time; time.sleep(0.5)'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t1 = time.time()
    eventlet.with_timeout(0.1, p.communicate, timeout_value=True)
    tdiff = time.time() - t1
    assert 0.1 <= tdiff <= 0.2, 'did not stop within allowed time'
