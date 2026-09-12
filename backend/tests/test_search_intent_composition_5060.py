"""T2-3 (#5060) — the COMPOSITION: subject-resolved identity, then the answer leads.

WHY THESE DRIVE THE REAL FUNCTIONS rather than hand-building a ranked page. The
defect T2-3 fixes is not in any one function — every one of them behaves as
written. It is in what the route hands them: the full query string
``patriots playoffs`` reached filters and scorer that can only read it as a
NAME, and no team owns a name containing "playoffs". A test that hand-orders a
list would assert its own fixture and stay green through that. So every test
here starts from `Evidence` and runs the route's own steps in the route's own
order — rank, reserve beneath the entity block, then promote the answer — using
the same imports the route uses.

This file is the sibling of `test_route_typeahead_entity_floor_4614.py` and
borrows its method deliberately; that file's lesson is quoted in the route.
"""

import pytest

from app.utils.search_headline_contender import reserve_headline_slot
from app.utils.search_intent import (
    INTENT_PLAYOFFS,
    INTENT_SEASON_YEAR,
    INTENT_TODAY,
    SearchIntent,
    answers_intent,
    parse_intent,
    promote_answering_rows,
    row_answers_intent,
)
from app.utils.search_match_class import (
    Evidence,
    entity_prefix_len,
    rank_with_keys,
)

# The real shapes, named once. `text` is what the route ranks and what
# `answers_intent` reads, so these carry the names production actually holds.
TEAM = {"type": "team", "text": "New England Patriots"}
PLAYOFF_MARKET = {"type": "market", "text": "Patriots to Make the Playoffs"}
DIVISION_MARKET = {"type": "market", "text": "Patriots to Win the AFC East Division"}
GAME = {"type": "event", "text": "New England Patriots at New York Jets"}
UNRELATED = {"type": "market", "text": "NFL MVP 2026"}

EV = {
    id(TEAM): Evidence(
        name="New England Patriots", aliases=("Patriots", "Pats"), kind="team",
        sport_key="americanfootball_nfl",
    ),
    id(PLAYOFF_MARKET): Evidence(
        name="Patriots to Make the Playoffs", kind="market",
        sport_key="americanfootball_nfl",
    ),
    id(DIVISION_MARKET): Evidence(
        name="Patriots to Win the AFC East Division", kind="market",
        sport_key="americanfootball_nfl",
    ),
    id(GAME): Evidence(
        name="New England Patriots at New York Jets", kind="event",
        sport_key="americanfootball_nfl",
    ),
    id(UNRELATED): Evidence(
        name="NFL MVP 2026", kind="market", sport_key="americanfootball_nfl",
    ),
}

PAGE = [TEAM, PLAYOFF_MARKET, DIVISION_MARKET, GAME, UNRELATED]


def compose(query: str) -> list[dict]:
    """The route's own three steps, in the route's own order.

    Mirrors `typeahead_search`: resolve the identity string from the intent,
    rank on THAT, reserve beneath the entity block, then promote the answer.
    """
    intent = parse_intent(query)
    q_identity = intent.subject if intent else query

    keyed = rank_with_keys(q_identity, [(EV[id(row)], row) for row in PAGE])
    page = reserve_headline_slot(
        [payload for _key, payload in keyed],
        set(),
        floor=entity_prefix_len(keyed),
    )
    return promote_answering_rows(page, intent)


# ── The defect T2-3 fixes ────────────────────────────────────────────────────

def test_a_question_no_longer_costs_the_reader_the_team():
    """RED before the fix: ranking `patriots playoffs` as one string.

    The team owns "Patriots" and "New England Patriots" and owns no name
    containing "playoffs", so on the full string it cannot reach the class it
    reaches on the subject. This asserts the CLASS moved, not merely that the
    page looks nice — a page can look right for the wrong reason.
    """
    team_ev = EV[id(TEAM)]
    from app.utils.search_match_class import match_class

    on_full_query = match_class("patriots playoffs", team_ev)
    on_subject = match_class("patriots", team_ev)
    assert on_subject < on_full_query, (
        "the subject must resolve the team to a BETTER class than the raw query; "
        f"got subject={on_subject} vs query={on_full_query}"
    )


def test_the_requested_answer_leads_and_the_team_is_still_on_the_page():
    """Design decision B: "`Patriots playoffs` opens playoff qualification; card
    identifies the team." Both halves are asserted — leading the answer is only
    correct if identity survives beside it."""
    page = compose("patriots playoffs")
    assert page[0] is PLAYOFF_MARKET, [r["text"] for r in page]
    assert TEAM in page, "the reader lost the team they named"


def test_the_division_question_leads_for_the_division_query():
    """Kills: promoting a fixed row regardless of which question was asked."""
    page = compose("patriots division")
    assert page[0] is DIVISION_MARKET, [r["text"] for r in page]


# ── The controls: a bare name is unchanged ───────────────────────────────────

def test_a_bare_team_name_still_leads_with_the_team():
    """Ruling 041 proper, untouched: a NAME is not a question.

    This is the guard that fails if the promotion ever runs on a generic query.
    """
    page = compose("patriots")
    assert page[0] is TEAM, [r["text"] for r in page]


@pytest.mark.parametrize("query", ["ai", "ipo", "weather", "emmys"])
def test_the_named_generic_controls_compose_without_an_intent(query):
    """T2-3's acceptance names these: "generic `ai`, `ipo`, weather and award
    controls unchanged". They match no scaffold, so the new path is not merely
    harmless for them — it is never entered."""
    assert parse_intent(query) is None


def test_promotion_is_a_no_op_without_an_intent():
    """Kills: running the partition unconditionally.

    Identity-compared, so this also catches a rebuild that returns equal-but-new
    dicts — the route hands these same objects onward to the evidence echo,
    which keys on `id()`.
    """
    page = list(PAGE)
    assert promote_answering_rows(page, None) is page


# ── Properties of the partition itself ───────────────────────────────────────

def test_the_partition_loses_no_row_and_invents_none():
    """Kills: a filter written where a partition was meant.

    The promotion orders a page; it must never change WHICH rows are on it. A
    reader who asked a question and lost four rows of context has been answered
    and robbed in one step.
    """
    page = compose("patriots playoffs")
    assert sorted(id(r) for r in page) == sorted(id(r) for r in PAGE)


def test_relative_order_survives_among_the_rows_that_did_not_answer():
    """Kills: replacing the stable partition with a re-sort.

    A comparison sort here would re-decide orderings the scorer already settled.
    The non-answering rows must come through in exactly the order they arrived.
    """
    intent = SearchIntent(kind=INTENT_PLAYOFFS, subject="patriots")
    before = [TEAM, PLAYOFF_MARKET, GAME, UNRELATED]
    after = promote_answering_rows(list(before), intent)
    assert after[0] is PLAYOFF_MARKET
    non_answering = [r for r in after if r is not PLAYOFF_MARKET]
    assert non_answering == [TEAM, GAME, UNRELATED]


def test_a_kind_that_answers_nothing_at_all_promotes_nothing():
    """`season_year` is in NEITHER answering map — a bare year is a qualifier on
    some other question, not a question, so the page comes back untouched rather
    than empty or reordered.

    Kills: mapping every kind to a pattern "for completeness", which would
    promote an arbitrary row to slot 0 on a query like "patriots 2025".
    """
    intent = SearchIntent(kind=INTENT_SEASON_YEAR, subject="patriots", season=2025)
    page = list(PAGE)
    assert promote_answering_rows(page, intent) is page
    assert all(not row_answers_intent(r, INTENT_SEASON_YEAR) for r in PAGE)


def test_today_is_answered_by_the_game_not_by_a_market_that_says_today():
    """The `today` arm, and the production defect that makes it necessary.

    MEASURED on production 2026-09-12, before this ship:

        q="red sox"         -> Boston Red Sox, THEN its games
        q="red sox tonight" -> its games, THEN Boston Red Sox

    So the subject substitution alone would REGRESS "red sox tonight": it
    resolves to the `red sox` page, where the team leads and the game the reader
    asked about sits behind it. A reader who types "tonight" asked about a GAME.

    Kills: dropping `_INTENT_ANSWER_TYPES` and letting `today` fall through to
    the name arm, where it promotes nothing and the team keeps the lead.
    """
    # "tonight" and "today" are the same scaffold; the fixture page is the
    # Patriots one, so the ordering half is asserted there.
    assert parse_intent("red sox tonight").kind == INTENT_TODAY
    page = compose("patriots today")
    assert page[0] is GAME, [r["text"] for r in page]
    assert TEAM in page, "the reader lost the team they named"


def test_the_two_answering_maps_never_overlap():
    """A kind is answered by its NAME or by its TYPE, never by both.

    Kills: adding a name pattern for `today` beside its type entry, which would
    make the answering test depend on which arm is consulted first — exactly the
    silent second rule this module is written to avoid.
    """
    from app.utils.search_intent import _INTENT_ANSWER_RE, _INTENT_ANSWER_TYPES

    assert not (set(_INTENT_ANSWER_RE) & set(_INTENT_ANSWER_TYPES))


def test_an_answering_row_is_matched_on_its_own_name_not_the_query():
    """Kills: matching the row against the QUERY instead of against the kind.

    `UNRELATED` ("NFL MVP 2026") shares no question word with the playoff
    intent and must not be promoted, while the playoff market must — even though
    neither string contains the word "patriots" in the same form the reader
    typed.
    """
    assert answers_intent(PLAYOFF_MARKET["text"], INTENT_PLAYOFFS) is True
    assert answers_intent(UNRELATED["text"], INTENT_PLAYOFFS) is False
