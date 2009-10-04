from eventlet import api, parallel
import unittest

class Spawn(unittest.TestCase):
    def test_simple(self):
        def f(a, b=None):
            return (a,b)
        
        coro = parallel.spawn(f, 1, b=2)
        self.assertEquals(coro.wait(), (1,2))
        
class Parallel(unittest.TestCase):
    def test_parallel(self):
        def f(a):
            api.sleep(0.01)
            return a
        p = parallel.Parallel(4)
        for i in xrange(10):
            p.spawn(f, i)
        result_list = list(p.results())
        self.assertEquals(result_list, range(10))