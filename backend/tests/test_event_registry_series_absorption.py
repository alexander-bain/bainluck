"""#1779 — consecutive-day series games must not be absorbed by the ±28h structured match.

THE DEFECT

``_find_by_structured_match`` accepts any same-sport candidate whose commence_time
is within ±28h and whose two team names match. For a sport where the same two
clubs play on consecutive days, **24h < 28h** — so the second game of a series
name-matched the first and was folded into it instead of being created. Nine MLB
games vanished and three rows were overwritten with the wrong day's score over
2026-08-10 → 08-12; the owner went looking for a live Red Sox game and it did not
exist on any surface, because it did not exist in the database.

THE FIX UNDER TEST (Alex ruling 2026-08-12)

The window is deliberately NOT narrowed — it exists for genuine cross-source date
disagreement (Kalshi settlement dates 24h off the start, UTC boundary crossings),
and narrowing it re-opens those. Instead a candidate is disqualified when it
already carries a **different game id from the incoming claim's own provider**.
The provider has already said these are two different games; names and times
cannot outvote that.

Four rounds, because each of the first three only covered rows the one before it
could not speak about:

* **R1** — same provider, different id → refuse, at any distance.
* **R2** (#1802) — individuated by ANY provider, starts >2h apart → refuse.
  Absence of the incoming provider's id is not evidence of sameness (gotcha #53).
* **R3** — individuated by NOBODY: two **published start times** more than half a
  day apart → refuse. This is 88% of events and was the largest remaining
  exposure; R1 and R2 never fire there.
* **R4** (ruling 042, Codex C-CERT-1801-R3) — R3's two answers were both read off
  a *label* rather than an identifier, and each one let a distinct scheduled game
  be absorbed:

  - its separate 12h window left the whole 0–12h band open, and a same-day
    doubleheader's second game lives there. Two real clocks are now held to the
    same ``_CROSS_PROVIDER_SAME_GAME_WINDOW`` an individuated row gets — one bar,
    no more forgiving number for id-less rows;
  - "is this a published start time?" was answered from the datetime's
    **formatting**. It is now answered from recorded provenance
    (``commence_time_source``), with the shape kept only as the fallback for rows
    written before the provenance existed — and the fallback says so when it runs.

  Both R4 specimens are Codex's, and both are asserted through the production
  entry point: R3's doubleheader test pre-populated BOTH rows and so never
  exercised the create path, which is exactly where the defect lived.

WHAT THE FIXTURES ARE

The seven absorption pairs are the real ones, not invented: absorbing-event ids,
their real ``espn_id`` / ``statpal_fixture_id`` and commence_times are the values
measured in production on 2026-08-12, and the incoming ESPN ids are the real ids
ESPN assigned the games that went missing. A synthetic fixture would prove the
branch runs; these prove the incident does not recur.
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.models import Event
from app.services.event_registry import (
    _CROSS_PROVIDER_SAME_GAME_WINDOW,
    _INGEST_FALLBACK_TIME_SOURCE,
    _is_a_different_scheduled_game,
    _is_a_published_start_time,
    _unindividuated_clocks_say_different_games,
    EventClaim,
    EventIdentity,
    _find_by_structured_match,
    _holds_distinct_provider_game_id,
    find_or_create_event,
)

from tests.test_event_registry import _FakeRegistrySession

MLB_SPORT_ID = 53232


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _event(*, event_id, away, home, commence, espn_id=None, statpal_id=None,
           external_id=None, status="completed", commence_time_source=None) -> Event:
    return Event(
        id=event_id,
        sport_id=MLB_SPORT_ID,
        away_team_name=away,
        home_team_name=home,
        commence_time=_utc(commence),
        status=status,
        espn_id=espn_id,
        statpal_fixture_id=statpal_id,
        external_id=external_id,
        commence_time_source=commence_time_source,
        completed_at=None,
    )


# (label, away, home, absorbing event id, its espn_id, its statpal id, its
#  commence_time, the missing game's commence_time, the missing game's real ESPN id)
#
# Measured 2026-08-12: production `events` rows + ESPN scoreboard for 08-10..08-12.
# Every delta below is inside the ±28h window, which is precisely the problem.
ABSORPTION_PAIRS = [
    ("BOS@TOR", "Boston Red Sox", "Toronto Blue Jays",
     15187583, "401816469", "355179", "2026-08-10T23:07:00", "2026-08-11T23:07:00", "401816479"),
    ("NYM@ATL", "New York Mets", "Atlanta Braves",
     15187584, "401816470", "355172", "2026-08-10T23:15:00", "2026-08-11T23:15:00", "401816482"),
    ("KC@LAD", "Kansas City Royals", "Los Angeles Dodgers",
     15187853, "401816475", "355174", "2026-08-11T02:10:00", "2026-08-12T02:10:00", "401816490"),
    ("COL@ARI", "Colorado Rockies", "Arizona Diamondbacks",
     15193365, "401816503", "355180", "2026-08-12T19:40:00", "2026-08-12T01:40:00", "401816488"),
    ("TB@ATH", "Tampa Bay Rays", "Athletics",
     15193123, "401816492", "355181", "2026-08-12T19:05:00", "2026-08-12T01:40:00", "401816507"),
    ("MIL@SD", "Milwaukee Brewers", "San Diego Padres",
     15193257, "401816491", "355190", "2026-08-12T20:10:00", "2026-08-12T01:40:00", "401816506"),
    ("HOU@SF", "Houston Astros", "San Francisco Giants",
     15193124, "401816489", "355191", "2026-08-12T19:45:00", "2026-08-12T01:45:00", "401816504"),
]

_IDS = [p[0] for p in ABSORPTION_PAIRS]


class TestTheSevenAbsorptions:
    """The 7/7 repro. Each pair must FALL INSIDE the window and STILL not match."""

    @pytest.mark.parametrize("pair", ABSORPTION_PAIRS, ids=_IDS)
    @pytest.mark.asyncio
    async def test_incoming_espn_game_is_not_absorbed(self, pair):
        (_label, away, home, ev_id, espn_id, statpal_id,
         absorber_time, missing_time, missing_espn) = pair

        absorber = _event(
            event_id=ev_id, away=away, home=home, commence=absorber_time,
            espn_id=espn_id, statpal_id=statpal_id,
        )
        session = _FakeRegistrySession(
            structured_candidates=[absorber], sport_id=MLB_SPORT_ID,
        )

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, home, away, _utc(missing_time),
            EventClaim("espn", missing_espn),
        )

        assert match is None, (
            f"{away} @ {home} on {missing_time} was absorbed into event {ev_id} "
            f"({absorber_time}) — that row already holds ESPN id {espn_id}, so ESPN "
            f"itself says {missing_espn} is a different game"
        )

    @pytest.mark.parametrize("pair", ABSORPTION_PAIRS, ids=_IDS)
    @pytest.mark.asyncio
    async def test_each_pair_really_is_inside_the_window(self, pair):
        """Guards the test itself.

        If a fixture's two times ever drifted outside ±28h the absorption test
        above would pass for the wrong reason — the candidate would be filtered
        out by the SQL window and the disqualification would never be exercised.
        """
        (_label, _away, _home, _ev, _espn, _statpal,
         absorber_time, missing_time, _missing_espn) = pair
        delta = abs((_utc(missing_time) - _utc(absorber_time)).total_seconds()) / 3600.0
        assert 0 < delta < 28, f"fixture drifted out of the ±28h window: {delta:.1f}h"

    @pytest.mark.parametrize("pair", ABSORPTION_PAIRS, ids=_IDS)
    @pytest.mark.asyncio
    async def test_an_idless_row_with_a_real_clock_is_also_refused(self, pair):
        """The id-less class. REWRITTEN TWICE — both prior versions asserted the defect.

        v1 pointed an id-less Kalshi claim at an absorber carrying an ``espn_id`` and a
        ``statpal_fixture_id`` and asserted it MATCHED (Codex specimen 6). R2 fixed that
        by making the absorber's ids do the work, and left this test proving the same
        "the window is untouched" point on a **shell with no ids at all** — asserting
        that an id-less row ~24h away MUST match, guarded by ``assert 0 < delta < 28``
        so it could never drift out of range. Seven green tests, pinning open exactly
        what the file's own docstring forbids six lines above them: *no absorption of a
        distinct scheduled game, regardless of which provider the claim arrives from*.

        That was not a smaller version of the bug. It was the LARGER half: 88% of events
        (63,952 of 72,918 in the last 90 days) carry no schedule-provider id, esports
        most of all, and for every one of them the guard R1/R2 added never fires.

        What replaces it: an id-less row whose commence_time is a **published start
        time** may not absorb a claim whose published start is more than half a day
        away. Every pair below is >12h apart. The legitimate intent — a genuine
        cross-source date disagreement on a row nothing has individuated — is asserted
        directly in ``TestTheIdlessRowsThatMustStillJoin``, not implied by this one.
        """
        (_label, away, home, ev_id, _espn_id, _statpal_id,
         absorber_time, missing_time, _missing_espn) = pair

        # No provider ids: nothing has said which game this row is. But its clock is
        # real — a whole-minute published start, not a fabricated `now`.
        shell = _event(
            event_id=ev_id, away=away, home=home, commence=absorber_time,
        )
        session = _FakeRegistrySession(
            structured_candidates=[shell], sport_id=MLB_SPORT_ID,
        )

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, home, away, _utc(missing_time),
            EventClaim("kalshi", "KXMLBGAME-26AUG11BOSTOR"),
        )
        assert match is None, (
            f"{away} @ {home} on {missing_time} was absorbed into an un-individuated "
            f"row at {absorber_time} — having no id is not a licence to absorb"
        )

    @pytest.mark.parametrize("pair", ABSORPTION_PAIRS, ids=_IDS)
    def test_each_idless_pair_is_beyond_the_half_day_rule(self, pair):
        """Guards the test above: >12h is what makes it a refusal, and <28h keeps it
        inside the SQL window, so the refusal is the predicate's doing and not the
        window's. Both bounds, because only asserting the upper one is what let the
        previous version look rigorous while asserting the defect.
        """
        (_label, _away, _home, _ev, _espn, _statpal,
         absorber_time, missing_time, _missing_espn) = pair
        delta = abs((_utc(missing_time) - _utc(absorber_time)).total_seconds()) / 3600.0
        assert 12 < delta < 28, f"fixture no longer exercises the rule: {delta:.1f}h"

    @pytest.mark.parametrize("pair", ABSORPTION_PAIRS, ids=_IDS)
    @pytest.mark.asyncio
    async def test_an_idless_claim_cannot_absorb_an_individuated_game(self, pair):
        """#1802 specimen 6, over all seven real pairs.

        The absorbers carry real production ``espn_id`` + ``statpal_fixture_id``. An
        id-less Kalshi claim a day away must not take them, even though Kalshi has no
        id column of its own to be disqualified on. Having no id to offer is not a
        licence to absorb somebody else's game.
        """
        (_label, away, home, ev_id, espn_id, statpal_id,
         absorber_time, missing_time, _missing_espn) = pair

        absorber = _event(
            event_id=ev_id, away=away, home=home, commence=absorber_time,
            espn_id=espn_id, statpal_id=statpal_id,
        )
        session = _FakeRegistrySession(
            structured_candidates=[absorber], sport_id=MLB_SPORT_ID,
        )

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, home, away, _utc(missing_time),
            EventClaim("kalshi", "KXMLBGAME-26AUG11BOSTOR"),
        )
        assert match is None
        assert absorber.commence_time == _utc(absorber_time), "row was dragged"


class TestDisqualificationPredicate:
    """``_holds_distinct_provider_game_id`` — the whole decision, in isolation."""

    def test_distinct_id_same_provider_disqualifies(self):
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", espn_id="401816469")
        assert _holds_distinct_provider_game_id(candidate, EventClaim("espn", "401816479"))

    def test_same_id_does_not_disqualify(self):
        """Idempotence. A re-poll of the same game must still find its own row."""
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", espn_id="401816469")
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("espn", "401816469"))

    def test_int_vs_str_id_is_not_a_difference(self):
        """ESPN ids arrive as both; a type difference must not read as a new game."""
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", espn_id="401816469")
        candidate.espn_id = 401816469
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("espn", "401816469"))

    def test_candidate_without_that_provider_id_is_kept(self):
        """The normal cross-source join: ESPN arriving at an odds_api-created row."""
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", external_id="abc123")
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("espn", "401816479"))

    def test_other_providers_id_never_disqualifies(self):
        """Two providers' id spaces are unrelated — comparing them is meaningless."""
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", external_id="abc123")
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("statpal", "355179"))

    def test_idless_provider_never_disqualifies(self):
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", espn_id="401816469")
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("kalshi", "KX-1"))
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("polymarket", "0xdead"))

    def test_empty_incoming_id_never_disqualifies(self):
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", espn_id="401816469")
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("espn", ""))

    def test_statpal_uses_its_own_column(self):
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", statpal_id="355179")
        assert _holds_distinct_provider_game_id(candidate, EventClaim("statpal", "355193"))
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("statpal", "355179"))

    def test_odds_api_uses_its_own_column(self):
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", external_id="abc123")
        assert _holds_distinct_provider_game_id(candidate, EventClaim("odds_api", "def456"))
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("odds_api", "abc123"))


class TestDoubleheadersStillCollapseCorrectly:
    """The ±28h window's original job must survive — ruling 2026-08-12 names this.

    Doubleheaders carry distinct provider ids too, so the id disqualification
    covers the case the window was built for. Where no ids exist yet, the window
    and its closest-by-time tiebreaker still decide.
    """

    @pytest.mark.asyncio
    async def test_distinct_ids_separate_the_two_games_of_a_doubleheader(self):
        game1 = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence="2026-08-10T17:07:00", espn_id="401816469")
        session = _FakeRegistrySession(structured_candidates=[game1], sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-10T23:07:00"), EventClaim("espn", "401816470"),
        )
        assert match is None, "game 2 of a doubleheader must not fold into game 1"

    @pytest.mark.asyncio
    async def test_idless_doubleheader_still_picks_the_closest_in_time(self):
        game1 = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence="2026-08-10T17:07:00")
        game2 = _event(event_id=2, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence="2026-08-10T23:07:00")
        session = _FakeRegistrySession(
            structured_candidates=[game1, game2], sport_id=MLB_SPORT_ID,
        )

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-10T23:05:00"), EventClaim("kalshi", "KX-1"),
        )
        assert match is game2

    @pytest.mark.asyncio
    async def test_swapped_orientation_still_matches_when_no_id_conflict(self):
        existing = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                          commence="2026-08-10T23:07:00", external_id="abc123")
        session = _FakeRegistrySession(structured_candidates=[existing], sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-10T23:07:00"), EventClaim("espn", "401816469"),
        )
        assert match is existing


class TestEndToEndThroughFindOrCreate:
    """The absorption is only really fixed if the top-level entry point creates."""

    @pytest.mark.asyncio
    async def test_missing_series_game_is_created_not_absorbed(self):
        absorber = _event(
            event_id=15187583, away="Boston Red Sox", home="Toronto Blue Jays",
            commence="2026-08-10T23:07:00", espn_id="401816469", statpal_id="355179",
        )
        session = _FakeRegistrySession(
            structured_candidates=[absorber], sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="baseball_mlb",
                home_team_name="Toronto Blue Jays",
                away_team_name="Boston Red Sox",
                commence_time=_utc("2026-08-11T23:07:00"),
                claim=EventClaim("espn", "401816479"),
                status="scheduled",
            ),
        )

        assert created is True, "the Aug 11 Red Sox game must be CREATED, not absorbed"
        assert event is not absorber
        assert event.espn_id == "401816479"
        assert event.commence_time == _utc("2026-08-11T23:07:00")
        # And the Aug 10 row is left completely alone.
        assert absorber.espn_id == "401816469"
        assert absorber.commence_time == _utc("2026-08-10T23:07:00")

    @pytest.mark.asyncio
    async def test_same_game_re_poll_still_finds_its_own_row(self):
        """Regression guard on the fix: it must not turn re-polls into duplicates."""
        existing = _event(
            event_id=15187583, away="Boston Red Sox", home="Toronto Blue Jays",
            commence="2026-08-10T23:07:00", espn_id="401816469",
        )
        session = _FakeRegistrySession(
            source_matches={"401816469": existing},
            structured_candidates=[existing],
            sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="baseball_mlb",
                home_team_name="Toronto Blue Jays",
                away_team_name="Boston Red Sox",
                commence_time=_utc("2026-08-10T23:07:00"),
                claim=EventClaim("espn", "401816469"),
            ),
        )
        assert created is False
        assert event is existing

    @pytest.mark.asyncio
    async def test_cross_source_join_still_works(self):
        """ESPN arriving at a row odds_api created must still MERGE, not duplicate."""
        existing = _event(
            event_id=15187583, away="Boston Red Sox", home="Toronto Blue Jays",
            commence="2026-08-10T23:07:00", external_id="abc123",
        )
        session = _FakeRegistrySession(
            structured_candidates=[existing], sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="baseball_mlb",
                home_team_name="Toronto Blue Jays",
                away_team_name="Boston Red Sox",
                commence_time=_utc("2026-08-10T23:07:00"),
                claim=EventClaim("espn", "401816469"),
            ),
        )
        assert created is False
        assert event is existing
        assert event.espn_id == "401816469"


# ═══════════════════════════════════════════════════════════════════════
# #1802 — Codex C-CERT-1801: cross-provider arrival order
#
# The same-provider disqualification above is a real guard, and it is not the
# incident's closure. Codex proved the branch still absorbed a distinct game
# through SIX shapes, all of them turning on one thing: the candidate did not yet
# carry the INCOMING provider's id, so the predicate returned False and the ±28h
# window did the rest.
#
# These fixtures use the PRODUCTION caller geometry, which the suite above did not:
# `EventClaim("odds_api", ...)` (backend/app/tasks/sports.py:412,
# odds_polling.py:671) and `EventClaim("statpal", ...)` (statpal_sync.py:150,260).
# There is no application `EventClaim("espn", ...)` caller at all — so every test
# above certifies a claim shape production never emits. That is exactly how 36
# green tests coexisted with an open P1.
# ═══════════════════════════════════════════════════════════════════════


class TestCrossProviderArrivalOrder:
    """Codex's six specimens. Each MUST fall inside ±28h and STILL not match."""

    # (label, candidate kwargs, incoming claim, incoming commence, hours apart)
    SPECIMENS = [
        ("odds_game1_then_statpal_game2_+24h",
         {"external_id": "odds-game-1"}, EventClaim("statpal", "statpal-game-2"),
         "2026-08-11T23:07:00", 24.0),
        ("statpal_game1_then_odds_game2_+24h",
         {"statpal_id": "statpal-game-1"}, EventClaim("odds_api", "odds-game-2"),
         "2026-08-11T23:07:00", 24.0),
        ("cross_provider_doubleheader_game2_+6h",
         {"external_id": "odds-game-1"}, EventClaim("statpal", "statpal-game-2"),
         "2026-08-11T05:07:00", 6.0),
        ("fall_DST_local_boundary_+25h",
         {"external_id": "odds-game-1"}, EventClaim("statpal", "statpal-game-2"),
         "2026-08-12T00:07:00", 25.0),
        ("inclusive_window_edge_exactly_+28h",
         {"external_id": "odds-game-1"}, EventClaim("statpal", "statpal-game-2"),
         "2026-08-12T03:07:00", 28.0),
        ("idless_kalshi_claim_+24h",
         {"espn_id": "401816469"}, EventClaim("kalshi", "KX-MLB-1"),
         "2026-08-11T23:07:00", 24.0),
    ]

    _LABELS = [s[0] for s in SPECIMENS]

    @pytest.mark.parametrize("label,cand_kwargs,claim,incoming,hours",
                             SPECIMENS, ids=_LABELS)
    def test_specimen_is_inside_the_window(self, label, cand_kwargs, claim,
                                           incoming, hours):
        """Guard: a specimen outside ±28h would pass for the wrong reason.

        Without this, a future widening of the disqualifier could be 'proved' by a
        fixture the SQL window had already filtered out — green for a reason that
        has nothing to do with the fix.
        """
        delta = abs((_utc(incoming) - _utc("2026-08-10T23:07:00")).total_seconds())
        assert delta / 3600.0 == pytest.approx(hours)
        assert delta <= 28 * 3600, f"{label} sits outside ±28h — fixture is wrong"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label,cand_kwargs,claim,incoming,hours",
                             SPECIMENS, ids=_LABELS)
    async def test_cross_provider_claim_does_not_absorb(self, label, cand_kwargs,
                                                        claim, incoming, hours):
        candidate = _event(event_id=15187583, away="Boston Red Sox",
                           home="Toronto Blue Jays",
                           commence="2026-08-10T23:07:00", **cand_kwargs)
        session = _FakeRegistrySession(structured_candidates=[candidate],
                                       sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc(incoming), claim,
        )
        assert match is None, (
            f"{label}: a {claim.source} claim {hours}h away absorbed a game "
            "individuated by another provider"
        )

    @pytest.mark.asyncio
    async def test_end_to_end_the_missing_game_is_created_and_the_row_is_untouched(self):
        """Codex's exact real-path repro, asserted on every field it reported moving."""
        absorber = _event(event_id=15187583, away="Boston Red Sox",
                          home="Toronto Blue Jays",
                          commence="2026-08-10T23:07:00", external_id="odds-game-1")
        session = _FakeRegistrySession(structured_candidates=[absorber],
                                       sport_id=MLB_SPORT_ID)

        event, created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="baseball_mlb",
                home_team_name="Toronto Blue Jays",
                away_team_name="Boston Red Sox",
                commence_time=_utc("2026-08-11T23:07:00"),
                claim=EventClaim("statpal", "statpal-game-2"),
                status="scheduled",
            ),
        )

        assert created is True, "the Aug 11 game must be CREATED, not absorbed"
        assert event is not absorber
        assert event.statpal_fixture_id == "statpal-game-2"
        assert event.commence_time == _utc("2026-08-11T23:07:00")
        # The three fields Codex watched move on the branch head:
        assert absorber.external_id == "odds-game-1"
        assert absorber.statpal_fixture_id is None, \
            "the prior game must not wear the missing game's statpal id"
        assert absorber.commence_time == _utc("2026-08-10T23:07:00"), \
            "the prior game must not be dragged forward"


class TestTheCrossProviderJoinStillWorks:
    """The fix must not make cross-source joining impossible — only dishonest joining."""

    @pytest.mark.asyncio
    async def test_same_game_different_providers_still_joins(self):
        """The whole point of the registry. Same start time, two providers, one row."""
        existing = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                          commence="2026-08-10T23:07:00", external_id="odds-game-1")
        session = _FakeRegistrySession(structured_candidates=[existing],
                                       sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-10T23:07:00"), EventClaim("statpal", "355179"),
        )
        assert match is existing

    @pytest.mark.asyncio
    async def test_modest_start_time_disagreement_still_joins(self):
        """A TV move / rounding difference is not a different game. 90 min < 2h."""
        existing = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                          commence="2026-08-10T23:07:00", external_id="odds-game-1")
        session = _FakeRegistrySession(structured_candidates=[existing],
                                       sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-11T00:37:00"), EventClaim("statpal", "355179"),
        )
        assert match is existing

    @pytest.mark.asyncio
    async def test_own_id_beats_the_clock_a_rain_delay_still_finds_its_row(self):
        """Identity outranks time. Same provider, same id, moved 5h — must still match.

        This is the case a pure time rule would break, and it is why the predicate
        checks the incoming provider's own id BEFORE it looks at the clock.
        """
        existing = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                          commence="2026-08-10T23:07:00", external_id="odds-game-1")
        session = _FakeRegistrySession(structured_candidates=[existing],
                                       sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-11T04:07:00"), EventClaim("odds_api", "odds-game-1"),
        )
        assert match is existing

    @pytest.mark.asyncio
    async def test_never_individuated_rows_are_not_a_free_pass(self):
        """REWRITTEN (#1779 R3). This asserted the defect.

        It previously took a shell with a real 23:07 start, pointed a Kalshi claim
        24h later at it, and asserted ``match is shell`` under the heading "keeps the
        wide window". The prediction-market treadmill it cites is real, but the row it
        used to justify it is not the treadmill's shape: treadmill rows carry a
        FABRICATED ``now`` timestamp, not a published start. Two published starts a day
        apart are two games, and no id-lessness changes that.

        The treadmill case it meant to protect is asserted for real, on a fabricated
        clock, in ``TestTheIdlessRowsThatMustStillJoin``.
        """
        shell = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence="2026-08-10T23:07:00")
        session = _FakeRegistrySession(structured_candidates=[shell],
                                       sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-11T23:07:00"), EventClaim("kalshi", "KX-1"),
        )
        assert match is None


class TestTheDisqualifierIsNotATautology:
    """The predicate must turn on real evidence, not always-true conditions."""

    def test_it_returns_FALSE_for_the_cases_that_must_still_join(self):
        same_time = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", external_id="odds-1")
        assert not _is_a_different_scheduled_game(
            same_time, EventClaim("statpal", "s-1"), _utc("2026-08-10T23:07:00"))

        shell = _event(event_id=2, away="A", home="B", commence="2026-08-10T23:07:00")
        assert not _is_a_different_scheduled_game(
            shell, EventClaim("statpal", "s-1"), _utc("2026-08-11T23:07:00")), \
            ("this predicate is scoped to INDIVIDUATED rows and must stay silent on "
             "shells — the id-less case belongs to "
             "_unindividuated_clocks_say_different_games, which DOES refuse this pair "
             "(asserted in TestTheIdlessClassPredicate). Read this as 'exactly one "
             "rule owns each candidate', never as 'a shell keeps the wide window'.")

    def test_it_returns_TRUE_only_when_individuated_AND_far(self):
        individuated = _event(event_id=1, away="A", home="B",
                              commence="2026-08-10T23:07:00", external_id="odds-1")
        assert _is_a_different_scheduled_game(
            individuated, EventClaim("statpal", "s-2"), _utc("2026-08-11T23:07:00"))

    def test_the_boundary_is_where_it_says_it_is(self):
        """Just inside 2h joins; just outside does not. Proves the constant is read."""
        row = _event(event_id=1, away="A", home="B",
                     commence="2026-08-10T23:07:00", external_id="odds-1")
        claim = EventClaim("statpal", "s-2")
        assert not _is_a_different_scheduled_game(
            row, claim, _utc("2026-08-11T01:06:00"))   # +1h59m
        assert _is_a_different_scheduled_game(
            row, claim, _utc("2026-08-11T01:08:00"))   # +2h01m


# ═══════════════════════════════════════════════════════════════════════
# #1779 R3 — the id-less class
#
# R1 and R2 both need an id to speak. Where the candidate carries none, nothing
# fired and the ±28h window decided exactly as it did before the incident — the
# original defect, fully intact, for 88% of events (63,952 of 72,918 in the last
# 90 days; esports is the single largest league bucket in it).
#
# The rule that closes it, and the two directions it must hold in (gotcha #43):
# an un-individuated row whose commence_time is a PUBLISHED start time (whole
# minute) refuses a claim whose published start is >12h away, AND every id-less
# join the wide window legitimately exists for still happens.
# ═══════════════════════════════════════════════════════════════════════


# A fabricated `now` — what tasks/prediction_market_matching.py writes when a market
# has no usable commence_time. Measured in production 2026-08-13: one such instant,
# 2026-05-13T18:35:00.015358Z, is the commence_time of 3,749 events across 10 sports.
# Sub-second precision is the tell; a published start is always a whole minute.
_FABRICATED_NOW = "2026-08-10T23:07:09.958462"
_FABRICATED_NOW_NEXT_DAY = "2026-08-11T15:05:00.021110"


class TestTheIdlessRowsThatMustStillJoin:
    """The inverse direction. A refusal-only guard would be trivially "correct"."""

    @pytest.mark.asyncio
    async def test_a_fabricated_clock_keeps_the_full_wide_window(self):
        """The treadmill case, asserted on the shape it actually has.

        A prediction-market auto-create with no usable market time writes ``now``.
        That row has NO clock — 3,749 unrelated games shared one such instant in
        production — so a distance rule cannot speak about it, and must not. A second
        market for the same game arriving a day later on its own fabricated ``now``
        has to find this row: Kalshi and Polymarket have no id column, so the
        structured match is their ONLY path to it. Refuse here and the NCAA-baseball
        duplicate treadmill (#1085) comes back.
        """
        shell = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence=_FABRICATED_NOW)
        session = _FakeRegistrySession(structured_candidates=[shell],
                                       sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc(_FABRICATED_NOW_NEXT_DAY), EventClaim("polymarket", "pm-1"),
        )
        assert match is shell, (
            "a row with a fabricated clock must keep the full ±28h window — there is "
            "no start time there to measure a disagreement against"
        )

    @pytest.mark.asyncio
    async def test_a_real_claim_still_finds_a_fabricated_clock_shell(self):
        """The valuable join: ESPN arrives at a Kalshi-created placeholder.

        This is how a prediction market ends up on the real event page. The shell's
        stamp is meaningless, so a full day of "disagreement" proves nothing.
        """
        shell = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence=_FABRICATED_NOW)
        session = _FakeRegistrySession(structured_candidates=[shell],
                                       sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-11T23:07:00"), EventClaim("espn", "401816479"),
        )
        assert match is shell

    @pytest.mark.asyncio
    async def test_a_fabricated_claim_still_finds_a_real_clock_shell(self):
        """The same join in the other arrival order — one side has no clock either way."""
        shell = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence="2026-08-10T23:07:00")
        session = _FakeRegistrySession(structured_candidates=[shell],
                                       sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc(_FABRICATED_NOW_NEXT_DAY), EventClaim("kalshi", "KX-1"),
        )
        assert match is shell

    @pytest.mark.asyncio
    async def test_a_timezone_sized_disagreement_on_two_real_clocks_now_creates(self):
        """REWRITTEN (R4). This test asserted the mechanism of the doubleheader defect.

        It read: "A source publishing a US local start as if it were UTC is off by
        4–7h. That is one game read off two clocks, and 12h is chosen precisely so it
        survives." The premise is true and the conclusion does not follow, because a
        4h gap between two id-less rows with real clocks is ALSO what the second game
        of a doubleheader looks like. The two hypotheses are the same distance apart,
        so no threshold separates them — this test was pinning open the exact band
        Codex's game-2 specimen absorbs through.

        The bar has no distance in it. When we cannot tell, we create: the timezone
        case now costs one mergeable duplicate, which the 30-minute merge task drains
        and the Flow Sentinel already hunts. The vanished game it buys off is
        invisible to every check we own.

        The join that genuinely must survive is the one where a clock is FABRICATED —
        the treadmill — and that is asserted for real, on fabricated clocks, in the
        three tests above.
        """
        shell = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence="2026-08-10T23:07:00")
        session = _FakeRegistrySession(structured_candidates=[shell],
                                       sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-10T19:07:00"), EventClaim("kalshi", "KX-1"),
        )
        assert match is None, (
            "4h between two published id-less starts is indistinguishable from "
            "game 2 of a doubleheader; the asymmetry says create"
        )

    @pytest.mark.asyncio
    async def test_end_to_end_the_idless_series_game_is_created(self):
        """Through the real entry point: created, and the id-less row left alone."""
        shell = _event(event_id=15187583, away="Boston Red Sox",
                       home="Toronto Blue Jays", commence="2026-08-10T23:07:00")
        session = _FakeRegistrySession(structured_candidates=[shell],
                                       sport_id=MLB_SPORT_ID)

        event, created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="baseball_mlb",
                home_team_name="Toronto Blue Jays",
                away_team_name="Boston Red Sox",
                commence_time=_utc("2026-08-11T23:07:00"),
                claim=EventClaim("kalshi", "KXMLBGAME-26AUG11BOSTOR"),
                status="scheduled",
            ),
        )

        assert created is True
        assert event is not shell
        assert shell.commence_time == _utc("2026-08-10T23:07:00"), "row was dragged"


class TestTheIdlessClassPredicate:
    """``_unindividuated_clocks_say_different_games`` — the decision in isolation."""

    def test_two_published_starts_a_day_apart_are_two_games(self):
        shell = _event(event_id=1, away="A", home="B", commence="2026-08-10T23:07:00")
        assert _unindividuated_clocks_say_different_games(
            shell, _utc("2026-08-11T23:07:00"))

    def test_it_is_silent_the_moment_any_provider_individuates_the_row(self):
        """Disjoint from the id-based guards: exactly one rule owns each candidate."""
        for kwargs in ({"espn_id": "401816469"}, {"statpal_id": "355179"},
                       {"external_id": "abc123"}):
            row = _event(event_id=1, away="A", home="B",
                         commence="2026-08-10T23:07:00", **kwargs)
            assert not _unindividuated_clocks_say_different_games(
                row, _utc("2026-08-11T23:07:00")), kwargs

    def test_a_fabricated_clock_on_either_side_silences_it(self):
        fabricated = _event(event_id=1, away="A", home="B", commence=_FABRICATED_NOW)
        assert not _unindividuated_clocks_say_different_games(
            fabricated, _utc("2026-08-11T23:07:00"))

        real = _event(event_id=2, away="A", home="B", commence="2026-08-10T23:07:00")
        assert not _unindividuated_clocks_say_different_games(
            real, _utc(_FABRICATED_NOW_NEXT_DAY))

    def test_the_boundary_is_where_the_constant_says_it_is(self):
        """Proves the constant is READ, not just declared.

        REWRITTEN (R4): there is no longer a separate un-individuated window to
        read. R3 had one at 12h and a same-day doubleheader's second game sat
        inside it. Two real clocks are now held to the SAME bar as two real clocks
        on an individuated row, so this asserts the shared constant — and that it
        is the shared one, which is the property that stops the two from drifting
        apart again.
        """
        assert _CROSS_PROVIDER_SAME_GAME_WINDOW.total_seconds() == 2 * 3600
        row = _event(event_id=1, away="A", home="B", commence="2026-08-10T12:00:00")
        assert not _unindividuated_clocks_say_different_games(
            row, _utc("2026-08-10T13:59:00"))            # 1h59m
        assert _unindividuated_clocks_say_different_games(
            row, _utc("2026-08-10T14:01:00"))            # 2h01m

    def test_the_un_individuated_bar_is_the_individuated_bar(self):
        """One bar, applied to both. Not two numbers that happen to be equal today.

        The same specimen, run through both predicates with the only difference
        being whether a provider has named the row. Same verdict at every distance —
        which is what "id-lessness does not buy a more forgiving definition of the
        same game" means operationally.
        """
        for gap_hours, expected in ((1.5, False), (2.5, True), (6, True), (24, True)):
            bare = _event(event_id=1, away="A", home="B",
                          commence="2026-08-10T12:00:00")
            named = _event(event_id=2, away="A", home="B",
                           commence="2026-08-10T12:00:00", espn_id="401816469")
            incoming = _utc("2026-08-10T12:00:00") + timedelta(hours=gap_hours)

            assert _unindividuated_clocks_say_different_games(
                bare, incoming) is expected, gap_hours
            assert _is_a_different_scheduled_game(
                named, EventClaim("statpal", "355179"), incoming) is expected, gap_hours

    def test_it_is_symmetric_in_time(self):
        """Earlier and later must behave identically — a sign error here is invisible."""
        row = _event(event_id=1, away="A", home="B", commence="2026-08-11T12:00:00")
        assert _unindividuated_clocks_say_different_games(
            row, _utc("2026-08-10T12:00:00"))
        assert _unindividuated_clocks_say_different_games(
            row, _utc("2026-08-12T12:00:00"))

    def test_a_null_candidate_time_cannot_disqualify(self):
        row = _event(event_id=1, away="A", home="B", commence="2026-08-10T23:07:00")
        row.commence_time = None
        assert not _unindividuated_clocks_say_different_games(
            row, _utc("2026-08-11T23:07:00"))


class TestPublishedStartTimeDetection:
    """The signal the whole id-less rule turns on."""

    def test_whole_minute_is_a_published_start(self):
        assert _is_a_published_start_time(_utc("2026-08-10T23:07:00"))
        assert _is_a_published_start_time(_utc("2026-08-10T00:00:00"))

    def test_sub_second_precision_is_a_fabricated_now(self):
        assert not _is_a_published_start_time(_utc(_FABRICATED_NOW))
        # The real production instant that 3,749 events across 10 sports share.
        assert not _is_a_published_start_time(_utc("2026-05-13T18:35:00.015358"))

    def test_whole_seconds_are_still_not_a_published_start(self):
        """Schedules are minute-granular. :09 is a clock reading, not a start time."""
        assert not _is_a_published_start_time(_utc("2026-08-10T23:07:09"))

    def test_none_is_not_a_published_start(self):
        assert not _is_a_published_start_time(None)


# ═══════════════════════════════════════════════════════════════════════
# R4 — Codex C-CERT-1801-R3's two BLOCK findings, as tests that fail first.
#
# R3 shipped 129 green tests over an implementation that still absorbed a
# distinct scheduled game. Both specimens below are Codex's, reproduced
# unchanged; each one is written through the PRODUCTION entry point, because
# the false green R3 shipped was false precisely at that boundary.
# ═══════════════════════════════════════════════════════════════════════


class TestTheSameDayDoubleheaderIsNotAbsorbed:
    """[P1] Game 2 of a same-day doubleheader, arriving when only game 1 exists.

    WHY R3'S TEST PASSED WHILE THE IMPLEMENTATION WAS BROKEN. The R3 suite's
    doubleheader case (``test_idless_doubleheader_still_picks_the_closest_in_time``)
    PRE-POPULATED BOTH rows and then proved the closest-by-time tiebreaker selects
    game 2. That is not the production failure. In production game 2 is the row that
    does not exist yet — it is the thing arriving — so the only question that matters
    is whether the matcher hands back game 1 and suppresses the create. It did.

    Both clocks here are whole-minute published starts and both rows are id-less, so
    R3's 12h rule is silent at 6h and the ±28h window decides exactly as it did
    before #1779. Codex measured the boundary: 12h00m absorbed, 12h01m refused.

    Alex's bar does not have a distance in it — *no absorption of a distinct
    scheduled game, full stop.*
    """

    @pytest.mark.asyncio
    async def test_game_two_is_created_when_only_game_one_exists(self):
        """THE production path. Only game 1 is in the table; game 2 arrives."""
        game1 = _event(event_id=15187583, away="Boston Red Sox",
                       home="Toronto Blue Jays", commence="2026-08-10T17:07:00")
        session = _FakeRegistrySession(structured_candidates=[game1],
                                       sport_id=MLB_SPORT_ID)

        event, created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="baseball_mlb",
                home_team_name="Toronto Blue Jays",
                away_team_name="Boston Red Sox",
                commence_time=_utc("2026-08-10T23:07:00"),
                claim=EventClaim("kalshi", "KXMLBGAME-26AUG101907BOSTOR"),
                status="scheduled",
            ),
        )

        assert created is True, (
            "game 2 of the 08-10 BOS@TOR doubleheader was absorbed into game 1 "
            "(17:07 vs 23:07, 6h). Both are published whole-minute starts; a "
            "same-day second game is a distinct scheduled game."
        )
        assert event is not game1
        assert game1.commence_time == _utc("2026-08-10T17:07:00"), (
            "game 1 was dragged onto game 2's start — the #1779 corruption half"
        )

    @pytest.mark.asyncio
    async def test_the_matcher_itself_refuses_game_one(self):
        """The same specimen one layer down, so a create-path change cannot mask it."""
        game1 = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence="2026-08-10T17:07:00")
        session = _FakeRegistrySession(structured_candidates=[game1],
                                       sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-10T23:07:00"), EventClaim("kalshi", "KX-G2"),
        )
        assert match is None

    @pytest.mark.parametrize(
        "gap_hours", [2.5, 4, 6, 9, 12],
        ids=["2h30m", "4h", "6h", "9h", "12h"],
    )
    @pytest.mark.asyncio
    async def test_no_gap_below_the_old_threshold_absorbs(self, gap_hours):
        """Codex found 12h00m absorbing and 12h01m refusing. The whole band is the bug.

        Parametrized rather than pinned at 6h so that "move the constant down a bit"
        is not a passing fix.
        """
        game1 = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence="2026-08-10T11:00:00")
        session = _FakeRegistrySession(structured_candidates=[game1],
                                       sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-10T11:00:00") + timedelta(hours=gap_hours),
            EventClaim("kalshi", "KX-G2"),
        )
        assert match is None, f"{gap_hours}h apart still absorbed"


class TestProvenanceNotShapeDecidesWhatIsPublished:
    """[P2] A real schedule that publishes seconds must not reopen +24h absorption.

    ``_is_a_published_start_time`` read authority off the FORMATTING of a datetime:
    ``second == 0 and microsecond == 0``. That is a label about the value, not a
    fact about where the value came from (ruling 042). Two consequences, both of
    which Codex reproduced:

    * a provider that publishes ``:00.5`` is read as fabricated, the id-less rule
      goes silent, and a game a full day away is absorbed;
    * a fabricated stamp that happens to land on an exact minute is read as
      published.

    The fix is to consult the provenance we already record — ``commence_time_source``
    — and to fall back to the shape heuristic ONLY where no provenance exists, saying
    so when it does.
    """

    @pytest.mark.asyncio
    async def test_a_sub_minute_real_schedule_a_day_away_is_not_absorbed(self):
        """Codex's specimen: both sides at ``:00.500000``, 24h apart, both real."""
        shell = _event(
            event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
            commence="2026-08-10T23:07:00.500000",
            commence_time_source="statpal",
        )
        session = _FakeRegistrySession(structured_candidates=[shell],
                                       sport_id=MLB_SPORT_ID)

        event, created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="baseball_mlb",
                home_team_name="Toronto Blue Jays",
                away_team_name="Boston Red Sox",
                commence_time=_utc("2026-08-11T23:07:00.500000"),
                commence_time_source="espn",
                claim=EventClaim("espn", "401816479"),
                status="scheduled",
            ),
        )

        assert created is True, (
            "a genuine schedule that carries seconds was read as a fabricated "
            "ingest stamp, so the id-less guard fell silent and tomorrow's game "
            "was absorbed — timestamp SHAPE is not provenance"
        )
        assert event is not shell

    def test_recorded_provenance_outranks_the_shape_in_both_directions(self):
        assert _is_a_published_start_time(
            _utc("2026-08-10T23:07:00.500000"), "statpal"), (
            "a schedule provider's start is published however it is formatted")
        assert not _is_a_published_start_time(
            _utc("2026-08-10T23:07:00"), _INGEST_FALLBACK_TIME_SOURCE), (
            "a stamp we KNOW we invented is not published just because it "
            "rounded to a whole minute")

    def test_an_unrecorded_provenance_still_falls_back_to_the_shape(self):
        """The 88% of rows written before provenance was recorded keep today's rule."""
        assert _is_a_published_start_time(_utc("2026-08-10T23:07:00"), None)
        assert not _is_a_published_start_time(_utc(_FABRICATED_NOW), None)

    def test_a_prediction_market_source_is_not_evidence_of_a_published_start(self):
        """``commence_time_source`` records WHO claimed the row, not that the clock is real.

        The prediction-market auto-create writes ``commence_time_source='kalshi'``
        even on the batch-shared ``now`` it substitutes, so reading that value as
        provenance would declare all 63,952 fabricated-clock rows published and turn
        the guard loose on them. Those must keep falling back to the shape.
        """
        assert not _is_a_published_start_time(_utc(_FABRICATED_NOW), "kalshi")
        assert _is_a_published_start_time(_utc("2026-08-10T23:07:00"), "kalshi")

    @pytest.mark.asyncio
    async def test_the_auto_create_records_that_it_invented_the_clock(self):
        """The provenance has to be WRITTEN, or the read above has nothing to find.

        Through the real function, not a grep of its source: the one code path in
        the codebase that fabricates a ``commence_time`` must store that fact, so a
        later matcher dereferences a recorded value instead of inferring one from
        the timestamp's formatting.
        """
        from types import SimpleNamespace

        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        now = _utc("2026-08-13T18:35:00.015358")
        session = _FakeRegistrySession(sport_id=99)
        market = SimpleNamespace(
            source="kalshi",
            external_id="KXCS2GAME-26AUG13NAVIG2",
            name="NAVI vs G2",
            commence_time=None,          # the trigger: no usable start time
            llm_sport_category=None,
        )
        matchup = SimpleNamespace(team_a="NAVI", team_b="G2", yes_team="NAVI")

        result = await _create_event_from_prediction_market(
            session, matchup, market, now,
        )

        assert result is not None, "fixture no longer reaches the create path"
        assert len(session.added) == 1
        created = session.added[0]
        assert created.commence_time == now
        assert created.commence_time_source == _INGEST_FALLBACK_TIME_SOURCE, (
            "the fabricated clock was recorded as if the market had published it"
        )
        assert not _is_a_published_start_time(
            created.commence_time, created.commence_time_source
        )

    @pytest.mark.asyncio
    async def test_the_auto_create_keeps_a_real_market_start_as_the_source(self):
        """The inverse. A recorded fabrication flag that is ALWAYS set says nothing."""
        from types import SimpleNamespace

        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        now = _utc("2026-08-13T18:35:00.015358")
        session = _FakeRegistrySession(sport_id=99)
        market = SimpleNamespace(
            source="kalshi",
            external_id="KXCS2GAME-26AUG13NAVIG2",
            name="NAVI vs G2",
            commence_time=_utc("2026-08-13T20:00:00"),   # a real published start
            llm_sport_category=None,
        )
        matchup = SimpleNamespace(team_a="NAVI", team_b="G2", yes_team="NAVI")

        await _create_event_from_prediction_market(session, matchup, market, now)

        assert len(session.added) == 1
        created = session.added[0]
        assert created.commence_time == _utc("2026-08-13T20:00:00")
        assert created.commence_time_source == "kalshi"
