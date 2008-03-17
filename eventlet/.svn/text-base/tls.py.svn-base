"""\
@file tls.py
@author Donovan Preston

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

import threading
import weakref

__all__ = ['local']

class _local(object):
    """
    Crappy Python 2.3 compatible implementation of thread-local storage
    """

    __slots__ = ('__thread_dict__',)

    def __init__(self):
        object.__setattr__(self, '__thread_dict__', weakref.WeakKeyDictionary())
        
    def __getattr__(self, attr):
        try:
            return self.__thread_dict__[threading.currentThread()][attr]
        except KeyError:
            raise AttributeError(attr)

    def __setattr__(self, attr, value):
        t = threading.currentThread()
        try:
            d = self.__thread_dict__[t]
        except KeyError:
            d = self.__thread_dict__[t] = {}
        d[attr] = value

try:
    local = threading.local
except AttributeError:
    local = _local
