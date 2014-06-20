builtins_orig = __builtins__

from eventlet import hubs
from eventlet.hubs import hub
from eventlet.patcher import slurp_properties
import sys

__all__ = dir(builtins_orig)
__patched__ = ['file', 'open']

slurp_properties(builtins_orig, globals(),
    ignore=__patched__, srckeys=dir(builtins_orig))

hubs.get_hub()

__original_file = file
class file(__original_file):
    def __init__(self, *args, **kwargs):
        super(file, self).__init__(*args, **kwargs)
        print >> sys.stderr, "*** DEBUG: file opened with", args
        hubs.notify_opened(self.fileno())

__original_open = open
__opening = False
def open(*args):
    global __opening
    result = __original_open(*args)
    if not __opening:
        __opening = True
        print >> sys.stderr, "*** DEBUG: open opened with", args
        hubs.notify_opened(result.fileno())
        __opening = False
    return result