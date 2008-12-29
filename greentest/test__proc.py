from __future__ import with_statement
import sys
from twisted.internet import reactor
import unittest
from eventlet.api import sleep, timeout
from eventlet import proc, coros

DELAY= 0.001

class TestCase(unittest.TestCase):

    def link(self, p, listener=None):
        getattr(p, self.link_method)(listener)

    def tearDown(self):
        self.p.unlink()

    def set_links(self, p, first_time, kill_exc_type):
        event = coros.event()
        self.link(p, event)

        proc_flag = []
        def receiver():
            sleep(DELAY)
            proc_flag.append('finished')
        receiver = proc.spawn(receiver)
        self.link(p, receiver)

        queue = coros.queue(1)
        self.link(p, queue)

        try:
            self.link(p)
        except kill_exc_type:
            if first_time:
                raise
        else:
            assert first_time, 'not raising here only first time'

        callback_flag = ['initial']
        self.link(p, lambda *args: callback_flag.remove('initial'))

        for _ in range(10):
            self.link(p, coros.event())
            self.link(p, coros.queue(1))
        return event, receiver, proc_flag, queue, callback_flag

    def set_links_timeout(self, link):
        # stuff that won't be touched
        event = coros.event()
        link(event)

        proc_finished_flag = []
        def myproc():
            sleep(10)
            proc_finished_flag.append('finished')
            return 555
        myproc = proc.spawn(myproc)
        link(myproc)

        queue = coros.queue(0)
        link(queue)
        return event, myproc, proc_finished_flag, queue

    def check_timed_out(self, event, myproc, proc_finished_flag, queue):
        with timeout(DELAY, None):
            event.wait()
            raise AssertionError('should not get there')

        with timeout(DELAY, None):
            queue.wait()
            raise AssertionError('should not get there')

        with timeout(DELAY, None):
            print repr(proc.wait(myproc))
            raise AssertionError('should not get there')
        assert proc_finished_flag == [], proc_finished_flag


class TestReturn_link(TestCase):
    link_method = 'link'

    def test_kill(self):
        p = self.p = proc.spawn(sleep, DELAY)
        self._test_return(p, True, proc.ProcKilled, proc.LinkedKilled, p.kill)
        # repeating the same with dead process
        for _ in xrange(3):
            self._test_return(p, False, proc.ProcKilled, proc.LinkedKilled, p.kill)

    def test_return(self):
        p = self.p = proc.spawn(lambda : 25)
        self._test_return(p, True, int, proc.LinkedCompleted, lambda : sleep(0))
        # repeating the same with dead process
        for _ in xrange(3):
            self._test_return(p, False, int, proc.LinkedCompleted, lambda : sleep(0))

    def _test_return(self, p, first_time, result_type, kill_exc_type, action):
        event, receiver, proc_flag, queue, callback_flag = self.set_links(p, first_time, kill_exc_type)

        # stuff that will time out because there's no unhandled exception:
        #link_raise_event, link_raise_receiver, link_raise_flag, link_raise_queue = self.set_links_timeout(p.link_raise)
        xxxxx = self.set_links_timeout(p.link_raise)

        action()
        try:
            sleep(DELAY)
        except kill_exc_type:
             assert first_time, 'raising here only first time'
        else:
            assert not first_time, 'Should not raise LinkedKilled here after first time'

        assert not p, p
        
        with timeout(DELAY):
            event_result = event.wait()
            queue_result = queue.wait()
            proc_result = proc.wait(receiver)

        assert isinstance(event_result, result_type), repr(event_result)
        assert isinstance(proc_result, kill_exc_type), repr(proc_result)
        sleep(DELAY)
        assert not proc_flag, proc_flag
        assert not callback_flag, callback_flag

        self.check_timed_out(*xxxxx)

class TestReturn_link_return(TestReturn_link):
    sync = False
    link_method = 'link_return'


class TestRaise_link(TestCase):
    link_method = 'link'

    def _test_raise(self, p, first_time, kill_exc_type=proc.LinkedFailed):
        event, receiver, proc_flag, queue, callback_flag = self.set_links(p, first_time, kill_exc_type)
        xxxxx = self.set_links_timeout(p.link_return)

        try:
            sleep(DELAY)
        except kill_exc_type:
             assert first_time, 'raising here only first time'
        else:
            assert not first_time, 'Should not raise LinkedKilled here after first time'

        assert not p, p

        with timeout(DELAY):
            self.assertRaises(ValueError, event.wait)
            self.assertRaises(ValueError, queue.wait)
            proc_result = proc.wait(receiver)

        assert isinstance(proc_result, kill_exc_type), repr(proc_result)
        sleep(DELAY)
        assert not proc_flag, proc_flag
        assert not callback_flag, callback_flag

        self.check_timed_out(*xxxxx)

    def test_raise(self):
        p = self.p = proc.spawn(int, 'badint')
        self._test_raise(p, True)
        # repeating the same with dead process
        for _ in xrange(3):
            self._test_raise(p, False)

class TestRaise_link_raise(TestCase):
    link_method = 'link_raise'


class TestStuff(unittest.TestCase):

    def test_wait_noerrors(self):
        x = proc.spawn(lambda : 1)
        y = proc.spawn(lambda : 2)
        z = proc.spawn(lambda : 3)
        self.assertEqual(proc.wait([x, y, z]), [1, 2, 3])
        self.assertEqual([proc.wait(X) for X in [x, y, z]], [1, 2, 3])

    def test_wait_error(self):
        def x():
            sleep(DELAY)
            return 1
        x = proc.spawn(x)
        z = proc.spawn(lambda : 3)
        y = proc.spawn(int, 'badint')
        y.link(x)
        x.link(y)
        y.link(z)
        z.link(y)
        self.assertRaises(ValueError, proc.wait, [x, y, z])
        assert isinstance(proc.wait(x), proc.LinkedFailed), repr(proc.wait(x))
        self.assertEqual(proc.wait(z), 3)
        self.assertRaises(ValueError, proc.wait, y)

    def test_wait_all_exception_order(self):
        # if there're several exceptions raised, the earliest one must be raised by wait
        def badint():
            sleep(0.1)
            int('first')
        a = proc.spawn(badint)
        b = proc.spawn(int, 'second')
        try:
            proc.wait([a, b])
        except ValueError, ex:
            assert 'second' in str(ex), repr(str(ex))

    def test_multiple_listeners_error(self):
        # if there was an error while calling a callback
        # it should not prevent the other listeners from being called 
        # (but all of them should be logged, check the output that they are)
        p = proc.spawn(lambda : 5)
        results = []
        def listener1(*args):
            results.append(10)
            1/0
        def listener2(*args):
            results.append(20)
            2/0
        def listener3(*args):
            3/0
        p.link(listener1)
        p.link(listener2)
        p.link(listener3)
        sleep(DELAY*3)
        assert results in [[10, 20], [20, 10]], results

        p = proc.spawn(int, 'hello')
        results = []
        p.link(listener1)
        p.link(listener2)
        p.link(listener3)
        sleep(DELAY*3)
        assert results in [[10, 20], [20, 10]], results

    def test_multiple_listeners_error_unlink(self):
        p = proc.spawn(lambda : 5)
        results = []
        def listener1(*args):
            results.append(5)
            1/0
        def listener2(*args):
            results.append(5)
            2/0
        def listener3(*args):
            3/0
        p.link(listener1)
        p.link(listener2)
        p.link(listener3)
        sleep(0)
        # unlink one that is not fired yet
        if listener1 in p._receivers:
            p.unlink(listener1)
        elif listener2 in p._receivers:
            p.unlink(listener2)
        sleep(DELAY*3)
        assert results == [5], results

    def FAILING_test_killing_unlinked(self):
        e = coros.event()
        def func():
            try:
                1/0
            except:
                e.send_exception(*sys.exc_info())
        p = proc.spawn_link(func)
        try:
            e.wait()
        except ZeroDivisionError:
            pass
        finally:
            p.unlink()
        sleep(DELAY)


funcs_only_1arg = [lambda x: None,
                   lambda x=1: None]

funcs_only_3args = [lambda x, y, z: None,
                    lambda x, y, z=1: None]

funcs_any_arg = [lambda a, b=1, c=1: None,
                 lambda *args: None]

class TestCallbackTypeErrors(unittest.TestCase):

    def test(self):
        p = proc.spawn(lambda : None)
        for func in funcs_only_1arg:
            p.link_return(func)
            self.assertRaises(TypeError, p.link_raise, func)
            self.assertRaises(TypeError, p.link, func)
        for func in funcs_only_3args:
            p.link_raise(func)
            self.assertRaises(TypeError, p.link_return, func)
            self.assertRaises(TypeError, p.link, func)
        for func in funcs_any_arg:
            p.link_raise(func)
            p.link_return(func)
            p.link(func)

if __name__=='__main__':
    unittest.main()
