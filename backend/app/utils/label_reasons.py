"""Where a reason for a Bad verdict ROUTES (UX-P117, #2060 item 1).

── THE RAIL EXISTED AND HAD NEVER HAD AN INPUT ──────────────────────────────────

``/api/admin/ranking-judgments/fixable-interest/clusters`` and ``/repair-clusters``
group judgments into defect clusters, rank them, and carry a triage state machine
(``open`` → ``linked`` / ``experiment`` / ``dismissed``). It is a finished
pipeline. Measured on production 2026-08-21:

    ranking_judgments                                        88 rows
      carrying `label_metadata.fixable_interest`              0
      label IN (bad, kill) WITH >=1 reason_tag               71
      ...of those, routed to a cluster                        0

Both cluster endpoints have therefore returned an empty list for the entire life
of the store. ``_build_fixable_clusters`` skips any row without a
``fixable_interest`` key, and nothing has ever written one: the web ReviewTab can
(it has a ``FIX_TYPES`` select) but the two FAST surfaces — native and
``/admin/labeling`` — never do, and those are the surfaces Alex actually grinds.

The consequence is the specific one #2060 is about. ``stale`` is the most-used tag
in the corpus — **35 of 88 rows, 40%** — which is Alex saying thirty-five separate
times that the queue serves dead markets (gotcha #33: a settled Kalshi market
keeps ``status='open'`` forever because polling stops seeing it). Not one became a
defect. The label was recorded and the COMPLAINT was dropped.

** So the chips are the mechanism and this table is the goal. ** A sixth reason
chip on a screen that routes nowhere is a sixth way to be ignored.

── THIS FILE DOES NOT CANONICALISE, AND THAT IS DELIBERATE ──────────────────────

``app/utils/discover_reason_tags.py`` already owns the spelling problem, and
``_normalize_reason_tags`` already runs on every write. The first draft of this
module shipped a second fold table — and it disagreed with the existing one in
three places within twenty lines of a comment condemning exactly that (it mapped
``unclear`` → ``confusing`` where the store maps ``confusing`` → ``unclear``, so
the route table would have been keyed on spellings the store never contains).

So: canonicalisation is imported, never re-expressed. Two spellings this queue
found genuinely unregistered (``boring``, and the ReviewTab's
``too_high``/``too_low``) were added THERE, as aliases, not worked around here.
The keys below are the store's canonical vocabulary and nothing else.

── A COMPLAINT THAT IS NOT A DATA DEFECT STILL ROUTES ───────────────────────────

"Boring" is not a bug in the card; it is a bug in the RANKING that put the card in
front of a human. Routing it to ``ranking_rule`` is the honest reading and keeps
the promise that a reasoned Bad is always evidence of something.

What is NOT routed is the positive vocabulary (``fun_or_weird``, ``movement``,
``high_stakes``…): those are not complaints, and manufacturing a defect from a
compliment would poison the cluster list this exists to fill. ``None`` therefore
means "this reason names no defect" and is returned for a known-positive tag and
for an unrecognised one alike — the caller needs no third case, but the two are
kept separable via ``NON_DEFECT_REASONS`` so a future audit can tell "we decided"
from "we have never seen this" (gotcha #53).
"""

from __future__ import annotations

from typing import Any

from app.utils.discover_reason_tags import canonical_reason_tag

#: The six chips one tap after Bad, in tap order (#2060 item 1, Alex's list).
#:
#: ``(stored_tag, display)``. The stored tag is the STORE's canonical spelling,
#: not the chip's English — "Confusing" stores ``unclear`` and "Boring" stores
#: ``low_stakes``, because those are the spellings the corpus already holds 16 and
#: 6 rows of. A chip that introduced a new spelling for an existing complaint
#: would split the very tally it exists to grow.
#:
#: Ordered by measured frequency of the complaint each names, so the most common
#: answer is the shortest reach on a phone. ``stale`` leads because it is 40% of
#: the corpus.
BAD_REASON_CHIPS: tuple[tuple[str, str], ...] = (
    ("stale", "Stale"),
    ("wrong_probability", "Wrong probability"),
    ("unclear", "Confusing"),
    ("duplicate", "Duplicate"),
    ("bad_image", "Bad image"),
    ("low_stakes", "Boring"),
)

#: Just the stored tags, for validation and for the native chip row.
BAD_REASON_TAGS: tuple[str, ...] = tuple(tag for tag, _ in BAD_REASON_CHIPS)

#: Canonical reason → ``fixable_interest.fix_type``.
#:
#: The right-hand values are NOT invented here — they are the existing
#: ``FIX_TYPES`` vocabulary the web ReviewTab already offers and the cluster
#: endpoints already group by (``frontend/components/admin/discover/ReviewTab.tsx``).
#: Reusing them is what makes a native chip tap land in the same cluster as a web
#: triage on the same underlying problem, rather than beside it.
REASON_FIX_TYPE: dict[str, str] = {
    "stale": "staleness",
    "duplicate": "duplicate_variant",
    "repetitive": "duplicate_variant",
    "bad_image": "bad_image",
    "wrong_probability": "data_bug",
    "misleading": "data_bug",
    "unclear": "missing_context",
    "generic_hook": "missing_context",
    "wrong_category": "category_mismatch",
    # Not defects in the card — defects in the ranking that served it.
    "low_stakes": "ranking_rule",
    "too_niche": "ranking_rule",
    "not_a_real_prediction": "ranking_rule",
    "finance_ladder": "ranking_rule",
    "commodity_ladder": "ranking_rule",
}

#: Canonical reasons that are known and deliberately route nowhere: the positive
#: vocabulary. Listed rather than left to fall through, so an audit can tell a
#: decided non-route from a spelling nobody has classified yet.
NON_DEFECT_REASONS: frozenset[str] = frozenset(
    {
        "movement",
        "public_story",
        "high_stakes",
        "close_probability",
        "source_disagreement",
        "celebrity_or_person",
        "sports_relevance",
        "fun_or_weird",
        "timely",
        "surprising_probability",
        "major_event",
    }
)

#: Labels whose reason tags are complaints.
#:
#: ``fine`` and ``love`` carry tags too — the native surface offers the same
#: 24-tag row on every verdict — but a tag on a ``love`` describes why the card is
#: GOOD. Routing it would file a defect against a card Alex just praised, and the
#: corpus has exactly one such row (``love`` + ``public_story``) waiting to prove
#: it.
NEGATIVE_LABELS: frozenset[str] = frozenset({"bad", "kill"})


def reason_fix_type(tag: str | None) -> str | None:
    """The ``fix_type`` a single reason routes to, or ``None`` for no defect.

    Canonicalises first, so a historical row holding an unregistered spelling
    (the 2 production ``boring`` rows) routes identically to a row written after
    the alias landed. Folding on read as well as on write is what makes the fix
    retroactive without rewriting a single stored tag.
    """
    canonical = canonical_reason_tag(tag)
    if not canonical or canonical in NON_DEFECT_REASONS:
        return None
    return REASON_FIX_TYPE.get(canonical)


def defect_route(
    *,
    label: str | None,
    reason_tags: Any,
) -> dict[str, Any] | None:
    """The ``fixable_interest`` payload a reasoned negative verdict implies.

    Returns ``None`` when nothing should be routed — a positive label, no tags, or
    only non-defect tags. ``None`` is the common case and stays cheap and silent:
    this runs inside every label write.

    ** ONE fix_type, because a cluster has one. ** ``_cluster_identity`` keys on a
    single ``fix_type``, so a Bad tagged both ``stale`` and ``bad_image`` cannot be
    two clusters from one row. The FIRST routable tag in the caller's order wins
    and every routable tag is recorded under ``reason_tags_routed``. The native
    chip row is single-select, so in the surface this is built for the tie cannot
    arise; it can only arise from the 24-tag multi-select, where the order Alex
    tapped them in is the best available statement of which he meant most.

    ** ``create_issue_candidate`` is deliberately NOT set. ** That flag means a
    human decided this deserves a GitHub issue. Inferring it from a tap would put
    71 auto-candidates into the triage list on the first backfill — the
    cried-wolf failure the Grid Sentinel's REAL/EXPLAINED/WATCH split exists to
    prevent, reproduced in a different queue.
    """
    if (label or "").strip().lower() not in NEGATIVE_LABELS:
        return None

    if isinstance(reason_tags, str):
        tags: list[Any] = [part for part in reason_tags.split(",") if part.strip()]
    elif isinstance(reason_tags, (list, tuple)):
        tags = list(reason_tags)
    else:
        return None

    routed: list[str] = []
    fix_type: str | None = None
    for tag in tags:
        mapped = reason_fix_type(tag)
        if mapped is None:
            continue
        if fix_type is None:
            fix_type = mapped
        routed.append(canonical_reason_tag(tag))

    if fix_type is None:
        return None

    return {
        "fix_type": fix_type,
        # Where this came from. A cluster reader must be able to tell a route
        # inferred from a chip tap from a `fix_type` a human chose in the
        # ReviewTab select — they carry different confidence, and only one of
        # them was a considered answer to "what kind of fix is this".
        "derived_from": "reason_tags",
        "reason_tags_routed": routed,
    }
