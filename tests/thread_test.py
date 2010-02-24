from eventlet.green import thread
from eventlet import greenthread
from eventlet import event
import eventlet

from tests import LimitedTestCase

class Locals(LimitedTestCase):
    def passthru(self, *args, **kw):
        self.results.append((args, kw))
        return args, kw

    def setUp(self):
        self.results = []
        super(Locals, self).setUp()

    def tearDown(self):
        self.results = []
        super(Locals, self).tearDown()

    def test_simple(self):
        tls = thread._local()
        g_ids = []
        evt = event.Event()
        def setter(tls, v):
            g_id = id(greenthread.getcurrent())
            g_ids.append(g_id)
            tls.value = v
            evt.wait()
        thread.start_new_thread(setter, args=(tls, 1))
        thread.start_new_thread(setter, args=(tls, 2))
        eventlet.sleep()
        objs = object.__getattribute__(tls, "__objs")
        self.failUnlessEqual(sorted(g_ids), sorted(objs.keys()))
        self.failUnlessEqual(objs[g_ids[0]]['value'], 1)
        self.failUnlessEqual(objs[g_ids[1]]['value'], 2)
        self.failUnlessRaises(AttributeError, lambda: tls.value)
        evt.send("done")
        eventlet.sleep()
