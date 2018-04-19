import importlib
__MySQLdb = importlib.import_module('MySQLdb')

__all__ = __MySQLdb.__all__
__patched__ = ["connect", "Connect", 'Connection', 'connections']

from eventlet.patcher import slurp_properties
slurp_properties(
    __MySQLdb, globals(),
    ignore=__patched__, srckeys=dir(__MySQLdb))

from eventlet import tpool

__orig_connections = importlib.import_module('MySQLdb.connections')


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

cursors = importlib.import_module('MySQLdb.cursors')
converters = importlib.import_module('MySQLdb.converters')

# TODO support instantiating cursors.FooCursor objects directly
# TODO though this is a low priority, it would be nice if we supported
# subclassing eventlet.green.MySQLdb.connections.Connection
