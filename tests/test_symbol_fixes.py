"""Regression tests for common school-math relation/fence symbols.

These tests intentionally avoid Word/olefile so the parser/preview fixes can be
checked in a lightweight environment.
"""
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from latex2mtef import latex_to_ast
from record import RecordType, SelectorType
from render import _normalize


def _walk(node):
    yield node
    for child in getattr(node, "children", []):
        yield from _walk(child)


def _char_codes(expr):
    return [
        n.value.mtcode
        for n in _walk(latex_to_ast(expr))
        if n.tag == RecordType.CHAR
    ]


def test_relation_aliases_preview_normalize():
    normalized = _normalize(r"x \ge 0,\ y \le 2,\ z \ne 1")
    assert r"\geq" in normalized
    assert r"\leq" in normalized
    assert r"\neq" in normalized
    assert r"\ge " not in normalized
    assert r"\le " not in normalized
    assert r"\ne " not in normalized


def test_perp_is_kept_in_editable_mtef_ast():
    assert 0x22A5 in _char_codes(r"OD \perp BC")


def test_common_geometry_relations_are_kept():
    assert 0x2225 in _char_codes(r"a \parallel b")
    assert 0x2223 in _char_codes(r"A \mid BC")


def test_bare_absolute_value_uses_bar_template():
    nodes = list(_walk(latex_to_ast(r"|x-1|")))
    bars = [
        n for n in nodes
        if n.tag == RecordType.TMPL and n.value.selector == SelectorType.tmBAR
    ]
    assert len(bars) == 1


def test_lvert_rvert_uses_bar_template():
    nodes = list(_walk(latex_to_ast(r"\lvert x-1 \rvert")))
    bars = [
        n for n in nodes
        if n.tag == RecordType.TMPL and n.value.selector == SelectorType.tmBAR
    ]
    assert len(bars) == 1
