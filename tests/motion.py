"""Reduce motion (Appearance › Behavior, Bald.ReduceMotion): every timed slide or zoom sits in an animation gated on
$EXP[Bald_FullMotion], with a twin under $EXP[Bald_ReduceMotion] (fades only, or the move at time 0). Tests about
the full-motion design read the skin through `full_motion`, which drops the twins and gives each gated animation back
the condition it had before the gate, so they can keep describing the motion itself."""

import copy

FULL = "$EXP[Bald_FullMotion]"
REDUCE = "$EXP[Bald_ReduceMotion]"


def split(condition):
    """(state, base): state is "full", "reduce" or None; base is the condition without the gate (None when the gate
    was the whole condition)."""
    if condition is None:
        return None, None
    for state, gate in (("full", FULL), ("reduce", REDUCE)):
        if condition == gate:
            return state, None
        suffix = f"] + {gate}"
        if condition.startswith("[") and condition.endswith(suffix):
            return state, condition[1:-len(suffix)]
    return None, condition


def _clean(elements):
    """The elements without reduce-motion twins, full-motion gates removed, recursively (in place)."""
    kept = []
    for element in elements:
        if element.tag == "animation":
            state, base = split(element.get("condition"))
            if state == "reduce":
                continue
            if state == "full":
                if base is None:
                    del element.attrib["condition"]
                else:
                    element.set("condition", base)
        children = _clean(list(element))
        for child in list(element):
            element.remove(child)
        element.extend(children)
        kept.append(element)
    return kept


def full_motion(node):
    """A copy of an element, or of a list of elements, as it reads without the reduce-motion twins."""
    if isinstance(node, list):
        return _clean(copy.deepcopy(node))
    return _clean([copy.deepcopy(node)])[0]
