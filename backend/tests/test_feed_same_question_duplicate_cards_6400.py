"""#6400 — Discover serves the Brazilian presidential election ONCE, not twice.

THE SPECIMEN, found mystery-shopping the Discover feed on production release
`355ca6dc`, 2026-09-15 ~17:2xZ. One page load at 390px; a DOM sweep of the whole
feed found TWO cards containing "Brazil Presidential", 1,156 px apart, with one
card between them:

    y=2284  Brazil Presidential Election        polymarket  resolves Oct 3, 2026
              Flávio Bolsonaro 52%  ·  Lula 47%  ·  Renan Santos 2%  ·  Romeu Zema <1%
    y=3440  Brazil Presidential election winner?  kalshi    resolves Oct 25, 2026
              Flávio Bolsonaro 54%  ·  Lula 46%  ·  Renan Santos 2%  ·  Augusto Cury 1%

Same on the wire: `GET /api/feed?limit=200` served them at ranks 6 and 7,
ADJACENT, ids 112996 and 109952, each advertising `sources: [kalshi, polymarket]`
— so each card already claims to be a blend, and the reader gets two of them two
points apart. That is the standing ruling read backwards ("the blend is the
product: one number per question") on top of `duplicate-family-rate@20=0`.

## They are one question, read from the VENUE rather than inferred

Polymarket's Gamma record for event 45915 (`slug: brazil-presidential-election`):

    "This market will resolve according to the listed candidate that wins this
     election. This market includes any potential second round."

which is exactly what Kalshi's `KXBRPRES-26` asks. The Oct 4 / Oct 25 split is
each venue's own end-date stamp, not two questions. Checked BEFORE building any
fold, because a deduper that over-pairs deletes a card the reader wanted.

## Why the existing caps cannot see it — both are working as designed

    classify_market_quality('Brazil Presidential Election',         'politics')
      family_key 'brazil presidential election'           story_key None
    classify_market_quality('Brazil Presidential election winner?', 'politics')
      family_key 'brazil presidential election winner'    story_key None

`diversify_quality_families(exact_family_cap=1)` keys on the normalized NAME, so
one trailing word is a second family; the story cap cannot fire because
`_subnational_election_story_key` returns None for anything presidential, on
purpose (a national race is not a local election). An exact-name cap is a
same-WORDING cap, and a cross-venue duplicate is differently worded by
definition. `test_the_name_keyed_caps_cannot_see_this_pair` pins that, so a later
reader can tell this fold is covering a real gap rather than duplicating a cap.

`is_same_question` — whose docstring says it exists for a DISPLAY caller — has
said True about this pair the whole time. Its ONLY caller was
`_dedupe_same_question_members`, which runs on bundle MEMBERS (#4446, #4479).
Two duplicates that are standalone cards never reached it.

Every control below is a title production actually served beside the specimen on
the same day, and the men's/women's US Open pair is #4479's own control: a
deduper is only as good as the cards it declines to delete.
"""

import ast
from pathlib import Path

import pytest

from app.utils.cross_source_matching import (
    could_be_same_question,
    is_same_question,
    same_question_tokens,
)
from app.utils.discover_bundles import fold_same_question_cards
from app.utils.feed_market_quality import (
    classify_market_quality,
    diversify_quality_families,
)

BRAZIL_POLY = "Brazil Presidential Election"
BRAZIL_KALSHI = "Brazil Presidential election winner?"


def _card(
    market_id: int,
    name: str,
    *,
    source: str,
    score: float,
    resolution_date: str | None = None,
    category: str = "politics",
) -> dict:
    """A scored futures card in the shape `_dedupe_and_cap` hands the fold."""
    quality = classify_market_quality(name, category)
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "reason": "reason",
        "headline": name,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": category,
            "source": source,
            "resolution_date": resolution_date,
        },
        "_quality_class": quality.quality_class,
        "_quality_family_key": quality.family_key,
        "_quality_story_key": quality.story_key,
        "_sort_time": 1000 + market_id,
    }


def _brazil_pair() -> list[dict]:
    """The two cards, in the rank order production served them (6 then 7)."""
    return [
        _card(112996, BRAZIL_POLY, source="polymarket", score=89,
              resolution_date="2026-10-04T00:00:00+00:00"),
        _card(109952, BRAZIL_KALSHI, source="kalshi", score=89,
              resolution_date="2026-10-25T14:00:00+00:00"),
    ]


def _names(items: list[dict]) -> list[str]:
    return [i["data"]["name"] if i.get("type") == "futures" else i["type"] for i in items]


# ---------------------------------------------------------------------------
# The gap this fold covers — pinned, so the fix is not mistaken for a duplicate
# of a cap that already exists
# ---------------------------------------------------------------------------


def test_the_name_keyed_caps_cannot_see_this_pair():
    kept = diversify_quality_families(
        _brazil_pair(), exact_family_cap=1, story_family_cap=5
    )

    assert _names(kept) == [BRAZIL_POLY, BRAZIL_KALSHI], (
        "the exact-family cap is expected to keep BOTH — if it starts folding "
        "them, this fold is redundant and should be reconsidered, not kept"
    )
    families = {c["_quality_family_key"] for c in _brazil_pair()}
    assert len(families) == 2, "one trailing word is what makes them two families"
    assert {c["_quality_story_key"] for c in _brazil_pair()} == {None}


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_discover_serves_the_brazil_election_once():
    kept = fold_same_question_cards(_brazil_pair())

    assert _names(kept) == [BRAZIL_POLY], (
        "the better-ranked card survives; the second phrasing of the same "
        "question is dropped"
    )


def test_the_survivor_is_the_better_ranked_card_whichever_venue_leads():
    """Rank order decides, not the venue — the contract the sibling states."""
    reversed_order = list(reversed(_brazil_pair()))

    assert _names(fold_same_question_cards(reversed_order)) == [BRAZIL_KALSHI]


def test_two_cards_from_ONE_venue_are_that_venue_s_own_listings():
    """Both gates are required. One venue asking twice is not ours to fold."""
    pair = _brazil_pair()
    pair[1]["data"]["source"] = "polymarket"

    assert _names(fold_same_question_cards(pair)) == [BRAZIL_POLY, BRAZIL_KALSHI]


# ---------------------------------------------------------------------------
# Controls — cards this must decline to delete
# ---------------------------------------------------------------------------

MENS_POLY = "2026 Men’s US Open Winner (Tennis)"
MENS_KALSHI = "US Open Men's Singles Winner"
WOMENS_KALSHI = "US Open Women's Singles Winner"


def test_the_mens_and_womens_us_open_are_two_questions():
    """#4479's own control: the pair that must NEVER fold scores HIGHER than the
    duplicate it sits beside, so no threshold separates them and only the
    matcher's guards do."""
    cards = [
        _card(114159, MENS_POLY, source="polymarket", score=80, category="tennis",
              resolution_date="2026-09-13T00:00:00+00:00"),
        _card(34277839, WOMENS_KALSHI, source="kalshi", score=79, category="tennis",
              resolution_date="2026-09-27T02:00:00+00:00"),
    ]

    assert _names(fold_same_question_cards(cards)) == [MENS_POLY, WOMENS_KALSHI]


def test_the_mens_us_open_still_folds_across_two_venues():
    """The control above must not have been bought by refusing everything."""
    cards = [
        _card(114159, MENS_POLY, source="polymarket", score=80, category="tennis",
              resolution_date="2026-09-13T00:00:00+00:00"),
        _card(34277822, MENS_KALSHI, source="kalshi", score=78, category="tennis",
              resolution_date="2026-09-28T02:00:00+00:00"),
    ]

    assert _names(fold_same_question_cards(cards)) == [MENS_POLY]


@pytest.mark.parametrize(
    "left,right",
    [
        # (The U.S. House pair that sat here as #6400's known residual — one
        # question in a reader's eyes, refused by the numeric-token guard — was
        # FIXED by #6537 and now folds. It moved to
        # `test_feed_house_duplicate_year_qualifier_6537.py`, which asserts the
        # fold rather than the refusal. It was never a real control here: this
        # helper builds cards with no resolution_date, and #6537's rule is gated
        # on the two rows resolving inside one cycle, so the row would have gone
        # on passing for a reason that has nothing to do with the titles.)
        # Two different chambers.
        ("Which party will win the U.S. Senate?", "Which party will win the U.S. House?"),
        # Two different ceremonies.
        ("Oscar Winner", "Grammy Winner"),
        # Two different championships, same sport, one word apart.
        ("NASCAR Cup Series Champion", "NASCAR Xfinity Series Champion"),
    ],
)
def test_neighbouring_questions_are_not_folded(left, right):
    cards = [
        _card(1, left, source="kalshi", score=80),
        _card(2, right, source="polymarket", score=79),
    ]

    assert _names(fold_same_question_cards(cards)) == [left, right]


def test_non_futures_cards_pass_through_untouched():
    """A mixed list is what the route actually holds."""
    event = {"type": "event", "score": 90, "data": {"id": 7, "home_team": "Rayo"}}
    bundle = {"type": "bundle", "score": 88, "data": {"kind": "theme"}}
    cards = [event, *_brazil_pair(), bundle]

    kept = fold_same_question_cards(cards)

    assert _names(kept) == ["event", BRAZIL_POLY, "bundle"]
    assert kept[0] is event and kept[2] is bundle


def test_a_card_with_no_name_is_kept_rather_than_dropped():
    cards = [
        _card(1, "", source="kalshi", score=80),
        _card(2, "", source="polymarket", score=79),
        *_brazil_pair(),
    ]

    kept = fold_same_question_cards(cards)

    assert len(kept) == 3, "two nameless cards are not evidence of one question"
    assert _names(kept)[-1] == BRAZIL_POLY


# ---------------------------------------------------------------------------
# The prefilter is an optimisation, and an optimisation that changes an answer
# is a bug. This is the only thing standing between the two.
# ---------------------------------------------------------------------------

# Every futures title Discover served on 2026-09-15 that shares a token with
# another one, plus the controls above — the corpus the prefilter was measured on.
_CORPUS = [
    BRAZIL_POLY,
    BRAZIL_KALSHI,
    MENS_POLY,
    MENS_KALSHI,
    WOMENS_KALSHI,
    "Which party will win the U.S. House?",
    "Which party will win the House in 2026?",
    "Which party will win the U.S. Senate?",
    "NASCAR Cup Series Champion",
    "NASCAR Xfinity Series Champion",
    "Next French Presidential Election",
    "Brazil Presidential Election First Round: 1st Place in Acre",
    "Premier Lacrosse League Championship Winner",
    "Canadian Team to Win the Stanley Cup® Before the 2030-31 Season",
    "Will Trump issue Obamacare rebates before Election Day?",
    "This Sep 2026 is the hottest September ever?",
    "Where will it rain this weekend (Sep 19 - Sep 20)?",
    "Recession in 2027?",
    "Will China invade Taiwan by end of 2026?",
    "Oscar Winner",
    "Grammy Winner",
    "2027 FIFA Women's World Cup Champion",
    "FIFA Women's World Cup 2027 Winner",
]


def test_the_prefilter_never_hides_a_pair_the_matcher_would_have_paired():
    """Naive versus prefiltered over every pair in the corpus, same verdicts.

    The prefilter's promise is one-directional — False means the real predicate
    would also have said no — so the failure mode is a SILENT lost fold, which
    no test of the fold's output would catch on a corpus that has no such pair.
    This compares the two directly.
    """
    tokens = {title: same_question_tokens(title) for title in _CORPUS}
    hidden = []
    paired = 0
    for i, left in enumerate(_CORPUS):
        for right in _CORPUS[i + 1:]:
            truth = is_same_question(left, right)
            paired += bool(truth)
            if truth and not could_be_same_question(tokens[left], tokens[right]):
                hidden.append((left, right))

    assert hidden == [], f"prefilter hid a real pair: {hidden}"
    assert paired >= 2, (
        "the corpus must contain pairs the matcher accepts, or this test passes "
        f"vacuously (accepted {paired})"
    )


def test_the_prefilter_actually_excludes_most_pairs():
    """Otherwise it is dead code carrying a proof obligation for nothing."""
    tokens = {title: same_question_tokens(title) for title in _CORPUS}
    total = admitted = 0
    for i, left in enumerate(_CORPUS):
        for right in _CORPUS[i + 1:]:
            total += 1
            admitted += bool(could_be_same_question(tokens[left], tokens[right]))

    assert admitted < total / 2, f"admitted {admitted} of {total}"


def test_a_short_title_is_never_excluded_by_the_shared_token_floor():
    """The exact arm has no token-count floor, so the prefilter must not add one."""
    assert could_be_same_question(same_question_tokens("Oscar"), same_question_tokens("Oscar"))
    assert is_same_question("Oscar Winner", "oscar winner!")
    assert could_be_same_question(
        same_question_tokens("Oscar Winner"), same_question_tokens("oscar winner!")
    )


# ---------------------------------------------------------------------------
# Wiring — a fold nothing calls is a fold that changes no page
# ---------------------------------------------------------------------------


def _feed_source() -> str:
    return (
        Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
    ).read_text()


#: #4170 — the broaden merge folds across the two pools it joins. It is a seam
#: BETWEEN the chains, not a chain, so the per-chain counts below exclude it and
#: `test_the_broaden_merge_folds_once` pins it on its own.
_MERGE_SEAM = "_merge_broadened_futures"


def _merge_seam_span(source: str) -> tuple[int, int]:
    """Character span of the merge-seam function in ``source``."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == _MERGE_SEAM:
            lines = source.splitlines(keepends=True)
            start = sum(len(line) for line in lines[: node.lineno - 1])
            end = sum(len(line) for line in lines[: node.end_lineno])
            return start, end
    raise AssertionError(f"{_MERGE_SEAM} is gone from feed.py — re-read #4170")


def test_the_broaden_merge_folds_once():
    source = _feed_source()
    start, end = _merge_seam_span(source)
    assert source[start:end].count("fold_same_question_cards(") == 1


def test_both_dedupe_chains_in_the_feed_route_call_the_fold():
    """Two chains exist — the fused/main `_dedupe_and_cap` and the fallback in
    `_score_futures_from_base`. #6400 was reachable through either, so a fold
    wired into one of them leaves the other serving the duplicate."""
    source = _feed_source()
    tree = ast.parse(source)

    seam = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == _MERGE_SEAM
    )
    seam_lines = range(seam.lineno, seam.end_lineno + 1)

    diversify_calls = 0
    fold_calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or node.lineno in seam_lines:
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name == "diversify_quality_families":
            diversify_calls += 1
        elif name == "fold_same_question_cards":
            fold_calls += 1

    assert diversify_calls == 2, (
        f"the route's dedupe chains moved ({diversify_calls} found) — re-read "
        "them and re-aim this assertion rather than relaxing it"
    )
    assert fold_calls == diversify_calls, (
        f"{fold_calls} fold call(s) for {diversify_calls} dedupe chain(s): a "
        "chain without the fold still serves the duplicate"
    )


def _call_offsets(source: str, needle: str) -> list[int]:
    offsets, at = [], source.find(needle)
    while at != -1:
        offsets.append(at)
        at = source.find(needle, at + 1)
    return offsets


def test_each_chain_runs_the_fold_after_its_name_keyed_caps():
    """Order is load-bearing in both directions: the fold's pairwise loop is
    bounded by running on the already-capped list, and a survivor can only be
    chosen once scoring has ordered the cards."""
    source = _feed_source()
    diversify = _call_offsets(source, "diversify_quality_families(\n")
    seam_start, seam_end = _merge_seam_span(source)
    folds = [
        at for at in _call_offsets(source, "fold_same_question_cards(")
        if not seam_start <= at < seam_end
    ]
    # The import line is a `fold_same_question_cards,` with no paren, so every
    # offset here is a call; the AST test above is what counts them.
    assert len(diversify) == len(folds) == 2, (diversify, folds)

    for chain, (cap_at, fold_at) in enumerate(zip(diversify, folds)):
        assert fold_at > cap_at, f"chain {chain} folds before it caps"
    assert folds[0] < diversify[1], (
        "the first chain's fold must belong to the first chain, not sit after "
        "the second chain's caps"
    )
