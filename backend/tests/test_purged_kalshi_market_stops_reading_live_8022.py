"""#8022: a question Kalshi has FORGOTTEN stops rendering as a live market.

## the defect

`https://bainluck.com/futures/109903` — "Iowa Democratic Governor nominee?" — is a
question we answered in July. Kalshi graded every leg and we stored its verdict:
Rob Sand `is_winner=true`, `resolution_source='api_settlement'`, the other two legs
authoritatively `false`, all in one transaction stamp. The page reads:

    99%
    Rob Sand
    Resolves Nov 3, 2027                     <- fourteen months away
    Prices update every 1-2 hours            <- directly above a 60-day-old number
    Last number 60 days ago

and 900px down the SAME page, the outcome list already prints **"Won"**. So the page
is holding the verdict and rendering it; only the hero and the chrome ignore it,
because every settled affordance is gated on `market.status === "resolved"`
(`app/futures/[id]/page.tsx:572`) and that column still says `open`.

**That frontend gate is correct and is NOT loosened** — #7870 settled it: a stray
`is_winner` must never let a live market claim a result. The stale thing is the
column, and 355 markets were in this state on 2026-09-22.

## why #7870's band 5 cannot reach them, BY DESIGN

Band 5 selects exactly these rows (`status <> 'resolved'` AND an authoritative
winner exists) and asks `GET /events/{ticker}`. All nine of the shopper's specimens
answer **HTTP 200 with `markets: []`** — the Kalshi EVENT is permanent, the MARKET
rows purge (gotcha #35) — and `all_terminal([])` is False on purpose, because an
absence is not a settlement (gotcha #53). Band 5 is healthy: its census cohort
(`FEDHIKE`, `KXMLBWINS-TB-26`, four `KXWNBAWINS-26*`) all flipped on production
between 01:39 and 08:09 on 2026-09-22. This is its named, held bucket.

## 🔴 the measurement that decides the SHAPE of this fix

The obvious repair is "flip when the event read comes back empty". It is
catastrophic, and this is how we know. Sizing this fix on 2026-09-22 I probed all
727 band-5 members on `GET /events/{t}?with_nested_markets=true` at concurrency 6
and got **727 of 727 empty** — a uniform answer across a population that must vary.
The control convicts the instrument, not the population:

    FEDHIKE        3 `finalized` markets at 13:5xZ  ->  0 minutes later
    KXGOVCA-26     2 markets one hour earlier       ->  0

No 429 at any point; every response a well-formed 200. **Kalshi expresses
rate-limiting on that endpoint as HTTP 200 with `markets: []`** — byte-for-byte the
shape of a retention purge. An "empty ⇒ settled" rule would have flipped the entire
727-row population the first time we were throttled.

## so the protocol is MARKET-CHANNEL-FIRST, and that is the whole safety argument

`app/services/settlement_probe.py:probe_kalshi` asks `GET /markets/{ticker}` and
consults the event ONLY if the market 404s. Probed on the WINNING LEG's own ticker
(`KXGOVIANOMD-26-RSAN` — a real market ticker, unlike our event-shaped
`external_id`), a live market answers on the first channel and the event is never
reached, so a soft-block on the events endpoint cannot manufacture a `PURGED`.

`TestASoftBlockOnTheEventsEndpointCannotSettleALiveMarket` is that measurement
written down, and `TestTheProbeIsAskedAboutTheWinningLegNotTheEvent` is the mutation
that would destroy it: pass the event ticker and the market channel 404s for every
row on earth, turning the protocol into the very "empty ⇒ settled" rule it exists to
refuse — while every other arm in this file still passes.

## this is not a grading write

`Disposition.PURGED` deliberately does not `licenses_grading()`, and nothing here
grades. `is_winner` was written by the venue as `api_settlement`; the only column
that moves is `futures_markets.status`, a lifecycle claim being brought into line
with a result we already hold and already render.
"""

from __future__ import annotations

import pytest

# NOT `from app.tasks import backfill_winners` — that resolves to the Celery task
# object the package re-exports, which carries none of the private functions below.
import app.tasks.backfill_winners as bw

from app.utils.settlement_truth import Disposition, ProbeOutcome


# ---------------------------------------------------------------- the rig


class _Result:
    def __init__(self, rowcount: int = 1):
        self.rowcount = rowcount

    def all(self):
        return []


class _RecordingSession:
    """Keeps the COMPILED SQL of every statement it is handed.

    A session that answers every UPDATE with `rowcount=1` proves a statement was
    issued and nothing about what it targets — delete the `source == 'kalshi'`
    clause, or `status != 'resolved'`, or point the UPDATE at `FuturesOutcome`, and
    such a rig still passes. Compiling with `literal_binds` is what lets the arms
    below assert the WHERE the production row actually depends on.
    """

    def __init__(self):
        self.statements: list[str] = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        try:
            sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        except Exception:
            sql = str(stmt)
        self.statements.append(sql)
        return _Result(1 if "UPDATE" in sql.upper() else 0)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None

    def market_status_updates(self) -> list[str]:
        return [
            s
            for s in self.statements
            if s.upper().startswith("UPDATE")
            and "futures_markets" in s
            and "status" in s
        ]


class _SessionCM:
    def __init__(self, session):
        self._session = session

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *a):
        return False


class _FakeClient:
    async def aclose(self):
        return None


def _outcome(disposition: Disposition) -> ProbeOutcome:
    """A ProbeOutcome the classifier could really have produced.

    `SETTLED` is constructed via the classifier rather than by hand because
    `ProbeOutcome.__post_init__` refuses a SETTLED outcome with no claim — a
    hand-built fake would raise and the arm would pass for the wrong reason.
    """
    if disposition is Disposition.SETTLED:
        from app.utils.settlement_truth import classify_kalshi

        return classify_kalshi(
            200, {"market": {"ticker": "X", "status": "finalized", "result": "yes"}}
        )
    return ProbeOutcome(disposition, reason=f"test: {disposition.value}")


async def _run(
    monkeypatch,
    *,
    candidates,
    probe_answers,
    session=None,
):
    """Drive the REAL `_resolve_purge_confirmed_markets`, venue stubbed.

    `probe_answers` is keyed on the ticker the production code chooses to ask
    about, so an arm can assert WHICH ticker was probed rather than only that some
    probe happened.
    """
    session = session or _RecordingSession()
    asked: list[str] = []

    async def _fake_probe(ticker, client):
        asked.append(ticker)
        if ticker not in probe_answers:
            raise AssertionError(
                f"production asked the venue about {ticker!r}, which this arm did "
                f"not stub; it stubbed {sorted(probe_answers)}"
            )
        answer = probe_answers[ticker]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(
        "app.services.settlement_probe.probe_kalshi", _fake_probe
    )
    monkeypatch.setattr(
        "app.services.settlement_probe.make_client", lambda *a, **k: _FakeClient()
    )
    monkeypatch.setattr(bw, "get_task_session", _SessionCM(session))

    stats: dict = {}
    await bw._resolve_purge_confirmed_markets(candidates, stats)
    return stats, session, asked


# The shopper's specimen, and its real winning leg.
IOWA = ("KXGOVIANOMD-26", "KXGOVIANOMD-26-RSAN")


# ------------------------------------------------------- the gate fires


@pytest.mark.asyncio
class TestAPurgedMarketWeAlreadyAnsweredStopsReadingLive:
    async def test_a_confirmed_purge_flips_the_market_to_resolved(self, monkeypatch):
        stats, session, _ = await _run(
            monkeypatch,
            candidates=[IOWA],
            probe_answers={IOWA[1]: _outcome(Disposition.PURGED)},
        )

        assert stats["status_resolved_purged"] == 1
        updates = session.market_status_updates()
        assert len(updates) == 1, session.statements
        sql = updates[0]
        # The WHERE the production row depends on, asserted from compiled SQL.
        assert "'kalshi'" in sql
        assert "KXGOVIANOMD-26" in sql
        assert "status != 'resolved'" in sql or "status IS DISTINCT FROM" in sql
        # COALESCE, not NOW(): a market resolved once and reopened keeps its FIRST
        # stamp. A mutation to a bare NOW() would silently rewrite settlement dates.
        assert "coalesce" in sql.lower()
        assert session.commits == 1

    async def test_nothing_is_graded_only_the_lifecycle_column_moves(
        self, monkeypatch
    ):
        """`PURGED` does not license grading, and this rail does not grade."""
        _, session, _ = await _run(
            monkeypatch,
            candidates=[IOWA],
            probe_answers={IOWA[1]: _outcome(Disposition.PURGED)},
        )
        for sql in session.statements:
            assert "futures_outcomes" not in sql, (
                "the purge rail touched futures_outcomes; PURGED does not license "
                f"a grading write (settlement_truth.licenses_grading): {sql}"
            )
            assert "is_winner" not in sql, sql


# --------------------------------------------- the gate holds, by disposition


@pytest.mark.asyncio
class TestASoftBlockOnTheEventsEndpointCannotSettleALiveMarket:
    """The 2026-09-22 measurement, written down as an executable arm.

    Kalshi answers a throttled `/events` read with 200 + `markets: []` — the purge
    shape. The market channel is what saves us: a live market answers there, so
    `probe_kalshi` never consults the event and the disposition is
    `OPEN_NO_SETTLEMENT`. If the protocol ever stops asking the market first, this
    arm is the one that goes red.
    """

    async def test_a_live_market_behind_an_empty_event_read_is_not_flipped(
        self, monkeypatch
    ):
        stats, session, _ = await _run(
            monkeypatch,
            candidates=[IOWA],
            probe_answers={IOWA[1]: _outcome(Disposition.OPEN_NO_SETTLEMENT)},
        )

        assert stats["status_resolved_purged"] == 0
        assert session.market_status_updates() == []
        assert session.commits == 0
        # Held BY NAME: "the venue says this is live" and "we were throttled" are
        # opposite facts and a single held-count would fuse them.
        assert stats["purge_held_open_no_settlement"] == 1

    async def test_being_throttled_costs_a_cycle_not_a_population(self, monkeypatch):
        """25 candidates, every probe rate-limited: zero rows move."""
        candidates = [(f"KXP-{i}", f"KXP-{i}-W") for i in range(25)]
        stats, session, _ = await _run(
            monkeypatch,
            candidates=candidates,
            probe_answers={
                t: _outcome(Disposition.RATE_LIMITED) for _, t in candidates
            },
        )

        assert stats["status_resolved_purged"] == 0
        assert session.market_status_updates() == []
        assert stats["purge_held_rate_limited"] == 25
        assert stats["purge_probed"] == 25


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "disposition",
    [
        Disposition.OPEN_NO_SETTLEMENT,
        Disposition.RATE_LIMITED,
        Disposition.TRANSPORT_ERROR,
        Disposition.AMBIGUOUS_EMPTY,
        Disposition.NOT_FOUND,
        Disposition.SETTLED,
    ],
)
async def test_only_purged_writes_every_other_disposition_holds(
    monkeypatch, disposition
):
    """`PURGED` is the ONLY disposition that may move a row.

    Enumerated rather than spot-checked because the failure mode is a widened
    predicate — `disposition is not OPEN_NO_SETTLEMENT`, say — which a single
    negative arm cannot see. `SETTLED` is in the list deliberately: it is the
    strongest venue answer there is and it STILL must not act here, because band
    5's own `all_terminal` branch owns that case and a second writer for it would
    be two rails racing on one column.
    """
    stats, session, _ = await _run(
        monkeypatch,
        candidates=[IOWA],
        probe_answers={IOWA[1]: _outcome(disposition)},
    )

    assert stats["status_resolved_purged"] == 0
    assert session.market_status_updates() == []
    assert stats[f"purge_held_{disposition.value}"] == 1


# ------------------------------------------------- the ticker that is asked


@pytest.mark.asyncio
class TestTheProbeIsAskedAboutTheWinningLegNotTheEvent:
    """The mutation that would turn this rail back into "empty ⇒ settled".

    Our `external_id` is an EVENT ticker (`KXGOVIANOMD-26`). `GET /markets/` on an
    event ticker 404s for every event that ever existed, so asking the probe about
    it would make the market channel a constant 404, push every row through to the
    event channel, and hand back `PURGED` for live markets and throttled reads
    alike. Every other arm in this file passes under that mutation — the stub would
    simply be keyed differently — which is why the asked-ticker is asserted here.
    """

    async def test_the_venue_is_asked_about_the_leg_ticker(self, monkeypatch):
        _, _, asked = await _run(
            monkeypatch,
            candidates=[IOWA],
            probe_answers={IOWA[1]: _outcome(Disposition.PURGED)},
        )
        assert asked == ["KXGOVIANOMD-26-RSAN"]
        assert "KXGOVIANOMD-26" not in asked


# ------------------------------------------------------------ robustness


@pytest.mark.asyncio
class TestOneBadProbeDoesNotWipeThePass:
    """Gotcha #42, on this rail: a healthy sibling must survive a raising probe."""

    async def test_a_raising_probe_is_counted_and_the_sibling_still_flips(
        self, monkeypatch
    ):
        good = ("KXGOOD-26", "KXGOOD-26-W")
        bad = ("KXBAD-26", "KXBAD-26-W")
        stats, session, _ = await _run(
            monkeypatch,
            candidates=[bad, good],
            probe_answers={
                bad[1]: RuntimeError("connection reset"),
                good[1]: _outcome(Disposition.PURGED),
            },
        )

        assert stats["purge_probe_errors"] == 1
        assert stats["status_resolved_purged"] == 1
        sql = session.market_status_updates()[0]
        assert "KXGOOD-26" in sql
        assert "KXBAD-26" not in sql


@pytest.mark.asyncio
class TestAnEmptyCandidateListIsNotAVenueCall:
    async def test_no_candidates_means_no_client_and_no_write(self, monkeypatch):
        def _explode(*a, **k):
            raise AssertionError("make_client was called with nothing to probe")

        monkeypatch.setattr("app.services.settlement_probe.make_client", _explode)
        stats: dict = {}
        await bw._resolve_purge_confirmed_markets([], stats)
        assert stats == {}


# ------------------------------------------------------------ the budget


def test_the_cycle_budget_is_bounded_and_smaller_than_band_fives():
    """The extra venue cost is a fixed ceiling per cycle, not per batch.

    Band 5 asks about `_STATUS_SYNC_MAX_TICKERS` events; this rail may add at most
    `_PURGE_CONFIRM_MAX_PROBES` x 2 calls on top. Pinned so a later widening is a
    deliberate edit against a stated bound rather than a drifting default — and
    pinned BELOW band 5's budget, because the 2026-09-22 measurement showed the
    throttle is real and silent.
    """
    assert bw._PURGE_CONFIRM_MAX_PROBES == 25
    assert bw._PURGE_CONFIRM_MAX_PROBES <= bw._STATUS_SYNC_MAX_TICKERS
    assert bw._PURGE_CONFIRM_CONCURRENCY == 3
    assert bw._PURGE_CONFIRM_CONCURRENCY < 5  # the grader's own semaphore
