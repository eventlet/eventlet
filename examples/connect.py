"""Spawn multiple workers and collect their results.

Demonstrates how to use eventlet.green package and proc module.
"""
from eventlet import proc
from eventlet.green import socket

# this example works with both standard eventlet hubs and with twisted-based hub
# uncomment the following line to use twisted hub
#from twisted.internet import reactor

def geturl(url):
    c = socket.socket()
    ip = socket.gethostbyname(url)
    c.connect((ip, 80))
    print '%s connected' % url
    c.send('GET /\r\n\r\n')
    return c.recv(1024)

urls = ['www.google.com', 'www.yandex.ru', 'www.python.org']
jobs = [proc.spawn(geturl, x) for x in urls]
print 'spawned %s jobs' % len(jobs)

# collect the results from workers
results = proc.waitall(jobs)
# Note, that any exception in the workers will be reraised by waitall
# unless trap_errors argument specifies otherwise

for url, result in zip(urls, results):
    print '%s: %s' % (url, repr(result)[:50])

