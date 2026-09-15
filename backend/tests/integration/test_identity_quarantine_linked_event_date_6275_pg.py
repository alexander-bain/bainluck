"""The quarantine compares the ticker to the LINKED EVENT's date (#6275, CERT-2902).

CERT-2902 BLOCKed #6275's first presentation on a repair named
``6275-COMPARE-QUARANTINE-TO-LINKED-EVENT-DATE``, and this file is the gate it
required. What it guards is worth stating precisely, because the first cut was
green against every test that existed.

## the defect

Alex's ruling (queue 363 item 4, #1902) is about a market bound to the WRONG
GAME: *a market whose own ticker names a different game date than THE EVENT IT
IS LINKED TO*. Two dates, from two rows. The census that measured the population
joins ``events`` and reads ``ev.commence_time`` for exactly that reason
(``scripts/census_settlement_contamination.py``).

The published chain read ``market_info.commence_time`` — the MARKET's own copy
of the start time, which is a third fact and not the one the ruling names. On
the specimen the ruling is written about, the two disagree:

    market 58609021   ticker ``KXMLBTOTAL-26AUG051940MINKC``    Aug 5 Eastern
                      ``futures_markets.commence_time``          Aug 5 Eastern
    event  15187509   ``events.commence_time``                   Aug 6 Eastern

So the comparison was the ticker's date against a date copied from that same
ticker, it agreed with itself, and **the one row the quarantine exists to hold
was the one row it declared clean**. Not a guard gap — a different predicate.

## why this needs a real server and a seeded population

Every test #6275 shipped with was green while the defect was live, and that is
structural rather than an oversight:

* the WIRING guards (``tests/test_identity_quarantine_reaches_the_curve_6275.py``)
  assert the CTE is in the chain and ``deduped`` filters on the flag. Both were
  true. Which COLUMN the CTE reads is not a fact about the wiring.
* the DIFFERENTIAL (``test_market_identity_quarantine_sql_real_postgres.py``)
  runs the chain over a VALUES corpus whose ``commence_time`` the test supplies
  directly. A corpus that hands the predicate one date cannot notice that the
  population hands it the wrong one.

The claim under test is relational — *which of two tables' dates decides* — so
it is proved the only way that claim can be: seed a market and an event that
DISAGREE, run the real rendered ``_calibration_population_ctes()``, and read the
rows back.

## red-first, executed here

:func:`_reverted` performs textual surgery on the production string to put the
market's own column back, and every arm runs BOTH ways. A green run therefore
means the reverted chain was proved to reproduce CERT-2902's finding in this
very process, not that nothing objected. Measured locally against PostgreSQL
before this file was committed:

    fixed      published {control, market-copy-wrong}   quarantined {specimen}
    reverted   published {specimen, control}            quarantined {market-copy-wrong}

Note the second column of the reverted row. The old predicate did not merely
MISS the specimen; it also quarantined a correctly-bound market whose own copy
of the start time had drifted. Both directions are asserted, because a repair
that only stopped missing would still be leaving good rows out of the curve.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml`` with the
all-skipped detector its neighbours carry — a PG-gated file no step invokes
skips silently while pytest exits 0, which is the failure mode
``tests/test_pg_gate_seed_completeness.py`` exists to end.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("CALIBRATION_TEST_DATABASE_URL") or os.environ.get(
    "SEARCH_TEST_DATABASE_URL"
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL (CI's service container) or "
            "CALIBRATION_TEST_DATABASE_URL to run the #6275 linked-event-date gate"
        ),
    ),
]

# Ids well clear of every sibling gate in the shared `search-recall` database,
# and inside int32 — `events.id` is `Mapped[int]`, i.e. INTEGER, and an
# out-of-range literal makes every INSERT and the cleanup DELETE raise an
# asyncpg DataError instead of running the gate.
SPORT_ID = 62750
EVENT_WRONG_DAY = 627500001
EVENT_SAME_DAY = 627500002
EVENT_MARKET_COPY_WRONG = 627500003

#: The specimen. Its ticker and its own `commence_time` are both Aug 5 Eastern
#: while its EVENT is Aug 6 — the exact shape of production market 58609021 on
#: event 15187509, which is the row CERT-2902 proved survived.
MID_SPECIMEN = 627501
#: The control the cert required retained: ticker, market copy and event all name
#: the same Eastern day. It must publish, or the repair would be quarantining on
#: a comparison that is simply always true.
MID_SAME_DAY = 627502
#: The OTHER direction, and the reason the old predicate was not merely narrow:
#: ticker and EVENT agree on Aug 5 while the market's own copy says Aug 7. The
#: ruling says nothing is wrong with this market's identity, so it must publish —
#: and under the reverted chain it is quarantined.
MID_MARKET_COPY_WRONG = 627503

ALL_MIDS = [MID_SPECIMEN, MID_SAME_DAY, MID_MARKET_COPY_WRONG]
ALL_EVENT_IDS = [EVENT_WRONG_DAY, EVENT_SAME_DAY, EVENT_MARKET_COPY_WRONG]

#: 19:40 ET on Aug 5 — a NIGHT game on purpose, so its UTC date is Aug 6 and any
#: chain that compared UTC dates instead of Eastern ones would quarantine the
#: control. The Eastern conversion is not this file's subject, but a fixture that
#: could not tell the two apart would credit the wrong mechanism.
AUG5_ET_NIGHT = datetime(2026, 8, 5, 23, 40, tzinfo=timezone.utc)
#: 19:30 ET on Aug 6 — the wrong game. Production event 15187509's own value.
AUG6_ET_NIGHT = datetime(2026, 8, 6, 23, 30, tzinfo=timezone.utc)
#: Production market 58609021's own `commence_time`, verbatim: 21:59 ET on Aug 5.
#: Kalshi stores a CLOSE time here far more often than a start (gotcha #14), which
#: is why the market's copy is not the fact the ruling names.
MARKET_COPY_AUG5 = datetime(2026, 8, 6, 1, 59, 43, tzinfo=timezone.utc)
#: A market copy that has drifted two days off its own event.
MARKET_COPY_AUG7 = datetime(2026, 8, 7, 23, 40, tzinfo=timezone.utc)

#: Every ticker names Aug 5. The three markets differ ONLY in which other date
#: disagrees with it, so whatever any arm below finds is attributable to the
#: comparison under test and to nothing else about the fixture.
TICKERS = {
    MID_SPECIMEN: "KXMLBTOTAL-26AUG051940MINKC",
    MID_SAME_DAY: "KXMLBTOTAL-26AUG051940SEAOAK",
    MID_MARKET_COPY_WRONG: "KXMLBTOTAL-26AUG051940NYYBOS",
}
EVENT_OF = {
    MID_SPECIMEN: EVENT_WRONG_DAY,
    MID_SAME_DAY: EVENT_SAME_DAY,
    MID_MARKET_COPY_WRONG: EVENT_MARKET_COPY_WRONG,
}
MARKET_COMMENCE = {
    MID_SPECIMEN: MARKET_COPY_AUG5,
    MID_SAME_DAY: MARKET_COPY_AUG5,
    MID_MARKET_COPY_WRONG: MARKET_COPY_AUG7,
}
EVENT_COMMENCE = {
    EVENT_WRONG_DAY: AUG6_ET_NIGHT,
    EVENT_SAME_DAY: AUG5_ET_NIGHT,
    EVENT_MARKET_COPY_WRONG: AUG5_ET_NIGHT,
}

#: What the repaired chain publishes, at market grain.
PUBLISHED_WHEN_FIXED = sorted([MID_SAME_DAY, MID_MARKET_COPY_WRONG])
#: What CERT-2902's chain published: the specimen rides, the correctly-bound
#: market with a drifted copy is held. Exactly inverted on both.
PUBLISHED_WHEN_REVERTED = sorted([MID_SPECIMEN, MID_SAME_DAY])

#: The repaired projection, as ``identity_quarantine_ctes`` emits it once the
#: population passes ``commence_time_col="event_commence_time"``. Pinned so the
#: reverted arm fails LOUDLY if the fix is reshaped, rather than silently
#: reverting nothing and letting every assertion below pass vacuously.
FIXED_PROJECTION = "src.event_commence_time AS commence_time"
#: The pre-repair projection, which is what the renderer's old default produced:
#: `market_info` has a column called `commence_time`, so the default bound
#: cleanly to the market's own copy.
REVERTED_PROJECTION = "src.commence_time AS commence_time"


def _reverted(ctes: str) -> str:
    """The production chain with ONLY CERT-2902's defect put back.

    Textual surgery on the real string rather than a hand-copied chain: a second
    copy of several thousand lines of SQL drifts, and a drifted copy that still
    reproduced the miss would prove nothing about the producer.
    """
    assert ctes.count(FIXED_PROJECTION) == 1, (
        "PREMISE GONE: the identity quarantine does not read "
        f"{FIXED_PROJECTION!r} exactly once in the built population SQL. Do not "
        "delete this gate — re-aim it at the new shape, or the red-first arm "
        "stops reverting anything and every assertion here passes vacuously."
    )
    return ctes.replace(FIXED_PROJECTION, REVERTED_PROJECTION, 1)


async def _seed(session):
    """Three lone resolved Kalshi binaries, one per event.

    ONE market per event on purpose: `event_sizes` needs >= 3 markets on an event
    before the members are folded into a grouped virtual market, so each market
    here is its own question and what is published or withheld is attributable to
    the market-level quarantine rather than to a sibling's admission.

    Both book sides are seeded, and the ask is not decoration: #940's liquidity
    predicate wants a real `yes_bid` and the q270 writer bar wants a two-sided
    book (`yes_ask IS NOT NULL AND (yes_ask - yes_bid) < 0.50`). A bid-only seed
    publishes NOTHING, and then every "the quarantine held it" assertion passes
    having held nothing.
    """
    await session.execute(
        text("INSERT INTO sports (id, key, name, active) VALUES (:id, :k, :n, true)"),
        {"id": SPORT_ID, "k": f"test_6275_{SPORT_ID}", "n": "Test 6275"},
    )
    for event_id in ALL_EVENT_IDS:
        await session.execute(
            text(
                "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
                "commence_time, status) VALUES "
                "(:id, :sid, 'Royals 6275', 'Twins 6275', :ct, 'completed')"
            ),
            {"id": event_id, "sid": SPORT_ID, "ct": EVENT_COMMENCE[event_id]},
        )
    for market_id in ALL_MIDS:
        await session.execute(
            text(
                "INSERT INTO futures_markets (id, external_id, name, source, status, "
                "category, event_id, commence_time, mutually_exclusive, market_type, "
                "llm_sport_category, volume) VALUES "
                "(:id, :xid, :nm, 'kalshi', 'resolved', 'championship', :ev, :ct, "
                "true, 'binary', 'baseball', 100)"
            ),
            {
                "id": market_id,
                "xid": TICKERS[market_id],
                "nm": f"market-6275-{market_id}",
                "ev": EVENT_OF[market_id],
                "ct": MARKET_COMMENCE[market_id],
            },
        )
        for idx, (name, prob, winner) in enumerate(
            (("Yes", 0.60, True), ("No", 0.40, False))
        ):
            outcome_id = market_id * 100 + idx
            await session.execute(
                text(
                    "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
                    "opening_probability, calibration_probability, is_winner, "
                    "resolution_source, volume) VALUES "
                    "(:id, :mid, :xid, :nm, :p, :p, :win, 'api_settlement', 10)"
                ),
                {
                    "id": outcome_id,
                    "mid": market_id,
                    "xid": f"test-6275-out-{outcome_id}",
                    "nm": name,
                    "p": prob,
                    "win": winner,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
                    "probability, reading_count, last_price, yes_bid, yes_ask) VALUES "
                    "(:oid, 'test-6275', :p, 1, :p, :p, :p)"
                ),
                {"oid": outcome_id, "p": prob},
            )
    await session.commit()


async def _cleanup(session):
    outcome_ids = [mid * 100 + idx for mid in ALL_MIDS for idx in (0, 1)]
    await session.execute(
        text("DELETE FROM futures_odds_snapshots WHERE outcome_id = ANY(:ids)"),
        {"ids": outcome_ids},
    )
    await session.execute(
        text("DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"),
        {"ids": ALL_MIDS},
    )
    await session.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:ids)"), {"ids": ALL_MIDS}
    )
    await session.execute(
        text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": ALL_EVENT_IDS}
    )
    await session.execute(text("DELETE FROM sports WHERE id = :id"), {"id": SPORT_ID})
    await session.commit()


async def _with_seeded_db(body):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            await _cleanup(session)
            await _seed(session)
            try:
                await body(session)
            finally:
                await _cleanup(session)
    finally:
        await engine.dispose()


async def _markets_in(session, ctes, relation):
    """The seeded markets present in ``relation``, at market grain.

    Market grain rather than outcome grain because the binary branch publishes
    one side per market, and which side wins the ``rn = 1`` race is not this
    gate's subject.
    """
    rows = (
        await session.execute(
            text(
                "WITH "
                + ctes
                + f" SELECT DISTINCT market_id FROM {relation} "
                "WHERE market_id = ANY(:ids) ORDER BY market_id"
            ),
            {"ids": ALL_MIDS},
        )
    ).all()
    return sorted(r.market_id for r in rows)


async def test_curve_quarantine_uses_linked_event_date_not_market_commence_6275():
    """CERT-2902's required gate, both directions, on rows.

    The specimen is held and absent from the published population; the same-day
    control publishes; and the market whose OWN copy has drifted — but whose
    event agrees with its ticker — publishes too, because nothing about its
    identity is disputed.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes

    async def body(session):
        ctes = _calibration_population_ctes()

        # NON-VACUITY FIRST. All three must be live candidates in `normalized`,
        # or a fixture failing the liquidity or truth gates would make the
        # "held" assertion below true for reasons with nothing to do with the
        # quarantine.
        candidates = await _markets_in(session, ctes, "normalized")
        assert candidates == sorted(ALL_MIDS), (
            "the fixture does not reach `normalized` whole "
            f"(got {candidates}, want {sorted(ALL_MIDS)}), so nothing below is "
            "attributable to the identity quarantine"
        )

        held = await _markets_in(session, ctes, "identity_disputed_markets")
        assert held == [MID_SPECIMEN], (
            "the quarantine is not comparing the ticker against the LINKED "
            f"EVENT's date (held {held}, want [{MID_SPECIMEN}]). The specimen's "
            "ticker and its own `futures_markets.commence_time` are both Aug 5 "
            "Eastern while its event is Aug 6 — the exact shape of production "
            "market 58609021 on event 15187509."
        )

        published = await _markets_in(session, ctes, "deduped")
        assert published == PUBLISHED_WHEN_FIXED, (
            f"the published population is {published}, want "
            f"{PUBLISHED_WHEN_FIXED}: the wrong-game market must be absent and "
            "both correctly-bound markets must survive"
        )

    await _with_seeded_db(body)


async def test_the_reverted_chain_reproduces_cert_2902s_finding():
    """Red-first, executed — and inverted on BOTH markets, not just the miss.

    Without this arm the gate above proves only that the current chain behaves
    as described; it cannot say the described behaviour is a change. Putting the
    market's own column back must publish the wrong-game row AND hold the
    correctly-bound one, which is the two-sided shape of the defect.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes

    async def body(session):
        ctes = _reverted(_calibration_population_ctes())

        held = await _markets_in(session, ctes, "identity_disputed_markets")
        assert held == [MID_MARKET_COPY_WRONG], (
            "the reverted chain did not reproduce CERT-2902's finding "
            f"(held {held}): reading the market's own `commence_time` must hold "
            "the market whose copy drifted and let the wrong-game one through"
        )

        published = await _markets_in(session, ctes, "deduped")
        assert published == PUBLISHED_WHEN_REVERTED, (
            f"the reverted chain published {published}, want "
            f"{PUBLISHED_WHEN_REVERTED}. If this is not inverted against the "
            "repaired arm the surgery above is no longer reverting the defect."
        )

    await _with_seeded_db(body)


async def test_an_unlinked_market_is_not_quarantined_and_still_publishes():
    """The LEFT join earns its keyword here.

    The census joins `events` INNER because it only ever looks at event-linked
    markets. This population deliberately includes unlinked ones — the horizon
    variant scopes itself to `fm.event_id IS NULL` — so an INNER join would not
    narrow the quarantine, it would empty the population. A market with no event
    has no event date to disagree with, and the quarantine's own NULL rule reads
    that as unknown rather than disputed.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes

    async def body(session):
        # Cut the specimen loose from its wrong-day event. Nothing else changes:
        # its ticker still says Aug 5 and its own `commence_time` still says
        # Aug 5, so any change in its fate is the event link and nothing else.
        await session.execute(
            text("UPDATE futures_markets SET event_id = NULL WHERE id = :id"),
            {"id": MID_SPECIMEN},
        )
        await session.commit()

        ctes = _calibration_population_ctes()
        held = await _markets_in(session, ctes, "identity_disputed_markets")
        assert held == [], (
            f"an unlinked market was quarantined ({held}) — the predicate is "
            "treating a missing event as a disagreement, which shrinks the "
            "curve on a guess"
        )
        published = await _markets_in(session, ctes, "deduped")
        assert published == sorted(ALL_MIDS), (
            f"the unlinked market was lost from the population ({published}) — "
            "the join to `events` is narrowing rows rather than carrying a "
            "column, which would empty the horizon variant outright"
        )

    await _with_seeded_db(body)
