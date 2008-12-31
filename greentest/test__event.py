# Copyright (c) 2008 Denis Bilenko
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

from __future__ import with_statement
import unittest
import sys
from eventlet.coros import event, Job, JobGroup
from eventlet.api import spawn, sleep, GreenletExit, exc_after, timeout

DELAY= 0.01

class TestEvent(unittest.TestCase):
    
    def test_send_exc(self):
        log = []
        e = event()

        def waiter():
            try:
                result = e.wait()
                log.append(('received', result))
            except Exception, ex:
                log.append(('catched', type(ex).__name__))
        spawn(waiter)
        sleep(0) # let waiter to block on e.wait()
        e.send(exc=Exception())
        sleep(0)
        assert log == [('catched', 'Exception')], log

    def test_send(self):
        event1 = event()
        event2 = event()

        spawn(event1.send, 'hello event1')
        exc_after(0, ValueError('interrupted'))
        try:
            result = event1.wait()
        except ValueError:
            with timeout(DELAY, None):
                result = event2.wait()
                raise AssertionError('Nobody sent anything to event2 yet it received %r' % (result, ))

class CommonJobTests:

    def test_simple_return(self):
        res = self.Job.spawn_new(lambda: 25).wait()
        assert res==25, res

    def test_exception(self):
        try:
            self.Job.spawn_new(sys.exit, 'bye').wait()
        except SystemExit, ex:
            assert ex.args == ('bye', )
        else:
            assert False, "Shouldn't get there"

    def _test_kill(self, sync):
        def func():
            sleep(DELAY)
            return 101
        res = self.Job.spawn_new(func)
        assert res
        if sync:
            res.kill()
        else:
            spawn(res.kill)
        wait_result = res.wait()
        assert not res, repr(res)
        assert isinstance(wait_result, GreenletExit), repr(wait_result)

    def test_kill_sync(self):
        return self._test_kill(True)

    def test_kill_async(self):
        return self._test_kill(False)

    def test_poll(self):
        def func():
            sleep(DELAY)
            return 25
        job = self.Job.spawn_new(func)
        self.assertEqual(job.poll(), None)
        assert job, repr(job)
        self.assertEqual(job.wait(), 25)
        self.assertEqual(job.poll(), 25)
        assert not job, repr(job)

        job = self.Job.spawn_new(func)
        self.assertEqual(job.poll(5), 5)
        assert job, repr(job)
        self.assertEqual(job.wait(), 25)
        self.assertEqual(job.poll(5), 25)
        assert not job, repr(job)

    def test_kill_after(self):
        def func():
            sleep(DELAY)
            return 25
        job = self.Job.spawn_new(func)
        job.kill_after(DELAY/2)
        result = job.wait()
        assert isinstance(result, GreenletExit), repr(result)

        job = self.Job.spawn_new(func)
        job.kill_after(DELAY*2)
        self.assertEqual(job.wait(), 25)
        sleep(DELAY*2)
        self.assertEqual(job.wait(), 25)

class TestJob(CommonJobTests, unittest.TestCase):

    def setUp(self):
        self.Job = Job

class TestJobGroup(CommonJobTests, unittest.TestCase):

    def setUp(self):
        self.Job = JobGroup()

    def tearDown(self):
        del self.Job

    def check_raises_badint(self, wait):
        try:
            wait()
        except ValueError, ex:
            assert 'badint' in str(ex), str(ex)
        else:
            raise AssertionError('must raise ValueError')

    def check_killed(self, wait, text=''):
        result = wait()
        assert isinstance(result, GreenletExit), repr(result)
        assert str(result) == text, str(result)

    def test_group_error(self):
        x = self.Job.spawn_new(int, 'badint')
        y = self.Job.spawn_new(sleep, DELAY)
        self.check_killed(y.wait, 'Killed because of ValueError in the group')
        self.check_raises_badint(x.wait)
        z = self.Job.spawn_new(sleep, DELAY)
        self.check_killed(z.wait, 'Killed because of ValueError in the group')

    def test_wait_all(self):
        x = self.Job.spawn_new(lambda : 1)
        y = self.Job.spawn_new(lambda : 2)
        z = self.Job.spawn_new(lambda : 3)
        assert self.Job.wait_all() == [1, 2, 3], repr(self.Job.wait_all())
        assert [x.wait(), y.wait(), z.wait()] == [1, 2, 3], [x.wait(), y.wait(), z.wait()]

    def test_error_wait_all(self):
        def x():
            sleep(DELAY)
            return 1
        # x will be killed
        x = self.Job.spawn_new(x)
        # y will raise ValueError
        y = self.Job.spawn_new(int, 'badint')
        # z cannot be killed because it does not yield. it will finish successfully
        z = self.Job.spawn_new(lambda : 3)
        self.check_raises_badint(self.Job.wait_all) 
        self.check_killed(x.poll, 'Killed because of ValueError in the group')
        self.check_killed(x.wait, 'Killed because of ValueError in the group')
        assert z.wait() == 3, repr(z.wait())
        self.check_raises_badint(y.wait)

        # zz won't be even started, because there's already an error in the group
        zz = self.Job.spawn_new(lambda : 4)
        self.check_killed(x.poll, 'Killed because of ValueError in the group')
        self.check_killed(x.wait, 'Killed because of ValueError in the group')

if __name__=='__main__':
    unittest.main()
