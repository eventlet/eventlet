import os
import subprocess
import sys


def run_eventlet_import(code: str, warning_filter: str | None = None):
    env = os.environ.copy()
    env.pop("EVENTLET_TESTS", None)
    if warning_filter is None:
        env.pop("PYTHONWARNINGS", None)
    else:
        env["PYTHONWARNINGS"] = warning_filter

    return subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
    )


def test_deprecation_warning_can_be_filtered_by_category():
    code = """
import sys
import warnings
from eventlet_deprecation import EventletDeprecationWarning

assert "eventlet" not in sys.modules
warnings.filterwarnings("ignore", category=EventletDeprecationWarning)
import eventlet
assert eventlet.EventletDeprecationWarning is EventletDeprecationWarning
"""

    result = run_eventlet_import(code)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_deprecation_warning_can_be_filtered_by_message_from_environment():
    result = run_eventlet_import(
        "import eventlet",
        warning_filter="ignore:Eventlet is deprecated",
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
