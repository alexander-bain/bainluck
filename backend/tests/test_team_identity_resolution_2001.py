"""#2001 — STRUCTURAL test over PRODUCTION relabel collisions.

Fixture: the real `/api/events/15200831/related-futures` payload (Astros @
Angels), 103 rows, each joined to its `futures_outcomes.external_id` (the Kalshi
ticker) and its STORED `futures_outcomes.team_id`, plus the production
`baseball_mlb` roster. Captured 2026-08-19 from deployed `962f668a`.

Every assertion below is two-directional, per gotcha #43: the truncated pair
MERGES **and** the city sibling it prefix-matches is REFUSED. A fix that only
does the first is the Angels/Athletics catastrophe the issue was filed to avoid.

The fixture banks the stored `team_id` specifically so
`test_the_stored_team_id_would_have_fused_the_city_siblings` can prove, on
production data, why the obvious one-line fix is not available. That test is the
reason this module exists in the shape it does.
"""

import json
from pathlib import Path

import pytest

from app.utils.futures_source_merge import (
    entities_compatible,
    merge_relabel_collisions,
    rows_name_same_entity,
)
from app.utils.team_identity_resolution import (
    build_team_alias_index,
    kalshi_ticker_abbrev,
    resolve_row_team_id,
    row_entity_is_ambiguous,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "related_futures_15200831_identity_20260819.json"
)

DODGERS = 10707
ANGELS = 10712
ASTROS = 10715

# The three groups where the truncation defect renders. Each is exactly one
# Kalshi row and one Polymarket row about ONE question.
TRUNCATED_MERGE_GROUPS = ("nl_west", "nl_champion")


@pytest.fixture(scope="module")
def doc():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def rows(doc):
    return doc["rows"]


@pytest.fixture(scope="module")
def index(doc):
    return build_team_alias_index(doc["teams"])


def _group(rows, name):
    return [r for r in rows if r.get("merge_group") == name]


# ── The fixture still describes the world it was captured from ──────────


def test_fixture_still_carries_the_truncation_specimens(rows):
    """If production drifts out of this shape the tests below prove nothing."""
    trunc = {r["outcome_name"] for r in rows if r["source"] == "kalshi"}
    assert "Los Angeles D" in trunc, "specimen needs the truncated Dodgers name"
    assert "Los Angeles A" in trunc, "specimen needs the truncated Angels name"

    for group in TRUNCATED_MERGE_GROUPS:
        pair = _group(rows, group)
        assert len(pair) == 2, f"{group}: expected the unmerged two-row defect"
        assert {r["source"] for r in pair} == {"kalshi", "polymarket"}
        assert len({r["market_id"] for r in pair}) == 2


def test_the_defect_is_present_in_the_fixture_unfixed(rows):
    """Baseline: the OLD name-shape predicate refuses every truncated pair.

    This is the bug, banked. `nl_west` renders 0.97 and 0.9845 as two rows with
    the same label.
    """
    for group in TRUNCATED_MERGE_GROUPS:
        a, b = _group(rows, group)
        assert not entities_compatible(a["outcome_name"], b["outcome_name"])
        assert len(merge_relabel_collisions(_group(rows, group))) == 2


# ── The measured reason the obvious fix is unavailable ──────────────────


def test_the_stored_team_id_would_have_fused_the_city_siblings(rows):
    """`futures_outcomes.team_id` is CROSSWISE on exactly this class.

    Not a hypothetical — read off the production payload. Matching on the stored
    column would have merged Kalshi's DODGERS row into Polymarket's ANGELS row.
    """
    stored = {}
    for r in rows:
        if r.get("stored_team_id"):
            stored.setdefault((r["source"], r["outcome_name"]), r["stored_team_id"])

    # Kalshi's truncated Dodgers row is stored as the ANGELS.
    assert stored[("kalshi", "Los Angeles D")] == ANGELS
    # Polymarket's Angels row is stored as the DODGERS.
    assert stored[("polymarket", "Los Angeles Angels")] == DODGERS
    # So the two would have "agreed" about nothing, in opposite directions —
    # and any predicate keyed on the stored column inherits both errors.
    assert stored[("kalshi", "Los Angeles D")] != DODGERS
    assert stored[("polymarket", "Los Angeles Angels")] != ANGELS

    # The untruncated rows are fine, which is what makes the defect invisible
    # until a truncation lands on it.
    assert stored[("polymarket", "Los Angeles Dodgers")] == DODGERS
    assert stored[("kalshi", "Houston")] == ASTROS


def test_the_shared_city_alias_is_refused_not_ranked(index):
    """"Los Angeles" is an alternate_name of BOTH LA teams in production.

    It must resolve to nothing. A resolver that picked one would be a coin flip
    wearing an id.
    """
    assert "los angeles" in index.ambiguous_aliases
    assert index.alias_team("Los Angeles") is None
    assert index.alias_team("los angeles") is None

    # And the refused set is EXACTLY the shared strings — every two-team city in
    # MLB, plus the "All-Stars" alias the two league pseudo-teams share. Pinned
    # as a whole set, because a resolver that refused more than this would be
    # quietly deleting merges rather than protecting them.
    assert index.ambiguous_aliases == frozenset(
        {"los angeles", "new york", "chicago", "all stars"}
    )
    # Note what is NOT here: the duplicate St. Louis rows fold to one club, so
    # `STL` stays resolvable. See test_the_duplicate_cardinals_rows_do_not_poison_STL.
    assert index.ambiguous_abbrevs == frozenset()

    # Unambiguous ones survive.
    assert index.abbrev_team("LAD") == DODGERS
    assert index.abbrev_team("LAA") == ANGELS
    assert index.alias_team("Los Angeles Dodgers") == DODGERS
    assert index.alias_team("Los Angeles Angels") == ANGELS


def test_a_truncated_name_never_resolves_by_name(index):
    """Exact-match only. No prefix path exists to be exploited."""
    for truncated in ("Los Angeles D", "Los Angeles A", "Chicago C", "New York M"):
        assert index.alias_team(truncated) is None


# ── Resolution over the real rows ───────────────────────────────────────


def test_the_ticker_resolves_what_the_name_destroyed(rows, index):
    got = {}
    for r in rows:
        tid = resolve_row_team_id(r, index)
        if tid is not None:
            got.setdefault((r["source"], r["outcome_name"]), set()).add(tid)

    assert got[("kalshi", "Los Angeles D")] == {DODGERS}
    assert got[("kalshi", "Los Angeles A")] == {ANGELS}
    assert got[("kalshi", "Houston")] == {ASTROS}
    assert got[("polymarket", "Los Angeles Dodgers")] == {DODGERS}
    assert got[("polymarket", "Los Angeles Angels")] == {ANGELS}
    assert got[("polymarket", "Houston Astros")] == {ASTROS}


def test_ticker_parsing_refuses_non_team_tickers():
    assert kalshi_ticker_abbrev("KXMLBNLWEST-26-LAD") == "LAD"
    assert kalshi_ticker_abbrev("KXMLB-26-HOU") == "HOU"
    # A dated game ticker names no team at its tail.
    assert kalshi_ticker_abbrev("KXMLBRFI-26AUG202010LAAHOU") is None
    assert kalshi_ticker_abbrev(None) is None
    assert kalshi_ticker_abbrev("") is None
    # A Polymarket condition id must not be mined for letters.
    assert kalshi_ticker_abbrev("0x749d8eccbc0a99447e71fc5e40a0096842774bef") is None


def test_only_the_TAIL_of_a_ticker_is_read(index):
    """The `$` anchor is load-bearing, so pin it with a case where it decides.

    Unanchored, `re.search` returns the LEFTMOST match, so a ticker carrying a
    team in the middle would resolve to it regardless of what the market is
    about.
    """
    assert kalshi_ticker_abbrev("KXMLB-LAD-SOMETHINGELSE") is None
    assert kalshi_ticker_abbrev("KXMLB-SOMETHINGELSE-LAD") == "LAD"


def test_a_ticker_naming_TWO_teams_resolves_to_neither(index):
    """A matchup ticker has no single subject. Refuse, never pick the tail."""
    two = {"source": "kalshi", "outcome_name": "Los Angeles D",
           "external_id": "KXMLBSERIES-26-LAD-HOU"}
    assert resolve_row_team_id(two, index) is None
    # ...and the truncated name cannot rescue it into a guess either.
    assert not row_entity_is_ambiguous(two, index)

    one = {"source": "kalshi", "outcome_name": "Los Angeles D",
           "external_id": "KXMLBSERIES-26-LAD"}
    assert resolve_row_team_id(one, index) == DODGERS


def test_abbrev_lookup_is_case_insensitive(index):
    assert index.abbrev_team("lad") == DODGERS
    assert index.abbrev_team(" LaD ") == DODGERS


# ── The fix, both directions ────────────────────────────────────────────


def test_the_truncated_pair_now_merges(rows, index):
    for group in TRUNCATED_MERGE_GROUPS:
        pair = _group(rows, group)
        merged = merge_relabel_collisions(pair, index)
        assert len(merged) == 1, f"{group}: expected ONE blended row"
        assert sorted(merged[0]["all_sources"]) == ["kalshi", "polymarket"]


def test_nl_west_prints_one_number_instead_of_97_and_9845(rows, index):
    """The defect exactly as it rendered."""
    pair = _group(rows, "nl_west")
    before = sorted(r["probability"] for r in pair)
    assert before == [0.97, 0.9845]

    row = merge_relabel_collisions(pair, index)[0]
    assert row["probability"] == pytest.approx((0.97 + 0.9845) / 2)
    assert row["blend_rule"] == "equal_weight_midpoint"


def test_the_city_sibling_is_VETOED(rows, index):
    """The half that matters. Dodgers and Angels must never blend.

    Both directions of the pairing, and through the public predicate as well as
    the merge, because a prefix rule would have accepted every one of these.
    """
    kal_d = next(
        r for r in rows if r["source"] == "kalshi" and r["outcome_name"] == "Los Angeles D"
    )
    kal_a = next(
        r for r in rows if r["source"] == "kalshi" and r["outcome_name"] == "Los Angeles A"
    )
    poly_d = next(
        r
        for r in rows
        if r["source"] == "polymarket" and r["outcome_name"] == "Los Angeles Dodgers"
    )
    poly_a = next(
        r
        for r in rows
        if r["source"] == "polymarket" and r["outcome_name"] == "Los Angeles Angels"
    )

    assert not rows_name_same_entity(kal_d, poly_a, index)
    assert not rows_name_same_entity(poly_a, kal_d, index)
    assert not rows_name_same_entity(kal_a, poly_d, index)
    assert not rows_name_same_entity(poly_d, kal_a, index)

    # and the true pairings still hold
    assert rows_name_same_entity(kal_d, poly_d, index)
    assert rows_name_same_entity(kal_a, poly_a, index)


def test_a_bare_city_no_longer_merges_into_whichever_team_came_first(rows, index):
    """The veto's second payoff: today's containment predicate merges a bare
    "Los Angeles" into the Dodgers OR the Angels depending only on row order."""
    poly_d = next(
        r
        for r in rows
        if r["source"] == "polymarket" and r["outcome_name"] == "Los Angeles Dodgers"
    )
    poly_a = next(
        r
        for r in rows
        if r["source"] == "polymarket" and r["outcome_name"] == "Los Angeles Angels"
    )
    bare = dict(poly_d)
    bare.update(
        {
            "source": "kalshi",
            "outcome_name": "Los Angeles",
            "external_id": None,
            "market_id": (poly_d["market_id"] or 0) + 1,
        }
    )

    # The OLD predicate accepts it against BOTH clubs — that is the latent bug:
    # the answer is decided by whichever row is encountered first.
    assert entities_compatible("Los Angeles", "Los Angeles Dodgers")
    assert entities_compatible("Los Angeles", "Los Angeles Angels")

    # The new one refuses both, because "Los Angeles" is KNOWN to name two teams.
    assert not rows_name_same_entity(bare, poly_d, index)
    assert not rows_name_same_entity(bare, poly_a, index)


def test_unrecognised_is_not_ambiguous_and_still_falls_through(rows, index):
    """The distinction the veto rests on. A name we have never seen must NOT be
    treated as a name we know is shared — otherwise the veto would quietly
    delete every merge outside the team roster (awards, players, matchups)."""
    unknown = {"source": "kalshi", "outcome_name": "Waterloo Road FC"}
    assert resolve_row_team_id(unknown, index) is None
    assert not row_entity_is_ambiguous(unknown, index)

    shared = {"source": "kalshi", "outcome_name": "Los Angeles"}
    assert resolve_row_team_id(shared, index) is None
    assert row_entity_is_ambiguous(shared, index) is True

    # Two unrecognised-but-compatible names still merge on shape, as before.
    a = {"source": "kalshi", "outcome_name": "Mason Miller", "market_id": 1}
    b = {"source": "polymarket", "outcome_name": "Mason Miller", "market_id": 2}
    assert rows_name_same_entity(a, b, index)


def test_the_duplicate_cardinals_rows_do_not_poison_STL(index, doc):
    """Production carries TWO St. Louis Cardinals team rows. They must fold to
    one club, not declare the club ambiguous — otherwise a known duplicate-row
    defect would silently become a merge outage on this surface."""
    stl = [t for t in doc["teams"] if "cardinals" in t["name"].lower()]
    assert len(stl) == 2, "specimen needs the duplicate rows"
    assert len({t["id"] for t in stl}) == 2

    assert "STL" not in index.ambiguous_abbrevs
    assert index.abbrev_team("STL") == min(t["id"] for t in stl)
    assert index.alias_team("St. Louis Cardinals") == index.abbrev_team("STL")
    assert index.alias_team("St.Louis Cardinals") == index.abbrev_team("STL")
    assert not index.is_ambiguous("St. Louis")


# ── Nothing else moved ──────────────────────────────────────────────────


def test_the_same_source_fan_is_untouched(rows, index):
    """43 Kalshi world_series_matchup rows are 43 questions, not one."""
    fan = _group(rows, "world_series_matchup")
    assert len(fan) == 43
    assert {r["source"] for r in fan} == {"kalshi"}
    assert merge_relabel_collisions(fan, index) == fan


def test_full_payload_census_only_the_expected_classes_collapse(rows, index):
    """Total accounting over all 103 production rows."""
    before = rows
    after = merge_relabel_collisions(before, index)

    merged_rows = [r for r in after if r.get("blend_rule")]
    groups = sorted(r["merge_group"] for r in merged_rows)
    assert groups == [
        "al_champion",
        "al_champion",
        "al_west",
        "al_west",
        "nl_champion",
        "nl_west",
        "world_series_champion",
        "world_series_champion",
        "world_series_champion",
    ], groups

    # Every merged row is a genuine two-source pair — never three, never one.
    for r in merged_rows:
        assert sorted(r["all_sources"]) == ["kalshi", "polymarket"]
        assert r["merged_source_count"] == 2

    assert len(after) == len(before) - len(merged_rows)

    # Untouched rows survive byte-identical.
    survivors = [r for r in before if r.get("merge_group") is None]
    assert all(r in after for r in survivors)


def test_omitting_the_index_is_byte_identical_to_the_old_behaviour(rows):
    """Additive, not a rewrite: no index -> exactly what shipped before."""
    assert merge_relabel_collisions(rows, None) == merge_relabel_collisions(rows)
