#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turn the upstream TinyPPI tree into Bald Process Info.

TinyPPI's code is AGPL, but its name, logo and original artwork are not
licensed for forks (upstream's LICENSE-ASSETS), and its author asked for a
fork to be clearly separate so support questions reach the right person. So
the fork's own commits never rename anything: they keep replaying onto
upstream unchanged, and this script is the last step, committed by
.github/workflows/follow-upstream.yml as "Fork branding (generated)". It:

* copies branding/ over the tree: our icon, fanart, overlay artwork, web
  icons, README, NOTICE and LICENSE-ASSETS (see tools/make_branding.py);
* renames the add-on: id script.bald.processinfo, window files
  script-baldpi-*.xml, property and log prefix BaldPI, and "Bald Process Info"
  wherever a person reads the name;
* rewrites addon.xml's metadata and sets the version to upstream's with
  FORK_REVISION appended (2.13.0 -> 2.13.0.2), so it is easy to tell which
  upstream release a build carries.

Links to the upstream project are left pointing at it. Idempotent.
"""

import re
import shutil
import sys
from pathlib import Path

FORK_REVISION = 3

ADDON_ID = "script.bald.processinfo"
NAME = "Bald Process Info"
SHORT = "BaldPI"
PROVIDER = "dangerouslaser"
SOURCE = "https://github.com/dangerouslaser/script.bald.processinfo"
SUMMARY = "Shows what the player is doing: video, audio, HDR and Dolby Vision output"
DESCRIPTION = (
    "An overlay with the codec, video, audio, HDR and Dolby Vision details of what is playing, "
    "and what the box is sending to the display. Runs on LibreELEC, including the Intel Dolby "
    "Vision build, and on CoreELEC. Based on the TinyPPI code by U3knOwn (AGPL-3.0-or-later); "
    "not affiliated with or supported by TinyPPI's author. Report problems at " + SOURCE + "/issues."
)

# Never rewritten: our own tooling, and anything that names the upstream project.
SKIP_DIRS = {".git", ".github", "branding", "tools", "tests"}
KEEP = ("CE-Repo/script.tinyppi", "ce-repo.github.io", "repository.jamal2362")
TEXT_SUFFIXES = {".py", ".xml", ".po", ".md", ".txt", ".html", ".js", ".css", ".json",
                 ".webmanifest", ".svg", ""}
# Files whose "TinyPPI" is read by people rather than code.
DISPLAY_FILES = re.compile(r"(\.po|index\.html|manifest\.webmanifest)$")


def _protect(text):
    for i, token in enumerate(KEEP):
        text = text.replace(token, f"\0KEEP{i}\0")
    return text


def _restore(text):
    for i, token in enumerate(KEEP):
        text = text.replace(f"\0KEEP{i}\0", token)
    return text


def rename_text(text, display=False):
    text = _protect(text)
    text = text.replace("script.tinyppi", ADDON_ID)
    text = text.replace("script-tinyppi-", "script-baldpi-")
    if display:
        text = text.replace("TinyPPI", NAME)
    text = text.replace("TinyPPI", SHORT).replace("TINYPPI", SHORT.upper())
    text = re.sub("tinyppi", "baldpi", text, flags=re.IGNORECASE)
    return _restore(text)


def _files(root):
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in SKIP_DIRS:
            continue
        if path.is_file():
            yield path


def copy_branding(root):
    """Copy branding/ over the tree; return the paths it wrote, which are ours
    already and are not renamed (the docs credit TinyPPI by name on purpose)."""
    branding = root / "branding"
    written = set()
    for src in sorted(branding.rglob("*")):
        rel = src.relative_to(branding)
        if rel.parts[0] == "_src" or not src.is_file():
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        written.add(rel)
    return written


def rename_paths(root):
    for path in list(_files(root)):
        if "tinyppi" in path.name.lower():
            path.rename(path.with_name(re.sub("tinyppi", "baldpi", path.name, flags=re.IGNORECASE)))


def rewrite_files(root, ours=frozenset()):
    for path in _files(root):
        if path.suffix not in TEXT_SUFFIXES or path.name in ("LICENSE",):
            continue
        if path.relative_to(root) in ours:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = rename_text(text, display=bool(DISPLAY_FILES.search(path.name)))
        if new != text:
            path.write_text(new, encoding="utf-8")


def _sub(pattern, repl, text, what, flags=0):
    new, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if not count:
        raise SystemExit(f"fork_branding: {what} not found in addon.xml")
    return new


def addon_xml(text):
    """Return addon.xml with the fork's identity and metadata."""
    def version(match):
        base = ".".join(match.group(2).split(".")[:3])
        return f'{match.group(1)}{base}.{FORK_REVISION}"'

    text = _sub(r'(<addon\b[^>]*?\bversion=")([^"]+)"', version, text, "version")
    text = _sub(r'(<addon\b[^>]*?\bid=")[^"]+"', rf'\g<1>{ADDON_ID}"', text, "id")
    text = _sub(r'(<addon\b[^>]*?\bname=")[^"]*"', rf'\g<1>{NAME}"', text, "name")
    text = _sub(r'(<addon\b[^>]*?\bprovider-name=")[^"]*"', rf'\g<1>{PROVIDER}"', text, "provider-name")
    text = _sub(
        r'(<import addon="script\.module\.sidedata"[^/]*?)(\s*optional="true")?\s*/>',
        lambda m: f'{m.group(1)} optional="true"/>', text, "script.module.sidedata import",
    )
    text = _sub(r"<source>[^<]*</source>", f"<source>{SOURCE}</source>", text, "<source>")
    # One English summary and description; the translations described TinyPPI.
    text = re.sub(r'\s*<summary lang="(?!en")[^"]+">.*?</summary>', "", text, flags=re.S)
    text = re.sub(r'\s*<description lang="(?!en")[^"]+">.*?</description>', "", text, flags=re.S)
    text = _sub(r'<summary lang="en">.*?</summary>', f'<summary lang="en">{SUMMARY}</summary>',
                text, "English summary", re.S)
    text = _sub(r'<description lang="en">.*?</description>',
                f'<description lang="en">{DESCRIPTION}</description>', text, "English description", re.S)
    return text


def apply(root):
    root = Path(root)
    ours = copy_branding(root)
    rename_paths(root)
    rewrite_files(root, ours)
    path = root / "addon.xml"
    path.write_text(addon_xml(path.read_text(encoding="utf-8")), encoding="utf-8")


def main():
    apply(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    main()
