"""#2167 — `/hub/esports` stops calling 104 props "MATCHES".

The tennis half of this issue shipped `_PROP_CLASSIFIERS` as the route OUT of the
"matches" section. Esports sat in `_INDIVIDUAL_MATCH_SPORTS` (the table that puts
`game_prop`s IN) and was absent from `_PROP_CLASSIFIERS`, with no
`prop_classifier_domain` on its `HubConfig` — so the split never ran and the hub
printed **MATCHES · 104** over 104 rows of which zero were matches.

## What this file asserts, and why it is shaped this way

Three things, because the defect could return through any of them independently:

1. the classifier calls each production prop family a prop;
2. the classifier calls a real match a MATCH — the negative control, and the
   reason this file is not just a list of `assert classify(...) is not None`. A
   classifier that answers "prop" to everything passes every assertion in (1)
   while emptying the matches rail entirely, which is a worse bug than the one
   being fixed;
3. the WIRING — the classifier is registered under the key the esports
   `HubConfig` actually declares. (1) and (2) pass on an unregistered function:
   importing a module is not the same as the route reaching it.

## Where the corpus comes from

Both lists are verbatim production names read on 2026-09-16, not invented:
the props from `GET /api/hub/esports`'s stranded `matches` section (all 104
classified, the sample below covers all six families), the controls from
`futures_markets` where `llm_sport_category = 'esports'` and the name carries
" vs ". They are frozen on purpose — a corpus refreshed from a fixed tree stops
being evidence of anything (notice 50).
"""

import pytest

from app.routes.hub import HUB_CONFIGS, _PROP_CLASSIFIERS
from app.utils.event_esports import classify_esports_prop

# Verbatim from the stranded section, with the prop kind each must be called.
PRODUCTION_PROPS: tuple[tuple[str, str], ...] = (
    ("Will BBL Esports be a 2027 VCT EMEA partner team?", "partner team"),
    ("Will 100 Thieves be a 2027 VCT Americas partner team?", "partner team"),
    ("Will Any Questions be a 2027 VCT CN partner team?", "partner team"),
    ("Will FlyQuest make a roster change by December?", "roster move"),
    ("Will Shenzhen NINJAS IN PYJAMAS make a roster change by December?", "roster move"),
    ("Will invy leave Paper Rex in 2026?", "roster move"),
    ("Will kiNgg leave LEVIATÁN in 2026?", "roster move"),
    ("Will Morgan Penta in LCS Split 3 2026?", "player prop"),
    ("Will Hans Sama Penta in LEC Summer Split 2026?", "player prop"),
    ("Will Jynxzi reach Gold rank in League of Legends by October 2, 2026?", "player prop"),
    ("Map 2 Total Rounds: Over/Under 20.5", "series prop"),
    ("Map 1 Total Rounds: Over/Under 21.5", "series prop"),
    ("Game 5: Odd/Even Total Kills?", "series prop"),
    ("Game 3: Both Teams Destroy Inhibitors?", "series prop"),
    ("Game 4: Both Teams Slay Baron Nashor?", "series prop"),
    ("Games Total: O/U 2.5", "series prop"),
    ("Will Cal Raleigh be on the cover of MLB The Show 27?", "cover"),
    ("Will Shohei Ohtani be on the cover of MLB The Show 27?", "cover"),
    ("Will Natus Vincere Make the LEC 2026 Summer Grand Final?", "season outcome"),
    ("Will LYON Qualify for Worlds 2026?", "season outcome"),
)

# Verbatim real matches. NONE of these may be called a prop.
PRODUCTION_MATCHES: tuple[str, ...] = (
    "Counter-Strike: Grêmio Esports vs Santos United (BO3) - CCT South America Challengers #3 Playoffs",
    "Counter-Strike: Nemiga vs Team Nemesis (BO5) - CIS LAN Championship Playoffs",
    "Counter-Strike: aimclub vs INFURITY Gaming (BO3) - Tipsport Cup Open #2 Group A",
    "Counter-Strike: Nemiga vs Team Nemesis - Map 3 Winner",
    "Dota 2: 1win vs Team Nemesis (BO3) - PGL Wallachia Group Stage",
    "Dota 2: 1win vs Team Nemesis - Game 2 Winner",
    "Dota 2: Natus Vincere vs Hokori (BO3) - PGL Wallachia Group Stage",
    "Valorant: FENNEL Female vs Team Falcons VEGA (BO3) - VCT Game Changers Pacific Playoffs",
    "Valorant: FULL SENSE SISU vs wiwiwi - Map 1 Winner",
    # These two LEAD with the map slot exactly like a series prop and still name a
    # real fixture. They are held out by the required `Total|Odd/Even|Both Teams`
    # token, NOT by the `^` anchor — mutation says deleting the anchor keeps this
    # file green, so the anchor is unwitnessed and the token is what does the work.
    "Map 3 Rounds Handicap: MEIA NOITE (-3.5) vs Los Niños (+3.5)",
    "Map Handicap: NEMI (-1.5) vs Team Nemesis (+1.5)",
)


@pytest.mark.parametrize("name,expected", PRODUCTION_PROPS)
def test_a_production_prop_is_called_a_prop(name: str, expected: str) -> None:
    assert classify_esports_prop(None, name) == expected


@pytest.mark.parametrize("name", PRODUCTION_MATCHES)
def test_a_production_match_is_still_a_match(name: str) -> None:
    """The negative control. A classifier that fails here empties the rail."""
    assert classify_esports_prop(None, name) is None


def test_the_hub_actually_reaches_this_classifier() -> None:
    """The wiring, which the two suites above cannot see.

    Both would pass with the module imported by nobody. The defect was never the
    predicate — it was that esports named no domain, so the split was skipped.
    """
    domain = HUB_CONFIGS["esports"].prop_classifier_domain
    assert domain == "esports", "esports HubConfig must declare its prop domain"
    assert _PROP_CLASSIFIERS.get(domain) is classify_esports_prop


def test_tennis_is_untouched() -> None:
    """The domain this issue already fixed must keep its own classifier."""
    assert HUB_CONFIGS["tennis"].prop_classifier_domain == "tennis"
    assert _PROP_CLASSIFIERS["tennis"] is not classify_esports_prop


def test_golf_is_not_swept_in() -> None:
    """Golf never had this defect — it is not an individual-match sport here.

    Named because the obvious over-reach when fixing a sectioning bug is to give
    every hub a classifier.
    """
    cfg = HUB_CONFIGS.get("golf")
    if cfg is not None:
        assert cfg.prop_classifier_domain != "esports"


def test_an_unknown_name_is_not_guessed_at() -> None:
    """No pattern fires on a name carrying none of the six families."""
    assert classify_esports_prop(None, "League of Legends: T1 vs Gen.G (BO5) - Worlds Final") is None
    assert classify_esports_prop(None, "") is None
    assert classify_esports_prop(None, None) is None
