import sys
if 'twisted.internet.reactor' not in sys.modules:
    from twisted.internet import pollreactor; pollreactor.install()
from eventlet.green import socket

execfile('test_urllib2.py')
