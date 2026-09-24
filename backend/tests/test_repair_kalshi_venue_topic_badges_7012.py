"""#7012 repair half — the venue-topic badge rail, guarded without a database.

Every fixture below is a REAL Kalshi payload, read from the venue 2026-09-18
(notice 26: measure the venue, not our mirror), and every expected verdict was
MEASURED by running the shipped cascade over it before it was written down
here. That ordering matters: a fixture invented to match an expectation passes
every assertion and proves nothing.

WHAT THESE GUARDS ARE AIMED AT
==============================

1. 🔴 **The rail must ask the SHIPPED cascade the SHIPPED arguments.** #7012
   changed two of them — ``_pick_series_tag`` replaced ``tags[0]``, and
   ``series_category`` is new. A rail that re-spelled either would ask a weaker
   question than the poller asks. ``KXPERFORMSUPERBOWL`` proves it: tagged
   ``['Live Music', 'Football']``, it is protected at step 1b ONLY because
   ``_pick_series_tag`` reads past the first tag. Re-spell it as ``tags[0]``
   and the rail demotes the very row the rule exists to protect.

2. **The rail must not become a second classifier.** It carries no sport
   literal, no regex over a name, no category word of its own.

3. **The gate must DISCRIMINATE.** Six subjects move; four controls do not, and
   each control is refused for a DIFFERENT reason. The controls are the half
   that can fail.

4. 🔴 **The rows this ship does NOT fix are pinned, not smoothed.** Three live
   rows sit in the population and stay as they are:

     * ``110748`` and its six ``KXPGAAWARDS`` siblings — the ticker map held a
       bare ``kxpga`` prefix, so ``startswith`` answered **golf** at step 1,
       above everything this rule touches. That was **#7042**, not this ship;
       since #7042 carved the series out of the ticker map the cascade answers
       ``entertainment`` and the row is a SUBJECT (a seventh), pinned below.
     * ``109401`` (MrBeast) — the cascade answers **football**, another SPORT.
       Moving a row between two sports has not been measured, so the rail counts
       it and declines.
     * ``52755584`` (Ford) — both venue categories say ``Companies``, which
       neither mapper models, so no topic is implied and the name guess stands.

   Each has a test asserting it does NOT move, so the ship line cannot quietly
   grow to cover them.

🔴 A NOTE ON HOW THESE FIXTURES WERE BUILT, because it nearly went wrong. An
earlier draft INFERRED two event categories as ``Entertainment``; the venue
actually says ``Social`` for both, and one of those rows does not move at all
(no name rule fires, so the cascade returns the honest-empty ``other``). The
suite was green on a verdict production does not produce. Every value in
``EVENTS``/``SERIES``/``PROD_ROWS`` below is now a READ, cross-checked against a
live replay over the whole open population.

NOT tested here: the write against real Postgres. That is the D51 dry run on
production, which returns the whole plan before anything is applied.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path

import pytest

from app.tasks import repair_kalshi_venue_topic_badges as rail
from app.tasks.kalshi import (
    _categorize_kalshi_market,
    _pick_series_tag,
    _VENUE_TOPIC_DEMOTION_TARGETS,
)
from app.utils.sport_keys import NON_SPORT_LLM_CATEGORIES

_SOURCE = Path(rail.__file__).read_text()


# ---------------------------------------------------------------------------
# 1 — the rail carries no rules of its own
# ---------------------------------------------------------------------------

#: Every sport this codebase currently stores on a Kalshi row, plus the topic
#: words a classifier would reach for. If any appears as a STRING LITERAL in the
#: rail's executable body, the rail has started deciding sports itself.
_FORBIDDEN_LITERALS = {
    "baseball", "tennis", "soccer", "esports", "basketball", "football",
    "hockey", "mma", "golf", "cricket", "boxing", "motorsports", "lacrosse",
    "rugby", "darts", "chess", "olympics", "cycling", "wrestling", "handball",
    "politics", "economics", "entertainment", "weather", "geopolitics",
    "culture", "health", "legal", "tech",
}


def _string_literals(source: str) -> set[str]:
    """Every string constant in the module's EXECUTABLE body.

    Docstrings are excluded deliberately — this module's docstrings name the
    sports in their evidence, which is the opposite of a defect. A literal that
    a docstring contains cannot classify anything.
    """
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                out.add(node.value.lower())
    return out


def _sql_literals(fn) -> list[str]:
    """Every SQL string the function hands to `text()`.

    The unit these guards judge. A scan over raw source would also read this
    module's comments and docstrings, which discuss the very constructs the
    guards forbid — the classic substring trap that makes a guard fire on its
    own explanation.
    """
    tree = ast.parse(inspect.getsource(fn).lstrip())
    out = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "text"
            and node.args
        ):
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.append(arg.value)
            elif isinstance(arg, ast.JoinedStr):  # f-string
                out.append(
                    "".join(
                        v.value
                        for v in arg.values
                        if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    )
                )
    return out


def _set_clause(stmt: str) -> str:
    """The columns an UPDATE assigns — the SET clause, not the whole statement.

    `'category ='` appears inside `llm_sport_category = :llm`, and a WHERE
    clause legitimately compares the column it is not allowed to WRITE. Only
    the SET clause answers "what does this change".
    """
    upper = stmt.upper()
    start = upper.index(" SET ") + len(" SET ")
    end = upper.index(" WHERE ", start)
    return stmt[start:end].strip()


def test_the_rail_carries_no_sport_rules_of_its_own():
    """🔴 The whole warrant. The VENUE decides; this module only asks."""
    found = _string_literals(_SOURCE) & _FORBIDDEN_LITERALS
    assert not found, (
        f"the rail names sports/topics in its executable body: {sorted(found)}. "
        "Its verdict must come from the shipped cascade over the venue's reply, "
        "never from a literal here."
    )


def test_the_rail_does_not_reimplement_the_tag_or_topic_translation():
    """No local copy of the two mappings the poller owns."""
    for banned in (
        "series_tag_to_category",
        "_kalshi_category_to_llm_category",
        "kalshi_to_sport",
    ):
        assert f"def {banned}" not in _SOURCE, (
            f"{banned} is the poller's; a second spelling here drifts silently"
        )


def test_the_rail_does_not_import_re():
    """A regex in a repair rail is a name rule wearing a different hat."""
    assert "import re" not in _SOURCE


def test_the_candidate_categories_are_derived_from_the_house_set():
    """Not typed out — derived, so it cannot drift from `sport_keys`."""
    assert set(rail.CANDIDATE_STORED_CATEGORIES) == set(NON_SPORT_LLM_CATEGORIES)


# ---------------------------------------------------------------------------
# 2 — the rail asks the SHIPPED cascade, with the SHIPPED arguments
# ---------------------------------------------------------------------------


def test_the_rail_asks_the_shipped_cascade_and_the_shipped_tag_chooser():
    """Imported from the poller, not redefined — and actually CALLED.

    🔴 An import-only check is not enough, and this suite proved it: a mutant
    that replaced the `_pick_series_tag(...)` CALL with `tags[0]` left the
    import line untouched and survived a substring assertion. The import says
    what is available; only a Call node says what is used.
    """
    src = inspect.getsource(rail.repair)
    assert "from app.tasks.kalshi import" in src

    tree = ast.parse(src.lstrip())
    called = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    for shipped in ("_categorize_kalshi_market", "_pick_series_tag"):
        assert shipped in called, (
            f"{shipped} is imported but never called — the rail is asking a "
            "different question than the poller asks"
        )
    assert "_VENUE_TOPIC_DEMOTION_TARGETS" in src


def test_the_rail_chooses_the_series_tag_the_way_the_poller_does(monkeypatch):
    """🔴 The same protection as the cascade test, asserted ON THE RAIL.

    The row is SYNTHETIC — `KXPERFORMSUPERBOWL-26` has no row in the candidate
    population — but the venue payload is real, and what is under test is the
    rail's plumbing, not the venue. A rail reading `tags[0]` would see
    'Live Music', miss the venue's own `Football`, and DEMOTE a row the whole
    rule exists to protect. Nothing else in this file can catch that.
    """
    row = _Row(
        99_000_001, "Who will headline the Super Bowl LX halftime show?",
        "open", "KXPERFORMSUPERBOWL-26", "entertainment", "football",
    )
    session = _StubSession([row])
    out = _run(
        session,
        monkeypatch,
        events={"KXPERFORMSUPERBOWL-26": _event(
            "KXPERFORMSUPERBOWL-26", "KXPERFORMSUPERBOWL", "Entertainment")},
        series={"KXPERFORMSUPERBOWL": {
            "category": "Entertainment", "tags": SUPERBOWL_SERIES_TAGS}},
        apply=True,
    )
    assert out["counts"]["venue_agrees"] == 1, (
        "the venue's own Football tag protects this row at step 1b"
    )
    assert out["counts"]["changed"] == 0
    assert session.updates == [], "a demotion here would be the rule self-harming"


def test_the_cascade_is_called_with_all_five_shipped_arguments():
    """🔴 #7012 added the fifth. A rail missing it asks the OLD question.

    Counts the call's arguments off the AST rather than trusting the text: a
    four-argument call still reads plausibly and would silently refuse `109341`,
    the specimen this whole issue is named for.
    """
    tree = ast.parse(inspect.getsource(rail.repair).lstrip())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_categorize_kalshi_market"
    ]
    assert len(calls) == 1, "exactly one verdict site, or the gate has two mouths"
    assert len(calls[0].args) + len(calls[0].keywords) == 5, (
        "the cascade takes (name, event_category, event_ticker, series_tag, "
        "series_category) — #7012 added the last one and `109341` is reachable "
        "through nothing else"
    )


def test_the_demotion_targets_are_the_pollers_own_set_by_identity():
    """Not a byte-identical copy — the SAME object.

    A private fork would pass a value test on the day it was written and drift
    the first time the poller's set changed.
    """
    src = inspect.getsource(rail.repair)
    assert "_VENUE_TOPIC_DEMOTION_TARGETS" in src
    assert "frozenset(" not in src, "a local set literal is a fork, not the set"
    # The poller's set is the authority for what may be WRITTEN. `crypto` is
    # barred because the poller DROPS a crypto verdict, so demoting into it
    # deletes a market rather than reclassifying one.
    assert "crypto" not in _VENUE_TOPIC_DEMOTION_TARGETS
    assert "other" not in _VENUE_TOPIC_DEMOTION_TARGETS
    assert "economics" in _VENUE_TOPIC_DEMOTION_TARGETS, (
        "the test is vacuous if the set is empty — economics is the "
        "destination three of the four subjects land on"
    )


# ---------------------------------------------------------------------------
# 3 — real venue payloads, read 2026-09-18
# ---------------------------------------------------------------------------

def _event(ticker, series, category):
    return {"event": {
        "event_ticker": ticker, "series_ticker": series, "category": category,
    }}


#: Read from `https://api.elections.kalshi.com/trade-api/v2/events/{t}`,
#: 2026-09-18. 🔴 EVERY value here was READ, not inferred. Two earlier drafts of
#: this table guessed `Entertainment` for the two `Social` events and the suite
#: went green on a verdict production does not produce — which is precisely the
#: failure a fixture is supposed to make impossible.
EVENTS = {
    # Subjects — the cascade moves these.
    "KXKRAKENBANKPUBLIC-27JAN01": _event(
        "KXKRAKENBANKPUBLIC-27JAN01", "KXKRAKENBANKPUBLIC", "Companies"),
    "KXBILLS": _event("KXBILLS", "KXBILLS", "Politics"),
    "KXWSMA-27MARCOMP": _event("KXWSMA-27MARCOMP", "KXWSMA", "Financials"),
    "KXYTVIEWSHIGH-YOU26OCT": _event(
        "KXYTVIEWSHIGH-YOU26OCT", "KXYTVIEWSHIGH", "Entertainment"),
    "KXCOMPANYACTIONANTH-27": _event(
        "KXCOMPANYACTIONANTH-27", "KXCOMPANYACTIONANTH", "Financials"),
    "KXELECTRICM3-28": _event("KXELECTRICM3-28", "KXELECTRICM3", "Companies"),
    # Controls — the cascade leaves these alone, each for a DIFFERENT reason.
    "KXPGAAWARDS-26-PIC": _event("KXPGAAWARDS-26-PIC", "KXPGAAWARDS", "Entertainment"),
    "KXDONATEMRBEAST-27JAN": _event(
        "KXDONATEMRBEAST-27JAN", "KXDONATEMRBEAST", "Social"),
    "KXFA-28JANUSSALES": _event("KXFA-28JANUSSALES", "KXFA", "Companies"),
    "KXTWITCHSUBSNINJA-27JAN01": _event(
        "KXTWITCHSUBSNINJA-27JAN01", "KXTWITCHSUBSNINJA", "Social"),
}

#: Read from `.../series/{t}`. `tags: None` is the venue's real answer for two
#: of these, not a placeholder — `_pick_series_tag` must survive it.
SERIES = {
    "KXKRAKENBANKPUBLIC": {"category": "Financials", "tags": ["IPOs", "Companies"]},
    "KXBILLS": {"category": "Politics", "tags": ["Congress"]},
    "KXWSMA": {"category": "Financials", "tags": ["KPIs"]},
    "KXYTVIEWSHIGH": {
        "category": "Entertainment",
        "tags": ["Views", "Music", "Monthly Views"],
    },
    "KXCOMPANYACTIONANTH": {"category": "Science and Technology", "tags": ["AI"]},
    "KXELECTRICM3": {
        "category": "Financials",
        "tags": ["Product launches", "Companies"],
    },
    "KXPGAAWARDS": {"category": "Entertainment", "tags": None},
    "KXDONATEMRBEAST": {"category": "Sports", "tags": ["Football"]},
    "KXFA": {"category": "Companies", "tags": ["KPIs"]},
    "KXTWITCHSUBSNINJA": {"category": "Entertainment", "tags": None},
}

#: The #7012 classifier's own protection control. It has NO stored row in the
#: candidate population, so it is exercised at CASCADE level rather than given a
#: fabricated id — an invented row would be the only thing in this file that
#: production could not confirm.
SUPERBOWL_SERIES_TAGS = ["Live Music", "Football"]


class _Row:
    def __init__(self, id, name, status, external_id, category, llm_sport_category):
        self.id = id
        self.name = name
        self.status = status
        self.external_id = external_id
        self.category = category
        self.llm_sport_category = llm_sport_category


#: The real production rows, read 2026-09-18 ~21:30Z — id, external_id, stored
#: `category` and stored `llm_sport_category` all as production holds them.
#: Four of the nine sit in the `other` arm, which a topic-only census omits.
PROD_ROWS = {
    # --- subjects ---------------------------------------------------------
    "KXKRAKENBANKPUBLIC-27JAN01": _Row(
        109341, "Which bank will take Kraken public before 2027?",
        "open", "KXKRAKENBANKPUBLIC-27JAN01", "other", "hockey"),
    "KXBILLS": _Row(
        109423, "Which bills will become law in 2026?",
        "open", "KXBILLS", "politics", "football"),
    "KXWSMA-27MARCOMP": _Row(
        59164729, "Williams-Sonoma total comparable brand growth in fiscal 2026",
        "open", "KXWSMA-27MARCOMP", "economics", "motorsports"),
    "KXYTVIEWSHIGH-YOU26OCT": _Row(
        60481237, "NBA YoungBoy: Highest daily view count in September 2026",
        "open", "KXYTVIEWSHIGH-YOU26OCT", "entertainment", "basketball"),
    "KXCOMPANYACTIONANTH-27": _Row(
        58015857,
        "Will Anthropic sign the Open Weights and American AI Leadership letter?",
        "open", "KXCOMPANYACTIONANTH-27", "economics", "golf"),
    # A SECOND motorsports row, so the undo's grouping-by-before-value is
    # actually exercised rather than asserted over five distinct values.
    "KXELECTRICM3-28": _Row(
        108495, "Will BMW release a Fully Electric M3 before 2028?",
        "open", "KXELECTRICM3-28", "other", "motorsports"),
    # #7042: a bare `kxpga` prefix USED to answer golf at STEP 1, above this
    # rule; the series is carved out of the ticker map now, so it is a subject.
    "KXPGAAWARDS-26-PIC": _Row(
        110748, "PGA Award for Best Theatrical Motion Picture?",
        "open", "KXPGAAWARDS-26-PIC", "entertainment", "golf"),
    # A SPORT -> SPORT verdict. Refused: not a demotion target.
    "KXDONATEMRBEAST-27JAN": _Row(
        109401,
        "Will MrBeast donate to East Carolina University athletics NIL program before 2027?",
        "open", "KXDONATEMRBEAST-27JAN", "other", "baseball"),
    # Both venue categories say `Companies`, modelled by neither mapper.
    "KXFA-28JANUSSALES": _Row(
        52755584, "Ford US vehicle sales volume in 2026",
        "open", "KXFA-28JANUSSALES", "other", "motorsports"),
    # The name trips no rule at all, so the cascade answers `other` — the
    # honest-empty default, which must never overwrite a stored value.
    "KXTWITCHSUBSNINJA-27JAN01": _Row(
        109248, "Will Ninja reach at least 10k Twitch subscribers this year?",
        "open", "KXTWITCHSUBSNINJA-27JAN01", "other", "esports"),
}


# ---------------------------------------------------------------------------
# 4 — the SHIPPED cascade's verdicts on those payloads (measured, then written)
# ---------------------------------------------------------------------------

def _verdict(ticker):
    row = PROD_ROWS[ticker]
    ev = EVENTS[ticker]["event"]
    series = SERIES[ev["series_ticker"]]
    return _categorize_kalshi_market(
        row.name,
        ev["category"],
        ticker,
        _pick_series_tag(series["tags"] or []),
        series["category"],
    )


@pytest.mark.parametrize(
    "ticker,expected",
    [
        # hockey  -> the Kraken is an exchange, not the Seattle club
        ("KXKRAKENBANKPUBLIC-27JAN01", "economics"),
        # football -> "bills" is legislation, not Buffalo
        ("KXBILLS", "politics"),
        # motorsports -> "Williams" is Williams-Sonoma, not the F1 team
        ("KXWSMA-27MARCOMP", "economics"),
        # basketball -> "NBA YoungBoy" is a rapper
        ("KXYTVIEWSHIGH-YOU26OCT", "entertainment"),
        # golf -> "Open" as in open weights
        ("KXCOMPANYACTIONANTH-27", "tech"),
    ],
)
def test_the_shipped_cascade_moves_the_subjects_off_the_sport_shelf(ticker, expected):
    """The ship, asserted as the value we WANT — never as `!= stored`.

    `!= stored` passes on `other`, which is the honest-empty default and would
    be a regression dressed as a fix.
    """
    assert _verdict(ticker) == expected


def test_the_headline_specimen_is_reachable_only_through_the_series_category():
    """🔴 `109341`'s EVENT category is modelled by nothing; its SERIES rescues it.

    Drops the fifth argument and asserts the answer CHANGES. Without this the
    suite would pass on a rail that never learned #7012's new parameter.
    """
    row = PROD_ROWS["KXKRAKENBANKPUBLIC-27JAN01"]
    ev = EVENTS["KXKRAKENBANKPUBLIC-27JAN01"]["event"]
    tag = _pick_series_tag(SERIES["KXKRAKENBANKPUBLIC"]["tags"])

    with_series = _categorize_kalshi_market(
        row.name, ev["category"], row.external_id, tag, "Financials")
    without = _categorize_kalshi_market(
        row.name, ev["category"], row.external_id, tag)

    assert with_series == "economics"
    assert without == "hockey", (
        "the event category alone still reads the club noun — if this ever "
        "stops being true the rail's reason for passing series_category is gone"
    )


def test_the_super_bowl_row_is_protected_by_reading_past_the_first_tag():
    """🔴 The prerequisite, proved by breaking it.

    `tags[0]` is 'Live Music'. If the rail re-spelled the chooser that way, the
    venue's own `Football` would go unread and the row would be demoted to
    entertainment — the rule overruling the venue using the venue.
    """
    name = "Who will headline the Super Bowl LX halftime show?"
    ticker = "KXPERFORMSUPERBOWL-26"
    tags = SUPERBOWL_SERIES_TAGS

    assert _pick_series_tag(tags) == "Football"
    assert tags[0] == "Live Music", "fixture must keep the sport tag NOT first"

    shipped = _categorize_kalshi_market(
        name, "Entertainment", ticker, _pick_series_tag(tags), "Entertainment")
    naive = _categorize_kalshi_market(
        name, "Entertainment", ticker, tags[0], "Entertainment")

    assert shipped == "football", "protected by the venue's own tag"
    assert naive == "entertainment", (
        "the naive spelling demotes it — this is what the guard is for"
    )


def test_the_pga_family_is_in_reach_once_7042_carves_it_out(monkeypatch):
    """#7042's boundary, moved by #7042 and pinned in its new place.

    Until #7042 a bare `kxpga` prefix answered golf at STEP 1 and this rail
    reported `venue_agrees` for a row that was still wrong. KXPGAAWARDS is now
    in `KALSHI_TICKER_PREFIXES_NOT_A_SPORT`, so step 1 declines, #7012's topic
    demotion answers `entertainment`, and the rail plans the move — with no
    edit to the rail itself.
    """
    assert _verdict("KXPGAAWARDS-26-PIC") == "entertainment"
    session = _StubSession([PROD_ROWS["KXPGAAWARDS-26-PIC"]])
    out = _run(session, monkeypatch)
    assert out["counts"]["changed"] == 1
    assert out["counts"]["venue_agrees"] == 0
    assert [(p["id"], p["before"], p["after"]) for p in out["planned"]] == [
        (110748, "golf", "entertainment"),
    ]
    assert session.updates == []


def test_a_sport_to_sport_verdict_is_refused_not_written(monkeypatch):
    """🔴 `109401` is a REAL row whose cascade answer is another SPORT.

    MrBeast's NIL market is stored `baseball`; the venue's series is tagged
    `Football`, so step 1b answers `football`. Moving a row between two sports
    is a different issue that has not been measured, so the rail counts it and
    declines. Without this branch the rail would silently widen past its warrant
    on the very first production pass.
    """
    assert _verdict("KXDONATEMRBEAST-27JAN") == "football"
    session = _StubSession([PROD_ROWS["KXDONATEMRBEAST-27JAN"]])
    out = _run(session, monkeypatch)
    assert out["counts"]["changed"] == 0
    assert out["counts"]["refused_not_a_demotion_target"] == 1
    assert session.updates == []


def test_the_ford_row_is_left_wrong_and_that_is_disclosed(monkeypatch):
    """A row this ship does NOT fix, pinned so the ship line cannot grow.

    Both of `52755584`'s venue categories say `Companies`, which neither mapper
    models, so no topic is implied and the name guess stands.
    """
    assert _verdict("KXFA-28JANUSSALES") == "motorsports"
    session = _StubSession([PROD_ROWS["KXFA-28JANUSSALES"]])
    out = _run(session, monkeypatch)
    assert out["counts"]["venue_agrees"] == 1
    assert out["counts"]["changed"] == 0


# ---------------------------------------------------------------------------
# 5 — the plan, driven end to end against a stub session
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows=(), scalar=0):
        self._rows = list(rows)
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _StubSession:
    """The four statement shapes `repair()` issues, and nothing else.

    `moves` lets a test say which ids the compare-and-set actually matched, so a
    PARTIAL apply can be driven.
    """

    def __init__(self, rows, moves=None, fail_update=False, remaining=0):
        self.rows = list(rows)
        self.moves = moves
        self.fail_update = fail_update
        self.remaining = remaining
        self.updates: list[dict] = []
        self.selects: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        upper = sql.upper()
        if "SET LOCAL" in upper:
            return _Result()
        if upper.strip().startswith("\n                        UPDATE") or " UPDATE " in upper or upper.lstrip().startswith("UPDATE"):
            if self.fail_update:
                raise RuntimeError("canceling statement due to statement timeout")
            self.updates.append(dict(params))
            moved = self.moves is None or params["id"] in self.moves
            return _Result([(params["id"],)] if moved else [])
        if "COUNT(*)" in upper:
            self.selects.append(sql)
            return _Result(scalar=self.remaining)
        if "SELECT" in upper:
            self.selects.append(sql)
            after = params.get("after_id") or 0
            lim = params.get("lim") or 20
            # `ORDER BY fm.id` is in the real statement, so the rig must sort
            # too — a stub that returns insertion order tests a walk the
            # database would never produce.
            picked = sorted(
                (r for r in self.rows if r.id > after), key=lambda r: r.id
            )[:lim]
            return _Result(picked)
        raise AssertionError(f"unexpected statement:\n{sql}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _run(session, monkeypatch, events=None, series=None, apply=False, **kw):
    """Drive `repair()` with both venue doors stubbed."""
    events = EVENTS if events is None else events
    series = SERIES if series is None else series

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
    return asyncio.run(rail.repair(session, apply=apply, **kw))


_SUBJECTS = [
    PROD_ROWS["KXKRAKENBANKPUBLIC-27JAN01"],
    PROD_ROWS["KXBILLS"],
    PROD_ROWS["KXWSMA-27MARCOMP"],
    PROD_ROWS["KXYTVIEWSHIGH-YOU26OCT"],
    PROD_ROWS["KXCOMPANYACTIONANTH-27"],
    PROD_ROWS["KXELECTRICM3-28"],
]


def test_the_seven_subjects_plan_and_every_control_is_refused_by_name(monkeypatch):
    """🔴 The ship and its disclosed refusals, in one run.

    All four refusal reasons appear, each raised by a REAL production row, so
    none of them is a branch that only a synthetic input can reach.
    """
    session = _StubSession(sorted(PROD_ROWS.values(), key=lambda r: r.id))
    out = _run(session, monkeypatch)

    assert out["terminal"] == "dry_run"
    assert out["counts"]["candidates_examined"] == 10
    assert out["counts"]["changed"] == 7
    assert {p["id"] for p in out["planned"]} == {
        109341, 109423, 59164729, 60481237, 58015857, 108495,
        110748,  # #7042: the Producers Guild, in reach since the carve-out
    }
    assert {(p["before"], p["after"]) for p in out["planned"]} == {
        ("hockey", "economics"),
        ("football", "politics"),
        ("motorsports", "economics"),
        ("basketball", "entertainment"),
        ("golf", "tech"),
        ("golf", "entertainment"),
    }
    # The controls, each by its own named reason.
    assert out["counts"]["venue_agrees"] == 1                   # Ford
    assert out["counts"]["refused_not_a_demotion_target"] == 1  # MrBeast, sport->sport
    assert out["counts"]["refused_other"] == 1                  # Ninja, no rule fires
    assert session.updates == []


def test_a_dry_run_never_writes(monkeypatch):
    session = _StubSession(_SUBJECTS)
    out = _run(session, monkeypatch)
    assert out["counts"]["rows_written"] == 0
    assert out["applied"] == []
    assert session.updates == []
    assert session.commits == 0


def test_an_apply_compare_and_sets_on_the_value_it_read(monkeypatch):
    """🔴 The CAS is not decoration: the Kalshi poller reaches these rows every
    two hours, so a write landing between this rail's SELECT and its UPDATE is
    an ORDINARY outcome, not a theoretical one.

    The predicate is asserted in the STATEMENT, not merely in the bound params.
    Deleting the WHERE clause leaves `:before` bound and unused — the mutant
    that survived the first sweep of this suite — so a params-only check
    passes while the rail silently clobbers a fresher value.
    """
    session = _StubSession(_SUBJECTS)
    out = _run(session, monkeypatch, apply=True)

    assert out["terminal"] == "changed"
    assert out["counts"]["rows_written"] == 6
    assert len(session.updates) == 6
    for u in session.updates:
        assert set(u) == {"llm", "id", "before"}, (
            "the UPDATE binds exactly three params — a fourth means another "
            "column joined the write"
        )

    stmt = [s for s in _sql_literals(rail.repair) if "UPDATE " in s.upper()][0]
    where = stmt[stmt.upper().index(" WHERE ") :]
    assert "llm_sport_category IS NOT DISTINCT FROM :before" in where, (
        "the compare-and-set guard is missing — a concurrent poll would be "
        "clobbered, and the D51 undo would name a value that was never there"
    )
    assert "IS NOT DISTINCT FROM" in where, (
        "NULL-safe: a plain `=` never matches a stored NULL, so rows with no "
        "badge would silently never move"
    )
    assert "RETURNING id" in stmt, (
        "the undo must be built from what MOVED, not from what was planned"
    )


def test_the_undo_names_only_the_rows_that_actually_moved(monkeypatch):
    """🔴 Built from RETURNING, never from the plan.

    A restore built from `planned` would write a stale `before` over a
    concurrent poller's fresher value — the undo becoming a second defect.
    """
    session = _StubSession(_SUBJECTS, moves={109341, 108495})
    out = _run(session, monkeypatch, apply=True)

    assert out["counts"]["changed"] == 6, "six were planned"
    assert out["counts"]["rows_written"] == 2, "two actually moved"
    assert {a["id"] for a in out["applied"]} == {109341, 108495}
    assert "109341" in out["restore_sql"] and "108495" in out["restore_sql"]
    for stranded in ("59164729", "60481237", "58015857", "109423"):
        assert stranded not in out["restore_sql"], (
            "a row that did not move must not appear in the undo"
        )


def test_the_restore_sql_is_runnable_and_grouped_by_before_value(monkeypatch):
    session = _StubSession(_SUBJECTS)
    out = _run(session, monkeypatch)
    sql = out["restore_sql"]
    # Five distinct before-values across the six subjects (motorsports twice)
    # -> one statement per DISTINCT value, not one per row.
    assert sql.count("UPDATE futures_markets") == 5
    assert "WHERE id IN (108495, 59164729);" in sql, (
        "the two motorsports rows share one statement; one statement per ROW "
        "would still be runnable but would prove the grouping is not happening"
    )
    for line in sql.splitlines():
        assert line.startswith("UPDATE futures_markets SET llm_sport_category = ")
        assert line.endswith(");")
        assert "{" not in line and "[" not in line, (
            "a before-value MAP interpolated where the value belongs is not "
            "valid SQL, and D51 is granted on this line being runnable"
        )


def test_a_write_failure_rolls_back_and_is_never_a_verdict(monkeypatch):
    session = _StubSession(_SUBJECTS, fail_update=True)
    out = _run(session, monkeypatch, apply=True)
    assert out["counts"]["write_failed"] == 6
    assert out["counts"]["rows_written"] == 0
    assert session.rollbacks == 6
    assert out["terminal"] == "no_rows_written", (
        "gotcha #53 — a pass that wrote nothing says so in a named terminal"
    )


# ---------------------------------------------------------------------------
# 6 — the venue is allowed to be unavailable, and that is never a verdict
# ---------------------------------------------------------------------------


def test_a_404_on_the_event_is_reported_separately_from_a_timeout(monkeypatch):
    """#36: 404 and 429 need opposite handling."""
    gone = _run(
        _StubSession([PROD_ROWS["KXKRAKENBANKPUBLIC-27JAN01"]]),
        monkeypatch,
        events={"KXKRAKENBANKPUBLIC-27JAN01": "404"},
    )
    assert gone["counts"]["not_at_venue"] == 1
    assert gone["counts"]["indeterminate"] == 0

    sick = _run(
        _StubSession([PROD_ROWS["KXKRAKENBANKPUBLIC-27JAN01"]]),
        monkeypatch,
        events={},
    )
    assert sick["counts"]["indeterminate"] == 1
    assert sick["counts"]["not_at_venue"] == 0
    assert sick["counts"]["changed"] == 0


def test_a_transient_failure_on_the_series_door_is_never_a_verdict(monkeypatch):
    """🔴 The cascade reads the tag ABOVE its name rules.

    Classifying without the tag because the venue rate-limited us is
    classifying on a rate limit.
    """
    session = _StubSession([PROD_ROWS["KXBILLS"]])
    out = _run(session, monkeypatch, series={}, apply=True)
    assert out["counts"]["indeterminate"] == 1
    assert out["counts"]["changed"] == 0
    assert session.updates == []


def test_membership_requires_the_venue_to_echo_our_ticker(monkeypatch):
    """Id identity, never a fuzzy answer."""
    session = _StubSession([PROD_ROWS["KXKRAKENBANKPUBLIC-27JAN01"]])
    out = _run(
        session,
        monkeypatch,
        events={
            "KXKRAKENBANKPUBLIC-27JAN01": _event(
                "KXSOMETHINGELSE-27JAN01", "KXKRAKENBANKPUBLIC", "Companies")
        },
        apply=True,
    )
    assert out["counts"]["not_our_ticker"] == 1
    assert out["counts"]["changed"] == 0
    assert session.updates == []


def test_the_honest_empty_default_never_overwrites_a_real_tag(monkeypatch):
    """`other` is the absence of an answer, not an answer."""
    session = _StubSession([PROD_ROWS["KXKRAKENBANKPUBLIC-27JAN01"]])
    monkeypatch.setattr(
        "app.tasks.kalshi._categorize_kalshi_market",
        lambda *a, **k: "other",
    )
    out = _run(session, monkeypatch, apply=True)
    assert out["counts"]["refused_other"] == 1
    assert out["counts"]["changed"] == 0
    assert session.updates == []


# ---------------------------------------------------------------------------
# 7 — scope and paging
# ---------------------------------------------------------------------------


def test_an_unknown_status_scope_is_refused_by_name(monkeypatch):
    """🔴 Never silently defaulted.

    A typo that quietly became `open` would report a complete pass over a
    population the operator did not ask for.
    """
    session = _StubSession(_SUBJECTS)
    out = _run(session, monkeypatch, status_scope="opne")
    assert out["terminal"] == "refused_bad_status_scope"
    assert out["status_scope"] == "opne", "the refusal echoes what was asked"
    assert "counts" not in out, "a refused pass reports no census at all"
    assert session.selects == [], "it refuses BEFORE it queries"
    assert session.updates == []


def test_the_default_scope_is_open(monkeypatch):
    session = _StubSession(_SUBJECTS)
    out = _run(session, monkeypatch)
    assert out["status_scope"] == "open"


@pytest.mark.parametrize("scope", ["open", "resolved", "all"])
def test_every_documented_scope_is_accepted(scope, monkeypatch):
    session = _StubSession(_SUBJECTS)
    out = _run(session, monkeypatch, status_scope=scope)
    assert out["status_scope"] == scope
    assert out["terminal"] == "dry_run"


def test_paging_is_a_keyset_on_id_and_never_an_offset():
    """🔴 An apply removes rows from its own population.

    An OFFSET walk would skip exactly as many rows as it repaired.
    """
    # Read the SQL STATEMENTS, not the whole source: this module's own prose
    # explains why an offset is wrong, and a substring scan over the source
    # would fire on that explanation.
    for stmt in _sql_literals(rail.repair):
        assert "OFFSET" not in stmt.upper(), (
            f"an offset walk skips exactly what it repaired:\n{stmt}"
        )
    walk = [s for s in _sql_literals(rail.repair) if "ORDER BY" in s]
    assert len(walk) == 1
    assert "fm.id > :after_id" in walk[0]
    assert "ORDER BY fm.id" in walk[0]


def test_the_cursor_advances_and_remaining_is_reported(monkeypatch):
    session = _StubSession(_SUBJECTS, remaining=37)
    out = _run(session, monkeypatch, limit=2)
    assert out["page_size"] == 2
    assert out["counts"]["candidates_examined"] == 2
    # Ascending id order over the six subjects starts 108495, 109341, … — so a
    # two-row page ends on 109341 and the NEXT call resumes strictly after it.
    assert out["next_after_id"] == 109341, "the largest id on the page"
    assert out["remaining_before_page"] == 37, (
        "gotcha #53 — a `changed: 0` page is not a finished population"
    )


def test_the_page_size_is_clamped_so_one_call_cannot_outrun_the_router_wall():
    assert rail._resolve_limit(None) == rail.DEFAULT_LIMIT
    assert rail._resolve_limit(0) == rail.DEFAULT_LIMIT
    assert rail._resolve_limit(-5) == rail.DEFAULT_LIMIT
    assert rail._resolve_limit(5) == 5
    assert rail._resolve_limit(10_000) == rail.MAX_LIMIT


# ---------------------------------------------------------------------------
# 8 — the columns this rail must never touch
# ---------------------------------------------------------------------------


def test_the_write_touches_exactly_one_column(monkeypatch):
    """🔴 Not `updated_at` (CERT-2382), not `status`, not `category`."""
    session = _StubSession(_SUBJECTS)
    _run(session, monkeypatch, apply=True)
    assert session.updates, "the test is vacuous if nothing was written"

    updates = [s for s in _sql_literals(rail.repair) if "UPDATE " in s.upper()]
    assert len(updates) == 1, "one write site, or there is a second mouth"

    # The SET clause is the only part that decides what CHANGES. Parsed as a
    # list of assignments rather than scanned as a substring: `category =`
    # occurs inside `llm_sport_category = :llm`, and the WHERE clause compares
    # the column legitimately.
    assignments = [a.strip() for a in _set_clause(updates[0]).split(",")]
    assert assignments == ["llm_sport_category = :llm"], (
        f"this rail writes exactly one column; found {assignments}"
    )
    for forbidden in ("updated_at", "NOW()"):
        assert forbidden not in updates[0], (
            f"{forbidden} must never appear in this rail's write — CERT-2382: "
            "a card renders updated_at as its own relative date, so a TRUTH "
            "repair would publish a freshness lie in the same statement"
        )


def test_the_write_is_core_sql_not_orm_attribute_assignment():
    """Gotchas #4/#5 — JSONB/ORM attribute assignment can silently fail.

    Asked off the AST as "is there an attribute ASSIGNMENT to a model column",
    not as a substring: `fm.llm_sport_category = ANY(:non_sport)` inside the
    SELECT is SQL text and is exactly what a substring scan would misread.
    """
    src = inspect.getsource(rail.repair)
    assert "session.execute(" in src

    tree = ast.parse(src.lstrip())
    written_attrs = {
        t.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for t in node.targets
        if isinstance(t, ast.Attribute)
    }
    assert "llm_sport_category" not in written_attrs, (
        "ORM attribute assignment can silently fail — use Core UPDATE"
    )


def test_the_rail_is_not_wired_to_a_beat():
    """ATTENDED ONLY — a terminating repair is never a standing job."""
    beat = Path("app/tasks/__init__.py")
    for candidate in (beat, Path("backend") / beat):
        if candidate.exists():
            assert "repair_kalshi_venue_topic_badges" not in candidate.read_text()


def test_the_repair_is_registered_under_its_own_key_not_the_siblings():
    """🔴 Not a widening of the frozen, already-applied #6955 bound."""
    from app.routes.admin_repairs import _REPAIRS

    assert _REPAIRS["kalshi-venue-topic-badges"] == (
        "app.tasks.repair_kalshi_venue_topic_badges",
        "repair",
    )
    assert _REPAIRS["kalshi-club-noun-category"] == (
        "app.tasks.repair_kalshi_club_noun_category",
        "repair",
    ), "the sibling must be untouched — its twelfth entry is a refusal control"
