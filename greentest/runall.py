#!/usr/bin/python
"""Run tests for different configurations (hub/reactor)"""
import sys
import os
import glob
import random
from optparse import OptionParser, Option
from copy import copy
from with_eventlet import import_reactor

COMMAND = './record_results.py ./with_timeout.py ./with_eventlet.py %(setup)s %(test)s'
NOT_HUBS = ['hub', 'nginx']

def w(s):
    sys.stderr.write("%s\n" % (s, ))

def enum_hubs():
    from eventlet.api import use_hub
    hubs = glob.glob('../eventlet/hubs/*.py')
    hubs = [os.path.basename(h)[:-3] for h in hubs]
    hubs = [h for h in hubs if h[:1]!='_']
    hubs = set(hubs) - set(NOT_HUBS)
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
    import twisted
    p = os.path.join(os.path.dirname(twisted.__file__), 'internet', '*?reactor.py')
    files = glob.glob(p)
    reactors = []
    for f in files:
        reactor = os.path.basename(f[:-3])
        try:
            import_reactor(reactor)
        except Exception, ex:
            print 'Skipping reactor %s: %s' % (reactor, ex)
        else:
            reactors.append(reactor)
    return reactors 

def enum_tests():
    tests = []
    tests += glob.glob('test*_green.py')
    tests += glob.glob('test__*.py')
    tests += glob.glob('*_test.py')
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
    parser = OptionParser(option_class=MyOption)
    parser.add_option('--hubs', type='stringlist')
    parser.add_option('--reactors', type='stringlist')
    parser.add_option('--tests', type='stringlist')
    parser.add_option('--ignore-hubs', type='stringlist', default=[])
    parser.add_option('--ignore-reactors', type='stringlist', default=[])
    parser.add_option('--ignore-tests', type='stringlist', default=[])
    parser.add_option('--show', help='show default values and exit', action='store_true', default=False)
    options, _args = parser.parse_args()
    if options.hubs is None:
        options.hubs = enum_hubs()
    if options.reactors is None:
        options.reactors = enum_reactors()
    if options.tests is None:
        options.tests = enum_tests()
    options.hubs = list(set(options.hubs) - set(options.ignore_hubs))
    options.reactors = list(set(options.reactors) - set(options.ignore_reactors))
    options.tests = list(set(options.tests) - set(options.ignore_tests))
    random.shuffle(options.hubs)
    random.shuffle(options.reactors)
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

    for setup in setups:
        w(setup)
        for test in options.tests:
            w(test)
            cmd(COMMAND % locals())

if __name__=='__main__':
    main()

