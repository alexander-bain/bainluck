"""#5349 Slice N1 — awards edition, ceremony, category-code, and marquee identity.

Pins the four identity requirements from Fable's `#5349` packet (`CASES.json` C02,
C03, C07, C19 steps 1-2, and X01):
1. C02: Prevent markets with insufficient edition evidence from joining every edition,
   and extract 2-digit edition years from `KXEMMY-<code><YY><MMM><DD>` tickers so a
   2026 Creative Arts Emmy (`KXEMMY-GADS26SEP14`) never attaches to `emmys-2027`
   even if `resolution_date` is missing.
2. C03: Keep Primetime, Daytime, International, Sports, News & Documentary,
   Children's & Family, and Regional Emmy identities separate in both
   `derive_awards_concept` and `AwardsEventAdapter.build_event`.
3. C07 / C19: Hold off a Kalshi Oscars category market whose ticker category code
   (`PIC`, `ACTO`, `ACTR`, `DIR`, `VIS`) conflicts with its title (e.g. `59164593`
   `KXOSCARVIS-27` titled `"Oscar Winner: Best Makeup and Hairstyling"`), and
   keep the refusal deterministic across rebuilds without a hand-kept ID list.
4. X01: Do not select `"Supporting Actress in a Drama Series"` as the Emmys marquee
   category through an unanchored `"drama series"` substring match.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_awards import (
    AwardsEventAdapter,
    derive_awards_concept,
    edition_year,
    has_venue_title_conflict,
    is_excluded_emmy_ceremony,
)


def _o(name, prob, is_winner=False, source=None):
    return SimpleNamespace(
        name=name,
        current_probability=prob,
        is_winner=is_winner,
        resolution_source=source,
        last_updated=None,
    )


def _market(id_, name, ticker, outcomes, *, status="open", resolution_date=None):
    return SimpleNamespace(
        id=id_,
        name=name,
        external_id=ticker,
        status=status,
        source="kalshi",
        resolution_date=resolution_date,
        outcomes=outcomes,
    )


class _Result:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self.items


class _DB:
    def __init__(self, items):
        self.items = items

    async def execute(self, query):
        return _Result(self.items)


async def _build(markets, slug):
    return await AwardsEventAdapter().build_event(slug, _DB(markets))


# ---------------------------------------------------------------------------
# 1. C02 — Edition evidence and edition-less refusal
# ---------------------------------------------------------------------------


def test_edition_year_extracts_year_from_hyphenated_emmy_date_tickers():
    """`KXEMMY-GADS26SEP14` and `KXEMMY-OVS26SEP14` carry their 2026 edition year
    before the `SEP14` date suffix even when `resolution_date` is None."""
    assert edition_year("KXEMMY-GADS26SEP14", None) == 26
    assert edition_year("KXEMMY-OVS26SEP14", None) == 26
    assert edition_year("KXEMMY-URP26SEP14", None) == 26
    assert edition_year("KXEMMY-OWCS26SEP14", None) == 26


async def test_c02_prior_edition_and_editionless_markets_do_not_join_dated_edition():
    """Case C02: neither `KXEMMY-GADS26SEP14` (with `resolution_date=None`) nor a
    truly edition-less category market (`KXEMMY-UNKNOWN`, `resolution_date=None`)
    may attach to `emmys-2027`."""
    drama_27 = _market(
        900301,
        "Emmy Winner: Outstanding Drama Series",
        "KXEMMYDSERIES-27SEP19",
        [_o("The Pitt", 0.55), _o("Severance", 0.35)],
    )
    guest_actor_26_no_date = _market(
        59172874,
        "Emmy winner: Outstanding Guest Actor in a Drama Series",
        "KXEMMY-GADS26SEP14",
        [
            _o("Ernest Harden, Jr.", 1.0, True, "api_settlement"),
            _o("Jonathan Pryce", 0.0, False, "api_settlement"),
        ],
        status="resolved",
        resolution_date=None,
    )
    editionless_comedy = _market(
        900302,
        "Emmy Winner: Outstanding Comedy Series",
        "KXEMMYCSERIES",
        [_o("Hacks", 0.50), _o("The Bear", 0.40)],
        resolution_date=None,
    )
    editionless_nomination = _market(
        900303,
        "Emmy nominees: Outstanding Comedy Series",
        "KXEMMYNOMS-COM",
        [_o("Hacks", 0.95), _o("The Bear", 0.90)],
        resolution_date=None,
    )

    body = await _build(
        [drama_27, guest_actor_26_no_date, editionless_comedy, editionless_nomination],
        "emmys-2027",
    )
    assert body is not None
    assert body["event"]["key"] == "event:awards:emmys-2027"
    child_ids = [c["market_id"] for c in body["children"]]
    assert child_ids == [900301]
    assert 59172874 not in child_ids
    assert 900302 not in child_ids
    assert 900303 not in child_ids


# ---------------------------------------------------------------------------
# 2. C03 — Distinct Emmy ceremony identities
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "external_id,name",
    [
        ("KXSPORTSEMMY-26", "Sports Broadcasting Award"),
        (None, "Daytime Emmy winner: Outstanding Drama Series"),
        (None, "International Emmy winner: Best Drama Series"),
        ("KXEMMYDAYTIME-27", "Daytime Emmys: Outstanding Drama Series"),
        ("KXEMMYINTL-27", "International Emmy Award for Drama Series"),
        (None, "News & Documentary Emmy Award for Outstanding Investigative Report"),
        (None, "Children's & Family Emmy Award for Outstanding Preschool Series"),
    ],
)
def test_c03_non_primetime_emmy_ceremonies_are_refused(external_id, name):
    """Case C03: Daytime, International, Sports, News & Documentary, and Children's &
    Family Emmys are distinct ceremonies and never link to `event:awards:emmys`."""
    assert is_excluded_emmy_ceremony(external_id, name) is True
    assert derive_awards_concept(external_id, name) is None


async def test_c03_build_event_excludes_non_primetime_emmy_markets():
    """A Daytime or International Emmy market sharing a `KXEMMY*` stem is refused
    during `AwardsEventAdapter.build_event("emmys-2027")`."""
    primetime_drama = _market(
        900301,
        "Emmy Winner: Outstanding Drama Series",
        "KXEMMYDSERIES-27SEP19",
        [_o("The Pitt", 0.55), _o("Severance", 0.35)],
    )
    daytime_drama = _market(
        900310,
        "Daytime Emmy winner: Outstanding Drama Series",
        "KXEMMYDAYTIME-27",
        [_o("General Hospital", 0.60), _o("The Young and the Restless", 0.30)],
    )
    intl_drama = _market(
        900311,
        "International Emmy winner: Best Drama Series",
        "KXEMMYINTL-27",
        [_o("Drops of God", 0.55), _o("The Newsreader", 0.35)],
    )
    body = await _build([primetime_drama, daytime_drama, intl_drama], "emmys-2027")
    assert [c["market_id"] for c in body["children"]] == [900301]


# ---------------------------------------------------------------------------
# 3. C07 & C19 — Category code vs. title conflict (`KXOSCARVIS-27` / Makeup)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "external_id,name,expected_conflict",
    [
        # Positively contradictory category titles on known codes -> True
        ("KXOSCARVIS-27", "Oscar Winner: Best Makeup and Hairstyling", True),
        ("kalshi:KXOSCARVIS-27", "Oscar Winner: Best Makeup and Hairstyling", True),
        ("KXOSCARPIC-27", "Oscar Winner: Best Director", True),
        ("KXOSCARDIR-27", "Oscar Winner: Best Picture", True),
        ("KXOSCARACTO-27", "Oscar Winner: Best Actress", True),
        ("KXOSCARACTR-27", "Oscar Winner: Best Actor", True),
        # Valid title variants on known codes -> False
        ("KXOSCARVIS-27", "Oscar Winner: Best Visual Effects", False),
        ("KXOSCARVIS-27", "99th Academy Award for Best Visual Effect", False),
        ("KXOSCARPIC-27", "Oscar Winner: Best Picture", False),
        ("KXOSCARPIC-27", "2027 Academy Award for Best Motion Picture of the Year", False),
        ("KXOSCARDIR-27", "Oscar Winner: Best Director", False),
        ("KXOSCARDIR-27", "2027 Oscar for Best Directing?", False),
        ("KXOSCARACTO-27", "Oscar for Best Actor in a Leading Role", False),
        ("KXOSCARACTR-27", "Oscar for Best Actress in a Supporting Role", False),
        # Missing or blank titles (not a positively contradictory category title) -> False
        ("KXOSCARVIS-27", None, False),
        ("KXOSCARVIS-27", "", False),
        ("KXOSCARVIS-27", "   ", False),
        ("KXOSCARPIC-27", None, False),
        # Unknown provider codes -> False (unchecked, never guessed)
        ("KXOSCARMAH-27", "Oscar Winner: Best Makeup and Hairstyling", False),
        ("KXOSCARSCORE-27", "2027 Oscar for Best Music (Original Score)", False),
        ("KXOSCARINTLFILM-27", "Oscar Winner: Best International Feature Film", False),
        # Nomination markets (both NOM ticker prefix and nomination phrasing on category stem) -> False
        ("KXOSCARNOMVISUAL-27", "Oscar nominations for Best Visual Effects", False),
        ("KXOSCARNOMPIC-27", "Oscar nominees: Best Makeup and Hairstyling", False),
        ("KXOSCARVIS-27", "Will Dune: Part Three be nominated for Best Makeup?", False),
        ("KXOSCARPIC-27", "Oscar nominations for Best Director", False),
        # Novelty props without category keywords -> False
        ("KXOSCARPIC-27", "Will Conan O'Brien host the Oscars?", False),
    ],
)
def test_c07_has_venue_title_conflict(external_id, name, expected_conflict):
    assert has_venue_title_conflict(external_id, name) is expected_conflict


def test_oscar_ticker_category_keywords_parity_with_theme_definitions():
    """Guard against quiet drift between `event_awards._OSCAR_TICKER_CATEGORY_KEYWORDS`
    and `theme_definitions._OSCAR_TICKER_CATEGORY_KEYWORDS`."""
    from app.utils.event_awards import _OSCAR_TICKER_CATEGORY_KEYWORDS as awards_map
    from app.utils.theme_definitions import _OSCAR_TICKER_CATEGORY_KEYWORDS as theme_map

    assert set(awards_map.keys()) == set(theme_map.keys())
    for code, pat in awards_map.items():
        other = theme_map[code]
        assert pat.pattern == other.pattern
        assert pat.flags == other.flags


async def test_c07_and_c19_conflicting_vis_market_is_held_off_across_rebuilds():
    """Cases C07 and C19 steps 1-2: `59164593` (`KXOSCARVIS-27` mis-titled
    'Oscar Winner: Best Makeup and Hairstyling') is held off `oscars-2027` so only
    `59164596` (`KXOSCARMAH-27`) renders as 'Best Makeup and Hairstyling', and the
    refusal holds across repeated builds until the venue's own title/code agree."""
    best_pic = _market(
        6173044,
        "Oscar Winner: Best Picture",
        "KXOSCARPIC-27",
        [_o("The Odyssey", 0.445), _o("You Can See Everything", 0.315)],
    )
    makeup_real = _market(
        59164596,
        "Oscar Winner: Best Makeup and Hairstyling",
        "KXOSCARMAH-27",
        [_o("Werwulf", 0.36), _o("Digger", 0.18)],
    )
    vis_mistitled = _market(
        59164593,
        "Oscar Winner: Best Makeup and Hairstyling",
        "KXOSCARVIS-27",
        [
            _o("The Odyssey", 0.285, False, "ungradeable_result"),
            _o("Dune: Part Three", 0.25, False, "ungradeable_result"),
        ],
        status="resolved",
    )

    for _ in range(2):
        body = await _build([best_pic, makeup_real, vis_mistitled], "oscars-2027")
        child_ids = [c["market_id"] for c in body["children"]]
        assert child_ids == [6173044, 59164596]
        assert 59164593 not in child_ids
        makeup_cards = [
            c for c in body["children"] if c["market_name"] == "Best Makeup and Hairstyling"
        ]
        assert len(makeup_cards) == 1
        assert makeup_cards[0]["market_id"] == 59164596

    # Once the venue corrects 59164593's title to Visual Effects, it attaches cleanly:
    vis_corrected = _market(
        59164593,
        "Oscar Winner: Best Visual Effects",
        "KXOSCARVIS-27",
        [_o("The Odyssey", 0.285), _o("Dune: Part Three", 0.25)],
    )
    body_after_fix = await _build([best_pic, makeup_real, vis_corrected], "oscars-2027")
    assert {c["market_id"] for c in body_after_fix["children"]} == {
        6173044,
        59164596,
        59164593,
    }


# ---------------------------------------------------------------------------
# 4. X01 — Marquee Drama Series selection does not match Supporting Actress
# ---------------------------------------------------------------------------


async def test_x01_emmys_marquee_selects_drama_series_not_supporting_actress():
    """Case X01: when 'Emmy Winner: Outstanding Supporting Actress in a Drama Series'
    (`9952617`) precedes 'Emmy Winner: Outstanding Drama Series' (`9750359`), the
    adapter selects `9750359` ('Outstanding Drama Series') as the primary hero and
    ceremony end_date source, never Supporting Actress."""
    supporting_actress_drama = _market(
        9952617,
        "Emmy Winner: Outstanding Supporting Actress in a Drama Series ",
        "KXEMMYDSACTR-26SEP14",
        [
            _o("Taylor Dearden", 1.0, True, "api_settlement"),
            _o("Katherine LaNasa", 0.0, False, "api_settlement"),
        ],
        status="resolved",
        resolution_date=datetime(2026, 9, 15, 1, 3, 45, tzinfo=timezone.utc),
    )
    drama_series = _market(
        9750359,
        "Emmy Winner: Outstanding Drama Series",
        "KXEMMYDSERIES-26SEP14",
        [
            _o("The Pitt", 1.0, True, "api_settlement"),
            _o("Euphoria", 0.0, False, "api_settlement"),
        ],
        status="resolved",
        resolution_date=datetime(2026, 9, 15, 2, 46, 47, tzinfo=timezone.utc),
    )
    body = await _build([supporting_actress_drama, drama_series], "emmys-2026")
    assert body["primary"]["evolution_market_id"] == 9750359
    assert body["primary"]["label"] == "Emmy Winner: Outstanding Drama Series"
    assert [c["name"] for c in body["primary"]["competitors"] if c["won"]] == [
        "The Pitt"
    ]
    assert body["event"]["end_date"] == "2026-09-15T02:46:47+00:00"
    assert body["children"][0]["market_id"] == 9750359
