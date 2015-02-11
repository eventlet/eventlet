from eventlet.green import threading, time
from eventlet.green.http import client
from eventlet.green.urllib import parse as urllib_parse, request as urllib_request
from eventlet import patcher

patcher.inject('http.cookiejar', globals(),
               ('http.client', client), ('threading', threading),
               ('urllib.parse', urllib_parse), ('urllib.request', urllib_request),
               ('time', time))

del urllib_request
del urllib_parse
del patcher
