"""\
@file exc.py
@brief Takes an exception object and returns a dictionary suitable for use debugging the exception later.

Copyright (c) 2005-2009, Donovan Preston

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


import linecache
import re
import sys
import traceback


def format_exc(exc=None):
    if exc is None:
        exc_type, exc_value, exc_tb = sys.exc_info()
    else:
        exc_type, exc_value, exc_tb = exc

    frames = []
    while exc_tb is not None:
        f = exc_tb.tb_frame
        
        frames.append((
            f.f_code.co_name,
            f.f_code.co_filename,
            exc_tb.tb_lineno,
            [(key, value) for (key, value)
             in f.f_locals.items() if key != '__builtins__'],
            [(key, value) for (key, value)
             in f.f_globals.items() if key != '__builtins__']))
        exc_tb = exc_tb.tb_next

    stack_trace = []

    result = {
        'error': True,
        'stack-trace': stack_trace,
        'description': str(exc_type) + ": " + str(exc_value),
        'text-exception': ''.join(
            traceback.format_exception(
                exc_type, exc_value, exc_tb))

        }

    for method, filename, lineno, local_vars, global_vars in frames:
        code = []
        vars_dict = {}
        stack_trace.append(
            {'filename': filename,
             'lineno': lineno,
             'method': method,
             'code': code,
             #'vars': vars_dict})
             })

        code_text = ''
        for line_number in range(lineno-2, lineno+2):
            line = linecache.getline(filename, line_number)
            code.append({'lineno': line_number, 'line': line})
            code_text += line

        # "self"
        for name, var in local_vars:
            if name == 'self' and hasattr(var, '__dict__'):
                vars_dict['self'] = dict([
                    (key, value) for (key, value) in var.__dict__.items()
                    if re.search(
                        r'\Wself.%s\W' % (re.escape(key),), code_text)])
                break

        # Local and global vars
        vars_dict['locals'] = dict(
            [(name, var) for (name, var) in local_vars
             if re.search(r'\W%s\W' % (re.escape(name),), code_text)])
        vars_dict['globals'] = dict(
            [(name, var) for (name, var) in global_vars
             if re.search(r'\W%s\W' % (re.escape(name),), code_text)])

    return result
