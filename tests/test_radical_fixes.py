"""Regression tests for nested/sequential radicals and OCR-style sqrt input."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from latex_normalize import normalize_sqrt_groups
from latex2mtef import latex_to_ast
from mtef_encode import emit_seq, sqrt, text_char
from record import RecordType, SelectorType


def _walk(node):
    yield node
    for child in getattr(node, "children", []):
        yield from _walk(child)


def _roots(expr):
    return [
        n for n in _walk(latex_to_ast(expr))
        if n.tag == RecordType.TMPL and n.value.selector == SelectorType.tmROOT
    ]


def _fractions(expr):
    return [
        n for n in _walk(latex_to_ast(expr))
        if n.tag == RecordType.TMPL and n.value.selector == SelectorType.tmFRACT
    ]


def test_normalize_bare_sqrt_number():
    assert normalize_sqrt_groups(r"\sqrt3 + \sqrt 12 + \sqrt[3]5") == (
        r"\sqrt{3} + \sqrt{12} + \sqrt[3]{5}"
    )


def test_normalize_bare_sqrt_command_and_fraction():
    assert normalize_sqrt_groups(r"\sqrt\alpha + \sqrt\frac{a}{b}") == (
        r"\sqrt{\alpha} + \sqrt{\frac{a}{b}}"
    )


def test_normalize_nested_unbraced_roots_inside_braces():
    assert normalize_sqrt_groups(r"\sqrt{6+2\sqrt5-\sqrt5}") == (
        r"\sqrt{6+2\sqrt{5}-\sqrt{5}}"
    )


def test_two_adjacent_roots_stay_two_full_root_templates():
    roots = _roots(r"\sqrt{a}\sqrt{b}")
    assert len(roots) == 2
    assert all(r.value.variation == 0 for r in roots)


def test_fraction_with_root_in_both_slots():
    expr = r"\frac{\sqrt{a}}{\sqrt{b}}"
    assert len(_fractions(expr)) == 1
    assert len(_roots(expr)) == 2


def test_root_containing_fraction_structure():
    expr = r"\sqrt{\frac{a}{b}}"
    roots = _roots(expr)
    fracs = _fractions(expr)
    assert len(roots) == 1
    assert len(fracs) == 1
    # fraction must be under the radical, not a sibling after it
    assert any(
        n.tag == RecordType.TMPL and n.value.selector == SelectorType.tmFRACT
        for n in _walk(roots[0])
    )


def test_root_emitter_resets_full_size_before_following_sibling():
    out = emit_seq([sqrt([text_char("3")]), text_char("x")], bytearray())
    # ROOT followed by another sibling must include MTEF FULL reset so MathType
    # does not keep the radical/script-sized context for the next atom.
    assert bytes([RecordType.FULL]) in bytes(out)


def test_real_exam_nested_radical_formula_structure():
    expr = (
        r"x=\frac{\sqrt[3]{10+6\sqrt3}(\sqrt3-1)}"
        r"{\sqrt{6+2\sqrt5-\sqrt5}}"
    )
    normalized = normalize_sqrt_groups(expr)
    assert r"\sqrt{3}" in normalized
    assert normalized.count(r"\sqrt{5}") == 2
    roots = _roots(normalized)
    # cube root + inner sqrt3 + factor sqrt3 + denominator root + 2 inner sqrt5
    assert len(roots) == 6
    assert any(r.value.variation == 1 for r in roots)


def test_preview_and_mathjax_use_same_sqrt_canonicalization():
    from render import _normalize as mathtext_normalize
    from mathjax_renderer import _normalize as mathjax_normalize

    expr = r"\frac{\sqrt3\sqrt5}{\sqrt{1+\sqrt2}}"
    expected_bits = (r"\sqrt{3}", r"\sqrt{5}", r"\sqrt{2}")
    mt = mathtext_normalize(expr)
    mj = mathjax_normalize(expr)
    for bit in expected_bits:
        assert bit in mt
        assert bit in mj
