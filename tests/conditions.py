"""Kodi boolean conditions as logic, so tests compare what a condition means rather than how it is spelled.

A condition is parsed the way Kodi's InfoBool parser reads it, after $EXP[...] is flattened: `!` binds tightest, then
`+` (and), then `|` (or), and `[...]` groups. Everything between operators is an opaque atom, compared as text with
whitespace removed; `$INFO[...]`, `$PARAM[...]` and parentheses inside an atom stay part of it, and the atoms `true`
and `false` are constants. Nothing is evaluated against Kodi: `Skin.HasSetting(x)` is just a named proposition.

- ``equivalent(a, b)``: true for every assignment of the atoms (reordered terms, extra brackets, a condition moved
  into an expression and so on all compare equal).
- ``implies(a, b)``: whenever `a` holds, `b` holds ("this control only shows when X").
- ``atoms(a)``: every atom `a` mentions.
"""

import re

from kodi_includes import EXP, expressions


_REFERENCE = re.compile(r"\$[A-Z]+\[")
_BODIES = []


def _expand(text, bodies):
    """Each $EXP[name] replaced by its body in brackets, as Kodi flattens expressions (CGUIIncludes wraps every
    expression it loads in [...]). Unknown names stay as atoms."""
    if bodies is None:
        if not _BODIES:
            _BODIES.append(expressions())
        bodies = _BODIES[0]
    for _ in range(50):
        expanded = EXP.sub(lambda m: f"[{bodies[m.group(1)]}]" if m.group(1) in bodies else m.group(0), text)
        if expanded == text:
            return text
        text = expanded
    raise ConditionError(f"expressions nest too deeply in {text[:80]!r}")


class ConditionError(ValueError):
    pass


def _tokens(text):
    """Operators, brackets and atoms. Brackets that open a $X[...] reference, or sit inside parentheses, belong to
    the atom around them."""
    tokens, atom, index, parens = [], [], 0, 0

    def flush():
        word = "".join(atom).strip()
        if word:
            tokens.append(("atom", re.sub(r"\s+", "", word)))
        atom.clear()

    while index < len(text):
        char = text[index]
        reference = _REFERENCE.match(text, index)
        if reference:
            depth, end = 0, reference.end() - 1
            while end < len(text):
                depth += {"[": 1, "]": -1}.get(text[end], 0)
                if depth == 0:
                    break
                end += 1
            atom.append(text[index:end + 1])
            index = end + 1
            continue
        if char == "(":
            parens += 1
        elif char == ")":
            parens -= 1
        if parens == 0 and char in "+|![]":
            flush()
            tokens.append(("op", char))
        else:
            atom.append(char)
        index += 1
    flush()
    return tokens


def parse(text, bodies=None):
    """A condition as a tree: ("and", [...]), ("or", [...]), ("not", x), ("atom", name), True or False."""
    tokens = _tokens(_expand(text or "", bodies))
    position = 0

    def peek():
        return tokens[position] if position < len(tokens) else (None, None)

    def take(expected=None):
        nonlocal position
        token = peek()
        if expected and token != ("op", expected):
            raise ConditionError(f"expected {expected!r} in {text!r}")
        position += 1
        return token

    def disjunction():
        terms = [conjunction()]
        while peek() == ("op", "|"):
            take()
            terms.append(conjunction())
        return terms[0] if len(terms) == 1 else ("or", terms)

    def conjunction():
        terms = [negation()]
        while peek() == ("op", "+"):
            take()
            terms.append(negation())
        return terms[0] if len(terms) == 1 else ("and", terms)

    def negation():
        if peek() == ("op", "!"):
            take()
            return ("not", negation())
        kind, value = take()
        if (kind, value) == ("op", "["):
            inner = disjunction()
            take("]")
            return inner
        if kind != "atom":
            raise ConditionError(f"unexpected {value!r} in {text!r}")
        return {"true": True, "false": False}.get(value.lower(), ("atom", value))

    if not tokens:
        raise ConditionError("empty condition")
    tree = disjunction()
    if position != len(tokens):
        raise ConditionError(f"trailing {tokens[position][1]!r} in {text!r}")
    return tree


def _atoms(tree, found):
    if isinstance(tree, bool):
        return found
    kind, value = tree
    if kind == "atom":
        found.add(value)
    elif kind == "not":
        _atoms(value, found)
    else:
        for term in value:
            _atoms(term, found)
    return found


def atoms(text, bodies=None):
    return _atoms(parse(text, bodies), set())


class _Bdd:
    """A reduced ordered binary decision diagram, variables ordered by atom text. Two conditions mean the same when
    they reduce to the same node, and this stays small for the or-of-rows shapes the skin's conditions have."""

    def __init__(self):
        self.unique, self.memo = {}, {}

    def node(self, name, low, high):
        if low == high:
            return low
        return self.unique.setdefault((name, low, high), (name, low, high))

    def build(self, tree):
        if isinstance(tree, bool):
            return tree
        kind, inner = tree
        if kind == "atom":
            return self.node(inner, False, True)
        if kind == "not":
            return self.negate(self.build(inner))
        result = kind == "and"
        for term in inner:
            result = self.apply(kind, result, self.build(term))
        return result

    def negate(self, node):
        if isinstance(node, bool):
            return not node
        key = ("not", node)
        if key not in self.memo:
            name, low, high = node
            self.memo[key] = self.node(name, self.negate(low), self.negate(high))
        return self.memo[key]

    def apply(self, kind, a, b):
        if isinstance(a, bool) or isinstance(b, bool):
            constant, other = (a, b) if isinstance(a, bool) else (b, a)
            return other if constant == (kind == "and") else constant
        if a == b:
            return a
        key = (kind, a, b)
        if key not in self.memo:
            name = min(a[0], b[0])
            a_low, a_high = (a[1], a[2]) if a[0] == name else (a, a)
            b_low, b_high = (b[1], b[2]) if b[0] == name else (b, b)
            self.memo[key] = self.node(name, self.apply(kind, a_low, b_low), self.apply(kind, a_high, b_high))
        return self.memo[key]

    def restrict(self, node, name, value):
        if isinstance(node, bool):
            return node
        if node[0] == name:
            return node[2] if value else node[1]
        return self.node(node[0], self.restrict(node[1], name, value), self.restrict(node[2], name, value))


def _tree(condition, bodies):
    return condition if isinstance(condition, (tuple, bool)) else parse(condition, bodies)


def implies(a, b, bodies=None, assume=None):
    """Whenever `a` holds, `b` holds. `assume` fixes atoms first ({"$PARAM[preview]": False})."""
    bdd = _Bdd()
    both = bdd.apply("and", bdd.build(_tree(a, bodies)), bdd.negate(bdd.build(_tree(b, bodies))))
    for name, value in (assume or {}).items():
        both = bdd.restrict(both, re.sub(r"\s+", "", name), value)
    return both is False


def equivalent(a, b, bodies=None):
    bdd = _Bdd()
    return bdd.build(_tree(a, bodies)) == bdd.build(_tree(b, bodies))


def all_of(conditions):
    """Several <visible> tags on one control, which Kodi ANDs."""
    return "[" + "] + [".join(conditions) + "]" if conditions else "true"


def same_actions(actual, expected, bodies=None):
    """Two lists of (condition, action) pairs are the same actions in the same order, conditions compared by meaning;
    a condition of None is unconditional."""
    return len(actual) == len(expected) and all(
        action == want and equivalent(cond or "true", want_cond or "true", bodies)
        for (cond, action), (want_cond, want) in zip(actual, expected))


def find_value(values, condition, bodies=None):
    """The first of (condition, value) pairs whose condition means `condition`; None when there is none."""
    return next((value for cond, value in values if cond is not None and equivalent(cond, condition, bodies)), None)


def has_action(actions, condition, action, bodies=None):
    """Some (condition, action) pair runs `action` under a condition that means `condition` (None: unconditional)."""
    return any(text == action and equivalent(cond or "true", condition or "true", bodies) for cond, text in actions)


def shows_for_content(visible, content):
    """A view container's <visible> means Container.Content(content) and stays literal: docs/NOTES.md ("Named
    conditions") keeps view containers' own visibility out of $EXP."""
    return "$EXP[" not in (visible or "") and equivalent(visible, f"Container.Content({content})")
