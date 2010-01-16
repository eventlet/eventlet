import select
import sys
import threading
_threadlocal = threading.local()

__all__ = ["use_hub"]

def get_default_hub():
    """Select the default hub implementation based on what multiplexing
    libraries are installed.  The order that the hubs are tried is:
    * twistedr
    * epoll
    * poll
    * select
    
    It won't ever automatically select the pyevent hub, because it's not 
    python-thread-safe.
    """    
    
    # pyevent hub disabled for now because it is not thread-safe
    #try:
    #    import eventlet.hubs.pyevent
    #    return eventlet.hubs.pyevent
    #except:
    #    pass

    if 'twisted.internet.reactor' in sys.modules:
        from eventlet.hubs import twistedr
        return twistedr

    try:
        import eventlet.hubs.epolls
        return eventlet.hubs.epolls
    except ImportError:
        if hasattr(select, 'poll'):
            import eventlet.hubs.poll
            return eventlet.hubs.poll
        else:
            import eventlet.hubs.selects
            return eventlet.hubs.selects


def use_hub(mod=None):
    """Use the module *mod*, containing a class called Hub, as the
    event hub. Usually not required; the default hub is usually fine.  
    
    Mod can be an actual module, a string, or None.  If *mod* is a module,
    it uses it directly.   If *mod* is a string, use_hub tries to import 
    `eventlet.hubs.mod` and use that as the hub module.  If *mod* is None, 
    use_hub uses the default hub.  Only call use_hub during application 
    initialization,  because it resets the hub's state and any existing 
    timers or listeners will never be resumed.
    """
    if mod is None:
        mod = get_default_hub()
    if hasattr(_threadlocal, 'hub'):
        del _threadlocal.hub
    if isinstance(mod, str):
        mod = __import__('eventlet.hubs.' + mod, globals(), locals(), ['Hub'])
    if hasattr(mod, 'Hub'):
        _threadlocal.Hub = mod.Hub
    else:
        _threadlocal.Hub = mod

def get_hub():
    """Get the current event hub singleton object.
    """
    try:
        hub = _threadlocal.hub
    except AttributeError:
        try:
            _threadlocal.Hub
        except AttributeError:
            use_hub()
        hub = _threadlocal.hub = _threadlocal.Hub()
    return hub
