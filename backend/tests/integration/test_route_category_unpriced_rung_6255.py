"""#6255 — a traded ladder must not print `0%` for a rung we hold no price for.

The half of #6235's class that #6235 deliberately left alone. #6235 withdraws a
market **nobody** has priced; a ladder with a real, traded leader could still
print a rung at `0%` underneath it — not because the market says "no", but
because `_market_row`'s `float(o.current_probability or 0)` folded a NULL to
zero. On screen that is indistinguishable from a rung the market has priced at
zero, and only the second of those is data (#2950).

MEASURED ON THE SERVED PAYLOAD, 2026-09-17 14:40Z — the page, not the table.
68 politics + 109 entertainment unique market rows were served; **16 carried a
`0.0` rung**. Each of those rungs was then read back out of `futures_outcomes`
rather than inferred from the rendered number, because the payload cannot tell
the two apart — that is the whole defect:

    13  the `0.0` is a NULL        <- this ship
     3  the `0.0` is priced        <- data, untouched

The 13:  11 `* Election Winner` politics ladders — `Colorado Governor`, `Idaho
Governor`, `Pennsylvania Governor`, `Massachusetts Senate`, `New Jersey Senate`,
`Oregon Senate`, `Tennessee Senate`, `West Virginia Senate`, `Wyoming Senate`,
`MI-02 House`, `MO-01 House` — plus `Harry Potter and the Philosopher's Stone ·
Rotten Tomatoes` and `Ligue 1: Team Points` (72 rungs, **71** unpriced).

🪤 A RAW `futures_outcomes` COUNT IS NOT THE LADDER THE ROUTE SEES, and an
earlier draft of this file quoted one. The Colorado ladder has 13 rows, of which
ten are named `Option A`..`Option J` and are stripped as placeholders by
`clean_outcomes` before `_market_row`'s body runs. The route sees **three** —
`Democrat 96.7`, `Republican 3.8`, `Other` unpriced — and `outcome_count` serves
3. The `* House` pair is the opposite case: its unpriced rungs are named `A`..
`E`, bare single letters that carry no noun prefix, so nothing strips them and
the card printed `E 0%` beside a 98% leader. Both are pinned below.

The 3:  `Which movie has 2nd biggest opening weekend`, `Which movie has 3rd
biggest opening weekend`, and `When will Nick Adams be confirmed as Ambassador
of Malaysia?`. Nick Adams is the sharpest control in the set — it is the one
served row whose HEADLINE is `0%`, and its `Yes` leg is priced at a real zero,
so a fix that reads the rendered number instead of the column would "repair" it
and delete data. It must still headline `0%` after this ship.

⚠️ TWO CORRECTIONS TO THE ISSUE'S OWN FRAMING, both found by measuring rather
than by reading the population SQL:

1. "Fewer than three priced outcomes" understates the reach on the sibling.
   `entertainment._market_row` is called with `max_outcomes=8` on several
   sections (the politics twin is fixed at 3), so `Harry Potter` has SIX priced
   rungs and still showed two unpriced ones in an eight-slot rack.
2. In `politics` the sort key is `(expired, -prob)` evaluated with `or 0`, so an
   **unpriced live** rung outranks an **expired priced** one. The filter
   therefore has to run BEFORE the slice, not after it, or a NULL spends a slot
   a real price could have taken.

🔴 WHY DROP AND NOT DEMOTE — THE #3758 TENSION, ADDRESSED. `politics._market_row`
rules the opposite way for a neighbouring case: an expired rung is *"DEMOTED,
NEVER DROPPED"*. That ruling is about **expired** rungs and it states its own
reason — such a rung's *"price is real history"*. An unpriced rung has no price
and no history, so the reason does not reach it, and the two rules compose
rather than conflict: `test_an_expired_priced_rung_is_still_demoted_never_dropped`
below pins #3758 intact.

Fixtures use ``Decimal``, not ``float``: ``current_probability`` is
``Numeric(7, 6)``, so production hands these functions a ``Decimal`` — and
``Decimal("0.000000")`` is FALSY, which is exactly the trap that separates a
priced zero from a NULL.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.routes.entertainment import _market_row as _entertainment_row
from app.routes.politics import _market_row as _politics_row

NOW = datetime(2026, 9, 17, 23, 0, tzinfo=timezone.utc)


def _outcome(name, probability, *, outcome_id=1, rank=1):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        probability_change_24h=0,
        rank=rank,
    )


def _market(*, market_id=1, name="Will the event happen?", outcomes,
            llm_sport_category="politics", hook_description=None,
            hook_generated_at=None, hook_leader_at_generation=None,
            market_metadata=None):
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id="kxmock",
        source="kalshi",
        category="news",
        llm_sport_category=llm_sport_category,
        outcomes=outcomes,
        resolution_date=NOW + timedelta(days=30),
        updated_at=NOW,
        volume_24h=1000,
        image_url=None,
        hook_description=hook_description,
        hook_generated_at=hook_generated_at,
        hook_leader_at_generation=hook_leader_at_generation,
        market_metadata=market_metadata,
        status="open",
    )


def _row(builder, market, **kw):
    """Call either sibling through one signature.

    `politics._market_row` takes `now` as a REQUIRED keyword (gotcha #44);
    `entertainment._market_row` does not take it at all and takes
    `max_outcomes` instead.
    """
    if builder is _politics_row:
        return builder(market, now=NOW)
    return builder(market, **kw)


BOTH = (_politics_row, _entertainment_row)


# ---------------------------------------------------------------------------
# The specimens, reproduced from the served payload with their real shapes
# ---------------------------------------------------------------------------


# 🪤 FIXTURE NAMES ARE LOAD-BEARING, AND THE FILTER THAT EATS THEM IS NOT THE
# ONE YOU FIND FIRST. Both builders open with `_clean_outcomes`, which is
# `cross_source_matching.clean_outcomes` — NOT the same-named local in
# `weather.py` that `grep "def _clean_outcomes"` returns as the only hit. The
# route's regex is the wider of the two:
#
#     weather.py            ^(?:player|person|candidate|option|party)\s+[A-Z]{1,3}$
#     cross_source_matching ^(?:player|person|candidate|option|party|song|movie
#                             |show|app|team|ticker|choice)\s+[A-Z0-9]{1,3}$
#
# So `Candidate 0` is a PLACEHOLDER to this route and is stripped before any of
# this ship's code runs. The first draft of these fixtures used exactly that,
# and the strawman below then reported the pre-fix row as already clean — a
# guard that passed in both directions. Real names, deliberately.
def _colorado_governor():
    """`futures_outcomes` for market 113053, verbatim, in rank order.

    THE RAW ROW COUNT IS NOT THE ARITY THE ROUTE SEES, and quoting the former
    is how this file's first draft overstated the ladder. Thirteen rows, but ten
    are named `Option A`..`Option J` and `clean_outcomes` strips every one of
    them before `_market_row`'s body runs. The route sees THREE — `Democrat`,
    `Republican` and `Other` — which is why the served card carries exactly
    three rungs and `outcome_count` reads 3, not 13.

    `Other` is the one that matters: no price, no placeholder name, and so it
    reaches the reader as a confident `0%`. All ten of the Option rows are
    included here anyway, so the fixture exercises that filter rather than
    assuming it.
    """
    return _market(
        market_id=113053, name="Colorado Governor Election Winner",
        outcomes=[
            _outcome("Democrat", Decimal("0.967000"), outcome_id=1130530, rank=1),
            _outcome("Option B", None, outcome_id=1130531, rank=1),
            _outcome("Option D", None, outcome_id=1130532, rank=2),
            _outcome("Republican", Decimal("0.037500"), outcome_id=1130533, rank=2),
            _outcome("Option F", None, outcome_id=1130534, rank=3),
            _outcome("Option H", None, outcome_id=1130535, rank=4),
            _outcome("Option J", None, outcome_id=1130536, rank=5),
            _outcome("Option A", None, outcome_id=1130537, rank=6),
            _outcome("Option C", None, outcome_id=1130538, rank=7),
            _outcome("Option E", None, outcome_id=1130539, rank=8),
            _outcome("Option G", None, outcome_id=1130540, rank=9),
            _outcome("Option I", None, outcome_id=1130541, rank=10),
            _outcome("Other", None, outcome_id=1130542, rank=11),
        ],
    )


def _mi_02_house():
    """`futures_outcomes` for market 115102, verbatim — the ugliest of the 13.

    Its unpriced rungs are named `A`..`E`, bare single letters. Those carry no
    noun prefix, so `clean_outcomes`'s placeholder pattern does NOT strip them
    and all eight rows reach the body. The served card therefore printed

        Republican Party  98%   Democratic Party  0.8%   E  0%

    — a bare letter with a fabricated zero beside it.
    """
    return _market(
        market_id=115102, name="MI-02 House Election Winner",
        outcomes=[
            _outcome("Republican Party", Decimal("0.979500"),
                     outcome_id=1151020, rank=1),
            _outcome("Other", None, outcome_id=1151021, rank=2),
            _outcome("B", None, outcome_id=1151022, rank=3),
            _outcome("Democratic Party", Decimal("0.008000"),
                     outcome_id=1151023, rank=4),
            _outcome("D", None, outcome_id=1151024, rank=5),
            _outcome("A", None, outcome_id=1151025, rank=6),
            _outcome("C", None, outcome_id=1151026, rank=7),
            _outcome("E", None, outcome_id=1151027, rank=8),
        ],
    )


def _ligue_1_team_points():
    """71 of 72 rungs unpriced, served into an EIGHT-slot rack.

    Names are spelled out rather than `Club 5` for the same reason as above —
    `team|player|option|…` + one to three alphanumerics is a placeholder to this
    route and would never reach the code under test.
    """
    outcomes = [_outcome("Paris Saint-Germain", Decimal("0.310000"),
                         outcome_id=5777428_0, rank=1)]
    outcomes += [
        _outcome(f"Ligue 1 club number {i}", None,
                 outcome_id=5777429_0 + i, rank=2 + i)
        for i in range(71)
    ]
    return _market(
        market_id=57774280, name="Ligue 1: Team Points",
        llm_sport_category="entertainment", outcomes=outcomes,
    )


# ===========================================================================
# THE SHIP — red before the fix, on BOTH siblings
# ===========================================================================


class TestTheFixturesSurviveThePlaceholderFilter:
    """Guards the guards — see the note above `_colorado_governor`.

    Every rung in this module must reach `_market_row`'s body. A name matching
    `clean_outcomes`'s placeholder pattern is stripped one line in, which makes
    the pre-fix row look already-clean and turns the strawman green. That
    happened once while this file was being written; this is what stops it
    happening silently to whoever edits a fixture next.
    """

    def test_the_rungs_this_ship_is_about_survive_the_placeholder_filter(self):
        """`Other`, `B`..`E` and the spelled-out club names must reach the body.

        If one of these were strippable the pre-fix row would already look
        clean and the strawman would go green for the wrong reason.
        """
        from app.utils.cross_source_matching import GARBAGE_OUTCOME_RE

        for name in ("Other", "A", "B", "E", "Ligue 1 club number 7",
                     "Democrat", "Republican Party", "Paris Saint-Germain"):
            assert not GARBAGE_OUTCOME_RE.match(name), name

    def test_the_option_rows_ARE_stripped_so_the_arity_is_three_not_thirteen(self):
        """The other half of the same fact, and the correction to my own read.

        `Option A`..`Option J` are placeholders to this route. A census that
        counts `futures_outcomes` rows says the Colorado ladder has 13 rungs
        with 11 unpriced; the route sees 3 with 1 unpriced, and 3 is what the
        served card and `outcome_count` report.
        """
        from app.utils.cross_source_matching import GARBAGE_OUTCOME_RE

        raw = _colorado_governor().outcomes
        assert len(raw) == 13
        survive = [o for o in raw if not GARBAGE_OUTCOME_RE.match(o.name or "")]
        assert [o.name for o in survive] == ["Democrat", "Republican", "Other"]
        assert _row(_politics_row, _colorado_governor())["outcome_count"] == 3

    def test_the_specimens_keep_their_measured_arity(self):
        assert len(_mi_02_house().outcomes) == 8
        assert len(_ligue_1_team_points().outcomes) == 72


class TestAnUnpricedRungLeavesTheServedSlice:
    def test_the_colorado_specimen_stops_printing_other_at_zero(self):
        """Photographed at 390px on 2026-09-17: `Democrat 98% / Republican 2% /
        Other 0%`, twice on one screen (Massachusetts and Oregon, same shape).
        """
        row = _row(_politics_row, _colorado_governor())
        rungs = {o["name"]: o["prob"] for o in row["top_outcomes"]}
        assert rungs == {"Democrat": 96.7, "Republican": 3.8}
        assert row["prob"] == 96.7
        assert row["outcome_count"] == 3

    def test_the_mi_02_specimen_stops_printing_a_bare_letter_at_zero(self):
        """`Republican Party 98% · Democratic Party 0.8% · E 0%` — the served
        card. `E` is an unpriced rung whose name is one character."""
        row = _row(_politics_row, _mi_02_house())
        rungs = {o["name"]: o["prob"] for o in row["top_outcomes"]}
        assert rungs == {"Republican Party": 98.0, "Democratic Party": 0.8}
        assert row["outcome_count"] == 8

    def test_no_served_rung_is_ever_a_null_on_either_sibling(self):
        """The ship's sentence, stated over both builders at once."""
        m = _market(
            market_id=1,
            outcomes=[
                _outcome("A", Decimal("0.600000"), outcome_id=1, rank=1),
                _outcome("B", None, outcome_id=2, rank=2),
                _outcome("C", None, outcome_id=3, rank=3),
            ],
        )
        for builder in BOTH:
            rungs = [o["name"] for o in _row(builder, m)["top_outcomes"]]
            assert rungs == ["A"], builder.__module__

    def test_an_eight_slot_rack_shows_only_what_is_priced(self):
        """`max_outcomes=8` is why the issue's "<3 priced" population was short.

        `Ligue 1: Team Points` has ONE priced rung and 71 NULLs; the eight-slot
        sections served seven fabricated zeros beneath the leader.
        """
        row = _entertainment_row(_ligue_1_team_points(), 8)
        assert [o["name"] for o in row["top_outcomes"]] == ["Paris Saint-Germain"]
        assert row["outcome_count"] == 72

    def test_a_null_no_longer_spends_a_slot_an_expired_price_could_take(self):
        """Correction 2, and the reason the filter runs BEFORE the slice.

        The key is `(expired, -prob)` with `or 0`, so an unpriced LIVE rung
        sorted ahead of an expired PRICED one. With three slots, two NULLs used
        to push a real (if expired) price off the card entirely.
        """
        m = _market(
            market_id=2,
            outcomes=[
                _outcome("Before Apr 1, 2026", Decimal("0.030000"),
                         outcome_id=21, rank=1),
                _outcome("Before Jul 1, 2026", Decimal("0.015000"),
                         outcome_id=22, rank=2),
                _outcome("Before Jan 1, 2029", None, outcome_id=23, rank=3),
                _outcome("Before Jan 1, 2030", None, outcome_id=24, rank=4),
            ],
        )
        rungs = [o["name"] for o in _row(_politics_row, m)["top_outcomes"]]
        assert rungs == ["Before Apr 1, 2026", "Before Jul 1, 2026"], (
            "a NULL took a slot from a priced rung — the filter ran after the "
            "slice instead of before it"
        )


# ===========================================================================
# CONTROLS — a priced zero is DATA and must survive every one of these
# ===========================================================================


class TestAPricedZeroIsDataAndIsUntouched:
    def test_the_nick_adams_specimen_still_headlines_a_real_zero(self):
        """The one served row that HEADLINES 0%, and it is correct to.

        Three rungs: `Yes` priced at a real 0, and two dated rungs that #3758
        demotes. A fix that keyed on the rendered `0.0` instead of on the column
        would silently delete this — which is why it is a test and not a note.
        """
        m = _market(
            market_id=109434,
            name="When will Nick Adams be confirmed as Ambassador of Malaysia?",
            outcomes=[
                _outcome("Yes", Decimal("0.000000"), outcome_id=1094340, rank=1),
                _outcome("Before Apr 1, 2026", Decimal("0.030000"),
                         outcome_id=1094341, rank=2),
                _outcome("Before Jul 1, 2026", Decimal("0.000000"),
                         outcome_id=1094342, rank=3),
            ],
        )
        row = _row(_politics_row, m)
        rungs = {o["name"]: o["prob"] for o in row["top_outcomes"]}
        assert rungs["Yes"] == 0.0
        assert rungs["Before Jul 1, 2026"] == 0.0
        assert row["prob"] == 0.0
        assert row["outcome_count"] == 3

    def test_a_priced_zero_rung_survives_beside_a_dropped_null(self):
        """The discrimination, in one market: same rendered number, two fates."""
        m = _market(
            market_id=3,
            outcomes=[
                _outcome("Leader", Decimal("0.700000"), outcome_id=31, rank=1),
                _outcome("Priced at zero", Decimal("0.000000"),
                         outcome_id=32, rank=2),
                _outcome("No price at all", None, outcome_id=33, rank=3),
            ],
        )
        for builder in BOTH:
            rungs = {o["name"]: o["prob"] for o in _row(builder, m)["top_outcomes"]}
            assert rungs == {"Leader": 70.0, "Priced at zero": 0.0}, builder.__module__

    def test_an_expired_priced_rung_is_still_demoted_never_dropped(self):
        """#3758 intact — the tension this ship had to address, pinned.

        Every rung here is expired and priced. #3758 rules that such a ladder is
        "unchanged rather than emptied", and this ship must not have widened
        into it: drop is for rungs with NO price, demote is for rungs whose
        price is real history.
        """
        m = _market(
            market_id=4,
            outcomes=[
                _outcome("Before Apr 1, 2026", Decimal("0.030000"),
                         outcome_id=41, rank=1),
                _outcome("Before Jul 1, 2026", Decimal("0.015000"),
                         outcome_id=42, rank=2),
            ],
        )
        row = _row(_politics_row, m)
        assert len(row["top_outcomes"]) == 2
        assert row["prob"] == 3.0


class TestTheLadderArityAndTheRefusalAreUnmoved:
    def test_outcome_count_still_counts_every_rung_on_both_siblings(self):
        """The filter drops rungs from the SLICE, never from the ladder.

        Anything downstream reading `outcome_count` — the kind classifier on the
        sibling among them — must see the same arity it saw yesterday.
        """
        m = _market(
            market_id=5,
            outcomes=[
                _outcome("A", Decimal("0.500000"), outcome_id=51, rank=1),
                _outcome("B", None, outcome_id=52, rank=2),
                _outcome("C", None, outcome_id=53, rank=3),
            ],
        )
        for builder in BOTH:
            assert _row(builder, m)["outcome_count"] == 3, builder.__module__

    def test_a_wholly_unpriced_market_is_still_refused_not_emptied(self):
        """#6235's refusal is what makes `priced` provably non-empty.

        It is NOT subsumed by this ship. Without it the filter would produce an
        empty slice and `top_outcomes[0]` would raise at request time — so this
        pins the two as a pair, in the order they have to hold.
        """
        m = _market(
            market_id=6,
            outcomes=[
                _outcome("A", None, outcome_id=61, rank=1),
                _outcome("B", None, outcome_id=62, rank=2),
            ],
        )
        for builder in BOTH:
            assert _row(builder, m) is None, builder.__module__

    def test_the_served_slice_is_never_empty_when_a_row_is_returned(self):
        """The sentinel `if top_outcomes else 0` was REMOVED, not guarded.

        A returned row always has at least one rung and its headline is that
        rung's real price — a `0` from an empty-list fallback would be the very
        thing this ship exists to stop printing.
        """
        m = _market(
            market_id=7,
            outcomes=[
                _outcome("Only priced rung", Decimal("0.010000"),
                         outcome_id=71, rank=9),
                _outcome("N", None, outcome_id=72, rank=1),
            ],
        )
        for builder in BOTH:
            row = _row(builder, m)
            assert row["top_outcomes"], builder.__module__
            assert row["prob"] == row["top_outcomes"][0]["prob"] == 1.0


class TestTheSiblingHeadlineAndHookReadTheSameObject:
    def test_the_entertainment_headline_is_the_priced_leader_not_a_null(self):
        """`priced[0]`, not `outcomes[0]`.

        The two part when every priced rung is a zero: `or 0` made a NULL tie
        with a real zero and the stable sort handed the headline to whichever
        rung came first in the ladder. Here the NULL is first.
        """
        m = _market(
            market_id=13,
            llm_sport_category="entertainment",
            outcomes=[
                _outcome("Unpriced", None, outcome_id=131, rank=1),
                _outcome("Priced at zero", Decimal("0.000000"),
                         outcome_id=132, rank=2),
            ],
        )
        row = _entertainment_row(m)
        assert row["prob"] == 0.0
        assert [o["name"] for o in row["top_outcomes"]] == ["Priced at zero"]

    def test_the_hook_staleness_gate_reads_the_leader_the_card_shows(self):
        """One object for the number, the rungs and the hook's leader.

        The gate used to read `outcomes[0]`, whose own comment justified it with
        "this route withholds no prices, so there is no null to sink" — the
        premise this ship changes. A hook generated against the real leader must
        survive; if the gate were still reading the NULL rung it would see a
        different leader, clause 2 would fire, and the hook would be dropped.

        🪤 `market_metadata` CARRIES THE POLICY VERSION OR THIS PROVES NOTHING.
        `is_hook_stale` checks `hook_policy_version` FIRST (#5461/#5926) and
        returns True for an absent key, so a fixture with `market_metadata=None`
        is suppressed before the leader clause is ever reached and the test
        passes for the wrong reason whichever object the gate reads. The first
        draft of this test did exactly that.

        `hook_generated_at` is read against the REAL clock — `_market_row` does
        not pass `now` — so it is anchored to now, not to this module's frozen
        `NOW` (gotcha #44).
        """
        m = _market(
            market_id=14,
            llm_sport_category="entertainment",
            hook_description="A real hook about the leader.",
            hook_generated_at=datetime.now(timezone.utc),
            hook_leader_at_generation="Priced leader",
            market_metadata={"hook_policy_version": 2},
            outcomes=[
                _outcome("Unpriced", None, outcome_id=141, rank=1),
                _outcome("Priced leader", Decimal("0.550000"),
                         outcome_id=142, rank=2),
            ],
        )
        row = _entertainment_row(m)
        assert row["top_outcomes"][0]["name"] == "Priced leader"
        assert row["hook"] == "A real hook about the leader."

    def test_the_hook_gate_still_drops_a_hook_whose_leader_really_changed(self):
        """The other side of the same clause, so the test above is not vacuous.

        Identical fixture but the hook was written when someone else led. If
        this passed too, the assertion above would be proving only that clause 2
        never fires here.
        """
        m = _market(
            market_id=15,
            llm_sport_category="entertainment",
            hook_description="A hook about last week's leader.",
            hook_generated_at=datetime.now(timezone.utc),
            hook_leader_at_generation="Someone else entirely",
            market_metadata={"hook_policy_version": 2},
            outcomes=[
                _outcome("Unpriced", None, outcome_id=151, rank=1),
                _outcome("Priced leader", Decimal("0.550000"),
                         outcome_id=152, rank=2),
            ],
        )
        assert _entertainment_row(m)["hook"] is None
