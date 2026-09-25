#!/usr/bin/env python3
"""Build the static Kodi repository feed from a clean, tagged skin checkout."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_SOURCE = Path(__file__).resolve().parent
BUNDLED_ADDONS = ("addons/script.bald.xcsetup",)


def addon_identity(path: Path) -> tuple[str, str]:
    root = ET.parse(path).getroot()
    return root.attrib["id"], root.attrib["version"]


def tracked_files(revision: str) -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", revision], cwd=ROOT, text=True
    )
    files = {"addon.xml", "LICENSE.txt"}
    directories = ("1080i/", "colors/", "extras/", "fonts/", "language/", "media/", "resources/", "scripts/")
    return [
        line
        for line in output.splitlines()
        if line in files or line.startswith(directories)
    ]


def git_file(revision: str, relative_path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{revision}:{relative_path}"], cwd=ROOT)


def git_tree_files(revision: str, directory: str) -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", revision, "--", directory],
        cwd=ROOT,
        text=True,
    )
    return output.splitlines()


def zip_skin(output: Path, revision: str, version: str) -> Path:
    destination = output / "skin.bald" / f"skin.bald-{version}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative_path in tracked_files(revision):
            archive.writestr(f"skin.bald/{relative_path}", git_file(revision, relative_path))
    return destination


def zip_repository(output: Path, version: str) -> Path:
    destination = output / "repository.bald" / f"repository.bald-{version}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in ("addon.xml", "icon.png", "fanart.jpg"):
            archive.write(REPOSITORY_SOURCE / name, f"repository.bald/{name}")
    return destination


def zip_bundled_addon(output: Path, revision: str, source: str) -> ET.Element:
    addon_xml_path = f"{source}/addon.xml"
    addon_xml = git_file(revision, addon_xml_path)
    root = ET.fromstring(addon_xml)
    addon_id = root.attrib["id"]
    version = root.attrib["version"]
    destination = output / addon_id / f"{addon_id}-{version}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"{source}/"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative_path in git_tree_files(revision, source):
            archive_path = f"{addon_id}/{relative_path.removeprefix(prefix)}"
            archive.writestr(archive_path, git_file(revision, relative_path))
    return root


def copy_metadata(output: Path, addon_id: str, source_dir: Path) -> None:
    target = output / addon_id
    target.mkdir(parents=True, exist_ok=True)
    for name in ("icon.png", "fanart.jpg"):
        shutil.copy2(source_dir / name, target / name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--expected-version")
    args = parser.parse_args()

    skin_xml = git_file(args.revision, "addon.xml")
    with tempfile.NamedTemporaryFile() as handle:
        handle.write(skin_xml)
        handle.flush()
        skin_id, skin_version = addon_identity(Path(handle.name))
    repository_id, repository_version = addon_identity(REPOSITORY_SOURCE / "addon.xml")
    if skin_id != "skin.bald":
        raise SystemExit(f"unexpected skin id: {skin_id}")
    if args.expected_version and skin_version != args.expected_version:
        raise SystemExit(
            f"tag version {args.expected_version} does not match addon.xml {skin_version}"
        )

    output = args.output.resolve()
    if output in {Path("/"), Path.home().resolve(), ROOT.resolve()}:
        raise SystemExit(f"refusing unsafe output directory: {output}")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    zip_skin(output, args.revision, skin_version)
    repository_zip = zip_repository(output, repository_version)
    copy_metadata(output, skin_id, ROOT / "resources")
    copy_metadata(output, repository_id, REPOSITORY_SOURCE)

    skin_root = ET.fromstring(skin_xml)
    repository_root = ET.parse(REPOSITORY_SOURCE / "addon.xml").getroot()
    addons = ET.Element("addons")
    addons.append(skin_root)
    for source in BUNDLED_ADDONS:
        addons.append(zip_bundled_addon(output, args.revision, source))
    addons.append(repository_root)
    ET.indent(addons, space="  ")
    index = ET.tostring(addons, encoding="utf-8", xml_declaration=True)
    (output / "addons.xml").write_bytes(index + b"\n")
    (output / "addons.xml.md5").write_text(hashlib.md5(index + b"\n").hexdigest())
    shutil.copy2(repository_zip, output.parent / repository_zip.name)
    (output.parent / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Bald for Kodi 22</title>"
        "<main style='max-width:44rem;margin:10vh auto;padding:2rem;font:18px system-ui;line-height:1.5'>"
        "<h1>Bald for Kodi 22</h1><p>Install the repository ZIP in Kodi, then choose "
        "<strong>Install from repository → Bald Add-on Repository → Look and feel → Skin</strong>.</p>"
        f"<p><a href='{repository_zip.name}'>Download Bald Add-on Repository {repository_version}</a></p>"
        "</main>"
    )


if __name__ == "__main__":
    main()
