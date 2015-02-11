from eventlet import patcher
from eventlet.green import os, socket
from eventlet.green.urllib import parse as urllib_parse

patcher.inject('http.client', globals(),
               ('os', os), ('socket', socket), ('urllib.parse', urllib_parse))

del patcher
del urllib_parse
