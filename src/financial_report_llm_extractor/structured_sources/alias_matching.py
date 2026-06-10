"""Normalization matcher for PDF alias auditing (spec PR-1, component 1).

Pure functions, no project imports. Diagnostic-only in PR-1: NOT wired
into live retrieval (that is PR-3, gated).

Fold pipeline (applied symmetrically to alias and text):
  1. lowercase            2. whitespace fold
  3. apostrophe removal   4. hyphen -> space
  5. edge-punctuation strip (PDF tokens carry ",.;:()" — must strip
     BEFORE plural fold or "receivables," never folds)
  6. plural fold (token: ies->y; strip trailing s when len > 3)
  7. stop-token drop (the/a/an)

The len>3 guard on s-stripping keeps short tokens (as/is) stable, which
resolves the rule-ordering asymmetry flagged in spec review.
"""
from __future__ import annotations

_STOP_TOKENS = frozenset({"the", "a", "an"})
_APOSTROPHES = ("'", "'")
_EDGE_PUNCT = ",.;:()\""


def _fold_token(token: str) -> list[str]:
    """Fold one whitespace token; may split (hyphen) or drop (stop word)."""
    t = token.lower()
    for ch in _APOSTROPHES:
        t = t.replace(ch, "")
    out: list[str] = []
    for part in t.split("-"):
        part = part.strip(_EDGE_PUNCT)
        if not part:
            continue
        if part.endswith("ies") and len(part) > 3:
            part = part[:-3] + "y"
        elif part.endswith("s") and len(part) > 3:
            part = part[:-1]
        if part in _STOP_TOKENS:
            continue
        out.append(part)
    return out


def normalize_phrase(s: str) -> str:
    return " ".join(t for tok in s.split() for t in _fold_token(tok))
