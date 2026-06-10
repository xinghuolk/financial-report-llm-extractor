"""Normalization matcher for PDF alias auditing (spec PR-1, component 1).

Pure functions, no project imports. Diagnostic-only in PR-1: NOT wired
into live retrieval (that is PR-3, gated).

Fold pipeline (applied symmetrically to alias and text):
  1. lowercase            2. whitespace fold
  3. apostrophe removal   4. hyphen -> space
  5. edge-punctuation strip (PDF tokens carry ",.;:()“”" — must strip
     BEFORE plural fold or "receivables," never folds)
  6. plural fold (token: ies->y; strip trailing s when len > 3)
  7. stop-token drop (the/a/an)

The len>3 guard on s-stripping keeps short tokens (as/is) stable, which
resolves the rule-ordering asymmetry flagged in spec review.

Limitations:
  CJK line-wrap is out of scope: 应收\\n账款 cannot match alias 应收账款 in either tier (token model).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

_STOP_TOKENS = frozenset({"the", "a", "an"})
_APOSTROPHES = ("'", "’")
_EDGE_PUNCT = ",.;:()\"“”"
_HYPHENS = ("-", "‐", "‑", "–")


def _fold_token(token: str) -> list[str]:
    """Fold one whitespace token; may split (hyphen) or drop (stop word)."""
    t = token.lower()
    for ch in _APOSTROPHES:
        t = t.replace(ch, "")
    for ch in _HYPHENS[1:]:
        t = t.replace(ch, "-")
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
    """Full fold of a phrase: tokens joined by single spaces ("" if empty).

    Symmetric-contract: matching only holds when BOTH alias and text go
    through this same fold. Naive suffix-strip means es-plurals do NOT
    reach the base form (taxes->taxe != tax; loss->los) — symmetric, so
    it causes missed matches, never wrong matches.
    """
    return " ".join(t for tok in s.split() for t in _fold_token(tok))


@dataclass(frozen=True)
class AliasMatch:
    alias: str
    kind: Literal["exact", "normalized"]
    matched_text: str
    count: int


def _ws_fold(s: str) -> str:
    return " ".join(s.lower().split())


def _norm_tokens_with_origin(text: str) -> tuple[list[str], list[int]]:
    """Normalized tokens + parallel index of the ORIGINAL whitespace token
    each came from (hyphen splits map several norm tokens to one origin)."""
    norm: list[str] = []
    origin: list[int] = []
    for i, tok in enumerate(text.split()):
        for folded in _fold_token(tok):
            norm.append(folded)
            origin.append(i)
    return norm, origin


@dataclass(frozen=True)
class PreparedText:
    """Pre-folded text for repeated match_alias calls against many aliases."""
    text_ws: str
    norm_tokens: tuple[str, ...]
    origin: tuple[int, ...]
    orig_tokens: tuple[str, ...]


def prepare_text(text: str) -> PreparedText:
    norm, origin = _norm_tokens_with_origin(text)
    return PreparedText(
        text_ws=_ws_fold(text),
        norm_tokens=tuple(norm),
        origin=tuple(origin),
        orig_tokens=tuple(text.split()),
    )


def match_alias(
    alias: str,
    text: str,
    *,
    prepared: PreparedText | None = None,
) -> AliasMatch | None:
    """Exact (current select_chunks semantics) else normalized (fold
    pipeline, token-window match with original-text recovery).

    Pass ``prepared`` (built via :func:`prepare_text`) to avoid
    re-tokenizing the same block text on every alias in a loop.
    """
    if prepared is None:
        prepared = prepare_text(text)

    alias_ws = _ws_fold(alias)
    if alias_ws and alias_ws in prepared.text_ws:
        return AliasMatch(
            alias=alias, kind="exact",
            matched_text=alias_ws, count=prepared.text_ws.count(alias_ws),
        )

    alias_norm = [t for tok in alias.split() for t in _fold_token(tok)]
    if not alias_norm:
        return None
    n, count, first_span = len(alias_norm), 0, None
    for i in range(len(prepared.norm_tokens) - n + 1):
        if list(prepared.norm_tokens[i:i + n]) == alias_norm:
            count += 1
            if first_span is None:
                first_span = (prepared.origin[i], prepared.origin[i + n - 1])
    if count == 0:
        return None
    assert first_span is not None
    matched = " ".join(prepared.orig_tokens[first_span[0]:first_span[1] + 1])
    return AliasMatch(
        alias=alias, kind="normalized", matched_text=matched, count=count,
    )
