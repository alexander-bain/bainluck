"""#6381 — a page stops denying a result the venue already gave us.

The defect, measured on production 2026-09-15: ``/events/15310639`` (Liverpool
FC v Fulham FC) served ``status: scheduled``, both scores ``null``, a ticking
refresh countdown and the hero chip **"No result reported"** — while one screen
below, on the same payload, its own ``Correct Score`` market read
``Draw 0-0 · Won``, graded ``is_winner=true, resolution_source='api_settlement'``
three days earlier. 426 ``scheduled`` rows were in that state, and 889
``suspended`` and 8 ``live`` ones alongside them.

ACCEPTANCE 3 OF #6381 IS `TestTheTwoStatesAreMutuallyExclusive`: the two states
cannot both hold on one payload. It is asserted on the payload `_format_event`
actually builds, not on a restatement of it, and the gate under test reads that
same dict — so a caller and its guard cannot unpack the payload differently and
agree with each other anyway.

The rest of the file guards the two ways this ships wrong:

* the VOCABULARY (`is_full_scope_score_market`) — a careless widening reads a
  half-time score as the full-time score. Both traps have live specimens ON THE
  SPECIMEN EVENTS THEMSELVES, so they are tested with their real names.
* the SCOPE (`venue_settlement_is_askable`) — a careless narrowing ships the fix
  to a third of its own class. The measured population sizes are in the table
  below so a future narrowing has to argue with a number.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.event_completion import UPCOMING_GRACE
from app.utils.venue_settlement import (
    FULL_SCOPE_SCORE_MARKETS,
    VENUE_SETTLEMENT_SOURCE,
    choose_settled_score,
    is_full_scope_score_market,
    venue_settlement_is_askable,
)

# ── The measured population, production 2026-09-15 ───────────────────────────
# Events holding ≥1 `is_winner=true, api_settlement` outcome with no score and
# no `completed_at` of their own, kickoff in the last 30 days and >2h past.
# `closed` (1,370) and `voided` (3,234) are deliberately NOT in scope — see the
# gate's docstring; `voided` never reaches the route at all (410).
_MEASURED_IN_SCOPE = {"suspended": 889, "scheduled": 426, "live": 8}

#: 56 of the 426 scheduled rows carry a full-scope graded score; the other 370
#: are graded on props alone. Acceptance 4 accepts *settled* without a score.
_MEASURED_WITH_A_SCORE = 56


def _now():
    """🔴 THE REAL CLOCK, ON PURPOSE — gotcha #44, and it already bit this file.

    This returned the literal `2026-09-15 18:00Z` for one morning. Every anchor
    in the file is written as an OFFSET from here, which is the shape gotcha #44
    asks for — but an offset is only meaningful from a moving origin, because
    the code under test reads the REAL clock: `started_without_result` asks
    `commence_time < now() - UPCOMING_GRACE`.

    Frozen origin + real-clock predicate = green when written, red forever
    after. Measured: `_now() - 30m` was 17:30Z, written to sit inside the 2h
    grace. It passed CI on `7ca69931c` that morning and went red at 19:30Z the
    SAME DAY — the instant the real clock put 17:30Z more than two hours in the
    past — reddening master for every lane in the fleet, with no diff to blame.

    The mirror image was live at the same time and is why this is a function,
    not two patched call sites: `_now() - 1h` as a "live row that has started"
    is false for any clock BEFORE 17:00Z, so `clock_sweep.py` failed 9/12
    points on the frozen version. Both directions have one cause and one fix.

    So: real clock, every call site, no exceptions. State an offset against the
    constant that defines the boundary (`UPCOMING_GRACE`) rather than a bare
    number, so widening the grace moves the anchor with it instead of silently
    invalidating the case's intent.
    """
    return datetime.now(timezone.utc)


def _event(**kw):
    """The Liverpool–Fulham specimen's row shape, `_format_event`-ready."""
    base = dict(
        id=15310639,
        external_id="kalshi:KXEPLGAME-26SEP12LIVFUL",
        sport=SimpleNamespace(key="soccer_epl", name="English Premier League"),
        home_team_name="Liverpool FC",
        away_team_name="Fulham FC",
        # 3.6 days past its own kickoff and still claiming to be a fixture.
        commence_time=_now() - timedelta(days=3, hours=14),
        completed_at=None,
        status="scheduled",
        home_score=None,
        away_score=None,
        box_score_data=None,
        win_probability_sources=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _payload(event):
    """The REAL serializer. Not a restatement of it — that is the whole point."""
    from app.routes.events import _format_event

    return _format_event(event)


def _session(graded, *, raises=None):
    """An `AsyncSession` stub returning `(market_name, outcome_name)` rows."""
    session = MagicMock()
    session.calls = 0

    async def execute(*_args, **_kwargs):
        session.calls += 1
        if raises is not None:
            raise raises
        result = MagicMock()
        result.all.return_value = list(graded)
        return result

    session.execute = AsyncMock(side_effect=execute)
    return session


# ═══════════════════════════════════════════════════════════════════════════
class TestTheVocabulary:
    """`is_full_scope_score_market` — the names, and the two live traps."""

    @pytest.mark.parametrize(
        "market_name",
        [
            # Soccer, 11 events. The Liverpool specimen's own market.
            "Liverpool FC vs Fulham FC: Correct Score",
            "Sevilla FC vs Valencia CF: Correct Score",
            # Tennis, 45 events — the same question under the venue's other name.
            "Lilli Tagger vs Amanda Anisimova: Exact Match Score",
            "Aryna Sabalenka vs Polina Iatcenko: Exact Match Score",
            # Order-independent, and case- and space-insensitive.
            "Correct Score: Liverpool FC vs Fulham FC",
            "Liverpool FC vs Fulham FC:  CORRECT   SCORE ",
        ],
    )
    def test_a_full_contest_score_market_is_recognised(self, market_name):
        assert is_full_scope_score_market(market_name)

    @pytest.mark.parametrize(
        "market_name",
        [
            # 🔴 TRAP 1 — 10 events carry this BESIDE their full-time market, so
            # a substring test publishes the half-time score as the final one.
            "Liverpool FC vs Fulham FC: 1st Half Correct Score",
            "Genoa CFC vs Frosinone Calcio: 1st Half Correct Score",
            "Sevilla FC vs Valencia CF: 2nd Half Correct Score",
            # 🔴 TRAP 2 — 8 events. Contains "Score" and is not a score.
            "Liverpool FC vs Fulham FC: First Team to Score",
            "Sunderland AFC vs Arsenal FC: First Team to Score",
            "Atletico Mineiro MG vs Fluminense FC RJ: Both Teams to Score",
            # Neighbours in the same measured census that are not scores either.
            "Sabalenka vs. Townsend: Match O/U 22.5",
            "Set 2 Winner: Sabalenka vs Townsend",
            "Liverpool FC vs Fulham FC: Regulation Time Total Goals",
            "",
            None,
        ],
    )
    def test_a_market_that_is_not_the_full_contest_score_is_refused(self, market_name):
        assert not is_full_scope_score_market(market_name)

    def test_the_traps_are_not_merely_absent_from_the_allowlist(self):
        """Both traps CONTAIN an allowlisted name; only exactness refuses them.

        Without this the two tests above pass for a `not in` over a list, which
        is the implementation that ships the bug.
        """
        assert any("correct score" in n for n in ["1st half correct score"])
        assert "correct score" in FULL_SCOPE_SCORE_MARKETS
        assert not is_full_scope_score_market("X: 1st Half Correct Score")


class TestTheChosenScore:
    """`choose_settled_score` — one name, or none. Never a picked one."""

    def test_the_one_graded_name_is_served_verbatim(self):
        assert choose_settled_score(["Draw 0-0"]) == "Draw 0-0"
        assert (
            choose_settled_score(["Aryna Sabalenka wins 2-0"])
            == "Aryna Sabalenka wins 2-0"
        )

    def test_the_same_name_twice_is_still_one_answer(self):
        assert choose_settled_score(["Draw 0-0", "Draw 0-0"]) == "Draw 0-0"

    def test_two_different_names_refuse_rather_than_pick_one(self):
        """Zero specimens today (56 events, 56 rows, 0 disagreements) — which is
        why it is written now. A deterministic tiebreak here is a confident
        wrong score on a page that had no score at all."""
        assert choose_settled_score(["Draw 0-0", "Liverpool FC wins 1-0"]) is None

    @pytest.mark.parametrize("names", [[], [None], [""], ["   "], [None, ""]])
    def test_nothing_graded_is_no_score_rather_than_a_blank_one(self, names):
        assert choose_settled_score(names) is None


class TestTheScope:
    """`venue_settlement_is_askable` — asked on the real payload."""

    def test_the_specimen_is_asked(self):
        assert venue_settlement_is_askable(
            _payload(_event()), live_claim_is_unbacked=False
        )

    def test_a_suspended_row_is_asked_and_it_is_the_LARGEST_arm(self):
        """889 events — more than the 426 the issue was filed on. A fix scoped
        to `started_without_result` alone leaves this half printing the same
        sentence over the same grades."""
        assert _MEASURED_IN_SCOPE["suspended"] > _MEASURED_IN_SCOPE["scheduled"]
        event = _event(status="suspended", commence_time=_now() - timedelta(hours=1))
        payload = _payload(event)
        assert payload["started_without_result"] is False
        assert venue_settlement_is_askable(payload, live_claim_is_unbacked=False)

    def test_a_live_row_is_asked_only_when_its_own_liveness_is_unbacked(self):
        event = _event(status="live", commence_time=_now() - timedelta(hours=1))
        payload = _payload(event)
        assert not venue_settlement_is_askable(payload, live_claim_is_unbacked=False)
        assert venue_settlement_is_askable(payload, live_claim_is_unbacked=True)

    @pytest.mark.parametrize(
        "event_kwargs, why",
        [
            (
                {"commence_time": _now() + timedelta(hours=3)},
                "a fixture whose clock has not run out says no such thing",
            ),
            (
                # Half a grace old: inside the window by construction, and it
                # stays inside if the grace changes. Never a bare `30 minutes`.
                {"commence_time": _now() - UPCOMING_GRACE / 2},
                "inside the upcoming grace it is still a fixture",
            ),
            (
                {
                    "status": "completed",
                    "completed_at": _now() - timedelta(days=3),
                    "home_score": 0,
                    "away_score": 0,
                },
                "we hold a better answer than the venue's grade",
            ),
            (
                {
                    "status": "completed",
                    "completed_at": _now() - timedelta(days=3),
                },
                "a finished status does not print the sentence, score or not",
            ),
            (
                {"home_score": 2, "away_score": 1},
                "a score outranks a grade even on a stuck status",
            ),
            ({"away_score": 1}, "one score is still a score"),
            (
                {"status": "closed"},
                "closed prints a Final, not 'No result reported' — its own defect",
            ),
        ],
    )
    def test_an_out_of_scope_row_is_never_asked(self, event_kwargs, why):
        payload = _payload(_event(**event_kwargs))
        assert not venue_settlement_is_askable(
            payload, live_claim_is_unbacked=False
        ), why

    def test_the_clock_origin_moves_because_every_anchor_hangs_off_it(self):
        """🔴 PINS THE ROT, NOT THE VALUE — the red that hit master 2026-09-15.

        The cases around this one cannot tell "the predicate correctly refuses
        this row" from "the anchor drifted out of the window it was written to
        sit in": both read as a pass right up until the drift crosses the
        boundary, and then it is a red with no diff behind it. Every other test
        in this file inherits `_now()`'s origin, so the premise is checked once,
        here, rather than restated at thirteen call sites.

        Asserted against the real clock and against `UPCOMING_GRACE` — never a
        bare literal — so re-freezing `_now()` fails HERE, naming the cause,
        instead of somewhere downstream hours later on somebody else's PR.
        """
        drift = abs(datetime.now(timezone.utc) - _now())
        assert drift < timedelta(minutes=1), (
            f"`_now()` is {drift} away from the real clock, so it has been "
            "re-frozen to a literal. Every anchor in this file is an offset "
            "from it, and the code under test reads the real clock: the two "
            "drift apart until a boundary case inverts and reddens master for "
            "the whole fleet with no diff behind it. Gotcha #44."
        )
        # The origin moving is necessary but not sufficient: the grace-relative
        # anchor must still land inside the window it exists to probe.
        age = datetime.now(timezone.utc) - (_now() - UPCOMING_GRACE / 2)
        assert timedelta(0) < age < UPCOMING_GRACE, (
            f"the 'inside the grace' anchor is {age} old against a "
            f"{UPCOMING_GRACE} grace — it no longer sits inside the window."
        )

    def test_completed_at_alone_does_NOT_take_a_stuck_row_out_of_scope(self):
        """🔴 PINS THE REMOVAL OF A GUARD, NOT ITS PRESENCE.

        `completed_at` reads like the same test as the score and is not: it
        records when we noticed, shows a reader nothing, and no arm of
        `hasNoReportedResult` consults it. A row that is still `suspended` or
        still past-kickoff-`scheduled` prints "No result reported" whether or
        not it carries one, so refusing to ask about it drops a population that
        has the defect. Measured 2026-09-15: 0 of the 1,323 in-scope rows carry
        a `completed_at`, which is why gating on it survived a mutation sweep
        while being wrong.
        """
        for kwargs in (
            {"completed_at": _now() - timedelta(days=1)},
            {
                "status": "suspended",
                "commence_time": _now() - timedelta(hours=1),
                "completed_at": _now() - timedelta(days=1),
            },
        ):
            payload = _payload(_event(**kwargs))
            assert venue_settlement_is_askable(
                payload, live_claim_is_unbacked=False
            ), kwargs


class TestTheServedKeys:
    """`_venue_settlement` — the query's shape and its refusals."""

    @pytest.mark.asyncio
    async def test_the_specimen_serves_settled_and_its_score(self):
        from app.routes.events import _venue_settlement

        session = _session(
            [
                ("Liverpool FC vs Fulham FC: Correct Score", "Draw 0-0"),
                ("Liverpool FC vs Fulham FC: First Team to Score", "No Goal"),
                ("Liverpool FC vs Fulham FC: 1st Half Correct Score", "Draw 1H 0-0"),
            ]
        )
        assert await _venue_settlement(session, _event()) == {
            "venue_settled": True,
            "venue_settled_result": "Draw 0-0",
        }

    @pytest.mark.asyncio
    async def test_props_alone_settle_the_event_without_inventing_a_score(self):
        """The issue's OTHER headline specimen. `/events/15304840` (Sabalenka v
        Townsend) holds 16 positive `api_settlement` grades and not one
        full-scope score market — measured. Acceptance 4 is this row."""
        from app.routes.events import _venue_settlement

        session = _session(
            [
                ("Sabalenka vs. Townsend: Match O/U 22.5", "Under"),
                ("Set 1 Winner: Sabalenka vs Townsend", "Yes"),
                ("Sabalenka vs. Townsend: Set 1 Games O/U 9.5", "Over"),
            ]
        )
        assert await _venue_settlement(session, _event()) == {
            "venue_settled": True,
            "venue_settled_result": None,
        }

    @pytest.mark.asyncio
    async def test_no_grade_at_all_is_a_stated_false_not_a_missing_key(self):
        from app.routes.events import _venue_settlement

        assert await _venue_settlement(_session([]), _event()) == {
            "venue_settled": False,
            "venue_settled_result": None,
        }

    @pytest.mark.asyncio
    async def test_a_failed_query_refuses_rather_than_answering_false(self):
        """A refusal leaves the page saying what it said before this key
        existed. Answering `false` would tell the reader the venue said
        nothing, which is a claim we did not make and cannot back."""
        from app.routes.events import _venue_settlement

        session = _session([], raises=RuntimeError("boom"))
        assert await _venue_settlement(session, _event()) is None

    @pytest.mark.asyncio
    async def test_the_query_reads_positive_grades_from_the_venue_only(self):
        """🔴 `is_winner IS TRUE` and `api_settlement`, both compiled.

        A count of graded legs, or a predicate that admits `is_winner=false`,
        reads a VOID market — every leg a loss — as a settled one and lets a
        page print a fabricated verdict. It is also what keeps the #1868/#3617
        class out: those are mass `is_winner=FALSE` stamps on games nobody
        played, and a predicate that only reads TRUE cannot see them.
        """
        from app.routes.events import _venue_settlement

        session = _session([])
        await _venue_settlement(session, _event())

        compiled = str(
            session.execute.await_args.args[0].compile(
                compile_kwargs={"literal_binds": True}
            )
        ).lower()
        assert "is_winner is true" in compiled
        assert f"resolution_source = '{VENUE_SETTLEMENT_SOURCE}'" in compiled
        assert "is_winner = false" not in compiled
        assert "count(" not in compiled


class TestTheTwoStatesAreMutuallyExclusive:
    """ACCEPTANCE 3. On one payload, the two states cannot both hold.

    "No result reported" is `frontend/lib/eventState.hasNoReportedResult`:
    `isSuspendedStatus(status) || startedWithoutResult(status, commence_time)`,
    plus the detail page's third arm in `hasNoReportedResultForShare` (an
    unbacked `live`). Each arm is enumerated here against the real payload.
    """

    @pytest.mark.parametrize(
        "event_kwargs, unbacked, arm",
        [
            ({}, False, "startedWithoutResult"),
            (
                {"status": "suspended", "commence_time": _now() - timedelta(hours=1)},
                False,
                "isSuspendedStatus",
            ),
            (
                {"status": "live", "commence_time": _now() - timedelta(hours=1)},
                True,
                "unbacked live (#5077)",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_a_payload_that_would_say_no_result_carries_the_grade(
        self, event_kwargs, unbacked, arm
    ):
        from app.routes.events import _venue_settlement

        event = _event(**event_kwargs)
        payload = _payload(event)

        # The page would render the sentence …
        renders_the_sentence = (
            payload["status"] == "suspended"
            or payload["started_without_result"]
            or (payload["status"] == "live" and unbacked)
        )
        assert renders_the_sentence, f"the {arm} arm no longer reaches the payload"

        # … so the payload must carry the contradiction, on the same read.
        assert venue_settlement_is_askable(
            payload, live_claim_is_unbacked=unbacked
        ), f"the {arm} arm is not asked"
        payload.update(
            await _venue_settlement(
                _session([("Liverpool FC vs Fulham FC: Correct Score", "Draw 0-0")]),
                event,
            )
        )
        assert payload["venue_settled"] is True
        assert payload["venue_settled_result"] == "Draw 0-0"

    @pytest.mark.asyncio
    async def test_the_route_wires_the_gate_to_the_payload_it_serves(self):
        """The gate reads the response dict, so the route cannot hand it a
        differently-derived view of the same state. Asserted on the source
        because the alternative — four unpacked arguments — is what lets a
        caller and this test agree with each other and both be wrong.
        """
        import inspect

        from app.routes import events as events_route

        source = inspect.getsource(events_route.get_event)
        assert "venue_settlement_is_askable(\n        response," in source, (
            "get_event must pass the response dict itself to the gate"
        )
        assert "_venue_settlement(db, event)" in source


class TestTheFrontendContractStillHasTwoArms:
    """If the web side grows a fourth way to say it, this guard goes red.

    The scope above mirrors `hasNoReportedResult`. A mirror that nothing checks
    is a comment, so the arms are counted in the file that defines them.
    """

    def test_has_no_reported_result_is_still_suspended_or_started_without(self):
        from pathlib import Path

        source = Path(__file__).resolve().parents[2] / "frontend/lib/eventState.ts"
        if not source.exists():  # pragma: no cover - backend-only checkouts
            pytest.skip("frontend not present in this checkout")
        body = source.read_text()
        marker = "export function hasNoReportedResult("
        assert marker in body, "hasNoReportedResult was renamed — re-scope #6381"
        tail = body[body.index(marker) :]
        returned = tail[tail.index("return ") : tail.index(";", tail.index("return "))]
        assert "isSuspendedStatus(status)" in returned
        assert "startedWithoutResult(status, commenceTime, now)" in returned
        assert returned.count("||") == 1, (
            "hasNoReportedResult grew an arm; venue_settlement_is_askable must "
            "grow the same one or #6381 ships to a subset of its own class"
        )


class TestTheVenueWordIsSpelledTwiceOnPurpose:
    """`api_settlement` is defined in two modules, and merging them is a BUG.

    int377 flagged the duplicate at merge (2026-09-15): `venue_settlement` and
    `kalshi_market_status` both define `VENUE_SETTLEMENT_SOURCE =
    "api_settlement"`. The obvious tidy — have the reader import the writer's
    constant — is the wrong one, and this guard is here to record why rather
    than leave the next reader to rediscover it.

    The two answer different questions:

    * `kalshi_market_status.VENUE_SETTLEMENT_SOURCE` is a WRITE constant. Its
      own docstring scopes it to `graded_columns` "and the string it emits" —
      one writer, the Kalshi forward capture.
    * `venue_settlement.VENUE_SETTLEMENT_SOURCE` is a READ filter over
      `futures_outcomes.resolution_source`, a column written by many hands.
      `backfill_winners.py` spells the word at 14 write-shaped sites, and
      `polymarket.py:4621` writes it for a venue Kalshi has nothing to do with.

    So an import would assert that the reader's population is defined by ONE of
    its writers. Rename the Kalshi constant and the import silently re-points
    the read at the new word, while every historical row — and everything
    `backfill_winners` and `polymarket` write tomorrow — still carries the old
    one. The page goes back to saying "No result reported" over grades we hold:
    the exact defect #6381 shipped to fix, re-introduced by a tidy, and failing
    closed so nothing would alarm.

    Asserting the gap makes a rename fail HERE, where the choice is visible.
    """

    def test_the_two_records_of_the_word_agree_today(self):
        from app.utils import kalshi_market_status

        assert VENUE_SETTLEMENT_SOURCE == kalshi_market_status.VENUE_SETTLEMENT_SOURCE, (
            "the writer's word and the reader's filter have drifted — the read "
            "population and the write are no longer the same rung. Do NOT fix "
            "this by importing one from the other (see this class's docstring); "
            "decide which rows the page may publish over, then re-state both."
        )

    def test_a_non_kalshi_writer_spells_it_too_which_is_what_forbids_the_import(self):
        """The record that LICENSES the duplicate, asserted instead of asserted-of.

        If this ever goes red because Kalshi's forward capture became the only
        writer of the word, the import stops being wrong and the duplicate
        stops being justified — which is a deliberate re-decision, not a tidy.
        """
        import re
        from pathlib import Path

        tasks = Path(__file__).resolve().parents[1] / "app/tasks"
        write_shaped = re.compile(
            r"""resolution_source\s*=\s*['"]""" + VENUE_SETTLEMENT_SOURCE + r"""['"]"""
        )
        non_kalshi_writers = sorted(
            path.name
            for path in tasks.glob("*.py")
            if not path.name.startswith("kalshi")
            and write_shaped.search(path.read_text())
        )
        assert non_kalshi_writers, (
            "no non-Kalshi task writes `api_settlement` any more — re-read this "
            "class's docstring before merging the two constants"
        )
        assert "polymarket.py" in non_kalshi_writers, (
            "polymarket.py no longer writes the word. The general assertion "
            "above stays green on siblings that only REFRESH already-graded "
            f"rows ({', '.join(non_kalshi_writers)}), so the cross-venue writer "
            "is pinned by name: it is the one that makes the read population "
            "wider than any single venue's writer."
        )
