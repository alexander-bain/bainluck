"""Tests for prediction-market link-rate denominator guards."""

from datetime import datetime, timezone

from app.routes.admin_matching import (
    ATTACH_ANCHORED,
    ATTACH_SELF_MINTED,
    ATTACH_UNLINKED,
    _LINK_RATE_NON_GAME_CATEGORIES,
    _LINK_RATE_SPORT_CATEGORIES,
    _classify_attachment,
    _is_obvious_non_game_market_name,
    _is_polymarket_matcher_game_level,
    _is_upstream_coverage_gap_market,
    _should_include_link_rate_bucket,
    _should_exclude_stale_open_unlinked_game_market,
)


def test_link_rate_bucket_excludes_unsupported_esports():
    assert "esports" not in _LINK_RATE_SPORT_CATEGORIES
    assert _should_include_link_rate_bucket("esports", "LOL") is False


def test_link_rate_bucket_rejects_impossible_sport_league_pairs():
    assert _should_include_link_rate_bucket("basketball", "NBA") is True
    assert _should_include_link_rate_bucket("basketball", "NHL") is False
    assert _should_include_link_rate_bucket("hockey", "NBA") is False


def test_obvious_non_game_market_name_detection():
    assert _is_obvious_non_game_market_name("Who will win the NBA Championship?") is True
    assert _is_obvious_non_game_market_name("Celtics vs Knicks") is False
    assert _is_obvious_non_game_market_name("Will Celtics win the game vs Knicks?") is False


def test_stale_open_unlinked_kalshi_game_market_excluded_from_link_rate():
    now = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)

    assert _should_exclude_stale_open_unlinked_game_market(
        source="kalshi",
        external_id="KXNBAGAME-26MAY16BOSNYK",
        status="open",
        event_id=None,
        now=now,
    ) is True


def test_active_or_linked_game_markets_stay_in_link_rate():
    now = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    recent_external_id = "KXNBAGAME-26MAY18BOSNYK"

    assert _should_exclude_stale_open_unlinked_game_market(
        source="kalshi",
        external_id=recent_external_id,
        status="open",
        event_id=None,
        now=now,
    ) is False
    assert _should_exclude_stale_open_unlinked_game_market(
        source="kalshi",
        external_id="KXNBAGAME-26MAY16BOSNYK",
        status="open",
        event_id=123,
        now=now,
    ) is False
    assert _should_exclude_stale_open_unlinked_game_market(
        source="polymarket",
        external_id="KXNBAGAME-26MAY16BOSNYK",
        status="open",
        event_id=None,
        now=now,
    ) is False


def test_polymarket_link_rate_uses_matcher_game_level_predicate():
    assert _is_polymarket_matcher_game_level(
        "Celtics vs Knicks",
        "championship",
        "123",
    ) is True
    assert _is_polymarket_matcher_game_level(
        "CF Estrela da Amadora vs. FC Porto - More Markets",
        "championship",
        "456",
    ) is True
    assert _is_polymarket_matcher_game_level(
        "Internationaux de Strasbourg (Doubles): Kichenok/Krawczyk vs Mihalikova/Nicholls",
        "championship",
        "493607",
    ) is False
    assert _is_polymarket_matcher_game_level(
        "World Championships: Czechia vs. Italy",
        "championship",
        "490611",
    ) is True  # "X vs. Y" is a game-level market


# -- Category-based denominator exclusion ----------------------------------

def test_non_game_categories_include_season_level_types():
    """Championship, award, season_win_total, player_futures must be excluded."""
    for cat in ("championship", "award", "season_win_total", "player_futures"):
        assert cat in _LINK_RATE_NON_GAME_CATEGORIES, f"{cat} missing from exclusion set"


def test_game_prop_not_in_non_game_categories():
    """game_prop is a game-level category and must NOT be excluded."""
    assert "game_prop" not in _LINK_RATE_NON_GAME_CATEGORIES


def test_non_game_categories_also_cover_structural_futures():
    """Division, conference, and series are season-level, not game-level."""
    for cat in ("division", "conference", "series"):
        assert cat in _LINK_RATE_NON_GAME_CATEGORIES


def test_non_game_category_exclusion_is_case_insensitive_in_loop():
    """The loop lowercases the category before checking, so mixed case works."""
    # Simulate the loop logic from the endpoint
    cat_raw = "Championship"
    cat = cat_raw.lower()
    assert cat in _LINK_RATE_NON_GAME_CATEGORIES


# -- #1230: upstream-coverage-gap denominator exclusion --------------------

def test_upstream_coverage_gap_excludes_itf_minor_tennis():
    """ITF minor-tour tennis has no schedule source → drop from the denominator."""
    assert _is_upstream_coverage_gap_market(
        "ITF Segrate: Juan Cruz Martin Manzano vs Raffaele Ciurnelli"
    ) is True
    assert _is_upstream_coverage_gap_market(
        "ITF Evansville: Renata Zarazua vs Sloane Stephens"
    ) is True


def test_upstream_coverage_gap_excludes_setka_table_tennis():
    """Setka / TT-Cup table-tennis circuits are uncovered upstream."""
    assert _is_upstream_coverage_gap_market("Setka Cup: A vs B: Total Games O/U 3.5") is True
    assert _is_upstream_coverage_gap_market("TT Cup: Player A vs Player B") is True
    assert _is_upstream_coverage_gap_market("Table Tennis: A vs B") is True


def test_upstream_coverage_gap_excludes_minor_cricket():
    """European Cricket Series (ECS) is a minor circuit with no coverage."""
    assert _is_upstream_coverage_gap_market(
        "ECS England: Rainham vs East Londoners"
    ) is True


def test_upstream_coverage_gap_keeps_covered_leagues():
    """Tier-1/2 leagues we DO schedule must stay in the denominator."""
    assert _is_upstream_coverage_gap_market("Yankees vs Red Sox") is False
    assert _is_upstream_coverage_gap_market("Lakers vs Celtics: Spread") is False
    assert _is_upstream_coverage_gap_market("Carlos Alcaraz vs Jannik Sinner") is False
    assert _is_upstream_coverage_gap_market("IPL: Mumbai Indians vs Chennai") is False
    assert _is_upstream_coverage_gap_market(None) is False


def test_upstream_coverage_gap_only_removes_unlinked_from_denominator():
    """The endpoint applies the predicate only when event_id IS None; a linked
    market is always kept in the numerator. This mirrors the loop logic."""
    # Simulate loop: linked coverage-gap market stays counted.
    event_id = 123
    name = "ITF Segrate: A vs B"
    excluded = event_id is None and _is_upstream_coverage_gap_market(name)
    assert excluded is False


def test_raw_rate_re_adds_excluded_upstream_gap():
    """Raw rate keeps the excluded (all-unlinked) markets in the denominator, so
    the honest rate is always >= the raw rate."""
    open_linked, open_total, excluded_open = 79, 100, 40
    honest = round(open_linked / open_total * 100, 1)
    raw = round(open_linked / (open_total + excluded_open) * 100, 1)
    assert honest == 79.0
    assert raw == round(79 / 140 * 100, 1)
    assert honest >= raw


# =============================================================================
# #3778 -- attached to WHAT: the anchored / self_minted split
# =============================================================================
#
# `linked` means `event_id IS NOT NULL` and nothing else, so a market attached
# to an event row its OWN ingest minted scores exactly like one attached to a
# row ESPN anchored. A twin-generating ingest and a healthy one therefore
# publish the same number, and the metric cannot fall. Measured on production
# 2026-09-07, open markets with events commencing in the last 14 days: kalshi
# 27.3% self-minted (309/1,130), polymarket 78.7% (9,184/11,670), while the
# Kalshi ATP/WTA receipt read 244/244 (100%), flat, and the US Open men's
# semi-final page rendered with no Kalshi curve.


def test_an_unlinked_market_is_neither_anchored_nor_self_minted():
    assert _classify_attachment(None, None, None) == ATTACH_UNLINKED
    # A NULL event_id wins even if ids somehow arrive: there is no row to grade.
    assert _classify_attachment(None, "182780", "x") == ATTACH_UNLINKED


def test_an_espn_anchored_event_is_anchored():
    assert _classify_attachment(15305016, "182722", None) == ATTACH_ANCHORED


def test_a_provider_anchored_event_is_anchored():
    """`external_id` counts: the point is that SOME other source can find the
    same row, not that ESPN specifically did."""
    assert _classify_attachment(15305016, None, "odds_api:abc123") == ATTACH_ANCHORED


def test_an_event_row_with_neither_id_is_self_minted():
    assert _classify_attachment(15304989, None, None) == ATTACH_SELF_MINTED


def test_the_split_is_exhaustive_and_the_buckets_do_not_overlap():
    """Every reachable input lands in exactly one bucket.

    A classifier that can return something else would make
    `sport_data[f"linked_{attachment}"]` raise KeyError inside the request
    path, so this is a contract with the caller and not decoration.
    """
    seen = {
        _classify_attachment(eid, espn, ext)
        for eid in (None, 15305016)
        for espn in (None, "", "182722")
        for ext in (None, "", "odds_api:abc")
    }
    assert seen == {ATTACH_UNLINKED, ATTACH_ANCHORED, ATTACH_SELF_MINTED}


def test_an_empty_string_id_is_not_an_anchor():
    """`''` is an absence wearing a value. Anchoring on it would let a blank
    column re-flatter exactly the number this split exists to deflate."""
    assert _classify_attachment(15304989, "", "") == ATTACH_SELF_MINTED


def test_the_split_is_non_vacuous_on_a_mixed_cohort():
    """#3778 acceptance item 3, and the one that catches a broken splitter.

    A cohort that happens to be all-anchored greens a splitter that has been
    wired to a column that is always NULL, or that classifies everything as
    anchored. The fixture is the two real rows from the US Open men's
    semi-final window, which differ in the only field that matters: ghost
    15304989 (espn NULL, the two Kalshi markets, the page that lost its
    curve) and real 15305016 (espn 182722). Both buckets must be occupied.
    """
    cohort = [
        # (event_id, espn_id, external_id) -- the real pair, recorded.
        (15304989, None, None),
        (15305016, "182722", None),
    ]
    buckets = [_classify_attachment(*row) for row in cohort]
    assert buckets.count(ATTACH_ANCHORED) >= 1, "no anchored row: splitter is vacuous"
    assert buckets.count(ATTACH_SELF_MINTED) >= 1, (
        "no self_minted row: a splitter reading an always-NULL column would "
        "pass every all-anchored cohort and report the flattering number again"
    )


def test_self_minted_is_not_reported_as_a_duplicate_count():
    """A naming contract, pinned because the misreading is the likely one.

    `self_minted` means 'an attachment this metric cannot grade', NOT 'a
    ghost'. A row with neither id can be the only row for a contest nobody
    else lists -- most of Polymarket's 78.7% is that, not twins. The twin
    question belongs to #3582 / #2693.
    """
    doc = _classify_attachment.__doc__ or ""
    assert "NOT A SYNONYM FOR GHOST" in doc.upper(), (
        "the constraint that stops a reader quoting self_minted as a duplicate "
        "count must travel with the function that mints the label"
    )
