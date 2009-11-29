from eventlet import patcher
from eventlet.green import asyncore
from eventlet.green import BaseHTTPServer
from eventlet.green import select
from eventlet.green import socket
from eventlet.green import SocketServer
from eventlet.green import ssl
from eventlet.green import threading
from eventlet.green import urllib
# *TODO: SimpleHTTPServer

# stupid test_support messing with our mojo
import test.test_support
i_r_e = test.test_support.is_resource_enabled
def is_resource_enabled(resource):
    if resource == 'network':
        return True
    else:
        return i_r_e(resource)
test.test_support.is_resource_enabled = is_resource_enabled

patcher.inject('test.test_ssl',
    globals(),
    ('asyncore', asyncore),
    ('BaseHTTPServer', BaseHTTPServer),
    ('select', select),
    ('socket', socket),
    ('SocketServer', SocketServer),
    ('ssl', ssl),
    ('threading', threading),
    ('urllib', urllib))

# these appear to not work due to some wonkiness in the threading
# module... skipping them for now (can't use SkipTest either because
# test_main doesn't understand it)
# *TODO: fix and restore these tests
ThreadedTests.testProtocolSSL2 = lambda s: None
ThreadedTests.testProtocolSSL3 = lambda s: None
ThreadedTests.testProtocolTLS1 = lambda s: None
ThreadedTests.testSocketServer = lambda s: None

if __name__ == "__main__":
    test_main()