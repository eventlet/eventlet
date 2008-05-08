"""\
@file nginx.py
@author Donovan Preston

Copyright (c) 2008, Linden Research, Inc.

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



from os.path import abspath, dirname
import sys
import traceback

sys.stdout = sys.stderr
mydir = dirname(dirname(dirname(abspath(__file__))))
if mydir not in sys.path:
    sys.path.append(mydir)


from eventlet import api
from eventlet import greenlib
from eventlet import httpc
from eventlet.hubs import hub
from eventlet import util


util.wrap_socket_with_coroutine_socket()


def hello_world(env, start_response):
    result = httpc.get('http://www.google.com/')
    start_response('200 OK', [('Content-type', 'text/plain')])
    return [result]


def wrap_application(master, env, start_response):
    try:
        real_application = api.named(env['eventlet_nginx_wsgi_app'])
    except:
        real_application = hello_world
    result = real_application(env, start_response)
    master.switch((result, None))
    return None, None


class StartResponse(object):
    def __call__(self, *args):
        self.args = args


pythonpath_already_set = False




WSGI_POLLIN = 0x01
WSGI_POLLOUT = 0x04

import traceback
class Hub(hub.BaseHub):
    def __init__(self, *args, **kw):
        hub.BaseHub.__init__(self, *args, **kw)
        self._connection_wrappers = {}

    def add_descriptor(self, fileno, read=None, write=None, exc=None):
        print "ADD DESCRIPTOR", fileno, read, write, exc
        traceback.print_stack()

        super(Hub, self).add_descriptor(fileno, read, write, exc)
        flag = 0
        if read:
            flag |= WSGI_POLLIN
        if write:
            flag |= WSGI_POLLOUT
        conn = self.connection_wrapper(fileno)
        self._connection_wrappers[fileno] = conn
        print "POLL REGISTER", flag
        self.poll_register(conn, flag)

    def remove_descriptor(self, fileno):
        super(Hub, self).remove_descriptor(fileno)

        try:
            self.poll_unregister(self._connection_wrappers[fileno])
        except RuntimeError:
            pass

    def wait(self, seconds=0):
        to_call = getattr(self, 'to_call', None)
        print "WAIT", self, to_call
        if to_call:
            print "CALL TOCALL"
            result = to_call[0](to_call[1])
            del self.to_call
            return result
        greenlib.switch(self.current_application, self.poll(int(seconds*1000)))

    def application(self, env, start_response):
        print "ENV",env
        self.poll_register = env['ngx.poll_register']
        self.poll_unregister = env['ngx.poll_unregister']
        self.poll = env['ngx.poll']
        self.connection_wrapper = env['ngx.connection_wrapper']
        self.current_application = api.getcurrent()

        slave = api.greenlet.greenlet(wrap_application)
        response = StartResponse()
        result = slave.switch(
            api.getcurrent(), env, response)
    
        while True:
            self.current_application = api.getcurrent()
            print "RESULT", result, callable(result[0])
            if result and callable(result[0]):
                print "YIELDING!"
                yield ''
                print "AFTER YIELD!"
                conn, flags = result[0]()
                fileno = conn.fileno()
                if flags & WSGI_POLLIN:
                    self.readers[fileno](fileno)
                elif flags & WSGI_POLLOUT:
                    self.writers[fileno](fileno)
                print "POLL STATE", conn, flags, dir(conn)
            else:
                start_response(*response.args)
                if isinstance(result, tuple):
                    for x in result[0]:
                        yield x
                else:
                    for x in result:
                        yield x
                return
            result = self.switch()
            if not isinstance(result, tuple):
                result = (result, None) ## TODO Fix greenlib's return values


def application(env, start_response):
    hub = api.get_hub()

    if not isinstance(hub, Hub):
        api.use_hub(sys.modules[Hub.__module__])
        hub = api.get_hub()

    global pythonpath_already_set
    if not pythonpath_already_set:
        pythonpath = env.get('eventlet_python_path', '').split(':')
        for seg in pythonpath:
            if seg not in sys.path:
                sys.path.append(seg)

    return hub.application(env, start_response)

