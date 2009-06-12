# Copyright (c) 2006-2007, Linden Research, Inc.
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

import errno
import os
import popen2
import signal

from eventlet import coros
from eventlet import pools
from eventlet import greenio


class DeadProcess(RuntimeError):
    pass


CHILD_POBJS = []

CHILD_EVENTS = {}


def wait_on_children():
    global CHILD_POBJS
    unclosed_pobjs = []
    for child_pobj in CHILD_POBJS:
        try:
            # We have to use poll() rather than os.waitpid because
            # otherwise the popen2 module leaks fds; hat tip to Brian
            # Brunswick
            code = child_pobj.poll()
            if code == -1:
                unclosed_pobjs.append(child_pobj)
                continue ## Wasn't this one that died

            event = CHILD_EVENTS.pop(child_pobj, None)
            if event:
                event.send(code)
        except OSError, e:
            if e[0] == errno.ECHILD:
                print "already dead"
                # Already dead; signal, but assume success
                event = CHILD_EVENTS.pop(child_pobj, None)
                event.send(0)
            else:
                print "raising"
                raise e
    
    CHILD_POBJS = unclosed_pobjs


def sig_child(signal, frame):
    from eventlet import api
    api.call_after(0, wait_on_children)
signal.signal(signal.SIGCHLD, sig_child)
    

def _add_child_pobj(pobj):
    """Add the given popen4 object to the list of child
    processes we are tracking. Return an event object
    that can be used to get the process' exit code.
    """
    CHILD_POBJS.append(pobj)
    event = coros.event()
    CHILD_EVENTS[pobj] = event
    return event


class Process(object):
    process_number = 0
    def __init__(self, command, args, dead_callback=lambda:None):
        self.process_number = self.process_number + 1
        Process.process_number = self.process_number
        self.command = command
        self.args = args
        self._dead_callback = dead_callback
        self.run()

    def run(self):
        self.dead = False
        self.started = False
        self.popen4 = None

        ## We use popen4 so that read() will read from either stdout or stderr
        self.popen4 = popen2.Popen4([self.command] + self.args)
        self.event = _add_child_pobj(self.popen4)
        child_stdout_stderr = self.popen4.fromchild
        child_stdin = self.popen4.tochild
        greenio.set_nonblocking(child_stdout_stderr)
        greenio.set_nonblocking(child_stdin)
        self.child_stdout_stderr = greenio.GreenPipe(child_stdout_stderr)
        self.child_stdout_stderr.newlines = '\n'  # the default is \r\n, which aren't sent over pipes
        self.child_stdin = greenio.GreenPipe(child_stdin)
        self.child_stdin.newlines = '\n'

        self.sendall = self.child_stdin.write
        self.send = self.child_stdin.write
        self.recv = self.child_stdout_stderr.read
        self.readline = self.child_stdout_stderr.readline

    def dead_callback(self):
        self.dead = True
        if self._dead_callback:
            self._dead_callback()

    def makefile(self, mode, *arg):
        if mode.startswith('r'):
            return self.child_stdout_stderr
        if mode.startswith('w'):
            return self.child_stdin
        raise RuntimeError("Unknown mode", mode)

    def read(self, amount=None):
        result = self.child_stdout_stderr.read(amount)
        if result == '':
            # This process is dead.
            self.dead_callback()
            raise DeadProcess
        return result

    def write(self, stuff):
        written = 0
        try:
            written = self.child_stdin.write(stuff)
            self.child_stdin.flush()
        except ValueError, e:
            ## File was closed
            assert str(e) == 'I/O operation on closed file'
        if written == 0:
            self.dead_callback()
            raise DeadProcess

    def flush(self):
        self.child_stdin.flush()

    def close(self):
        self.child_stdout_stderr.close()
        self.child_stdin.close()
        self.dead_callback()

    def close_stdin(self):
        self.child_stdin.close()

    def kill(self, sig=None):
        if sig == None:
            sig = signal.SIGTERM
        os.kill(self.popen4.pid, sig)

    def getpid(self):
        return self.popen4.pid

    def wait(self):
        return self.event.wait()


class ProcessPool(pools.Pool):
    def __init__(self, command, args=None, min_size=0, max_size=4):
        """@param command the command to run
        """
        self.command = command
        if args is None:
            args = []
        self.args = args
        pools.Pool.__init__(self, min_size, max_size)

    def create(self):
        """Generate a process
        """
        def dead_callback():
            self.current_size -= 1
        return Process(self.command, self.args, dead_callback)

    def put(self, item):
        if not item.dead:
            if item.popen4.poll() != -1:
                item.dead_callback()
            else:
                pools.Pool.put(self, item)
