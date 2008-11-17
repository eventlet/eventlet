#!/usr/bin/python
import sys
import os
import sqlite3
import glob

REPO_URL = 'http://devel.ag-projects.com/~denis/cgi-bin/hgweb.cgi'

hubs_order = ['selecthub', 'poll', 'selects', 'libev', 'twistedr/selectreactor',
              'twistedr/pollreactor', 'twistedr/epollreactor']

def make_table(database):
    c = sqlite3.connect(database)
    res = c.execute(('select command_record.id, testname, hub, runs, errors, fails, '
                     'timeouts, exitcode, stdout from parsed_command_record join '
                     'command_record on parsed_command_record.id=command_record.id ')).fetchall()
    table = {} # testname -> hub -> test_result (runs, errors, fails, timeouts)
    tests = set()
    for id, testname, hub, runs, errors, fails, timeouts, exitcode, stdout in res:
        tests.add(testname)
        test_result = TestResult(runs, errors, fails, timeouts, exitcode, id, stdout)
        table.setdefault(testname, {})[hub] = test_result
    return table, sorted(tests)

def calc_hub_stats(table):
    hub_stats = {} # hub -> cumulative test_result
    for testname in table:
        for hub in table[testname]:
            test_result = table[testname][hub]
            hub_stats.setdefault(hub, TestResult(0,0,0,0)).__iadd__(test_result)
    hubs = hub_stats.items()
    hub_names = sorted(hub_stats.keys())
    def get_order(hub):
        try:
            return hubs_order.index(hub)
        except ValueError:
            return 100 + hub_names.index(hub)
    hubs.sort(key=lambda (hub, stats): get_order(hub))
    return hub_stats, [x[0] for x in hubs]

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

    @property
    def failed(self):
        return self.errors + self.fails

    @property
    def total(self):
        return self.runs + self.timeouts

    @property
    def percentage(self):
        return float(self.passed) / self.total

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
        if self.id is None:
            return 'white'
        if self.timeouts or self.exitcode in [7, 9, 10]:
            return 'red'
        elif self.errors or self.fails or self.exitcode:
            return 'yellow'
        else:
            return '"#72ff75"'

    def warnings(self):
        r = []
        if not self.failed and not self.timeouts:
            if self.exitcode in [7, 9, 10]:
                r += ['TIMEOUT']
            if self.exitcode:
                r += ['exitcode=%s' % self.exitcode]
            if self.output is not None:
                output = self.output.lower()
                warning = output.count('warning')
                if warning:
                    r += ['%s warnings' % warning]
                tracebacks = output.count('traceback')
                if tracebacks:
                    r += ['%s tracebacks' % tracebacks]
        return r

    def text(self):
        errors = []
        if self.fails:
            errors += ['%s failed' % self.fails]
        if self.errors:
            errors += ['%s raised' % self.errors]
        if self.timeouts:
            errors += ['%s timeout' % self.timeouts]
        errors += self.warnings()
        if self.id is None:
            errors += ['<hr>%s total' % self.total]
        return '\n'.join(["%s passed" % self.passed] + errors).replace(' ', '&nbsp;')

    # shorter passed/failed/raised/timeout
    def text_short(self):
        r = '%s/%s/%s' % (self.passed, self.failed, self.timeouts)
        if self.warnings():
            r += '\n' + '\n'.join(self.warnings()).replace(' ', '&nbsp;')
        return r
 
    def format(self):
        text = self.text().replace('\n', '<br>\n')
        if self.id is None:
            valign = 'bottom'
        else:
            text = '<a class="x" href="%s.txt">%s</a>' % (self.id, text)
            valign = 'center'
        return '<td align=center valign=%s bgcolor=%s>%s</td>' % (valign, self.color(), text)

def format_testname(changeset, test):
    return '<a href="%s/file/%s/greentest/%s">%s</a>' % (REPO_URL, changeset, test, test)

def format_table(table, hubs, tests, hub_stats, changeset):
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
        r += '<tr><td>%s</td>' % format_testname(changeset, test)
        for hub in hubs:
            test_result = table[test].get(hub)
            if test_result is None:
                r += '<td align=center bgcolor=gray>no data</td>'
            else:
                r += test_result.format() + '\n'
        r += '</tr>'

    r += '</table>'
    return r

def format_header(rev, changeset):
    url = '%s/log/%s' % (REPO_URL, changeset)
    return '<a href="%s">Eventlet changeset %s: %s</a><p>' % (url, rev, changeset)

def format_html(table, rev, changeset):
    r = '<html><head><style type="text/css">a.x {color: black; text-decoration: none;} </style></head><body>'
    r += format_header(rev, changeset)
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

def main(db):
    full_changeset = db.split('.')[1]
    rev, changeset = full_changeset.split('_', 1)
    table, tests = make_table(db)
    hub_stats, hubs = calc_hub_stats(table)
    report = format_html(format_table(table, hubs, tests, hub_stats, changeset), rev, changeset)
    path = '../htmlreports/%s' % full_changeset
    try:
        os.makedirs(path)
    except OSError, ex:
        if 'File exists' not in str(ex):
            raise
    file(path + '/index.html', 'w').write(report)
    generate_raw_results(path, db)

if __name__=='__main__':
    if not sys.argv[1:]:
        latest_db = sorted(glob.glob('results.*.db'))[-1]
        print latest_db
        sys.argv.append(latest_db)
    for db in sys.argv[1:]:
        main(db)

