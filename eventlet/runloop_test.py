"""\
@file runloop_test.py
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

import sys
import time
import StringIO
import unittest

from eventlet import runloop


class TestRunloop(unittest.TestCase):
    mode = 'static'
    def test_empty(self):
        r = runloop.RunLoop()
        r.schedule_call(0, r.abort)
        r.run()
        assert not r.running


    def test_timer(self):
        r = runloop.RunLoop()
        r.schedule_call(0.125, r.abort)
        start_time = time.time()
        r.run()
        assert time.time() - start_time >= 0.125
        assert not r.running

    def test_observer(self):
        observed = []
        r = runloop.RunLoop()
        r.add_observer(lambda runloop, activity: observed.append(activity))
        r.schedule_call(0, r.abort)
        r.run()
        assert observed == ['entry', 'before_timers', 'before_waiting', 'after_waiting', 'exit']
        assert not r.running


    def test_remove_observer(self):
        r = runloop.RunLoop()

        observed = []
        def observe(runloop, mode):
            observed.append(mode)
            r.remove_observer(observe)

        looped = []
        def run_loop_twice(runloop, mode):
            if looped:
                r.abort()
            else:
                looped.append(True)

        r.add_observer(observe, 'before_timers')
        r.add_observer(run_loop_twice, 'after_waiting')
        r.run()
        assert len(observed) == 1
        assert not r.running

    def test_observer_exception(self):
        r = runloop.RunLoop()

        observed = []
        def observe(runloop, mode):
            observed.append(mode)
            raise Exception("Squelch me please")

        looped = []
        def run_loop_twice(runloop, mode):
            if looped:
                r.abort()
            else:
                looped.append(True)

        saved = sys.stderr
        sys.stderr = err = StringIO.StringIO()

        r.add_observer(observe, 'before_timers')
        r.add_observer(run_loop_twice, 'after_waiting')
        r.run()

        err.seek(0)
        sys.stderr = saved

        assert len(observed) == 1
        assert err.read()
        assert not r.running

    def test_timer_exception(self):
        r = runloop.RunLoop()

        observed = []
        def timer():
            observed.append(True)
            raise Exception("Squelch me please")

        looped = []
        def run_loop_twice(runloop, mode):
            if looped:
                r.abort()
            else:
                looped.append(True)

        saved = sys.stderr
        sys.stderr = err = StringIO.StringIO()

        r.schedule_call(0, timer)
        r.add_observer(run_loop_twice, 'after_waiting')
        r.run()

        err.seek(0)
        sys.stderr = saved

        assert len(observed) == 1
        assert err.read()
        assert not r.running

    def test_timer_system_exception(self):
        r = runloop.RunLoop()
        def timer():
            raise SystemExit

        r.schedule_call(0, timer)

        caught = []
        try:
            r.run()
        except SystemExit:
            caught.append(True)

        assert caught
        assert not r.running

if __name__ == '__main__':
    unittest.main()

