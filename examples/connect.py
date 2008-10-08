import sys
from eventlet.green import socket
from eventlet.green import time
from eventlet.api import spawn

def client():
    # using domain name directly is of course possible too
    # this is a test to see that dns lookups happen simultaneously too
    ip = socket.gethostbyname('www.google.com')
    c = socket.socket()
    c.connect((ip, 80))
    c.send('GET /\r\n\r\n')
    print c.recv(1024)


for x in range(5):
    # note that spawn doesn't switch to new greenlet immediately.
    spawn(client)

# the execution ends with the main greenlet exit (by design), so we need to give control
# to other greenlets for some time here.
time.sleep(1)
sys.stdout.flush()
