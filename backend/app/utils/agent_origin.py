"""Outbound `x-bainluck-origin` tagging for our own Python probes.

Notice 39 / #1916: every production read our fleet makes should say whether a
person or a lane made it. `tools/bl-agent-curl.sh` (rung 1) does that for the
`curl` an agent types by hand. This module is the same contract for the other
half of the fleet's traffic — the ~90 scripts under `backend/scripts/` — which
no shell shadow can reach.

FOUR RAILS, BECAUSE THE FLEET HAS FOUR (#4642)
-----------------------------------------------
The sweep that tagged the directory found the traffic does not leave by one
door. `tagged()` serves the first three, `curl_args()` the fourth:

  1. `urllib.request.Request(url, headers=...)`     — 81 sites
  2. `urlopen(<a URL>)`, which carries no headers at all and had to be
     converted to a Request before it could be tagged
  3. `httpx` / `requests` verbs                     — 26 sites
  4. `subprocess.run(["curl", ...])`                — 12 sites, and the one
     rung 1 can NEVER cover: it exports a shell FUNCTION, and a subprocess
     execs the binary

WHAT THE TAG BUYS, STATED HONESTLY — AND IT DIFFERS BY ROUTE
-------------------------------------------------------------
On the SEARCH route the tag has teeth: `routes/events.py:_request_is_automation`
suppresses the search-query log write and the trending vote, so an untagged
probe does not merely add a row, it VOTES, and the head warmer then spends real
work warming our own specimens. Twelve scripts here reach `/api/events/search`
or `/api/events/typeahead`, and for those this module is the whole point.

Everywhere else — overwhelmingly `/api/admin/db-query` — the tag is
ATTRIBUTION ONLY, and deliberately so:

  * It buys no rate-limit relief. Admin paths are keyed on a hash of the
    admin token (300/min) and that bucket outranks the trusted-address ceiling
    in `utils/rate_limit.py`, so tagging cannot and must not change what a
    script is allowed to spend.
  * The header is caller-supplied and therefore forgeable. It is fit for saying
    WHO, never for granting WHAT — see the "CEILING, NEVER EXEMPTION" note in
    `utils/rate_limit.py`. Nothing in this module should ever be read by an
    authorization path.

Applying it to a third-party call costs nothing rather than needing a judgment
call per site: `is_our_host` decides at RUNTIME, so the static rule the guard
enforces stays the simple one — every outbound call goes through the carrier.

THE HEADER NAME LIVES HERE, ONCE
--------------------------------
`routes/events.py` reads this constant rather than its own literal. A sender and
a reader that disagree by one character produce no error anywhere: every probe
looks tagged, every row still gets written, and the drift is invisible until
someone counts. One definition removes that failure mode by construction.
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, List, Mapping, Optional
from urllib.parse import urlsplit

#: The wire name. `routes/events.py` imports this; do not re-spell it anywhere.
ORIGIN_HEADER = "x-bainluck-origin"

#: The one value that is honoured POSITIVELY — it keeps the search-log row.
#: Use it when you mean to measure as a person.
ORIGIN_USER = "user"

_OUR_HOSTS = ("bainluck.com", "localhost", "127.0.0.1")


def resolve_agent() -> Optional[str]:
    """The agent name for THIS call, read from ``BL_AGENT`` at call time, or None.

    Read at call time, never captured at import time. The shell helper shipped
    with a comment about this because the obvious shape fails silently: a name
    baked in at load produces an EMPTY header, the backend's ``if not raw``
    reads empty as a person, and the call votes in the search head exactly as it
    did untagged — while the author has every reason to believe it is tagged.
    A module-level constant here would reintroduce that for any script that sets
    ``BL_AGENT`` after import.

    UNSET OR BLANK RETURNS None, AND THE CALLER THEN ADDS NOTHING (notice 39
    guard 1). An earlier draft substituted ``agent-unnamed`` on the reasoning
    that being unnamed is not evidence of humanity. That reasoning is right
    about the WORLD and wrong about the DIRECTION of the failure, which is what
    decides a default:

      * Tagging an unnamed caller SUPPRESSES its search-log row
        (`routes/events.py:_request_is_automation` treats any non-"user" value
        as automation). So a default that tags makes every un-configured caller
        — a human running a script by hand included — vanish from the table.
        That drains the warm head silently and leaves nothing behind to notice.
      * Not tagging leaves a row we can see, count and later attribute.

    `_request_is_automation`'s own docstring picks the same direction for the
    same reason: it FAILS TOWARD LOGGING. A default is a guess, and the only
    safe guess is the one whose mistakes are visible.
    """
    return (os.environ.get("BL_AGENT") or "").strip() or None


def _host_of(url: str) -> str:
    """Lowercased hostname of ``url``, or "" if it has none."""
    try:
        # A scheme-relative or bare-host string has no netloc until it has a
        # scheme, so give it one rather than string-munging the URL by hand.
        split = urlsplit(url if "//" in url else f"//{url}")
        return (split.hostname or "").lower()
    except ValueError:
        # An unparseable URL is not ours; refusing to tag is the safe direction.
        return ""


def is_our_host(url: str) -> bool:
    """True when ``url`` points at a host we own.

    Our probes call Kalshi, Polymarket, ESPN and GitHub from the same scripts.
    An internal header naming our lanes has no business on a third party's wire,
    so this matches the parsed HOST as a suffix. A substring test would have
    tagged ``https://example.com/?ref=bainluck.com``.
    """
    host = _host_of(url)
    if not host:
        return False
    return any(host == h or host.endswith(f".{h}") for h in _OUR_HOSTS)


def origin_headers(
    url: str, existing: Optional[Mapping[str, str]] = None
) -> Dict[str, str]:
    """Headers to ADD so ``url`` says who sent it. Possibly empty.

    Returns a new dict; the caller merges it. Empty means "add nothing", which
    is the correct answer for a third-party host, an already-tagged request, or
    a caller who never named itself (see `resolve_agent`).

    An explicit header from the caller always wins. A request carrying two
    `x-bainluck-origin` values that disagree about whether its sender is a
    person is worse than one carrying none: the backend reads ``.get()``, i.e.
    the first, so the caller's stated intent could silently lose to this
    module's default.
    """
    if not is_our_host(url):
        return {}

    lowered = {str(k).lower() for k in (existing or {})}
    if ORIGIN_HEADER in lowered:
        return {}

    who = resolve_agent()
    if who is None:
        # Pass through untouched: no origin header AND no bot User-Agent. Both
        # halves matter — a `BainLuckBot/1.0` UA with no origin header is a
        # request that looks automated in the router log while still voting in
        # the search head, which is the worst of both readings.
        return {}

    headers = {ORIGIN_HEADER: who}
    # The router log records the UA, which is what makes fleet traffic legible
    # in a log window without a database read. Never clobber a caller's own.
    if "user-agent" not in lowered:
        headers["User-Agent"] = f"BainLuckBot/1.0 ({who})"
    return headers


def tagged(url: str, headers: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """``headers`` plus the origin tag — the one-call form for request builders."""
    merged = dict(headers or {})
    merged.update(origin_headers(url, merged))
    return merged


def curl_args(url: str, existing: Optional[Iterable[str]] = None) -> List[str]:
    """``-H`` arguments to SPLICE into a ``subprocess`` curl argv. Possibly empty.

    THE SHELL SHADOW DOES NOT REACH HERE, AND THAT IS THE WHOLE POINT
    ----------------------------------------------------------------
    Rung 1 tags the ``curl`` an agent types by exporting a shell FUNCTION.
    ``subprocess.run(["curl", ...])`` executes the curl BINARY directly: no
    shell is involved, so no function can be interposed and the call goes out
    untagged. Ten scripts under ``backend/scripts/`` fire this way and two of
    them hit ``/api/events/typeahead``, so this is not a hypothetical rail —
    it is the one the shadow can never cover.

    Returns a list to splice, never a mutated argv, for the same reason
    `origin_headers` returns a dict to merge: the caller owns its own command.

    Every rule `origin_headers` applies applies here, and deliberately so — a
    second answer to "should this call be tagged?" is a second thing to drift.
    Third-party host, unnamed caller, or an argv that already states an origin
    all yield ``[]``.
    """
    already = False
    for arg in existing or ():
        # `-H x-bainluck-origin: lane` arrives as its own argv element, so the
        # header name is a PREFIX of the value string, not the whole of it.
        if str(arg).lower().lstrip().startswith(f"{ORIGIN_HEADER}:"):
            already = True
            break
    if already:
        return []

    headers = origin_headers(url)
    args: List[str] = []
    for name, value in headers.items():
        args += ["-H", f"{name}: {value}"]
    return args
