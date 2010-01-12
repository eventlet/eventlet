from eventlet import api

def get_ident():
    """ Returns ``id()`` of current greenlet.  Useful for debugging."""
    return id(api.getcurrent())

class local(object):
    def __getattribute__(self, attr, g=get_ident):
        try:
            d = object.__getattribute__(self, '__dict__')
            return d.setdefault('__objs', {})[g()][attr]
        except KeyError:
            raise AttributeError(
                "No variable %s defined for the thread %s"
                % (attr, g()))

    def __setattr__(self, attr, value, g=get_ident):
        d = object.__getattribute__(self, '__dict__')
        d.setdefault('__objs', {}).setdefault(g(), {})[attr] = value

    def __delattr__(self, attr, g=get_ident):
        try:
            d = object.__getattribute__(self, '__dict__')            
            del d.setdefault('__objs', {})[g()][attr]
        except KeyError:
            raise AttributeError(
                "No variable %s defined for thread %s"
                % (attr, g()))
