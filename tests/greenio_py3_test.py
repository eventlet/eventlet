# !/usr/bin/env python
# -*- coding:utf-8 -*-
"""
Test eventlet.greenio.py3.GreenFileIO.writable()
Create at 2022-06-22 21:05 by Zhichao Wu
"""
import os
import shutil
import tempfile
import unittest

import tests
from eventlet import greenio
from eventlet.green import os


# class TestDocTest():
#     """
#
#     >>> d=TestDocTest()
#     >>> d.run()
#     1
#     >>> d.run()
#     2
#     """
#
#     def __init__(self):
#         self.count = 0
#
#     def run(self):
#         self.count += 1
#         return self.count
#
#
def read_file(filepath):
    with open(filepath, 'r') as fr:
        result = fr.read()
    return result


#
# class GreenFileIOTestCase(unittest.TestCase):
#     filepath = './1.txt'
#
#     def tearDown(self):
#         import os as sys_os
#         if sys_os.path.isfile(self.filepath):
#             sys_os.remove(self.filepath)
#
#
#     def test_writable(self):
#         filepath=self.filepath
#         # case 1:write file by mode 'w'
#         expected = 'test eventlet.greenio.py3.GreenFileIO write with mode "w".'
#         with os.fdopen(os.open(filepath, O_RDWR | O_CREAT, 0o777), 'w') as fw:
#             fw.write(expected)
#         self.assertEqual(expected, read_file(filepath))
#
#         # case 2:write file by mode 'a'
#         expected_2 = 'test eventlet.greenio.py3.GreenFileIO write with mode "a".'
#         with os.fdopen(os.open(filepath, O_RDWR | O_CREAT | O_APPEND, 0o777), 'a') as fa:
#         # with open(self.filepath, 'a') as fa:
#             fa.write(expected_2)
#         self.assertEqual(expected + expected_2, read_file(filepath))
#
#         error_flag = False
#         try:
#             with os.fdopen(os.open(filepath, O_RDWR | O_CREAT | O_APPEND, 0o777), 'r') as fw:
#                 fw.write(expected)
#         except OSError as e:
#             print(e)
#             error_flag = True
#         self.assertTrue(error_flag)


class TestGreenFileIO(tests.LimitedTestCase):
    @tests.skip_on_windows
    def setUp(self):
        super(self.__class__, self).setUp()
        self.tempdir = tempfile.mkdtemp('_green_file_io_test')

    def tearDown(self):
        shutil.rmtree(self.tempdir)
        super(self.__class__, self).tearDown()

    def test_write(self):
        filepath = os.path.join(self.tempdir, 'test_file_w.txt')
        writer = greenio.GreenPipe(filepath, 'w')
        excepted = "Test write to file with mode 'w'."
        writer.write(excepted)
        writer.close()

        actual = read_file(filepath)
        self.assertEqual(excepted, actual, msg='actual=%s,excepted=%s' % (actual, excepted))

    def test_append(self):
        filepath = os.path.join(self.tempdir, 'test_file_a.txt')
        old_data = 'Exist data...\n'
        with open(filepath, 'w')as fw:
            fw.write(old_data)
        writer = greenio.GreenPipe(filepath, 'a')
        new_data = "Test write to file with mode 'a'."
        writer.write(new_data)
        writer.close()

        excepted = old_data + new_data
        actual = read_file(filepath)
        self.assertEqual(excepted, actual, msg='actual=%s,excepted=%s' % (actual, excepted))

    def test_read_and_write(self):
        filepath = os.path.join(self.tempdir, 'test_file_rw.txt')
        with open(filepath, 'w'):
            pass
        writer = greenio.GreenPipe(filepath, 'r+')
        excepted = "Test write to file with mode 'r+'."
        writer.write(excepted)
        writer.close()

        actual = read_file(filepath)
        self.assertEqual(excepted, actual, msg='actual=%s,excepted=%s' % (actual, excepted))


if __name__ == '__main__':
    unittest.main()
