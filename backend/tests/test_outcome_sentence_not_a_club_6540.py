"""#6540 — a settled prop row stops reading "Denver scores first Broncos".

WHAT A READER SAW
=================

``/events/14638896`` — Broncos 10 @ Chiefs 31, Monday night, **Final** — printed
this card::

    Denver vs Kansas City: First Team to Score a TD
      Kansas City scores first TD        Won
      Denver scores first Broncos        Lost     <- not a sentence
      No team scores a TD                Lost

One mangled row between two correct ones.

THE STORED ROW IS CLEAN, SO THIS IS A SERVE-TIME DEFECT
=======================================================

Outcome ``224646239`` holds ``Denver scores first TD`` in the database, and
``/api/events/14638896/game-markets`` served ``Denver scores first Broncos``
(read on production 2026-09-16 13:29Z). The mangling is introduced between the
two by #6447's club-name repair, so nothing needs backfilling and no writer is
at fault.

HOW IT HAPPENS
==============

``_TRUNCATED_TAIL_RE`` was written against SIDE names, where everything before a
trailing 1-3 capital run is a city: ``Los Angeles R`` -> city ``Los Angeles``,
tail ``R``. #6447 then began feeding it whole OUTCOME strings, and an outcome is
a sentence::

    "Denver scores first TD"  ->  city "Denver scores first" + tail "TD"

``den`` matches the string, so the repair resolves the Broncos and composes
``"Denver scores first" + " " + "Broncos"``.

WHY ONLY ONE OF THE THREE ROWS
==============================

The repair fires only where the sentence's opening words match a ticker code.
``kc`` does not match ``Kansas City scores first TD``, and ``No team scores a
TD`` matches neither, so both fall through to the tail-consistency arm and are
left alone. That asymmetry is why the card printed one wrong row rather than a
uniformly wrong card — and why an eyeball on the other two rows reads as
evidence that the repair is working.

THE GUARD
=========

The head must be club-SHAPED — every word beginning with a capital or a digit —
which is shape, not a stop-word list, per the criterion #5181 set for this
family. A list would owe a new entry for every market template Kalshi invents.
"""

from __future__ import annotations

import pytest

from app.utils.kalshi_display_names import repair_truncated_names

# The production specimen, verbatim: market 60249812 on event 14638896.
_MNF_TICKER = "KXNFLFIRSTTDTEAM-26SEP14DENKC"
_MNF_OUTCOMES = [
    "Kansas City scores first TD",
    "Denver scores first TD",
    "No team scores a TD",
]


class TestTheSentenceIsNotRewritten:
    def test_the_production_specimen_is_left_alone(self):
        """THE ship. No row of that card may be rewritten.

        Asserted as the whole mapping rather than one key: the defect is that a
        repair was invented at all, and a test naming only the Denver row would
        pass if a later change started mangling the Kansas City one instead.
        """
        assert repair_truncated_names(_MNF_TICKER, _MNF_OUTCOMES) == {}

    def test_the_mangled_string_is_not_reachable_from_any_of_them(self):
        """The exact string a reader saw, named so the case cannot drift."""
        composed = set(repair_truncated_names(_MNF_TICKER, _MNF_OUTCOMES).values())

        assert "Denver scores first Broncos" not in composed
        assert not any(" scores first " in name for name in composed), (
            f"a repair composed a sentence rather than a club name: {composed}"
        )

    @pytest.mark.parametrize(
        "sentence",
        [
            "Denver scores first TD",
            "Kansas City scores first TD",
            "No team scores a TD",
            "Denver wins by 1+ TD",
            "Denver leads at HT",
            "Green Bay wins in OT",
        ],
    )
    def test_no_outcome_sentence_is_treated_as_a_truncated_club(self, sentence):
        """The class, not the instance.

        Every one of these ends in a short capital run and opens with a word
        that can match a ticker code — the exact shape the repair mistook for a
        truncation. `HT` and `OT` are here because the defect is about the SHAPE
        of a sentence, so a fix that only knew about `TD` would be the stop-word
        list this guard exists to refuse.
        """
        for ticker in (_MNF_TICKER, "KXNFLSPREAD-26SEP14GBNYJ"):
            assert repair_truncated_names(ticker, [sentence]) == {}


class TestSixFourFourSevensShipStillWorks:
    """THE CONTROLS. A guard that silenced the repair entirely would pass above.

    Each of these is a real repair #6447 shipped, and every one must survive —
    otherwise this fix re-opens "the event page names a club that does not
    exist" to close "the event page prints a sentence".
    """

    @pytest.mark.parametrize(
        "ticker,shipped,expected",
        [
            ("KXNFLFIRSTTD-26SEP10SFLAR", "Los Angeles R", "Los Angeles Rams"),
            ("KXNFLSPREAD-26SEP14GBNYJ", "New York J", "New York Jets"),
            ("KXMLBGAME-26SEP14LADSF", "Los Angeles D", "Los Angeles Dodgers"),
        ],
    )
    def test_a_truncated_side_is_still_completed(self, ticker, shipped, expected):
        assert repair_truncated_names(ticker, [shipped]) == {shipped: expected}

    def test_a_two_word_city_is_still_club_shaped(self):
        """`Kansas City K` is a city and a tail — the head has a space in it.

        The guard tests every WORD of the head, so a multi-word city must pass.
        A naive "the head is one word" rule would refuse most of the map.
        """
        out = repair_truncated_names("KXMLBGAME-26SEP14KCDET", ["Kansas City R"])

        assert out == {"Kansas City R": "Kansas City Royals"}, (
            "a genuine two-word city was refused, so the guard is reading the "
            f"head as a sentence: {out}"
        )
