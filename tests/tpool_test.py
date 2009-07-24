# Copyright (c) 2007, Linden Research, Inc.
# Copyright (c) 2007, IBM Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from sys import stdout
import time
from unittest import TestCase, main
import random
import uuid

from eventlet import coros, api, tpool

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

one = 1
two = 2
three = 3

class TestTpool(TestCase):
    def setUp(self):
        # turn off exception printing, because we'll be deliberately
        # triggering exceptions in our tests
        tpool.QUIET = True

    def tearDown(self):
        tpool.QUIET = False

    def test_a_buncha_stuff(self):
        pool = coros.CoroutinePool(max_size=10)
        waiters = []
        for i in range(0,9):
            waiters.append(pool.execute(sender_loop,i))
        for waiter in waiters:
            waiter.wait()

    def test_wrap_tuple(self):
        my_tuple = (1, 2)
        prox = tpool.Proxy(my_tuple)
        self.assertEqual(prox[0], 1)
        self.assertEqual(prox[1], 2)
        self.assertEqual(len(my_tuple), 2)

    def test_wrap_string(self):
        my_object = "whatever"
        prox = tpool.Proxy(my_object)
        self.assertEqual(str(my_object), str(prox))
        self.assertEqual(len(my_object), len(prox))
        self.assertEqual(my_object.join(['a', 'b']), prox.join(['a', 'b']))

    def test_wrap_uniterable(self):
        # here we're treating the exception as just a normal class
        prox = tpool.Proxy(FloatingPointError())
        def index():
            prox[0]
        def key():
            prox['a']

        self.assertRaises(IndexError, index)
        self.assertRaises(TypeError, key)

    def test_wrap_dict(self):
        my_object = {'a':1}
        prox = tpool.Proxy(my_object)
        self.assertEqual('a', prox.keys()[0])
        self.assertEqual(1, prox['a'])
        self.assertEqual(str(my_object), str(prox))
        self.assertEqual(repr(my_object), repr(prox))
        self.assertEqual(`my_object`, `prox`)

    def test_wrap_module_class(self):
        prox = tpool.Proxy(uuid)
        self.assertEqual(tpool.Proxy, type(prox))
        id = prox.uuid4()
        self.assertEqual(id.get_version(), uuid.uuid4().get_version())
        self.assert_(repr(prox.uuid4))

    def test_wrap_eq(self):
        prox = tpool.Proxy(uuid)
        id1 = prox.uuid4()
        id2 = prox.UUID(str(id1))
        self.assertEqual(id1, id2)
        id3 = prox.uuid4()
        self.assert_(id1 != id3)

    def test_wrap_nonzero(self):
        prox = tpool.Proxy(uuid)
        id1 = prox.uuid4()
        self.assert_(bool(id1))
        prox2 = tpool.Proxy([1, 2, 3])
        self.assert_(bool(prox2))

    def test_multiple_wraps(self):
        prox1 = tpool.Proxy(uuid)
        prox2 = tpool.Proxy(uuid)
        x1 = prox1.uuid4()
        x2 = prox1.uuid4()
        del x2
        x3 = prox2.uuid4()

    def test_wrap_getitem(self):
        prox = tpool.Proxy([0,1,2])
        self.assertEqual(prox[0], 0)

    def test_wrap_setitem(self):
        prox = tpool.Proxy([0,1,2])
        prox[1] = 2
        self.assertEqual(prox[1], 2)

    def test_raising_exceptions(self):
        prox = tpool.Proxy(uuid)
        def nofunc():
            prox.never_name_a_function_like_this()
        self.assertRaises(AttributeError, nofunc)

    def assertLessThan(self, a, b):
        self.assert_(a < b, "%s is not less than %s" % (a, b))

    def test_variable_and_keyword_arguments_with_function_calls(self):
        import optparse
        parser = tpool.Proxy(optparse.OptionParser())
        z = parser.add_option('-n', action='store', type='string', dest='n')
        opts,args = parser.parse_args(["-nfoo"])
        self.assertEqual(opts.n, 'foo')

    def test_contention(self):
        from greentest import tpool_test
        prox = tpool.Proxy(tpool_test)

        pool = coros.CoroutinePool(max_size=4)
        waiters = []
        waiters.append(pool.execute(lambda: self.assertEquals(prox.one, 1)))
        waiters.append(pool.execute(lambda: self.assertEquals(prox.two, 2)))
        waiters.append(pool.execute(lambda: self.assertEquals(prox.three, 3)))
        for waiter in waiters:
            waiter.wait()

    def test_timeout(self):
        import time
        api.exc_after(0.1, api.TimeoutError())
        self.assertRaises(api.TimeoutError,
                          tpool.execute, time.sleep, 0.3)


    def dont_test_benchmark(self):
        """ Benchmark computing the amount of overhead tpool adds to function calls.  Rename to activate."""
        iterations = 10000
        def bench(f, *args, **kw):
            for i in xrange(iterations):
                f(*args, **kw)
        def noop():
            pass

        normal_results = []
        tpool_results = []
        for i in xrange(3):
            start = time.time()
            bench(noop)
            end = time.time()
            normal_results.append(end-start)

            start = time.time()
            bench(tpool.execute, noop)
            end = time.time()
            tpool_results.append(end-start)

        avg_normal = sum(normal_results)/len(normal_results)
        avg_tpool =  sum(tpool_results)/len(tpool_results)
        tpool_overhead = (avg_tpool-avg_normal)/iterations
        print "%s iterations\nTpool overhead is %s seconds per call.  Normal: %s; Tpool: %s" % (
            iterations, tpool_overhead, normal_results, tpool_results)


if __name__ == '__main__':
    main()
