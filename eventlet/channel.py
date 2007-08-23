"""\
@file channel.py
@author Bob Ippolito

Copyright (c) 2005-2006, Bob Ippolito
Copyright (c) 2007, Linden Research, Inc.
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

import collections

from eventlet import api, greenlib

import greenlet

__all__ = ['channel']

class channel(object):
    """A channel is a control flow primitive for co-routines. It is a 
    "thread-like" queue for controlling flow between two (or more) co-routines.
    The state model is:
    
    * If one co-routine calls send(), it is unscheduled until another 
      co-routine calls receive().
    * If one co-rounte calls receive(), it is unscheduled until another 
      co-routine calls send().
    * Once a paired send()/receive() have been called, both co-routeines
      are rescheduled.

    This is similar to: http://stackless.com/wiki/Channels
    """
    balance = 0

    def _tasklet_loop(self):
        deque = self.deque = collections.deque()
        hub = api.get_hub()
        switch = greenlib.switch
        direction, caller, args = switch()
        try:
            while True:
                if direction == -1:
                    # waiting to receive
                    if self.balance > 0:
                        sender, args = deque.popleft()
                        hub.schedule_call(0, switch, sender)
                        hub.schedule_call(0, switch, caller, *args)
                    else:
                        deque.append(caller)
                else:
                    # waiting to send
                    if self.balance < 0:
                        receiver = deque.popleft()
                        hub.schedule_call(0, switch, receiver, *args)
                        hub.schedule_call(0, switch, caller)
                    else:
                        deque.append((caller, args))
                self.balance += direction
                direction, caller, args = hub.switch()
        finally:
            deque.clear()
            del self.deque
            self.balance = 0

    def _send_tasklet(self, *args):
        try:
            t = self._tasklet
        except AttributeError:
            t = self._tasklet = greenlib.tracked_greenlet()
            greenlib.switch(t, (self._tasklet_loop,))
        if args:
            return greenlib.switch(t, (1, greenlet.getcurrent(), args))
        else:
            return greenlib.switch(t, (-1, greenlet.getcurrent(), args))
        
    def receive(self):
        return self._send_tasklet()

    def send(self, value):
        return self._send_tasklet(value)

    def send_exception(self, exc):
        return self._send_tasklet(None, exc)
