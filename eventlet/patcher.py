import sys


__all__ = ['inject', 'import_patched', 'monkey_patch', 'is_monkey_patched']

__exclude = set(('__builtins__', '__file__', '__name__'))

def inject(module_name, new_globals, *additional_modules):
    """Base method for "injecting" greened modules into an imported module.  It
    imports the module specified in *module_name*, arranging things so
    that the already-imported modules in *additional_modules* are used when
    *module_name* makes its imports.

    *new_globals* is either None or a globals dictionary that gets populated
    with the contents of the *module_name* module.  This is useful when creating
    a "green" version of some other module.

    *additional_modules* should be a collection of two-element tuples, of the
    form (<name>, <module>).  If it's not specified, a default selection of
    name/module pairs is used, which should cover all use cases but may be
    slower because there are inevitably redundant or unnecessary imports.
    """
    patched_name = '__patched_module_' + module_name
    if patched_name in sys.modules:
        # returning already-patched module so as not to destroy existing
        # references to patched modules
        return sys.modules[patched_name]

    if not additional_modules:
        # supply some defaults
        additional_modules = (
            _green_os_modules() +
            _green_select_modules() +
            _green_socket_modules() +
            _green_thread_modules() +
            _green_time_modules())

    ## Put the specified modules in sys.modules for the duration of the import
    saved = {}
    for name, mod in additional_modules:
        saved[name] = sys.modules.get(name, None)
        sys.modules[name] = mod

    ## Remove the old module from sys.modules and reimport it while
    ## the specified modules are in place
    old_module = sys.modules.pop(module_name, None)
    try:
        module = __import__(module_name, {}, {}, module_name.split('.')[:-1])

        if new_globals is not None:
            ## Update the given globals dictionary with everything from this new module
            for name in dir(module):
                if name not in __exclude:
                    new_globals[name] = getattr(module, name)

        ## Keep a reference to the new module to prevent it from dying
        sys.modules[patched_name] = module
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
    """Imports a module in a way that ensures that the module uses "green"
    versions of the standard library modules, so that everything works
    nonblockingly.

    The only required argument is the name of the module to be imported.
    """
    return inject(
        module_name,
        None,
        *additional_modules + tuple(kw_additional_modules.items()))


def patch_function(func, *additional_modules):
    """Huge hack here -- patches the specified modules for the
    duration of the function call."""
    if not additional_modules:
        # supply some defaults
        additional_modules = (
            _green_os_modules() +
            _green_select_modules() +
            _green_socket_modules() +
            _green_thread_modules() + 
            _green_time_modules())

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

def _original_patch_function(func, *module_names):
    """Kind of the opposite of patch_function; wraps a function such
    that sys.modules is populated only with the unpatched versions of
    the specified modules.  Also a gross hack; tell your kids not to
    import inside function bodies!"""
    def patched(*args, **kw):
        saved = {}
        for name in module_names:
            saved[name] = sys.modules.get(name, None)
            sys.modules[name] = original(name)
        try:
            return func(*args, **kw)
        finally:
            for name in module_names:
                if saved[name] is not None:
                    sys.modules[name] = saved[name]
                else:
                    del sys.modules[name]
    return patched


def original(modname):
    original_name = '__original_module_' + modname
    if original_name in sys.modules:
        return sys.modules.get(original_name)

    # re-import the "pure" module and store it in the global _originals
    # dict; be sure to restore whatever module had that name already
    current_mod = sys.modules.pop(modname, None)
    try:
        real_mod = __import__(modname, {}, {}, modname.split('.')[:-1])
        # hacky hack: Queue's constructor imports threading; therefore
        # we wrap it with something that ensures it always gets the
        # original threading
        if modname == 'Queue':
            real_mod.Queue.__init__ = _original_patch_function(real_mod.Queue.__init__, 'threading')
        sys.modules[original_name] = real_mod
    finally:
        if current_mod is not None:
            sys.modules[modname] = current_mod
        else:
            del sys.modules[modname]
    return sys.modules[original_name]

already_patched = {}
def monkey_patch(**on):
    """Globally patches certain system modules to be greenthread-friendly.

    The keyword arguments afford some control over which modules are patched.
    If no keyword arguments are supplied, all possible modules are patched.
    If keywords are set to True, only the specified modules are patched.  E.g.,
    ``monkey_patch(socket=True, select=True)`` patches only the select and 
    socket modules.  Most arguments patch the single module of the same name 
    (os, time, select).  The exceptions are socket, which also patches the ssl 
    module if present; and thread, which patches thread, threading, and Queue.

    It's safe to call monkey_patch multiple times.
    """
    accepted_args = set(('os', 'select', 'socket', 'thread', 'time', 'psycopg'))
    default_on = on.pop("all",None)
    for k in on.iterkeys():
        if k not in accepted_args:
            raise TypeError("monkey_patch() got an unexpected "\
                                "keyword argument %r" % k)
    if default_on is None:
        default_on = not (True in on.values())
    for modname in accepted_args:
        on.setdefault(modname, default_on)
        
    modules_to_patch = []
    if on['os'] and not already_patched.get('os'):
        modules_to_patch += _green_os_modules()
        already_patched['os'] = True
    if on['select'] and not already_patched.get('select'):
        modules_to_patch += _green_select_modules()
        already_patched['select'] = True
    if on['socket'] and not already_patched.get('socket'):
        modules_to_patch += _green_socket_modules()
        already_patched['socket'] = True
    if on['thread'] and not already_patched.get('thread'):
        # hacks ahead
        threading = original('threading')
        import eventlet.green.threading as greenthreading
        greenthreading._patch_main_thread(threading)
        modules_to_patch += _green_thread_modules()
        already_patched['thread'] = True
    if on['time'] and not already_patched.get('time'):
        modules_to_patch += _green_time_modules()
        already_patched['time'] = True
    if on['psycopg'] and not already_patched.get('psycopg'):
        try:
            from eventlet.support import psycopg2_patcher
            psycopg2_patcher.make_psycopg_green()
            already_patched['psycopg'] = True
        except ImportError:
            # note that if we get an importerror from trying to
            # monkeypatch psycopg, we will continually retry it
            # whenever monkey_patch is called; this should not be a
            # performance problem but it allows is_monkey_patched to
            # tell us whether or not we succeeded
            pass

    for name, mod in modules_to_patch:
        orig_mod = sys.modules.get(name)
        for attr_name in mod.__patched__:
            patched_attr = getattr(mod, attr_name, None)
            if patched_attr is not None:
                setattr(orig_mod, attr_name, patched_attr)

def is_monkey_patched(module):
    """Returns True if the given module is monkeypatched currently, False if
    not.  *module* can be either the module itself or its name.

    Based entirely off the name of the module, so if you import a
    module some other way than with the import keyword (including
    import_patched), this might not be correct about that particular
    module."""
    return module in already_patched or \
           getattr(module, '__name__', None) in already_patched

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
    from eventlet.green import threading
    return [('Queue', Queue), ('thread', thread), ('threading', threading)]

def _green_time_modules():
    from eventlet.green import time
    return [('time', time)]


if __name__ == "__main__":
    import sys
    sys.argv.pop(0)
    monkey_patch()
    execfile(sys.argv[0])
