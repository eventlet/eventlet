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

"""Run tests for different configurations (hub/reactor)"""
import sys
import os
import random
from glob import glob
from optparse import OptionParser, Option
from copy import copy
from time import time
from with_eventlet import import_reactor

first_hubs = ['poll', 'selects', 'twistedr']
first_reactors = ['selectreactor', 'pollreactor']

COMMAND = sys.executable + ' ./record_results.py ' + sys.executable + ' ./with_timeout.py ./with_eventlet.py %(setup)s %(test)s'
PARSE_PERIOD = 10

# the following aren't in the default list unless --all option present
NOT_HUBS = set()
NOT_REACTORS = set(['wxreactor', 'glib2reactor', 'gtk2reactor'])
NOT_TESTS = set(['db_pool_test.py'])

def w(s):
    sys.stderr.write("%s\n" % (s, ))

def enum_hubs():
    from eventlet.api import use_hub
    hubs = glob('../eventlet/hubs/*.py')
    hubs = [os.path.basename(h)[:-3] for h in hubs]
    hubs = [h for h in hubs if h[:1]!='_']
    hubs = set(hubs)
    hubs.discard('hub')
    hubs -= NOT_HUBS
    result = []
    for hub in hubs:
        try:
            use_hub(hub)
        except Exception, ex:
            print 'Skipping hub %s: %s' % (hub, ex)
        else:
            result.append(hub)
    return result

def enum_reactors():
    try:
        import twisted
    except ImportError:
        return []
    p = os.path.join(os.path.dirname(twisted.__file__), 'internet', '*?reactor.py')
    files = glob(p)
    all_reactors = [os.path.basename(f[:-3]) for f in files]
    all_reactors = set(all_reactors) - NOT_REACTORS
    selected_reactors = []
    for reactor in all_reactors:
        try:
            import_reactor(reactor)
        except Exception, ex:
            print 'Skipping reactor %s: %s' % (reactor, ex)
        else:
            selected_reactors.append(reactor)
    return selected_reactors

def enum_tests():
    tests = []
    tests += glob('test_*.py')
    tests += glob('*_test.py')
    tests = set(tests) - NOT_TESTS - set(['test_support.py'])
    return tests

def cmd(program):
    w(program)
    res = os.system(program)>>8
    w(res)
    if res==1:
        sys.exit(1)
    return res

def check_stringlist(option, opt, value):
    return value.split(',')

class MyOption(Option):
    TYPES = Option.TYPES + ("stringlist",)
    TYPE_CHECKER = copy(Option.TYPE_CHECKER)
    TYPE_CHECKER["stringlist"] = check_stringlist

def main():
    global NOT_HUBS, NOT_REACTORS, NOT_TESTS
    parser = OptionParser(option_class=MyOption)
    parser.add_option('-u', '--hubs', type='stringlist')
    parser.add_option('-r', '--reactors', type='stringlist')
    parser.add_option('--ignore-hubs', type='stringlist', default=[])
    parser.add_option('--ignore-reactors', type='stringlist', default=[])
    parser.add_option('--ignore-tests', type='stringlist', default=[])
    parser.add_option('-s', '--show', help='show default values and exit', action='store_true', default=False)
    parser.add_option('-a', '--all', action='store_true', default=False)
    options, args = parser.parse_args()
    options.tests = args or None
    if options.all:
        NOT_HUBS = NOT_REACTORS = NOT_TESTS = set()
    if options.hubs is None:
        options.hubs = enum_hubs()
    if options.reactors is None:
        options.reactors = enum_reactors()
    if options.tests is None:
        options.tests = enum_tests()

    tests = []
    for t in options.tests:
        tests.extend(glob(t))
    options.tests = tests

    options.hubs = list(set(options.hubs) - set(options.ignore_hubs))
    options.reactors = list(set(options.reactors) - set(options.ignore_reactors))
    options.tests = list(set(options.tests) - set(options.ignore_tests))
    random.shuffle(options.hubs)
    options.hubs.sort(key=first_hubs.__contains__, reverse=True)
    random.shuffle(options.reactors)
    options.reactors.sort(key=first_reactors.__contains__, reverse=True)
    random.shuffle(options.tests)

    print 'hubs: %s' % ','.join(options.hubs)
    print 'reactors: %s' % ','.join(options.reactors)
    print 'tests: %s' % ','.join(options.tests)

    if options.show:
       return

    setups = []
    for hub in options.hubs:
        if hub == 'twistedr':
            for reactor in options.reactors:
                setups.append('--hub twistedr --reactor %s' % reactor)
        else:
            setups.append('--hub %s' % hub)

    last_time = time()

    for setup in setups:
        w(setup)
        for test in options.tests:
            w(test)
            cmd(COMMAND % locals())
            if time()-last_time>PARSE_PERIOD:
                os.system('./parse_results.py')
                last_time = time()
    os.system('./parse_results.py')

if __name__=='__main__':
    main()

