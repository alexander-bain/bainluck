"""#6955 — the club-noun rail, guarded without a database.

CERT-3072 blocked the classifier half of #6955 for a reason that is the whole
subject of this file: the fix was correct and the reader's four cards did not
move, because no poll will ever hand those rows back. This rail addresses them
by id. So the tests that matter are not "does it write the right value" — they
are:

1. **The rail must not become a second classifier.** Same guard as the two
   enumerated siblings, for the same reason: the realistic decay is somebody
   adding "just one" keyword, after which the repair and the poller disagree and
   nothing notices. Here it is sharper than usual, because the alternative to
   asking the venue is a ``name ILIKE '%hurricane%'`` predicate that would sweep
   the 160 genuinely-sport events the census found onto the weather shelf.

2. **The venue gate must DISCRIMINATE.** The subject fixtures and the control
   fixtures are real Gamma payloads captured 2026-09-18; the controls are the
   half that can fail. A fixture that misrepresented production would pass every
   ship assertion, and only a control catches it.

3. 🔴 **The MEMBERSHIP gate is the one this rail lives or dies on**, and it is
   the reason this is a module rather than four ids appended to a sibling. The
   sibling selects on ``market_metadata->>'polymarket_event_id'``, which on this
   bound reaches 4 of 12 rows and misses ALL FOUR CARDS #6955 WAS FILED ABOUT —
   a repair that would have passed its own after-check while the defect stayed
   on screen. The obvious correction (union in the ``group_id``) admits the four
   members and also admits a Gaza ceasefire market sitting under the Kraken IPO
   container. Both halves are asserted below, in both directions.

4. **The served payload must carry the repair.** A column nothing renders is an
   inert fix. ``_format_futures_for_search`` is the function that produced the
   payload read off production 2026-09-18, and it serves ``llm_sport_category``
   verbatim — so the route-level assertion is exact rather than a restatement.

NOT tested here: the write against real Postgres. That is the D51 dry run on
production, which returns the whole plan before anything is applied.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tasks import repair_polymarket_club_noun_category as rail


# ---------------------------------------------------------------------------
# Real Gamma payloads, captured 2026-09-18, trimmed to the three keys the
# shipped cascade reads (`title`, `tags`, `markets[].question`). The market
# lists are COMPLETE for the subjects, because the membership gate reads them.
# ---------------------------------------------------------------------------

SUBJECT_HURRICANE_COUNT_ARCHIVED = {
    # 744619 — holds the four cards #6955 names. active=False closed=True
    # archived=True at the venue, which is exactly why no poll reaches it.
    "title": "How many hurricanes will form during the Atlantic Hurricane Season in 2026?",
    "tags": [
        {"label": "Weather"},
        {"label": "climate"},
        {"label": "hurricane"},
        {"label": "Hurricane Season"},
    ],
    "markets": [
        {"question": "Will there be 1-3 hurricanes during the Atlantic Hurricane Season in 2026?"},
        {"question": "Will there be 4-6 hurricanes during the Atlantic Hurricane Season in 2026?"},
        {"question": "Will there be 7+ hurricanes during the Atlantic Hurricane Season in 2026?"},
        {"question": "Will there be 0 hurricanes during the Atlantic Hurricane Season in 2026?"},
    ],
}

SUBJECT_HURRICANE_COUNT_ACTIVE = {
    # 765230 — the ACTIVE replacement family, identical title, same defect, and
    # still outside the poller's newest-first horizon.
    "title": "How many hurricanes will form during the Atlantic Hurricane Season in 2026?",
    "tags": [
        {"label": "Weather"},
        {"label": "climate"},
        {"label": "hurricane"},
        {"label": "Hurricanes"},
    ],
    "markets": [
        {"question": "Will there be 0 hurricanes during the Atlantic Hurricane Season in 2026?"},
        {"question": "Will there be 1-3 hurricanes during the Atlantic Hurricane Season in 2026?"},
        {"question": "Will there be 4-6 hurricanes during the Atlantic Hurricane Season in 2026?"},
        {"question": "Will there be 7+ hurricanes during the Atlantic Hurricane Season in 2026?"},
    ],
}

SUBJECT_LANDFALL = {
    # 743877
    "title": "Will 2 or more hurricanes make landfall in the US in 2026?",
    "tags": [
        {"label": "Weather"},
        {"label": "climate"},
        {"label": "hurricane"},
        {"label": "Hurricane Season"},
    ],
    "markets": [{"question": "Will 2 or more hurricanes make landfall in the US in 2026?"}],
}

SUBJECT_KRAKEN_IPO = {
    # 16183 — the crypto arm of the bound, and the container that holds the
    # stranger the membership gate has to refuse.
    "title": "Kraken IPO by ___ ?",
    "tags": [
        {"label": "Crypto"},
        {"label": "exchange"},
        {"label": "Finance"},
        {"label": "Business"},
        {"label": "2025 Predictions"},
        {"label": "Featured"},
        {"label": "IPOs"},
        {"label": "Crypto Listings"},
    ],
    "markets": [
        {"question": "Kraken IPO in 2025?"},
        {"question": "Kraken IPO by March 31, 2026?"},
        {"question": "Kraken IPO by December 31, 2026?"},
        {"question": "Kraken IPO by June 30, 2026?"},
        {"question": "Kraken IPO by March 31, 2027?"},
        {"question": "Kraken IPO by June 30, 2027?"},
        {"question": "Kraken IPO by December 31, 2027?"},
    ],
}

# ── The controls. These are the half that can fail. ─────────────────────────

CONTROL_NHL_HURRICANES = {
    # 970184 — a real Carolina Hurricanes fixture. If the gate ever stops
    # discriminating, this is the row that ends up on the weather shelf.
    "title": "Capitals vs. Hurricanes",
    "tags": [
        {"label": "Sports"},
        {"label": "NHL"},
        {"label": "Games"},
        {"label": "Hockey"},
    ],
    "markets": [
        {"question": "Capitals vs. Hurricanes"},
        {"question": "Capitals vs. Hurricanes: O/U 4.5"},
        {"question": "Capitals vs. Hurricanes: O/U 5.5"},
    ],
}

CONTROL_NHL_KRAKEN = {
    # 983261 — a real Seattle Kraken fixture.
    "title": "Flames vs. Kraken",
    "tags": [
        {"label": "Sports"},
        {"label": "NHL"},
        {"label": "Games"},
        {"label": "Hockey"},
    ],
    "markets": [
        {"question": "Flames vs. Kraken"},
        {"question": "Spread: Kraken (-1.5)"},
        {"question": "Flames vs. Kraken: O/U 5.5"},
    ],
}

SUBJECTS = [
    (SUBJECT_HURRICANE_COUNT_ARCHIVED, "744619 hurricane count (archived)", "weather"),
    (SUBJECT_HURRICANE_COUNT_ACTIVE, "765230 hurricane count (active)", "weather"),
    (SUBJECT_LANDFALL, "743877 landfall", "weather"),
    (SUBJECT_KRAKEN_IPO, "16183 Kraken IPO", "crypto"),
]

CONTROLS = [
    (CONTROL_NHL_HURRICANES, "970184 Capitals vs. Hurricanes"),
    (CONTROL_NHL_KRAKEN, "983261 Flames vs. Kraken"),
]


# ---------------------------------------------------------------------------
# 1 — the rail must not become a second classifier
# ---------------------------------------------------------------------------

#: Every sport and non-sport category token the cascade can return. A literal
#: from this set appearing in the rail's own source means it has started
#: deciding rather than asking.
_CATEGORY_TOKENS = {
    "hockey", "basketball", "football", "baseball", "soccer", "tennis", "golf",
    "mma", "boxing", "cricket", "rugby", "motorsports", "olympics", "esports",
    "horse_racing", "lacrosse", "aussierules", "table_tennis",
    "weather", "crypto", "politics", "economics", "tech", "health",
    "geopolitics", "legal", "culture", "entertainment",
}


def test_the_rail_carries_no_sport_rules_of_its_own():
    """No category literal anywhere in the executable source.

    `"other"` is the single allowed exception: it is the poller's own
    honest-empty sentinel, not a verdict this rail forms, and refusing it is the
    guard that stops a real value being overwritten with the default.
    """
    source = inspect.getsource(rail)
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.strip().lower() in _CATEGORY_TOKENS:
                offenders.append((node.lineno, node.value))
    assert not offenders, (
        "the rail names a category in its own source, so it has become a second "
        f"classifier that can drift from the poller: {offenders}"
    )


def test_the_rail_does_not_import_re():
    """A regex here would be a name rule, which is the thing the venue replaces."""
    tree = ast.parse(inspect.getsource(rail))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "re" not in imported, (
        "the rail imports `re`; a name rule here would drift from the shipped "
        "cascade, which is the failure this design exists to prevent"
    )


def test_the_rail_actually_calls_the_shipped_cascade():
    """The guards above are satisfied by a rail that decides NOTHING.

    So assert the positive: the shipped cascade is the thing consulted. Without
    this, a rail that returned a hard-coded verdict would pass both guards.
    """
    source = inspect.getsource(rail)
    assert "classify_event_payload" in source, (
        "the rail must run the SHIPPED ingest cascade, not a local rule"
    )
    assert "from app.tasks.repair_polymarket_sport_category import classify_event_payload" in source


def test_the_event_id_list_is_an_enumerated_bound():
    """A bound that grows into a population has stopped being attended."""
    assert 1 <= len(rail.CLUB_NOUN_EVENT_IDS) <= 20, (
        "this is an ATTENDED, terminating repair over an enumerated bound, not a "
        "population — if the class is really this big it needs a censused drain "
        "with a cursor, like the `polymarket-sport-category` sibling"
    )
    assert len(set(rail.CLUB_NOUN_EVENT_IDS)) == len(rail.CLUB_NOUN_EVENT_IDS)
    assert all(e.isdigit() for e in rail.CLUB_NOUN_EVENT_IDS)


def test_the_four_cards_the_issue_names_are_in_the_bound():
    """#6955's specimens live on 744619; its active twin is 765230."""
    assert "744619" in rail.CLUB_NOUN_EVENT_IDS
    assert "765230" in rail.CLUB_NOUN_EVENT_IDS


# ---------------------------------------------------------------------------
# 2 — the venue gate must discriminate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload,label,expected", SUBJECTS, ids=[s[1] for s in SUBJECTS])
def test_the_shipped_cascade_moves_the_subjects_off_the_sport_shelf(payload, label, expected):
    from app.tasks.repair_polymarket_sport_category import classify_event_payload

    _category, llm = classify_event_payload(payload)
    assert llm == expected, f"{label}: venue tags say {expected}, cascade said {llm}"


@pytest.mark.parametrize("payload,label", CONTROLS, ids=[c[1] for c in CONTROLS])
def test_the_shipped_cascade_leaves_real_hockey_alone(payload, label):
    """🔴 The half that can fail.

    A real Carolina Hurricanes fixture and a real Seattle Kraken fixture, from
    the 160 events the census confirmed. They are not excluded by a predicate —
    they ride the same gate and the venue's own `NHL`/`Hockey` tags keep them
    where they are.
    """
    from app.tasks.repair_polymarket_sport_category import classify_event_payload

    _category, llm = classify_event_payload(payload)
    assert llm == "hockey", f"{label}: a real NHL fixture must stay hockey, got {llm}"


# ---------------------------------------------------------------------------
# 3 — the membership gate, in both directions
# ---------------------------------------------------------------------------


def test_the_venue_market_list_names_the_four_member_cards():
    """The rows the metadata key misses are exactly the ones the venue names."""
    named = rail.venue_market_questions(SUBJECT_HURRICANE_COUNT_ARCHIVED)
    for question in (
        "Will there be 0 hurricanes during the Atlantic Hurricane Season in 2026?",
        "Will there be 1-3 hurricanes during the Atlantic Hurricane Season in 2026?",
        "Will there be 4-6 hurricanes during the Atlantic Hurricane Season in 2026?",
        "Will there be 7+ hurricanes during the Atlantic Hurricane Season in 2026?",
    ):
        assert question.strip().casefold() in named, question


def test_the_venue_does_not_name_the_stranger_in_the_kraken_container():
    """🔴 The Gaza ceasefire row, which `group_id` alone would have swept in.

    `13791106` sits under `group_id = 'polymarket:16183'` and is nothing to do
    with a Kraken IPO. Writing `crypto` onto it would be a new defect committed
    while fixing an old one.
    """
    named = rail.venue_market_questions(SUBJECT_KRAKEN_IPO)
    assert "israel x hamas ceasefire phase ii by february 28?" not in named


def test_the_membership_gate_is_case_and_whitespace_insensitive():
    """Two spellings of one string, not a fuzzy match."""
    named = rail.venue_market_questions(
        {"markets": [{"question": "  Kraken IPO in 2025?  "}]}
    )
    assert "kraken ipo in 2025?" in named


def test_venue_market_questions_survives_a_junk_market_list():
    assert rail.venue_market_questions({}) == set()
    assert rail.venue_market_questions({"markets": None}) == set()
    assert rail.venue_market_questions({"markets": ["not a dict", {"question": None}]}) == set()


def test_the_select_reaches_the_group_and_not_only_the_metadata_key():
    """🔴 The trap this module exists for, asserted on the SQL itself.

    On this bound `market_metadata->>'polymarket_event_id'` reaches 4 of 12 rows
    and misses all four cards #6955 names. If somebody "simplifies" this SELECT
    back to the sibling's single predicate, the rail keeps passing its own
    counts and stops fixing the defect.
    """
    source = inspect.getsource(rail.repair)
    assert "fm.group_id = :gid" in source, (
        "the SELECT must reach member rows through the group; the metadata key "
        "alone finds only the container row"
    )
    assert "market_metadata->>'polymarket_event_id' = :eid" in source, (
        "the SELECT must still reach the container row, whose NAME is the event "
        "title and therefore appears in no market list"
    )
    assert "has_event_id" in source, (
        "the container row must be distinguishable, or the membership gate will "
        "ask the venue to name a title it never lists and refuse the parent"
    )


# ---------------------------------------------------------------------------
# 4 — the plan, driven end to end against a stub session
# ---------------------------------------------------------------------------


class _Row:
    def __init__(self, id, name, status, llm_sport_category, has_event_id):
        self.id = id
        self.name = name
        self.status = status
        self.llm_sport_category = llm_sport_category
        self.has_event_id = has_event_id


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def all(self):
        return self._rows


class _StubSession:
    """The three statement shapes `repair()` issues, and nothing else.

    `moves` lets a test say which ids the compare-and-set actually matched, so a
    PARTIAL apply can be driven. Default None means "all of them".
    """

    def __init__(self, rows_by_event, moves=None):
        self.rows_by_event = rows_by_event
        self.moves = moves
        self.updates: list[dict] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "SET LOCAL" in sql:
            return _Result()
        if "UPDATE" in sql.upper():
            self.updates.append(dict(params))
            # RETURNING id — the rail reads WHICH rows moved, not how many.
            ids = (
                params["ids"]
                if self.moves is None
                else [i for i in params["ids"] if i in self.moves]
            )
            return _Result([(i,) for i in ids], rowcount=len(ids))
        if "SELECT" in sql.upper():
            return _Result(self.rows_by_event.get(params["eid"], []))
        raise AssertionError(f"unexpected statement:\n{sql}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _run(session, monkeypatch, verdicts, apply=False):
    """Drive `repair()` with the venue stubbed to `verdicts` (event_id -> payload)."""

    async def fake_fetch(_client, event_id):
        entry = verdicts.get(event_id)
        if entry is None:
            return "indeterminate", None
        if entry == "404":
            return "not_at_venue", None
        return "ok", entry

    monkeypatch.setattr(rail, "_fetch_event", fake_fetch)
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)
    return asyncio.run(rail.repair(session, apply=apply))


#: The real 744619 rows, production 2026-09-18. Note `has_event_id` is True on
#: the container ONLY — that asymmetry is the defect this rail navigates.
def _hurricane_rows():
    return [
        _Row(57005138, "How many hurricanes will form during the Atlantic Hurricane Season in 2026?", "open", "hockey", True),
        _Row(57005139, "Will there be 1-3 hurricanes during the Atlantic Hurricane Season in 2026?", "open", "hockey", False),
        _Row(57005140, "Will there be 4-6 hurricanes during the Atlantic Hurricane Season in 2026?", "open", "hockey", False),
        _Row(57005141, "Will there be 7+ hurricanes during the Atlantic Hurricane Season in 2026?", "open", "hockey", False),
        _Row(57005142, "Will there be 0 hurricanes during the Atlantic Hurricane Season in 2026?", "open", "hockey", False),
    ]


#: The real 16183 rows, including the stranger.
def _kraken_rows():
    return [
        _Row(112848, "Kraken IPO by ___ ?", "open", "hockey", True),
        _Row(13791103, "Kraken IPO in 2025?", "resolved", "tech", False),
        _Row(13791104, "Kraken IPO by March 31, 2026?", "resolved", "tech", False),
        _Row(13791105, "Kraken IPO by December 31, 2026?", "resolved", "tech", False),
        _Row(13791106, "Israel x Hamas Ceasefire Phase II by February 28?", "resolved", "tech", False),
    ]


def test_all_five_hurricane_rows_are_planned_including_the_four_the_metadata_key_misses(monkeypatch):
    """🔴 The ship, in one assertion.

    Four of these five rows carry no `polymarket_event_id`. They are the cards
    a reader meets on /search. If this list ever comes back as `[57005138]`, the
    rail has regressed to the sibling's predicate and fixes nothing visible.
    """
    session = _StubSession({"744619": _hurricane_rows()})
    monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_IDS", ("744619",))

    out = _run(session, monkeypatch, {"744619": SUBJECT_HURRICANE_COUNT_ARCHIVED})

    assert sorted(p["id"] for p in out["planned"]) == [
        57005138, 57005139, 57005140, 57005141, 57005142
    ]
    assert {p["after"] for p in out["planned"]} == {"weather"}
    assert {p["before"] for p in out["planned"]} == {"hockey"}
    assert out["counts"]["rows_not_named_by_venue"] == 0
    assert out["terminal"] == "dry_run"
    assert session.updates == []


def test_the_stranger_in_the_kraken_container_is_refused_by_id(monkeypatch):
    """🔴 The other direction. The group is not trusted on its own."""
    session = _StubSession({"16183": _kraken_rows()})
    monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_IDS", ("16183",))

    out = _run(session, monkeypatch, {"16183": SUBJECT_KRAKEN_IPO})

    planned_ids = {p["id"] for p in out["planned"]}
    assert 13791106 not in planned_ids, (
        "a Gaza ceasefire market was about to be filed under crypto"
    )
    assert sorted(planned_ids) == [112848, 13791103, 13791104, 13791105]
    assert out["counts"]["rows_not_named_by_venue"] == 1
    assert [r["id"] for r in out["not_named_by_venue"]] == [13791106]
    assert out["not_named_by_venue"][0]["reason"] == "not_named_by_venue"


def test_a_real_nhl_event_is_refused_by_the_venue(monkeypatch):
    """The control, through the whole rail rather than the cascade alone."""
    session = _StubSession(
        {"970184": [_Row(999, "Capitals vs. Hurricanes", "open", "hockey", True)]}
    )
    monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_IDS", ("970184",))

    out = _run(session, monkeypatch, {"970184": CONTROL_NHL_HURRICANES})

    assert out["planned"] == []
    assert out["counts"]["unchanged"] == 1
    assert any(r["reason"] == "venue_agrees" for r in out["refused"])
    assert session.updates == []


def test_a_dry_run_never_writes(monkeypatch):
    session = _StubSession({"744619": _hurricane_rows()})
    monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_IDS", ("744619",))

    out = _run(session, monkeypatch, {"744619": SUBJECT_HURRICANE_COUNT_ARCHIVED}, apply=False)

    assert out["counts"]["rows_written"] == 0
    assert session.updates == []
    assert session.commits == 0
    assert out["restore_sql"], "the D51 undo must travel with the DRY RUN, not just the apply"


def test_an_apply_writes_the_planned_rows_and_compare_and_sets(monkeypatch):
    session = _StubSession({"744619": _hurricane_rows()})
    monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_IDS", ("744619",))

    out = _run(session, monkeypatch, {"744619": SUBJECT_HURRICANE_COUNT_ARCHIVED}, apply=True)

    assert out["counts"]["rows_written"] == 5
    assert out["terminal"] == "changed"
    assert len(session.updates) == 1
    write = session.updates[0]
    assert write["llm"] == "weather"
    assert sorted(write["ids"]) == [57005138, 57005139, 57005140, 57005141, 57005142]
    # 🔴 The compare-and-set value. Without it a re-ingest that landed between
    # the SELECT and the UPDATE is clobbered by a verdict computed before it.
    assert write["before"] == "hockey"
    assert sorted(p["id"] for p in out["applied"]) == [
        57005138, 57005139, 57005140, 57005141, 57005142
    ]


def test_two_before_values_split_into_two_compare_and_sets(monkeypatch):
    """The Kraken container holds `hockey` and `tech`. One UPDATE cannot serve both."""
    session = _StubSession({"16183": _kraken_rows()})
    monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_IDS", ("16183",))

    out = _run(session, monkeypatch, {"16183": SUBJECT_KRAKEN_IPO}, apply=True)

    befores = sorted(u["before"] for u in session.updates)
    assert befores == ["hockey", "tech"]
    assert all(u["llm"] == "crypto" for u in session.updates)
    assert out["counts"]["rows_written"] == 4


def test_a_partial_compare_and_set_restores_only_the_rows_that_moved(monkeypatch):
    """The undo must name the rows that MOVED, not the rows we hoped to move.

    A rowcount says HOW MANY matched and never WHICH, so an undo built from the
    plan could write a stale `before` over the fresher value that caused the
    miss — turning the restore into a second defect.
    """
    session = _StubSession({"744619": _hurricane_rows()}, moves={57005139, 57005142})
    monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_IDS", ("744619",))

    out = _run(session, monkeypatch, {"744619": SUBJECT_HURRICANE_COUNT_ARCHIVED}, apply=True)

    assert out["counts"]["rows_written"] == 2
    assert sorted(p["id"] for p in out["applied"]) == [57005139, 57005142]
    assert len(out["planned"]) == 5
    # The restore names the two that moved and NOT the three that did not.
    assert "57005139, 57005142" in out["restore_sql"]
    assert "57005138" not in out["restore_sql"]


def test_a_transient_venue_failure_is_never_a_verdict(monkeypatch):
    session = _StubSession({"744619": _hurricane_rows()})
    monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_IDS", ("744619",))

    out = _run(session, monkeypatch, {}, apply=True)

    assert out["counts"]["indeterminate"] == 1
    assert out["counts"]["rows_written"] == 0
    assert session.updates == []
    assert out["terminal"] == "no_rows_written"


def test_a_404_is_reported_separately_from_a_timeout(monkeypatch):
    session = _StubSession({"744619": _hurricane_rows()})
    monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_IDS", ("744619",))

    out = _run(session, monkeypatch, {"744619": "404"})

    assert out["counts"]["not_at_venue"] == 1
    assert out["counts"]["indeterminate"] == 0


def test_an_id_that_names_no_row_is_reported_by_name(monkeypatch):
    """A stale bound must be visible, not read as a small success."""
    session = _StubSession({})
    monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_IDS", ("744619",))

    out = _run(session, monkeypatch, {"744619": SUBJECT_HURRICANE_COUNT_ARCHIVED})

    assert out["missing_ids"] == ["744619"]
    assert out["counts"]["events_examined"] == 0


# ---------------------------------------------------------------------------
# 5 — the write stays one column
# ---------------------------------------------------------------------------


def _executable_source(module) -> str:
    """The module's source with every docstring and comment removed.

    🔴 Scoping matters here and getting it wrong cost a red run. This file's
    prose NAMES the columns the rail must not write, at length and on purpose —
    a guard that greps raw source therefore fires on its own explanation. The
    thing under test is what the module DOES, so strip the prose and unparse
    what is left.
    """
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            body.pop(0)
    return ast.unparse(tree)


def _assigned_columns(update_sql: str) -> set[str]:
    """The column names an UPDATE's SET clause assigns.

    🔴 Parsed, not grepped. `"category =" not in sql` is True for
    `llm_sport_category = :llm` only by accident and False for it in general —
    the substring trap, which turned this guard red the first time it ran.
    """
    set_body = update_sql.split("SET", 1)[1].split("WHERE", 1)[0]
    return {
        assignment.split("=")[0].strip()
        for assignment in set_body.split(",")
        if "=" in assignment
    }


def _update_statements() -> list[str]:
    source = inspect.getsource(rail.repair)
    return [
        chunk for chunk in source.split("text(") if "UPDATE futures_markets" in chunk
    ]


def test_the_update_writes_only_llm_sport_category():
    statements = _update_statements()
    assert statements, "no UPDATE found — this guard would pass vacuously"
    for stmt in statements:
        assert _assigned_columns(stmt) == {"llm_sport_category"}


def test_the_update_is_a_compare_and_set():
    """🔴 Found by mutation: deleting this clause left every test green.

    Asserting that `before` is PASSED proves only that a parameter is bound.
    The concurrency guard is the clause in the WHERE — without it a re-ingest
    that landed between the SELECT and the UPDATE is clobbered by a verdict
    computed before it, and the D51 restore then carries a stale `before`.
    """
    statements = _update_statements()
    assert statements, "no UPDATE found — this guard would pass vacuously"
    for stmt in statements:
        where = stmt.split("WHERE", 1)[1]
        assert "llm_sport_category IS NOT DISTINCT FROM :before" in where, (
            "the UPDATE is unconditional on the prior value"
        )


def test_the_update_never_touches_the_observation_clock():
    """🔴 CERT-2382's finding on the sibling.

    `updated_at` is rendered by the card as its own relative date. Stamping
    NOW() would leave stale prices unchanged while presenting them as observed
    just now — a TRUTH repair introducing a reader-visible lie about freshness.
    """
    assert "updated_at" not in _executable_source(rail), (
        "a column a surface RENDERS is not bookkeeping; a repair touches only "
        "the column it is repairing"
    )


def test_the_rail_never_writes_status_because_that_is_a_calibration_write():
    """🔴 CERT-3072 asked for this write by name. It is refused, and MEASURED.

    The clause — do not "preserve the venue-closed legacy event as falsely
    open" — names something real: `744619` is `closed`/`archived` at the venue
    while our rows read `open`, and they reach a reader precisely because
    `/api/events/search` filters on `status == "open"`.

    It is still refused, because `status` has only two values in production
    (`open` / `resolved`) so the clause can only be spelled `resolved`, and
    `resolved` is the calibration population's own gate. Polymarket voided the
    family by resolving all four mutually-exclusive buckets to "No", and #762's
    void fence misses them (`resolution_source='api_settlement'`, not
    `did_not_play`/`withdrew`), so flipping it would invert 2 legs into the
    published accuracy curve. Mechanism belongs to #6986, not to a taxonomy rail.

    This test pins BOTH halves — the refusal and the premise it rests on — so
    that if calibration ever stops gating on `status`, the decision re-opens
    loudly here instead of being inherited as a stored opinion.
    """
    statements = _update_statements()
    assert statements, "no UPDATE found — this guard would pass vacuously"
    for stmt in statements:
        assert "status" not in _assigned_columns(stmt), (
            "the rail assigns `status`; writing `resolved` here is a write to "
            "the calibration curve taken from a taxonomy rail — see #6986"
        )

    # The premise. Read as text: importing precompute_calibration is heavy, and
    # editing its CTEs discards every banked unit, so this never touches it.
    calibration = (
        Path(inspect.getfile(rail)).resolve().parents[1] / "routes" / "calibration.py"
    )
    assert calibration.is_file(), f"premise unreadable: {calibration} is missing"
    gate = re.compile(r"status\s*=\s*'resolved'")
    hits = len(gate.findall(calibration.read_text()))
    assert hits > 0, (
        "calibration no longer gates its population on `status = 'resolved'`. "
        "The refusal above was priced on that coupling — re-read the rail's "
        "docstring and #6986 and decide again; do not simply delete this test."
    )


def test_the_rail_touches_no_settlement_or_price_field():
    source = inspect.getsource(rail.repair)
    for forbidden in (
        "is_winner",
        "settled_at",
        "current_probability",
        "opening_probability",
        "resolution_source",
    ):
        assert forbidden not in source, (
            f"the rail reads or writes {forbidden!r}; a taxonomy repair must not "
            "touch settlement — 'settled means settled'"
        )


def test_the_restore_writes_only_llm_sport_category():
    sql = rail.restore_sql(
        [{"id": 57005139, "before": "hockey"}, {"id": 13791103, "before": "tech"}]
    )
    for line in sql.splitlines():
        assert line.startswith("UPDATE futures_markets SET llm_sport_category = ")
        assert line.count("SET") == 1


def test_the_restore_splits_by_distinct_before_value():
    sql = rail.restore_sql(
        [
            {"id": 1, "before": "hockey"},
            {"id": 2, "before": "hockey"},
            {"id": 3, "before": "tech"},
        ]
    )
    lines = sql.splitlines()
    assert len(lines) == 2
    assert "WHERE id IN (1, 2);" in sql
    assert "WHERE id IN (3);" in sql


def test_the_restore_line_is_a_statement_not_a_dict_repr():
    """A restore that looks runnable and is not is worse than none: D51 is
    granted on the strength of it."""
    sql = rail.restore_sql([{"id": 57005139, "before": "hockey"}])
    assert "{" not in sql and "}" not in sql
    assert sql.endswith(";")


def test_a_null_before_restores_to_null_not_the_string():
    sql = rail.restore_sql([{"id": 1, "before": None}])
    assert "= NULL " in sql
    assert "'None'" not in sql


def test_an_empty_plan_produces_no_restore_statement():
    assert rail.restore_sql([]) == ""


# ---------------------------------------------------------------------------
# 6 — wiring
# ---------------------------------------------------------------------------


def test_the_repair_is_registered():
    from app.routes.admin_repairs import _REPAIRS

    assert _REPAIRS["polymarket-club-noun-category"] == (
        "app.tasks.repair_polymarket_club_noun_category",
        "repair",
    )


def test_the_dispatcher_header_names_the_repair():
    """The header list has drifted behind the registry twice before; a reader
    who trusts it would conclude a deployed rail does not exist."""
    import app.routes.admin_repairs as mod

    assert "polymarket-club-noun-category" in (mod.__doc__ or "")


def test_the_rail_is_not_wired_to_a_beat():
    """ATTENDED ONLY. A terminating repair on a schedule is a standing job that
    re-asks the venue forever for rows it already fixed."""
    from app.tasks import celery_app

    schedule = celery_app.conf.beat_schedule or {}
    for name, entry in schedule.items():
        assert "club_noun" not in str(entry.get("task", "")), (
            f"beat entry {name} schedules the attended club-noun repair"
        )


# ---------------------------------------------------------------------------
# 7 — the served payload carries the repair
# ---------------------------------------------------------------------------


def _search_row(llm_sport_category: str):
    """A futures row shaped as `_format_futures_for_search` reads it.

    Values are the real 57005142 row, production 2026-09-18 — `market_tier=4`,
    `category='game_prop'`, `sport=None`, which is what makes
    `llm_sport_category` the field the card has left to badge with.
    """
    return SimpleNamespace(
        id=57005142,
        name="Will there be 0 hurricanes during the Atlantic Hurricane Season in 2026?",
        sport=None,
        category="game_prop",
        llm_sport_category=llm_sport_category,
        market_tier=4,
        market_type=None,
        status="open",
        source="polymarket",
        resolution_date=None,
        updated_at=None,
        outcomes=[],
    )


def test_the_search_payload_serves_the_repaired_category():
    """🔴 Reach. A column nothing renders is an inert fix.

    `_format_futures_for_search` is the function that produced the payload read
    off production 2026-09-18, where all five #6955 rows came back
    `llm_sport_category: "hockey"` beside a sibling weather market serving
    `"weather"`. It passes the column through verbatim, so the repair is the
    only thing standing between the stored value and the reader.
    """
    from app.routes.events import _format_futures_for_search

    before = _format_futures_for_search(_search_row("hockey"))
    after = _format_futures_for_search(_search_row("weather"))

    assert before["llm_sport_category"] == "hockey"
    assert after["llm_sport_category"] == "weather"


def test_no_search_result_for_a_repaired_row_says_hockey():
    """The route-level form of the ship, stated as the negative CERT-3072 named."""
    from app.routes.events import _format_futures_for_search

    served = [_format_futures_for_search(_search_row(cat)) for cat in ("weather", "crypto")]
    for row in served:
        assert row["llm_sport_category"] != "hockey"
        assert "hockey" not in str(row.get("sport") or "").lower()
