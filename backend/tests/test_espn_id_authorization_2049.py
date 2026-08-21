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

**FF3 (queue 387).** Codex's follow-up review found the census itself had the
bypass it exists to prevent: it exempted an entire FILE whose text merely
mentioned the guard, so the three files that already import it — the three that
hold every real writer — were skipped wholesale. Section 4 now binds each write
SITE to an authorization (value provenance, or domination by an
``authorize_espn_pair`` verdict), and a mutation harness executes the shipping
census against a mirror of the real tree carrying a file that both imports the
guard and writes raw. That run must exit 1.
"""

from __future__ import annotations

import ast
import os
import pathlib
import re
import subprocess
import sys
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
# 4. Siblings 2–5 — the census, bound at the WRITE SITE (FF3, queue 387)
# ═══════════════════════════════════════════════════════════════════════════
#
# codex C-2049-2050 review, [P2]: the first version of this census asked the
# wrong question. It read each file's TEXT and skipped the whole file when the
# text mentioned a guard::
#
#     if "espn_candidate_selection" in src or "espn_id_stamp" in src:
#         continue          # <-- the ENTIRE file, not this write
#
# codex proved the bypass by injecting a manufacturer and an *unused* import of
# the guard into the same file: the AST detector saw the manufacturer, and the
# outer text condition threw the whole file away before the detector's answer
# was ever read. On the frozen tree that one line exempted every detected write
# in ``admin_providers.py``, ``espn_sync.py`` and ``espn_helpers.py`` — i.e. a
# sixth manufacturer added anywhere in the three files that already import the
# gate passed the "repo-wide" guard automatically.
#
# The replacement asks the question per WRITE: *is this specific assignment
# bound to an authorization?* Two ways to be bound, both structural:
#
#   value  — the value being written derives, through local rebinding, from a
#            call to one of the authorizing selectors. ``event.espn_id =
#            matched.espn_id`` where ``matched, _ = select_authorized_espn_
#            candidate(...)`` is bound; the same line where ``matched`` came
#            from ``pool[0]`` is not.
#   gate   — the write is dominated by an ``if`` whose test reads a flag that
#            ``authorize_espn_pair`` returned. This is the shape the write-time
#            defence in ``write_espn_win_probability`` uses.
#
# Anything else is UNBOUND and must appear, with a reason, in
# :data:`UNBOUND_WRITES` — which is asserted exhaustive in both directions, so
# padding it to silence the census is not a quiet operation.

#: Functions whose return value is authorized, and which tuple slots carry it.
#: ``select_espn_candidate`` returns ``(espn_commence_time, espn_id)`` — both
#: halves come off the authorized candidate — while the shared primitive
#: returns ``(candidate, reason)`` and only slot 0 is the candidate.
AUTHORIZED_SELECTORS = {
    "select_authorized_espn_candidate": (0,),
    "_select_authorized_espn_candidate": (0,),
    "select_espn_candidate": (0, 1),
}

#: Functions returning an authorization verdict, and which slot is the boolean.
AUTHORIZATION_GATES = {"authorize_espn_pair": (0,)}

#: Dict-subscript writes are only interesting when the dict is an UPDATE
#: PAYLOAD. ``espn_data["espn_id"] = …`` / ``meta["espn_id"] = …`` are response
#: bodies reading the column back out, and a census that cannot tell a read
#: from a write is noise an operator learns to ignore.
PAYLOAD_NAMES = re.compile(r"(?i)(val|update|payload|fields|set|stamp)")

_SQL_SET = re.compile(r"(?is)\bset\b")
_SQL_SET_CLAUSE_END = re.compile(r"(?is)\b(where|returning|from)\b")
_SQL_ESPN_ASSIGN = re.compile(r"(?is)\bespn_id\s*=")

#: Escape hatch for the mutation harness below, which needs to run this exact
#: test body against a mirrored tree. Nothing in production reads it, and the
#: census carries a non-vacuity floor so pointing it at an empty directory
#: fails loudly rather than passing.
CENSUS_ROOT_ENV = "BAINLUCK_ESPN_ID_CENSUS_ROOT"


class EspnIdWrite:
    """One detected write to ``espn_id``, with why it is (or is not) bound."""

    __slots__ = ("rel", "lineno", "shape", "func", "source", "bound")

    def __init__(self, rel, lineno, shape, func, source, bound):
        self.rel = rel
        self.lineno = lineno
        self.shape = shape
        self.func = func
        self.source = source
        self.bound = bound

    @property
    def key(self) -> tuple:
        """Line-number-free identity: file, function, exact source line.

        Line numbers churn on every edit above the write; the source text does
        not. Keying on the text also means a *second* ungated write in an
        already-allowlisted function is a new key (or a duplicate count), so
        the allowlist cannot cover a function wholesale — which is the same
        mistake, one level down, that this whole rewrite exists to remove.
        """
        return (self.rel, self.func, self.source)

    def __repr__(self) -> str:  # pragma: no cover - failure output only
        state = f"bound:{self.bound}" if self.bound else "UNBOUND"
        return f"{self.rel}:{self.lineno} [{self.func}] {self.shape} ({state}) | {self.source}"


def _parent_map(tree: ast.AST) -> dict:
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _docstring_constants(tree: ast.AST) -> set:
    """ids of the Constant nodes that are docstrings.

    The SQL scan below reads string literals, and prose about a bug quotes the
    bug: ``repair_event_espn_id``'s module docstring contains a literal
    ``UPDATE events SET`` example three lines long. A census that flags its own
    documentation teaches people to delete the documentation.
    """
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None) or []
            first = body[0] if body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                out.add(id(first.value))
    return out


def _qualname(node, parents) -> str:
    parts = []
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            parts.append(cur.name)
        cur = parents.get(cur)
    return ".".join(reversed(parts)) or "<module>"


def _enclosing_function(node, parents):
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
        cur = parents.get(cur)
    return None


def _called_name(call: ast.Call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _scope_assignments(scope):
    """Assignments in ``scope``, not descending into nested defs.

    A nested helper's locals are a different frame; letting them authorize a
    name in the enclosing frame would be a hole, not a convenience.
    """
    out = []

    def walk(node, is_root):
        if not is_root and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Assign):
            out.append(node)
        for child in ast.iter_child_nodes(node):
            walk(child, False)

    walk(scope, True)
    return out


def _authorized_and_gate_names(scope, upto_line: int) -> tuple[set, set]:
    """Names holding an authorized value / an authorization flag at ``upto_line``.

    Processed in SOURCE order and **rebinding revokes**: ``espn_event = None``
    followed by ``espn_event, _ = select_authorized_espn_candidate(...)`` ends
    authorized, and the reverse order ends unauthorized. A set that only ever
    grows would let a name be laundered by one authorized bind anywhere in the
    function.
    """
    authorized: set = set()
    gates: set = set()

    for node in sorted(_scope_assignments(scope), key=lambda n: n.lineno):
        if node.lineno > upto_line:
            break
        target = node.targets[0] if len(node.targets) == 1 else None
        if isinstance(target, ast.Tuple):
            slots = [(i, e.id) for i, e in enumerate(target.elts) if isinstance(e, ast.Name)]
        elif isinstance(target, ast.Name):
            slots = [(0, target.id)]
        else:
            continue

        value = node.value
        if isinstance(value, ast.Call):
            called = _called_name(value)
            if called in AUTHORIZED_SELECTORS:
                carrying = AUTHORIZED_SELECTORS[called]
                for index, name in slots:
                    (authorized.add if index in carrying else authorized.discard)(name)
                    gates.discard(name)
                continue
            if called in AUTHORIZATION_GATES:
                carrying = AUTHORIZATION_GATES[called]
                for index, name in slots:
                    (gates.add if index in carrying else gates.discard)(name)
                    authorized.discard(name)
                continue
        if isinstance(value, ast.Name) and value.id in authorized:
            for _index, name in slots:  # plain alias: `ee = _matched`
                authorized.add(name)
                gates.discard(name)
            continue
        for _index, name in slots:
            authorized.discard(name)
            gates.discard(name)

    return authorized, gates


def _value_is_authorized(value, authorized: set) -> bool:
    if value is None:
        return False
    if isinstance(value, ast.Name):
        return value.id in authorized
    if (isinstance(value, ast.Attribute) and value.attr == "espn_id"
            and isinstance(value.value, ast.Name)):
        return value.value.id in authorized
    return False


def _dominated_by_gate(node, parents, gates: set) -> bool:
    child = node
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, ast.If) and any(child is stmt for stmt in cur.body):
            used = {n.id for n in ast.walk(cur.test) if isinstance(n, ast.Name)}
            if used & gates:
                return True
        child = cur
        cur = parents.get(cur)
    return False


def espn_id_writes(rel: str, src: str) -> list:
    """Every real write to ``espn_id`` in ``src``, each classified bound/unbound.

    AST, not regex, and that is the whole point of the method: the residual
    false positives a text scan produced here were a **docstring** quoting the
    old code, and SQL strings *comparing* the column (``d.espn_id = t.espn_id``
    in a join). Neither is a write, and neither is Python at all. A parser
    cannot be fooled by either, nor by the next shape nobody has thought of.

    One thing the parser alone still could not see is a write performed in SQL
    text — ``UPDATE events SET espn_id = …`` is a manufacturer as surely as an
    ORM stamp is, and two of them ship today. Those are found by scanning
    non-docstring string constants for a SET clause that assigns the column;
    ``WHERE``/``RETURNING``/``FROM`` end the clause so a following comparison is
    not mistaken for the assignment. INSERT is deliberately out of scope: a row
    created *from* an ESPN id is anchored on it rather than claiming it.
    """
    tree = ast.parse(src)
    parents = _parent_map(tree)
    docstrings = _docstring_constants(tree)
    lines = src.splitlines()
    found: list = []

    def source_line(lineno: int) -> str:
        return lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""

    def record(node, shape: str, lineno: int, value=None) -> None:
        scope = _enclosing_function(node, parents) or tree
        authorized, gates = _authorized_and_gate_names(scope, node.lineno)
        bound = "value" if _value_is_authorized(value, authorized) else None
        if bound is None:
            stmt = node
            while stmt is not None and not isinstance(stmt, ast.stmt):
                stmt = parents.get(stmt)
            if stmt is not None and _dominated_by_gate(stmt, parents, gates):
                bound = "gate"
        found.append(
            EspnIdWrite(rel, lineno, shape, _qualname(node, parents), source_line(lineno), bound)
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets, value = [node.target], node.value
        elif isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Attribute) and node.func.attr == "values"
                    and any(kw.arg == "espn_id" for kw in node.keywords)):
                keyword = next(kw for kw in node.keywords if kw.arg == "espn_id")
                record(node, "values(espn_id=…)", node.lineno, keyword.value)
            continue
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            text = node.value
            for match in _SQL_SET.finditer(text):
                tail = text[match.end():]
                end = _SQL_SET_CLAUSE_END.search(tail)
                clause = tail[:end.start()] if end else tail
                assign = _SQL_ESPN_ASSIGN.search(clause)
                if assign:
                    offset = text[:match.end() + assign.start()].count("\n")
                    record(node, "sql SET espn_id", node.lineno + offset)
                    break
            continue
        else:
            continue

        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr == "espn_id":
                record(node, "attribute stamp", target.lineno, value)
            elif (isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "espn_id"
                    and isinstance(target.value, ast.Name)
                    and PAYLOAD_NAMES.search(target.value.id)):
                record(node, f"payload {target.value.id}['espn_id']", target.lineno, value)

    return found


def census_espn_id_writes(app_root: pathlib.Path) -> list:
    """Run :func:`espn_id_writes` over every module under ``app_root``."""
    writes: list = []
    for path in sorted(app_root.rglob("*.py")):
        src = path.read_text(encoding="utf-8", errors="replace")
        if "espn_id" not in src:
            continue
        writes.extend(espn_id_writes(str(path.relative_to(app_root.parent)), src))
    return writes


def _real_app_root() -> pathlib.Path:
    override = os.environ.get(CENSUS_ROOT_ENV)
    if override:
        return pathlib.Path(override)
    return pathlib.Path(__file__).resolve().parents[1] / "app"


class TestNoUngatedEspnIdStampSurvives:
    """A negative census over every non-test ``espn_id`` write.

    This is deliberately structural AND deliberately negative. Codex's owed
    item 3 rejects a source-reading assertion as *proof that the gate works* —
    so the gate working is proven by the executable tests above. What a census
    can prove that execution cannot is that no **sixth** manufacturer is sitting
    in a rail nobody wrote a test for, which is precisely how #2049 shipped
    while five siblings stayed open.
    """

    #: Writes that no authorization can bind, each with the reason it is safe.
    #: Keyed on (file, function, exact source line) and asserted EXHAUSTIVE in
    #: both directions by :meth:`test_the_allowlist_is_exhaustive`: an entry
    #: that no longer matches a real unbound write is a failure, so the list
    #: cannot quietly accumulate. Every entry here is either a different column
    #: (``Team.espn_id``), a CLEAR (writing NULL manufactures nothing), or the
    #: id-anchored/attended rails that the gate is downstream of.
    UNBOUND_WRITES = {
        ("app/routes/admin_providers.py", "sync_espn_teams",
         "team.espn_id = espn_team.espn_id"):
            "Team.espn_id — the TEAM identity column, not Event.espn_id. There "
            "is no commence_time for a team, so the same-game gate has nothing "
            "to compare; team identity is #1204's problem, not #1980's.",
        ("app/routes/source_intelligence.py", "cleanup_oscillation",
         "UPDATE events SET espn_id = NULL"):
            "Clears the column on a collision group so the rows can re-match. "
            "Writing NULL cannot manufacture an identity.",
        ("app/services/event_registry.py", "_attach_claim",
         "event.espn_id = claim.source_id"):
            "ESPN's own claim carries ESPN's id — arm (A) of gotcha #32, an "
            "id-anchored correspondence, not a name-derived one. Guarded by "
            "`if not event.espn_id`, so it never overwrites.",
        ("app/tasks/espn_sync.py", "_cleanup_bad_espn_matches._clear_espn_data",
         "team.espn_id = None"):
            "A CLEAR of Team.espn_id during bad-match cleanup.",
        ("app/tasks/espn_sync.py", "_backfill_team_logos",
         "team.espn_id = matched_espn.espn_id"):
            "Team.espn_id again, and already gated on `match_was_exact` so a "
            "fuzzy token-overlap hit never sets the id.",
        ("app/tasks/repair_event_espn_id.py", "<module>",
         "SET espn_id = :true_espn_id"):
            "The attended repair rail (SPEC-Q370): the value comes from a "
            "human-reviewed plan file, and the compare IS the WHERE clause "
            "(`AND espn_id = :wrong_espn_id`), so it cannot move a row it did "
            "not read.",
        ("app/utils/espn_helpers.py", "upsert_team",
         "team.espn_id = espn_team.espn_id"):
            "Team.espn_id, reached only after the mismatch guard above it "
            "returns early on a conflicting existing id.",
        ("app/utils/espn_id_stamp.py", "stamp_espn_id_if_unheld",
         "event.espn_id = espn_id"):
            "The guarded stamp helper itself (ruling 042). It is the writer "
            "the gate hands off to; the id it receives is the caller's to "
            "authorize, and every caller is censused here.",
    }

    #: Non-vacuity floor. If the census stops finding writes it has stopped
    #: being a census, and a green board would mean nothing. These are floors,
    #: not equalities, so adding a rail does not fail the suite.
    MIN_TOTAL_WRITES = 13
    MIN_BOUND_WRITES = 5

    def test_every_name_derived_writer_routes_through_the_gate(self):
        writes = census_espn_id_writes(_real_app_root())

        assert len(writes) >= self.MIN_TOTAL_WRITES, (
            f"the census found only {len(writes)} espn_id writes — it has gone "
            "vacuous (wrong root, or the detector stopped detecting)"
        )
        assert sum(1 for w in writes if w.bound) >= self.MIN_BOUND_WRITES, (
            "no write is being recognised as gate-bound; the binder is broken "
            "and every real writer is about to be re-classified by hand"
        )

        offenders = [
            w for w in writes
            if not w.bound and w.key not in self.UNBOUND_WRITES
        ]
        assert not offenders, (
            "ungated espn_id writes — each must take its value from "
            "`select_authorized_espn_candidate` (or a local alias of it), sit "
            "under an `if` on an `authorize_espn_pair` verdict, or be added to "
            "UNBOUND_WRITES with a written reason:\n  "
            + "\n  ".join(repr(w) for w in offenders)
        )

    def test_the_allowlist_is_exhaustive(self):
        """A stale entry is how an allowlist stops being read.

        Two of the old file-level ``ALLOWED`` entries
        (``repair_event_espn_id``, ``create_events_from_truth``) exempted files
        whose writes the detector could not even see, so they had been inert
        for their whole life and nobody could tell. Entries must correspond to
        a write that is really there, really unbound, and really unique.
        """
        writes = census_espn_id_writes(_real_app_root())
        unbound = [w.key for w in writes if not w.bound]

        stale = sorted(set(self.UNBOUND_WRITES) - set(unbound))
        assert not stale, (
            "UNBOUND_WRITES entries matching no real unbound write — delete "
            f"them or fix the key:\n  {stale}"
        )

        duplicated = sorted({k for k in unbound if unbound.count(k) > 1})
        assert not duplicated, (
            "two unbound writes share one allowlist key, so one of them is "
            f"covered by the other's reason:\n  {duplicated}"
        )

    def test_the_census_can_actually_see_a_manufacturer(self):
        """A guard whose detector is broken reports a clean board forever.

        The #2049 shape, and the false-positive shapes it must stay blind to,
        run through the real detector.
        """
        caught = espn_id_writes(
            "probe.py",
            "def f(ev, ee, vals, meta):\n"
            "    ev.espn_id = ee.espn_id\n"            # the manufacturer
            "    vals['espn_id'] = ee.espn_id\n"       # an update payload
            "    q.values(espn_id=ee.espn_id)\n"       # a Core update
            "    meta['espn_id'] = ev.espn_id\n"       # a RESPONSE read-back
            "    return 'WHERE d.espn_id = t.espn_id'\n"  # SQL COMPARE, not a write
        )

        # sorted by line: ast.walk is breadth-first, so its raw order is an
        # implementation detail and asserting on it would be a flake waiting.
        assert [w.shape for w in sorted(caught, key=lambda w: w.lineno)] == [
            "attribute stamp", "payload vals['espn_id']", "values(espn_id=…)",
        ], caught
        assert all(w.bound is None for w in caught), "nothing here is authorized"

    def test_the_binder_separates_a_bound_write_from_its_ungated_twin(self):
        """The binding rule, exercised on both answers for one line of code."""
        bound = espn_id_writes("probe.py", _BOUND_BY_VALUE_SRC)
        assert [w.bound for w in bound] == ["value"], bound

        alias = espn_id_writes("probe.py", _BOUND_BY_ALIAS_SRC)
        assert [w.bound for w in alias] == ["value"], alias

        gated = espn_id_writes("probe.py", _BOUND_BY_GATE_SRC)
        assert [w.bound for w in gated] == ["gate"], gated

        raw = espn_id_writes("probe.py", _UNGATED_SRC)
        assert [w.bound for w in raw] == [None], raw

    def test_a_later_rebind_revokes_authorization(self):
        """Laundering: select once, then overwrite the name with a raw pick."""
        launder = espn_id_writes("probe.py", _LAUNDERED_SRC)
        assert [w.bound for w in launder] == [None], launder

    def test_a_docstring_quoting_the_pattern_is_not_a_write(self):
        """…and a real write standing beside one is still caught.

        `repair_event_espn_id` documents the bug it repairs by quoting the SQL,
        three lines of it, in its module docstring. A detector that flagged
        that would be answered by deleting the documentation.
        """
        writes = espn_id_writes("probe.py", _DOCSTRING_DECOY_SRC)
        assert len(writes) == 1, writes
        assert writes[0].shape == "sql SET espn_id"
        assert "UPDATE events SET espn_id = :real" in writes[0].source
        assert writes[0].lineno > 8, (
            f"reported the DOCSTRING's line, not the write's: {writes[0]}"
        )

        prose_only = espn_id_writes("probe.py", _DOCSTRING_ONLY_SRC)
        assert prose_only == [], prose_only


# ── the mutation harness: the census must FAIL, in a real pytest run ────────
#
# codex's [P2] was not "the assertion is wrong", it was "the assertion is never
# reached". Asserting that `census_espn_id_writes` returns offenders would
# repeat that mistake one level up — it proves the detector, which was never in
# doubt, and not the test that consumes it. So the mutant is dropped into a
# mirror of the real app tree and the shipping test is executed against it in a
# subprocess. The evidence is pytest's own exit code.

#: BOTH halves of codex's bypass: the guard is imported (and even called, on a
#: path that does not feed the write) AND the write is raw. Under the old
#: file-level exemption this file was skipped entirely.
_MUTANT_SIXTH_MANUFACTURER = '''"""A sixth manufacturer.

It even quotes the shape it is committing, in prose:
``UPDATE events SET espn_id = :whatever`` — which the census must ignore.
"""

from app.utils.espn_candidate_selection import (  # noqa: F401
    authorize_espn_pair,
    select_authorized_espn_candidate,
)


def stamp_the_first_name_hit(event, espn_events, names_match):
    _ok, _reason = authorize_espn_pair(None, event.commence_time)
    for ee in espn_events:
        if names_match(event.home_team_name, ee.home_team.display_name):
            event.espn_id = ee.espn_id
            return ee
    return None
'''

#: The control: same import, same file name shape, but the value is selected
#: through the gate. If the census flagged this too, "bound" would mean nothing.
_CONTROL_BOUND_WRITER = '''"""A writer that selects through the gate."""

from app.utils.espn_candidate_selection import select_authorized_espn_candidate


def stamp_the_authorized_hit(event, espn_events, names_match):
    matched, reason = select_authorized_espn_candidate(
        espn_events,
        event.commence_time,
        is_name_match=lambda ee: names_match(
            event.home_team_name, ee.home_team.display_name
        ),
    )
    if matched is None:
        return reason
    event.espn_id = matched.espn_id
    return "ok"
'''

#: Prose that quotes the pattern and writes nothing. Present in BOTH runs.
_CONTROL_PROSE_ONLY = '''"""Notes on the manufacture.

The bug was ``event.espn_id = ee.espn_id`` with no time gate, repaired by
``UPDATE events SET espn_id = :true WHERE id = :id AND espn_id = :wrong``.
"""

DESCRIPTION = "see the docstring"
'''


def _mirror_app_tree(dest: pathlib.Path) -> pathlib.Path:
    """Copy the real ``app/`` package (python only) so a mutant can be added."""
    real = pathlib.Path(__file__).resolve().parents[1] / "app"
    mirror = dest / "app"
    for src in real.rglob("*.py"):
        target = mirror / src.relative_to(real)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(src.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return mirror


def _run_census_against(mirror: pathlib.Path):
    backend = pathlib.Path(__file__).resolve().parents[1]
    nodeid = (
        f"tests/{pathlib.Path(__file__).name}::TestNoUngatedEspnIdStampSurvives"
        "::test_every_name_derived_writer_routes_through_the_gate"
    )
    env = dict(os.environ, **{CENSUS_ROOT_ENV: str(mirror)})
    return subprocess.run(
        [
            sys.executable, "-m", "pytest", nodeid,
            "-q", "--no-header", "-p", "no:cacheprovider",
        ],
        cwd=str(backend),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


class TestTheCensusFailsOnAMutant:
    """codex's exact bypass, executed: import present, write ungated."""

    def test_an_importing_file_with_an_ungated_write_fails_the_census(self, tmp_path):
        mirror = _mirror_app_tree(tmp_path)
        (mirror / "tasks" / "mutant_sixth_manufacturer.py").write_text(
            _MUTANT_SIXTH_MANUFACTURER, encoding="utf-8"
        )
        (mirror / "tasks" / "mutant_prose_only.py").write_text(
            _CONTROL_PROSE_ONLY, encoding="utf-8"
        )

        proc = _run_census_against(mirror)
        output = proc.stdout + proc.stderr

        assert proc.returncode == 1, (
            "the census did not FAIL on a file that imports the guard and "
            f"writes raw (exit {proc.returncode}; anything but 1 means the "
            f"gate never ran — gotcha #54):\n{output[-4000:]}"
        )
        assert "mutant_sixth_manufacturer.py" in output, output[-4000:]
        assert "event.espn_id = ee.espn_id" in output, output[-4000:]
        assert "mutant_prose_only.py" not in output, (
            "flagged a file whose only mention of the pattern is prose:\n"
            + output[-4000:]
        )

    def test_the_same_write_selected_through_the_gate_passes(self, tmp_path):
        """The control: without it, "it failed" proves nothing about binding."""
        mirror = _mirror_app_tree(tmp_path)
        (mirror / "tasks" / "control_bound_writer.py").write_text(
            _CONTROL_BOUND_WRITER, encoding="utf-8"
        )
        (mirror / "tasks" / "mutant_prose_only.py").write_text(
            _CONTROL_PROSE_ONLY, encoding="utf-8"
        )

        proc = _run_census_against(mirror)
        assert proc.returncode == 0, (
            "an authorized writer was flagged, so the new binding is just a "
            f"different way of failing everything:\n{(proc.stdout + proc.stderr)[-4000:]}"
        )


# ── source fixtures for the in-process binder tests ─────────────────────────

_BOUND_BY_VALUE_SRC = """
from app.utils.espn_candidate_selection import select_authorized_espn_candidate


def f(event, pool, m):
    matched, reason = select_authorized_espn_candidate(pool, event.commence_time, is_name_match=m)
    if matched is not None:
        event.espn_id = matched.espn_id
"""

_BOUND_BY_ALIAS_SRC = """
from app.utils.espn_candidate_selection import select_authorized_espn_candidate


def f(event, pool, m):
    _matched, _reason = select_authorized_espn_candidate(pool, event.commence_time, is_name_match=m)
    if _matched is None:
        return
    ee = _matched
    event.espn_id = ee.espn_id
"""

_BOUND_BY_GATE_SRC = """
from app.utils.espn_candidate_selection import authorize_espn_pair


def f(event, ee, vals):
    ok, reason = authorize_espn_pair(ee.date, event.commence_time)
    if ee.espn_id and ok:
        vals["espn_id"] = ee.espn_id
"""

_UNGATED_SRC = """
from app.utils.espn_candidate_selection import authorize_espn_pair  # noqa: F401


def f(event, pool, m):
    for ee in pool:
        if m(event.home_team_name, ee.home_team.display_name):
            event.espn_id = ee.espn_id
            break
"""

_LAUNDERED_SRC = """
from app.utils.espn_candidate_selection import select_authorized_espn_candidate


def f(event, pool, m):
    matched, reason = select_authorized_espn_candidate(pool, event.commence_time, is_name_match=m)
    matched = pool[0]
    event.espn_id = matched.espn_id
"""

_DOCSTRING_DECOY_SRC = '''"""Prose that quotes the bug.

The old rail ran ``UPDATE events SET espn_id = :wrong`` with no gate, and the
ORM twin was ``event.espn_id = ee.espn_id``.
"""

from sqlalchemy import text

FIX = text("UPDATE events SET espn_id = :real WHERE id = :id")
'''

_DOCSTRING_ONLY_SRC = '''"""Only prose.

``UPDATE events SET espn_id = :wrong`` and ``ev.espn_id = ee.espn_id`` appear
here and nowhere else in the module.
"""

NOTE = "documented, not executed"
'''
