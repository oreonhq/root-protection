import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from rpctl.boot import entry_title
from rpctl.config import Config, DEFAULTS, dump_toml
from rpctl.detect import _parse_dm_name
from rpctl.snap import snapshot_lv_name
from rpctl import __version__


class TestParseDm(unittest.TestCase):
    def test_mapper_simple(self):
        self.assertEqual(_parse_dm_name("/dev/mapper/oreon-root"), ("oreon", "root"))

    def test_mapper_escaped_dash(self):
        self.assertEqual(_parse_dm_name("/dev/mapper/oreon--vg-root--lv"), ("oreon-vg", "root-lv"))

    def test_dev_vg_lv(self):
        self.assertEqual(_parse_dm_name("/dev/oreon/root"), ("oreon", "root"))


class TestConfig(unittest.TestCase):
    def test_defaults_roundtrip(self):
        text = dump_toml(DEFAULTS)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "c.toml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            cfg = Config.load(path)
            self.assertFalse(cfg.enabled)
            self.assertEqual(cfg.snapper_config, "root")
            self.assertEqual(cfg.get("retention", "timeline_limit_daily"), 7)
            self.assertTrue(cfg.get("health", "refuse_create_on_crit"))

    def test_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "c.toml")
            with open(path, "w", encoding="utf-8") as f:
                f.write('[general]\nenabled = true\nsnapper_config = "system"\n')
            cfg = Config.load(path)
            self.assertTrue(cfg.enabled)
            self.assertEqual(cfg.snapper_config, "system")
            self.assertEqual(cfg.get("health", "crit_data_percent"), 85)


class TestSnapNames(unittest.TestCase):
    def test_lv_name(self):
        self.assertEqual(snapshot_lv_name("root", 3), "root-snapshot3")
        self.assertEqual(entry_title(3, "daily timeline"), "root-protection snap 3 - daily timeline")


class TestVersion(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, "1.0.8")


class TestCliImport(unittest.TestCase):
    def test_parser(self):
        import runpy

        ns = runpy.run_path(os.path.join(ROOT, "root-protection"), run_name="rp_not_main")
        self.assertIn("build_parser", ns)
        p = ns["build_parser"]()
        args = p.parse_args(["version"])
        self.assertEqual(args.cmd, "version")


if __name__ == "__main__":
    unittest.main()
