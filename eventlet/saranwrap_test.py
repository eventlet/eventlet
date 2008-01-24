#!/usr/bin/python
# @file test_saranwrap.py
# @brief Test cases for saranwrap.
#
# Copyright (c) 2007, Linden Research, Inc.
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from eventlet import saranwrap, coros

import os
import sys
import tempfile
import time
import unittest
import uuid

# random test stuff
def list_maker():
    return [0,1,2]

one = 1
two = 2
three = 3

class TestSaranwrap(unittest.TestCase):
    def assert_server_exists(self, prox):
        self.assert_(saranwrap.status(prox))
        prox.foo = 0
        self.assertEqual(0, prox.foo)
        
    def test_wrap_tuple(self):
        my_tuple = (1, 2)
        prox = saranwrap.wrap(my_tuple)
        self.assertEqual(prox[0], 1)
        self.assertEqual(prox[1], 2)
        self.assertEqual(len(my_tuple), 2)

    def test_wrap_string(self):
        my_object = "whatever"
        prox = saranwrap.wrap(my_object)
        self.assertEqual(str(my_object), str(prox))
        self.assertEqual(len(my_object), len(prox))
        self.assertEqual(my_object.join(['a', 'b']), prox.join(['a', 'b']))

    def test_wrap_uniterable(self):
        # here we're treating the exception as just a normal class
        prox = saranwrap.wrap(FloatingPointError())
        def index():
            prox[0]
        def key():
            prox['a']

        self.assertRaises(IndexError, index)
        self.assertRaises(TypeError, key)

    def test_wrap_dict(self):
        my_object = {'a':1}
        prox = saranwrap.wrap(my_object)
        self.assertEqual('a', prox.keys()[0])
        self.assertEqual(1, prox['a'])
        self.assertEqual(str(my_object), str(prox))
        self.assertEqual('saran:' + repr(my_object), repr(prox))
        self.assertEqual('saran:' + `my_object`, `prox`)

    def test_wrap_module_class(self):
        prox = saranwrap.wrap(uuid)
        self.assertEqual(saranwrap.Proxy, type(prox))
        id = prox.uuid4()
        self.assertEqual(id.get_version(), uuid.uuid4().get_version())
        self.assert_(repr(prox.uuid4))

    def test_wrap_eq(self):
        prox = saranwrap.wrap(uuid)
        id1 = prox.uuid4()
        id2 = prox.UUID(str(id1))
        self.assertEqual(id1, id2)
        id3 = prox.uuid4()
        self.assert_(id1 != id3)

    def test_wrap_nonzero(self):
        prox = saranwrap.wrap(uuid)
        id1 = prox.uuid4()
        self.assert_(bool(id1))
        prox2 = saranwrap.wrap([1, 2, 3])
        self.assert_(bool(prox2))

    def test_multiple_wraps(self):
        prox1 = saranwrap.wrap(uuid)
        prox2 = saranwrap.wrap(uuid)
        x1 = prox1.uuid4()
        x2 = prox1.uuid4()
        del x2
        x3 = prox2.uuid4()

    def test_dict_passthru(self):
        prox = saranwrap.wrap(uuid)
        x = prox.uuid4()
        self.assertEqual(type(x.__dict__), saranwrap.ObjectProxy)
        # try it all on one line just for the sake of it
        self.assertEqual(type(saranwrap.wrap(uuid).uuid4().__dict__), saranwrap.ObjectProxy)

    def test_is_value(self):
        server = saranwrap.Server(None, None, None)
        self.assert_(server.is_value(None))

    def test_wrap_getitem(self):
        prox = saranwrap.wrap([0,1,2])
        self.assertEqual(prox[0], 0)

    def test_wrap_setitem(self):
        prox = saranwrap.wrap([0,1,2])
        prox[1] = 2
        self.assertEqual(prox[1], 2)

    def test_raising_exceptions(self):
        prox = saranwrap.wrap(uuid)
        def nofunc():
            prox.never_name_a_function_like_this()
        self.assertRaises(AttributeError, nofunc)

    def test_raising_weird_exceptions(self):
        # the recursion is killing me!
        prox = saranwrap.wrap(saranwrap)
        try:
            prox.raise_a_weird_error()
            self.assert_(False)
        except:
            import sys
            ex = sys.exc_info()[0]
            self.assertEqual(ex, "oh noes you can raise a string")
        self.assert_server_exists(prox)

    def test_unpicklable_server_exception(self):
        prox = saranwrap.wrap(saranwrap)
        def unpickle():
            prox.raise_an_unpicklable_error()

        self.assertRaises(saranwrap.UnrecoverableError, unpickle)

        # It's basically dead
        #self.assert_server_exists(prox)

    def test_pickleable_server_exception(self):
        prox = saranwrap.wrap(saranwrap)
        def fperror():
            prox.raise_standard_error()

        self.assertRaises(FloatingPointError, fperror)
        self.assert_server_exists(prox)

    def test_print_does_not_break_wrapper(self):
        prox = saranwrap.wrap(saranwrap)
        prox.print_string('hello')
        self.assert_server_exists(prox)

    def test_stderr_does_not_break_wrapper(self):
        prox = saranwrap.wrap(saranwrap)
        prox.err_string('goodbye')
        self.assert_server_exists(prox)

    def assertLessThan(self, a, b):
        self.assert_(a < b, "%s is not less than %s" % (a, b))

    def test_status(self):
        prox = saranwrap.wrap(time)
        a = prox.gmtime(0)
        status = saranwrap.status(prox)
        self.assertEqual(status['object_count'], 1)
        self.assertEqual(status['next_id'], 2)
        self.assert_(status['pid'])  # can't guess what it will be
        # status of an object should be the same as the module
        self.assertEqual(saranwrap.status(a), status)
        # create a new one then immediately delete it
        prox.gmtime(1)
        is_id = prox.ctime(1) # sync up deletes
        status = saranwrap.status(prox)
        self.assertEqual(status['object_count'], 1)
        self.assertEqual(status['next_id'], 3)
        prox2 = saranwrap.wrap(uuid)
        self.assert_(status['pid'] != saranwrap.status(prox2)['pid'])
    
    def test_del(self):
        prox = saranwrap.wrap(time)
        delme = prox.gmtime(0)
        status_before = saranwrap.status(prox)
        #print status_before['objects']
        del delme
        # need to do an access that doesn't create an object
        # in order to sync up the deleted objects
        prox.ctime(1)
        status_after = saranwrap.status(prox)
        #print status_after['objects']
        self.assertLessThan(status_after['object_count'], status_before['object_count'])

    def test_variable_and_keyword_arguments_with_function_calls(self):
        import optparse
        prox = saranwrap.wrap(optparse)
        parser = prox.OptionParser()
        z = parser.add_option('-n', action='store', type='string', dest='n')
        opts,args = parser.parse_args(["-nfoo"])
        self.assertEqual(opts.n, 'foo')

    def test_original_proxy_going_out_of_scope(self):
        def make_uuid():
            prox = saranwrap.wrap(uuid)
            # after this function returns, prox should fall out of scope
            return prox.uuid4()
        tid = make_uuid()
        self.assertEqual(tid.get_version(), uuid.uuid4().get_version())
        def make_list():
            from eventlet import saranwrap_test
            prox = saranwrap.wrap(saranwrap_test.list_maker)
            # after this function returns, prox should fall out of scope
            return prox()
        proxl = make_list()
        self.assertEqual(proxl[2], 2)

    def test_status_of_none(self):
        try:
            saranwrap.status(None)
            self.assert_(False)
        except AttributeError, e:
            pass

    def test_not_inheriting_pythonpath(self):
        # construct a fake module in the temp directory
        temp_dir = tempfile.mkdtemp("saranwrap_test")
        fp = open(os.path.join(temp_dir, "jitar_hero.py"), "w")
        fp.write("""import os, sys
pypath = os.environ['PYTHONPATH']
sys_path = sys.path""")
        fp.close()

        # this should fail because we haven't stuck the temp_dir in our path yet
        prox = saranwrap.wrap_module('jitar_hero')
        import cPickle
        try:
            prox.pypath
            self.fail()
        except cPickle.UnpicklingError:
            pass

        # now try to saranwrap it
        sys.path.append(temp_dir)
        try:
            import jitar_hero
            prox = saranwrap.wrap(jitar_hero)
            self.assert_(prox.pypath.count(temp_dir))
            self.assert_(prox.sys_path.count(temp_dir))
        finally:
            import shutil
            shutil.rmtree(temp_dir)
            sys.path.remove(temp_dir)
                        
    def test_contention(self):
        from eventlet import saranwrap_test
        prox = saranwrap.wrap(saranwrap_test)
                
        pool = coros.CoroutinePool(max_size=4)
        waiters = []
        waiters.append(pool.execute(lambda: self.assertEquals(prox.one, 1)))
        waiters.append(pool.execute(lambda: self.assertEquals(prox.two, 2)))
        waiters.append(pool.execute(lambda: self.assertEquals(prox.three, 3)))
        for waiter in waiters:
            waiter.wait()

    def test_copy(self):
        import copy
        compound_object = {'a':[1,2,3]}
        prox = saranwrap.wrap(compound_object)
        def make_assertions(copied):
            self.assert_(isinstance(copied, dict))
            self.assert_(isinstance(copied['a'], list))
            self.assertEquals(copied, compound_object)
            self.assertNotEqual(id(compound_object), id(copied))

        make_assertions(copy.copy(prox))
        make_assertions(copy.deepcopy(prox))

    def test_list_of_functions(self):
        return # this test is known to fail, we can implement it sometime in the future if we wish
        from eventlet import saranwrap_test
        prox = saranwrap.wrap([saranwrap_test.list_maker])
        self.assertEquals(list_maker(), prox[0]())
                              
    def test_detection_of_server_crash(self):
        # make the server crash here
        pass

    def test_equality_with_local_object(self):
        # we'll implement this if there's a use case for it
        pass

    def test_non_blocking(self):
        # here we test whether it's nonblocking
        pass

if __name__ == '__main__':
    unittest.main()
