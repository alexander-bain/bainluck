"""#7505's companion leg, over its whole life — not just the write that made it.

CERT-3251 blocked `e970ed0cd` for a reason worth writing down at the top of the
file that answers it. The ingest half was right: on a sole-moneyline Polymarket
event the venue names both sides, we stored one, and a reader met "Davis Cup:
Liam Draxl vs. Quentin Halys — Liam Draxl 50%" — two names in the title, one
number underneath. `_parent_outcome_data` now writes the partner as
`{condition_id}_side1`, priced `1 - prob` over `complementary_book(...)`.

What the ship's own reasoning never asked was what happens to that row NEXT. It
checked four consumers — serve-time dedup, history name-routing, leg retirement,
the upsert conflict key — and concluded "all consumers check out". It did not
check the ones that make a row a living thing rather than a stored one:

  * the **price refresh**, which re-quotes a leg every cycle,
  * **history / token resolution**, which draws its chart and keeps its CLOB
    token warm,
  * **settlement**, which decides whether it won.

Every one of those keys on `_yes` / `_no` independently, so a new suffix is
invisible to all three. The failures are not symmetrical and only the first is
cosmetic: a stale companion makes a visible pair stop summing to 1; an unresolved
one draws an empty chart; an ungraded one is a settled question with no result,
and a WRONGLY graded one is an affirmative lie about who won.

🔴 THE ONE THING THAT MUST NOT LEARN THE SUFFIX. `duplicate_condition_outcomes`
and `winner_field_coherence` drop a suffixed leg whose BARE twin is on the same
market — which is exactly this pair's shape. Teaching them `_side1` would filter
the companion out of every reader surface at serve time, and the fix would go
inert on precisely its own population. `_side1` is outside `BINARY_LEG_SUFFIXES`
deliberately; `TestTheServeTimeDedupStillReadsTheCompanionAsARung` below is the
control that keeps it that way.

🔴 AND THE SEAM THAT WAS MAPPED BUT NOT BUILT, so nobody builds it twice.
`tasks/clob_resolve.py` hardcodes the same pair — `_suffix_of` knows two
suffixes and `map_clob_to_outcome` refuses unless `set(by_suf) == {"_yes",
"_no"}`. Teaching it `(bare, _side1)` would have been INERT: that rail's cohort
is `fm.source='polymarket' AND fm.status='resolved' AND fm.external_id LIKE
'0x%'`, and a sole-moneyline parent's `external_id` is the Gamma EVENT id, a
bare integer. Measured on production 2026-09-21 over Polymarket `% vs%` markets
holding exactly one leg: **17,837 are not hex-keyed and 4 are.** So the rail
cannot see 99.98% of this population, and the settlement repair belongs where
the population actually arrives — `backfill_winners`, seam 4 below, whose bare
branch these markets reach through `condition_id == event_id and
len(api_markets) == 1`. Widening a retrieval rule the fetch gate never asks is
the failure this note exists to prevent.

Every arm here is an EXECUTING control, not a shape assertion: each drives the
real function over a companion pair and reads what it did. Red-first against the
four app files reverted: 8 ship arms fail, 13 controls pass.
"""

import pytest

# `import app.tasks.backfill_winners as bw`, NOT `from app.tasks import
# backfill_winners`: the package exports the Celery TASK under that attribute
# name, and a task object has no `get_task_session` for the settlement arms
# below to patch.
import app.tasks.backfill_winners as bw
from app.tasks import futures_price_refresh as fpr
from tests.test_futures_price_refresh_counts_declines_5869 import _WriteSession

# Marked per class rather than per module: most arms here are synchronous and a
# module-level asyncio mark makes pytest-asyncio warn on every one of them.


#: The Davis Cup rubber #7505 was filed for, at the numbers the venue published
#: (Gamma `/events/1045485`, `daviscup-draxl-halys-2026-09-19`, read 2026-09-21:
#: ONE market, `outcomes: ["Liam Draxl", "Quentin Halys"]`, prices 0.5 / 0.5).
#: Moved off the coin flip here on purpose — a 50/50 pair is the one input where
#: writing the companion at the WRONG side's price is invisible, so every number
#: below is 0.70 / 0.30.
CID = "0xdraxlhalys"
YES_P, NO_P = 0.70, 0.30


def _item(prob=YES_P, bid=0.68, ask=0.72):
    """One fetched item, exactly as `_refresh_polymarket_prices` builds it.

    The `no` sub-dict is the fetcher's own derivation — `1 - accepted` over
    `complementary_book(bid, ask)` — and is passed rather than re-derived here,
    because the whole of seam 1 is that the companion must be priced by the
    SAME producer as the decomposed `_no` leg and not by a second one.
    """
    from app.tasks.polymarket import complementary_book

    no_bid, no_ask, no_last = complementary_book(bid, ask, None)
    return {
        "external_id": CID,
        "probability": prob,
        "yes_bid": bid,
        "yes_ask": ask,
        "last_price": None,
        "no": {
            "probability": 1.0 - prob,
            "yes_bid": no_bid,
            "yes_ask": no_ask,
            "last_price": no_last,
        },
    }


class _Outcome:
    """The three fields every seam below reads off a stored leg."""

    def __init__(self, external_id, name, outcome_id=12):
        self.id = outcome_id
        self.external_id = external_id
        self.name = name


class _RecordingSession(_WriteSession):
    """`_WriteSession`, plus WHICH number reached WHICH row.

    The sibling harness counts updates, which answers "did the writer fire" and
    not "did it pair the sides correctly" — and on this seam those are different
    questions with the same count. The bound values are read off the compiled
    `UPDATE` rather than intercepted anywhere the test controls, so a change to
    how `_write_prices` composes its statement shows up here as a failure
    instead of being silently accommodated.
    """

    def __init__(self, rows):
        super().__init__(rows=rows)
        self.written: list[tuple[int, float]] = []

    async def execute(self, statement, params=None):
        sql = str(statement).lstrip().upper()
        if sql.startswith("UPDATE FUTURES_OUTCOMES"):
            bound = statement.compile().params
            self.written.append(
                (bound["id_1"], bound["current_probability"])
            )
        return await super().execute(statement, params)


@pytest.mark.asyncio
class TestTheCompanionIsRePricedEveryCycle:
    """Seam 1 — `_write_prices._legs`, and the `return` that stranded the pair.

    `_legs` resolved `bare` FIRST and returned on it, so a market storing the
    bare id AND `{cid}_side1` wrote one snapshot for two stored rows. The
    companion kept whatever ingest gave it, forever. On the first price move the
    card stops summing to 1 and a reader sees two sides of one match quoted
    minutes apart — worse than the half-filled bar #7505 set out to fix, because
    a wrong pair looks authoritative in a way a missing one does not.
    """

    async def test_both_stored_rows_are_written(self):
        session = _WriteSession(rows=((11, CID), (12, f"{CID}_side1")))
        stats: dict = {}
        written = await fpr._write_prices(
            session, 60280227, "polymarket", [_item()], stats
        )
        assert written == 2, (
            "two stored rows, two writes. One is the CERT-3251 defect: the "
            f"companion never re-priced. stats={stats!r}"
        )
        assert session.updates == 2
        assert stats.get("unknown_outcomes", 0) == 0

    async def test_the_companion_gets_the_complement_of_the_price_we_accepted(self):
        """Which NUMBER landed on which ROW — read off the statement, not re-derived.

        Counting writes cannot tell a correct pair from a writer that stamped
        the yes price onto both rows, and reconstructing `_legs`' rule in the
        test would be a second definition that agrees with itself forever. So
        this reads the bound values out of the real `UPDATE` the real closure
        produced.

        70/30 rather than the venue's own 50/50 for the same reason: on a coin
        flip every wrong answer here is numerically indistinguishable from the
        right one.
        """
        session = _RecordingSession(rows=((11, CID), (12, f"{CID}_side1")))
        stats: dict = {}
        await fpr._write_prices(session, 60280227, "polymarket", [_item()], stats)

        # `approx` on the value and exact on the id. `1.0 - 0.70` is
        # 0.30000000000000004 and the writer stores what it computed, so an
        # equality here would pin a float artefact rather than the pairing —
        # while a tolerance of 1e-6 still tells 0.3 from 0.7 by five orders of
        # magnitude, which is the only confusion this arm is for.
        assert [oid for oid, _p in session.written] == [11, 12], (
            f"both stored rows must be written, in order. Wrote {session.written!r}"
        )
        assert [p for _oid, p in session.written] == [
            pytest.approx(YES_P),
            pytest.approx(NO_P),
        ], (
            f"the bare row must keep {YES_P} and the companion must carry {NO_P} "
            "— the complement of the price we ACCEPTED, which is what ingest "
            f"stored it at. Wrote {session.written!r}"
        )

    async def test_a_market_with_no_companion_is_untouched(self):
        """The control. Without it, "two writes" is satisfied by a writer that
        doubled every leg in the table."""
        session = _WriteSession(rows=((11, CID),))
        stats: dict = {}
        written = await fpr._write_prices(
            session, 60280227, "polymarket", [_item()], stats
        )
        assert written == 1, f"one stored row, one write. stats={stats!r}"
        assert session.updates == 1

    async def test_the_decomposed_yes_no_convention_is_untouched(self):
        """The second control, on the convention that already worked.

        A decomposed binary stores `_yes` and `_no` and no bare row. Seam 1's
        repair moved the bare branch, so this is the arm that catches a repair
        that fixed one convention by breaking another.
        """
        session = _WriteSession(rows=((11, f"{CID}_yes"), (12, f"{CID}_no")))
        stats: dict = {}
        written = await fpr._write_prices(
            session, 60280227, "polymarket", [_item()], stats
        )
        assert written == 2
        assert session.updates == 2

    async def test_a_kalshi_item_cannot_grow_a_companion(self):
        """`_write_prices` is SHARED by both venues and only Polymarket's fetcher
        builds a `no` side. A Kalshi item carrying a bare row and, somehow, a
        `_side1` sibling must still write one leg — the pairing is gated on the
        side object existing, not on the key existing."""
        session = _WriteSession(rows=((11, CID), (12, f"{CID}_side1")))
        stats: dict = {}
        item = _item()
        item.pop("no")
        written = await fpr._write_prices(
            session, 60280227, "kalshi", [item], stats
        )
        assert written == 1, (
            "no side object means no second write — a companion must never be "
            "priced by inference from the leg beside it"
        )

    async def test_an_empty_book_declines_the_pair_whole(self):
        """#6676's item-level guard must still cover both sides.

        The empty-book refusal is asked once, of the ITEM, precisely so that a
        book and its complement cannot disagree and print 49% above 51%. The
        companion is a third leg reaching that guard and it inherits the same
        answer: both rows decline, or neither does.
        """
        session = _WriteSession(rows=((11, CID), (12, f"{CID}_side1")))
        stats: dict = {}
        written = await fpr._write_prices(
            session,
            60280227,
            "polymarket",
            [_item(prob=0.49, bid=0.01, ask=0.98)],
            stats,
        )
        assert written == 0, (
            "an untradeable book must decline BOTH sides. One write here is the "
            f"phantom pair #6676 is about. stats={stats!r}"
        )
        assert session.updates == 0




class TestTheCompanionsChartCanBeDrawn:
    """Seam 2 — `strip_polymarket_leg`, and the condition id that never reduced.

    A Polymarket leg's history is fetched by asking Gamma for the CONDITION, then
    picking the token that belongs to this leg. `strip_polymarket_leg` is what
    turns a leg id into a condition id, and it knew two suffixes. `_side1` fell
    through unchanged, so the fill asked Gamma for a condition called
    `0x…_side1`, `by_condition` held no such key, and every companion was counted
    `no_exact_condition` — a priced row on a reader's page whose chart is empty
    for a reason nothing on the page could explain.
    """

    def test_the_companion_id_reduces_to_its_condition(self):
        from app.utils.generic_market_history import strip_polymarket_leg

        assert strip_polymarket_leg(f"{CID}_side1") == CID

    def test_the_other_two_conventions_are_unchanged(self):
        """The control: a repair that taught this one suffix by widening the
        match — say, cutting at the last `_` — would pass the arm above and
        truncate a condition id that legitimately contains one."""
        from app.utils.generic_market_history import strip_polymarket_leg

        assert strip_polymarket_leg(f"{CID}_yes") == CID
        assert strip_polymarket_leg(f"{CID}_no") == CID
        assert strip_polymarket_leg(CID) == CID
        assert strip_polymarket_leg("0xabc_side2") == "0xabc_side2", (
            "only the suffix #7505 writes is a leg marker. `_side2` is not one, "
            "and inventing it here would strip a real id"
        )

    def test_the_contract_the_fill_builds_addresses_the_right_condition(self):
        """End of the seam, not the middle of it: the dict the fetcher is handed.

        `polymarket_contract` is what carries the condition id to Gamma, so
        asserting on it rather than on the helper is what proves the reduction
        reached the caller that needed it.
        """
        from app.utils.generic_market_history import polymarket_contract

        contract = polymarket_contract(
            _Outcome(f"{CID}_side1", "Quentin Halys"),
            token_id="7788",
            resolved_via="gamma_condition_by_name",
        )
        assert contract is not None
        assert contract["condition_id"] == CID, (
            "the CONDITION is what Gamma is asked for; a suffixed id here is the "
            "`no_exact_condition` CERT-3251 measured"
        )
        assert contract["outcome_external_id"] == f"{CID}_side1", (
            "and the LEG id is what identifies the row — reducing that too would "
            "collapse the pair onto one series"
        )

    def test_the_cached_contract_still_matches_its_own_row(self):
        """`_contract_matches` compares a cached contract's condition against a
        freshly stripped one, so a companion's cached series must not type as
        `contract_condition_mismatch` and be discarded on read — a chart that
        fetches correctly and is thrown away.

        ⚠️ THIS ARM IS GREEN WITHOUT THE REPAIR AND THAT IS EXPECTED: writer and
        reader both go through `strip_polymarket_leg`, so today they agree
        whatever it returns. It is here for the day one of them stops — a second,
        private reduction rule on either side is the drift it catches — not as
        evidence that seam 2 was broken. The arms above are that evidence.
        """
        from app.utils.generic_market_history import (
            _contract_matches,
            polymarket_contract,
        )

        outcome = _Outcome(f"{CID}_side1", "Quentin Halys")
        contract = polymarket_contract(
            outcome, token_id="7788", resolved_via="gamma_condition_by_name"
        )
        market = _Outcome("1045485", "Draxl vs Halys", outcome_id=60280227)
        market.source = "polymarket"
        assert _contract_matches(contract, market, outcome) is None

    def test_the_companion_asks_gamma_for_its_own_side_by_name(self):
        """Q489, on the new suffix. `_yes`/`_no` legs name their side from the
        ID; the companion has no such marker and must fall through to its stored
        NAME — which is the venue's own `outcomes[1]` token, so Gamma can align
        it. A companion that resolved to "Yes" would take the token belonging to
        the row beside it and print an INVERTED line, not a stale one."""
        from app.utils.generic_market_history import wanted_gamma_outcome_name

        assert (
            wanted_gamma_outcome_name(_Outcome(f"{CID}_side1", "Quentin Halys"))
            == "Quentin Halys"
        )
        assert wanted_gamma_outcome_name(_Outcome(f"{CID}_yes", "Liam Draxl")) == "Yes"
        assert wanted_gamma_outcome_name(_Outcome(f"{CID}_no", "Quentin Halys")) == "No"


class TestTheCompanionsBookStaysWarm:
    """Seam 5 — `polymarket_token_topup.condition_id_of`.

    The top-up keeps a leg's CLOB token current, and it finds the token by
    reducing the leg id to a condition id. `_side1` did not reduce, so the
    function returned None for an id that plainly starts `0x` — and the leg
    #7505 gave a reader a price for is the one leg whose book goes cold.
    """

    def test_the_companion_reduces(self):
        from app.tasks.polymarket_token_topup import condition_id_of

        assert condition_id_of(f"{CID}_side1") == CID

    def test_the_existing_conventions_and_the_refusals_are_unchanged(self):
        """The control, and it carries the two REFUSALS that matter: a parent
        row's Gamma event id is a bare integer and must stay None, and `None`
        stays None. A repair that reduced more aggressively would turn a parent
        id into a condition id and 404 the caller."""
        from app.tasks.polymarket_token_topup import condition_id_of

        assert condition_id_of(f"{CID}_yes") == CID
        assert condition_id_of(f"{CID}_no") == CID
        assert condition_id_of(CID) == CID
        assert condition_id_of("1045485") is None, "a parent's Gamma EVENT id"
        assert condition_id_of(None) is None


class TestTheServeTimeDedupStillReadsTheCompanionAsARung:
    """Seam 6 — the one rule in this repair that must NOT learn `_side1`.

    `drop_duplicate_legs` removes a suffixed leg whose BARE twin is on the same
    market, and the companion pair is exactly that shape: `0x…` beside
    `0x…_side1`. It runs at SERVE time in `routes/feed.py`, `routes/events.py`
    and six places in `routes/futures.py`, so the day `BINARY_LEG_SUFFIXES`
    learns this suffix is the day #7505 goes inert on its own population — the
    leg written every poll, filtered out of every reader surface, the exact
    failure `_side1` was chosen to avoid.

    It is a real second rung, not a duplicate of one. The pair the rule was
    written for is the DECOMPOSITION, where `_yes` restates the bare row's own
    question; here the two rows are two different fighters.

    Stated as behaviour rather than as `assert "_side1" not in BINARY_LEG_SUFFIXES`
    on purpose: the constant is not the only way the rule could acquire it, and a
    reader who widens `binary_leg_base` instead should meet the same red.
    """

    def test_the_pair_survives_the_serve_time_filter(self):
        from app.utils.duplicate_condition_outcomes import drop_duplicate_legs

        rows = [
            {"external_id": CID, "name": "Liam Draxl"},
            {"external_id": f"{CID}_side1", "name": "Quentin Halys"},
        ]
        kept = drop_duplicate_legs(rows, lambda r: r["external_id"])
        assert [r["name"] for r in kept] == ["Liam Draxl", "Quentin Halys"], (
            "both fighters must reach the reader. Dropping the companion here "
            "makes the whole of #7505 invisible while still writing the row "
            f"every poll. Kept: {kept!r}"
        )

    def test_a_real_decomposition_duplicate_is_still_dropped(self):
        """The control, and the reason the rule exists. Without it, "the pair
        survives" is satisfied by a filter that stopped filtering."""
        from app.utils.duplicate_condition_outcomes import drop_duplicate_legs

        rows = [
            {"external_id": CID, "name": "Liam Draxl"},
            {"external_id": f"{CID}_yes", "name": "Yes"},
            {"external_id": f"{CID}_no", "name": "No"},
        ]
        kept = drop_duplicate_legs(rows, lambda r: r["external_id"])
        assert [r["name"] for r in kept] == ["Liam Draxl"]

    def test_the_winner_coherence_reader_keeps_the_companion_too(self):
        """The same rule has a SECOND, independent copy in
        `winner_field_coherence`, and a half-taught pair would be worse than an
        untaught one: a leg one reader keeps and the other drops is a row whose
        presence depends on which surface you are looking at.

        `strip_condition_leg_suffix` answers None for "this row cannot be a
        duplicate leg", which is the answer the companion needs — and it is a
        different answer from "a leg whose twin is absent", which is why the
        assertion is on None rather than on the id coming back unchanged.
        """
        from app.utils.winner_field_coherence import (
            DUPLICATE_CONDITION_LEG_SUFFIXES,
            strip_condition_leg_suffix,
        )

        assert strip_condition_leg_suffix(f"{CID}_side1") is None, (
            "the companion is a rung, not a duplicate of one — see this class's "
            "docstring"
        )
        # The control, in the same arm: the rule still recognises the pair it
        # was written for.
        assert strip_condition_leg_suffix(f"{CID}_no") == CID
        assert DUPLICATE_CONDITION_LEG_SUFFIXES == ("_yes", "_no")

    def test_the_sql_half_of_the_coherence_rule_names_the_same_two_suffixes(self):
        """🔴 THE RULE IS WRITTEN TWICE — once in Python and once as raw SQL
        (`right(fo.external_id, 4) = '_yes' OR right(fo.external_id, 3) = '_no'`).
        A Python-only change would leave the two disagreeing about what a
        duplicate leg is, which is the drift that makes a row appear on one
        surface and not another. Asserted on the SQL text because the SQL text is
        the thing that could silently acquire `_side1`.
        """
        from app.utils import winner_field_coherence as wfc
        import inspect

        sql = inspect.getsource(wfc)
        assert "_side1" not in sql, (
            "the coherence rule — Python or SQL — must not learn the companion "
            "suffix; teaching it drops #7505 off every reader surface"
        )


# ---------------------------------------------------------------------------
# Seam 4 — settlement
# ---------------------------------------------------------------------------

#: The Gamma shapes the settlement phase reads. A sole-moneyline event: ONE
#: market, `outcomes` and `outcomePrices` index-aligned, settled decisively.
SETTLE_EVENT_ID = "1045485"
SETTLE_MARKET_ID = 60280227
SETTLE_CID = "0xdraxlhalyssettled"


def _settled_event(draxl_won=True):
    prices = ["1.0", "0.0"] if draxl_won else ["0.0", "1.0"]
    return {
        "id": SETTLE_EVENT_ID,
        "title": "Davis Cup: Liam Draxl vs. Quentin Halys",
        "closed": True,
        "markets": [
            {
                "conditionId": SETTLE_CID,
                "question": "Davis Cup: Liam Draxl vs. Quentin Halys",
                "outcomes": '["Liam Draxl", "Quentin Halys"]',
                "outcomePrices": f'["{prices[0]}", "{prices[1]}"]',
                "closed": True,
            }
        ],
    }


class _SettleRow:
    def __init__(self):
        self.id = SETTLE_MARKET_ID
        self.external_id = SETTLE_EVENT_ID
        self.group_type = None
        self.poly_event_id = SETTLE_EVENT_ID


class _GradeRecorder:
    """Every `is_winner` this rail wrote, and to which leg.

    Reads the bound values off the compiled statement rather than a string, so a
    change in how the UPDATE is composed shows up as a failure instead of being
    silently accommodated — and so the two legs cannot be confused with each
    other, which is the only mistake this class exists to catch.
    """

    def __init__(self, stored):
        self.stored = set(stored)
        self.grades: dict[str, bool] = {}
        self.prices: dict[str, float] = {}

    def record_update(self, stmt):
        bound = stmt.compile().params
        cid = bound.get("external_id_1")
        # Records what the DATABASE would have changed, not what the rail
        # attempted: a statement that matches no row changes nothing, and a
        # recorder that logged the attempt would make "a market with no
        # companion is untouched" unfalsifiable — the write is always issued.
        if cid is None or cid not in self.stored:
            return 0
        if "is_winner" in bound:
            self.grades[cid] = bound["is_winner"]
        return 1


def _install_settlement(monkeypatch, recorder, event_payload):
    from unittest.mock import AsyncMock, MagicMock

    import app.services.polymarket_api as poly_api_mod
    import app.tasks.redis_state as redis_state

    class _Redis:
        def __init__(self):
            self.store: dict = {}

        def get(self, key):
            return self.store.get(key)

        def setex(self, key, ttl, value):
            self.store[key] = str(value)

        def delete(self, key):
            return 1 if self.store.pop(key, None) is not None else 0

        def sadd(self, key, *vals):
            return None

        def smembers(self, key):
            return set()

        def expire(self, key, ttl):
            return True

    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: _Redis())

    class _Result:
        def __init__(self, rows):
            self._rows = list(rows)

        def all(self):
            return self._rows

    async def _execute(stmt, params=None):
        cls = type(stmt).__name__
        if cls == "Update":
            return MagicMock(rowcount=recorder.record_update(stmt))
        sql = str(getattr(stmt, "text", stmt))
        if "FROM futures_markets fm" in sql:
            p = params or {}
            picked = [r for r in [_SettleRow()] if r.id > (p.get("last_id") or 0)]
            return _Result(picked[: (p.get("limit") or len(picked))])
        if "UPDATE futures_outcomes" in sql:
            # the price-sync `text()` statements, one per leg
            p = params or {}
            cid = p.get("cid")
            if cid in recorder.stored and "price" in p:
                recorder.prices[cid] = p["price"]
            return MagicMock(rowcount=1 if cid in recorder.stored else 0)
        return MagicMock(rowcount=0)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())

    class _Service:
        def __init__(self, *a, **k):
            pass

        async def get_market_by_condition(self, cid):
            return None

        async def get_event_by_id(self, eid):
            return event_payload if str(eid) == SETTLE_EVENT_ID else None

        async def close(self):
            return None

    monkeypatch.setattr(poly_api_mod, "PolymarketAPIService", _Service)
    return bw


@pytest.mark.asyncio
class TestBothSidesOfTheFightAreGraded:
    """Seam 4 — the settlement rail, and the `else` that skipped the companion.

    The bare update runs FIRST and the `_yes`/`_no` branch is its `else`, so on a
    sole-moneyline market — the only shape that stores `cid` beside
    `{cid}_side1` — the bare row was crowned and the companion was never
    touched. A reader met a finished match showing `Draxl — Won` above
    `Halys 30%`: a settled question still quoting a live-looking price for the
    fighter who lost, on the same card, one line down.

    🔴 THIS IS THE ARM WHERE A WRONG ANSWER IS AN AFFIRMATIVE LIE, so the
    specimen is graded BOTH WAYS. A control that only ever settles Draxl passes
    for a writer that stamps `is_winner=False` on the companion unconditionally —
    which is right half the time and silently crowns the loser the other half.
    """

    async def test_the_companion_is_graded_the_other_way(self, monkeypatch):
        recorder = _GradeRecorder({SETTLE_CID, f"{SETTLE_CID}_side1"})
        bw = _install_settlement(monkeypatch, recorder, _settled_event(draxl_won=True))

        await bw._backfill_polymarket_winners_from_api(limit=10)

        assert recorder.grades == {
            SETTLE_CID: True,
            f"{SETTLE_CID}_side1": False,
        }, (
            "the venue settled outcomes[0] at 1.0, so the bare leg won and the "
            f"companion lost. Graded: {recorder.grades!r}"
        )

    async def test_the_companion_wins_when_its_own_side_wins(self, monkeypatch):
        """The inversion. Without it the arm above is satisfied by a hardcoded
        `False`, and a hardcoded `False` publishes a wrong winner on every match
        the second-named side takes."""
        recorder = _GradeRecorder({SETTLE_CID, f"{SETTLE_CID}_side1"})
        bw = _install_settlement(monkeypatch, recorder, _settled_event(draxl_won=False))

        await bw._backfill_polymarket_winners_from_api(limit=10)

        assert recorder.grades == {
            SETTLE_CID: False,
            f"{SETTLE_CID}_side1": True,
        }, (
            "the venue settled outcomes[1] at 1.0, so the COMPANION won. "
            f"Graded: {recorder.grades!r}"
        )

    async def test_the_companions_settlement_price_is_its_own(self, monkeypatch):
        """`prices[1]`, not `prices[0]`. Sharing the bare leg's price would print
        a settled pair reading 100% / 100%."""
        recorder = _GradeRecorder({SETTLE_CID, f"{SETTLE_CID}_side1"})
        bw = _install_settlement(monkeypatch, recorder, _settled_event(draxl_won=True))

        await bw._backfill_polymarket_winners_from_api(limit=10)

        assert recorder.prices == {SETTLE_CID: 1.0, f"{SETTLE_CID}_side1": 0.0}, (
            f"each leg carries its own settlement price. Synced: {recorder.prices!r}"
        )

    async def test_a_market_with_no_companion_grades_exactly_as_before(
        self, monkeypatch
    ):
        """The control. The companion write must match nothing on the markets
        that have no companion — which is almost all of them."""
        recorder = _GradeRecorder({SETTLE_CID})
        bw = _install_settlement(monkeypatch, recorder, _settled_event(draxl_won=True))

        await bw._backfill_polymarket_winners_from_api(limit=10)

        assert recorder.grades == {SETTLE_CID: True}, (
            "a lone bare leg is graded once and nothing else is claimed. "
            f"Graded: {recorder.grades!r}"
        )
