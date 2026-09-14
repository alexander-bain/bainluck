"""#2621 — the sport chip on a Discover card names the competition, not a
fragment of its key.

Photographed on production 2026-09-14 21:58Z, phone width 390px,
https://www.bainluck.com/ (Discover, the default landing page): a finished
La Liga match whose chip read ``LIGA``. The payload for that card, same minute:

    "sport":       "soccer_spain_la_liga",
    "sport_name":  "La Liga - Spain",
    "sport_label": "LIGA"

``EventCard.tsx`` renders ``data.sport_label`` verbatim, so the served string is
the rendered string and this is decided entirely in ``_get_sport_label``.

THE CLASS, which is why this file is not three assertions about three keys:
``_SPORT_LABEL_MAP`` is an allowlist whose DEFAULT IS A PLAUSIBLE REAL WORD. A
miss did not fail and did not fall silent — it clipped the key's last segment
and shipped it as a league name. Measured against the real population rather
than a guessed one (``SELECT s.key ... FROM events e JOIN sports s`` over a
10-day window, 95 distinct keys, read 2026-09-14 23:2xZ): 83 miss the 14-entry
map and 58 of those clipped to a word the key does not support.

TWO DISTINCT READER HARMS, and the second is the worse one:

  1. WRONG — ``soccer_italy_serie_a`` -> ``A``, ``soccer_france_ligue_one`` ->
     ``ONE``, ``soccer_spain_la_liga`` -> ``LIGA``, ``baseball_mlb_preseason``
     -> ``PRESEASON``.
  2. COLLIDING — the clip is not merely wrong, it is INFORMATION-FREE. Ten
     competitions printed one chip reading ``LEAGUE`` (UEFA Nations, UEFA
     Europa, UEFA Europa Conference, Japan's J League, Turkey, Russia, Greece,
     Saudi Arabia, the Caribbean Premier League and Sweden's HOCKEY league);
     three printed ``OPEN``; three printed ``BUNDESLIGA`` across two different
     sports; ``LIGA`` itself is shared by La Liga and Portugal's Primeira Liga.
     A chip exists to tell one competition from another, so a label that cannot
     is the whole defect even where the word is real.

``TestNoTwoCompetitionsShareAChip`` is the load-bearing class: a fix that adds
the four photographed keys to the map — the fix a reader of the issue title
writes — leaves all ten ``LEAGUE`` keys colliding and fails there.

NOT IN SCOPE, deliberately: the eleven ``*_other`` keys still label ``OTHER``
under both the old derivation and the new one, so this ship neither fixes nor
regresses them. They are a separate defect (the served name IS the key for those
rows) and are pinned below as a control so a later widening is visible.
"""


from collections import defaultdict

from app.routes.feed import _SPORT_LABEL_MAP, _get_sport_label

# ---------------------------------------------------------------------------
# The real population, frozen from production 2026-09-14: every sport key
# carrying an event in a 10-day window. Frozen deliberately — the guard's
# question is "can two competitions print one chip", which needs a corpus of
# keys that genuinely coexist on the feed, not a hand-built sample that would
# only contain the collisions its author already knew about.
# ---------------------------------------------------------------------------
PRODUCTION_SPORT_KEYS = [
    "tennis_other",
    "soccer_other",
    "esports",
    "esports_other",
    "icehockey_other",
    "baseball_milb",
    "boxing_boxing",
    "baseball_other",
    "soccer_argentina_primera_division",
    "soccer_spain_la_liga",
    "basketball_other",
    "americanfootball_ncaaf_fcs",
    "baseball_npb",
    "soccer_efl_champ",
    "soccer_brazil_campeonato",
    "soccer_spain_segunda_division",
    "soccer_germany_liga3",
    "baseball_kbo",
    "soccer_england_league1",
    "soccer_brazil_serie_b",
    "soccer_england_league2",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    "soccer_germany_bundesliga",
    "soccer_netherlands_eredivisie",
    "soccer_mexico_ligamx",
    "soccer_japan_j_league",
    "soccer_italy_serie_b",
    "soccer_uefa_nations_league",
    "soccer_sweden_superettan",
    "cricket_other",
    "soccer_poland_ekstraklasa",
    "soccer_portugal_primeira_liga",
    "soccer_turkey_super_league",
    "aussierules_aflw",
    "handball_germany_bundesliga",
    "rugby_other",
    "soccer_belgium_first_div",
    "soccer_sweden_allsvenskan",
    "tennis_atp_us_open",
    "soccer_germany_bundesliga2",
    "soccer_uefa_europa_league",
    "soccer_russia_premier_league",
    "soccer_korea_kleague1",
    "tennis_wta_us_open",
    "soccer_greece_super_league",
    "soccer_france_ligue_two",
    "soccer_norway_eliteserien",
    "soccer_switzerland_superleague",
    "soccer_saudi_arabia_pro_league",
    "soccer_germany_dfb_pokal",
    "icehockey_liiga",
    "soccer_chile_campeonato",
    "soccer_finland_veikkausliiga",
    "soccer_uefa_europa_conference_league",
    "cricket_international_t20",
    "soccer_england_efl_cup",
    "soccer_spl",
    "soccer_denmark_superliga",
    "rugbyleague_nrl",
    "americanfootball_other",
    "soccer_fa_cup",
    "soccer_league_of_ireland",
    "rugbyleague_nrlw",
    "soccer_germany_bundesliga_women",
    "soccer_austria_bundesliga",
    "cricket_caribbean_premier_league",
    "soccer_conmebol_copa_libertadores",
    "tennis_wta_guadalajara_open",
    "soccer_china_superleague",
    "americanfootball_cfl",
    "basketball_euroleague",
    "soccer_conmebol_copa_sudamericana",
    "icehockey_mestis",
    "icehockey_sweden_hockey_league",
    "aussierules_afl",
    "motorsport_other",
    "cricket_odi",
    "cricket_test_match",
    "soccer_italy_coppa_italia",
    "lacrosse_pll",
    "soccer_concacaf_leagues_cup",
    "mma_other",
    # In the map already, and carried events in the same window — present so the
    # collision question is asked over what a reader actually sees side by side,
    # mapped and derived labels together.
    "americanfootball_nfl",
    "basketball_nba",
    "baseball_mlb",
    "icehockey_nhl",
    "soccer_epl",
    "soccer_usa_mls",
    "soccer_uefa_champs_league",
    "golf_pga",
    "tennis_atp",
    "tennis_wta",
    "mma_mixed_martial_arts",
    "mma_ufc",
    "golf_lpga",
    "lacrosse_ncaa",
]

# The `*_other` rows store their own key where a brand belongs, so every one of
# them labels `OTHER`. Unchanged by this ship in either direction — pinned so
# the collision test below can exempt exactly these and nothing else, and so a
# later fix that touches them shows up here as a failure to update this list.
OTHER_FAMILY = sorted(k for k in PRODUCTION_SPORT_KEYS if k.split("_")[-1] == "other")


class TestThePhotographedCard:
    """The specimen on the landing page, and the three keys named beside it."""

    def test_la_liga_chip_no_longer_reads_liga(self):
        # The photographed card. `LIGA` is both wrong and shared with Portugal.
        assert _get_sport_label("soccer_spain_la_liga") == "LA LIGA"

    def test_serie_a_chip_is_not_the_single_letter_a(self):
        assert _get_sport_label("soccer_italy_serie_a") == "SERIE A"

    def test_ligue_1_chip_is_not_the_word_one(self):
        assert _get_sport_label("soccer_france_ligue_one") == "LIGUE 1"

    def test_mlb_preseason_keeps_the_sport_it_belongs_to(self):
        # Derived, not mapped: "PRESEASON" alone named no competition.
        assert _get_sport_label("baseball_mlb_preseason") == "MLB PRESEASON"

    def test_the_original_filings_us_open_card_names_its_draw(self):
        # #2621 as first filed, 2026-09-01: `tennis_atp_us_open` -> `OPEN`.
        # Note this is stronger than that filing's own suggestion of "US OPEN",
        # which would print one identical chip for both draws.
        assert _get_sport_label("tennis_atp_us_open") == "ATP US OPEN"
        assert _get_sport_label("tennis_wta_us_open") == "WTA US OPEN"
        assert _get_sport_label("tennis_atp_us_open") != _get_sport_label(
            "tennis_wta_us_open"
        )


class TestNoTwoCompetitionsShareAChip:
    """The load-bearing class. A chip that cannot tell two competitions apart
    has failed at the only job it has, so this asks the question over the real
    population rather than over the keys the issue happened to name."""

    def test_every_competition_gets_its_own_chip(self):
        by_label = defaultdict(list)
        for key in PRODUCTION_SPORT_KEYS:
            if key in OTHER_FAMILY:
                continue
            by_label[_get_sport_label(key)].append(key)
        collisions = {
            label: sorted(keys) for label, keys in by_label.items() if len(keys) > 1
        }
        assert collisions == {}, (
            "one chip word for several competitions — a reader cannot tell them "
            f"apart: {collisions}"
        )

    def test_the_ten_league_keys_that_collided_are_each_distinct_now(self):
        # Named explicitly so the largest collision cannot silently come back
        # through a future map entry or a re-clip.
        league_keys = [
            k
            for k in PRODUCTION_SPORT_KEYS
            if k.endswith("_league") and k not in OTHER_FAMILY
        ]
        assert len(league_keys) >= 8, "the corpus lost the keys this test is about"
        labels = [_get_sport_label(k) for k in league_keys]
        assert len(set(labels)) == len(labels), f"still colliding: {labels}"
        assert "LEAGUE" not in labels

    def test_bundesliga_does_not_label_a_handball_match_as_the_football_one(self):
        football = _get_sport_label("soccer_germany_bundesliga")
        handball = _get_sport_label("handball_germany_bundesliga")
        austria = _get_sport_label("soccer_austria_bundesliga")
        assert len({football, handball, austria}) == 3


class TestTheDerivationItself:
    """Properties that hold for any key, including ones nobody has enumerated —
    the reason the fix is a derivation and not a longer allowlist."""

    def test_an_unenumerated_key_is_named_in_full_not_clipped(self):
        # No such key exists today; the point is that the first time one ranks,
        # it reads correctly with no map edit and no second filing of #2621.
        assert (
            _get_sport_label("tennis_wta_brisbane_international")
            == "WTA BRISBANE INTERNATIONAL"
        )

    def test_the_label_is_never_only_the_final_segment_of_a_long_key(self):
        # The exact mutant: `return parts[-1].upper()`. Every multi-segment key
        # outside the map must carry more than its tail.
        offenders = []
        for key in PRODUCTION_SPORT_KEYS:
            if key in _SPORT_LABEL_MAP:
                continue
            parts = key.split("_")
            if len(parts) < 3:
                continue
            if _get_sport_label(key) == parts[-1].upper():
                offenders.append(key)
        assert offenders == [], f"still clipped to the last segment: {offenders}"

    def test_the_sport_family_prefix_is_dropped_not_printed(self):
        # The opposite mutant: returning the whole key uppercased. The chip sits
        # beside a category emoji, so the family word is already on screen.
        assert _get_sport_label("soccer_fa_cup") == "FA CUP"
        assert _get_sport_label("cricket_test_match") == "TEST MATCH"

    def test_a_single_segment_key_is_served_whole(self):
        assert _get_sport_label("esports") == "ESPORTS"

    def test_no_key_yields_no_chip(self):
        assert _get_sport_label(None) is None
        assert _get_sport_label("") is None

    def test_a_trailing_or_doubled_separator_does_not_empty_the_chip(self):
        # `"a__b".split("_")` yields an empty middle segment; joining it raw
        # would print a double space inside the chip.
        assert _get_sport_label("soccer_spain__segunda") == "SPAIN SEGUNDA"
        assert _get_sport_label("soccer_spain_") == "SPAIN"


class TestTheChipsThatWereAlreadyRight:
    """The other direction. 25 of the 83 fall-through keys already read
    correctly under the clip; a fix that improves the broken ones by breaking
    these has not helped a reader."""

    def test_acronym_keys_are_unchanged(self):
        for key, expected in [
            ("mma_ufc", "UFC"),
            ("golf_lpga", "LPGA"),
            ("lacrosse_pll", "PLL"),
            ("americanfootball_cfl", "CFL"),
            ("baseball_npb", "NPB"),
            ("baseball_kbo", "KBO"),
            ("baseball_milb", "MILB"),
            ("rugbyleague_nrl", "NRL"),
            ("basketball_euroleague", "EUROLEAGUE"),
            ("icehockey_liiga", "LIIGA"),
            ("aussierules_afl", "AFL"),
        ]:
            assert _get_sport_label(key) == expected, key

    def test_the_mapped_brands_still_win_over_the_derivation(self):
        for key, expected in [
            ("americanfootball_nfl", "NFL"),
            ("baseball_mlb", "MLB"),
            ("soccer_uefa_champs_league", "UCL"),
            ("mma_mixed_martial_arts", "MMA"),
        ]:
            assert _get_sport_label(key) == expected, key

    def test_the_other_family_is_untouched_by_this_ship(self):
        # A control, not an endorsement: `OTHER` is a separate defect. If a
        # later change starts naming these, this test is the place that says so.
        assert len(OTHER_FAMILY) >= 10
        for key in OTHER_FAMILY:
            assert _get_sport_label(key) == "OTHER", key


class TestTheMapStaysAMapOfBrands:
    """#2621's cause was an allowlist whose default was a plausible value. The
    repair is the derivation; the map must not quietly grow back into the
    mechanism by absorbing keys the derivation already serves."""

    def test_every_mapped_label_is_shorter_than_its_derived_form(self):
        # A map entry earns its place by being the brand a reader knows, which
        # is always tighter than "COUNTRY COMPETITION". An entry that merely
        # restates the derivation is dead weight and hides the derivation's
        # behaviour from every other key.
        for key, label in _SPORT_LABEL_MAP.items():
            derived = " ".join(p.upper() for p in key.split("_")[1:])
            assert len(label) <= len(derived), f"{key}: {label!r} vs {derived!r}"

    # A source-scan for the literal `parts[-1]` was written here and DELETED
    # rather than repaired: it red-flagged this file's own docstring, which
    # quotes the defective line on purpose, and it killed no mutant that
    # `test_the_label_is_never_only_the_final_segment_of_a_long_key` does not
    # already kill behaviourally over the real corpus. A guard that restates a
    # behavioural test in text form only adds a way to fail on prose.
