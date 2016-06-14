from eventlet.support import six
import tests

__test__ = six.PY3


def test_green_http_doesnt_change_original_module():
    tests.run_isolated('green_http_doesnt_change_original_module.py')


def test_green_httplib_doesnt_change_original_module():
    tests.run_isolated('green_httplib_doesnt_change_original_module.py')
