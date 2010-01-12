from eventlet import patcher
from eventlet.green import thread
from eventlet.green import time

patcher.inject('threading',
    globals(),
    ('thread', thread),
    ('time', time))

del patcher

if __name__ == '__main__':
    _test()
