"""Small, conservative LaTeX normalizers shared by preview and MTEF parsing.

The project receives a lot of OCR/Gemini-style school-math LaTeX.  A very
common form is ``\\sqrt3`` / ``\\sqrt 5`` instead of an explicit braced
radicand.  TeX accepts some of those forms, but different renderers/parsers can
interpret the following atom differently.  Canonicalising the root argument
keeps the preview and the editable MathType MTEF tree in sync.
"""
from __future__ import annotations

import re

_SQRT = r"\sqrt"
_FRAC_COMMANDS = {"frac", "dfrac", "tfrac", "cfrac"}
_ONE_ARG_COMMANDS = {
    "mathrm", "textrm", "text", "mbox", "mathit", "mathbf", "boldsymbol",
    "operatorname", "widehat", "hat", "overline", "underline", "vec",
}


def _command_end(s: str, i: int) -> tuple[str, int]:
    """Read a TeX command at *i* (which must point at backslash)."""
    if i >= len(s) or s[i] != "\\":
        return "", i
    j = i + 1
    if j >= len(s):
        return "", j
    if s[j].isalpha():
        k = j
        while k < len(s) and s[k].isalpha():
            k += 1
        return s[j:k], k
    return s[j], j + 1


def _balanced_end(s: str, i: int, opener: str, closer: str) -> int:
    """Return end-exclusive index of a balanced group, or ``i`` if invalid."""
    if i >= len(s) or s[i] != opener:
        return i
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c == "\\":  # escaped delimiter / command; skip command token
            _, j2 = _command_end(s, j)
            j = max(j + 1, j2)
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return i


def _skip_spaces(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def _argument_end(s: str, i: int) -> int:
    """Read one useful TeX/OCR atom starting at *i* and return end-exclusive.

    For digits we intentionally consume a whole numeric literal.  OCR commonly
    emits ``\\sqrt12`` intending ``\\sqrt{12}``, and this behaviour is more
    useful for school-math input than strict token-by-token TeX semantics.
    """
    i = _skip_spaces(s, i)
    if i >= len(s):
        return i

    if s[i] == "{":
        end = _balanced_end(s, i, "{", "}")
        return end if end > i else min(i + 1, len(s))

    if s[i] == "\\":
        name, end = _command_end(s, i)
        if not name:
            return min(i + 1, len(s))

        j = end
        if name == "sqrt":
            j = _skip_spaces(s, j)
            if j < len(s) and s[j] == "[":
                k = _balanced_end(s, j, "[", "]")
                if k > j:
                    j = k
            return _argument_end(s, j)

        if name in _FRAC_COMMANDS:
            for _ in range(2):
                j = _skip_spaces(s, j)
                k = _argument_end(s, j)
                if k <= j:
                    break
                j = k
            return j

        if name in _ONE_ARG_COMMANDS:
            j = _skip_spaces(s, j)
            k = _argument_end(s, j)
            return k if k > j else end

        # Symbols/functions like \alpha, \sin are one command token.
        return end

    # OCR-friendly whole number / decimal literal.
    if s[i].isdigit():
        m = re.match(r"\d+(?:[.,]\d+)?", s[i:])
        if m:
            return i + len(m.group(0))

    # Otherwise one TeX character atom (x, a, +, -, ...).
    return i + 1


def _normalize_sqrt_once(text: str) -> tuple[str, bool]:
    s = text or ""
    out: list[str] = []
    i = 0
    changed = False

    while i < len(s):
        if s.startswith(_SQRT, i):
            # Do not touch a longer command such as \sqrtest.
            after = i + len(_SQRT)
            if after < len(s) and s[after].isalpha():
                out.append(s[i])
                i += 1
                continue

            out.append(_SQRT)
            i = after

            # Preserve optional root index, canonicalising only the radicand.
            j = _skip_spaces(s, i)
            if j < len(s) and s[j] == "[":
                end_idx = _balanced_end(s, j, "[", "]")
                if end_idx > j:
                    out.append(s[j:end_idx])
                    i = end_idx
                else:
                    i = j
            else:
                i = j

            i = _skip_spaces(s, i)
            if i >= len(s):
                continue

            # Already canonical.  Do not skip the group: leaving its content in
            # the main scan lets nested unbraced roots be fixed too.
            if s[i] == "{":
                continue

            end = _argument_end(s, i)
            if end <= i:
                continue
            atom = s[i:end]
            out.append("{" + atom + "}")
            i = end
            changed = True
            continue

        out.append(s[i])
        i += 1

    return "".join(out), changed


def normalize_sqrt_groups(latex: str) -> str:
    """Canonicalise unbraced ``\\sqrt``/``\\sqrt[n]`` arguments.

    Examples:
      ``\\sqrt3`` -> ``\\sqrt{3}``
      ``\\sqrt 12`` -> ``\\sqrt{12}``
      ``\\sqrt\\alpha`` -> ``\\sqrt{\\alpha}``
      ``\\sqrt\\frac{a}{b}`` -> ``\\sqrt{\\frac{a}{b}}``
      ``\\sqrt[3]5`` -> ``\\sqrt[3]{5}``

    The pass is repeated a few times so nested forms are normalised as well.
    """
    s = latex or ""
    for _ in range(8):
        s2, changed = _normalize_sqrt_once(s)
        s = s2
        if not changed:
            break
    return s
