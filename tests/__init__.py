# Copyright (c) 2008-2009 AG Projects
# Author: Denis Bilenko
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

# package is named tests, not test, so it won't be confused with test in stdlib
import sys
import os
import errno
import unittest


def requires_twisted(func):
    from eventlet.api import get_hub
    if 'Twisted' not in type(get_hub()).__name__:
        try:
            from nose.plugins.skip import SkipTest
            def skipme(*a, **k):
                raise SkipTest()
            skipme.__name__ == func.__name__
            return skipme
        except ImportError:
            # no nose, we'll just skip the test ourselves
            return lambda *a, **k: None
    else:
        return func
        
class LimitedTestCase(unittest.TestCase):

    def setUp(self):
        from eventlet import api
        self.timer = api.exc_after(1, RuntimeError('test is taking too long'))

    def tearDown(self):
        self.timer.cancel()

def find_command(command):
    for dir in os.getenv('PATH', '/usr/bin:/usr/sbin').split(os.pathsep):
        p = os.path.join(dir, command)
        if os.access(p, os.X_OK):
            return p
    raise IOError(errno.ENOENT, 'Command not found: %r' % command)

