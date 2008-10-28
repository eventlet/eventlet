#!/usr/bin/python
"""Run the program and record stdout/stderr/exitcode into the database results.rev_changeset.db

Usage: %prog program [args]
"""
import sys
import os
import sqlite3
import warnings

warnings.simplefilter('ignore')

COMMAND_CHANGESET = r"hg log -r tip | grep changeset"

def record(changeset, argv, stdout, returncode):
    c = sqlite3.connect('results.%s.db' % changeset)
    c.execute('''create table if not exists command_record
              (id integer primary key autoincrement,
               command text,
               stdout text,
               exitcode integer)''')
    c.execute('insert into command_record (command, stdout, exitcode)'
              'values (?, ?, ?)', (`argv`, stdout, returncode))
    c.commit()

def main():
    argv = sys.argv[1:]
    if argv[0]=='-d':
        debug = True
        del argv[0]
    else:
        debug = False
    changeset = os.popen(COMMAND_CHANGESET).read().replace('changeset:', '').strip().replace(':', '_')
    output_name = os.tmpnam()
    arg = ' '.join(argv) + ' &> %s' % output_name
    print arg
    returncode = os.system(arg)>>8
    print arg, 'finished with code', returncode
    stdout = file(output_name).read()
    if not debug:
        record(changeset, argv, stdout, returncode)
        os.unlink(output_name)
    sys.exit(returncode)

if __name__=='__main__':
    main()

