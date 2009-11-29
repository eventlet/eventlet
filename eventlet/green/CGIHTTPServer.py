from eventlet import patcher
from eventlet.green import BaseHTTPServer
from eventlet.green import SimpleHTTPServer
from eventlet.green import urllib
from eventlet.green import select

patcher.inject('CGIHTTPServer',
    globals(),
    ('BaseHTTPServer', BaseHTTPServer),
    ('SimpleHTTPServer', SimpleHTTPServer),
    ('urllib',  urllib),
    ('select',  select))

del patcher

if __name__ == '__main__':
    test()