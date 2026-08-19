"""#1986 — two source rows relabelled to one name must MERGE, not both render.

THE DEFECT, on screen. Event 15194464 (Orioles at Rays) rendered:

    CHAMPIONSHIP PATH
    World Series Champion  ▓▓▓░░░  8%
    World Series Champion  ▓▓░░░░  4%

Two rows, identical label, different numbers. Behind them: Kalshi's "Pro
Baseball Champion" (0.077) and Polymarket's "MLB World Series Champion 2026"
(0.0405), both normalized to one display label — so the single field that would
make the pair legible (WHICH SOURCE) is exactly the field the relabel removes.

Ruling: *the blend is the product* — one number per question. Source divergence
is a data bug to fix, not a feature to show, and the three deliberate comparison
surfaces (category-page spotlights, playoffs source lines, My Stuff dots) do not
include the event page. So the pair MERGES through the standing blend.

WHY THIS IS NOT A ONE-LINE DEDUPE. A census of the real payload found TWO
collision classes wearing the same `merge_group`:

  class                 rows  sources  market_ids  meaning
  world_series_champion    2  kalshi+  275 + 114584  ONE question, two sources
                              polymarket
  world_series_matchup    30  kalshi   2417016       THIRTY questions, one each
                                                     per possible opponent

Collapsing on `merge_group` alone would fuse thirty distinct opponent matchups
("Tampa Bay vs Milwaukee", "Tampa Bay vs Atlanta", ...) into a single row. The
predicate below therefore requires a genuine cross-source disagreement about
ONE question: distinct sources, distinct markets, and compatible entity names.
When any of those fails it REFUSES to merge — a refusal renders today's
(imperfect) two rows, while a wrong merge silently invents a number.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.utils.aggregation import SOURCE_WEIGHTS, _weighted_median
from app.utils.source_divergence import SourceDivergence, assess_divergence

__all__ = [
    "merge_relabel_collisions",
    "blend_probabilities",
    "blend_with_verdict",
    "entities_compatible",
]


def _norm_entity(name: Optional[str]) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (name or "").lower())).strip()


def entities_compatible(a: Optional[str], b: Optional[str]) -> bool:
    """True when two outcome names plausibly name the SAME entity.

    Sources disagree on team naming ("Tampa Bay" vs "Tampa Bay Rays"), so exact
    equality is too strict. Token-subset containment covers the alias case while
    still refusing two different people ("Mason Miller" vs "Emmanuel Clase"),
    which is what keeps award markets from merging across candidates.
    """
    na, nb = _norm_entity(a), _norm_entity(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = set(na.split()), set(nb.split())
    return ta <= tb or tb <= ta


def blend_with_verdict(
    rows: list[dict],
) -> tuple[Optional[float], Optional[SourceDivergence], str]:
    """One number for one question — and WHICH RULE produced it.

    Ruling (b), cycle 99, replaced this function's original behaviour on the
    only shape it actually meets in production. Both halves, in the order the
    ruling set them:

    **1. The divergence gate runs first.** A pair 40+ points apart is not two
    opinions; one of the two rows is about a different question. `AL West
    Winner — Houston` arrives as Kalshi 0.575 and Polymarket 0.060, and no
    statistic rescues that: the median prints 6%, a mean prints 31.75%, and the
    mean is not more correct, only differently wrong. Gated pairs render the
    primary row's own stated number and carry the flag out to matching.

    **2. Below the threshold, an equal-weight pair prints the MIDPOINT.** This
    function's docstring used to defend returning the lower value as "the
    standing algorithm's answer". It was the standing algorithm's answer, and
    the census showed what that answer costs on exactly this surface: with
    kalshi and polymarket both at 0.8 the cumulative weight crosses the midpoint
    inside the FIRST sorted entry, so `median == min(values)` on 3 of 3 live
    merges and the bias is not approximately half the spread, it IS half the
    spread — `delta == -spread/2` exactly, always downward. A rule that always
    resolves a tie downward is not a tiebreak, it is a systematic discount, and
    the sort order it depends on carries no meaning.

    This does NOT fork a second aggregator, which was the original objection and
    a fair one. The scope is a genuine two-way TIE, where the weighted median is
    not expressing a judgement about authority — there is none to express — it
    is just reading whichever value sorted first. The events hero keeps the
    weighted median untouched, including its heavier-source tiebreak, which the
    ruling explicitly preserved as designed behaviour.

    Returns ``(value, divergence_or_None, rule_name)``.
    """
    vals: list[float] = []
    wts: list[float] = []
    srcs: list[str] = []
    for r in rows:
        p = r.get("probability")
        if p is None:
            continue
        vals.append(float(p))
        srcs.append((r.get("source") or "").lower())
        wts.append(SOURCE_WEIGHTS.get((r.get("source") or "").lower(), 0.8))
    if not vals:
        return None, None, "empty"

    # Two rows from DISTINCT sources is the shape both halves of the ruling
    # govern. Same-source rows are sibling outcomes, not a disagreement, and
    # `merge_relabel_collisions` already refuses to merge them — but this
    # function is public, so it re-checks rather than trusting its caller.
    if len(vals) == 2 and srcs[0] != srcs[1]:
        divergence = assess_divergence(
            dict(zip(srcs, vals)), dict(zip(srcs, wts)), order=srcs
        )
        if divergence is not None:
            return round(divergence.primary_value, 6), divergence, "divergence_gate"
        if wts[0] == wts[1]:
            return round((vals[0] + vals[1]) / 2.0, 6), None, "equal_weight_midpoint"

    return round(_weighted_median(vals, wts), 6), None, "weighted_median"


def blend_probabilities(rows: list[dict]) -> Optional[float]:
    """The value alone. See `blend_with_verdict` for which rule produced it."""
    return blend_with_verdict(rows)[0]


def merge_relabel_collisions(rows: list[dict]) -> list[dict]:
    """Collapse cross-source duplicates of ONE question into one blended row.

    Order-preserving: the merged row takes the position of the first
    contributor. Non-colliding rows pass through untouched and byte-identical.
    The merged row gains `all_sources` and `source_count` so the UI can say
    "2 sources" without printing two contradictory numbers.
    """
    groups: dict[Any, list[int]] = {}
    for i, r in enumerate(rows):
        key = r.get("merge_group")
        if not key:
            continue
        groups.setdefault(key, []).append(i)

    merged_into: dict[int, list[int]] = {}
    consumed: set[int] = set()

    for _key, idxs in groups.items():
        for pos, i in enumerate(idxs):
            if i in consumed:
                continue
            partners = []
            for j in idxs[pos + 1:]:
                if j in consumed:
                    continue
                a, b = rows[i], rows[j]
                # A genuine cross-source duplicate of one question requires ALL
                # THREE. Same source or same market means these are sibling
                # outcomes of one multi-outcome market (the 30-row matchup
                # class), never a source disagreement.
                if (a.get("source") or "") == (b.get("source") or ""):
                    continue
                if a.get("market_id") == b.get("market_id"):
                    continue
                if not entities_compatible(a.get("outcome_name"), b.get("outcome_name")):
                    continue
                partners.append(j)
            if partners:
                merged_into[i] = partners
                consumed.update(partners)
                consumed.add(i)

    if not merged_into:
        return rows

    out: list[dict] = []
    for i, r in enumerate(rows):
        if i in merged_into:
            contributors = [rows[i]] + [rows[j] for j in merged_into[i]]
            new = dict(r)
            blended, divergence, rule = blend_with_verdict(contributors)
            if blended is not None:
                new["probability"] = blended
            new["blend_rule"] = rule
            if divergence is not None:
                # The flag rides ON THE ROW rather than going only to a log,
                # because the row is what reaches every consumer — the read
                # path, an audit, and matching — and a pair this broken should
                # not be silently indistinguishable from a clean merge.
                new["divergence"] = divergence.as_evidence()
            srcs = sorted({(c.get("source") or "unknown") for c in contributors})
            new["all_sources"] = srcs
            new["source_count"] = len(srcs)
            new["merged_source_count"] = len(contributors)
            out.append(new)
        elif i in consumed:
            continue
        else:
            out.append(r)
    return out
