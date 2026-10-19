# Degree symbol rendering fix

Requested behavior: render degree notation using a full-size inline `\circ` instead of a superscript degree glyph.

Normalization examples:

- `60^\circ` -> `60\circ`
- `30^{\circ}` -> `30\circ`
- `45°` -> `45\circ`
- `90\degree` -> `90\circ`
- `90\textdegree` -> `90\circ`

The same normalization is shared by MathText preview, MathJax preview and editable MathType MTEF output, so preview and OLE stay consistent.
