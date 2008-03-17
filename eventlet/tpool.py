"""\
@file tpool.py

Copyright (c) 2007, Linden Research, Inc.
Copyright (c) 2007, IBM Corp.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os, socket, time, threading
import Queue

from sys import stdout
from Queue import Empty, Queue

from eventlet import api, coros, httpc, httpd, util, wrappedfd
from eventlet.api import trampoline, get_hub

_rpipe, _wpipe = os.pipe()
_rfile = os.fdopen(_rpipe,"r",0)
_wrap_rfile = wrappedfd.wrapped_file(_rfile)
util.set_nonblocking(_rfile)

def _signal_t2e():
    nwritten = os.write(_wpipe,' ')

_reqq = Queue(maxsize=-1)
_rspq = Queue(maxsize=-1)

def tpool_trampoline():
    global _reqq, _rspq
    while(True):
        _c = _wrap_rfile.recv(1)
        assert(_c != "")
        while not _rspq.empty():
            try:
                (e,rv) = _rspq.get(block=False)
                e.send(rv)
            except Empty:
                pass

def esend(meth,*args, **kwargs):
    global _reqq, _rspq
    e = coros.event()
    _reqq.put((e,meth,args,kwargs))
    return e

def tworker():
    global _reqq, _rspq
    while(True):
        (e,meth,args,kwargs) = _reqq.get()
        rv = None
        try:
            rv = meth(*args,**kwargs)
        except Exception,exn:
            import sys, traceback
            (a,b,tb) = sys.exc_info()
            rv = (exn,a,b,tb)
        _rspq.put((e,rv))
        _signal_t2e()

def erecv(e):
    rv = e.wait()
    if isinstance(rv,tuple) and len(rv) == 4 and isinstance(rv[0],Exception):
        import sys, traceback
        (e,a,b,tb) = rv
        traceback.print_exception(Exception,e,tb)
        traceback.print_stack()
        raise e
    return rv

def erpc(meth,*args, **kwargs):
    e = esend(meth,*args,**kwargs)
    rv = erecv(e)
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
            if kwargs.pop('nonblocking',False):
                rv = f(*args, **kwargs)
            else:
                rv = erpc(f,*args,**kwargs)
            if type(rv) in self._autowrap:
                return Proxy(rv)
            else:
                return rv
        return doit

_nthreads = 20
_threads = {}
def setup():
    global _threads
    for i in range(0,_nthreads):
        _threads[i] = threading.Thread(target=tworker)
        _threads[i].setDaemon(True)
        _threads[i].start()

    api.spawn(tpool_trampoline)

setup()
