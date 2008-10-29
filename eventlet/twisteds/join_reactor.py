"""Integrate eventlet with twisted's reactor mainloop.

You generally don't have to use it unless you need to call reactor.run()
yourself.
"""
from eventlet.hubs.twistedr import BaseTwistedHub
from eventlet.api import use_hub, _threadlocal
from eventlet.support import greenlet

use_hub(BaseTwistedHub)
assert not hasattr(_threadlocal, 'hub')
hub = _threadlocal.hub = _threadlocal.Hub(greenlet.getcurrent())

