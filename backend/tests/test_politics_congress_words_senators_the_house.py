"""/politics files a question about Senators' votes or what the House will do
under Congressional, not Other.

THE READER'S VIEW (bainluck.com/politics, `/api/politics` built 2026-09-28
10:25Z): the Other section's six cards included "How many Senators will vote
for the Clarity Act?" and "Will the House pass a cap on federal student loan
interest rates?", while "Senate passes Clarity Act by...?" sat under
Congressional.

THE CAUSE: the congressional line of `_THEME_BY_NAME` read `senator` (never
the plural) and "House" only as "House of Rep…" or "House seat". Same class as
#9193's `midterms?`.

Every name below is a real open market read from production 2026-09-28, with
its real ticker, and no ticker starts with a `_THEME_BY_TICKER*` prefix, so the
theme comes from the NAME (`test_no_specimen_is_decided_by_its_ticker`).
"""

from types import SimpleNamespace

import pytest

from app.routes.politics import (
    _THEME_BY_TICKER,
    _THEME_BY_TICKER_CLASSIFY_ONLY,
    _classify_theme,
    _find_chamber_control,
)


def _market(external_id: str, name: str):
    return SimpleNamespace(external_id=external_id, name=name)


_SENATORS = [
    ("KXVOTECLARITY-26MAY16", "How many Senators will vote for the Clarity Act?"),
    ("KXSVOTECLARITY-MAY26", "Which Senators will vote for the Clarity Act?"),
    ("KXVOTELAKE-28", "Which Senators will vote for Kari Lake?"),
    ("KXLOSEREELECTIONRSEN-2026", "How many Republican senators will lose reelection in 2026?"),
]

_THE_HOUSE = [
    ("KXSTUDENTLOANCAP-26AUG", "Will the House pass a cap on federal student loan interest rates?"),
    ("KXVOTEMILLSEXPEL-26APR", "Will the House vote on a resolution to expel Cory Mills?"),
    ("KXSOTHLEAVE-26", "Mike Johnson out as Speaker of the House?"),
    ("KXLEAVEMILLS-26NOV03", "Will Cory Mills leave the House?"),
    # Was Policy on the word "bill"; the chamber decides first, as it does for
    # "Senate passes Clarity Act by...?".
    ("KXRECNCH-26", "When will the House pass a reconciliation bill?"),
]

# Controls: what the widening must NOT move.
_STILL_PRESIDENTIAL = [
    ("KXSUPERBOWLWHITEHOUSE", "Will the 2026 Pro Football champs visit the White House?"),
    ("KXWHVISIT-27", "Who will visit the White House in 2026?"),
]
_STILL_POLICY = [
    ("KXPATIENTSMONOPOLIES-27", "Will a bill curbing pharmaceutical monopolies become law?"),
    ("KXSAFEBANK-27JAN01", "Will cannabis banking insurance protections become law in 2026?"),
]


@pytest.mark.parametrize("external_id, name", _SENATORS)
def test_a_senators_question_is_congressional(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "congressional"


@pytest.mark.parametrize("external_id, name", _THE_HOUSE)
def test_a_the_house_question_is_congressional(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "congressional"


@pytest.mark.parametrize("external_id, name", _STILL_PRESIDENTIAL)
def test_the_white_house_stays_presidential(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "presidential"


@pytest.mark.parametrize("external_id, name", _STILL_POLICY)
def test_a_policy_question_naming_no_chamber_stays_policy(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "policy"


def test_no_specimen_is_decided_by_its_ticker():
    """If a future ticker prefix claimed one of these, the name-rule assertions
    above would pass for the wrong reason."""
    prefixes = [p for p, _ in (*_THEME_BY_TICKER, *_THEME_BY_TICKER_CLASSIFY_ONLY)]
    everything = _SENATORS + _THE_HOUSE + _STILL_PRESIDENTIAL + _STILL_POLICY
    claimed = [e for e, _ in everything if any(e.lower().startswith(p) for p in prefixes)]
    assert claimed == []


def _mk(id_, external_id, name, source, outcomes):
    return SimpleNamespace(
        id=id_, external_id=external_id, name=name, source=source,
        mutually_exclusive=True, status="open",
        outcomes=[SimpleNamespace(name=n, current_probability=p) for n, p in outcomes],
    )


def test_the_polymarket_house_twin_now_meets_kalshi_the_way_the_senate_twins_do():
    """The widening moves Polymarket's "Which party will win the House in 2026?"
    out of Other into the pool `_find_chamber_control` reads — the Senate twin
    (112902) has always been there. Both chambers now get the same rule:
    closest to a true complement wins. Stored 2026-09-28: Kalshi 91.65 + 8.45
    (off by 0.1), Polymarket 92.5 + 7.5 with six unpriced placeholder legs
    (off by 0.0), so the House card reads Polymarket's pair."""
    kalshi = _mk(108621, "CONTROLH-2026", "Which party will win the U.S. House?", "kalshi",
                 [("Democratic Party", 0.9165), ("Republican Party", 0.0845)])
    poly = _mk(112903, "32225", "Which party will win the House in 2026?", "polymarket",
               [("Democratic Party", 0.925), ("Republican Party", 0.075), ("Other", None),
                *[(f"Party {c}", None) for c in "ABCDEF"]])
    assert _classify_theme(poly) == "congressional"

    house = _find_chamber_control([kalshi, poly])["house"]
    assert (house["market_id"], house["dem"], house["gop"]) == (112903, 92.5, 7.5)
