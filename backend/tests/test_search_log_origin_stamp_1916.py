"""THE SEARCH LOG RECORDS WHERE A QUERY CAME FROM, at write time. #1916 step 3.

The column landed in `search_log_origin` (the migration) and the model; this is
the WRITE. Until it exists, `search_query_logs.origin` is NULL on every row and
the consumer that wants it — `_USER_HEAD_SQL` in `tasks/search_head_warmer.py` —
has to keep inferring humanity from `session_id IS NOT NULL`, which is a side
effect of client code and not provenance. LAT-P102 measured what the inference
costs: **13 of 4,257 rows in the 30-day window read as attested.** The warm head
is elected out of those 13.

## The three values, and why the asymmetry is deliberate

    NULL     no writer stamped this row — every row predating this sha, and any
             future writer that logs without stamping. Unknown, and readable as
             unknown (gotcha #53).
    'user'   the request reached the stamp on a path that stamps and asserted no
             automation. An assertion this system MADE.
    <agent>  the verbatim `x-bainluck-origin` value, lowercased, truncated to the
             column's 64.

`'user'` on an absent header is not the default-by-absence #1916 exists to end:
a row only reaches `_origin_for_log` after `_record_search_query`'s automation
gate let it through, so the value records a decision rather than a silence. The
absence that must stay unreadable-as-human is the one that never reaches this
function at all, and that one stays NULL.

## Why the agent branch is unreachable today, and is written and tested anyway

`_record_search_query` returns before the dispatch for any request
`_request_is_automation` recognises, so at this sha the only value HTTP can put
in the column is `'user'`. Writing the literal `'user'` would be shorter. Notice
39 is explicit that the direction of travel is the opposite — "tagged rows stay
in the table and are COUNTED, never dropped" — and on the day the suppression is
relaxed, the short version does not fail: it stamps the entire fleet `'user'`,
in an append-only table, with no way afterwards to tell those rows from a
person's. The derivation cannot do that, and
`test_a_tagged_request_would_stamp_its_agent_name` is what keeps it derived.
"""

from __future__ import annotations

import inspect

import pytest

from app.routes.events import (
    _log_search_query,
    _origin_for_log,
    _record_search_query,
    _request_is_automation,
)
from app.utils.agent_origin import ORIGIN_HEADER, ORIGIN_USER


class _Req:
    """The smallest object the two header readers accept."""

    def __init__(self, headers=None, cookies=None):
        self.headers = headers if headers is not None else {}
        self.cookies = cookies or {}
        self.state = type("S", (), {})()


class _Boom:
    """A request whose header read raises — the failure both readers swallow."""

    class _H:
        def get(self, *a, **k):
            raise RuntimeError("header store is gone")

    headers = _H()
    cookies: dict = {}
    state = type("S", (), {})()


# ---------------------------------------------------------------------------
# 1. The value
# ---------------------------------------------------------------------------


class TestTheStampedValue:

    def test_no_header_stamps_the_positive_assertion(self):
        assert _origin_for_log(_Req()) == ORIGIN_USER

    def test_an_explicit_user_header_stamps_user(self):
        assert _origin_for_log(_Req({ORIGIN_HEADER: "user"})) == ORIGIN_USER

    def test_a_tagged_request_would_stamp_its_agent_name(self):
        """🔴 THE REASON THE VALUE IS DERIVED AND NOT THE LITERAL `'user'`.

        Unreachable over HTTP at this sha — the automation gate returns first —
        and that is exactly why it is pinned. The day notice 39's "counted, never
        dropped" lands, the shortcut labels the fleet human forever.
        """
        assert _origin_for_log(_Req({ORIGIN_HEADER: "lane1"})) == "lane1"

    def test_the_value_is_lowercased(self):
        """One agent, one row-group. `Lane1` and `lane1` must not be two."""
        assert _origin_for_log(_Req({ORIGIN_HEADER: "Lane1"})) == "lane1"

    def test_whitespace_is_stripped(self):
        assert _origin_for_log(_Req({ORIGIN_HEADER: "  lane1  "})) == "lane1"

    def test_a_blank_header_reads_as_a_person(self):
        """`resolve_agent` returns None for an unset `BL_AGENT` and the caller
        then sends nothing — but a hand-rolled sender can still put an empty
        string on the wire. `_request_is_automation` reads empty as a person, so
        the stamp must agree with it or the row's provenance contradicts the
        decision to keep the row."""
        assert _origin_for_log(_Req({ORIGIN_HEADER: ""})) == ORIGIN_USER
        assert not _request_is_automation(_Req({ORIGIN_HEADER: ""}))

    def test_a_long_value_is_truncated_to_the_columns_width(self):
        """`String(64)`. A guard that refuses to store freezes the old value;
        this one stores what fits rather than raising on a caller's typo."""
        assert len(_origin_for_log(_Req({ORIGIN_HEADER: "x" * 200}))) == 64

    def test_no_request_at_all_stamps_a_person(self):
        """Same direction as `_request_is_automation`, which returns False for
        `None`: an in-process call with no HTTP request reads as a person, and a
        bug here that over-suppresses drains the warm head silently."""
        assert _origin_for_log(None) == ORIGIN_USER

    def test_a_raising_header_store_does_not_break_search(self):
        assert _origin_for_log(_Boom()) == ORIGIN_USER


# ---------------------------------------------------------------------------
# 2. The stamp reaches the row
# ---------------------------------------------------------------------------


class TestTheStampReachesTheWrite:

    def test_the_recorder_passes_an_origin(self):
        """The seam. Without this the helper above is dead code and every row
        keeps writing NULL — which is what the pre-#1916 tree already did, so no
        other test in this file would fail."""
        src = inspect.getsource(_record_search_query)
        assert "origin=_origin_for_log(request)" in src, (
            "the recorder must stamp from the SAME request the automation gate "
            "read, in the same call"
        )

    def test_the_writer_puts_it_on_the_row(self):
        src = inspect.getsource(_log_search_query)
        assert "origin=" in src, "the ORM row must carry the column"

    def test_the_writer_truncates_defensively(self):
        """Belt and braces with `_origin_for_log`'s own bound: the writer is
        reachable from callers that never went through the helper."""
        src = inspect.getsource(_log_search_query)
        assert "origin[:64]" in src

    def test_an_unstamped_caller_writes_null_not_user(self):
        """🔴 THE ONE THAT MUST NEVER FLIP. `origin` defaults to `None`, and a
        `None` must reach the column as NULL — 'nobody stamped this' — never as
        `'user'`. A default of `ORIGIN_USER` on this parameter would fabricate
        human rows for every caller that does not stamp, in an append-only
        table."""
        sig = inspect.signature(_log_search_query)
        assert sig.parameters["origin"].default is None


# ---------------------------------------------------------------------------
# 3. The stamp and the gate cannot disagree
# ---------------------------------------------------------------------------


class TestTheStampAgreesWithTheGate:
    """Whatever the gate lets through, the stamp must describe truthfully.

    These two functions read the same header for opposite purposes, so the
    failure that matters is not either one alone — it is drift between them.
    """

    @pytest.mark.parametrize(
        "headers",
        [
            {},
            {ORIGIN_HEADER: ""},
            {ORIGIN_HEADER: "user"},
            {ORIGIN_HEADER: "USER"},
            {ORIGIN_HEADER: " user "},
        ],
    )
    def test_every_request_the_gate_keeps_stamps_user(self, headers):
        req = _Req(headers)
        assert not _request_is_automation(req), "precondition: the gate keeps it"
        assert _origin_for_log(req) == ORIGIN_USER

    @pytest.mark.parametrize("agent", ["lane1", "bus", "flow-sentinel", "lane1b"])
    def test_every_request_the_gate_drops_would_stamp_its_own_name(self, agent):
        req = _Req({ORIGIN_HEADER: agent})
        assert _request_is_automation(req), "precondition: the gate drops it"
        assert _origin_for_log(req) == agent

    def test_the_two_readers_share_one_header_name(self):
        """A sender and a reader that drift by one character raise nothing
        anywhere — every probe looks tagged and every row is still written.
        Both read the imported constant, never a literal."""
        assert ORIGIN_HEADER not in inspect.getsource(_origin_for_log), (
            "spell the header via `_ORIGIN_HEADER`, never inline"
        )
        assert "_ORIGIN_HEADER" in inspect.getsource(_origin_for_log)
