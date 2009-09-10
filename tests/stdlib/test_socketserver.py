#!/usr/bin/env python

# to get past the silly 'requires' check
from test import test_support
test_support.use_resources = ['network']

from eventlet.green import SocketServer
from eventlet.green import socket
from eventlet.green import select
from eventlet.green import time
from eventlet.green import threading

# need to override these modules before import so 
# that classes inheriting from threading.Thread refer
# to the correct module
import sys
sys.modules['threading'] = threading
sys.modules['SocketServer'] = SocketServer

from test import test_socketserver

test_socketserver.socket = socket
test_socketserver.select = select
test_socketserver.time = time

# skipping these tests for now
#from test.test_socketserver import *

if __name__ == "__main__":
    pass#test_main()