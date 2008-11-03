"""This test checks that socket instances (not GreenSockets but underlying sockets)
are not leaked by the hub.
"""
import sys
import unittest
from eventlet.green import socket
from eventlet.green.thread import start_new_thread
from eventlet.green.time import sleep
import weakref
import gc

address = ('0.0.0.0', 7878)

def init_server():
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(address)
    s.listen(5)
    return s

def handle_request(s):
    conn, address = s.accept()
    #print 'handle_request - accepted'
    res = conn.recv(100)
    assert res == 'hello', `res`
    #print 'handle_request - recvd %r' % res
    res = conn.send('bye')
    #print 'handle_request - sent %r' % res
    #print 'handle_request - conn refcount: %s' % sys.getrefcount(conn)
    #conn.close()

def make_request():
    #print 'make_request'
    s = socket.socket()
    s.connect(address)
    #print 'make_request - connected'
    res = s.send('hello')
    #print 'make_request - sent %s' % res
    res = s.recv(100)
    assert res == 'bye', `res`
    #print 'make_request - recvd %r' % res
    #s.close()

def run_interaction():
    s = init_server()
    start_new_thread(handle_request, (s, ))
    start_new_thread(make_request, ())
    sleep(0.2)
    #print sys.getrefcount(s.fd)
    #s.close()
    return weakref.ref(s.fd)

def run_and_check():
    w = run_interaction()
    if w():
        print gc.get_referrers(w())
        for x in gc.get_referrers(w()):
            print x
            for y in gc.get_referrers(x):
                print '-', y
        raise AssertionError('server should be dead by now')

class test(unittest.TestCase):

    def test(self):
        run_and_check()
        run_and_check()


if __name__=='__main__':
    unittest.main()

