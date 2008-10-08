#!/usr/bin/env python

import sys
if 'twisted.internet.reactor' not in sys.modules:
    # the following line makes a difference on my machine (fixes 2 failures)
    from twisted.internet import pollreactor; pollreactor.install()

from eventlet.green import socket
from eventlet.green import select
from eventlet.green import time

execfile('test_socket.py')
