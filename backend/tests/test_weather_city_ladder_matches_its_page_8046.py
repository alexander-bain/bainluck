"""#8046 Half A — the /weather city ladder prints the number its own market page prints.

The Houston panel read "90-91°F 46%" over a ladder summing to 116.9%; one tap
away `/futures/62721461` read 39% over a ladder summing to 100.0%. The page
runs the #23 squeeze (`normalize_display_probs`) and the card did not.

The specimen below is Houston's served ladder of 2026-09-28 00:3xZ, verbatim.
The page's answer for its modal bucket was 0.3892 — the number these tests pin.

Runs the REAL `get_cities` statements against SQLite (same harness as
`test_weather_percent_contract_6616.py`).
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import (  # noqa: E402
    Base,
    FuturesMarket,
    FuturesOddsSnapshot,
    FuturesOutcome,
)
from app.routes import league_futures  # noqa: E402
from app.routes.weather import get_cities  # noqa: E402

NOW = datetime.now(timezone.utc)
FRESH = NOW - timedelta(hours=1)
_TOMORROW = (NOW + timedelta(days=1)).date()

# Houston, 2026-09-28 00:3xZ, `GET /api/weather/cities` — sums to 1.169.
HOUSTON = [
    ("81°F or below", 0.02),
    ("82-83°F", 0.0105),
    ("84-85°F", 0.018),
    ("86-87°F", 0.03),
    ("88-89°F", 0.15),
    ("90-91°F", 0.455),
    ("92-93°F", 0.37),
    ("94-95°F", 0.055),
    ("96-97°F", 0.03),
    ("98-99°F", 0.03),
    ("100°F or higher", 0.0005),
]
# New York, same payload — a coherent 1.024 ladder the page prints RAW
# (`/futures/62721466` served 0.375 for 72-73°F, identical to the card).
NEW_YORK = [
    ("65°F or below", 0.004),
    ("66-67°F", 0.02),
    ("68-69°F", 0.09),
    ("70-71°F", 0.3),
    ("72-73°F", 0.375),
    ("74-75°F", 0.17),
    ("76-77°F", 0.05),
    ("78°F or higher", 0.015),
]


@pytest.fixture(autouse=True)
def _sqlite_returns_aware_datetimes():
    fields = ("resolution_date", "updated_at", "created_at", "last_updated")

    def _restore_utc(target, _context):  # pragma: no cover - sqlite shim
        for field in fields:
            value = getattr(target, field, None)
            if isinstance(value, datetime) and value.tzinfo is None:
                setattr(target, field, value.replace(tzinfo=timezone.utc))

    event.listen(FuturesMarket, "load", _restore_utc)
    event.listen(FuturesOutcome, "load", _restore_utc)
    try:
        yield
    finally:
        event.remove(FuturesMarket, "load", _restore_utc)
        event.remove(FuturesOutcome, "load", _restore_utc)


class AsyncDB:
    def __init__(self, session: Session):
        self._session = session

    async def execute(self, query):
        return self._session.execute(query)


def _session_with(*cities) -> Session:
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng,
        tables=[
            FuturesMarket.__table__,
            FuturesOutcome.__table__,
            FuturesOddsSnapshot.__table__,
        ],
    )
    session = Session(eng)
    for mid, city, ladder in cities:
        session.add(
            FuturesMarket(
                id=mid,
                source="polymarket",
                external_id=f"poly-temp-{mid}",
                name=f"Highest temperature in {city} on {_TOMORROW:%B} {_TOMORROW.day}?",
                status="open",
                llm_sport_category="weather",
                resolution_date=NOW + timedelta(days=1),
                updated_at=FRESH,
            )
        )
        for i, (label, p) in enumerate(ladder):
            session.add(
                FuturesOutcome(
                    id=mid * 100 + i,
                    market_id=mid,
                    external_id=f"o-{mid}-{i}",
                    name=label,
                    current_probability=p,
                    last_updated=FRESH,
                )
            )
    session.commit()
    return session


def _served(session, name):
    cities = asyncio.run(get_cities(AsyncDB(session)))
    city = next(c for c in cities if c["name"] == name)
    return city, {b["label"]: b for b in city["high"]["dist"]}


def test_houston_prints_the_pages_39_not_the_raw_46():
    city, dist = _served(_session_with((62721461, "Houston", HOUSTON)), "Houston")

    assert dist["90-91°F"]["probability"] == pytest.approx(0.3892, abs=0.0006)
    assert dist["90-91°F"]["prob"] == 39
    assert sum(b["probability"] for b in city["high"]["dist"]) == pytest.approx(
        1.0, abs=0.005
    )
    # `prob` and `probability` stay one number on two scales (#6616).
    for b in city["high"]["dist"]:
        assert b["prob"] == round(b["probability"] * 100)
    # The mode is an argmax; a single divisor cannot move it.
    assert city["high"]["mode"] == 90.5


def test_a_coherent_ladder_the_page_prints_raw_stays_raw():
    """Control: the squeeze is the page's gate, not "always sum to 1"."""
    _, dist = _served(_session_with((62721466, "New York", NEW_YORK)), "New York")

    assert dist["72-73°F"]["probability"] == pytest.approx(0.375)
    assert dist["72-73°F"]["prob"] == 38


def test_a_withheld_leg_turns_the_squeeze_off_as_it_does_on_the_page(monkeypatch):
    """#7103: the page refuses the squeeze once it has withheld a leg."""

    async def _one_withheld(db, market):
        return {market.outcomes[0].id}

    monkeypatch.setattr(league_futures, "_page_withheld_outcome_ids", _one_withheld)
    _, dist = _served(_session_with((62721461, "Houston", HOUSTON)), "Houston")

    assert dist["90-91°F"]["probability"] == pytest.approx(0.455)
    assert dist["90-91°F"]["prob"] == 46


def test_a_failed_refusal_read_keeps_the_raw_ladder_and_the_other_cities(monkeypatch):
    async def _boom(db, market):
        if market.id == 62721461:
            raise RuntimeError("poison board")
        return set()

    monkeypatch.setattr(league_futures, "_page_withheld_outcome_ids", _boom)
    session = _session_with(
        (62721461, "Houston", HOUSTON),
        (62721464, "Miami", [("84-85°F", 0.39), ("86-87°F", 0.45), ("88-89°F", 0.28)]),
    )
    cities = asyncio.run(get_cities(AsyncDB(session)))
    by_name = {c["name"]: {b["label"]: b for b in c["high"]["dist"]} for c in cities}

    assert by_name["Houston"]["90-91°F"]["probability"] == pytest.approx(0.455)
    # The healthy sibling is still squeezed (gotcha #42).
    assert sum(b["probability"] for b in by_name["Miami"].values()) == pytest.approx(
        1.0, abs=0.005
    )
