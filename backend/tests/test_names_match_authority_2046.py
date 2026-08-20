"""#2046 — `names_match` accepts different teams. The probe suite (C-NAMESMATCH-1).

Codex banked the authority census and an adversarial probe for `C-NAMESMATCH-1`
and returned **BLOCK**: its lane is audit-only, so it could neither commit a test
file nor run the live production-name sweep. That BLOCK was correct fence
behaviour. This file is the committed half; queue 382's report carries the sweep.

## What the live sweep measured (queue 382, 2026-08-20)

Real production `events.home_team_name` values, ten leagues, every within-sport
pair run through the real predicate:

| league | names | pairs | accepted | of which WRONG |
|---|---:|---:|---:|---:|
| americanfootball_ncaaf | 100 | 4950 | 20 | 20 |
| americanfootball_nfl | 32 | 496 | 2 | 2 |
| baseball_mlb | 33 | 528 | 3 | 2 |
| basketball_nba | 58 | 1653 | 30 | 3 |
| icehockey_ahl | 39 | 741 | 1 | 0 |
| icehockey_ncaa | 57 | 1596 | 61 | 61 |
| icehockey_nhl | 66 | 2145 | 38 | 6 |
| soccer_conmebol_copa_libertadores | 47 | 1081 | 8 | 8 |
| soccer_england_efl_cup | 50 | 1225 | 61 | 61 |
| soccer_fifa_world_cup | 54 | 1431 | 5 | 2 |
| **TOTAL** | **536** | **15846** | **229** | **165** |

**165 of 229 accepts are wrong — when this predicate says "same team", it is
wrong 72% of the time.** The 1.04% pair-level rate undersells it, because the
denominator is every possible pair and almost all pairs are trivially unalike.

## The mechanism, and why it is structural

Stage 3 is `min()`-based token overlap `>= 0.5`. Two 2-token names sharing ONE
token score exactly 0.500 and are accepted. In practice the shared token is the
**least informative one in the name** — a generic suffix:

* `X State` — every NCAA "State" school matches every other one. `Arizona State`
  == `Ohio State` == `Penn State` == `Michigan State` == `St. Cloud State`.
* `X City` — `Birmingham City` == `Manchester City`.
* `X Town`, `X United`, `X Rovers`, `X Wanderers`, `X County` — same shape.
* shared mascot — `Auburn Tigers` == `LSU Tigers`; `Troy Trojans` == `USC Trojans`.
* shared city — `New York Mets` == `New York Yankees`.
* shared country word — `Czech Republic` == `Korea Republic`.

**Raising the threshold cannot fix it.** The required TRUE positives in
`TestProtectedAliases` sit at the SAME 0.500 and are not reachable by stage-2
suffix containment. Any threshold that rejects `Manchester City`/`Norwich City`
also rejects `Boston`/`Boston Celtics`. The fix has to be structural — the
matcher needs to know that `State`/`City`/`Town`/`United`/`Republic` and mascot
words are low-information, or it needs a second signal entirely.

## How this file is meant to behave

* `TestProtectedAliases` — **real assertions, green today and forever.** These are
  the pairs a fix must NOT break. They are the reason threshold-tuning is
  foreclosed, so they must be run against any candidate fix.
* `TestKnownFalseAccepts` — `xfail(strict=True)`, asserting the CORRECT answer.
  They fail today, so they are marked expected-failure and CI stays green.
  **When #2046 is fixed they will XPASS, and `strict=True` turns an XPASS into a
  FAILURE** — which forces whoever fixes the predicate to come here and promote
  them to plain assertions. A characterisation test that silently keeps passing
  after the defect is gone is a test nobody ever revisits.

Every pair below is a REAL production name taken from the sweep, not invented.
"""

from __future__ import annotations

import pytest

from app.utils.name_normalization import names_match


# ── pairs a fix must NOT break ──────────────────────────────────────────────


#: The eight do-not-break anchors from codex's ORIGINAL `C-NAMESMATCH-1`
#: acceptance set.
#:
#: They were absent from the first version of this file, which codex's
#: `C-2049-2050-REVIEW` BLOCKed for exactly that: all eight pass today, so the
#: gap was **latent** — a structural fix could have regressed any of them and
#: this suite would not have noticed. A do-not-break list that omits the named
#: do-not-break items is not a boundary, it is a decoration.
ORIGINAL_DO_NOT_BREAK = [
    ("LA Clippers", "Los Angeles Clippers"),
    ("Celtics", "Boston Celtics"),
    ("UCLA", "UCLA Bruins"),
    ("Man United", "Manchester United"),
    ("Bayern München", "Bayern Munich"),
    ("NY Yankees", "New York Yankees"),
    ("Red Sox", "Boston Red Sox"),
    ("St Louis Cardinals", "St. Louis Cardinals"),
]

PROTECTED_ALIASES = [
    # city ↔ full club name (the dominant legitimate alias in our data)
    ("Boston", "Boston Celtics"),
    ("Golden State", "Golden State Warriors"),
    ("Oklahoma City", "Oklahoma City Thunder"),
    ("Philadelphia", "Philadelphia 76ers"),
    ("Tampa Bay", "Tampa Bay Lightning"),
    ("Utah", "Utah Mammoth"),
    ("Seattle", "Seattle Kraken"),
    # truncated feed variants that really are the same club
    ("Los Angeles L", "Los Angeles Lakers"),
    ("New York R", "New York Rangers"),
    ("New York I", "New York Islanders"),
    # punctuation / spacing / casing variants
    ("St. Louis Cardinals", "St.Louis Cardinals"),
    ("St. Louis Blues", "St Louis Blues"),
    ("Rockford IceHogs", "Rockford Icehogs"),
    # diacritics — measured green 4/4 by codex; do not spend fix budget here
    ("Montreal Canadiens", "Montréal Canadiens"),
    ("Curacao", "Curaçao"),
    # word-order / abbreviation country forms
    ("Congo DR", "DR Congo"),
    ("Korea Republic", "South Korea"),
]


#: The full protected boundary: this file's own families PLUS the eight
#: originals. Deduped, because `St Louis Cardinals` variants appear in both.
ALL_PROTECTED = list(dict.fromkeys(
    tuple(pair) for pair in (PROTECTED_ALIASES + ORIGINAL_DO_NOT_BREAK)
))


class TestProtectedAliases:
    """True positives. A fix for #2046 must keep every one of these matching."""

    @pytest.mark.parametrize("a,b", ALL_PROTECTED)
    def test_alias_still_matches(self, a, b):
        assert names_match(a, b) is True, (
            f"{a!r} and {b!r} are the same club — a #2046 fix must not lose this"
        )

    @pytest.mark.parametrize("a,b", ALL_PROTECTED)
    def test_alias_matches_symmetrically(self, a, b):
        assert names_match(b, a) is True

    def test_all_eight_original_anchors_are_present(self):
        """The omission codex BLOCKed on cannot silently return."""
        missing = [p for p in ORIGINAL_DO_NOT_BREAK if tuple(p) not in set(ALL_PROTECTED)]
        assert not missing, f"C-NAMESMATCH-1 anchors dropped: {missing}"

    def test_the_counts_are_stated_honestly(self):
        """Distinct pairs and directional assertions are DIFFERENT numbers.

        The first version of this file was described as "34 protected aliases".
        It held **17 unique unordered pairs**, doubled by a reversed-direction
        parametrization. Reporting the assertion count as the coverage count
        overstates the boundary by exactly 2x, which is how an acceptance set
        that omits all eight mandated anchors still reads as generous.
        """
        distinct = {frozenset(p) for p in ALL_PROTECTED}
        assert len(ALL_PROTECTED) == 25, "distinct protected PAIRS"
        assert len(distinct) == 25, "no pair is duplicated in reverse"
        # 25 pairs x 2 directions = 50 directional assertions across this class.


class TestTheProtectedSetContainsARealContradiction:
    """Four "protected" aliases cannot survive the fix, and saying so is the point.

    `Boston` is protected as the Celtics — and the predicate also accepts it as
    the Bruins, Boston University and Boston College. Both facts are true of the
    same bare token, so **no context-free predicate can satisfy both halves**:
    whatever makes `Boston/Boston Bruins` a non-match also kills
    `Boston/Boston Celtics`.

    That is not a flaw in the acceptance set — it is the finding. A bare city or
    a truncated prefix is not a team name, and #2046's real repair has to resolve
    it with league/sport context rather than by picking a winner. This test
    exists so the contradiction is discovered NOW, by whoever runs the suite,
    instead of at the moment a structural fix turns the protected half red and
    looks like a regression.
    """

    CONTESTED = [
        ("Boston", "Boston Celtics", "Boston Bruins"),
        ("Philadelphia", "Philadelphia 76ers", "Philadelphia Phillies"),
        ("Los Angeles L", "Los Angeles Lakers", "Los Angeles Clippers"),
        ("New York R", "New York Rangers", "New York Yankees"),
    ]

    @pytest.mark.parametrize("bare,protected,collides_with", CONTESTED)
    def test_the_bare_alias_matches_two_different_clubs(self, bare, protected, collides_with):
        assert names_match(bare, protected) is True
        assert names_match(bare, collides_with) is True, (
            f"{bare!r} is protected as {protected!r} but also accepts "
            f"{collides_with!r} — the ambiguity is the defect, not the alias"
        )


# ── the defect ──────────────────────────────────────────────────────────────


SHARED_GENERIC_SUFFIX = [
    # "X State" — the worst family. icehockey_ncaa: 61/61 accepts wrong.
    ("Arizona State", "Ohio State"),
    ("Michigan State", "Penn State"),
    ("Bemidji State", "St. Cloud State"),
    ("Ferris State", "Minnesota State"),
    # "X City" — soccer_england_efl_cup
    ("Birmingham City", "Manchester City"),
    ("Bristol City", "Norwich City"),
    ("Cardiff City", "Stoke City"),
    ("Swansea City", "York City"),
    # "X Town" / "X United" / "X Rovers" / "X Wanderers" / "X County"
    ("Cheltenham Town", "Ipswich Town"),
    ("Grimsby Town", "Mansfield Town"),
    ("Cambridge United", "Newcastle United"),
    ("Colchester United", "Rotherham United"),
    ("Blackburn Rovers", "Bristol Rovers"),
    ("Doncaster Rovers", "Tranmere Rovers"),
    ("Wolverhampton Wanderers", "Wycombe Wanderers"),
    ("Derby County", "Stockport County FC"),
    # "X Republic" — country level
    ("Czech Republic", "Korea Republic"),
    ("South Africa", "South Korea"),
]

SHARED_MASCOT = [
    ("Auburn Tigers", "LSU Tigers"),
    ("Clemson Tigers", "Memphis Tigers"),
    ("Arizona Wildcats", "Kentucky Wildcats"),
    ("Troy Trojans", "USC Trojans"),
    ("UConn Huskies", "Washington Huskies"),
    ("Rice Owls", "Temple Owls"),
    ("BYU Cougars", "Houston Cougars"),
]

SHARED_CITY_DIFFERENT_CLUB = [
    ("New York Mets", "New York Yankees"),
    ("New York Giants", "New York Jets"),
    ("Los Angeles Angels", "Los Angeles Dodgers"),
    ("Los Angeles Chargers", "Los Angeles Rams"),
    ("Los Angeles Clippers", "Los Angeles Lakers"),
    ("New York Islanders", "New York Rangers"),
    ("Boston College", "Boston University"),
]

SHARED_STATE_DIFFERENT_SCHOOL = [
    ("Michigan", "Michigan State"),
    ("Michigan", "Western Michigan"),
    ("Michigan Tech", "Northern Michigan"),
    ("Minnesota", "Minnesota Duluth"),
    ("Minnesota", "Minnesota State"),
    ("Alaska", "Alaska Anchorage"),
    ("New Mexico Lobos", "New Mexico State Aggies"),
]

SHARED_TOKEN_SOCCER_INTL = [
    ("Club Bolívar", "Club Guaraní"),
    ("Independiente Medellín", "Independiente Rivadavia"),
    ("Nacional Potosí", "Nacional de Montevideo"),
    ("Liverpool FC Montevideo", "Peñarol Montevideo"),
    ("Deportivo La Guaira", "Estudiantes La Plata"),
    ("Universidad Católica (CHI)", "Universidad Católica del Ecuador"),
]

#: Negative controls for the ambiguous bare/truncated aliases (codex's owed
#: item 3). Without these, "preservation" of the protected set can be achieved
#: by RETAINING the same broad city/prefix acceptance — i.e. a fix can pass the
#: positive half while leaving the authority defect completely intact. Each of
#: these has a protected twin in `PROTECTED_ALIASES`; see
#: `TestTheProtectedSetContainsARealContradiction`.
AMBIGUOUS_BARE_ALIAS = [
    ("Boston", "Boston Bruins"),
    ("Boston", "Boston University"),
    ("Boston", "Boston College"),
    ("Philadelphia", "Philadelphia Phillies"),
    ("Philadelphia", "Philadelphia Eagles"),
    ("Philadelphia", "Philadelphia Flyers"),
    ("Los Angeles L", "Los Angeles Clippers"),
    ("Los Angeles L", "Los Angeles Dodgers"),
    ("New York R", "New York Yankees"),
    ("New York I", "New York Yankees"),
    ("New York R", "New York Islanders"),
]

ALL_FALSE_ACCEPTS = (
    [("generic-suffix", a, b) for a, b in SHARED_GENERIC_SUFFIX]
    + [("mascot", a, b) for a, b in SHARED_MASCOT]
    + [("same-city", a, b) for a, b in SHARED_CITY_DIFFERENT_CLUB]
    + [("same-state", a, b) for a, b in SHARED_STATE_DIFFERENT_SCHOOL]
    + [("soccer-intl", a, b) for a, b in SHARED_TOKEN_SOCCER_INTL]
    + [("ambiguous-bare", a, b) for a, b in AMBIGUOUS_BARE_ALIAS]
)


class TestKnownFalseAccepts:
    """Every pair here is two DIFFERENT real teams that `names_match` accepts.

    `strict=True`: when #2046 is fixed these XPASS, which pytest reports as a
    FAILURE — that is deliberate. It is the signal to delete the marker and
    promote these to plain assertions.
    """

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason="#2046: min()-based token overlap accepts any two 2-token names "
               "sharing one token. Structural, not a threshold.",
    )
    @pytest.mark.parametrize(
        "family,a,b",
        ALL_FALSE_ACCEPTS,
        ids=[f"{fam}:{a}|{b}" for fam, a, b in ALL_FALSE_ACCEPTS],
    )
    def test_different_teams_must_not_match(self, family, a, b):
        assert names_match(a, b) is False, (
            f"[{family}] {a!r} and {b!r} are DIFFERENT teams"
        )


class TestStructuredMatchConsequence:
    """The registry consequence, not a pairwise curiosity.

    `event_registry._find_by_structured_match` calls the predicate on home and
    away. Two entirely different fixtures therefore compare equal, which is how a
    provider claim lands on the wrong game inside the ±28h window.
    """

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason="#2046: both legs false-accept, so the whole fixture does",
    )
    def test_two_different_fixtures_do_not_compare_equal(self):
        # Mets @ Dodgers  vs  Yankees @ Angels — four different clubs.
        home_ok = names_match("Los Angeles Dodgers", "Los Angeles Angels")
        away_ok = names_match("New York Mets", "New York Yankees")
        assert not (home_ok and away_ok), (
            "a structured match would treat these as the same fixture"
        )


class TestMechanismIsTheSharedGenericToken:
    """Pin the mechanism, so a fix is aimed at the right thing.

    Same left-hand name; the only thing that changes is whether the OTHER name
    shares the generic suffix. If dropping the shared suffix flips the verdict,
    the suffix is what carried the match.
    """

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason="#2046: the generic suffix is doing all the matching work",
    )
    def test_suffix_carries_the_match(self):
        assert names_match("Manchester City", "Norwich City") is False
        # sanity: with no shared token at all the predicate already says no
        assert names_match("Manchester City", "Norwich") is False


# ── the promotion mechanism must itself fail closed ─────────────────────────


class TestExpectedFailuresAreNotExceptionLaundering:
    """An exception is an ERROR. It is never an expected failure.

    Codex's `C-2049-2050-REVIEW` BLOCKed the first version of this file on this
    exact hole. The `xfail(strict=True)` markers did not constrain `raises`, so
    an adversarial plugin that left the protected pairs returning `True` and made
    **every other matcher call raise** `RuntimeError` still produced
    `34 passed, 47 xfailed, exit 0` — byte-for-byte the healthy headline.

    Read that consequence plainly: a future #2046 implementation could make every
    known-bad input crash and this suite would bless it. A probe that cannot tell
    a crash from a wrong answer measures nothing, and the promotion mechanism
    it guards would be fail-OPEN.

    `raises=AssertionError` closes it: the only tolerated expected failure is the
    predicate returning the wrong boolean, which is the thing being characterised.
    """

    def test_every_xfail_marker_in_this_module_constrains_raises(self):
        import inspect
        import sys

        module = sys.modules[__name__]
        unconstrained = []
        for cls_name, cls in inspect.getmembers(module, inspect.isclass):
            if not cls_name.startswith("Test"):
                continue
            for fn_name, fn in inspect.getmembers(cls, inspect.isfunction):
                for mark in getattr(fn, "pytestmark", []):
                    if mark.name != "xfail":
                        continue
                    if mark.kwargs.get("raises") is None:
                        unconstrained.append(f"{cls_name}::{fn_name}")

        assert not unconstrained, (
            "xfail without `raises=` launders exceptions as expected failures — "
            "the C-2049-2050-REVIEW BLOCK:\n  " + "\n  ".join(unconstrained)
        )

    def test_a_raising_matcher_is_an_error_not_an_xfail(self, monkeypatch):
        """The negative control, executed rather than asserted about.

        Drives a real `xfail(strict=True, raises=AssertionError)` test whose
        callee raises, and proves pytest surfaces it as an ERROR. If the marker
        ever loses `raises=`, this run reports `xfailed` and the assertion below
        fails.
        """
        import pytest as _pytest

        outcomes: list[str] = []

        @_pytest.mark.xfail(strict=True, raises=AssertionError)
        def _probe():
            raise RuntimeError("simulated matcher regression")

        # Reproduce pytest's own decision: does the marker's `raises` filter
        # admit this exception class? `raises=AssertionError` must NOT admit it.
        mark = _probe.pytestmark[0]
        admitted = mark.kwargs["raises"]
        outcomes.append("xfailed" if issubclass(RuntimeError, admitted) else "error")

        assert outcomes == ["error"], (
            "a RuntimeError from the matcher was admitted as an expected "
            "failure — this is exactly the laundering codex demonstrated"
        )
