"""The debug module contains utilities and functions for better 
debugging Eventlet-powered applications."""

__all__ = ['spew', 'unspew', 'hub_listener_stacks', 
'hub_exceptions', 'tpool_exceptions']


class Spew(object):
    """
    """
    def __init__(self, trace_names=None, show_values=True):
        self.trace_names = trace_names
        self.show_values = show_values

    def __call__(self, frame, event, arg):
        if event == 'line':
            lineno = frame.f_lineno
            if '__file__' in frame.f_globals:
                filename = frame.f_globals['__file__']
                if (filename.endswith('.pyc') or
                    filename.endswith('.pyo')):
                    filename = filename[:-1]
                name = frame.f_globals['__name__']
                line = linecache.getline(filename, lineno)
            else:
                name = '[unknown]'
                try:
                    src = inspect.getsourcelines(frame)
                    line = src[lineno]
                except IOError:
                    line = 'Unknown code named [%s].  VM instruction #%d' % (
                        frame.f_code.co_name, frame.f_lasti)
            if self.trace_names is None or name in self.trace_names:
                print '%s:%s: %s' % (name, lineno, line.rstrip())
                if not self.show_values:
                    return self
                details = '\t'
                tokens = line.translate(
                    string.maketrans(' ,.()', '\0' * 5)).split('\0')
                for tok in tokens:
                    if tok in frame.f_globals:
                        details += '%s=%r ' % (tok, frame.f_globals[tok])
                    if tok in frame.f_locals:
                        details += '%s=%r ' % (tok, frame.f_locals[tok])
                if details.strip():
                    print details
        return self


def spew(trace_names=None, show_values=False):
    """Install a trace hook which writes incredibly detailed logs
    about what code is being executed to stdout.
    """
    sys.settrace(Spew(trace_names, show_values))


def unspew():
    """Remove the trace hook installed by spew.
    """
    sys.settrace(None)
    
    
def hub_listener_stacks(state):
    """Toggles whether or not the hub records the stack when clients register 
    listeners on file descriptors.  This can be useful when trying to figure 
    out what the hub is up to at any given moment.  To inspect the stacks
    of the current listeners, you have to iterate over them::
    
    from eventlet import hubs
    for reader in hubs.get_hub().get_readers():
        print reader
    """
    from eventlet import hubs
    hubs.get_hub().set_debug_listeners(state)
    
def hub_exceptions(state):
    """Toggles whether the hub prints exceptions that are raised from its
    timers.  This can be useful to see how greenthreads are terminating.
    """
    from eventlet import hubs
    hubs.get_hub().set_timer_exceptions(state)
    
def tpool_exceptions(state):
    """Toggles whether tpool itself prints exceptions that are raised from 
    functions that are executed in it, in addition to raising them like
    it normally does."""
    from eventlet import tpool
    tpool.QUIET = not state