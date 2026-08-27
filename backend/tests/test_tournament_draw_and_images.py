"""Guard tests for UX-P142 — the released draw, and a face that is the right face.

Alex reviewed the live page on his phone, 2026-08-27, and filed four findings.
Two of them are backend facts and both are guarded here:

  (a) "The draw exists (ceremony was today) but the page shows none."
  (c) "Players have no images."

Every test is anchored to something that was MEASURED on ceremony day rather
than to a hypothetical:

* ESPN's men's first-round list opens on an unseeded qualifier slot and puts
  Alcaraz 37th, so its order is ingest order and NOT the draw sheet — which is
  why nothing here writes ``draw_slot``;
* 30 of 256 main-draw slots were still ``TBD``/``Bye`` at the ceremony, because
  qualifying does not finish until 08-28;
* not one of the 96 registered main-draw fixtures had a match market at either
  source, which is why ``build_slate`` had to stop dropping unpriced fixtures
  before any of them could reach the page;
* a bare-name Wikipedia lookup returns a SERBIAN FOOTBALLER for the tennis
  player Aleksandar Kovacevic, and the 17th President of the United States for
  Andrew Johnson — both with a photograph, both HTTP 200.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.espn_tennis import (
    espn_round_key,
    parse_draw,
    round_names_for_size,
)
from app.utils.tournament_register import (
    ALLOWED_IMAGE_PREFIXES,
    TournamentRegister,
    load_register,
    player_image,
    us_open_2026_contract,
    validate_player,
    validate_player_image,
    validate_register,
)
from app.utils.tournament_slate import build_slate

REGISTER_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "tournament_registers"
    / "us-open-2026.json"
)


@pytest.fixture(scope="module")
def register() -> dict:
    return json.loads(REGISTER_PATH.read_text())


def _competitor(name: str, athlete_id: int, *, country: str | None = "USA") -> dict:
    return {
        "id": str(athlete_id),
        "order": 1,
        "athlete": {
            "displayName": name,
            "flag": (
                {
                    "href": f"https://a.espncdn.com/i/teamlogos/countries/500/{country}.png",
                    "alt": country,
                }
                if country
                else None
            ),
        },
    }


def _pad_to_draw_size(competitions: list[dict], size: int = 128) -> list[dict]:
    """Fill the first round out to ``size`` slots.

    ``parse_draw`` reads a draw's size off the COUNT of its own first-round
    competitions — "Round 1" is ``R128`` only because there are 64 of it — so a
    two-competitor fixture list is, correctly, a two-slot draw whose Round 1 is
    the Final.  Tests that mean to exercise a 128 draw have to look like one.
    """
    filler = [
        {
            "id": f"pad-{index}",
            "round": {"displayName": "Round 1"},
            "date": "2026-08-30T04:00Z",
            "competitors": [
                _competitor(f"Pad {index} A", 900000 + index * 2),
                _competitor(f"Pad {index} B", 900001 + index * 2),
            ],
        }
        for index in range(
            size // 2
            - sum(
                1
                for c in competitions
                if str((c.get("round") or {}).get("displayName")).lower() == "round 1"
            )
        )
    ]
    return [*competitions, *filler]


def _scoreboard(competitions: list[dict], *, slug: str = "mens-singles") -> dict:
    return {
        "events": [
            {
                "name": "US Open",
                "groupings": [
                    {"grouping": {"slug": slug}, "competitions": competitions}
                ],
            }
        ]
    }


# ---------------------------------------------------------------------------
# ROUND NAMING — "Round 1" is R128 only because there are 64 of it
# ---------------------------------------------------------------------------


class TestRoundNaming:
    def test_a_128_draw_names_its_rounds_largest_first(self):
        assert round_names_for_size(128) == [
            "R128",
            "R64",
            "R32",
            "R16",
            "QF",
            "SF",
            "F",
        ]

    def test_a_64_draw_starts_at_R64_not_R128(self):
        # A doubles draw's "Round 1" is R64. Reading it as R128 would file
        # every doubles fixture one round too early for the rest of its life.
        assert round_names_for_size(64)[0] == "R64"
        assert espn_round_key("Round 1", draw_size=64) == "R64"
        assert espn_round_key("Round 1", draw_size=128) == "R128"

    def test_the_small_rounds_have_no_R_name(self):
        assert round_names_for_size(8) == ["QF", "SF", "F"]
        assert round_names_for_size(2) == ["F"]

    def test_a_non_power_of_two_is_refused_rather_than_guessed(self):
        assert round_names_for_size(100) == []
        assert round_names_for_size(0) == []
        assert espn_round_key("Round 1", draw_size=100) is None

    def test_all_three_qualifying_rounds_collapse_to_one_bucket(self):
        for name in (
            "Qualifying 1st Round",
            "Qualifying 2nd Round",
            "Qualifying Final",
        ):
            assert espn_round_key(name, draw_size=128) == "qualifying"

    def test_the_named_rounds_map_by_name_not_by_index(self):
        assert espn_round_key("Quarterfinal", draw_size=128) == "QF"
        assert espn_round_key("Semifinal", draw_size=128) == "SF"
        assert espn_round_key("Final", draw_size=128) == "F"

    def test_an_unknown_round_is_None_and_the_fixture_is_dropped(self):
        assert espn_round_key("Consolation Plate", draw_size=128) is None
        assert espn_round_key(None, draw_size=128) is None


# ---------------------------------------------------------------------------
# THE DRAW PARSE
# ---------------------------------------------------------------------------


class TestParseDraw:
    def test_a_first_round_competition_becomes_a_fixture(self):
        payload = _scoreboard(
            _pad_to_draw_size(
                [
                    {
                        "id": "1",
                        "round": {"displayName": "Round 1"},
                        "date": "2026-08-30T04:00Z",
                        "competitors": [
                            _competitor("Carlos Alcaraz", 111, country="esp"),
                            _competitor("Roman Safiullin", 222, country="rus"),
                        ],
                    }
                ]
            )
        )
        parsed = parse_draw([payload], event_name="US Open")
        fixtures = parsed["draws"]["mens-singles"]
        assert len(fixtures) == 64
        assert fixtures[0]["round"] == "R128"
        assert [p["name"] for p in fixtures[0]["players"]] == [
            "Carlos Alcaraz",
            "Roman Safiullin",
        ]
        assert all(p["determined"] for p in fixtures[0]["players"])
        assert fixtures[0]["players"][0]["country"] == "esp"

    def test_a_TBD_side_is_carried_as_undetermined_not_dropped(self):
        # A main draw released before qualifying finishes carries REAL
        # placeholder slots — 30 of 256 at this ceremony. The fixture still
        # says "somebody plays Jack Kennedy", which is true.
        payload = _scoreboard(
            [
                {
                    "id": "1",
                    "round": {"displayName": "Round 1"},
                    "date": "2026-08-30T04:00Z",
                    "competitors": [
                        {"id": "-3", "order": 1, "athlete": {"displayName": "TBD"}},
                        _competitor("Jack Kennedy", 333),
                    ],
                }
            ]
        )
        parsed = parse_draw([payload], event_name="US Open")
        fixture = parsed["draws"]["mens-singles"][0]
        assert [p["determined"] for p in fixture["players"]] == [False, True]
        assert fixture["players"][0]["espn_athlete_id"] is None
        assert parsed["stats"]["placeholder_slots"] == 1

    def test_a_BYE_is_the_same_placeholder_as_a_TBD(self):
        # The core API says `Bye` where the site API says `TBD`, for the same
        # thing. Both carry a non-positive athlete id, which is the check.
        payload = _scoreboard(
            [
                {
                    "id": "1",
                    "round": {"displayName": "Round 1"},
                    "date": "2026-08-30T04:00Z",
                    "competitors": [
                        {"id": "0", "order": 1, "name": "Bye", "athlete": {}},
                        _competitor("Jack Kennedy", 333),
                    ],
                }
            ]
        )
        fixture = parse_draw([payload], event_name="US Open")["draws"]["mens-singles"][
            0
        ]
        assert fixture["players"][0]["determined"] is False

    def test_two_placeholders_yield_no_fixture_at_all(self):
        payload = _scoreboard(
            [
                {
                    "id": "1",
                    "round": {"displayName": "Round 1"},
                    "date": "2026-08-30T04:00Z",
                    "competitors": [
                        {"id": "-3", "order": 1, "athlete": {"displayName": "TBD"}},
                        {"id": "-4", "order": 2, "athlete": {"displayName": "TBD"}},
                    ],
                }
            ]
        )
        assert parse_draw([payload], event_name="US Open")["draws"] == {}

    def test_another_tournament_on_the_same_board_is_ignored(self):
        payload = {
            "events": [
                {
                    "name": "Winston-Salem Open",
                    "groupings": [
                        {
                            "grouping": {"slug": "mens-singles"},
                            "competitions": [
                                {
                                    "id": "9",
                                    "round": {"displayName": "Round 1"},
                                    "date": "2026-08-30T04:00Z",
                                    "competitors": [
                                        _competitor("A Player", 1),
                                        _competitor("B Player", 2),
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        assert parse_draw([payload], event_name="US Open")["draws"] == {}

    def test_both_tours_carry_the_same_competition_and_it_counts_once(self):
        comp = {
            "id": "182705",
            "round": {"displayName": "Round 1"},
            "date": "2026-08-30T04:00Z",
            "competitors": [_competitor("A Player", 1), _competitor("B Player", 2)],
        }
        parsed = parse_draw(
            [_scoreboard([comp]), _scoreboard([comp])], event_name="US Open"
        )
        assert len(parsed["draws"]["mens-singles"]) == 1
        assert parsed["stats"]["competitions"] == 1

    def test_an_empty_payload_is_an_empty_parse_and_not_a_crash(self):
        assert parse_draw([], event_name="US Open") == {
            "draws": {},
            "stats": {
                "events": 0,
                "competitions": 0,
                "fixtures": 0,
                "placeholder_slots": 0,
            },
        }


# ---------------------------------------------------------------------------
# THE COMMITTED REGISTER, AFTER THE CEREMONY
# ---------------------------------------------------------------------------


class TestReleasedDraw:
    def test_the_latch_is_set(self, register):
        assert register["draw_released"] is True

    def test_it_carries_the_real_main_draw_on_both_sides(self, register):
        reg = TournamentRegister(register)
        for draw in ("mens-singles", "womens-singles"):
            fixtures = [
                m
                for m in reg.matchups
                if m.get("draw") == draw and m.get("round") == "R128"
            ]
            assert len(fixtures) >= 45, draw

    def test_NO_FIXTURE_INVENTS_A_DRAW_SLOT(self, register):
        # ESPN publishes pairings, not positions. Writing a slot from its list
        # order would fabricate the entire second round while looking exactly
        # like the first — the one claim on this page nobody could check.
        assert all(p.get("draw_slot") is None for p in register["players"])

    def test_every_main_draw_fixture_is_a_pair_of_registered_players(self, register):
        reg = TournamentRegister(register)
        keys = set(reg.by_entity)
        for matchup in reg.matchups:
            if matchup.get("round") != "R128":
                continue
            players = matchup["players"]
            assert len(players) == 2
            assert players[0] != players[1]
            assert set(players) <= keys

    def test_an_unpriced_fixture_carries_a_CENSUSED_ABSENCE_not_an_empty_list(
        self, register
    ):
        # "Nobody looked" and "we looked and there is nothing" must not be the
        # same shape — the rule `reaches` already follows for its no_market
        # cells.
        reg = TournamentRegister(register)
        fixture = next(m for m in reg.matchups if m.get("round") == "R128")
        sources = fixture["sources"]
        assert {b["source"] for b in sources} == {"kalshi", "polymarket"}
        for block in sources:
            assert block["status"] == "missing"
            assert block["market_id"] is None
            assert block["evidence"]["kind"] == "draw-fixture-census-absent"
            assert block["evidence"]["observed_at"]

    def test_the_committed_register_validates_clean(self, register):
        assert validate_register(register, us_open_2026_contract()) == []

    def test_the_qualifying_matchups_kept_their_live_markets(self, register):
        # The draw ingest must never overwrite a priced fixture with a
        # censused absence: that would drop a live price to make room for a
        # fact we already had.
        reg = TournamentRegister(register)
        qualifying = [m for m in reg.matchups if m.get("round") == "qualifying"]
        assert len(qualifying) == 28
        live = [
            m
            for m in qualifying
            if any(b.get("status") == "live" for b in m.get("sources") or [])
        ]
        assert len(live) == len(qualifying)


# ---------------------------------------------------------------------------
# build_slate — a fixture nobody prices is still a fixture
# ---------------------------------------------------------------------------


def _register_with_one_unpriced_fixture() -> dict:
    return {
        "schema_version": "tournament-register/v1",
        "tournament": "us-open",
        "season": "2026",
        "version": 1,
        "generated_at": "2026-08-27T18:00:00+00:00",
        "draw_released": True,
        "players": [
            {
                "entity_key": "a-player",
                "display_name": "A Player",
                "draw": "mens-singles",
                "role": "participant",
                "sources": [],
            },
            {
                "entity_key": "b-player",
                "display_name": "B Player",
                "draw": "mens-singles",
                "role": "participant",
                "sources": [],
            },
        ],
        "matchups": [
            {
                "matchup_key": "mens-singles:a-player-vs-b-player:2026-08-30",
                "draw": "mens-singles",
                "round": "R128",
                "scheduled_date": "2026-08-30T16:00:00+00:00",
                "players": ["a-player", "b-player"],
                "sources": [
                    {
                        "source": source,
                        "kind": "match",
                        "market_id": None,
                        "outcome_id": None,
                        "status": "missing",
                        "evidence": {"kind": "draw-fixture-census-absent"},
                    }
                    for source in ("kalshi", "polymarket")
                ],
            }
        ],
    }


class TestUnpricedFixturesRender:
    """The one line that made the whole released draw invisible."""

    def test_it_is_NOT_dropped(self):
        now = datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)
        slate = build_slate(_register_with_one_unpriced_fixture(), prices={}, now=now)
        assert slate["count"] == 1
        assert "NO_LIVE_SOURCE" not in slate["dropped"]

    def test_it_says_UNPRICED_and_not_DARK(self):
        now = datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)
        row = build_slate(_register_with_one_unpriced_fixture(), prices={}, now=now)[
            "matches"
        ][0]
        # `dark` is a price we had that aged out; `unpriced` is no market at
        # all. Only one of those is a fault of ours.
        assert row["priced"] is False
        assert row["price_state"] == "unpriced"

    def test_it_invents_NO_number_on_either_side(self):
        now = datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)
        row = build_slate(_register_with_one_unpriced_fixture(), prices={}, now=now)[
            "matches"
        ][0]
        assert row["coherent"] is False
        assert row["probability_is_live"] is False
        for side in row["sides"]:
            assert side["probability"] is None
            assert side["raw_probability"] is None
            assert side["move"] is None

    def test_a_played_fixture_is_still_dropped(self):
        # The clock still governs. A fixture six hours past its start is gone
        # whether or not anybody priced it.
        now = datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc)
        slate = build_slate(_register_with_one_unpriced_fixture(), prices={}, now=now)
        assert slate["count"] == 0
        assert slate["dropped"] == {"ALREADY_PLAYED": 1}

    def test_a_LIVE_quote_with_unmapped_sides_is_STILL_dropped(self):
        # The one drop that must survive: that is a real quote we cannot
        # attribute to a player — a linkage DEFECT, not an absence — and
        # rendering it unpriced would hide it.
        register = _register_with_one_unpriced_fixture()
        register["matchups"][0]["sources"] = [
            {
                "source": "polymarket",
                "kind": "match",
                "market_id": 1,
                "outcome_id": 2,
                "status": "live",
                "evidence": {},
                "sides": {"a-player": {"outcome_id": 2}},  # b-player missing
            }
        ]
        now = datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)
        slate = build_slate(register, prices={}, now=now)
        assert slate["count"] == 0
        assert slate["dropped"] == {"SIDES_UNMAPPED": 1}


# ---------------------------------------------------------------------------
# PLAYER IMAGES — ruling 8, and the wrong-face failure mode
# ---------------------------------------------------------------------------


class TestPlayerImageValidation:
    def test_no_block_is_fine(self):
        assert validate_player_image(None) == []

    def test_a_face_MUST_carry_its_verification(self):
        # The whole point. `Aleksandar Kovacevic` returns a Serbian footballer
        # at 200 with a photo; an unverified URL is a wrong face waiting to
        # happen, so the register refuses the file rather than rendering it.
        block = {
            "url": "https://upload.wikimedia.org/x.jpg",
            "flag_url": None,
            "evidence": {"kind": "player-image-census"},
        }
        assert validate_player_image(block) == ["PLAYER_IMAGE_NOT_VERIFIED"]
        block["verified_subject"] = True
        assert validate_player_image(block) == []

    def test_a_FLAG_needs_no_verification(self):
        # A flag is a claim about a country, read off the same ESPN record as
        # the name. There is no wrong-person failure mode to guard against.
        assert (
            validate_player_image(
                {
                    "url": None,
                    "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/esp.png",
                    "evidence": {"kind": "player-image-census"},
                }
            )
            == []
        )

    def test_an_arbitrary_host_is_refused(self):
        assert "PLAYER_IMAGE_BAD_URL" in validate_player_image(
            {
                "url": "https://evil.example.com/x.jpg",
                "verified_subject": True,
                "evidence": {},
            }
        )

    def test_a_censused_absence_still_needs_its_evidence(self):
        assert validate_player_image({"url": None, "flag_url": None}) == [
            "PLAYER_IMAGE_WRONG_SHAPE"
        ]
        assert (
            validate_player_image({"url": None, "flag_url": None, "evidence": {}}) == []
        )

    def test_the_finding_reaches_validate_player(self):
        # A validator nothing calls is a validator that is not running.
        findings = validate_player(
            {
                "entity_key": "x",
                "display_name": "X Player",
                "draw": "mens-singles",
                "role": "participant",
                "sources": [],
                "image": {"url": "https://upload.wikimedia.org/x.jpg", "evidence": {}},
            },
            draw_released=True,
            sources={"kalshi", "polymarket"},
        )
        assert "PLAYER_IMAGE_NOT_VERIFIED" in findings

    def test_player_image_ships_the_urls_and_NOT_the_evidence(self):
        view = player_image(
            {
                "image": {
                    "url": "https://upload.wikimedia.org/x.jpg",
                    "flag_url": "https://a.espncdn.com/f.png",
                    "verified_subject": True,
                    "subject_description": "American tennis player",
                    "evidence": {"kind": "player-image-census"},
                }
            }
        )
        assert view == {
            "url": "https://upload.wikimedia.org/x.jpg",
            "flag_url": "https://a.espncdn.com/f.png",
        }

    def test_no_image_yields_None_rather_than_an_empty_dict(self):
        assert player_image({}) is None
        assert player_image({"image": {"url": None, "flag_url": None}}) is None
        assert player_image(None) is None


class TestCommittedImageCoverage:
    """Alex's ruling-8 gate, as a number the suite can fail on."""

    def test_every_board_contender_has_a_verified_face(self, register):
        # "Half-covered looks worse than none." On the championship boards it
        # is not half-covered: it is complete, and this is what holds it there.
        reg = TournamentRegister(register)
        for draw in ("mens-singles", "womens-singles"):
            missing = [
                p["display_name"]
                for p in reg.board_players(draw)
                if not (p.get("image") or {}).get("url")
            ]
            assert missing == [], f"{draw}: {missing}"

    def test_every_main_draw_player_has_at_least_a_flag(self, register):
        reg = TournamentRegister(register)
        in_draw = {
            key
            for m in reg.matchups
            if m.get("round") == "R128"
            for key in m["players"]
        }
        blank = [
            reg.by_entity[key]["display_name"]
            for key in in_draw
            if not (reg.by_entity[key].get("image") or {}).get("url")
            and not (reg.by_entity[key].get("image") or {}).get("flag_url")
        ]
        assert blank == [], f"main-draw players with no image at all: {blank}"

    def test_main_draw_FACE_coverage_clears_the_gate(self, register):
        reg = TournamentRegister(register)
        for draw in ("mens-singles", "womens-singles"):
            in_draw = {
                key
                for m in reg.matchups
                if m.get("round") == "R128" and m.get("draw") == draw
                for key in m["players"]
            }
            faces = sum(
                1
                for key in in_draw
                if (reg.by_entity[key].get("image") or {}).get("url")
            )
            assert faces / len(in_draw) >= 0.90, f"{draw}: {faces}/{len(in_draw)}"

    def test_every_pinned_url_is_on_an_allowed_host(self, register):
        for player in register["players"]:
            image = player.get("image") or {}
            for url in (image.get("url"), image.get("flag_url")):
                if url is None:
                    continue
                assert url.startswith(ALLOWED_IMAGE_PREFIXES), url

    def test_every_face_names_the_article_it_came_from(self, register):
        # Checkable later without re-fetching — the same posture `sides` takes
        # toward its source labels.
        for player in register["players"]:
            image = player.get("image") or {}
            if not image.get("url"):
                continue
            assert image["verified_subject"] is True
            assert image["subject_title"]
            assert "tennis" in str(image.get("subject_description") or "").lower()

    def test_the_serbian_footballer_did_NOT_get_in(self, register):
        # The named specimen. `Aleksandar Kovacevic` bare-name resolves to a
        # footballer; the census must have taken the `(tennis)` article.
        reg = TournamentRegister(register)
        player = reg.by_entity.get("aleksandar-kovacevic")
        assert player is not None
        image = player.get("image") or {}
        assert image.get("subject_title") == "Aleksandar Kovacevic (tennis)"
        assert "tennis" in image["subject_description"].lower()

    def test_the_us_president_did_NOT_get_in(self, register):
        reg = TournamentRegister(register)
        player = reg.by_entity.get("andrew-johnson")
        if player is None:
            pytest.skip("Andrew Johnson is not in this register version")
        image = player.get("image") or {}
        assert "President" not in str(image.get("subject_description") or "")


class TestRegisterLoadsFromDisk:
    def test_load_register_still_reads_the_committed_file(self):
        register = load_register("us-open", "2026")
        assert register is not None
        assert register["draw_released"] is True
        assert (
            TournamentRegister(register).image_coverage("mens-singles")["faces"] > 100
        )
