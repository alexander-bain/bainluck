"""CAL-P130 — guards for the ``slotratio`` dimension.

``sumband`` bands a market's published price sum against constants (1.15, 2, 5,
15) that encode one assumption: the market is a PARTITION, so a coherent sum is
~1. CAL-P127 recorded that this premise is backwards in golf — "will player X
finish top 10" is an independent binary and a hundred of them priced against ten
slots legitimately sum to ten (gotcha #23). ``slotratio`` exists to band the
quantity that is actually coherent-or-not: the sum divided by the slot count the
market's own NAME declares.

Everything that can go wrong here is silent. A mis-parsed slot count does not
error; it moves rows between two well-formed arms and changes a verdict.

* **🔴 LEAKAGE IS THE ONE THAT MATTERS.** The rail's ``shape`` and ``sumband``
  dimensions classify on ``sh.mw`` — how many outcomes actually WON. That is
  legitimate for diagnosis and fatal for a shipping exclusion rule, which would
  then decide which resolved markets count by what they resolved to. Every input
  to ``slotratio`` must be knowable at publish time.
  :func:`test_the_expression_never_reads_a_realized_winner` is the guard that
  makes this dimension different in kind from its neighbours, and it is the one
  to keep if the rest are ever trimmed.
* **A truncated digit run.** ``Top 100`` must yield 100, never 10. This is
  CAL-P127's load-bearing-digit lesson (a bare ``R`` predicate swallowing
  ``KXPGAROUNDSCORE``) restated for a quantity that is used as a DIVISOR — a
  slot count wrong by 10x moves a market four bands.
* **An unanchored match.** The cell carries ~90 single-player markets shaped
  ``Will X finish in the Top 5 at the 2026 U.S. Open?``. Those are two-leg
  binaries whose coherent sum is 1, NOT five-slot fields. They end in ``?`` and
  the anchor is the only thing keeping them out of the banded arms.
* **Banding the cut.** ``To Make the Cut`` declares no number and the cut size is
  a property of the weekend. Guessing it would be the dimension inventing the
  quantity it claims to measure, so the cut gets its own arm and is never banded.

THE ONE THING THESE TESTS DO NOT PROVE. They compare the SQL's regex literals
against Python's ``re`` after an EXPLICIT translation of the POSIX class
``[[:space:]]``, which Python does not implement. The translation is performed by
:func:`_posix_to_python` and asserted to be the only POSIX construct present, so
a future pattern using one Python cannot model fails
:func:`test_the_patterns_stay_inside_the_translatable_subset` instead of being
silently mis-modelled. The shipped expression was additionally executed
SERVER-SIDE against production during CAL-P130 and parsed the cell's 12
over-summing markets correctly; that run is evidence the tests cannot supply,
and is recorded in ``artifacts/cal-p130/RULE-DESIGN-polymarket-golf.md``.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")

#: The POSIX character classes this module knows how to model in Python. A
#: pattern using anything outside this set must be measured against the server.
_POSIX_TRANSLATIONS = {"[[:space:]]": r"\s"}


def _posix_to_python(pattern: str) -> str:
    for posix, py in _POSIX_TRANSLATIONS.items():
        pattern = pattern.replace(posix, py)
    return pattern


def _match_patterns() -> list[str]:
    """Regex literals the shipped SLOTS expression matches names against (``~*``)."""
    return re.findall(r"~\*\s*'([^']+)'", cce.SLOTS_EXPR)


def _capture_pattern() -> str:
    """The literal the shipped SLOTS expression CAPTURES the digit run with."""
    found = re.findall(r"SUBSTRING\(fm2\.name FROM '([^']+)'\)", cce.SLOTS_EXPR)
    assert len(found) == 1, f"expected exactly one capture literal, got {found}"
    return found[0]


def _slots(name: str) -> float | None:
    """Model the shipped SLOTS_EXPR against ``name``, using its own literals."""
    topn, winner = _match_patterns()[0], _match_patterns()[1]
    if re.search(_posix_to_python(topn), name, re.IGNORECASE):
        m = re.search(_posix_to_python(_capture_pattern()), name, re.IGNORECASE)
        assert m is not None, f"top-N matched but capture failed on {name!r}"
        return float(m.group(1))
    if re.search(_posix_to_python(winner), name, re.IGNORECASE):
        return 1.0
    return None


# --------------------------------------------------------------------------
# 🔴 the leakage guard — the reason this dimension is shippable at all
# --------------------------------------------------------------------------


def test_the_expression_never_reads_a_realized_winner():
    """A rule keyed on this dimension must be evaluable BEFORE a winner exists.

    ``shape`` and ``sumband`` branch on ``sh.mw`` (realized win count). If
    ``slotratio`` did too, an exclusion rule built on it would select resolved
    markets by their resolution — leakage — and every ECE it reported would be
    measured on a population defined by the answer.
    """
    expr = cce.SLOTRATIO_EXPR
    for forbidden in ("is_winner", "sh.mw", "sh.mn", ".mw", "win_count"):
        assert forbidden not in expr, (
            f"slotratio references {forbidden!r} — that is a realized-outcome "
            "input and makes any rule built on this dimension leak"
        )


def test_the_expression_reads_only_the_name_and_the_published_sum():
    """The two inputs are both known at publish time; nothing else appears."""
    expr = cce.SLOTRATIO_EXPR
    assert "fm2.name" in expr, "slot count must come from the market name"
    assert "ms.msum" in expr, "the numerator must be the published price sum"


def test_the_join_supplies_both_inputs():
    """``fm2`` and ``ms`` are aliases; if either join is dropped the SQL breaks."""
    join = cce.SLOTRATIO_JOIN
    assert "futures_markets fm2" in join
    assert "msums ms" in join


def test_the_dimension_is_registered_with_the_msums_cte():
    """``ms.msum`` only exists because SUMBAND_PRE defines the ``msums`` CTE."""
    expr, join, pre = cce.DIMENSIONS["slotratio"]
    assert expr is cce.SLOTRATIO_EXPR
    assert join is cce.SLOTRATIO_JOIN
    assert pre is cce.SUMBAND_PRE, "slotratio needs the msums CTE"


def test_the_dimension_is_reachable_from_the_command_line():
    assert "slotratio" in cce.DIMENSIONS


# --------------------------------------------------------------------------
# the digit run is a DIVISOR, so truncating it moves a market four bands
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("PGA Tour: U.S. Open Top 5", 5),
        ("PGA Tour: U.S. Open Top 10", 10),
        ("PGA Tour: PGA Championship Top 20", 20),
        ("PGA Tour: Valspar Championship Winner", 1),
        ("Korn Ferry Tour: Pinnacle Bank Championship Winner", 1),
    ],
)
def test_the_real_field_names_in_the_cell_parse(name, expected):
    assert _slots(name) == expected


def test_a_three_digit_slot_count_is_not_truncated():
    """``Top 100`` is 100 slots. Capturing ``[0-9]`` instead of ``[0-9]+`` would
    read it as 1 and put a coherent market in the worst band."""
    assert _slots("Some Tour: Big Field Top 100") == 100


def test_the_capture_takes_a_whole_digit_run():
    assert "[0-9]+" in _capture_pattern(), (
        "the capture must take a full digit run; a single-digit capture "
        "silently divides by the wrong number"
    )


# --------------------------------------------------------------------------
# anchoring — the ~90 single-player binaries must stay OUT of the banded arms
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Will Tommy Fleetwood finish in the Top 5 at the 2026 U.S. Open?",
        "Will Taylor Pendrith finish in the Top 10 at the 2026 RBC Canadian Open?",
        "Will Eric Cole finish in the Top 20 at the 2026 Wyndham Championship?",
    ],
)
def test_a_single_player_binary_declares_no_slot_count(name):
    """These are two-leg Yes/No markets whose coherent sum is 1, not N. They are
    real rows in ``polymarket/golf`` and the trailing ``?`` is the only thing
    keeping them out of the banded arms."""
    assert _slots(name) is None


def test_a_top_n_that_is_not_at_the_end_does_not_match():
    """Gotcha #129: an enumeration written by reading one source's titles is
    complete for that source and silently partial for the next."""
    assert _slots("PGA Tour: Top 5 Playoff Bracket Winner Margin") is None


def test_the_top_n_pattern_is_anchored():
    assert _match_patterns()[0].rstrip().endswith("$")


def test_the_winner_pattern_is_anchored():
    assert _match_patterns()[1].rstrip().endswith("$")


# --------------------------------------------------------------------------
# the cut is separated, never banded
# --------------------------------------------------------------------------


def test_the_cut_declares_no_slot_count():
    assert _slots("2026 U.S. Open: To Make the Cut") is None


def test_the_cut_gets_its_own_arm_before_the_generic_unparsed_arm():
    """158 of the cell's ~296 field markets are cut markets. Folding them into
    ``z_no_declared_n`` would hide the largest single family behind a name that
    says 'miscellaneous'."""
    expr = cce.SLOTRATIO_EXPR
    assert "z_cut_no_declared_n" in expr
    assert expr.index("z_cut_no_declared_n") < expr.index("z_no_declared_n"), (
        "the cut branch must be tested BEFORE the generic unparsed branch, "
        "or it is unreachable"
    )


def test_no_band_is_applied_to_a_row_without_a_declared_slot_count():
    """A row the rule cannot see must not be scored as if it could."""
    expr = cce.SLOTRATIO_EXPR
    first_band = expr.index("a_ratio_lt_0.25")
    assert expr.index("z_cut_no_declared_n") < first_band
    assert expr.index("z_no_declared_n") < first_band
    assert expr.index("z_no_sum") < first_band


# --------------------------------------------------------------------------
# the bands themselves
# --------------------------------------------------------------------------


def _band_thresholds() -> list[float]:
    """Thresholds read off the band each one leads to, so the pairing is pinned.

    Anchoring on the ``THEN '<band>'`` label rather than on the arithmetic is
    deliberate: the denominator is an interpolated CASE expression full of
    parentheses, and a regex that tried to span it would silently match nothing
    and make this guard vacuous.
    """
    found = re.findall(r"<=?\s*([0-9.]+)\s*THEN\s*'([a-z]_ratio[^']*)'",
                       cce.SLOTRATIO_EXPR)
    assert found, "no banded arms found — the extraction regex has gone stale"
    return [float(threshold) for threshold, _band in found]


def test_the_bands_are_ordered():
    t = _band_thresholds()
    assert t == sorted(t), f"band thresholds out of order: {t}"


def test_the_bands_are_symmetric_in_log_space_around_one():
    """1/4, 3/4, 4/3, 4 — chosen before the fold ran so the banding cannot be
    fitted to the answer, and symmetric so it can SEE an under-sum as readily as
    an over-sum (lesson 13: a correction expected to run one way runs both)."""
    t = _band_thresholds()
    assert len(t) == 4, f"expected four thresholds, got {t}"
    lo1, lo2, hi2, hi1 = t
    assert lo1 * hi1 == pytest.approx(1.0, abs=0.01), (lo1, hi1)
    assert lo2 * hi2 == pytest.approx(1.0, abs=0.01), (lo2, hi2)


def test_the_ratio_divides_by_the_declared_slot_count_not_a_constant():
    """The whole point of the dimension: ``sumband`` compares to a constant and
    is therefore wrong on any multi-slot field (gotcha #23)."""
    assert re.search(r"ms\.msum / \(\s*\n?\s*CASE", cce.SLOTRATIO_EXPR), (
        "the denominator must be the name-derived slot expression"
    )
    assert "ms.msum <=" not in cce.SLOTRATIO_EXPR, (
        "a bare sum comparison would be sumband's mistake reintroduced"
    )


# --------------------------------------------------------------------------
# the modelling caveat itself
# --------------------------------------------------------------------------


def test_the_patterns_stay_inside_the_translatable_subset():
    """These tests model POSIX regexes with Python's ``re``. That is only sound
    for the constructs listed in ``_POSIX_TRANSLATIONS``; anything else must be
    measured against the server instead of guessed at here."""
    for pattern in _match_patterns() + [_capture_pattern()]:
        residue = pattern
        for posix in _POSIX_TRANSLATIONS:
            residue = residue.replace(posix, "")
        assert "[:" not in residue, (
            f"{pattern!r} uses a POSIX class this module cannot model; add it "
            "to _POSIX_TRANSLATIONS with a justification or test it server-side"
        )


def test_sumband_is_left_untouched():
    """``slotratio`` is an addition. Two dimensions that band the same quantity
    must not quietly redefine each other — CAL-P129's ``field1|*`` arms are the
    N=1 special case of this one and must stay comparable across sessions."""
    assert "1.15" in cce.SUMBAND_ONLY_EXPR
    assert "e_sum_gt_15" in cce.SUMBAND_ONLY_EXPR
