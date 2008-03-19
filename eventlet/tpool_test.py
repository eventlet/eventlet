"""\
@file tpool_test.py

Copyright (c) 2007, Linden Research, Inc.
Copyright (c) 2007, IBM Corp.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os, socket, time, threading
from eventlet import coros, api,  tpool, tests

from eventlet.tpool import erpc
from sys import stdout

import random
r = random.WichmannHill()

_g_debug = False

def prnt(msg):
    if _g_debug:
        print msg
        
class yadda(object):
    def __init__(self):
        pass

    def foo(self,when,n=None):
        assert(n is not None)
        prnt("foo: %s, %s" % (when,n))
        time.sleep(r.random()/20.0)
        return n

def sender_loop(pfx):
    n = 0
    obj = tpool.Proxy(yadda())
    while n < 10:
        if not (n % 5):
            stdout.write('.')
            stdout.flush()
        api.sleep(0)
        now = time.time()
        prnt("%s: send (%s,%s)" % (pfx,now,n))
        rv = obj.foo(now,n=n)
        prnt("%s: recv %s" % (pfx, rv))
        assert(n == rv)
        api.sleep(0)
        n += 1


class TestTpool(tests.TestCase):    
    def test1(self):
        pool = coros.CoroutinePool(max_size=10)
        waiters = []
        for i in range(0,9):
            waiters.append(pool.execute(sender_loop,i))
        for waiter in waiters:
            waiter.wait()


if __name__ == '__main__':
    tests.main()
