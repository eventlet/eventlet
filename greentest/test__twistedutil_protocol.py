from twisted.internet import reactor
from greentest import exit_unless_twisted
exit_unless_twisted()

import sys
import unittest
from twisted.internet.error import ConnectionLost, ConnectionDone
from twisted.python import failure

import eventlet.twistedutil.protocol as pr
from eventlet.api import spawn, sleep, with_timeout, call_after
from eventlet.green import socket

DELAY=0.01

def setup_server_socket(self, delay=DELAY, port=0):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('127.0.0.1', port))
    port = s.getsockname()[1]
    s.listen(5)
    s.settimeout(delay*3)
    def serve():
        conn, addr = s.accept()
        conn.settimeout(delay+1)
        try:
            hello = conn.recv(128)
        except socket.timeout:
            return
        conn.sendall('you said %s. ' % hello)
        sleep(delay)
        conn.sendall('BYE')
        sleep(delay)
        #conn.close()
    spawn(serve)
    return port

def setup_server_SpawnFactory(self, delay=DELAY, port=0):
    def handle(conn):
        port.stopListening()
        hello = conn.recv()
        conn.write('you said %s. ' % hello)
        sleep(delay)
        conn.write('BYE')
        sleep(delay)
        conn.loseConnection()
    port = reactor.listenTCP(0, pr.SpawnFactory(handle, pr.UnbufferedTransport))
    return port.getHost().port


class TestCase(unittest.TestCase):

    def setUp(self):
        port = self.setup_server()
        self.conn = self.connector.connectTCP('127.0.0.1', port)

class TestUnbufferedTransport(TestCase):

    connector = pr.GreenClientCreator(reactor, pr.UnbufferedTransport)
    setup_server = setup_server_socket

    def test_recv(self):
        self.conn.write('hello')
        self.assertEqual(self.conn.recv(), 'you said hello. ')
        self.assertEqual(self.conn.recv(), 'BYE')
        self.assertEqual(self.conn.recv(), '')
        self.assertEqual(self.conn.recv(), '')

    def test_recv_error(self):
        self.conn.write('hello')
        self.assertEqual(self.conn.recv(), 'you said hello. ')
        try:
            1/0
        except:
            f = failure.Failure()
        spawn(self.conn.protocol.connectionLost, f)
        self.assertRaises(ZeroDivisionError, self.conn.recv)

    def test_iterator(self):
        self.conn.write('hello')
        i = iter(self.conn)
        self.assertEqual(i.next(), 'you said hello. ')
        self.assertEqual(i.next(), 'BYE')
        self.assertRaises(StopIteration, i.next)


class TestUnbufferedTransport_SpawnFactory(TestUnbufferedTransport):
    setup_server = setup_server_SpawnFactory


class TestTransport(pr.GreenTransportBase):

    protocol_class = pr.Protocol

    def recv(self):
        return self._wait()

class TestError(TestCase):

    connector = pr.GreenClientCreator(reactor, TestTransport)
    setup_server = setup_server_socket

    def test_error(self):
        self.conn.write('hello')
        self.assertEqual(self.conn.recv(), 'you said hello. ')
        self.assertEqual(self.conn.recv(), 'BYE')
        self.assertRaises(ConnectionDone, self.conn.recv)

class TestError_SpawnFactory(TestError):
    setup_server = setup_server_SpawnFactory

class TestGreenTransport(TestCase):

    connector = pr.GreenClientCreator(reactor, pr.GreenTransport)
    setup_server = setup_server_socket

    def test_read(self):
        self.conn.write('hello')
        self.assertEqual(self.conn.read(9), 'you said ')
        self.assertEqual(self.conn.read(999), 'hello. BYE')
        self.assertEqual(self.conn.read(9), '')
        self.assertEqual(self.conn.read(1), '')
        self.assertEqual(None, self.conn._queue)

    def test_read2(self):
        self.conn.write('world')
        self.assertEqual(self.conn.read(), 'you said world. BYE')
        self.assertEqual(self.conn.read(), '')
        self.assertEqual(self.conn.recv(), '')

    def test_read_error(self):
        self.conn.write('hello')
        self.assertEqual(self.conn.read(9), 'you said ')
        self.assertEqual(self.conn.recv(), 'hello. ')
        sleep(DELAY*1.5) # make sure the rest of data arrives
        try:
            1/0
        except:
            #self.conn.loseConnection(failure.Failure()) # does not work, why?
            spawn(self.conn._queue.send_exception, *sys.exc_info())
        self.assertEqual(self.conn.read(9), 'BYE')
        self.assertRaises(ZeroDivisionError, self.conn.read, 9)
        self.assertEqual(None, self.conn._queue)
        self.assertEqual(self.conn.read(1), '')
        self.assertEqual(self.conn.read(1), '')

    def test_recv(self):
        self.conn.write('hello')
        self.assertEqual('you said hello. ', self.conn.recv())
        self.assertEqual('BYE', self.conn.recv())
        self.assertEqual('', self.conn.recv())
        self.assertEqual('', self.conn.recv())

    def test_recv2(self):
        self.conn.write('whoa')
        self.assertEqual('you said ', self.conn.recv(9))
        self.assertEqual('whoa. ', self.conn.recv(999))
        self.assertEqual('BYE', self.conn.recv(9))
        self.assertEqual('', self.conn.recv(1))
        self.assertEqual('', self.conn.recv())
        self.assertEqual('', self.conn.read())

    def test_recv_error(self):
        self.conn.write('hello')
        self.assertEqual('you said hello. ', self.conn.recv())
        sleep(DELAY*1.5) # make sure the rest of data arrives
        try:
            1/0
        except:
            #self.conn.loseConnection(failure.Failure()) # does not work, why?
            spawn(self.conn._queue.send_exception, *sys.exc_info())
        self.assertEqual('BYE', self.conn.recv())
        self.assertRaises(ZeroDivisionError, self.conn.recv, 9)
        self.assertEqual(None, self.conn._queue)
        self.assertEqual('', self.conn.recv(1))
        self.assertEqual('', self.conn.recv())

    def test_iterator(self):
        self.conn.write('hello')
        self.assertEqual('you said hello. ', self.conn.next())
        self.assertEqual('BYE', self.conn.next())
        self.assertRaises(StopIteration, self.conn.next)

    _tests = [x for x in locals().keys() if x.startswith('test_')]

    def test_resume_producing(self):
        for test in self._tests:
            self.setUp()
            self.conn.resumeProducing()
            getattr(self, test)()

    def test_pause_producing(self):
        self.conn.pauseProducing()
        self.conn.write('hi')
        result = with_timeout(DELAY*10, self.conn.read, timeout_value='timed out')
        self.assertEqual('timed out', result)

    def test_pauseresume_producing(self):
        self.conn.pauseProducing()
        call_after(DELAY*5, self.conn.resumeProducing)
        self.conn.write('hi')
        result = with_timeout(DELAY*10, self.conn.read, timeout_value='timed out')
        self.assertEqual('you said hi. BYE', result)


class TestGreenTransport_SpawnFactory(TestGreenTransport):
    setup_server = setup_server_SpawnFactory

if __name__=='__main__':
    unittest.main()

