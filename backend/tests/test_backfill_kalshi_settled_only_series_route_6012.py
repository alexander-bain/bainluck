"""`POST /api/admin/backfill-kalshi-settled` can pin the scan to a series — #227 Item 2.

## The block this repairs

`backfill_kalshi_settled` Phase 1 is the only writer that can lift a Kalshi
market out of `status='open'` when the venue has already settled it (gotcha #33):
it is keyed on the leg ticker, carries no date band and no `JOIN events`, so it
reaches rows the calibration sweep structurally cannot (the 485 markets with
`event_id IS NULL` that #5596 documents at its line 253 as "NOT this ship").

It had not reached the US Open men's champion (`KXATP-26USO`) because of
arithmetic, not a race. The #230 de-starvation boost is
`[s for s in non_priority if s in partial_settled][:boost_cap]` with
`boost_cap = 40`, and `SERIES_PREFIXES` comes off a `GROUP BY 1 ORDER BY 1`, so
the boost is the alphabetically-first 40 of (measured 2026-09-14) 1,093
candidates. `KXATP` sorts 53rd and is truncated out of *every* run; the fallback
cursor rotation is `window=100` over ~6,736 prefixes, i.e. ~67 runs at 4 runs/day
— about 17 days. (`KXATPWTA`, the exacta, holds one open market with no resolved
sibling, so `has_resolved` is false and no boost ordering can ever reach it.)

The task has accepted `only_series` since #227 Item 2 precisely for this — it
bypasses both the cap and the cursor — but **no route passed it**, so the
documented remedy was unreachable from the API and needed an attended
`heroku run` one-off. This suite pins the pass-through.

## Why the duplicate route had to go with it

The path had TWO `@router.post("/backfill-kalshi-settled")` handlers. The first
(line ~1956) served every request, because Starlette matches in registration
order — but the duplicate was not inert: FastAPI builds the OpenAPI dict by
iterating all routes, so the LATER one won the schema and `/docs` rendered a
signature nobody could reach. Adding `only_series` to the live handler while the
shadow stood would have left it invisible in `/docs` to the one operator who
needs it. `test_exactly_one_route_is_registered` and
`test_openapi_advertises_only_series` are that pair, and they fail in both
directions: a re-added shadow reddens the first, a shadow that wins the schema
again reddens the second.

Both directions are asserted throughout (gotcha #43): every "targeting works"
test has a sibling proving the **scheduled** sweep's dispatch is byte-identical
to what it was, so "just always pass only_series" cannot pass this file.
"""
import pytest
from fastapi.testclient import TestClient

import app.routes.admin_data_quality as adq
from app.main import app

ADMIN_TOKEN = "only-series-route-6012"
PATH = "/api/admin/backfill-kalshi-settled"
TASK = "app.tasks.backfill_kalshi_settled"

#: The untargeted dispatch carries this key set and no other. Asserted as a SHAPE
#: rather than as `{"limit": 5000}`, because the literal would be a second copy of
#: the route's own default and would false-red the day someone legitimately
#: retunes it — while still failing, as it must, on any run that adds an
#: `only_series` key in ANY form (including an explicit `None`, which is a
#: behaviour change for the 4x daily beat).
SCHEDULED_KWARG_KEYS = {"limit"}


class _FakeResult:
    id = "task-id-6012"


@pytest.fixture
def dispatched(monkeypatch):
    """Capture the Celery dispatch instead of sending it.

    The route is a settlement trigger; the thing under test is exactly what it
    hands the broker, so the fake records the call rather than asserting on a
    response body that cannot distinguish the two code paths.
    """
    calls = []

    def _fake(name, args=None, kwargs=None, queue=None):
        calls.append({"name": name, "args": args, "kwargs": kwargs, "queue": queue})
        return _FakeResult()

    monkeypatch.setattr(adq, "_safe_send_task", _fake)
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    return calls


@pytest.fixture
def client():
    return TestClient(app)


def _post(client, query=""):
    """Authenticate the way an operator must: `Authorization: Bearer` only.

    Queue #252 Item 3 removed the `?secret=` path, so a test that supplied the
    token in the URL would exercise a path no caller can use.
    """
    return client.post(
        f"{PATH}{query}", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
    )


# --------------------------------------------------------------------------
# The ship: only_series reaches the task
# --------------------------------------------------------------------------

def test_only_series_reaches_the_task_kwargs(client, dispatched):
    r = _post(client, "?only_series=KXATP&only_series=KXATPWTA")
    assert r.status_code == 200, r.text
    assert len(dispatched) == 1
    call = dispatched[0]
    assert call["name"] == TASK
    assert call["kwargs"]["only_series"] == ["KXATP", "KXATPWTA"]


def test_a_single_series_is_still_a_list(client, dispatched):
    """The task signature is `only_series: list[str] | None`; a lone value that
    arrived as a bare string would be iterated CHARACTERWISE by the task's
    `tuple(s.strip().upper() for s in only_series)` and pin the scan to 'K'."""
    _post(client, "?only_series=KXATP")
    assert dispatched[0]["kwargs"]["only_series"] == ["KXATP"]


def test_targeted_run_still_routes_to_the_background_queue(client, dispatched):
    """The surviving handler is the one that names its queue. The shadow did not,
    so this also proves the deletion kept the right one of the two."""
    _post(client, "?only_series=KXATP")
    assert dispatched[0]["queue"] == "background"


def test_limit_still_travels_alongside_only_series(client, dispatched):
    _post(client, "?limit=42&only_series=KXATP")
    assert dispatched[0]["kwargs"] == {"limit": 42, "only_series": ["KXATP"]}


def test_response_echoes_the_targeting_so_the_operator_can_verify_it(client, dispatched):
    r = _post(client, "?only_series=KXATP")
    assert r.json()["only_series"] == ["KXATP"]


# --------------------------------------------------------------------------
# The other direction: the scheduled sweep is untouched (gotcha #43)
# --------------------------------------------------------------------------

def test_omitting_only_series_dispatches_the_scheduled_kwargs_exactly(client, dispatched):
    """No `only_series` key at all — not `None`, not `[]`. The 4x daily beat and
    every existing caller must see the dispatch they see today."""
    r = _post(client)
    assert r.status_code == 200, r.text
    assert set(dispatched[0]["kwargs"]) == SCHEDULED_KWARG_KEYS
    assert "only_series" not in dispatched[0]["kwargs"]


def test_blank_only_series_degrades_to_the_full_sweep(client, dispatched):
    """`?only_series=` must not become "pin the scan to nothing". Blanks are
    dropped, and an all-blank value leaves the scheduled dispatch."""
    _post(client, "?only_series=&only_series=%20%20")
    assert set(dispatched[0]["kwargs"]) == SCHEDULED_KWARG_KEYS


def test_blanks_are_dropped_but_real_prefixes_survive(client, dispatched):
    _post(client, "?only_series=&only_series=KXATP")
    assert dispatched[0]["kwargs"]["only_series"] == ["KXATP"]


def test_surrounding_whitespace_is_stripped(client, dispatched):
    _post(client, "?only_series=%20KXATP%20")
    assert dispatched[0]["kwargs"]["only_series"] == ["KXATP"]


def test_response_reports_none_when_untargeted(client, dispatched):
    assert _post(client).json()["only_series"] is None


# --------------------------------------------------------------------------
# The duplicate route
# --------------------------------------------------------------------------

def _routes_for_path():
    return [r for r in app.routes if getattr(r, "path", "") == PATH]


def test_exactly_one_route_is_registered(client):
    """A re-added duplicate silently wins the OpenAPI schema while losing every
    real request — the exact shape that hid this route's signature for as long
    as it existed."""
    assert len(_routes_for_path()) == 1


def test_openapi_advertises_only_series(client):
    """The reason the shadow had to go: `/docs` is where an operator learns the
    parameter exists. While the duplicate stood, the schema showed ITS signature
    (`limit` described as 'Max outcomes to process') and `only_series` was
    invisible even though the served handler accepted it."""
    spec = app.openapi()["paths"][PATH]["post"]
    names = {p["name"] for p in spec.get("parameters", [])}
    assert "only_series" in names
    assert "limit" in names


def test_no_duplicate_operation_id_warning(client, recwarn):
    """FastAPI emits `Duplicate Operation ID ...` for a shadowed path. Its
    absence is the framework's own witness that the shadow is gone."""
    app.openapi_schema = None
    try:
        app.openapi()
    finally:
        app.openapi_schema = None
    assert not [
        w for w in recwarn.list
        if "Duplicate Operation ID" in str(w.message)
        and "backfill_kalshi_settled" in str(w.message)
    ]


# --------------------------------------------------------------------------
# It is a settlement trigger, so authentication is part of the contract
# --------------------------------------------------------------------------

def test_unauthenticated_targeted_call_dispatches_nothing(client, dispatched):
    """A 403 that still queued the task would be a production settlement write
    behind a failed auth check."""
    r = client.post(f"{PATH}?only_series=KXATP")
    assert r.status_code == 403
    assert dispatched == []


def test_secret_in_the_query_string_is_not_accepted(client, dispatched):
    """Queue #252 Item 3: `?secret=` is dead as a transport and must not be
    resurrected by a new parameter sitting next to it."""
    r = client.post(f"{PATH}?secret={ADMIN_TOKEN}&only_series=KXATP")
    assert r.status_code == 403
    assert dispatched == []
