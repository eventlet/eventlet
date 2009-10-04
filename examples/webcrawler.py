#! /usr/bin/env python
"""\
@file webcrawler.py

This is a simple web "crawler" that fetches a bunch of urls using a coroutine pool.  It fetches as
 many urls at time as coroutines in the pool.
"""

urls = ["http://www.google.com/intl/en_ALL/images/logo.gif",
        "http://us.i1.yimg.com/us.yimg.com/i/ww/beta/y3.gif",
        "http://eventlet.net"]

import time
from eventlet.green import urllib2
from eventlet import coros

def fetch(url):
    # we could do something interesting with the result, but this is
    # example code, so we'll just report that we did it
    print "%s fetching %s" % (time.asctime(), url)
    req = urllib2.urlopen(url)
    print "%s fetched %s (%s)" % (time.asctime(), url, len(req.read()))

pool = coros.CoroutinePool(max_size=4)
waiters = []
for url in urls:
    waiters.append(pool.execute(fetch, url))

# wait for all the coroutines to come back before exiting the process
for waiter in waiters:
    waiter.wait()


