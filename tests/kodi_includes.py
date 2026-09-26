"""Static models of Kodi's include resolution, for structural tests. Conditions, $VAR, $EXP and $INFO are not evaluated.

Two entry points:

- ``resolve_window(filename)`` expands every named include in one window from the definitions in all include files
  (``include_definitions``): <param> defaults and overrides, $PARAM[...] in text and attributes, and the caller's
  other children placed at <nested />. Used by the settings window tests.
- ``Skin`` loads Includes.xml and the files it names in order, keeping the first definition of each include, variable
  and expression name as CGUIIncludes does. The per-install Skin Variables output is skipped unless given, as on a
  fresh install. Used by the Home tests.
"""

import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN = Path(__file__).resolve().parents[1] / "1080i"
XML = SKIN
GENERATED = "script-skinvariables-generator-includes.xml"
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


EXP = re.compile(r"\$EXP\[([^\]]+)\]")
_ATOM = re.compile(r"(?<![A-Z])\[([^\[\]|+]*)\]")


def expressions(folder=SKIN):
    """Every <expression> body in the include files by name, first definition kept; the per-install Skin Variables
    output is skipped as on a fresh install."""
    bodies = {}
    for path in sorted(folder.glob("*.xml")):
        if path.name == GENERATED:
            continue
        root = ET.parse(path).getroot()
        if root.tag == "includes":
            for node in root.findall("expression"):
                bodies.setdefault(node.get("name"), node.text or "")
    return bodies


def expand(text, bodies=None):
    """Replace each $EXP[name] with its body until none is left, as Kodi flattens expressions. Unknown names stay."""
    bodies = bodies if bodies is not None else expressions()
    while True:
        expanded = EXP.sub(lambda match: bodies.get(match.group(1), match.group(0)), text)
        if expanded == text:
            return text
        text = expanded


def condition(text, bodies=None):
    """A condition in plain form for comparisons: expressions expanded, then the brackets around a single term or the
    whole condition dropped (the [...] each expression body is wrapped in) and double negation removed, so
    "!$EXP[Bald_HasRow]" reads "String.IsEmpty(Window(home).Property(Bald.Row))"."""
    text = expand(text or "", bodies)
    kept = []

    def keep(match):
        kept.append(match.group(0))
        return f"\0{len(kept) - 1}\0"

    text = re.sub(r"\$[A-Z]+\[[^\[\]]*\]", keep, text)
    while True:
        plain = _ATOM.sub(r"\1", text).replace("!!", "")
        if plain.startswith("[") and plain.endswith("]"):
            depth = 0
            for index, char in enumerate(plain):
                depth += (char == "[") - (char == "]")
                if depth == 0:
                    break
            if index == len(plain) - 1:
                plain = plain[1:-1]
        if plain == text:
            break
        text = plain
    return re.sub(r"\0(\d+)\0", lambda match: kept[int(match.group(1))], text)


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


class Skin:
    def __init__(self, generated=None):
        self.includes, self.expressions, self.variables = {}, {}, {}
        self.missing = []
        self.generated = generated
        self._load(XML / "Includes.xml")

    def _load(self, path):
        root = ET.parse(path).getroot()
        for node in root.findall("expression"):
            self.expressions.setdefault(node.get("name"), node.text or "")
        for node in root.findall("variable"):
            self.variables.setdefault(node.get("name"), node)
        for node in root.findall("include"):
            if node.get("name") and len(node):
                body = node.find("definition")
                defaults = {param.get("name"): param.text or "" for param in node.findall("param")}
                self.includes.setdefault(node.get("name"), (node if body is None else body, defaults))
            elif node.get("file") == GENERATED:
                if self.generated:
                    self._load(self.generated)
            elif node.get("file") and "IsLessOrEqual(System.ScreenHeight,720)" not in (node.get("condition") or ""):
                self._load(XML / node.get("file"))

    def window(self, name):
        root = ET.parse(XML / name).getroot()
        self._resolve(root)
        return root

    def _resolve(self, node):
        while True:
            call = next((child for child in node if child.tag == "include" and not child.get("file")), None)
            if call is None:
                break
            index = list(node).index(call)
            node.remove(call)
            name = call.get("content") or (call.text or "").strip()
            if name not in self.includes:
                self.missing.append(name)
                continue
            body, defaults = self.includes[name]
            params = dict(defaults)
            params.update({param.get("name"): param.text or "" for param in call.findall("param")})
            extra = [child for child in call if child.tag != "param"]
            for child in body:
                if child.tag == "param":
                    continue
                if child.tag == "nested":
                    inserted = [copy.deepcopy(element) for element in extra]
                else:
                    inserted = [copy.deepcopy(child)]
                    marker = inserted[0].find("nested")
                    if marker is not None:
                        at = list(inserted[0]).index(marker)
                        inserted[0].remove(marker)
                        for offset, element in enumerate(extra):
                            inserted[0].insert(at + offset, copy.deepcopy(element))
                    self._params(inserted[0], params)
                for element in inserted:
                    node.insert(index, element)
                    index += 1
        for child in node:
            self._resolve(child)

    @staticmethod
    def _params(node, params):
        def value(match):
            return params.get(match.group(1), "")
        for element in node.iter():
            if element.text:
                element.text = PARAM.sub(value, element.text)
            for key, text in list(element.attrib.items()):
                element.set(key, PARAM.sub(value, text))

    def unknown_references(self, root):
        text = ET.tostring(root, encoding="unicode")
        expressions = set(re.findall(r"\$EXP\[([^\]]+)\]", text)) - set(self.expressions)
        variables = set(re.findall(r"\$VAR\[([^,\]]+)", text))
        for variable in self.variables.values():
            for value in variable.findall("value"):
                variables |= set(re.findall(r"\$VAR\[([^,\]]+)", value.text or ""))
        return sorted(expressions | {f"$VAR[{name}]" for name in variables - set(self.variables)} | set(self.missing))
