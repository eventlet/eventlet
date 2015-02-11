from eventlet import patcher
from eventlet.green import os, time, select, socket, SocketServer, subprocess
from eventlet.green.http import client
from eventlet.green.urllib import parse as urllib_parse

patcher.inject('http.server', globals(),
               ('http.client', client), ('os', os), ('select', select),
               ('socket', socket), ('socketserver', SocketServer), ('time', time),
               ('urllib.parse', urllib_parse))


CGIHTTPRequestHandler.run_cgi = patcher.patch_function(
    CGIHTTPRequestHandler.run_cgi, ('subprocess', subprocess))

del urllib_parse
del client
del patcher
