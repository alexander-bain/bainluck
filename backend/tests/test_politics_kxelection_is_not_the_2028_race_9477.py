"""#9477 residual — the `kxelection` ticker prefix stops filing an administration
question and a bill under the 2028 presidential race.

THE READER'S VIEW this protects: #9477 took the Trump-administration questions
out of the Related Markets under "2028 Democratic presidential nominee" on
/politics by deleting the candidate-NAME line. But `_classify_theme` reads the
ticker tables BEFORE any name line, and `("kxelection", "presidential")` sat in
`_THEME_BY_TICKER`. So two administration-shaped questions kept the presidential
theme through the ticker alone and would be the next Related Markets on the 2028
board: "Will Trump declare an election emergency?" and "Will the SAVE America Act
become law?".

THE MEASUREMENT (production, 2026-09-28): every `futures_markets` row whose
`external_id` starts `KXELECTION`, any status, is one of those two, both open and
both `llm_sport_category = 'politics'`. So the LIKE arm fetched nothing the
category arm does not, and the label was wrong on 2 of 2. The prefix is deleted;
the name lines decide (`trump` → policy, `become law` → policy).

WHAT WOULD MAKE THIS FILE VACUOUS: a table with no ticker prefixes passes the
"not presidential" tests. `test_the_old_table_filed_them_presidential` re-runs the
specimens against the retired entry and requires the old answer, and
`test_real_presidential_questions_keep_their_theme` is the control that fails on a
fix that breaks the presidential name line instead.
"""

from types import SimpleNamespace

import pytest

from app.routes import politics as politics_route
from app.routes.politics import (
    _THEME_BY_TICKER,
    _THEME_BY_TICKER_CLASSIFY_ONLY,
    _classify_theme,
)

# The only two KXELECTION series ever stored (production, 2026-09-28).
_SPECIMENS = [
    ("KXELECTIONEMERGENCY", "Will Trump declare an election emergency?"),
    ("KXELECTIONBILL", "Will the SAVE America Act become law?"),
]


def _market(external_id: str, name: str):
    return SimpleNamespace(external_id=external_id, name=name)


@pytest.mark.parametrize("external_id, name", _SPECIMENS)
def test_the_specimens_file_under_policy(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "policy", (
        f"{name!r} is not a 2028 race question; filed presidential it becomes a "
        "Related Market under the 2028 nominee board (#9477)"
    )


@pytest.mark.parametrize("external_id, _name", _SPECIMENS)
def test_no_ticker_table_decides_the_specimens(external_id, _name):
    """The theme must come from the NAME: no ticker prefix may claim these."""
    ext = external_id.lower()
    for prefix, theme in (*_THEME_BY_TICKER, *_THEME_BY_TICKER_CLASSIFY_ONLY):
        assert not ext.startswith(prefix), (prefix, theme)


@pytest.mark.parametrize("external_id, name", _SPECIMENS)
def test_the_old_table_filed_them_presidential(monkeypatch, external_id, name):
    """Strawman: restoring the retired entry puts both back in the race."""
    monkeypatch.setattr(
        politics_route,
        "_THEME_BY_TICKER",
        [("kxelection", "presidential"), *_THEME_BY_TICKER],
    )
    assert politics_route._classify_theme(_market(external_id, name)) == "presidential"


@pytest.mark.parametrize("external_id, name", [
    ("KXPRESNOMD-28", "2028 Democratic presidential nominee"),
    ("KXPRESPERSON-28", "Who will win the 2028 presidential election?"),
    ("KXTHIRDTERM-28", "Will Trump run for a third term?"),
    ("POLY-2028-ELECTION", "Which party will win the 2028 election?"),
])
def test_real_presidential_questions_keep_their_theme(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "presidential"
