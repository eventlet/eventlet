#!/usr/bin/env python

from eventlet.green import threading
from eventlet.green import socket
from eventlet.green import urllib2
from eventlet.green import BaseHTTPServer

# need to override these modules before import so
# that classes inheriting from threading.Thread refer
# to the correct parent class
import sys
sys.modules['threading'] = threading
sys.modules['BaseHTTPServer'] = BaseHTTPServer

from test import test_urllib2_localnet

test_urllib2_localnet.socket = socket
test_urllib2_localnet.urllib2 = urllib2
test_urllib2_localnet.BaseHTTPServer = BaseHTTPServer

from test.test_urllib2_localnet import *

if __name__ == "__main__":
    test_main()