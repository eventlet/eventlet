from eventlet.api import Greenlet

class SwitchingToDeadGreenlet(Exception):
    pass

def switch(other=None, value=None, exc=None):
    self = Greenlet.getcurrent()
    if other is None:
        other = self.parent
    if other is None:
        other = self
    if not (other or hasattr(other, 'run')):
        raise SwitchingToDeadGreenlet("Switching to dead greenlet %r %r %r" % (other, value, exc))
    if exc:
        return other.throw(exc)
    else:
        return other.switch(value)        

import warnings
warnings.warn("greenlib is deprecated; use greenlet methods directly", DeprecationWarning, stacklevel=2)
