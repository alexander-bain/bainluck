"""The latency NEEDLE, pinned so the series cannot re-base without a commit.

`.claude/handoff/NEEDLE-SPEC.md` (Alex, 2026-08-28, as amended the same day by
the "option b" ruling) gives this lane ONE number and one machine-readable
line, and Fable's heartbeat copies that line into YOUR-TURN verbatim.

🔴 **The published statistic is the EQUAL-WEIGHTED cold p50** — the median of
the per-member-path cold medians — NOT the median over pooled raw samples. The
raw pool was the original headline and moved −25 % on identical code purely
from sample mix; the equal-weighted form moved 1 % across the same pair. The
tests below pin which of the two the line carries, because the two differ by
hundreds of milliseconds on real data and a silent swap would look like a ship.

Three things can rot silently and all three are guarded here:

1. **The pool.** `needle_latency.POOL` names the member paths by key. If a key
   drifts out of `cold_path_snapshot.PATHS`, or a member quietly becomes a
   non-blocking sibling, the needle starts describing a different population
   while still printing the same label — the exact failure ruling 127 named as
   "a delta between two measurements is a delta of instruments". A test that
   reads the literal is the only thing that makes a re-base a visible edit.

2. **The line.** A heartbeat that parses it will read whatever shape it is
   given. The regex below is the spec's shape, not the script's current output,
   so a formatting change fails here rather than in a downstream parser.

3. **The statistic.** `test_the_published_number_is_equal_weighted_not_pooled`
   drives a snapshot where the two answers are far apart and asserts the line
   carries the equal-weighted one. Nothing else in the file would notice the
   swap, and on production data the swap is worth ~170 ms.

And the behavioural guard: a pool that goes thin must REFUSE, not publish. That
is not hypothetical — the second reading ever taken (2026-08-28, one minute
after the first) came back with one 11 ms sample because the first run had
warmed everything it then measured. Note the sample-count floor alone does NOT
cover this under equal weighting (the median of one 11 ms member is 11 ms), so
the member-count and surface-coverage floors are pinned too.

No network: the script is driven against a synthetic snapshot.
"""

from __future__ import annotations

import importlib.util
import io
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: The spec's line, as a spec-shaped regex rather than a copy of the format
#: string. `<ms>` is an integer: the needle is a glanceable number, and a
#: decimal place on a median that moves by hundreds is false precision.
NEEDLE_LINE = re.compile(
    r"^NEEDLE: latency (?P<ms>\d+) ms @ "
    r"(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00)$"
)


def _load(name: str):
    path = REPO / "backend" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def nl():
    return _load("needle_latency")


@pytest.fixture(scope="module")
def cps():
    return _load("cold_path_snapshot")


# --------------------------------------------------------------------------
# The pool
# --------------------------------------------------------------------------


def test_pool_names_the_three_graded_surfaces(nl):
    """The spec names three surfaces. Two are PATHS groups; cold search is
    folded in from `search_cold_samples` and therefore is NOT a POOL key."""
    assert set(nl.POOL) == {"Discover open", "tab loads"}


def test_every_pool_member_exists_in_the_instrument(nl, cps):
    keys = {p.key for p in cps.PATHS}
    for surface, members in nl.POOL.items():
        for key in members:
            assert (
                key in keys
            ), f"{surface} member {key!r} is not a cold_path_snapshot path"


def test_every_pool_member_gates_first_paint(nl, cps):
    """A needle that averaged in the siblings a tab also issues would be
    describing traffic, not a wait. Only `blocking` paths may be members."""
    by_key = {p.key: p for p in cps.PATHS}
    for members in nl.POOL.values():
        for key in members:
            assert by_key[
                key
            ].blocking, f"{key} is not blocking and cannot be in the pool"


def test_pool_membership_is_the_frozen_literal(nl):
    """Reads the literal on purpose. Adding a surface is legitimate; doing it
    without an edit here — and therefore without a visible commit — is not."""
    assert nl.POOL["Discover open"] == ("discover_native", "discover_web")
    assert nl.POOL["tab loads"] == (
        "sports_native",
        "sports_web",
        "search_trending",
        "my_stuff_stats",
    )


def test_typeahead_is_not_in_the_pool(nl):
    """It is a keystroke with its own 500 ms bar, and the non-voting
    `debug_timing` mode it must be sampled in reads ~2.2x low. Mixing it in
    would drag the needle down for a methodological reason."""
    flat = [k for members in nl.POOL.values() for k in members]
    assert not any("typeahead" in k for k in flat)


# --------------------------------------------------------------------------
# A synthetic snapshot, so the line and the refusal can be driven offline
# --------------------------------------------------------------------------


def _sample(ms: float, cold: bool) -> dict:
    return {"server_ms": ms, "class": "cold" if cold else "warm"}


def _snapshot(nl, cps, *, cold_per_path: int, ms: float = 500.0) -> dict:
    keys = [k for members in nl.POOL.values() for k in members]
    tab_samples = {
        p.key: (
            (
                [_sample(ms, True) for _ in range(cold_per_path)]
                + [_sample(20.0, False) for _ in range(2)]
            )
            if p.key in keys
            else [_sample(20.0, False)]
        )
        for p in cps.PATHS
    }
    return {
        "label": "synthetic",
        "term_set": "obscure",
        "commit": "deadbeef",
        "uptime_seconds": 9999,
        "warm_slug": True,
        "canonical": True,
        "taken_at": "2026-08-28T17:51:51+00:00",
        "transport_floor_wall_p50_ms": 250.0,
        "stats_before": "/tmp/stats-before.json",
        "tab_samples": tab_samples,
        "search_cold_samples": [_sample(ms, True) for _ in range(cold_per_path)],
        "requests": {"feed": 30, "other": 20, "typeahead": 6, "search": 6, "health": 4},
        "with_search": True,
    }


def _only_these_go_cold(nl, cps, cold: dict[str, list[float]]) -> dict:
    """A snapshot where exactly `cold` produced cold samples, everything warm.

    `cold` maps a member key (or the pseudo-key `search_cold`) to its cold
    server-ms values. Lets each refusal floor be driven in isolation, which is
    the only way to know a test is pinning the floor it claims to pin.
    """
    snap = _snapshot(nl, cps, cold_per_path=0)
    snap["search_cold_samples"] = [
        _sample(v, True) for v in cold.get("search_cold", [])
    ]
    for p in cps.PATHS:
        snap["tab_samples"][p.key] = [_sample(v, True) for v in cold.get(p.key, [])] + [
            _sample(20.0, False),
            _sample(20.0, False),
        ]
    return snap


def test_the_published_number_is_equal_weighted_not_pooled(nl, cps):
    """🔴 The option-b ruling, pinned. Alex switched the published statistic
    after the raw pool moved −25 % on identical code from sample mix alone.

    Here the two answers are deliberately far apart: one slow path missed once,
    one fast path missed nine times. The raw pool is dragged to the fast mode
    (10 of 11 samples are 10 ms); the equal-weighted median is not.
    """
    snap = _only_these_go_cold(
        nl,
        cps,
        {
            "discover_native": [3000.0],
            "discover_web": [2000.0],
            "sports_native": [1000.0],
            "my_stuff_stats": [10.0] * 9,
            "search_cold": [500.0],
        },
    )
    nd = nl.needle(snap)

    # per-path medians: 3000, 2000, 1000, 10, 500 -> median 1000
    assert nd["needle_ms"] == 1000.0
    # raw pool: nine 10 ms samples out of thirteen -> median 10
    assert nd["pool_p50_ms"] == 10.0
    assert nd["pool_n"] == 13

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = nl.report(snap, nd)
    assert rc == 0
    last = buf.getvalue().strip().splitlines()[-1]
    m = NEEDLE_LINE.match(last)
    assert m, f"last line does not match the spec shape: {last!r}"
    assert m.group("ms") == "1000", "the line must carry the equal-weighted p50"


def test_a_median_over_a_minority_of_members_refuses(nl, cps):
    """Equal weighting does not fix a member DROPPING OUT. Three of seven
    paths is a different population, so it refuses even though the raw
    sample count and the surface coverage are both satisfied."""
    snap = _only_these_go_cold(
        nl,
        cps,
        {
            "discover_native": [900.0] * 4,
            "sports_native": [900.0] * 4,
            "search_cold": [900.0] * 4,
        },
    )
    nd = nl.needle(snap)
    assert nd["n_cold_members"] == 3
    assert nd["pool_n"] >= nl.MIN_POOL_N, "sample-count floor must NOT be the cause"
    assert len(nd["surfaces_cold"]) == nl.MIN_SURFACES, "surface floor must not be it"

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = nl.report(snap, nd)
    assert rc == 1
    out = buf.getvalue()
    assert "member paths" in out and "POOL TOO THIN" in out
    assert not NEEDLE_LINE.search(out)


def test_a_missing_graded_surface_refuses(nl, cps):
    """The line says "across the three graded surfaces". If Discover never
    went cold, publishing it would claim three and describe two."""
    snap = _only_these_go_cold(
        nl,
        cps,
        {
            "sports_native": [900.0] * 3,
            "sports_web": [900.0] * 3,
            "search_trending": [900.0] * 3,
            "my_stuff_stats": [12.0] * 3,
            "search_cold": [500.0] * 3,
        },
    )
    nd = nl.needle(snap)
    assert nd["n_cold_members"] == 5, "member-count floor must NOT be the cause"
    assert nd["pool_n"] >= nl.MIN_POOL_N, "sample-count floor must NOT be the cause"
    assert nd["surfaces_cold"] == ["cold search", "tab loads"]

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = nl.report(snap, nd)
    assert rc == 1
    out = buf.getvalue()
    assert "Discover open" in out and "POOL TOO THIN" in out
    assert not NEEDLE_LINE.search(out)


def test_a_healthy_pool_emits_the_spec_line(nl, cps):
    snap = _snapshot(nl, cps, cold_per_path=3, ms=711.0)
    nd = nl.needle(snap)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = nl.report(snap, nd)
    assert rc == 0
    last = buf.getvalue().strip().splitlines()[-1]
    m = NEEDLE_LINE.match(last)
    assert m, f"last line does not match the spec shape: {last!r}"
    assert m.group("ms") == "711"
    assert m.group("ts") == snap["taken_at"]


def test_a_thin_pool_refuses_instead_of_publishing(nl, cps):
    """The 2026-08-28 self-poisoning case. One fast sample is not a needle."""
    snap = _snapshot(nl, cps, cold_per_path=0, ms=11.0)
    snap["search_cold_samples"] = []
    snap["tab_samples"]["my_stuff_stats"] = [_sample(11.0, True)]
    nd = nl.needle(snap)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = nl.report(snap, nd)
    assert rc == 1, "a thin pool must refuse"
    out = buf.getvalue()
    assert "POOL TOO THIN" in out
    assert not NEEDLE_LINE.search(out), "a refused run must not emit a needle line"


def test_cold_only_warm_samples_never_reach_the_pool(nl, cps):
    snap = _snapshot(nl, cps, cold_per_path=3, ms=711.0)
    nd = nl.needle(snap)
    # 6 member paths x 3 cold + 3 cold search = 21. The 2 warm per path are out.
    assert nd["pool_n"] == 21
    assert nd["pool_p50_ms"] == 711.0
    # Every path is uniform here, so both statistics agree — which is the point:
    # the 20 ms warm samples would have moved either one had they leaked in.
    assert nd["needle_ms"] == 711.0
    assert nd["n_cold_members"] == 7


def test_a_member_with_no_cold_sample_is_absent_not_counted_fast(nl, cps):
    snap = _snapshot(nl, cps, cold_per_path=3, ms=711.0)
    snap["tab_samples"]["search_trending"] = [_sample(20.0, False)] * 5
    nd = nl.needle(snap)
    assert nd["n_surfaces_cold"] == 6 and nd["n_surfaces"] == 7
    buf = io.StringIO()
    with redirect_stdout(buf):
        nl.report(snap, nd)
    assert "search_trending produced NO cold sample" in buf.getvalue()


# --------------------------------------------------------------------------
# The convention that makes the line arrive unprompted
# --------------------------------------------------------------------------


def test_the_lane_report_convention_requires_the_needle_line():
    readme = REPO / "docs" / "audits" / "latency" / "README.md"
    assert readme.exists(), "the latency lane's report convention file is missing"
    text = readme.read_text()
    assert "NEEDLE: latency" in text
    assert "needle_latency.py" in text
