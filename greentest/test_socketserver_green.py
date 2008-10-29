import sys
from eventlet.green.SocketServer import *
from eventlet.green import socket
from eventlet.green import select
from eventlet.green import time
from eventlet.green import threading

execfile('test_socketserver.py')
