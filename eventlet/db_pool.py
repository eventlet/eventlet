"""\
@file db_pool.py
@brief Uses saranwrap to implement a pool of nonblocking database connections to a db server.

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

import os, sys

from eventlet.pools import Pool
from eventlet.processes import DeadProcess
from eventlet import saranwrap

class DatabaseConnector(object):
    """\
@brief This is an object which will maintain a collection of database
connection pools keyed on host,databasename"""
    def __init__(self, module, credentials, min_size = 0, max_size = 4, conn_pool=None, *args, **kwargs):
        """\
        @brief constructor
        @param min_size the minimum size of a child pool.
        @param max_size the maximum size of a child pool."""
        assert(module)
        self._conn_pool_class = conn_pool
        if self._conn_pool_class is None:
            self._conn_pool_class = ConnectionPool
        self._module = module
        self._min_size = min_size
        self._max_size = max_size
        self._args = args
        self._kwargs = kwargs
        self._credentials = credentials  # this is a map of hostname to username/password
        self._databases = {}

    def credentials_for(self, host):
        if host in self._credentials:
            return self._credentials[host]
        else:
            return self._credentials.get('default', None)

    def get(self, host, dbname):
        key = (host, dbname)
        if key not in self._databases:
            new_kwargs = self._kwargs.copy()
            new_kwargs['db'] = dbname
            new_kwargs['host'] = host
            new_kwargs.update(self.credentials_for(host))
            dbpool = self._conn_pool_class(self._module, min_size=self._min_size, max_size=self._max_size,
                                           *self._args, **new_kwargs)
            self._databases[key] = dbpool

        return self._databases[key]

class BaseConnectionPool(Pool):
    # *TODO: we need to expire and close connections if they've been
    # idle for a while, so that system-wide connection count doesn't
    # monotonically increase forever
    def __init__(self, db_module, min_size = 0, max_size = 4, *args, **kwargs):
        assert(db_module)
        self._db_module = db_module
        self._args = args
        self._kwargs = kwargs
        super(BaseConnectionPool, self).__init__(min_size, max_size)

    def get(self):
        # wrap the connection for easier use
        conn = super(BaseConnectionPool, self).get()
        return PooledConnectionWrapper(conn, self)

    def put(self, conn):
        # rollback any uncommitted changes, so that the next client
        # has a clean slate.  This also pokes the connection to see if
        # it's dead or None
        try:
            conn.rollback()
        except AttributeError, e:
            # this means it's already been destroyed, so we don't need to print anything
            conn = None
        except:
            # we don't care what the exception was, we just know the
            # connection is dead
            print "WARNING: connection.rollback raised: %s" % (sys.exc_info()[1])
            conn = None

        # unwrap the connection for storage
        if isinstance(conn, GenericConnectionWrapper):
            if conn:
                base = conn._base
                conn._destroy()
                conn = base
            else:
                conn = None
                
        if conn is not None:
            super(BaseConnectionPool, self).put(conn)
        else:
            self.current_size -= 1
    

class SaranwrappedConnectionPool(BaseConnectionPool):
    """A pool which gives out saranwrapped database connections from a pool
    """
    def create(self):
        return saranwrap.wrap(self._db_module).connect(*self._args, **self._kwargs)

class TpooledConnectionPool(BaseConnectionPool):
    """A pool which gives out tpool.Proxy-based database connections from a pool.
    """
    def create(self):
        from eventlet import tpool
        try:
            # *FIX: this is a huge hack that will probably only work for MySQLdb
            autowrap = (self._db_module.cursors.DictCursor,)
        except:
            autowrap = ()
        return tpool.Proxy(self._db_module.connect(*self._args, **self._kwargs),
                           autowrap=autowrap)

class RawConnectionPool(BaseConnectionPool):
    """A pool which gives out plain database connections from a pool.
    """
    def create(self):
        return self._db_module.connect(*self._args, **self._kwargs)

# default connection pool is the tpool one
ConnectionPool = TpooledConnectionPool


class GenericConnectionWrapper(object):
    def __init__(self, baseconn):
        self._base = baseconn
    def __enter__(self): return self._base.__enter__()
    def __exit__(self, exc, value, tb): return self._base.__exit__(exc, value, tb)
    def __repr__(self): return self._base.__repr__()
    def affected_rows(self): return self._base.affected_rows()
    def autocommit(self,*args, **kwargs): return self._base.autocommit(*args, **kwargs)
    def begin(self): return self._base.begin()
    def change_user(self,*args, **kwargs): return self._base.change_user(*args, **kwargs)
    def character_set_name(self,*args, **kwargs): return self._base.character_set_name(*args, **kwargs)
    def close(self,*args, **kwargs): return self._base.close(*args, **kwargs)
    def commit(self,*args, **kwargs): return self._base.commit(*args, **kwargs)
    def cursor(self, cursorclass=None, **kwargs): return self._base.cursor(cursorclass, **kwargs)
    def dump_debug_info(self,*args, **kwargs): return self._base.dump_debug_info(*args, **kwargs)
    def errno(self,*args, **kwargs): return self._base.errno(*args, **kwargs)
    def error(self,*args, **kwargs): return self._base.error(*args, **kwargs)
    def errorhandler(self, conn, curs, errcls, errval): return self._base.errorhandler(conn, curs, errcls, errval)
    def literal(self, o): return self._base.literal(o)
    def set_character_set(self, charset): return self._base.set_character_set(charset)
    def set_sql_mode(self, sql_mode): return self._base.set_sql_mode(sql_mode)
    def show_warnings(self): return self._base.show_warnings()
    def warning_count(self): return self._base.warning_count()
    def literal(self, o): return self._base.literal(o)
    def ping(self,*args, **kwargs): return self._base.ping(*args, **kwargs)
    def query(self,*args, **kwargs): return self._base.query(*args, **kwargs)
    def rollback(self,*args, **kwargs): return self._base.rollback(*args, **kwargs)
    def select_db(self,*args, **kwargs): return self._base.select_db(*args, **kwargs)
    def set_server_option(self,*args, **kwargs): return self._base.set_server_option(*args, **kwargs)
    def set_character_set(self, charset): return self._base.set_character_set(charset)
    def set_sql_mode(self, sql_mode): return self._base.set_sql_mode(sql_mode)
    def server_capabilities(self,*args, **kwargs): return self._base.server_capabilities(*args, **kwargs)
    def show_warnings(self): return self._base.show_warnings()
    def shutdown(self,*args, **kwargs): return self._base.shutdown(*args, **kwargs)
    def sqlstate(self,*args, **kwargs): return self._base.sqlstate(*args, **kwargs)
    def stat(self,*args, **kwargs): return self._base.stat(*args, **kwargs)
    def store_result(self,*args, **kwargs): return self._base.store_result(*args, **kwargs)
    def string_literal(self,*args, **kwargs): return self._base.string_literal(*args, **kwargs)
    def thread_id(self,*args, **kwargs): return self._base.thread_id(*args, **kwargs)
    def use_result(self,*args, **kwargs): return self._base.use_result(*args, **kwargs)
    def warning_count(self): return self._base.warning_count()


class PooledConnectionWrapper(GenericConnectionWrapper):
    """ A connection wrapper where:
    - the close method returns the connection to the pool instead of closing it directly
    - you can do if conn:
    - returns itself to the pool if it gets garbage collected
    """
    def __init__(self, baseconn, pool):
        super(PooledConnectionWrapper, self).__init__(baseconn)
        self._pool = pool

    def __nonzero__(self):
        return (hasattr(self, '_base') and bool(self._base))

    def _destroy(self):
        self._pool = None
        try:
            del self._base
        except AttributeError:
            pass
        
    def close(self):
        """ Return the connection to the pool, and remove the
        reference to it so that you can't use it again through this
        wrapper object.
        """
        if self and self._pool:
            self._pool.put(self)
        self._destroy()
    
    def __del__(self):
        self.close()
