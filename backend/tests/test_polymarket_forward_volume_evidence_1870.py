"""#1870 — the forward Polymarket path stores zero, unknown and positive activity as three facts.

Two writer defects, reproduced by executing the real writer on 2026-10-01
(``artifacts/1870-independent-volume-replay-20261001/HANDBACK.md``):

* Gamma's recorded ``volume="0"`` parsed to ``0.0`` and then BOTH legs wrote
  NULL, because the writer tested ``if market.volume`` and zero is falsy. So
  "nothing traded" and "we never asked" were stored identically — Polymarket had
  exactly 0 rows at ``volume = 0`` where Kalshi had 5%.
* A positive ``0.25`` was written as integer 0, which
  ``calibration_trade_evidence`` reads as untraded: positive activity stored as
  zero trading.

Every assertion reads what the shipping code handed the session — bound INSERT
values, the conflict-update set, and the metadata merge — off the real
``_process_event_batch`` (parser tests call the real ``_parse_market``). None of
it reads source text.

Scope limit, stated so nobody reads more into a green run: this repairs the
FORWARD writer only. The recovery utility and the calibration consumer (which
reads the scalar and ignores ``volume_evidence``) are Calibration's and are not
touched here; a fractional amount therefore reads as scalar UNKNOWN downstream,
with the exact traded amount in the receipt — never as untraded.
"""

from __future__ import annotations

import contextlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import pytest
from sqlalchemy.dialects import postgresql

from app.services.polymarket_api import (
    PolymarketAPIService,
    PolymarketEvent,
    PolymarketMarket,
)
from app.tasks.polymarket import (
    POLYMARKET_CONDITION_VOLUME_PROBE,
    polymarket_activity_volume,
)
from tests.test_polymarket_under_snapshot_book_p097 import (
    RecordingSession,
    _bound_params,
)

NOW = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)
CID = "0x1870aa"
OTHER_CID = "0x1870bb"


# ── the parser ────────────────────────────────────────────────────────────


def _gamma_market(**volume_fields) -> dict:
    """A Gamma market payload with only the volume fields varied."""
    payload = {
        "conditionId": CID,
        "question": "Will it happen?",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.6", "0.4"]',
        "clobTokenIds": '["1", "2"]',
    }
    payload.update(volume_fields)
    return payload


def _parsed_volume(**volume_fields) -> Optional[float]:
    market = PolymarketAPIService()._parse_market(_gamma_market(**volume_fields))
    assert market is not None, "the parser refused the whole market"
    return market.volume


class TestTheParserKeepsTheVenuesAmount:
    def test_a_recorded_string_zero_is_zero_not_unknown(self):
        assert _parsed_volume(volume="0") == 0.0

    def test_a_positive_amount_survives_exactly(self):
        assert _parsed_volume(volume="450.989666") == pytest.approx(450.989666)
        assert _parsed_volume(volume="0.25") == pytest.approx(0.25)

    def test_a_primary_zero_outranks_a_positive_fallback(self):
        assert _parsed_volume(volume="0", volumeNum=100) == 0.0

    def test_a_missing_or_null_primary_reads_the_fallback(self):
        assert _parsed_volume(volumeNum=812.5) == pytest.approx(812.5)
        assert _parsed_volume(volume=None, volumeNum="3") == pytest.approx(3.0)

    def test_both_absent_is_unknown(self):
        assert _parsed_volume() is None

    @pytest.mark.parametrize("bad", ["abc", "nan", "inf", "-5"])
    def test_a_malformed_primary_is_unknown_never_the_fallback(self, bad):
        assert _parsed_volume(volume=bad, volumeNum=100) is None

    def test_the_event_total_uses_the_same_rule(self):
        event = PolymarketAPIService()._parse_event(
            {"id": "e1", "title": "t", "volume": "0", "markets": []}
        )
        assert event is not None and event.volume == 0.0


# ── the classifier ────────────────────────────────────────────────────────


class TestTheClassifier:
    def test_zero_is_a_confirmed_zero(self):
        got = polymarket_activity_volume(0.0, observed_at=NOW)
        assert got.scalar == 0 and got.observed
        assert got.receipt["verdict"] == "confirmed_zero"

    def test_a_fraction_is_traded_with_a_null_scalar_never_zero(self):
        got = polymarket_activity_volume(0.25, observed_at=NOW)
        assert got.scalar is None and got.observed
        assert got.receipt["verdict"] == "traded"
        assert got.receipt["gamma_volume"] == pytest.approx(0.25)

    def test_a_large_amount_is_capped_not_overflowed(self):
        got = polymarket_activity_volume(9e12, observed_at=NOW)
        assert got.scalar == 2_000_000_000
        assert got.receipt["gamma_volume"] == pytest.approx(9e12)

    @pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -1.0])
    def test_unknown_writes_nothing(self, bad):
        got = polymarket_activity_volume(bad, observed_at=NOW)
        assert got == (None, False, None)

    def test_the_receipt_names_only_the_probe_this_path_ran(self):
        receipt = polymarket_activity_volume(3.0, observed_at=NOW).receipt
        assert receipt["probe"] == POLYMARKET_CONDITION_VOLUME_PROBE
        assert receipt["grain"] == "condition"
        assert receipt["fetched_at"] == NOW.isoformat()
        # No CLOB/trades call was made, so no trade count may be claimed.
        assert "n_trades" not in receipt


# ── the writer, executed ──────────────────────────────────────────────────


def _event(volume: Optional[float], *, event_volume: Optional[float] = 5_000.0):
    """One game event, two decomposed binary sub-markets, coherent books.

    The volume under test sits on ``CID``; ``OTHER_CID`` is a fixed control at
    a positive amount so a test can see the policy was applied per condition.
    """
    def _market(cid: str, question: str, vol: Optional[float]):
        return PolymarketMarket(
            condition_id=cid,
            question=question,
            outcomes=["Yes", "No"],
            outcome_prices=[0.61, 0.39],
            best_bid=0.60,
            best_ask=0.62,
            last_trade_price=0.61,
            volume=vol,
            active=True,
        )

    return PolymarketEvent(
        id="evt-1870",
        title="Yankees vs Red Sox",
        slug="yankees-red-sox",
        active=True,
        closed=False,
        neg_risk=False,
        tags=["Sports", "MLB", "Baseball"],
        start_date=datetime(2026, 10, 2, 23, 5, tzinfo=timezone.utc),
        volume=event_volume,
        markets=[
            _market(CID, "Yankees vs Red Sox moneyline", volume),
            _market(OTHER_CID, "Yankees vs Red Sox o/u 8.5 runs", 90_000.0),
        ],
    )


async def _run(monkeypatch, event: PolymarketEvent) -> RecordingSession:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks import polymarket as poly
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    session = RecordingSession()

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(poly, "get_task_session", _fake_session)
    stats: dict = defaultdict(int)
    stats["errors"] = []
    await poly._process_event_batch(
        [event],
        stats,
        FuturesMarket,
        FuturesOutcome,
        FuturesOddsSnapshot,
        pg_insert,
        probability_to_american,
        compute_market_tier,
    )
    assert not stats["errors"], f"writer raised: {stats['errors']}"
    return session


def _upserts(session: RecordingSession, table: str) -> dict[str, object]:
    """``external_id -> statement`` for every upsert on ``table``."""
    out: dict[str, object] = {}
    for stmt in session.statements:
        if getattr(getattr(stmt, "table", None), "name", None) != table:
            continue
        ext = _bound_params(stmt).get("external_id")
        if ext is not None and getattr(stmt, "_post_values_clause", None) is not None:
            out[ext] = stmt
    return out


def _conflict_set(stmt) -> dict:
    return {
        getattr(k, "key", k): v
        for k, v in stmt._post_values_clause.update_values_to_set
    }


_MISSING = object()


def _leg_volumes(session: RecordingSession, cid: str = CID) -> dict[str, tuple]:
    """``leg -> (INSERT volume, conflict-update volume or _MISSING)``."""
    outcomes = _upserts(session, "futures_outcomes")
    out = {}
    for leg in ("yes", "no"):
        stmt = outcomes.get(f"{cid}_{leg}")
        assert stmt is not None, f"the {leg} leg of {cid} was never written"
        update = _conflict_set(stmt)
        out[leg] = (
            _bound_params(stmt).get("volume"),
            update["volume"] if "volume" in update else _MISSING,
        )
    return out


def _market_stmt(session: RecordingSession, cid: str = CID):
    stmt = _upserts(session, "futures_markets").get(cid)
    assert stmt is not None, f"the sub-market row {cid} was never written"
    return stmt


def _inserted_receipt(session: RecordingSession, cid: str = CID):
    md = _bound_params(_market_stmt(session, cid)).get("market_metadata") or {}
    return md.get("volume_evidence")


def _merged_metadata_sql(session: RecordingSession, cid: str = CID) -> Optional[str]:
    """The conflict-update metadata merge, compiled with its literals inlined."""
    merge = _conflict_set(_market_stmt(session, cid)).get("market_metadata")
    if merge is None:
        return None
    return str(
        merge.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestTheWriterHarness:
    @pytest.mark.asyncio
    async def test_the_fixture_reaches_the_decomposed_writer(self, monkeypatch):
        """Guards against a vacuous green: both conditions and both legs land."""
        session = await _run(monkeypatch, _event(12.0))
        outcomes = _upserts(session, "futures_outcomes")
        for cid in (CID, OTHER_CID):
            assert {f"{cid}_yes", f"{cid}_no"} <= set(outcomes)


class TestTheWriterStoresThreeFacts:
    @pytest.mark.asyncio
    async def test_a_recorded_zero_survives_insert_and_update(self, monkeypatch):
        """RED before #1870: both legs bound NULL for Gamma's ``"0"``."""
        legs = _leg_volumes(await _run(monkeypatch, _event(0.0)))
        assert legs == {"yes": (0, 0), "no": (0, 0)}

    @pytest.mark.asyncio
    async def test_a_known_positive_amount_writes_its_integer(self, monkeypatch):
        legs = _leg_volumes(await _run(monkeypatch, _event(450.989666)))
        assert legs == {"yes": (450, 450), "no": (450, 450)}

    @pytest.mark.asyncio
    async def test_a_fraction_never_becomes_zero(self, monkeypatch):
        """RED before #1870: ``0.25`` bound integer 0 on both legs.

        The update writes NULL rather than omitting the column: a positive
        observation disproves a prior false zero, so it must clear it.
        """
        legs = _leg_volumes(await _run(monkeypatch, _event(0.25)))
        assert legs == {"yes": (None, None), "no": (None, None)}

    @pytest.mark.asyncio
    async def test_unknown_inserts_null_and_leaves_a_prior_reading(self, monkeypatch):
        legs = _leg_volumes(await _run(monkeypatch, _event(None)))
        assert legs == {"yes": (None, _MISSING), "no": (None, _MISSING)}

    @pytest.mark.asyncio
    async def test_the_policy_is_per_condition(self, monkeypatch):
        """The control condition keeps its own amount beside a zero."""
        session = await _run(monkeypatch, _event(0.0))
        assert _leg_volumes(session, OTHER_CID) == {
            "yes": (90_000, 90_000),
            "no": (90_000, 90_000),
        }

    @pytest.mark.asyncio
    async def test_the_parent_total_keeps_a_recorded_zero(self, monkeypatch):
        """RED before #1870: ``if event.volume`` dropped the parent's zero."""
        session = await _run(monkeypatch, _event(12.0, event_volume=0.0))
        parent = _market_stmt(session, "evt-1870")
        assert _bound_params(parent)["volume"] == 0


class TestTheReceiptAgreesWithTheScalar:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "amount, verdict", [(0.0, "confirmed_zero"), (0.25, "traded"), (450.5, "traded")]
    )
    async def test_the_inserted_receipt(self, monkeypatch, amount, verdict):
        receipt = _inserted_receipt(await _run(monkeypatch, _event(amount)))
        assert receipt is not None
        assert receipt["verdict"] == verdict
        assert receipt["gamma_volume"] == pytest.approx(amount)
        assert receipt["probe"] == POLYMARKET_CONDITION_VOLUME_PROBE
        assert receipt["grain"] == "condition"

    @pytest.mark.asyncio
    async def test_the_condition_amount_not_the_event_total(self, monkeypatch):
        receipt = _inserted_receipt(
            await _run(monkeypatch, _event(7.0, event_volume=5_000.0))
        )
        assert receipt["gamma_volume"] == pytest.approx(7.0)

    @pytest.mark.asyncio
    async def test_the_update_merges_the_receipt_and_keeps_other_keys(
        self, monkeypatch
    ):
        """The receipt rides the existing ``COALESCE(md,'{}') || …`` merge."""
        sql = _merged_metadata_sql(await _run(monkeypatch, _event(0.0)))
        assert sql is not None, "the conflict update never touches metadata"
        assert "coalesce(futures_markets.market_metadata" in sql.lower()
        assert "||" in sql
        assert "'volume_evidence'" in sql
        assert '"verdict": "confirmed_zero"' in sql
        # Sibling keys still travel beside it.
        assert "'polymarket_event_id'" in sql

    @pytest.mark.asyncio
    async def test_unknown_adds_no_receipt(self, monkeypatch):
        session = await _run(monkeypatch, _event(None))
        assert _inserted_receipt(session) is None
        sql = _merged_metadata_sql(session) or ""
        assert "volume_evidence" not in sql
        # The other condition's receipt is its own, not this one's.
        assert _inserted_receipt(session, OTHER_CID)["verdict"] == "traded"

    @pytest.mark.asyncio
    async def test_the_aggregate_parent_carries_no_condition_receipt(
        self, monkeypatch
    ):
        session = await _run(monkeypatch, _event(0.0))
        parent_md = _bound_params(_market_stmt(session, "evt-1870")).get(
            "market_metadata"
        ) or {}
        assert "volume_evidence" not in parent_md
