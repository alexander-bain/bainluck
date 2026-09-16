"""Shared cross-source matching utilities for category page routes.

Extracts the common pattern of finding markets that exist on both Kalshi and
Polymarket, then ranking by probability disagreement.  Used by politics.py,
entertainment.py, and economics.py.

Also provides ``group_markets_by_group_id`` for collapsing Polymarket
sub-markets that share a ``group_id`` into a single representative market
with merged outcomes — used by all four category pages.
"""

import re
from collections import defaultdict
from typing import Callable, Sequence

from app.models import FuturesMarket

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

GARBAGE_OUTCOME_RE = re.compile(
    r"^(?:player|person|candidate|option|party|song|movie|show|app|team|ticker|choice)\s+[A-Z0-9]{1,3}$", re.I
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "be",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "shall",
    "that",
    "the",
    "this",
    "to",
    "will",
    "would",
}
_TOKEN_ALIASES = {
    "above": "over",
    "below": "under",
    "exceed": "over",
    "exceeds": "over",
    "exceeding": "over",
    "greater": "over",
    "less": "under",
    "presidency": "president",
    "presidential": "president",
    "wins": "win",
    "winner": "win",
    "winning": "win",
}
_DIRECTION_TOKENS = {"over", "under"}

#: A dotted acronym — ``u.s.``, ``u.k.``, ``a.m.`` — matched on the lowercased
#: title so :func:`_near_match_tokens` can rejoin it into one token instead of
#: letting ``_TOKEN_RE`` shatter it into single characters. Requires at least two
#: dotted letters, so an ordinary sentence cannot match it.
_DOTTED_ACRONYM_RE = re.compile(r"\b[a-z](?:\.[a-z])+\.?")


def _join_acronym(match: re.Match) -> str:
    return match.group(0).replace(".", "")


def source(market: FuturesMarket) -> str:
    """Return the lowercased source name for a market."""
    return (market.source or "").lower()


def is_resolved(market: FuturesMarket) -> bool:
    """A market is effectively resolved if any outcome is >= 99% or all near-zero."""
    probs = [float(o.current_probability or 0) for o in market.outcomes
             if o.current_probability is not None]
    if not probs:
        return False
    if any(p >= 0.99 for p in probs):
        return True
    if len(probs) >= 2 and all(p <= 0.01 for p in probs):
        return True
    return False


def clean_outcomes(outcomes: list) -> list:
    """Filter garbage placeholder outcomes."""
    return [o for o in outcomes if not GARBAGE_OUTCOME_RE.match(o.name or "")]


def normalize_question(q: str) -> str:
    """Normalize a question string for cross-source matching.

    Strips punctuation, lowercases, and trims whitespace.
    """
    return re.sub(r"[^a-z0-9 ]+", "", q.lower()).strip()


def _near_match_tokens(q: str) -> set[str]:
    """Tokenize a question, rejoining dotted acronyms first (#6537).

    ``U.S.`` split into the two single-character tokens ``u`` and ``s``, which
    are in neither side's meaning and cost a pair two union slots — the artefact
    that refused Kalshi's "Which party will win the U.S. House?" beside
    Polymarket's "Which party will win the House in 2026?" on the thresholds even
    after the year qualifier was set aside. The EXACT arm never had this problem:
    :func:`normalize_question` deletes the dots and inserts nothing, so it has
    always read "U.S. House" and "US House" as one string. This is the near arm
    agreeing with it about what a word is.

    REJOINED, never dropped, and this is the whole safety of it: ``U.S.`` -> ``us``
    and ``U.K.`` -> ``uk`` stay distinct, where deleting single-character tokens
    would have collapsed two countries into the same question. It is also NOT
    "tokenize the normalized string" — that would fuse ``men's`` into ``mens``,
    and the measured 2027 Women's World Cup duplicate (Jaccard 0.75, one token of
    room) falls under the bound when it loses its ``s``.

    Effect on the controls this predicate is bound by is to move them AWAY from
    the bound: the U.S. House beside the U.S. Senate reads 0.667 / 0.800 here
    where it read 0.714 / 0.833.
    """
    tokens = []
    for token in _TOKEN_RE.findall(_DOTTED_ACRONYM_RE.sub(_join_acronym, q.lower())):
        canonical = _TOKEN_ALIASES.get(token, token)
        if canonical not in _STOPWORDS:
            tokens.append(canonical)
    return set(tokens)


def _numeric_tokens(tokens: set[str]) -> set[str]:
    return {token for token in tokens if token.isdigit()}


def _direction_tokens(tokens: set[str]) -> set[str]:
    return tokens & _DIRECTION_TOKENS


def _near_match_signature(q: str) -> tuple[set[str], frozenset[str], frozenset[str]]:
    """Precompute the token sets used for conservative near-matching.

    Returns ``(tokens, numeric_tokens, direction_tokens)`` so the O(n^2)
    pairing loop in :func:`find_cross_source_markets` can tokenize each row
    once instead of re-tokenizing both sides on every candidate pair.
    """
    tokens = _near_match_tokens(q)
    return tokens, frozenset(_numeric_tokens(tokens)), frozenset(_direction_tokens(tokens))


def _conservative_near_match_score(
    left_sig: tuple[set[str], frozenset[str], frozenset[str]],
    right_sig: tuple[set[str], frozenset[str], frozenset[str]],
) -> float | None:
    """Jaccard score for obvious paraphrases, or None if not a conservative match.

    Same guards as the public :func:`_is_conservative_near_match`, but operates
    on precomputed signatures and returns the Jaccard similarity so callers can
    reuse it for ranking instead of recomputing the token sets.
    """
    left_tokens, left_num, left_dir = left_sig
    right_tokens, right_num, right_dir = right_sig
    if len(left_tokens) < 3 or len(right_tokens) < 3:
        return None
    if left_num != right_num:
        return None
    if (left_dir or right_dir) and left_dir != right_dir:
        return None

    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    if union == 0:
        return None
    jaccard = overlap / union
    containment = overlap / min(len(left_tokens), len(right_tokens))
    if jaccard >= 0.72 and containment >= 0.85:
        return jaccard
    return None


def _is_conservative_near_match(left: str, right: str) -> bool:
    """Return True for obvious paraphrases, with guards against false matches."""
    return (
        _conservative_near_match_score(
            _near_match_signature(left), _near_match_signature(right)
        )
        is not None
    )


def is_same_question(left: str | None, right: str | None) -> bool:
    """Are these two market titles the SAME question asked by two venues?

    The two passes :func:`find_cross_source_markets` already runs, in the same
    order and for the same reasons, exposed for callers that hold serialized
    market dicts rather than ``FuturesMarket`` rows: an exact normalized-question
    match first (the strongest evidence), then the conservative near-match, whose
    guards — three tokens minimum, identical numeric tokens, identical direction
    tokens, Jaccard >= 0.72 AND containment >= 0.85 — are what make it usable
    outside a spotlight that a reader can eyeball.

    The exact arm is not redundant with the near-match arm: a two-token title
    ("Oscar Winner") is refused by the near-match token-count guard, and two
    venues asking a short question identically are the easiest case of all.

    A DISPLAY caller must be stricter than a matcher (a matcher that over-pairs
    shows a spurious spread; a deduper that over-pairs DELETES a card the reader
    wanted), so the discrimination is measured, not assumed. Every pair of titles
    served together on Discover page one on 2026-09-09 was run through this:
    the one real duplicate — Kalshi "2027 FIFA Women's World Cup Champion" and
    Polymarket "FIFA Women's World Cup 2027 Winner", both in the World Cup
    bundle — matches at Jaccard 0.75, and all ten same-bundle non-duplicates are
    refused, including the three that share a canonical_market_key with their
    neighbour: the men's and women's US Open, the 2030 men's World Cup beside the
    2027 women's, and the Oscar beside the Grammy. Those controls live in
    `test_cross_source_matching.py`; a change that pairs any of them is a bug in
    this function whatever it does for the duplicate.
    """
    if not left or not right:
        return False
    if normalize_question(left) == normalize_question(right):
        return True
    return _is_conservative_near_match(left, right)


# Minimum shared tokens a pair must have before :func:`is_same_question` can
# possibly pair it. DERIVED FROM THE THRESHOLDS ABOVE, not tuned:
#
#   near arm — needs ``min(len) >= 3`` and ``containment >= 0.85``, so the
#     overlap is at least ``ceil(0.85 * 3) = 3``;
#   exact arm — equal normalized questions have equal token sets, so the
#     overlap is the whole set.
#
# 2 rather than 3 buys the one case the near arm's floor excludes: an exact
# match that two or three tokens long ("Oscar Winner"). It is one below the
# tightest reachable bound, deliberately, because this filter's only job is to
# say NO cheaply and a filter that says no too often is a silent bug.
#
# 🔴 THIS CONSTANT IS A CONSEQUENCE OF 0.72 / 0.85 / 3. Anyone who loosens
# those must re-derive it — a lower containment bound admits pairs with fewer
# shared tokens, and this filter would start hiding them from the matcher.
_SAME_QUESTION_MIN_SHARED_TOKENS = 2


def same_question_tokens(question: str | None) -> frozenset[str]:
    """The token set :func:`could_be_same_question` compares, computed once.

    Exposed so a caller holding N titles can tokenize N times instead of the
    2 * N * (N - 1) / 2 times a naive pairwise loop over
    :func:`is_same_question` costs — that loop re-tokenizes BOTH sides on every
    pair, and it is the whole cost. Measured on the 137 futures titles Discover
    served on 2026-09-15: 9,316 pairs at 3.95 us each (37 ms) unfiltered,
    versus 62 surviving pairs and 2.3 ms with this.
    """
    return frozenset(_near_match_tokens(question or ""))


def could_be_same_question(
    left_tokens: frozenset[str], right_tokens: frozenset[str]
) -> bool:
    """Cheap NECESSARY condition for :func:`is_same_question` — never sufficient.

    A ``False`` here is a promise that ``is_same_question`` would also have said
    no; a ``True`` means "ask it". Callers MUST still call the real predicate —
    this sees no numeric tokens, no direction tokens and no thresholds.

    The promise holds under title rewriting that only REMOVES tokens (the
    leading-year strip in ``discover_bundles._comparison_title`` is the live
    case): a smaller token set can only shrink the overlap the real predicate
    sees, so a pair that clears the real bound after stripping also clears this
    one before it. It would NOT hold for a rewrite that ADDS or SUBSTITUTES
    tokens; nothing does that today, and this is the sentence that would have
    to change first.
    """
    if (
        len(left_tokens) < _SAME_QUESTION_MIN_SHARED_TOKENS
        or len(right_tokens) < _SAME_QUESTION_MIN_SHARED_TOKENS
    ):
        # Too short for the shared-token floor to mean anything: the exact arm
        # can still pair these ("Oscar Winner"), so refuse to exclude them.
        return True
    return len(left_tokens & right_tokens) >= _SAME_QUESTION_MIN_SHARED_TOKENS


# ---------------------------------------------------------------------------
# Outcome alignment — comparing like with like
# ---------------------------------------------------------------------------


def _outcome_key(name: str | None) -> str:
    """Normalize an outcome name so the same outcome matches across sources.

    Deliberately conservative: case-fold and collapse whitespace, nothing else.
    A looser key (stripping punctuation, decomposing accents) would fold
    "Ülle Madise" and "Ulle Madise" together, which is desirable, but it also
    folds bracket labels that are NOT the same outcome — "2.4%" and "2-4%",
    "$800-900B" and "800-900B". Measured over the 122 production pairs on
    /politics (2026-08-30) the looser key bought exactly one extra pair and
    risked the whole threshold-ladder population, so it is not worth it.
    """
    return re.sub(r"\s+", " ", (name or "").strip()).casefold()


def align_on_shared_outcome(
    kalshi_row: dict, poly_row: dict
) -> tuple[str, float, float] | None:
    """Pick the one outcome both sources price, or None if there isn't one.

    A cross-source spread is only a spread when the two numbers are the price
    of the SAME thing. Both row builders rank a market's outcomes and report
    the leader's probability as ``prob``, and until this function existed the
    spotlight subtracted one market's leader from the other's — which is a
    disagreement only when the two leaders happen to be the same outcome.

    Measured on production, 2026-08-30, over every cross-source pair
    /politics finds (122 of them):

      * 98 of 122 pairs have DIFFERENT leading outcomes, so their "spread" was
        an artifact of which outcome happened to lead on each side. The served
        top four included "How many House seats will Democrats win in
        Louisiana?" as Kalshi 92.5% (exactly 1 seat) vs Polymarket 36.0%
        (9 seats) — a 56.5pt spread between two numbers that were never in
        conflict, plus a "Merged: 64.3%" that is the average of two different
        futures.
      * 95 of 122 share no outcome name at all — a cumulative Kalshi ladder
        ("Above 2.2%") against Polymarket discrete brackets ("2.4%") cannot be
        reduced to one comparable number in either direction (gotcha #17).
        Those pairs are dropped rather than shown with a number nobody can act
        on.
      * The artifact was also HIDING real disagreement, not only inventing it:
        "Rio de Janeiro Governor winner?" served a 0.7pt spread that looked
        like near-perfect agreement, while the two sources priced Eduardo Paes
        at 94.0% and 63.8% — a genuine 30.2pt gap.

    Alignment reads ``top_outcomes``, the list the row builder has already
    built and already normalized, so the number on a spotlight card is the
    same number, on the same basis, as the one the market's own section
    prints. Reading ``FuturesMarket.outcomes`` directly here would be a second
    basis: ``_normalize_outcome_probs`` fires on 102 of the 244 markets in
    those pairs, so the two would visibly disagree. Top-3 costs nothing —
    all 27 comparable pairs align inside it, because a pair whose leaders
    agree aligns on rank 1 by construction.

    When the leaders differ but some lower-ranked outcome is shared, that
    outcome is still a legitimate comparison and often the most interesting
    one on the page ("both sources price Goldman Sachs, and they are 53 points
    apart about it"), so the shared outcome with the highest price on either
    side wins. For a leader-agreeing pair that rule selects the shared leader,
    so there is one rule, not two.

    Returns ``(outcome_name, kalshi_prob, poly_prob)``.
    """
    kalshi_by_key = {
        _outcome_key(o.get("name")): o
        for o in (kalshi_row.get("top_outcomes") or [])
        if _outcome_key(o.get("name"))
    }
    poly_by_key = {
        _outcome_key(o.get("name")): o
        for o in (poly_row.get("top_outcomes") or [])
        if _outcome_key(o.get("name"))
    }
    shared = set(kalshi_by_key) & set(poly_by_key)
    if not shared:
        return None

    best_key = max(
        shared,
        key=lambda k: (
            max(
                float(kalshi_by_key[k].get("prob") or 0),
                float(poly_by_key[k].get("prob") or 0),
            ),
            k,
        ),
    )
    # Kalshi's spelling is the one shown. The two agree after normalization by
    # construction; they can still differ in case or spacing, and picking one
    # side deterministically keeps the label stable as prices move.
    name = (kalshi_by_key[best_key].get("name") or "").strip()
    return (
        name,
        float(kalshi_by_key[best_key].get("prob") or 0),
        float(poly_by_key[best_key].get("prob") or 0),
    )


def _spotlight_match(kalshi_row: dict, poly_row: dict) -> dict | None:
    """Build one spotlight row, or None when the pair is not comparable."""
    aligned = align_on_shared_outcome(kalshi_row, poly_row)
    if aligned is None:
        return None
    outcome, kalshi_prob, poly_prob = aligned
    return {
        "q": kalshi_row["q"],
        "outcome": outcome,
        "kalshi": kalshi_prob,
        "poly": poly_prob,
        "delta": round(abs(kalshi_prob - poly_prob), 1),
        "category": kalshi_row.get("theme", ""),
        "kalshi_market_id": kalshi_row["market_id"],
        "poly_market_id": poly_row["market_id"],
    }


# ---------------------------------------------------------------------------
# Core cross-source matching algorithm
# ---------------------------------------------------------------------------


def find_cross_source_markets(
    markets: Sequence[FuturesMarket],
    *,
    market_row_fn: Callable[[FuturesMarket], dict | None],
    max_results: int = 8,
) -> list[dict]:
    """Find markets that exist on both Kalshi & Polymarket, ranked by disagreement.

    A pair is only reported when both sources price the SAME outcome, and the
    reported spread is that outcome's — see :func:`align_on_shared_outcome`
    for why, and for what the numbers looked like before. Pairs with no shared
    outcome are matched and then dropped, so the section shows fewer, truer
    rows rather than more, louder ones.

    Ranking happens AFTER the drop, which matters: mis-aligned leaders produce
    the largest fake spreads, so sorting first systematically promoted exactly
    the rows that were wrong and buried the real ones below the cut.

    Parameters
    ----------
    markets:
        Sequence of FuturesMarket objects to scan.
    market_row_fn:
        Callable that receives a single FuturesMarket and returns either None
        (skip this market) or a dict containing at minimum ``q``, ``prob``,
        ``src``, ``market_id`` and ``top_outcomes`` (a ranked list of
        ``{"name", "prob"}``, which all three category routes already build).
        A row without ``top_outcomes`` can never be aligned and so is never
        reported.  May include extra keys (e.g. ``theme``) that will be
        preserved in the output.
    max_results:
        Maximum number of cross-source pairs to return (default 8).

    Returns
    -------
    list[dict]
        Each entry has: ``q``, ``outcome``, ``kalshi``, ``poly``, ``delta``,
        ``category``, ``kalshi_market_id``, ``poly_market_id``.  ``outcome``
        names the single outcome ``kalshi`` and ``poly`` both price.
    """
    by_norm: dict[str, dict[str, dict]] = defaultdict(dict)
    rows_by_source: dict[str, list[tuple[str, dict]]] = {
        "kalshi": [],
        "polymarket": [],
    }

    for m in markets:
        if is_resolved(m):
            continue
        row = market_row_fn(m)
        if not row:
            continue
        src = row.get("src", "")
        if src not in ("kalshi", "polymarket"):
            continue
        norm = normalize_question(row["q"])
        if norm and src not in by_norm[norm]:
            by_norm[norm][src] = row
            rows_by_source[src].append((norm, row))

    matches = []
    matched_market_ids = set()
    for _norm, sources in by_norm.items():
        if "kalshi" not in sources or "polymarket" not in sources:
            continue
        k = sources["kalshi"]
        p = sources["polymarket"]
        # Both ids are consumed even when the pair yields no row. An exact
        # normalized-question match is the strongest evidence two markets are
        # the same question; that it cannot be reduced to one comparable
        # number is a reason to show nothing, never a reason to release the
        # markets into the near-match pass to find a WEAKER partner.
        matched_market_ids.add(k["market_id"])
        matched_market_ids.add(p["market_id"])
        match = _spotlight_match(k, p)
        if match is not None:
            matches.append(match)

    # Precompute token signatures once per row so the conservative near-match
    # pass below is O(n) tokenization instead of re-tokenizing both sides on
    # every (kalshi, polymarket) pair. With ~900 markets the naive version did
    # millions of redundant regex tokenizations and dominated endpoint latency.
    poly_sigs = [
        (p_norm, p, _near_match_signature(p["q"]))
        for p_norm, p in rows_by_source["polymarket"]
    ]

    for k_norm, k in rows_by_source["kalshi"]:
        if k["market_id"] in matched_market_ids:
            continue
        k_sig = _near_match_signature(k["q"])
        best_poly = None
        best_score = 0.0
        for p_norm, p, p_sig in poly_sigs:
            if p["market_id"] in matched_market_ids or k_norm == p_norm:
                continue
            score = _conservative_near_match_score(k_sig, p_sig)
            if score is not None and score > best_score:
                best_poly = p
                best_score = score
        if not best_poly:
            continue
        matched_market_ids.add(k["market_id"])
        matched_market_ids.add(best_poly["market_id"])
        match = _spotlight_match(k, best_poly)
        if match is not None:
            matches.append(match)

    matches.sort(key=lambda x: -x["delta"])
    return matches[:max_results]


# ---------------------------------------------------------------------------
# Group-ID market collapsing for category pages
# ---------------------------------------------------------------------------


def group_markets_by_group_id(
    markets: Sequence[FuturesMarket],
) -> list[FuturesMarket]:
    """Collapse markets sharing a ``group_id`` into a single representative.

    Polymarket decomposes multi-outcome questions (e.g. "Who wins Best
    Picture?") into N independent binary sub-markets, each with its own
    ``FuturesMarket`` row but the same ``group_id``.  On category pages this
    causes N duplicate rows for what the user perceives as one question.

    This helper groups by ``group_id``, picks the representative market
    (most outcomes, then highest volume), and **merges** the unique outcomes
    from all sibling markets onto the representative so it carries the full
    outcome set.

    Markets with ``group_id IS NULL`` pass through unchanged.

    Returns a new list — the input is not mutated.
    """
    ungrouped: list[FuturesMarket] = []
    by_group: dict[str, list[FuturesMarket]] = defaultdict(list)

    for m in markets:
        gid = getattr(m, "group_id", None)
        if gid is None:
            ungrouped.append(m)
        else:
            by_group[gid].append(m)

    result: list[FuturesMarket] = list(ungrouped)

    for _gid, members in by_group.items():
        if len(members) == 1:
            result.append(members[0])
            continue

        # Pick representative: most outcomes first, then highest volume_24h
        members.sort(
            key=lambda m: (
                len(getattr(m, "outcomes", None) or []),
                getattr(m, "volume_24h", 0) or 0,
            ),
            reverse=True,
        )
        representative = members[0]

        rep_outcomes = getattr(representative, "outcomes", None) or []
        # Collect outcome names already on the representative
        existing_names: set[str] = {
            (o.name or "").lower().strip() for o in rep_outcomes
        }

        # Merge unique outcomes from sibling markets
        merged_outcomes = list(rep_outcomes)
        for sibling in members[1:]:
            for o in getattr(sibling, "outcomes", None) or []:
                name_key = (o.name or "").lower().strip()
                if name_key and name_key not in existing_names:
                    merged_outcomes.append(o)
                    existing_names.add(name_key)

        # Attach merged outcomes.  We mutate the relationship list in-place
        # because SQLAlchemy lazy-loaded lists support item assignment.
        # This is safe because we are in a read-only request context and the
        # session will not be flushed/committed.
        representative.outcomes = merged_outcomes  # type: ignore[assignment]

        result.append(representative)

    return result
