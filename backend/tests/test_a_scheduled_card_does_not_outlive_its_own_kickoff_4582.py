"""A card that says "not started" stops saying it when the game starts (#4582).

═══ WHAT THE BUS SAW ═══

The NFL Week 1 opener, Patriots at Seahawks, event `14780138`, commence
`2026-09-10T00:20:00Z`. Twenty-four paired samples of served
`GET /api/events/14780138` against ESPN's board, every two minutes, 00:12–00:57Z
(`ARTIFACT-M-20260910-NFL-OPENER-LIFECYCLE.md`):

    00:21:02Z   live        <- ours beat ESPN's own board to the real kickoff
    00:23:02Z   scheduled   <- a game that had started, told it had not
    00:25:03Z   live        <- and back

A market must not flicker. This is the marquee game of the night doing it.

═══ WHAT IT WAS NOT ═══

The issue was filed as two writers racing on `events.status`, to be fixed with a
monotonic-lifecycle guard: once the authority says `live`, nothing demotes the
row. That is a good rule and it would not have touched this. **The status column
never moved.** Nothing in the codebase can write `scheduled` onto a `live` row —
the only two sites that write the literal are the repair arms of
`espn_sync._transition_event_statuses_impl`, and both select on the row already
being `completed`/`closed`/`suspended` with a NULL `completed_at`. Hysteresis on
a column that never flipped is a guard over an empty set.

═══ WHAT IT WAS ═══

`_cached_detail_payload`'s `else` branch, which handed every non-live, non-settled
entry a flat `_EVENT_DETAIL_DEFAULT_TTL`. The payload built at 00:20:03Z said
`scheduled` — true when it was built — and kept saying it for three hundred
seconds. **00:20:03 + 300 = 00:25:03**, which is the second the bus saw it
recover, to the second.

The alternation is the second half of it: each uvicorn worker holds its own
`_event_detail_cache` dict and production runs `WEB_CONCURRENCY=2`, so the two
leases expire at different moments and a reader refreshing the page is served
whichever worker takes the request.

Both halves were reproduced on production the same evening.

* **The divergence**, on the opener itself, 02:25:22–02:26:50Z: two byte-distinct
  payloads alternating three seconds apart, the same `hero_probability` pair
  (0.2601 / 0.2475) recurring in both directions. A number cannot move back and
  forth in six seconds; two caches can.
* **The lease outliving a promotion**, on event 15298741 with the served payload
  and `events.status` read side by side every four seconds: one entry written
  02:30:50Z while the row still said `scheduled`, served unchanged until
  02:34:41Z — 231 seconds on a single lease, spanning the column's promotion to
  `live` at 02:32:07Z.

That second specimen is reported for the lease length only. Its `commence_time`
was itself moved forward to 02:36:00Z during the window, so from that point
`served_event_status` had its own correct reason to say `scheduled` and the
reader-visible duration is not attributable to the lease alone. The opener is the
clean one and is what every assertion below is built on: its `commence_time` was
00:20:00Z when the bus sampled it and is 00:20:00Z still, so nothing but this
lease can have produced 00:23:02Z's `scheduled`.

═══ WHAT THESE TESTS PIN ═══

Both directions. A fix that simply shortened every unstarted lease would pass the
defect half and quietly spend the latency decision `_EVENT_DETAIL_DEFAULT_TTL`
was measured for on the entire scheduled population — 2,252 rows, almost none of
them anywhere near their kickoff. So each "it re-reads" case is paired with a
control that must still be served from cache:

* the opener's own entry is dead at 00:23:02Z …
* … while a game tomorrow keeps its full five minutes,
* … while a `suspended` row — the other occupant of that `else` branch, which
  makes no claim about not having started — keeps its five minutes too, and
* … while an entry written two seconds before kickoff still gets a real lease
  rather than a two-second one, because a wall of simultaneous kickoffs must not
  become a wall of uncached recomputes.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routes import events as events_route

EVENT_ID = 14780138

#: The opener's real kickoff, and the anchor every offset below is taken from, so
#: no assertion in this file reads the clock (gotcha #44).
COMMENCE = datetime(2026, 9, 10, 0, 20, 0, tzinfo=timezone.utc)
COMMENCE_EPOCH = COMMENCE.timestamp()

#: The three sample times the bus recorded, as offsets from kickoff.
SAMPLE_LIVE_FIRST = 62.0        # 00:21:02Z
SAMPLE_FLAPPED_BACK = 182.0     # 00:23:02Z  <- the defect
SAMPLE_LIVE_AGAIN = 303.0       # 00:25:03Z

#: When the poisoned entry was written: the last pre-kickoff request to that
#: worker. 00:25:03 minus `_EVENT_DETAIL_DEFAULT_TTL` is 00:20:03, three seconds
#: after kickoff — so the entry was written just AFTER the whistle, while the row
#: was still `scheduled` because `transition-event-statuses` had not run yet.
POISONED_ENTRY_WRITTEN = 3.0


@pytest.fixture(autouse=True)
def _clean_cache():
    events_route._event_detail_cache.clear()
    yield
    events_route._event_detail_cache.clear()


def _iso(offset_from_kickoff: float) -> str:
    """A time as `_format_event` stores it: an ISO string, tz-aware."""
    return (COMMENCE + timedelta(seconds=offset_from_kickoff)).isoformat()


def _plant(status: str, *, written_at: float, commence=_iso(0.0)) -> dict:
    """One entry written `written_at` seconds after kickoff, as `get_event` writes it."""
    payload = {"id": EVENT_ID, "status": status, "commence_time": commence}
    events_route._event_detail_cache[EVENT_ID] = (
        COMMENCE_EPOCH + written_at,
        status,
        payload,
    )
    return payload


def _served(at: float):
    """What a reader gets `at` seconds after kickoff."""
    return events_route._cached_detail_payload(EVENT_ID, COMMENCE_EPOCH + at)


class TestTheConstantsStillMeanWhatTheLadderAssumes:
    """A ladder read off constants is only as good as their ordering."""

    def test_the_grace_actually_binds(self):
        assert (
            events_route._EVENT_DETAIL_UNSTARTED_GRACE
            < events_route._EVENT_DETAIL_DEFAULT_TTL
        ), "a grace at or above the default TTL is not a bound, it is a rename"

    def test_the_grace_is_a_real_lease(self):
        assert events_route._EVENT_DETAIL_UNSTARTED_GRACE > 0, (
            "a zero grace makes the last seconds before every kickoff uncached"
        )

    def test_an_unstarted_claim_never_outlives_a_live_one(self):
        assert (
            events_route._EVENT_DETAIL_UNSTARTED_GRACE
            <= events_route._EVENT_DETAIL_LIVE_TTL
        ), (
            "past its own kickoff a `scheduled` entry is the LEAST trustworthy "
            "thing this cache holds; it may not be leased longer than a live one"
        )


class TestTheDefect:
    """The opener's three samples, in order, at the times they were taken."""

    def test_the_opener_is_not_still_upcoming_at_the_reported_00_23_02z(self):
        _plant("scheduled", written_at=POISONED_ENTRY_WRITTEN)
        assert _served(SAMPLE_FLAPPED_BACK) is None, (
            "00:23:02Z served `scheduled` for a game that kicked off at 00:20:00Z"
        )

    def test_that_miss_is_the_new_bound_and_not_ordinary_expiry(self):
        """The red half, pinned in place: the old flat rule WOULD have served it."""
        age_at_the_flap = SAMPLE_FLAPPED_BACK - POISONED_ENTRY_WRITTEN
        assert age_at_the_flap < events_route._EVENT_DETAIL_DEFAULT_TTL, (
            "if the entry were simply 300s old the defect would have fixed "
            "itself; it was 179s old and had 121s of lease left to run"
        )

    def test_the_recovery_at_00_25_03z_was_the_lease_running_out(self):
        """00:20:03 + 300 = 00:25:03. The arithmetic that names the cause."""
        assert (
            POISONED_ENTRY_WRITTEN + events_route._EVENT_DETAIL_DEFAULT_TTL
            == pytest.approx(SAMPLE_LIVE_AGAIN, abs=1.0)
        )

    def test_the_first_live_sample_is_the_other_worker(self):
        """00:21:02Z read `live`, so the row itself was already promoted."""
        _plant("live", written_at=SAMPLE_LIVE_FIRST)
        assert _served(SAMPLE_LIVE_FIRST + 1.0) is not None
        assert _served(SAMPLE_FLAPPED_BACK) is None, (
            "the live worker's own entry had expired by 00:23:02Z, so the "
            "`scheduled` reading came from the other one"
        )

    def test_the_flap_cannot_span_two_samples_any_more(self):
        """Whatever a worker holds, it cannot still say `scheduled` two minutes on."""
        _plant("scheduled", written_at=POISONED_ENTRY_WRITTEN)
        assert _served(SAMPLE_FLAPPED_BACK) is None
        _plant("scheduled", written_at=-1.0)
        assert _served(SAMPLE_FLAPPED_BACK) is None


class TestTheBoundary:
    """Where the lease ends, from both sides of the whistle."""

    def test_an_entry_written_before_kickoff_expires_a_grace_after_it(self):
        grace = events_route._EVENT_DETAIL_UNSTARTED_GRACE
        _plant("scheduled", written_at=-120.0)
        assert _served(grace - 1.0) is not None
        assert _served(grace + 1.0) is None

    def test_an_entry_written_just_before_kickoff_still_gets_a_real_lease(self):
        """The floor. Two seconds of lease would make the last half-minute
        before every start an uncached band, and fourteen NFL games start at
        once."""
        grace = events_route._EVENT_DETAIL_UNSTARTED_GRACE
        _plant("scheduled", written_at=-2.0)
        assert _served(-1.0) is not None
        assert _served(grace - 1.0) is not None
        assert _served(grace + 1.0) is None

    def test_an_entry_written_after_kickoff_re_reads_at_the_live_cadence(self):
        """A row not yet promoted is still true — `transition-event-statuses`
        runs every 60s — so this re-checks rather than refusing to cache."""
        grace = events_route._EVENT_DETAIL_UNSTARTED_GRACE
        _plant("scheduled", written_at=10.0)
        assert _served(10.0 + grace - 1.0) is not None
        assert _served(10.0 + grace + 1.0) is None


class TestTheControls:
    """Everything the bound must NOT reach."""

    def test_a_game_tomorrow_keeps_its_full_five_minutes(self):
        default = events_route._EVENT_DETAIL_DEFAULT_TTL
        far = _iso(86400.0)
        _plant("scheduled", written_at=-86400.0, commence=far)
        assert _served(-86400.0 + default - 1.0) is not None
        assert _served(-86400.0 + default + 1.0) is None

    def test_a_suspended_row_is_not_touched(self):
        """The other occupant of the `else` branch. A rain delay makes no claim
        about not having started, so this rule has nothing to say about it."""
        default = events_route._EVENT_DETAIL_DEFAULT_TTL
        _plant("suspended", written_at=3600.0)
        assert _served(3600.0 + default - 1.0) is not None
        assert _served(3600.0 + default + 1.0) is None

    def test_the_live_ladder_is_untouched(self):
        live_ttl = events_route._EVENT_DETAIL_LIVE_TTL
        _plant("live", written_at=60.0)
        assert _served(60.0 + live_ttl - 1.0) is not None
        assert _served(60.0 + live_ttl + 1.0) is None

    def test_a_settled_row_keeps_its_hour(self):
        settled_ttl = events_route._EVENT_DETAIL_SETTLED_TTL
        events_route._event_detail_cache[EVENT_ID] = (
            COMMENCE_EPOCH,
            "closed",
            {"id": EVENT_ID, "status": "closed", "commence_time": _iso(0.0)},
        )
        assert _served(settled_ttl - 1.0) is not None
        assert _served(settled_ttl + 1.0) is None

    def test_a_miss_is_still_a_miss(self):
        assert _served(0.0) is None


class TestTheHelper:
    """`_unstarted_entry_ttl`'s truth table, including the abstention."""

    @pytest.mark.parametrize(
        "seconds_to_start,expected",
        [
            (86400.0, 300.0),   # tomorrow — the full default
            (600.0, 300.0),     # ten minutes out — still capped at the default
            (100.0, 130.0),     # inside the default — expires a grace after start
            (0.0, 30.0),        # exactly at the whistle
            (-1000.0, 30.0),    # long past it — the floor holds
        ],
    )
    def test_the_ladder(self, seconds_to_start, expected):
        cached_at = COMMENCE_EPOCH - seconds_to_start
        payload = {"commence_time": _iso(0.0)}
        assert events_route._unstarted_entry_ttl(payload, cached_at) == expected

    def test_it_never_returns_more_than_the_default(self):
        payload = {"commence_time": _iso(0.0)}
        for seconds_to_start in (0.0, 1.0, 299.0, 300.0, 301.0, 10_000.0):
            ttl = events_route._unstarted_entry_ttl(
                payload, COMMENCE_EPOCH - seconds_to_start
            )
            assert ttl <= events_route._EVENT_DETAIL_DEFAULT_TTL

    def test_it_never_returns_less_than_the_grace(self):
        payload = {"commence_time": _iso(0.0)}
        for seconds_to_start in (-10_000.0, -1.0, 0.0, 1.0, 10_000.0):
            ttl = events_route._unstarted_entry_ttl(
                payload, COMMENCE_EPOCH - seconds_to_start
            )
            assert ttl >= events_route._EVENT_DETAIL_UNSTARTED_GRACE

    @pytest.mark.parametrize("commence", [None, "", "not a time", 1234, []])
    def test_no_usable_start_abstains_and_keeps_the_default(self, commence):
        """The abstention falls the OPPOSITE way from its `completed_at` twin.

        Shortening is the intervention here. A row whose kickoff this function
        cannot locate is not a row to spend latency on for a boundary it has not
        been shown to have.
        """
        ttl = events_route._unstarted_entry_ttl(
            {"commence_time": commence}, COMMENCE_EPOCH
        )
        assert ttl == events_route._EVENT_DETAIL_DEFAULT_TTL

    def test_an_absent_key_abstains(self):
        ttl = events_route._unstarted_entry_ttl({}, COMMENCE_EPOCH)
        assert ttl == events_route._EVENT_DETAIL_DEFAULT_TTL

    def test_a_datetime_is_accepted_as_well_as_a_string(self):
        assert events_route._unstarted_entry_ttl(
            {"commence_time": COMMENCE}, COMMENCE_EPOCH - 100.0
        ) == 130.0

    def test_a_naive_datetime_is_read_as_utc(self):
        naive = COMMENCE.replace(tzinfo=None)
        assert events_route._unstarted_entry_ttl(
            {"commence_time": naive}, COMMENCE_EPOCH - 100.0
        ) == 130.0


class TestTheWiringIsLive:
    """The helper is only a fix if the payload it reads really carries the field.

    The abstention above is the quiet failure mode of this whole ship: a payload
    with no `commence_time` gets the full default TTL and the bound never fires,
    silently, forever. Every other test in this file would still pass in that
    world, because they all hand the helper a payload they built themselves.

    So this reads the two ends against each other out of the source — the key
    `_unstarted_entry_ttl` asks for, and the keys `_format_event` writes — rather
    than asserting a literal twice and calling that agreement.
    """

    @staticmethod
    def _module_ast():
        import ast
        import inspect

        return ast.parse(inspect.getsource(events_route))

    @staticmethod
    def _fn(tree, name):
        import ast

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        raise AssertionError(f"{name} not found — renamed? this guard is stale")

    def test_the_key_the_helper_reads_is_the_key_the_serializer_writes(self):
        import ast

        tree = self._module_ast()

        reads = [
            node.args[0].value
            for node in ast.walk(self._fn(tree, "_unstarted_entry_ttl"))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ]
        assert len(reads) == 1, f"expected one payload lookup, found {reads}"
        key = reads[0]

        written = {
            k.value
            for node in ast.walk(self._fn(tree, "_format_event"))
            if isinstance(node, ast.Dict)
            for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        assert key in written, (
            f"`_unstarted_entry_ttl` reads {key!r} but `_format_event` never "
            f"writes it — the bound would abstain on every request and #4582 "
            f"would be live again with all its tests green"
        )

    def test_the_serializer_is_still_the_one_the_cache_stores(self):
        """`get_event` caches what `_format_event` returned, not a later mutation."""
        import ast
        import inspect

        src = inspect.getsource(events_route.get_event)
        assert "_format_event(" in src
        assert "_event_detail_cache[" in src, (
            "the write site moved; re-check that the cached dict is still the "
            "serialized payload this helper reads"
        )
        tree = ast.parse(inspect.getsource(events_route))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "_event_detail_cache"
                and isinstance(getattr(node, "ctx", None), ast.Store)
            ):
                return
        raise AssertionError("no store into _event_detail_cache found")
