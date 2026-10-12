"""#1541 — a rolled sportsbook board names its own edition and never links the settled one.

THE DEFECT, on production 2026-10-12 17:04Z. `/futures/7` (odds_api
`golf_us_open_winner`, open) read "US Open Winner · Scottie Scheffler 13%" with
current prices, and its "Part of: US Open" breadcrumb opened
`/event/golf/u-s-open` — GOLF SETTLED MAJOR, Jun 18–21, Wyndham Clark WON. The
row's retained provider identity (`market_metadata.odds_api_current_event`, polled
16:33Z) is event `3eebece4…`, commence **2027-06-17**: every quote is the 2027 US
Open. The bare name made no edition claim, so the #7792 guard kept the link into
the edition the concept page serves.

Root's source hold on the first cut (PR #10945 @ 32c84d6486) named two holes,
both closed here: a missing/stale/malformed anchor fell back to the bare-name
link (the settled page again), and "edition year == calendar year" does not
prove the destination serves that edition (in January 2027 a 2027 quote would
pass while `/event/golf/u-s-open` still serves the settled 2026 fallback).

The link is now kept only when the DESTINATION'S OWN served window — the
concept tier's cached envelope, `event.start_date`/`end_date` — holds the
provider's verified edition. Three arms:
  1. the anchor reader (`read_odds_api_anchor`) — the single reading of the
     identity, shared with `member_of`, refusing missing/malformed/stale anchors;
  2. the pure destination test (`concept_serves_edition`), incl. the Jan-2027
     shape with fixed dates;
  3. the served detail payload from `_format_market_detail` for the market-7
     shape, every fail-closed case and both controls, through the real envelope
     reader over a fake Redis.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.concept_links import concept_serves_edition
from app.utils.event_concept_cache import cache_keys, encode_payload, stamp_envelope
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


# ── 2. the destination test ─────────────────────────────────────────────────


def _envelope(start: datetime, end: datetime, status: str = "settled") -> dict:
    return {"event": {
        "key": CONCEPT, "name": "U.S. Open", "status": status,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
    }}


SETTLED_2026 = _envelope(
    datetime(2026, 6, 18, tzinfo=timezone.utc), datetime(2026, 6, 21, tzinfo=timezone.utc)
)
UPCOMING_2027 = _envelope(
    datetime(2027, 6, 17, tzinfo=timezone.utc), datetime(2027, 6, 20, tzinfo=timezone.utc),
    status="upcoming",
)


def test_a_settled_prior_edition_does_not_serve_the_next_one():
    """The production read: provider 2027-06-17 vs the page's 2026-06-18..21."""
    assert concept_serves_edition(SETTLED_2026, COMMENCE_2027) is False


def test_january_2027_a_same_year_quote_still_needs_the_destination():
    """Root's Jan-2027 case: a calendar check passes (2027 == 2027) while the
    destination still serves the settled 2026 fallback. The dates refuse it."""
    jan_2027_commence = datetime(2027, 6, 17, 10, tzinfo=timezone.utc)
    assert jan_2027_commence.year == datetime(2027, 1, 15, tzinfo=timezone.utc).year
    assert concept_serves_edition(SETTLED_2026, jan_2027_commence) is False


def test_the_destination_serving_that_edition_keeps_the_link():
    assert concept_serves_edition(UPCOMING_2027, COMMENCE_2027) is True
    assert concept_serves_edition(SETTLED_2026, COMMENCE_2026) is True


@pytest.mark.parametrize("envelope", [
    None, {}, {"event": None}, {"event": {"start_date": None}},
    {"event": {"start_date": "2027-06-17"}},              # naive: refused
    {"event": {"start_date": "not a date"}},
    {"event": {"start_date": "2027-06-20T00:00:00+00:00", "end_date": "2027-06-17T00:00:00+00:00"}},
])
def test_an_unreadable_destination_fails_closed(envelope):
    assert concept_serves_edition(envelope, COMMENCE_2027) is False


def test_no_provider_instant_fails_closed():
    assert concept_serves_edition(UPCOMING_2027, None) is False


# ── 3. the served payload ───────────────────────────────────────────────────


class _FakeRedis:
    def __init__(self, store):
        self.store = store

    def get(self, key):
        return self.store.get(key)


def _cached(envelope: dict, slot: str = "primary") -> dict:
    stamped = stamp_envelope(
        envelope, created_at=datetime.now(timezone.utc), lifecycle_watermark=None
    )
    return {getattr(cache_keys(CONCEPT), slot): encode_payload(stamped)}


@pytest.fixture
def concept_cache(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(
        "app.utils.event_concept_cache.get_client", lambda: _FakeRedis(store)
    )
    return store


def _outcome(oid, name, prob, seen):
    return SimpleNamespace(
        id=oid, name=name, external_id=name,
        current_probability=prob, current_american_odds=None,
        rank=oid, rank_change_24h=None, probability_change_24h=None,
        opening_probability=prob, opening_american_odds=None,
        is_winner=False, resolution_source=None,
        last_updated=seen, team_id=None,
    )


def _market7(metadata, source="odds_api"):
    # `_format_market_detail` reads the real clock, so stamps are relative to it.
    seen = datetime.now(timezone.utc) - timedelta(minutes=30)
    return SimpleNamespace(
        id=7, name=NAME, description=None, category="championship",
        source=source, external_id=KEY, status="open",
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


def _serve(metadata, source="odds_api"):
    from app.routes.futures import _format_market_detail

    return _format_market_detail(_market7(metadata, source), None, set())


def _fresh(commence):
    now = datetime.now(timezone.utc)
    return {"odds_api_current_event": _identity(commence, now - timedelta(hours=1))}


def _window_around(instant, *, days_before, days_after=3, status="settled"):
    return _envelope(instant - timedelta(days=days_before),
                     instant - timedelta(days=days_before) + timedelta(days=days_after),
                     status=status)


def test_the_served_rolled_board_carries_its_year_and_no_settled_link(concept_cache):
    """The market-7 shape: next year's provider event, the page serving last year's."""
    commence = datetime.now(timezone.utc) + timedelta(days=248)
    concept_cache.update(_cached(_window_around(commence, days_before=364)))
    detail = _serve(_fresh(commence))
    assert detail["edition_year"] == str(commence.year)
    assert detail["event_concept_key"] is None
    assert detail["hub_slug"] is not None  # the hub is not edition-specific


def test_a_same_year_quote_with_a_prior_edition_destination_has_no_link(concept_cache):
    """The Jan-2027 shape on the real serializer: the provider edition is in the
    current calendar year, the destination serves the prior edition."""
    commence = datetime.now(timezone.utc)
    concept_cache.update(_cached(_window_around(commence, days_before=365)))
    detail = _serve(_fresh(commence))
    assert detail["edition_year"] == str(commence.year)
    assert detail["event_concept_key"] is None


def test_the_destination_serving_the_provider_edition_keeps_the_link(concept_cache):
    """Control: tournament week, the page has rebuilt to the provider's edition."""
    commence = datetime.now(timezone.utc) + timedelta(days=2)
    concept_cache.update(_cached(_window_around(commence, days_before=0, status="upcoming")))
    detail = _serve(_fresh(commence))
    assert detail["event_concept_key"] == CONCEPT


def test_the_24h_mirror_is_read_when_the_primary_has_expired(concept_cache):
    commence = datetime.now(timezone.utc) + timedelta(days=2)
    concept_cache.update(_cached(_window_around(commence, days_before=0), slot="stale"))
    assert _serve(_fresh(commence))["event_concept_key"] == CONCEPT


def test_a_cold_concept_cache_withholds_the_link(concept_cache):
    commence = datetime.now(timezone.utc) + timedelta(days=2)
    detail = _serve(_fresh(commence))
    assert detail["edition_year"] == str(commence.year)
    assert detail["event_concept_key"] is None


@pytest.mark.parametrize("metadata", [
    {},                                                    # missing
    None,
    {"odds_api_current_event": "not a mapping"},          # malformed
])
def test_a_missing_or_malformed_anchor_serves_no_year_and_no_link(concept_cache, metadata):
    # Even a destination that WOULD match cannot be linked without the provider's own edition.
    commence = datetime.now(timezone.utc) + timedelta(days=2)
    concept_cache.update(_cached(_window_around(commence, days_before=0)))
    detail = _serve(metadata)
    assert detail["edition_year"] is None
    assert detail["event_concept_key"] is None


def test_a_stale_anchor_serves_no_year_and_no_link(concept_cache):
    now = datetime.now(timezone.utc)
    commence = now + timedelta(days=2)
    concept_cache.update(_cached(_window_around(commence, days_before=0)))
    detail = _serve({"odds_api_current_event": _identity(commence, now - timedelta(hours=13))})
    assert detail["edition_year"] is None
    assert detail["event_concept_key"] is None


def test_a_non_sportsbook_source_is_not_gated(concept_cache):
    """Scope control: the gate is for the ROLLING odds_api key only."""
    detail = _serve({}, source="kalshi")
    assert detail["edition_year"] is None
    assert detail["event_concept_key"] == CONCEPT
