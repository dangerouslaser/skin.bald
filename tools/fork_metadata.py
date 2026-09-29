#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apply the LibreELEC fork's addon.xml changes to upstream's addon.xml.

The fork's commits never touch addon.xml, so rebasing them onto a new upstream
release cannot conflict on its version line.  This script applies the fork's
edits on top instead, and .github/workflows/follow-upstream.yml commits the
result as the branch's last commit ("Fork metadata (generated)"), dropping the
previous one before every rebase.

The version is upstream's with FORK_REVISION appended (2.12.0 -> 2.12.0.1), so
it always sorts after the upstream release it is built on.  Raise
FORK_REVISION when the fork changes without a new upstream release.
"""

import re
import sys
from pathlib import Path

FORK_REVISION = 1

PROVIDER = "dangerouslaser"
SOURCE = "https://github.com/dangerouslaser/script.tinyppi"
DESCRIPTION_NOTE = (
    " This build also runs on LibreELEC, including the Intel Dolby Vision build,"
    " where the output signal is read from DRM instead of the Amlogic driver."
)


def _sub(pattern: str, repl, text: str, what: str) -> str:
    new, count = re.subn(pattern, repl, text, count=1)
    if not count:
        raise SystemExit(f"fork_metadata: {what} not found in addon.xml")
    return new


def apply(text: str) -> str:
    """Return ``text`` (an addon.xml) with the fork's edits applied."""
    def version(match):
        upstream = match.group(2)
        # Idempotent: a version already carrying a fork revision keeps its base.
        base = ".".join(upstream.split(".")[:3])
        return f'{match.group(1)}{base}.{FORK_REVISION}"'

    text = _sub(r'(<addon\b[^>]*?\bversion=")([^"]+)"', version, text, "version")

    def provider(match):
        names = match.group(2)
        if PROVIDER not in names:
            names = f"{names}, {PROVIDER}"
        return f'{match.group(1)}{names}"'

    text = _sub(r'(<addon\b[^>]*?\bprovider-name=")([^"]*)"', provider, text, "provider-name")

    text = _sub(
        r'(<import addon="script\.module\.sidedata"[^/]*?)(\s*optional="true")?\s*/>',
        lambda m: f'{m.group(1)} optional="true"/>',
        text,
        "script.module.sidedata import",
    )
    text = _sub(r"<source>[^<]*</source>", f"<source>{SOURCE}</source>", text, "<source>")

    def description(match):
        body = match.group(2)
        if DESCRIPTION_NOTE.strip() not in body:
            body += DESCRIPTION_NOTE
        return f"{match.group(1)}{body}{match.group(3)}"

    text = _sub(
        r'(<description lang="en">)(.*?)(</description>)', description, text, "English description"
    )
    return text


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "addon.xml")
    path.write_text(apply(path.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
