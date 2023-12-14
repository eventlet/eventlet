"""Tests for the testing infrastructure."""

from . import run_python


def test_run_python_timeout():
    output = run_python('', args=('-c', 'import time; time.sleep(0.5)'), timeout=0.1)
    assert output.endswith(b'FAIL - timed out')


def test_run_python_pythonpath_extend():
    code = '''import os, sys ; print('\\n'.join(sys.path))'''
    output = run_python('', args=('-c', code), pythonpath_extend=('dira', 'dirb'))
    assert b'/dira\n' in output
    assert b'/dirb\n' in output
