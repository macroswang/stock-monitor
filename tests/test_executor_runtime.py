"""设备互斥、账号核验、总时限；测试中不连接 adb。"""
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from executor.adb import Adb, wait_until
from executor.identity import account_matches
from executor.runtime import budget, device_operation


class RuntimeTests(unittest.TestCase):
    def test_device_is_exclusive_across_processes(self):
        serial = "test-" + uuid.uuid4().hex
        class FakeAdb:
            def __init__(self): self.serial = serial
            def devices(self): return [serial]
        script = '''
import sys
from executor.runtime import device_operation
class Fake:
    serial = sys.argv[1]
    def devices(self): return [self.serial]
try:
    with device_operation(Fake()): print('unexpected-entry')
except RuntimeError: print('blocked')
'''
        with device_operation(FakeAdb()):
            result = subprocess.run([sys.executable, "-c", script, serial], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "blocked")

    def test_device_is_exclusive_across_threads(self):
        serial = "test-" + uuid.uuid4().hex
        class FakeAdb:
            def __init__(self): self.serial = serial
            def devices(self): return [serial]
        with device_operation(FakeAdb()):
            def competing():
                with self.assertRaisesRegex(RuntimeError, "其他操作"):
                    with device_operation(FakeAdb()):
                        self.fail("设备被并发占用")
            with ThreadPoolExecutor(1) as pool:
                pool.submit(competing).result()
        with device_operation(FakeAdb()):
            pass

    def test_ambiguous_device_selection_refused(self):
        class FakeAdb:
            serial = None
            def devices(self): return ["a", "b"]
        with self.assertRaisesRegex(RuntimeError, "唯一"):
            with device_operation(FakeAdb()): pass

    def test_subprocess_inherits_remaining_budget(self):
        with patch("executor.adb.subprocess.run", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as run:
            with budget(.05):
                Adb(adb="fake").run("devices", timeout=15)
            self.assertLessEqual(run.call_args.kwargs["timeout"], .05)

    def test_expired_budget_stops_even_a_tap(self):
        with patch("executor.adb.subprocess.run") as run:
            with budget(0):
                with self.assertRaises(TimeoutError): Adb(adb="fake").tap(1, 1)
            run.assert_not_called()

    def test_nested_wait_cannot_extend_outer_budget(self):
        with patch("executor.adb.subprocess.run", return_value=subprocess.CompletedProcess([], 0, b"ok", b"")) as run:
            with budget(.03):
                wait_until(lambda: Adb(adb="fake").shell("true"), 20)
            self.assertLessEqual(run.call_args.kwargs["timeout"], .03)

    def test_mask_matching_uses_all_visible_digits(self):
        self.assertTrue(account_matches("12**789", "123456789"))
        self.assertFalse(account_matches("13**789", "123456789"))
        self.assertFalse(account_matches("登录", "123456789"))
        self.assertFalse(account_matches("***89", "123456789"))
        self.assertFalse(account_matches("123456780", "123456789"))
        self.assertTrue(account_matches("**6789", "123456789"))

    def test_dump_reads_and_deletes_unique_path_in_one_command(self):
        xml = b'<hierarchy><node text="test"/></hierarchy>'
        with patch("executor.adb.subprocess.run", return_value=subprocess.CompletedProcess([], 0, xml, b"")) as run:
            adb = Adb(adb="fake")
            self.assertIn("<hierarchy>", adb.dump_xml(retries=1))
            first = run.call_args.args[0][-1]
            adb.dump_xml(retries=1)
            second = run.call_args.args[0][-1]
            self.assertNotEqual(first, second)
            self.assertIn("rm -f /sdcard/guanliang_", first)
            self.assertEqual(run.call_count, 2)
