"""#6235 — /politics and /entertainment must not print a confident 0% for a
market nobody has priced.

live/245 shopped `/politics` at 390px on 2026-09-14 and photographed three
consecutive cards reading `North Carolina Senate election: Roy Cooper vote
percent · LEADER At least 46% · 0%`; the Congressional section was 10 of 10.

🔴 THE REPORTED MECHANISM IS NOT THE MECHANISM. The intake note named
``_leader_prob``'s ``... if outcomes and outcomes[0].current_probability else
None`` and reasoned that **0.0 is falsy**, so a zero leader becomes ``None`` and
``is_probability_extreme(None)`` keeps it. That line is real and that reasoning
is sound, but it is **inert on this population**: a census of every open market
in these categories found **no market whose leader is exactly 0.0** —

    politics       exact_zero 0   under2 44   over98 711   all_priced 5241
    entertainment  exact_zero 0   under2 18   over98 419   all_priced 1383

The specimens' ``current_probability`` is **NULL**, not ``0.0``. Read back by
id, `KXVOTEGENERAL-SENATEID-26JRIS` carries ten rungs and every one of them is
NULL. ``_leader_prob`` therefore returns ``None`` **correctly** (``float(None)``
would raise), ``is_probability_extreme(None)`` is ``False`` **by contract**, and
the one-line ``is not None`` repair would change nothing a reader can see. The
0% is fabricated one level down, by ``_market_row``'s ``float(o.current_
probability or 0)``.

WHERE THE FIX COMES FROM. This is **#2950's refusal**, ported from
``economics._market_row``, whose docstring states the rule: *a priced zero is
DATA (the market says no); a NULL is the ABSENCE of data, and only the second is
grounds for refusing the row.* #2950's own census (see
``test_route_economics_empty_market_zero_2950.py``) cleared the two siblings —

    politics.py       _market_row   `if not outcomes: return None`   OK
    entertainment.py  _market_row   `if not outcomes: return None`   OK

— and that reading was right about the arm it named and blind to the other one.
Those lines refuse a market with **no outcomes**; neither refuses a market whose
outcomes carry **no price**. #2950 recorded its own all-NULL arm as *"guarded,
currently inert — 0 of 2269"*, so on the day it shipped the difference between
the two arms was invisible. It is not invisible now: that guard is live and
catching 23 economics markets, while the unported siblings leak.

MEASURED ON PRODUCTION 2026-09-14, the same minute, over the three dashboards
that share this row shape. The already-fixed sibling is the control:

    /api/economics       0 of  55 rows printing 0%   <- #2950 is here
    /api/politics       32 of  68 rows printing 0%
    /api/entertainment  20 of 112 rows printing 0%

⚠️ THE ZEROS ARE NOT A BACKFILL HOLE. Before withdrawing a card it is worth
knowing whether the price merely failed to denormalise onto the column — that
would make the 0% an alarm and this fix the deletion of it. It did not: of the
424 open markets in these categories with no priced outcome, **420 have never
held a single ``futures_odds_snapshots`` row**. There is no price to recover.
A market that gets its first price returns on the next build.

WHY THE ZEROS CLUSTER. ``build_section`` sorts ``-abs(prob - 50)`` — most
extreme first — so a fabricated 0.0 is not merely admitted, it is promoted to
the top of its section. That is why the Congressional section was 10 of 10 and
not 10 of 893: the sort and the extremeness gate were pulling opposite ways and
the fabricated value won. Backfill is ample (893 congressional candidates for
10 slots), so the sections refill rather than empty.

NOT IN SCOPE HERE — SHIPPED SINCE, AS #6255. A **partially** priced ladder could
still put an unpriced rung in its top three and print `0%` beside it (measured:
544 politics + 14 entertainment markets have fewer than 3 priced outcomes). That
is the same sentence one level down, and `_market_row`'s #3758 comment rules
that a rung is *"DEMOTED, NEVER DROPPED ... a ladder whose rungs have ALL expired
is unchanged rather than emptied"*, so whether an unpriced rung is dropped,
demoted or rendered as "—" was a judgement that belonged with its own issue
rather than being a silent widening here.

#6255 took it and chose DROP, on the ground that #3758's ruling is about
**expired** rungs and its stated reason — that such a rung's *"price is real
history"* — does not reach a rung that has no price at all. The control below
was written naming itself as the test that ship must rewrite; it has been
rewritten and now pins the boundary from the other side. Expired-and-priced
rungs are still demoted and still never dropped.

Fixtures use ``Decimal``, not ``float``: ``current_probability`` is
``Numeric(7, 6)``, so production hands these functions a ``Decimal`` — and
``Decimal("0.000000")`` is FALSY, which is the whole trap. A float fixture would
not exercise it.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.routes.entertainment import _market_row as _entertainment_row
from app.routes.politics import _market_row as _politics_row

NOW = datetime(2026, 9, 14, 23, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Mock builders — same shape as tests/integration/test_route_politics.py
# ---------------------------------------------------------------------------


class _MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def unique(self):
        return self


class _MockResult:
    def __init__(self, items):
        self._scalars = _MockScalars(items)

    def scalars(self):
        return self._scalars

    def all(self):
        # A column select is consumed through .all(), an entity select through
        # .scalars().all() — the politics snapshot query is the former since
        # LAT-P023 (#1607). Both halves, or the route 500s.
        return self._scalars.all()


def _outcome(name, probability, *, outcome_id=1, rank=1):
    # `is_winner` / `resolution_source`: #8083 routed the themed dashboards
    # through `_withheld_price_outcome_ids`, whose arms read the settlement
    # columns a real `FuturesOutcome` always carries.
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        probability_change_24h=0,
        rank=rank,
        is_winner=None,
        resolution_source=None,
        # #8102: #8011's unobserved-board arm reads this column unguarded, the
        # way a real `FuturesOutcome` always carries it. NOW keeps the arm
        # withholding nothing, so these contracts test what they were written for.
        last_updated=datetime.now(timezone.utc),
    )


def _market(
    *,
    market_id=1,
    name="Will the event happen?",
    external_id="kxmock",
    llm_sport_category="politics",
    outcomes,
):
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id,
        source="kalshi",
        category="news",
        llm_sport_category=llm_sport_category,
        outcomes=outcomes,
        resolution_date=NOW + timedelta(days=30),
        updated_at=NOW,
        volume_24h=1000,
        image_url=None,
        hook_description=None,
        status="open",
    )


def _row(builder, market):
    """Call either sibling's row builder through one signature.

    `politics._market_row` takes `now` as a REQUIRED keyword (gotcha #44);
    `entertainment._market_row` does not take it at all.
    """
    if builder is _politics_row:
        return builder(market, now=NOW)
    return builder(market)


# The specimen from the shop, reproduced with its real id, real name and real
# emptiness: ten rungs, ten NULLs, never a single snapshot.
def _idaho_senate_vote_percent():
    return _market(
        market_id=60768795,
        name="Idaho Senate election: Jim Risch vote percent",
        external_id="KXVOTEGENERAL-SENATEID-26JRIS",
        outcomes=[
            _outcome(f"At least {pct}%", None, outcome_id=60768795_00 + i, rank=i + 1)
            for i, pct in enumerate(range(50, 68, 2))
        ],
    )


# An entertainment specimen from the same payload read.
def _youtube_weekly_top_song():
    return _market(
        market_id=60779679,
        name="YouTube Charts: Weekly Top Song USA",
        external_id="KXYOUTUBETOPSONG-26SEP18",
        llm_sport_category="entertainment",
        outcomes=[
            _outcome("Taylor Swift", None, outcome_id=6077967_90, rank=1),
            _outcome("Morgan Wallen", None, outcome_id=6077967_91, rank=2),
            _outcome("YoungBoy Never Broke Again", None, outcome_id=6077967_92, rank=3),
        ],
    )


# ===========================================================================
# THE SHIP — red on the parent, for BOTH siblings
# ===========================================================================


class TestAnUnpricedMarketIsNotARow:
    def test_the_photographed_politics_specimen_is_refused(self):
        """Master returns a row whose `prob` is 0.0 under a real question."""
        assert _politics_row(_idaho_senate_vote_percent(), now=NOW) is None

    def test_the_entertainment_specimen_is_refused(self):
        assert _entertainment_row(_youtube_weekly_top_song()) is None

    def test_both_siblings_refuse_an_all_null_market(self):
        """Stated over both builders in one loop, so neither can be repaired
        alone the way #2950 was."""
        for builder in (_politics_row, _entertainment_row):
            m = _market(
                market_id=2,
                outcomes=[
                    _outcome("Yes", None, outcome_id=20, rank=1),
                    _outcome("No", None, outcome_id=21, rank=2),
                ],
            )
            assert _row(builder, m) is None, f"{builder.__module__} served a row"

    def test_no_returned_row_carries_a_probability_no_outcome_holds(self):
        """The property, not the value: whatever comes back, its `prob` and
        every rung it prints came from an outcome that had a price.

        Stated this way so it survives the next rewrite of either builder —
        there is no fabricated value left that could pass for a measurement.
        """
        for builder in (_politics_row, _entertainment_row):
            for outcomes in (
                [_outcome("Yes", None, outcome_id=30)],
                [
                    _outcome("Yes", None, outcome_id=31),
                    _outcome("No", None, outcome_id=32),
                ],
                [
                    _outcome(f"At least {p}", None, outcome_id=33_00 + p)
                    for p in range(5)
                ],
            ):
                m = _market(market_id=3, outcomes=outcomes)
                row = _row(builder, m)
                assert row is None, (
                    f"{builder.__module__} turned {len(outcomes)} unpriced "
                    f"outcome(s) into {row!r}"
                )

    def test_a_single_priced_rung_is_enough_to_keep_the_ladder(self):
        """The refusal is `no price ANYWHERE`, not `the leader has no price`.

        The boundary matters: the population this ship withdraws is markets
        that have never traded, and a ladder with one live rung has traded.
        """
        for builder in (_politics_row, _entertainment_row):
            m = _market(
                market_id=4,
                outcomes=[
                    _outcome("At least 50%", None, outcome_id=40, rank=1),
                    _outcome("At least 52%", Decimal("0.310000"), outcome_id=41, rank=2),
                    _outcome("At least 54%", None, outcome_id=42, rank=3),
                ],
            )
            row = _row(builder, m)
            assert row is not None, f"{builder.__module__} dropped a traded ladder"
            assert row["prob"] == 31.0


class TestTheRoutesDoNotServeTheZero:
    """Asserted on the served body, not the helper.

    A helper-only guard stays green if someone deletes the call site.
    """

    async def test_politics_does_not_serve_the_unpriced_market(self, client, mock_db):
        mock_db.execute.return_value = _MockResult([_idaho_senate_vote_percent()])
        body = (await client.get("/api/politics")).json()

        assert 60768795 not in _all_market_ids(body), (
            "the unpriced market reached the payload; "
            f"rows served: {_all_rows(body)!r}"
        )

    async def test_no_politics_row_anywhere_reads_zero(self, client, mock_db):
        """The user-visible claim, stated over the whole document — every
        section, so a row that moves between themes cannot escape it."""
        mock_db.execute.return_value = _MockResult([_idaho_senate_vote_percent()])
        body = (await client.get("/api/politics")).json()

        zeros = [r for r in _all_rows(body) if r.get("prob") == 0]
        assert zeros == [], f"rows printing a confident 0%: {zeros!r}"

    async def test_entertainment_does_not_serve_the_unpriced_market(
        self, client, mock_db
    ):
        mock_db.execute.return_value = _MockResult([_youtube_weekly_top_song()])
        body = (await client.get("/api/entertainment")).json()

        assert 60779679 not in _all_market_ids(body), (
            "the unpriced market reached the payload; "
            f"rows served: {_all_rows(body)!r}"
        )

    async def test_no_entertainment_row_anywhere_reads_zero(self, client, mock_db):
        mock_db.execute.return_value = _MockResult([_youtube_weekly_top_song()])
        body = (await client.get("/api/entertainment")).json()

        zeros = [r for r in _all_rows(body) if r.get("prob") == 0]
        assert zeros == [], f"rows printing a confident 0%: {zeros!r}"


# ===========================================================================
# CONTROLS — green on the parent too. These are what stop the fix from
# becoming "drop anything that computes to zero".
# ===========================================================================


class TestControls:
    def test_CONTROL_a_normal_market_still_renders(self):
        for builder in (_politics_row, _entertainment_row):
            m = _market(
                market_id=5,
                outcomes=[
                    _outcome("Yes", Decimal("0.550000"), outcome_id=50, rank=1),
                    _outcome("No", Decimal("0.450000"), outcome_id=51, rank=2),
                ],
            )
            row = _row(builder, m)
            assert row is not None and row["prob"] == 55.0

    def test_CONTROL_a_priced_zero_is_data_and_still_renders(self):
        """`Decimal("0.000000")` is FALSY, which is why `or 0` cannot tell it
        from a NULL. A market that says "no" is ANSWERING the question; it keeps
        its row. This is the control the intake note's proposed `is not None`
        one-liner would have needed and the reason that line is not the fix."""
        for builder in (_politics_row, _entertainment_row):
            m = _market(
                market_id=6,
                outcomes=[
                    _outcome("Yes", Decimal("0.000000"), outcome_id=60, rank=1),
                    _outcome("No", Decimal("1.000000"), outcome_id=61, rank=2),
                ],
            )
            row = _row(builder, m)
            assert row is not None and row["prob"] == 100.0

    def test_CONTROL_an_all_zero_PRICED_market_still_renders_its_zero(self):
        """🔴 THE LITERAL 0.0 THE INTAKE NOTE ASKED FOR, asserted in the
        opposite direction to the one it expected.

        Every side priced, every side at zero. Nothing is missing — the book is
        empty of belief — so the row stays and reads 0%. A market with NO price
        and a market priced AT zero render identically today; this is the case
        that proves the fix tells them apart, and the case a naive "refuse if
        prob == 0" would delete.
        """
        for builder in (_politics_row, _entertainment_row):
            m = _market(
                market_id=7,
                outcomes=[
                    _outcome("Yes", Decimal("0.000000"), outcome_id=70, rank=1),
                    _outcome("No", Decimal("0.000000"), outcome_id=71, rank=2),
                ],
            )
            row = _row(builder, m)
            assert row is not None, (
                f"{builder.__module__} dropped a PRICED zero — the fix has "
                "overreached from 'no data' to 'no belief'"
            )
            assert row["prob"] == 0.0

    def test_an_unpriced_rung_inside_a_traded_ladder_is_now_dropped_6255(self):
        """REWRITTEN BY #6255 — deliberately, which is what this control asked.

        Its previous body asserted `rungs["At least 42%"] == 0.0` and said so in
        its own docstring: *"When that issue ships, this control is the test it
        must come back and rewrite — deliberately, not by accident."* This is
        that rewrite. The assertion is INVERTED rather than deleted, so the
        scope boundary #6235 drew is still pinned — from the other side.

        #6235 withdraws a market nobody has priced; #6255 carries the same
        sentence one level down and withdraws a RUNG nobody has priced. The
        leader and its price are unchanged, which is the point: this drops an
        absence, never data.

        The full guard set for the rung-level half lives in
        `test_route_category_unpriced_rung_6255.py`.
        """
        m = _market(
            market_id=8,
            outcomes=[
                _outcome("At least 40%", Decimal("0.720000"), outcome_id=80, rank=1),
                _outcome("At least 42%", None, outcome_id=81, rank=2),
            ],
        )
        for builder in (_politics_row, _entertainment_row):
            row = _row(builder, m)
            assert row is not None and row["prob"] == 72.0
            rungs = {o["name"]: o["prob"] for o in row["top_outcomes"]}
            assert "At least 42%" not in rungs, (
                "an unpriced rung is back in the served slice; #6255 drops it "
                "rather than printing the NULL as 0%"
            )
            assert rungs == {"At least 40%": 72.0}
            assert row["outcome_count"] == 2, (
                "the rung left the SLICE, not the ladder — arity must not move"
            )

    def test_CONTROL_outcome_count_still_counts_every_rung(self):
        """The refusal drops ROWS, never rungs — a kept market's arity is
        unchanged, so nothing downstream that reads `outcome_count` shifts."""
        m = _market(
            market_id=9,
            outcomes=[
                _outcome("At least 40%", Decimal("0.720000"), outcome_id=90, rank=1),
                _outcome("At least 42%", None, outcome_id=91, rank=2),
                _outcome("At least 44%", None, outcome_id=92, rank=3),
            ],
        )
        for builder in (_politics_row, _entertainment_row):
            assert _row(builder, m)["outcome_count"] == 3

    def test_CONTROL_a_market_with_no_outcomes_is_still_refused(self):
        """The arm #2950's census DID clear. Untouched, and it must stay."""
        for builder in (_politics_row, _entertainment_row):
            assert _row(builder, _market(market_id=10, outcomes=[])) is None

    def test_CONTROL_the_economics_sibling_is_unchanged(self):
        """The control surface for the whole ship. `/api/economics` served 0 of
        55 zero rows BEFORE this change because #2950 already landed there; this
        ship must not have touched it in either direction."""
        from app.routes.economics import _market_row as _economics_row

        unpriced = _market(
            market_id=11,
            llm_sport_category="economics",
            outcomes=[_outcome("Yes", None, outcome_id=110, rank=1)],
        )
        assert _economics_row(unpriced) is None

        priced_zero = _market(
            market_id=12,
            llm_sport_category="economics",
            outcomes=[
                _outcome("Yes", Decimal("0.000000"), outcome_id=120, rank=1),
                _outcome("No", Decimal("0.000000"), outcome_id=121, rank=2),
            ],
        )
        row = _economics_row(priced_zero)
        assert row is not None and row["prob"] == 0.0


# ---------------------------------------------------------------------------
# Extractors — they report their own yield rather than returning quietly.
# ---------------------------------------------------------------------------


def _all_rows(body: dict) -> list[dict]:
    """Every market-shaped row anywhere in the payload.

    A row is `{q, prob, ...}`. Walking the whole document rather than naming a
    theme means a row that moves between sections cannot escape the assertion.
    """
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            if "q" in node and "prob" in node:
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(body)
    return found


def _all_market_ids(body: dict) -> set:
    return {r["market_id"] for r in _all_rows(body) if r.get("market_id") is not None}
