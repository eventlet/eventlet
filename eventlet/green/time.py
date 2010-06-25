__time = __import__('time')
exec "\n".join(["%s = __time.%s" % (var, var) for var in dir(__time)])
__patched__ = ['sleep']
from eventlet.greenthread import sleep
sleep # silence pyflakes
