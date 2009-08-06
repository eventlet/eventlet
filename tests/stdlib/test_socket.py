#!/usr/bin/env python

from test import test_socket
from test.test_socket import *

from eventlet.green import socket
from eventlet.green import select
from eventlet.green import time
from eventlet.green import thread
from eventlet.green import threading

test_socket.socket = socket
test_socket.select = select
test_socket.time = time
test_socket.thread = thread
test_socket.threading = threading

if __name__ == "__main__":
    test_main()