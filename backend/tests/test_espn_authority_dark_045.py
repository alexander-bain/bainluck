"""lane1/045 — ESPN must not name itself, and its silence must not read as "none".

Two defects, one file.

**The 403.** ESPN began refusing ``User-Agent: BainLuck/1.0``. Measured
2026-09-01 21:4x PDT against ``soccer/bra.1/scoreboard``: ``BainLuck/1.0`` 403,
``Mozilla/5.0`` 403, header removed 403, httpx's own ``python-httpx/x`` **200**.
So the client stops naming the product and, on a 403, retries once with the
header removed.

**The silence.** ``get_scoreboard`` returned ``[]`` for both "no games today"
and "the request failed" (gotcha #53), which is why the block ran for an unknown
period unnoticed — and worse, why ESPN's silence could be *written*: the roster
sync clears a team's stored roster on an empty answer, the box-score pass stamps
``error: not_available`` on the event, and the espn_id validator clears a team's
ESPN link when the id is missing from the fetched list. Every one of those is a
durable claim about the WORLD derived from a claim about ESPN.

Each behavioural test asserts BOTH arms — dark returns ``None`` *and* an honestly
empty answer still returns ``[]``/``{}`` — because a guard that only pins the
dark arm passes just as well on a client that returns ``None`` for everything.
"""

import ast
import logging
from pathlib import Path

import httpx
import pytest

from app.services import espn_api
from app.services.espn_api import (
    AUTHORITY_DARK_THRESHOLD,
    PATH_DEFAULT_UA,
    PATH_NO_UA,
    ESPNAPIService,
    ESPNAuthorityDark,
    espn_authority_state,
    reset_espn_authority_state,
)

# ── Payloads ────────────────────────────────────────────────────────────────

ONE_GAME_BOARD = {
    "events": [
        {
            "id": "401999999",
            "name": "Away Team at Home Team",
            "shortName": "AWY @ HOM",
            "date": "2026-09-01T23:00Z",
            "status": {"type": {"name": "STATUS_SCHEDULED", "detail": "9:00 PM"}},
            "competitions": [
                {
                    "competitors": [
                        {"homeAway": "home", "score": "0",
                         "team": {"id": "1", "displayName": "Home Team"}},
                        {"homeAway": "away", "score": "0",
                         "team": {"id": "2", "displayName": "Away Team"}},
                    ],
                }
            ],
        }
    ]
}

EMPTY_BOARD = {"events": []}

SUMMARY_EMPTY = {"header": {}, "boxscore": {}}


def _service(handler=None) -> ESPNAPIService:
    """Service whose wire is a MockTransport — no test may reach the network.

    The transport is injected at construction, not swapped onto the client
    afterwards: with proxy env vars set (as in CI sandboxes) httpx mounts the
    proxy ahead of ``_transport``, and a swapped attribute is silently ignored
    while the request goes out for real. That is how the first cut of this file
    "passed" against live ESPN.
    """
    transport = httpx.MockTransport(handler) if handler is not None else None
    # rate_limit_delay=0: the pacing sleep is not what these guards measure.
    return ESPNAPIService(timeout=1.0, rate_limit_delay=0.0, transport=transport)


async def _wire(svc: ESPNAPIService, handler=None):
    """Build both production clients so their real headers can be inspected."""
    primary = await svc._get_client()
    no_ua = await svc._get_no_ua_client()
    return primary, no_ua


@pytest.fixture(autouse=True)
def _fresh_counter():
    reset_espn_authority_state()
    yield
    reset_espn_authority_state()


# ── 1. We do not name ourselves to ESPN ─────────────────────────────────────


@pytest.mark.asyncio
async def test_primary_client_sends_the_library_user_agent_and_never_the_product():
    svc = _service()
    try:
        client = await svc._get_client()
        ua = client.headers.get("user-agent")
        assert ua, "the primary path must send httpx's default UA, not no UA"
        assert ua.startswith("python-httpx"), f"unexpected primary UA: {ua!r}"
        assert "bainluck" not in ua.lower(), (
            "the product UA is measured-403 at ESPN — it must not come back"
        )
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_no_ua_client_omits_the_header_entirely_rather_than_sending_empty():
    """An empty UA is a different (measured-403) thing from no UA header."""
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("user-agent"))
        return httpx.Response(200, json=EMPTY_BOARD)

    svc = _service(handler)
    try:
        _, no_ua = await _wire(svc)
        assert "user-agent" not in no_ua.headers
        await no_ua.get("https://site.api.espn.com/x")
        assert seen == [None], f"no-UA path sent a User-Agent: {seen!r}"
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_a_403_retries_once_with_no_user_agent_and_that_retry_can_serve():
    sent: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        ua = request.headers.get("user-agent")
        sent.append(ua)
        if ua is not None:
            return httpx.Response(403, text="denied")
        return httpx.Response(200, json=ONE_GAME_BOARD)

    svc = _service(handler)
    try:
        await _wire(svc)
        events = await svc.get_scoreboard("basketball_nba")
        assert events is not None and len(events) == 1
        assert len(sent) == 2, f"expected exactly one retry, got {sent!r}"
        assert sent[0] is not None and sent[0].startswith("python-httpx")
        assert sent[1] is None, "the retry must drop the User-Agent header"
        assert espn_authority_state()["served_path"] == PATH_NO_UA
        assert espn_authority_state()["consecutive_failures"] == 0
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_the_retry_happens_once_and_not_in_a_loop():
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("user-agent"))
        return httpx.Response(403, text="denied")

    svc = _service(handler)
    try:
        await _wire(svc)
        assert await svc.get_scoreboard("basketball_nba") is None
        assert len(calls) == 2, f"403 must cost exactly two requests, got {calls!r}"
    finally:
        await svc.close()


# ── 2. [] means "nothing there". None means "we do not know". ───────────────


@pytest.mark.asyncio
async def test_scoreboard_dark_is_none_and_an_empty_slate_is_still_a_list():
    """Both arms. The empty-slate arm is what makes the dark arm mean anything."""
    state = {"status": 403}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["status"] == 200:
            return httpx.Response(200, json=EMPTY_BOARD)
        return httpx.Response(state["status"], text="denied")

    svc = _service(handler)
    try:
        await _wire(svc)
        assert await svc.get_scoreboard("basketball_nba") is None

        state["status"] = 200
        empty = await svc.get_scoreboard("basketball_nba")
        assert empty == [], "an answered-but-empty slate must stay an empty list"
        assert empty is not None
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_event_context_dark_is_none_and_an_empty_summary_is_still_a_dict():
    state = {"status": 500}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["status"] == 200:
            return httpx.Response(200, json=SUMMARY_EMPTY)
        return httpx.Response(state["status"], text="boom")

    svc = _service(handler)
    try:
        await _wire(svc)
        assert await svc.get_event_context("basketball_nba", "1") is None

        state["status"] = 200
        ctx = await svc.get_event_context("basketball_nba", "1")
        assert isinstance(ctx, dict) and ctx["box_score"] == {}
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_roster_dark_is_none_and_an_empty_roster_is_still_a_list():
    state = {"status": 503}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["status"] == 200:
            return httpx.Response(200, json={"athletes": []})
        return httpx.Response(state["status"], text="boom")

    svc = _service(handler)
    try:
        await _wire(svc)
        assert await svc.get_team_roster("basketball_nba", "13") is None

        state["status"] = 200
        assert await svc.get_team_roster("basketball_nba", "13") == []
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_teams_dark_is_none_and_an_empty_league_is_still_a_list():
    state = {"status": 429}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["status"] == 200:
            return httpx.Response(200, json={"sports": [{"leagues": [{"teams": []}]}]})
        return httpx.Response(state["status"], text="slow down")

    svc = _service(handler)
    try:
        await _wire(svc)
        # 429 retries once inside _get, then goes dark rather than returning [].
        assert await svc.get_teams("basketball_nba") is None

        state["status"] = 200
        assert await svc.get_teams("basketball_nba") == []
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_a_transport_failure_is_dark_not_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no route", request=request)

    svc = _service(handler)
    try:
        await _wire(svc)
        assert await svc.get_scoreboard("basketball_nba") is None
        assert espn_authority_state()["consecutive_failures"] == 1
        assert "timeout" in (espn_authority_state()["last_error"] or "")
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_a_404_is_an_answer_not_darkness():
    """The resource is absent; the authority is alive. It must not count dark."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    svc = _service(handler)
    try:
        await _wire(svc)
        assert await svc.get_scoreboard("basketball_nba") == []
        st = espn_authority_state()
        assert st["consecutive_failures"] == 0
        assert st["total_answers"] == 1
        assert st["total_failures"] == 0
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_get_raises_authority_dark_so_a_new_caller_cannot_get_a_silent_empty():
    """``_get`` raises. A method that forgets to catch it fails loudly."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    svc = _service(handler)
    try:
        await _wire(svc)
        with pytest.raises(ESPNAuthorityDark) as exc:
            await svc._get("https://site.api.espn.com/whatever")
        assert exc.value.status == 500
    finally:
        await svc.close()


# ── 3. Darkness is announced, once, and loudly ──────────────────────────────


@pytest.mark.asyncio
async def test_consecutive_darkness_announces_at_the_threshold_exactly_once(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="boom")

    svc = _service(handler)
    try:
        await _wire(svc)
        with caplog.at_level(logging.ERROR, logger="app.services.espn_api"):
            for _ in range(AUTHORITY_DARK_THRESHOLD - 1):
                await svc.get_scoreboard("basketball_nba")
            assert not [r for r in caplog.records if "AUTHORITY DARK" in r.message], (
                "announced before the threshold"
            )

            await svc.get_scoreboard("basketball_nba")
            announcements = [r for r in caplog.records if "AUTHORITY DARK" in r.message]
            assert len(announcements) == 1

            for _ in range(3):
                await svc.get_scoreboard("basketball_nba")
            announcements = [r for r in caplog.records if "AUTHORITY DARK" in r.message]
            assert len(announcements) == 1, "one announcement per dark spell, not per call"

        st = espn_authority_state()
        assert st["is_dark"] is True
        assert st["dark_since"] is not None
        assert st["last_status"] == 503
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_an_answer_clears_the_dark_state_and_says_so(caplog):
    state = {"status": 503}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["status"] == 200:
            return httpx.Response(200, json=EMPTY_BOARD)
        return httpx.Response(state["status"], text="boom")

    svc = _service(handler)
    try:
        await _wire(svc)
        for _ in range(AUTHORITY_DARK_THRESHOLD):
            await svc.get_scoreboard("basketball_nba")
        assert espn_authority_state()["is_dark"] is True

        with caplog.at_level(logging.ERROR, logger="app.services.espn_api"):
            state["status"] = 200
            await svc.get_scoreboard("basketball_nba")
        assert [r for r in caplog.records if "AUTHORITY RECOVERED" in r.message]

        st = espn_authority_state()
        assert st["is_dark"] is False
        assert st["consecutive_failures"] == 0
        assert st["dark_since"] is None
    finally:
        await svc.close()


# ── 4. The destructive callers keep what they have ──────────────────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Answers the two SELECTs `_sync_espn_rosters` makes, records writes."""

    def __init__(self, teams):
        self._answers = [_FakeResult(teams), _FakeResult(teams)]
        self.writes: list = []

    async def execute(self, stmt, *args, **kwargs):
        if self._answers:
            return self._answers.pop(0)
        self.writes.append(stmt)
        return _FakeResult([])


class _FakeTeamRow:
    def __init__(self, tid, espn_id, name):
        self.id = tid
        self.espn_id = espn_id
        self.name = name


@pytest.mark.parametrize(
    "roster, expect_write, label",
    [
        (None, False, "authority dark — the stored roster is KEPT"),
        ([], True, "ESPN answered 'no players' — the roster is cleared"),
    ],
)
@pytest.mark.asyncio
async def test_roster_sync_never_clears_a_roster_on_espn_silence(
    monkeypatch, roster, expect_write, label
):
    """The whole point: `if not roster: clear` treated 403 as "no players"."""
    from app.models.models import Team
    from app.tasks import roster_sync

    class _FakeESPN:
        async def get_team_roster(self, sport_key, team_id):
            return roster

    monkeypatch.setattr(
        "app.services.espn_api.get_espn_service", lambda: _FakeESPN()
    )

    session = _FakeSession([_FakeTeamRow(7, "13", "Lakers")])
    result = await roster_sync._sync_espn_rosters(session, Team, 1, "basketball_nba")

    assert bool(session.writes) is expect_write, label
    if roster is None:
        assert result["authority_dark"] == 1
        assert result["empty_rosters"] == 0
    else:
        assert result["empty_rosters"] == 1
        assert result.get("authority_dark", 0) == 0


# ── 5. Every ESPN call site asks the question ───────────────────────────────

#: Methods that can now answer ``None`` for "ESPN did not answer".
DARK_CAPABLE = {
    "get_scoreboard",
    "get_teams",
    "get_team_roster",
    "get_event_context",
}

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCANNED_DIRS = ("app", "scripts")


def _none_checks_in(node: ast.AST) -> set[str]:
    """Names compared against ``None`` with ``is``/``is not`` anywhere inside."""
    checked: set[str] = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Compare):
            continue
        if not any(isinstance(op, (ast.Is, ast.IsNot)) for op in sub.ops):
            continue
        operands = [sub.left, *sub.comparators]
        names = {o.id for o in operands if isinstance(o, ast.Name)}
        has_none = any(
            isinstance(o, ast.Constant) and o.value is None for o in operands
        )
        if has_none:
            checked |= names
    return checked


#: How an ESPN client comes into existence. A receiver bound by one of these
#: is an ESPN receiver; ``service.get_teams()`` on the MLB or StatPal client is
#: a different method that happens to share a name, and is not scanned.
_ESPN_FACTORIES = {"ESPNAPIService", "get_espn_service", "ESPNApiClient"}


def _callee_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _espn_receivers(node: ast.AST) -> set[str]:
    """Names bound to an ESPN client anywhere inside ``node``."""
    names: set[str] = set()
    for sub in ast.walk(node):
        value = None
        target = None
        if isinstance(sub, ast.Assign) and len(sub.targets) == 1:
            target = sub.targets[0]
            value = sub.value
        elif isinstance(sub, (ast.With, ast.AsyncWith)):
            for item in sub.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Await):
                    ctx = ctx.value
                if (
                    isinstance(ctx, ast.Call)
                    and _callee_name(ctx.func) in _ESPN_FACTORIES
                    and isinstance(item.optional_vars, ast.Name)
                ):
                    names.add(item.optional_vars.id)
            continue
        if not isinstance(target, ast.Name) or value is None:
            continue
        if isinstance(value, ast.Await):
            value = value.value
        if isinstance(value, ast.Call) and _callee_name(value.func) in _ESPN_FACTORIES:
            names.add(target.id)
    return names


def _dark_call_target(stmt: ast.AST) -> tuple[str, str, str, int] | None:
    """(name, receiver, method, lineno) for an assignment from a dark-capable call."""
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return None
    target = stmt.targets[0]
    if not isinstance(target, ast.Name):
        return None
    value = stmt.value
    if isinstance(value, ast.Await):
        value = value.value
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if not isinstance(func, ast.Attribute) or func.attr not in DARK_CAPABLE:
        return None
    receiver = func.value.id if isinstance(func.value, ast.Name) else ""
    return target.id, receiver, func.attr, stmt.lineno


def test_every_espn_call_site_handles_the_dark_answer():
    """A new caller that ignores ``None`` reintroduces the exact defect.

    Bound per call site — the enclosing function of THIS call must contain the
    ``is None`` test — so a sibling caller's check cannot satisfy it. A file the
    scanner cannot parse RAISES rather than passing silently.
    """
    offenders: list[str] = []
    sites: list[str] = []

    for directory in _SCANNED_DIRS:
        for path in sorted((_REPO_ROOT / directory).rglob("*.py")):
            if path.name == "espn_api.py":
                continue  # the service defines these; it does not consume them
            source = path.read_text(encoding="utf-8")
            if not any(m in source for m in DARK_CAPABLE):
                continue
            # A parse failure is a scanner failure, not a pass.
            tree = ast.parse(source, filename=str(path))
            module_receivers = _espn_receivers(tree)
            for func in ast.walk(tree):
                if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                checked = _none_checks_in(func)
                receivers = module_receivers | _espn_receivers(func)
                for stmt in ast.walk(func):
                    found = _dark_call_target(stmt)
                    if not found:
                        continue
                    name, receiver, method, lineno = found
                    if receiver not in receivers:
                        continue  # not an ESPN client — same method name, other service
                    sites.append(f"{path.relative_to(_REPO_ROOT)}:{lineno} {method}")
                    if name not in checked:
                        offenders.append(
                            f"{path.relative_to(_REPO_ROOT)}:{lineno} "
                            f"{name} = {receiver}.{method}() with no `{name} is None` check"
                        )

    # Measured at 19 on 2026-09-01. A DROP means the scanner stopped seeing call
    # sites, which reads identical to "they all comply" — so it fails, and the
    # number is updated deliberately when a caller is genuinely removed.
    assert len(sites) >= 19, (
        f"the scanner found only {len(sites)} ESPN call sites (expected >= 19): "
        + ", ".join(sites)
    )
    assert not offenders, "ESPN call sites that read silence as emptiness:\n" + "\n".join(
        offenders
    )


def test_the_service_module_does_not_advertise_the_product_user_agent():
    source = (_REPO_ROOT / "app" / "services" / "espn_api.py").read_text()
    code = "\n".join(
        line for line in source.splitlines()
        if not line.strip().startswith(("#", "*"))
    )
    # The measurement lives in the docstring; the string must not reach a header.
    assert '"User-Agent": "BainLuck' not in code
    assert "'User-Agent': 'BainLuck" not in code
    assert espn_api.AUTHORITY_DARK_THRESHOLD == 10
    assert PATH_DEFAULT_UA != PATH_NO_UA
