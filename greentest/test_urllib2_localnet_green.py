import sys
if 'twisted.internet.reactor' not in sys.modules:
    # the following line makes a difference on my machine, tests take
    # muuuch less time (5x) to complete compared to selectreactor
    from twisted.internet import pollreactor; pollreactor.install()

from eventlet.green import threading
from eventlet.green import socket
from eventlet.green import urllib2
from eventlet.green import BaseHTTPServer

execfile('test_urllib2_localnet.py')
