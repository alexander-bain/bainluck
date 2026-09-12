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
    ):
        self.id = id
        self.name = name
        self.source = source
        self.external_id = external_id
        self.llm_sport_category = llm_sport_category
        self.commence_time = commence_time


class _FakeSession:
    """Enough session to run the PLAN half. It refuses to write.

    The rail issues two statements: the population SELECT and a `count()` for
    the remaining floor. Both are selects, so "any select after the first is the
    count" is sufficient here and keeps the fake honest about ordering.
    """

    def __init__(self, rows):
        self._rows = rows
        self._select_calls = 0
        self.writes = 0

    async def execute(self, statement):
        if getattr(statement, "__visit_name__", None) != "select":
            self.writes += 1
            raise AssertionError(
                "the plan half issued a write — `apply=False` must never reach "
                "the UPDATE"
            )
        self._select_calls += 1
        rows = self._rows
        first = self._select_calls == 1

        class _Result:
            def all(self):
                return rows

            def scalar_one(self):
                assert not first, "the population SELECT is not the count"
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
    assert "re.compile" not in source and "import re" not in source, (
        "a regex over market names here would be a second classifier"
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
