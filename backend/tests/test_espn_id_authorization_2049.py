"""Time/currency is an AUTHORIZATION gate for every ``espn_id`` writer (C-2049).

Queue 385 item 1(a), from codex ``C-2049-2050-REVIEW``'s **BLOCK** on PR #2049.

## What #2049 fixed, and what it left open

#2049 taught ``select_espn_candidate`` to break a **multi-candidate** tie by time
instead of by dict ordering. That part works and is not re-litigated here.

Codex's BLOCK is about the other two halves:

1. **The selector fails OPEN on a lone match.** Time is consulted only after
   ``len(matches) >= 2``; the single-match branch returns unconditionally. Executed
   against the real selector, a sole candidate **24 hours** after the requested game
   was returned and stamped, and a sole candidate with ``date=None`` returned
   ``(None, espn_id)`` — an id with no time at all. A missing correct scoreboard row,
   a same-city false accept (#2046), or a partial two-day fetch therefore still
   manufactures the wrong identity. *Time was a tie-breaker; it has to be the gate.*

2. **Five sibling writers never had the gate in the first place.** Closing one
   caller while ``espn_sync``'s live path, two backfills and two admin routes retain
   first-name-hit id authority closes nothing: the wrong-id/correct-time shape stays
   producible. Codex proved the live one is not dormant by executing
   ``match_event_to_espn`` → ``write_espn_win_probability`` on a pool ordered
   ``[next-day, correct-day]`` and reading ``espn_id="wrong-next-day"`` out of the
   resulting Core-update parameters, at 24.0h error.

## The rule these tests assert

**An unverifiable match stamps nothing.** A candidate authorizes a stamp only when
its own date is present AND within ``MAX_SAME_GAME_SECONDS`` of the listing's
``commence_time``. That applies to the one-candidate case, the missing-date case,
and the winner of a multi-candidate tie alike — a tie-break picks the *best*
candidate, it does not make the best candidate *correct*.

Every test below drives a **real shipping function**, not a source string. Codex's
owed item 3 is explicit that an ``inspect.getsource`` assertion does not prove the
selector controls the write, so the structural check at the bottom is a *negative*
census (no ungated stamp survives) and is additional to, never a substitute for,
the executable ones.
"""

from __future__ import annotations

import ast
import pathlib
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.espn_candidate_selection import (
    MAX_SAME_GAME_SECONDS,
    authorize_espn_pair,
    select_authorized_espn_candidate,
    select_espn_candidate,
)

UTC = timezone.utc


# ── fixtures ────────────────────────────────────────────────────────────────


class _Team:
    def __init__(self, display_name, name=None):
        self.display_name = display_name
        self.name = name or display_name


class _Game:
    """Minimal stand-in for ``ESPNEvent`` (only the fields the writers read)."""

    def __init__(self, espn_id, home, away, date, *, win_prob=0.61):
        self.espn_id = str(espn_id)
        self.home_team = _Team(home) if home else None
        self.away_team = _Team(away) if away else None
        self.date = date
        self.home_win_probability = win_prob
        self.home_score = 3
        self.away_score = 1
        self.status = "in"
        self.status_detail = "Top 5th"
        self.clock = "0:00"
        self.short_name = f"{away} @ {home}"
        self.broadcasts = []


# ═══════════════════════════════════════════════════════════════════════════
# 1. The gate itself
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthorizeEspnPair:
    def test_a_dateless_candidate_is_never_authorized(self):
        ok, reason = authorize_espn_pair(None, datetime(2026, 8, 19, 2, 5, tzinfo=UTC))
        assert ok is False
        assert "date" in reason

    def test_a_candidate_beyond_the_bound_is_refused(self):
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        ok, _reason = authorize_espn_pair(commence + timedelta(hours=24), commence)
        assert ok is False

    def test_a_candidate_inside_the_bound_is_authorized(self):
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        ok, _reason = authorize_espn_pair(
            commence + timedelta(seconds=MAX_SAME_GAME_SECONDS - 60), commence
        )
        assert ok is True

    def test_a_missing_commence_time_refuses_rather_than_crashes(self):
        ok, _reason = authorize_espn_pair(datetime(2026, 8, 19, 2, 5, tzinfo=UTC), None)
        assert ok is False

    def test_naive_and_aware_datetimes_do_not_crash_the_gate(self):
        """Production mixes tz-aware ESPN dates with naive DB timestamps."""
        ok, _reason = authorize_espn_pair(
            datetime(2026, 8, 19, 2, 5, tzinfo=UTC), datetime(2026, 8, 19, 2, 5)
        )
        assert ok is True


# ═══════════════════════════════════════════════════════════════════════════
# 2. The selector — the fail-open codex executed
# ═══════════════════════════════════════════════════════════════════════════


class TestSelectorFailsClosed:
    """``select_espn_candidate`` — the exact specimens from the BLOCK."""

    def test_lone_next_day_candidate_stamps_nothing(self):
        """codex: sole candidate 24h out returned ``(…, "only-but-next-day")``."""
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        only = _Game(
            "only-but-next-day", "Los Angeles Dodgers", "San Francisco Giants",
            commence + timedelta(hours=24),
        )

        assert select_espn_candidate(
            [only], "Los Angeles Dodgers", "San Francisco Giants", commence,
        ) == (None, None), (
            "a lone name match 24h away is not evidence of identity — it is the "
            "next game of the series with the correct row missing from the pool"
        )

    def test_lone_dateless_candidate_stamps_nothing(self):
        """codex: sole dateless candidate returned ``(None, "only-dateless")``.

        The id was stamped with **no** ``espn_commence_time`` beside it, so the
        same-game check could never run downstream either.
        """
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        only = _Game("only-dateless", "Boston Red Sox", "New York Yankees", None)

        assert select_espn_candidate(
            [only], "Boston Red Sox", "New York Yankees", commence,
        ) == (None, None)

    def test_the_tie_break_winner_must_also_pass_the_gate(self):
        """A tie-break picks the best candidate; it does not make it correct."""
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        pool = [
            _Game(1, "Chicago Cubs", "St. Louis Cardinals", commence + timedelta(hours=48)),
            _Game(2, "Chicago Cubs", "St. Louis Cardinals", commence + timedelta(hours=24)),
        ]

        assert select_espn_candidate(
            pool, "Chicago Cubs", "St. Louis Cardinals", commence,
        ) == (None, None), (
            "both candidates are other games in the series; picking the nearer "
            "one still manufactures an identity"
        )

    def test_the_et_boundary_case_the_two_day_pool_exists_for_still_resolves(self):
        """Do not un-fix the bug the widening was for: 4h off is the SAME game."""
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        only = _Game(
            401816500, "Los Angeles Angels", "Texas Rangers",
            commence - timedelta(hours=4),
        )

        assert select_espn_candidate(
            [only], "Los Angeles Angels", "Texas Rangers", commence,
        ) == (only.date, only.espn_id)


class TestSelectAuthorizedEspnCandidateIsTheSharedPrimitive:
    """Siblings use different name matchers, so the gate takes the matcher in."""

    def test_it_reports_why_it_refused(self):
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        far = _Game(7, "A", "B", commence + timedelta(hours=24))

        chosen, reason = select_authorized_espn_candidate(
            [far], commence, is_name_match=lambda ee: True,
        )

        assert chosen is None
        assert reason and reason != "ok", "a refusal must say which gate refused"

    def test_it_picks_the_nearest_authorized_candidate(self):
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        far = _Game("far", "A", "B", commence + timedelta(hours=24))
        near = _Game("near", "A", "B", commence + timedelta(minutes=10))

        chosen, reason = select_authorized_espn_candidate(
            [far, near], commence, is_name_match=lambda ee: True,
        )

        assert chosen is near and reason == "ok"

    def test_excluded_ids_are_not_selectable(self):
        """Claimed-id exclusion belongs inside the primitive, not beside it."""
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        taken = _Game("taken", "A", "B", commence)

        chosen, _reason = select_authorized_espn_candidate(
            [taken], commence, is_name_match=lambda ee: True, exclude_ids={"taken"},
        )

        assert chosen is None

    def test_a_non_matching_pool_is_distinguishable_from_a_refused_one(self):
        """gotcha #53: "nothing matched" and "matched but refused" are not the
        same fact, and a caller that logs them identically cannot be debugged."""
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)

        _c1, no_match = select_authorized_espn_candidate(
            [_Game(1, "A", "B", commence)], commence, is_name_match=lambda ee: False,
        )
        _c2, refused = select_authorized_espn_candidate(
            [_Game(1, "A", "B", commence + timedelta(hours=24))],
            commence, is_name_match=lambda ee: True,
        )

        assert no_match != refused


# ═══════════════════════════════════════════════════════════════════════════
# 3. Sibling 1 — the LIVE sync path (codex's executable specimen)
# ═══════════════════════════════════════════════════════════════════════════


def _espn_names_match(names, espn_team) -> bool:
    """The shape ``espn_sync`` passes into ``match_event_to_espn``."""
    display = (getattr(espn_team, "display_name", None) or getattr(espn_team, "name", None) or "")
    return any(str(n).lower() == display.lower() for n in names)


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


class TestLiveSyncMatcherRefuses:
    """``match_event_to_espn`` is called by ``espn_sync.process_sport_events``."""

    def _pool_ordered_wrong_first(self, commence):
        return [
            _Game("wrong-next-day", "Los Angeles Dodgers", "San Francisco Giants",
                  commence + timedelta(hours=24)),
            _Game("correct-day", "Los Angeles Dodgers", "San Francisco Giants", commence),
        ]

    def test_it_picks_the_correct_day_not_the_first_hit(self):
        from app.utils.espn_helpers import match_event_to_espn

        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        event = _Event(1, "Los Angeles Dodgers", "San Francisco Giants", commence)

        matched, method = match_event_to_espn(
            event, self._pool_ordered_wrong_first(commence), {}, set(), _espn_names_match,
        )

        assert matched is not None and matched.espn_id == "correct-day", (
            f"selected the 24.0h sibling — codex's specimen (method={method})"
        )

    def test_it_refuses_when_only_the_wrong_day_is_present(self):
        from app.utils.espn_helpers import match_event_to_espn

        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        event = _Event(1, "Los Angeles Dodgers", "San Francisco Giants", commence)
        only_wrong = [self._pool_ordered_wrong_first(commence)[0]]

        matched, _method = match_event_to_espn(
            event, only_wrong, {}, set(), _espn_names_match,
        )

        assert matched is None, "an unverifiable lone match must stamp nothing"

    def test_an_espn_id_hit_is_still_honoured(self):
        """Arm 1 (id-anchored) is correct and must not be gated away."""
        from app.utils.espn_helpers import match_event_to_espn

        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        held = _Game("held", "Los Angeles Dodgers", "San Francisco Giants", commence)
        event = _Event(1, "Los Angeles Dodgers", "San Francisco Giants", commence,
                       espn_id="held")

        matched, method = match_event_to_espn(
            event, [held], {"held": held}, set(), _espn_names_match,
        )

        assert matched is held and method == "espn_id"


class TestLiveWriterRefusesToCompileAWrongIdUpdate:
    """Defence in depth: codex passed a selected row straight into the writer."""

    @pytest.mark.asyncio
    async def test_write_espn_win_probability_omits_an_unauthorized_id(self):
        from app.utils.espn_helpers import write_espn_win_probability

        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        event = _Event(1, "Los Angeles Dodgers", "San Francisco Giants", commence)
        wrong = _Game("wrong-next-day", "Los Angeles Dodgers", "San Francisco Giants",
                      commence + timedelta(hours=24))

        captured: list = []

        class _Session:
            async def execute(self, stmt):
                captured.append(stmt)
                return None

            def add(self, obj):
                pass

        await write_espn_win_probability(
            _Session(), event, wrong, "name", set(), {},
        )

        stamped = [
            params for params in
            (getattr(s, "compile", None) and s.compile().params or {} for s in captured)
            if "espn_id" in params
        ]
        assert not stamped, (
            f"compiled a Core update carrying espn_id from a 24.0h sibling: {stamped}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Siblings 2–5 — the four remaining writers
# ═══════════════════════════════════════════════════════════════════════════


class TestNoUngatedEspnIdStampSurvives:
    """A negative census over every non-test ``espn_id`` write.

    This is deliberately structural AND deliberately negative. Codex's owed
    item 3 rejects a source-reading assertion as *proof that the gate works* —
    so the gate working is proven by the executable tests above. What a census
    can prove that execution cannot is that no **sixth** manufacturer is sitting
    in a rail nobody wrote a test for, which is precisely how #2049 shipped
    while five siblings stayed open.
    """

    #: Every rail allowed to assign ``Event.espn_id``, with why it is safe.
    ALLOWED = {
        # the gate itself, and the guarded stamp helper (ruling 042)
        "app/utils/espn_candidate_selection.py",
        "app/utils/espn_id_stamp.py",
        # attended/plan-bound rails — reviewed, not name-derived
        "app/tasks/repair_event_espn_id.py",
        "app/tasks/create_events_from_truth.py",
        # ESPN's own registry claim carries ESPN's id and time
        "app/services/event_registry.py",
    }

    #: Dict-subscript writes are only interesting when the dict is an UPDATE
    #: PAYLOAD. ``espn_data["espn_id"] = …`` / ``meta["espn_id"] = …`` are
    #: response bodies reading the column back out, and a census that cannot
    #: tell a read from a write is noise an operator learns to ignore.
    PAYLOAD_NAMES = re.compile(r"(?i)(val|update|payload|fields|set|stamp)")

    def _espn_id_writes(self, src: str):
        """Every real Python write to ``espn_id`` in ``src``, as (lineno, shape).

        AST, not regex, and that is the whole point of the method: the three
        residual false positives a text scan produced here were a **docstring**
        quoting the old code, and two **SQL strings** comparing the column
        (``d.espn_id = t.espn_id``). None of them is Python at all. A parser
        cannot be fooled by any of the three, and it also cannot be fooled by
        the next one nobody has thought of.
        """
        found = []
        for node in ast.walk(ast.parse(src)):
            targets = []
            if isinstance(node, (ast.Assign,)):
                targets = list(node.targets)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            elif isinstance(node, ast.Call):
                # Core update: `.values(espn_id=…)`
                if (isinstance(node.func, ast.Attribute) and node.func.attr == "values"
                        and any(kw.arg == "espn_id" for kw in node.keywords)):
                    found.append((node.lineno, "values(espn_id=…)"))
                continue

            for t in targets:
                if isinstance(t, ast.Attribute) and t.attr == "espn_id":
                    found.append((t.lineno, "attribute stamp"))
                elif (isinstance(t, ast.Subscript)
                        and isinstance(t.slice, ast.Constant)
                        and t.slice.value == "espn_id"
                        and isinstance(t.value, ast.Name)
                        and self.PAYLOAD_NAMES.search(t.value.id)):
                    found.append((t.lineno, f"payload {t.value.id}['espn_id']"))
        return found

    def test_every_name_derived_writer_routes_through_the_gate(self):
        root = pathlib.Path(__file__).resolve().parents[1] / "app"

        offenders = []
        for path in sorted(root.rglob("*.py")):
            rel = str(path.relative_to(root.parent))
            if rel in self.ALLOWED:
                continue
            src = path.read_text(encoding="utf-8", errors="replace")
            if "espn_id" not in src:
                continue
            # A file that writes espn_id must reach the authorization gate.
            if "espn_candidate_selection" in src or "espn_id_stamp" in src:
                continue
            for lineno, shape in self._espn_id_writes(src):
                offenders.append(f"{rel}:{lineno} ({shape})")

        assert not offenders, (
            "ungated espn_id writers — each must select through "
            "`select_authorized_espn_candidate` or be added to ALLOWED with a "
            "written reason:\n  " + "\n  ".join(offenders)
        )

    def test_the_census_can_actually_see_a_manufacturer(self):
        """A guard whose detector is broken reports a clean board forever.

        The #2049 shape, and the two false-positive shapes it must stay blind
        to, run through the real detector.
        """
        caught = self._espn_id_writes(
            "def f(ev, ee, vals, meta):\n"
            "    ev.espn_id = ee.espn_id\n"            # the manufacturer
            "    vals['espn_id'] = ee.espn_id\n"       # an update payload
            "    q.values(espn_id=ee.espn_id)\n"       # a Core update
            "    meta['espn_id'] = ev.espn_id\n"       # a RESPONSE read-back
            "    return 'WHERE d.espn_id = t.espn_id'\n"  # SQL in a string
        )

        # sorted by line: ast.walk is breadth-first, so its raw order is an
        # implementation detail and asserting on it would be a flake waiting.
        assert [shape for _ln, shape in sorted(caught)] == [
            "attribute stamp", "payload vals['espn_id']", "values(espn_id=…)",
        ], caught
