"""#9340 — the spelled-out MLB postseason rounds, without a database.

These run where the real-Postgres gate (`test_search_division_series_pg.py`)
skips. Three rules, each with the shape that broke it beside it:

1. `division series` / `championship series` alias to the round
   abbreviations the venues actually use.
2. The alias arm compiles a round abbreviation WHOLE-WORD — `%alds%` is
   inside Byron Don(alds) and Wea(lds)tone.
3. The intent parser does not read `division series` as a division question:
   read as one, the dropdown hunted "series"'s division market and served
   nothing.
"""

import re

from sqlalchemy.dialects import postgresql

from app.routes.events import _alias_futures_arms, _phrase_alias_alternatives
from app.utils import search_intent
from app.utils.search_intent import INTENT_DIVISION, parse_intent


def _sql(clauses) -> str:
    return " ".join(
        str(c.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for c in clauses
    )


def test_the_spelled_out_rounds_alias_to_their_abbreviations():
    assert _phrase_alias_alternatives(["division", "series"]) == [["alds"], ["nlds"]]
    assert _phrase_alias_alternatives(["Championship", "Series"]) == [["alcs"], ["nlcs"]]
    # A span: the rest of the query rides along.
    assert _phrase_alias_alternatives(["mlb", "division", "series"]) == [
        ["mlb", "alds"], ["mlb", "nlds"],
    ]


def test_the_words_apart_are_not_the_round():
    for terms in (["division"], ["series"], ["series", "division"], ["world", "series"]):
        assert _phrase_alias_alternatives(terms) == [], terms


def test_the_alias_arm_compiles_the_abbreviation_whole_word():
    sql = _sql(_alias_futures_arms(["division", "series"]))
    assert "(^|[^[:alnum:]])alds([^[:alnum:]]|$)" in sql, sql
    assert "(^|[^[:alnum:]])nlds([^[:alnum:]]|$)" in sql, sql


def test_the_old_substring_compile_is_the_shape_that_reaches_byron_donalds():
    """Strawman: without the trailing boundary, `alds` matches the surname."""
    word_start = re.compile(r"(^|[^A-Za-z0-9])alds", re.I)
    whole = re.compile(r"(^|[^A-Za-z0-9])alds([^A-Za-z0-9]|$)", re.I)
    assert "alds" in "Byron Donalds vote percent".lower()
    assert not whole.search("Byron Donalds vote percent")
    assert whole.search("MLB Playoffs: Team to advance to ALDS")
    assert word_start.search("advance to ALDS")


def test_non_round_alias_terms_compile_as_before():
    """`march madness` -> `college basketball` is untouched by the whole-word rule."""
    sql = _sql(_alias_futures_arms(["march", "madness"]))
    assert "([^[:alnum:]]|$)" not in sql, sql


def test_division_series_is_not_a_division_question():
    for q in ("division series", "Division Series", "mlb division series",
              "yankees division series"):
        assert parse_intent(q) is None, q


def test_a_division_question_is_still_one():
    """Control: the lookahead refuses only the round."""
    for q in ("yankees win the division", "yankees division", "division yankees",
              "patriots to win division"):
        intent = parse_intent(q)
        assert intent is not None and intent.kind == INTENT_DIVISION, q


def test_without_the_lookahead_division_series_is_misread(monkeypatch):
    """Strawman: the pre-#9340 pattern claims the round as a division question."""
    old = re.compile(
        r"\b(?:(?:to\s+)?(?:win|wins|take|takes)\s+(?:the\s+)?)?division\b", re.I
    )
    scaffolds = tuple(
        (kind, old if pattern is search_intent._DIVISION_RE else pattern)
        for kind, pattern in search_intent._SCAFFOLDS
    )
    monkeypatch.setattr(search_intent, "_SCAFFOLDS", scaffolds)
    intent = parse_intent("division series")
    assert intent is not None and intent.kind == INTENT_DIVISION
    assert intent.subject == "series"
