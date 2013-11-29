import six

if six.PY2:
    __MySQLdb = __import__('MySQLdb')
if six.PY3:
    __MySQLdb = __import__('pymysql')

__all__ = __MySQLdb.__all__
__patched__ = ["connect", "Connect", 'Connection', 'connections']

from eventlet.patcher import slurp_properties
slurp_properties(__MySQLdb, globals(), 
    ignore=__patched__, srckeys=dir(__MySQLdb))
                       
from eventlet import tpool

if six.PY2:
    __orig_connections = __import__('MySQLdb.connections').connections
if six.PY3:
    __orig_connections = __import__('pymysql.connections').connections

def Connection(*args, **kw):
    conn = tpool.execute(__orig_connections.Connection, *args, **kw)
    return tpool.Proxy(conn, autowrap_names=('cursor',))
connect = Connect = Connection

# replicate the MySQLdb.connections module but with a tpooled Connection factory
class MySQLdbConnectionsModule(object):
    pass
connections = MySQLdbConnectionsModule()
for var in dir(__orig_connections):
    if not var.startswith('__'):
        setattr(connections, var, getattr(__orig_connections, var))
connections.Connection = Connection

if six.PY2:
   cursors = __import__('MySQLdb.cursors').cursors
   converters = __import__('MySQLdb.converters').converters
if six.PY3:
   cursors = __import__('pymysql.cursors').cursors
   converters = __import__('pymysql.converters').converters

# TODO support instantiating cursors.FooCursor objects directly
# TODO though this is a low priority, it would be nice if we supported
# subclassing eventlet.green.MySQLdb.connections.Connection
