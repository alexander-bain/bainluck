"""A golf card is named by the venue, not by re-casing its own slug (#7020).

Seen on production v4793, 2026-09-19 ~19:40 PDT, on the live Korn Ferry card at
390px on the Discover feed:

    Nationwide Children S Hospital Championship

``_slug_tournament`` is ``re.sub(r"[^a-z0-9]+", "_", name.lower())``, which turns
a non-alphanumeric run into a SEPARATOR rather than deleting it. So the
apostrophe does not vanish, it becomes an underscore — ``children's`` ->
``children_s`` — and ``tourn_key.replace("_", " ").title()`` then renders the
orphaned ``s`` as a standalone capital. The round trip is lossy and nothing
downstream can repair it: by the time the client holds the key, ``children s``
and ``children's`` are the same string.

The correct spelling was never missing. It is in our own database, on the
markets the card is built from:

    61010899  datagolf    "Nationwide Children's Hospital Championship - Winner"
    61226145  polymarket  "Korn Ferry Tour: Nationwide Children's ... Third Round Leader"

═══ SCOPE: 33 OF 94, NOT ONE BAD ROW ═══

Measured against the DataGolf schedule this route already loads, 33 of its 94
tournaments would render a wrong name if they reached that fallback — and the
apostrophe is only one of the ways:

    u_s_open                       'U S Open'              vs  'U.S. Open'
    rbc_heritage                   'Rbc Heritage'          vs  'RBC Heritage'
    bmw_pga_championship           'Bmw Pga Championship'  vs  'BMW PGA Championship'
    zurich_classic_of_new_orleans  '... Classic Of ...'    vs  '... Classic of ...'
    at_t_pebble_beach_pro_am       'At T Pebble Beach Pro Am' vs 'AT&T Pebble Beach Pro-Am'

Only one was visible on the night it was filed, because only two tournament
cards were live and ``biltmore_championship_asheville`` happens to title-case
cleanly. The other 32 are latent behind the golf calendar, which is why this is
fixed as a rule rather than as a map entry — and every entry the maps have
already gained for it, ``hsbc_women_s_world_championship`` among them, was this
same defect patched one tournament at a time.

═══ WHY THE OBVIOUS FIX IS THE TRAP, AND WHAT THE CONTROL IS FOR ═══

#7020 proposes serving the name the markets already carry. That is right, but
taking the FIRST member is a coin flip, and #7348 measured the reason on a
different surface: one BMW PGA family carries both spellings at once, and the
garbled one leads.

    61485021  kalshi  Bmw Pga Championship: Top 10 Finishers   <- garbled, LEADS
    61525809  kalshi  BMW PGA Championship: To Make the Cut    <- correct

So naive member-name recovery repairs "Children S" and regresses into "Bmw Pga
Championship". ``TestTheGarbledSiblingDoesNotWin`` is not decoration — it is the
whole reason this is a scoring rule and not ``tourn_markets[0].name``, and it
deliberately puts the garbled spelling in the MAJORITY so a tie-break on
frequency alone cannot pass it.

The rule: among member names that slugify back to this same key, prefer one
that ``.title()`` could not have produced. An apostrophe, an ampersand or an
acronym is exactly the information the slug destroyed; a candidate equal to its
own ``.title()`` carries none.

═══ THE SAFETY PROPERTY IS THE SLUG FILTER ═══

``TestItCannotRenameTheCardToADifferentEvent`` is the assertion that makes this
change small. Every accepted candidate slugifies back to the key it was looked
up by, so the fix can only restore characters the slug erased — it can never
change WHICH tournament a card is about. A member carrying a different event,
or chrome the stripper does not know, is refused and the caller keeps the
behaviour it has today. That refusal is invisible by construction (it neither
raises nor drops a card), so it is asserted rather than assumed.
"""

import pytest

from app.routes.golf import (
    _build_tournament_entry,
    _display_name_from_markets,
    _slug_tournament,
)

#: The production specimen, spelled as the markets actually spell it.
_REAL_NAME = "Nationwide Children's Hospital Championship"
_SPECIMEN_SLUG = "nationwide_children_s_hospital_championship"

#: What the un-fixed fallback served, and what no assertion below may accept.
_SLUG_DERIVED = "Nationwide Children S Hospital Championship"


class _Market:
    """`name` is the attribute under test; the rest is what the builder reads."""

    def __init__(self, name, external_id="golf_specimen"):
        self.name = name
        self.id = 1
        self.external_id = external_id
        self.source = "datagolf"
        self.market_metadata: dict = {}


def _entry(tourn_key, markets):
    """Drive the real builder the feed uses, with one golfer to keep it alive."""
    return _build_tournament_entry(
        tourn_key,
        markets,
        {
            "john marshall butler": {
                "name": "John Marshall Butler",
                "sources": {"datagolf_model": 0.5},
                "movement_24h": None,
                "movement_is_dated": False,
                "opening_probability": 0.16,
            }
        },
        [],
        [1],
        ["datagolf"],
        None,
        None,
    )


#: The five markets the live card was actually built from.
_SPECIMEN_MARKETS = [
    _Market(f"{_REAL_NAME} - Winner"),
    _Market(f"{_REAL_NAME} - Top 5 Finish"),
    _Market(f"{_REAL_NAME} - Top 10 Finish"),
    _Market(f"Korn Ferry Tour: {_REAL_NAME} Third Round Leader"),
    _Market(f"Korn Ferry Tour: {_REAL_NAME} Hole in One?"),
]


class TestTheCardIsNamedByTheVenue:
    def test_the_served_card_keeps_the_apostrophe(self):
        """The reader-visible assertion: the published name, end to end."""
        entry = _entry(_SPECIMEN_SLUG, _SPECIMEN_MARKETS)

        assert entry is not None
        assert entry["name"] == _REAL_NAME

    def test_the_slug_derived_spelling_is_not_served(self):
        """The vacuity guard.

        Asserting the correct name alone would also pass against a future where
        the maps grew a hand-patched entry, which is the practice this ship is
        meant to end. This names the string the defect produced, so the test
        fails for the reason it was written.
        """
        entry = _entry(_SPECIMEN_SLUG, _SPECIMEN_MARKETS)

        assert entry["name"] != _SLUG_DERIVED
        assert " S " not in entry["name"]

    def test_the_recovery_is_order_independent(self):
        """A card must not rename itself between two equivalent requests.

        The markets arrive in whatever order the query returned them, so a rule
        that resolved ties by position would serve one spelling now and another
        later — a defect no single screenshot could ever catch.
        """
        forward = _display_name_from_markets(_SPECIMEN_SLUG, _SPECIMEN_MARKETS)
        reverse = _display_name_from_markets(_SPECIMEN_SLUG, list(reversed(_SPECIMEN_MARKETS)))

        assert forward == reverse == _REAL_NAME


class TestTheGarbledSiblingDoesNotWin:
    """#7348's family: the venue ships both spellings and the bad one leads."""

    #: Garbled deliberately in the MAJORITY, 3 against 2.
    _BMW = [
        _Market("Bmw Pga Championship: Top 10 Finishers"),
        _Market("Bmw Pga Championship: Top 20 Finishers"),
        _Market("Bmw Pga Championship: Top 5 Finishers"),
        _Market("BMW PGA Championship: To Make the Cut"),
        _Market("BMW PGA Championship End of Round 1 Leader"),
    ]

    def test_the_acronym_beats_the_title_cased_majority(self):
        assert _display_name_from_markets("bmw_pga_championship", self._BMW) == "BMW PGA Championship"

    def test_the_first_member_alone_would_have_lost(self):
        """Proves the control is live: the naive rule really does fail here.

        If the leading member ever stopped being the garbled one, the test
        above would pass for free and quietly stop guarding anything.
        """
        naive = self._BMW[0].name

        assert "Bmw Pga" in naive


class TestItCannotRenameTheCardToADifferentEvent:
    """The slug filter is the safety property, so it is asserted, not assumed."""

    def test_a_member_naming_another_tournament_is_refused(self):
        foreign = [_Market("Sanderson Farms Championship - Winner")]

        assert _display_name_from_markets(_SPECIMEN_SLUG, foreign) is None

    def test_every_accepted_candidate_slugs_back_to_its_own_key(self):
        recovered = _display_name_from_markets(_SPECIMEN_SLUG, _SPECIMEN_MARKETS)

        assert _slug_tournament(recovered) == _SPECIMEN_SLUG

    @pytest.mark.parametrize(
        "markets",
        [
            pytest.param([], id="no_markets"),
            pytest.param([_Market(None)], id="name_is_none"),
            pytest.param([_Market("")], id="name_is_empty"),
            pytest.param([object()], id="object_without_a_name"),
        ],
    )
    def test_an_unusable_market_list_refuses_rather_than_raises(self, markets):
        assert _display_name_from_markets(_SPECIMEN_SLUG, markets) is None


class TestTodaysBehaviourIsPreserved:
    """Controls. These pass before this ship and after it."""

    def test_a_key_with_no_usable_member_keeps_the_slug_fallback(self):
        """The fallback is narrowed, not removed."""
        entry = _entry("some_unmapped_event", [_Market("Wholly Unrelated Market - Winner")])

        assert entry["name"] == "Some Unmapped Event"

    def test_a_hand_mapped_tournament_is_unchanged(self):
        """The maps still win, so no curated name regresses to a venue string."""
        entry = _entry("pga_championship", [_Market("Pga Championship - Winner")])

        assert entry["name"] == "PGA Championship"

    def test_a_cleanly_title_cased_key_is_unaffected(self):
        """The card that shared the live screenshot with the defect."""
        entry = _entry(
            "biltmore_championship_asheville",
            [_Market("Biltmore Championship Asheville - Winner")],
        )

        assert entry["name"] == "Biltmore Championship Asheville"
