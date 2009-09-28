# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import sys


__exclude = ('__builtins__', '__file__', '__name__')


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

