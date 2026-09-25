#!/usr/bin/env python3
"""Bald development checks. Standard library only; live commands target local Kodi."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

import kodi_rpc

ROOT = Path(__file__).resolve().parents[1]
KODI = Path.home() / "Library/Application Support/Kodi"
LOG = Path.home() / "Library/Logs/kodi.log"
ESTUARY = Path("/Applications/Kodi.app/Contents/Resources/Kodi/addons/skin.estuary")


class LogCursor:
    """Read appended bytes; refuse ambiguous results after rotation/truncation."""
    def __init__(self, path):
        self.path = path
        stat = path.stat()
        self.identity = (stat.st_dev, stat.st_ino)
        self.offset = stat.st_size

    def read(self):
        with self.path.open("rb") as stream:
            stat = os.fstat(stream.fileno())
            if (stat.st_dev, stat.st_ino) != self.identity or stat.st_size < self.offset:
                raise RuntimeError("Kodi log rotated or truncated; repeat the check with a fresh cursor")
            stream.seek(self.offset)
            return stream.read().decode("utf-8", errors="replace")


def log_errors(text):
    return [line for line in text.splitlines() if re.search(
        r"\b(?:error|fatal)\b|(?:xml.*(?:parse|parsing).*(?:fail|error))", line, re.I)]


@contextmanager
def runtime_lock():
    path = Path(tempfile.gettempdir()) / f"bald-kodi-{os.getuid()}.lock"
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another kodi_dev command owns the Kodi runtime") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def wait_for(probe, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = probe()
        if result:
            return result
        time.sleep(0.2)
    raise RuntimeError("Timed out waiting for Kodi to reach the expected state")


def control_ids(folder):
    ids = set()
    for path in folder.glob("*.xml"):
        for node in ET.parse(path).iter():
            value = node.get("id", "") if node.tag == "control" else ""
            if node.tag == "param" and node.get("name") == "id":
                value = (node.text or node.get("value") or "").strip()
            if value.isdigit():
                ids.add(int(value))
    return sorted(ids)


def state():
    ids = control_ids(ROOT / "1080i")
    focus = kodi_rpc.call("XBMC.GetInfoBooleans", {"booleans": [f"Control.HasFocus({i})" for i in ids]})
    focused = [i for i in ids if focus.get(f"Control.HasFocus({i})")]
    return {
        "focused_control_ids": focused,
        "focused_items": kodi_rpc.call("XBMC.GetInfoLabels", {"labels": [
            f"Container({i}).{field}" for i in focused for field in ("CurrentItem", "ListItem.Title")]
        }) if focused else {},
        "gui": kodi_rpc.call("GUI.GetProperties", {"properties": ["currentwindow", "currentcontrol", "skin"]}),
        "labels": kodi_rpc.call("XBMC.GetInfoLabels", {"labels": [
            "System.CurrentWindow", "System.CurrentControl", "Container.ListItem.Title",
            "Container.CurrentItem", "Container.NumItems", "System.ScreenWidth", "System.ScreenHeight"]}),
        "conditions": kodi_rpc.call("XBMC.GetInfoBooleans", {"booleans": [
            "Window.IsVisible(home)", "Window.IsVisible(movieinformation)", "Player.HasMedia"]}),
    }


def require_bald():
    snapshot = state()
    if snapshot["gui"]["skin"]["id"] != "skin.bald":
        raise RuntimeError("Active skin is not skin.bald; select Bald before this operation")
    if snapshot["conditions"]["Player.HasMedia"]:
        raise RuntimeError("Playback is active; stop playback before runtime checks")
    return snapshot


def doctor():
    checks = []

    def check(name, probe):
        try:
            ok, detail = probe()
            checks.append({"check": name, "ok": bool(ok), "detail": detail})
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            checks.append({"check": name, "ok": False, "detail": str(exc)})

    link = KODI / "addons/skin.bald"
    check("skin symlink", lambda: (link.is_symlink() and link.resolve() == ROOT, str(link.resolve())))
    check("log readable", lambda: (LOG.is_file() and os.access(LOG, os.R_OK), str(LOG)))
    expected = ET.parse(ROOT / "addon.xml").find("requires/import[@addon='xbmc.gui']").get("version")

    def estuary():
        actual = ET.parse(ESTUARY / "addon.xml").find("requires/import[@addon='xbmc.gui']").get("version")
        return actual == expected, {"skin_api": actual, "expected": expected}

    check("bundled Estuary API", estuary)

    def version():
        result = kodi_rpc.call("Application.GetProperties", {"properties": ["version", "name"]})
        return result["version"]["major"] == 22, result

    check("Kodi 22 / JSON-RPC", version)
    check("active skin", lambda: ((s := state())["gui"]["skin"]["id"] == "skin.bald", s))

    def eventserver():
        result = kodi_rpc.call("Settings.GetSettingValue", {"setting": "services.esenabled"})
        return result["value"] is True, "Enabled setting; delivery is verified by reload, not UDP send"

    check("EventServer enabled", eventserver)
    return {"checks": checks}, 0 if all(c["ok"] for c in checks) else 1


def validate():
    errors, warnings, parsed = [], [], {}
    for path in sorted(ROOT.rglob("*")):
        if path.suffix not in {".xml", ".xsp"} or any(p.startswith(".") for p in path.relative_to(ROOT).parts):
            continue
        try:
            parsed[path] = ET.parse(path).getroot()
        except ET.ParseError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    # Static include names only. Kodi expressions and conditional reachability need runtime review.
    xml_roots = [node for path, node in parsed.items() if path.parent == ROOT / "1080i"]
    names = {inc.get("name") for node in xml_roots for inc in node.iter("include") if inc.get("name")}
    for path, node in parsed.items():
        if path.parent != ROOT / "1080i":
            continue
        for inc in node.iter("include"):
            if inc.get("name") or inc.get("file"):
                continue
            name = inc.get("content") or (inc.text or "").strip()
            if name and "$" not in name and name not in names:
                warnings.append(f"{path.name}: unresolved static include {name!r}")
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                            cwd=ROOT, text=True, capture_output=True)
    return {"parsed_files": len(parsed), "errors": errors, "warnings": sorted(set(warnings)),
            "tests_exit_code": result.returncode, "tests": result.stdout + result.stderr}, bool(errors or result.returncode)


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def capture(directory, name="capture"):
    path = directory / f"{name}.png"
    # Kodi builtin arguments do not provide general-purpose escaping.
    if any(char in str(path) for char in '\"(),\n\r'):
        raise ValueError("Screenshot path cannot contain quotes, commas, parentheses or newlines")
    if path.exists():
        raise ValueError(f"Refusing to overwrite existing screenshot: {path}")
    kodi_rpc.builtin(f'TakeScreenshot("{path}")', announce=False)

    def ready():
        if not path.exists():
            return False
        data = path.read_bytes()
        if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n") or not data.endswith(b"IEND\xaeB`\x82"):
            return False
        return struct.unpack("!II", data[16:24])

    width, height = wait_for(ready)
    snapshot = state()
    save_json(directory / f"{name}.json", snapshot)
    return {"image": str(path), "width": width, "height": height, "state": snapshot}


def collect_log(cursor, directory):
    text = cursor.read()
    (directory / "kodi.log").write_text(text)
    return log_errors(text)


def reload_skin(directory, settle):
    require_bald()
    cursor = LogCursor(LOG)
    kodi_rpc.builtin("ReloadSkin()", announce=False)
    try:
        wait_for(lambda: "skin loaded..." in cursor.read().lower())
        time.sleep(settle)
        snapshot = require_bald()
    finally:
        errors = collect_log(cursor, directory)
    return {"reload_observed": True, "state": snapshot, "errors": errors}, bool(errors)


def selection_restored(before, after):
    values = before["focused_items"]
    valid = any(values.get(f"Container({i}).ListItem.Title") and
                values.get(f"Container({i}).CurrentItem", "").isdigit()
                for i in before["focused_control_ids"])
    return bool(valid) and values == after["focused_items"]


def smoke(directory, settle):
    require_bald()
    cursor = LogCursor(LOG)
    result = {"scenario": "home-info-back", "steps": []}
    try:
        kodi_rpc.call("GUI.ActivateWindow", {"window": "home"})

        def home_ready():
            s = state()
            return s if s["gui"]["currentwindow"]["id"] == 10000 and s["labels"]["Container.ListItem.Title"] else False

        wait_for(home_ready)
        time.sleep(settle)
        first = capture(directory, "01-home")
        result["steps"].append(first)
        before = first["state"]
        kodi_rpc.call("Input.Info")
        wait_for(lambda: state()["conditions"]["Window.IsVisible(movieinformation)"])
        time.sleep(settle)
        result["steps"].append(capture(directory, "02-info"))
        kodi_rpc.call("Input.Back")
        wait_for(home_ready)
        time.sleep(settle)
        last = capture(directory, "03-back")
        result["steps"].append(last)
        after = last["state"]
        result["selection_restored"] = selection_restored(before, after)
        control = before["focused_control_ids"]
        result["control_restored"] = bool(control) and control == after["focused_control_ids"]
        result["passed"] = result["selection_restored"] and result["control_restored"]
    except (OSError, RuntimeError, ValueError) as exc:
        result.update(passed=False, failure=str(exc))
    result["errors"] = collect_log(cursor, directory)
    return result, not result.get("passed", False) or bool(result["errors"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "validate", "state", "capture", "reload", "smoke"):
        command = sub.add_parser(name)
        if name in {"capture", "reload", "smoke"}:
            command.add_argument("--output", type=Path, help="New artifact directory (default: temporary directory)")
        if name in {"reload", "smoke"}:
            command.add_argument("--settle", type=float, default=2, help="Seconds to observe after transitions (0–30)")
        if name == "reload":
            command.add_argument("--check-log", action="store_true", help="Compatibility flag; fresh logs are always checked")
        if name == "smoke":
            command.add_argument("scenario", choices=["home-info-back"])
    args = parser.parse_args()
    directory = None
    try:
        if hasattr(args, "settle") and not 0 <= args.settle <= 30:
            raise ValueError("--settle must be between 0 and 30 seconds")
        if args.command == "doctor":
            result, code = doctor()
        elif args.command == "validate":
            result, code = validate()
        elif args.command == "state":
            result, code = state(), 0
        else:
            with runtime_lock():
                if args.output:
                    requested = args.output.expanduser().resolve()
                    requested.mkdir(parents=True, exist_ok=False)
                    directory = requested
                else:
                    directory = Path(tempfile.mkdtemp(prefix="bald-kodi-"))
                if args.command == "capture":
                    result, code = capture(directory), 0
                elif args.command == "reload":
                    result, code = reload_skin(directory, args.settle)
                else:
                    result, code = smoke(directory, args.settle)
                result["artifacts"] = str(directory)
                save_json(directory / "report.json", result)
    except (OSError, RuntimeError, ValueError, KeyError, ET.ParseError) as exc:
        result, code = {"error": str(exc)}, 1
        if directory and directory.is_dir():
            result["artifacts"] = str(directory)
            # Preserve evidence even when reload confirmation or capture times out.
            save_json(directory / "failure.json", result)
    print(json.dumps(result, indent=2))
    return int(code)


if __name__ == "__main__":
    sys.exit(main())
