"""http client that uses pycurl
"""

from eventlet import api

import pycurl


CURL_POLL_NONE = 0
CURL_POLL_IN = 1
CURL_POLL_OUT = 2
CURL_POLL_INOUT = 3
CURL_POLL_REMOVE = 4



SUSPENDED_COROS = {}
LAST_SOCKET = None
LAST_SOCKET_DONE = False


def hub_callback(fileno):
    print "HUB_CALLBACK", fileno
    SUSPENDED_COROS[fileno].switch()


def socket_callback(action, socket, user_data, socket_data):
    global LAST_SOCKET
    global LAST_SOCKET_DONE
    LAST_SOCKET = socket
    LAST_SOCKET_DONE = False
    print "SOCKET_CALLBACK", action, socket, user_data, socket_data
    hub = api.get_hub()
    if action == CURL_POLL_NONE:
        # nothing to do
        return
    elif action == CURL_POLL_IN:
        print "POLLIN"
        hub.add_descriptor(socket, read=hub_callback)
    elif action == CURL_POLL_OUT:
        print "POLLOUT"
        hub.add_descriptor(socket, write=hub_callback)
    elif action == CURL_POLL_INOUT:
        print "POLLINOUT"
        hub.add_descriptor(socket, read=hub_callback, write=hub_callback)
    elif action == CURL_POLL_REMOVE:
        print "POLLREMOVE"
        hub.remove_descriptor(socket)
        LAST_SOCKET_DONE = True


THE_MULTI = pycurl.CurlMulti()
THE_MULTI.setopt(pycurl.M_SOCKETFUNCTION, socket_callback)


def read(*data):
    print "READ", data


def write(*data):
    print "WRITE", data


def runloop_observer(*_):
    result, numhandles = THE_MULTI.socket_all()
    print "PERFORM RESULT", result
    while result == pycurl.E_CALL_MULTI_PERFORM:
        result, numhandles = THE_MULTI.socket_all()
        print "PERFORM RESULT2", result


def get(url):
    hub = api.get_hub()
    c = pycurl.Curl()
    c.setopt(pycurl.URL, url)
    #c.setopt(pycurl.M_SOCKETFUNCTION, socket_callback)
    c.setopt(pycurl.WRITEFUNCTION, write)
    c.setopt(pycurl.READFUNCTION, read)
    c.setopt(pycurl.NOSIGNAL, 1)
    THE_MULTI.add_handle(c)
    hub.add_observer(runloop_observer, 'before_waiting')
    while True:
        print "TOP"
        result, numhandles = THE_MULTI.socket_all()
        print "PERFORM RESULT", result
        while result == pycurl.E_CALL_MULTI_PERFORM:
            result, numhandles = THE_MULTI.socket_all()
            print "PERFORM RESULT2", result

        if LAST_SOCKET_DONE:
            break

        SUSPENDED_COROS[LAST_SOCKET] = api.getcurrent()
        print "SUSPENDED", SUSPENDED_COROS
        api.get_hub().switch()
        print "BOTTOM"

    if not SUSPENDED_COROS:
        hub.remove_observer(runloop_observer)


#from eventlet.support import pycurls
#reload(pycurls); from eventlet.support import pycurls; pycurls.get('http://localhost/')