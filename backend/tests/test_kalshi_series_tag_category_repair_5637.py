"""#5637 / CERT-2737 — the two findings that blocked the classifier ship.

CERT-2737 granted that step 1b classifies correctly and withheld the token for
two reasons, both of which are about what happens to rows that ALREADY EXIST:

1. **Current rows never converge.** `app/tasks/kalshi.py` writes the tag through
   `coalesce(nullif(llm_sport_category, 'other'), new)` — #1888's honest-empty
   rule — so a row already stamped with a WRONG sport keeps it through every
   poll, forever. The Redblacks row the issue was filed about is one of 28 such
   rows measured open on production 2026-09-12, every one of them a game played
   that same weekend.

2. **A transient lookup was cached as a verdict.** `get_series_metadata`
   returned `None` for a 404 *and* for a 429/5xx/timeout, and the caller cached
   that `None` module-wide until the dyno restarted. One sick request therefore
   froze a whole series into name-guessed classification for hours.

The required repair is `5637-CURRENT-ROWS-AND-TRANSIENT-LOOKUPS-CONVERGE`, with
named current-row and transient-recovery tests. Those two are
:func:`test_a_current_wrong_sport_row_converges_5637` and
:func:`test_a_transient_series_lookup_is_never_cached_as_a_verdict_5637`; the
rest of this file is the anti-vacuity scaffolding around them.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.tasks import repair_kalshi_series_tag_category as rail

# ---------------------------------------------------------------------------
# The specimens. Real rows, read off production 2026-09-12 — not invented.
# ---------------------------------------------------------------------------

#: The row CERT-2737 named. CFL, stored `basketball`, kickoff 2026-09-12 20:00Z.
_REDBLACKS_ID = 60616653
_REDBLACKS_NAME = "Ottawa Redblacks vs Toronto Argonauts: Total Points"
_REDBLACKS_TICKER = "KXCFLTOTAL-26SEP12OTTTOR"

#: An AFC Wimbledon fixture stored `tennis` — the club whose NAME is the guess.
_WIMBLEDON_ID = 60489002
_WIMBLEDON_NAME = "Wimbledon vs Doncaster"
_WIMBLEDON_TICKER = "KXEFLL1GAME-26SEP12WIMDR"

#: An NFL fantasy-points row stored `basketball` (#5621's family).
_FFPTS_ID = 60780329
_FFPTS_NAME = "Baltimore vs Indianapolis: Fantasy Points"
_FFPTS_TICKER = "KXNFLFFPTS-26SEP13BALIND"


class _Row:
    """One `futures_markets` row as the rail reads it (attribute access)."""

    def __init__(
        self,
        id,
        name,
        source,
        external_id,
        llm_sport_category,
        commence_time=None,
        event_id=None,
    ):
        self.id = id
        self.name = name
        self.source = source
        self.external_id = external_id
        self.llm_sport_category = llm_sport_category
        self.commence_time = commence_time
        self.event_id = event_id


class _GhostRow:
    """One row of `_GHOST_EVENT_SQL`, as the event arm reads it."""

    def __init__(
        self, id, h, a, st, sport_key, real_id=None, real_key=None, real_ct=None
    ):
        self.id = id
        self.h = h
        self.a = a
        self.ct = None
        self.st = st
        self.sport_key = sport_key
        self.real_id = real_id
        self.real_key = real_key
        self.real_ct = real_ct


class _FakeSession:
    """Enough session to run the PLAN half of both arms. It refuses to write.

    Three statements reach it: the population SELECT, the raw-`text()` ghost
    query, and a `count()` for the remaining floor. They are told apart by
    SHAPE, not by call order — an ordering fake silently mis-answers the moment
    a statement is added, which is how a fake starts lying.
    """

    def __init__(self, rows, ghosts=()):
        self._rows = rows
        self._ghosts = list(ghosts)
        self.writes = 0
        self.ghost_query_args = None

    async def execute(self, statement, params=None):
        visit = getattr(statement, "__visit_name__", None)
        if visit == "textclause":
            self.ghost_query_args = params
            ghosts = self._ghosts

            class _GhostResult:
                def all(self):
                    return ghosts

            return _GhostResult()
        if visit != "select":
            self.writes += 1
            raise AssertionError(
                "the plan half issued a write — `apply=False` must never reach "
                "the UPDATE"
            )
        rows = self._rows
        # The count is the only SELECT with no FROM-list entity of its own; the
        # rail asks for it via `scalar_one`, so both are served and the caller
        # picks. That keeps the fake shape-driven rather than order-driven.

        class _Result:
            def all(self):
                return rows

            def scalar_one(self):
                return len(rows)

        return _Result()

    async def commit(self):  # pragma: no cover - reaching this is the failure
        raise AssertionError("`apply=False` committed")


class _TagStub:
    """Stands in for `_resolve_series_tag_result`, recording what it was asked.

    `calls` is the anti-vacuity instrument for the `mapped_ticker` gate: a test
    that asserts "no venue call was made" is worthless unless something counts
    the calls that WOULD have been made.
    """

    def __init__(self, by_ticker):
        self._by_ticker = by_ticker
        self.calls: list[str] = []

    async def __call__(self, service, ticker):
        self.calls.append(ticker)
        return self._by_ticker[ticker]


def _result(tag=None, resolved=True, not_asked=False):
    from app.tasks.kalshi import SeriesTagResult

    return SeriesTagResult(tag=tag, resolved=resolved, not_asked=not_asked)


async def _plan(rows, tags, monkeypatch):
    import app.tasks.kalshi as kalshi_module

    stub = _TagStub(tags)
    monkeypatch.setattr(kalshi_module, "_resolve_series_tag_result", stub)
    session = _FakeSession(rows)
    out = await rail.repair(session, apply=False)
    return out, stub


# ---------------------------------------------------------------------------
# FINDING 1 — the current-row test CERT-2737 named.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_current_wrong_sport_row_converges_5637(monkeypatch):
    """THE NAMED CURRENT-ROW TEST.

    The row CERT-2737 said stays visible. Stored `basketball`; the venue tags
    its series `Football`; the shipped cascade agrees. It must be PLANNED, and
    the plan must carry the before-value so D51's restore is exact.
    """
    row = _Row(
        _REDBLACKS_ID, _REDBLACKS_NAME, "kalshi", _REDBLACKS_TICKER, "basketball"
    )
    out, _ = await _plan(
        [row], {_REDBLACKS_TICKER: _result(tag="Football")}, monkeypatch
    )

    assert [p["id"] for p in out["planned"]] == [_REDBLACKS_ID]
    plan = out["planned"][0]
    assert plan["before"] == "basketball"
    assert plan["after"] == "football", (
        "the rail must write what the VENUE's tag resolves to, not a literal of "
        "its own — it has no sport vocabulary to write from"
    )
    assert out["changed"] == 0, "a dry run must change nothing"
    assert "basketball" in out["restore_sql"], (
        "the D51 undo has to name the value it restores, on the dry run too"
    )


@pytest.mark.asyncio
async def test_every_measured_family_converges_not_only_the_cited_one(monkeypatch):
    """The ship is 28 rows across four wrong sports, not one Redblacks row.

    Three families, three different before-values, two different after-values.
    A rail that hard-coded the cited case would pass the test above and fail
    this one.
    """
    rows = [
        _Row(_REDBLACKS_ID, _REDBLACKS_NAME, "kalshi", _REDBLACKS_TICKER, "basketball"),
        _Row(_WIMBLEDON_ID, _WIMBLEDON_NAME, "kalshi", _WIMBLEDON_TICKER, "tennis"),
        _Row(_FFPTS_ID, _FFPTS_NAME, "kalshi", _FFPTS_TICKER, "basketball"),
    ]
    tags = {
        _REDBLACKS_TICKER: _result(tag="Football"),
        _WIMBLEDON_TICKER: _result(tag="Soccer"),
        _FFPTS_TICKER: _result(tag="Football"),
    }
    out, _ = await _plan(rows, tags, monkeypatch)

    moved = {p["id"]: (p["before"], p["after"]) for p in out["planned"]}
    assert moved == {
        _REDBLACKS_ID: ("basketball", "football"),
        _WIMBLEDON_ID: ("tennis", "soccer"),
        _FFPTS_ID: ("basketball", "football"),
    }
    # D51: one statement per distinct before-value, and this rail spans several
    # by construction — the multi-statement case is the normal case here.
    assert out["restore_sql"].count("UPDATE futures_markets") == 2


@pytest.mark.asyncio
async def test_an_already_correct_row_is_refused_not_rewritten(monkeypatch):
    row = _Row(
        _REDBLACKS_ID, _REDBLACKS_NAME, "kalshi", _REDBLACKS_TICKER, "football"
    )
    out, _ = await _plan(
        [row], {_REDBLACKS_TICKER: _result(tag="Football")}, monkeypatch
    )
    assert out["planned"] == []
    assert out["refused"] == {"already_correct": 1}


@pytest.mark.asyncio
async def test_a_mapped_ticker_is_refused_and_costs_no_venue_call(monkeypatch):
    """Step 1 names the LEAGUE; the tag could only be less specific.

    The recorded call list is what makes this test non-vacuous — `not_asked`
    has to come from the resolver short-circuiting, not from the rail forgetting
    to ask.
    """
    row = _Row(
        999_001, "Pittsburgh at Philadelphia", "kalshi",
        "KXNHLGAME-26APR22PITPHI", "hockey",
    )
    out, stub = await _plan(
        [row], {"KXNHLGAME-26APR22PITPHI": _result(not_asked=True)}, monkeypatch
    )
    assert out["planned"] == []
    assert out["refused"] == {"mapped_ticker": 1}
    assert out["series_asked"] == 0, (
        "a mapped ticker must not spend the venue budget"
    )


@pytest.mark.asyncio
async def test_the_venue_budget_meters_calls_made_not_series_seen(monkeypatch):
    """A free answer must not spend the budget.

    Four rows in ONE series, and the resolver reports `called` on only the
    first — the rest are cache hits. The budget is the cost of asking the venue,
    so it must read 1, not 4. The first cut metered distinct series and charged
    for cache hits, which stalls a drain that has spent nothing.
    """
    rows = [
        _Row(900 + i, _WIMBLEDON_NAME, "kalshi", _WIMBLEDON_TICKER, "tennis")
        for i in range(4)
    ]

    class _CachingStub:
        def __init__(self):
            self.calls = 0

        async def __call__(self, service, ticker):
            self.calls += 1
            from app.tasks.kalshi import SeriesTagResult

            return SeriesTagResult(tag="Soccer", called=self.calls == 1)

    import app.tasks.kalshi as kalshi_module

    stub = _CachingStub()
    monkeypatch.setattr(kalshi_module, "_resolve_series_tag_result", stub)
    out = await rail.repair(_FakeSession(rows), apply=False)

    assert len(out["planned"]) == 4, "all four rows are still judged"
    assert out["venue_calls"] == 1, (
        "three of the four answers were free; charging for them is how a drain "
        "stalls without having spent anything"
    )
    assert out["series_asked"] == 1


@pytest.mark.asyncio
async def test_a_tag_we_do_not_model_falls_through_rather_than_guessing(monkeypatch):
    row = _Row(
        999_002, "Some Olympic Thing", "kalshi", "KXOLYWHATEVER-26SEP12AAA", "tennis"
    )
    out, _ = await _plan(
        [row], {"KXOLYWHATEVER-26SEP12AAA": _result(tag="Olympics")}, monkeypatch
    )
    assert out["planned"] == []
    assert out["refused"] == {"no_usable_tag": 1}


@pytest.mark.asyncio
async def test_the_cascade_gate_refuses_a_row_the_venue_tag_alone_would_move(
    monkeypatch,
):
    """THE GATE THAT MAKES THE PREDICATE SAFE.

    An IPO market inside a sports series: the venue tags the series `Hockey`,
    but step 0 of the shipped cascade overrides the sport for an IPO name. The
    rail must defer to the cascade — it is what ingest actually runs — and
    refuse, rather than writing the tag's answer straight through.

    Without gate 5 this row would be planned, which is the whole difference
    between a predicate that is safe and one that is merely narrow.
    """
    row = _Row(
        999_003, "Kraken IPO before 2027?", "kalshi",
        "KXKRAKENIPO-26SEP12AAA", "economics",
    )
    out, _ = await _plan(
        [row], {"KXKRAKENIPO-26SEP12AAA": _result(tag="Hockey")}, monkeypatch
    )
    assert out["planned"] == [], (
        "the venue tag said hockey and the shipped cascade said otherwise — the "
        "cascade wins, because the cascade is what ingest runs"
    )
    assert out["refused"] == {"cascade_disagrees": 1}


@pytest.mark.asyncio
async def test_a_row_from_another_venue_is_refused(monkeypatch):
    row = _Row(
        999_004, _REDBLACKS_NAME, "polymarket", _REDBLACKS_TICKER, "basketball"
    )
    out, _ = await _plan([row], {}, monkeypatch)
    assert out["planned"] == []
    assert out["refused"] == {"not_kalshi": 1}


# ---------------------------------------------------------------------------
# FINDING 2 — the transient-recovery tests CERT-2737 named.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_transient_series_lookup_is_never_cached_as_a_verdict_5637(
    monkeypatch,
):
    """THE NAMED TRANSIENT-RECOVERY TEST.

    A first lookup fails transiently; the second succeeds. The failure must NOT
    be remembered — the series must be asked again, and the second answer must
    be the one that counts.

    This runs against the real `_resolve_series_tag_result` and a fake service,
    because the defect lived in the cache write, which a stubbed resolver would
    step over.
    """
    import app.tasks.kalshi as kalshi_module
    from app.services.kalshi_api import KalshiSeriesLookupError

    monkeypatch.setattr(kalshi_module, "_SERIES_TAG_CACHE", {})
    monkeypatch.setattr(kalshi_module, "_SERIES_TAG_FAILURE_UNTIL", {})

    # A controlled clock from the FIRST call, not from the retry: the
    # suppression deadline is `now + TTL`, so a clock patched only afterwards
    # would be compared against a real monotonic baseline and never lapse.
    clock = [1000.0]
    monkeypatch.setattr(kalshi_module, "_series_tag_clock", lambda: clock[0])

    class _SickThenWell:
        def __init__(self):
            self.calls = 0

        async def get_series_metadata(self, series):
            self.calls += 1
            if self.calls == 1:
                raise KalshiSeriesLookupError("429 from the venue")
            return {"tags": ["Football"]}

    service = _SickThenWell()

    first = await kalshi_module._resolve_series_tag_result(service, _REDBLACKS_TICKER)
    assert first.resolved is False, "a failed lookup is not a resolved answer"
    assert first.tag is None
    assert kalshi_module._SERIES_TAG_CACHE == {}, (
        "🔴 THE DEFECT: the failure must never reach the ANSWER cache. Caching "
        "it there froze the series into name-guessed classification until the "
        "dyno restarted."
    )

    # The retry is suppressed for one beat and no longer, so travel past the
    # TTL rather than sleeping through it.
    clock[0] += kalshi_module._SERIES_TAG_FAILURE_TTL_SECONDS + 1.0

    second = await kalshi_module._resolve_series_tag_result(service, _REDBLACKS_TICKER)
    assert service.calls == 2, (
        "once the suppression lapses the series must be asked again — recovery "
        "must never need a dyno restart"
    )
    assert second.resolved is True
    assert second.tag == "Football"
    assert kalshi_module._SERIES_TAG_CACHE == {"KXCFLTOTAL": "Football"}
    assert kalshi_module._SERIES_TAG_FAILURE_UNTIL == {}, (
        "an answer retires the failure record"
    )


@pytest.mark.asyncio
async def test_a_venue_confirmed_absence_is_still_cached(monkeypatch):
    """The other half — and the control that keeps the test above honest.

    "The venue answered and there is no tag" IS a fact worth remembering. A fix
    that simply stopped caching everything would pass the transient test and
    re-fetch every untagged series on every event in the beat.
    """
    import app.tasks.kalshi as kalshi_module

    monkeypatch.setattr(kalshi_module, "_SERIES_TAG_CACHE", {})
    monkeypatch.setattr(kalshi_module, "_SERIES_TAG_FAILURE_UNTIL", {})

    class _NoTag:
        def __init__(self):
            self.calls = 0

        async def get_series_metadata(self, series):
            self.calls += 1
            return {"tags": []}

    service = _NoTag()
    await kalshi_module._resolve_series_tag_result(service, _REDBLACKS_TICKER)
    await kalshi_module._resolve_series_tag_result(service, _REDBLACKS_TICKER)

    assert service.calls == 1, "a venue-confirmed absence must be cached"
    assert kalshi_module._SERIES_TAG_CACHE == {"KXCFLTOTAL": None}


@pytest.mark.asyncio
async def test_an_indeterminate_row_is_never_written_and_stops_the_scan(monkeypatch):
    """A transient failure is not a verdict, and it is not progress either.

    The row must be refused, the cursor must NOT advance past it, and
    `scan_exhausted` must be unreachable while it stands — CERT-666's correction
    to the Polymarket sibling, where an unresolved last row was reported as a
    finished drain.
    """
    rows = [
        _Row(_REDBLACKS_ID, _REDBLACKS_NAME, "kalshi", _REDBLACKS_TICKER, "basketball"),
        _Row(_WIMBLEDON_ID, _WIMBLEDON_NAME, "kalshi", _WIMBLEDON_TICKER, "tennis"),
    ]
    tags = {
        _REDBLACKS_TICKER: _result(resolved=False),
        _WIMBLEDON_TICKER: _result(tag="Soccer"),
    }
    out, stub = await _plan(rows, tags, monkeypatch)

    assert out["planned"] == [], "nothing is written on an indeterminate row"
    assert out["refused"] == {"indeterminate": 1}
    assert out["stopped_at_unresolved"] is True
    assert out["terminal"] == "paused_unresolved"
    assert out["scan_exhausted"] is False, (
        "🔴 completion must be unreachable while a retryable row remains"
    )
    assert out["next_cursor"] is None, (
        "the cursor must not advance past the unresolved row — advancing is how "
        "a row gets skipped forever"
    )
    assert stub.calls == [_REDBLACKS_TICKER], (
        "the scan stops AT the unresolved row; the second row is not consumed"
    )


@pytest.mark.asyncio
async def test_the_service_tells_a_404_apart_from_a_failure():
    """Gotcha #36, at the layer the ship first got wrong.

    `get_series_metadata`'s docstring always claimed "None only for 404". Its
    body returned None for a 429 past its backoff, a 5xx and a timeout too.
    """
    import httpx

    from app.services.kalshi_api import KalshiAPIService, KalshiSeriesLookupError

    service = KalshiAPIService()

    class _Client:
        def __init__(self, status):
            self._status = status
            self.calls = 0

        async def get(self, url, **kwargs):
            self.calls += 1
            # The request must be attached: `raise_for_status` on a bare
            # Response raises RuntimeError, which the method would fold into a
            # lookup error — a green test proving the wrong thing.
            return httpx.Response(
                self._status,
                json={"series": {"tags": ["Football"]}},
                request=httpx.Request("GET", url),
            )

    service.client = _Client(404)
    assert await service.get_series_metadata("KXCFLTOTAL") is None, (
        "a 404 is the one absence this method may report"
    )

    service.client = _Client(500)
    with pytest.raises(KalshiSeriesLookupError):
        await service.get_series_metadata("KXCFLTOTAL")

    service.client = _Client(200)
    assert await service.get_series_metadata("KXCFLTOTAL") == {"tags": ["Football"]}


# ---------------------------------------------------------------------------
# The rail has no opinions of its own.
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return pathlib.Path(rail.__file__).read_text()


def _code_strings_and_names() -> list[str]:
    """Every string literal and identifier in the module's CODE — not its prose.

    Docstrings and comments are excluded on purpose: this rail's docstring has
    to name the sports it measured in order to be readable, and a guard that
    could not tell prose from behaviour would force the documentation out.
    """
    tree = ast.parse(_module_source())
    out: list[str] = []
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node not in docstrings:
                out.append(node.value)
        elif isinstance(node, ast.Name):
            out.append(node.id)
        elif isinstance(node, ast.Attribute):
            out.append(node.attr)
    return out


def test_the_scan_actually_sees_the_code():
    """Anti-vacuity: the guard below is worthless if its population is empty."""
    found = _code_strings_and_names()
    assert len(found) > 50, f"the AST scan found only {len(found)} nodes"
    assert "llm_sport_category" in found, (
        "the scan must be reaching the rail's real statements"
    )


def test_the_rail_has_no_sport_vocabulary_of_its_own():
    """🔴 The strongest form of the "no second classifier" guard.

    The enumerated siblings can only assert that their ONE target sport word
    appears once, because a target category is a sport word by necessity. This
    rail has no target: it writes whatever the venue's tag resolves to, so it
    can assert the total absence — and that absence is what makes "if this rail
    and the poller disagree, one of them is buggy" a structural claim rather
    than a promise.
    """
    from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY

    vocabulary = set(SPORT_PREFIX_TO_LLM_CATEGORY) | set(
        SPORT_PREFIX_TO_LLM_CATEGORY.values()
    )
    assert len(vocabulary) > 10, "the vocabulary this guard checks against is empty"

    offenders = sorted(
        token
        for token in _code_strings_and_names()
        if token.lower() in vocabulary
    )
    assert offenders == [], (
        f"this rail must not name a sport in its code: {offenders}. It decides "
        "nothing about sport itself — the venue's tag and the shipped cascade do."
    )


def test_the_rail_calls_the_shipped_classifier_and_not_a_copy():
    source = _module_source()
    for symbol in (
        "_categorize_kalshi_market",
        "_resolve_series_tag_result",
        "series_tag_to_category",
    ):
        assert "from app.tasks.kalshi import" in source and symbol in source, (
            f"the rail must ask the shipped {symbol}, never reimplement it"
        )
    # 🔴 Matched on LINES, not as a substring. `"import re" not in source` was
    # the first spelling and it went red on
    # `from app.utils.match_receipts import record_link_change_receipts` — a
    # guard keyed on a substring fires on the import that merely starts with it.
    import_lines = [ln.strip() for ln in source.splitlines() if ln.strip().startswith(("import ", "from "))]
    assert "re.compile" not in source, (
        "a regex over market names here would be a second classifier"
    )
    assert not any(ln == "import re" or ln.startswith("import re ") for ln in import_lines), (
        "this rail must not reach for the regex module"
    )


def test_the_dispatcher_can_actually_call_this_rail():
    """A rail nobody can invoke is not a repair.

    Also pins the param names: FastAPI drops an unknown query param SILENTLY, so
    a rail whose signature names a cursor the dispatcher does not forward pages
    for ever over page one (the Polymarket sibling's Q496 defect 1).
    """
    import importlib
    import inspect

    from app.routes.admin_repairs import _REPAIRS

    entry = _REPAIRS.get("kalshi-series-tag-category")
    assert entry is not None, "the rail is not registered"
    module = importlib.import_module(entry[0])
    fn = getattr(module, entry[1])
    params = inspect.signature(fn).parameters
    assert "apply" in params
    for cursor_param in ("after_date", "after_id"):
        assert cursor_param in params, (
            f"{cursor_param} must be declared or the dispatcher will not forward it"
        )


def test_the_keyset_resumes_the_null_commence_region():
    """The Polymarket sibling's Q496 defect 3, not re-learned here.

    A cursor inside the NULL-`commence_time` region carries `after_date=None`.
    A gate that required a truthy date would never activate, and the next call
    would silently restart at page one.
    """
    assert rail._keyset_after({"after_date": None, "after_id": None}) is None
    assert rail._keyset_after({"after_date": None, "after_id": 5}) is not None, (
        "after_id alone IS a resume — it is the NULL region"
    )
    assert rail._keyset_after({"after_date": "2026-09-12T20:00:00+00:00", "after_id": 5}) is not None


# ---------------------------------------------------------------------------
# CERT-2744's finding — the ghost EVENT arm. The duplicate CARD a reader sees
# is an `events` row; correcting the market's badge does not remove it.
# ---------------------------------------------------------------------------

#: The ghost and its real counterpart, both read off production 2026-09-12.
_GHOST_EVENT_ID = 15308761        # basketball_other, "Ottawa Redblacks vs Toronto Argonauts"
_REAL_EVENT_ID = 15307938         # americanfootball_cfl, the same fixture, teams reversed


async def _plan_with_ghosts(rows, tags, ghosts, monkeypatch, apply=False):
    import app.tasks.kalshi as kalshi_module

    monkeypatch.setattr(kalshi_module, "_resolve_series_tag_result", _TagStub(tags))
    session = _FakeSession(rows, ghosts=ghosts)
    return await rail.repair(session, apply=apply), session


def _redblacks_market():
    return _Row(
        _REDBLACKS_ID, _REDBLACKS_NAME, "kalshi", _REDBLACKS_TICKER, "basketball",
        event_id=_GHOST_EVENT_ID,
    )


@pytest.mark.asyncio
async def test_served_search_returns_one_fixture_after_historical_repair_5637(
    monkeypatch,
):
    """THE TEST CERT-2744 NAMED.

    `q=Redblacks` returns the game twice: the real CFL fixture and a
    `basketball_other` ghost minted from the Kalshi prop. Search serves EVENTS,
    so the second card only disappears when that event row is retired.

    This asserts the decision and the write, against the real shapes: the ghost
    is planned, the retire is a compare-and-set on the status it actually held,
    and the market is unhooked so it can reach the real fixture. The served
    disappearance follows from `status='voided'`, which is the same value
    `repair_5621_phantom_ffpts_events` uses for the same purpose.
    """
    ghost = _GhostRow(
        _GHOST_EVENT_ID, "Ottawa Redblacks", "Toronto Argonauts", "scheduled",
        "basketball_other",
        real_id=_REAL_EVENT_ID, real_key="americanfootball_cfl",
    )
    out, _ = await _plan_with_ghosts(
        [_redblacks_market()],
        {_REDBLACKS_TICKER: _result(tag="Football")},
        [ghost],
        monkeypatch,
    )

    assert len(out["ghost_events_planned"]) == 1, (
        "the duplicate card is an events row — planning only the market leaves "
        "the reader looking at two fixtures"
    )
    plan = out["ghost_events_planned"][0]
    assert plan["event_id"] == _GHOST_EVENT_ID
    assert plan["real_event_id"] == _REAL_EVENT_ID
    assert plan["before_status"] == "scheduled", "the undo must name the real status"
    assert plan["venue_sport"] == "football"
    assert out["ghost_events_retired"] == 0, "a dry run retires nothing"
    assert "scheduled" in out["event_restore_sql"], (
        "the D51 undo for the event arm travels on the dry run too"
    )

    # 🔴 AND THE SERVED HALF, PROVEN RATHER THAN INFERRED. `GET
    # /api/events/search` filters on an ALLOWLIST of statuses, so the retired
    # ghost leaves the results exactly when `RETIRED_STATUS` is absent from it —
    # and the real fixture stays exactly when ITS status is present. Read off the
    # route module, so a change to either list fails here rather than silently
    # making this rail write a value that changes nothing a reader sees.
    from app.routes.events import _SEARCH_STARTED_STATUSES, _SEARCH_STATUSES

    assert "scheduled" in _SEARCH_STATUSES, (
        "control: the survivor's status must be served, or this proves nothing"
    )
    assert rail.RETIRED_STATUS not in _SEARCH_STATUSES, (
        f"search serves {_SEARCH_STATUSES}; retiring a ghost to "
        f"{rail.RETIRED_STATUS!r} would leave the duplicate card on the page"
    )
    assert rail.RETIRED_STATUS not in _SEARCH_STARTED_STATUSES, (
        "the started-only arm of search must not serve it either"
    )


@pytest.mark.asyncio
async def test_a_ghost_with_no_real_counterpart_is_never_retired(monkeypatch):
    """🔴 THE GATE THAT DECIDES WHETHER A READER LOSES A GAME.

    Measured on production 2026-09-12: of 13 candidate ghosts in these families
    only 4 have a counterpart. The other 9 — five NWSL fixtures among them — are
    the ONLY row we hold for that match. Retiring one would not remove a
    duplicate, it would remove the game from the site.
    """
    alone = _GhostRow(
        15308754, "Houston", "Utah Royals", "scheduled", "baseball_other",
        real_id=None,
    )
    out, _ = await _plan_with_ghosts(
        [_Row(1, "Houston vs Utah Royals", "kalshi",
              "KXNWSLGAME-26SEP12HDAURO", "baseball", event_id=15308754)],
        {"KXNWSLGAME-26SEP12HDAURO": _result(tag="Soccer")},
        [alone],
        monkeypatch,
    )
    assert out["ghost_events_planned"] == []
    assert out["ghost_events_refused"] == {"no_real_counterpart": 1}


@pytest.mark.asyncio
async def test_a_counterpart_in_the_wrong_sport_does_not_authorise_a_retire(
    monkeypatch,
):
    """Two teams with those names playing within 36 hours is not enough.

    The counterpart has to be the same fixture PROPERLY FILED — in the sport the
    venue says. A lookalike in another sport proves nothing, and retiring on it
    would delete a real game on the strength of a name collision, which is the
    very family of mistake #5637 is about.
    """
    ghost = _GhostRow(
        _GHOST_EVENT_ID, "Ottawa Redblacks", "Toronto Argonauts", "scheduled",
        "basketball_other",
        real_id=999, real_key="basketball_nba",
    )
    out, _ = await _plan_with_ghosts(
        [_redblacks_market()],
        {_REDBLACKS_TICKER: _result(tag="Football")},
        [ghost],
        monkeypatch,
    )
    assert out["ghost_events_planned"] == []
    assert out["ghost_events_refused"] == {"counterpart_wrong_sport": 1}


@pytest.mark.asyncio
async def test_an_event_already_in_the_right_sport_is_left_alone(monkeypatch):
    """An event we minted, in the RIGHT sport, is not a wrong-sport ghost.

    Several of the 13 candidates are `soccer_other` NWSL fixtures — made by us,
    but correctly sported. Retiring those would be vandalism, and the counterpart
    gate alone would not stop it.
    """
    ghost = _GhostRow(
        15307901, "Kansas City", "Orlando", "scheduled", "soccer_other",
        real_id=12345, real_key="soccer_usa_nwsl",
    )
    out, _ = await _plan_with_ghosts(
        [_Row(2, "Kansas City vs Orlando", "kalshi",
              "KXNWSLGAME-26SEP12KCORL", "tennis", event_id=15307901)],
        {"KXNWSLGAME-26SEP12KCORL": _result(tag="Soccer")},
        [ghost],
        monkeypatch,
    )
    assert out["ghost_events_planned"] == []
    assert out["ghost_events_refused"] == {"event_already_right_sport": 1}


@pytest.mark.asyncio
async def test_an_ingested_event_never_reaches_the_event_arm(monkeypatch):
    """Gate 1 lives in SQL, so its refusal is an ABSENCE from the result set.

    An absence is exactly the shape that reads as "nothing to do" (gotcha #53),
    so the arm counts the ids the query did not return under their own name
    rather than inferring a shortfall.
    """
    out, _ = await _plan_with_ghosts(
        [_redblacks_market()],
        {_REDBLACKS_TICKER: _result(tag="Football")},
        [],  # the SQL returned nothing: this event is ingested, not ours
        monkeypatch,
    )
    assert out["ghost_events_planned"] == []
    assert out["ghost_events_refused"] == {"event_not_ours_to_retire": 1}


@pytest.mark.asyncio
async def test_the_event_arm_is_only_asked_about_events_it_has_a_verdict_for(
    monkeypatch,
):
    """The ghost query is bounded by the ids this pass planned, never open-ended.

    A rail that scanned `events` freely would be a different, far larger ship
    than #5637, and its blast radius would not be the population anyone measured.
    """
    out, session = await _plan_with_ghosts(
        [_redblacks_market()],
        {_REDBLACKS_TICKER: _result(tag="Football")},
        [],
        monkeypatch,
    )
    assert session.ghost_query_args == {"event_ids": [_GHOST_EVENT_ID]}


def test_the_event_arm_has_a_ceiling_and_refuses_rather_than_trimming():
    """A sudden crowd is a reason to stop, not a reason to retire 60 of them."""
    assert rail.MAX_EXPECTED_GHOST_EVENTS >= 13, (
        "the ceiling must clear the measured population or the arm never runs"
    )
    assert rail.MAX_EXPECTED_GHOST_EVENTS <= 200, (
        "a ceiling that clears any plausible crowd is not a ceiling"
    )


def test_the_event_undo_names_the_status_each_row_actually_held():
    """One statement per distinct prior status, and never a Python repr."""
    sql = rail.event_restore_sql(
        [
            {"event_id": 2, "before_status": "scheduled"},
            {"event_id": 1, "before_status": "scheduled"},
            {"event_id": 3, "before_status": None},
        ]
    )
    assert "UPDATE events SET status = 'scheduled' WHERE id IN (1, 2);" in sql
    assert "UPDATE events SET status = NULL WHERE id IN (3);" in sql
    assert "{" not in sql, "a dict in the undo is the senate sibling's first bug"


def test_the_undo_restores_only_the_rows_the_write_actually_matched():
    """CERT-2744 follow-up `5637-RESTORE-ONLY-CAS-MATCHED-ROWS`.

    A drifted row's planned `before` is a value the database no longer holds, so
    restoring it would write a STALE sport onto a row the rail deliberately left
    alone. An undo that corrupts a row the repair refused to touch is worse than
    no undo.
    """
    planned = [
        {"id": 1, "before": "basketball"},
        {"id": 2, "before": "tennis"},   # drifted: never written
    ]
    applied = [{"id": 1, "before": "basketball"}]

    assert "tennis" in rail.restore_sql(planned), "control: the plan does name it"
    undo = rail.restore_sql(applied)
    assert "tennis" not in undo, (
        "restoring a row the compare-and-set refused would overwrite whatever "
        "the other writer put there"
    )
    assert undo == "UPDATE futures_markets SET llm_sport_category = 'basketball' WHERE id IN (1);"


class _ApplySession(_FakeSession):
    """Runs the APPLY half, and lets a row DRIFT.

    🔴 This class exists because of a survivor. `test_the_undo_restores_only_the
    _rows_the_write_actually_matched` calls `restore_sql` directly, so swapping
    the payload back to `restore_sql(planned)` left it green — the guard proved
    the helper and never proved the WIRING. Only an apply that reaches the
    payload can catch that.

    `matched_ids` is what the compare-and-set is pretended to have matched;
    anything planned and absent from it is a row another writer moved.
    """

    def __init__(self, rows, matched_ids, ghosts=()):
        super().__init__(rows, ghosts=ghosts)
        self._matched = set(matched_ids)
        self.committed = 0
        self.market_unhooks = 0
        self.unhooked_event_ids = None

    async def execute(self, statement, params=None):
        visit = getattr(statement, "__visit_name__", None)
        if visit == "update":
            table = statement.table.name
            if table == "futures_markets" and not statement._returning:
                self.market_unhooks += 1
                # 🔴 Record WHICH events the unhook targeted, not merely that it
                # ran. Asserting the call count alone left `retired_ids = []`
                # green — the statement still executes, against nothing.
                self.unhooked_event_ids = sorted(
                    statement.compile().params.get("event_id_1") or []
                )

                class _Empty:
                    rowcount = 0

                    def fetchall(self):
                        return []

                return _Empty()
            # Return the intersection of THIS statement's targets with the
            # matched set. Returning the whole matched set for every group made
            # the compare-and-set look like it matched the same id twice —
            # `changed` read 2 for one row, and the fake, not the rail, was
            # wrong.
            targeted = set(statement.compile().params.get("id_1") or [])
            hit = sorted(targeted & self._matched)

            class _Written:
                rowcount = len(hit)

                def fetchall(self):
                    return [(i,) for i in hit]

            return _Written()
        return await super().execute(statement, params)

    async def commit(self):
        self.committed += 1


@pytest.mark.asyncio
async def test_the_payload_undo_is_built_from_the_matched_rows_not_the_plan(
    monkeypatch,
):
    """The wiring half of `5637-RESTORE-ONLY-CAS-MATCHED-ROWS`.

    Two rows planned, one drifts. The returned `restore_sql` must name only the
    row that actually moved — the drifted one's `before` is a value the database
    no longer holds, and writing it back would corrupt a row this rail refused
    to touch.
    """
    import app.tasks.kalshi as kalshi_module

    rows = [
        _Row(_REDBLACKS_ID, _REDBLACKS_NAME, "kalshi", _REDBLACKS_TICKER, "basketball"),
        _Row(_WIMBLEDON_ID, _WIMBLEDON_NAME, "kalshi", _WIMBLEDON_TICKER, "tennis"),
    ]
    monkeypatch.setattr(
        kalshi_module,
        "_resolve_series_tag_result",
        _TagStub(
            {
                _REDBLACKS_TICKER: _result(tag="Football"),
                _WIMBLEDON_TICKER: _result(tag="Soccer"),
            }
        ),
    )
    # Only the Redblacks row matches; the Wimbledon row drifted.
    session = _ApplySession(rows, matched_ids=[_REDBLACKS_ID])
    out = await rail.repair(session, apply=True)

    assert out["changed"] == 1
    assert [r["id"] for r in out["applied_rows"]] == [_REDBLACKS_ID]
    assert "basketball" in out["restore_sql"]
    assert "tennis" not in out["restore_sql"], (
        "🔴 the drifted row must not appear in the undo — its planned `before` "
        "is not what the database holds"
    )
    assert out["drifted"], "a plan/write shortfall is never unexplained"
    assert out["drifted"][0]["skipped_ids"] == [_WIMBLEDON_ID]
    assert session.committed == 1


@pytest.mark.asyncio
async def test_the_event_undo_is_also_built_from_the_matched_rows(monkeypatch):
    """Same rule, the other table — and the unhook only touches retired events."""
    import app.tasks.kalshi as kalshi_module

    monkeypatch.setattr(
        kalshi_module,
        "_resolve_series_tag_result",
        _TagStub({_REDBLACKS_TICKER: _result(tag="Football")}),
    )
    ghost = _GhostRow(
        _GHOST_EVENT_ID, "Ottawa Redblacks", "Toronto Argonauts", "scheduled",
        "basketball_other",
        real_id=_REAL_EVENT_ID, real_key="americanfootball_cfl",
    )
    receipts = []

    async def _fake_receipt(market_rows, **kwargs):
        receipts.append((market_rows, kwargs))
        return len(market_rows)

    monkeypatch.setattr(rail, "_record_link_change", _fake_receipt)

    session = _ApplySession(
        [_redblacks_market()], matched_ids=[_REDBLACKS_ID, _GHOST_EVENT_ID],
        ghosts=[ghost],
    )
    out = await rail.repair(session, apply=True)

    assert out["ghost_events_retired"] >= 1
    assert "scheduled" in out["event_restore_sql"]
    assert session.market_unhooks == 1, (
        "the markets on a retired event must be unhooked, or gotcha #15 keeps "
        "the prop pinned to the voided row forever"
    )
    assert session.unhooked_event_ids == [_GHOST_EVENT_ID], (
        "the unhook must name the events actually retired — an UPDATE against "
        "an empty id list runs, reports nothing, and frees no market"
    )
    # LINKLOSS-03: clearing `event_id` without receipting it leaves the price
    # gone from a card with no explanation anywhere in the system. CI's
    # `test_every_unlink_writer_in_the_app_records_a_link_change` caught this
    # one; the assertion below is so THIS file catches the next one.
    assert len(receipts) == 1, "every retired event owes exactly one link-change receipt"
    rows, kwargs = receipts[0]
    assert kwargs["previous_event_id"] == _GHOST_EVENT_ID
    assert kwargs["new_event_id"] is None
    assert [r["id"] for r in rows] == [_REDBLACKS_ID], (
        "the receipt names the markets read BEFORE the update — the previous "
        "event id does not survive it"
    )


@pytest.mark.asyncio
async def test_a_drifted_event_is_left_out_of_the_event_undo(monkeypatch):
    """The event arm's half of `5637-RESTORE-ONLY-CAS-MATCHED-ROWS`.

    Two ghosts planned, one drifts (somebody moved its status between the scan
    and the write). The event undo must name only the one that moved — writing
    `scheduled` back onto an event another writer just completed would undo
    THEIR work, not ours.

    Without this the mutation "build the event undo from `ghost_planned`"
    survives, because in the happy path planned and applied are the same list.
    """
    import app.tasks.kalshi as kalshi_module

    monkeypatch.setattr(
        kalshi_module,
        "_resolve_series_tag_result",
        _TagStub(
            {
                _REDBLACKS_TICKER: _result(tag="Football"),
                _WIMBLEDON_TICKER: _result(tag="Soccer"),
            }
        ),
    )
    drifted_event_id = 15307874
    ghosts = [
        _GhostRow(
            _GHOST_EVENT_ID, "Ottawa Redblacks", "Toronto Argonauts", "scheduled",
            "basketball_other",
            real_id=_REAL_EVENT_ID, real_key="americanfootball_cfl",
        ),
        _GhostRow(
            drifted_event_id, "Wimbledon", "Doncaster", "postponed", "tennis_other",
            real_id=15305089, real_key="soccer_england_league1",
        ),
    ]
    rows = [
        _redblacks_market(),
        _Row(_WIMBLEDON_ID, _WIMBLEDON_NAME, "kalshi", _WIMBLEDON_TICKER, "tennis",
             event_id=drifted_event_id),
    ]
    async def _fake_receipt(market_rows, **kwargs):
        return len(market_rows)

    monkeypatch.setattr(rail, "_record_link_change", _fake_receipt)

    # Everything matches EXCEPT the postponed ghost.
    session = _ApplySession(
        rows,
        matched_ids=[_REDBLACKS_ID, _WIMBLEDON_ID, _GHOST_EVENT_ID],
        ghosts=ghosts,
    )
    out = await rail.repair(session, apply=True)

    assert out["ghost_events_retired"] == 1
    assert "scheduled" in out["event_restore_sql"]
    assert "postponed" not in out["event_restore_sql"], (
        "🔴 the drifted event must not appear in the undo — restoring a status "
        "the row no longer holds overwrites whoever moved it"
    )
    assert out["ghost_events_drifted"], "an event shortfall is never unexplained"
    assert out["ghost_events_drifted"][0]["skipped_ids"] == [drifted_event_id]
    assert session.unhooked_event_ids == [_GHOST_EVENT_ID], (
        "only the retired event's markets are unhooked; the drifted event's "
        "market stays attached to a row that is still live"
    )


@pytest.mark.asyncio
async def test_a_crowd_of_ghosts_refuses_the_arm_instead_of_retiring_them(
    monkeypatch,
):
    """The ceiling is a REFUSAL, not a trim.

    Measured population was 13 candidates / 4 retirable. If this predicate ever
    matches a crowd, something upstream changed and a person should look before
    games start vanishing from the site — so the arm writes NOTHING and says
    why, rather than retiring the first `MAX_EXPECTED_GHOST_EVENTS` of them.

    Asserting the constant's value alone left "ignore the ceiling" green; this
    is the behaviour.
    """
    import app.tasks.kalshi as kalshi_module

    over = rail.MAX_EXPECTED_GHOST_EVENTS + 1
    tickers = {f"KXCFLTOTAL-26SEP12X{i:03d}": _result(tag="Football") for i in range(over)}
    monkeypatch.setattr(
        kalshi_module, "_resolve_series_tag_result", _TagStub(tickers)
    )
    rows = [
        _Row(1000 + i, f"A{i} vs B{i}", "kalshi", t, "basketball", event_id=2000 + i)
        for i, t in enumerate(tickers)
    ]
    ghosts = [
        _GhostRow(
            2000 + i, f"A{i}", f"B{i}", "scheduled", "basketball_other",
            real_id=3000 + i, real_key="americanfootball_cfl",
        )
        for i in range(over)
    ]
    async def _fake_receipt(market_rows, **kwargs):  # never reached over the ceiling
        raise AssertionError("nothing is unhooked when the ceiling refuses")

    monkeypatch.setattr(rail, "_record_link_change", _fake_receipt)
    session = _ApplySession(
        rows, matched_ids=[r.id for r in rows] + [g.id for g in ghosts], ghosts=ghosts
    )
    out = await rail.repair(session, apply=True)

    assert out["ghost_events_over_ceiling"] is True
    assert len(out["ghost_events_planned"]) == over, (
        "the plan is still reported in full — an operator needs to SEE the crowd"
    )
    assert out["ghost_events_retired"] == 0, (
        "🔴 nothing is retired over the ceiling, and nothing is trimmed to fit"
    )
    assert session.unhooked_event_ids is None, "no market is unhooked either"
