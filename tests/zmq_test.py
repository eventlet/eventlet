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

    def tearDown(self):
        self.clear_up_sockets()
        super(TestUpstreamDownStream, self).tearDown()

    def create_bound_pair(self, type1, type2, interface='tcp://127.0.0.1'):
        """Create a bound socket pair using a random port."""
        self.context = context = get_hub().get_context()
        s1 = context.socket(type1)
        port = s1.bind_to_random_port(interface)
        s2 = context.socket(type2)
        s2.connect('%s:%s' % (interface, port))
        self.sockets = [s1, s2]
        return s1, s2, port

    def clear_up_sockets(self):
        for sock in self.sockets:
            sock.close()

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
        req, rep, port = self.create_bound_pair(zmq.PAIR, zmq.PAIR)
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
    def test_close_socket_raises_enotsup(self):
        req, rep, port = self.create_bound_pair(zmq.PAIR, zmq.PAIR)
        rep.close()
        req.close()
        self.assertRaisesErrno(zmq.ENOTSUP, rep.recv)
        self.assertRaisesErrno(zmq.ENOTSUP, req.send, 'test')

    @skip_unless_zmq
    def test_send_1k_req_rep(self):
        req, rep, port = self.create_bound_pair(zmq.REQ, zmq.REP)
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
                    sleep()
                    done.send(0)
                    break
                rep.send('i')
        spawn(tx)
        spawn(rx)
        final_i = done.wait()
        self.assertEqual(final_i, 0)

    @skip_unless_zmq
    def test_send_1k_push_pull(self):
        down, up, port = self.create_bound_pair(zmq.PUSH, zmq.PULL)
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

    @skip_unless_zmq
    def test_send_1k_pub_sub(self):
        pub, sub_all, port = self.create_bound_pair(zmq.PUB, zmq.SUB)
        sub1 = self.context.socket(zmq.SUB)
        sub2 = self.context.socket(zmq.SUB)
        self.sockets.extend([sub1, sub2])
        addr = 'tcp://127.0.0.1:%s' % port
        sub1.connect(addr)
        sub2.connect(addr)
        sub_all.setsockopt(zmq.SUBSCRIBE, '')
        sub1.setsockopt(zmq.SUBSCRIBE, 'sub1')
        sub2.setsockopt(zmq.SUBSCRIBE, 'sub2')
        sub_all_done = event.Event()
        sub1_done = event.Event()
        sub2_done = event.Event()

        def rx(sock, done_evt, msg_count=10000):
            count = 0
            while count < msg_count:
                msg = sock.recv()
                if 'LAST' in msg:
                    break
                count += 1

            done_evt.send(count)

        def tx(sock):
            for i in range(1, 1001):
                msg = "sub%s %s" % (1 if i % 2 else 2, i)
                sock.send(msg)
                sleep()
            sock.send('sub1 LAST')
            sock.send('sub2 LAST')

        spawn(rx, sub_all, sub_all_done)
        spawn(rx, sub1, sub1_done)
        spawn(rx, sub2, sub2_done)
        spawn(tx, pub)
        sub1_count = sub1_done.wait()
        sub2_count = sub2_done.wait()
        sub_all_count = sub_all_done.wait()
        self.assertEqual(sub1_count, 500)
        self.assertEqual(sub2_count, 500)
        self.assertEqual(sub_all_count, 1000)

    @skip_unless_zmq
    def test_change_subscription(self):
        pub, sub, port = self.create_bound_pair(zmq.PUB, zmq.SUB)
        sub.setsockopt(zmq.SUBSCRIBE, 'test')

        sub_done = event.Event()

        def rx(sock, done_evt):
            count = 0
            sub = 'test'
            while True:
                msg = sock.recv()
                if sub == 'done':
                    break
                if 'LAST' in msg and sub == 'test':
                    sock.setsockopt(zmq.UNSUBSCRIBE, 'test')
                    sock.setsockopt(zmq.SUBSCRIBE, 'done')
                    sub = 'done'
                count += 1
            done_evt.send(count)

        def tx(sock):
            for i in range(1, 101):
                msg = "test %s" % i
                sock.send(msg)
                if i == 50:
                    sock.send('test LAST')
                sleep()
            sock.send('done DONE')

        spawn(rx, sub, sub_done)
        spawn(tx, pub)

        rx_count = sub_done.wait()
        self.assertEqual(rx_count, 50)



        












        

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
            import os
            os.environ['EVENTLET_HUB'] = 'zeromq'
            hub = get_hub()
            try:
                this_thread_context = hub.get_context()
            except:
                test_result.append('fail')
                raise
            test_result.append(ctx is this_thread_context)
        Thread(target=assert_different, args=(context,)).start()
        count = 0
        while count < 100 and not test_result:
            count += 1
        self.assertFalse(test_result[0])





