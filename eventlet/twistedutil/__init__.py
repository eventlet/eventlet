# Copyright (c) 2008 AG Projects
# Author: Denis Bilenko
#
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

from twisted.internet import defer
from twisted.python import failure
from eventlet.api import get_hub, spawn, getcurrent

def block_on(deferred):
    cur = [getcurrent()]
    synchronous = []
    def cb(value):
        if cur:
            if getcurrent() is cur[0]:
                synchronous.append((value, None))
            else:
                cur[0].switch(value)
        return value
    def eb(failure):
        if cur:
            if getcurrent() is cur[0]:
                synchronous.append((None, failure))
            else:
                failure.throwExceptionIntoGenerator(cur[0])
    deferred.addCallbacks(cb, eb)
    if synchronous:
        result, failure = synchronous[0]
        if failure is not None:
            failure.raiseException()
        return result
    try:
        return get_hub().switch()
    finally:
        del cur[0]

def _putResultInDeferred(deferred, f, args, kwargs):
    try:
        result = f(*args, **kwargs)
    except:
        f = failure.Failure()
        deferred.errback(f)
    else:
        deferred.callback(result)

def deferToGreenThread(func, *args, **kwargs):
    d = defer.Deferred()
    spawn(_putResultInDeferred, d, func, args, kwargs)
    return d

def callInGreenThread(func, *args, **kwargs):
    return spawn(func, *args, **kwargs)


if __name__=='__main__':
    import sys
    try:
        num = int(sys.argv[1])
    except:
        sys.exit('Supply number of test as an argument, 0, 1, 2 or 3')
    from twisted.internet import reactor
    def test():
        print block_on(reactor.resolver.getHostByName('www.google.com'))
        print block_on(reactor.resolver.getHostByName('###'))
    if num==0:
        test()
    elif num==1:
        spawn(test)
        from eventlet.api import sleep
        print 'sleeping..'
        sleep(5)
        print 'done sleeping..'
    elif num==2:
        from eventlet.twistedutil import join_reactor
        spawn(test)
        reactor.run()
    elif num==3:
        from eventlet.twistedutil import join_reactor
        print "fails because it's impossible to use block_on from the mainloop"
        reactor.callLater(0, test)
        reactor.run()

