from eventlet import patcher
from eventlet.green import asyncore
from eventlet.green import ftplib
from eventlet.green import threading
from eventlet.green import socket

patcher.inject('test.test_ftplib', globals())
    
if __name__ == "__main__":
    test_main()
