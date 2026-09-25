"""Checks for reliable runtime evidence without requiring a running Kodi."""
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("kodi_dev", TOOLS / "kodi_dev.py")
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


class KodiDevTests(unittest.TestCase):
    def test_log_cursor_excludes_old_errors_and_keeps_appended_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kodi.log"
            path.write_text("ERROR old\n")
            cursor = dev.LogCursor(path)
            with path.open("a") as stream:
                stream.write("info skin loaded...\nerror new\n context\n")
            self.assertEqual(dev.log_errors(cursor.read()), ["error new"])
            self.assertIn(" context", cursor.read())

    def test_truncated_log_cannot_pass_using_old_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kodi.log"
            path.write_text("old data" * 20)
            cursor = dev.LogCursor(path)
            path.write_text("new")
            with self.assertRaises(RuntimeError):
                cursor.read()

    def test_replaced_log_cannot_pass_using_old_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kodi.log"
            path.write_text("old")
            cursor = dev.LogCursor(path)
            path.rename(path.with_suffix(".old"))
            path.write_text("skin loaded...")
            with self.assertRaises(RuntimeError):
                cursor.read()

    def test_focus_candidates_include_parameterized_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Home.xml").write_text('''<window>
              <control id="511"/><control id="$PARAM[id]"/>
              <include><param name="id">9101</param></include>
              <param name="id" value="6001"/><param name="width">1920</param>
            </window>''')
            self.assertEqual(dev.control_ids(Path(tmp)), [511, 6001, 9101])

    def test_reload_timeout_preserves_fresh_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            log = directory / "source.log"
            log.write_text("old error\n")
            def send(_, **kwargs):
                with log.open("a") as stream:
                    stream.write("ERROR reload failed\n")
            with patch.object(dev, "LOG", log), patch.object(dev, "require_bald"), \
                 patch.object(dev.kodi_rpc, "builtin", side_effect=send), \
                 patch.object(dev, "wait_for", side_effect=RuntimeError("timeout")):
                with self.assertRaises(RuntimeError):
                    dev.reload_skin(directory, 0)
            self.assertEqual((directory / "kodi.log").read_text(), "ERROR reload failed\n")

    def test_capture_refuses_builtin_argument_injection(self):
        with patch.object(dev.kodi_rpc, "builtin") as send:
            with self.assertRaises(ValueError):
                dev.capture(Path('/tmp/bad"),Quit('))
            send.assert_not_called()

    def test_existing_output_directory_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "failure.json"
            path.write_text("prior evidence")
            with patch.object(sys, "argv", ["kodi_dev.py", "capture", "--output", tmp]), \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(dev.main(), 1)
            self.assertEqual(path.read_text(), "prior evidence")
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_selection_requires_nonempty_title_and_index(self):
        snapshot = {"focused_control_ids": [9101], "focused_items": {
            "Container(9101).CurrentItem": "", "Container(9101).ListItem.Title": ""}}
        self.assertFalse(dev.selection_restored(snapshot, snapshot))
        snapshot["focused_items"].update({"Container(9101).CurrentItem": "1",
                                          "Container(9101).ListItem.Title": "Movie"})
        self.assertTrue(dev.selection_restored(snapshot, snapshot))
        after = {"focused_items": dict(snapshot["focused_items"], **{"Container(9101).CurrentItem": "2"})}
        self.assertFalse(dev.selection_restored(snapshot, after))


if __name__ == "__main__":
    unittest.main()
