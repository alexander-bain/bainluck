"""/politics files statewide down-ballot races beside the governor races, EU and
Kyiv questions under International, and confirmations / "become law" questions
under Policy — the #9193 residuals.

THE READER'S VIEW (bainluck.com/politics, `/api/politics` built 2026-09-28
16:25Z): the Policy section's twelve cards included "Georgia Secretary of
State Election Winner", "Georgia Secretary of State winner?" and "Georgia
Attorney General winner?" — elections, not policy. The Other section's six
cards included "Will any aircraft land or take off at Kyiv Boryspil Airport by
October 31?", "What countries will hold referenda on leaving the EU?", "Which
countries will vote to leave the EU before 2030?", "Which ICE reforms will
become law in 2026?" and "When will James McDonald be confirmed as SDNY U.S.
attorney?".

THE CAUSE: three gaps in `_THEME_BY_NAME` / `_PLACE_LED_GOV_RACE_RE`:
  * the policy line's `secretary of|attorney general` arm (written for federal
    appointments) also read a statewide election's title, and the place-led
    race shape knew only governor and lieutenant governor;
  * the international line had no `eu`, `kyiv` or `zelensk…`;
  * the policy line had no `be confirmed as`, `u.s. attorney` or `become law`.

Every name below is a real open market read from production 2026-09-28, with
its real ticker, unless its comment says otherwise, and no ticker starts with a
`_THEME_BY_TICKER*` prefix, so the theme comes from the NAME
(`test_no_specimen_is_decided_by_its_ticker`).
"""

from types import SimpleNamespace

import pytest

from app.routes.politics import (
    _THEME_BY_TICKER,
    _THEME_BY_TICKER_CLASSIFY_ONLY,
    _classify_theme,
)


def _market(external_id: str, name: str):
    return SimpleNamespace(external_id=external_id, name=name)


# The three served in Policy, plus the Kalshi/Polymarket title variants and
# New Mexico's pair (filed under International on the word "Mexico").
_STATE_RACES = [
    ("965509", "Georgia Secretary of State Election Winner"),
    ("KXSECSTATEGA-26", "Georgia Secretary of State winner?"),
    ("KXATTYGENGA-26", "Georgia Attorney General winner?"),
    ("965463", "Georgia Attorney General Election Winner"),
    ("KXCAATTORNEYGENERAL-26", "California Attorney General winner?"),
    ("KXIAAGSEC-26NOV03", "Iowa Secretary of Agriculture winner?"),
    ("KXSECSTATESC-26NOV03", "South Carolina Secretary of State winner?"),
    ("KXATTYGENNM-26", "New Mexico Attorney General winner?"),
    ("KXSECSTATENM-26NOV03", "New Mexico Secretary of State winner?"),
]

_INTERNATIONAL = [
    ("0xa27fd413954372554ffbdd40d301", "Will any aircraft land or take off at Kyiv Boryspil Airport by October 31?"),
    ("KXEUREF-30", "What countries will hold referenda on leaving the EU?"),
    ("KXEUEXITCOUNTRY-30", "Which countries will vote to leave the EU before 2030?"),
    ("KXETIASAPPLY-28", "Will the EU's ETIAS accept applications before 2028?"),
    ("KXZELENSKYYOUT", "Volodymyr Zelenskyy departure announced?"),
]

_POLICY = [
    ("KXICEREFORM", "Which ICE reforms will become law in 2026?"),
    ("KXMCDONALDCONF-26JUN17", "When will James McDonald be confirmed as SDNY U.S. attorney?"),
    ("KXCOMMISHFDA-26AUG20", "When will Heidi Overton be confirmed as Commissioner of the FDA?"),
    ("KXPIRROOUT-26AUG", "Jeanine Pirro announces departure as D.C. U.S. Attorney?"),
    ("197892", "H.R. 22 (SAVE Act) signed into law in 2026?"),
]

# Controls: what the edits must NOT move.
_STILL_POLICY = [
    # Federal appointments — the population the `secretary of|attorney general`
    # arm was written for. None is a place-led race title.
    ("KXHEGSETHOUT-26APR", "Pete Hegseth out as Secretary of Defense?"),
    ("KXNEXTDEPUTYAG-28JAN01", "Who will be the next Deputy Attorney General?"),
    ("KXSECNAVY-26SEP03", "When will Hung Cao be confirmed as Secretary of the Navy?"),
]
_STILL_GUBERNATORIAL = [
    ("KXLTGOVGA-26", "Georgia Lieutenant Governor winner?"),
    ("965553", "Georgia Lieutenant Governor Election Winner"),
    ("KXLUKEOUT-26JUL", "Sylvia Luke out as Lieutenant Governor of Hawaii?"),
]
_STILL_OTHER = [
    # "confirmed as" without "be": an Epstein curiosity, not an appointment.
    ("207661", '"I beat Bush" Epstein Email Sender confirmed as ___ ?'),
    ("KXADAMSCITIZEN", "Which countries will make Eric Adams a citizen?"),
]


@pytest.mark.parametrize("external_id, name", _STATE_RACES)
def test_a_statewide_race_sits_beside_the_governor_races(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "gubernatorial"


def test_a_foreign_place_led_attorney_general_race_is_international():
    # Synthetic: no open foreign one exists today. The place test decides
    # WHOSE office it is, exactly as it does for "São Paulo Governor…" (#7240).
    assert _classify_theme(_market("SYNTH-1", "Ontario Attorney General winner?")) == "international"


@pytest.mark.parametrize("external_id, name", _INTERNATIONAL)
def test_an_eu_or_kyiv_question_is_international(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "international"


@pytest.mark.parametrize("external_id, name", _POLICY)
def test_a_confirmation_or_become_law_question_is_policy(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "policy"


@pytest.mark.parametrize("external_id, name", _STILL_POLICY)
def test_a_federal_appointment_stays_policy(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "policy"


@pytest.mark.parametrize("external_id, name", _STILL_GUBERNATORIAL)
def test_a_lieutenant_governor_question_stays_gubernatorial(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "gubernatorial"


@pytest.mark.parametrize("external_id, name", _STILL_OTHER)
def test_an_unrelated_question_stays_other(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "other"


def test_no_specimen_is_decided_by_its_ticker():
    """If a future ticker prefix claimed one of these, the name-rule assertions
    above would pass for the wrong reason."""
    prefixes = [p for p, _ in (*_THEME_BY_TICKER, *_THEME_BY_TICKER_CLASSIFY_ONLY)]
    everything = (
        _STATE_RACES + _INTERNATIONAL + _POLICY
        + _STILL_POLICY + _STILL_GUBERNATORIAL + _STILL_OTHER
    )
    claimed = [e for e, _ in everything if any(e.lower().startswith(p) for p in prefixes)]
    assert claimed == []
