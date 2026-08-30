"""#1728 — a settled prop that HIT printed a red MISS, because a composite
statistic was graded as a different statistic entirely.

Two defects, one class each, both measured on production 2026-08-30:

1. **FIRST-PREFIX-WINS over the ticker maps.** `_PROP_TICKER_TO_STAT` and
   `_COMBO_STATS` are matched by ticker PREFIX, and some Kalshi series tickers
   are proper prefixes of others. `KXMLBHRR` ("Hits + Runs + RBIs") extends
   `KXMLBHR` ("home runs"), so the shorter key answered first and **1,890
   event-linked KXMLBHRR markets published a batter's HOME RUN total as their
   `actual`**. A 2-hit game rendered `0` and a red MISS. `KXNBAPRA` extends
   `KXNBAPR` the same way (no live rows today — NBA offseason — which is
   exactly why the rule, not the instance, is what gets fixed).

2. **A MISSING KEY TREATED AS A ZERO.** Both the route (`found = any leg
   resolved`) and the resolver (`get(stat, 0)`) turned an unresolvable leg into
   a silent PARTIAL sum and published a confident verdict off it. Ruling
   "settled means settled" plus the standing rule that no verdict beats a wrong
   one: a composite grades only when every leg resolves.

The census below runs the REAL route grading functions over a REAL captured
payload (both events named in the issue, 77 H+R+RBI outcome rows) and asserts
the transition census in both directions (gotcha #43) — every intended change
happens, and zero of any other class.
"""

import json
from pathlib import Path

import pytest

from app.routes.events import (
    _build_prop_grade_context,
    _grade_settled_prop,
    _prop_stat_keys,
)
from app.tasks.backfill_winners import _COMBO_STATS, _PROP_TICKER_TO_STAT

# `_prop_stats_for_ticker`, `_sum_prop_stats` and `_PRESENCE_FLAG_STATS` are
# imported INSIDE the tests that use them, deliberately: this file is the
# red-first probe for #1728 and must stay COLLECTABLE against the unfixed tree,
# where those three symbols do not exist. A module-level import there is a
# collection crash, and a collection crash is a story about the harness rather
# than a result (gotcha #124).

FIXTURE = Path(__file__).parent / "fixtures" / "event_hits_runs_rbis_1728.json"

# The three rows the issue reports as red-MISS-on-a-HIT and that the fix flips.
EXPECTED_VERDICT_FLIPS = {
    ("15187845", "Corey Seager: 2+"),
    ("15187845", "Mike Trout: 3+"),
    ("15187845", "Vaughn Grissom: 2+"),
}

HRR_KEYS = ("hits", "runs", "rbis")


class _Obj:
    """Stand-in for the ORM rows the grader reads (attribute access only)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.fixture(scope="module")
def payload():
    return json.loads(FIXTURE.read_text())


def _ctx_for(event_payload):
    built = _build_prop_grade_context(
        _Obj(box_score_data={"source": "espn", "players": event_payload["box_score"]})
    )
    assert built is not None, "real production box score must build a grade context"
    return built


# --------------------------------------------------------------------------
# Defect 1 — the prefix collision, and the RULE that prevents the next one
# --------------------------------------------------------------------------


def test_the_composite_ticker_is_not_graded_as_home_runs():
    """KXMLBHRR is Hits+Runs+RBIs. KXMLBHR is home runs. It read the latter."""
    from app.tasks.backfill_winners import _prop_stats_for_ticker

    assert _prop_stats_for_ticker("kxmlbhrr-26aug11clechw-x") == [
        "hits",
        "runs",
        "rbis",
    ]


def test_the_shorter_sibling_still_resolves_to_itself():
    """Both directions: fixing KXMLBHRR must not steal KXMLBHR's own rows."""
    from app.tasks.backfill_winners import _prop_stats_for_ticker

    assert _prop_stats_for_ticker("kxmlbhr-26aug11clechw-x") == ["home runs"]


def test_the_latent_nba_collision_is_fixed_too():
    """KXNBAPRA extends KXNBAPR — the same class, zero live rows today."""
    from app.tasks.backfill_winners import _prop_stats_for_ticker

    assert _prop_stats_for_ticker("kxnbapra-26x") == ["points", "rebounds", "assists"]
    assert _prop_stats_for_ticker("kxnbapr-26x") == ["points", "rebounds"]


def test_the_standalone_rbi_series_has_a_mapping_at_all():
    """KXMLBRBI had none, so every one of its outcomes was withheld.

    Withholding is the honest failure mode, not a false verdict — this is a
    coverage gap rather than a wrong answer, and it is fixed here because it is
    the same statistic and the same box-score key as the composite above.
    """
    from app.tasks.backfill_winners import _prop_stats_for_ticker

    assert _prop_stats_for_ticker("kxmlbrbi-26x") == ["rbis"]


def test_no_mapping_is_shadowed_by_a_shorter_sibling():
    """THE CLASS CHECK, not the instance.

    For EVERY key in either table, a ticker built from that key must resolve to
    that key's own stats. This is what nothing asserted, and it is why two
    series were silently graded as different statistics. Any future series that
    extends an existing prefix fails here instead of shipping a false verdict.
    """
    from app.tasks.backfill_winners import _prop_stats_for_ticker

    shadowed = {}
    for table in (_PROP_TICKER_TO_STAT, _COMBO_STATS):
        for prefix, stat in table.items():
            want = [stat] if isinstance(stat, str) else list(stat)
            got = _prop_stats_for_ticker(prefix + "-26x")
            if got != want:
                shadowed[prefix] = {"want": want, "got": got}
    assert not shadowed, (
        "These ticker prefixes resolve to another series' statistic, so every "
        f"one of their outcomes grades off the wrong column: {shadowed}"
    )


def test_dict_insertion_order_is_not_load_bearing():
    """Hand-ordering the literals would fix today and re-break tomorrow.

    Re-running the resolution against a reversed view of each table must give
    the same answer — that is the difference between "we ordered the dict" and
    "longest prefix wins".
    """
    import app.tasks.backfill_winners as bw

    original_single, original_combo = bw._PROP_TICKER_TO_STAT, bw._COMBO_STATS
    try:
        bw._PROP_TICKER_TO_STAT = dict(reversed(list(original_single.items())))
        bw._COMBO_STATS = dict(reversed(list(original_combo.items())))
        assert bw._prop_stats_for_ticker("kxmlbhrr-26x") == ["hits", "runs", "rbis"]
        assert bw._prop_stats_for_ticker("kxmlbhr-26x") == ["home runs"]
        assert bw._prop_stats_for_ticker("kxnbapra-26x") == [
            "points",
            "rebounds",
            "assists",
        ]
    finally:
        bw._PROP_TICKER_TO_STAT, bw._COMBO_STATS = original_single, original_combo


def test_the_market_name_fallback_reads_the_composite_not_the_bare_hits(payload):
    """Polymarket-shaped rows carry no Kalshi ticker; the NAME must still parse.

    "Hits + Runs + RBIs" contains the substring "hits", and the singles loop
    would have claimed it.
    """
    ctx = _ctx_for(payload["events"]["15187845"])
    market = _Obj(external_id=None, name="Texas vs LA Angels: Hits + Runs + RBIs")
    assert _prop_stat_keys(market, ctx) == ["hits", "runs", "rbis"]


# --------------------------------------------------------------------------
# Defect 2 — a missing key is not a zero
# --------------------------------------------------------------------------


def test_a_missing_leg_withholds_rather_than_publishing_a_partial_sum():
    from app.tasks.backfill_winners import _sum_prop_stats

    assert _sum_prop_stats({"hits": 2.0, "runs": 1.0}, list(HRR_KEYS)) is None


def test_a_complete_row_sums_every_leg():
    from app.tasks.backfill_winners import _sum_prop_stats

    assert _sum_prop_stats(
        {"hits": 2.0, "runs": 1.0, "rbis": 3.0}, list(HRR_KEYS)
    ) == 6.0


def test_a_non_numeric_leg_withholds():
    from app.tasks.backfill_winners import _sum_prop_stats

    assert _sum_prop_stats({"hits": "DNP", "runs": 1.0, "rbis": 0.0}, list(HRR_KEYS)) is None


def test_an_absent_presence_flag_is_a_genuine_zero_not_a_withhold():
    """The exception, and it is load-bearing.

    `espn_api.py` writes "double doubles" ONLY when the player recorded one, so
    absence there means zero. Withholding on it would strip a correct "no" from
    every player who did not record a double-double — a regression the blanket
    rule would have shipped silently.
    """
    from app.tasks.backfill_winners import _PRESENCE_FLAG_STATS, _sum_prop_stats

    assert "double doubles" in _PRESENCE_FLAG_STATS
    assert _sum_prop_stats({"points": 12.0}, ["double doubles"]) == 0.0


def test_the_route_withholds_on_a_pitcher_row_instead_of_grading_it(payload):
    """A pitcher's box line carries hits/runs but no rbis (they are ALLOWED,
    not earned). Grading a batter composite off it published a partial sum."""
    ev = payload["events"]["15187845"]
    pitchers = [n for n, s in ev["box_score"].items() if "rbis" not in s]
    assert pitchers, "fixture must retain at least one pitcher row"
    ctx = _ctx_for(ev)
    graded = _grade_settled_prop(
        True,
        ctx,
        _Obj(external_id="KXMLBHRR-26X", name="Texas vs LA Angels: Hits + Runs + RBIs",
             status="resolved"),
        _Obj(name=f"{pitchers[0]}: 2+", is_winner=False,
             resolution_source="api_settlement"),
        2.0,
        False,
    )
    assert graded["actual"] is None
    assert graded["hit"] is None, "a wrong verdict is worse than none"


# --------------------------------------------------------------------------
# The transition census over the real payload — both directions
# --------------------------------------------------------------------------


def _census(payload):
    flips, actual_changes, wrong, withheld, unchanged = set(), 0, [], 0, 0
    for eid, ev in payload["events"].items():
        ctx = _ctx_for(ev)
        for row in ev["hrr_props"]:
            outcome_name = row["outcome_name"]
            player = outcome_name.split(":")[0].strip()
            stats = ctx["norm_box"].get(ctx["normalize"](player))
            if stats is None:
                continue
            graded = _grade_settled_prop(
                True,
                ctx,
                _Obj(external_id="KXMLBHRR-26X", name=row["market_name"],
                     status="resolved"),
                _Obj(name=outcome_name, is_winner=row["published"].get("hit"),
                     resolution_source=row["published"].get("resolution_source")),
                row["threshold"],
                False,
            )
            if any(stats.get(k) is None for k in HRR_KEYS):
                withheld += 1
                if graded["hit"] is not None or graded["actual"] is not None:
                    wrong.append(("published a partial", eid, outcome_name, graded))
                continue
            truth = sum(float(stats[k]) for k in HRR_KEYS)
            if graded["actual"] != truth:
                wrong.append(("wrong actual", eid, outcome_name, truth, graded["actual"]))
            if graded["hit"] != (truth >= row["threshold"]):
                wrong.append(("wrong verdict", eid, outcome_name, graded["hit"]))
            if graded["actual"] != row["published"]["actual"]:
                actual_changes += 1
            else:
                unchanged += 1
            if graded["hit"] != row["published"]["hit"]:
                flips.add((eid, outcome_name))
    return flips, actual_changes, wrong, withheld, unchanged


def test_every_composite_row_grades_to_its_own_box_score(payload):
    """Acceptance 1 + 3: every cross-checkable row is right, none is withheld,
    and nothing that was already correct moved."""
    flips, actual_changes, wrong, withheld, unchanged = _census(payload)
    assert not wrong, f"rows still disagreeing with the box score: {wrong[:8]}"
    assert withheld == 0, (
        "every player named by an H+R+RBI prop on these two events is a batter "
        "with all three legs; a withhold here means the fixture or the lookup "
        f"changed shape ({withheld} rows)"
    )
    assert actual_changes >= 39, (
        f"the measured production defect was 39 wrong `actual` values; "
        f"only {actual_changes} changed"
    )
    assert unchanged >= 20, (
        f"rows that were already correct must stay correct; only {unchanged} "
        "were left alone"
    )


def test_the_red_misses_named_in_the_issue_now_read_as_hits(payload):
    """Acceptance 1: the user-visible half. These printed a red MISS."""
    flips, _, _, _, _ = _census(payload)
    assert flips == EXPECTED_VERDICT_FLIPS, (
        "the set of verdicts this fix changes must be exactly the three rows "
        f"the box score says HIT — got {sorted(flips)}"
    )


def test_no_verdict_flips_from_hit_to_miss(payload):
    """The other direction: nothing that read HIT may start reading MISS."""
    regressions = []
    for eid, ev in payload["events"].items():
        ctx = _ctx_for(ev)
        for row in ev["hrr_props"]:
            if row["published"]["hit"] is not True:
                continue
            graded = _grade_settled_prop(
                True,
                ctx,
                _Obj(external_id="KXMLBHRR-26X", name=row["market_name"],
                     status="resolved"),
                _Obj(name=row["outcome_name"], is_winner=True,
                     resolution_source="api_settlement"),
                row["threshold"],
                False,
            )
            if graded["hit"] is False:
                regressions.append((eid, row["outcome_name"], graded))
    assert not regressions, f"HIT -> MISS regressions: {regressions}"
