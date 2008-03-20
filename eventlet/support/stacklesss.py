"""\
@file __init__.py
@brief Support for using stackless python.  Broken and riddled with
print statements at the moment.  Please fix it!

Copyright (c) 2007, Linden Research, Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import sys
import types

import stackless
import traceback


caller = None


coro_args = {}


tasklet_to_greenlet = {}


def getcurrent():
    return tasklet_to_greenlet[stackless.getcurrent()]


class FirstSwitch(object):
    def __init__(self, gr):
        self.gr = gr

    def __call__(self, *args, **kw):
        print "first call", args, kw
        gr = self.gr
        del gr.switch
        run, gr.run = gr.run, None
        t = stackless.tasklet(run)
        gr.t = t
        tasklet_to_greenlet[t] = gr
        t.setup(*args, **kw)
        result = t.run()


class greenlet(object):
    def __init__(self, run=None, parent=None):
        self.dead = False
        if parent is None:
            parent = getcurrent()

        self.parent = parent
        if run is not None:
            self.run = run

        self.switch = FirstSwitch(self)

    def switch(self, *args):
        print "switch", args
        global caller
        caller = stackless.getcurrent()
        coro_args[self] = args
        self.t.insert()
        stackless.schedule()
        if caller is not self.t:
            caller.remove()
        rval = coro_args[self]
        return rval

    def run(self):
        pass

    def __bool__(self):
        return self.run is None and not self.dead


class GreenletExit(Exception):
    pass


def emulate():
    module = types.ModuleType('greenlet')
    sys.modules['greenlet'] = module
    module.greenlet = greenlet
    module.getcurrent = getcurrent
    module.GreenletExit = GreenletExit

    caller = t = stackless.getcurrent()
    tasklet_to_greenlet[t] = None
    main_coro = greenlet()
    tasklet_to_greenlet[t] = main_coro
    main_coro.t = t
    del main_coro.switch  ## It's already running
    coro_args[main_coro] = None
