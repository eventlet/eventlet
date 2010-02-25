#!/usr/bin/env python

from eventlet import patcher
from eventlet.green import socket
from eventlet.green import urllib
from eventlet.green import threading

try:
    socket.ssl
    socket.sslerror
except AttributeError:
    raise ImportError("Socket module doesn't support ssl")

patcher.inject('test.test_socket_ssl',
    globals(),
    ('socket', socket),
    ('urllib', urllib),
    ('threading', threading))

test_basic = patcher.patch_function(test_basic, 
    ('urllib', urllib))    
test_rude_shutdown = patcher.patch_function(test_rude_shutdown, 
    ('threading', threading))


if __name__ == "__main__":
    test_main()
