#!/usr/bin/env python

from test import test_socket_ssl

from eventlet.green import socket
from eventlet.green import urllib
from eventlet.green import threading

test_socket_ssl.socket = socket
# bwahaha
import sys
sys.modules['urllib'] = urllib
sys.modules['threading'] = threading
# to get past the silly 'requires' check
test_socket_ssl.__name__ = '__main__'

from test.test_socket_ssl import *

if __name__ == "__main__":
    test_main()