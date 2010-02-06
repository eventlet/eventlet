import sys


__exclude = set(('__builtins__', '__file__', '__name__'))


def inject(module_name, new_globals, *additional_modules):
    if not additional_modules:
        # supply some defaults
        additional_modules = (
            _green_os_modules() +
            _green_select_modules() +
            _green_socket_modules() +
            _green_thread_modules())
        
    ## Put the specified modules in sys.modules for the duration of the import
    saved = {}
    for name, mod in additional_modules:
        saved[name] = sys.modules.get(name, None)
        sys.modules[name] = mod

    ## Remove the old module from sys.modules and reimport it while the specified modules are in place
    old_module = sys.modules.pop(module_name, None)
    try:
        module = __import__(module_name, {}, {}, module_name.split('.')[:-1])

        if new_globals is not None:
            ## Update the given globals dictionary with everything from this new module
            for name in dir(module):
                if name not in __exclude:
                    new_globals[name] = getattr(module, name)

        ## Keep a reference to the new module to prevent it from dying
        sys.modules['__patched_module_' + module_name] = module
    finally:
        ## Put the original module back
        if old_module is not None:
            sys.modules[module_name] = old_module
        elif module_name in sys.modules:
            del sys.modules[module_name]

        ## Put all the saved modules back
        for name, mod in additional_modules:
            if saved[name] is not None:
                sys.modules[name] = saved[name]
            else:
                del sys.modules[name]

    return module


def import_patched(module_name, *additional_modules, **kw_additional_modules):
    return inject(
    	module_name,
    	None,
    	*additional_modules + tuple(kw_additional_modules.items()))


def patch_function(func, *additional_modules):
    """Huge hack here -- patches the specified modules for the 
    duration of the function call."""
    def patched(*args, **kw):
        saved = {}
        for name, mod in additional_modules:
            saved[name] = sys.modules.get(name, None)
            sys.modules[name] = mod
        try:
            return func(*args, **kw)
        finally:
            ## Put all the saved modules back
            for name, mod in additional_modules:
                if saved[name] is not None:
                    sys.modules[name] = saved[name]
                else:
                    del sys.modules[name]
    return patched
        

def monkey_patch(os=True, select=True, socket=True, thread=True):
    modules_to_patch = []
    if os:
        modules_to_patch += _green_os_modules()
    if select:
        modules_to_patch += _green_select_modules()
    if socket:
        modules_to_patch += _green_socket_modules()
    if thread:
        modules_to_patch += _green_thread_modules()
    for name, mod in modules_to_patch:
        sys.modules[name] = mod

def _green_os_modules():
    from eventlet.green import os
    return [('os', os)]

def _green_select_modules():
    from eventlet.green import select
    return [('select', select)]

def _green_socket_modules():
    from eventlet.green import socket
    try:
        from eventlet.green import ssl
        return [('socket', socket), ('ssl', ssl)]
    except ImportError:
        return [('socket', socket)]

def _green_thread_modules():
    from eventlet.green import Queue
    from eventlet.green import thread
    return [('Queue', Queue), ('thread', thread)]
    