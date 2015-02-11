from eventlet import patcher
from eventlet.green import time

patcher.inject('http.cookies', globals())
_getdate = patcher.patch_function(_getdate, ('time', time))

del patcher
