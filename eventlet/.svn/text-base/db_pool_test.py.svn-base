#!/usr/bin/python
# @file test_mysql_pool.py
# @brief Test cases for mysql_pool
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

import os.path

from eventlet import api, coros, tests
from eventlet import db_pool

class DBTester(object):
    def setUp(self):
        self.create_db()
        self.connection = None
        connection = self._dbmodule.connect(**self._auth)
        cursor = connection.cursor()
        cursor.execute("""CREATE  TABLE gargleblatz 
        (
        a INTEGER
        ) ENGINE = InnoDB;""")
        connection.commit()
        cursor.close()
        
    def tearDown(self):
        if self.connection is not None:
            self.connection.close()
        self.drop_db()

    def set_up_test_table(self, connection = None):
        if connection is None:
            if self.connection is None:
                self.connection = self._dbmodule.connect(**self._auth)
            connection = self.connection

        cursor = connection.cursor()
        cursor.execute("""CREATE TEMPORARY TABLE test_table 
        (
        row_id INTEGER PRIMARY KEY AUTO_INCREMENT, 
        value_int INTEGER, 
        value_float FLOAT, 
        value_string VARCHAR(200), 
        value_uuid CHAR(36), 
        value_binary BLOB, 
        value_binary_string VARCHAR(200) BINARY, 
        value_enum ENUM('Y','N'), 
        created TIMESTAMP 
        ) ENGINE = InnoDB;""")
        connection.commit()
        cursor.close()

class TestDBConnectionPool(DBTester):
    def setUp(self):
        super(TestDBConnectionPool, self).setUp()
        self.pool = self.create_pool()
        self.connection = self.pool.get()
    
    def tearDown(self):
        self.pool.put(self.connection)
        super(TestDBConnectionPool, self).tearDown()

    def assert_cursor_works(self, cursor):
        cursor.execute("show full processlist")
        rows = cursor.fetchall()
        self.assert_(rows)

    def test_connecting(self):
        self.assert_(self.connection is not None)

    def test_create_cursor(self):
        cursor = self.connection.cursor()
        cursor.close()

    def test_run_query(self):
        cursor = self.connection.cursor()
        self.assert_cursor_works(cursor)
        cursor.close()

    def test_run_bad_query(self):
        cursor = self.connection.cursor()
        try:
            cursor.execute("garbage blah blah")
            self.assert_(False)
        except AssertionError:
            raise
        except Exception, e:
            pass
        cursor.close()

    def test_put_none(self):
        # the pool is of size 1, and its only connection is out
        self.assert_(self.pool.free() == 0)
        self.pool.put(None)
        # ha ha we fooled it into thinking that we had a dead process
        self.assert_(self.pool.free() == 1)
        conn2 = self.pool.get()
        self.assert_(conn2 is not None)
        self.assert_(conn2.cursor)
        del conn2

    def test_close_does_a_put(self):
        self.assert_(self.pool.free() == 0)
        self.connection.close()
        self.assert_(self.pool.free() == 1)
        self.assertRaises(AttributeError, self.connection.cursor)

    def test_deletion_does_a_put(self):
        self.assert_(self.pool.free() == 0)
        self.connection = None
        self.assert_(self.pool.free() == 1)

    def test_put_doesnt_double_wrap(self):
        self.pool.put(self.connection)
        conn = self.pool.get()
        self.assert_(not isinstance(conn._base, db_pool.PooledConnectionWrapper))

    def test_bool(self):
        self.assert_(self.connection)
        self.connection.close()
        self.assert_(not self.connection)

    def fill_test_table(self, conn):
        curs = conn.cursor()
        for i in range(1000):
            curs.execute('insert into test_table (value_int) values (%s)' % i)
        conn.commit()

    def test_returns_immediately(self):
        self.pool = self.create_pool()
        conn = self.pool.get()
        self.set_up_test_table(conn)
        self.fill_test_table(conn)
        curs = conn.cursor()
        results = []
        SHORT_QUERY = "select * from test_table"
        evt = coros.event()
        def a_query():
            self.assert_cursor_works(curs)
            curs.execute(SHORT_QUERY)
            results.append(2)
            evt.send()
        evt2 = coros.event()
        api.spawn(a_query)
        results.append(1)
        self.assertEqual([1], results)
        evt.wait()
        self.assertEqual([1, 2], results)

    def test_connection_is_clean_after_put(self):
        self.pool = self.create_pool()
        conn = self.pool.get()
        self.set_up_test_table(conn)
        curs = conn.cursor()
        for i in range(10):
            curs.execute('insert into test_table (value_int) values (%s)' % i)
        # do not commit  :-)
        self.pool.put(conn)
        del conn
        conn2 = self.pool.get()
        curs2 = conn2.cursor()
        for i in range(10):
            curs2.execute('insert into test_table (value_int) values (%s)' % i)
        conn2.commit()
        rows = curs2.execute("select * from test_table")
        # we should have only inserted them once
        self.assertEqual(10, rows)

    def test_visibility_from_other_connections(self):
        # *FIX: use some non-indra-specific table for testing (can't use a temp table)
        self.pool = self.create_pool(3)
        conn = self.pool.get()
        conn2 = self.pool.get()
        curs = conn.cursor()
        try:
            curs2 = conn2.cursor()
            rows2 = curs2.execute("insert into gargleblatz (a) values (%s)" % (314159))
            self.assertEqual(rows2, 1)
            conn2.commit()
            selection_query = "select * from gargleblatz"
            rows2 = curs2.execute(selection_query)
            self.assertEqual(rows2, 1)
            del curs2
            del conn2
            # create a new connection, it should see the addition
            conn3 = self.pool.get()
            curs3 = conn3.cursor()
            rows3 = curs3.execute(selection_query)
            self.assertEqual(rows3, 1)
            # now, does the already-open connection see it?
            rows = curs.execute(selection_query)
            self.assertEqual(rows, 1)
        finally:
            # clean up my litter
            curs.execute("delete from gargleblatz where a=314159")
            conn.commit()
        

    def test_two_simultaneous_connections(self):
        self.pool = self.create_pool(2)
        conn = self.pool.get()
        self.set_up_test_table(conn)
        self.fill_test_table(conn)
        curs = conn.cursor()
        conn2 = self.pool.get()
        self.set_up_test_table(conn2)
        self.fill_test_table(conn2)
        curs2 = conn2.cursor()
        results = []
        LONG_QUERY = "select * from test_table"
        SHORT_QUERY = "select * from test_table where row_id <= 20"

        evt = coros.event()
        def long_running_query():
            self.assert_cursor_works(curs)
            curs.execute(LONG_QUERY)
            results.append(1)
            evt.send()
        evt2 = coros.event()
        def short_running_query():
            self.assert_cursor_works(curs2)
            curs2.execute(SHORT_QUERY)
            results.append(2)
            evt2.send()

        api.spawn(long_running_query)
        api.spawn(short_running_query)
        evt.wait()
        evt2.wait()
        #print "results %s" % results
        results.sort()
        self.assertEqual([1, 2], results)


class TestTpoolConnectionPool(TestDBConnectionPool):
    def create_pool(self, max_items = 1):
        return db_pool.TpooledConnectionPool(self._dbmodule, 0, max_items, **self._auth)


class TestSaranwrapConnectionPool(TestDBConnectionPool):
    def create_pool(self, max_items = 1):
        return db_pool.SaranwrappedConnectionPool(self._dbmodule, 0, max_items, **self._auth)

class TestMysqlConnectionPool(object):
    def setUp(self):
        import MySQLdb
        self._dbmodule = MySQLdb
        try:
            import simplejson
            import os.path
            auth_utf8 = simplejson.load(open(os.path.join(os.path.dirname(__file__), 'auth.json')))
            # have to convert unicode objects to str objects because mysqldb is dum
            self._auth = dict([(str(k), str(v))
                         for k, v in auth_utf8.items()])
        except (IOError, ImportError), e:
            self._auth = {'host': 'localhost','user': 'root','passwd': '','db': 'persist0'}
        super(TestMysqlConnectionPool, self).setUp()

    def create_db(self):
        auth = self._auth.copy()
        try:
            self.drop_db()
        except Exception:
            pass
        dbname = auth.pop('db')
        db = self._dbmodule.connect(**auth).cursor()
        db.execute("create database "+dbname)
        db.close()
        del db

    def drop_db(self):
        db = self._dbmodule.connect(**self._auth).cursor()
        db.execute("drop database "+self._auth['db'])
        db.close()
        del db

class TestMysqlTpool(TestMysqlConnectionPool, TestTpoolConnectionPool, tests.TestCase):
    pass

class TestMysqlSaranwrap(TestMysqlConnectionPool, TestSaranwrapConnectionPool, tests.TestCase):
    pass


if __name__ == '__main__':
    try:
        import MySQLdb
    except ImportError:
        print "Unable to import MySQLdb, skipping db_pool_test."
    else:
        tests.main()
else:
    import MySQLdb
