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

import os

from eventlet.pools import Pool
from eventlet.processes import DeadProcess
from eventlet import saranwrap

class DatabaseConnector(object):
    """\
@brief This is an object which will maintain a collection of database
connection pools keyed on host,databasename"""
    def __init__(self, module, credentials, min_size = 0, max_size = 4, *args, **kwargs):
        """\
        @brief constructor
        @param min_size the minimum size of a child pool.
        @param max_size the maximum size of a child pool."""
        assert(module)
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
            dbpool = ConnectionPool(self._module, self._min_size, self._max_size, *self._args, **new_kwargs)
            self._databases[key] = dbpool

        return self._databases[key]


class ConnectionPool(Pool):
    """A pool which gives out saranwrapped database connections from a pool
    """
    def __init__(self, module, min_size = 0, max_size = 4, *args, **kwargs):
        assert(module)
        self._module = module
        self._args = args
        self._kwargs = kwargs
        Pool.__init__(self, min_size, max_size)

    def create(self):
        return saranwrap.wrap(self._module).connect(*self._args, **self._kwargs)

    def put(self, conn):
        # rollback any uncommitted changes, so that the next process
        # has a clean slate.  This also pokes the process to see if
        # it's dead or None
        try:
            conn.rollback()
        except (AttributeError, DeadProcess), e:
            conn = self.create()
        # TODO figure out if we're still connected to the database
        if conn is not None:
            Pool.put(self, conn)
        else:
            self.current_size -= 1
