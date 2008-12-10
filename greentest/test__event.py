import unittest
import sys
from eventlet.coros import event, spawn_link
from eventlet.api import spawn, sleep, GreenletExit, exc_after

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


class TestSpawnLink(unittest.TestCase):

    def test_simple_return(self):
        res = spawn_link(lambda: 25).wait()
        assert res==25, res

    def test_exception(self):
        try:
            spawn_link(sys.exit, 'bye').wait()
        except SystemExit, ex:
            assert ex.args == ('bye', )
        else:
            assert False, "Shouldn't get there"

    def _test_kill(self, sync):
        def func():
            sleep(0.1)
            return 101
        res = spawn_link(func)
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
            sleep(0.1)
            return 25
        job = spawn_link(func)
        self.assertEqual(job.poll(), None)
        assert job, repr(job)
        self.assertEqual(job.wait(), 25)
        self.assertEqual(job.poll(), 25)
        assert not job, repr(job)

        job = spawn_link(func)
        self.assertEqual(job.poll(5), 5)
        assert job, repr(job)
        self.assertEqual(job.wait(), 25)
        self.assertEqual(job.poll(5), 25)
        assert not job, repr(job)

    def test_kill_after(self):
        def func():
            sleep(0.1)
            return 25
        job = spawn_link(func)
        job.kill_after(0.05)
        result = job.wait()
        assert isinstance(result, GreenletExit), repr(result)

        job = spawn_link(func)
        job.kill_after(0.2)
        self.assertEqual(job.wait(), 25)
        sleep(0.2)
        self.assertEqual(job.wait(), 25)


if __name__=='__main__':
    unittest.main()
