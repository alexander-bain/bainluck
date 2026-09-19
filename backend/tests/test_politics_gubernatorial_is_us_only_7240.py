"""#7240 — the /politics Gubernatorial section is US governor races only.

Production LOOK at 390px on 2026-09-19 14:37Z: the Gubernatorial section read
`10 shown · 403 total` and **five of the ten cards were not US governor
races** — Belgorod Oblast and Ulyanovsk Oblast (Russia), São Paulo, Santa
Catarina and Mato Grosso do Sul (Brazil) — styled identically to Nevada,
Idaho, Illinois, Pennsylvania and Colorado.

The page already knew better: the International section directly below carried
`Brazil Presidential Election First Round: 1st Place in Santa Catarina`, the
same Brazilian state, filed correctly *because that title happens to contain
the word "Brazil"*. `_THEME_BY_NAME` recognises a foreign contest only by a
country word or demonym, and a state name never says its country.

Measured before the rule was written, on a 500-row sample of open
governor/gubernatorial markets replayed through the real `_classify_theme`:
414 classified `gubernatorial`, of which 69 are place-led race titles naming
Brazilian, Mexican, Russian, Slovak or Japanese subdivisions.

⚠️  THE FIRST DRAFT OF THIS RULE SHIPPED TEN US RACES ABROAD, and only the
replay caught it. `Alabama Lieutenant Governor winner?` has a leading phrase
that is not a bare state name; with a greedy place group the optional
`lieutenant` branch is never tried, so the place parsed as "Alabama
Lieutenant", missed the allowlist, and the market was called international.
That is the failure this file exists to pin — an allowlist whose miss returns
a real value stores a plausible lie. `test_us_lieutenant_governor_races_stay`
is the arm that was red.

Both directions are pinned per gotcha #43: the foreign cards go AND every
shape of US governor market stays.
"""

from types import SimpleNamespace

import pytest

from app.routes.politics import _classify_theme


def _market(name: str, external_id: str = "999") -> SimpleNamespace:
    return SimpleNamespace(name=name, external_id=external_id)


def theme(name: str, external_id: str = "999") -> str:
    return _classify_theme(_market(name, external_id))


# --------------------------------------------------------------------------
# The ship: the five cards a reader actually saw
# --------------------------------------------------------------------------

SHOPPED_FOREIGN = [
    "Belgorod Oblast Gubernatorial Election Winner",
    "Ulyanovsk Oblast Gubernatorial Election Winner",
    "São Paulo Governor Election Winner",
    "Santa Catarina Governor Election Winner",
    "Mato Grosso do Sul Governor Election Winner",
]


@pytest.mark.parametrize("name", SHOPPED_FOREIGN)
def test_the_five_shopped_cards_leave_the_gubernatorial_section(name):
    assert theme(name) == "international", (
        f"{name!r} is still filed as a US governor race"
    )


@pytest.mark.parametrize(
    "name",
    [
        # Russia — none of these say "Russia", which is not even in the
        # international pattern.
        "Bryansk Oblast Gubernatorial Election Winner",
        "Penza Oblast Gubernatorial Election Winner",
        "Chechnya Gubernatorial Election Winner",
        "Mordovia Gubernatorial Election Winner",
        "Tuva Gubernatorial Election Winner",
        # Brazil — including the connector places that set the four-word cap.
        "Rio Grande do Norte Governor winner?",
        "Rio de Janeiro Governor winner?",
        "Minas Gerais Governor winner?",
        "Ceará gubernatorial election winner?",
        "Federal District Governor Election Winner",
        # Mexico.
        "Nuevo León Governor Election Winner",
        "Quintana Roo Governor Election Winner",
        "Baja California Sur Governor Election Winner",
        # Slovakia and Japan.
        "Banská Bystrica Region Governor Election Winner",
        "Žilina Region Governor Election Winner",
        "Fukushima Governor Election Winner",
    ],
)
def test_foreign_subdivision_races_are_international(name):
    assert theme(name) == "international"


# --------------------------------------------------------------------------
# The other direction — every shape of US governor market stays put
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Idaho Governor Election Winner",
        "Illinois Governor Election Winner",
        "Pennsylvania Governor Election Winner",
        "Colorado Governor Election Winner",
        "Alaska Governor winner?",
        # Multi-word states, and the three- and four-word territories that the
        # place cap has to clear.
        "New Hampshire Governor Election Winner",
        "Rhode Island Governor Election Winner",
        "West Virginia Governor Election Winner",
        # All five territories that elect a governor — mutation found the arm
        # passing with Guam and American Samoa dropped from the allowlist.
        "Puerto Rico Governor Election Winner",
        "Northern Mariana Islands Governor Election Winner",
        "U.S. Virgin Islands Governor Election Winner",
        "Guam Governor Election Winner",
        "American Samoa Governor Election Winner",
    ],
)
def test_us_governor_races_stay_gubernatorial(name):
    assert theme(name) == "gubernatorial"


@pytest.mark.parametrize(
    "state",
    [
        "Alabama", "Arkansas", "California", "Georgia", "Idaho",
        "Nevada", "Oklahoma", "Rhode Island", "Texas", "Vermont",
    ],
)
def test_us_lieutenant_governor_races_stay(state):
    """The arm that was red in the first draft. See the module docstring."""
    assert theme(f"{state} Lieutenant Governor winner?") == "gubernatorial"
    assert theme(f"{state} Lieutenant Governor Election Winner") == "gubernatorial"


def test_new_mexico_is_a_state_not_a_country():
    """A corollary the replay surfaced: `\\bmexico\\b` matches inside "New
    Mexico", so both New Mexico governor markets were filed INTERNATIONAL on
    production before this change."""
    assert theme("New Mexico Governor Election Winner") == "gubernatorial"
    assert theme("New Mexico Governor winner?") == "gubernatorial"


@pytest.mark.parametrize(
    "name",
    [
        # Not the place-led race shape, so the rule says nothing and the
        # ordinary patterns keep deciding. All of these are US markets.
        "Massachusetts Governor margin of victory",
        "Wisconsin Governor Election: Turnout",
        "Nevada Governor election: Joe Lombardo vote percent",
        "Kentucky Governor Election Winner (2027)",
        "Alaska Governor winner? (Party)",
        "New York Governor Election: Nassau County Winner",
        "Closest Governor race in 2026?",
        "Will Democrats sweep all swing state Governor races?",
    ],
)
def test_unshaped_us_governor_titles_are_untouched(name):
    assert theme(name) == "gubernatorial"


@pytest.mark.parametrize(
    ("name", "unchanged_theme"),
    [
        # `nominee` (presidential) is matched before `governor`, so this Texas
        # race has never been in the Gubernatorial section.
        ("Texas Democratic Governor nominee?", "presidential"),
        # Both keywords here are plural — `\bgovernor\b` does not match
        # "governorships" and `\bmidterm\b` does not match "midterms" — so
        # nothing claims it.
        ("Who will hold more governorships after the midterms?", "other"),
    ],
)
def test_titles_this_rule_says_nothing_about_keep_their_prior_theme(name, unchanged_theme):
    """Verified against unpatched master, not asserted from reading the code.

    These two are NOT gubernatorial today and this change does not make them
    so; they are pinned because they are the near neighbours a later edit
    would most plausibly sweep up. The gaps they expose — `nominee` outranking
    `governor`, and both keyword lists being blind to the plural — are real
    and are deliberately NOT fixed here: neither is reader-visible on the
    shopped section, and widening the patterns is a different claim needing
    its own measurement.
    """
    assert theme(name) == unchanged_theme


def test_a_sentence_ending_in_the_race_title_is_not_a_place():
    """`.+?` would swallow a whole clause and find no US state in it, calling a
    US market international. The word cap and the capitalisation guard are
    what stop that, so this must never be `international`."""
    assert theme("Will Trump endorse the Ohio Governor Election Winner") != "international"
    assert theme("who wins the santa catarina governor election winner") != "international"


def test_each_place_guard_is_independently_load_bearing():
    """Both guards survived mutation against the test above, because either
    one alone refuses those two titles. These pin them APART:

    * a long but title-cased clause — the capitalisation guard is happy with
      every word, so only the four-word cap refuses it;
    * a short but lower-cased one — three words is inside the cap, so only the
      capitalisation guard refuses it.

    Delete either guard and exactly one of these two lines goes red.
    """
    assert theme("Will Trump Endorse The Ohio Governor Election Winner") != "international"
    assert theme("who wins the governor election winner") != "international"


def test_the_kalshi_ticker_map_still_wins_first():
    """`_THEME_BY_TICKER` runs before the new gate and is deliberately
    unchanged — pinned so a later edit cannot quietly reorder them."""
    assert theme("Belgorod Oblast Gubernatorial Election Winner", "KXGOVRU-26") == "gubernatorial"


# --------------------------------------------------------------------------
# Claim 2 — a Federal Reserve governor is not a state governor
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Lisa Cook out as Fed Governor by September 30?",
        "Lisa Cook officially out as Fed Governor by...?",
        "Jerome Powell departure as Fed Governor announced?",
        "Who will be nominated as a Fed Governor in 2026?",
        "Who will be the next Federal Reserve Governor?",
    ],
)
def test_fed_governor_is_policy_not_gubernatorial(name):
    assert theme(name) == "policy"


def test_the_fed_rule_does_not_reach_a_state_governor():
    assert theme("Ohio Governor margin of victory") == "gubernatorial"
    assert theme("Federal District Governor Election Winner") == "international"
