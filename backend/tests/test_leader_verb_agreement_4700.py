"""A plural team name takes a plural verb; everything else keeps the singular (#4700).

Page one served `Los Angeles Dodgers leads at 30%` in slot 1 and `Los Angeles
Rams leads at 14%` in slot 2, with `J.D. Vance leads at 23%` — correct —
between them, so the two grammars sat side by side on the morning page.

THE POINT OF THIS FILE IS THE SECOND DIRECTION. The obvious fix is "the name
ends in s, so use `lead`", and the census on #4700 shows that rule wrong in BOTH
directions on strings production served the same minute:

    Layne Riggs leads at 29%                            a person   -> singular RIGHT
    No new Director of Legislative Affairs leads at 35% an abstract -> singular RIGHT
    Miami Heat / Utah Jazz / Tampa Bay Lightning        teams       -> singular RIGHT
    Boston Red Sox                                      a team      -> plural RIGHT

So spelling is consulted only AFTER `FuturesOutcome.team_id` has proven the
subject is a team, and the tests below pin the refusals as hard as the fixes.

Class guard, not a fixture: `test_every_leads_template_agrees` drives every
template in all three generators through both a plural team and a person, so a
new branch that hard-codes "leads" again fails here rather than on the page.
"""

import pytest

from app.utils.feed_reasons import (
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
    leader_agreement_verb,
)

# ── The predicate itself ─────────────────────────────────────────────────────

#: (name, is_team, expected verb). Every row is a real subject we serve or a
#: named league team, not an invented string.
AGREEMENT_CASES = [
    # Plural team nicknames — the defect this issue was opened on.
    ("Los Angeles Dodgers", True, "lead"),
    ("Los Angeles Rams", True, "lead"),
    ("Philadelphia Waterdogs", True, "lead"),
    ("Guyana Amazon Warriors", True, "lead"),
    ("Florida Panthers", True, "lead"),
    ("Montreal Alouettes", True, "lead"),
    ("Toronto Blue Jays", True, "lead"),
    ("San Francisco 49ers", True, "lead"),
    # Plural without a trailing "s" — the orthographic rule misses these.
    ("Boston Red Sox", True, "lead"),
    ("Chicago White Sox", True, "lead"),
    # Teams whose nickname is a mass noun: American usage is SINGULAR, and they
    # are exactly the names that do not end in "s", so spelling is safe here.
    ("Miami Heat", True, "leads"),
    ("Utah Jazz", True, "leads"),
    ("Orlando Magic", True, "leads"),
    ("Minnesota Wild", True, "leads"),
    ("Tampa Bay Lightning", True, "leads"),
    ("Oklahoma City Thunder", True, "leads"),
    ("Colorado Avalanche", True, "leads"),
    # NOT teams. These must be untouched however they are spelled — the whole
    # reason the fix is gated on `team_id` rather than on the string.
    ("Layne Riggs", False, "leads"),
    ("J.D. Vance", False, "leads"),
    ("Kaden Honeycutt", False, "leads"),
    ("Chandler Smith", False, "leads"),
    ("No new Director of Legislative Affairs", False, "leads"),
    ("Anna Kelly", False, "leads"),
    ("Yes", False, "leads"),
]


@pytest.mark.parametrize("name,is_team,expected", AGREEMENT_CASES)
def test_leader_agreement_verb(name, is_team, expected):
    assert leader_agreement_verb(name, is_team) == expected


def test_a_person_whose_surname_ends_in_s_is_never_pluralised():
    """The trap, stated on its own so a regression names itself.

    `Layne Riggs` and `Los Angeles Dodgers` both end in "s". Only the team moves.
    """
    assert leader_agreement_verb("Layne Riggs", False) == "leads"
    assert leader_agreement_verb("Los Angeles Dodgers", True) == "lead"


def test_unknown_team_ness_keeps_todays_wording():
    """FAIL SINGULAR.

    `team_id` is populated on only 3 of 45 served leader outcomes, so "unknown"
    is the COMMON case — a team without a linked row (`Guyana Amazon Warriors`,
    `Florida Panthers`) must read exactly as it does today rather than become a
    guess. The default is part of the contract, so it is asserted positionally
    AND by omission.
    """
    assert leader_agreement_verb("Los Angeles Dodgers") == "leads"
    assert leader_agreement_verb("Los Angeles Dodgers", False) == "leads"
    assert leader_agreement_verb(None, True) == "leads"
    assert leader_agreement_verb("", True) == "leads"


# ── The templates, driven end to end ─────────────────────────────────────────

#: Every highlight-reason set that reaches a `leads` template, so the guard is
#: over the CLASS of leader copy rather than over one branch.
#: THESE MUST BE THE KEYS PRODUCTION EMITS. CERT-2482 blocked the first
#: presentation because this list said `resolving_soon` / `resolves_this_month`
#: — neither of which exists. Both fell through to the default branch, so the
#: "class guard" drove the two resolution templates ZERO times and missed a
#: hard-coded "leads" in the 30-day headline. A guard whose fixtures do not
#: match the production vocabulary is not a smaller guard, it is no guard: it
#: passes green while measuring nothing.
#:
#: Pinned against the source below so this cannot rot again.
LEADER_REASON_SETS = [
    [],
    ["multi_source"],
    ["leader_change"],
    ["resolving_soon_7d"],
    ["resolving_soon_30d"],
]


def _rendered(reasons, name, is_team):
    """Every reader-visible string the three generators produce for one leader."""
    common = dict(
        highlight_reasons=reasons,
        leader_name=name,
        leader_probability=0.30,
        rendered_leader_percent=30,
        leader_is_team=is_team,
        market_name="MLB World Series Winner",
    )
    headline = generate_futures_headline(**common)
    return [
        headline,
        generate_futures_reason(**common),
        generate_futures_context_summary(
            headline=headline,
            highlight_reasons=reasons,
            market_name=common["market_name"],
            leader_name=name,
            leader_probability=0.30,
            rendered_leader_percent=30,
            leader_is_team=is_team,
        ),
    ]


@pytest.mark.parametrize("reasons", LEADER_REASON_SETS)
def test_every_leads_template_agrees(reasons):
    """A plural team never gets "leads"; a person never gets "lead"."""
    for text in _rendered(reasons, "Los Angeles Dodgers", True):
        assert not _has_word(text, "leads"), f"plural team took a singular verb: {text!r}"
    for text in _rendered(reasons, "Layne Riggs", False):
        assert not _has_word(text, "lead"), f"person took a plural verb: {text!r}"


def _has_word(text: str, word: str) -> bool:
    """Whole-word match.

    It was `" leads " not in f" {text} "`, which is the SECOND way CERT-2482
    found this guard hollow: the 30-day headline ends the clause with a
    semicolon — "Los Angeles Dodgers leads; resolves within a month" — and a
    space-delimited probe sails straight past it. Word boundaries, both
    directions, so punctuation cannot hide a defect again.
    """
    import re

    return bool(re.search(rf"\b{re.escape(word)}\b", text or ""))


def test_the_reported_page_one_lines_are_repaired():
    """The two lines from the issue title, composed as production composes them."""
    dodgers = generate_futures_headline(
        highlight_reasons=[],
        leader_name="Los Angeles Dodgers",
        leader_probability=0.297506,
        rendered_leader_percent=30,
        leader_is_team=True,
        market_name="MLB World Series Winner",
    )
    assert dodgers == "Los Angeles Dodgers lead at 30%"

    rams = generate_futures_headline(
        highlight_reasons=[],
        leader_name="Los Angeles Rams",
        leader_probability=0.139929,
        rendered_leader_percent=14,
        leader_is_team=True,
        market_name="NFL Super Bowl Winner",
    )
    assert rams == "Los Angeles Rams lead at 14%"


def test_the_correct_line_between_them_is_untouched():
    """`J.D. Vance leads at 23%` sat between the two defects and read right."""
    assert generate_futures_headline(
        highlight_reasons=[],
        leader_name="J.D. Vance",
        leader_probability=0.23,
        rendered_leader_percent=23,
        leader_is_team=False,
        market_name="Republican 2028 nominee",
    ) == "J.D. Vance leads at 23%"


# ── The route wiring: the signal has to REACH the templates ──────────────────


def test_the_route_reads_team_id_from_the_leader_outcome():
    """`_leader_outcome_is_team` is what joins `team_id` to the copy.

    Without this the helper above is correct and unreachable — the #4695 shape,
    where ten read sites agreed on a vocabulary nothing emitted.
    """
    from app.routes.feed import _leader_outcome_is_team

    assert _leader_outcome_is_team([{"name": "Los Angeles Dodgers", "team_id": 861}])
    assert not _leader_outcome_is_team([{"name": "Layne Riggs", "team_id": None}])
    assert not _leader_outcome_is_team([])
    # A dict that never carried the key at all (a reduced fixture) is unknown,
    # not a team.
    assert not _leader_outcome_is_team([{"name": "Los Angeles Dodgers"}])
    # It is the LEADER that decides, not any team further down the field.
    assert not _leader_outcome_is_team(
        [{"name": "Layne Riggs", "team_id": None}, {"name": "Dodgers", "team_id": 861}]
    )


def test_an_outcome_object_without_the_attribute_is_unknown_not_a_crash():
    """ABSENCE OF CAPTURE IS NOT SILENCE, in its third form this week.

    The trace builder reads `team_id` off outcome objects, and reduced test
    fixtures (`SimpleNamespace`) do not carry it — Q480's two trace tests broke
    on exactly that. A served ORM row always has the column, so the tolerant
    read costs the real population nothing and keeps a reduced fixture meaning
    "unknown" (-> singular) rather than raising.
    """
    from types import SimpleNamespace

    from app.routes.feed import _top_outcomes_for_trace

    market = SimpleNamespace(
        outcomes=[
            SimpleNamespace(
                name="Los Angeles Dodgers",
                external_id="dodgers",
                current_probability=0.30,
                probability_change_24h=None,
                rank=1,
                rank_change_24h=None,
                opening_probability=None,
            )
        ]
    )
    outcomes_data, leader_name, _ = _top_outcomes_for_trace(market)
    assert leader_name == "Los Angeles Dodgers"
    assert outcomes_data[0]["team_id"] is None


def test_every_generator_accepts_the_signal():
    """All three generators take `leader_is_team`, so no call site is stranded."""
    import inspect

    for fn in (
        generate_futures_headline,
        generate_futures_reason,
        generate_futures_context_summary,
    ):
        params = inspect.signature(fn).parameters
        assert "leader_is_team" in params, fn.__name__
        assert params["leader_is_team"].default is False, fn.__name__


def test_the_reason_keys_this_file_drives_are_the_ones_production_emits():
    """CERT-2482's root cause, guarded.

    Reads the resolution keys straight out of `feed_reasons.py` and asserts the
    fixture list contains them. A typo'd or renamed key now fails here instead
    of silently making every parametrised case exercise the default branch.
    """
    import re
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "app" / "utils" / "feed_reasons.py"
    ).read_text()
    emitted = set(re.findall(r'"(resolving_soon_\d+d)" in reasons', source))
    assert emitted, "no resolution keys found — did the branch names change?"
    driven = {key for reasons in LEADER_REASON_SETS for key in reasons}
    assert emitted <= driven, (
        f"resolution branches never exercised by the class guard: "
        f"{sorted(emitted - driven)}"
    )


def test_the_thirty_day_headline_agrees():
    """The exact sentence CERT-2482 named: it returned "Dodgers leads; ...".""" 
    assert generate_futures_headline(
        highlight_reasons=["resolving_soon_30d"],
        leader_name="Los Angeles Dodgers",
        leader_probability=0.30,
        rendered_leader_percent=30,
        leader_is_team=True,
        market_name="MLB World Series Winner",
    ) == "Los Angeles Dodgers lead; resolves within a month"

    assert generate_futures_headline(
        highlight_reasons=["resolving_soon_30d"],
        leader_name="Layne Riggs",
        leader_probability=0.29,
        rendered_leader_percent=29,
        leader_is_team=False,
        market_name="NASCAR Truck Series Champion",
    ) == "Layne Riggs leads; resolves within a month"
