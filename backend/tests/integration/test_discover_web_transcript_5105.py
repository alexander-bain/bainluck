"""#5105 — the server half of the web/server connection gate.

The route tests (``test_route_feed_opening_seating_5105.py``) drive the REAL
``get_feed`` and stop at its JSON; the page tests
(``frontend/__tests__/discover/discoverPageOpeningEdition5105.test.tsx``) mount
the REAL Discover page and answer it with payloads they author themselves. Both
halves are accepted; nothing yet carried one exact server response across.

This file closes that boundary from the server side. It drives the same harness
(dict Redis, mocked DB, the planted display-chain deck — imported, not copied)
through six short fixed-clock sequences, and records every response as the
route produced it: the request the page is expected to issue (path, query,
session header), the status, the cache headers and the RAW body text. The page
test (``frontend/__tests__/discover/discoverWebServerTranscript5105.test.tsx``)
then mounts the real page with the real ``fetchFeed``, refuses any request
that is not byte-for-byte the recorded one, and answers it with exactly these
bytes. Nothing is retyped on either side.

Synthetic contract data from the one source, not a capture: no provider, no
production, no replay framework. Repeatable with the existing runner:

    DISCOVER_5105_TRANSCRIPT_WRITE=1 python3 -m pytest \\
        tests/integration/test_discover_web_transcript_5105.py

writes the fixture; without the variable the test regenerates it and fails on
any drift, so the committed file is always what this source serves.

Expected server identities are literal here too, so a transcript that drifted
into nonsense cannot be written in the first place.
"""

from __future__ import annotations

import json
import os
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pytest

from app.utils import principal_independent_cache as _pic
from tests.integration.test_route_feed_opening_seating_5105 import (  # noqa: F401  (fixtures)
    CROSSING,
    T0,
    T1,
    F,
    _DictRedis,
    _drain,
    _drop_base,
    _harness,
    _ids,
    _install,
    _plant,
    fut,
    live,
    seated,
    tourney,
)

TRANSCRIPT = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "__tests__"
    / "fixtures"
    / "discover5105ServerTranscript.json"
)
WRITE_ENV = "DISCOVER_5105_TRANSCRIPT_WRITE"

#: The id the page test pins ``crypto.randomUUID`` to: a fresh visitor's first
#: request goes out without a session (shared-anon), every later one with this.
SESSION = "sess-5105-web-gate"

#: Response headers the page reads (``reportFeedTelemetry`` and friends) and
#: that do not vary run to run.
KEPT_HEADERS = ("content-type", "x-feed-cache", "x-feed-singleflight")


def _query(*, offset: int, edition: str | None) -> str:
    """The query ``fetchFeed`` builds for the web Discover page: ``offset`` is
    omitted at 0 (``if (params?.offset)``), ``edition`` appended last and
    form-encoded by ``URLSearchParams``."""
    parts = ["limit=20"]
    if offset:
        parts.append(f"offset={offset}")
    parts.append("event_pct=0.15")
    if edition:
        parts.append(f"edition={quote_plus(edition)}")
    return "/api/feed?" + "&".join(parts)


class _FixedMonotonic:
    """``time`` for one module, with ``monotonic`` read off the step clock."""

    def __init__(self, clock):
        self._clock = clock

    def monotonic(self):
        return self._clock.now.timestamp()

    def __getattr__(self, name):
        return getattr(time, name)


class _Recorder:
    def __init__(self, client, clock, monkeypatch):
        self.client = client
        self.clock = clock
        self.steps: list[dict] = []
        # The route also stamps cache metadata (``cache.built_at``, ages) from
        # the wall clock; it reads the step's clock too, so a body is a
        # function of its inputs and the committed file can be drift-checked.
        # Shared-artifact ages run on ``time.monotonic`` inside
        # ``principal_independent_cache``; under a fixed clock no time passes
        # within a request either (the real one ages them by microseconds).
        monkeypatch.setattr(time, "time", lambda: clock.now.timestamp())
        monkeypatch.setattr(_pic, "time", _FixedMonotonic(clock))

    async def step(self, label, *, at, offset=0, edition=None, session=True):
        self.clock.now = at
        url = _query(offset=offset, edition=edition)
        headers = {"x-session-id": SESSION} if session else {}
        resp = await self.client.get(url, headers=headers)
        await _drain()
        assert resp.status_code == 200, resp.text
        self.steps.append(
            {
                "label": label,
                "clock": at.isoformat(),
                "request": {"url": url, "session": SESSION if session else None},
                "status": resp.status_code,
                "headers": {k: resp.headers[k] for k in KEPT_HEADERS if k in resp.headers},
                "body": resp.text,
            }
        )
        return resp.headers, resp.json()


# --- the six sequences ------------------------------------------------------

#: Thin supply: three eligible cards spread through 30 ordinary live games.
SPARSE33 = [live(1), fut(0), live(2), fut(1), live(3), fut(2)] + [live(i) for i in range(4, 31)]
SPARSE33_SEATED = F(0, 1, 2) + [f"event:{i}" for i in range(1, 31)]


async def sparse_opening(client, monkeypatch, clock):
    _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, SPARSE33)
    rec = _Recorder(client, clock, monkeypatch)
    _, p0 = await rec.step("page0", at=T0, session=False)
    assert _ids(p0["items"]) == SPARSE33_SEATED[:20]
    assert p0["continuation_start"] == 3 and p0["total"] == 33
    _, p1 = await rec.step("page1", at=T0 + timedelta(seconds=30), offset=20, edition=p0["edition"])
    assert p1["edition_status"] == "pinned" and p1["edition"] == p0["edition"]
    assert _ids(p1["items"]) == SPARSE33_SEATED[20:]
    assert p1["continuation_start"] == 3 and p1["has_more"] is False
    return rec.steps


#: No eligible card at all: every card is an ordinary live game.
ALL_LIVE = [live(i) for i in range(1, 26)]


async def boundary_zero(client, monkeypatch, clock):
    _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, ALL_LIVE)
    rec = _Recorder(client, clock, monkeypatch)
    _, p0 = await rec.step("page0", at=T0, session=False)
    assert _ids(p0["items"]) == _ids(ALL_LIVE)[:20]
    assert p0["continuation_start"] == 0
    _, p1 = await rec.step("page1", at=T0 + timedelta(seconds=30), offset=20, edition=p0["edition"])
    assert p1["edition_status"] == "pinned" and p1["continuation_start"] == 0
    assert _ids(p1["items"]) == _ids(ALL_LIVE)[20:]
    return rec.steps


#: The current deck after the tournament started: a newcomer joined at seat 2.
CROSSING_NEW = [fut(0), tourney("t-open"), fut(500)] + [fut(i) for i in range(1, 44)]
#: Composed at T1: the live tournament leaves the first ten for seat 11.
CROSSING_NEW_SEATED = F(0, 500, *range(1, 9)) + ["tournament:t-open"] + F(*range(9, 44))


async def tournament_start(client, monkeypatch, clock):
    fake = _install(monkeypatch, _DictRedis())
    holder = _plant(monkeypatch, CROSSING)
    rec = _Recorder(client, clock, monkeypatch)
    _, p0 = await rec.step("page0", at=T0, session=False)
    old = p0["edition"]
    assert _ids(p0["items"]) == _ids(CROSSING)[:20] and "continuation_start" not in p0

    # The tournament starts and a newcomer joins; the base has turned over.
    holder["deck"] = CROSSING_NEW
    _drop_base(fake)
    _, retired = await rec.step("retired-page1", at=T1, offset=20, edition=old)
    assert retired["edition_status"] == "expired" and retired["edition"] != old
    assert _ids(retired["items"]) == CROSSING_NEW_SEATED[20:40]
    new = retired["edition"]

    _, fresh = await rec.step("replacement-page0", at=T1 + timedelta(seconds=2))
    assert "edition_status" not in fresh and fresh["edition"] == new
    assert _ids(fresh["items"]) == CROSSING_NEW_SEATED[:20]

    _, p1 = await rec.step("page1", at=T1 + timedelta(seconds=30), offset=20, edition=new)
    assert p1["edition_status"] == "pinned" and p1["edition"] == new
    assert _ids(p1["items"]) == CROSSING_NEW_SEATED[20:40] and p1["has_more"] is True

    # The page's look-ahead: its window (40) is within reach of what it holds.
    _, p2 = await rec.step("lookahead-page2", at=T1 + timedelta(seconds=31), offset=40, edition=new)
    assert p2["edition_status"] == "pinned" and p2["has_more"] is False
    assert _ids(p2["items"]) == CROSSING_NEW_SEATED[40:]
    return rec.steps


def _conflicted(i):
    """A live game whose own start is still ahead: conflicting typed fields,
    unexempt — a deck carrying it in its opening is unsupported."""
    card = live(i)
    card["data"]["commence_time"] = (T1 + timedelta(hours=2)).isoformat()
    return card


async def unavailable_replacement(client, monkeypatch, clock):
    fake = _install(monkeypatch, _DictRedis())
    holder = _plant(monkeypatch, CROSSING)
    rec = _Recorder(client, clock, monkeypatch)
    _, p0 = await rec.step("page0", at=T0, session=False)
    old = p0["edition"]

    holder["deck"] = CROSSING_NEW
    _drop_base(fake)
    _, retired = await rec.step("retired-page1", at=T1, offset=20, edition=old)
    assert retired["edition_status"] == "expired"

    # Before the replacement page zero arrives, the current deck turns
    # unsupported (a conflicting game in its opening) and its base turns over.
    holder["deck"] = [_conflicted(900)] + CROSSING_NEW
    _drop_base(fake)
    headers, refused = await rec.step("unavailable-page0", at=T1 + timedelta(seconds=2))
    assert refused["cache"]["status"] == "unavailable"
    assert refused["cache"]["reason"] == "opening_unsupported"
    assert refused["items"] == [] and "edition" not in refused

    # The conflict clears; the reader's Retry recovers the current deck.
    holder["deck"] = CROSSING_NEW
    _drop_base(fake)
    _, recovered = await rec.step("retry-page0", at=T1 + timedelta(seconds=20), edition=old)
    assert recovered["edition_status"] == "expired"
    assert recovered["edition"] == retired["edition"]
    assert _ids(recovered["items"]) == CROSSING_NEW_SEATED[:20]
    return rec.steps


#: A full, all-eligible opening: no continuation, so no heading.
FULL40 = [fut(i) for i in range(0, 40)]


async def full_opening_back(client, monkeypatch, clock):
    _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, FULL40)
    rec = _Recorder(client, clock, monkeypatch)
    _, p0 = await rec.step("page0", at=T0, session=False)
    assert _ids(p0["items"]) == F(*range(0, 20)) and "continuation_start" not in p0
    token = p0["edition"]
    # Back: the restored page revalidates its edition, still as the shared-anon
    # first request (no request has minted a session yet).
    _, again = await rec.step(
        "back-revalidate-page0", at=T0 + timedelta(minutes=1), edition=token, session=False
    )
    assert again["edition_status"] == "pinned" and again["edition"] == token
    assert _ids(again["items"]) == F(*range(0, 20))
    _, p1 = await rec.step("page1", at=T0 + timedelta(minutes=1, seconds=30), offset=20, edition=token)
    assert p1["edition_status"] == "pinned" and _ids(p1["items"]) == F(*range(20, 40))
    return rec.steps


async def empty_vs_refusal(client, monkeypatch, clock):
    fake = _install(monkeypatch, _DictRedis())
    holder = _plant(monkeypatch, [])
    rec = _Recorder(client, clock, monkeypatch)
    _, empty = await rec.step("complete-empty-page0", at=T0, session=False)
    assert empty["items"] == [] and empty["total"] == 0
    assert empty.get("cache", {}).get("status") != "unavailable"

    holder["deck"] = [_conflicted(900)] + [fut(i) for i in range(0, 30)]
    _drop_base(fake)
    # A different fresh visitor whose own first page zero is refused.
    _, refused = await rec.step("refused-page0", at=T0 + timedelta(minutes=1), session=False)
    assert refused["cache"]["status"] == "unavailable"
    assert refused["cache"]["reason"] == "opening_unsupported"

    holder["deck"] = [fut(i) for i in range(0, 30)]
    _drop_base(fake)
    _, recovered = await rec.step("retry-page0", at=T0 + timedelta(minutes=2), session=False)
    assert _ids(recovered["items"]) == F(*range(0, 20))
    return rec.steps


SCENARIOS = {
    "sparse_opening": sparse_opening,
    "boundary_zero": boundary_zero,
    "tournament_start": tournament_start,
    "unavailable_replacement": unavailable_replacement,
    "full_opening_back": full_opening_back,
    "empty_vs_refusal": empty_vs_refusal,
}


def _render(scenarios: dict) -> str:
    doc = {
        "about": (
            "#5105 web/server connection gate: exact get_feed responses (served "
            "switch ON, fixed request clocks, dict Redis, mocked DB) for the real "
            "Discover page to consume. Generated, never hand-edited."
        ),
        "generator": "backend/tests/integration/test_discover_web_transcript_5105.py",
        "regenerate": (
            f"cd backend && {WRITE_ENV}=1 python3 -m pytest "
            "tests/integration/test_discover_web_transcript_5105.py"
        ),
        "session": SESSION,
        "scenarios": scenarios,
    }
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


@pytest.mark.parametrize("name", list(SCENARIOS))
async def test_each_sequence_is_served_as_the_page_expects(client, monkeypatch, seated, name):
    """Every sequence runs on its own fresh harness and its server-side facts
    hold (the literal asserts inside each builder)."""
    steps = await SCENARIOS[name](client, monkeypatch, seated)
    assert steps and all(s["status"] == 200 for s in steps)


async def test_the_committed_transcript_is_what_this_source_serves(client, monkeypatch, seated):
    scenarios = {}
    for name, build in SCENARIOS.items():
        # Each sequence starts from nothing, exactly as in its own test above.
        from app.utils import request_cache as _rc

        _rc._reset_last_good_for_tests()
        _rc._reset_inflight_for_tests()
        scenarios[name] = await build(client, monkeypatch, seated)
    rendered = _render(scenarios)

    if os.environ.get(WRITE_ENV) == "1":
        TRANSCRIPT.parent.mkdir(parents=True, exist_ok=True)
        TRANSCRIPT.write_text(rendered)
    assert TRANSCRIPT.exists(), f"missing {TRANSCRIPT}; regenerate with {WRITE_ENV}=1"
    assert TRANSCRIPT.read_text() == rendered, (
        "the committed transcript is not what get_feed serves now; "
        f"regenerate with {WRITE_ENV}=1 and review the diff"
    )
