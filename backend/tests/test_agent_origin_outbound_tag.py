"""Guards for outbound `x-bainluck-origin` tagging (notice 39 / #1916, #4459 ship 5).

The class of bug every test here exists to catch is the SILENT one. Nothing in
this channel raises when it breaks: a header spelled wrong, a header resolved at
import time, a header sent to Kalshi, a header sent twice — each produces a
perfectly normal 200 and a probe whose author believes it is tagged. So these
assert the wire, not the happy path.
"""

from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys
import textwrap

import pytest

from app.utils.agent_origin import (
    ORIGIN_HEADER,
    ORIGIN_USER,
    curl_args,
    is_our_host,
    origin_headers,
    resolve_agent,
    tagged,
)

BACKEND = pathlib.Path(__file__).resolve().parents[1]
GATE_SCRIPTS = sorted(BACKEND.glob("scripts/gate_*.py"))


# ---------------------------------------------------------------------------
# The name on the wire
# ---------------------------------------------------------------------------


def test_header_name_is_the_documented_wire_name():
    assert ORIGIN_HEADER == "x-bainluck-origin"
    assert ORIGIN_USER == "user"


def test_reader_and_sender_share_one_constant():
    """`routes/events.py` must not re-spell the header.

    A sender/reader drift of one character raises nothing: every probe looks
    tagged and every row is still written. This is the only cheap guard.
    """
    from app.routes import events

    assert events._ORIGIN_HEADER is ORIGIN_HEADER
    assert events._ORIGIN_USER is ORIGIN_USER

    src = (BACKEND / "app" / "routes" / "events.py").read_text()
    # The literal may appear in prose/docstrings, but never as an assignment.
    assert not re.search(
        r'^_ORIGIN_HEADER\s*=\s*[\'"]', src, re.M
    ), "events.py re-spells the header literal instead of importing it"


# ---------------------------------------------------------------------------
# Resolution happens at CALL time
# ---------------------------------------------------------------------------


def test_agent_is_resolved_at_call_time_not_import_time(monkeypatch):
    """The failure the shell helper shipped a comment about.

    A name captured at import produces an EMPTY header, the backend reads empty
    as a person, and the call votes in the search head exactly as it did
    untagged.
    """
    monkeypatch.setenv("BL_AGENT", "lane-one")
    assert resolve_agent() == "lane-one"
    monkeypatch.setenv("BL_AGENT", "lane-two")
    assert resolve_agent() == "lane-two", "agent was captured, not re-read"


@pytest.mark.parametrize("value", [None, "", "   ", "\t"])
def test_absent_or_blank_agent_passes_through_untagged(monkeypatch, value):
    """Notice 39 guard 1: an unnamed caller is left exactly as it was.

    Both halves are asserted deliberately. A substituted default here does not
    merely mislabel the call — any non-"user" value SUPPRESSES the search-log
    row server-side, so an un-configured caller would silently vanish from the
    table it exists to populate. And a bot User-Agent without the origin header
    is the worst reading of all: automated in the router log, still voting in
    the search head.
    """
    if value is None:
        monkeypatch.delenv("BL_AGENT", raising=False)
    else:
        monkeypatch.setenv("BL_AGENT", value)

    assert resolve_agent() is None
    assert origin_headers("https://api.bainluck.com/api/x") == {}

    original = {"Authorization": "Bearer t"}
    assert tagged("https://api.bainluck.com/api/x", original) == original
    assert (
        "User-Agent" not in tagged("https://api.bainluck.com/api/x", {})
    ), "a bot UA without the origin header is automated in the log and a person to the head"


def test_a_named_lane_is_still_tagged_through_every_builder(monkeypatch):
    """The other side of the flip: naming yourself must still work everywhere.

    Guards the repair against over-correcting into a no-op — the failure mode
    where pass-through is achieved by tagging nothing at all.
    """
    monkeypatch.setenv("BL_AGENT", "latency")
    url = "https://api.bainluck.com/api/x"

    assert resolve_agent() == "latency"
    assert origin_headers(url)[ORIGIN_HEADER] == "latency"
    assert tagged(url, {})[ORIGIN_HEADER] == "latency"
    assert tagged(url, {})["User-Agent"] == "BainLuckBot/1.0 (latency)"


# ---------------------------------------------------------------------------
# Never on a third party's wire
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://api.bainluck.com/api/admin/db-query",
        "https://bainluck.com/",
        "http://localhost:8000/api/feed",
        "http://127.0.0.1:8000/api/feed",
        "api.bainluck.com/api/feed",  # scheme-less, as a script may build it
    ],
)
def test_our_hosts_are_tagged(url, monkeypatch):
    # An explicit lane: since the guard-1 flip, an unnamed caller adds nothing,
    # so without this the assertion below would pass or fail on the CI shell's
    # environment rather than on the host rule it exists to test.
    monkeypatch.setenv("BL_AGENT", "latency")
    assert is_our_host(url)
    assert ORIGIN_HEADER in origin_headers(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.elections.kalshi.com/trade-api/v2/events",
        "https://gamma-api.polymarket.com/events",
        "https://site.api.espn.com/apis/site/v2/sports",
        "https://api.github.com/repos/x/y",
        "https://the-odds-api.com/v4/sports",
    ],
)
def test_third_party_hosts_are_never_tagged(url, monkeypatch):
    # A NAMED lane, or this asserts nothing: since the guard-1 flip an unnamed
    # caller adds nothing to any host, so an unset BL_AGENT would satisfy the
    # `== {}` below without the host rule ever being consulted.
    monkeypatch.setenv("BL_AGENT", "latency")
    assert not is_our_host(url)
    assert origin_headers(url) == {}


def test_lookalike_host_is_not_ours(monkeypatch):
    """A substring test would tag this; the host is parsed instead."""
    monkeypatch.setenv("BL_AGENT", "latency")  # see above: else `== {}` is vacuous
    assert not is_our_host("https://example.com/?ref=bainluck.com")
    assert not is_our_host("https://bainluck.com.evil.test/x")
    assert origin_headers("https://example.com/?ref=bainluck.com") == {}


def test_userinfo_cannot_smuggle_our_host():
    assert not is_our_host("https://api.bainluck.com@evil.test/x")


# ---------------------------------------------------------------------------
# Never twice — the caller's explicit intent wins
# ---------------------------------------------------------------------------


def test_existing_tag_is_not_overridden(monkeypatch):
    monkeypatch.setenv("BL_AGENT", "lane")
    existing = {ORIGIN_HEADER: ORIGIN_USER}
    assert origin_headers("https://api.bainluck.com/x", existing) == {}
    assert tagged("https://api.bainluck.com/x", existing)[ORIGIN_HEADER] == ORIGIN_USER


def test_existing_tag_match_is_case_insensitive(monkeypatch):
    """HTTP header names are case-insensitive; a dict lookup is not."""
    monkeypatch.setenv("BL_AGENT", "lane")
    existing = {"X-BainLuck-Origin": ORIGIN_USER}
    assert origin_headers("https://api.bainluck.com/x", existing) == {}


def test_tagged_preserves_caller_headers_and_does_not_mutate(monkeypatch):
    monkeypatch.setenv("BL_AGENT", "lane")
    original = {"Authorization": "Bearer t", "Content-Type": "application/json"}
    out = tagged("https://api.bainluck.com/x", original)
    assert out["Authorization"] == "Bearer t"
    assert out["Content-Type"] == "application/json"
    assert out[ORIGIN_HEADER] == "lane"
    assert ORIGIN_HEADER not in original, "caller's dict was mutated"


def test_caller_user_agent_is_not_clobbered(monkeypatch):
    monkeypatch.setenv("BL_AGENT", "lane")
    out = tagged("https://api.bainluck.com/x", {"User-Agent": "mine/1.0"})
    assert out["User-Agent"] == "mine/1.0"


# ---------------------------------------------------------------------------
# The argv rail — the one the shell shadow can never reach
# ---------------------------------------------------------------------------


def test_curl_args_names_our_host(monkeypatch):
    monkeypatch.setenv("BL_AGENT", "latency")
    args = curl_args("https://api.bainluck.com/api/events/typeahead?q=x")
    assert args[0] == "-H"
    assert f"{ORIGIN_HEADER}: latency" in args
    # every header must arrive as its own `-H` pair or curl reads it as a URL
    assert len(args) % 2 == 0
    assert args[::2] == ["-H"] * (len(args) // 2)


def test_curl_args_is_empty_for_a_third_party(monkeypatch):
    monkeypatch.setenv("BL_AGENT", "latency")
    assert curl_args("https://api.elections.kalshi.com/trade-api/v2/events") == []


@pytest.mark.parametrize("value", [None, "", "   "])
def test_curl_args_is_empty_for_an_unnamed_caller(monkeypatch, value):
    """Notice 39 guard 1 on the argv rail: pass through, do not invent a name."""
    if value is None:
        monkeypatch.delenv("BL_AGENT", raising=False)
    else:
        monkeypatch.setenv("BL_AGENT", value)
    assert curl_args("https://api.bainluck.com/api/x") == []


def test_curl_args_does_not_restate_an_origin_the_argv_already_carries(monkeypatch):
    """Two `-H x-bainluck-origin:` values would let this module's default
    silently beat the caller's stated intent — curl sends both and the server
    reads one."""
    monkeypatch.setenv("BL_AGENT", "latency")
    argv = ["curl", "-s", "-H", f"{ORIGIN_HEADER}: harness", "https://bainluck.com/"]
    assert curl_args("https://bainluck.com/", argv) == []
    # and case-insensitively, because a header name is
    assert curl_args("https://bainluck.com/", ["-H", "X-BainLuck-Origin: user"]) == []


def test_curl_args_agrees_with_the_header_builder(monkeypatch):
    """One decision about who we are, rendered two ways. If these ever diverge,
    the same probe is a lane over urllib and a person over curl."""
    monkeypatch.setenv("BL_AGENT", "latency")
    url = "https://api.bainluck.com/api/x"
    from_headers = origin_headers(url)
    rendered = {}
    args = curl_args(url)
    for flag, pair in zip(args[::2], args[1::2]):
        assert flag == "-H"
        name, _, value = pair.partition(": ")
        rendered[name] = value
    assert rendered == from_headers


# ---------------------------------------------------------------------------
# The gate scripts actually carry it
# ---------------------------------------------------------------------------


def test_there_are_gate_scripts_to_check():
    """Denominator guard: an empty glob would make every test below vacuous."""
    assert len(GATE_SCRIPTS) >= 4, [p.name for p in GATE_SCRIPTS]


def _http_gate_scripts():
    return [p for p in GATE_SCRIPTS if "urllib.request.Request" in p.read_text()]


# ---------------------------------------------------------------------------
# THE WHOLE DIRECTORY, NOT A HAND-LISTED SET (#4642)
# ---------------------------------------------------------------------------
#
# The predecessor of this section asserted three scripts BY NAME. That guard
# could only ever stay green: it said nothing about the 90 other scripts making
# production calls, and a new one could be added untagged without failing
# anything. Worse, the hand-list is what made the population unknowable —
# #4642 was filed because "nobody can currently say which subset touches search
# without reading all 56".
#
# So the rule below is stated over the DIRECTORY and the offender list is
# computed, never enumerated. `tagged()`/`curl_args()` decide at RUNTIME whether
# a given URL is ours, so the static rule is the simple one — every outbound
# call goes through the carrier — and third-party hosts cost nothing because the
# carrier returns empty for them.

ALL_SCRIPTS = sorted(BACKEND.glob("scripts/*.py"))

#: Attribute names that build an outbound request, by rail.
_URLLIB = "Request"
_CLIENT_VERBS = {"get", "post", "put", "delete", "head", "patch"}


def _dotted(call: ast.Call) -> str:
    func, parts = call.func, []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts))


def _is_tagged_call(node) -> bool:
    return isinstance(node, ast.Call) and (
        getattr(node.func, "id", None) == "tagged"
        or getattr(node.func, "attr", None) == "tagged"
    )


def _is_request_call(node) -> bool:
    return isinstance(node, ast.Call) and _dotted(node).split(".")[-1] == _URLLIB


def _scopes_of(tree: ast.AST) -> dict:
    """Map every node to the innermost function that encloses it.

    Needed because the same name — almost always ``url`` — is a parameter in one
    function and a ``Request`` in another within a single script. Resolving at
    module level would let the second vouch for the first.
    """
    enclosing = {}
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(scope):
            # Overwrite, deliberately. `ast.walk` is BREADTH-first, so an outer
            # function is visited before the nested one it contains, and the
            # last writer therefore wins the innermost scope — which is the one
            # a name resolves in. `setdefault` here would silently keep the
            # OUTER scope and reintroduce the cross-function leak this exists
            # to close.
            enclosing[node] = scope
    return enclosing


def _bindings(scope: ast.AST) -> dict:
    """Every value a name is bound to in ``scope``: assignments AND parameters.

    Parameters are bindings too, and that is the half the previous rule missed.
    ``def fetch(url: str)`` can never receive a ``Request``, so a bare
    ``urlopen(url)` inside it is untagged no matter what the rest of the file
    assigns to a name spelled ``url``.
    """
    bound: dict = {}
    args = getattr(scope, "args", None)
    if args is not None:
        for arg in (
            list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
            + [a for a in (args.vararg, args.kwarg) if a is not None]
        ):
            bound.setdefault(arg.arg, []).append(arg)
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            targets, value = [node.target], node.value
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            # A loop variable is bound to an ELEMENT of the iterable, which this
            # cannot see. `None` is not a `Request`, so such a name is reported
            # rather than trusted — the safe direction for a silent failure.
            targets, value = [node.target], None
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                bound.setdefault(target.id, []).append(value)
    return bound


def _name_is_a_request(name: str, call: ast.Call, tree: ast.AST, scopes: dict) -> bool:
    """True only when EVERY binding of ``name`` visible here builds a ``Request``.

    The rule this replaces assumed it, in a comment: "a bare Name is a Request
    built on an earlier line; that Request is itself a rail-1 site and is checked
    there." True 72 times out of 83 on the directory as it stands — and false
    eleven times, six of them against our own host (#4747). An assumption that
    holds 87% of the time reads exactly like a check that holds 100% of the time,
    which is why this resolves the name instead.

    Unresolvable is reported, not waved through: the whole failure class here is
    silent, so the safe direction for a name we cannot follow is to name it.
    """
    scope = scopes.get(call)
    for candidate in (scope, tree) if scope is not None else (tree,):
        values = _bindings(candidate).get(name)
        if not values:
            continue
        return all(_is_request_call(v) for v in values)
    return False


def _untagged_sites(path: pathlib.Path) -> list:
    """Every outbound call site in ``path`` that does not carry the tag.

    Four rails, because the fleet has four and only the first was ever guarded:

      1. ``urllib.request.Request(url, headers=...)``
      2. ``urlopen(<a URL, not a Request>)`` — carries no headers AT ALL, so it
         cannot be tagged without being converted to a Request first
      3. ``httpx``/``requests`` ``.get``/``.post``/...
      4. ``subprocess.run(["curl", ...])`` — rung 1 exports a shell FUNCTION,
         and a subprocess executes the BINARY, so the shadow can never reach it
    """
    src = path.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:  # a broken script is its own, louder failure
        return [f"{path.name}: does not parse ({exc})"]

    scopes = _scopes_of(tree)
    bad = []
    for node in ast.walk(tree):
        # rail 4 — a curl argv list
        if isinstance(node, ast.List) and node.elts:
            head = node.elts[0]
            if isinstance(head, ast.Constant) and head.value == "curl":
                seg = ast.get_source_segment(src, node) or ""
                if "curl_args(" not in seg and "ORIGIN_HEADER" not in seg:
                    bad.append(f"{path.name}:{node.lineno} curl argv is untagged")
            continue

        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node)
        short = name.split(".")[-1]

        # rail 2 — urlopen given a URL rather than a Request
        if short == "urlopen" and node.args:
            first = node.args[0]
            # A Request built inline is fine — it is a rail-1 site and is checked
            # below. A bare NAME is only fine once resolved: see
            # `_name_is_a_request` for the eleven sites the old assumption missed.
            ok = _is_request_call(first) or (
                isinstance(first, ast.Name)
                and _name_is_a_request(first.id, node, tree, scopes)
            )
            if not ok:
                bad.append(
                    f"{path.name}:{node.lineno} urlopen() on a URL carries no "
                    f"headers — wrap it in urllib.request.Request(url, headers=tagged(url))"
                )
            continue

        # rails 1 and 3
        if short == _URLLIB:
            pass
        elif short in _CLIENT_VERBS and (
            name.startswith("requests.")
            or name.startswith("httpx.")
            or name.split(".")[0].endswith("client")
            or "client." in name
        ):
            pass
        else:
            continue

        headers = next((k.value for k in node.keywords if k.arg == "headers"), None)
        if headers is None:
            bad.append(f"{path.name}:{node.lineno} {name}() built with no headers")
        elif not _is_tagged_call(headers):
            bad.append(f"{path.name}:{node.lineno} {name}() headers bypass tagged()")
    return bad


def test_the_script_population_is_big_enough_to_be_a_real_check():
    """Denominator guard (the whole point of the rewrite).

    A glob that silently returns nothing turns the assertion below into a
    tautology. The count is deliberately a FLOOR well under today's ~276: this
    asserts the glob works, not that the directory never shrinks.
    """
    assert len(ALL_SCRIPTS) >= 150, len(ALL_SCRIPTS)
    carriers = [p for p in ALL_SCRIPTS if "agent_origin" in p.read_text()]
    assert len(carriers) >= 60, (
        f"only {len(carriers)} scripts import the carrier — the sweep regressed"
    )


def test_no_backend_script_makes_an_untagged_outbound_call():
    """#4642 done-when 3: the count of untagged callers is 0, for the DIRECTORY.

    Asserted on the AST, so a commented-out call cannot pass and a new script
    cannot silently reintroduce one. The failure names every offending site.
    """
    offenders = [site for path in ALL_SCRIPTS for site in _untagged_sites(path)]
    assert offenders == [], (
        f"{len(offenders)} untagged outbound call site(s) under backend/scripts/. "
        "Each one writes a row to search_query_logs if it reaches /api/events/search, "
        "and CASTS A TRENDING VOTE the head warmer then spends real work on. "
        "Route it through app.utils.agent_origin.tagged() / curl_args():\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Rail 2 resolves the name it used to merely trust (#4747)
# ---------------------------------------------------------------------------
#
# The census above is an ASSERTION THAT A NUMBER IS ZERO, and the cheapest way
# to make such an assertion pass is to stop counting. That is not hypothetical
# here: for the whole life of #4642 rail 2 skipped every `urlopen(<name>)`
# on the stated reasoning that the name "is a Request built on an earlier line".
# It was, 72 times out of 83 — and eleven times it was a URL string, six of
# those against our own host.
#
# So these tests do not exercise the directory. They exercise the RULE, on
# sources written to be unambiguous, and they fail if the rule ever degrades
# back into trusting a name. A revert of `_name_is_a_request` to `return True`
# leaves the census green and turns every case below red.


def _sites_for(tmp_path, source: str) -> list:
    script = tmp_path / "synthetic_probe.py"
    script.write_text(textwrap.dedent(source))
    return _untagged_sites(script)


_OURS = "https://api.bainluck.com/api/events/search?q=x"

RAIL2_CASES = [
    (
        "a name assigned a URL STRING is the bug this closes",
        f'''
        from urllib.request import urlopen
        def go():
            url = "{_OURS}"
            with urlopen(url, timeout=5) as r:
                return r.read()
        ''',
        True,
    ),
    (
        "a name assigned a tagged Request is genuinely fine",
        f'''
        from urllib.request import Request, urlopen
        from app.utils.agent_origin import tagged
        def go():
            url = "{_OURS}"
            req = Request(url, headers=tagged(url))
            with urlopen(req, timeout=5) as r:
                return r.read()
        ''',
        False,
    ),
    (
        "a PARAMETER can never be a Request — the half whole-file lookup missed",
        '''
        from urllib.request import urlopen
        def fetch(url: str):
            with urlopen(url, timeout=5) as r:
                return r.read()
        ''',
        True,
    ),
    (
        "an inline Request needs no resolution at all",
        f'''
        from urllib.request import Request, urlopen
        from app.utils.agent_origin import tagged
        def go():
            url = "{_OURS}"
            with urlopen(Request(url, headers=tagged(url)), timeout=5) as r:
                return r.read()
        ''',
        False,
    ),
    (
        "a Request built with UNtagged headers is still caught, by rail 1",
        f'''
        from urllib.request import Request, urlopen
        def go():
            url = "{_OURS}"
            req = Request(url, headers={{"Accept": "application/json"}})
            with urlopen(req, timeout=5) as r:
                return r.read()
        ''',
        True,
    ),
    (
        "a loop variable is reported, not trusted",
        f'''
        from urllib.request import urlopen
        def go(paths):
            for url in paths:
                with urlopen(url, timeout=5) as r:
                    yield r.read()
        ''',
        True,
    ),
]


@pytest.mark.parametrize(
    "why,source,expect_offender",
    [pytest.param(w, s, e, id=w[:48]) for w, s, e in RAIL2_CASES],
)
def test_rail_two_resolves_the_name(tmp_path, why, source, expect_offender):
    sites = _sites_for(tmp_path, source)
    assert bool(sites) is expect_offender, f"{why}\n  got: {sites}"


def test_a_name_does_not_borrow_another_function_s_request(tmp_path):
    """The case that proves resolution is SCOPED, not a file-wide name lookup.

    Both functions spell it `url`. One builds a Request; the other is handed a
    string. A whole-file map — the obvious first implementation, and the one I
    wrote first — lets the Request vouch for the parameter and reports nothing.
    Two of the six real sites (`calibration_scorecard.fetch`,
    `calibration_threshold_table.fetch`) have exactly this shape.
    """
    source = textwrap.dedent(
        f'''
        from urllib.request import Request, urlopen
        from app.utils.agent_origin import tagged
        def tagged_caller():
            url = Request("{_OURS}", headers=tagged("{_OURS}"))
            with urlopen(url, timeout=5) as r:  # CLEAN
                return r.read()
        def untagged_caller(url: str):
            with urlopen(url, timeout=5) as r:  # OFFENDER
                return r.read()
        '''
    )
    sites = _sites_for(tmp_path, source)
    assert len(sites) == 1, sites

    # Anchor on the source line the census names, not on a hand-counted offset —
    # a wrong constant here would read as a failure of the rule.
    reported = int(sites[0].split(":")[1].split()[0])
    assert "# OFFENDER" in source.splitlines()[reported - 1], (
        f"census pointed at line {reported}: {source.splitlines()[reported - 1]!r}"
    )


def test_a_nested_function_does_not_resolve_against_its_enclosing_scope(tmp_path):
    """Sibling functions cannot tell a correct scope map from a broken one.

    `ast.walk` is breadth-first, so an outer function is walked BEFORE the
    function nested inside it, and every node of the inner body is visited
    twice. Recording the first writer (`setdefault`) therefore files inner nodes
    under the OUTER scope — and for two functions that merely sit side by side
    the two spellings are indistinguishable, which is how the first version of
    this test passed against both.

    Only nesting separates them. Here the outer `url` is a tagged Request and
    the inner `url` is a parameter; under the broken map the outer vouches for
    the inner and the call is reported clean.
    """
    source = textwrap.dedent(
        f'''
        from urllib.request import Request, urlopen
        from app.utils.agent_origin import tagged
        def outer():
            url = Request("{_OURS}", headers=tagged("{_OURS}"))
            def inner(url):
                with urlopen(url, timeout=5) as r:  # OFFENDER
                    return r.read()
            with urlopen(url, timeout=5) as r:  # CLEAN
                return inner, r.read()
        '''
    )
    sites = _sites_for(tmp_path, source)
    assert len(sites) == 1, sites
    reported = int(sites[0].split(":")[1].split()[0])
    assert "# OFFENDER" in source.splitlines()[reported - 1], (
        f"census pointed at line {reported}: {source.splitlines()[reported - 1]!r}"
    )


def test_the_espn_fallback_stays_header_free(monkeypatch):
    """`reconcile_mlb_schedule` measured that ESPN 403s a urllib call WITH headers.

    Routing it through the carrier for the guard's benefit must not put a header
    back on that wire. It does not, because ESPN is not our host — but the whole
    point of #4747 is that "must not" reasoning in a comment is worth less than
    an assertion, so this asserts it with an agent deliberately NAMED.
    """
    monkeypatch.setenv("BL_AGENT", "latency")
    espn = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"

    assert tagged(espn) == {}
    assert tagged(espn, {"Accept": "application/json"}) == {"Accept": "application/json"}
    assert "User-Agent" not in tagged(espn)


def test_the_carrier_is_reached_by_the_search_touching_probes():
    """The subset #4642 says nobody could name: probes that hit search/typeahead.

    These are the only scripts where the tag has TEETH rather than being
    attribution, so they are asserted by name as well as by the sweep above —
    a rename that drops one out of the directory rule would otherwise be silent.
    """
    search_probes = [
        p
        for p in ALL_SCRIPTS
        if "events/search" in p.read_text() or "/typeahead" in p.read_text()
    ]
    assert len(search_probes) >= 8, [p.name for p in search_probes]
    untagged = [
        p.name
        for p in search_probes
        if "agent_origin" not in p.read_text()
        # a script may only MENTION the endpoint in prose; it needs the carrier
        # only if it actually builds a call
        and any(
            marker in p.read_text()
            for marker in ("urllib.request.Request", "httpx.", "requests.", '"curl"')
        )
    ]
    assert untagged == [], f"search/typeahead probes still voting untagged: {untagged}"

    # PER SITE, not per file. `test_search_origin_channel_p118` asks whether a
    # script DECLARES itself machine traffic, which is a whole-file question: a
    # script could satisfy it with a `tagged()` call on its db-query while still
    # firing an untagged search URL from a different line. Closed here, where
    # the offender list is already computed site by site.
    leaky = [site for p in search_probes for site in _untagged_sites(p)]
    assert leaky == [], (
        "a search/typeahead probe declares itself machine traffic but still has "
        "an untagged call site — the file passes the class guard while the "
        "request votes:\n  " + "\n  ".join(leaky)
    )


def test_every_carrier_import_sits_below_its_sys_path_bootstrap():
    """`app` is only importable after the path insert — and order is the bug.

    This is the failure the AST rule above cannot see: a script can be perfectly
    tagged and still raise ImportError the next time it is run, because the
    import was placed above the line that makes `app` reachable. Nothing catches
    it until someone runs the script for real, which for probe tooling can be
    weeks.

    Checked statically here. latency/305 also executed all 93 edited prologues
    in a subprocess from a hostile cwd (`/tmp`) — 0 failures — but 93
    subprocesses is not a thing to spend CI time on every run.
    """
    offenders = []
    for path in ALL_SCRIPTS:
        src = path.read_text()
        if "from app.utils.agent_origin import" not in src:
            continue
        import_at = src.index("from app.utils.agent_origin import")
        inserts = [m.end() for m in re.finditer(r"^\s*\w*sys\.path\.insert", src, re.M)]
        if not inserts:
            offenders.append(f"{path.name}: imports the carrier with no sys.path insert")
        elif not any(i < import_at for i in inserts):
            offenders.append(f"{path.name}: carrier imported ABOVE every sys.path insert")
    assert offenders == [], "\n  ".join(offenders)


def test_no_script_hand_spells_the_header():
    """One definition, once — the drift `agent_origin`'s docstring exists for.

    Six scripts spelled `X-Bainluck-Origin` as a literal. A sender and a reader
    that disagree by one character produce no error anywhere.
    """
    offenders = []
    for path in ALL_SCRIPTS:
        for lineno, line in enumerate(path.read_text().split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "bainluck-origin" not in stripped.lower():
                continue
            # a docstring/comment may name it; an ASSIGNED literal may not
            if re.search(r"""["']x-bainluck-origin["']\s*:""", stripped, re.I):
                offenders.append(f"{path.name}:{lineno}")
    assert offenders == [], (
        "the header is spelled by hand instead of imported as ORIGIN_HEADER: "
        + ", ".join(offenders)
    )


@pytest.mark.parametrize("path", _http_gate_scripts(), ids=lambda p: p.name)
def test_gate_scripts_import_cleanly(path: pathlib.Path):
    """The import sits below a `sys.path` insert; a bad placement is an
    ImportError that only shows up when the gate is next run for real."""
    proc = subprocess.run(
        [sys.executable, "-c", f"import ast,sys; ast.parse(open({str(path)!r}).read())"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    src = path.read_text()
    insert_at = src.index("sys.path.insert")
    import_at = src.index("from app.utils.agent_origin import tagged")
    assert import_at > insert_at, (
        f"{path.name}: agent_origin imported before sys.path is set up"
    )


# ---------------------------------------------------------------------------
# The tag must never buy privilege
# ---------------------------------------------------------------------------


def test_rate_limiter_does_not_read_the_origin_header():
    """`x-bainluck-origin` is caller-supplied and forgeable. It is fit for
    saying WHO, never for granting WHAT. If an allowlist is ever keyed on it,
    this fails — deliberately."""
    src = (BACKEND / "app" / "utils" / "rate_limit.py").read_text()
    assert "bainluck-origin" not in src.lower(), (
        "rate_limit.py reads the forgeable origin header — an allowlist for the "
        "entire internet; see agent_origin.py's module docstring"
    )
