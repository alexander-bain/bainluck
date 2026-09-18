"""#6757 residual — a no-result marker cannot protect an unsupported price.

WHAT A READER SAW (production v4709, 2026-09-18 04:09Z). ``/futures/2951399`` —
"WBC Featherweight Title on January 1, 2027", ``status='open'``, resolving in
2027 — printed seventeen prices summing to 876.5%, thirteen of them an identical
**49%** ("Title is vacant — 49%" among them), each labelled LATEST and eleven
days stale. Every one of its seventeen legs carries
``resolution_source='ungradeable_result'`` / ``is_winner=False``.

WHY THE SHIPPED FIX COULD NOT REACH IT. #6757's arm (``_empty_book_outcome_ids``
on the ladder, the matching arm in ``_drop_unsupported_snapshot_points`` on the
chart) exempts a row whose ``resolution_source`` is non-null, on the reasoning
that a graded row's number is a result and withholding it deletes that result
(#6532). But ``ungradeable_result`` is not a grade. ``resolution_authority``
classifies it as a RETRACTION — "it asserts no winner" (CAL-P056, #1852) — and
``kalshi_fabricated_loss.RETRACTION_SOURCE`` is its one canonical spelling. The
exemption meant to protect a result was being claimed by rows that have none,
and what it protected was the midpoint of an empty book.

THESE TESTS RUN THE REAL ROUTES ON A REAL POSTGRES. ``get_futures_market`` and
``get_futures_history`` are called through the FastAPI app with the production
session dependency pointed at a disposable database seeded with SYNTHETIC rows
(every name carries the ``SYNTHETIC-6757`` label). The three sibling arms are
NOT stubbed — a control that passes here passes against the whole withheld-id
union, so a number that survives is a number the route really serves.

Gated exactly like ``test_bookmaker_count_real_postgres.py``: set
``SEARCH_TEST_DATABASE_URL`` (CI's ``search-recall`` job provides one) or the
module skips, loudly.

THE CONTROLS, and what each can fail on:

* ``D`` — the WBC shape. Retracted legs on an empty-book midpoint are WITHHELD
  after the fix (RED on base: they were served). A retracted leg on a real
  two-sided quote KEEPS its price — a no-result marker alone must neither
  protect an unsupported price nor delete a supported one.
* ``S`` — a genuinely settled field (``api_settlement`` winner AND loser). The
  ladder keeps every result and the chart keeps the completed journey,
  including the champion's early points that ran through an empty book. Fails
  if the repair over-reaches from "retraction" to "any terminal source".
* ``A`` — the shipped #6757 arm: ungraded (``resolution_source IS NULL``)
  empty-book legs are still withheld. Fails if the repair loosens the arm.
* ``C`` — a healthy two-sided field. Nothing moves. Fails if the repair
  over-reaches into real quotes.
* Adjacent terminal sources (``did_not_play``, ``all_losers``) are PINNED to
  current behaviour (still exempt). That is a statement about the patch's
  scope, not a verdict on those sources — see ``REPORT.md``.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6757 no-result "
            "exemption contract (CI job `search-recall` provides one)"
        ),
    ),
]

LABEL = "SYNTHETIC-6757"
RETRACTION = "ungradeable_result"

#: The WBC shape, leg for leg. ``(name, probability, bid, ask, resolution_source,
#: is_winner, expect_priced_after_fix)``.
D_LEGS = (
    # Thirteen identical 49s on production; four are enough to be a wall.
    ("retracted empty-book #1", 0.490, 0.0100, 0.9700, RETRACTION, False, False),
    ("retracted empty-book #2", 0.490, 0.0100, 0.9700, RETRACTION, False, False),
    ("retracted empty-book #3", 0.490, 0.0100, 0.9700, RETRACTION, False, False),
    (
        "Title is vacant (retracted empty-book)",
        0.490,
        0.0100,
        0.9700,
        RETRACTION,
        False,
        False,
    ),
    # The hero: a retracted leg on a REAL two-sided book. A no-result marker must
    # not delete a supported quote.
    ("retracted, real quote (hero)", 0.930, 0.9000, 0.9600, RETRACTION, False, True),
    # A real 0.50 on a tight book is a valid price, whatever the grade says.
    ("retracted, real 0.50 quote", 0.500, 0.4900, 0.5100, RETRACTION, False, True),
    # Missing book metadata keeps today's conservative behaviour: nothing to
    # judge the number against, so it is not withheld by this arm.
    ("retracted, no book stored", 0.490, None, None, RETRACTION, False, True),
)

#: A genuinely settled Kalshi field: ``(name, probability, bid, ask, source, is_winner)``.
S_LEGS = (
    ("settled winner", 1.000, 0.9900, 1.0000, "api_settlement", True),
    ("settled loser, book collapsed", 0.000, 0.0000, 0.0100, "api_settlement", False),
    # The row the existing exemption was written for (#6532): graded, but its
    # current number is still the midpoint of a stale empty book. Kept.
    ("settled loser, stale empty book", 0.490, 0.0100, 0.9700, "api_settlement", False),
)

#: Adjacent terminal sources — NOT retractions — on the empty-book shape. Pinned
#: to current behaviour (exempt). Deciding them is out of this patch's scope.
ADJACENT_LEGS = (
    ("did_not_play on empty book", 0.490, 0.0100, 0.9700, "did_not_play", False),
    ("all_losers on empty book", 0.490, 0.0100, 0.9700, "all_losers", False),
)

#: The shipped #6757 arm: ungraded empty-book legs beside one real bid.
A_LEGS = (
    ("ungraded empty-book #1", 0.480, 0.0100, 0.9500, None, False, False),
    ("ungraded empty-book #2", 0.480, 0.0100, 0.9500, None, False, False),
    ("ungraded, a real bid", 0.740, 0.5200, 0.9600, None, False, True),
)

#: A healthy two-sided field. Nothing here may move.
C_LEGS = (
    ("healthy favourite", 0.620, 0.6100, 0.6300, None, False, True),
    ("healthy second", 0.300, 0.2900, 0.3150, None, False, True),
    ("healthy longshot", 0.080, 0.0700, 0.0900, None, False, True),
)


def _now():
    return datetime.now(timezone.utc)


async def _seed(engine) -> dict[str, dict]:
    """Seed the four synthetic markets and return ``{key: {name: outcome_id}}``."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome

    ids: dict[str, dict] = {}
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():

            def market(key, name, source, status, resolution_date=None):
                m = FuturesMarket(
                    source=source,
                    external_id=f"{LABEL}-{key}",
                    name=f"{LABEL} {name}",
                    description=f"{LABEL} synthetic fixture — not a real market",
                    category="championship",
                    market_tier=5,
                    mutually_exclusive=True,
                    status=status,
                    resolution_date=resolution_date,
                )
                session.add(m)
                return m

            def leg(m, name, p, bid, ask, source, winner, rank):
                o = FuturesOutcome(
                    market=m,
                    external_id=f"{LABEL}-{m.external_id}-{rank}",
                    name=f"{LABEL} {name}",
                    current_probability=p,
                    current_yes_bid=bid,
                    current_yes_ask=ask,
                    rank=rank,
                    is_winner=winner,
                    resolution_source=source,
                    last_updated=_now() - timedelta(days=11),
                )
                session.add(o)
                return o

            def snap(o, bookmaker, p, bid, ask, last_price, age_hours):
                session.add(
                    FuturesOddsSnapshot(
                        outcome=o,
                        bookmaker=bookmaker,
                        probability=p,
                        yes_bid=bid,
                        yes_ask=ask,
                        last_price=last_price,
                        captured_at=_now() - timedelta(hours=age_hours),
                    )
                )

            # D — the WBC shape (Kalshi, open, resolves 2027).
            d = market(
                "D",
                "WBC-shape retracted field",
                "kalshi",
                "open",
                datetime(2027, 1, 1, tzinfo=timezone.utc),
            )
            d_legs = {}
            for i, (name, p, bid, ask, src, win, _keep) in enumerate(D_LEGS, 1):
                o = leg(d, name, p, bid, ask, src, win, i)
                d_legs[name] = o
                if bid is not None:
                    # The stale empty-book midpoint, drawn three times over the
                    # last week — the points the chart must stop drawing.
                    for h in (150, 100, 50):
                        snap(o, "kalshi", p, bid, ask, None, h)
            # One retracted empty-book leg ALSO carries a real earlier point on a
            # two-sided book: PER POINT, NOT PER SERIES — that point survives.
            snap(
                d_legs["retracted empty-book #1"],
                "kalshi",
                0.450,
                0.4000,
                0.5000,
                0.45,
                160,
            )

            # S — genuinely settled (Kalshi, resolved).
            s = market("S", "settled field", "kalshi", "resolved")
            s_legs = {}
            for i, (name, p, bid, ask, src, win) in enumerate(S_LEGS, 1):
                o = leg(s, name, p, bid, ask, src, win, i)
                s_legs[name] = o
                # Every settled leg's journey ran through an empty-book midpoint
                # before the venue decided — the completed journey stays whole.
                snap(o, "kalshi", 0.490, 0.0100, 0.9700, None, 150)
                snap(o, "kalshi", 0.490, 0.0100, 0.9700, None, 100)
                snap(o, "kalshi", p, bid, ask, p, 20)

            # Adjacent terminal sources live on the settled market too.
            for i, (name, p, bid, ask, src, win) in enumerate(
                ADJACENT_LEGS, len(S_LEGS) + 1
            ):
                o = leg(s, name, p, bid, ask, src, win, i)
                s_legs[name] = o
                snap(o, "kalshi", p, bid, ask, None, 100)

            # A — the shipped #6757 arm (Polymarket, open).
            a = market("A", "ungraded empty-book field", "polymarket", "open")
            a_legs = {}
            for i, (name, p, bid, ask, src, win, _keep) in enumerate(A_LEGS, 1):
                o = leg(a, name, p, bid, ask, src, win, i)
                a_legs[name] = o
                snap(o, "polymarket", p, bid, ask, None, 100)

            # C — healthy (Polymarket, open).
            c = market("C", "healthy two-sided field", "polymarket", "open")
            c_legs = {}
            for i, (name, p, bid, ask, src, win, _keep) in enumerate(C_LEGS, 1):
                o = leg(c, name, p, bid, ask, src, win, i)
                c_legs[name] = o
                snap(o, "polymarket", p, bid, ask, p, 100)
                snap(o, "polymarket", p, bid, ask, p, 50)

        ids["D"] = {"market": d.id, **{n: o.id for n, o in d_legs.items()}}
        ids["S"] = {"market": s.id, **{n: o.id for n, o in s_legs.items()}}
        ids["A"] = {"market": a.id, **{n: o.id for n, o in a_legs.items()}}
        ids["C"] = {"market": c.id, **{n: o.id for n, o in c_legs.items()}}
    return ids


@pytest.fixture
async def seeded(monkeypatch):
    """Real Postgres, real schema, real routes; the session dependency pointed here."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import Base, get_db, get_db_rw

    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    ids = await _seed(engine)

    async def _get_db():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    async def _anon():
        return None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_db_rw] = _get_db
    app.dependency_overrides[get_optional_user] = _anon

    # The detail route caches its provenance half in Redis; make that half a
    # no-op so the assertions read the rows and never a cached prior run.
    import app.routes.futures as fr

    async def _no_sources(_db, _market_id, _outcome_ids):
        return [], []

    monkeypatch.setattr(fr, "_load_market_sources", _no_sources)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, ids

    app.dependency_overrides.clear()
    await engine.dispose()


def _label(name: str) -> str:
    return f"{LABEL} {name}"


async def _detail(client, market_id):
    r = await client.get(f"/api/futures/{market_id}")
    assert r.status_code == 200, r.text
    return r.json()


async def _history(client, market_id, **params):
    r = await client.get(
        f"/api/futures/{market_id}/history",
        params={"hours": 24 * 14, "top_n": 50, **params},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _prices(detail) -> dict[str, float | None]:
    return {o["name"]: o["probability"] for o in detail["outcomes"]}


def _drawn(history) -> dict[str, list[float]]:
    return {
        o["name"]: [pt["probability"] for pt in o["history"]]
        for o in history["outcomes"]
    }


class TestD_TheWBCShape:
    async def test_retracted_empty_book_legs_are_withheld_on_the_ladder(self, seeded):
        """🔴 RED ON BASE. The four retracted 49s are served; after the fix they are withheld.

        Rows, names and ranks stay: the price is nulled, the leg is not removed.
        """
        client, ids = seeded
        detail = await _detail(client, ids["D"]["market"])
        prices = _prices(detail)
        withheld = [n for n, p, *_, keep in D_LEGS if not keep]
        assert len(detail["outcomes"]) == len(
            D_LEGS
        ), "rows are kept; only prices are withheld"
        for name in withheld:
            assert (
                prices[_label(name)] is None
            ), f"{name!r} is a retracted empty-book midpoint and must be withheld"
        assert detail["prices_withheld"] == len(withheld)

    async def test_a_retracted_leg_on_a_real_quote_keeps_its_price(self, seeded):
        """A no-result marker alone must not DELETE a supported quote either."""
        client, ids = seeded
        prices = _prices(await _detail(client, ids["D"]["market"]))
        assert prices[_label("retracted, real quote (hero)")] == pytest.approx(0.93)
        assert prices[_label("retracted, real 0.50 quote")] == pytest.approx(0.50)
        assert prices[_label("retracted, no book stored")] == pytest.approx(
            0.49
        ), "missing book metadata keeps the current conservative behaviour"

    async def test_the_chart_stops_drawing_the_retracted_midpoints(self, seeded):
        """🔴 RED ON BASE. The chart and the ladder must not disagree (#5898).

        PER POINT: the one real earlier point on leg #1 survives while its three
        empty-book midpoints go.
        """
        client, ids = seeded
        drawn = _drawn(await _history(client, ids["D"]["market"]))
        for name in (
            "retracted empty-book #2",
            "retracted empty-book #3",
            "Title is vacant (retracted empty-book)",
        ):
            assert (
                drawn.get(_label(name), []) == []
            ), f"{name!r}: an empty-book midpoint must not be charted"
        assert drawn[_label("retracted empty-book #1")] == [pytest.approx(0.45)]
        assert (
            len(drawn[_label("retracted, real quote (hero)")]) == 3
        ), "a real quote's points stay"
        assert len(drawn[_label("retracted, real 0.50 quote")]) == 3


class TestS_GenuinelySettled:
    async def test_the_ladder_keeps_every_result(self, seeded):
        """Settled means settled — wins AND losses keep their numbers (#6532)."""
        client, ids = seeded
        detail = await _detail(client, ids["S"]["market"])
        prices = _prices(detail)
        for name, p, *_ in S_LEGS:
            assert prices[_label(name)] == pytest.approx(
                p
            ), f"{name!r}: a settled row's number is a result"
        winners = {o["name"]: o["is_winner"] for o in detail["outcomes"]}
        assert winners[_label("settled winner")] is True
        assert winners[_label("settled loser, book collapsed")] is False

    async def test_the_chart_keeps_the_completed_journey(self, seeded):
        """The champion's early empty-book points are the journey, and they stay."""
        client, ids = seeded
        drawn = _drawn(await _history(client, ids["S"]["market"]))
        for name, p, *_ in S_LEGS:
            assert (
                len(drawn[_label(name)]) == 3
            ), f"{name!r}: a settled series is shown whole"

    async def test_adjacent_terminal_sources_keep_current_behaviour(self, seeded):
        """PINNED, NOT RULED. ``did_not_play`` / ``all_losers`` are not retractions.

        This patch only stops ``ungradeable_result`` from claiming the grade
        exemption. Whether other terminal sources should is a separate
        decision; until it is made they print as they do today.
        """
        client, ids = seeded
        prices = _prices(await _detail(client, ids["S"]["market"]))
        drawn = _drawn(await _history(client, ids["S"]["market"]))
        for name, p, *_ in ADJACENT_LEGS:
            assert prices[_label(name)] == pytest.approx(p)
            assert len(drawn[_label(name)]) == 1


class TestA_TheShippedArm:
    async def test_ungraded_empty_book_legs_are_still_withheld(self, seeded):
        client, ids = seeded
        detail = await _detail(client, ids["A"]["market"])
        prices = _prices(detail)
        assert prices[_label("ungraded empty-book #1")] is None
        assert prices[_label("ungraded empty-book #2")] is None
        assert prices[_label("ungraded, a real bid")] == pytest.approx(0.74)
        assert detail["prices_withheld"] == 2
        drawn = _drawn(await _history(client, ids["A"]["market"]))
        assert drawn.get(_label("ungraded empty-book #1"), []) == []
        assert len(drawn[_label("ungraded, a real bid")]) == 1


class TestC_Healthy:
    async def test_nothing_moves(self, seeded):
        client, ids = seeded
        detail = await _detail(client, ids["C"]["market"])
        prices = _prices(detail)
        for name, p, *_ in C_LEGS:
            assert prices[_label(name)] == pytest.approx(p)
        assert detail["prices_withheld"] == 0
        drawn = _drawn(await _history(client, ids["C"]["market"]))
        for name, *_ in C_LEGS:
            assert len(drawn[_label(name)]) == 2
