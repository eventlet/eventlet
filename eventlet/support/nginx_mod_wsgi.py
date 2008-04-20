
import sys
import traceback

sys.path.insert(0, '/Users/donovan/Code/mulib-hg')
sys.stdout = sys.stderr

from eventlet import api
from eventlet import httpc

from eventlet.hubs import nginx


def old_real_application(env, start_response):
    #result = httpc.get('http://127.0.0.1:8081/')
    start_response('200 OK', [('Content-type', 'text/plain')])
    #sys.stderr.write("RESULT %r" % (result, ))
    return 'hello'


def wrap_application(master, env, start_response):
    real_application = api.named(env['eventlet_nginx_wsgi_app'])
    result = real_application(env, start_response)
    ## Should catch exception and return here?
    #sys.stderr.write("RESULT2 %r" % (result, ))
    master.switch((result, None))
    return None, None


class StartResponse(object):
    def __init__(self, start_response):
        self.start_response = start_response

    def __call__(self, *args):
        self.args = args


def application(env, start_response):
    hub = api.get_hub()

    if not isinstance(hub, nginx.Hub):
        api.use_hub(nginx)

    hub.poll_register = env['ngx.poll_register']
    hub.poll_unregister = env['ngx.poll_unregister']
    hub.sleep = env['ngx.sleep']
    hub.current_application = api.getcurrent()

    slave = api.greenlet.greenlet(wrap_application)
    response = StartResponse(start_response)
    result = slave.switch(
        hub.current_application, env, response)

    while True:
        #sys.stderr.write("RESULT3 %r" % (result, ))
        if result is None or result == (None, None):
            yield ''
        else:
            start_response(*response.args)
            if isinstance(result, tuple):
                for x in result[0]:
                    yield x
            else:
                for x in result:
                    yield x
            return
        result = hub.switch()
