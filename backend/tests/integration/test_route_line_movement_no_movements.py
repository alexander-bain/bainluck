"""Contract guards for ``GET /api/events/{id}/line-movement`` (latency/133).

Two defects on this one handler, both found by measuring production rather
than by reading the code:

1. **A flat market 500s.** ``team_stats`` was bound only inside the handler's
   ``if analysis.movements:`` block by the #871 evidence-gate refactor
   (2026-08-17), but ``context_meta`` reads it unconditionally. An event whose
   odds never moved enough to register a movement therefore skipped the
   binding and died on ``UnboundLocalError`` (Sentry BAINLUCK-MS) — a plain
   ``text/plain`` 500, no cache row written, so it recurred on every view.
   Measured 2026-09-03 against production: 2 of 20 recent completed events
   (both tennis, both with 0 detected movements) returned 500. This is gotcha
   #7's shape: a name that only exists down one branch.

2. **A synchronous LLM call parked the event loop.** The disagreement branch
   called the *sync* ``generate_market_disagreement_explanation`` from inside
   an async handler with a 30s OpenAI client timeout — blocking the loop, not
   just the request. It fired on every cache miss: ``disagreement_data`` is
   set on 264/264 rows ever written to ``line_movement_analyses`` and
   ``disagreement_explanation`` on 0 of them.

The first test is the red-first arm for (1): it exercises the real handler
through the real router, and fails with a 500 if ``team_stats`` moves back
inside the conditional. The second is its control — the same fixture with a
market that DID move — so a green in the first arm cannot be the harness
declining to reach the handler at all.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import routes as app_routes
from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw


# ── Fixtures ───────────────────────────────────────────────────────────


def _make_event(*, event_id: int = 4242, opening_prob: float = 0.95):
    """A completed tennis event shaped like the two that 500'd in production.

    ``espn_id`` is None on purpose: this guard is about the handler's own
    branch structure, and no test should reach out to ESPN.
    """
    event = MagicMock()
    event.id = event_id
    event.status = "completed"
    event.espn_id = None
    event.home_team_name = "Iga Swiatek"
    event.away_team_name = "Nadia Podoroska"
    event.home_score = 2
    event.away_score = 0
    event.period = None
    event.game_clock = None
    event.opening_home_probability = opening_prob
    event.win_probability_sources = {}
    event.box_score_data = None
    event.commence_time = datetime(2026, 9, 3, 15, 4, tzinfo=timezone.utc)
    event.sport = MagicMock()
    event.sport.key = "tennis_wta_us_open"
    return event


def _make_snapshots(probs: list[float]):
    """Odds snapshots one minute apart, one bookmaker each."""
    base = datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc)
    snaps = []
    for i, p in enumerate(probs):
        snap = MagicMock()
        snap.captured_at = base + timedelta(minutes=i)
        snap.home_win_probability = p
        snaps.append(snap)
    return snaps


def _make_session(*, event, snapshots):
    """Mock session that dispatches on the table each SELECT reads from.

    Everything other than ``events`` and ``odds_snapshots`` comes back empty —
    in particular ``line_movement_analyses``, so every request is a cache miss
    and runs the full build path (which is where both defects live).
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    def _result(*, scalar=None, scalar_rows=()):
        res = MagicMock()
        res.scalar_one_or_none.return_value = scalar
        res.scalar.return_value = scalar
        res.scalars.return_value.all.return_value = list(scalar_rows)
        res.scalars.return_value.first.return_value = (
            list(scalar_rows)[0] if scalar_rows else None
        )
        res.scalars.return_value.unique.return_value.all.return_value = list(scalar_rows)
        res.all.return_value = []
        res.fetchall.return_value = []
        res.first.return_value = None
        return res

    async def mock_execute(stmt, *args, **kwargs):
        sql = str(stmt).lower()
        # Most specific table names first — "events" is a substring of nothing
        # here, but odds_snapshots and win_prob_snapshots both end in
        # "snapshots", so match on the full name.
        if "line_movement_analyses" in sql:
            return _result(scalar=None)
        if "odds_snapshots" in sql:
            return _result(scalar_rows=snapshots)
        if "win_prob_snapshots" in sql:
            return _result(scalar_rows=())
        if "scoring_plays" in sql:
            return _result(scalar_rows=())
        if "teams" in sql:
            return _result(scalar_rows=())
        if "events" in sql:
            return _result(scalar=event)
        return _result()

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


async def _get_line_movement(session, event_id: int):
    """Drive the real route through the real app with ``session`` behind it."""
    from app.main import app

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                return await ac.get(f"/api/events/{event_id}/line-movement")
    finally:
        app.dependency_overrides.clear()


# ── The ship: a flat market renders instead of 500ing ──────────────────


@pytest.mark.asyncio
async def test_event_with_no_detected_movements_returns_200_not_500():
    """RED-FIRST arm. A market that never moved must render an empty panel.

    Before the fix this raised ``UnboundLocalError: cannot access local
    variable 'team_stats'`` and Starlette returned a text/plain 500.
    """
    event = _make_event()
    # Dead flat: nothing clears SIGNIFICANT_MOVE_THRESHOLD, so
    # detect_line_movements returns zero movements and the handler skips the
    # whole `if analysis.movements:` block.
    session = _make_session(event=event, snapshots=_make_snapshots([0.95] * 40))

    resp = await _get_line_movement(session, event.id)

    assert resp.status_code == 200, (
        f"flat market 500'd: {resp.status_code} "
        f"{resp.headers.get('content-type')} {resp.text[:200]}"
    )
    body = resp.json()
    assert body["movements"] == []
    # context_meta is the dict that read the unbound name — it must be built.
    assert body["context"] is not None
    assert body["context"]["has_team_stats"] is False
    assert body["context"]["injuries_count"] == 0
    assert body["explanation"] is None


@pytest.mark.asyncio
async def test_event_with_detected_movements_still_returns_200():
    """CONTROL arm. The same fixture on the moving path.

    Without this, a green above could mean the request never reached the
    handler (a 404 from a mis-shaped mock would also 'not 500').
    """
    event = _make_event(event_id=4243, opening_prob=0.50)
    # A large, sustained swing — comfortably over the significance threshold.
    probs = [0.50] * 5 + [0.62] * 5 + [0.75] * 5 + [0.88] * 5
    session = _make_session(event=event, snapshots=_make_snapshots(probs))

    resp = await _get_line_movement(session, event.id)

    assert resp.status_code == 200, resp.text[:200]
    body = resp.json()
    assert body["movements"], "control arm detected no movement — fixture is inert"
    assert body["context"] is not None


# ── No synchronous LLM call on the request path ────────────────────────


_BLOCKING_LLM_HELPERS = frozenset({"generate_market_disagreement_explanation"})


def _blocking_llm_calls(source: str) -> list[str]:
    """Names in ``_BLOCKING_LLM_HELPERS`` that ``source`` actually CALLS.

    AST, not regex: a mention in a comment or a docstring explaining why the
    call was removed is not a call, and a guard that cannot tell the two apart
    goes red on its own rationale.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (
            fn.id if isinstance(fn, ast.Name)
            else fn.attr if isinstance(fn, ast.Attribute)
            else None
        )
        if name in _BLOCKING_LLM_HELPERS:
            found.append(name)
    return found


def test_no_sync_llm_call_on_the_line_movement_request_path():
    """``app/routes/events.py`` must not CALL the sync disagreement generator.

    It is a blocking OpenAI request (30s client timeout) and the handler is
    async, so invoking it parks the event loop for every concurrent request on
    the dyno — not just this one. The helper itself stays; calling it from a
    request handler is the defect.
    """
    from app.routes import events as events_module

    hits = _blocking_llm_calls(inspect.getsource(events_module))
    assert not hits, (
        f"app/routes/events.py calls {sorted(set(hits))} on a request path — "
        "synchronous OpenAI calls block the event loop"
    )


def test_blocking_llm_call_scan_catches_a_planted_call():
    """CONTROL. The checker must go red on a call it is supposed to catch.

    Plants the exact shape that shipped — including the from-import and the
    surrounding try/except that made it look handled — and requires a hit.
    Without this, a checker that silently parses nothing stays green forever.
    """
    planted = (
        "async def handler(event):\n"
        "    try:\n"
        "        from app.services.llm import "
        "generate_market_disagreement_explanation\n"
        "        return generate_market_disagreement_explanation(home_team='a')\n"
        "    except Exception:\n"
        "        return None\n"
    )
    assert _blocking_llm_calls(planted) == [
        "generate_market_disagreement_explanation"
    ], "checker missed a planted blocking call — the route scan is vacuous"

    # And the inverse: a mere mention must NOT trip it, or the guard would
    # forbid its own explanation.
    mention_only = (
        "# do not call generate_market_disagreement_explanation() here\n"
        "X = 'generate_market_disagreement_explanation('\n"
    )
    assert _blocking_llm_calls(mention_only) == []


# ── The same rule, widened to EVERY route module ───────────────────────
#
# CERT-868's named follow-up (`LATENCY-133-BLOCKING-CALL-GUARD-SCOPE`): the guard
# above names one helper in one file, so it could only ever catch the defect that
# had already been fixed. #3322 then found the same class in `routes/oscars.py`
# — six calls, 10.83s on production — which the narrow guard was structurally
# incapable of seeing. Widened here, with the oscars fix, rather than landed with
# those call sites as a tracked exemption: after that fix there is nothing to
# exempt.

# Cheap enough to call from anywhere: a null-check on the module-global client
# that issues no request. It is the ONLY exemption, and it is behavioural, not
# historical — nothing is on this list because it is inconvenient to fix.
_NON_BLOCKING_LLM_HELPERS = frozenset({"is_available"})

# Operator-triggered batch enrichment, whose whole purpose is to run the LLM over
# rows — a different shape of caller from a page request, and a different fix
# (#4068). They are exempt BY NAME so that a sync LLM call appearing in any other
# route module still fails today, and the exemption is self-retiring: the control
# below requires each of these to still contain a hit, so whoever fixes #4068 is
# made to delete the entry rather than leave a permanent hole behind.
_BATCH_ENRICHMENT_MODULES = frozenset({"admin_providers.py", "admin_taxonomy.py"})


def _sync_llm_entry_points() -> frozenset[str]:
    """Every public synchronous helper `app/services/llm.py` exposes.

    DERIVED, never listed: a literal set would cover the helpers that existed the
    day it was written, which is exactly how the narrow guard missed oscars. A new
    blocking helper is covered by this the moment it is defined.
    """
    from app.services import llm as llm_module

    tree = ast.parse(inspect.getsource(llm_module))
    return frozenset(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)  # `async def` is an AsyncFunctionDef
        and not node.name.startswith("_")
        and node.name not in _NON_BLOCKING_LLM_HELPERS
    )


def _sync_llm_calls_in_async_bodies(source: str, names) -> list[tuple[str, str]]:
    """`(async function, helper)` for each blocking call reachable in an async def.

    Scoped to async bodies, per CERT-868: the helpers are synchronous by design and
    calling one from a task or a sync path is correct. Parking the event loop is
    the defect, so an async body is where the defect lives. Nested `def`s inside an
    async function are walked too — wrapping the call in a closure does not unpark
    the loop when the closure is awaited.
    """
    hits: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            fn = inner.func
            name = (
                fn.id if isinstance(fn, ast.Name)
                else fn.attr if isinstance(fn, ast.Attribute)
                else None
            )
            if name in names:
                hits.append((node.name, name))
    return hits


def test_no_route_module_calls_a_sync_llm_helper_from_an_async_handler():
    """No `app/routes/*.py` may CALL a synchronous llm.py helper in an async def.

    `app/services/llm.py` is synchronous end to end — 35 of 35 helpers — so any of
    them invoked from an async handler blocks the event loop, and the cost is paid
    by every concurrent request on the worker process, not just the one that asked.
    Generation belongs on a task that writes where the request can read it
    (`app/tasks/oscars_previews.py` is the worked example).
    """
    routes_dir = Path(inspect.getsourcefile(app_routes)).parent
    names = _sync_llm_entry_points()
    assert names, "derived an EMPTY helper set — the scan would be vacuous"

    offenders: dict[str, list[tuple[str, str]]] = {}
    for path in sorted(routes_dir.glob("*.py")):
        if path.name in _BATCH_ENRICHMENT_MODULES:
            continue
        hits = _sync_llm_calls_in_async_bodies(path.read_text(), names)
        if hits:
            offenders[path.name] = sorted(set(hits))

    assert not offenders, (
        "synchronous OpenAI calls on an async request path: "
        + "; ".join(
            f"{mod} ({', '.join(f'{fn}() in {where}()' for where, fn in hits)})"
            for mod, hits in sorted(offenders.items())
        )
        + " — move generation to a task and read its result (#3322, CERT-868)"
    )


def test_the_batch_enrichment_exemption_retires_itself():
    """Every exempt module must STILL have a hit, or the exemption must go.

    A denylist of known-unknowns hands the claim to the first new state: left
    alone, this one would keep excusing `admin_taxonomy.py` long after #4068 is
    fixed, and would silently cover a *new* blocking call added to it. So the
    exemption is only valid while it is load-bearing — fix #4068 and this test
    goes red until the module's name is deleted from `_BATCH_ENRICHMENT_MODULES`.
    """
    routes_dir = Path(inspect.getsourcefile(app_routes)).parent
    names = _sync_llm_entry_points()

    for module in sorted(_BATCH_ENRICHMENT_MODULES):
        path = routes_dir / module
        assert path.exists(), (
            f"{module} is exempted but no longer exists — drop it from "
            "_BATCH_ENRICHMENT_MODULES"
        )
        assert _sync_llm_calls_in_async_bodies(path.read_text(), names), (
            f"{module} no longer calls a sync LLM helper from an async handler — "
            "#4068 is fixed, so remove it from _BATCH_ENRICHMENT_MODULES and let "
            "the guard cover it"
        )


def test_the_widened_scan_is_not_vacuous():
    """CONTROL, three ways — the widening's own three failure modes.

    A derived-set guard can go quietly vacuous where a literal one cannot, so this
    pins each way it could: an empty set, a scope that misses async bodies, and an
    exemption that swallows a real helper.
    """
    names = _sync_llm_entry_points()

    # 1. The derivation actually finds the known blocking helpers, including the
    #    two the oscars route used to call.
    for expected in (
        "generate_market_disagreement_explanation",
        "generate_oscars_category_preview",
        "generate_oscars_movers_summary",
    ):
        assert expected in names, f"derivation lost {expected} — the scan is narrower than it reads"

    # ...and does NOT sweep in the cheap null-check, or every route goes red for
    # asking whether the LLM is configured at all.
    assert "is_available" not in names

    # 2. A planted call inside an async def is caught, and attributed.
    planted = (
        "async def get_thing(db):\n"
        "    from app.services.llm import generate_oscars_category_preview\n"
        "    return generate_oscars_category_preview('Best Picture', [])\n"
    )
    assert _sync_llm_calls_in_async_bodies(planted, names) == [
        ("get_thing", "generate_oscars_category_preview")
    ], "the widened scan missed a planted async-path call"

    # 3. The same call in a SYNC body is not a finding: these helpers are meant to
    #    be called, just not from the loop. A guard that forbade them everywhere
    #    would forbid the task this issue's fix depends on.
    sync_body = (
        "def build_it():\n"
        "    return generate_oscars_category_preview('Best Picture', [])\n"
    )
    assert _sync_llm_calls_in_async_bodies(sync_body, names) == []
