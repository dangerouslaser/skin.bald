"""packaging/repository.bald/build_repository.py: where it may write, and that what it publishes comes from the
revision, not the working tree."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import ROOT, load_file

build = load_file("bald_build_repository_test", ROOT / "packaging" / "repository.bald" / "build_repository.py")


class OutputTests(unittest.TestCase):
    def refused(self, path):
        with self.assertRaises(SystemExit):
            build.check_output(Path(path))

    def test_the_checkout_home_and_their_ancestors_are_refused(self):
        for path in ("/", Path.home(), Path.home().parent, ROOT, ROOT.parent, ROOT / ".."):
            with self.subTest(path=path):
                self.refused(path)

    def test_a_direct_child_of_the_checkout_or_home_is_refused(self):
        # Its parent would receive index.html and the repository zip.
        self.refused(ROOT / "kodi")
        self.refused(Path.home() / "kodi")

    def test_a_folder_inside_the_checkout_is_allowed(self):
        build.check_output(ROOT / "_site" / "kodi")  # the release workflow's output (new in a CI checkout)

    def test_only_new_empty_or_previously_built_folders(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(build, "ROOT", Path(directory) / "repo"):
            output = Path(directory) / "site" / "kodi"
            build.check_output(output)  # new
            output.mkdir(parents=True)
            build.check_output(output)  # empty
            (output / "notes.txt").write_text("mine")
            self.refused(output)  # someone else's
            (output / "addons.xml.md5").write_text("0")
            build.check_output(output)  # a feed built before
            file = Path(directory) / "file"
            file.write_text("x")
            self.refused(file)


class RevisionTests(unittest.TestCase):
    def test_metadata_comes_from_the_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build.copy_metadata(output, "HEAD", "repository.bald", build.REPOSITORY_SOURCE)
            for name in ("icon.png", "fanart.jpg"):
                self.assertEqual((output / "repository.bald" / name).read_bytes(),
                                 build.git_file("HEAD", f"{build.REPOSITORY_SOURCE}/{name}"))
            build.copy_metadata(output, "HEAD", "skin.bald", "resources", "resources")
            shots = sorted(path.name for path in (output / "skin.bald" / "resources").glob("screenshot-*.jpg"))
            tracked = sorted(path.rsplit("/", 1)[1] for path in build.git_tree_files("HEAD", "resources")
                             if path.count("/") == 1 and path.rsplit("/", 1)[1].startswith("screenshot-"))
            self.assertEqual(shots, tracked)


if __name__ == "__main__":
    unittest.main()
