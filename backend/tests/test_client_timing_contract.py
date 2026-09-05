"""Guards for the client-timing contract (LAT-P232, #2751).

THE CLASS THESE CATCH. The ingest endpoint is public and unauthenticated, so the
browser's sanitizer is not a security boundary for it. The only thing standing
between a hostile POST and the table is
`app/utils/client_timing_contract.validate_packet`. These tests are the proof
that it holds — and specifically that it holds against a caller who is NOT our
frontend and never ran our sanitizer.

The privacy claim under test, exactly: every field stored is a field already
being sent to Google for that same reader in that same moment, and route-shaped
fields are stored MORE coarsely than GA gets them. A test that only checked
"our own good packet survives" would pass on a module with no allowlist at all,
so the load-bearing cases here are the hostile ones.
"""

import pytest

from app.utils.client_timing_contract import (
    ACCEPTED_EVENT_NAMES,
    EVENT_KEY_SPECS,
    MAX_COUNT,
    MAX_DURATION_MS,
    MAX_EVENTS_PER_REQUEST,
    MAX_STRING_LEN,
    NOT_MEASURED,
    PROMOTED_DIMENSIONS,
    mask_path,
    validate_packet,
)

# ---------------------------------------------------------------------------
# The happy path — the packet the frontend actually sends
# ---------------------------------------------------------------------------


def test_a_real_screen_timing_packet_survives_intact():
    """The needle must actually get through, or the whole ship is dead."""
    name, clean = validate_packet(
        "screen_timing",
        {
            "surface": "discover",
            "entry": "cold",
            "shell_ms": 210,
            "first_card_ms": 1480,
            "fold_ms": 1900,
            "interactive_ms": 2300,
            "card_count": 12,
            "device_class": "phone",
            "network_class": "4g",
            "app_build": "abc1234",
            "outcome_class": "ok",
        },
    )
    assert name == "screen_timing"
    assert clean["first_card_ms"] == 1480
    assert clean["surface"] == "discover"
    assert clean["card_count"] == 12
    assert len(clean) == 11


# ---------------------------------------------------------------------------
# The security boundary — a caller who never ran our sanitizer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile_key",
    [
        "user_id",
        "email",
        "session_id",
        "anon_id",
        "ip",
        "query",
        "platform",
        "event_timestamp",
        "auth_token",
        "cookie",
    ],
)
def test_identifier_keys_never_survive(hostile_key):
    """The whole privacy claim in one test.

    A hostile POST does not pass through `sanitize.ts`. If these keys could ride
    in on a legitimately-named event, the table would hold identifiers and the
    claim would be false. Note `session_id`/`platform`/`event_timestamp` are
    included deliberately: they are LEGAL enrichment keys elsewhere in the
    taxonomy, and the three perf events are exactly the ones that strip them.
    """
    _, clean = validate_packet(
        "screen_timing",
        {"first_card_ms": 900, hostile_key: "definitely-an-identifier"},
    )
    assert hostile_key not in clean
    # …and the legitimate key still came through, so this is an allowlist and
    # not merely a blocklist that happens to name these ten strings.
    assert clean["first_card_ms"] == 900


def test_an_unknown_event_name_is_refused_whole():
    name, clean = validate_packet("page_view", {"first_card_ms": 100})
    assert name is None
    assert clean == {}


def test_a_content_carrying_event_is_refused_even_though_it_is_real():
    """`feed_exit` is a real, registered perf event — and still not accepted.

    It keeps the enrichment keys, so it carries a client session marker. Being
    a legitimate event elsewhere is not a reason to admit it here.
    """
    name, _ = validate_packet("feed_exit", {"dwell_ms": 100})
    assert name is None


def test_accepted_names_are_exactly_three():
    assert ACCEPTED_EVENT_NAMES == {"screen_timing", "feed_telemetry", "web_vital"}


def test_every_promoted_dimension_is_an_allowlisted_key():
    """A promoted column that no allowlist names would always be NULL.

    The ingest route fills promoted columns from the CLEAN dict, so a typo in
    `PROMOTED_DIMENSIONS` produces a silently always-empty column rather than an
    error — the kind of dead field that reads as "no data" forever.
    """
    every_key = set()
    for spec in EVENT_KEY_SPECS.values():
        every_key.update(spec)
    for dim in PROMOTED_DIMENSIONS:
        assert dim in every_key, f"{dim} is promoted but no event declares it"


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------


def test_not_measured_survives_and_is_not_confused_with_a_bad_value():
    """`-1` is a MEANING, not a malformed number.

    Dropping it would delete exactly the surfaces that never reached a first
    card — the population the needle exists to find — and would make the
    remaining p50 look better the more often the page failed.
    """
    _, clean = validate_packet("screen_timing", {"first_card_ms": NOT_MEASURED})
    assert clean["first_card_ms"] == NOT_MEASURED


@pytest.mark.parametrize(
    "bad",
    [-2, -1000, MAX_DURATION_MS + 1, float("inf"), float("nan"), "1480", None, [1]],
)
def test_impossible_durations_are_dropped(bad):
    _, clean = validate_packet("screen_timing", {"first_card_ms": bad, "card_count": 3})
    assert "first_card_ms" not in clean
    # One bad key costs that key, never the packet (gotcha #42).
    assert clean["card_count"] == 3


def test_a_bool_is_not_a_duration():
    """`bool` subclasses `int` in Python.

    Without an explicit guard `True` stores as `1` and invents a 1ms render out
    of a flag — a plausible wrong number, which is worse than a missing one.
    """
    _, clean = validate_packet("screen_timing", {"first_card_ms": True})
    assert "first_card_ms" not in clean


def test_counts_are_bounded():
    _, clean = validate_packet("screen_timing", {"card_count": MAX_COUNT + 1})
    assert "card_count" not in clean


def test_a_long_enum_is_truncated_not_stored_whole():
    _, clean = validate_packet("screen_timing", {"outcome_class": "x" * 5000})
    assert len(clean["outcome_class"]) == MAX_STRING_LEN


def test_cls_keeps_its_fractional_value():
    """CLS is unitless and small; rounding it to an int would zero every score."""
    _, clean = validate_packet(
        "web_vital", {"metric_name": "CLS", "metric_value": 0.0512345}
    )
    assert clean["metric_value"] == 0.051


def test_a_packet_of_only_junk_yields_nothing():
    name, clean = validate_packet("screen_timing", {"nope": 1, "also_nope": "x"})
    assert name == "screen_timing"
    assert clean == {}


@pytest.mark.parametrize("bad_params", ["string", 42, None, ["a"]])
def test_non_object_params_are_refused(bad_params):
    name, clean = validate_packet("screen_timing", bad_params)
    assert name is None
    assert clean == {}


def test_a_non_string_event_name_is_refused():
    assert validate_packet(None, {})[0] is None
    assert validate_packet(42, {})[0] is None


# ---------------------------------------------------------------------------
# Path masking — the field GA gets in full and this table does not
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("/event/12345", "event/:id"),
        ("/event/12345/props", "event/:id/props"),
        ("/", "discover"),
        ("", "discover"),
        ("/discover", "discover"),
        ("/team/9f8e7d6c-1234-5678-9abc-def012345678", "team/:id"),
        ("/search?q=secret+thing", "search"),
        ("/search#fragment", "search"),
        ("/a/" + "z" * 60, "a/:slug"),
        ("/a/b/c/d/e", "a/b/c"),
    ],
)
def test_mask_path_strips_ids_by_shape(raw, expected):
    assert mask_path(raw) == expected


def test_page_path_is_masked_on_the_way_in():
    """GA receives the raw path today; this table must not.

    `web_vital.page_path` is NOT masked by the client (unlike `surface`), so if
    the server did not mask it an event id would land in a durable first-party
    store while the docstring claimed otherwise.
    """
    _, clean = validate_packet(
        "web_vital",
        {"metric_name": "LCP", "metric_value": 2100, "page_path": "/event/98765"},
    )
    assert clean["page_path"] == "event/:id"
    assert "98765" not in clean["page_path"]


def test_masking_is_idempotent():
    """`surface` arrives already masked; masking it twice must not corrupt it."""
    once = mask_path("/event/12345")
    assert mask_path(once) == once


def test_a_query_string_cannot_ride_in_on_a_path():
    _, clean = validate_packet(
        "feed_telemetry", {"endpoint": "/api/feed?token=abc123&user=alex"}
    )
    assert "token" not in clean["endpoint"]
    assert "alex" not in clean["endpoint"]


def test_masked_output_is_length_capped():
    assert (
        len(mask_path("/" + "/".join("segment" + str(i) for i in range(50))))
        <= MAX_STRING_LEN
    )


# ---------------------------------------------------------------------------
# The contract must not drift from the frontend's
# ---------------------------------------------------------------------------


def test_batch_cap_is_declared_and_small():
    """The client mirrors this constant; a big number here is a free write hole."""
    assert 0 < MAX_EVENTS_PER_REQUEST <= 50


def test_server_allowlist_matches_the_frontend_perf_event_keys():
    """The duplication is deliberate; the DRIFT is what would be a bug.

    Parsed out of `sanitize.ts` rather than restated, so a key added on one side
    and not the other reds here instead of silently becoming a field the browser
    sends and the table drops (or worse, the reverse).
    """
    import pathlib
    import re

    sanitize = (
        pathlib.Path(__file__).resolve().parents[2]
        / "frontend"
        / "lib"
        / "analytics"
        / "sanitize.ts"
    )
    if not sanitize.exists():  # pragma: no cover - backend-only checkouts
        pytest.skip("frontend/ not present in this checkout")

    text = sanitize.read_text()
    for event_name, spec in EVENT_KEY_SPECS.items():
        block = re.search(
            rf"^  {re.escape(event_name)}: new Set\(\[(.*?)^  \]\),",
            text,
            re.S | re.M,
        )
        assert block, f"could not find PERF_EVENT_KEYS entry for {event_name}"
        frontend_keys = set(re.findall(r"'([a-z_]+)'", block.group(1)))
        assert set(spec) == frontend_keys, (
            f"{event_name} drifted: server-only={set(spec) - frontend_keys}, "
            f"frontend-only={frontend_keys - set(spec)}"
        )
