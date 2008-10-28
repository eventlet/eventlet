#!/usr/bin/python
import sys
import os
import sqlite3

def make_table(database):
    c = sqlite3.connect(database)
    res = c.execute(('select command_record.id, testname, hub, runs, errors, fails, '
                     'timeouts, exitcode, stdout from parsed_command_record join '
                     'command_record on parsed_command_record.id=command_record.id ')).fetchall()
    table = {} # testname -> hub -> test_result (runs, errors, fails, timeouts)
    hub_stats = {} # hub -> cumulative test_result
    tests = set()
    for id, testname, hub, runs, errors, fails, timeouts, exitcode, stdout in res:
        tests.add(testname)
        test_result = TestResult(runs, errors, fails, timeouts, exitcode, id, stdout)
        table.setdefault(testname, {})[hub] = test_result
        hub_stats.setdefault(hub, TestResult(0,0,0,0)).__iadd__(test_result)
    hubs = hub_stats.items()
    hubs.sort(key=lambda t: t[1].passed, reverse=True)
    return table, [x[0] for x in hubs], sorted(tests), hub_stats

class TestResult:

    def __init__(self, runs, errors, fails, timeouts, exitcode=None, id=None, output=None):
        self.runs = runs
        self.errors = errors
        self.fails = fails
        self.timeouts = timeouts
        self.exitcode = exitcode
        self.id = id
        self.output = output

    @property
    def passed(self):
        return self.runs - self.errors - self.fails

    def __iadd__(self, other):
        self.runs += other.runs
        self.errors += other.errors
        self.fails += other.fails
        self.timeouts += other.timeouts
        if self.exitcode != other.exitcode:
            self.exitcode = None
        self.id = None
        self.output = None

    def color(self):
        if self.timeouts or self.exitcode in [7, 9, 10]:
            return 'red'
        elif self.errors or self.fails or self.exitcode:
            return 'yellow'
        else:
            return '"#72ff75"'

    def text(self):
        errors = []
        if self.fails:
            errors += ['%s failed' % self.fails]
        if self.errors:
            errors += ['%s raised' % self.errors]
        if self.timeouts:
            errors += ['%s timeout' % self.timeouts]
        if not errors:
            if self.exitcode in [7, 9, 10]:
                errors += ['TIMEOUT']
            if self.exitcode:
                errors += ['exitcode=%s' % self.exitcode]
            if self.output is not None:
                output = self.output.lower()
                warning = output.count('warning')
                if warning:
                    errors += ['%s warnings' % warning]
                tracebacks = output.count('traceback')
                if tracebacks:
                    errors += ['%s tracebacks' % tracebacks]
        return '\n'.join(["%s passed" % self.passed] + errors).replace(' ', '&nbsp;')
       
    def format(self):
        text = self.text().replace('\n', '<br>\n')
        if self.id is not None:
            text = '<a href="%s.txt">%s</a>' % (self.id, text)
        return '<td align=center bgcolor=%s>%s</td>' % (self.color(), text)

def format_table(table, hubs, tests, hub_stats):
    r = '<table border=1>\n<tr>\n<td/>\n'
    for hub in hubs:
        r += '<td align=center>%s</td>\n' % hub
    r += '</tr>\n'

    r += '<tr><td>Total</td>'
    for hub in hubs:
        test_result = hub_stats.get(hub)
        if test_result is None:
            r += '<td align=center bgcolor=gray>no data</td>'
        else:
            r += test_result.format() + '\n'
    r += '</tr>'

    r += '<tr><td colspan=%s/></tr>' % (len(hubs)+1)

    for test in tests:
        r += '<tr><td>%s</td>' % test
        for hub in hubs:
            test_result = table[test].get(hub)
            if test_result is None:
                r += '<td align=center bgcolor=gray>no data</td>'
            else:
                r += test_result.format() + '\n'
        r += '</tr>'

    r += '</table>'
    return r

def format_html(table):
    r = '<html><head><style type="text/css">a {color: black; text-decoration: none;} </style></head><body>'
    r += table
    r += '</body></html>'
    return r

def generate_raw_results(path, database):
    c = sqlite3.connect(database)
    res = c.execute('select id, stdout from command_record').fetchall()
    for id, out in res:
        file(os.path.join(path, '%s.txt' % id), 'w').write(out)
        sys.stderr.write('.')
    sys.stderr.write('\n')

def main():
    [db] = sys.argv[1:]
    r = make_table(db)
    report = format_html(format_table(*r))
    changeset = db.split('.')[1]
    path = '../htmlreports/%s' % changeset
    try:
        os.makedirs(path)
    except OSError, ex:
        if 'File exists' not in str(ex):
            raise
    file(path + '/index.html', 'w').write(report)
    generate_raw_results(path, db)

if __name__=='__main__':
    main()
