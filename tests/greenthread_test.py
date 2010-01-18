from tests import LimitedTestCase
from eventlet import greenthread
from eventlet.support import greenlets as greenlet

_g_results = []
def passthru(*args, **kw):
    _g_results.append((args, kw))
    return args, kw

class Spawn(LimitedTestCase):
    def tearDown(self):
        global _g_results
        super(Spawn, self).tearDown()
        _g_results = []
        
    def test_simple(self):
        gt = greenthread.spawn(passthru, 1, b=2)
        self.assertEquals(gt.wait(), ((1,),{'b':2}))
        self.assertEquals(_g_results, [((1,),{'b':2})])
        
    def test_n(self):
        gt = greenthread.spawn_n(passthru, 2, b=3)
        self.assert_(not gt.dead)
        greenthread.sleep(0)
        self.assert_(gt.dead)
        self.assertEquals(_g_results, [((2,),{'b':3})])
    
    def test_kill(self):
        gt = greenthread.spawn(passthru, 6)
        greenthread.kill(gt)
        self.assertRaises(greenlet.GreenletExit, gt.wait)
        greenthread.sleep(0.001)
        self.assertEquals(_g_results, [])
        greenthread.kill(gt)

    def test_kill_meth(self):
        gt = greenthread.spawn(passthru, 6)
        gt.kill()
        self.assertRaises(greenlet.GreenletExit, gt.wait)
        greenthread.sleep(0.001)
        self.assertEquals(_g_results, [])
        gt.kill()
        
    def test_kill_n(self):
        gt = greenthread.spawn_n(passthru, 7)
        greenthread.kill(gt)
        greenthread.sleep(0.001)
        self.assertEquals(_g_results, [])
        greenthread.kill(gt)
    
    def test_link(self):
        results = []
        def link_func(g, *a, **kw):
            results.append(g)
            results.append(a)
            results.append(kw)
        gt = greenthread.spawn(passthru, 5)
        gt.link(link_func, 4, b=5)
        self.assertEquals(gt.wait(), ((5,), {}))
        self.assertEquals(results, [gt, (4,), {'b':5}])
        
    def test_link_after_exited(self):
        results = []
        def link_func(g, *a, **kw):
            results.append(g)
            results.append(a)
            results.append(kw)
        gt = greenthread.spawn(passthru, 5)
        self.assertEquals(gt.wait(), ((5,), {}))
        gt.link(link_func, 4, b=5)
        self.assertEquals(results, [gt, (4,), {'b':5}])
        
