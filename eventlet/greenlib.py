# Copyright (c) 2005-2006, Bob Ippolito
# Copyright (c) 2007, Linden Research, Inc.
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

from eventlet.api import Greenlet

class SwitchingToDeadGreenlet(Exception):
    pass

def switch(other=None, value=None, exc=None):
    self = Greenlet.getcurrent()
    if other is None:
        other = self.parent
    if other is None:
        other = self
    if not (other or hasattr(other, 'run')):
        raise SwitchingToDeadGreenlet("Switching to dead greenlet %r %r %r" % (other, value, exc))
    if exc:
        return other.throw(exc)
    else:
        return other.switch(value)        

import warnings
warnings.warn("greenlib is deprecated; use greenlet methods directly", DeprecationWarning, stacklevel=2)
