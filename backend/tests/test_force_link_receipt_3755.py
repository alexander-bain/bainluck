"""#3755 — a hand-run link is as visible in the history as a matcher pass.

WHAT WAS WRONG. ``POST /api/admin/prediction-markets/force-link`` runs the real
matching pipeline — ``_find_matching_event`` plus the duplicate guard — and then
commits ``market.event_id`` directly, writing **no** row to
``market_match_receipts``. So a link made this way was real, correct and
invisible: no phase, no candidate list, no score, absent from
``/api/admin/match-receipts`` and from the link-change history. Four Polymarket
rows for the 9/8 US Open quarterfinals were linked through it at ~01:50Z on
2026-09-06 and the receipts table held 0 rows for them before AND after.

That is the #2705 hole wearing a different hat: "has no receipt" was supposed to
mean "the matcher never reached this row", and one endpoint could make it mean
"a human linked it correctly and told nobody".

THE FOUR LINES THESE TESTS HOLD:

1. **Every exit receipts, including the three refusals.** The scheduled matcher
   records its rejections; the hand tool recorded nothing at all. A ``return``
   with no receipt is the old silence.
2. **An attach carries NO actor, and that is deliberate.** ``actor`` in this
   module means *who ended or moved a link* — ``link_change_row`` keys the
   append-only history off exactly that. A fresh attach moved nothing, so an
   actor on it would invent a departure. The provenance lives in ``phase``.
   This is asserted, not left to a reviewer, because "add the actor too" is the
   obvious-looking change that would quietly corrupt the link-loss census.
3. **The record can never cost the thing it records.** A recording path that
   raises would fail a link the operator already committed. Proved by making
   the session blow up and asserting the caller still gets a number.
4. **The reason stays a closed enum**, so the refusals remain countable rather
   than becoming three free-text strings.
"""

from datetime import datetime, timezone

import pytest

from app.routes import admin_matching as am
from app.utils import match_receipts as mr

NOW = datetime(2026, 9, 7, 4, 0, tzinfo=timezone.utc)

MARKET_ROW = {
    "id": 60345165,
    "source": "polymarket",
    "external_id": "us-open-wta-sabalenka-noskova",
    "name": "US Open WTA: Aryna Sabalenka vs Linda Noskova",
}


# =============================================================================
# Part 1 — record_out_of_band_attempt, the writer the attach case had no
#          signature for. ``record_link_change_receipts`` needs a
#          ``previous_event_id``; an attach has none, which is why nobody wrote
#          one.
# =============================================================================


class _Result:
    def all(self):
        return []


@pytest.fixture()
def captured_receipts(monkeypatch):
    """Every receipt handed to the one funnel, in order."""
    seen: list = []

    async def _fake_flush(session, receipts, chunk=500):
        seen.extend(receipts)
        return len(receipts)

    async def _fake_verify(session, receipts):
        return 0

    monkeypatch.setattr(mr, "flush_receipts", _fake_flush)
    monkeypatch.setattr(mr, "verify_links_are_durable", _fake_verify)
    return seen


class _NullSessionFactory:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        pass

    def __call__(self):
        return self


@pytest.mark.asyncio
async def test_attach_receipt_carries_phase_and_no_actor(captured_receipts):
    written = await mr.record_out_of_band_attempt(
        MARKET_ROW,
        phase=mr.PHASE_ADMIN_REPAIR,
        linked_event_id=15306160,
        detail={"score": 26.5656},
        now=NOW,
        session_factory=_NullSessionFactory(),
    )

    assert written == 1
    (receipt,) = captured_receipts
    assert receipt.outcome == mr.OUTCOME_LINKED
    assert receipt.linked_event_id == 15306160
    assert receipt.phase == mr.PHASE_ADMIN_REPAIR
    assert receipt.market_id == MARKET_ROW["id"]
    assert receipt.detail["score"] == 26.5656

    # THE LOAD-BEARING ASSERTION. An actor here would put a phantom row in the
    # append-only link history and make an attach read as a departure from
    # somewhere it never was.
    assert receipt.actor is None
    assert receipt.previous_event_id is None
    assert mr.link_change_row(receipt) is None


@pytest.mark.asyncio
async def test_refusal_receipt_carries_a_closed_enum_reason(captured_receipts):
    written = await mr.record_out_of_band_attempt(
        MARKET_ROW,
        phase=mr.PHASE_ADMIN_REPAIR,
        reject_reason=mr.REJECT_NO_CANDIDATE,
        now=NOW,
        session_factory=_NullSessionFactory(),
    )

    assert written == 1
    (receipt,) = captured_receipts
    assert receipt.outcome == mr.OUTCOME_REJECTED
    assert receipt.reject_reason == mr.REJECT_NO_CANDIDATE
    assert receipt.reject_reason in mr.REJECT_REASONS
    assert receipt.linked_event_id is None


@pytest.mark.asyncio
async def test_an_unknown_reason_raises_in_the_callers_stack(captured_receipts):
    with pytest.raises(ValueError, match="unknown match reject reason"):
        await mr.record_out_of_band_attempt(
            MARKET_ROW,
            phase=mr.PHASE_ADMIN_REPAIR,
            reject_reason="looked_wrong",
            now=NOW,
            session_factory=_NullSessionFactory(),
        )
    assert captured_receipts == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"linked_event_id": 1, "reject_reason": mr.REJECT_NO_CANDIDATE},
    ],
    ids=["neither", "both"],
)
async def test_an_attempt_must_say_what_it_decided(kwargs, captured_receipts):
    with pytest.raises(ValueError, match="exactly one"):
        await mr.record_out_of_band_attempt(
            MARKET_ROW, phase=mr.PHASE_ADMIN_REPAIR, now=NOW,
            session_factory=_NullSessionFactory(), **kwargs,
        )
    assert captured_receipts == []


@pytest.mark.asyncio
async def test_the_record_never_costs_the_link_it_records(monkeypatch):
    """A committed link must not be undone by a failure to explain it."""

    class _Exploding:
        async def __aenter__(self):
            raise RuntimeError("receipts database is down")

        async def __aexit__(self, *exc):
            return False

        def __call__(self):
            return self

    written = await mr.record_out_of_band_attempt(
        MARKET_ROW,
        phase=mr.PHASE_ADMIN_REPAIR,
        linked_event_id=15306160,
        now=NOW,
        session_factory=_Exploding(),
    )
    assert written == 0


# =============================================================================
# Part 2 — the wiring. Part 1 can pass while the endpoint calls none of it,
#          which is exactly the state #3755 found the code in.
# =============================================================================


class _FakeMarket:
    def __init__(self):
        self.id = MARKET_ROW["id"]
        self.source = MARKET_ROW["source"]
        self.external_id = MARKET_ROW["external_id"]
        self.name = MARKET_ROW["name"]
        self.event_id = None


class _FakeDB:
    def __init__(self, market):
        self._market = market
        self.commits = 0

    async def execute(self, stmt):
        market = self._market

        class _R:
            def scalars(self):
                return self

            def first(self):
                return market

        return _R()

    async def commit(self):
        self.commits += 1


@pytest.fixture()
def force_link_harness(monkeypatch):
    """Drive the real endpoint with the pipeline stubbed, capturing receipts."""
    calls: list[dict] = []

    monkeypatch.setattr(am, "_check_admin_destructive", lambda *a, **k: None)

    async def _fake_receipt(market_row, **kwargs):
        calls.append({"market_row": market_row, **kwargs})
        return 1

    monkeypatch.setattr(mr, "record_out_of_band_attempt", _fake_receipt)

    from app.utils import prediction_market_matching as pmm_utils

    monkeypatch.setattr(
        pmm_utils, "extract_game_date_from_ticker", lambda *a, **k: None
    )
    return calls


def _configure(monkeypatch, *, matchup, matched, refusal):
    from app.tasks import prediction_market_matching as pmm
    from app.utils import prediction_market_matching as pmm_utils

    monkeypatch.setattr(
        pmm_utils, "extract_matchup_with_ticker_fallback", lambda *a, **k: matchup
    )

    async def _fake_find(*a, **k):
        return matched

    async def _fake_reason(*a, **k):
        return refusal

    monkeypatch.setattr(pmm, "_find_matching_event", _fake_find)
    monkeypatch.setattr(pmm, "_check_duplicate_kalshi_linkage_reason", _fake_reason)


MATCHED = {
    "event_id": 15306160,
    "home_team": "Aryna Sabalenka",
    "away_team": "Linda Noskova",
    "score": 26.5656,
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "matchup,matched,refusal,expected_status,expected_reason",
    [
        (None, None, None, "no_matchup", mr.REJECT_NO_MATCHUP),
        (("a", "b"), None, None, "no_event_found", mr.REJECT_NO_CANDIDATE),
        (
            ("a", "b"), MATCHED, "event_date",
            "duplicate_guard_blocked", mr.REJECT_EVENT_DATE_CONFLICT,
        ),
    ],
    ids=["no_matchup", "no_event_found", "duplicate_guard_blocked"],
)
async def test_every_refusal_exit_writes_a_receipt(
    monkeypatch, force_link_harness, matchup, matched, refusal,
    expected_status, expected_reason,
):
    _configure(monkeypatch, matchup=matchup, matched=matched, refusal=refusal)
    db = _FakeDB(_FakeMarket())

    result = await am.prediction_market_force_link(
        request=None, secret="x", external_id=MARKET_ROW["external_id"], db=db,
    )

    assert result["status"] == expected_status
    assert result["receipts_written"] == 1
    (call,) = force_link_harness
    assert call["reject_reason"] == expected_reason
    assert call["phase"] == mr.PHASE_ADMIN_REPAIR
    assert "linked_event_id" not in call
    # A refusal changed nothing, so nothing was committed.
    assert db.commits == 0


@pytest.mark.asyncio
async def test_the_successful_link_writes_a_receipt_carrying_its_score(
    monkeypatch, force_link_harness
):
    _configure(monkeypatch, matchup=("a", "b"), matched=MATCHED, refusal=None)
    market = _FakeMarket()
    db = _FakeDB(market)

    result = await am.prediction_market_force_link(
        request=None, secret="x", external_id=MARKET_ROW["external_id"], db=db,
    )

    assert result["status"] == "linked"
    assert result["event_id"] == MATCHED["event_id"]
    assert result["receipts_written"] == 1
    assert market.event_id == MATCHED["event_id"]
    assert db.commits == 1

    (call,) = force_link_harness
    assert call["linked_event_id"] == MATCHED["event_id"]
    assert call["phase"] == mr.PHASE_ADMIN_REPAIR
    # The score the endpoint returned is the score the history keeps — #3755's
    # own verification line.
    assert call["detail"]["score"] == MATCHED["score"]
    assert "reject_reason" not in call or call["reject_reason"] is None


@pytest.mark.asyncio
async def test_the_receipt_reads_the_market_before_the_commit_expires_it(
    monkeypatch, force_link_harness
):
    """gotcha #6: the ORM row is expired by ``commit()``.

    The receipt is written after it, so the endpoint must have copied the
    market's identity to scalars beforehand. Simulated by expiring the fake the
    way SQLAlchemy would — any attribute read after the commit raises.
    """
    _configure(monkeypatch, matchup=("a", "b"), matched=MATCHED, refusal=None)

    class _ExpiringMarket:
        """``_FakeMarket`` whose identity reads raise once ``expire()`` has run.

        Explicit properties rather than ``__getattribute__`` on purpose. The
        endpoint reads some fields through ``getattr(row, "x", None)``, which
        swallows an ``AttributeError`` and would let this test pass without
        proving anything — so the raise must NOT be an ``AttributeError``, and a
        special method raising anything else is itself a CodeQL finding
        (``py/unexpected-raise-in-special-method``). A property raising
        ``RuntimeError`` propagates through ``getattr``'s default and trips no
        rule. ``event_id`` stays a plain attribute: the endpoint writes it.
        """

        def __init__(self):
            self._expired = False
            self.event_id = None

        def expire(self):
            self._expired = True

        def _read(self, item):
            if self._expired:
                raise RuntimeError(f"instance is expired; {item} would lazy-load")
            return MARKET_ROW[item]

        @property
        def id(self):
            return self._read("id")

        @property
        def source(self):
            return self._read("source")

        @property
        def external_id(self):
            return self._read("external_id")

        @property
        def name(self):
            return self._read("name")

    market = _ExpiringMarket()

    class _ExpiringDB(_FakeDB):
        async def commit(self):
            await super().commit()
            market.expire()

    result = await am.prediction_market_force_link(
        request=None, secret="x", external_id=MARKET_ROW["external_id"],
        db=_ExpiringDB(market),
    )

    assert result["status"] == "linked"
    (call,) = force_link_harness
    assert call["market_row"]["id"] == MARKET_ROW["id"]
    assert call["market_row"]["name"] == MARKET_ROW["name"]
    assert call["market_row"]["source"] == MARKET_ROW["source"]
