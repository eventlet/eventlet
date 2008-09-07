"""\
@file db_pool.py
@brief A pool of nonblocking database connections.

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

from collections import deque
import os
import sys
import time

from eventlet.pools import Pool
from eventlet.processes import DeadProcess
from eventlet import api

class ConnectTimeout(Exception):
    pass

class DatabaseConnector(object):
    """\
@brief This is an object which will maintain a collection of database
connection pools keyed on host,databasename"""
    def __init__(self, module, credentials, 
                 conn_pool=None, *args, **kwargs):
        """\
        @brief constructor
        @param min_size the minimum size of a child pool.
        @param max_size the maximum size of a child pool."""
        assert(module)
        self._conn_pool_class = conn_pool
        if self._conn_pool_class is None:
            self._conn_pool_class = ConnectionPool
        self._module = module
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
            dbpool = self._conn_pool_class(self._module,
                *self._args, **new_kwargs)
            self._databases[key] = dbpool

        return self._databases[key]


class BaseConnectionPool(Pool):
    def __init__(self, db_module, 
                       min_size = 0, max_size = 4, 
                       max_idle = 10, max_age = 30,
                       connect_timeout = 5,
                       *args, **kwargs):
        """
        Constructs a pool with at least *min_size* connections and at most
        *max_size* connections.  Uses *db_module* to construct new connections.
        
        The *max_idle* parameter determines how long pooled connections can
        remain idle, in seconds.  After *max_idle* seconds have elapsed 
        without the connection being used, the pool closes the connection.  
        
        *max_age* is how long any particular connection is allowed to live.
        Connections that have been open for longer than *max_age* seconds are
        closed, regardless of idle time.  If *max_age* is 0, all connections are 
        closed on return to the pool, reducing it to a concurrency limiter.
        
        *connect_timeout* is the duration in seconds that the pool will wait 
        before timing out on connect() to the database.  If triggered, the
        timeout will raise a ConnectTimeout from get().
        
        The remainder of the arguments are used as parameters to the
        *db_module*'s connection constructor.
        """
        assert(db_module)
        self._db_module = db_module
        self._args = args
        self._kwargs = kwargs
        self.max_idle = max_idle
        self.max_age = max_age
        self.connect_timeout = connect_timeout
        self._expiration_timer = None
        super(BaseConnectionPool, self).__init__(min_size=min_size, 
                                                 max_size=max_size,
                                                 order_as_stack=True)
        
    def _schedule_expiration(self):
        """ Sets up a timer that will call _expire_old_connections when the 
        oldest connection currently in the free pool is ready to expire.  This
        is the earliest possible time that a connection could expire, thus, the
        timer will be running as infrequently as possible without missing a 
        possible expiration.
        
        If this function is called when a timer is already scheduled, it does 
        nothing.
        
        If max_age or max_idle is 0, _schedule_expiration likewise does nothing.
        """
        if self.max_age is 0 or self.max_idle is 0:
            # expiration is unnecessary because all connections will be expired
            # on put
            return
        
        if ( self._expiration_timer is not None 
             and not getattr(self._expiration_timer, 'called', False)
             and not getattr(self._expiration_timer, 'cancelled', False) ):
            # the next timer is already scheduled
            return 
            
        try:
            now = time.time()
            self._expire_old_connections(now)
            # the last item in the list, because of the stack ordering,
            # is going to be the most-idle
            idle_delay = (self.free_items[-1][0] - now) + self.max_idle
            oldest = min([t[1] for t in self.free_items])
            age_delay = (oldest - now) + self.max_age
            
            next_delay = min(idle_delay, age_delay)
        except IndexError, ValueError:
            # no free items, unschedule ourselves
            self._expiration_timer = None
            return
        
        if next_delay > 0:
            # set up a continuous self-calling loop
            self._expiration_timer = api.call_after(next_delay,
                                                    self._schedule_expiration)
        
    def _expire_old_connections(self, now):
        """ Iterates through the open connections contained in the pool, closing
        ones that have remained idle for longer than max_idle seconds, or have
        been in existence for longer than max_age seconds.
        
        *now* is the current time, as returned by time.time().
        """
        original_count = len(self.free_items)
        new_free = [
            (last_used, created_at, conn)
            for last_used, created_at, conn in self.free_items
            if not self._is_expired(now, last_used, created_at, conn)]
        self.free_items.clear()
        self.free_items.extend(new_free)
        
        # adjust the current size counter to account for expired 
        # connections
        self.current_size -= original_count - len(self.free_items)

    def _is_expired(self, now, last_used, created_at, conn):
        """ Returns true and closes the connection if it's expired."""
        if ( self.max_idle <= 0
             or self.max_age <= 0
             or now - last_used > self.max_idle
             or now - created_at > self.max_age ):
            self._safe_close(conn, quiet=True)
            return True
        return False
        
    def _unwrap_connection(self, conn):
        """ If the connection was wrapped by a subclass of
        BaseConnectionWrapper and is still functional (as determined
        by the __nonzero__ method), returns the unwrapped connection.
        If anything goes wrong with this process, returns None.
        """
        base = None
        try:
            if conn:
                base = conn._base
                conn._destroy()
            else:
                base = None
        except AttributeError:
            pass
        return base

    def _safe_close(self, conn, quiet = False):
        """ Closes the (already unwrapped) connection, squelching any
        exceptions."""
        try:
            conn.close()
        except KeyboardInterrupt:
            raise
        except AttributeError:
            pass # conn is None, or junk
        except:
            if not quiet:
                print "Connection.close raised: %s" % (sys.exc_info()[1])

    def get(self):
        conn = super(BaseConnectionPool, self).get()
        # if the call to get() draws from the free pool, it will come
        # back as a tuple
        if isinstance(conn, tuple):
            _last_used, created_at, conn = conn
        else:
            created_at = time.time()
        
        # wrap the connection so the consumer can call close() safely
        wrapped = PooledConnectionWrapper(conn, self)
        # annotating the wrapper so that when it gets put in the pool
        # again, we'll know how old it is
        wrapped._db_pool_created_at = created_at
        return wrapped

    def put(self, conn):
        created_at = getattr(conn, '_db_pool_created_at', 0)

        # rollback any uncommitted changes, so that the next client
        # has a clean slate.  This also pokes the connection to see if
        # it's dead or None
        try:
            conn.rollback()
        except KeyboardInterrupt:
            raise
        except:
            # we don't care what the exception was, we just know the
            # connection is dead
            print "WARNING: connection.rollback raised: %s" % (sys.exc_info()[1])
            conn = None
                
        base = self._unwrap_connection(conn)
        now = time.time()
        if (base is not None 
            and not self._is_expired(now, now, created_at, base)):
            super(BaseConnectionPool, self).put( (now, created_at, base) )
        else:
            self.current_size -= 1
        
        self._schedule_expiration()

    def clear(self):
        """ Close all connections that this pool still holds a reference to, 
        and removes all references to them.
        """
        if self._expiration_timer:
            self._expiration_timer.cancel()
        for _last_used, _created_at, conn in self.free_items:
            self._safe_close(conn, quiet=True)
        self.free_items.clear()
            
    def __del__(self):
        self.clear()
    

class SaranwrappedConnectionPool(BaseConnectionPool):
    """A pool which gives out saranwrapped database connections.
    """
    def create(self):
        return self.connect(self._db_module,
                                    self.connect_timeout,
                                    *self._args,
                                    **self._kwargs)

    def connect(self, db_module, connect_timeout, *args, **kw):
        timeout = api.exc_after(connect_timeout, ConnectTimeout())
        try:
            from eventlet import saranwrap
            return saranwrap.wrap(db_module).connect(*args, **kw)
        finally:
            timeout.cancel()
            
    connect = classmethod(connect)
        

class TpooledConnectionPool(BaseConnectionPool):
    """A pool which gives out tpool.Proxy-based database connections.
    """
    def create(self):
        return self.connect(self._db_module,
                                    self.connect_timeout,
                                    *self._args,
                                    **self._kwargs)

    def connect(self, db_module, connect_timeout, *args, **kw):
        timeout = api.exc_after(connect_timeout, ConnectTimeout())
        try:
            from eventlet import tpool
            try:
                # *FIX: this is a huge hack that will probably only work for MySQLdb
                autowrap = (db_module.cursors.DictCursor,)
            except:
                autowrap = ()
            conn = tpool.execute(db_module.connect, *args, **kw)
            return tpool.Proxy(conn, autowrap=autowrap)
        finally:
            timeout.cancel()

    connect = classmethod(connect)

class RawConnectionPool(BaseConnectionPool):
    """A pool which gives out plain database connections.
    """
    def create(self):
        return self.connect(self._db_module,
                                    self.connect_timeout,
                                    *self._args,
                                    **self._kwargs)

    def connect(self, db_module, connect_timeout, *args, **kw):
        timeout = api.exc_after(connect_timeout, ConnectTimeout())
        try:
            return db_module.connect(*args, **kw)
        finally:
            timeout.cancel()

    connect = classmethod(connect)


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
    - bool(conn) returns a reasonable value
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
