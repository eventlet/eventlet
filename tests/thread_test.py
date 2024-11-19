import gc
import weakref

import eventlet
from eventlet import corolocal
from eventlet import event
from eventlet import greenthread
from eventlet import patcher
from eventlet.green import thread

from tests import LimitedTestCase, run_isolated


class Locals(LimitedTestCase):
    def passthru(self, *args, **kw):
        self.results.append((args, kw))
        return args, kw

    def setUp(self):
        self.results = []
        super().setUp()

    def tearDown(self):
        self.results = []
        super().tearDown()

    def test_assignment(self):
        my_local = corolocal.local()
        my_local.a = 1

        def do_something():
            my_local.b = 2
            self.assertEqual(my_local.b, 2)
            try:
                my_local.a
                self.fail()
            except AttributeError:
                pass

        eventlet.spawn(do_something).wait()
        self.assertEqual(my_local.a, 1)

    def test_calls_init(self):
        init_args = []

        class Init(corolocal.local):
            def __init__(self, *args):
                init_args.append((args, eventlet.getcurrent()))

        my_local = Init(1, 2, 3)
        self.assertEqual(init_args[0][0], (1, 2, 3))
        self.assertEqual(init_args[0][1], eventlet.getcurrent())

        def do_something():
            my_local.foo = 'bar'
            self.assertEqual(len(init_args), 2, init_args)
            self.assertEqual(init_args[1][0], (1, 2, 3))
            self.assertEqual(init_args[1][1], eventlet.getcurrent())

        eventlet.spawn(do_something).wait()

    def test_calling_methods(self):
        class Caller(corolocal.local):
            def callme(self):
                return self.foo

        my_local = Caller()
        my_local.foo = "foo1"
        self.assertEqual("foo1", my_local.callme())

        def do_something():
            my_local.foo = "foo2"
            self.assertEqual("foo2", my_local.callme())

        eventlet.spawn(do_something).wait()

        my_local.foo = "foo3"
        self.assertEqual("foo3", my_local.callme())

    def test_no_leaking(self):
        refs = weakref.WeakKeyDictionary()
        my_local = corolocal.local()

        class X:
            pass

        def do_something(i):
            o = X()
            refs[o] = True
            my_local.foo = o

        p = eventlet.GreenPool()
        for i in range(100):
            p.spawn(do_something, i)
        p.waitall()
        del p
        gc.collect()
        eventlet.sleep(0)
        gc.collect()
        # at this point all our coros have terminated
        self.assertEqual(len(refs), 1)


def test_compat_lock_release():
    # https://github.com/eventlet/eventlet/issues/697
    for mod in (patcher.original("threading"), thread):
        try:
            mod.Lock().release()
        except RuntimeError as e:
            # python3
            assert "release unlocked lock" in str(e).lower(), str((mod, e))
        except thread.error as e:
            # python2.7
            assert "release unlocked lock" in str(e).lower(), str((mod, e))


def test_reinit():
    # py39+ expects locks to have a _at_fork_reinit() method
    # https://github.com/eventlet/eventlet/pull/721#pullrequestreview-769377850
    lk = thread.Lock()
    lk.acquire()
    lk._at_fork_reinit()
    assert lk.acquire(blocking=False)
    assert not lk.acquire(blocking=False)


def test_can_use_eventlet_in_os_threads():
    run_isolated("osthreads.py")
