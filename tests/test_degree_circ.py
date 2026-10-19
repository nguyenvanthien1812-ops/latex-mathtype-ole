"""Regression tests for full-size inline degree/circle rendering."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from latex_normalize import normalize_degree_to_inline_circ
from latex2mtef import latex_to_ast
from record import RecordType, SelectorType


def _walk(node):
    yield node
    for child in getattr(node, "children", []):
        yield from _walk(child)


def test_degree_variants_become_inline_circ_without_caret():
    s = normalize_degree_to_inline_circ(r"60^\circ+30^{\circ}+45°+90\degree")
    assert "^" not in s
    assert "°" not in s
    assert s.count(r"\circ") == 4
    assert r"\\circ" not in s


def test_mtef_degree_has_no_superscript_template():
    ast = latex_to_ast(r"60^\circ")
    nodes = list(_walk(ast))
    assert not any(
        n.tag == RecordType.TMPL and n.value.selector == SelectorType.tmSUP
        for n in nodes
    )
    assert any(
        n.tag == RecordType.CHAR and getattr(n.value, "mtcode", None) == 0x2218
        for n in nodes
    )


def test_preview_normalizers_match_degree_policy():
    from render import _normalize as mathtext_normalize
    from mathjax_renderer import _normalize as mathjax_normalize
    for expr in (r"60^\circ", r"30^{\circ}", "45°"):
        mt = mathtext_normalize(expr)
        mj = mathjax_normalize(expr)
        assert "^" not in mt and "^" not in mj
        assert r"\circ" in mt and r"\circ" in mj
