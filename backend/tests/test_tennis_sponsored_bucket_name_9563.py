"""#9563 — a tournament bucket names ESPN's SPONSORED title, so the late
tournament row reaches the #9465 contest.

Specimen, production 2026-09-29 06:55Z: Alcaraz v Michelsen (ATP Japan Open,
ESPN competition 183497). The tour-week pass had put ESPN's id on Kalshi's
``15320475`` (``tennis_atp``) the day before; at 06:05Z the Odds API opened
``tennis_atp_japan_open`` and minted ``15321406``. Search printed 15321406
(3 sportsbooks, no Kalshi, no Polymarket). The #9465 contest would have
labelled it the holder's duplicate — the China Open specimen 15320661 serves
``kalshi + polymarket + betting`` through exactly that fold — but the pass's
``sport_keys`` read ``["tennis_atp_china_open", "tennis_wta_china_open"]``:
ESPN calls the event "Kinoshita Group Japan Open Tennis Championships", which
never folds EQUAL to ``japanopen``, so the bucket's rows were never read.
"""

from __future__ import annotations

from app.utils.espn_tennis_anchor import (
    anchorable_sport_keys,
    bucketless_competitions,
    named_board_tournaments,
)
from tests.test_espn_tennis_anchor import _Event, _at, _competition, _payload
from tests.test_tennis_tour_week_anchor_2774 import _install_generic, _TagRecorder

JAPAN_OPEN = "Kinoshita Group Japan Open Tennis Championships"

#: The six tournament names ESPN's board carried at 2026-09-29 06:5xZ, verbatim.
BOARD_NAMES = [
    "China Open",
    JAPAN_OPEN,
    "Jingshan Tennis Open",
    "Adana Open",
    "Chengdu Open",
    "AITO Hangzhou Open",
]

#: Production's tennis sport keys at the same read (`SELECT key FROM sports`).
PRODUCTION_KEYS = [
    "tennis_atp", "tennis_atp_aus_open_singles", "tennis_atp_barcelona_open",
    "tennis_atp_canadian_open", "tennis_atp_china_open", "tennis_atp_cincinnati_open",
    "tennis_atp_dubai", "tennis_atp_french_open", "tennis_atp_halle_open",
    "tennis_atp_hamburg_open", "tennis_atp_indian_wells", "tennis_atp_italian_open",
    "tennis_atp_japan_open", "tennis_atp_madrid_open", "tennis_atp_miami_open",
    "tennis_atp_monte_carlo_masters", "tennis_atp_munich", "tennis_atp_qatar_open",
    "tennis_atp_queens_club_champ", "tennis_atp_us_open", "tennis_atp_washington_open",
    "tennis_atp_wimbledon", "tennis_other", "tennis_wta", "tennis_wta_aus_open_singles",
    "tennis_wta_bad_homburg_open", "tennis_wta_canadian_open", "tennis_wta_charleston_open",
    "tennis_wta_china_open", "tennis_wta_cincinnati_open", "tennis_wta_dubai",
    "tennis_wta_french_open", "tennis_wta_german_open", "tennis_wta_guadalajara_open",
    "tennis_wta_indian_wells", "tennis_wta_italian_open", "tennis_wta_madrid_open",
    "tennis_wta_miami_open", "tennis_wta_monterrey_open", "tennis_wta_qatar_open",
    "tennis_wta_queens_club_champ", "tennis_wta_singapore_open", "tennis_wta_strasbourg",
    "tennis_wta_stuttgart_open", "tennis_wta_us_open", "tennis_wta_washington_open",
    "tennis_wta_wimbledon",
]


def _comps(names):
    return [
        {"espn_competition_id": str(i), "event_name": name}
        for i, name in enumerate(names)
    ]


# ═══════════════════════════ the pure scope ═══════════════════════════


class TestTheSponsoredTitle:
    def test_the_production_board_names_the_japan_open_bucket(self):
        assert anchorable_sport_keys(PRODUCTION_KEYS, _comps(BOARD_NAMES)) == [
            "tennis_atp_china_open", "tennis_atp_japan_open", "tennis_wta_china_open",
        ]

    def test_its_competitions_leave_the_generic_pass(self):
        """A tournament is anchored through its bucket OR the generic buckets,
        never both — the complement has to move with the naming."""
        left = bucketless_competitions(PRODUCTION_KEYS, _comps(BOARD_NAMES))
        assert sorted(c["event_name"] for c in left) == [
            "AITO Hangzhou Open", "Adana Open", "Chengdu Open", "Jingshan Tennis Open",
        ]

    def test_an_exact_title_still_names_its_bucket(self):
        assert named_board_tournaments(
            ["tennis_atp_us_open", "tennis_wta_us_open"], _comps(["US Open"])
        ) == {"usopen": "usopen"}


class TestContainmentOnlyAnswersUniquely:
    def test_a_token_inside_two_board_titles_names_neither(self):
        assert named_board_tournaments(
            ["tennis_atp_japan_open"],
            _comps([JAPAN_OPEN, "Rakuten Japan Open Indoor"]),
        ) == {}

    def test_two_tokens_inside_one_title_name_it_for_neither(self):
        assert named_board_tournaments(
            ["tennis_atp_japan_open", "tennis_atp_group_japan"],
            _comps([JAPAN_OPEN]),
        ) == {}

    def test_an_exact_host_is_never_taken_by_a_containing_token(self):
        # `chinaopen` is ESPN's exact title; `inaopen` sits inside it too.
        assert named_board_tournaments(
            ["tennis_atp_china_open", "tennis_atp_ina_open"], _comps(["China Open"])
        ) == {"chinaopen": "chinaopen"}

    def test_the_generic_buckets_still_name_nothing(self):
        assert named_board_tournaments(
            ["tennis_atp", "tennis_wta", "tennis_other"], _comps(BOARD_NAMES)
        ) == {}


# ═══════════════════════════ the task, end to end ═══════════════════════════

KEYS = ["tennis_atp", "tennis_atp_japan_open", "tennis_other", "tennis_wta"]


def _rows():
    holder = _Event(15320475, "Alcaraz", "Michelsen", "scheduled",
                    _at("2026-09-30T01:00Z"), espn_id="183497",
                    commence_time_source="polymarket_venue")
    late = _Event(15321406, "Carlos Alcaraz", "Alex Michelsen", "scheduled",
                  _at("2026-09-30T02:00Z"), commence_time_source="odds_api")
    return holder, late


def _board():
    return [_payload(
        [_competition("183497", ["Alex Michelsen", "Carlos Alcaraz"],
                      date="2026-09-30T01:00Z")],
        event_name=JAPAN_OPEN,
    )]


class TestTheEspnAnchoredBareRowAndTheLaterTournamentRow:
    async def test_the_specimen_shows_once(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        holder, late = _rows()
        tags = _TagRecorder().install(monkeypatch)
        _install_generic(
            monkeypatch, payloads=_board(), sport_keys=KEYS,
            generic=[(holder, "tennis_atp")], tournament_events=[late],
        )

        stats = await _sync_tennis_from_espn()

        assert stats["sport_keys"] == ["tennis_atp_japan_open"], (
            "ESPN's sponsored title must name the bucket, or the late row is never read"
        )
        assert stats["generic_competitions"] == 0, "Japan Open has a bucket now"
        assert stats["generic_held_competitions"] == 1
        assert stats["generic_contests_resolved"] == 1
        assert tags.written == [(15321406, 15320475)]
        assert tags.backed_up == [(15321406, 15320475)], "backup before the write (D51)"
        assert late.espn_id is None, "the id stays on ONE row — merge-duplicate-events"
        assert holder.espn_id == "183497"
        assert stats["already_anchored"] == 1, "the holder keeps its ESPN channel"
        assert stats.get("stamp_refused", 0) == 0

    async def test_control_with_no_holder_the_tournament_row_anchors_alone(
        self, monkeypatch
    ):
        """An ordinary sponsored-title week: nobody holds 183497, so the Odds
        API row takes the id through its bucket and nothing is labelled."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        _, late = _rows()
        tags = _TagRecorder().install(monkeypatch)
        _install_generic(
            monkeypatch, payloads=_board(), sport_keys=KEYS,
            generic=[], tournament_events=[late],
        )

        stats = await _sync_tennis_from_espn()

        assert late.espn_id == "183497"
        assert stats["anchored"] == 1
        assert tags.written == []
