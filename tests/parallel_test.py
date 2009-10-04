from eventlet import api, parallel
import unittest

class Spawn(unittest.TestCase):
    def test_simple(self):
        def f(a, b=None):
            return (a,b)
        
        coro = parallel.spawn(f, 1, b=2)
        self.assertEquals(coro.wait(), (1,2))

def passthru(a):
    api.sleep(0.01)
    return a
        
class Parallel(unittest.TestCase):
    def test_parallel(self):
        p = parallel.Parallel(4)
        for i in xrange(10):
            p.spawn(passthru, i)
        result_list = list(p.results())
        self.assertEquals(result_list, range(10))
        
    def test_spawn_all(self):
        p = parallel.Parallel(4)
        result_list = list(p.spawn_all(passthru, xrange(10)))
        self.assertEquals(result_list, range(10))
