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
    assert {"skin.bald", "script.bald.xcsetup", "script.bald.helper", "repository.bald"} <= addons.keys()
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

    helper = addons["script.bald.helper"]
    assert helper.find("./extension[@point='xbmc.service']").attrib["library"] == "service.py"
    assert helper.find("./extension[@point='xbmc.python.pluginsource']").attrib["library"] == "plugin.py"
    helper_zip = root / "script.bald.helper" / f"script.bald.helper-{helper.attrib['version']}.zip"
    with zipfile.ZipFile(helper_zip) as zipped:
        names = set(zipped.namelist())
        assert "script.bald.helper/service.py" in names
        assert "script.bald.helper/resources/lib/keymap.py" in names
        assert "script.bald.helper/resources/lib/blur.py" in names
        assert "script.bald.helper/plugin.py" in names
        for module in ("follow", "mdblist", "ratings", "plugin"):
            assert f"script.bald.helper/resources/lib/{module}.py" in names
        assert "script.bald.helper/resources/settings.xml" in names
        assert "script.bald.helper/resources/language/resource.language.en_gb/strings.po" in names
        assert "script.bald.helper/resources/icon.png" in names
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
    assert (root / "script.bald.helper" / "resources" / "icon.png").is_file()
    # The blurred backgrounds need Kodi's Pillow module.
    assert helper.find("./requires/import[@addon='script.module.pil']") is not None
    # The skin never requires the helper (an optional import would re-enable a disabled helper on skin updates).
    assert addons["skin.bald"].find("./requires/import[@addon='script.bald.helper']") is None

    skin_version = addons["skin.bald"].attrib["version"]
    skin_zip = root / "skin.bald" / f"skin.bald-{skin_version}.zip"
    with zipfile.ZipFile(skin_zip) as zipped:
        names = set(zipped.namelist())
        assert "skin.bald/shortcuts/skinvariables-generator.json" in names
        assert "skin.bald/shortcuts/generator/screen.xml" in names
        assert "skin.bald/shortcuts/skinvariables-shortcut-homewidgets.json" in names
        assert "skin.bald/shortcuts/skinvariables-shortcut-livetvwidgets.json" in names
        assert "skin.bald/shortcuts/skinvariables-shortcut-hubs.json" in names
        assert "skin.bald/scripts/hubs.py" in names
        assert "skin.bald/shortcuts/generator/screens.xml" in names
        assert "skin.bald/1080i/Includes_Bald_HomeDefaults.xml" in names
        assert not any("script-skinvariables-generator-includes" in name for name in names)
        assert "skin.bald/playlists/inprogress_movies.xsp" in names
        assert "skin.bald/playlists/inprogress_episodes.xsp" in names
        # Files that started from Estuary point readers to its licence notice.
        assert "skin.bald/LICENSE.txt" in names
        assert "skin.bald/LICENSE-Estuary.txt" in names

    assert (root / "skin.bald" / "resources" / "icon.png").is_file()
    assert (root / "skin.bald" / "resources" / "fanart.jpg").is_file()
    # Screenshots addon.xml declares are published beside the icon (Kodi's add-on browser) and used by the site.
    page = (root.parent / "index.html").read_text(encoding="utf-8")
    for shot in addons["skin.bald"].findall("./extension[@point='xbmc.addon.metadata']/assets/screenshot"):
        assert (root / "skin.bald" / shot.text).is_file(), shot.text
        assert f'src="kodi/skin.bald/{shot.text}"' in page, shot.text
    # Kodi's HTTP directory parser only reads double-quoted links, so the site also works as a Kodi file source.
    assert f'href="repository.bald-{repository_version}.zip"' in page
    assert "href='" not in page


if __name__ == "__main__":
    main()
