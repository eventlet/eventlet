# Copyright (c) 2007, Linden Research, Inc.
# Copyright (c) 2007, IBM Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import threading

from Queue import Empty, Queue

from eventlet import api, coros, greenio

QUIET=False

_rpipe, _wpipe = os.pipe()
_rfile = os.fdopen(_rpipe,"r",0)
## Work whether or not wrap_pipe_with_coroutine_pipe was called
if not isinstance(_rfile, greenio.GreenPipe):
    _rfile = greenio.GreenPipe(_rfile)


def _signal_t2e():
    from eventlet import util
    nwritten = util.__original_write__(_wpipe, ' ')

_reqq = Queue(maxsize=-1)
_rspq = Queue(maxsize=-1)

def tpool_trampoline():
    global _reqq, _rspq
    while(True):
        _c = _rfile.recv(1)
        assert(_c != "")
        while not _rspq.empty():
            try:
                (e,rv) = _rspq.get(block=False)
                e.send(rv)
                rv = None
            except Empty:
                pass

def esend(meth,*args, **kwargs):
    global _reqq, _rspq
    e = coros.event()
    _reqq.put((e,meth,args,kwargs))
    return e

SYS_EXCS = (KeyboardInterrupt, SystemExit)


def tworker():
    global _reqq, _rspq
    while(True):
        msg = _reqq.get()
        if msg is None:
            return
        (e,meth,args,kwargs) = msg
        rv = None
        try:
            rv = meth(*args,**kwargs)
        except SYS_EXCS:
            raise
        except Exception,exn:
            import sys
            (a,b,tb) = sys.exc_info()
            rv = (exn,a,b,tb)
        _rspq.put((e,rv))
        meth = args = kwargs = e = rv = None
        _signal_t2e()


def erecv(e):
    rv = e.wait()
    if isinstance(rv,tuple) and len(rv) == 4 and isinstance(rv[0],Exception):
        import traceback
        (e,a,b,tb) = rv
        if not QUIET:
            traceback.print_exception(Exception,e,tb)
            traceback.print_stack()
        raise e
    return rv


def execute(meth,*args, **kwargs):
    """Execute method in a thread, blocking the current
    coroutine until the method completes.
    """
    e = esend(meth,*args,**kwargs)
    rv = erecv(e)
    return rv

## TODO deprecate
erpc = execute



def proxy_call(autowrap, f, *args, **kwargs):
    """ Call a function *f* and returns the value.  If the type of the
    return value is in the *autowrap* collection, then it is wrapped in
    a Proxy object before return.  Normally *f* will be called
    nonblocking with the execute method; if the keyword argument
    "nonblocking" is set to true, it will simply be executed directly."""
    if kwargs.pop('nonblocking',False):
        rv = f(*args, **kwargs)
    else:
        rv = execute(f,*args,**kwargs)
    if isinstance(rv, autowrap):
        return Proxy(rv, autowrap)
    else:
        return rv

class Proxy(object):
    """ a simple proxy-wrapper of any object that comes with a methods-only interface,
    in order to forward every method invocation onto a thread in the native-thread pool.
    A key restriction is that the object's methods cannot call into eventlets, since the
    eventlet dispatcher runs on a different native thread.  This is for running native-threaded
    code only. """
    def __init__(self, obj,autowrap=()):
        self._obj = obj
        self._autowrap = autowrap

    def __getattr__(self,attr_name):
        f = getattr(self._obj,attr_name)
        if not callable(f):
            return f
        def doit(*args, **kwargs):
            return proxy_call(self._autowrap, f, *args, **kwargs)
        return doit

    # the following are a buncha methods that the python interpeter
    # doesn't use getattr to retrieve and therefore have to be defined
    # explicitly
    def __getitem__(self, key):
        return proxy_call(self._autowrap, self._obj.__getitem__, key)
    def __setitem__(self, key, value):
        return proxy_call(self._autowrap, self._obj.__setitem__, key, value)
    def __deepcopy__(self, memo=None):
        return proxy_call(self._autowrap, self._obj.__deepcopy__, memo)
    def __copy__(self, memo=None):
        return proxy_call(self._autowrap, self._obj.__copy__, memo)
    # these don't go through a proxy call, because they're likely to
    # be called often, and are unlikely to be implemented on the
    # wrapped object in such a way that they would block
    def __eq__(self, rhs):
        return self._obj.__eq__(rhs)
    def __repr__(self):
        return self._obj.__repr__()
    def __str__(self):
        return self._obj.__str__()
    def __len__(self):
        return len(self._obj)
    def __nonzero__(self):
        return bool(self._obj)



_nthreads = int(os.environ.get('EVENTLET_THREADPOOL_SIZE', 20))
_threads = {}
def setup():
    global _threads
    for i in range(0,_nthreads):
        _threads[i] = threading.Thread(target=tworker)
        _threads[i].setDaemon(True)
        _threads[i].start()

    api.spawn(tpool_trampoline)

setup()


def killall():
    for i in _threads:
        _reqq.put(None)
    for thr in _threads.values():
        thr.join()

