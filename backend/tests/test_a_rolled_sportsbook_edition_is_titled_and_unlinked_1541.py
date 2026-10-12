"""#1541 — a rolled sportsbook board names its own edition and never links the settled one.

THE DEFECT, on production 2026-10-12 17:04Z. `/futures/7` (odds_api
`golf_us_open_winner`, open) read "US Open Winner · Scottie Scheffler 13%" with
current prices, and its "Part of: US Open" breadcrumb opened
`/event/golf/u-s-open` — GOLF SETTLED MAJOR, Jun 18–21, Wyndham Clark WON. The
row's retained provider identity (`market_metadata.odds_api_current_event`, polled
16:33Z) is event `3eebece4…`, commence **2027-06-17**: every quote is the 2027 US
Open. The bare name made no edition claim, so the #7792 guard kept the link into
the edition the concept page serves.

Three arms:
  1. the anchor reader (`read_odds_api_anchor`) — the single reading of the
     identity, shared with `member_of`, refusing missing/malformed/stale anchors;
  2. the deriver — a provider edition year other than the one in play withholds
     the link exactly like a named foreign year, and a bare name with no instant
     keeps it (control);
  3. the served detail payload from `_format_market_detail` — `edition_year` and
     `event_concept_key` read off the real serializer for the market-7 shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.utils.concept_links import derive_market_concept_key
from app.utils.futures_verified_title import Refusal, read_odds_api_anchor

KEY = "golf_us_open_winner"
NAME = "US Open Winner"
CONCEPT = "event:golf:u-s-open"

# Fixed clock for the pure arms (gotcha #44): the production read's own instant.
CLOCK = datetime(2026, 10, 12, 17, 4, tzinfo=timezone.utc)
POLLED = datetime(2026, 10, 12, 16, 33, 3, tzinfo=timezone.utc)
COMMENCE_2027 = datetime(2027, 6, 17, 10, 0, tzinfo=timezone.utc)
COMMENCE_2026 = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)


def _identity(commence: datetime, polled: datetime, **overrides) -> dict:
    ident = {
        "scope": "current_quotes_only",
        "event_id": "3eebece4661c5d29038bcf7c79a74dff",
        "sport_key": KEY,
        "commence_time": commence.isoformat(),
        "polled_at": polled.isoformat(),
    }
    ident.update(overrides)
    return ident


# ── 1. the anchor reader ────────────────────────────────────────────────────


def test_a_current_anchor_reads_the_provider_edition():
    read = read_odds_api_anchor(
        {"odds_api_current_event": _identity(COMMENCE_2027, POLLED)}, KEY, CLOCK
    )
    assert read == (COMMENCE_2027, POLLED)


def test_an_absent_anchor_is_refused_not_guessed():
    assert read_odds_api_anchor({}, KEY, CLOCK) == Refusal("anchor_missing")
    assert read_odds_api_anchor(None, KEY, CLOCK) == Refusal("anchor_missing")


def test_another_keys_anchor_is_refused():
    meta = {"odds_api_current_event": _identity(COMMENCE_2027, POLLED, sport_key="golf_masters_tournament_winner")}
    assert read_odds_api_anchor(meta, KEY, CLOCK) == Refusal("anchor_malformed")


def test_a_stale_anchor_is_refused():
    meta = {"odds_api_current_event": _identity(COMMENCE_2027, CLOCK - timedelta(hours=13))}
    assert read_odds_api_anchor(meta, KEY, CLOCK) == Refusal("anchor_stale")


def test_a_naive_commence_is_refused():
    meta = {"odds_api_current_event": _identity(COMMENCE_2027, POLLED, commence_time="2027-06-17T10:00:00")}
    assert read_odds_api_anchor(meta, KEY, CLOCK) == Refusal("anchor_malformed")


# ── 2. the deriver ──────────────────────────────────────────────────────────


def test_a_bare_name_with_no_edition_keeps_its_link():
    """Control: without an instant the bare name still resolves (the #7792 shape)."""
    assert derive_market_concept_key(KEY, NAME, "golf", 205, now=CLOCK) == CONCEPT


def test_a_next_year_provider_edition_gets_no_link():
    assert derive_market_concept_key(
        KEY, NAME, "golf", 205, now=CLOCK, edition_instant=COMMENCE_2027
    ) is None


def test_an_in_play_provider_edition_keeps_its_link():
    assert derive_market_concept_key(
        KEY, NAME, "golf", 205, now=CLOCK, edition_instant=COMMENCE_2026
    ) == CONCEPT


def test_the_instant_guard_covers_the_other_edition_blind_domains():
    tennis = "2027 US Open Men's Singles Winner"
    bare_tennis = "US Open Men's Singles Winner"
    assert derive_market_concept_key("x", bare_tennis, "tennis", 128, now=CLOCK) is not None
    assert derive_market_concept_key(
        "x", bare_tennis, "tennis", 128, now=CLOCK, edition_instant=COMMENCE_2027
    ) is None
    # A named year is still refused on its own (unchanged #7792 arm).
    assert derive_market_concept_key("x", tennis, "tennis", 128, now=CLOCK) is None


# ── 3. the served payload ───────────────────────────────────────────────────


def _outcome(oid, name, prob, seen):
    return SimpleNamespace(
        id=oid, name=name, external_id=name,
        current_probability=prob, current_american_odds=None,
        rank=oid, rank_change_24h=None, probability_change_24h=None,
        opening_probability=prob, opening_american_odds=None,
        is_winner=False, resolution_source=None,
        last_updated=seen, team_id=None,
    )


def _market7(metadata):
    # `_format_market_detail` reads the real clock, so stamps are relative to it.
    seen = datetime.now(timezone.utc) - timedelta(minutes=30)
    return SimpleNamespace(
        id=7, name=NAME, description=None, category="championship",
        source="odds_api", external_id=KEY, status="open",
        sport=None, sport_id=None, event_id=None, market_type="field",
        market_tier=1, llm_sport_category="golf", mutually_exclusive=True,
        commence_time=None, resolution_date=None, created_at=None,
        updated_at=seen, group_id=None, canonical_market_key="golf::championship:",
        hook_description=None, hook_generated_at=None,
        hook_leader_at_generation=None, image_url=None, category_tags=["golf"],
        market_metadata=metadata,
        outcomes=[
            _outcome(546, "Scottie Scheffler", 0.13, seen),
            _outcome(547, "Rory McIlroy", 0.076, seen),
            _outcome(549, "Jon Rahm", 0.05, seen),
        ],
    )


def _serve(metadata):
    from app.routes.futures import _format_market_detail

    return _format_market_detail(_market7(metadata), None, set())


def test_the_served_rolled_board_carries_its_year_and_no_settled_link():
    now = datetime.now(timezone.utc)
    # Offset first (gotcha #44): 400 days ahead is never the current year.
    commence = now + timedelta(days=400)
    detail = _serve({"odds_api_current_event": _identity(commence, now - timedelta(hours=1))})
    assert detail["edition_year"] == str(commence.year)
    assert detail["edition_year"] != str(now.year)
    assert detail["event_concept_key"] is None
    # The hub is not edition-specific and stays.
    assert detail["hub_slug"] is not None


def test_the_served_in_play_board_keeps_its_link():
    """Control on the same serializer: an in-play provider edition still links."""
    now = datetime.now(timezone.utc)
    detail = _serve({"odds_api_current_event": _identity(now, now - timedelta(hours=1))})
    assert detail["edition_year"] == str(now.year)
    assert detail["event_concept_key"] == CONCEPT


def test_a_stale_anchor_serves_no_year_and_makes_no_claim():
    now = datetime.now(timezone.utc)
    detail = _serve(
        {"odds_api_current_event": _identity(now + timedelta(days=400), now - timedelta(hours=13))}
    )
    assert detail["edition_year"] is None
    assert detail["event_concept_key"] == CONCEPT
