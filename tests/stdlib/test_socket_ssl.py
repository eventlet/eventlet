#!/usr/bin/env python

from eventlet import patcher
from eventlet.green import socket
from eventlet.green import urllib
from eventlet.green import threading

patcher.inject('test.test_socket_ssl',
    globals(),
    ('socket', socket),
    ('urllib', urllib),
    ('threading', threading))

if __name__ == "__main__":
    test_main()
