import sys

from eventlet import patcher
from eventlet.green import select

patcher.inject('selectors', globals(), ('select', select))

del patcher

if sys.platform != 'win32':
    SelectSelector._select = staticmethod(select.select)
