"""#5603 liveness half — a fight card stops wearing the LIVE pill ten hours early.

═══ THE DEFECT ═══

Read on production 2026-09-12 13:48Z, `GET /api/feed` served this concept card:

    name       "Fight Night: Silva vs Delgado"
    status     live                 ← the pulsing red ● LIVE pill
    headline   "Live"
    start_date 2026-09-12T23:45:00Z ← its own main event, TEN HOURS away

The card contradicts itself inside one payload, so it needs no screenshot to
grade. The control in the same feed is the Vuelta concept, correctly live since
08-22.

Cause. A card's token is a DATE (`event_commence_token` → `YYMONDD`), so every
bout on one UTC calendar day is one card, and `combat_status` opens the live
window at the card's first bout (#4505). The callers spelled that first bout
``bouts[0]`` — the earliest row in the token, in whatever state it is in. The
2026-09-12 MMA token held, ahead of the UFC card proper (16:00Z → 23:45Z):

    suspended  01:25Z  Neemias Santana vs Shawn Marcos Da Silva   (15308196)
    suspended  02:30Z  Vincius Pires vs Rafael Pereira            (15308197)
    suspended  10:00Z  Kennedy Rayomba vs Andrej Kalasnik         (15308904)

`earliest` came out 01:25Z, so the pill lit at 01:25Z for a card whose first
fight is at 16:00Z. Production carried ZERO live combat bouts at the time of the
read (36 scheduled, 6 suspended across MMA and boxing). Boxing's 26SEP12 token
had the same shape — three suspended bouts (01:30Z/02:25Z/03:00Z) in front of a
18:00Z card — so this was two cards, not one specimen.

═══ WHY THE OBVIOUS FILTER IS WRONG ═══

`_list_event_bouts` documents itself as returning "scheduled/live bouts" while
its query filters on nothing but `commence_time` — so the tempting repair is to
make the code match its own docstring and keep only `scheduled`/`live`.

That trades a false positive for a false negative. Once the prelims FINISH they
are `completed`, and the earliest surviving bout is in the future — the card
would drop to `upcoming` while the main card is on air. A card's window is the
span of the fights that actually happen, which includes the ones already fought.
So the rule here is a DENY-list of called-off statuses, and
`test_a_card_mid_run_with_finished_prelims_is_still_live` is the guard that
fails if anyone later "simplifies" it into an allow-list.

═══ SCOPE ═══

This fixes a window set by a bout that will not be fought. It does NOT fix
same-day cross-promotion grouping — a *completed* early bout from another
promotion still shares the date token and still drags the window back. That is
the key itself (#5602, lane1 under D35) and is deliberately untouched.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_boxing import BOXING_CONFIG
from app.utils.event_combat import (
    CombatEventAdapter,
    card_is_called_off,
    card_status_from_bouts,
    card_status_span,
    combat_status,
    fight_child_settled,
    list_card_concepts,
)
from app.utils.event_ufc import UFC_CONFIG


def _at(hour, *, day=12, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc)


class _MockScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def unique(self):
        return self


class _MockResult:
    """Kalshi market rows read via `.all()`; events rows via `.scalars().all()`."""

    def __init__(self, rows, event_rows):
        self._rows = rows
        self._event_rows = event_rows

    def all(self):
        return self._rows

    def scalars(self):
        return _MockScalars(self._event_rows)


class _MockDB:
    """Answers each of the card paths' reads with its own rows.

    Dispatch on the STATEMENT, not the access path. `build_event` reads the
    Kalshi markets with `.scalars().unique().all()` and the events bouts with
    `.scalars().all()` — one mock that answers both with the same list hands the
    bout rows back as markets, and the adapter then falls through to the
    events-only envelope. The call-site-2 test would still go green while
    proving nothing about call site 2.
    """

    def __init__(self, rows, event_rows=None, outcome_rows=None, market_rows=None):
        self._rows = rows
        self._event_rows = event_rows or []
        self._outcome_rows = outcome_rows or []
        self._market_rows = market_rows or []

    async def execute(self, statement=None, *_a, **_k):
        sql = str(statement) if statement is not None else ""
        if "futures_outcomes" in sql:
            return _MockResult(self._outcome_rows, [])
        if "futures_markets" in sql:
            return _MockResult(self._rows, self._market_rows)
        return _MockResult(self._rows, self._event_rows)


class _FakeOutcome:
    def __init__(self, name, probability=0.5):
        self.name = name
        self.outcome_name = name
        self.probability = probability
        self.current_probability = probability


class _FakeMarket:
    """Minimal FuturesMarket stand-in: a two-sided Kalshi fight on the card."""

    def __init__(self, id, external_id, name, commence, fighters):
        self.id = id
        self.external_id = external_id
        self.name = name
        self.commence_time = commence
        self.status = "open"
        self.outcomes = [_FakeOutcome(f) for f in fighters]
        self.market_metadata = {}
        self.event_id = None
        self.image_url = None
        self.volume_24h = None
        self.source = "kalshi"
        self.market_type = "fight"
        self.market_tier = 1
        self.hook_description = None
        self.group_id = None
        self.close_time = commence
        self.llm_sport_category = None
        self.resolution_source = None


class _FakeBout:
    """Minimal Event stand-in for the events-table schedule source."""

    def __init__(self, id, home, away, commence, status="scheduled"):
        self.id = id
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence
        self.status = status
        self.win_probability_sources = None


def bout(hour, status="scheduled", *, day=12, minute=0):
    """One bout on the 2026-09-12 token, as the callers hand them over."""
    return SimpleNamespace(
        commence_time=datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc),
        status=status,
    )


# The production card, in the order `bout_order_key` sorts it.
SPECIMEN = [
    bout(1, "suspended", minute=25),
    bout(2, "suspended", minute=30),
    bout(10, "suspended"),
    bout(16),  # the UFC card proper
    bout(18),
    bout(23, minute=45),  # main event
]


class TestTheSpecimen:
    def test_the_span_skips_the_three_suspended_bouts(self):
        first, last = card_status_span(SPECIMEN)
        assert first == datetime(2026, 9, 12, 16, tzinfo=timezone.utc)
        assert last == datetime(2026, 9, 12, 23, 45, tzinfo=timezone.utc)

    def test_the_card_reads_upcoming_at_the_hour_it_served_live(self):
        """13:48Z, the minute of the production read."""
        now = datetime(2026, 9, 12, 13, 48, tzinfo=timezone.utc)
        first, last = card_status_span(SPECIMEN)
        assert combat_status(last, now, first) == "upcoming"

    def test_and_it_really_did_say_live_before_this(self):
        """The un-filtered pair is the defect: this is what shipped."""
        now = datetime(2026, 9, 12, 13, 48, tzinfo=timezone.utc)
        unfiltered_first = SPECIMEN[0].commence_time
        unfiltered_last = SPECIMEN[-1].commence_time
        assert combat_status(unfiltered_last, now, unfiltered_first) == "live"

    def test_the_pill_still_lights_when_the_card_actually_starts(self):
        now = datetime(2026, 9, 12, 16, 1, tzinfo=timezone.utc)
        first, last = card_status_span(SPECIMEN)
        assert combat_status(last, now, first) == "live"


class TestTheFalseNegativeGuard:
    def test_a_card_mid_run_with_finished_prelims_is_still_live(self):
        """The reason this is a deny-list and not an allow-list.

        Filtering to `scheduled`/`live` — the spelling `_list_event_bouts`'
        docstring suggests — makes this test fail: at 21:00Z the only
        non-completed bouts are at 22:00Z and 23:45Z, both future, so the card
        would go dark with the main card on air.
        """
        card = [
            bout(18, "completed"),
            bout(19, "completed"),
            bout(20, "live"),
            bout(22),
            bout(23, minute=45),
        ]
        now = datetime(2026, 9, 12, 21, tzinfo=timezone.utc)
        first, last = card_status_span(card)
        assert first == datetime(2026, 9, 12, 18, tzinfo=timezone.utc)
        assert combat_status(last, now, first) == "live"

    @pytest.mark.parametrize("status", ["completed", "closed", "live", "scheduled"])
    def test_a_bout_that_happens_is_never_dropped_from_the_span(self, status):
        card = [bout(18, status), bout(23, minute=45)]
        first, _ = card_status_span(card)
        assert first == datetime(2026, 9, 12, 18, tzinfo=timezone.utc)


class TestTheVocabularyIsOpen:
    @pytest.mark.parametrize(
        "status", ["suspended", "SUSPENDED", " Suspended ", "postponed", "cancelled"]
    )
    def test_called_off_spellings_leave_the_span(self, status):
        card = [bout(1, status), bout(16), bout(23, minute=45)]
        first, _ = card_status_span(card)
        assert first == datetime(2026, 9, 12, 16, tzinfo=timezone.utc)

    @pytest.mark.parametrize("status", ["in_progress", "delayed", "", None, "weird"])
    def test_an_unknown_status_counts_as_a_real_bout(self, status):
        """`events.status` is written by several providers and is an open set.

        An unknown value must keep today's behaviour — count as a bout — rather
        than silently vanish from the card's window. An allow-list would drop it.
        """
        card = [bout(1, status), bout(16), bout(23, minute=45)]
        first, _ = card_status_span(card)
        assert first == datetime(2026, 9, 12, 1, tzinfo=timezone.utc)


class TestDegenerateInput:
    def test_every_bout_called_off_is_not_a_span(self):
        """CERT-2727. The first spelling of this fix kept the FULL span here.

        Its reasoning — written into the docstring, never measured — was that
        such a card "is past its main event anyway, so `combat_status`' trailing
        arm settles it either way". The test that blessed it probed 14h45m after
        the last bout, which is the one region of the clock where the claim is
        true. Inside the trailing arm's own ~6h it is false, and the card served
        `live`. See `TestAnAllCalledOffCardIsNeverLive` for the sweep that would
        have caught it.
        """
        card = [bout(22, "suspended", day=11), bout(23, "suspended", day=11)]
        assert card_status_span(card) == (None, None)

    def test_no_bouts_at_all(self):
        assert card_status_span([]) == (None, None)

    def test_bouts_without_a_commence_are_not_a_span(self):
        assert card_status_span(
            [SimpleNamespace(commence_time=None, status="scheduled")]
        ) == (
            None,
            None,
        )

    def test_a_stampless_bout_does_not_poison_a_real_span(self):
        card = [
            SimpleNamespace(commence_time=None, status="scheduled"),
            bout(16),
            bout(20),
        ]
        first, last = card_status_span(card)
        assert first == datetime(2026, 9, 12, 16, tzinfo=timezone.utc)
        assert last == datetime(2026, 9, 12, 20, tzinfo=timezone.utc)

    def test_the_pair_does_not_depend_on_the_callers_sort(self):
        """min/max, not `[0]`/`[-1]`.

        The callers sort the FULL list by `bout_order_key`; dropping rows out of
        the middle must not make the answer depend on which ones went.
        """
        assert card_status_span(list(reversed(SPECIMEN))) == card_status_span(SPECIMEN)


class TestAnAllCalledOffCardIsNeverLive:
    """CERT-2727 — the repair the first spelling of #5603 needed.

    A card whose every bout is called off has no window to be inside, but the
    first fix restored the UNFILTERED span for it, so `combat_status` read the
    called-off times as if they were a schedule and lit the pill for the ~6h its
    trailing arm stays open. Terminal, not `upcoming`: a fully-postponed card
    that reads `upcoming` never leaves the feed's upcoming surface.

    Deliberately NOT routed through `combat_status`: no arithmetic over the
    times of fights that will not happen can produce an honest live window.
    """

    OFF = [bout(16, "suspended"), bout(18, "suspended"), bout(23, "cancelled")]

    def test_the_span_helper_has_no_span_for_it(self):
        assert card_status_span(self.OFF) == (None, None)

    def test_it_is_never_live_at_any_minute_of_the_two_days_around_it(self):
        """The sweep the original degenerate test should have been.

        That test probed ONE clock — 14h45m past the last bout — which is the
        region where the broken fallback happens to agree. 18:00Z, the minute
        the card's own middle bout was scheduled for, is where it said `live`.
        """
        start = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
        for minutes in range(0, 48 * 60, 13):
            now = start + timedelta(minutes=minutes)
            assert card_status_from_bouts(self.OFF, now) != "live", now

    def test_the_exact_minute_the_block_probed(self):
        now = datetime(2026, 9, 12, 18, tzinfo=timezone.utc)
        assert card_status_from_bouts(self.OFF, now) == "settled"
        # And this is what it did before the repair — the mutation that fails.
        unfiltered = (self.OFF[0].commence_time, self.OFF[-1].commence_time)
        assert combat_status(unfiltered[1], now, unfiltered[0]) == "live"

    def test_one_surviving_bout_is_enough_to_keep_a_real_window(self):
        """The boundary: this rule fires on ALL called off, never on some."""
        now = datetime(2026, 9, 12, 18, tzinfo=timezone.utc)
        card = [bout(16, "suspended"), bout(17), bout(23, "cancelled")]
        assert card_status_from_bouts(card, now) == "live"

    def test_a_card_we_hold_no_bouts_for_is_unknown_not_off(self):
        """`card_is_called_off` must not fire on an empty list.

        A Kalshi-only card has no events rows at all; it classifies from the
        caller's fallback pair exactly as it did before this repair.
        """
        now = datetime(2026, 9, 12, 18, tzinfo=timezone.utc)
        assert card_is_called_off([]) is False
        assert (
            card_status_from_bouts(
                [],
                now,
                fallback_first=datetime(2026, 9, 12, 17, tzinfo=timezone.utc),
                fallback_last=datetime(2026, 9, 12, 23, tzinfo=timezone.utc),
            )
            == "live"
        )

    def test_a_called_off_card_floors_no_child_as_settled(self):
        """Terminal and settled part company.

        `fight_child_settled` takes the card's ASSIGNED settledness (#1803). A
        called-off card is terminal because nothing WILL be fought — which is
        not a reason to grade a fight that never happened, so the child falls
        back to the price test exactly as a card in play does.
        """
        assert fight_child_settled(0.5, card_settled=False) is False
        # The floor itself still works where a card really did finish.
        assert fight_child_settled(0.5, card_settled=True) is True


class TestAnAllCalledOffCardNeverReportsLive5603:
    """`test_an_all_called_off_card_never_reports_live_5603`, the named repair
    guard, through the concept envelope and BOTH adapters.

    The unit tests above prove the rule; these prove every serve path reaches
    it. That distinction is the whole reason CERT-2727 blocked: the first fix
    put the all-called-off case in `card_status_span`, which each adapter is
    free to override with its own fallback — and one of them does, by design,
    for Kalshi-only cards. A rule only one of three callers honours is not a
    rule, so each path is asserted separately rather than by a source scan.
    """

    @staticmethod
    def _off_bouts():
        return [
            _FakeBout(1, "Dominic Valle", "Francois Scarboro Jr", _at(16), "suspended"),
            _FakeBout(2, "Luis Alberto Lopez", "Daniel Lugo", _at(18), "postponed"),
            _FakeBout(3, "Giovani Santillan", "Abass Barou", _at(23), "cancelled"),
        ]

    NOW = datetime(2026, 9, 12, 18, tzinfo=timezone.utc)

    @pytest.mark.parametrize("cfg", [UFC_CONFIG, BOXING_CONFIG], ids=["ufc", "boxing"])
    @pytest.mark.asyncio
    async def test_the_concept_lister_does_not_emit_it_as_live(self, cfg):
        """Call site 1. `statuses` defaults to upcoming/live, so a terminal card
        drops out of the feed entirely — the strongest form of "never live"."""
        db = _MockDB([], event_rows=self._off_bouts())
        concepts = await list_card_concepts(cfg, db, statuses=("upcoming", "live"))
        assert [c for c in concepts if c["status"] == "live"] == []

    @pytest.mark.parametrize("cfg", [UFC_CONFIG, BOXING_CONFIG], ids=["ufc", "boxing"])
    @pytest.mark.asyncio
    async def test_the_concept_lister_reports_it_terminal_when_asked_for_all(self, cfg):
        """Not merely absent — absent could mean "no rows reached the lister",
        which would make the test above vacuous. Ask for every status and read
        the value, so the card is proven present AND terminal."""
        db = _MockDB([], event_rows=self._off_bouts())
        concepts = await list_card_concepts(
            cfg, db, statuses=("upcoming", "live", "settled")
        )
        assert concepts, "the mock rows never reached the lister"
        assert {c["status"] for c in concepts} == {"settled"}

    @pytest.mark.parametrize("cfg", [UFC_CONFIG, BOXING_CONFIG], ids=["ufc", "boxing"])
    def test_the_events_only_adapter_envelope_is_not_live(self, cfg):
        """Call site 3 — `_build_events_envelope`, the page behind the card."""
        env = CombatEventAdapter(cfg)._build_events_envelope(
            "26sep12", self._off_bouts(), self.NOW
        )
        assert env["event"]["status"] == "settled"

    @pytest.mark.parametrize("cfg", [UFC_CONFIG, BOXING_CONFIG], ids=["ufc", "boxing"])
    @pytest.mark.asyncio
    async def test_the_kalshi_backed_adapter_envelope_is_not_live(self, cfg):
        """Call site 2 — `build_event`, which holds events bouts AND Kalshi
        markets. The Kalshi fallback pair must not resurrect the live pill."""
        prefix = "KXUFCFIGHT" if cfg.domain == "ufc" else "KXBOXING"
        markets = [
            _FakeMarket(
                101,
                f"{prefix}-26SEP12VALLESCARBORO",
                "Valle vs Scarboro",
                _at(16),
                ("Dominic Valle", "Francois Scarboro Jr"),
            ),
            _FakeMarket(
                102,
                f"{prefix}-26SEP12LOPEZLUGO",
                "Lopez vs Lugo",
                _at(18),
                ("Luis Alberto Lopez", "Daniel Lugo"),
            ),
        ]
        db = _MockDB([], event_rows=self._off_bouts(), market_rows=markets)
        adapter = CombatEventAdapter(cfg)
        env = await adapter.build_event("26sep12", db)
        assert env is not None, "the adapter never built the card"
        # Prove we are on the KALSHI branch, not the events-only envelope that
        # the previous test already covers: only that branch charts a market.
        assert env["primary"]["evolution_market_id"] is not None
        assert env["event"]["status"] == "settled"


class TestTheClockIsNotBranchedOn:
    def test_the_specimen_verdict_holds_at_every_minute_before_the_first_bout(self):
        first, last = card_status_span(SPECIMEN)
        start = datetime(2026, 9, 12, tzinfo=timezone.utc)
        for minutes in range(0, 16 * 60, 17):
            now = start + timedelta(minutes=minutes)
            assert combat_status(last, now, first) == "upcoming"
