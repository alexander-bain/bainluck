"""/politics shows each race once, not once per venue — #9448.

THE READER'S VIEW (bainluck.com/politics at 390px, `/api/politics` built
2026-09-28 19:25Z): the governor section's ten cards held three Georgia races
twice each, a Polymarket card and a Kalshi card, and the Secretary of State pair
led with opposite candidates:

    60205440 polymarket  Georgia Secretary of State Election Winner   Tim Fleming (R) 49.5
    108638   kalshi      Georgia Secretary of State winner?           Penny Brown Reynolds 51.0
    60205471 polymarket  Georgia Attorney General Election Winner     Brian Strickland (R) 47.5
    108657   kalshi      Georgia Attorney General winner?             Brian Strickland 51.0
    60205419 polymarket  Georgia Lieutenant Governor Election Winner  Greg Dolezal (R) 50.5
    108521   kalshi      Georgia Lieutenant Governor winner?          Greg Dolezal 51.5

THE CAUSE: `build_section` sorted each theme's pool and sliced it; nothing
folded a venue's market into its twin.

THE TRAP: `is_same_question` also pairs "Georgia Governor winner?" with
"Georgia Lieutenant Governor winner?", which are two races. So a twin must
ALSO price the same candidates (party tag stripped), and the controls below
fail if either guard is removed.

Names, venues and candidates are the served rows above unless a comment says
otherwise.
"""

import ast
import inspect
from types import SimpleNamespace

from app.routes import politics as politics_module
from app.routes.politics import _is_venue_twin, _take_without_venue_twins
from app.utils.cross_source_matching import is_same_question


def _market(market_id: int, source: str, name: str, *candidates: str):
    return SimpleNamespace(
        id=market_id,
        source=source,
        name=name,
        outcomes=[SimpleNamespace(name=c, external_id=None) for c in candidates],
    )


SOS_POLY = _market(
    60205440, "polymarket", "Georgia Secretary of State Election Winner",
    "Tim Fleming (R)", "Penny Brown Reynolds (D)",
)
SOS_KALSHI = _market(
    108638, "kalshi", "Georgia Secretary of State winner?",
    "Penny Brown Reynolds", "Tim Fleming",
)
AG_POLY = _market(
    60205471, "polymarket", "Georgia Attorney General Election Winner",
    "Brian Strickland (R)", "Tanya Miller (D)",
)
AG_KALSHI = _market(
    108657, "kalshi", "Georgia Attorney General winner?",
    "Brian Strickland", "Tanya Miller",
)
LTGOV_POLY = _market(
    60205419, "polymarket", "Georgia Lieutenant Governor Election Winner",
    "Greg Dolezal (R)", "Josh McLaurin (D)",
)
LTGOV_KALSHI = _market(
    108521, "kalshi", "Georgia Lieutenant Governor winner?",
    "Greg Dolezal", "Josh McLaurin",
)
GOV_KALSHI = _market(
    108645, "kalshi", "Georgia Governor winner?",
    "Keisha Lance Bottoms", "Rick Jackson",
)
NEVADA_KALSHI = _market(
    109209, "kalshi", "Nevada Governor winner?", "Joe Lombardo", "Aaron Ford",
)


def _section(markets, limit=10):
    """Rows in the order given (already sorted), through the section's take."""
    return _take_without_venue_twins(
        [({"market_id": m.id}, m) for m in markets], limit
    )


def _ids(rows):
    return [r["market_id"] for r in rows]


# --------------------------------------------------------------------------
# The ship: the served governor section, one card per race
# --------------------------------------------------------------------------

def test_the_served_governor_section_shows_each_georgia_race_once():
    served_order = [
        LTGOV_POLY, GOV_KALSHI, SOS_POLY, SOS_KALSHI, AG_KALSHI,
        LTGOV_KALSHI, AG_POLY, NEVADA_KALSHI,
    ]
    assert _ids(_section(served_order)) == [
        60205419,  # Lieutenant Governor — Polymarket sorted first, kept
        108645,    # Governor — no twin on this page
        60205440,  # Secretary of State — Polymarket sorted first, kept
        108657,    # Attorney General — Kalshi sorted first, kept
        109209,    # Nevada
    ]


def test_a_folded_twins_slot_backfills_from_the_pool():
    assert _ids(_section([SOS_POLY, SOS_KALSHI, NEVADA_KALSHI], limit=2)) == [
        60205440, 109209,
    ]


def test_the_pair_keeps_whichever_card_sorts_first():
    assert _ids(_section([SOS_KALSHI, SOS_POLY])) == [108638]
    assert _ids(_section([SOS_POLY, SOS_KALSHI])) == [60205440]


def test_the_party_tag_is_the_only_difference_between_the_candidate_sets():
    for poly, kalshi in (
        (SOS_POLY, SOS_KALSHI), (AG_POLY, AG_KALSHI), (LTGOV_POLY, LTGOV_KALSHI),
    ):
        assert _is_venue_twin(poly, kalshi)
        assert _is_venue_twin(kalshi, poly)


# --------------------------------------------------------------------------
# Controls: two different races must both stay
# --------------------------------------------------------------------------

def test_governor_and_lieutenant_governor_are_two_races_though_the_titles_pair():
    # CONSTRUCTED: the real "Georgia Lieutenant Governor winner?" is Kalshi's,
    # so it is re-sourced to Polymarket here. Otherwise the same-venue guard
    # refuses the pair first and the candidate guard is never exercised.
    ltgov_as_poly = _market(
        1, "polymarket", "Georgia Lieutenant Governor winner?",
        "Greg Dolezal (R)", "Josh McLaurin (D)",
    )
    assert is_same_question(GOV_KALSHI.name, ltgov_as_poly.name), (
        "premise: the title matcher alone pairs these two races"
    )
    assert not _is_venue_twin(GOV_KALSHI, ltgov_as_poly)
    assert _ids(_section([GOV_KALSHI, ltgov_as_poly])) == [108645, 1]


def test_same_candidates_but_a_different_office_is_not_a_twin():
    # CONSTRUCTED: the AG pair's candidates on the SoS title. The candidate
    # sets match, so only the title guard can refuse this pair.
    sos_titled_ag = _market(
        2, "polymarket", "Georgia Secretary of State Election Winner",
        "Brian Strickland (R)", "Tanya Miller (D)",
    )
    assert not _is_venue_twin(AG_KALSHI, sos_titled_ag)


def test_two_markets_on_one_venue_are_never_folded():
    # CONSTRUCTED: a second Kalshi row for the Secretary of State race.
    second_kalshi = _market(
        3, "kalshi", "Georgia Secretary of State winner?",
        "Penny Brown Reynolds", "Tim Fleming",
    )
    assert _ids(_section([SOS_KALSHI, second_kalshi])) == [108638, 3]


def test_a_market_with_no_outcomes_is_never_a_twin():
    empty = _market(4, "polymarket", "Georgia Secretary of State winner?")
    assert not _is_venue_twin(SOS_KALSHI, empty)


def test_a_binary_question_on_both_venues_is_not_folded_on_its_title_alone():
    # CONSTRUCTED: "Yes" on both sides is equal and says nothing about the race,
    # so the title would be the only evidence. The uxp194 spotlight pin plants
    # exactly this pair and asserts both sides render.
    kalshi = _market(5, "kalshi", "Will the coalition hold through the winter?", "Yes")
    poly = _market(6, "polymarket", "Will the coalition hold through the winter?", "Yes")
    assert is_same_question(kalshi.name, poly.name)  # the premise: titles pair
    assert _ids(_section([kalshi, poly])) == [5, 6]


def test_a_yes_no_pair_is_not_a_candidate_set_either():
    kalshi = _market(7, "kalshi", "Will the envoy be confirmed?", "Yes", "No")
    poly = _market(8, "polymarket", "Will the envoy be confirmed?", "Yes", "No")
    assert not _is_venue_twin(kalshi, poly)


def test_one_named_candidate_is_not_enough_evidence():
    # CONSTRUCTED: two different offices, one shared nominee listed alone.
    kalshi = _market(9, "kalshi", "Georgia Governor winner?", "Rick Jackson")
    poly = _market(10, "polymarket", "Georgia Lieutenant Governor winner?", "Rick Jackson (R)")
    assert is_same_question(kalshi.name, poly.name)  # the premise: titles pair
    assert not _is_venue_twin(kalshi, poly)


# --------------------------------------------------------------------------
# Wiring: every section goes through the fold
# --------------------------------------------------------------------------

def test_build_section_returns_through_the_fold():
    """`build_section` is a closure inside the endpoint, so this reads its AST."""
    tree = ast.parse(inspect.getsource(politics_module))
    build = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "build_section"
    )
    returns = [ast.unparse(n.value) for n in ast.walk(build) if isinstance(n, ast.Return)]
    assert returns == ["_take_without_venue_twins(pairs, limit)"], returns
