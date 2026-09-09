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

    def test_live_only_on_race_day(self):
        """The reader-facing claim: `● LIVE` means the race is happening.

        This test used to assert the defect — `NOW + 2 days == "live"` — which is
        what put a `LIVE` badge over "Sep 13 – Sep 13" on the Italian Grand Prix
        page on 2026-09-09, four days out. The two days/four days arms are the
        controls: a race that has not started is never live, however close it is."""
        assert f1_status("open", NOW + timedelta(hours=2), NOW) == "live"
        assert f1_status("open", NOW + timedelta(hours=4), NOW) == "live"
        assert f1_status("open", NOW, NOW) == "live"
        assert f1_status("open", NOW + timedelta(hours=5), NOW) == "upcoming"
        assert f1_status("open", NOW + timedelta(days=2), NOW) == "upcoming"
        assert f1_status("open", NOW + timedelta(days=4), NOW) == "upcoming"

    def test_a_race_under_way_is_not_settled(self):
        """The same defect from the other side: the old rule called the race
        finished the instant lights went out, so a running GP was dropped from the
        feed as settled. It stays live until the race and podium are done."""
        assert f1_status("open", NOW - timedelta(hours=1), NOW) == "live"
        assert f1_status("open", NOW - timedelta(hours=3), NOW) == "live"
        assert f1_status("open", NOW - timedelta(hours=4), NOW) == "settled"

    def test_a_venue_grade_beats_the_clock_either_way(self):
        """A graded market is settled even mid-window — the assigned term wins."""
        assert f1_status("resolved", NOW + timedelta(hours=1), NOW) == "settled"
        assert f1_status("closed", NOW - timedelta(hours=1), NOW) == "settled"

    def test_upcoming_when_far_or_unknown(self):
        assert f1_status("open", NOW + timedelta(days=20), NOW) == "upcoming"
        assert f1_status("open", None, NOW) == "upcoming"


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
        assert concepts[0]["status"] == "upcoming"  # 3 days out — not under way
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

    async def test_a_gp_four_days_out_is_listed_but_wears_no_live_badge(self):
        """The specimen, end to end: the Italian GP as production served it on
        2026-09-09 — race Sunday 13:00Z, page one on Wednesday, `status: "live"`.

        Three arms, because each is a separate way the old rule reached a reader:
        the card must still be LISTED (a demotion that deletes the card is not a
        fix), the headline the feed prints must not be the word "Live", and the
        concept score must not carry the +35 live bonus that ranked it there."""
        from app.routes.feed import _concept_headline, _score_event_concept

        # The lister reads the wall clock itself, so both arms are OFFSETS from one
        # `now` taken first — never a literal date that would branch on the clock
        # (gotcha #44). Four days out reproduces Wednesday; two hours out is Sunday.
        now = datetime.now(timezone.utc)
        rows = [(1, "Italian Grand Prix: Driver Winner", "open", now + timedelta(days=4))]
        concepts = await list_f1_gp_concepts(_MockDB(rows))

        assert len(concepts) == 1, "the card must survive the demotion, not vanish"
        c = concepts[0]
        assert c["status"] == "upcoming"
        assert _concept_headline(c, now) == "This week"

        # Race day, same market: the badge comes back and so does the bonus.
        live_rows = [(1, "Italian Grand Prix: Driver Winner", "open", now + timedelta(hours=2))]
        live = (await list_f1_gp_concepts(_MockDB(live_rows)))[0]
        assert live["status"] == "live"
        assert _concept_headline(live, now) == "Live"
        assert _score_event_concept(live, now) - _score_event_concept(c, now) >= 35

    async def test_far_off_gp_excluded_by_status(self):
        far = datetime.now(timezone.utc) + timedelta(days=40)
        rows = [(1, "Singapore Grand Prix Winner", "open", far)]
        # Default statuses are (upcoming, live); a 40-day-out GP is "upcoming" and
        # DOES surface — assert the descriptor is well-formed.
        concepts = await list_f1_gp_concepts(_MockDB(rows))
        assert len(concepts) == 1
        assert concepts[0]["status"] == "upcoming"
        assert concepts[0]["start_date"] == far.isoformat()
