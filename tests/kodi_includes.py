"""A small static resolver for Kodi skin includes, for tests that check windows as Kodi would build them.

It expands named includes (``<include>Name</include>`` and ``<include content="Name">``) with their <param> defaults and
overrides, substitutes $PARAM[...] in text and attributes, and places the caller's other children at <nested />.
Include conditions, $VAR, $EXP and $INFO are left alone: they need a running Kodi.
"""
import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

SKIN = Path(__file__).resolve().parents[1] / "1080i"
PARAM = re.compile(r"\$PARAM\[([^\]]+)\]")


def include_definitions(folder=SKIN):
    definitions = {}
    for path in sorted(folder.glob("*.xml")):
        root = ET.parse(path).getroot()
        if root.tag != "includes":
            continue
        for node in root.findall("include"):
            if node.get("name"):
                definitions[node.get("name")] = node
    return definitions


def _params(node):
    return {param.get("name"): param.get("value", param.text or "") for param in node.findall("param")}


def _substitute(element, params):
    def replace(text):
        return PARAM.sub(lambda match: params.get(match.group(1), ""), text) if text else text

    for node in element.iter():
        node.text = replace(node.text)
        node.tail = replace(node.tail)
        for key, value in node.attrib.items():
            node.attrib[key] = replace(value)


class UnresolvedInclude(KeyError):
    pass


def _expand_in_place(parent, definitions):
    children = []
    for child in list(parent):
        if child.tag == "include" and not child.get("file"):
            children.extend(_expand_include(child, definitions))
        else:
            _expand_in_place(child, definitions)
            children.append(child)
    for child in list(parent):
        parent.remove(child)
    parent.extend(children)


def _expand_include(call, definitions):
    name = call.get("content") or (call.text or "").strip()
    if name not in definitions:
        raise UnresolvedInclude(name)
    definition = definitions[name]
    params = _params(definition)
    params.update(_params(call))
    body = definition.find("definition")
    source = body if body is not None else definition
    nested = [copy.deepcopy(child) for child in call if child.tag != "param"]

    holder = ET.Element("holder")
    holder.extend(copy.deepcopy(child) for child in source if child.tag != "param")
    _substitute(holder, params)
    for parent in list(holder.iter()):
        for index, child in enumerate(list(parent)):
            if child.tag == "nested":
                parent.remove(child)
                for offset, node in enumerate(nested):
                    parent.insert(index + offset, node)
    _expand_in_place(holder, definitions)
    return list(holder)


def resolve_window(filename, definitions=None):
    """Return the window's root element with every static include expanded."""
    definitions = definitions if definitions is not None else include_definitions()
    root = ET.parse(SKIN / filename).getroot()
    _expand_in_place(root, definitions)
    return root
