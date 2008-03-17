"""\
@file timer_test.py
@author Donovan Preston

Copyright (c) 2006-2007, Linden Research, Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import unittest

from eventlet import api, runloop, tests, timer

class TestTimer(tests.TestCase):
    mode = 'static'
    def test_copy(self):
        t = timer.Timer(0, lambda: None)
        t2 = t.copy()
        assert t.seconds == t2.seconds
        assert t.tpl == t2.tpl
        assert t.called == t2.called

    def test_cancel(self):
        r = runloop.RunLoop()
        called = []
        t = timer.Timer(0, lambda: called.append(True))
        t.cancel()
        r.add_timer(t)
        r.add_observer(lambda r, activity: r.abort(), 'after_waiting')
        r.run()
        assert not called
        assert not r.running

    def test_schedule(self):
        hub = api.get_hub()
        r = hub.runloop
        # clean up the runloop, preventing side effects from previous tests
        # on this thread
        if r.running:
            r.abort()
            api.sleep(0)
        called = []
        t = timer.Timer(0, lambda: (called.append(True), hub.runloop.abort()))
        t.schedule()
        r.default_sleep = lambda: 0.0
        r.run()
        assert called
        assert not r.running

if __name__ == '__main__':
    unittest.main()
