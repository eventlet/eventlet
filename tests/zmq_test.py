from __future__ import with_statement

from eventlet import event, spawn, sleep, patcher, semaphore
from eventlet.hubs import get_hub, _threadlocal, use_hub
from nose.tools import *
from tests import check_idle_cpu_usage, mock, LimitedTestCase, using_pyevent, skip_unless
from unittest import TestCase

from threading import Thread
try:
    from eventlet.green import zmq
except ImportError:
    zmq = {}    # for systems lacking zmq, skips tests instead of barfing


def zmq_supported(_):
    try:
        import zmq
    except ImportError:
        return False
    return not using_pyevent(_)


class TestUpstreamDownStream(LimitedTestCase):
    @skip_unless(zmq_supported)
    def setUp(self):
        super(TestUpstreamDownStream, self).setUp()
        self.context = zmq.Context()
        self.sockets = []

    @skip_unless(zmq_supported)
    def tearDown(self):
        self.clear_up_sockets()
        super(TestUpstreamDownStream, self).tearDown()

    def create_bound_pair(self, type1, type2, interface='tcp://127.0.0.1'):
        """Create a bound socket pair using a random port."""
        s1 = self.context.socket(type1)
        port = s1.bind_to_random_port(interface)
        s2 = self.context.socket(type2)
        s2.connect('%s:%s' % (interface, port))
        self.sockets.append(s1)
        self.sockets.append(s2)
        return s1, s2, port

    def clear_up_sockets(self):
        for sock in self.sockets:
            sock.close()
        self.sockets = None
        self.context.destroy(0)

    def assertRaisesErrno(self, errno, func, *args):
        try:
            func(*args)
        except zmq.ZMQError as e:
            self.assertEqual(e.errno, errno, "wrong error raised, expected '%s' \
got '%s'" % (zmq.ZMQError(errno), zmq.ZMQError(e.errno)))
        else:
            self.fail("Function did not raise any error")

    @skip_unless(zmq_supported)
    def test_close_linger(self):
        """Socket.close() must support linger argument.

        https://github.com/eventlet/eventlet/issues/9
        """
        sock1, sock2, _ = self.create_bound_pair(zmq.PAIR, zmq.PAIR)
        sock1.close(1)
        sock2.close(linger=0)

    @skip_unless(zmq_supported)
    def test_recv_spawned_before_send_is_non_blocking(self):
        req, rep, port = self.create_bound_pair(zmq.PAIR, zmq.PAIR)
#       req.connect(ipc)
#       rep.bind(ipc)
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

    @skip_unless(zmq_supported)
    def test_close_socket_raises_enotsup(self):
        req, rep, port = self.create_bound_pair(zmq.PAIR, zmq.PAIR)

        rep.close()
        req.close()
        self.assertRaisesErrno(zmq.ENOTSUP, rep.recv)
        self.assertRaisesErrno(zmq.ENOTSUP, req.send, 'test')

    @skip_unless(zmq_supported)
    def test_close_xsocket_raises_enotsup(self):
        req, rep, port = self.create_bound_pair(zmq.XREQ, zmq.XREP)

        rep.close()
        req.close()
        self.assertRaisesErrno(zmq.ENOTSUP, rep.recv)
        self.assertRaisesErrno(zmq.ENOTSUP, req.send, 'test')

    @skip_unless(zmq_supported)
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
            done.send(0)

        def rx():
            while True:
                rx_i = rep.recv()
                if rx_i == "1000":
                    rep.send('done')
                    break
                rep.send('i')
        spawn(tx)
        spawn(rx)
        final_i = done.wait()
        self.assertEqual(final_i, 0)

    @skip_unless(zmq_supported)
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

    @skip_unless(zmq_supported)
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

        sleep(0.2)

        def rx(sock, done_evt, msg_count=10000):
            count = 0
            while count < msg_count:
                msg = sock.recv()
                sleep()
                if 'LAST' in msg:
                    break
                count += 1

            done_evt.send(count)

        def tx(sock):
            for i in range(1, 1001):
                msg = "sub%s %s" % ([2,1][i % 2], i)
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

    @skip_unless(zmq_supported)
    def test_change_subscription(self):
        pub, sub, port = self.create_bound_pair(zmq.PUB, zmq.SUB)
        sub.setsockopt(zmq.SUBSCRIBE, 'test')

        sleep(0.2)
        sub_done = event.Event()

        def rx(sock, done_evt):
            count = 0
            sub = 'test'
            while True:
                msg = sock.recv()
                sleep()
                if 'DONE' in msg:
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
                if i != 50:
                    sock.send(msg)
                else:
                    sock.send('test LAST')
                sleep()
            sock.send('done DONE')

        spawn(rx, sub, sub_done)
        spawn(tx, pub)

        rx_count = sub_done.wait()
        self.assertEqual(rx_count, 50)

    @skip_unless(zmq_supported)
    def test_recv_multipart_bug68(self):
        req, rep, port = self.create_bound_pair(zmq.REQ, zmq.REP)
        msg = ['']
        req.send_multipart(msg)
        recieved_msg = rep.recv_multipart()
        self.assertEqual(recieved_msg, msg)

        # Send a message back the other way
        msg2 = [""]
        rep.send_multipart(msg2, copy=False)
        # When receiving a copy it's a zmq.core.message.Message you get back
        recieved_msg = req.recv_multipart(copy=False)
        # So it needs to be converted to a string
        # I'm calling str(m) consciously here; Message has a .data attribute
        # but it's private __str__ appears to be the way to go
        self.assertEqual([str(m) for m in recieved_msg], msg2)

    @skip_unless(zmq_supported)
    def test_recv_noblock_bug76(self):
        req, rep, port = self.create_bound_pair(zmq.REQ, zmq.REP)
        self.assertRaisesErrno(zmq.EAGAIN, rep.recv, zmq.NOBLOCK)
        self.assertRaisesErrno(zmq.EAGAIN, rep.recv, zmq.NOBLOCK, True)

    @skip_unless(zmq_supported)
    def test_send_during_recv(self):
        sender, receiver, port = self.create_bound_pair(zmq.XREQ, zmq.XREQ)
        sleep()

        num_recvs = 30
        done_evts = [event.Event() for _ in range(num_recvs)]

        def slow_rx(done, msg):
            self.assertEqual(sender.recv(), msg)
            done.send(0)

        def tx():
            tx_i = 0
            while tx_i <= 1000:
                sender.send(str(tx_i))
                tx_i += 1

        def rx():
            while True:
                rx_i = receiver.recv()
                if rx_i == "1000":
                    for i in range(num_recvs):
                        receiver.send('done%d' % i)
                    sleep()
                    return

        for i in range(num_recvs):
            spawn(slow_rx, done_evts[i], "done%d" % i)

        spawn(tx)
        spawn(rx)
        for evt in done_evts:
            self.assertEqual(evt.wait(), 0)


    @skip_unless(zmq_supported)
    def test_send_during_recv_multipart(self):
        sender, receiver, port = self.create_bound_pair(zmq.XREQ, zmq.XREQ)
        sleep()

        num_recvs = 30
        done_evts = [event.Event() for _ in range(num_recvs)]

        def slow_rx(done, msg):
            self.assertEqual(sender.recv_multipart(), msg)
            done.send(0)

        def tx():
            tx_i = 0
            while tx_i <= 1000:
                sender.send_multipart([str(tx_i), '1', '2', '3'])
                tx_i += 1

        def rx():
            while True:
                rx_i = receiver.recv_multipart()
                if rx_i == ["1000", '1', '2', '3']:
                    for i in range(num_recvs):
                        receiver.send_multipart(['done%d' % i, 'a', 'b', 'c'])
                    sleep()
                    return

        for i in range(num_recvs):
            spawn(slow_rx, done_evts[i], ["done%d" % i, 'a', 'b', 'c'])

        spawn(tx)
        spawn(rx)
        for i in range(num_recvs):
            final_i = done_evts[i].wait()
            self.assertEqual(final_i, 0)


    # Need someway to ensure a thread is blocked on send... This isn't working
    @skip_unless(zmq_supported)
    def test_recv_during_send(self):
        sender, receiver, port = self.create_bound_pair(zmq.XREQ, zmq.XREQ)
        sleep()

        num_recvs = 30
        done = event.Event()

        try:
            SNDHWM = zmq.SNDHWM
        except AttributeError:
            # ZeroMQ <3.0
            SNDHWM = zmq.HWM

        sender.setsockopt(SNDHWM, 10)
        sender.setsockopt(zmq.SNDBUF, 10)

        receiver.setsockopt(zmq.RCVBUF, 10)

        def tx():
            tx_i = 0
            while tx_i <= 1000:
                sender.send(str(tx_i))
                tx_i += 1
            done.send(0)

        spawn(tx)
        final_i = done.wait()
        self.assertEqual(final_i, 0)

    @skip_unless(zmq_supported)
    def test_close_during_recv(self):
        sender, receiver, port = self.create_bound_pair(zmq.XREQ, zmq.XREQ)
        sleep()
        done1 = event.Event()
        done2 = event.Event()

        def rx(e):
            self.assertRaisesErrno(zmq.ENOTSUP, receiver.recv)
            e.send()

        spawn(rx, done1)
        spawn(rx, done2)

        sleep()
        receiver.close()

        done1.wait()
        done2.wait()

    @skip_unless(zmq_supported)
    def test_getsockopt_events(self):
        sock1, sock2, _port = self.create_bound_pair(zmq.DEALER, zmq.DEALER)
        sleep()
        poll_out = zmq.Poller()
        poll_out.register(sock1, zmq.POLLOUT)
        sock_map = poll_out.poll(100)
        self.assertEqual(len(sock_map), 1)
        events = sock1.getsockopt(zmq.EVENTS)
        self.assertEqual(events & zmq.POLLOUT, zmq.POLLOUT)
        sock1.send('')

        poll_in = zmq.Poller()
        poll_in.register(sock2, zmq.POLLIN)
        sock_map = poll_in.poll(100)
        self.assertEqual(len(sock_map), 1)
        events = sock2.getsockopt(zmq.EVENTS)
        self.assertEqual(events & zmq.POLLIN, zmq.POLLIN)

    @skip_unless(zmq_supported)
    def test_cpu_usage_after_bind(self):
        """zmq eats CPU after PUB socket .bind()

        https://bitbucket.org/eventlet/eventlet/issue/128

        According to the ZeroMQ documentation, the socket file descriptor
        can be readable without any pending messages. So we need to ensure
        that Eventlet wraps around ZeroMQ sockets do not create busy loops.

        A naive way to test it is to measure resource usage. This will require
        some tuning to set appropriate acceptable limits.
        """
        sock = self.context.socket(zmq.PUB)
        self.sockets.append(sock)
        sock.bind_to_random_port("tcp://127.0.0.1")
        sleep()
        check_idle_cpu_usage(0.2, 0.1)

    @skip_unless(zmq_supported)
    def test_cpu_usage_after_pub_send_or_dealer_recv(self):
        """zmq eats CPU after PUB send or DEALER recv.

        Same https://bitbucket.org/eventlet/eventlet/issue/128
        """
        pub, sub, _port = self.create_bound_pair(zmq.PUB, zmq.SUB)
        sub.setsockopt(zmq.SUBSCRIBE, "")
        sleep()
        pub.send('test_send')
        check_idle_cpu_usage(0.2, 0.1)

        sender, receiver, _port = self.create_bound_pair(zmq.DEALER, zmq.DEALER)
        sleep()
        sender.send('test_recv')
        msg = receiver.recv()
        self.assertEqual(msg, 'test_recv')
        check_idle_cpu_usage(0.2, 0.1)


class TestQueueLock(LimitedTestCase):
    @skip_unless(zmq_supported)
    def test_queue_lock_order(self):
        q = zmq._QueueLock()
        s = semaphore.Semaphore(0)
        results = []

        def lock(x):
            with q:
                results.append(x)
            s.release()

        q.acquire()

        spawn(lock, 1)
        sleep()
        spawn(lock, 2)
        sleep()
        spawn(lock, 3)
        sleep()

        self.assertEquals(results, [])
        q.release()
        s.acquire()
        s.acquire()
        s.acquire()
        self.assertEquals(results, [1,2,3])

    @skip_unless(zmq_supported)
    def test_count(self):
        q = zmq._QueueLock()
        self.assertFalse(q)
        q.acquire()
        self.assertTrue(q)
        q.release()
        self.assertFalse(q)

        with q:
            self.assertTrue(q)
        self.assertFalse(q)

    @skip_unless(zmq_supported)
    def test_errors(self):
        q = zmq._QueueLock()

        self.assertRaises(zmq.LockReleaseError, q.release)

        q.acquire()
        q.release()

        self.assertRaises(zmq.LockReleaseError, q.release)

    @skip_unless(zmq_supported)
    def test_nested_acquire(self):
        q = zmq._QueueLock()
        self.assertFalse(q)
        q.acquire()
        q.acquire()

        s = semaphore.Semaphore(0)
        results = []
        def lock(x):
            with q:
                results.append(x)
            s.release()

        spawn(lock, 1)
        sleep()
        self.assertEquals(results, [])
        q.release()
        sleep()
        self.assertEquals(results, [])
        self.assertTrue(q)
        q.release()

        s.acquire()
        self.assertEquals(results, [1])


class TestBlockedThread(LimitedTestCase):
    @skip_unless(zmq_supported)
    def test_block(self):
        e = zmq._BlockedThread()
        done = event.Event()
        self.assertFalse(e)

        def block():
            e.block()
            done.send(1)

        spawn(block)
        sleep()

        self.assertFalse(done.has_result())
        e.wake()
        done.wait()
