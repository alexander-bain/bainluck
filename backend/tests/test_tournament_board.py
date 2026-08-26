"""Guards for the US Open championship boards (UX-P131).

The centre of gravity here is the honesty contract, because that is the thing a
reader cannot check for themselves.  A wrong ranking is visible; a *stale*
number rendered in the same confident type as a live one is not, and #2199 has
the US Open outright fields dark for 8-32 days while this page ships.  So the
majority of these tests assert that a number the system has not seen recently
can never present as live — at the row level, at the board level, and in the
one direction that matters (a false LIVE is the failure; a false STALE is
merely cautious).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.tournament_board import (
    DARK_PRICE_HOURS,
    TREND_DAYS,
    build_boards,
    draw_label,
    price_state,
)
from app.utils.tournament_register import STALE_PRICE_HOURS

NOW = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


def _source(source: str, market_id: int, outcome_id: int, **kw):
    block = {
        "source": source,
        "market_id": market_id,
        "outcome_id": outcome_id,
        "status": kw.pop("status", "live"),
        "terminal_result": kw.pop("terminal_result", None),
        "evidence": {"kind": "test"},
    }
    block.update(kw)
    return block


def _player(entity_key: str, name: str, draw: str, sources: list[dict], **kw):
    return {
        "entity_key": entity_key,
        "display_name": name,
        "draw": draw,
        "seed": kw.pop("seed", None),
        "country": kw.pop("country", None),
        "draw_slot": None,
        "section": None,
        "sources": sources,
    }


def _register(players: list[dict]):
    return {
        "schema_version": "tournament-register/v1",
        "tournament": "us-open",
        "season": "2026",
        "version": 1,
        "generated_at": "2026-08-25T00:50:00+00:00",
        "draw_released": False,
        "players": players,
        "matchups": [],
    }


def _priced(probability: float, *, age_hours: float = 1.0):
    return {
        "probability": probability,
        "observed_at": NOW - timedelta(hours=age_hours),
    }


def _two_source_register():
    return _register(
        [
            _player(
                "player-a",
                "Player A",
                "mens-singles",
                [_source("kalshi", 1, 10), _source("polymarket", 2, 20)],
            ),
            _player(
                "player-b",
                "Player B",
                "mens-singles",
                [_source("kalshi", 1, 11)],
            ),
        ]
    )


# ---------------------------------------------------------------------------
# price_state — the freshness verdict
# ---------------------------------------------------------------------------

def test_price_state_live_inside_the_stale_window():
    assert price_state(0.0) == "live"
    assert price_state(STALE_PRICE_HOURS) == "live"


def test_price_state_stale_between_the_two_thresholds():
    assert price_state(STALE_PRICE_HOURS + 0.01) == "stale"
    assert price_state(DARK_PRICE_HOURS) == "stale"


def test_price_state_dark_past_the_dark_threshold():
    assert price_state(DARK_PRICE_HOURS + 0.01) == "dark"
    # The #2199 shape: 8 to 32 days without a capture.
    assert price_state(8 * 24) == "dark"
    assert price_state(32 * 24) == "dark"


def test_never_observed_is_dark_not_fresh():
    """An absent timestamp is the strongest evidence of absence, not of health.

    Reading `None` as anything but dark is gotcha #53's shape — one value
    standing for both "nothing to report" and "never happened".
    """
    assert price_state(None) == "dark"


# ---------------------------------------------------------------------------
# THE HONESTY CONTRACT — a stale number can never present as live
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("age_hours", [STALE_PRICE_HOURS + 1, 8 * 24, 32 * 24])
def test_stale_row_is_never_marked_live(age_hours):
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.50, age_hours=age_hours),
            ("polymarket", 2, 20): _priced(0.54, age_hours=age_hours),
            ("kalshi", 1, 11): _priced(0.10, age_hours=age_hours),
        },
        now=NOW,
    )
    board = payload["boards"][0]
    assert board["price_state"] != "live"
    assert all(row["probability_is_live"] is False for row in board["rows"])


def test_stale_row_still_carries_its_number_and_its_age():
    """We show that we do not know — we do not show nothing.

    Dropping the number loses real information; printing it as live is a lie.
    The resolution is to print it WITH its age, which is why both fields are
    required to be present rather than one of them being optional.
    """
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.50, age_hours=8 * 24),
            ("polymarket", 2, 20): _priced(0.54, age_hours=8 * 24),
        },
        now=NOW,
    )
    row = payload["boards"][0]["rows"][0]
    assert row["probability"] == pytest.approx(0.52)
    assert row["probability_is_live"] is False
    assert row["observed_at"] is not None
    assert row["age_hours"] == pytest.approx(192.0)
    assert row["price_state"] == "dark"


def test_board_age_is_the_newest_reading_not_the_oldest():
    """One fresh row does not make the board fresh, and one stale row does not
    make it stale. The board reports the newest thing anyone has seen, because
    that is the strongest true claim available about the page as a whole."""
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.50, age_hours=200),
            ("polymarket", 2, 20): _priced(0.54, age_hours=200),
            ("kalshi", 1, 11): _priced(0.10, age_hours=1),
        },
        now=NOW,
    )
    board = payload["boards"][0]
    assert board["price_state"] == "live"
    assert board["age_hours"] == pytest.approx(1.0)
    # ...and the individually stale row is STILL not live. A healthy board
    # never launders a stale row.
    stale_row = next(r for r in board["rows"] if r["entity_key"] == "player-a")
    assert stale_row["probability_is_live"] is False
    assert stale_row["price_state"] == "dark"


def test_live_row_is_marked_live():
    """The guard must be able to say yes, or it is asserting nothing."""
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.50, age_hours=0.5),
            ("polymarket", 2, 20): _priced(0.54, age_hours=0.5),
        },
        now=NOW,
    )
    row = payload["boards"][0]["rows"][0]
    assert row["probability_is_live"] is True
    assert row["price_state"] == "live"


# ---------------------------------------------------------------------------
# THE MIXED-CONTRIBUTOR BOUNDARY — the gap `C-USOPEN-DAY3-TIER2` named
#
# Every test above this block puts contributors of the SAME age in a row, or a
# stale row BESIDE a fresh one. Both stayed green through the real defect,
# which is why the cert found it and the suite did not: the failure lives
# INSIDE one row, between its own legs. The reviewer's specimen verbatim —
# 1h Kalshi 0.40 + 20d Polymarket 0.44 -> blended 0.42 rendered live.
#
# The kill criterion these encode: *a row may not be presented live while any
# value contributing to its published blend is stale or dark.*
# ---------------------------------------------------------------------------

def _mixed_row(fresh_age: float, stale_age: float, now=NOW):
    """One row, two contributors, two different ages."""
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.40, age_hours=fresh_age),
            ("polymarket", 2, 20): _priced(0.44, age_hours=stale_age),
        },
        now=now,
    )
    return next(
        r for r in payload["boards"][0]["rows"] if r["entity_key"] == "player-a"
    )


def test_the_reviewers_specimen_does_not_read_live():
    """1h Kalshi + 20d Polymarket -> 0.42, and it is NOT a live number.

    The number is still published — it is the best estimate we have and
    dropping it throws away the fresh half too. What is refused is the
    CONFIDENCE: `probability_is_live` is false, so the client renders it muted
    with its age, exactly as it would a wholly stale row.
    """
    row = _mixed_row(fresh_age=1.0, stale_age=20 * 24)
    assert row["probability"] == pytest.approx(0.42)
    assert row["probability_is_live"] is False
    assert row["price_state"] == "dark"


def test_a_mixed_row_ages_from_its_OLDEST_contributor():
    """`age_hours` describes the number as printed, not its luckiest leg.

    "1 hour ago" was never true of a blend that contains a twenty-day-old
    value. The governing age is the oldest, so the label the reader sees is
    the one that is true of the whole row.
    """
    row = _mixed_row(fresh_age=1.0, stale_age=20 * 24)
    assert row["age_hours"] == pytest.approx(480.0)
    assert row["observed_at"] == (NOW - timedelta(hours=20 * 24)).isoformat()


def test_a_mixed_row_still_shows_the_freshest_reading():
    """Honest partial freshness: the fresh leg is not hidden, only demoted.

    Suppressing it would tell the reader nothing moved today when half the row
    did. It is a separate field from `observed_at` so that a client reading
    only the obvious name gets the pessimistic answer.
    """
    row = _mixed_row(fresh_age=1.0, stale_age=20 * 24)
    assert row["freshest_age_hours"] == pytest.approx(1.0)
    assert row["freshest_observed_at"] == (NOW - timedelta(hours=1)).isoformat()
    assert row["mixed_freshness"] is True
    assert row["stale_sources"] == ["polymarket"]


def test_a_mixed_row_names_the_stale_contributor_per_source():
    """Each source carries its own verdict, so the UI can say WHICH leg is old."""
    row = _mixed_row(fresh_age=1.0, stale_age=20 * 24)
    by_source = {s["source"]: s for s in row["sources"]}
    assert by_source["kalshi"]["price_state"] == "live"
    assert by_source["kalshi"]["age_hours"] == pytest.approx(1.0)
    assert by_source["polymarket"]["price_state"] == "dark"
    assert by_source["polymarket"]["age_hours"] == pytest.approx(480.0)


@pytest.mark.parametrize(
    "stale_age",
    [
        STALE_PRICE_HOURS + 0.01,   # the first instant it is not live
        DARK_PRICE_HOURS,           # the last instant it is merely stale
        DARK_PRICE_HOURS + 0.01,    # the first instant it is dark
        20 * 24,                    # the reviewer's specimen
        32 * 24,                    # the #2199 population's far end
    ],
)
def test_one_non_live_contributor_is_enough_to_kill_the_row(stale_age):
    """The AND, swept across the boundary. ONE is enough — there is no quorum.

    Parametrized over the thresholds rather than one comfortable value: an
    off-by-one at `STALE_PRICE_HOURS` is precisely the bug that would let the
    common case through while the dramatic 20-day case looks guarded.
    """
    row = _mixed_row(fresh_age=0.1, stale_age=stale_age)
    assert row["probability_is_live"] is False
    assert row["mixed_freshness"] is True


def test_a_row_is_live_only_when_EVERY_contributor_is_live():
    """The positive direction, or the AND is asserting nothing.

    Both legs inside the window, both ages different — the guard must not have
    become "reject anything with unequal timestamps".
    """
    row = _mixed_row(fresh_age=0.1, stale_age=STALE_PRICE_HOURS)
    assert row["probability_is_live"] is True
    assert row["price_state"] == "live"
    assert row["mixed_freshness"] is False
    assert row["stale_sources"] == []
    # ...and the governing age is still the older of the two.
    assert row["age_hours"] == pytest.approx(STALE_PRICE_HOURS)


def test_a_fresh_leg_beside_a_never_observed_leg_is_not_live():
    """An absent timestamp is older than any timestamp (gotcha #53).

    The mixed version of `test_price_with_no_observation_time_is_not_live`:
    one contributor with a real reading cannot vouch for one that has none.
    """
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.40, age_hours=0.1),
            ("polymarket", 2, 20): {"probability": 0.44, "observed_at": None},
        },
        now=NOW,
    )
    row = payload["boards"][0]["rows"][0]
    assert row["probability"] == pytest.approx(0.42)
    assert row["probability_is_live"] is False
    assert row["price_state"] == "dark"
    assert row["age_hours"] is None
    assert row["observed_at"] is None
    # The fresh leg is still reported — the row knows more than "never".
    assert row["freshest_age_hours"] == pytest.approx(0.1)


def test_the_board_banner_is_still_the_newest_reading_not_the_governing_one():
    """The AND is a ROW rule and must not have leaked up to the board.

    A board whose banner fired because one of forty rows carries a 30-day leg
    would be a banner nobody reads. Rows are individually honest; the board
    reports the strongest true claim about the page.
    """
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.40, age_hours=1.0),
            ("polymarket", 2, 20): _priced(0.44, age_hours=20 * 24),
            ("kalshi", 1, 11): _priced(0.10, age_hours=0.5),
        },
        now=NOW,
    )
    board = payload["boards"][0]
    assert board["price_state"] == "live"
    assert board["age_hours"] == pytest.approx(0.5)
    # ...and the mixed row inside it is counted rather than described.
    assert board["mixed_freshness_rows"] == 1
    assert board["rows_not_live"] == 1


def test_a_single_source_row_is_unaffected_by_the_AND():
    """A one-legged row has nothing to disagree with itself about.

    Guards the regression risk in the other direction: an AND implemented over
    an empty or singleton list must not start refusing the simple case.
    """
    payload = build_boards(
        _two_source_register(),
        prices={("kalshi", 1, 11): _priced(0.10, age_hours=1.0)},
        now=NOW,
    )
    row = next(
        r for r in payload["boards"][0]["rows"] if r["entity_key"] == "player-b"
    )
    assert row["source_count"] == 1
    assert row["probability_is_live"] is True
    assert row["mixed_freshness"] is False


def test_price_with_no_observation_time_is_not_live():
    payload = build_boards(
        _two_source_register(),
        prices={("kalshi", 1, 10): {"probability": 0.50, "observed_at": None}},
        now=NOW,
    )
    row = payload["boards"][0]["rows"][0]
    assert row["probability"] == pytest.approx(0.50)
    assert row["probability_is_live"] is False
    assert row["observed_at"] is None


# ---------------------------------------------------------------------------
# The register is the membership rule
# ---------------------------------------------------------------------------

def test_unregistered_identity_never_reaches_a_board():
    """A market not in the register does not render — charter data doctrine."""
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.50),
            ("polymarket", 2, 20): _priced(0.54),
            ("kalshi", 1, 11): _priced(0.10),
            # Not pinned by the register. It is real, it is priced, and it
            # outranks everything on the board — and it must not appear.
            ("kalshi", 99, 999): _priced(0.99),
        },
        now=NOW,
    )
    board = payload["boards"][0]
    assert [r["entity_key"] for r in board["rows"]] == ["player-a", "player-b"]
    assert all(r["probability"] != pytest.approx(0.99) for r in board["rows"])
    assert payload["render_findings"] == []


def test_registered_player_with_no_price_is_counted_not_invented():
    payload = build_boards(
        _two_source_register(),
        prices={("kalshi", 1, 10): _priced(0.50)},
        now=NOW,
    )
    board = payload["boards"][0]
    assert [r["entity_key"] for r in board["rows"]] == ["player-a"]
    assert board["unpriced"] == 1
    assert board["contenders"] == 1


def test_settled_source_renders_a_result_never_a_probability():
    """Settled means settled — the standing ruling, enforced at the boundary."""
    register = _register(
        [
            _player(
                "player-c",
                "Player C",
                "mens-singles",
                [
                    _source(
                        "kalshi", 1, 12, status="settled", terminal_result="lost"
                    )
                ],
            )
        ]
    )
    payload = build_boards(
        register,
        # Even with a price sitting right there, a settled row must not print it.
        prices={("kalshi", 1, 12): _priced(0.42)},
        now=NOW,
    )
    row = payload["boards"][0]["rows"][0]
    assert row["state"] == "lost"
    assert row["probability"] is None
    assert row["probability_is_live"] is False
    assert payload["render_findings"] == []


def test_missing_source_produces_no_probability():
    register = _register(
        [
            _player(
                "player-d",
                "Player D",
                "womens-singles",
                [_source("kalshi", 3, 13, status="missing")],
            )
        ]
    )
    payload = build_boards(register, prices={}, now=NOW)
    board = payload["boards"][0]
    assert board["rows"] == []
    assert board["unpriced"] == 1
    assert payload["render_findings"] == []


# ---------------------------------------------------------------------------
# Ranking and blending
# ---------------------------------------------------------------------------

def test_rows_rank_by_blend_descending():
    register = _register(
        [
            _player("low", "Low", "mens-singles", [_source("kalshi", 1, 1)]),
            _player("high", "High", "mens-singles", [_source("kalshi", 1, 2)]),
            _player("mid", "Mid", "mens-singles", [_source("kalshi", 1, 3)]),
        ]
    )
    payload = build_boards(
        register,
        prices={
            ("kalshi", 1, 1): _priced(0.05),
            ("kalshi", 1, 2): _priced(0.52),
            ("kalshi", 1, 3): _priced(0.20),
        },
        now=NOW,
    )
    rows = payload["boards"][0]["rows"]
    assert [r["entity_key"] for r in rows] == ["high", "mid", "low"]
    assert [r["rank"] for r in rows] == [1, 2, 3]


def test_equal_weight_pair_prints_the_midpoint_not_the_lower_value():
    """Reuses the repo's blend; does not fork a second aggregator.

    kalshi and polymarket both weigh 0.8, and ruling-era work established that
    the weighted median on an equal-weight pair is a systematic downward
    discount rather than a tiebreak. If this ever prints 0.50 again, the board
    has stopped using `blend_with_verdict`.
    """
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.50),
            ("polymarket", 2, 20): _priced(0.54),
        },
        now=NOW,
    )
    row = payload["boards"][0]["rows"][0]
    assert row["probability"] == pytest.approx(0.52)
    assert row["blend_rule"] == "equal_weight_midpoint"
    assert row["source_count"] == 2
    assert row["divergent"] is False


def test_divergent_pair_is_flagged_and_does_not_print_a_midpoint():
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.575),
            ("polymarket", 2, 20): _priced(0.060),
        },
        now=NOW,
    )
    row = payload["boards"][0]["rows"][0]
    assert row["divergent"] is True
    assert row["blend_rule"] == "divergence_gate"
    assert row["probability"] != pytest.approx((0.575 + 0.060) / 2)


def test_sources_travel_with_the_row_but_the_blend_is_the_headline():
    """Sources present so the UI can whisper "2 sources"; never a comparison."""
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.50),
            ("polymarket", 2, 20): _priced(0.54),
        },
        now=NOW,
    )
    row = payload["boards"][0]["rows"][0]
    assert {s["source"] for s in row["sources"]} == {"kalshi", "polymarket"}
    assert all(s["observed_at"] is not None for s in row["sources"])


# ---------------------------------------------------------------------------
# Trend lines — unsmoothed, one rule, real days only
# ---------------------------------------------------------------------------

def test_trend_carries_only_days_that_were_actually_observed():
    """No interpolation across the gap. A hole in the data is a hole in the line."""
    payload = build_boards(
        _two_source_register(),
        prices={("kalshi", 1, 10): _priced(0.50)},
        series_by_outcome={
            10: [("2026-08-20", 0.40), ("2026-08-21", 0.44), ("2026-08-25", 0.50)]
        },
        now=NOW,
    )
    row = payload["boards"][0]["rows"][0]
    assert [p["date"] for p in row["trend"]] == [
        "2026-08-20",
        "2026-08-21",
        "2026-08-25",
    ]
    assert [p["probability"] for p in row["trend"]] == [0.40, 0.44, 0.50]


def test_trend_delta_is_last_minus_first():
    payload = build_boards(
        _two_source_register(),
        prices={("kalshi", 1, 10): _priced(0.50)},
        series_by_outcome={10: [("2026-08-20", 0.40), ("2026-08-25", 0.50)]},
        now=NOW,
    )
    assert payload["boards"][0]["rows"][0]["trend_delta"] == pytest.approx(0.10)


def test_single_point_trend_has_no_delta():
    payload = build_boards(
        _two_source_register(),
        prices={("kalshi", 1, 10): _priced(0.50)},
        series_by_outcome={10: [("2026-08-25", 0.50)]},
        now=NOW,
    )
    assert payload["boards"][0]["rows"][0]["trend_delta"] is None


def test_trend_uses_the_same_blend_rule_as_the_headline():
    """Both sources on one day → the day is a midpoint, exactly like the headline.

    A mean would agree here by coincidence; the next test is the one that
    separates them.
    """
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.50),
            ("polymarket", 2, 20): _priced(0.54),
        },
        series_by_outcome={
            10: [("2026-08-24", 0.50)],
            20: [("2026-08-24", 0.54)],
        },
        now=NOW,
    )
    trend = payload["boards"][0]["rows"][0]["trend"]
    assert trend == [{"date": "2026-08-24", "probability": pytest.approx(0.52)}]


def test_a_divergent_day_is_gated_in_the_trend_too_not_meaned():
    """The distinction a mean would erase.

    On a day where the two sources are 50+ points apart, the headline rule
    refuses to average them. The trend must refuse identically, or the line
    plots a number the page has decided it will not print.
    """
    payload = build_boards(
        _two_source_register(),
        prices={
            ("kalshi", 1, 10): _priced(0.575),
            ("polymarket", 2, 20): _priced(0.060),
        },
        series_by_outcome={
            10: [("2026-08-24", 0.575)],
            20: [("2026-08-24", 0.060)],
        },
        now=NOW,
    )
    point = payload["boards"][0]["rows"][0]["trend"][0]
    assert point["probability"] != pytest.approx((0.575 + 0.060) / 2)
    assert point["probability"] == pytest.approx(
        payload["boards"][0]["rows"][0]["probability"]
    )


# ---------------------------------------------------------------------------
# Page shape
# ---------------------------------------------------------------------------

def test_both_draws_produce_their_own_board():
    register = _register(
        [
            _player("m1", "M One", "mens-singles", [_source("kalshi", 1, 1)]),
            _player("w1", "W One", "womens-singles", [_source("kalshi", 2, 2)]),
        ]
    )
    payload = build_boards(
        register,
        prices={("kalshi", 1, 1): _priced(0.3), ("kalshi", 2, 2): _priced(0.4)},
        now=NOW,
    )
    assert [b["draw"] for b in payload["boards"]] == [
        "mens-singles",
        "womens-singles",
    ]
    assert [b["label"] for b in payload["boards"]] == [
        "Men's Singles",
        "Women's Singles",
    ]


def test_a_register_with_one_draw_produces_one_board():
    """No empty second board invented to satisfy a constant."""
    payload = build_boards(
        _two_source_register(),
        prices={("kalshi", 1, 10): _priced(0.5)},
        now=NOW,
    )
    assert len(payload["boards"]) == 1


def test_draw_label_falls_back_readably():
    assert draw_label("mens-singles") == "Men's Singles"
    assert draw_label("mens-doubles") == "Mens Doubles"


def test_payload_carries_register_provenance():
    payload = build_boards(_two_source_register(), prices={}, now=NOW)
    assert payload["tournament"] == "us-open"
    assert payload["season"] == "2026"
    assert payload["register_version"] == 1
    assert payload["draw_released"] is False
    assert payload["generated_at"] == NOW.isoformat()


def test_empty_prices_is_an_honest_empty_board_not_a_crash():
    payload = build_boards(_two_source_register(), prices={}, now=NOW)
    board = payload["boards"][0]
    assert board["rows"] == []
    assert board["contenders"] == 0
    assert board["unpriced"] == 2
    assert board["price_state"] == "dark"
    assert board["newest_observed_at"] is None


def test_trend_window_constant_is_bounded():
    """A trend line is a page element, not an archive."""
    assert 7 <= TREND_DAYS <= 90


# ---------------------------------------------------------------------------
# The contract, asserted as a contract
# ---------------------------------------------------------------------------

def test_no_row_anywhere_claims_live_without_a_fresh_observation():
    """The invariant stated once, over a mixed board.

    This is the assertion the page's honesty actually rests on: whatever the
    ranking, whatever the source count, `probability_is_live` is true only when
    EVERY value inside the row's published blend is inside the stale window.
    Written as a sweep so a future row shape cannot slip past the per-case
    tests above.

    UX-P135 widened it. The sweep originally held only single-source rows, so
    it could not have caught `C-USOPEN-DAY3-TIER2` — it asserted the row's
    stated age was fresh, which was true of the mixed row's newest leg. Two
    multi-source rows are now in it, and the assertion is over every
    CONTRIBUTOR's age rather than the row's summary.
    """
    register = _register(
        [
            _player("fresh", "Fresh", "mens-singles", [_source("kalshi", 1, 1)]),
            _player("stale", "Stale", "mens-singles", [_source("kalshi", 1, 2)]),
            _player("dark", "Dark", "mens-singles", [_source("kalshi", 1, 3)]),
            _player("unseen", "Unseen", "mens-singles", [_source("kalshi", 1, 4)]),
            # The specimen: fresh Kalshi, twenty-day Polymarket.
            _player(
                "mixed",
                "Mixed",
                "mens-singles",
                [_source("kalshi", 1, 5), _source("polymarket", 2, 6)],
            ),
            # ...and its healthy twin, so the sweep can say yes to a blend.
            _player(
                "both-fresh",
                "Both Fresh",
                "mens-singles",
                [_source("kalshi", 1, 7), _source("polymarket", 2, 8)],
            ),
        ]
    )
    payload = build_boards(
        register,
        prices={
            ("kalshi", 1, 1): _priced(0.40, age_hours=1),
            ("kalshi", 1, 2): _priced(0.30, age_hours=STALE_PRICE_HOURS + 2),
            ("kalshi", 1, 3): _priced(0.20, age_hours=30 * 24),
            ("kalshi", 1, 4): {"probability": 0.10, "observed_at": None},
            ("kalshi", 1, 5): _priced(0.40, age_hours=1),
            ("polymarket", 2, 6): _priced(0.44, age_hours=20 * 24),
            ("kalshi", 1, 7): _priced(0.55, age_hours=1),
            ("polymarket", 2, 8): _priced(0.57, age_hours=2),
        },
        now=NOW,
    )
    for row in payload["boards"][0]["rows"]:
        if row["probability_is_live"]:
            assert row["age_hours"] is not None
            assert row["age_hours"] <= STALE_PRICE_HOURS
            # THE CONTRIBUTOR-LEVEL FORM. The summary age agreeing is not
            # enough — that is precisely what stayed green through the defect.
            assert row["stale_sources"] == []
            for source in row["sources"]:
                assert source["age_hours"] is not None
                assert source["age_hours"] <= STALE_PRICE_HOURS
        else:
            assert row["price_state"] in ("stale", "dark")
    live = sorted(
        r["entity_key"] for r in payload["boards"][0]["rows"] if r["probability_is_live"]
    )
    assert live == ["both-fresh", "fresh"]


# ---------------------------------------------------------------------------
# Contenders only — the second population pass must not contaminate the boards
# (UX-P132)
# ---------------------------------------------------------------------------

def _participant(entity_key: str, name: str, draw: str):
    """A qualifying-draw player: registered identity, no outright price."""
    return {
        "entity_key": entity_key,
        "display_name": name,
        "draw": draw,
        "role": "participant",
        "seed": None,
        "country": None,
        "draw_slot": None,
        "section": None,
        "sources": [],
    }


def test_a_participant_never_reaches_a_board():
    """The defect this prevents: a first-round qualifier ranked above Alcaraz.

    A participant's only quote is P(wins this match). Ranked on a championship
    board it is not a wrong number — it is an answer to a different question,
    which is worse, because it looks entirely plausible.
    """
    register = _register([
        _player("carlos-alcaraz", "Carlos Alcaraz", "mens-singles",
                [_source("kalshi", 1, 11)]),
        _participant("diego-dedura-palomero", "Diego Dedura-Palomero", "mens-singles"),
    ])
    payload = build_boards(
        register,
        prices={("kalshi", 1, 11): _priced(0.30)},
        now=NOW,
    )
    board = payload["boards"][0]
    assert [row["entity_key"] for row in board["rows"]] == ["carlos-alcaraz"]
    # And they do not inflate the "more registered players have no price" line.
    assert board["unpriced"] == 0
    assert board["contenders"] == 1


def test_a_draw_with_only_participants_produces_no_board():
    """A qualifying-only draw has no championship board to build."""
    register = _register([
        _player("carlos-alcaraz", "Carlos Alcaraz", "mens-singles",
                [_source("kalshi", 1, 11)]),
        _participant("aliona-falei", "Aliona Falei", "womens-singles"),
    ])
    payload = build_boards(
        register, prices={("kalshi", 1, 11): _priced(0.30)}, now=NOW
    )
    assert [b["draw"] for b in payload["boards"]] == ["mens-singles"]


def test_a_v1_register_without_roles_still_renders_every_player():
    """Backwards compatibility: absent `role` reads as contender, not as nothing."""
    register = _register([
        _player("carlos-alcaraz", "Carlos Alcaraz", "mens-singles",
                [_source("kalshi", 1, 11)]),
        _player("jannik-sinner", "Jannik Sinner", "mens-singles",
                [_source("kalshi", 1, 12)]),
    ])
    assert all("role" not in p for p in register["players"])
    payload = build_boards(
        register,
        prices={("kalshi", 1, 11): _priced(0.30), ("kalshi", 1, 12): _priced(0.52)},
        now=NOW,
    )
    assert len(payload["boards"][0]["rows"]) == 2
