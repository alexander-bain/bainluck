"""An LPGA card is named by the venue too, not by re-casing its `_womens` key (#8124).

Seen on production `/categories/golf` at 390px, 2026-09-22, under the LPGA Tour
heading:

    Nw Arkansas Championship Womens

`GET /api/golf` served `name: 'Nw Arkansas Championship Womens'` with
`key: 'nw_arkansas_championship_womens'`. The venues spell it correctly, on the
markets the card is built from (production, 2026-09-27):

    61811389  polymarket  "LPGA: NW Arkansas Championship Winner"
    61811391  polymarket  "LPGA: NW Arkansas Championship Hole in One?"

#7020 already recovers the venue's spelling from member names, but only for a
candidate that slugifies back to the card's key. The grouping appends `_womens`
to the key whenever a member matches `_WOMENS_RE`, and no venue writes that
word, so no LPGA member could ever pass the check and every LPGA card fell
through to `tourn_key.replace("_", " ").title()`.

The suffix is ours, so the check now also accepts the key without it. The
safety property is unchanged: a candidate must still slugify to this card's own
event, so the recovery can restore spelling but never swap the tournament. The
women's distinction is not carried by this string: `is_womens` and the LPGA
tour label are read from the member names, and the tests below assert both
survive the rename.
"""

from app.routes.golf import _build_tournament_entry, _display_name_from_markets

_KEY = "nw_arkansas_championship_womens"
_REAL_NAME = "NW Arkansas Championship"

#: What production served, and what no assertion below may accept.
_SLUG_DERIVED = "Nw Arkansas Championship Womens"


class _Market:
    def __init__(self, name, source="polymarket"):
        self.name = name
        self.id = 1
        self.external_id = "golf_specimen"
        self.source = source
        self.market_metadata: dict = {}


def _entry(tourn_key, markets):
    """Drive the real builder the feed uses, with one golfer to keep it alive."""
    return _build_tournament_entry(
        tourn_key,
        markets,
        {
            "hye-jin choi": {
                "name": "Hye-Jin Choi",
                "sources": {"polymarket": 0.1},
                "movement_24h": None,
                "movement_is_dated": False,
                "opening_probability": 0.08,
            }
        },
        [],
        [1],
        ["polymarket"],
        None,
        None,
    )


#: The live card's open members, spelled as production stores them. The Kalshi
#: sponsor-titled member is included because it is really on the card and must
#: be refused (it slugifies to a different, longer key).
_SPECIMEN_MARKETS = [
    _Market("LPGA: NW Arkansas Championship Winner"),
    _Market("LPGA: NW Arkansas Championship Hole in One?"),
    _Market("LPGA: NW Arkansas Championship Albatross?"),
    _Market("Walmart NW Arkansas Championship presented by P&G End of Round 2 Leader", "kalshi"),
]


class TestTheLpgaCardIsNamedByTheVenue:
    def test_the_served_card_reads_the_venues_spelling(self):
        entry = _entry(_KEY, _SPECIMEN_MARKETS)

        assert entry is not None
        assert entry["name"] == _REAL_NAME

    def test_the_slug_derived_spelling_is_not_served(self):
        """Vacuity guard: names the exact string the defect produced."""
        entry = _entry(_KEY, _SPECIMEN_MARKETS)

        assert entry["name"] != _SLUG_DERIVED
        assert "Womens" not in entry["name"]

    def test_the_card_is_still_a_womens_lpga_card(self):
        """Dropping the word from the name must not drop the fact."""
        entry = _entry(_KEY, _SPECIMEN_MARKETS)

        assert entry["is_womens"] is True
        assert entry["tour"] == "lpga"
        assert entry["key"] == _KEY


class TestTheSafetyPropertyHolds:
    def test_a_member_naming_another_tournament_is_still_refused(self):
        foreign = [_Market("LPGA: Walmart Classic Winner")]

        assert _display_name_from_markets(_KEY, foreign) is None

    def test_only_a_trailing_suffix_is_ignored(self):
        """`womens` elsewhere in a key is part of the event, not our suffix."""
        markets = [_Market("LPGA: Open Championship Winner")]

        assert _display_name_from_markets("womens_open_championship", markets) is None

    def test_a_mens_key_does_not_widen(self):
        """A key without the suffix matches exactly as before #8124."""
        markets = [_Market("NW Arkansas Championship Womens - Winner")]

        assert _display_name_from_markets("nw_arkansas_championship", markets) is None
