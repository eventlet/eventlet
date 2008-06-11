#! /usr/bin/env python
"""\
@file webcrawler.py

This is a simple web "crawler" that fetches a bunch of urls using a coroutine pool.  It fetches as
 many urls at time as coroutines in the pool.

Copyright (c) 2007, Linden Research, Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

urls = ["http://www.google.com/intl/en_ALL/images/logo.gif",
        "http://wiki.secondlife.com/w/images/secondlife.jpg",
        "http://us.i1.yimg.com/us.yimg.com/i/ww/beta/y3.gif"]

import time
from eventlet import coros, httpc, util

# replace socket with a cooperative coroutine socket because httpc
# uses httplib, which uses socket.  Removing this serializes the http
# requests, because the standard socket is blocking.
util.wrap_socket_with_coroutine_socket()

def fetch(url):
    # we could do something interesting with the result, but this is
    # example code, so we'll just report that we did it
    print "%s fetching %s" % (time.asctime(), url)
    httpc.get(url)
    print "%s fetched %s" % (time.asctime(), url)

pool = coros.CoroutinePool(max_size=4)
waiters = []
for url in urls:
    waiters.append(pool.execute(fetch, url))

# wait for all the coroutines to come back before exiting the process
for waiter in waiters:
    waiter.wait()


