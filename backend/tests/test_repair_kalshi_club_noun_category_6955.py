"""#6955 Kalshi half — the club-noun rail, guarded without a database.

The Polymarket half of this issue is live. The Kalshi half exists for a
DIFFERENT reason, and every guard here is aimed at that difference:

1. 🔴 **The poller reaches these rows and declines to fix them, on purpose.**
   Kalshi's upsert is ``coalesce(nullif(existing,'other'), new)`` (#1888), so a
   real tag is never overwritten. The merged classifier fix therefore moves not
   one stored row, and no amount of polling will. ``test_the_kalshi_writer_
   still_refuses_to_overwrite_a_real_tag`` pins that premise against the
   poller's own source, so if #1888 is ever relaxed this rail's reason to exist
   re-opens loudly instead of being inherited.

2. **The rail must not become a second classifier.** Sharper here than on the
   sibling: the alternative to asking the venue is a ``name ILIKE '%hurricane%'``
   predicate, and the census found 287 genuinely-sport rows that predicate would
   sweep onto the weather shelf — Carolina Hurricanes, Seattle Kraken, a 24:1
   majority.

3. **The venue gate must DISCRIMINATE.** Subject and control fixtures are real
   Kalshi payloads captured 2026-09-18. The controls are the half that can fail:
   a fixture that misrepresented production would pass every ship assertion.

4. **The membership gate is id identity, and one subject has an EMPTY market
   list.** ``KXHURCTOTMAJ-26JUN30`` comes back from the venue with
   ``markets: []``. A gate that required the venue to name the row's ticker
   would refuse the very row it is meant to repair.

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

from app.tasks import repair_kalshi_club_noun_category as rail


# ---------------------------------------------------------------------------
# Real Kalshi payloads, captured 2026-09-18 from
# `/trade-api/v2/events/{ticker}?with_nested_markets=true` and
# `/trade-api/v2/series/{ticker}`, trimmed to the keys the gate reads.
# ---------------------------------------------------------------------------


def _event(ticker, category, series, title, market_tickers=()):
    return {
        "event": {
            "event_ticker": ticker,
            "category": category,
            "series_ticker": series,
            "title": title,
        },
        "markets": [{"ticker": t} for t in market_tickers],
    }


#: 8431183 — a card a reader meets searching "Atlantic hurricanes".
SUBJECT_ATLANTIC_TOTAL = _event(
    "KXHURCTOT-26DEC01",
    "Climate and Weather",
    "KXHURCTOT",
    "How many Atlantic hurricanes will there be in 2026?",
    [f"KXHURCTOT-26DEC01-T{n}" for n in range(4, 13)],
)

#: 25925286 — the Eastern Pacific family.
SUBJECT_EPAC_TOTAL = _event(
    "KXHURRICANE-26DEC01EPACTOT",
    "Climate and Weather",
    "KXHURRICANE",
    "How many Eastern Pacific hurricanes will there be this year?",
    [f"KXHURRICANE-26DEC01EPACTOT-T{n}" for n in range(1, 10)],
)

#: 25925285 — served as HOCKEY directly above two weather siblings of the same
#: series family on `q=named storms`, production 19:00Z.
SUBJECT_ATLANTIC_NAMES = _event(
    "KXHURRICANENAMES-26DEC01ATL",
    "Climate and Weather",
    "KXHURRICANENAMES",
    "What named storms will be hurricanes in the Atlantic this year?",
    [f"KXHURRICANENAMES-26DEC01ATL-{n}" for n in range(1, 22)],
)

#: 🔴 28147412 — RESOLVED, and the venue returns it with NO markets at all.
SUBJECT_RESOLVED_EMPTY_MARKETS = _event(
    "KXHURCTOTMAJ-26JUN30",
    "Climate and Weather",
    "KXHURCTOTMAJ",
    "How many major Atlantic hurricanes will there be this month?",
    [],
)

#: 🔴 CONTROL, and the most important one: a real NHL fixture whose title
#: contains the club noun. The ticker map classifies it at step 1 of the
#: cascade, above everything else — so this control fails loudly if the rail
#: ever starts reading the name.
CONTROL_CAROLINA_NHL_PROP = _event(
    "KXNHLPTS-26FEB26TBCAR",
    "Sports",
    "KXNHLPTS",
    "TB Lightning at CAR Hurricanes: Points",
    [],
)

CONTROL_CAROLINA_SERIES = _event(
    "KXNHLEAST-26",
    "Sports",
    "KXNHLEAST",
    "Series Winner: Montreal Canadiens vs Carolina Hurricanes",
    [],
)

#: 🔴 CONTROL that is IN the bound: the cascade reads the club noun at step 2,
#: above the venue's `Companies` at step 4, so the gate refuses it. Its presence
#: makes the dry run prove that refusal instead of this file asserting it.
CONTROL_KRAKEN_IN_BOUND = _event(
    "KXKRAKENBANKPUBLIC-27JAN01",
    "Companies",
    "KXKRAKENBANKPUBLIC",
    "Which bank will take Kraken public before 2027?",
    [f"KXKRAKENBANKPUBLIC-27JAN01-{n}" for n in range(1, 6)],
)

#: The venue's series replies, verbatim `tags` lists.
SERIES_TAGS = {
    "KXHURCTOT": {"tags": ["Hurricanes", "Natural disasters"]},
    "KXHURCTOTMAJ": {"tags": ["Hurricanes", "Natural disasters"]},
    "KXHURRICANE": {"tags": ["Hurricanes"]},
    "KXHURRICANENAMES": {"tags": ["Hurricanes"]},
    "KXKRAKENBANKPUBLIC": {"tags": ["IPOs", "Companies"]},
    "KXNHLPTS": {"tags": ["Hockey"]},
    "KXNHLEAST": {"tags": ["Hockey"]},
}

#: (payload, label, stored name, the answer the venue's own reply produces)
SUBJECTS = [
    (SUBJECT_ATLANTIC_TOTAL, "atlantic-total",
     "How many Atlantic hurricanes will there be in 2026?", "weather"),
    (SUBJECT_EPAC_TOTAL, "epac-total",
     "How many Eastern Pacific hurricanes will there be this year?", "weather"),
    (SUBJECT_ATLANTIC_NAMES, "atlantic-names",
     "What named storms will be hurricanes in the Atlantic this year?", "weather"),
    (SUBJECT_RESOLVED_EMPTY_MARKETS, "resolved-no-markets",
     "How many major Atlantic hurricanes will there be this month?", "weather"),
]

CONTROLS = [
    (CONTROL_CAROLINA_NHL_PROP, "carolina-nhl-prop",
     "TB Lightning at CAR Hurricanes: Points", "hockey"),
    (CONTROL_CAROLINA_SERIES, "carolina-series",
     "Series Winner: Montreal Canadiens vs Carolina Hurricanes", "hockey"),
    (CONTROL_KRAKEN_IN_BOUND, "kraken-in-bound",
     "Which bank will take Kraken public before 2027?", "hockey"),
]


def _cascade(payload, name):
    """The shipped cascade, fed exactly what the rail feeds it."""
    from app.tasks.kalshi import _categorize_kalshi_market

    event = payload["event"]
    series = SERIES_TAGS.get(event["series_ticker"])
    return _categorize_kalshi_market(
        name,
        event["category"],
        event["event_ticker"],
        rail.venue_series_tag(series),
    )


# ---------------------------------------------------------------------------
# 1 — the rail must not become a second classifier
# ---------------------------------------------------------------------------

_CATEGORY_TOKENS = {
    "hockey", "baseball", "basketball", "football", "soccer", "tennis", "golf",
    "mma", "boxing", "cricket", "rugby", "esports", "motorsports", "olympics",
    "darts", "chess", "cycling", "wrestling", "softball", "badminton",
    "aussierules", "sailing", "poker", "lacrosse",
    "weather", "crypto", "politics", "economics", "tech", "health",
    "geopolitics", "legal", "culture", "entertainment", "energy", "commodities",
}


def _executable_source(module) -> str:
    """The module's source with every docstring removed.

    Scoping matters: the rail's prose NAMES the columns it must not write, at
    length and on purpose, so a guard that greps raw source fires on its own
    explanation. The thing under test is what the module DOES.
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


def test_the_rail_carries_no_sport_rules_of_its_own():
    """No category literal anywhere in the executable source.

    ``"other"`` is the single allowed exception: the poller's own honest-empty
    sentinel, not a verdict this rail forms.
    """
    tree = ast.parse(_executable_source(rail))
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
    """A regex here would be a name rule — the thing the venue replaces, and the
    thing that would sweep 287 real hockey rows onto the weather shelf."""
    tree = ast.parse(inspect.getsource(rail))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "re" not in imported


def test_the_rail_actually_calls_the_shipped_cascade():
    """The guards above are satisfied by a rail that decides NOTHING, so assert
    the positive: the poller's own function is the thing consulted."""
    source = _executable_source(rail)
    assert "from app.tasks.kalshi import _categorize_kalshi_market" in source
    assert "_categorize_kalshi_market(" in source


def test_the_rail_does_not_reimplement_the_tag_translation():
    """`series_tag_to_category` stays in the poller. The rail may read `tags[0]`
    — a payload shape — but must never map a tag to a category itself."""
    source = _executable_source(rail)
    assert "series_tag_to_category" not in source


# ---------------------------------------------------------------------------
# 2 — the premise: why the poller is not the answer
# ---------------------------------------------------------------------------


def test_the_kalshi_writer_still_refuses_to_overwrite_a_real_tag():
    """🔴 THE WHOLE REASON THIS MODULE EXISTS, pinned against the poller.

    Unlike the Polymarket sibling — whose rows the poller never reaches — these
    rows are polled every two hours. The poller writes nothing because #1888's
    upsert only upgrades ``other``. If that ever changes, this rail becomes
    unnecessary and should be deleted rather than left running; this test is
    where that news arrives.
    """
    kalshi_py = Path(inspect.getfile(rail)).resolve().parent / "kalshi.py"
    assert kalshi_py.is_file(), f"premise unreadable: {kalshi_py} is missing"
    source = kalshi_py.read_text()
    guarded = re.search(
        r"update_set\[.llm_sport_category.\]\s*=\s*func\.coalesce\(\s*"
        r"func\.nullif\(",
        source,
    )
    assert guarded, (
        "app/tasks/kalshi.py no longer writes llm_sport_category through "
        "coalesce(nullif(existing,'other'), new). If the poller now overwrites "
        "a real tag, the merged classifier fix repairs these rows by itself and "
        "this attended rail should be RETIRED — re-read #6955 before deleting "
        "this test."
    )


# ---------------------------------------------------------------------------
# 3 — the venue gate must discriminate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,label,name,expected", SUBJECTS, ids=[s[1] for s in SUBJECTS]
)
def test_the_shipped_cascade_moves_the_subjects_off_the_sport_shelf(
    payload, label, name, expected
):
    assert _cascade(payload, name) == expected


@pytest.mark.parametrize(
    "payload,label,name,expected", CONTROLS, ids=[c[1] for c in CONTROLS]
)
def test_the_shipped_cascade_leaves_the_controls_where_they_are(
    payload, label, name, expected
):
    """Two of these are real NHL fixtures whose titles say "Hurricanes"; the
    third is the bound member the gate is expected to refuse."""
    assert _cascade(payload, name) == expected


def test_the_subject_and_control_titles_both_contain_the_club_noun():
    """The controls are only controls if they are genuinely confusable.

    A control that shares nothing with the subject proves nothing — it would
    pass against a rail that keyed on the word "hurricane" itself.
    """
    subjects = " ".join(s[2] for s in SUBJECTS).lower()
    controls = " ".join(c[2] for c in CONTROLS).lower()
    assert "hurricane" in subjects
    assert "hurricane" in controls


def test_the_venue_series_tag_is_the_poller_s_first_tag():
    """`tags[0]`, the same one line as `_resolve_series_tag_result`. The rail
    must hand the cascade the argument the poller hands it, or the gate is
    testing a different function than the one that runs."""
    assert rail.venue_series_tag({"tags": ["Hurricanes", "Natural disasters"]}) == "Hurricanes"
    assert rail.venue_series_tag({"tags": ["IPOs", "Companies"]}) == "IPOs"


def test_the_venue_series_tag_survives_an_absent_or_junk_tag_list():
    for payload in (None, {}, {"tags": None}, {"tags": []}, {"tags": "Hockey"}):
        assert rail.venue_series_tag(payload) is None


def test_venue_market_tickers_reads_ids_not_names():
    got = rail.venue_market_tickers(SUBJECT_ATLANTIC_TOTAL)
    assert "KXHURCTOT-26DEC01-T4" in got
    assert len(got) == 9


def test_venue_market_tickers_survives_a_junk_market_list():
    assert rail.venue_market_tickers({}) == set()
    assert rail.venue_market_tickers({"markets": None}) == set()
    assert rail.venue_market_tickers({"markets": ["nope", 7, {}, {"ticker": None}]}) == set()


def test_the_resolved_subject_really_has_no_markets_at_the_venue():
    """The case the membership gate's clause 1 exists for."""
    assert rail.venue_market_tickers(SUBJECT_RESOLVED_EMPTY_MARKETS) == set()


# ---------------------------------------------------------------------------
# 4 — the bound
# ---------------------------------------------------------------------------


def test_the_bound_is_enumerated_and_unique():
    assert 1 <= len(rail.CLUB_NOUN_EVENT_TICKERS) <= 20, (
        "this is an ATTENDED, terminating repair over an enumerated bound, not "
        "a population — if the class is really this big it needs a censused "
        "drain with a cursor, like the `kalshi-series-tag-category` sibling"
    )
    assert len(set(rail.CLUB_NOUN_EVENT_TICKERS)) == len(rail.CLUB_NOUN_EVENT_TICKERS)


def test_every_bound_entry_is_a_kalshi_event_ticker():
    """Our `external_id` IS the venue's event ticker; that identity is the
    membership gate, so a malformed entry here would silently match nothing."""
    for ticker in rail.CLUB_NOUN_EVENT_TICKERS:
        assert ticker == ticker.strip()
        assert ticker.startswith("KX")
        assert "-" in ticker
        assert ticker.upper() == ticker


def test_the_three_rows_a_reader_meets_on_search_are_in_the_bound():
    """🔴 The ship, as a bound assertion.

    Production 19:00Z, `/api/events/search?q=Atlantic hurricanes` served
    8431182, 8431183 and 25925285 badged `hockey`. These are their tickers.
    """
    for ticker in (
        "KXHURCTOTMAJ-26DEC01",
        "KXHURCTOT-26DEC01",
        "KXHURRICANENAMES-26DEC01ATL",
    ):
        assert ticker in rail.CLUB_NOUN_EVENT_TICKERS


def test_the_refused_control_is_in_the_bound_on_purpose():
    """So the dry run PROVES the refusal instead of the docstring claiming it."""
    assert "KXKRAKENBANKPUBLIC-27JAN01" in rail.CLUB_NOUN_EVENT_TICKERS


# ---------------------------------------------------------------------------
# 5 — the plan, driven end to end against a stub session
# ---------------------------------------------------------------------------


class _Row:
    def __init__(self, id, name, status, external_id, llm_sport_category):
        self.id = id
        self.name = name
        self.status = status
        self.external_id = external_id
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

    def __init__(self, rows_by_ticker, moves=None, fail_update=False):
        self.rows_by_ticker = rows_by_ticker
        self.moves = moves
        self.fail_update = fail_update
        self.updates: list[dict] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "SET LOCAL" in sql:
            return _Result()
        if "UPDATE" in sql.upper():
            if self.fail_update:
                raise RuntimeError("canceling statement due to statement timeout")
            self.updates.append(dict(params))
            ids = (
                params["ids"]
                if self.moves is None
                else [i for i in params["ids"] if i in self.moves]
            )
            return _Result([(i,) for i in ids], rowcount=len(ids))
        if "SELECT" in sql.upper():
            return _Result(self.rows_by_ticker.get(params["ticker"], []))
        raise AssertionError(f"unexpected statement:\n{sql}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


#: The venue replies keyed as the rail asks for them.
_EVENTS = {
    p["event"]["event_ticker"]: p
    for p in (
        SUBJECT_ATLANTIC_TOTAL,
        SUBJECT_EPAC_TOTAL,
        SUBJECT_ATLANTIC_NAMES,
        SUBJECT_RESOLVED_EMPTY_MARKETS,
        CONTROL_KRAKEN_IN_BOUND,
        CONTROL_CAROLINA_NHL_PROP,
    )
}


def _run(session, monkeypatch, events=None, series=None, apply=False, bound=None):
    """Drive `repair()` with both venue doors stubbed."""
    events = _EVENTS if events is None else events
    series = SERIES_TAGS if series is None else series

    async def fake_event(_client, ticker):
        entry = events.get(ticker)
        if entry is None:
            return "indeterminate", None
        if entry == "404":
            return "not_found", None
        return "ok", entry

    async def fake_series(_client, ticker):
        entry = series.get(ticker)
        if entry is None:
            return "indeterminate", None
        if entry == "404":
            return "not_found", None
        return "ok", {"series": entry}

    monkeypatch.setattr(rail, "_fetch_event", fake_event)
    monkeypatch.setattr(rail, "_fetch_series", fake_series)
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)
    if bound is not None:
        monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_TICKERS", tuple(bound))
    return asyncio.run(rail.repair(session, apply=apply))


#: The real production rows, 2026-09-18 19:05Z. One row per event.
_PROD_ROWS = {
    "KXHURCTOT-26DEC01": _Row(
        8431183, "How many Atlantic hurricanes will there be in 2026?",
        "open", "KXHURCTOT-26DEC01", "hockey"),
    "KXHURRICANE-26DEC01EPACTOT": _Row(
        25925286, "How many Eastern Pacific hurricanes will there be this year?",
        "open", "KXHURRICANE-26DEC01EPACTOT", "hockey"),
    "KXHURRICANENAMES-26DEC01ATL": _Row(
        25925285, "What named storms will be hurricanes in the Atlantic this year?",
        "open", "KXHURRICANENAMES-26DEC01ATL", "hockey"),
    "KXHURCTOTMAJ-26JUN30": _Row(
        28147412, "How many major Atlantic hurricanes will there be this month?",
        "resolved", "KXHURCTOTMAJ-26JUN30", "hockey"),
    "KXKRAKENBANKPUBLIC-27JAN01": _Row(
        109341, "Which bank will take Kraken public before 2027?",
        "open", "KXKRAKENBANKPUBLIC-27JAN01", "hockey"),
}


def _rows(*tickers):
    return {t: [_PROD_ROWS[t]] for t in tickers}


def test_the_storm_rows_are_planned_and_the_kraken_row_is_refused(monkeypatch):
    """🔴 The ship and its disclosed refusal, in one run."""
    bound = list(_PROD_ROWS)
    session = _StubSession(_rows(*bound))
    out = _run(session, monkeypatch, bound=bound)

    moved = {p["id"]: p["after"] for p in out["planned"]}
    assert moved == {
        8431183: "weather",
        25925286: "weather",
        25925285: "weather",
        28147412: "weather",
    }
    assert 109341 not in moved
    assert out["counts"]["changed"] == 4
    assert out["counts"]["unchanged"] == 1
    reasons = {r["event_ticker"]: r["reason"] for r in out["refused"]}
    assert reasons["KXKRAKENBANKPUBLIC-27JAN01"] == "venue_agrees"


def test_the_resolved_row_with_no_venue_markets_is_still_repaired(monkeypatch):
    """🔴 Membership clause 1. A gate that required the venue's `markets[]` to
    name the row would refuse the only row this event has."""
    session = _StubSession(_rows("KXHURCTOTMAJ-26JUN30"))
    out = _run(session, monkeypatch, bound=["KXHURCTOTMAJ-26JUN30"])
    assert [p["id"] for p in out["planned"]] == [28147412]
    assert out["counts"]["rows_not_named_by_venue"] == 0


def test_a_stranger_sharing_the_group_is_refused_by_id(monkeypatch):
    """The Polymarket sibling's Kraken container collected a Gaza ceasefire
    market. Kalshi's correspondence is id identity, so prove it refuses."""
    stranger = _Row(
        999999, "Israel x Hamas Ceasefire Phase II by February 28?",
        "resolved", "KXSOMETHINGELSE-26", "tech",
    )
    session = _StubSession(
        {"KXHURCTOT-26DEC01": [_PROD_ROWS["KXHURCTOT-26DEC01"], stranger]}
    )
    out = _run(session, monkeypatch, bound=["KXHURCTOT-26DEC01"])
    assert [p["id"] for p in out["planned"]] == [8431183]
    assert out["counts"]["rows_not_named_by_venue"] == 1
    assert [r["id"] for r in out["not_named_by_venue"]] == [999999]


def test_a_real_carolina_fixture_is_refused_by_the_venue(monkeypatch):
    """Put a genuine NHL event in the bound by mistake and the gate declines it
    — the bound is a bound, not a claim."""
    nhl = _Row(1633610, "TB Lightning at CAR Hurricanes: Points",
               "resolved", "KXNHLPTS-26FEB26TBCAR", "hockey")
    session = _StubSession({"KXNHLPTS-26FEB26TBCAR": [nhl]})
    out = _run(session, monkeypatch, bound=["KXNHLPTS-26FEB26TBCAR"])
    assert out["planned"] == []
    assert out["counts"]["unchanged"] == 1


def test_a_dry_run_never_writes(monkeypatch):
    bound = list(_PROD_ROWS)
    session = _StubSession(_rows(*bound))
    out = _run(session, monkeypatch, bound=bound)
    assert session.updates == []
    assert session.commits == 0
    assert out["applied"] == []
    assert out["terminal"] == "dry_run"
    assert out["counts"]["rows_written"] == 0
    # The undo travels with the dry run, built from the plan.
    assert "UPDATE futures_markets SET llm_sport_category = 'hockey'" in out["restore_sql"]


def test_an_apply_writes_the_planned_rows_and_compare_and_sets(monkeypatch):
    bound = list(_PROD_ROWS)
    session = _StubSession(_rows(*bound))
    out = _run(session, monkeypatch, bound=bound, apply=True)
    assert out["counts"]["rows_written"] == 4
    assert out["terminal"] == "changed"
    assert {p["id"] for p in out["applied"]} == {8431183, 25925286, 25925285, 28147412}
    for params in session.updates:
        assert params["before"] == "hockey"
        assert params["llm"] == "weather"
    assert 109341 not in {i for p in session.updates for i in p["ids"]}


def test_a_partial_compare_and_set_restores_only_the_rows_that_moved(monkeypatch):
    """🔴 RETURNING, not rowcount. A restore built from the PLAN would write a
    stale `before` over a value a concurrent poll had just corrected."""
    bound = list(_PROD_ROWS)
    session = _StubSession(_rows(*bound), moves={8431183})
    out = _run(session, monkeypatch, bound=bound, apply=True)
    assert out["counts"]["rows_written"] == 1
    assert [p["id"] for p in out["applied"]] == [8431183]
    assert out["restore_sql"] == (
        "UPDATE futures_markets SET llm_sport_category = 'hockey' "
        "WHERE id IN (8431183);"
    )


def test_two_rows_sharing_a_before_but_earning_different_answers_do_not_collide(
    monkeypatch,
):
    """🔴 The UPDATE groups by the (before, after) PAIR.

    The cascade is asked per ROW, so one event can legitimately return two
    answers for two rows that store the same value. Grouping on `before` alone
    would write one answer over both.
    """
    # A member row of the same event, storing the same value as the container.
    # The point is not that its answer is good, it is that it DIFFERS, and the
    # write must carry each row's own verdict rather than the group's first.
    #
    # Note which ticker the cascade is handed: the EVENT's, for every row under
    # it, because that is what the poller hands it. A member row is not
    # classified on its own leg ticker.
    #
    # ⭐ THIS FIXTURE WAS "…: Points" UNTIL #7012, and the swap is worth the two
    # lines. That name read as basketball through `_STAT_TO_SPORT` (#4365) — a
    # name-rule sport guess with no venue signal behind it, which is precisely
    # the shape #7012 now demotes to the venue's topic. So the cascade started
    # answering `weather` for it, the same as the container, and this test began
    # failing for the best possible reason: the old specimen stopped being a
    # disagreement because the classifier got it right. The property under test
    # is the UPDATE's grouping, not that specimen, so it needs a row that still
    # earns a different answer — and step 0's `\bIPO\b` rule is the sturdiest
    # one available, sitting ABOVE the ticker and the venue alike.
    member = _Row(
        555001, "CAR Hurricanes arena operator IPO before 2027",
        "open", "KXHURCTOT-26DEC01-T4", "hockey",
    )
    session = _StubSession(
        {"KXHURCTOT-26DEC01": [_PROD_ROWS["KXHURCTOT-26DEC01"], member]}
    )
    out = _run(session, monkeypatch, bound=["KXHURCTOT-26DEC01"], apply=True)
    written = {tuple(p["ids"]): p["llm"] for p in session.updates}
    assert written == {(8431183,): "weather", (555001,): "economics"}, (
        "both rows stored `hockey`; grouping the UPDATE on `before` alone would "
        "have written one verdict over both"
    )
    # And the D51 undo names each row's own prior value, not the group's.
    assert out["restore_sql"] == (
        "UPDATE futures_markets SET llm_sport_category = 'hockey' "
        "WHERE id IN (555001, 8431183);"
    )


def test_a_transient_venue_failure_on_the_event_door_is_never_a_verdict(monkeypatch):
    session = _StubSession(_rows("KXHURCTOT-26DEC01"))
    out = _run(session, monkeypatch, events={}, bound=["KXHURCTOT-26DEC01"], apply=True)
    assert out["planned"] == []
    assert out["counts"]["indeterminate"] == 1
    assert out["counts"]["not_at_venue"] == 0
    assert session.updates == []


def test_a_transient_venue_failure_on_the_series_door_is_never_a_verdict(monkeypatch):
    """🔴 The tag is consulted ABOVE the name rules, so classifying without it
    is classifying on a rate limit."""
    session = _StubSession(_rows("KXHURCTOT-26DEC01"))
    out = _run(
        session, monkeypatch, series={}, bound=["KXHURCTOT-26DEC01"], apply=True
    )
    assert out["planned"] == []
    assert out["counts"]["indeterminate"] == 1
    assert session.updates == []


def test_the_honest_empty_default_never_overwrites_a_real_tag(monkeypatch):
    """The poller's own guard, inherited. If the cascade can say nothing useful
    about a row, `other` is not a verdict to write over a stored value."""
    blank = _event("KXZZZQQQ-26", None, "KXZZZQQQ", "Zzzqqq wibble?")
    row = _Row(777001, "Zzzqqq wibble?", "open", "KXZZZQQQ-26", "hockey")
    session = _StubSession({"KXZZZQQQ-26": [row]})
    out = _run(
        session, monkeypatch,
        events={"KXZZZQQQ-26": blank},
        series={"KXZZZQQQ": {"tags": []}},
        bound=["KXZZZQQQ-26"],
        apply=True,
    )
    assert _cascade(blank, "Zzzqqq wibble?") == "other", (
        "fixture no longer reaches the honest-empty default — this guard would "
        "pass vacuously"
    )
    assert out["planned"] == []
    assert out["counts"]["refused_other"] == 1
    assert session.updates == []


def test_a_404_on_the_event_is_reported_separately_from_a_timeout(monkeypatch):
    session = _StubSession(_rows("KXHURCTOT-26DEC01"))
    out = _run(
        session, monkeypatch,
        events={"KXHURCTOT-26DEC01": "404"},
        bound=["KXHURCTOT-26DEC01"],
    )
    assert out["counts"]["not_at_venue"] == 1
    assert out["counts"]["indeterminate"] == 0


def test_a_404_on_the_series_is_not_indeterminate(monkeypatch):
    """The poller's `get_series_metadata` returns None for a 404 and the cascade
    proceeds tagless. This rail does the same rather than stalling."""
    session = _StubSession(_rows("KXHURCTOT-26DEC01"))
    out = _run(
        session, monkeypatch,
        series={"KXHURCTOT": "404"},
        bound=["KXHURCTOT-26DEC01"],
    )
    assert out["counts"]["indeterminate"] == 0
    assert [p["id"] for p in out["planned"]] == [8431183]


def test_a_ticker_that_names_no_row_is_reported_by_name(monkeypatch):
    """A small `changed` must not read as success when the census went stale."""
    session = _StubSession({})
    out = _run(session, monkeypatch, bound=["KXHURCTOT-26DEC01"])
    assert out["missing_tickers"] == ["KXHURCTOT-26DEC01"]
    assert out["counts"]["events_examined"] == 0


def test_a_blocked_write_rolls_back_and_is_counted_not_swallowed(monkeypatch):
    session = _StubSession(_rows("KXHURCTOT-26DEC01"), fail_update=True)
    out = _run(session, monkeypatch, bound=["KXHURCTOT-26DEC01"], apply=True)
    assert out["counts"]["write_failed"] == 1
    assert out["counts"]["rows_written"] == 0
    assert session.rollbacks == 1
    assert out["terminal"] == "no_rows_written"


def test_the_series_door_is_asked_once_per_series_not_once_per_event(monkeypatch):
    """Four series carry twelve events; a per-event fetch is four times the
    venue traffic for the same answer."""
    calls: list[str] = []

    async def counting_series(_client, ticker):
        calls.append(ticker)
        return "ok", {"series": SERIES_TAGS[ticker]}

    async def fake_event(_client, ticker):
        return "ok", _EVENTS[ticker]

    bound = ["KXHURRICANE-26DEC01EPACTOT", "KXHURCTOT-26DEC01"]
    session = _StubSession(_rows(*bound))
    monkeypatch.setattr(rail, "_fetch_event", fake_event)
    monkeypatch.setattr(rail, "_fetch_series", counting_series)
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)
    monkeypatch.setattr(rail, "CLUB_NOUN_EVENT_TICKERS", tuple(bound))
    asyncio.run(rail.repair(session, apply=False))
    assert sorted(calls) == ["KXHURCTOT", "KXHURRICANE"]


# ---------------------------------------------------------------------------
# 6 — what is never written
# ---------------------------------------------------------------------------


def _assigned_columns(update_sql: str) -> set[str]:
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
    """On this rail the CAS is not theoretical: the Kalshi poller runs every two
    hours and DOES touch these rows."""
    statements = _update_statements()
    assert statements, "no UPDATE found — this guard would pass vacuously"
    for stmt in statements:
        where = stmt.split("WHERE", 1)[1]
        assert "llm_sport_category IS NOT DISTINCT FROM :before" in where


def test_the_update_never_touches_the_observation_clock():
    """CERT-2382: the card renders `updated_at` as its own relative date."""
    assert "updated_at" not in _executable_source(rail)


def test_the_rail_never_writes_status_because_that_is_a_calibration_write():
    """`resolved` is the calibration population's own gate, so writing it from a
    taxonomy rail is a write to the accuracy curve. Two rows in this bound are
    already resolved and are repaired anyway: a taxonomy badge is never a result.

    This pins BOTH halves — the refusal and the premise it rests on.
    """
    statements = _update_statements()
    assert statements, "no UPDATE found — this guard would pass vacuously"
    for stmt in statements:
        assert "status" not in _assigned_columns(stmt)

    calibration = (
        Path(inspect.getfile(rail)).resolve().parents[1] / "routes" / "calibration.py"
    )
    assert calibration.is_file(), f"premise unreadable: {calibration} is missing"
    hits = len(re.findall(r"status\s*=\s*'resolved'", calibration.read_text()))
    assert hits > 0, (
        "calibration no longer gates its population on `status = 'resolved'`. "
        "The refusal above was priced on that coupling — re-read the rail's "
        "docstring and #6986 and decide again; do not simply delete this test."
    )


def test_the_rail_never_writes_the_topic_column_it_measured_against():
    """`category` already reads `weather` on all eleven rows — it is the second
    instrument in the census. The poller writes it on INSERT and never again."""
    statements = _update_statements()
    for stmt in statements:
        assert "category" not in (_assigned_columns(stmt) - {"llm_sport_category"})


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


def test_the_select_never_trusts_the_group_to_admit_a_row():
    """`group_id` finds candidates; only `external_id` identity admits one."""
    source = inspect.getsource(rail.repair)
    assert "fm.group_id = :gid" in source, "the SELECT must still SURFACE group rows"
    gate = source.split("THE MEMBERSHIP GATE", 1)[1]
    assert "ext == venue_ticker" in gate
    assert "ext in named" in gate


# ---------------------------------------------------------------------------
# 7 — D51
# ---------------------------------------------------------------------------


def test_the_restore_writes_only_llm_sport_category():
    sql = rail.restore_sql(
        [{"id": 8431183, "before": "hockey"}, {"id": 109341, "before": "tech"}]
    )
    for line in sql.splitlines():
        assert line.startswith("UPDATE futures_markets SET llm_sport_category = ")
        assert line.count("SET") == 1


def test_the_restore_splits_by_distinct_before_value():
    sql = rail.restore_sql(
        [
            {"id": 1, "before": "hockey"},
            {"id": 2, "before": "hockey"},
            {"id": 3, "before": "baseball"},
        ]
    )
    lines = sql.splitlines()
    assert len(lines) == 2
    assert "WHERE id IN (1, 2);" in sql
    assert "WHERE id IN (3);" in sql


def test_the_restore_line_is_a_statement_not_a_dict_repr():
    """A sibling shipped a version that interpolated the before-value MAP where
    the value belongs. D51 is granted on the restore being runnable."""
    sql = rail.restore_sql([{"id": 1, "before": "hockey"}])
    assert "{" not in sql and "}" not in sql


def test_a_null_before_restores_to_null_not_the_string():
    sql = rail.restore_sql([{"id": 1, "before": None}])
    assert "= NULL WHERE" in sql
    assert "'None'" not in sql


def test_an_empty_plan_produces_no_restore_statement():
    assert rail.restore_sql([]) == ""


# ---------------------------------------------------------------------------
# 8 — wiring
# ---------------------------------------------------------------------------


def test_the_repair_is_registered():
    from app.routes.admin_repairs import _REPAIRS

    assert _REPAIRS["kalshi-club-noun-category"] == (
        "app.tasks.repair_kalshi_club_noun_category",
        "repair",
    )


def test_the_dispatcher_header_names_the_repair():
    """The header list has drifted behind the registry twice before."""
    # `from app.routes import …` rather than `import app.routes.admin_repairs`:
    # the test above imports a NAME from the same module, and mixing the two
    # import forms is a CodeQL note (py/import-and-import-from). No severity,
    # but a new alert on master for nothing.
    from app.routes import admin_repairs as mod

    assert "kalshi-club-noun-category" in (mod.__doc__ or "")


def test_the_rail_is_not_wired_to_a_beat():
    """ATTENDED ONLY. A terminating repair on a schedule is a standing job that
    re-asks the venue forever for rows it already fixed."""
    from app.tasks import celery_app

    schedule = celery_app.conf.beat_schedule or {}
    for name, entry in schedule.items():
        assert "kalshi_club_noun" not in str(entry.get("task", "")), (
            f"beat entry {name} schedules the attended club-noun repair"
        )


# ---------------------------------------------------------------------------
# 9 — the served payload carries the repair
# ---------------------------------------------------------------------------


def _search_row(llm_sport_category: str):
    """The real 8431183 row, production 2026-09-18, shaped as
    `_format_futures_for_search` reads it."""
    return SimpleNamespace(
        id=8431183,
        name="How many Atlantic hurricanes will there be in 2026?",
        sport=None,
        category="weather",
        llm_sport_category=llm_sport_category,
        market_tier=4,
        market_type="quantity",
        status="open",
        source="kalshi",
        resolution_date=None,
        updated_at=None,
        outcomes=[],
    )


def test_the_search_payload_serves_the_repaired_category():
    """🔴 Reach. A column nothing renders is an inert fix.

    `_format_futures_for_search` produced the payload read off production
    19:00Z, where 8431182/8431183/25925285 came back `llm_sport_category:
    "hockey"` beside Kalshi siblings serving `"weather"`.
    """
    from app.routes.events import _format_futures_for_search

    before = _format_futures_for_search(_search_row("hockey"))
    after = _format_futures_for_search(_search_row("weather"))

    assert before["llm_sport_category"] == "hockey"
    assert after["llm_sport_category"] == "weather"


def test_no_search_result_for_a_repaired_row_says_hockey():
    from app.routes.events import _format_futures_for_search

    served = _format_futures_for_search(_search_row("weather"))
    assert served["llm_sport_category"] != "hockey"
    assert "hockey" not in str(served.get("sport") or "").lower()
