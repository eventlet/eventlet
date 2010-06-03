from eventlet import patcher
from eventlet.green import thread
from eventlet.green import time

__patched__ = ['_start_new_thread', '_allocate_lock', '_get_ident', '_sleep',
               'local', 'stack_size', 'Lock']

patcher.inject('threading',
    globals(),
    ('thread', thread),
    ('time', time))

del patcher

def _patch_main_thread(mod):
    # this is some gnarly patching for the threading module;
    # if threading is imported before we patch (it nearly always is),
    # then the main thread will have the wrong key in threading._active,
    # so, we try and replace that key with the correct one here
    # this works best if there are no other threads besides the main one
    curthread = mod._active.pop(mod._get_ident(), None)
    if curthread:
        mod._active[thread.get_ident()] = curthread
