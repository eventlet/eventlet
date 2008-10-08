import sys
if 'twisted.internet.reactor' not in sys.modules:
    from twisted.internet import pollreactor; pollreactor.install()
from eventlet.green.SocketServer import *
from eventlet.green import socket
from eventlet.green import select
from eventlet.green import time
from eventlet.green import threading

execfile('test_socketserver.py')
