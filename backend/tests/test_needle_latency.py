"""The latency NEEDLE, pinned so the series cannot re-base without a commit.

`.claude/handoff/NEEDLE-SPEC.md` (Alex, 2026-08-28, as amended TWICE the same
day) gives this lane ONE number and one machine-readable line, and Fable's
heartbeat copies that line into YOUR-TURN verbatim.

🔴 **AMENDED BY THE OPTION-C RULING (2026-08-28), AND THE SERIES BREAKS.** The
warmer landed and won: five of seven member paths could no longer be driven
cold, so the cold-only statistic refused seven reads running. A metric that
refuses because the product got FASTER is measuring the wrong thing. Alex ruled
a strict division, and both halves are pinned here:

* **`NEEDLE: latency <ms>`** — what a brand-new install actually waits, per
  ruling 137's definition of a first load, **whatever cache serves it**. This
  is the dial. `needle_latency.user_wait()`.
* **`DIAG: latency-build <ms>`** — the same statistic over COLD samples only.
  Report-only, so a build regression cannot hide behind the warmer. It never
  reaches the dial. `needle_latency.needle()`, unchanged, and the
  882 → 873 → 940 → 1273 series belongs to IT from here.

The two lines carry distinct names precisely so a reader cannot plot a point
from one against the other, and `test_a_refused_diag_does_not_suppress_the_needle`
pins the decoupling — that coupling is what published nothing for seven reads.

🔴 **Both statistics are EQUAL-WEIGHTED** — the median of the per-member-path
medians — NOT the median over pooled raw samples. The raw pool was the original
headline and moved −25 % on identical code purely from sample mix; the
equal-weighted form moved 1 % across the same pair. The tests below pin which
of the two each line carries, because they differ by hundreds of milliseconds
on real data and a silent swap would look like a ship.

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

#: The DIAG line's shape. A DIFFERENT name, deliberately: the two series must
#: never be plotted against each other, and a shared prefix is how that happens.
DIAG_LINE = re.compile(
    r"^DIAG: latency-build (?P<ms>\d+) ms @ "
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
        nl.report(snap, nd, nl.user_wait(snap))
    diag = [line for line in buf.getvalue().splitlines() if line.startswith("DIAG: ")]
    assert len(diag) == 1, buf.getvalue()
    m = DIAG_LINE.match(diag[0])
    assert m, f"the DIAG line does not match the spec shape: {diag[0]!r}"
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
        nl.report(snap, nd, nl.user_wait(snap))
    out = buf.getvalue()
    assert "member paths" in out and "DIAG POOL TOO THIN" in out
    assert not DIAG_LINE.search(out), "a refused DIAG must not emit a build number"


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
        nl.report(snap, nd, nl.user_wait(snap))
    out = buf.getvalue()
    assert "Discover open" in out and "DIAG POOL TOO THIN" in out
    assert not DIAG_LINE.search(out)


def test_a_healthy_pool_emits_the_spec_line(nl, cps):
    """Both lines, distinct names, and the NEEDLE LAST — the heartbeat reads the
    last line, so a DIAG that printed after it would be copied onto Alex's dial
    as the user-facing number."""
    # 🔴 THE FIXTURE IS BUILT SO THE TWO ANSWERS CANNOT COINCIDE. With an equal
    # cold/warm split the served median IS the cold median and this test would
    # pass with either statistic wired to either line — which is the one thing
    # it exists to rule out. Two cold at 711 against three warm at 20 puts the
    # served median firmly in the warm mode on every tab member, while cold
    # search stays 711 on both.
    snap = _snapshot(nl, cps, cold_per_path=0)
    for p in cps.PATHS:
        snap["tab_samples"][p.key] = [_sample(711.0, True)] * 2 + [
            _sample(20.0, False)
        ] * 3
    snap["search_cold_samples"] = [_sample(711.0, True)] * 3

    nd, uw = nl.needle(snap), nl.user_wait(snap)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = nl.report(snap, nd, uw)
    assert rc == 0
    lines = buf.getvalue().strip().splitlines()

    m = NEEDLE_LINE.match(lines[-1])
    assert m, f"the LAST line must be the needle: {lines[-1]!r}"
    assert m.group("ts") == snap["taken_at"]
    # six tab members at a served median of 20, cold search at 711 -> 20
    assert m.group("ms") == "20", "the NEEDLE carries the SERVED statistic"

    d = DIAG_LINE.match(lines[-2])
    assert d, f"the DIAG line must sit directly above it: {lines[-2]!r}"
    assert d.group("ms") == "711", "DIAG carries the COLD statistic"

    assert m.group("ms") != d.group("ms")


def test_a_thin_pool_refuses_instead_of_publishing(nl, cps):
    """The 2026-08-28 self-poisoning case. One fast sample is not a needle.

    Under option c this refuses on BOTH lines: the DIAG pool is one member, and
    the needle's own pool is too, because the fixture strips every other
    member's samples entirely rather than merely warming them.
    """
    snap = _snapshot(nl, cps, cold_per_path=0, ms=11.0)
    snap["search_cold_samples"] = []
    snap["tab_samples"]["my_stuff_stats"] = [_sample(11.0, True)]
    for key in ("discover_native", "discover_web", "sports_native", "sports_web"):
        snap["tab_samples"][key] = []
    nd, uw = nl.needle(snap), nl.user_wait(snap)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = nl.report(snap, nd, uw)
    assert rc == 1, "a thin pool must refuse"
    out = buf.getvalue()
    assert "DIAG POOL TOO THIN" in out
    assert not DIAG_LINE.search(out)
    assert not NEEDLE_LINE.search(out), "a refused run must not emit a needle number"
    assert "NEEDLE: latency REFUSED" in out, (
        "the refusal must still be MACHINE-READABLE — the heartbeat parses the "
        "last line and a silent omission reads as a missing run, not a refusal"
    )


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


# --------------------------------------------------------------------------
# 🔴 The option-c ruling: the NEEDLE is the user's WAIT, and DIAG is decoupled
# --------------------------------------------------------------------------


def test_the_needle_counts_warm_samples_and_diag_does_not(nl, cps):
    """The whole division, in one snapshot.

    A person opening a warm tab genuinely waits the warm number. The cold-only
    statistic discarded exactly that and therefore described the bad half as if
    it were the whole — which is how a fixed product produced seven refusals.
    """
    snap = _snapshot(nl, cps, cold_per_path=0)
    for p in cps.PATHS:
        snap["tab_samples"][p.key] = [_sample(900.0, True)] + [_sample(30.0, False)] * 4
    snap["search_cold_samples"] = [_sample(900.0, True)] * 3

    uw, nd = nl.user_wait(snap), nl.needle(snap)

    # served medians: 30 on every tab member (one 900 among four 30s), 900 for
    # cold search -> median 30.
    assert uw["needle_ms"] == 30.0
    # cold medians: 900 everywhere -> 900.
    assert nd["needle_ms"] == 900.0
    assert uw["n_members"] == 7


def test_the_needle_is_equal_weighted_too_not_a_raw_pool(nl, cps):
    """Option b's lesson survives option c. One chatty fast member must not be
    able to drag the dial, which is exactly what the raw pool let happen
    (-25 % on identical code from sample mix alone)."""
    snap = _snapshot(nl, cps, cold_per_path=0)
    for p in cps.PATHS:
        snap["tab_samples"][p.key] = [_sample(800.0, False)] * 2
    snap["tab_samples"]["my_stuff_stats"] = [_sample(5.0, False)] * 40
    snap["search_cold_samples"] = [_sample(800.0, False)] * 2

    uw = nl.user_wait(snap)
    # 40 of the 52 samples are 5 ms; a raw pool would say 5.
    assert uw["pool_n"] > 40
    assert uw["needle_ms"] == 800.0, "one chatty member must not move the dial"


def test_a_refused_diag_does_not_suppress_the_needle(nl, cps):
    """🔴 The decoupling, and the reason the ruling exists.

    Under the old shape a thin COLD pool returned 1 before the line was ever
    printed, so seven consecutive reads published nothing about a product that
    was, in fact, fast. DIAG may refuse all it likes; the needle still ships.
    """
    snap = _snapshot(nl, cps, cold_per_path=0)
    for p in cps.PATHS:
        snap["tab_samples"][p.key] = [_sample(45.0, False)] * 5
    snap["search_cold_samples"] = [_sample(45.0, False)] * 6

    nd, uw = nl.needle(snap), nl.user_wait(snap)
    assert nd["n_cold_members"] == 0, "nothing went cold — DIAG must refuse"

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = nl.report(snap, nd, uw)
    out = buf.getvalue()

    assert rc == 0, "the needle published, so the run succeeded"
    assert "DIAG POOL TOO THIN" in out
    assert "DIAG: latency-build REFUSED" in out
    m = NEEDLE_LINE.match(out.strip().splitlines()[-1])
    assert m and m.group("ms") == "45"


def test_a_throttled_member_refuses_the_needle_rather_than_flattering_it(nl, cps):
    """#2260, on the new statistic. A 429 answers in 2 ms with a real
    `x-response-time`; if it reached the served pool it would pull the dial
    toward zero and read as a ship."""
    snap = _snapshot(nl, cps, cold_per_path=0)
    for p in cps.PATHS:
        snap["tab_samples"][p.key] = [_sample(600.0, False)] * 5
    snap["search_cold_samples"] = [
        {"server_ms": 3.0, "http": 429, "class": cps.REJECTED} for _ in range(6)
    ]

    uw = nl.user_wait(snap)
    search = next(m for m in uw["members"] if m["key"] == "search_cold")
    assert search["served"] == [], "a 429 must not count as a served wait"
    assert search["rejections"] == {"429": 6}

    reasons = " ".join(nl.wait_refusals(uw))
    assert "RATE LIMITED" in reasons
    assert "cold search" in reasons


def test_the_needle_refusal_names_only_the_surfaces_actually_missing(nl, cps):
    """A precedence bug once listed every surface as missing, including the two
    that were served: on sets `-` binds tighter than `|`, so
    `set(POOL) | {"cold search"} - served` is `POOL | (X - served)`."""
    snap = _snapshot(nl, cps, cold_per_path=0)
    for p in cps.PATHS:
        snap["tab_samples"][p.key] = [_sample(600.0, False)] * 5
    snap["search_cold_samples"] = []

    reasons = " ".join(nl.wait_refusals(nl.user_wait(snap)))
    assert "cold search" in reasons
    assert "Discover open" not in reasons, reasons
    assert "tab loads" not in reasons, reasons


def test_the_two_lines_carry_different_names(nl):
    """A shared prefix is how two incomparable series end up on one chart."""
    assert NEEDLE_LINE.pattern.startswith("^NEEDLE: latency ")
    assert DIAG_LINE.pattern.startswith("^DIAG: latency-build ")


def test_the_harness_paces_itself_under_the_rate_limit(cps):
    """#2260's other half. 60 req/min per IP; an unpaced canonical run issues
    ~68 in twenty seconds and the searches, which go last, are what gets
    refused."""
    assert (
        cps.MIN_REQUEST_INTERVAL_S * 60 > 60
    ), "the interval must keep a 60-request minute inside the budget"
    assert cps.MIN_REQUEST_INTERVAL_S < 2.0, (
        "a canonical run is ~68 requests; much above this and a reading takes "
        "longer than the caches it is trying to observe"
    )
