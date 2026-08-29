"""FF1 (queue 387) — a lone, name-only ESPN row is not an identity.

Queue 385 turned time into an **authorization gate** for the ``espn_id`` stamp
(#2049) and then wrote the residual down in its own module docstring::

    Within the bound the gate cannot distinguish a doubleheader's sibling when
    the correct row is absent — the two halves are ~5.5h apart and both
    authorize.

Codex (``C-2058-REVIEW``, P1) executed that sentence. It ran the **real**
``match_event_to_espn`` and the **real** ``write_espn_win_probability`` against
one same-team ESPN row **5.5 hours** after the requested game and got
``matched_id='espn-game-2', method='name'``; the Core statement then compiled
``espn_id='espn-game-2'`` and added it to ``claimed``.

The finding is not "the number is slightly wrong". It is that **absence of the
correct scoreboard half converts the wrong half into an authorized identity** —
the gate reads a fact about *what we happened to fetch* as a fact about *which
game this is*.

## The repository was contradicting itself

``app/tasks/prediction_market_matching._ticker_date_far_from_event`` — an
independent guard, on an independent rail — calls anything beyond **±3h** of a
known start time a DIFFERENT game, explicitly "(separates doubleheaders ~5h
apart)". Its ±3h is not a guess: a 1,000-row systematic production sample
(2026-08-12) put 744 linked MLB markets at *exactly* 0h once the ticker's
Eastern clock was read correctly, and the ±3h rule reproduced the independently
measured 24.4% wrong-game rate almost exactly.

So one module said 5.5h is the same game and another said it is not. FF1
resolves that in favour of the conservative side, because the two questions are
not the same question:

* **merge** asks "may these two rows be absorbed into one?" — reversible,
  visible, and it has its own id-anchoring requirement (ruling 048);
* **identity** asks "may this scoreboard row *become* this event's espn_id?" —
  and a wrong id is neither visible nor reversible (#1980 measured ±15/±30
  offsets against a correct ``commence_time``).

``MAX_SAME_GAME_SECONDS`` is therefore no longer an alias of the merge window.
The merge window survives as ``MAX_CORROBORATED_SAME_GAME_SECONDS`` and is
reachable only *with* corroboration — a provider anchor, or a same-teams
sibling that was present in the pool and rejected. Uncorroborated name-only
selection lives inside the doubleheader boundary.

These tests are the executable form of that rule. They were written RED against
``ec636bae`` and each one reproduced codex's manufacture before the fix.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.espn_candidate_selection import (
    MAX_CORROBORATED_SAME_GAME_SECONDS,
    MAX_SAME_GAME_SECONDS,
    authorize_espn_pair,
    select_authorized_espn_candidate,
    select_espn_candidate,
)

UTC = timezone.utc

#: Codex's specimen gap. A split doubleheader (1:05pm / 7:05pm local) is ~6h;
#: a traditional one is ~3.5h. 5.5h sits squarely inside that band and squarely
#: inside the old 6h bound.
DOUBLEHEADER_GAP = timedelta(hours=5, minutes=30)

#: A time in the PAST, so the #1207 premature-live guard in the writer does not
#: short-circuit before reaching the id stamp. Fixed, not clock-derived: gotcha
#: #44 — offset first, then truncate, and never branch on the wall clock.
COMMENCE = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)


# ── minimal ESPN/DB stand-ins (same shapes the sibling rails read) ───────────


class _Team:
    def __init__(self, display_name):
        self.display_name = display_name
        self.name = display_name
        self.espn_id = None
        self.abbreviation = None
        self.logo_url = None
        self.color = None
        self.alternate_color = None


class _Game:
    """Stand-in for ``ESPNEvent`` — only the fields the selector/writer read."""

    def __init__(self, espn_id, home, away, date, win_prob=0.61):
        self.espn_id = str(espn_id)
        self.name = f"{away} at {home}"
        self.short_name = f"{away} @ {home}"
        self.home_team = _Team(home) if home else None
        self.away_team = _Team(away) if away else None
        self.date = date
        self.status = "in"
        self.status_detail = "Top 5th"
        self.period = 5
        self.clock = "0:00"
        self.home_score = 3
        self.away_score = 2
        self.home_win_probability = win_prob
        self.venue = None
        self.broadcasts = []


class _Event:
    def __init__(self, id, home, away, commence_time, espn_id=None):
        self.id = id
        self.home_team_name = home
        self.away_team_name = away
        self.home_team_normalized = None
        self.away_team_normalized = None
        self.home_team_alt_names = None
        self.away_team_alt_names = None
        self.commence_time = commence_time
        self.espn_id = espn_id
        self.status = "live"
        self.home_score = None
        self.away_score = None
        self.win_probability_sources = {}
        self.espn_win_prob_home = None
        self.game_clock = None
        self.period = None


def _espn_names_match(names, espn_team) -> bool:
    """The predicate shape ``espn_sync`` hands to ``match_event_to_espn``."""
    display = (
        getattr(espn_team, "display_name", None)
        or getattr(espn_team, "name", None)
        or ""
    )
    return any(str(n).lower() == display.lower() for n in names)


class _CapturingSession:
    """Records every Core statement so the compiled params can be inspected."""

    def __init__(self):
        self.statements: list = []
        self.added: list = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return None

    def add(self, obj):
        self.added.append(obj)

    def compiled_params(self):
        out = []
        for stmt in self.statements:
            compile_fn = getattr(stmt, "compile", None)
            if compile_fn is None:
                continue
            try:
                out.append(dict(compile_fn().params))
            except Exception:  # pragma: no cover - defensive
                continue
        return out

    def stamped_espn_ids(self):
        return [p["espn_id"] for p in self.compiled_params() if "espn_id" in p]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Codex's specimen, on the real live path
# ═══════════════════════════════════════════════════════════════════════════


class TestLoneDoubleheaderSiblingIsRefused:
    """The exact P1: one same-team row, 5.5h out, correct half absent."""

    def test_match_event_to_espn_refuses_the_lone_sibling(self):
        from app.utils.espn_helpers import match_event_to_espn

        event = _Event(1, "Boston Red Sox", "New York Yankees", COMMENCE)
        sibling = _Game(
            "espn-game-2", "Boston Red Sox", "New York Yankees",
            COMMENCE + DOUBLEHEADER_GAP,
        )

        matched, method = match_event_to_espn(
            event, [sibling], {}, set(), _espn_names_match,
        )

        assert matched is None, (
            "codex's specimen: matched_id='espn-game-2', method='name'. A lone "
            "name-only row 5.5h away is the OTHER half of a doubleheader as "
            f"readily as it is this game (got method={method!r})"
        )

    @pytest.mark.asyncio
    async def test_the_writer_does_not_compile_the_lone_siblings_id(self):
        """Defence in depth must be INDEPENDENT defence.

        Codex's note: "The writer's second check repeats the same 6-hour
        predicate, so it does not provide independent defence." Handing the row
        straight to the writer bypasses the selector entirely, which is exactly
        how the specimen was produced.
        """
        from app.utils.espn_helpers import write_espn_win_probability

        event = _Event(2, "Boston Red Sox", "New York Yankees", COMMENCE)
        sibling = _Game(
            "espn-game-2", "Boston Red Sox", "New York Yankees",
            COMMENCE + DOUBLEHEADER_GAP,
        )
        session = _CapturingSession()
        claimed: set = set()

        await write_espn_win_probability(session, event, sibling, "name", claimed, {})

        assert session.stamped_espn_ids() == [], (
            "compiled a Core update carrying espn_id from a 5.5h sibling: "
            f"{session.stamped_espn_ids()}"
        )
        assert "espn-game-2" not in claimed, (
            "the id was added to `claimed`, so the CORRECT half can no longer "
            "claim it either — one absence became two wrong answers"
        )

    def test_the_shared_selector_refuses_it_and_says_why(self):
        sibling = _Game(
            "espn-game-2", "Boston Red Sox", "New York Yankees",
            COMMENCE + DOUBLEHEADER_GAP,
        )

        chosen, reason = select_authorized_espn_candidate(
            [sibling], COMMENCE, is_name_match=lambda ee: True,
        )

        assert chosen is None
        # gotcha #53: a refusal that cannot be told apart from "nothing matched"
        # cannot be operated on. This refusal has its own token.
        assert reason not in ("no-name-match", "ok")
        assert "5.5" in reason, f"the refusal must quote the gap it refused on: {reason}"

    def test_the_two_arg_wrapper_refuses_it_too(self):
        """``sports.py``'s ``discover_events`` — the original #1980 surface."""
        sibling = _Game(
            "espn-game-2", "Boston Red Sox", "New York Yankees",
            COMMENCE + DOUBLEHEADER_GAP,
        )

        assert select_espn_candidate(
            [sibling], "Boston Red Sox", "New York Yankees", COMMENCE,
        ) == (None, None)

    def test_the_sibling_is_refused_from_either_side(self):
        """Our game may be the SECOND half; direction is not evidence."""
        earlier = _Game(
            "espn-game-1", "Boston Red Sox", "New York Yankees",
            COMMENCE - DOUBLEHEADER_GAP,
        )

        assert select_espn_candidate(
            [earlier], "Boston Red Sox", "New York Yankees", COMMENCE,
        ) == (None, None)


# ═══════════════════════════════════════════════════════════════════════════
# 2. The self-contradiction, pinned so it cannot re-open
# ═══════════════════════════════════════════════════════════════════════════


class TestTheRepositoryAgreesWithItselfAboutDistinctGames:
    """One codebase, one answer to "are these two records the same game?"."""

    def test_name_only_authority_never_exceeds_the_doubleheader_boundary(self):
        # The independent guard's HHMM window. Discovered by measurement, not
        # by taste (1,000-row production sample, 2026-08-12).
        #
        # Q439 (#2214) retired `_ticker_date_far_from_event`, which this pin
        # used to read the window off. That deletion does NOT move the boundary:
        # the ±3h came from a sample measured *"once the ticker's Eastern clock
        # was read correctly"* — the sentence this file already quotes — and the
        # deleted helper was the one that never did the reading. The window is
        # now pinned to the named constant instead of to a function, so the next
        # correction on that rail cannot silently drag this gate with it.
        from app.tasks.prediction_market_matching import (
            _EVENT_DATE_MAX_DIFF_HOURS,
            _ticker_date_conflicts_with_event,
        )

        assert _EVENT_DATE_MAX_DIFF_HOURS == 3

        # And the surviving decider still answers the boundary the same way.
        # 13:00 ET is 18:00Z in February; the ticker clock is Eastern.
        base = datetime(2026, 2, 21, 18, 0, tzinfo=UTC)
        ticker = datetime(2026, 2, 21, 13, 0, tzinfo=UTC)
        assert _ticker_date_conflicts_with_event(
            ticker + timedelta(hours=3, minutes=1), base, "kxmlbgame"
        )
        assert not _ticker_date_conflicts_with_event(
            ticker + timedelta(hours=2, minutes=59), base, "kxmlbgame"
        )

        assert MAX_SAME_GAME_SECONDS <= 3 * 3600, (
            "the espn_id authorization gate believes a pair is the same game "
            "that the wrong-game guard calls a distinct game. Two independently "
            "tuned answers to one question is how the codebase grows a "
            "contradiction — and this one manufactures identities."
        )

    @pytest.mark.parametrize("hours", [3.5, 4.0, 5.5, 6.0])
    def test_every_gap_the_other_guard_calls_distinct_is_refused_here(self, hours):
        gap = timedelta(hours=hours)
        ok, reason = authorize_espn_pair(COMMENCE + gap, COMMENCE)
        assert ok is False, f"{hours}h authorized a name-only stamp ({reason})"

    def test_the_merge_window_survives_but_only_as_the_corroborated_bound(self):
        """Do not silently delete a constant another rail reasons about.

        The 6h merge window is still here and still means what it meant; it is
        just no longer accepted as *identity* evidence on its own.
        """
        from app.utils.event_merge_invariant import MAX_ABSORPTION_SEPARATION_SECONDS

        assert MAX_CORROBORATED_SAME_GAME_SECONDS == MAX_ABSORPTION_SEPARATION_SECONDS
        assert MAX_SAME_GAME_SECONDS < MAX_CORROBORATED_SAME_GAME_SECONDS


# ═══════════════════════════════════════════════════════════════════════════
# 3. What still authorizes — the fix must fail closed, not fail shut
# ═══════════════════════════════════════════════════════════════════════════


class TestCorroborationStillAuthorizes:
    """"Refuse when unverifiable" is not "refuse"."""

    def test_a_present_and_rejected_sibling_is_a_uniqueness_proof(self):
        """Codex's own line: the correct half being PRESENT and rejected is
        real evidence; the correct half being ABSENT is not.

        With both halves in the pool we are no longer reading a fetch artifact:
        the slate's same-teams rows are all here and the nearer one wins.
        """
        near = _Game("game-1", "A Team", "B Team", COMMENCE + timedelta(hours=4))
        far = _Game("game-2", "A Team", "B Team", COMMENCE + timedelta(hours=9, minutes=30))

        chosen, reason = select_authorized_espn_candidate(
            [far, near], COMMENCE, is_name_match=lambda ee: True,
        )

        assert chosen is near, reason

    def test_a_provider_anchor_authorizes_past_the_name_only_bound(self):
        """A held ``espn_id`` that the pool confirms is identity evidence.

        Reachable in production from the admin live-sync and score-backfill
        rails, which do not pre-exclude held ids. It is deliberately NOT
        reachable from ``espn_sync.process_sport_events``: that caller builds
        ``espn_by_id`` from the same pool and pre-seeds ``claimed_espn_ids``,
        so the live path always runs on the tight, uncorroborated bound.
        """
        anchored = _Game("espn-777", "A Team", "B Team", COMMENCE + DOUBLEHEADER_GAP)

        chosen, reason = select_authorized_espn_candidate(
            [anchored], COMMENCE,
            is_name_match=lambda ee: True,
            anchor_espn_id="espn-777",
        )

        assert chosen is anchored, reason

        # …and the anchor must be the SAME id, not merely "an id".
        other, _r = select_authorized_espn_candidate(
            [anchored], COMMENCE,
            is_name_match=lambda ee: True,
            anchor_espn_id="espn-778",
        )
        assert other is None

    def test_an_ordinary_same_game_row_is_untouched(self):
        exact = _Game("espn-1", "A Team", "B Team", COMMENCE)
        near = _Game("espn-2", "C Team", "D Team", COMMENCE + timedelta(minutes=25))

        assert select_espn_candidate(
            [exact], "A Team", "B Team", COMMENCE,
        ) == (exact.date, exact.espn_id)
        assert select_espn_candidate(
            [near], "C Team", "D Team", COMMENCE,
        ) == (near.date, near.espn_id)

    @pytest.mark.asyncio
    async def test_the_writer_still_stamps_an_id_anchored_match(self):
        """``match_method='espn_id'`` is ESPN's own identity, not a name guess.

        Arm 1 must not be gated away by a rule aimed at arm 2 — that would turn
        a fail-closed fix into a coverage regression.
        """
        from app.utils.espn_helpers import write_espn_win_probability

        event = _Event(3, "A Team", "B Team", COMMENCE, espn_id="espn-999")
        # An id-anchored row whose clock disagrees (ESPN "TBD" placeholder).
        row = _Game("espn-999", "A Team", "B Team", COMMENCE + DOUBLEHEADER_GAP)
        session = _CapturingSession()

        await write_espn_win_probability(session, event, row, "espn_id", set(), {})

        assert session.stamped_espn_ids() == ["espn-999"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. The five siblings codex enumerated
# ═══════════════════════════════════════════════════════════════════════════


class TestEveryEnumeratedSiblingRoutesThroughTheGate:
    """Codex named five rails that reach the same primitive. A fix that only
    covered ``sports.py`` would leave four manufacturers running.
    """

    SIBLINGS = [
        ("app/utils/espn_helpers.py", "match_event_to_espn"),
        ("app/tasks/espn_sync.py", "_backfill_espn_ids_for_completed"),
        ("app/utils/espn_helpers.py", "backfill_espn_scores_for_events"),
        ("app/routes/admin_providers.py", "_espn_live_sync_impl"),
        ("app/routes/admin_providers.py", "_espn_backfill_ids_impl"),
    ]

    def test_no_sibling_selects_by_name_without_the_primitive(self):
        """Every name-derived selection goes through the shared authority.

        Structural on purpose: the executable specimens above prove the gate
        works; this proves nobody is standing beside it.
        """
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        offenders = []
        for rel in {"app/utils/espn_helpers.py", "app/tasks/espn_sync.py",
                    "app/routes/admin_providers.py", "app/tasks/sports.py"}:
            src = (root / rel).read_text(encoding="utf-8")
            if "espn" not in src:
                continue
            if ("select_authorized_espn_candidate" not in src
                    and "select_espn_candidate" not in src
                    and "authorize_espn_pair" not in src):
                offenders.append(rel)
        assert not offenders, (
            f"these rails derive ESPN identity but never call the gate: {offenders}"
        )

    def test_the_writer_gate_is_not_a_copy_of_the_selector_predicate(self):
        """Codex: a second check that repeats the first is not defence.

        The writer's check must be able to refuse something the selector let
        through, which means it must consult the same *authority*, not a
        re-implementation of the same arithmetic.
        """
        from app.utils import espn_helpers

        src = inspect.getsource(espn_helpers.write_espn_win_probability)
        assert "authorize_espn_pair" in src
        assert "MAX_SAME_GAME_SECONDS" not in src, (
            "the writer re-implements the bound instead of asking the gate"
        )
