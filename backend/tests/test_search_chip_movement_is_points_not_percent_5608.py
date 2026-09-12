"""#5608 — the search-suggestion chip called percentage POINTS a percent.

    "Surging +10.0% — Rodri: Next Club"

`probability_change_24h` is a probability DELTA in 0-1 units — every writer
stores it as `new - previous` — so `change * 100` is percentage POINTS. A
candidate who went 37.8% -> 47.8% was labelled "+10.0%", which a reader takes as
a tenth more than they had (about 4.8 points): under half the real move, in a
unit the number was never in.

This is the LAST surface of a three-surface family, all fixed today:

    #4066   the Discover golf card's green pill   "18%"  -> "18 pts"    (live)
    #5619   eight futures sentence sites          "38.0" -> "38 points"
    #5608   this chip                             "+10.0%" -> "+10 points"

All three now route through `feed_reasons._points`, the house display formatter,
rather than repeating `round(abs(v) * 100, 1)` inline — repeating it is how the
surfaces drifted apart in the first place.

THE SIGN STAYS OUTSIDE THE FORMATTER. `_points` returns the ABSOLUTE magnitude
("10 points", "1 point"), because its other callers put the direction in a verb.
This chip puts the direction in both a verb AND a sign ("Falling -94 points"), so
the sign is composed here. That is deliberate, and the negative arm below is what
stops a future edit from dropping it and serving "Falling 94 points".

SCOPE. `backend/app/routes/events.py` is touched under Fable-5's ruling of
Sat 2026-09-12 8:08AM PT: discover owns #5608 for this defect family only,
because the lane holding the formatter fixes the last surface of its own family.
Not a licence to sweep the route file.
"""

from types import SimpleNamespace

from app.routes.events import _mover_chips


def _row(name, *, market_name="EPL Playmaker Award", market_id=1, change=0.5):
    """The shape `_mover_chips` walks: an outcome with a loaded market."""
    return SimpleNamespace(
        name=name,
        market_id=market_id,
        probability_change_24h=change,
        market=SimpleNamespace(id=market_id, name=market_name, event=None),
    )


def _label(change, *, name="Rayan Cherki", market_id=1):
    chips = _mover_chips([_row(name, market_id=market_id, change=change)])
    assert chips, f"no chip produced for change={change}"
    return chips[0]["label"]


def test_a_ten_point_rise_is_ten_points_not_ten_percent():
    """The defect, in the exact shape #5608 was filed on."""
    label = _label(0.10)
    assert "+10 points" in label, label
    assert "%" not in label, f"the chip still calls a delta a percent: {label!r}"


def test_the_whole_label_reads_as_a_sentence():
    """Asserted as the WHOLE value, not a substring.

    A containment check passes on a label that also still carries the old
    percent somewhere else in it.
    """
    assert _label(0.10, market_id=7) == "Surging +10 points — EPL Playmaker Award"


def test_a_fall_keeps_its_minus_sign():
    """`_points` is absolute, so the sign is composed at the call site.

    Drop it and the chip says "Falling 94 points", which reads as a rise with a
    contradicting verb.
    """
    label = _label(-0.94)
    assert "-94 points" in label, label
    assert label.startswith("Falling "), label
    assert "%" not in label, label


def test_a_one_point_move_is_singular():
    """The worst reading of the old form: `round(0.01 * 100, 1)` is exactly 1.0,
    so the chip said "+1.0%". "+1 points" is also wrong and is what a bare int()
    cast would produce."""
    label = _label(0.01)
    assert "+1 point " in label or label.endswith("+1 point"), label
    assert "1.0 point" not in label, label
    assert "1 points" not in label, label


def test_a_real_decimal_survives():
    """The fix must route through the formatter, not round to a whole number."""
    label = _label(0.235)
    assert "23.5 points" in label, label


def test_no_chip_on_any_magnitude_calls_a_delta_a_percent():
    """The class, swept across the range rather than on one specimen.

    A per-value arm proves the value; this proves the RULE, so a future branch
    that reintroduces "%" for (say) large moves is caught even though every
    specimen above still passes.
    """
    magnitudes = [0.001, 0.01, 0.1, 0.235, 0.5, -0.01, -0.29, -0.94, 0.999]
    labels = [_label(m, market_id=i + 1) for i, m in enumerate(magnitudes)]

    assert len(labels) == len(magnitudes), "every magnitude must yield a chip"
    offenders = [label for label in labels if "%" in label]
    assert not offenders, f"these chips still print a percent: {offenders}"
    assert all(" point" in label for label in labels), labels
