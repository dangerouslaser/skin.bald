"""Bald's en_gb skin strings, for tests that check localized labels by meaning rather than by literal text."""

import re
from pathlib import Path


PO = Path(__file__).resolve().parents[1] / "language" / "resource.language.en_gb" / "strings.po"
BALD_RANGE = range(31700, 32000)
LOCALIZE = re.compile(r"\$LOCALIZE\[(\d+)\]")
_ENTRY = re.compile(r'^msgctxt "#(\d+)"\nmsgid "((?:[^"\\]|\\.)*)"', re.M)


def strings():
    """Every numbered skin string in en_gb, id -> msgid."""
    return {int(num): text for num, text in _ENTRY.findall(PO.read_text(encoding="utf-8"))}


def bald_strings():
    return {num: text for num, text in strings().items() if num in BALD_RANGE}


def loc(msgid):
    """The $LOCALIZE[...] that shows Bald's own string `msgid`; fails if Bald does not define it exactly once."""
    matches = [num for num, text in bald_strings().items() if text == msgid]
    if len(matches) != 1:
        raise AssertionError(f"Bald strings define {msgid!r} {len(matches)} times")
    return f"$LOCALIZE[{matches[0]}]"


def english(text):
    """`text` with Bald's own $LOCALIZE ids replaced by their en_gb wording; Kodi core ids are left as written."""
    table = bald_strings()
    return LOCALIZE.sub(lambda m: table.get(int(m.group(1)), m.group(0)), text or "")
