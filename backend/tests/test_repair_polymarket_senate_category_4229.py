"""#4229 — the Polymarket senate rail, guarded without a database.

Three classes of rot, and one thing that is NOT a test here.

1. **The rail must not become a second classifier.** Same guard as the Kalshi
   sibling and the Q495 rail, for the same reason: the realistic decay is
   somebody adding "just one" keyword, after which the repair and the poller
   disagree and nothing notices. Here it is sharper, because the alternative to
   asking the venue is a `name ILIKE '%senat%'` predicate that would sweep the
   68 genuinely-hockey events the census found.

2. **The venue gate must DISCRIMINATE**, not merely exist. The subject fixtures
   and the hockey control fixtures are real Gamma payloads captured 2026-09-09;
   the controls are the half that can fail. A fixture that misrepresented
   production would pass every ship assertion and only a control catches it.

3. **The write must stay one column.** `category` is INSERT-time only in the
   poller's own `update_set`, so a rail that wrote it would be doing something
   ingest never does.

NOT tested here: the write against real Postgres. That is the D51 dry-run on
production, which returns the whole plan before anything is applied.
"""

from __future__ import annotations

import ast
import asyncio
import inspect

import pytest

from app.tasks import celery_app, repair_polymarket_senate_category as rail


# ---------------------------------------------------------------------------
# Real Gamma payloads, captured 2026-09-09, trimmed to the three keys the
# shipped cascade reads (`title`, `tags`, `markets[].question`). The trimmed
# form was verified to return the SAME verdict as the full payload for all four.
# ---------------------------------------------------------------------------

SUBJECT_FED_CHAIR = {
    "title": "How many senators will vote for Trump's Fed chair nominee?",
    "tags": [
        {"label": "Trump"},
        {"label": "Politics"},
        {"label": "Fed"},
        {"label": "Economy"},
        {"label": "Fed Chair"},
    ],
    "markets": [
        {"question": "Will 55 senators vote “Yea” for Trump’s Fed Chair nominee?"},
        {"question": "Will 58 senators vote “Yea” for Trump’s Fed Chair nominee?"},
    ],
}

SUBJECT_BLANCHE = {
    "title": "How many senators will vote for Todd Blanche as Attorney General?",
    "tags": [
        {"label": "Trump"},
        {"label": "Todd Blanche"},
        {"label": "Politics"},
        {"label": "Senate"},
        {"label": "attorney general"},
    ],
    "markets": [
        {"question": 'Will 50 senators vote "Yea" for Todd Blanche as Attorney General?'},
        {"question": 'Will 53 senators vote "Yea" for Todd Blanche as Attorney General?'},
    ],
}

#: 🔴 THE CONTROLS. Both are `Senators` events that a name predicate would
#: sweep, and both must come back hockey. 68 of the 74 events censused look
#: like these.
CONTROL_NHL = {
    "title": "Red Wings vs. Senators",
    "tags": [{"label": "Sports"}, {"label": "NHL"}, {"label": "Games"}],
    "markets": [{"question": "Red Wings vs. Senators"}],
}

CONTROL_AHL = {
    "title": "AHL: Belleville Senators vs. Cleveland Monsters",
    "tags": [{"label": "Sports"}, {"label": "Games"}],
    "markets": [{"question": "AHL: Belleville Senators vs. Cleveland Monsters"}],
}


# ---------------------------------------------------------------------------
# 1 — no rules of its own
# ---------------------------------------------------------------------------

#: Sport tokens that would mean the rail had grown an opinion. Scanned over
#: string LITERALS in executable code only — never identifiers, and never
#: docstrings or comments, both of which discuss `hockey` and `Ottawa` by
#: necessity.
_SPORT_TOKENS = (
    "hockey",
    "nhl",
    "ahl",
    "ottawa",
    "belleville",
    "basketball",
    "baseball",
    "football",
    "soccer",
    "tennis",
    "golf",
    "politics",
)


def _parsed():
    """The module's AST with every docstring removed.

    `ast` rather than a regex, deliberately: a regex that strips `#` to
    end-of-line also eats a `#` inside a string literal, which is the trap that
    makes source-scan guards read as passing while scanning the wrong text.
    """
    source = inspect.getsource(rail)
    assert source.strip(), "getsource returned nothing — the scan would be vacuous"

    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body.pop(0)
    return tree


def _literals() -> list[str]:
    return [
        n.value
        for n in ast.walk(_parsed())
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def test_the_rail_carries_no_sport_rules_of_its_own():
    """It asks the venue through the shipped cascade and decides nothing itself."""
    haystack = " ".join(_literals()).lower()
    found = sorted(t for t in _SPORT_TOKENS if t in haystack)
    assert not found, (
        f"{found} appear as string literals in `repair_polymarket_senate_category`. "
        "This rail must take the venue's answer via `classify_event_payload` and "
        "nothing else — a category keyword here is a second classifier that will "
        "drift from the poller silently."
    )


def _sql_statements() -> list[str]:
    """String literals that are WHOLE SQL statements against `futures_markets`.

    🔴 Both halves of this filter are load-bearing, and each was added because
    the naive version failed:

    * `"UPDATE" in s` alone matched a LOG LINE ("the UPDATE for event %s did not
      land"), whose text legitimately contains the word `senate` — the guard
      below then reported a name predicate in a message.
    * requiring `WHERE` too excludes the F-STRING FRAGMENTS of `restore_sql`.
      An f-string is several `ast.Constant`s, so `"UPDATE futures_markets SET
      llm_sport_category = "` arrives as a literal with no WHERE and no second
      assignment, and a set-clause parser reads it as a one-column UPDATE by
      accident rather than by measurement.

    `restore_sql` is therefore not scanned here — it is checked by running it,
    in `test_the_restore_writes_only_llm_sport_category`.
    """
    out = []
    for s in _literals():
        upper = s.strip().upper()
        if not upper.startswith(("SELECT", "UPDATE")):
            continue
        if "FUTURES_MARKETS" not in upper or "WHERE" not in upper:
            continue
        out.append(s)
    return out


def test_the_rail_never_matches_on_a_market_name():
    """The unbounded alternative this rail exists to refuse.

    `name ILIKE '%senat%'` would sweep the 68 genuinely-hockey Ottawa/Belleville
    events the 2026-09-09 census found. The bound is ids; the verdict is the
    venue's.
    """
    statements = _sql_statements()
    assert statements, "no SQL statements found — this scan would be vacuous"

    for s in statements:
        upper = s.upper()
        assert "LIKE" not in upper, f"a name predicate appeared in SQL:\n{s}"
        assert "SENAT" not in upper, f"a name predicate appeared in SQL:\n{s}"


def test_the_rail_does_not_import_re():
    """Complements the literal scan: a rule assembled from fragments still needs `re`."""
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(_parsed())
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(_parsed())
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "re" not in imported, (
        "`repair_polymarket_senate_category` imports `re`. Matching a market name "
        "here is the second-classifier failure this module exists to avoid."
    )


def test_the_rail_actually_calls_the_shipped_cascade():
    """Absence of rules is not presence of a call.

    A module with no category keywords and no cascade call would pass the scan
    above while relabelling blindly.
    """
    source = inspect.getsource(rail)
    assert "classify_event_payload" in source, (
        "the rail no longer calls the shipped cascade; it is now deciding "
        "categories by some other means"
    )
    assert "from app.tasks.repair_polymarket_sport_category import" in source, (
        "the cascade must be imported from the sibling rail, not reimplemented"
    )


# ---------------------------------------------------------------------------
# 2 — the bound
# ---------------------------------------------------------------------------


def test_the_event_id_list_is_an_enumerated_bound():
    """Enumerated, small, unique, and strings — the ids are JSONB text values."""
    ids = rail.SENATE_EVENT_IDS
    assert isinstance(ids, tuple), "the bound must be immutable"
    assert ids, "an empty bound makes every other guard here vacuous"
    assert len(ids) == len(set(ids)), f"duplicate ids in the bound: {ids}"
    assert all(isinstance(i, str) for i in ids), (
        "polymarket_event_id is JSONB text; an int here would match no row and "
        "the rail would report `missing_ids` for a row that exists"
    )
    assert len(ids) < 25, (
        f"the bound has grown to {len(ids)}. It is an enumerated measurement, "
        "not a population — if the class is really this big it needs a censused "
        "drain with a cursor, like the `polymarket-sport-category` sibling."
    )


def test_the_fed_chair_card_is_in_the_bound():
    """#4229's own specimen. The issue is that card; a bound without it ships nothing."""
    assert "162276" in rail.SENATE_EVENT_IDS


# ---------------------------------------------------------------------------
# 3 — the venue gate discriminates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,label",
    [(SUBJECT_FED_CHAIR, "fed-chair"), (SUBJECT_BLANCHE, "blanche")],
)
def test_the_shipped_cascade_calls_the_subjects_political(payload, label):
    from app.tasks.repair_polymarket_sport_category import classify_event_payload

    _category, llm = classify_event_payload(payload)
    assert llm == "politics", f"{label} came back {llm!r}, so the ship does not happen"


@pytest.mark.parametrize("payload,label", [(CONTROL_NHL, "nhl"), (CONTROL_AHL, "ahl")])
def test_the_shipped_cascade_leaves_real_hockey_alone(payload, label):
    """🔴 The control. If this passes trivially the fixture is wrong, not the rail."""
    from app.tasks.repair_polymarket_sport_category import classify_event_payload

    _category, llm = classify_event_payload(payload)
    assert llm == "hockey", (
        f"the {label} control came back {llm!r}. A rail that moves these has "
        "relabelled 68 real hockey events."
    )


# ---------------------------------------------------------------------------
# 4 — the plan, driven end to end against a stub session
# ---------------------------------------------------------------------------


class _Row:
    def __init__(self, id, name, status, llm_sport_category):
        self.id = id
        self.name = name
        self.status = status
        self.llm_sport_category = llm_sport_category


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
        if sql.strip().upper().startswith("SELECT") or "SELECT" in sql.split("\n")[1:2][0].upper():
            return _Result(self.rows_by_event.get(params["eid"], []))
        if "UPDATE" in sql.upper():
            self.updates.append(dict(params))
            # RETURNING id — the rail reads WHICH rows moved, not how many.
            ids = params["ids"] if self.moves is None else [
                i for i in params["ids"] if i in self.moves
            ]
            return _Result([(i,) for i in ids], rowcount=len(ids))
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


def test_a_political_event_is_planned_and_a_hockey_event_is_refused(monkeypatch):
    """The whole rail in one pass: one subject moves, one control does not."""
    session = _StubSession(
        {
            "162276": [_Row(114420, "Fed chair nominee", "open", "hockey")],
            "3230": [_Row(999, "Red Wings vs. Senators", "resolved", "hockey")],
        }
    )
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", ("162276", "3230"))

    out = _run(
        session,
        monkeypatch,
        {"162276": SUBJECT_FED_CHAIR, "3230": CONTROL_NHL},
    )

    assert out["counts"]["changed"] == 1
    assert out["counts"]["unchanged"] == 1
    assert [p["id"] for p in out["planned"]] == [114420]
    assert out["planned"][0]["before"] == "hockey"
    assert out["planned"][0]["after"] == "politics"
    assert out["terminal"] == "dry_run"
    # A dry run writes nothing, and the control was refused BY THE VENUE.
    assert session.updates == []
    assert any(r["reason"] == "venue_agrees" for r in out["refused"])


def test_a_dry_run_never_writes(monkeypatch):
    session = _StubSession({"162276": [_Row(114420, "Fed chair", "open", "hockey")]})
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", ("162276",))

    out = _run(session, monkeypatch, {"162276": SUBJECT_FED_CHAIR}, apply=False)

    assert out["counts"]["rows_written"] == 0
    assert session.updates == []
    assert session.commits == 0
    assert out["restore_sql"], "the D51 undo must travel with the DRY RUN, not just the apply"


def test_an_apply_writes_the_planned_rows_and_compare_and_sets(monkeypatch):
    session = _StubSession(
        {
            "162276": [
                _Row(114420, "Fed chair", "open", "hockey"),
                _Row(114421, "Fed chair leg", "open", "hockey"),
            ]
        }
    )
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", ("162276",))

    out = _run(session, monkeypatch, {"162276": SUBJECT_FED_CHAIR}, apply=True)

    assert out["counts"]["rows_written"] == 2
    assert out["terminal"] == "changed"
    assert len(session.updates) == 1
    write = session.updates[0]
    assert write["llm"] == "politics"
    assert sorted(write["ids"]) == [114420, 114421]
    # 🔴 The compare-and-set value. Without it a re-ingest that landed between
    # the SELECT and the UPDATE is clobbered by a verdict computed before it.
    assert write["before"] == "hockey"
    # The undo is built from what moved, and here everything did.
    assert sorted(p["id"] for p in out["applied"]) == [114420, 114421]


def test_a_partial_compare_and_set_restores_only_the_rows_that_moved(monkeypatch):
    """🔴 CERT-2382's nonblocking follow-up `4229-D51-RESTORE-TRACKS-ACTUAL-WRITES`.

    The compare-and-set is allowed to match fewer rows than planned — a
    re-ingest landing between the SELECT and the UPDATE is exactly what it is
    for. A rowcount says HOW MANY matched and never WHICH, so an undo built from
    the plan would write a stale `before` over the fresher value that caused the
    miss, turning the restore into a second defect. `RETURNING id` is what makes
    it exact.
    """
    session = _StubSession(
        {
            "162276": [
                _Row(114420, "Fed chair", "open", "hockey"),
                _Row(114421, "Fed chair leg", "open", "hockey"),
            ]
        },
        moves={114420},  # 114421 was re-ingested underneath us
    )
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", ("162276",))

    out = _run(session, monkeypatch, {"162276": SUBJECT_FED_CHAIR}, apply=True)

    assert out["counts"]["rows_written"] == 1
    assert [p["id"] for p in out["applied"]] == [114420]
    assert len(out["planned"]) == 2, "the plan still records what was intended"
    assert "114420" in out["restore_sql"]
    assert "114421" not in out["restore_sql"], (
        "the undo names a row the database never moved; restoring it would "
        "overwrite the fresher value that caused the compare-and-set to miss"
    )


def test_a_dry_runs_restore_is_built_from_the_plan(monkeypatch):
    """Nothing moved, so `applied` is empty — but the operator still needs the undo."""
    session = _StubSession({"162276": [_Row(114420, "Fed chair", "open", "hockey")]})
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", ("162276",))

    out = _run(session, monkeypatch, {"162276": SUBJECT_FED_CHAIR}, apply=False)

    assert out["applied"] == []
    assert "114420" in out["restore_sql"], (
        "a dry run must still show the undo for the write it is proposing"
    )


def test_a_transient_venue_failure_is_never_a_verdict(monkeypatch):
    """#36 — a 429 must not be recorded as a category. It writes nothing at all."""
    session = _StubSession({"162276": [_Row(114420, "Fed chair", "open", "hockey")]})
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", ("162276",))

    out = _run(session, monkeypatch, {}, apply=True)  # no entry -> indeterminate

    assert out["counts"]["indeterminate"] == 1
    assert out["counts"]["changed"] == 0
    assert out["counts"]["rows_written"] == 0
    assert session.updates == []
    # Gotcha #53: the zero-yield case is NAMED, not four silent zeros.
    assert out["terminal"] == "no_rows_written"
    assert any(r["reason"] == "indeterminate" for r in out["refused"])


def test_a_404_is_reported_separately_from_a_timeout(monkeypatch):
    session = _StubSession({"162276": [_Row(114420, "Fed chair", "open", "hockey")]})
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", ("162276",))

    out = _run(session, monkeypatch, {"162276": "404"}, apply=True)

    assert out["counts"]["not_at_venue"] == 1
    assert out["counts"]["indeterminate"] == 0
    assert session.updates == []


def test_an_id_that_names_no_row_is_reported_by_name(monkeypatch):
    """A stale bound must be loud, or a small `changed` reads as success."""
    session = _StubSession({})
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", ("162276",))

    out = _run(session, monkeypatch, {"162276": SUBJECT_FED_CHAIR})

    assert out["missing_ids"] == ["162276"]
    assert out["counts"]["events_examined"] == 0


# ---------------------------------------------------------------------------
# 5 — the write stays one column
# ---------------------------------------------------------------------------


def test_the_update_writes_only_llm_sport_category():
    """`category` is INSERT-time only in the poller's `update_set`.

    A rail that wrote it would be doing something the ingest path never does, on
    rows whose whole problem is that ingest cannot reach them.
    """
    updates = [s for s in _sql_statements() if s.strip().upper().startswith("UPDATE")]
    assert updates, "no UPDATE statement found — this scan would be vacuous"

    for sql in updates:
        set_clause = sql.upper().split("SET", 1)[1].split("WHERE", 1)[0]
        assigned = {
            part.split("=")[0].strip()
            for part in set_clause.split(",")
            if "=" in part
        }
        assert assigned == {"LLM_SPORT_CATEGORY"}, (
            f"the UPDATE assigns {sorted(assigned)}; this rail writes exactly "
            "llm_sport_category and nothing else."
        )


def test_the_update_never_touches_the_observation_clock():
    """🔴 CERT-2382's required repair, `4229-PRESERVE-THE-MARKETS-OBSERVATION-CLOCK`.

    The first SHA carried `updated_at = NOW()` in the UPDATE, out of habit. On
    this table `updated_at` is not bookkeeping — **the card renders it as its own
    relative date.** The Fed Chair card's before-LOOK reads `May 17` in the
    corner, which IS the 115-day staleness shown to a reader. Stamping NOW()
    would have left four-month-old prices unchanged while presenting them as
    observed just now: a TRUTH regression introduced by the TRUTH repair.

    Its own test rather than a clause of the one above, because the assertion
    above is about SCOPE (one column) and this is about a specific column being
    reader-visible. Merging them would let a future edit that re-adds the stamp
    fail with a message about scope, which is not what a reader needs to be told.
    """
    for sql in _sql_statements():
        assert "UPDATED_AT" not in sql.upper(), (
            "the repair writes `updated_at`. That column is rendered on the card "
            "as the market's own relative date, so stamping it would present "
            f"unchanged stale prices as fresh:\n{sql}"
        )


def test_the_restore_writes_only_llm_sport_category():
    """The undo is checked by RUNNING it, not by scanning its f-string pieces.

    `restore_sql` is assembled from an f-string, so its literals reach the AST
    as fragments — a scan over those reads a one-column UPDATE whether or not
    the function actually emits one. Generating the statement is the only way to
    see what it really says.
    """
    sql = rail.restore_sql([{"id": 1, "before": "hockey"}])
    set_clause = sql.upper().split("SET", 1)[1].split("WHERE", 1)[0]
    assigned = {p.split("=")[0].strip() for p in set_clause.split(",") if "=" in p}
    assert assigned == {"LLM_SPORT_CATEGORY"}, (
        f"the restore assigns {sorted(assigned)}; the undo must put back exactly "
        "the column the apply moved."
    )


def test_the_update_is_a_compare_and_set():
    """The predicate, not just the bound parameter.

    `test_an_apply_writes_the_planned_rows_and_compare_and_sets` asserts the
    `before` value is PASSED — which stays true if the WHERE clause that uses it
    is deleted. Only the statement text proves the guard is still applied, and
    without it a re-ingest that landed between the SELECT and the UPDATE is
    clobbered by a verdict computed before it.
    """
    updates = [s for s in _sql_statements() if s.strip().upper().startswith("UPDATE")]
    assert updates, "no UPDATE statement found — this scan would be vacuous"

    for sql in updates:
        where = sql.upper().split("WHERE", 1)[1]
        assert "LLM_SPORT_CATEGORY IS NOT DISTINCT FROM :BEFORE" in where, (
            f"the UPDATE is no longer a compare-and-set:\n{sql}"
        )


def test_the_rail_touches_no_settlement_or_price_field():
    """Why moving a RESOLVED row is safe: this column is a badge, never a result."""
    forbidden = (
        "is_winner",
        "settled_at",
        "resolution_date",
        "probability",
        "price",
        "status =",
    )
    for sql in [s for s in _literals() if "UPDATE" in s.upper()]:
        lowered = sql.lower()
        for token in forbidden:
            assert token not in lowered, (
                f"the UPDATE mentions {token!r}. 'Settled means settled' holds "
                "here only because this rail writes a taxonomy badge and nothing "
                "a reader would call a result."
            )


# ---------------------------------------------------------------------------
# 6 — D51
# ---------------------------------------------------------------------------


def test_the_restore_line_is_a_statement_not_a_dict_repr():
    """The Kalshi sibling shipped this bug once: a restore that cannot be pasted."""
    plan = [
        {"id": 114420, "before": "hockey"},
        {"id": 34676409, "before": "hockey"},
    ]
    sql = rail.restore_sql(plan)
    assert "{" not in sql and "}" not in sql, f"a dict leaked into the restore:\n{sql}"
    assert sql.count(";") == 1
    assert "SET llm_sport_category = 'hockey'" in sql
    assert "34676409" in sql and "114420" in sql


def test_the_restore_splits_by_distinct_before_value():
    plan = [
        {"id": 1, "before": "hockey"},
        {"id": 2, "before": "golf"},
    ]
    sql = rail.restore_sql(plan)
    assert sql.count(";") == 2, f"two before-values must give two statements:\n{sql}"
    assert "'hockey'" in sql and "'golf'" in sql


def test_a_null_before_restores_to_null_not_the_string():
    sql = rail.restore_sql([{"id": 1, "before": None}])
    assert "= NULL" in sql
    assert "'None'" not in sql


def test_an_empty_plan_produces_no_restore_statement():
    assert rail.restore_sql([]) == ""


# ---------------------------------------------------------------------------
# 7 — registered, and the header list did not drift
# ---------------------------------------------------------------------------


def test_the_repair_is_registered():
    from app.routes import admin_repairs

    assert admin_repairs._REPAIRS["polymarket-senate-category"] == (
        "app.tasks.repair_polymarket_senate_category",
        "repair",
    )


def test_the_dispatcher_header_names_the_repair():
    """The catalog comment has drifted behind the registry before; it says so itself."""
    from app.routes import admin_repairs

    assert "polymarket-senate-category" in (admin_repairs.__doc__ or ""), (
        "the repair is registered but absent from the module docstring's catalog"
    )


def test_the_rail_is_not_wired_to_a_beat():
    """ATTENDED ONLY — a terminating repair over six ids is not a standing job."""
    schedule = celery_app.conf.beat_schedule or {}
    for name, entry in schedule.items():
        assert "senate" not in str(entry.get("task", "")).lower(), (
            f"beat entry {name!r} runs the senate repair; it is attended only"
        )
