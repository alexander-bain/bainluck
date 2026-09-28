"""#9477 — /politics files the sitting administration under Policy, not under the
2028 presidential race.

THE READER'S VIEW (bainluck.com/politics at 390px, 2026-09-28 22:05Z): the
Related Markets under "2028 Democratic presidential nominee" were six questions,
and only "Will Trump run for a third term?" was about 2028. The other five were
"Kennedy Center demolition announced by...?", "Who will join Trump's sovereign
wealth fund before 2027?", "Will Trump try to fire Powell as Fed Chair or
Governor?", "Will Trump's impeachments be expunged?" and "Will Trump try to fire
Kevin Warsh?".

THE CAUSE: a candidate-NAME line in `_THEME_BY_NAME`
(`trump|biden|desantis|harris|newsom|haley|ramaswamy|kennedy|rfk` → presidential)
sat second in the list. On 2026-09-28 it claimed 578 open rows (296 question
groups). Every row that was really about the race also carried a word the
presidential-WORD line reads, so the names only added wrong rows: the
administration, a building, a county, a governor's race and a cabinet post. The
line is gone; the administration lands in Policy through a `trump|rfk` line at
the bottom of the list, after every topic line has had its say.

Every name below is a real open market read from production 2026-09-28, and
`test_no_specimen_is_decided_by_its_ticker` keeps each theme coming from the NAME
(except the one ticker specimen, which is about the ticker on purpose).
"""

from types import SimpleNamespace

import pytest

from app.routes.politics import (
    _THEME_BY_NAME,
    _THEME_BY_TICKER,
    _THEME_BY_TICKER_CLASSIFY_ONLY,
    _classify_theme,
)


def _market(external_id: str, name: str):
    return SimpleNamespace(external_id=external_id, name=name)


# The five non-2028 Related Markets from the reader's screenshot, bar the
# Kennedy Center (below), plus the administration questions beside them.
_ADMINISTRATION = [
    ("KXUSFUNDHEAD-27", "Who will join Trump's sovereign wealth fund before 2027?"),
    ("KXTRYFIREPOWELL-26MAY12", "Will Trump try to fire Powell as Fed Chair or Governor?"),
    ("KXEXPUNGEIMPEACH-26JUN", "Will Trump's impeachments be expunged?"),
    ("KXTRYFIREWARSH-27JAN01", "Will Trump try to fire Kevin Warsh?"),
    ("KXTRUMPSUE-26AUG", "Who will Donald Trump sue in 2026?"),
    ("KXLAKEAMERICA-26AUGUNDO", "Will Trump reverse the Lake America renaming?"),
    ("KXDOED-29", "Will Trump abolish the Department of Education?"),
    ("KXTRUMPPARDONS-29JAN21", "Who will Trump pardon?"),
    ("286502", "RFK Jr. Out by December 31?"),
    # Curly apostrophe, as Kalshi writes it.
    ("KXTRUMPARCH-27", "Will construction begin on Trump’s triumphal arch in 2026?"),
]

# White House staff and press — the office, not the race. `white house` in the
# presidential-word line would claim the first three without the line above it.
_WHITE_HOUSE_OFFICE = [
    ("871261", "When will Trump announce a new White House Press Secretary?"),
    ("KXDJTWHDINNER-29", "Will Trump attend any White House Correspondents Dinner?"),
    ("1044905", "Trump bans more news outlets from White House by September 30?"),
    ("KXTRUMPACT-26SEP27", "How many presidential actions will Trump take this week? (9/27-10/3)"),
]

# Not a person at all, or not the person the name line meant.
_NOT_THE_CANDIDATE = [
    ("1039019", "Kennedy Center demolition announced by...?", "other"),
    ("KXKENNEDYREOPEN-28", "When will the Kennedy Center's main building reopen?", "other"),
    ("KXHARRISCOUNTYJUDGE-26", "Harris County Judge winner?", "other"),
    ("0x30f0732734e61902d81cf2", "Will Gavin Newsom be arrested before 2027?", "other"),
    ("KXKAMALAGOV-27", "Will Kamala Harris run for California Governor?", "gubernatorial"),
]

# A topic line decides before the administration line at the bottom.
_TOPIC_FIRST = [
    ("KXVETOOVERRIDE-29JAN20", "Will Congress override Trump's veto?", "congressional"),
    ("81619", "Will Republicans lose a seat in the US Senate for any state Trump won in 2024?", "congressional"),
    ("KXDJTVOSTARIFFS", "Will the Supreme Court rule in favor of Trump's tariffs?", "scotus"),
    ("KXJUDGMENT-CARROLL28", "Will SCOTUS overturn Trump's $83.3 million Carroll judgment?", "scotus"),
    ("145744", "Will Trump endorse María Corina Machado for Venezuela president in 2026?", "international"),
]

# Controls: every 2028 / presidency question the name line used to catch stays.
_STILL_PRESIDENTIAL = [
    ("KXTRUMPRUN", "Will Trump run for a third term?"),
    ("KXAMEND22-29", "Will Trump be allowed to run for a 3rd term?"),
    ("KXNEWSOMRUN-28", "When will Gavin Newsom announce his presidential candidacy?"),
    ("KXKAMALARUN-28", "When will Kamala Harris announce her presidential candidacy?"),
    ("KXDESANTISRUN-28", "Will Ron DeSantis announce a presidential run in 2026?"),
    ("KXTRUMPENDORSE28-28MAR01", "Who will Donald Trump endorse in the 2028 presidential election?"),
    ("117525", "Will Trump endorse JD Vance for president before 2027?"),
    ("73969", "Trump out as President before 2027?"),
    ("KXTRUMPAPPROVALYEAR-26DEC", "How high will Trump's approval rating get before 2027?"),
    ("30829", "Democratic Presidential Nominee 2028"),
]


@pytest.mark.parametrize("external_id, name", _ADMINISTRATION)
def test_the_administration_is_policy(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "policy"


@pytest.mark.parametrize("external_id, name", _WHITE_HOUSE_OFFICE)
def test_white_house_staff_and_press_are_policy(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "policy"


@pytest.mark.parametrize("external_id, name, theme", _NOT_THE_CANDIDATE)
def test_a_building_a_county_and_a_governor_race_are_not_presidential(external_id, name, theme):
    assert _classify_theme(_market(external_id, name)) == theme


@pytest.mark.parametrize("external_id, name, theme", _TOPIC_FIRST)
def test_a_topic_line_decides_before_the_administration_line(external_id, name, theme):
    assert _classify_theme(_market(external_id, name)) == theme


@pytest.mark.parametrize("external_id, name", _STILL_PRESIDENTIAL)
def test_the_race_stays_presidential(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "presidential"


def test_the_press_secretary_ticker_is_not_a_presidential_series():
    """`KXPRESSSEC*` starts with `kxpres` — the #9165 prefix collision."""
    m = _market("KXPRESSSECANNOUNCE-26", "When will Trump’s next Press Secretary be announced?")
    assert _classify_theme(m) == "policy"


def test_no_line_files_a_bare_candidate_name_as_presidential():
    """The class guard. A name alone cannot tell a candidacy from a news story,
    so no presidential line may match a question that is nothing but a name."""
    for name in ("Trump", "Biden", "Harris", "Kennedy", "Newsom", "DeSantis", "Ramaswamy", "Haley"):
        hits = [t for p, t in _THEME_BY_NAME if p.search(f"Will {name} do it?")]
        assert "presidential" not in hits[:1], name


def test_the_administration_line_is_last():
    """If it moved up, it would take Congress, SCOTUS and 2028 questions that
    mention Trump away from the lines that should decide them."""
    pattern, theme = _THEME_BY_NAME[-1]
    assert theme == "policy" and pattern.search("Trump")


def test_no_specimen_is_decided_by_its_ticker():
    """If a future ticker prefix claimed one of these, the name assertions above
    would pass for the wrong reason."""
    prefixes = [p for p, _ in (*_THEME_BY_TICKER, *_THEME_BY_TICKER_CLASSIFY_ONLY)]
    everything = (
        [e for e, _ in _ADMINISTRATION + _WHITE_HOUSE_OFFICE + _STILL_PRESIDENTIAL]
        + [e for e, _, _ in _NOT_THE_CANDIDATE + _TOPIC_FIRST]
    )
    claimed = [e for e in everything if any(e.lower().startswith(p) for p in prefixes)]
    assert claimed == []
