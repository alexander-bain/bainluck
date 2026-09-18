"""#6909 — every NFL prop was ungradeable from the box score, because the stat
vocabulary was baseball, basketball and soccer only.

`_prop_stat_keys` resolves a Kalshi ticker prefix first and a market name
second. Both tables held NBA/NHL/MLB entries and nothing else, and
`_PROP_NAME_STAT_SINGLES` carries no football stat either, so every NFL prop
returned None and `_grade_settled_prop` bailed before it read a stat.

Measured on production 2026-09-18 (49ers 7 - Rams 27, `completed`, event
14632820): `actual` was null on **510 of 510** served props, and **35** printed
`Resolved · grading unavailable` while that same event's `box_score_data` held
the answer — Puka Nacua's line says 74 receiving yards, so the withheld
"Puka Nacua: 80+" was always a MISS.

Two things this file pins that the diff alone does not say:

1. **The key is what the BOX SCORE calls it, not what the series calls it.**
   Kalshi's Rushing Attempts series is `KXNFLRSHATT`; ESPN stores that quantity
   as `carries`. A plausible-looking `"rushing attempts"` entry would have gone
   on returning None forever and read as "still unmapped".

2. **`kxnflrec` is a proper prefix of `kxnflrecyds`** — the #1728 collision
   exactly. It is safe only because `_prop_stats_for_ticker` takes the LONGEST
   matching prefix; under first-match-wins every receiving-yards prop would
   grade off a reception COUNT.

The census runs the REAL route grading functions over the REAL captured payload
and asserts both directions (gotcha #43): every intended row newly grades, and
ZERO rows of any other class move. The 13 newly-graded verdicts below were each
hand-checked against the box-score line quoted beside them.

** THIS SHIP IS NARROW AND SAYS SO. ** It does not make every NFL prop
gradeable: 178 of the 510 rows still carry no stat line after it. What it
claims is that none of them is an unexplained gap —
`test_every_row_still_without_a_stat_line_is_accounted_for` sorts every one
into a named bucket and fails if any lands outside them. Team totals and
cross-player superlatives are named follow-ups there, which is why #6909 stays
open.
"""

import json
from pathlib import Path

import pytest

from app.routes.events import (
    _build_prop_grade_context,
    _grade_settled_prop,
    _prop_stat_keys,
)
from app.tasks.backfill_winners import _PROP_TICKER_TO_STAT

FIXTURE = Path(__file__).parent / "fixtures" / "event_nfl_prop_vocabulary_6909.json"


class _Obj:
    """Stand-in for the ORM rows the grader reads (attribute access only)."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture(scope="module")
def captured():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def ctx(captured):
    event = _Obj(box_score_data={"players": captured["box_score_players"]})
    built = _build_prop_grade_context(event)
    # Not an assertion about the fix: the context built fine BEFORE it too. The
    # box score was never the missing piece, which is the whole point of #6909.
    assert built is not None
    return built


def _grade_every_prop(captured, ctx):
    """Run the real grader over every captured row. Returns (row, result) pairs.

    🪤 THE PRICE COMES FROM `_stored`, NOT FROM THE SERVED `over_probability`.
    `_venue_typed_hit` (#6751) reads `outcome.current_probability`, and the two
    are not the same number: on 3 of these 510 rows the route serves 0.01 for a
    Team Sacks rung the database stores at 0.12-0.31. Feeding the served value
    back in put those rungs under the 0.1 loss ceiling and made this rig type
    three MISS verdicts production never printed — a finding about the harness
    wearing the shape of a finding about the fix.
    """
    out = []
    for row in captured["player_props"]:
        meta = captured["markets"][str(row["_market_id"])]
        stored = row["_stored"] or {}
        market = _Obj(external_id=meta["external_id"], name=meta["name"])
        outcome = _Obj(
            name=row["outcome_name"],
            is_winner=stored.get("is_winner", row["is_winner"]),
            resolution_source=stored.get("resolution_source", row["resolution_source"]),
            current_probability=stored.get("current_probability"),
        )
        graded = _grade_settled_prop(
            True, ctx, market, outcome, row["threshold"], row["_inverted"]
        )
        out.append((row, graded))
    return out


# Every row the fix newly grades, with the box-score line that decides it.
# `served` is what production printed on 2026-09-18: None == the reader saw
# "Resolved · grading unavailable".
EXPECTED_NEWLY_GRADED = {
    ("Puka Nacua: 80+", "Receiving Yards"): (74.0, False),
    ("Demarcus Robinson: 50+", "Receiving Yards"): (50.0, True),
    ("Kyren Williams: 50+", "Rushing Yards"): (41.0, False),
    ("Kyren Williams: 60+", "Rushing Yards"): (41.0, False),
    ("Christian McCaffrey: 110+", "Rushing Yards"): (68.0, False),
    ("Matthew Stafford: 19+", "Passing Completions"): (15.0, False),
    ("Brock Purdy: 5+", "Rushing Attempts"): (5.0, True),
    ("Brock Purdy: 7+", "Rushing Attempts"): (5.0, False),
    ("Deebo Samuel Sr.: 6+", "Receptions"): (6.0, True),
    ("Puka Nacua: 6+", "Receptions"): (5.0, False),
    ("Colby Parkinson: 2+", "Receptions"): (1.0, False),
    # Second pass (CERT-3058's required repair). Both legs are keys ESPN
    # already writes, so the composite is the whole fix.
    ("Kyren Williams: 70+", "Rushing + Receiving Yards"): (65.0, False),
    ("Christian McCaffrey: 110+", "Rushing + Receiving Yards"): (88.0, False),
}


def _label(row, captured):
    return (
        row["outcome_name"],
        captured["markets"][str(row["_market_id"])]["name"].split(": ")[-1],
    )


def test_the_captured_payload_still_carries_the_defect(captured):
    """The fixture is the BEFORE and must not be refreshed from a fixed tree."""
    props = captured["player_props"]
    assert len(props) == 510
    assert sum(1 for r in props if r["hit"] is None) == 35
    assert all(r.get("actual") is None for r in props if "actual" in r)
    # Every row carries its STORED price/verdict, including the 20 TEAM rungs
    # whose served label the route lengthens ("Los Angeles R" -> "Los Angeles
    # Rams") so it no longer keys the stored outcome by name. Those were
    # re-matched on the "N+" tail plus a prefix-compatible team; a fixture that
    # loses them silently withholds 13 verdicts production printed, which is
    # what the rig-validity test below exists to catch.
    assert all(r["_stored"] for r in props)


def test_the_rig_reproduces_production_wherever_the_box_score_stays_silent(
    captured, ctx
):
    """Rig validity, asserted before anything is concluded from the rig.

    On every row the box score CANNOT answer, this harness must print exactly
    what production printed on 2026-09-18 — same verdict, same withholding.
    Where it does not, the harness is the story and no census taken with it
    means anything (gotcha #124's shape, applied to a fixture rig).
    """
    mismatches = []
    for row, graded in _grade_every_prop(captured, ctx):
        if graded.get("actual") is not None:
            continue  # the box score answered; that IS the change under test
        if graded.get("hit") != row["hit"]:
            mismatches.append((_label(row, captured), row["hit"], graded.get("hit")))
    assert mismatches == []


def test_every_withheld_row_the_box_score_can_answer_is_now_graded(captured, ctx):
    newly = {}
    for row, graded in _grade_every_prop(captured, ctx):
        if row["hit"] is None and graded.get("hit") is not None:
            newly[_label(row, captured)] = (graded["actual"], graded["hit"])
    assert newly == EXPECTED_NEWLY_GRADED


def test_no_row_that_graded_before_changes_its_verdict(captured, ctx):
    """The direction that would be a REGRESSION, asserted on its own.

    #4783 is open about venue-contradicted grades on NFL pages, so a fix that
    newly disagrees with a Kalshi settlement is not obviously an improvement.
    Measured: on this game it disagrees with none of them — 0 flips against 312
    box-score-confirmed agreements. A future mapping that flips one has to come
    past this test and say so.
    """
    flips, preserved, box_confirmed = [], 0, 0
    for row, graded in _grade_every_prop(captured, ctx):
        served, fresh = row["hit"], graded.get("hit")
        if served is None or fresh is None:
            continue
        if served != fresh:
            flips.append((_label(row, captured), served, fresh))
            continue
        preserved += 1
        if graded.get("actual") is not None:
            # The box score read the stat itself and landed on the same verdict
            # the venue had already typed off the price. This is the cell that
            # makes the whole ship safe, so it is counted apart from the rows
            # the venue is still carrying alone.
            box_confirmed += 1
    assert flips == []
    assert preserved == 475
    # 312 on the first pass; the `kxnflrryds` composite gives seven already-typed
    # rungs a stat line without moving one of them. Each of those seven is also
    # checked individually below, because a count rising is not the same claim as
    # the right seven rising.
    assert box_confirmed == 319


def test_the_newly_graded_rows_corroborate_the_venue_in_the_band_it_refuses(
    captured, ctx
):
    """Why the fix is the vocabulary and NOT a looser `_VENUE_GRADE_*` bound.

    #6751's venue fallback types a verdict only when the settled price
    corroborates it (>= 0.9 won / <= 0.1 lost). Those bounds were calibrated on
    `KXNFLFFPTS`, whose settled prices converge; NFL box-score props do not, so
    the refused rows sit at 0.5-0.89 and the gate withholds exactly the close
    calls. There was no ground truth for that band — zero box-score-graded rows
    live in it — and `is_winner` agreeing on the rows the gate already passes
    cannot speak for the rows it refuses.

    The box score supplies that missing ground truth, and the venue was right
    all 13 times, INCLUDING "Brock Purdy: 7+" at a settled price of 0.89 that a
    looser floor would have graded a HIT off a 5-carry game. So the constants
    stay where they are.
    """
    checked = 0
    for row, graded in _grade_every_prop(captured, ctx):
        if row["hit"] is not None or graded.get("hit") is None:
            continue
        assert graded["hit"] == row["is_winner"], _label(row, captured)
        checked += 1
    assert checked == 13


def test_the_rushing_attempts_key_is_carries_not_rushing_attempts():
    """The naming trap, pinned: ESPN has no "rushing attempts" key at all."""
    assert _PROP_TICKER_TO_STAT["kxnflrshatt"] == "carries"


def test_kxnflrecyds_outranks_the_kxnflrec_prefix_it_extends(captured):
    """#1728's collision, on the pair this ship adds."""
    recyds = _Obj(external_id="KXNFLRECYDS-26SEP10SFLAR", name="x: Receiving Yards")
    rec = _Obj(external_id="KXNFLREC-26SEP10SFLAR", name="x: Receptions")
    assert _prop_stat_keys(recyds, {"stats_for_ticker": _stats}) == ["receiving yards"]
    assert _prop_stat_keys(rec, {"stats_for_ticker": _stats}) == ["receptions"]


def _stats(ticker_lower):
    from app.tasks.backfill_winners import _prop_stats_for_ticker

    return _prop_stats_for_ticker(ticker_lower)


@pytest.mark.parametrize(
    "prefix,why",
    [
        ("kxnflpassatt", "an ESPN line has completions, no attempts key"),
        ("kxnfltd", "does not say which of rushing/receiving/return TDs it sums"),
        ("kxnflffpts", "a scoring formula, not a box-score stat (#6751 grades it)"),
    ],
)
def test_the_deliberate_absences_stay_absent(prefix, why):
    """Each of these is a WITHHOLDING, not a gap for a later pattern-fill.

    Mapping one of them to a plausible neighbouring key is how a confident
    wrong verdict gets published, which is the failure #1728 exists for.
    """
    assert _stats(f"{prefix}-26sep10sflar") is None, why


def test_team_and_leaderboard_tickers_are_not_swept_up_by_a_player_prefix():
    """The blast-radius check: these share the KXNFL stem and must stay unmapped."""
    for ticker in (
        "kxnflteamyds",
        "kxnflteamtd",
        "kxnflteamsack",
        "kxnflfg",
        "kxnflmostrshyds",
        "kxnflmostrecyds",
    ):
        assert _stats(f"{ticker}-26sep10sflar") is None, ticker


# --------------------------------------------------------------------------
# CERT-3058's required repair: the Rushing + Receiving Yards composite.
# --------------------------------------------------------------------------


def test_kxnflrryds_reads_both_component_keys_and_neither_alone():
    """The composite, and the prefix neighbourhood it lands in.

    `kxnflrryds` shares the `kxnflr` stem with `kxnflrshyds`, `kxnflrecyds` and
    `kxnflrec`, so the thing to prove is not only that it resolves but that it
    did not disturb — or get answered by — any of the three it sits beside.
    """
    assert _stats("kxnflrryds-26sep10sflar") == ["rushing yards", "receiving yards"]
    assert _stats("kxnflrshyds-26sep10sflar") == ["rushing yards"]
    assert _stats("kxnflrecyds-26sep10sflar") == ["receiving yards"]
    assert _stats("kxnflrec-26sep10sflar") == ["receptions"]


def test_kxnflrryds_grades_the_two_withheld_rungs_off_the_summed_line(captured, ctx):
    """The rows a reader was watching print "Resolved · grading unavailable".

    Hand-checked against the box score, which is the bar the first pass set and
    the reason this family was held back from it: Kyren Williams 41 rushing +
    24 receiving = 65 against a 70+ rung, Christian McCaffrey 68 + 20 = 88
    against 110+. Both MISS.
    """
    newly = {}
    for row, graded in _grade_every_prop(captured, ctx):
        if "RRYDS" not in captured["markets"][str(row["_market_id"])]["external_id"]:
            continue
        if row["hit"] is None and graded.get("hit") is not None:
            newly[row["outcome_name"]] = (graded["actual"], graded["hit"])
    assert newly == {
        "Kyren Williams: 70+": (65.0, False),
        "Christian McCaffrey: 110+": (88.0, False),
    }


def test_kxnflrryds_preserves_every_verdict_it_newly_explains(captured, ctx):
    """The winner/loser preservation half, named row by row.

    Seven already-typed rungs gain a stat line here. A count is not enough: a
    composite that summed the WRONG two keys would still raise the count, and
    the three rungs that sit either side of Deebo Samuel's 60 yards are the
    ones that would expose it. The ladder is the independent second signal —
    40+ HIT, 65+ MISS, 90+ MISS can only bracket one number.
    """
    gained = {}
    for row, graded in _grade_every_prop(captured, ctx):
        if "RRYDS" not in captured["markets"][str(row["_market_id"])]["external_id"]:
            continue
        if row["hit"] is None or graded.get("actual") is None:
            continue
        assert graded["hit"] == row["hit"], row["outcome_name"]
        gained[row["outcome_name"]] = (graded["actual"], graded["hit"])
    assert gained == {
        "Deebo Samuel Sr.: 40+": (60.0, True),
        "Deebo Samuel Sr.: 65+": (60.0, False),
        "Deebo Samuel Sr.: 90+": (60.0, False),
        "Kyren Williams: 95+": (65.0, False),
        "Kyren Williams: 120+": (65.0, False),
        "Christian McCaffrey: 135+": (88.0, False),
        "Christian McCaffrey: 160+": (88.0, False),
    }


def test_a_receiver_who_never_carried_is_withheld_rather_than_summed_as_zero(
    captured, ctx
):
    """The three rows this repair deliberately does NOT grade, and why.

    Puka Nacua IS in the box score, with 74 receiving yards and no `rushing
    yards` key at all — he never carried. Reading that absence as a zero would
    give 74 and grade his 100+/125+/150+ rungs, and on this game it would even
    be right. It stays withheld anyway: `_sum_prop_stats` withholds on any
    unresolvable leg (#1728), and the absence of a key cannot distinguish "did
    not carry" from "the parse dropped the rushing group". Buying three
    verdicts by weakening that is the trade #1728 exists to refuse.

    So this is a pinned withholding, not an oversight — the same standing the
    deliberate absences above have.
    """
    withheld = set()
    for row, graded in _grade_every_prop(captured, ctx):
        if "RRYDS" not in captured["markets"][str(row["_market_id"])]["external_id"]:
            continue
        if graded.get("actual") is None:
            withheld.add(row["outcome_name"])
    assert withheld == {"Puka Nacua: 100+", "Puka Nacua: 125+", "Puka Nacua: 150+"}
    assert "rushing yards" not in captured["box_score_players"]["Puka Nacua"]
    assert captured["box_score_players"]["Puka Nacua"]["receiving yards"] == 74.0


# The families this ship maps. Kept beside the accounting test below so the
# taxonomy cannot drift away from the table it describes.
_MAPPED_NFL_FAMILIES = frozenset(
    {
        "kxnflpassyds",
        "kxnflrshyds",
        "kxnflrecyds",
        "kxnflpasstds",
        "kxnflpasscomp",
        "kxnflpassint",
        "kxnflrshatt",
        "kxnfllongrsh",
        "kxnfllongrec",
        "kxnflrec",
        "kxnflrryds",
    }
)


def _residual_bucket(ticker):
    if ticker in ("kxnfltd", "kxnflpassatt"):
        return "deliberate withholding"
    if ticker.startswith("kxnflteam") or ticker == "kxnflfg":
        return "team-level, not a player prop"
    if ticker.startswith("kxnflmost"):
        return "cross-player superlative"
    if ticker in _MAPPED_NFL_FAMILIES:
        return "mapped family, leg absent from the box score"
    return "UNCLASSIFIED"


def test_every_row_still_without_a_stat_line_is_accounted_for(captured, ctx):
    """The ship is NARROW, and this is the test that keeps the claim honest.

    #6909 does not make every NFL prop gradeable and must not be read as if it
    did: after this repair 178 of the 510 captured rows still carry no stat
    line. What it does claim is that none of them is an unexplained gap. Each
    falls in exactly one bucket, and **UNCLASSIFIED must be empty** — that is
    the assertion, the counts beside it are just the current census.

    Two of these buckets are follow-ups with a named shape, not pattern-fills,
    and they are why #6909 stays OPEN:

    * `kxnflteam*` / `kxnflfg` (40) — team totals. They need a team-level
      aggregate the player map cannot express; `box_score_data["players"]` is
      keyed by player and has no team row to read.
    * `kxnflmost*` (25) — "Most Receiving Yards" is a superlative across
      players, not an "N+" threshold against one. `_PROP_RE` does not even
      parse it, so it needs a different grader, not a different key.

    The other two are settled questions, not follow-ups: 65 are the deliberate
    withholdings pinned above, and 48 are rows whose leg the box score simply
    does not carry (a back with no receiving line, a receiver who never
    carried), which `_sum_prop_stats` withholds by #1728's rule.
    """
    import collections

    buckets = collections.Counter()
    for row, graded in _grade_every_prop(captured, ctx):
        if graded.get("actual") is not None:
            continue
        meta = captured["markets"][str(row["_market_id"])]
        ticker = (meta["external_id"] or "").split("-")[0].lower()
        buckets[_residual_bucket(ticker)] += 1

    assert buckets["UNCLASSIFIED"] == 0, "a residual row no bucket explains"
    assert dict(buckets) == {
        "deliberate withholding": 65,
        "mapped family, leg absent from the box score": 48,
        "team-level, not a player prop": 40,
        "cross-player superlative": 25,
    }
    assert sum(buckets.values()) == 178
