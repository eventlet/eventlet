from eventlet import event, spawn, sleep, patcher
from eventlet.hubs import use_hub, get_hub, _threadlocal
from eventlet.hubs.hub import READ, WRITE
from eventlet.green import zmq
from nose.tools import *
from tests import mock, LimitedTestCase, skip_unless
from unittest import TestCase

from threading import Thread

def using_zmq(_f):
    return 'zeromq' in type(get_hub()).__module__

def skip_unless_zmq(func):
    """ Decorator that skips a test if we're using the pyevent hub."""
    return skip_unless(using_zmq)(func)

class TestUpstreamDownStream(LimitedTestCase):

    def create_bound_pair(self, type1, type2, interface='tcp://127.0.0.1'):
        """Create a bound socket pair using a random port."""
        self.context = context = get_hub().get_context()
        s1 = context.socket(type1)
        port = s1.bind_to_random_port(interface)
        s2 = context.socket(type2)
        s2.connect('%s:%s' % (interface, port))
        return s1, s2

    def assertRaisesErrno(self, errno, func, *args):
        try:
            func(*args)
        except zmq.ZMQError, e:
            self.assertEqual(e.errno, errno, "wrong error raised, expected '%s' \
got '%s'" % (zmq.ZMQError(errno), zmq.ZMQError(e.errno)))
        else:
            self.fail("Function did not raise any error")

    @skip_unless_zmq
    def test_recv_spawned_before_send_is_non_blocking(self):
        ipc = 'ipc:///tmp/tests'
        req, rep = self.create_bound_pair(zmq.PAIR, zmq.PAIR)
#        req.connect(ipc)
#        rep.bind(ipc)
        sleep()
        msg = dict(res=None)
        done = event.Event()
        def rx():
            msg['res'] = rep.recv()
            done.send('done')
        spawn(rx)
        req.send('test')
        done.wait()
        self.assertEqual(msg['res'], 'test')

    @skip_unless_zmq
    def test_send_1k_req_rep(self):
        req, rep = self.create_bound_pair(zmq.REQ, zmq.REP)
        sleep()
        done = event.Event()
        def tx():
            tx_i = 0
            req.send(str(tx_i))
            while req.recv() != 'done':
                tx_i += 1
                req.send(str(tx_i))
        def rx():
            while True:
                rx_i = rep.recv()
                if rx_i == "1000":
                    rep.send('done')
                    done.send(0)
                    break
                rep.send('i')
        spawn(tx)
        spawn(rx)
        final_i = done.wait()
        self.assertEqual(final_i, 0)

    @skip_unless_zmq
    def test_send_1k_up_down(self):
        down, up = self.create_bound_pair(zmq.DOWNSTREAM, zmq.UPSTREAM)
        sleep()
        done = event.Event()
        def tx():
            tx_i = 0
            while tx_i <= 1000:
                tx_i += 1
                down.send(str(tx_i))
        def rx():
            while True:
                rx_i = up.recv()
                if rx_i == "1000":
                    done.send(0)
                    break
        spawn(tx)
        spawn(rx)
        final_i = done.wait()
        self.assertEqual(final_i, 0)




        

class TestThreadedContextAccess(TestCase):
    """zmq's Context must be unique within a hub

    The zeromq API documentation states:
    All zmq sockets passed to the zmq_poll() function must share the same zmq
    context and must belong to the thread calling zmq_poll()

    As zmq_poll is what's eventually being called then we need to insure that
    all sockets that are going to be passed to zmq_poll (via hub.do_poll) are
    in the same context
    """

    @skip_unless_zmq
    def test_threadlocal_context(self):
        hub = get_hub()
        context = hub.get_context()
        self.assertEqual(context, _threadlocal.context)
        next_context = hub.get_context()
        self.assertTrue(context is next_context)

    @skip_unless_zmq
    def test_different_context_in_different_thread(self):
        context = get_hub().get_context()
        test_result = []
        def assert_different(ctx):
            assert not hasattr(_threadlocal, 'hub')
            this_thread_context = get_hub().get_context()
            test_result.append(ctx is this_thread_context)
        Thread(target=assert_different, args=(context,)).start()
        while not len(test_result):
            pass
        self.assertFalse(test_result[0])





