
import sys

from eventlet import api
from eventlet import httpc

from eventlet.hubs import nginx


def real_application(env, start_response):
    #result = httpc.get('http://127.0.0.1:8081/')
    start_response('200 OK', [('Content-type', 'text/plain')])
    #sys.stderr.write("RESULT %r" % (result, ))
    return 'hi'


def wrap_application(master, env, start_response):
    result = real_application(env, start_response)
    ## Should catch exception and return here?
    #sys.stderr.write("RESULT2 %r" % (result, ))
    master.switch((result, None))
    return None, None


def application(env, start_response):
    hub = api.get_hub()

    if not isinstance(hub, nginx.Hub):
        api.use_hub(nginx)

    hub.poll_register = env['ngx.poll_register']
    hub.poll_unregister = env['ngx.poll_unregister']
    hub.sleep = env['ngx.sleep']
    hub.current_application = api.getcurrent()

    slave = api.greenlet.greenlet(wrap_application)
    result = slave.switch(
        hub.current_application, env, start_response)

    while True:
        #sys.stderr.write("RESULT3 %r" % (result, ))
        if result is None or result == (None, None):
            yield ''
        else:
            if isinstance(result, tuple):
                yield result[0]
            else:
                yield result
            return
        result = hub.switch()
