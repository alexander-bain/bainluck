"""#9477 — /politics's presidential theme is the US race, not every row that says
"president".

THE READER'S VIEW (/api/politics, rebuilt 2026-09-29 02:25Z, the first build
carrying #9479): the 2028 nominee board's Related Markets were eight rows, and
the ones not about 2028 were "Natalie Harp White House departure announced?",
"How high will Trump's approval rating get before 2027?", "How high will
Trump's approval rating go in 2026?" and "Keiko Fujimori out as President of
Peru?" (plus the two `KXELECTION*` rows PR #9506 takes).

THE CAUSE: the race line reads `president|presidential|white house|nominee`,
the approval line files `approval rating` as presidential, and the bottom line
files every `primary` there. On 2026-09-28 that put 464 open rows in the theme;
Related Markets is its eight most open questions, so any of them can surface.
Measured over the 2,330 open rows that any changed line can read: 254 leave
presidential — 149 House-seat nominees/primaries (Congressional), 46 White
House / approval / sitting-presidency rows (Policy), 44 foreign presidencies
(International), 12 other presidencies and state offices (Other), 1 SCOTUS —
and 72 foreign-politics rows move Other/Policy/Congressional → International on
the new country words. What stays presidential is the race (212 rows).

Every name below is a real open market read from production 2026-09-28/29
(ids as stored; long Polymarket condition ids shortened), except the three
marked constructed.
"""

from types import SimpleNamespace

import pytest

from app.routes.politics import (
    _INTERNATIONAL_RE,
    _THEME_BY_NAME,
    _classify_theme,
)


def _market(external_id: str, name: str):
    return SimpleNamespace(external_id=external_id, name=name)


# The four rows the reader saw on the 2028 board after #9479 went live.
_SERVED_02_25Z = [
    ("KXHARPANNOUNCEOUT-26AUG", "Natalie Harp White House departure announced?", "policy"),
    ("KXTRUMPAPPROVALYEAR-26DEC31", "How high will Trump's approval rating get before 2027?", "policy"),
    ("102722", "How high will Trump's approval rating go in 2026?", "policy"),
    ("KXFUJIMORIOUT-26JUL", "Keiko Fujimori out as President of Peru?", "international"),
]

# Each class, by the line that now takes it.
_NOT_THE_RACE = [
    # the White House is the administration
    ("KXWHVISIT-27", "Who will visit the White House in 2026?", "policy"),
    ("326588", "Susie Wiles out as White House Chief of Staff by December 31?", "policy"),
    ("1083671", "White House # posts September 29 - October 6, 2026?", "policy"),
    ("KXPRESSBRIEFINGCOUNT-26SEP", "Number of White House Press Briefings in Sep 2026?", "policy"),
    # approval is the sitting president's
    ("KXAPRPOTUS-26OCT02", "Trump's approval rating on Oct 2, 2026?", "policy"),
    ("0xd2e96e78b5a59e12b4d60d6b84", "Will Trump's approval rating hit 35% in 2026?", "policy"),
    # the sitting presidency
    ("73969", "Trump out as President before 2027?", "policy"),
    ("KXTRUMPOUT27-27", "Donald Trump announces departure as President? (Excluding death)", "policy"),
    ("KXUSMDLFRDM-27", "Who will receive the Presidential Medal of Freedom in 2026?", "policy"),
    ("887359", "Natalie Harp out as Special Assistant to the President by December 31?", "policy"),
    ("196931", "Will Trump repeal Presidential term limits in 2026?", "policy"),
    ("0x59ab95a34e1af8e44e21", 'Will Trump post "President Xi" on Truth Social this week?', "policy"),
    ("KXNEWSCOTUSCONF-29JAN20", "How many Supreme Court justices will the President confirm?", "scotus"),
    # a past race, a book
    ("KXBIDENAMBIEN-28", "Will it be reported that Joe Biden used Ambien before the 2024 presidential debate?", "other"),
    ("KXBIDENBOOK-26JUN10", "When will Biden release his presidential memoir?", "other"),
    # someone else's president
    ("KXFIFALEAVE-27JAN01", "Gianni Infantino out as President of FIFA in 2026", "other"),
    ("KXLUCASFILM-27", "Who will be the next President of Lucasfilm before 2027?", "other"),
    ("KXNEXTATLFED-30JAN01", "Who will be the next President of the Federal Reserve Bank of Atlanta?", "other"),
    ("KXFAINOUT-26JUL", "Shawn Fain announces departure as UAW President?", "other"),
    ("KXRMALEAVE-27JAN01", "Real Madrid: Florentino Pérez Out as President", "other"),
    ("KXCPSBOARDPRES-26NOV03", "Chicago Board of Education President winner?", "other"),
    ("KXNAVAJOPRES-26NOV03", "Navajo Nation presidential election winner?", "other"),
    # a foreign presidency, by name or under a KXPRES ticker
    ("84590", "Miguel Díaz-Canel out as President of Cuba by...?", "international"),
    ("103614", "Tshisekedi out as President of the DRC by December 31, 2026?", "international"),
    ("KXESTPRES-27JAN01", "Next President of Estonia?", "international"),
    ("KXSERBIAPRES-26DEC27", "Next Serbian presidential election winner?", "international"),
    ("KXPHILIPPINESPRES-28", "Philippine presidential election winner?", "international"),
    ("145968", "Mahmoud Abbas out as Palestinian President by...?", "international"),
    ("226397", "Christine Lagarde out as ECB president in 2026?", "international"),
    ("KXSAXANHMP-26OCT06", "Next Minister-President of Saxony-Anhalt?", "international"),
    ("KXPRESTAIWAN-28", "Taiwan presidential election winner?", "international"),
    ("KXPRESTURKEYR1-28", "Turkish presidential election: first round winner?", "international"),
    ("KXPRESNIGERIA-27", "Nigerian presidential election winner?", "international"),
    # a House seat's nominee or primary
    ("KXTXPRIMARY-38D26", "TX-38 Democratic nominee?", "congressional"),
    ("KXMOVNJ11SPECIALD-26FEB", "Margin of victory in the NJ-11 special Democratic primary?", "congressional"),
    ("KXCA22PRIMARY-26", "Who will advance from the CA-22 primary?", "congressional"),
    ("133792", "How many Democratic House Incumbents will not win their Primary?", "congressional"),
    ("KXTRUMPPRIMARYCOMBO-27", "Trump-endorsed May primary candidates combo", "congressional"),
    # a state office
    ("KXCOMPTROLLERNOMILD-26", "Illinois Democratic Comptroller nominee?", "other"),
    ("KXAGNOMILR-26", "Illinois Republican Attorney General nominee?", "other"),
    ("KXCAINSCOM-26", "California Insurance Commissioner primary: who will advance?", "other"),
    # a ballot measure that says "primary"
    ("1028998", "Massachusetts passes jungle primary ballot measure?", "policy"),
    ("KXSTATEBALLOTMEASURE-WY", "Will Wyoming vote to exempt 50% of primary-home assessed value?", "policy"),
]

# Controls: the race stays, including every phrasing near a changed line.
_THE_RACE = [
    ("KXPRESNOMD-28", "2028 Democratic presidential nominee"),
    ("KXPRESPERSON-28", "2028 U.S. Presidential Election winner?"),
    ("KXPRESPARTY-2032", "Which party will win the 2032 Presidential Election?"),
    ("KXTRUMPRUN", "Will Trump run for a third term?"),
    ("0x888f977a11c21cce076c", "Will Mark Cuban announce a Presidential run before 2027?"),
    ("378769", "Democratic VP Nominee 2028"),
    ("KXDPRESPRIMARY-28SC", "2028 South Carolina Democratic primary winner?"),
    ("KXNHPRIMARY28-28", "Will New Hampshire schedule its 2028 presidential primary before South Carolina?"),
    ("POPVOTEMOV-28NOV07", "2028 popular vote margin of victory?"),
    ("ECMOV-28NOV07", "2028 Electoral College margin of victory?"),
    ("KXPERSONPRESFUENTES-45", "Will Nick Fuentes become President of the United States before 2045?"),
    ("KXPRESPRIOROFFICE-29FEB01", "Prior offices of the President inaugurated in 2029?"),
    # The two phrasings of the race that name the White House — not open on
    # 2026-09-28; #8038's own specimens, kept here beside the line they bind.
    ("POLY-WH-1", "Will Trump win the White House in 2028?"),
    ("POLY-WH-2", "Who will be the next occupant of the White House?"),
]

# Controls: rows the new lines must NOT move out of their current section.
_UNMOVED = [
    ("191680", "WA-09 House Election Winner", "other"),
    ("KXMIDTERMMOV-WI08R", "Wisconsin's 8th District margin of victory", "other"),
    ("KXTERMLIMITS-29", "Will Trump impose term limits on Congress?", "congressional"),
    ("886932", "Alaska passes ballot measure repealing ranked choice voting?", "other"),
    # constructed: a governor's primary decides at the governor line, before
    # the primary fallback
    ("GA-GOV-PRIMARY", "Georgia Governor Republican primary winner?", "gubernatorial"),
]


@pytest.mark.parametrize("external_id, name, theme", _SERVED_02_25Z)
def test_the_rows_served_on_the_2028_board_leave_it(external_id, name, theme):
    assert _classify_theme(_market(external_id, name)) == theme


@pytest.mark.parametrize("external_id, name, theme", _NOT_THE_RACE)
def test_a_row_that_is_not_the_us_race_is_not_presidential(external_id, name, theme):
    assert _classify_theme(_market(external_id, name)) == theme


@pytest.mark.parametrize("external_id, name", _THE_RACE)
def test_the_race_stays_presidential(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "presidential"


@pytest.mark.parametrize("external_id, name, theme", _UNMOVED)
def test_a_neighbouring_row_keeps_its_section(external_id, name, theme):
    assert _classify_theme(_market(external_id, name)) == theme


def _district_line():
    (pat,) = [p for p, t in _THEME_BY_NAME if t == "congressional" and "A[KLRZ]" in p.pattern]
    return pat


def test_the_district_line_reads_a_real_state_code_in_capitals():
    pat = _district_line()
    assert pat.search("TX-38 Democratic nominee?")
    assert pat.search("WY-AL Republican primary winner?")
    # a lower-case code, a non-state pair, and a code without nominee/primary
    assert not pat.search("tx-38 democratic nominee?")
    assert not pat.search("Will the XX-12 nominee be named?")
    assert not pat.search("Will the COVID-19 nominee be confirmed?")  # "CO-" needs the dash next
    assert not pat.search("WA-09 House Election Winner")


def test_the_kxpres_check_reads_the_country_line_by_name():
    """`_classify_theme` answers a foreign `KXPRES*` row through
    `_INTERNATIONAL_RE`; it must be the list's first, International line so a
    foreign presidency also never reaches the race by name."""
    pat, theme = _THEME_BY_NAME[0]
    assert pat is _INTERNATIONAL_RE
    assert theme == "international"
