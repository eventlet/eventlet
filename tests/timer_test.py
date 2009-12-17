from unittest import TestCase, main

from eventlet import api, timer

class TestTimer(TestCase):
    mode = 'static'

    def test_copy(self):
        t = timer.Timer(0, lambda: None)
        t2 = t.copy()
        assert t.seconds == t2.seconds
        assert t.tpl == t2.tpl
        assert t.called == t2.called

##     def test_cancel(self):
##         r = runloop.RunLoop()
##         called = []
##         t = timer.Timer(0, lambda: called.append(True))
##         t.cancel()
##         r.add_timer(t)
##         r.add_observer(lambda r, activity: r.abort(), 'after_waiting')
##         r.run()
##         assert not called
##         assert not r.running

    def test_schedule(self):
        hub = api.get_hub()
        # clean up the runloop, preventing side effects from previous tests
        # on this thread
        if hub.running:
            hub.abort()
            api.sleep(0)
        called = []
        #t = timer.Timer(0, lambda: (called.append(True), hub.abort()))
        #t.schedule()
        # let's have a timer somewhere in the future; make sure abort() still works
        # (for pyevent, its dispatcher() does not exit if there is something scheduled)
        # XXX pyevent handles this, other hubs do not
        #api.get_hub().schedule_call_global(10000, lambda: (called.append(True), hub.abort()))
        api.get_hub().schedule_call_global(0, lambda: (called.append(True), hub.abort()))
        hub.default_sleep = lambda: 0.0
        hub.switch()
        assert called
        assert not hub.running

if __name__ == '__main__':
    main()
