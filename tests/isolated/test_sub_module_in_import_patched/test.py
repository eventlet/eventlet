import eventlet
import tests.isolated.test_sub_module_in_import_patched.sample_main_module as test_module


if __name__ == '__main__':
    assert test_module.function_use_socket() is not eventlet.green.socket
    patched_module = eventlet.import_patched(
        'tests.isolated.test_sub_module_in_import_patched.sample_main_module')
    assert patched_module.function_use_socket() is eventlet.green.socket
    print('pass')
