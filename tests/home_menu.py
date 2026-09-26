"""Read Home's main menu (grouplist 9000) the way Kodi resolves it, for tests."""

import copy
import xml.etree.ElementTree as ET
from pathlib import Path


XML = Path(__file__).resolve().parents[1] / "1080i"


def _includes():
    return ET.parse(XML / "Includes_Bald_Home.xml").getroot()


def entries():
    home = ET.parse(XML / "Home.xml").getroot()
    return [node for node in home.findall(".//control[@id='9000']/include") if node.get("content") == "Bald_HomeMenuButton"]


def entry(label=None, preview=None):
    for node in entries():
        if label is not None and node.findtext("param[@name='label']") == label:
            return node
        if preview is not None and node.findtext("param[@name='preview']") == preview:
            return node
    raise AssertionError(f"no menu entry {label or preview}")


def _expand(call, includes):
    """The elements a nested include call contributes, with its params substituted (one level, as used here)."""
    name = call.get("content") or (call.text or "").strip()
    definition = includes.find(f"include[@name='{name}']")
    params = {node.get("name"): node.text or "" for node in definition.findall("param")}
    params.update({node.get("name"): node.text or "" for node in call.findall("param")})
    body = definition.find("definition")
    result = []
    for child in (body if body is not None else definition):
        if child.tag == "param":
            continue
        child = copy.deepcopy(child)
        for node in child.iter():
            for key, value in list(node.attrib.items()):
                node.set(key, _substitute(value, params))
            if node.text:
                node.text = _substitute(node.text, params)
        result.append(child)
    return result


def _substitute(text, params):
    for key, value in params.items():
        text = text.replace(f"$PARAM[{key}]", value)
    return text


def nested(node):
    """The children an entry passes to the button (<nested />), with nested includes expanded."""
    includes = _includes()
    children = []
    for child in node:
        if child.tag == "param":
            continue
        children += _expand(child, includes) if child.tag == "include" else [child]
    return children


def actions(node, tag):
    return [(child.get("condition"), child.text) for child in nested(node) if child.tag == tag]


def select_actions(node):
    return actions(node, "onclick")
