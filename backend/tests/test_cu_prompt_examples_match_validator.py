"""A prompt example the validator rejects is a FALSE TEACHER (#1809 step 0).

The rev-5 production batch wrote frames for 2 of 125 profiles — 1.6% coverage —
and dropped **9 of the 11 it attempted** on the literal invariant. The standing
diagnosis was "prompt regression, not a data property", and verifying it rather
than assuming it found something sharper than a weak instruction:

    rule 6 taught      title "W7M" -> value "7M"
    the validator says value_appears_in_title("7M", "W7M") is False

because ``7`` is preceded by a letter and so is not a standalone token. The
prompt was demonstrating, as its very first worked example, a form that
``sanitize_cu_frame`` discards on arrival. Every frame the model produced by
faithfully following that pattern was thrown away, and the counter recorded it
as the model's failure.

Nothing checked the examples against the code that grades them. That is the
gap this file closes: the prompt and the validator are two statements of one
rule, written in different languages, three hundred lines apart, and they had
drifted. Now the ACCEPTED examples are executed against the real validator, so
a false teacher fails CI instead of quietly costing a coverage number.
"""

from __future__ import annotations

import re

import pytest

from app.tasks.enrich_markets import CU_WRITER_REV, _CU_V2_PROMPT
from app.utils.cu_frame import (
    sanitize_cu_frame,
    unit_appears_in_title,
    value_appears_in_title,
)

#: ``"<title>" -> value "<v>", unit "<u>"`` inside the ACCEPTED block.
_ACCEPTED_RE = re.compile(
    r'"(?P<title>[^"]+\?)"\s*->\s*value "(?P<value>[^"]+)"(?:,\s*unit "(?P<unit>[^"]+)")?'
)


def _accepted_examples():
    block = _CU_V2_PROMPT.split("ACCEPTED")[1].split("REJECTED")[0]
    return [m.groupdict() for m in _ACCEPTED_RE.finditer(block)]


class TestEveryAcceptedExampleSurvivesTheValidator:

    def test_the_block_is_findable_and_populated(self):
        examples = _accepted_examples()
        assert len(examples) >= 4, (
            "the ACCEPTED block moved or changed shape — this test is now "
            "vacuous, which is worse than absent"
        )

    @pytest.mark.parametrize("example", _accepted_examples(),
                             ids=lambda e: e["value"])
    def test_the_example_is_accepted_by_the_real_validator(self, example):
        """The whole point: run the taught form through the grading code."""
        frame, drop = sanitize_cu_frame(
            {
                "measure": "points",
                "comparator": "gte",
                "value": example["value"],
                "unit": example["unit"],
            },
            title=example["title"],
        )
        assert drop is None, (
            f"the prompt teaches value={example['value']!r} unit={example['unit']!r} "
            f"for title {example['title']!r}, and the validator DROPS it ({drop}). "
            "Fix the example or fix the validator — but they cannot disagree, "
            "because the model is being graded on one and instructed by the other."
        )
        assert frame["value"] == example["value"]

    def test_the_W7M_false_teacher_is_gone(self):
        """The specific regression, pinned by name.

        Kept as its own test rather than folded into the sweep above, because
        this example was in the prompt for an entire writer revision and cost a
        measured 82% drop rate. A parametrised sweep would let it back in the
        moment someone rewrote it in a shape the regex misses.
        """
        assert not value_appears_in_title("7M", "W7M")
        assert '"W7M" -> value "7M"' not in _CU_V2_PROMPT
        assert 'title "W7M"' not in _CU_V2_PROMPT


class TestTheRejectedFormsAreActuallyRejected:
    """The other half: the prompt's warnings must describe real behaviour.

    A warning against something the validator happily accepts is noise that
    teaches the model to be timid — and timidity is the 91%-absent number.
    """

    @pytest.mark.parametrize("value,title", [
        ("13000000", "Will X reach 13M subscribers?"),   # expanded suffix
        ("100", "Bitcoin above $100K?"),                  # fragment of a longer token
        ("27", "Who wins the 2026-27 season?"),           # tail of a compact range
        ("2025", "Will it happen in 2026?"),              # a nearby remembered number
    ])
    def test_rejected_values_really_are_rejected(self, value, title):
        assert not value_appears_in_title(value, title)
        frame, drop = sanitize_cu_frame(
            {"measure": "points", "value": value, "unit": None}, title=title
        )
        assert frame is None and drop == "value_not_in_title"

    def test_spelled_out_symbol_units_are_rejected(self):
        assert not unit_appears_in_title("percent", "Will it hit 70%?")

    def test_a_title_with_no_number_yields_an_explicit_null_frame(self):
        """Absence is a correct answer, and it must stay distinguishable from a
        drop — consumers read `frame: null` as "the title states no number" and
        an ABSENT key as "this profile predates rev 5"."""
        frame, drop = sanitize_cu_frame(None, title="Who wins the scoring title?")
        assert frame is None and drop == "absent"


class TestTheRevWasBumpedWithThePrompt:
    """`_cu_v2_needs_retag` gates on the rev.

    Without a bump the re-run reports `skipped_fresh` and generates nothing —
    CU-NEXT names this as the tell, and it is a false green: the batch
    "succeeds", the counters do not move, and the prompt change is never
    measured at all.
    """

    def test_rev_is_at_least_6(self):
        assert CU_WRITER_REV >= 6, (
            "the frame prompt changed; bump CU_WRITER_REV or the re-run skips "
            "every profile it just wrote"
        )
