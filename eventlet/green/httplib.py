from eventlet import patcher
from eventlet.green import socket
from eventlet.support import six

to_patch = [('socket', socket)]

try:
    from eventlet.green import ssl
    to_patch.append(('ssl', ssl))
except ImportError:
    pass

if six.PY2:
    patcher.inject('httplib', globals(), *to_patch)
if six.PY3:
    patcher.inject('http.client', globals(), *to_patch)

if __name__ == '__main__':
    test()
