import sys


__exclude = set(('__builtins__', '__file__', '__name__'))


def inject(module_name, new_globals, *additional_modules):
    ## Put the specified modules in sys.modules for the duration of the import
    saved = {}
    for name, mod in additional_modules:
        saved[name] = sys.modules.get(name, None)
        sys.modules[name] = mod

    ## Remove the old module from sys.modules and reimport it while the specified modules are in place
    old_module = sys.modules.pop(module_name, None)
    module = __import__(module_name, {}, {}, module_name.split('.')[:-1])

    if new_globals is not None:
        ## Update the given globals dictionary with everything from this new module
        for name in dir(module):
            if name not in __exclude:
                new_globals[name] = getattr(module, name)

    ## Keep a reference to the new module to prevent it from dying
    sys.modules['__patched_module_' + module_name] = module
    ## Put the original module back
    if old_module is not None:
        sys.modules[module_name] = old_module
    else:
        del sys.modules[module_name]

    ## Put all the saved modules back
    for name, mod in additional_modules:
        if saved[name] is not None:
            sys.modules[name] = saved[name]

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
    return patched
        