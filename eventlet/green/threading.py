from eventlet import patcher
from eventlet.green import thread
from eventlet.green import time

__patched__ = ['_start_new_thread', '_allocate_lock', '_get_ident']

patcher.inject('threading',
    globals(),
    ('thread', thread),
    ('time', time))

del patcher

if __name__ == '__main__':
    _test()
