"""#8689 — a fragment search term matches at the START of a word, not anywhere.

`us open` on production (2026-09-25 19:12Z) served, in its ten futures rows,
Chengdu/Korea doubles (via "Ven*us*", "R*us*e"), both Australian Open winner
markets (via "*Aus*tralian"), a CS:GO match (via "Aimha*us*") and a transit story
(via "p*us*h"), with the two real 2027 US Open markets at slots 6 and 8.

`us` has no extractable trigram, so `_futures_name_match_term` treats it as a
fragment and never word-votes it (LAT-P037). It used to keep a bare substring
ILIKE; it now keeps the ILIKE AND a word-start regex (`_build_word_start_ilike`,
the team arm's rule since #7381). The prefix-typing case LAT-P037 protects is a
word start, so `re` still reaches "Recession".

These run against the compiled predicate and the rule's own regex — no Postgres.
`tests/integration/test_search_recall_contract.py::
test_a_fragment_term_matches_a_word_start_not_an_infix` is the real-database twin.
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models import FuturesMarket
from app.routes import events as events_route


def _predicate(term: str, expansion: str | None = None):
    return events_route._futures_name_match_term(term, expansion)


def _sql(term: str, expansion: str | None = None) -> str:
    return str(
        select(FuturesMarket.id)
        .where(_predicate(term, expansion))
        .compile(dialect=postgresql.dialect())
    )


def _regexes(term: str, expansion: str | None = None) -> list[str]:
    """The `~*` patterns the predicate binds, exactly as Postgres receives them."""
    compiled = (
        select(FuturesMarket.id)
        .where(_predicate(term, expansion))
        .compile(dialect=postgresql.dialect())
    )
    return [v for v in compiled.params.values() if isinstance(v, str) and "[:alnum:]" in v]


def _matches(term: str, name: str, expansion: str | None = None) -> bool:
    """Evaluate the predicate over one name the way Postgres would.

    ILIKE half: case-insensitive substring. Regex half: `[^[:alnum:]]` is "not a
    letter or digit" — Python's `[\\W_]` — under `~*` (case-insensitive).
    """
    def _one(t: str, pattern: str) -> bool:
        py = pattern.replace("[^[:alnum:]]", r"[\W_]")
        return t.lower() in name.lower() and re.search(py, name, re.I) is not None

    patterns = _regexes(term, expansion)
    candidates = [term] + ([expansion] if expansion else [])
    assert len(patterns) == len(candidates), patterns
    return any(_one(t, p) for t, p in zip(candidates, patterns))


# The production specimen: every one of these was on `us open`'s served ten.
_INFIX_COLLISIONS = [
    "Chengdu Open (Doubles): Peers/Venus vs Johnson/Zielinski",
    "Korea Open (Doubles): Lee/Ye vs Joint/Ruse",
    "Australian Open Men's Singles Winner",
    "Counter-Strike: ENCE vs Aimhaus (BO1) - Urban Riga Open #7 Group B",
    "Will HART push back Skyline's 2031 opening date?",
]
_ANSWERS = [
    "2027 US Open Men's Singles Winner",
    "2027 US Open Women's Singles Winner",
    "Number of Honey Deuces sold at the US Open",
    "US Open Winner",
]


class TestTheFragmentArmIsWordStart:
    def test_the_fragment_arm_carries_a_word_start_regex(self):
        sql = _sql("us")
        assert "ILIKE" in sql, "the fragment lost its trigram-servable ILIKE half"
        assert "~*" in sql, (
            "a fragment term is a bare substring again: `us` matches inside "
            "'Venus', 'Ruse', 'Australian', 'Aimhaus' and 'push' (#8689)"
        )

    def test_the_fragment_still_never_word_votes(self):
        """LAT-P037's boundary is unchanged: no `to_tsvector` below it."""
        sql = _sql("re")
        assert "to_tsvector" not in sql and "numnode" not in sql

    @pytest.mark.parametrize("name", _INFIX_COLLISIONS)
    def test_us_does_not_match_inside_a_word(self, name):
        assert not _matches("us", name), f"`us` matched an infix in {name!r}"

    @pytest.mark.parametrize("name", _ANSWERS)
    def test_us_still_matches_the_us_open(self, name):
        assert _matches("us", name), f"`us` lost a real word-start match: {name!r}"

    def test_a_typed_prefix_is_a_word_start_and_survives(self):
        """The LAT-P037 case: `re` is a word being typed, "Recession" starts with it."""
        assert _matches("re", "US Recession in 2026?")
        assert not _matches("re", "Liga MX Clausura Champion (Torreon)")

    def test_the_expansion_takes_the_same_rule(self):
        """`la` -> `los angeles`: either spelling, each at a word start."""
        assert _matches("la", "Los Angeles Mayor winner?", "los angeles")
        assert _matches("la", "LA Galaxy MLS Cup winner", "los angeles")
        assert not _matches("la", "Atlanta Dream WNBA Champion", "los angeles")

    def test_punctuated_fragments_are_escaped_not_wildcards(self):
        """`1.` and `u.s.` are fragments; a full stop must not match any character."""
        assert _matches("1.", "Will 1. FC Köln be relegated from the 2026-27 Bundesliga?")
        # "11." passes the ILIKE; only the escaped `\\.` stops `1.` matching "11".
        assert not _matches("1.", "Will the club finish 11. in the table?")
        assert _matches("u.s.", "U.S. Open Golf Winner")

    def test_a_non_ascii_letter_before_the_term_is_part_of_the_word(self):
        """`[:alnum:]` is locale-aware in Postgres; `[\\W_]` in Python agrees."""
        assert "us" in "Gräus Cup".lower()
        assert not _matches("us", "Gräus Cup")
