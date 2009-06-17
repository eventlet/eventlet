#!/usr/bin/python
# Copyright (c) 2008-2009 AG Projects
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

"""Execute python script with hub installed.

Usage: %prog [--hub HUB] [--reactor REACTOR] program.py
"""
import sys

def import_reactor(reactor):
    m = __import__('twisted.internet.' + reactor)
    return getattr(m.internet, reactor)

def setup_hub(hub, reactor):
    if reactor is not None:
        import_reactor(reactor).install()
    if hub is not None:
        from eventlet.api import use_hub
        try:
            use_hub(hub)
        except ImportError, ex:
            # as a shortcut, try to import the reactor with such name
            try:
                r = import_reactor(hub)
            except ImportError:
                sys.exit('No hub %s: %s' % (hub, ex))
            else:
                r.install()
                use_hub('twistedr')

def parse_args():
    hub = None
    reactor = None
    del sys.argv[0] # kill with_eventlet.py
    if sys.argv[0]=='--hub':
        del sys.argv[0]
        hub = sys.argv[0]
        del sys.argv[0]
    if sys.argv[0]=='--reactor':
        del sys.argv[0]
        reactor = sys.argv[0]
        del sys.argv[0]
    return hub, reactor

if __name__=='__main__':
    hub, reactor = parse_args()
    setup_hub(hub, reactor)
    from eventlet.api import get_hub
    hub = get_hub() # set up the hub now
    print '===HUB=%r' % hub
    if 'twisted.internet.reactor' in sys.modules:
        print '===REACTOR=%r' % sys.modules['twisted.internet.reactor']
    sys.stdout.flush()
    execfile(sys.argv[0])

