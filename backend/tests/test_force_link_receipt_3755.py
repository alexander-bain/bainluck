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

from datetime import datetime, timedelta, timezone

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
        # The arm this table used to omit, and the omission is why the endpoint
        # spent event_date_conflict on both for a release. See the parity test
        # below for what the two reasons mean.
        (
            ("a", "b"), MATCHED, "sibling_date",
            "duplicate_guard_blocked", mr.REJECT_ALREADY_LINKED_ELSEWHERE,
        ),
    ],
    ids=[
        "no_matchup", "no_event_found",
        "duplicate_guard_blocked_event_date",
        "duplicate_guard_blocked_sibling_date",
    ],
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

    # CERT-2236: THE OPERATOR IS TOLD WHAT THE ROW IS TOLD. Asserting only the
    # stored reason and the response ``status`` is what let both duplicate arms
    # ship an identical response body — the database could tell a ticker-date
    # conflict from a sibling already on the event, and the person who ran the
    # tool could not, which is the one-word answer this endpoint exists to
    # replace. Asserted as equality with the stored reason rather than against a
    # second literal, so a mapping that drifts on one side fails here.
    assert result["reject_reason"] == expected_reason, (
        f"{expected_status} returned {result.get('reject_reason')!r} while "
        f"storing {expected_reason!r}: the history and the operator disagree"
    )


@pytest.mark.asyncio
async def test_the_two_guard_arms_are_two_different_reasons(
    monkeypatch, force_link_harness
):
    """The parity property, not the two cases above.

    The duplicate guard has two arms and the enum already documents them as a
    pair: ``REJECT_EVENT_DATE_CONFLICT`` names ``_REFUSAL_EVENT_DATE`` in its own
    docstring, and ``REJECT_ALREADY_LINKED_ELSEWHERE`` is defined as "a sibling
    ticker for the same game is already on that event". The scheduled matcher
    maps them apart; this hand-run endpoint spent one reason on both, so a
    sibling refusal entered ``market_match_receipts`` as a date conflict and
    #2706's ``GROUP BY reject_reason`` counted it in the wrong bucket for good.

    Asserted as *distinctness* rather than two literals so that collapsing the
    map back to a single reason fails here even if someone rewrites both rows of
    the table above to agree with the collapse.
    """
    from app.tasks import prediction_market_matching as pmm

    seen = {}
    returned = {}
    for arm in (pmm._REFUSAL_EVENT_DATE, pmm._REFUSAL_SIBLING_DATE):
        force_link_harness.clear()
        _configure(monkeypatch, matchup=("a", "b"), matched=MATCHED, refusal=arm)
        result = await am.prediction_market_force_link(
            request=None, secret="x", external_id=MARKET_ROW["external_id"],
            db=_FakeDB(_FakeMarket()),
        )
        assert result["status"] == "duplicate_guard_blocked"
        (call,) = force_link_harness
        # The raw refusal still travels in detail — the reason is a bucket, the
        # detail is the evidence, and #3755 wanted both.
        assert call["detail"]["refusal"] == arm
        # CERT-2236: the response says it too. While the enum was computed only
        # as an argument to the receipt call, this loop passed on two responses
        # that were byte-identical.
        assert result["reject_reason"] == call["reject_reason"]
        returned[arm] = result["reject_reason"]
        seen[arm] = call["reject_reason"]

    assert seen[pmm._REFUSAL_EVENT_DATE] != seen[pmm._REFUSAL_SIBLING_DATE], (
        "both guard arms wrote the same reject_reason, so the receipt history "
        "cannot tell a ticker-date conflict from a sibling already on the event"
    )
    assert returned[pmm._REFUSAL_EVENT_DATE] != returned[pmm._REFUSAL_SIBLING_DATE], (
        "both guard arms RETURNED the same reject_reason, so the operator who "
        "just ran the tool is told the link was refused and left to guess "
        "whether the date or a sibling refused it — opposite next steps"
    )
    assert seen[pmm._REFUSAL_EVENT_DATE] == mr.REJECT_EVENT_DATE_CONFLICT
    assert seen[pmm._REFUSAL_SIBLING_DATE] == mr.REJECT_ALREADY_LINKED_ELSEWHERE
    # Countable, not free text (line 4 of this module's contract).
    assert set(seen.values()) <= mr.REJECT_REASONS
    assert set(returned.values()) <= mr.REJECT_REASONS


def test_the_guard_arms_are_still_only_two():
    """The endpoint maps one arm by name and lets ``else`` take the rest.

    That is deliberate parity with the matcher's own call site rather than a
    second opinion about the mapping — but an ``else`` is a catch-all, so a
    THIRD refusal arm added upstream would be silently filed as
    ``already_linked_elsewhere`` and nothing above would go red. Key on the
    module that mints the arms, so the first new one fails here instead.

    ``_check_duplicate_kalshi_linkage_reason`` lives in lane1's matcher (D39).
    If this fails, the arm is theirs and the mapping is ours: add the case to
    the endpoint and to the table above — do not delete this test.
    """
    from app.tasks import prediction_market_matching as pmm

    arms = {n: v for n, v in vars(pmm).items() if n.startswith("_REFUSAL_")}
    assert arms == {
        "_REFUSAL_EVENT_DATE": "event_date",
        "_REFUSAL_SIBLING_DATE": "sibling_date",
        # #4965: the third arm. This test did its job — it went red when the arm
        # was added, and the endpoint mapping above was extended to name it
        # rather than let the ``else`` file it as a sibling collision. The
        # decision recorded: a venue-fixture conflict is a DATE conflict, so it
        # shares REJECT_EVENT_DATE_CONFLICT with `_REFUSAL_EVENT_DATE` and is
        # asserted to do so in `test_the_venue_fixture_arm_is_a_date_conflict`.
        "_REFUSAL_VENUE_FIXTURE": "venue_fixture",
    }, f"the duplicate guard's refusal arms changed: {arms}"


@pytest.mark.asyncio
async def test_the_venue_fixture_arm_is_a_date_conflict(
    monkeypatch, force_link_harness
):
    """#4965's arm must not enter the receipt history as a sibling collision.

    The mapping above is an ``else`` catch-all, so before this the new arm
    would have been filed as ``already_linked_elsewhere`` — #2706's
    ``GROUP BY reject_reason`` would have counted every Polymarket wrong-date
    refusal in the bucket that means "someone else got there first", which is
    the opposite operator instruction.
    """
    from app.tasks import prediction_market_matching as pmm
    from app.utils import match_receipts as mr

    _configure(
        monkeypatch, matchup=("a", "b"), matched=MATCHED,
        refusal=pmm._REFUSAL_VENUE_FIXTURE,
    )
    market = _FakeMarket()
    db = _FakeDB(market)

    result = await am.prediction_market_force_link(
        request=None, secret="x", external_id=MARKET_ROW["external_id"], db=db,
    )

    assert result["status"] == "duplicate_guard_blocked"
    assert result["reject_reason"] == mr.REJECT_EVENT_DATE_CONFLICT, (
        "a venue-fixture refusal was filed as a sibling collision"
    )
    (call,) = force_link_harness
    assert call["reject_reason"] == mr.REJECT_EVENT_DATE_CONFLICT
    assert call["detail"]["refusal"] == pmm._REFUSAL_VENUE_FIXTURE
    # The market must NOT have been linked.
    assert market.event_id != MATCHED["event_id"]


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


# =============================================================================
# Part 3 — the trace. #3755 made every exit WRITE a receipt; this part is about
#          what that receipt SAYS.
#
#          ``_find_matching_event`` already builds the whole explanation — the
#          window it searched, one row per event it retrieved, and the verdict
#          that dropped each — into a receipt handed to it, and it runs a
#          bounded probe that separates the two answers a NULL ``event_id``
#          conflates: "no event anywhere carries these names" (upstream has a
#          market we have no game for) and "the game IS in our events table and
#          our window excluded it" (ours, and fixable). The endpoint passed no
#          receipt and no probe budget, so all of it was discarded and the
#          operator got the bare word ``no_event_found`` with a blanket
#          ``no_candidate`` in the history — a matcher bug filed in the
#          upstream-gap bucket, the same wrong-bucket class Part 2 closed for
#          the duplicate guard's second arm.
#
#          THESE TESTS DRIVE THE REAL PIPELINE. Only the database is faked. The
#          matchup extractor is stubbed to a real ``MatchupInfo`` because these
#          are tests about the trace, not about name parsing; everything that
#          produces the trace — the two search passes, ``_score_candidates``,
#          the covering probe, ``_reason_from_traces`` — is production code.
#
#          The parity that makes this safe to do at all is asserted elsewhere
#          and deliberately not duplicated here:
#          ``test_match_receipts_2705.py::
#          test_score_candidates_returns_the_same_decision_with_and_without_a_
#          receipt`` holds that a receipt observes and does not steer.
# =============================================================================


PIPELINE_MARKET = {
    "id": 60345165,
    "source": "polymarket",
    "external_id": "us-open-wta-sabalenka-noskova",
    "name": "US Open WTA: Aryna Sabalenka vs Linda Noskova",
}


def _clock() -> datetime:
    """The endpoint stamps ``datetime.now(timezone.utc)`` and takes no injection.

    So every time in Part 3 is an OFFSET from the real clock, never from the
    frozen ``NOW`` the earlier parts use (gotcha #44: offset first, and never
    branch on the clock). Anchoring a candidate to a fixed 2026-09-07 while the
    scorer measures proximity to today makes the ranking a function of the date
    the suite runs — a nearer runner-up wins on a Monday and loses on a Tuesday.
    """
    return datetime.now(timezone.utc)


class _PipelineMarket:
    """The market row the pipeline reads, not just the four the endpoint copies."""

    def __init__(self):
        for k, v in PIPELINE_MARKET.items():
            setattr(self, k, v)
        self.event_id = None
        self.commence_time = _clock()
        self.llm_sport_category = "tennis"


class _Sport:
    def __init__(self, key):
        self.key = key


class _Event:
    def __init__(self, id, home, away, commence, status="scheduled",
                 sport_key="tennis_wta", external_id="odds-api-1"):
        self.id = id
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence
        self.status = status
        self.sport = _Sport(sport_key) if sport_key else None
        self.sport_id = 7
        self.external_id = external_id


class _ProbeRow:
    """What the probe's column-select hands back — no ORM entity, five fields."""

    def __init__(self, event):
        self.id = event.id
        self.home_team_name = event.home_team_name
        self.away_team_name = event.away_team_name
        self.commence_time = event.commence_time
        self.status = event.status


class _Rows:
    """One canned result, shaped for every access the pipeline makes of one."""

    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _ScriptedDB:
    """The endpoint's ``db`` AND the pipeline's session, answering in call order.

    Ordered rather than statement-sniffing on purpose: the order IS the
    contract being tested (market lookup, windowed pass, broad pass, probe),
    and a fake that inspects the SQL would keep passing after the endpoint
    stopped running one of those passes.
    """

    def __init__(self, *results):
        self._results = list(results)
        self.commits = 0
        self.queries = 0

    async def execute(self, stmt):
        self.queries += 1
        if not self._results:
            raise AssertionError(f"unscripted query #{self.queries}")
        return _Rows(self._results.pop(0))

    async def commit(self):
        self.commits += 1


@pytest.fixture()
def real_pipeline(monkeypatch):
    """Everything real except the database and the name parser."""
    from app.utils import prediction_market_matching as pmm_utils
    from app.utils.prediction_market_matching import MatchupInfo

    matchup = MatchupInfo(
        "Aryna Sabalenka", "Linda Noskova",
        yes_team="Aryna Sabalenka", format_type="bare_matchup",
    )
    monkeypatch.setattr(
        pmm_utils, "extract_matchup_with_ticker_fallback", lambda *a, **k: matchup
    )
    return matchup


async def _force_link(db):
    return await am.prediction_market_force_link(
        request=None, secret="x",
        external_id=PIPELINE_MARKET["external_id"], db=db,
    )


@pytest.mark.asyncio
async def test_a_game_we_carry_is_not_reported_as_a_game_we_lack(
    force_link_harness, real_pipeline
):
    """THE SHIP. The event exists; the ±48h window excluded it.

    Before this change the operator was told ``no_event_found`` and the history
    was told ``no_candidate`` — "upstream has a market we have no game for" —
    for a row sitting in ``events`` ten days out. Those two answers have
    opposite fixes, and only one of them is ours.
    """
    from app.utils import match_receipts as _mr

    real_event = _Event(
        15306160, "Aryna Sabalenka", "Linda Noskova", _clock() + timedelta(days=10),
    )
    db = _ScriptedDB(
        [_PipelineMarket()],   # the endpoint's own lookup
        [],                    # pass 1: windowed — nothing inside ±48h
        [],                    # pass 2: broad — nothing scheduled in ±14d either
        [_ProbeRow(real_event)],  # the covering probe: but the game IS here
    )

    result = await _force_link(db)

    assert result["status"] == "no_event_found"
    assert result["reject_reason"] == _mr.REJECT_OUTSIDE_TIME_WINDOW, (
        "a game in our own events table was reported as an upstream gap"
    )
    assert result["reject_reason"] != _mr.REJECT_NO_CANDIDATE

    # The named event, not just a count.
    assert result["candidates_considered"] == 1
    (candidate,) = result["candidates"]
    assert candidate["event_id"] == 15306160
    assert candidate["verdict"] == _mr.REJECT_OUTSIDE_TIME_WINDOW
    # Coverage is what separates a candidate from a one-token coincidence.
    assert candidate["sides_matched"] == candidate["sides_named"] == 2

    # The window that excluded it, so the reader can see WHICH window to argue
    # with — and the probe's own arm, so a saturated broad arm could never be
    # mistaken for a covering hit.
    assert result["search"]["window_start"] and result["search"]["window_end"]
    assert result["search"]["candidate_probe"]["arm"] == "covering"
    assert result["search"]["candidate_probe"]["covering_hits"] == 1

    # Nothing was linked, so nothing was committed.
    assert db.commits == 0
    # Every scripted query was consumed: the probe really ran.
    assert db.queries == 4

    # And the HISTORY says the same thing the operator was shown.
    (call,) = force_link_harness
    assert call["reject_reason"] == _mr.REJECT_OUTSIDE_TIME_WINDOW
    assert [c.event_id for c in call["candidates"]] == [15306160]
    assert call["detail"]["candidate_probe"]["covering_hits"] == 1


@pytest.mark.asyncio
async def test_the_probe_that_draws_that_distinction_is_actually_asked_for(
    force_link_harness, real_pipeline
):
    """Without ``probe_allowed`` the pipeline records ``skipped_budget``.

    Anchored on the receipt's own detail rather than on the kwarg, so it holds
    through a rename: the scheduled matcher rations the probe across thousands
    of rows a cycle, and a hand tool that inherited that rationing would be the
    WEAKER of the two diagnoses for no reason.
    """
    db = _ScriptedDB([_PipelineMarket()], [], [], [], [])
    result = await _force_link(db)

    assert result["status"] == "no_event_found"
    assert result["search"].get("candidate_probe") != "skipped_budget"
    # Nothing anywhere carries these names — the honest upstream-gap bucket.
    assert result["reject_reason"] == "no_candidate"
    assert result["search"]["candidate_probe"]["hits"] == 0


@pytest.mark.asyncio
async def test_a_losing_candidate_is_named_with_the_gate_that_dropped_it(
    force_link_harness, real_pipeline
):
    """Rows came back and lost. The trace says which gate, per row."""
    db = _ScriptedDB(
        [_PipelineMarket()],
        [  # retrieved on one shared surname, neither is the game
            _Event(11, "Aryna Sabalenka", "Iga Swiatek", _clock() + timedelta(hours=2)),
            _Event(12, "Coco Gauff", "Linda Noskova", _clock() + timedelta(hours=3)),
        ],
        [],   # broad pass
        [],   # probe, covering arm: nothing carries BOTH sides
        [],   # probe, broad arm: the fallback the covering miss triggers
    )

    result = await _force_link(db)

    assert result["status"] == "no_event_found"
    assert result["candidates_considered"] >= 2
    by_id = {c["event_id"]: c for c in result["candidates"]}
    assert set(by_id) >= {11, 12}
    for event_id in (11, 12):
        assert by_id[event_id]["verdict"] == "name_mismatch"
        # One side each — a retrieval coincidence, and the payload says so
        # rather than leaving the reader to assume both sides were present.
        assert by_id[event_id]["sides_matched"] == 1
        assert by_id[event_id]["sides_named"] == 2


@pytest.mark.asyncio
async def test_the_chosen_event_is_traced_against_what_it_beat(
    force_link_harness, real_pipeline
):
    """An attach gets the trace too — "why THIS event" is about the runners-up.

    Also gotcha #6, one step past the Part 2 test: ``commit()`` expires every
    ORM object in the session, including the candidate ``Event`` rows, and the
    response is assembled after it. It holds because a trace copies scalars at
    trace time; if it ever held live rows this would raise instead of assert.
    """
    db = _ScriptedDB(
        [_PipelineMarket()],
        [
            _Event(21, "Aryna Sabalenka", "Linda Noskova", _clock() + timedelta(hours=1)),
            _Event(22, "Aryna Sabalenka", "Linda Noskova", _clock() + timedelta(hours=30)),
        ],
    )

    result = await _force_link(db)

    assert result["status"] == "linked"
    assert result["event_id"] == 21
    assert db.commits == 1

    verdicts = {c["event_id"]: c["verdict"] for c in result["candidates"]}
    assert verdicts == {21: "chosen", 22: "lower_score"}
    assert result["candidates_considered"] == 2

    (call,) = force_link_harness
    assert call["linked_event_id"] == 21
    assert {c.event_id for c in call["candidates"]} == {21, 22}


@pytest.mark.asyncio
async def test_no_matchup_reports_no_candidate_list_at_all(
    monkeypatch, force_link_harness
):
    """"We never searched" and "we searched and found nothing" are different.

    An empty ``candidates: []`` on this exit would render the first as the
    second, which is gotcha #53 in miniature — the same body for an absence and
    for a result.
    """
    from app.utils import prediction_market_matching as pmm_utils

    monkeypatch.setattr(
        pmm_utils, "extract_matchup_with_ticker_fallback", lambda *a, **k: None
    )
    result = await _force_link(_ScriptedDB([_PipelineMarket()]))

    assert result["status"] == "no_matchup"
    assert "candidates" not in result
    assert "candidates_considered" not in result
    assert "search" not in result


@pytest.mark.asyncio
async def test_a_truncated_candidate_list_is_legible_as_truncated(
    monkeypatch, force_link_harness
):
    """``candidates`` is capped; ``candidates_considered`` is not.

    A capped list with no raw count reads as "that was all of them", which is
    exactly the reading that turned five saturated probe rows into a verdict
    (gotcha #53). Driven through a stub of the DB-bound search so the count can
    exceed the cap without inventing a plausible twelve-way retrieval.
    """
    from app.tasks import prediction_market_matching as pmm
    from app.utils import prediction_market_matching as pmm_utils
    from app.utils.prediction_market_matching import MatchupInfo

    monkeypatch.setattr(
        pmm_utils, "extract_matchup_with_ticker_fallback",
        lambda *a, **k: MatchupInfo("a", "b", yes_team="a", format_type="bare_matchup"),
    )

    overflow = mr.MAX_TRACE_CANDIDATES + 4

    async def _fake_find(session, matchup, market, now, **kwargs):
        receipt = kwargs["receipt"]
        for i in range(overflow):
            receipt.trace(mr.CandidateTrace(
                event_id=100 + i, verdict="lower_score", score=float(i),
                sides_matched=2, sides_named=2,
            ))
        receipt.reject(mr.REJECT_NAME_SCORE_BELOW)
        return None

    monkeypatch.setattr(pmm, "_find_matching_event", _fake_find)

    result = await _force_link(_ScriptedDB([_PipelineMarket()]))

    assert result["candidates_considered"] == overflow
    assert len(result["candidates"]) == mr.MAX_TRACE_CANDIDATES
    assert result["candidates_considered"] > len(result["candidates"])
    # Best-scoring first, so the cap drops the least interesting rows.
    assert result["candidates"][0]["score"] == float(overflow - 1)
    # The pipeline's own reason survived, rather than being flattened.
    assert result["reject_reason"] == mr.REJECT_NAME_SCORE_BELOW


@pytest.mark.asyncio
async def test_the_stored_row_keeps_the_trace_not_just_the_response(
    monkeypatch, captured_receipts
):
    """The writer, end to end: candidates reach ``market_match_receipts``.

    Part 3's other tests stub the writer to read its arguments. This one runs
    the real :func:`record_out_of_band_attempt` and asserts the receipt handed
    to the flush carries the trace, because a response-only trace is a
    diagnosis that evaporates when the operator closes the tab.
    """
    traces = [
        mr.CandidateTrace(event_id=31, verdict="lower_score", score=9.5),
        mr.CandidateTrace(event_id=32, verdict="chosen", score=26.5),
    ]

    written = await mr.record_out_of_band_attempt(
        MARKET_ROW,
        phase=mr.PHASE_ADMIN_REPAIR,
        linked_event_id=32,
        candidates=traces,
        now=NOW,
        session_factory=_NullSessionFactory(),
    )

    assert written == 1
    (receipt,) = captured_receipts
    assert [c.event_id for c in receipt.candidates] == [31, 32]
    # The chosen row is never dropped by the cap, and leads the stored payload.
    payload = receipt.candidate_payload()
    assert payload[0]["event_id"] == 32
    assert payload[0]["verdict"] == "chosen"
    # And the row that actually goes to Postgres carries it.
    assert receipt.to_row()["candidates"] == payload


def test_the_detail_the_operator_reads_is_the_detail_the_row_stores():
    """One coercion, used by both, so the two renderings cannot drift.

    ``_find_matching_event`` puts raw ``datetime`` window bounds in
    ``receipt.detail``; the stored row runs them through ``jsonable`` and so
    does the response. If the endpoint grew its own converter, a reader
    comparing a screenshot to a receipt row would be comparing two formats.
    """
    detail = {"window_start": NOW, "nested": {"end": NOW}, "list": [NOW]}
    assert mr.jsonable(detail) == {
        "window_start": NOW.isoformat(),
        "nested": {"end": NOW.isoformat()},
        "list": [NOW.isoformat()],
    }

    receipt = mr.MatchReceipt(
        market_id=1, source="polymarket", external_id="x", market_name="x",
        phase=mr.PHASE_ADMIN_REPAIR, attempted_at=NOW,
    )
    receipt.reject(mr.REJECT_NO_CANDIDATE, **detail)
    assert receipt.to_row()["detail"] == mr.jsonable(receipt.detail)


# =============================================================================
# Part 4 — the crash Part 3 walked into. Not a new feature: a live 500 that
#          shipped in 36c87611 and passed a cert, because every test in Parts 1
#          and 2 stubs the matchup as a TUPLE and the real parser returns a
#          ``MatchupInfo``.
#
#          ``detail={"matchup": list(matchup) if matchup else None}`` on the
#          ``no_event_found`` exit. ``MatchupInfo`` defines ``__slots__`` and
#          neither ``__iter__`` nor ``__bool__``, so the guard was always true
#          and ``list()`` always raised — and because the ``await _receipt(...)``
#          it sat inside was an argument to the same call, the receipt #3755
#          exists to write was never written either. Every hand-run force-link
#          on a market the matcher could not place returned HTTP 500 and
#          recorded nothing, which is the exact silence this file was opened to
#          end, reinstated by the fix for it.
# =============================================================================


def test_matchupinfo_is_not_iterable_and_is_always_truthy():
    """Key on the type that MINTS the value, not on the call site that broke.

    Two properties, both load-bearing and neither obvious from a call site:
    a ``MatchupInfo`` cannot be spread, unpacked or ``list()``-ed, and it can
    never be falsy — so an ``if matchup`` in front of such an expression buys
    nothing at all. If someone gives the class an ``__iter__`` this test goes
    red and the reader is told the constraint has moved, rather than a crash
    quietly becoming legal again somewhere else.
    """
    from app.utils.prediction_market_matching import MatchupInfo

    matchup = MatchupInfo("a", "", yes_team="a", format_type="will_win")
    assert not hasattr(MatchupInfo, "__iter__")
    assert not hasattr(MatchupInfo, "__bool__")
    assert not hasattr(MatchupInfo, "__len__")
    assert bool(matchup) is True, "an empty-team_b matchup is STILL truthy"
    with pytest.raises(TypeError):
        list(matchup)


@pytest.mark.asyncio
async def test_the_unmatched_exit_survives_the_real_matchup_type(
    force_link_harness, real_pipeline
):
    """The regression itself: this exit, with the type production hands it.

    Part 3's tests would also go red on a reintroduction, but this one names
    the failure so the next reader does not have to infer it from a probe
    assertion. The parse still reaches the row — under ``team_a``/``team_b``,
    the names ``_find_matching_event`` already writes, so both writers of
    ``market_match_receipts`` describe a matchup the same way.
    """
    db = _ScriptedDB([_PipelineMarket()], [], [], [], [])

    result = await _force_link(db)  # raised TypeError before the fix

    assert result["status"] == "no_event_found"
    (call,) = force_link_harness
    assert call["detail"]["team_a"] == "Aryna Sabalenka"
    assert call["detail"]["team_b"] == "Linda Noskova"
    assert call["detail"]["format_type"] == "bare_matchup"
    # The broken key never once reached Postgres, so nothing consumes it.
    assert "matchup" not in call["detail"]


# =============================================================================
# Part 5 — CERT-2236. The parity Parts 1-4 asserted for ONE exit and claimed for
#          all of them.
#
#          #3755's subject line is "returns AND stores". Part 3 held it for
#          ``no_event_found`` — the only exit that passed ``trace.detail`` to
#          the writer — while a link and a duplicate refusal stored just their
#          own ``score`` / ``refusal`` fields. So the response published the
#          searched window on all three exits and the durable row carried it on
#          one, and the row was the thinner of the pair precisely when the
#          attempt SUCCEEDED: "which window found this, and what else was in
#          it" is the question a wrong attach gets asked a week later, by which
#          time the response is gone and the row is all there is.
#
#          These drive the REAL pipeline for the same reason Part 3 does — with
#          the search stubbed, ``trace.detail`` is empty and every assertion
#          below passes vacuously on the broken code (the trap in
#          r_a_component_that_no_ops_on_an_unrecognised_fixture...). The
#          window keys asserted are the ones ``_find_matching_event`` really
#          writes, so a rename upstream surfaces here instead of silently
#          emptying the guard.
# =============================================================================


WINDOW_KEYS = {"window_start", "window_end", "windowed_candidates", "scoring_ref"}


def _assert_search_reached_the_row(result, call, exit_name):
    """The response's ``search`` and the stored ``detail`` are one account.

    Compared through ``jsonable`` because the endpoint merges the RAW
    ``trace.detail`` into the receipt (datetimes and all) and the row coerces on
    the way to JSONB, while the response coerces on the way out — one function,
    two call sites, asserted equal rather than assumed so.
    """
    stored = mr.jsonable(call["detail"])
    assert WINDOW_KEYS <= set(stored), (
        f"the {exit_name} receipt dropped the searched window "
        f"{sorted(WINDOW_KEYS - set(stored))}: the operator was shown a window "
        f"the history cannot reproduce"
    )
    for key, value in result["search"].items():
        assert stored[key] == value, (
            f"{exit_name}: response search[{key!r}]={value!r} but the stored "
            f"row says {stored.get(key)!r}"
        )


@pytest.mark.asyncio
async def test_a_hand_made_attach_records_the_window_that_found_it(
    force_link_harness, real_pipeline
):
    """THE REPAIR, success arm. A link stores the search, not only its score."""
    db = _ScriptedDB(
        [_PipelineMarket()],
        [
            _Event(21, "Aryna Sabalenka", "Linda Noskova", _clock() + timedelta(hours=1)),
            _Event(22, "Aryna Sabalenka", "Linda Noskova", _clock() + timedelta(hours=30)),
        ],
    )

    result = await _force_link(db)

    assert result["status"] == "linked"
    (call,) = force_link_harness
    assert call["linked_event_id"] == 21
    _assert_search_reached_the_row(result, call, "linked")
    # The window did not displace the exit's own fields: merged BEFORE them.
    assert call["detail"]["score"] == pytest.approx(result["score"])
    assert call["detail"]["home_team"] == "Aryna Sabalenka"
    assert call["detail"]["team_a"] == "Aryna Sabalenka"


@pytest.mark.asyncio
async def test_a_duplicate_refusal_records_the_window_and_names_its_arm(
    monkeypatch, force_link_harness, real_pipeline
):
    """THE REPAIR, refusal arm — both halves of the BLOCK in one run.

    The guard itself is lane1's (D39) and is stubbed; what is under test is the
    endpoint's handling of its answer. The pipeline that BUILT the trace is
    real, so ``trace.detail`` is genuinely populated and the parity assertion
    has something to fail on.
    """
    from app.tasks import prediction_market_matching as pmm

    async def _refuse(*a, **k):
        return pmm._REFUSAL_SIBLING_DATE

    monkeypatch.setattr(pmm, "_check_duplicate_kalshi_linkage_reason", _refuse)

    db = _ScriptedDB(
        [_PipelineMarket()],
        [_Event(21, "Aryna Sabalenka", "Linda Noskova", _clock() + timedelta(hours=1))],
    )

    result = await _force_link(db)

    assert result["status"] == "duplicate_guard_blocked"
    assert result["event_id"] == 21
    # The refused link is not made, and the trace survives the refusal.
    assert db.commits == 0
    assert result["reject_reason"] == mr.REJECT_ALREADY_LINKED_ELSEWHERE

    (call,) = force_link_harness
    _assert_search_reached_the_row(result, call, "duplicate_guard_blocked")
    assert call["detail"]["refusal"] == pmm._REFUSAL_SIBLING_DATE
    assert call["detail"]["candidate_event_id"] == 21
    # It considered a real candidate and says so — a refusal is not an absence.
    assert [c["event_id"] for c in result["candidates"]] == [21]


@pytest.mark.asyncio
async def test_every_refusal_exit_returns_the_enum_the_row_will_group_by(
    monkeypatch, force_link_harness
):
    """The property behind Part 2's table: no refusal answers with a status alone.

    Part 2 checks each exit it knows about. This checks the RULE — that a
    response saying the link did not happen always carries the countable reason,
    so a caller can read ``reject_reason`` without first learning which statuses
    subdivide and which do not. ``duplicate_guard_blocked`` subdivides; that is
    what the BLOCK found, and a fourth exit added later would repeat it.
    """
    from app.tasks import prediction_market_matching as pmm

    exits = [
        (None, None, None),
        (("a", "b"), None, None),
        (("a", "b"), MATCHED, pmm._REFUSAL_EVENT_DATE),
        (("a", "b"), MATCHED, pmm._REFUSAL_SIBLING_DATE),
    ]

    for matchup, matched, refusal in exits:
        force_link_harness.clear()
        _configure(monkeypatch, matchup=matchup, matched=matched, refusal=refusal)
        result = await am.prediction_market_force_link(
            request=None, secret="x", external_id=MARKET_ROW["external_id"],
            db=_FakeDB(_FakeMarket()),
        )
        assert result["status"] != "linked"
        reason = result.get("reject_reason")
        assert reason in mr.REJECT_REASONS, (
            f"{result['status']} returned reject_reason={reason!r}, which is "
            f"not a countable reason the receipt history groups by"
        )
        (call,) = force_link_harness
        assert reason == call["reject_reason"]


@pytest.mark.asyncio
async def test_an_exit_specific_field_outranks_the_window_it_merges_over(
    monkeypatch, force_link_harness
):
    """The merge ORDER, pinned so the docstring is not the only thing asserting it.

    ``_detail`` puts the common window in first so an exit's own key of the same
    name wins. The two sets are disjoint today — this fails the moment they stop
    being, rather than letting the pipeline's value shadow the endpoint's and
    make a linked receipt report a score that is not the score it linked on.
    """
    from app.tasks import prediction_market_matching as pmm
    from app.utils import prediction_market_matching as pmm_utils
    from app.utils.prediction_market_matching import MatchupInfo

    monkeypatch.setattr(
        pmm_utils, "extract_matchup_with_ticker_fallback",
        lambda *a, **k: MatchupInfo("a", "b", yes_team="a", format_type="will_win"),
    )

    async def _fake_find(session, matchup, market, now, **kwargs):
        # A collision planted on purpose: the pipeline claims a `score` too.
        kwargs["receipt"].detail.update({"score": -1.0, "window_start": NOW})
        return MATCHED

    async def _no_refusal(*a, **k):
        return None

    monkeypatch.setattr(pmm, "_find_matching_event", _fake_find)
    monkeypatch.setattr(pmm, "_check_duplicate_kalshi_linkage_reason", _no_refusal)

    result = await _force_link(_ScriptedDB([_PipelineMarket()]))

    assert result["status"] == "linked"
    (call,) = force_link_harness
    assert call["detail"]["score"] == MATCHED["score"], (
        "the merged window overwrote the exit's own score: the receipt now "
        "reports a score the link was not made on"
    )
    # The non-colliding window key still came through.
    assert call["detail"]["window_start"] == NOW
