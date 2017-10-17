import sys
from eventlet import patcher
from eventlet.green.urllib import response
_canonical_name = 'urllib.error'
patcher.inject(_canonical_name, globals(), ('urllib.response', response))
_MISSING = object()
module_imported = sys.modules.get(_canonical_name, patcher.original(_canonical_name))
_current_module = sys.modules[__name__]
_keep_names = (
    'URLError',
    'HTTPError',
    'ContentTooShortError',
)
for k in _keep_names:
    v = getattr(module_imported, k, _MISSING)
    if v is not _MISSING:
        setattr(_current_module, k, v)
del _canonical_name, _current_module, _keep_names, k, v, module_imported, patcher, sys
