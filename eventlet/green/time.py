__time = __import__('time')
for var in dir(__time):
    exec "%s = __time.%s" % (var, var)
from eventlet.api import sleep
