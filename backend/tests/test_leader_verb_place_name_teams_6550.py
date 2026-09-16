"""A team printed as a bare place takes the singular verb (#6550).

Production `/sports`, 2026-09-16 12:30Z, two cards on ONE screen:

    Texas (10%) lead College Football National Championship Winner     wrong
    Texas Tech (36%) leads College Football Big 12 Championship Winner right

and Discover served `Texas lead at 10%` for the same market (181). Same subject
word, opposite verbs, adjacent on one frame.

THIS IS THE INVERSE OF #4700, NOT A REPEAT OF IT. #4700's gate is doing its job
— the outcome carries `team_id` — but the rule it guards assumes the printed
subject ENDS IN THE NICKNAME. In college and several pro markets the venue
prints the bare school or city and never prints the nickname at all, so the
trailing-`s` test reads a PLACE as a plural. Measured on production: 66 rows
over 16 (printed, team) pairs of open markets, `Las Vegas` (Aces, 0.87) and
`Texas` (Longhorns, 0.725) among them — page-one leaders, not a tail.

THE FIX IS NOT A PLACE-NAME WORD LIST. #4700's "do not decide this on spelling"
binds this direction too. The signal is `teams.name`: a printed name that is a
STRICT PREFIX of it has had its nickname stripped and is a place; a printed name
EQUAL to it prints the nickname and keeps #4700's rule.

THE POINT OF THIS FILE IS THE SECOND DIRECTION, AGAIN. The new arm may only ever
turn a wrong "lead" into "leads" — it must never take the plural back off
`Los Angeles Dodgers`, which is the regression that would undo #4700. Every
row of `KNOWN_TEAM_NAME_CASES` below that reads "lead" is that assertion, and
`test_unknown_team_name_keeps_4700s_rule` pins the default that makes it safe on
every caller that cannot name the team.
"""

import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils.feed_reasons import (
    _printed_name_omits_nickname,
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
    leader_agreement_verb,
)

# ── The predicate, on the measured pairs ─────────────────────────────────────

#: (printed name, `teams.name`, expected verb). Every row is a real
#: (`futures_outcomes.name`, `teams.name`) pair read off production on
#: 2026-09-16, not an invented string.
KNOWN_TEAM_NAME_CASES = [
    # ── The defect: the nickname is stripped, so the subject is a place. ──
    ("Texas", "Texas Longhorns", "leads"),
    ("Texas", "Texas Rangers", "leads"),
    ("Indianapolis", "Indianapolis Colts", "leads"),
    ("New Orleans", "New Orleans Saints", "leads"),
    ("New Orleans", "New Orleans Privateers", "leads"),
    ("Las Vegas", "Las Vegas Raiders", "leads"),
    ("Las Vegas", "Las Vegas Aces", "leads"),
    ("St. Louis", "St. Louis Cardinals", "leads"),
    ("Saint Louis", "Saint Louis Billikens", "leads"),
    ("Dallas", "Dallas Mavericks", "leads"),
    ("Memphis", "Memphis Grizzlies", "leads"),
    ("North Texas", "North Texas Mean Green", "leads"),
    ("Rutgers", "Rutgers Scarlet Knights", "leads"),
    ("Leeds", "Leeds United", "leads"),
    ("Olympiacos", "Olympiacos Piraeus", "leads"),
    # `Ole Miss` reads right today only by luck — the `ss` guard was written for
    # a hypothetical singular nickname, not for this. Now it is right on purpose.
    ("Ole Miss", "Ole Miss Rebels", "leads"),
    # Already right, and the card beside the defect on the reported frame. A
    # stripped nickname that happens not to end in "s" must not move either.
    ("Texas Tech", "Texas Tech Red Raiders", "leads"),
    ("Notre Dame", "Notre Dame Fighting Irish", "leads"),
    ("Georgia", "Georgia Bulldogs", "leads"),
    # ── #4700's own lines, with the team name now KNOWN. The nickname IS
    #    printed, so the name equals `teams.name` and the plural must survive.
    ("Los Angeles Dodgers", "Los Angeles Dodgers", "lead"),
    ("Los Angeles Rams", "Los Angeles Rams", "lead"),
    ("Boston Red Sox", "Boston Red Sox", "lead"),
    ("Chicago White Sox", "Chicago White Sox", "lead"),
    ("Toronto Blue Jays", "Toronto Blue Jays", "lead"),
    ("San Francisco 49ers", "San Francisco 49ers", "lead"),
    # Singular nicknames, name known and equal: unchanged.
    ("Miami Heat", "Miami Heat", "leads"),
    ("Tampa Bay Lightning", "Tampa Bay Lightning", "leads"),
]


@pytest.mark.parametrize("printed,team_name,expected", KNOWN_TEAM_NAME_CASES)
def test_leader_agreement_verb_with_a_known_team_name(printed, team_name, expected):
    assert leader_agreement_verb(printed, True, team_name) == expected


def test_the_two_cards_on_the_reported_frame_now_agree():
    """The line from the issue title, composed as production composes it.

    `Texas` and `Texas Tech` sat side by side on one screen with opposite verbs.
    """
    texas = generate_futures_headline(
        highlight_reasons=[],
        leader_name="Texas",
        leader_probability=0.0975,
        rendered_leader_percent=10,
        leader_is_team=True,
        leader_team_name="Texas Longhorns",
        market_name="College Football National Championship Winner",
    )
    assert texas == "Texas leads at 10%"

    texas_tech = generate_futures_headline(
        highlight_reasons=[],
        leader_name="Texas Tech",
        leader_probability=0.36,
        rendered_leader_percent=36,
        leader_is_team=True,
        leader_team_name="Texas Tech Red Raiders",
        market_name="College Football Big 12 Championship Winner",
    )
    assert texas_tech == "Texas Tech leads at 36%"


def test_unknown_team_name_keeps_4700s_rule():
    """FAIL TO TODAY'S WORDING, not to singular.

    `leader_team_name` defaults to None, so a caller that cannot name the team
    gets #4700 verbatim. This is what bounds the blast radius: the new arm can
    only ever turn a wrong "lead" into "leads", never the reverse. Asserted
    positionally AND by omission, because the default is part of the contract.
    """
    assert leader_agreement_verb("Los Angeles Dodgers", True) == "lead"
    assert leader_agreement_verb("Los Angeles Dodgers", True, None) == "lead"
    assert leader_agreement_verb("Los Angeles Dodgers", True, "") == "lead"
    # And the defect itself is simply unrepaired rather than differently wrong.
    assert leader_agreement_verb("Texas", True) == "lead"


def test_team_ness_is_still_the_outer_gate():
    """A team name cannot make a non-team move, in either direction.

    #4700 gated on `FuturesOutcome.team_id` precisely so a person is never
    touched. A stray `leader_team_name` must not open that gate.

    🔴 THE SECOND ROW IS THE ONE THAT ISOLATES IT, and the first row cannot.
    `Layne Riggs` inside `Layne Riggs Racing` IS a strict prefix, so a gate
    widened to `leader_is_team or leader_team_name` still returns "leads" there
    and the control passes while measuring nothing. The row that separates the
    two is a non-team whose supplied name is NOT a prefix: gated, it keeps
    #4700's singular; ungated, the orthographic arm makes it "lead".
    """
    assert leader_agreement_verb("Layne Riggs", False, "Layne Riggs Racing") == "leads"
    assert leader_agreement_verb("Layne Riggs", False, "Kaulig Racing") == "leads"
    assert leader_agreement_verb(None, True, "Texas Longhorns") == "leads"
    assert leader_agreement_verb("", True, "Texas Longhorns") == "leads"


# ── The prefix test itself ───────────────────────────────────────────────────


def test_a_strict_prefix_ends_on_a_word_boundary():
    """`Texas` is inside `Texas Longhorns`; it is not inside `Texassippi FC`.

    Substring containment would fire on any name that merely starts with the
    same letters, which is orthography wearing a join's clothes.
    """
    assert _printed_name_omits_nickname("Texas", "Texas Longhorns") is True
    assert _printed_name_omits_nickname("Texas", "Texassippi FC") is False
    assert _printed_name_omits_nickname("Texas", "Longhorns of Texas") is False


def test_an_equal_name_is_not_a_stripped_nickname():
    """STRICT prefix. Equality means the nickname is printed, so #4700 decides."""
    assert (
        _printed_name_omits_nickname("Los Angeles Dodgers", "Los Angeles Dodgers")
        is False
    )
    assert (
        leader_agreement_verb("Los Angeles Dodgers", True, "Los Angeles Dodgers")
        == "lead"
    )


def test_an_absent_team_name_is_not_a_stripped_nickname():
    assert _printed_name_omits_nickname("Texas", None) is False
    assert _printed_name_omits_nickname("Texas", "") is False
    assert _printed_name_omits_nickname("", "Texas Longhorns") is False


def test_case_and_spacing_do_not_decide_it():
    """The two strings come from two tables and are not guaranteed to match byte
    for byte; a verb must not hinge on which one was title-cased."""
    assert _printed_name_omits_nickname("texas", "Texas Longhorns") is True
    assert _printed_name_omits_nickname("Texas ", " Texas  Longhorns") is True


def test_a_printed_plural_nickname_outranks_the_prefix_test():
    """`Sox` is the stronger evidence of the two.

    `_PLURAL_TEAM_NICKNAMES_WITHOUT_S` is asked first on purpose: a printed
    plural nickname keeps its verb even if the stored name runs on past it.
    """
    assert leader_agreement_verb("Boston Red Sox", True, "Boston Red Sox FC") == "lead"


# ── The templates, driven end to end ─────────────────────────────────────────

#: The same production highlight-reason vocabulary #4700's class guard uses —
#: CERT-2482 blocked that guard's first presentation for inventing keys, and a
#: second file inventing its own would measure nothing in exactly the same way.
LEADER_REASON_SETS = [
    [],
    ["multi_source"],
    ["leader_change"],
    ["resolving_soon_7d"],
    ["resolving_soon_30d"],
]


def _has_word(text: str, word: str) -> bool:
    """Whole-word match — the 30-day headline ends its clause with a semicolon,
    so a space-delimited probe sails straight past the verb (#4700's `_has_word`)."""
    return bool(re.search(rf"\b{re.escape(word)}\b", text or ""))


def _rendered(reasons, name, team_name):
    """Every reader-visible string the three generators produce for one leader."""
    common = dict(
        highlight_reasons=reasons,
        leader_name=name,
        leader_probability=0.30,
        rendered_leader_percent=30,
        leader_is_team=True,
        leader_team_name=team_name,
        market_name="College Football National Championship Winner",
    )
    headline = generate_futures_headline(**common)
    return [
        headline,
        generate_futures_reason(**common),
        generate_futures_context_summary(
            headline=headline,
            highlight_reasons=reasons,
            market_name=common["market_name"],
            leader_name=name,
            leader_probability=0.30,
            rendered_leader_percent=30,
            leader_is_team=True,
            leader_team_name=team_name,
        ),
    ]


@pytest.mark.parametrize("reasons", LEADER_REASON_SETS)
def test_every_leads_template_agrees_on_a_place(reasons):
    """A place-name team never gets "lead"; a printed plural nickname never
    loses it. Class guard over all three generators, so a new branch that
    resolves the verb itself fails here rather than on the page."""
    for text in _rendered(reasons, "Texas", "Texas Longhorns"):
        assert not _has_word(text, "lead"), f"place took a plural verb: {text!r}"
    for text in _rendered(reasons, "Los Angeles Dodgers", "Los Angeles Dodgers"):
        assert not _has_word(
            text, "leads"
        ), f"plural team lost its plural verb: {text!r}"


# ── The fix has to reach every caller that composes a caption ────────────────


def test_every_caption_call_site_passes_the_team_name():
    """A source scan, because the defect's twin is a call site that never asked.

    `leader_is_team` reaches nine call sites in `feed.py` — three per serializer,
    plus the admin trace that exists to reproduce the card. A tenth added without
    `leader_team_name` would print `Texas lead` on exactly one surface, which is
    the shape this file was opened on: the same market reading two ways on two
    screens. Pinned on the pairing rather than on the count so adding a
    serializer is not a red.
    """
    source = (
        Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
    ).read_text(encoding="utf-8")
    lines = source.split("\n")
    sites = [
        index
        for index, line in enumerate(lines)
        if line.strip() == "leader_is_team=_leader_outcome_is_team(outcomes_data),"
    ]
    assert sites, "the #4700 call sites moved — this scan is measuring nothing"
    for index in sites:
        assert (
            lines[index + 1].strip()
            == "leader_team_name=_leader_outcome_team_name(outcomes_data),"
        ), f"feed.py:{index + 1} composes a caption without the team name"


def test_every_outcome_row_that_carries_team_id_carries_team_name():
    """The row builders, structurally — the link a call-site scan cannot see.

    `leader_team_name` reaching all nine call sites proves nothing if the dict
    those call sites read never got the name onto row 0. There are three
    builders (the Discover serializer, the Sports serializer, the admin trace)
    and #4700 had to be applied to all three; a fourth added with `team_id` and
    without `team_name` would serve `Texas lead` on its own surface only, which
    is the two-screens-two-grammars shape this issue was opened on.
    """
    source = (
        Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
    ).read_text(encoding="utf-8")
    rows = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Dict)
        and any(
            isinstance(key, ast.Constant) and key.value == "team_id"
            for key in node.keys
            if key is not None
        )
    ]
    assert len(rows) == 3, f"the outcome row builders moved: found {len(rows)}"
    for row in rows:
        keys = {key.value for key in row.keys if isinstance(key, ast.Constant)}
        assert (
            "team_name" in keys
        ), f"feed.py:{row.lineno} builds an outcome row with team_id and no team_name"


def test_every_row_builder_actually_resolves_the_names():
    """And the key must be filled from a real lookup, not left to default.

    🔴 THIS IS THE INERTNESS GUARD, and the key-presence scan above cannot be
    it. `"team_name": team_names.get(...)` over a `team_names` that nobody ever
    populated is byte-for-byte as green as the fix and serves `Texas lead` on
    every card — the whole chain present, the answer always `None`, every other
    test in this file still passing. So each builder must either resolve the map
    in its own body (the two serializers) or take it as a parameter from a
    caller that does (the admin trace).
    """
    source = (
        Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    def _builds_a_team_row(function):
        return any(
            isinstance(node, ast.Dict)
            and any(
                isinstance(key, ast.Constant) and key.value == "team_name"
                for key in node.keys
                if key is not None
            )
            for node in ast.walk(function)
        )

    def _resolves_the_map(function):
        takes_it = any(
            argument.arg == "team_names"
            for argument in function.args.args + function.args.kwonlyargs
        )
        calls_it = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_team_names_by_id"
            for node in ast.walk(function)
        )
        return takes_it or calls_it

    builders = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _builds_a_team_row(node)
    ]
    assert len(builders) == 3, f"the outcome row builders moved: {len(builders)}"
    for builder in builders:
        assert _resolves_the_map(
            builder
        ), f"{builder.name} builds a team_name it never looks up"


class _RecordingSession:
    """A stub session that records the statement and replays fixed rows."""

    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self._rows)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_team_names_are_resolved_off_both_row_carriers():
    """`_team_names_by_id` reads `team_id` from `__dict__`, never by attribute.

    Discover serves from rebuilt `FuturesOutcomeSnapshot` rows and Sports from
    hydrated ORM rows, and the two must answer identically or the same market
    reads two ways on two screens. `__dict__.get` is also the only safe read
    here: `getattr` on an unprojected mapped attribute lazy-loads and raises
    `MissingGreenlet` inside the per-item serializer, emptying the whole futures
    pool (gotcha #42).
    """
    from app.routes.feed import _team_names_by_id
    from app.utils.futures_market_snapshot import (
        OUTCOME_ROW_COLUMNS,
        FuturesOutcomeSnapshot,
    )

    snapshot_values = [
        834 if column == "team_id" else None for column in OUTCOME_ROW_COLUMNS
    ]
    orm_like = SimpleNamespace(team_id=15263)
    unlinked = SimpleNamespace(team_id=None)

    session = _RecordingSession([(834, "Texas Longhorns"), (15263, "Georgia Bulldogs")])
    names = await _team_names_by_id(
        session,
        [FuturesOutcomeSnapshot(snapshot_values), orm_like, unlinked],
    )

    assert names == {834: "Texas Longhorns", 15263: "Georgia Bulldogs"}
    assert len(session.statements) == 1, "one PK SELECT for the whole pool"
    asked = session.statements[0].whereclause.right.value
    assert sorted(asked) == [834, 15263], "an id was dropped or invented"


@pytest.mark.asyncio
async def test_a_pool_with_no_linked_team_asks_nothing():
    """The short-circuit is load-bearing: most futures pools link no team at all
    (`team_id` was populated on 3 of 45 served leaders when #4700 measured it),
    so an unconditional SELECT would be a per-request round trip that answers
    `{}`."""
    from app.routes.feed import _team_names_by_id

    session = _RecordingSession([])
    assert await _team_names_by_id(session, [SimpleNamespace(team_id=None)]) == {}
    assert await _team_names_by_id(session, []) == {}
    assert session.statements == []


def test_the_leader_row_carries_the_team_name():
    """`_leader_outcome_team_name` reads row 0 and nothing else.

    Same contract as `_leader_outcome_is_team`: `outcomes_data[0]` IS the leader,
    and unknown reads None so the copy is #4700's.
    """
    from app.routes.feed import _leader_outcome_team_name

    assert _leader_outcome_team_name([]) is None
    assert _leader_outcome_team_name([{"name": "Texas"}]) is None
    assert (
        _leader_outcome_team_name(
            [
                {"name": "Texas", "team_id": 834, "team_name": "Texas Longhorns"},
                {
                    "name": "Ohio State",
                    "team_id": 9,
                    "team_name": "Ohio State Buckeyes",
                },
            ]
        )
        == "Texas Longhorns"
    )
