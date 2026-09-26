#!/usr/bin/env python3
"""Small dependency-free validation for a built Kodi repository."""

from __future__ import annotations

import hashlib
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def main() -> None:
    root = Path(sys.argv[1])
    assert (root.parent / "index.html").is_file()
    index = root / "addons.xml"
    payload = index.read_bytes()
    assert hashlib.md5(payload).hexdigest() == (root / "addons.xml.md5").read_text().strip()
    addons = {node.attrib["id"]: node for node in ET.parse(index).getroot()}
    assert {"skin.bald", "script.bald.xcsetup", "repository.bald"} <= addons.keys()
    assert addons["skin.bald"].find("./requires/import[@addon='xbmc.gui']").attrib["version"] == "5.18.0"
    assert addons["script.bald.xcsetup"].find(
        "./requires/import[@addon='pvr.iptvsimple']"
    ).attrib["version"].startswith("22.")
    repository_version = addons["repository.bald"].attrib["version"]
    assert "minversion" not in addons["repository.bald"].find(
        "./extension[@point='xbmc.addon.repository']/dir"
    ).attrib
    assert (root.parent / f"repository.bald-{repository_version}.zip").is_file()

    for addon_id, node in addons.items():
        version = node.attrib["version"]
        archive = root / addon_id / f"{addon_id}-{version}.zip"
        assert archive.is_file(), archive
        with zipfile.ZipFile(archive) as zipped:
            names = set(zipped.namelist())
            assert f"{addon_id}/addon.xml" in names
            parsed = ET.fromstring(zipped.read(f"{addon_id}/addon.xml"))
            assert parsed.attrib["id"] == addon_id
            assert parsed.attrib["version"] == version

    xc_version = addons["script.bald.xcsetup"].attrib["version"]
    xc_zip = root / "script.bald.xcsetup" / f"script.bald.xcsetup-{xc_version}.zip"
    with zipfile.ZipFile(xc_zip) as zipped:
        names = set(zipped.namelist())
        assert "script.bald.xcsetup/default.py" in names
        assert "script.bald.xcsetup/resources/settings.xml" in names
        assert "script.bald.xcsetup/resources/language/resource.language.en_gb/strings.po" in names
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)

    skin_version = addons["skin.bald"].attrib["version"]
    skin_zip = root / "skin.bald" / f"skin.bald-{skin_version}.zip"
    with zipfile.ZipFile(skin_zip) as zipped:
        names = set(zipped.namelist())
        assert "skin.bald/shortcuts/skinvariables-generator.json" in names
        assert "skin.bald/shortcuts/generator/home-widgets.xml" in names
        assert "skin.bald/shortcuts/skinvariables-shortcut-homewidgets.json" in names
        assert "skin.bald/playlists/inprogress_movies.xsp" in names
        assert "skin.bald/playlists/inprogress_episodes.xsp" in names

    assert (root / "skin.bald" / "resources" / "icon.png").is_file()
    assert (root / "skin.bald" / "resources" / "fanart.jpg").is_file()


if __name__ == "__main__":
    main()
