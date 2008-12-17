"""Spawn multiple greenlet-workers and collect their results.

Demonstrates how to use eventlet.green package and coros.Job.
"""
from eventlet.green import socket
from eventlet.coros import Job

# this example works with both standard eventlet hubs and with twisted-based hub
# comment out the following line to use standard eventlet hub
from twisted.internet import reactor

def geturl(url):
    c = socket.socket()
    ip = socket.gethostbyname(url)
    c.connect((ip, 80))
    c.send('GET /\r\n\r\n')
    return c.recv(1024)

urls = ['www.google.com', 'www.yandex.ru', 'www.python.org']
jobs = [Job.spawn_new(geturl, x) for x in urls]

print 'spawned %s jobs' % len(jobs)

# collect the results from workers, one by one
for url, job in zip(urls, jobs):
    print '%s: %s' % (url, repr(job.wait())[:50])

