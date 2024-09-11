import eventlet
import tests


def test_pathlib_open_issue_534():
    pathlib = eventlet.import_patched('pathlib')
    path = pathlib.Path(__file__)
    with path.open():
        # should not raise
        pass


def test_os_read_nonblocking():
    tests.run_isolated('os_read_nonblocking.py')


def test_os_write_nonblocking():
    tests.run_isolated('os_write_nonblocking.py')
