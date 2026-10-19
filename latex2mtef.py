import re
from latex_normalize import normalize_sqrt_groups
r"""
latex2mtef.py -- Parser LaTeX (math) -> cay MtAST, dung lai builder cua mtef_encode.

Pham vi v1 (du cho phan lon $...$ inline):
  - chu/so/toan tu, nhom { }, ^ _ (sub/sup/subsup)
  - \frac{}{}, \sqrt{}, \sqrt[n]{}
  - \left( .. \right) va ngoac thuong ( ) [ ] | (fence)
  - bang ky hieu: Hy Lap, toan tu, quan he, mui ten, \sum \int \prod (dang char + script)
Bo sung: cases/aligned/array/matrix co ban bang MTEF pile, van giu nguyen
dinh dang cua parser ban TNR13 cho moi cong thuc thong thuong.
Tat ca deu round-trip kiem chung duoc bang decoder cua ban.
"""
from record import (CharTypeface, SelectorType, RecordType, OptionType,
                    MtPile, MtAST)
from mtef_encode import (Char, text_char, function_text, Tmpl, frac, sup, sub, subsup,
                         sqrt, nth_root, fenced, hat, Line, equation)

LC = CharTypeface.fnLCGREEK
UC = CharTypeface.fnUCGREEK
SY = CharTypeface.fnSYMBOL
TX = CharTypeface.fnTEXT
VAR = CharTypeface.fnVARIABLE
FN = CharTypeface.fnFUNCTION
VEC = CharTypeface.fnVECTOR
NUM = CharTypeface.fnNUMBER

FUNCTION_COMMANDS = {
    "sin", "cos", "tan", "cot", "sec", "csc",
    "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh",
    "log", "ln", "exp", "lim", "max", "min",
    "det", "gcd", "ker", "arg", "deg", "mod",
}
STYLE_COMMANDS = {
    "mathrm": TX, "textrm": TX, "text": TX, "mbox": TX,
    "mathit": VAR, "mathbf": VEC, "boldsymbol": VEC,
}
SPACING_COMMANDS = {",", ";", ":", "!", "quad", "qquad", "enspace", "thinspace",
                    "limits", "nolimits"}
ESCAPED_CHARS = {"{": "{", "}": "}", "%": "%", "#": "#", "_": "_",
                 "&": "&", "$": "$", "\\": "\\"}

# command -> (mtcode unicode, typeface)
SYMBOLS = {
    # Hy Lap thuong
    "alpha":0x03B1,"beta":0x03B2,"gamma":0x03B3,"delta":0x03B4,"epsilon":0x03B5,
    "zeta":0x03B6,"eta":0x03B7,"theta":0x03B8,"iota":0x03B9,"kappa":0x03BA,
    "lambda":0x03BB,"mu":0x03BC,"nu":0x03BD,"xi":0x03BE,"pi":0x03C0,"rho":0x03C1,
    "sigma":0x03C3,"tau":0x03C4,"phi":0x03C6,"chi":0x03C7,"psi":0x03C8,"omega":0x03C9,
}
SYMBOLS_UC = {
    "Gamma":0x0393,"Delta":0x0394,"Theta":0x0398,"Lambda":0x039B,"Xi":0x039E,
    "Pi":0x03A0,"Sigma":0x03A3,"Phi":0x03A6,"Psi":0x03A8,"Omega":0x03A9,
}
SYMBOLS_OP = {
    "times":0x00D7,"div":0x00F7,"pm":0x00B1,"mp":0x2213,"cdot":0x22C5,
    "leq":0x2264,"le":0x2264,"leqslant":0x2264,
    "geq":0x2265,"ge":0x2265,"geqslant":0x2265,
    "neq":0x2260,"ne":0x2260,"lt":0x003c,"gt":0x003e,
    # Quan he hinh hoc/thuong gap. Preview da hieu \perp, nhung neu parser
    # MTEF khong co mapping thi ky hieu se bien mat khi double-click MathType.
    "perp":0x22A5,"bot":0x22A5,"parallel":0x2225,"mid":0x2223,
    "approx":0x2248,"equiv":0x2261,"infty":0x221E,"partial":0x2202,
    "rightarrow":0x2192,"to":0x2192,"leftarrow":0x2190,"Rightarrow":0x21D2,
    "in":0x2208,"notin":0x2209,"subset":0x2282,"cup":0x222A,"cap":0x2229,
    "forall":0x2200,"exists":0x2203,"nabla":0x2207,"angle":0x2220,
    "circ":0x2218,
    "sum":0x2211,"prod":0x220F,"int":0x222B,            # v1: dang char + script
}

# ky tu don trong math -> ky hieu SYMBOL voi char8 (giong MathType): (mtcode, typeface, bits8)
_MATH_CHAR = {
    "-": (0x2212, SY, 0x2d),     # MINUS SIGN
    "+": (0x002b, SY, 0x2b),
    "=": (0x003d, SY, 0x3d),
    "<": (0x003c, SY, 0x3c),
    ">": (0x003e, SY, 0x3e),
    "\u00b0": (0x00b0, SY, 0xb0),  # do (degree)
    "≤": (0x2264, SY, None),
    "≥": (0x2265, SY, None),
    "≠": (0x2260, SY, None),
}

class _Tok:
    def __init__(self, s):
        self.s = s; self.i = 0
    def eof(self):  return self.i >= len(self.s)
    def peek(self): return None if self.eof() else self.s[self.i]
    def next(self):
        c = self.s[self.i]; self.i += 1; return c
    def command(self):
        # da an dau '\' ; doc ten lenh (chu cai) hoac 1 ky tu dac biet
        if self.eof(): return ""
        if not self.s[self.i].isalpha():
            return self.next()                      # vd \, \{ \%
        j = self.i
        while not self.eof() and self.s[self.i].isalpha():
            self.i += 1
        return self.s[j:self.i]


def _skip_ws(t):
    while not t.eof() and t.peek() == " ":
        t.next()


def _cmd_nodes(name):
    if name in FUNCTION_COMMANDS:
        return function_text(name)
    if name in SYMBOLS:
        return [Char(SYMBOLS[name], LC)]
    if name in SYMBOLS_UC:
        return [Char(SYMBOLS_UC[name], UC)]
    if name in SYMBOLS_OP:
        return [Char(SYMBOLS_OP[name], SY)]
    if name in SPACING_COMMANDS:
        return []
    if name in ESCAPED_CHARS:
        return [text_char(ESCAPED_CHARS[name])]
    return None


def _retag(nodes, typeface, function=False):
    """Doi style cac ky tu Latin trong mot group; giu nguyen symbol/Greek."""
    first = True

    def visit(node):
        nonlocal first
        if node.tag == RecordType.CHAR:
            c = node.value
            if c.typeface not in (SY, LC, UC):
                c.typeface = NUM if chr(c.mtcode).isdigit() and typeface == TX else typeface
                if function and first:
                    c.options |= OptionType.MtefOptCharFuncStart
                    first = False
        for child in getattr(node, "children", []):
            visit(child)

    for node in nodes:
        visit(node)
    return nodes


def _read_delimiter(t, default="("):
    _skip_ws(t)
    if t.eof():
        return default
    if t.peek() != "\\":
        return t.next()
    t.next()
    name = t.command()
    return {
        "lbrace": "{", "rbrace": "}", "{": "{", "}": "}",
        "lvert": "|", "rvert": "|", "vert": "|", "Vert": "|",
        "langle": "<", "rangle": ">", ".": ".",
    }.get(name, default)




def _read_braced_text(t):
    """Doc noi dung trong mot cap { } va ho tro ngoac long nhau."""
    _skip_ws(t)
    if t.peek() != "{":
        return ""
    t.next()
    depth = 1
    out = []
    while not t.eof() and depth:
        c = t.next()
        if c == "{":
            depth += 1
            if depth > 1:
                out.append(c)
        elif c == "}":
            depth -= 1
            if depth:
                out.append(c)
        else:
            out.append(c)
    return "".join(out)


def _extract_environment(t, env):
    """Lay noi dung den \\end{env}; chi dung sau khi da doc \\begin{env}."""
    marker = r"\end{" + env + "}"
    end = t.s.find(marker, t.i)
    if end < 0:
        body = t.s[t.i:]
        t.i = len(t.s)
        return body
    body = t.s[t.i:end]
    t.i = end + len(marker)
    return body


def _split_top_level(text, separator="\\\\"):
    """Tach theo separator chi khi dang o ngoai nhom { }."""
    parts, current = [], []
    depth = 0
    i = 0
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}" and depth:
            depth -= 1
        if depth == 0 and text.startswith(separator, i):
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            i += len(separator)
            # Bo tuy chon khoang cach sau \\, vi du \\[2pt].
            if i < len(text) and text[i] == "[":
                close = text.find("]", i + 1)
                if close >= 0:
                    i = close + 1
            continue
        current.append(c)
        i += 1
    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def _remove_alignment_marks(row):
    """Bo dau & can cot o muc ngoai cung, khong dong vao & trong nhom."""
    out = []
    depth = 0
    for c in row:
        if c == "{":
            depth += 1
        elif c == "}" and depth:
            depth -= 1
        if c == "&" and depth == 0:
            continue
        out.append(c)
    return "".join(out)


def _pile(rows, halign=0, valign=1):
    pile = MtPile()
    pile.halign = halign
    pile.valign = valign
    return MtAST(RecordType.PILE, pile, [Line(row) for row in rows])


def _parse_environment(env, body):
    """Tao MTEF pile/fence cho cases va cac moi truong nhieu dong co ban."""
    env = env.lower()
    if env == "array":
        # Bo khai bao cot dau tien, vi du {rl}.
        body = re.sub(r"^\s*\{[^{}]*\}\s*", "", body, count=1)

    raw_rows = _split_top_level(body)
    parsed_rows = [
        _parse_seq(_Tok(_remove_alignment_marks(row)))
        for row in raw_rows
    ]
    if not parsed_rows:
        parsed_rows = [[]]

    # 0 = left alignment; 1 = vertical center trong pile.
    pile_node = _pile(parsed_rows, halign=0, valign=1)
    if env == "cases":
        return fenced([pile_node], left=True, right=False,
                      kind=SelectorType.tmBRACE)
    if env == "pmatrix":
        return fenced([pile_node], left=True, right=True,
                      kind=SelectorType.tmPAREN)
    if env == "bmatrix":
        return fenced([pile_node], left=True, right=True,
                      kind=SelectorType.tmBRACK)
    if env == "vmatrix":
        return fenced([pile_node], left=True, right=True,
                      kind=SelectorType.tmBAR)
    return pile_node

def _parse_group(t):
    """Doc mot 'atom-group': { ... } -> list node, hoac mot atom don."""
    _skip_ws(t)
    if t.peek() == "{":
        t.next()
        nodes = _parse_seq(t, stop="}")
        if t.peek() == "}": t.next()
        return nodes
    a = _parse_atom(t)
    return a if a is not None else []


def _parse_atom(t):
    """Mot atom: tra ve list node (thuong 1)."""
    _skip_ws(t)
    c = t.peek()
    if c is None: return []
    if c == "\\":
        t.next(); name = t.command()
        if name == "begin":
            env = _read_braced_text(t).strip().lower()
            supported = {
                "cases", "aligned", "alignedat", "array", "matrix",
                "pmatrix", "bmatrix", "vmatrix",
            }
            if env in supported:
                return [_parse_environment(env, _extract_environment(t, env))]
            return []
        if name in ("frac", "dfrac", "tfrac", "cfrac"):
            num = _parse_group(t); den = _parse_group(t)
            return [frac(num, den)]
        if name in STYLE_COMMANDS:
            return _retag(_parse_group(t), STYLE_COMMANDS[name])
        if name == "operatorname":
            if t.peek() == "*":
                t.next()
            return _retag(_parse_group(t), FN, function=True)
        if name == "sqrt":
            _skip_ws(t)
            if t.peek() == "[":
                t.next(); idx = _parse_seq(t, stop="]")
                if t.peek() == "]": t.next()
                rad = _parse_group(t)
                return [nth_root(rad, idx)]
            rad = _parse_group(t)
            return [sqrt(rad)]
        if name in ("widehat", "hat"):
            content = _parse_group(t)
            return [hat(content)]
        if name in ("left", "right"):
            # \left( .. \right)  -> doc dau fence roi noi dung toi \right
            fence = _read_delimiter(t, "(")
            if name == "right":
                return []                            # da xu ly o \left
            inner = _parse_seq(t, stop_cmd="right")
            # an \right va dau fence cua no
            if t.peek() == "\\":
                t.next(); t.command()
                _read_delimiter(t, ")")          # an dau fence phai
            kind = {"(":SelectorType.tmPAREN, "[":SelectorType.tmBRACK,
                    "{":SelectorType.tmBRACE, "|":SelectorType.tmBAR}.get(fence, SelectorType.tmPAREN)
            return [fenced(inner, kind=kind)]
        if name in ("lvert", "vert"):
            # Ho tro \lvert x \rvert va \vert x \vert nhu MathType fence.
            # Neu khong tim thay vach dong, tra ve mot vach SYMBOL thay vi bo lenh.
            start = t.i
            patterns = (r"\rvert", r"\vert")
            hits = [(t.s.find(mark, start), mark) for mark in patterns]
            hits = [(pos, mark) for pos, mark in hits if pos >= 0]
            if hits:
                pos, mark = min(hits, key=lambda item: item[0])
                body = t.s[start:pos]
                t.i = pos + len(mark)
                inner = _parse_seq(_Tok(body))
                return [fenced(inner, kind=SelectorType.tmBAR)]
            return [Char(ord("|"), SY, bits8=0x7c)]
        if name == "rvert":
            return [Char(ord("|"), SY, bits8=0x7c)]
        nodes = _cmd_nodes(name)
        return nodes if nodes is not None else []
    if c == "{":
        # nhom { } trong suot (khong phai dau ngoac nhin thay)
        t.next()
        inner = _parse_seq(t, stop="}")
        if t.peek() == "}": t.next()
        return inner
    if c == "|":
        # Gia tri tuyet doi / dinh thuc viet bang |...|. Truoc day moi dau |
        # bi ma hoa nhu ky tu TEXT rieng nen trong MathType co the trong day/dam.
        # Dung template tmBAR de MathType quan ly hai vach nhu fence chuan.
        t.next()
        inner = _parse_seq(t, stop="|")
        if t.peek() == "|":
            t.next()
            return [fenced(inner, kind=SelectorType.tmBAR)]
        # Khong co vach dong: giu nhu ky tu don de tranh lam mat du lieu.
        return [Char(ord("|"), SY, bits8=0x7c)] + inner
    if c in "([":
        # ngoac thuong -> fence
        t.next()
        close = {"(": ")", "[": "]"}[c]
        inner = _parse_seq(t, stop=close)
        if t.peek() == close: t.next()
        kind = {"(": SelectorType.tmPAREN, "[": SelectorType.tmBRACK}[c]
        return [fenced(inner, kind=kind)]
    # ky tu don
    t.next()
    if c in _MATH_CHAR:
        code, tf, bits8 = _MATH_CHAR[c]
        return [Char(code, tf, bits8=bits8)]
    return [text_char(c)]


def _parse_seq(t, stop=None, stop_cmd=None):
    nodes = []
    while True:
        _skip_ws(t)
        c = t.peek()
        if c is None: break
        if stop and c == stop: break
        if stop_cmd and c == "\\":
            # nhin truoc xem co phai \stop_cmd khong
            save = t.i; t.next(); nm = t.command()
            if nm == stop_cmd:
                t.i = save; break
            t.i = save
        atom = _parse_atom(t)
        # scripts ^ _
        sub_n = sup_n = None
        while True:
            _skip_ws(t)
            ch = t.peek()
            if ch == "^":
                t.next(); sup_n = _parse_group(t)
            elif ch == "_":
                t.next(); sub_n = _parse_group(t)
            else:
                break
        nodes.extend(atom)
        if sub_n is not None and sup_n is not None:
            nodes.append(subsup(sub_n, sup_n))
        elif sup_n is not None:
            nodes.append(sup(sup_n))
        elif sub_n is not None:
            nodes.append(sub(sub_n))
    return nodes


_DEG_RE = re.compile(r"\^\s*\{?\s*\\circ\s*\}?")


def latex_to_ast(latex):
    """Chuoi LaTeX (khong gom dau $) -> cay MtAST hoan chinh."""
    latex = normalize_sqrt_groups(latex or "")
    # Chuan hoa cac bien the quan he do OCR/Gemini thuong tra ve.
    latex = latex.replace("≤", r"\le ").replace("≥", r"\ge ").replace("≠", r"\ne ")
    latex = re.sub(r"(?<![<\\])<\s*=", r"\\le ", latex)
    latex = re.sub(r"(?<![>\\])>\s*=", r"\\ge ", latex)
    latex = latex.replace(r"\leqslant", r"\leq").replace(r"\geqslant", r"\geq")
    # OCR co the tra \int\limits {a}^{b}; khoi phuc dau _ bi mat.
    latex = re.sub(
        r"(\\(?:int|sum|prod)\s*\\limits)\s*\{([^{}]+)\}\s*\^\s*\{",
        r"\1_{\2}^{",
        latex,
    )
    # chuan hoa cac cach viet "do": ^\circ, ^{\circ}, \degree, \textdegree -> °
    latex = _DEG_RE.sub("\u00b0", latex)
    latex = latex.replace(r"\degree", "\u00b0").replace(r"\textdegree", "\u00b0")
    t = _Tok(latex)
    nodes = _parse_seq(t)
    return equation(nodes)


if __name__ == "__main__":
    from mtef_encode import encode_body, _trace
    for expr in [r"a^2 + b^2 = c^2",
                 r"\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}",
                 r"\sum_{i=1}^{n} i^2",
                 r"\left( \frac{x}{y} \right)^2"]:
        ast = latex_to_ast(expr)
        body = encode_body(ast)
        print("=" * 60)
        print("LaTeX:", expr, "->", len(body), "bytes")
        print(_trace(body))
