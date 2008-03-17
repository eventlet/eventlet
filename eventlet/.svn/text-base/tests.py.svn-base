"""\
@file tests.py
@author Donovan Preston
@brief Indirection layer for tests in case we want to fix unittest.

Copyright (c) 2006-2007, Linden Research, Inc.
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

import errno
import os
import sys
import unittest, doctest


TestCase = unittest.TestCase


name = getattr(sys.modules['__main__'], '__name__', None)
main = unittest.main

# listing of files containing doctests
doc_test_files = ['coros']

def find_command(command):
    for dir in os.getenv('PATH', '/usr/bin:/usr/sbin').split(os.pathsep):
        p = os.path.join(dir, command)
        if os.access(p, os.X_OK):
            return p
    raise IOError(errno.ENOENT, 'Command not found: %r' % command)
    
def run_all_tests(test_files = doc_test_files):
    """ Runs all the unit tests, returning immediately after the 
    first failed test.
    
    Returns true if the tests all succeeded.  This method is really much longer
    than it ought to be.
    """
    eventlet_dir = os.path.realpath(os.path.dirname(__file__))
    if eventlet_dir not in sys.path:
        sys.path.append(eventlet_dir)
    
    # add all _test files as a policy
    import glob
    test_files += [os.path.splitext(os.path.basename(x))[0] 
                  for x in glob.glob(os.path.join(eventlet_dir, "*_test.py"))]
    test_files.sort()
    
    for test_file in test_files:
        print "-=", test_file, "=-"
        try:
            test_module = __import__(test_file)
        except ImportError:
            print "Unable to import %s, skipping" % test_file
            continue
            
        if test_file.endswith('_test'):
            # gawd, unittest, why you make it so difficult to just run some tests!
            suite = unittest.findTestCases(test_module)
            result = unittest.TextTestRunner().run(suite)
            if not result.wasSuccessful():
                return False
        else:    
            failures, tests = doctest.testmod(test_module)
            if failures:
                return False
            else:
                print "OK"
                
    return True
    
if __name__ == '__main__':
    run_all_tests()
