"""\
@file logutil.py
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

import syslog
import logging


def file_logger(filename):
    """Create a logger. This sucks, the logging module sucks, but
    it'll do for now.
    """
    handler = logging.FileHandler(filename)
    formatter = logging.Formatter()
    handler.setFormatter(formatter)
    log = logging.getLogger(filename)
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    return log, handler


def stream_logger(stream):
    """Create a logger. This sucks."""
    handler = logging.StreamHandler(stream)
    formatter = logging.Formatter()
    handler.setFormatter(formatter)
    log = logging.getLogger()
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    return log, handler


class LineLogger(object):
    towrite = ''
    def __init__(self, emit=None):
        if emit is not None:
            self.emit = emit

    def write(self, stuff):
        self.towrite += stuff
        if '\n' in self.towrite:
            self.flush()

    def flush(self):
        try:
            newline = self.towrite.index('\n')
        except ValueError:
            newline = len(self.towrite)
        while True:
            self.emit(self.towrite[:newline])
            self.towrite = self.towrite[newline+1:]
            try:
                newline = self.towrite.index('\n')
            except ValueError:
                break

    def close(self):
        pass

    def emit(self, *args):
        pass


class SysLogger(LineLogger):
    """A file-like object which writes to syslog. Can be inserted
    as sys.stdin and sys.stderr to have logging output redirected
    to syslog.
    """
    def __init__(self, priority):
        self.priority = priority

    def emit(self, line):
        syslog.syslog(self.priority, line)


class TeeLogger(LineLogger):
    def __init__(self, one, two):
        self.one, self.two = one, two

    def emit(self, line):
        self.one.emit(line)
        self.two.emit(line)


class FileLogger(LineLogger):
    def __init__(self, file):
        self.file = file

    def emit(self, line):
        self.file.write(line + '\n')
        self.file.flush()

