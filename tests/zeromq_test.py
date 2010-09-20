from eventlet import spawn, sleep, getcurrent
from eventlet.hubs import use_hub, get_hub
from eventlet.green import zmq
from nose.tools import *
from tests import mock, LimitedTestCase
from eventlet.hubs.hub import READ, WRITE

class _TestZMQ(LimitedTestCase):

    def setUp(self):
        use_hub('zeromq')

        super(_TestZMQ, self).setUp()
#        self.timer.cancel()

    def tearDown(self):
        super(_TestZMQ, self).tearDown()
        use_hub()

class TestUpstreamDownStream(_TestZMQ):

    def _get_socket_pair(self):
        return (zmq.Context().socket(zmq.PAIR),
                zmq.Context().socket(zmq.PAIR))


    def test_recv_non_blocking(self):
        ipc = 'ipc:///tmp/tests'
        req, rep = self._get_socket_pair()
        req.connect(ipc)
        rep.bind(ipc)
        sleep(0.2)
#        req.send('test')
#        set_trace()
        hub = get_hub()
#        hub.add(READ, rep, getcurrent().switch)
        msg = {}
        def rx():
            msg['res'] = rep.recv()
        spawn(rx)

        req.send('test')

        sleep(0.2)


        self.assertEqual(msg['res'], 'test')


