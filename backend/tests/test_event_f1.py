"""#999 L2-72: F1 adapter pure helpers (winner-field motorsports).
L2-86 (B5): the GP concept lister that surfaces Grands Prix on the /sports feed."""

from datetime import datetime, timezone, timedelta

import pytest

from app.utils.event_f1 import (
    is_gp_winner_market,
    gp_tokens,
    shares_gp,
    f1_status,
    list_f1_gp_concepts,
)

NOW = datetime(2026, 7, 9, tzinfo=timezone.utc)


class TestGpWinnerClassifier:
    def test_main_race_winner_is_primary(self):
        assert is_gp_winner_market("British Grand Prix Winner") is True
        assert is_gp_winner_market("British Grand Prix: Driver Winner") is True

    def test_submarkets_are_not_the_primary(self):
        for n in [
            "British Grand Prix: Sprint Race Winner",
            "British Grand Prix Qualifying Session (Q3): Pole Position",
            "Austrian Grand Prix Main Race: Podium Finishers",
            "Austrian Grand Prix Main Race: Top Constructor",
            "British Grand Prix Sprint Race: Top 5 Finishers",
        ]:
            assert is_gp_winner_market(n) is False, n


class TestGpTokens:
    def test_distinctive_gp_name(self):
        assert gp_tokens("British Grand Prix Winner") == {"british"}
        assert gp_tokens("Austrian Grand Prix Main Race: Fastest Lap") == {"austrian"}

    def test_shares_gp(self):
        toks = gp_tokens("British Grand Prix Winner")
        assert shares_gp("British Grand Prix: Sprint Race Winner", toks) is True
        assert shares_gp("Austrian Grand Prix Winner", toks) is False
        assert shares_gp("anything", set()) is False


class TestF1Status:
    def test_settled_past_or_resolved(self):
        assert f1_status("resolved", NOW + timedelta(days=2), NOW) == "settled"
        assert f1_status("open", NOW - timedelta(days=1), NOW) == "settled"

    def test_a_race_that_has_not_started_is_not_live(self):
        """🔴 UX-1035 / #2711. This assertion USED TO BE ``== "live"``, under the
        name ``test_live_on_race_weekend``, and it was pinning the bug.

        ``resolution_date`` IS the race time here (and is published as the
        concept's ``start_date``), and the branch above returns ``settled`` the
        moment it passes. So "within 4 days of resolution" was four days BEFORE
        lights out — the concept was live only while the race had not started,
        and settled from the moment it had. On production 2026-09-02 that put
        ``status: "live"`` next to ``start_date: "2026-09-06T15:00:00Z"`` on the
        Dutch Grand Prix card.
        """
        assert f1_status("open", NOW + timedelta(days=2), NOW) == "upcoming"

    def test_no_proximity_to_the_race_makes_a_card_live(self):
        """The whole former window, swept. If any of these comes back "live",
        the threshold has been reintroduced under a new number."""
        for days in (0.1, 1, 2, 3, 3.9, 4, 4.1, 7, 20):
            assert f1_status("open", NOW + timedelta(days=days), NOW) == "upcoming", (
                f"a race {days} days away is not live"
            )

    def test_live_is_not_a_state_this_adapter_can_produce_at_all(self):
        """Structural, not sampled. The adapter holds ONE timestamp and spends
        it on the settle boundary, so there is no argument by which it could
        honestly report a race in progress. Pinning the absence stops the next
        reader from restoring the old branch as an oversight."""
        for status in ("open", "active", None, "", "unknown"):
            for res in (None, NOW - timedelta(days=1), NOW + timedelta(days=2)):
                assert f1_status(status, res, NOW) in ("upcoming", "settled")

    def test_upcoming_when_far_or_unknown(self):
        assert f1_status("open", NOW + timedelta(days=20), NOW) == "upcoming"
        assert f1_status("open", None, NOW) == "upcoming"

    def test_replaying_the_two_cards_the_shopper_saw(self):
        """🔴 THE PRODUCTION PAYLOAD, THROUGH THE NEW FUNCTION.

        Verbatim from `GET /api/feed?mode=sports&limit=200` at 2026-09-02
        ~22:5xZ (the concept cards are banked whole at
        `frontend/__tests__/fixtures/conceptCards2711.json`). Both F1 cards
        carried `status: "live"` beside these very timestamps as their own
        `start_date`, which is the same field this function reads as
        `resolution_date`.

        The two `upcoming` F1 cards in the same payload are the CONTROL: they
        must not move, or this fix is a blanket demotion rather than the removal
        of a false claim.
        """
        shopped = datetime(2026, 9, 2, 22, 50, tzinfo=timezone.utc)
        was_live = {
            "Dutch Grand Prix Winner": datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc),
            "Freedom 250 Grand Prix of Washington Winner": datetime(
                2026, 9, 6, 21, 30, tzinfo=timezone.utc
            ),
        }
        was_upcoming = {
            "Italian Grand Prix Winner": datetime(
                2026, 9, 13, 13, 0, tzinfo=timezone.utc
            ),
            "Spanish Grand Prix: Driver Winner": datetime(
                2026, 9, 20, 13, 0, tzinfo=timezone.utc
            ),
        }
        for name, race_time in was_live.items():
            assert f1_status("open", race_time, shopped) == "upcoming", name
            assert race_time > shopped, f"{name}: the race had not started"
        for name, race_time in was_upcoming.items():
            assert f1_status("open", race_time, shopped) == "upcoming", name

    def test_the_race_itself_still_settles(self):
        """The control for the edit: only the "live" arm was removed. A race
        whose time has passed must still settle, or this fix would leave every
        finished GP claiming to be upcoming forever."""
        assert f1_status("open", NOW - timedelta(seconds=1), NOW) == "settled"
        assert f1_status("resolved", NOW + timedelta(days=2), NOW) == "settled"


class TestTheCardCannotSayLiveThroughTheOtherDoor:
    """🔴 UX-1035 / #2711 — THE SECOND "LIVE", AND WHY THE BADGE FIX NEEDS IT.

    The card prints "LIVE" from TWO independent fields, and removing the
    ``f1_status`` claim only removes one of them.

    ``FeedCard.tsx`` renders the red LIVE badge from ``data.status``, and one
    line below renders ``item.headline`` in an amber chip — gated, and this is
    the trap, on ``item.headline && !isLive``. The headline is SUPPRESSED WHILE
    THE CARD IS LIVE. So on the shopped payload the Dutch Grand Prix carried
    ``status: "live"`` AND ``headline: "Live"`` (both banked in
    `frontend/__tests__/fixtures/conceptCards2711.json`), and the badge hid the
    chip. Take the badge away and the chip is what becomes visible.

    Had ``_concept_headline`` inferred "Live" on its own — from price, from
    proximity, from anything but ``status`` — this fix would have swapped a red
    LIVE for an amber Live and called it a repair. It does not: ``feed.py``'s
    ``_concept_headline`` opens with ``if c.get("status") == "live"``, the same
    field ``f1_status`` produces, so the two move together.

    That coupling is the thing worth pinning. Both halves were already tested
    ALONE — ``TestF1Status`` here, ``TestConceptHeadline`` in
    `test_feed_event_concepts.py` (which asserts ``status="live"`` -> "Live",
    correctly, since a cycling grand tour really can be live). Neither can see
    the join, and the join is where the bug would come back: give the headline
    its own live inference and every test above stays green while the card says
    Live again.
    """

    def test_a_grand_prix_produces_neither_a_live_badge_nor_a_live_headline(self):
        """The two shopped GPs, end to end: ``f1_status`` -> ``_concept_headline``.

        Composed, not reimplemented — the status this asserts on is the one the
        adapter actually returns, so re-tuning ``f1_status`` moves this test too.
        """
        from app.routes.feed import _concept_headline

        shopped = datetime(2026, 9, 2, 22, 50, tzinfo=timezone.utc)
        races = {
            "Dutch Grand Prix Winner": datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc),
            "Freedom 250 Grand Prix of Washington Winner": datetime(
                2026, 9, 6, 21, 30, tzinfo=timezone.utc
            ),
        }
        for name, race_time in races.items():
            status = f1_status("open", race_time, shopped)
            assert status != "live", name
            headline = _concept_headline(
                {"status": status, "latest_commence": race_time}, shopped
            )
            assert headline != "Live", (
                f"{name}: the badge is gone but the headline still says Live — "
                "the amber chip is unsuppressed exactly when the badge goes away"
            )
            # Positive half: it does not merely fall silent, it counts down.
            assert headline == "This week", name

    def test_the_headline_still_says_live_for_a_concept_that_really_is_live(self):
        """The control, and the reason this is a join test rather than a change
        to ``_concept_headline``. Nothing here narrows the headline itself — a
        cycling grand tour, which IS under way, must keep its Live. The F1 card
        stops saying Live because its STATUS changed, not because the headline
        learned a new rule."""
        from app.routes.feed import _concept_headline

        assert _concept_headline({"status": "live"}, NOW) == "Live"


class _MockResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _MockDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_a, **_k):
        return _MockResult(self._rows)


@pytest.mark.asyncio
class TestListF1GpConcepts:
    async def test_groups_gp_and_counts_weekend_markets(self):
        # One British GP: winner market anchors; sub-markets fold into entry_count.
        soon = datetime.now(timezone.utc) + timedelta(days=3)
        rows = [
            (1, "British Grand Prix: Driver Winner", "open", soon),
            (2, "British Grand Prix: Driver Pole Position", "open", soon),
            (3, "British Grand Prix: Constructor Fastest Lap", "open", soon),
            # A different GP, further out.
            (4, "Hungarian Grand Prix Winner", "open", soon + timedelta(days=14)),
        ]
        concepts = await list_f1_gp_concepts(_MockDB(rows))
        # British (soonest) first.
        assert concepts[0]["key"] == "event:f1:british-grand-prix-driver-winner"
        assert concepts[0]["domain"] == "f1"
        # #2711: 3 days out is UPCOMING. It read "live" here for the same reason
        # the Dutch GP card did — see `f1_status`. The lister still SURFACES it
        # (the default `statuses` admits upcoming), so this fix changes what the
        # card claims, not whether the concept exists.
        assert concepts[0]["status"] == "upcoming"
        assert concepts[0]["start_date"] == soon.isoformat()
        assert concepts[0]["entry_count"] == 3  # winner + pole + fastest-lap
        assert concepts[0]["is_major"] is False
        # Both GPs surfaced.
        assert {c["name"] for c in concepts} == {
            "British Grand Prix: Driver Winner",
            "Hungarian Grand Prix Winner",
        }

    async def test_season_championship_is_not_a_gp_concept(self):
        # "F1 Drivers Champion" has no winner/to-win token → not a GP concept.
        rows = [(1, "F1 Drivers Champion", "open", None)]
        assert await list_f1_gp_concepts(_MockDB(rows)) == []

    async def test_non_grand_prix_winner_market_excluded(self):
        # A non-race "winner" market miscategorized as motorsports (the real World
        # Cup KXWCGROUPPTS case) must NOT leak a nonsense GP concept — the lister is
        # Grand-Prix-scoped.
        soon = datetime.now(timezone.utc) + timedelta(days=3)
        rows = [
            (1, "Any Group Winner to Finish with Fewer than 6 Points", "open", soon),
            (2, "British Grand Prix Winner", "open", soon),
        ]
        concepts = await list_f1_gp_concepts(_MockDB(rows))
        assert [c["name"] for c in concepts] == ["British Grand Prix Winner"]

    async def test_far_off_gp_excluded_by_status(self):
        far = datetime.now(timezone.utc) + timedelta(days=40)
        rows = [(1, "Singapore Grand Prix Winner", "open", far)]
        # Default statuses are (upcoming, live); a 40-day-out GP is "upcoming" and
        # DOES surface — assert the descriptor is well-formed.
        concepts = await list_f1_gp_concepts(_MockDB(rows))
        assert len(concepts) == 1
        assert concepts[0]["status"] == "upcoming"
        assert concepts[0]["start_date"] == far.isoformat()
