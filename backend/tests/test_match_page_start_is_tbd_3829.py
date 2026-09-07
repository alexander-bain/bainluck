"""#3829 — the match page must not print a start time the hub calls TBD.

═══ WHAT THE READER SAW ═══

Production ``27c827b1``, 390px, 2026-09-07. Frances Tiafoe v Alex Michelsen,
US Open men's quarter-final, ``event_id 15306225``.

``/tournaments/us-open``, QF tab::

    TOMORROW · TBD · MEN'S SINGLES

``/events/15306225``, the same match::

    Starts in 1d 8h              Sep 8, 2026 · 11:30 AM EDT

One fixture, two surfaces, two answers — and the confident one was the wrong
one. All four quarter-finals shared a single fabricated
``2026-09-08T15:30:00+00:00``; four matches cannot begin at 11:30 on two courts.

═══ WHY THE HUB WAS RIGHT AND THE MATCH PAGE WAS NOT ═══

ESPN files a fixture on the scoreboard as soon as its round is drawn and
withholds the hour until the courts are assigned, saying which of the two you
hold in ``start_is_tbd`` (``services/espn_tennis.py:806``). ``tournament_slate``
carries it, and the hub has honoured it since Q463. The flag never reached
``/api/tournaments/by-event/{id}``, so ``app/events/[id]/page.tsx`` had nothing
to gate on and rendered ``commence_time`` unconditionally.

═══ WHAT IS PINNED HERE ═══

The backend half: the flag is derived, it is derived with three states rather
than two, and it rides EVERY answer the route gives once the event is known to
be in a tournament. The frontend half — day printed, clock refused, countdown
suppressed — is pinned by
``frontend/__tests__/matchPageStartIsTbd3829.test.tsx``.
"""

import ast
import inspect

from app.routes import tournaments


# ── THE PRODUCTION SHAPE, COPIED FROM THE WIRE ──────────────────────────────
#
# `GET /api/tournaments/us-open?sections=first` at 2026-09-07T08:4xZ, trimmed to
# the fields under test. Eight R16 rows carrying REAL staggered times and four
# QF rows sharing midnight-EDT: the defect and its control in one payload, from
# one code path, at one moment. A fixture invented here could have agreed with
# the implementation and disagreed with ESPN.
_SLATE_ROWS = [
    {"event_id": 15305579, "round": "R16", "start_is_tbd": False,
     "scheduled_date": "2026-09-07T15:00:00+00:00"},
    {"event_id": 15305580, "round": "R16", "start_is_tbd": False,
     "scheduled_date": "2026-09-07T15:30:00+00:00"},
    {"event_id": 15305578, "round": "R16", "start_is_tbd": False,
     "scheduled_date": "2026-09-07T17:00:00+00:00"},
    {"event_id": 15305797, "round": "R16", "start_is_tbd": False,
     "scheduled_date": "2026-09-07T18:30:00+00:00"},
    {"event_id": 15306160, "round": "QF", "start_is_tbd": True,
     "scheduled_date": "2026-09-08T04:00:00+00:00"},
    {"event_id": 15306814, "round": "QF", "start_is_tbd": True,
     "scheduled_date": "2026-09-08T04:00:00+00:00"},
    {"event_id": 15306225, "round": "QF", "start_is_tbd": True,
     "scheduled_date": "2026-09-08T04:00:00+00:00"},
    {"event_id": 15306813, "round": "QF", "start_is_tbd": True,
     "scheduled_date": "2026-09-08T04:00:00+00:00"},
]

_HUB = {"slate": {"matches": _SLATE_ROWS}}


class TestTheFlagIsDerivedFromTheAuthority:
    """The four rows that reported the bug, and the eight that must not move."""

    def test_the_four_quarter_finals_report_no_published_start(self):
        """Every event id named in #3829, by id, not by count."""
        for event_id in (15306225, 15306813, 15306160, 15306814):
            assert tournaments._slate_start_is_tbd(_HUB, event_id) is True, (
                f"event {event_id} is a US Open QF with no published order of "
                "play; the match page must not print an hour for it"
            )

    def test_the_round_of_16_control_keeps_its_real_time(self):
        """THE CONTROL, and it is a strong one: same tournament, same payload,
        same code path, same request — differing only in the fact under test.

        A guard whose control is an MLB game proves the tennis branch was never
        entered. These eight prove it was entered and returned the other answer.
        """
        for event_id in (15305579, 15305580, 15305578, 15305797):
            assert tournaments._slate_start_is_tbd(_HUB, event_id) is False, (
                f"event {event_id} has a real published hour from ESPN's order "
                "of play; suppressing its clock would be a new bug"
            )

    def test_an_event_absent_from_the_slate_is_None_and_not_False(self):
        """THE FAIL DIRECTION, and the reason this is a tri-state.

        "ESPN told us the time is real" and "we never asked" are different
        facts. Collapsing them to ``False`` would let a future reader treat
        every unlisted fixture as confirmed — the exact upgrade of unknown to
        known that produced the defect. Collapsing them to ``True`` is the
        opposite error and is just as wrong: a finished match is ALWAYS absent
        from today's order of play, and its start time is perfectly well known.
        """
        assert tournaments._slate_start_is_tbd(_HUB, 15304939) is None

    def test_a_non_boolean_flag_is_unknown_rather_than_truthy(self):
        """A row whose flag is a string, a number or missing is not evidence.

        ``"false"`` is truthy in Python and would have suppressed the clock on
        a match with a perfectly good time.
        """
        for junk in ("false", "true", 0, 1, None):
            hub = {"slate": {"matches": [{"event_id": 7, "start_is_tbd": junk}]}}
            assert tournaments._slate_start_is_tbd(hub, 7) is None, (
                f"{junk!r} is not a boolean and must not be read as one"
            )

    def test_an_empty_or_shapeless_hub_never_raises(self):
        """This rides the response of a page a reader is looking at."""
        for hub in ({}, {"slate": None}, {"slate": {}}, {"slate": {"matches": None}}):
            assert tournaments._slate_start_is_tbd(hub, 15306225) is None


class TestTheFlagRidesEveryAnswer:
    """The design risk that source inspection is the only way to pin.

    A quarter-final is precisely the row that dead-ends at ``NOT_IN_REGISTER``:
    ``tournament_slate`` mints ``espn:{competition_id}`` as the matchup key when
    the register no longer holds the pairing, so a second-week match is linked
    through ``by_espn`` and is absent from ``by_event`` by design. Measured on
    production: ``/api/tournaments/by-event/15306225`` returns exactly
    ``{"event_id", "tournament", "reason": "NOT_IN_REGISTER"}``.

    So a field added only to the fully-resolved return would be a field the four
    pages that reported the bug never receive, and every test above would still
    pass. That is what this class exists to catch.
    """

    @staticmethod
    def _returns_after_the_cheap_no() -> list[ast.Return]:
        # Parsed RAW. `inspect.cleandoc` re-indents against the body's common
        # prefix and turns a module-level `def` into an IndentationError.
        source = inspect.getsource(tournaments.get_event_tournament)
        tree = ast.parse(source)
        func = tree.body[0]
        assert isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))

        returns = [n for n in ast.walk(func) if isinstance(n, ast.Return)]
        dict_returns = [
            n for n in returns if isinstance(n.value, ast.Dict)
        ]
        # The CHEAP NO is the one return that must NOT carry the flag: it is
        # taken before `_hub_payload` is ever called, and adding a key there
        # would be claiming knowledge about an event we deliberately did not
        # look up.
        cheap_no = [
            n for n in dict_returns
            if not any(
                isinstance(k, ast.Constant) and k.value == "tournament"
                and isinstance(v, ast.Name)
                for k, v in zip(n.value.keys, n.value.values)
            )
        ]
        return [n for n in dict_returns if n not in cheap_no]

    def test_every_in_tournament_answer_carries_the_flag(self):
        """`container`, `NOT_IN_REGISTER`, `REGISTER_MOVED` and the full one."""
        tournament_returns = self._returns_after_the_cheap_no()
        assert len(tournament_returns) >= 3, (
            "expected the container bail-outs and the resolved answer; the "
            "route's shape changed and this guard needs re-reading"
        )
        for node in tournament_returns:
            keys = {
                k.value for k in node.value.keys
                if isinstance(k, ast.Constant)
            }
            assert "start_is_tbd" in keys, (
                f"the return at line {node.lineno} of `get_event_tournament` "
                "answers about an event inside a tournament and does not carry "
                "`start_is_tbd`; the match page will print a fabricated clock "
                "for every fixture that takes this branch (#3829)"
            )

    def test_the_cheap_no_is_untouched(self):
        """A Lakers game must not pay for the US Open being on.

        The flag is lifted from `hub`, and `hub` is only ever built past the
        sport-key gate — so this is free. The guard states it anyway, because
        the cheapest way to regress it is to hoist the lift for tidiness.
        """
        source = inspect.getsource(tournaments.get_event_tournament)
        cheap_no = source.index('return {"event_id": event_id, "tournament": None}')
        assert cheap_no < source.index("_slate_start_is_tbd("), (
            "the non-tournament answer must return before the flag is derived"
        )

    def test_the_flag_is_lifted_from_the_hub_and_not_sourced_again(self):
        """ONE writer of record, which was the whole defect.

        The hub and the match page disagreeing about one fixture is what #3829
        is. A second read of ESPN — or of the order-of-play cache — would be a
        second chance to disagree, and it would cost a request the warm-cache
        dict lookup does not.

        THE DOCSTRING IS EXCLUDED, AND THAT IS NOT A LOOPHOLE. The prose above
        the code cites ``services/espn_tennis.py:806`` as the flag's origin,
        which is exactly the sort of thing this function SHOULD say; the first
        draft of this guard read the whole source and failed on it, forbidding
        the documentation of the rule it enforces. The rule is about what the
        function DOES, so it is stated over the statements.
        """
        tree = ast.parse(inspect.getsource(tournaments._slate_start_is_tbd))
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        body = func.body[1:] if ast.get_docstring(func) else func.body
        code = "\n".join(ast.unparse(node) for node in body)

        # `await` would mean a second source; a name from any I/O layer would
        # mean the same thing before it was awaited.
        assert not any(
            isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith))
            for node in body for n in ast.walk(node)
        ), "`_slate_start_is_tbd` must not perform I/O; the hub is already in hand"
        for forbidden in ("db", "session", "redis", "espn", "fetch", "load_"):
            assert forbidden not in code, (
                f"`_slate_start_is_tbd` reached for {forbidden!r}; it must stay "
                "a pure read of the hub object already in hand"
            )
