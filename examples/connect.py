"""Spawn multiple greenlet-workers and collect their results.

Demonstrates how to use coros.Job.
"""
import sys
import string
from eventlet.api import sleep
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

def progress_indicator():
    while True:
        sys.stderr.write('.')
        sleep(0.5)

Job(progress_indicator)

urls = ['www.%s.com' % (x*3) for x in string.letters]
jobs = [Job(geturl, x) for x in urls]

print 'spawned %s jobs' % len(jobs)

# collect the results from workers, one by one
for url, job in zip(urls, jobs):
    sys.stderr.write('%s: ' % url)
    try:
        result = job.wait()
    except Exception, ex: # when using BaseException here and pressing Ctrl-C recv returns None sometimes
        sys.stderr.write('%s' % ex)
    else:
        sys.stderr.write('%s bytes: %s...' % (len(result), repr(result)[:40]))
    finally:
        sys.stderr.write('\n')

