import os
import unittest
from unittest.mock import patch

from executor import adb as adb_module
from executor.adb import find_selected, parse_nodes, resolve_adb


class ResolveAdbTests(unittest.TestCase):
    def test_explicit_path_wins(self):
        self.assertEqual(resolve_adb("/custom/adb"), "/custom/adb")

    def test_env_var_is_used_before_path_lookup(self):
        with patch.dict(os.environ, {"ADB_PATH": "/env/adb"}):
            self.assertEqual(resolve_adb(), "/env/adb")

    def test_known_locations_are_used_when_path_is_minimal(self):
        # Simulate a Finder-launched app: no adb on PATH.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ADB_PATH", None)
            with patch.object(adb_module.shutil, "which", return_value=None):
                resolved = resolve_adb()
        self.assertTrue(
            resolved.endswith("adb") or resolved.endswith("adb.exe"),
            resolved,
        )

    def test_falls_back_to_bare_command_when_nothing_exists(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ADB_PATH", None)
            with patch.object(adb_module.shutil, "which", return_value=None):
                with patch.object(adb_module, "_ADB_CANDIDATES", ("/nope/adb",)):
                    self.assertEqual(resolve_adb(), "adb")


class NodeParsingTests(unittest.TestCase):
    XML = """<hierarchy rotation="1">
  <node text="交易" resource-id="" class="android.widget.RelativeLayout"
        content-desc="交易" bounds="[536,1818][724,1920]" clickable="true"
        enabled="true" password="false" checked="false" selected="true"/>
  <node text="今日委托" resource-id="pkg:id/tab_name" class="android.widget.TextView"
        content-desc="" bounds="[36,819][172,869]" clickable="false"
        enabled="true" password="false" checked="false" selected="true"/>
</hierarchy>"""

    def test_content_desc_and_selected_are_parsed(self):
        nodes = parse_nodes(self.XML)
        tab = nodes[0]

        self.assertEqual(tab.description, "交易")
        self.assertTrue(tab.selected)
        self.assertEqual(find_selected(nodes, ("今日委托",)).text, "今日委托")


if __name__ == "__main__":
    unittest.main()
