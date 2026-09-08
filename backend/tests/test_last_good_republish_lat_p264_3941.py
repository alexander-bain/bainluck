"""#3941 — the warm rail must not republish a page the route REFUSED.

LAT-P264. The ship, in the reader's terms: **the Discover front page stops
being served a mirror that the system itself already refused as too old.**

THE DEFECT, as a sequence:

1. ``GET /api/feed`` builds a live page from shared artifacts. CERT-1864's
   input-age ceiling asks whether the oldest of those artifacts has already
   spent the whole 60s live window. If it has, the page is REFUSED.
2. Refused does not mean nothing is served. Branch (b) hands back a still-valid
   PRIOR payload, and it is scrupulous about the arithmetic: the TTLs it stamps
   come from that payload's own age, so a 55-second-old fallback is published
   with the five seconds it actually has left.
3. ``_prewarm_feed_shape`` then republished it. Its ``feed_response_cache_ttls``
   call omits ``oldest_artifact_age_s``, which defaults to ``0.0``, so the page
   the route had just declined to serve was written to Redis under a **full
   30s/60s window** — by the one writer whose entire job is keeping that shape
   under the ceiling.
4. Both existing refusal gates let it through on the merits: ``build_quality``
   is ``"complete"`` (it WAS a complete build, merely an old one) and ``items``
   is non-empty (that is the whole point of serving a prior page).

THE FIX is the third refusal, and it is the same refusal as the other two:
publish only a page THIS pass built; on anything else keep last-good. The two
sets in ``feed_cache.py`` say which is which, and
``test_every_cache_status_the_route_can_stamp_is_classified`` reads them back
out of the route so the classification cannot be skipped by forgetting it
exists.

WHAT THIS IS NOT. It is not #3841. Nothing here passes an artifact age into the
window of a page this pass BUILT, so the ``artifact_TTL + PERIOD + lateness <=
CEILING`` arithmetic — which at PERIOD 30 / MIN_HEADROOM 10 would force
``artifact_TTL <= 20``, half what LAT-P261 (#3904) shipped — is never entered.
``test_the_healthy_pass_still_publishes_a_full_window`` pins that from the
outside and ``test_the_rail_does_not_pass_an_artifact_age_into_its_own_ttls``
pins it from the source.
"""

import ast
import asyncio
import importlib
import inspect
import json
import textwrap
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.utils import feed_cache as fc
from app.utils.feed_cache import (
    FEED_BUILT_CACHE_STATUSES,
    FEED_PREWARM_KEY_SCOPE_KEY,
    FEED_PREWARM_SCOPE_KEY,
    FEED_SERVED_FROM_PRIOR_CACHE_STATUSES,
    feed_payload_was_built_by_this_request,
)

# NOTE: `from app.tasks import precompute_category_pages` resolves to the Celery
# TASK of that name registered in app/tasks/__init__.py, not the module. Pull the
# module out of sys.modules explicitly.
pcp = importlib.import_module("app.tasks.precompute_category_pages")

RESOLVED_KEY = "feed_cache:lat-p264"


def _run_warm(payload, *, resolved_key=RESOLVED_KEY):
    """Drive ``_prewarm_feed_shape`` with a ``get_feed`` returning ``payload``."""
    rc = MagicMock()

    async def fake_get_feed(**kwargs):
        request = kwargs["request"]
        assert request.scope.get(FEED_PREWARM_SCOPE_KEY) is True
        if resolved_key is not None:
            request.scope[FEED_PREWARM_KEY_SCOPE_KEY] = resolved_key
        return payload

    @asynccontextmanager
    async def fake_session():
        yield MagicMock()

    with patch("app.routes.feed.get_feed", fake_get_feed), patch(
        "app.tasks.base.get_task_session", fake_session
    ):
        result = asyncio.run(
            pcp._prewarm_feed_shape(dict(pcp.FEED_PREWARM_SHAPES[0]), rc)
        )
    return result, rc


def _ceiling_refusal_payload():
    """Exactly what branch (b) of the route returns, fields and all.

    Built through ``build_feed_cache_metadata`` rather than hand-typed, so a
    change to the metadata shape reaches this fixture instead of leaving it
    pinning a payload the route stopped producing.
    """
    return {
        "items": [{"id": "a"}, {"id": "b"}],
        "total": 2,
        "limit": 20,
        "offset": 0,
        "has_more": False,
        "cache": fc.build_feed_cache_metadata(
            "last_good",
            # The five seconds a 55-second-old fallback has left — the number
            # the rail was throwing away.
            ttl_seconds=5,
            stale_ttl_seconds=5,
            reason="input_age_ceiling",
            live=True,
            built_at=1_700_000_000.0,
        ),
    }


# --- The ship -----------------------------------------------------------------


def test_the_rail_refuses_to_republish_a_page_the_ceiling_refused():
    """THE REGRESSION. A ``last_good`` page must never reach ``setex``."""
    result, rc = _run_warm(_ceiling_refusal_payload())

    rc.setex.assert_not_called()
    assert result["outcome"] == "not_built"


def test_the_refusal_says_why_on_the_report_not_only_in_the_log():
    """LAT-P261 (#3904)'s rule, applied to the outcome it did not yet have.

    ``/api/admin/feed-live-prewarm/last`` serves this dict and the log buffer is
    ~3 minutes, so a reason that lives only in a log line is a reason nobody
    reads (gotcha #53). A reader must be able to tell this refusal from the
    other three without catching it in the act.
    """
    result, _ = _run_warm(_ceiling_refusal_payload())

    assert result["cache_status"] == "last_good"
    assert result["not_built_reason"] == "input_age_ceiling"
    assert "duration_s" in result


@pytest.mark.parametrize("status", sorted(FEED_BUILT_CACHE_STATUSES))
def test_every_built_status_still_publishes(status):
    """The other direction, and the one that would hurt more if it broke.

    An allowlist that is too small does not fail loudly — it silently stops
    warming, and the symptom is a slow front page, which is this lane's whole
    subject. So each member is exercised, not merely asserted to be in the set.
    """
    payload = {
        "items": [{"id": "a"}],
        "total": 1,
        "cache": fc.build_feed_cache_metadata(status, ttl_seconds=30),
    }
    result, rc = _run_warm(payload)

    assert result["outcome"] == "ok", f"a {status!r} build was not published"
    written = {call.args[0] for call in rc.setex.call_args_list}
    assert written == {RESOLVED_KEY, f"{RESOLVED_KEY}:stale"}


@pytest.mark.parametrize("status", sorted(FEED_SERVED_FROM_PRIOR_CACHE_STATUSES))
def test_no_served_from_prior_status_is_ever_republished(status):
    payload = {
        "items": [{"id": "a"}],
        "total": 1,
        "cache": fc.build_feed_cache_metadata(status, ttl_seconds=30),
    }
    result, rc = _run_warm(payload)

    rc.setex.assert_not_called()
    assert result["outcome"] == "not_built"


# --- Fail closed --------------------------------------------------------------


@pytest.mark.parametrize(
    "cache_block",
    [
        pytest.param(None, id="no_cache_block"),
        pytest.param("miss", id="cache_is_a_string"),
        pytest.param({}, id="cache_has_no_status"),
        pytest.param({"status": None}, id="status_is_null"),
        pytest.param({"status": "a_status_nobody_has_written_yet"}, id="unknown"),
    ],
)
def test_a_payload_that_does_not_say_is_not_published(cache_block):
    """An unknown costs one warm pass. Guessing costs a fresh window on a lie.

    This is the asymmetry the whole fix turns on, so it is pinned as its own
    test rather than left implicit in the helper. The defect being repaired was
    itself a default that failed OPEN — ``oldest_artifact_age_s=0.0``, "assume
    the inputs are brand new" — and repeating that shape in the gate that
    replaces it would be a poor joke.
    """
    payload = {"items": [{"id": "a"}], "total": 1}
    if cache_block is not None:
        payload["cache"] = cache_block

    result, rc = _run_warm(payload)

    rc.setex.assert_not_called()
    assert result["outcome"] == "not_built"


def test_the_predicate_never_raises_on_a_shape_it_did_not_expect():
    for junk in (None, [], "", 0, {"cache": []}, {"cache": {"status": 7}}):
        assert feed_payload_was_built_by_this_request(junk) is False


# --- The classification cannot be skipped by forgetting it exists -------------


def _resolve_status_arguments():
    """Every value ``routes/feed.py`` can pass as the metadata's status.

    A literal resolves to itself. A NAME resolves to every string constant the
    file assigns to it — including through a conditional expression, which is
    how ``_pb_status`` is written — and, when the name is bound by tuple unpack
    from a call (``_shared_status``, ``_base_status``), to the string constants
    that helper returns.

    A name this cannot resolve is returned as an unresolved marker rather than
    quietly dropped: the test below fails on it, and whoever added it extends
    this resolver — which is exactly the moment they have to decide which set
    their new status belongs in.
    """
    source = inspect.getsource(importlib.import_module("app.routes.feed"))
    tree = ast.parse(source)

    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def _strings(node):
        return {
            n.value
            for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }

    # name -> string constants assigned to it directly or through an IfExp.
    assigned: dict[str, set[str]] = {}
    # name -> the functions it is tuple-unpacked from.
    unpacked_from: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str
                ):
                    assigned.setdefault(target.id, set()).add(node.value.value)
                elif isinstance(node.value, ast.IfExp):
                    assigned.setdefault(target.id, set()).update(
                        _strings(node.value.body) | _strings(node.value.orelse)
                    )
            elif isinstance(target, ast.Tuple):
                call = node.value
                if isinstance(call, ast.Await):
                    call = call.value
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                    for element in target.elts:
                        if isinstance(element, ast.Name):
                            unpacked_from.setdefault(element.id, set()).add(
                                call.func.id
                            )

    resolved: set[str] = set()
    unresolved: set[str] = set()
    call_sites = 0
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "build_feed_cache_metadata"
            and node.args
        ):
            continue
        call_sites += 1
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            resolved.add(first.value)
            continue
        if isinstance(first, ast.Name):
            found = set(assigned.get(first.id, ()))
            for helper in unpacked_from.get(first.id, ()):
                if helper in functions:
                    for ret in ast.walk(functions[helper]):
                        if isinstance(ret, ast.Return) and ret.value is not None:
                            found |= _strings(ret.value)
            if found:
                resolved |= found
                continue
        unresolved.add(ast.unparse(first))

    return resolved, unresolved, call_sites


def test_every_cache_status_the_route_can_stamp_is_classified():
    """Why this is an ALLOWLIST and not "refuse ``last_good``".

    A denylist of the statuses known to be unsafe hands the SAFE answer to
    whichever status is added next — nobody writing a fourteenth
    serve-from-a-prior-build path is going to remember a frozenset in another
    module. The allowlist gives a new status the conservative answer by
    default, and this test makes it impossible to ship one without saying which
    it is.
    """
    resolved, unresolved, call_sites = _resolve_status_arguments()

    assert not unresolved, (
        "`build_feed_cache_metadata` is being called with a status this test "
        f"cannot resolve: {sorted(unresolved)}. Extend `_resolve_status_"
        "arguments` — and while you are there, classify the value into "
        "FEED_BUILT_CACHE_STATUSES or FEED_SERVED_FROM_PRIOR_CACHE_STATUSES."
    )
    assert call_sites >= 12, (
        f"only {call_sites} `build_feed_cache_metadata` call sites found — the "
        "resolver has stopped seeing the route and is passing vacuously"
    )

    classified = FEED_BUILT_CACHE_STATUSES | FEED_SERVED_FROM_PRIOR_CACHE_STATUSES
    unclassified = resolved - classified
    assert not unclassified, (
        f"`routes/feed.py` can stamp cache.status={sorted(unclassified)}, which "
        "neither set in `feed_cache.py` names. The warm rail republishes a "
        "payload only when its status is in FEED_BUILT_CACHE_STATUSES, so an "
        "unclassified status is silently treated as unpublishable. Decide: did "
        "the responding request BUILD that page, or serve it from an earlier "
        "build? (#3941)"
    )


def test_the_two_sets_are_disjoint():
    assert not (FEED_BUILT_CACHE_STATUSES & FEED_SERVED_FROM_PRIOR_CACHE_STATUSES)


# --- #3841's trap is not entered ----------------------------------------------


def test_the_healthy_pass_still_publishes_a_full_window():
    """The published window on a BUILT page is unchanged by this fix.

    #3841 is real, adjacent, and is not being fixed here. Its tempting
    one-liner — pass ``oldest_artifact_age_s`` into the rail's TTLs — is a trap:
    ``artifact_TTL + PERIOD + lateness <= CEILING`` at PERIOD 30 /
    MIN_HEADROOM 10 forces ``artifact_TTL <= 20``, half of what LAT-P261
    (#3904) shipped and short enough that occasional holes become permanent
    ones. So the healthy pass is pinned at the full window, from the outside.
    """
    payload = {
        "items": [{"id": "a"}],
        "total": 1,
        "cache": fc.build_feed_cache_metadata("miss", ttl_seconds=30),
    }
    result, rc = _run_warm(payload)

    assert result["outcome"] == "ok"
    written = {call.args[0]: call.args for call in rc.setex.call_args_list}
    assert written[RESOLVED_KEY][1] == fc.feed_response_cache_ttl(
        my_teams_only=False, identified=False
    )
    assert written[f"{RESOLVED_KEY}:stale"][1] == fc.FEED_RESPONSE_STALE_TTL_SECONDS
    assert json.loads(written[RESOLVED_KEY][2])["total"] == 1


def test_the_rail_does_not_pass_an_artifact_age_into_its_own_ttls():
    """A source guard, because the trap is one keyword argument wide.

    The behavioural test above catches it only for a page built from nothing
    shared, which is what a unit fixture always is. This catches the edit.
    """
    source = textwrap.dedent(inspect.getsource(pcp._prewarm_feed_shape))
    tree = ast.parse(source)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "feed_response_cache_ttls"
    ]
    assert len(calls) == 1, "the rail should compute its window exactly once"
    passed = {kw.arg for kw in calls[0].keywords}
    assert "oldest_artifact_age_s" not in passed, (
        "the warm rail is now shortening its published window by the age of the "
        "artifacts a page was built from. That is #3841's one-liner, and it "
        "forces artifact_TTL <= 20 against a 30s republish period — read "
        "#3941's docstring before keeping this."
    )
