# Radical / nested-root fix (2026-08-14)

This revision keeps the existing MathType-like font and layout, and changes only
LaTeX/MTEF handling for radicals.

- Canonicalises OCR-style `\sqrt3`, `\sqrt 5`, `\sqrt[3]5`, `\sqrt\alpha` and
  `\sqrt\frac{a}{b}` into explicit braced radicands.
- Applies the same radical normalisation to preview (MathText/MathJax) and to the
  editable MTEF parser so preview and double-click MathType content agree.
- Keeps the MTEF `FULL` size reset after each radical when another sibling atom
  follows. This prevents the next root/number/factor from inheriting a smaller
  root/script style.
- Adds regression tests for adjacent roots, roots in numerator/denominator,
  `\sqrt{\frac{...}{...}}`, nested roots, and the real Câu 12 expression.
- No font-family, font-size theme, UI, or document styling changes.
