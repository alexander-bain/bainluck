"""#999 L2-72: F1 adapter pure helpers (winner-field motorsports).
L2-86 (B5): the GP concept lister that surfaces Grands Prix on the /sports feed."""

from datetime import datetime, timezone, timedelta

import pytest

from app.utils.event_f1 import (
    _MOTORSPORT_TICKER_LABELS,
    is_gp_winner_market,
    gp_tokens,
    gp_sport_label,
    shares_gp,
    f1_status,
    list_f1_gp_concepts,
    ticker_sport_label,
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
            (1, "KXF1RACE-GBRGP26", "British Grand Prix: Driver Winner", "open", soon),
            (2, "KXF1RACE-GBRGP26", "British Grand Prix: Driver Pole Position", "open", soon),
            (3, "KXF1RACE-GBRGP26", "British Grand Prix: Constructor Fastest Lap", "open", soon),
            # A different GP, further out.
            (4, "KXF1RACE-HUNGP26", "Hungarian Grand Prix Winner", "open", soon + timedelta(days=14)),
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
        rows = [(1, "KXF1WDC-26", "F1 Drivers Champion", "open", None)]
        assert await list_f1_gp_concepts(_MockDB(rows)) == []

    async def test_non_grand_prix_winner_market_excluded(self):
        # A non-race "winner" market miscategorized as motorsports (the real World
        # Cup KXWCGROUPPTS case) must NOT leak a nonsense GP concept — the lister is
        # Grand-Prix-scoped.
        soon = datetime.now(timezone.utc) + timedelta(days=3)
        rows = [
            (1, "KXWCGROUPPTS-26", "Any Group Winner to Finish with Fewer than 6 Points", "open", soon),
            (2, "KXF1RACE-GBRGP26", "British Grand Prix Winner", "open", soon),
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
        rows = [(1, "KXF1RACE-ITAGP26", "Italian Grand Prix: Driver Winner", "open", now + timedelta(days=4))]
        concepts = await list_f1_gp_concepts(_MockDB(rows))

        assert len(concepts) == 1, "the card must survive the demotion, not vanish"
        c = concepts[0]
        assert c["status"] == "upcoming"
        assert _concept_headline(c, now) == "This week"

        # Race day, same market: the badge comes back and so does the bonus.
        live_rows = [(1, "KXF1RACE-ITAGP26", "Italian Grand Prix: Driver Winner", "open", now + timedelta(hours=2))]
        live = (await list_f1_gp_concepts(_MockDB(live_rows)))[0]
        assert live["status"] == "live"
        assert _concept_headline(live, now) == "Live"
        assert _score_event_concept(live, now) - _score_event_concept(c, now) >= 35

    async def test_far_off_gp_excluded_by_status(self):
        far = datetime.now(timezone.utc) + timedelta(days=40)
        rows = [(1, "KXF1RACE-SGPGP26", "Singapore Grand Prix Winner", "open", far)]
        # Default statuses are (upcoming, live); a 40-day-out GP is "upcoming" and
        # DOES surface — assert the descriptor is well-formed.
        concepts = await list_f1_gp_concepts(_MockDB(rows))
        assert len(concepts) == 1
        assert concepts[0]["status"] == "upcoming"
        assert concepts[0]["start_date"] == far.isoformat()


class TestTickerSportLabel:
    """#7541 — the pure helper, per ticker family."""

    def test_the_two_production_specimens_are_told_apart(self):
        # Read off `futures_markets` 2026-09-20: the two rows that sat one card
        # apart on the sports feed, both `llm_sport_category = 'motorsports'`,
        # both matching the lister's "grand prix" filter.
        assert ticker_sport_label("KXF1RACE-AZEGP26") == "F1"
        assert ticker_sport_label("KXMOTOGPRACE-OSTE26") == "MotoGP"

    def test_case_and_whitespace_are_not_the_discriminator(self):
        assert ticker_sport_label("  kxmotogprace-oste26  ") == "MotoGP"

    def test_longest_prefix_wins(self):
        """`kxf1` and `kxmotogp` are both prefixes of longer families, so the
        map is length-ordered. A dict iterated in source order would let
        `kxf1` answer for a `KXF1RACE` row — harmless today, and exactly the
        kind of ordering bug that only shows up once a family is added."""
        assert ticker_sport_label("KXNASCARRACE-26") == "NASCAR"
        assert ticker_sport_label("KXNASCAR-CUP26") == "NASCAR"
        assert [p for p, _ in _MOTORSPORT_TICKER_LABELS] == sorted(
            [p for p, _ in _MOTORSPORT_TICKER_LABELS], key=len, reverse=True
        )

    def test_no_evidence_is_none_not_a_guess(self):
        # A Polymarket id, an unknown family, and nothing at all. `None` means
        # the chip keeps the domain fallback — never a blank chip.
        assert ticker_sport_label("0x8f3a91bd2c") is None
        assert ticker_sport_label("KXDRONERACE-26") is None
        assert ticker_sport_label("") is None
        assert ticker_sport_label(None) is None


class TestGpSportLabel:
    """#7541 — the group-level rule: unanimity, or silence."""

    def test_a_unanimous_group_is_labelled(self):
        assert gp_sport_label(["KXMOTOGPRACE-OSTE26", "KXMOTOGPRACE-OSTE26"]) == "MotoGP"

    def test_rows_with_no_ticker_do_not_veto_the_ones_that_have_one(self):
        """A GP grouped across venues: Kalshi carries the family, Polymarket
        does not. The Kalshi evidence still decides — otherwise adding a
        Polymarket row to a correctly-labelled GP would silently blank it."""
        assert gp_sport_label(["KXF1RACE-AZEGP26", "0x8f3a91bd2c", None]) == "F1"

    def test_a_group_that_straddles_two_championships_says_nothing(self):
        """Two championships under one GP token means our GROUPING is wrong,
        and the honest answer is silence, not a coin flip. `sorted` on the
        input must not decide which chip a reader sees."""
        mixed = ["KXF1RACE-AZEGP26", "KXMOTOGPRACE-OSTE26"]
        assert gp_sport_label(mixed) is None
        assert gp_sport_label(list(reversed(mixed))) is None

    def test_no_evidence_at_all_is_none(self):
        assert gp_sport_label([]) is None
        assert gp_sport_label(None) is None
        assert gp_sport_label(["0xabc", None]) is None


@pytest.mark.asyncio
class TestAMotoGpRaceDoesNotWearAnF1Chip:
    """#7541 — the defect, end to end through the lister.

    Production 2026-09-20 16:05Z, `/sports`, card 5 of Live Now:

        🏎 F1 — Motorrad Grand Prix von Osterreich Winner — Marc Marquez 60%

    "Motorrad Grand Prix von Osterreich" is the MotoGP Austrian Grand Prix.
    The lister admitted it because its only sport guard is the phrase "grand
    prix", which MotoGP, Formula E and IndyCar all use, and then served no
    `sport_label` — so `conceptDomainLabel` fell through to `domain.upper()`.
    """

    # The row as production held it, name included (un-umlauted, as Kalshi
    # writes it) — the fixture is the specimen, not a paraphrase of it.
    MOTOGP = (61497311, "KXMOTOGPRACE-OSTE26", "Motorrad Grand Prix von Osterreich Winner")
    F1 = (61495797, "KXF1RACE-AZEGP26", "Azerbaijan Grand Prix Winner")

    async def test_the_motogp_race_is_labelled_motogp(self):
        soon = datetime.now(timezone.utc) + timedelta(hours=2)
        mid, ext, name = self.MOTOGP
        concepts = await list_f1_gp_concepts(_MockDB([(mid, ext, name, "open", soon)]))

        assert len(concepts) == 1, "the card must be RELABELLED, never suppressed"
        assert concepts[0]["sport_label"] == "MotoGP"
        # The routing token is untouched: `domain` keys the adapter registry and
        # the event URL, and renaming it would break both.
        assert concepts[0]["domain"] == "f1"

    async def test_the_f1_race_still_says_f1_now_from_evidence(self):
        """The control. The Azerbaijan card read `F1` before this change too —
        from the routing token, which happened to be right. It must still read
        `F1`, or the fix has traded one wrong chip for a missing one."""
        soon = datetime.now(timezone.utc) + timedelta(hours=2)
        mid, ext, name = self.F1
        concepts = await list_f1_gp_concepts(_MockDB([(mid, ext, name, "open", soon)]))
        assert concepts[0]["sport_label"] == "F1"

    async def test_both_races_on_one_feed_get_their_own_chip(self):
        """Both rows were open, `motorsports`, and "grand prix" on the same day.
        They are separate GP token groups, so they must not pool evidence."""
        soon = datetime.now(timezone.utc) + timedelta(hours=2)
        rows = [
            (mid, ext, name, "open", soon) for mid, ext, name in (self.MOTOGP, self.F1)
        ]
        by_name = {c["name"]: c for c in await list_f1_gp_concepts(_MockDB(rows))}
        assert by_name["Motorrad Grand Prix von Osterreich Winner"]["sport_label"] == "MotoGP"
        assert by_name["Azerbaijan Grand Prix Winner"]["sport_label"] == "F1"

    async def test_an_unlabelled_gp_omits_the_key_rather_than_serving_null(self):
        """`sport_label: None` on the wire would satisfy a consumer's presence
        test and render a BLANK chip — worse than the wrong one. The key is
        absent, so `conceptDomainLabel` takes its domain fallback and an older
        client is untouched."""
        soon = datetime.now(timezone.utc) + timedelta(hours=2)
        rows = [(9, "0xpolymarketonly", "Monaco Grand Prix: Driver Winner", "open", soon)]
        concepts = await list_f1_gp_concepts(_MockDB(rows))
        assert len(concepts) == 1
        assert "sport_label" not in concepts[0]

    async def test_a_foreign_row_sharing_a_name_token_gets_no_vote_on_the_chip(self):
        """`entry_count` groups on ANY shared name token, deliberately loosely.
        The chip may not: evidence is only ever the winner anchors the card is
        built from. Here an Austrian F1 sub-market shares the token `osterreich`
        with nothing, but a same-token MotoGP sprint would otherwise be counted —
        so assert the chip survives a weekend market that carries a foreign
        ticker."""
        soon = datetime.now(timezone.utc) + timedelta(hours=2)
        mid, ext, name = self.MOTOGP
        rows = [
            (mid, ext, name, "open", soon),
            # Folds into entry_count (shared token), carries an F1 ticker, and is
            # not a winner market — it must not turn the chip off.
            (7, "KXF1RACE-AUTGP26", "Motorrad Grand Prix Main Race: Fastest Lap", "open", soon),
        ]
        concepts = await list_f1_gp_concepts(_MockDB(rows))
        assert len(concepts) == 1
        assert concepts[0]["entry_count"] == 2, "the size proxy still counts it"
        assert concepts[0]["sport_label"] == "MotoGP", "but it does not vote"
