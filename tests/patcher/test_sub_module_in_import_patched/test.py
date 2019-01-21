import eventlet
from tests import LimitedTestCase
import tests.patcher.test_sub_module_in_import_patched.sample_main_module


class ImportPatchedHandlesSubmoduleTest(LimitedTestCase):
    def test_sub_module_is_patched(self):
        patched_module = eventlet.import_patched(
            'tests.patcher.test_sub_module_in_import_patched.sample_main_module')
        print(patched_module.function_use_socket())
        assert patched_module.function_use_socket() is eventlet.green.socket
