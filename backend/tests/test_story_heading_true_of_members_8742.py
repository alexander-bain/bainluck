"""#8742 — a bundle's heading must be true of every member it heads.

THE DEFECT, read off production Discover page one at 390px, 2026-09-25 23:23Z:

    slot 10  Washington Power — "Who holds power in Washington?"
               · Democratic nomination odds leader on October 31?
               · Who will be the next to leave the Burnham Cabinet?   (the UK's)
    slot 7   AI — "Which AI model comes out on top?"
               · Best AI at the end of 2026?
               · Will Tristan Buckmaster sue OpenAI or Bubeck?        (a lawsuit)

Two halves, two repairs:

1. `story:us_federal_power` MEMBERSHIP was the bare vocabulary `cabinet|supreme
   court|nomination|confirmed|...` with no jurisdiction and no sense. Measured by
   running `_story_key` over every open market that evening: 96 members, 41 of
   them false — celebrity pregnancies ("confirmed pregnant"), Epstein, Satoshi,
   Ebola, state supreme court seats, Brazil's Supreme Court, both Burnham
   Cabinet markets. Every name in EVICTED below is one of those 41, verbatim.
2. `story:ai`'s SENTENCE promised a model ranking over a family (318 members)
   that is mostly OpenAI-the-company, releases and token prices. The sentence is
   rewritten to one true of all of them; membership is untouched except
   "Claude Monet's artwork", which was never about a model.

The KEPT list is the half that makes this a guard rather than a deletion: the
federal questions that sit next to each narrowing and must survive it — an
ambassador named by a foreign country, a Supreme Court case naming a state, a
"confirmed as" Senate confirmation, a Trump Cabinet question.
"""

import pytest

from app.utils.discover_bundles import (
    AUTHORED_STORY_QUESTIONS,
    _story_question_promises_a_winner,
    assemble_story_theme_bundles,
)
from app.utils.feed_market_quality import _story_key

FED = "story:us_federal_power"

# Production id 61998713, verbatim (open, 2026-09-26), served in the slot-10 pair.
DEM_NOMINATION = "Democratic nomination odds leader on October 31?"

# Production id 31266896, verbatim (open, 2026-09-26).
LULA = "Will Lula announce nomination of a Supreme Court minister by...?"

# Production names (open markets, 2026-09-25), with the category they carry.
EVICTED = [
    ("Who will be the next to leave the Burnham Cabinet?", "politics"),
    ("Who will be the first to leave the Burnham Cabinet?", "politics"),
    ("Kylie Jenner confirmed pregnant in 2026?", "entertainment"),
    ("Rihanna confirmed pregnant in 2026?", "entertainment"),
    ("Madison Beer and Justin Herbert confirmed married by December 31?", "entertainment"),
    ("Adam Back confirmed to be Satoshi by December 31?", "politics"),
    ('"I beat Bush" Epstein Email Sender confirmed as ___ ?', "politics"),
    ("Ebola: new country confirmed before October 1?", "entertainment"),
    ("Ren Zhengfei confirmed outside China by October 31?", "tech"),
    ("Will a new interstellar visitor be confirmed before 2027?", "space"),
    ("Texas Supreme Court Place 8 winner?", "legal"),
    ("Washington Supreme Court Position 5 winner?", "legal"),
    ("Voter turnout in the 2026 Wisconsin Supreme Court election?", "politics"),
    ("Will Robert Jarosh be retained on the Wyoming Supreme Court?", "legal"),
    ("Illinois Republican Attorney General nominee?", "politics"),
    ("Will Alexandre de Moraes leave Brazil's Supreme Court?", "legal"),
    ("Alexandre de Moraes out as Brazil Supreme Court Justice?", "politics"),
    # CERT-3524's residue: states no country, only its office — Washington has
    # no ministers. The siblings say Brazil and left on arm 3 already.
    (LULA, "politics"),
    ("Will Lula announce the nomination of an individual for Minister of the Supreme Federal Court of Brazil by September 30?", "politics"),
    ("Will Lula announce the nomination of an individual for Minister of the Supreme Federal Court of Brazil by December 31?", "politics"),
    # Arm 5: a party's nomination is a primary, not a Washington office. The
    # three production rows the old vocabulary seated (ids 61998713, 61998708,
    # 61876970); the first is this file's own slot-10 specimen.
    (DEM_NOMINATION, "politics"),
    ("Republican nomination odds leader on October 31?", "politics"),
    ("Rubio flips Vance for GOP nomination by October 31?", "politics"),
]

KEPT = [
    ("Who will leave Trump's Cabinet next?", "politics"),
    ("How many more people leave the Trump cabinet this year?", "politics"),
    ("Will a cabinet member be impeached?", "politics"),
    ("When will the U.S. have a Cabinet-level AI official?", "politics"),
    ("Will the Supreme Court rule in favor of Trump's tariffs?", "politics"),
    ("Will US Supreme Court ban transgender girls and women from competing on female sports teams?", "legal"),
    ("When will Wesley Hunt be confirmed as U.S. Ambassador to Saudi Arabia?", "politics"),
    ("When will Nick Adams be confirmed as Ambassador of Malaysia?", "politics"),
    ("Will Heidi Overton be confirmed as FDA Commissioner by October 31?", "health"),
    ("When will Trump's Labor Secretary pick be confirmed?", "politics"),
    ("How many federal judges will be confirmed in Sep 2026?", "politics"),
    ("When will James McDonald be confirmed as SDNY U.S. attorney?", "politics"),
    ("New Supreme Court justice confirmed?", "legal"),
    ("Kash Patel out as FBI Director?", "politics"),
    ("Will the SAVE Act become law?", "politics"),
    ("Who will be the next Deputy Attorney General?", "politics"),
    # A state named AFTER the court is a Washington case, not a state office.
    ("Will the Supreme Court hear Texas's challenge to the tariffs?", "legal"),
    # The US question of the Lula row's exact shape names a justice, not a
    # minister, and must survive the arm that evicts it.
    ("Will Trump announce nomination of a Supreme Court justice by...?", "politics"),
    # A party word that is not directly before `nomination` names who acts on
    # a Washington nomination, not whose primary it is.
    ("Will Republicans block Trump's Supreme Court nomination?", "politics"),
]


@pytest.mark.parametrize("name,category", EVICTED)
def test_a_market_the_washington_heading_is_false_of_leaves_the_family(name, category):
    assert _story_key(name, category) != FED, name


@pytest.mark.parametrize("name,category", KEPT)
def test_a_washington_question_stays_in_the_family(name, category):
    assert _story_key(name, category) == FED, name


def _futures(market_id: int, name: str, category: str, score: float) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": "reason",
        "headline": name,
        "_sort_time": 0.0,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": category,
            "canonical_market_key": None,
            "discover_card": {},
        },
    }


def _bundles(items: list[dict]) -> list[dict]:
    return [i for i in assemble_story_theme_bundles(items) if i.get("type") == "bundle"]


def test_the_served_washington_pair_no_longer_folds_under_the_heading():
    """The slot-10 pair, end to end: Burnham leaves, so there is no pair to fold,
    and both markets come back as their own cards rather than disappearing."""
    items = [
        _futures(61998713, DEM_NOMINATION, "politics", 60.0),
        _futures(59693461, "Who will be the next to leave the Burnham Cabinet?", "politics", 58.0),
    ]
    out = assemble_story_theme_bundles(list(items))
    assert _bundles(out) == []
    assert {i["data"]["id"] for i in out} == {61998713, 59693461}


def test_a_real_washington_pair_still_folds():
    """Control: two members the heading is true of still make the bundle, so the
    test above is measuring the eviction and not a broken bundler."""
    items = [
        _futures(8817578, "Kash Patel out as FBI Director?", "politics", 60.0),
        _futures(108332, "Who will leave Trump's Cabinet next?", "politics", 58.0),
    ]
    bundles = _bundles(items)
    assert len(bundles) == 1
    assert bundles[0]["data"]["shared_question"] == "Who holds power in Washington?"


def test_the_ai_heading_is_true_of_the_lawsuit_it_was_served_over():
    items = [
        _futures(109596, "Best AI at the end of 2026?", "tech", 60.0),
        _futures(60608877, "Will Tristan Buckmaster sue OpenAI or Bubeck?", "tech", 58.0),
    ]
    bundles = _bundles(items)
    assert len(bundles) == 1
    assert bundles[0]["data"]["shared_question"] == "What happens next in AI?"


def test_the_ai_heading_no_longer_promises_a_winner():
    # "Which AI model comes out on top?" read as a victory question; most of
    # the family (valuations, devices, lawsuits, release dates) answers none.
    assert "on top" not in AUTHORED_STORY_QUESTIONS["story:ai"]
    assert _story_question_promises_a_winner("story:ai") is False


def test_monet_is_not_an_ai_model_but_claude_still_is():
    assert _story_key("Claude Monet's artwork break auction record this season?", "entertainment") != "story:ai"
    assert _story_key("Will Claude Opus 5.6+ debut at an output token price of at least $15 by June 30, 2027?", "tech") == "story:ai"
    assert _story_key("When will Anthropic release Claude 6?", "tech") == "story:ai"


def test_the_lula_row_is_not_bundled_under_washington_and_both_cards_survive():
    """CERT-3524's replay, end to end: the production Lula title beside a true
    Washington member folded into one "Who holds power in Washington?" bundle.
    Now there is no Washington pair, and neither card is lost."""
    items = [
        _futures(108332, "Who will leave Trump's Cabinet next?", "politics", 60.0),
        _futures(31266896, LULA, "politics", 58.0),
    ]
    out = assemble_story_theme_bundles(list(items))
    for bundle in _bundles(out):
        assert 31266896 not in bundle["data"]["member_ids"]
    assert _bundles(out) == []
    assert {i["data"]["id"] for i in out} == {108332, 31266896}


def test_a_washington_bundle_still_forms_beside_the_lula_row_without_it():
    """Non-vacuous half: with two true members present the Washington bundle does
    fold — so the test above is measuring the Lula eviction, not a bundler that
    folds nothing — and the Lula row is outside it, as its own card."""
    items = [
        _futures(8817578, "Kash Patel out as FBI Director?", "politics", 60.0),
        _futures(108332, "Who will leave Trump's Cabinet next?", "politics", 59.0),
        _futures(31266896, LULA, "politics", 58.0),
    ]
    out = assemble_story_theme_bundles(list(items))
    bundles = _bundles(out)
    assert len(bundles) == 1
    assert bundles[0]["data"]["shared_question"] == "Who holds power in Washington?"
    assert sorted(bundles[0]["data"]["member_ids"]) == [108332, 8817578]
    loose = [i for i in out if i.get("type") == "futures"]
    assert [i["data"]["id"] for i in loose] == [31266896]


def test_the_2028_race_is_no_longer_split_across_two_page_one_stories():
    """Arm 5, end to end, as served 2026-09-26 00:4xZ: the Democratic
    nomination-odds row beside a true Washington member. It no longer folds under
    "Who holds power in Washington?" and comes back as its own card; the
    Washington member, alone, is not a bundle either."""
    items = [
        _futures(61998713, DEM_NOMINATION, "politics", 60.0),
        _futures(108332, "Who will leave Trump's Cabinet next?", "politics", 58.0),
    ]
    out = assemble_story_theme_bundles(list(items))
    assert _bundles(out) == []
    assert {i["data"]["id"] for i in out} == {61998713, 108332}
