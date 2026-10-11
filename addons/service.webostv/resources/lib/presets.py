"""Picture preset names: grouping by HDR type and friendly labels.

webOS keeps separate preset sets per signal type and names them with a
prefix: SDR presets are bare ("cinema"), HDR10/HLG presets start with
"hdr" ("hdrCinema"), Dolby Vision presets with "dolbyHdr".
"""

from __future__ import annotations

import re

# Presets for TVs whose webOS won't list them (webOS 5.x, 2020 OLEDs such as
# the CX): the set those models offer. Setting works there; reading doesn't.
FALLBACK_MODES = (
    "vivid", "normal", "eco", "cinema", "sports", "game", "filmMaker", "expert1", "expert2",
    "hdrVivid", "hdrStandard", "hdrCinemaBright", "hdrCinema", "hdrGame", "hdrFilmMaker",
    "dolbyHdrVivid", "dolbyHdrStandard", "dolbyHdrCinemaBright", "dolbyHdrCinema", "dolbyHdrGame",
)

# Rule kind -> settings id
SETTING_IDS = {
    "sdr": "preset_sdr",
    "hdr10": "preset_hdr10",
    "hlg": "preset_hlg",
    "dolbyvision": "preset_dv",
}

_BASE_LABELS = {
    "filmMaker": "Filmmaker Mode",
    "cinema": "Cinema",
    "cinemaBright": "Cinema Home",
    "expert1": "Expert (Bright room)",
    "expert2": "Expert (Dark room)",
    "normal": "Standard",
    "standard": "Standard",
    "vivid": "Vivid",
    "eco": "Eco",
    "sports": "Sports",
    "game": "Game Optimizer",
    "personalized": "Personalized",
    "photo": "Photo",
}


def family(value: str) -> str:
    """Return "dolbyvision", "hdr" or "sdr" for a preset name."""
    if value.startswith("dolbyHdr"):
        return "dolbyvision"
    if value.startswith("hdr"):
        return "hdr"
    return "sdr"


def base_name(value: str) -> str:
    for prefix in ("dolbyHdr", "hdr"):
        if value.startswith(prefix) and len(value) > len(prefix):
            rest = value[len(prefix):]
            return rest[0].lower() + rest[1:]
    return value


def label(value: str) -> str:
    base = base_name(value)
    name = _BASE_LABELS.get(base) or re.sub(r"(?<!^)(?=[A-Z0-9])", " ", base).capitalize()
    suffix = {"hdr": " (HDR)", "dolbyvision": " (Dolby Vision)"}.get(family(value), "")
    return f"{name}{suffix}"


def for_kind(kind: str, values: list[str]) -> list[str]:
    """Presets that apply to a rule kind (HLG uses the HDR set)."""
    wanted = {"sdr": "sdr", "hdr10": "hdr", "hlg": "hdr", "dolbyvision": "dolbyvision"}[kind]
    return [v for v in values if family(v) == wanted]


# Context-menu "intents": preferred presets in order; the first one that
# exists for the playing signal type wins.
INTENTS = {
    "filmmaker": [
        "filmMaker", "hdrFilmMaker", "dolbyHdrFilmMaker",
        "expert2", "cinema", "hdrCinema", "dolbyHdrCinema",
    ],
    "bright": [
        "expert1", "hdrCinemaBright", "dolbyHdrCinemaBright",
        "normal", "hdrStandard", "dolbyHdrStandard",
    ],
}
KIND_FAMILY = {"sdr": "sdr", "hdr10": "hdr", "hlg": "hdr", "dolbyvision": "dolbyvision"}
# SDR "normal" is called "standard" in the HDR sets.
_SDR_BASE = {"standard": "normal"}
_HDR_BASE = {"normal": "standard"}


def equivalents(value: str) -> list[str]:
    """The same preset in each family, starting with the value itself."""
    base = base_name(value)
    hdr_base = _HDR_BASE.get(base, base)
    cap = hdr_base[:1].upper() + hdr_base[1:]
    names = [value, _SDR_BASE.get(base, base), f"hdr{cap}", f"dolbyHdr{cap}"]
    return list(dict.fromkeys(names))


def candidates(choice: str) -> list[str]:
    """Presets to try for an intent name or a preset picked by the user."""
    return list(INTENTS.get(choice) or equivalents(choice))


def resolve(choices: list[str], kind: str | None, modes: list[dict]) -> str | None:
    """Pick the first choice valid for the signal.

    kind is the playing HDR type; when unknown, fall back to the modes the
    TV marks visible for the current signal. modes is TvController.picture_modes().
    """
    known = {m["value"] for m in modes}
    if kind in KIND_FAMILY:
        wanted = KIND_FAMILY[kind]
        for choice in choices:
            if family(choice) == wanted and (not known or choice in known):
                return choice
        return None
    visible = {m["value"] for m in modes if m.get("visible")}
    return next((c for c in choices if c in visible), None)
