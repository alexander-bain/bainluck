"""#6681 — a Settings → Your Interests tile must be able to show its own name.

Three of the 22 tiles could not: "College Foo…", "College Basketball",
"Entertainm…".  The row is `[emoji | name] Spacer() [Love Big Wild Nah]`, the
four capsules are `.fixedSize()` and the Spacer absorbs nothing, so the name is
the only compressible thing in it — and the name is also the ONLY thing telling
one row from the next, because every row's capsules read the same four words.
A reader scanning for College Football met the same truncated stem as College
Basketball two rows down.

The fix is a `minimumScaleFactor` floor on the name, sized by measurement rather
than by eye.  The arithmetic is pinned in
`BainLuckTests/SettingsInterestTileNamesAreReadable6681Tests.swift`, which
measures the real font.

WHY A BACKEND GUARD EXISTS FOR AN iOS LAYOUT
--------------------------------------------
Two holes the Swift test cannot cover, both of which would leave it green while
the defect is back on the screen:

1. **CI compiles no Swift (#4302).**  The Swift test only ever runs on a lane's
   machine when someone remembers.  This file runs in CI on every push.

2. **The Swift test asserts on the CONSTANT, not on the view.**  Deleting
   `.minimumScaleFactor(...)` from the `Text(item.name)` render — or re-inlining
   any of the geometry literals the constant block replaced — leaves every Swift
   assertion passing and the tiles truncated again.  The Swift test's whole
   claim to describe the real row rests on the view and the test sharing
   `AffinityRowMetrics`; this file is what makes that sharing enforceable.

Anchored per site, never by count: CERT-550's lesson on
`test_ios_missing_probability_render.py` is that a global count of a modifier
cannot say WHICH site carries it, so one site can be un-wired while another is
added and the total holds.
"""

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
VIEW = REPO / "ios/Bain Luck/Bain Luck/Views/PreferencesView.swift"

# The measured scale each overflowing name NEEDS at 402pt (iPhone 17 / 17 Pro,
# the device #6681 was filed from), from the real font via
# UIFont.preferredFont(forTextStyle: .subheadline) at default Dynamic Type:
#
#     College Football   0.866
#     College Basketball 0.757   <- the binding one
#     Entertainment      0.983
#
# So the shipped floor must be at or below 0.757 to fit every name on the filed
# device.  The 0.85 originally suggested on the issue clears two of the three
# and leaves College Basketball truncated.
WORST_NEEDED_SCALE_AT_FILED_WIDTH = 0.757


def _source() -> str:
    """The view with comments stripped.

    The fix's own doc comment quotes the rejected 0.85 and tabulates the scale
    factors, so a guard reading raw bytes would match its own explanation — and
    could then be silenced by deleting a comment rather than by fixing the view.
    """
    text = VIEW.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


def test_the_tile_name_render_carries_the_scale_floor():
    """The floor is on the NAME, anchored to that render and no other."""
    src = _source()

    # Anchor on the render itself: Text(item.name) through to the floor, with
    # only modifier lines between.  A floor added anywhere else in the file
    # cannot satisfy this.
    name_render = re.search(
        r"Text\(item\.name\)(?:\s*\.\w+\([^\n]*\)|\s*\.\w+\s*\{[^\n]*)*"
        r"\s*\.minimumScaleFactor\(AffinityRowMetrics\.nameMinimumScaleFactor\)",
        src,
    )
    assert name_render, (
        "The Settings → Your Interests tile name no longer carries "
        "`.minimumScaleFactor(AffinityRowMetrics.nameMinimumScaleFactor)`. "
        "Without it the three long names truncate again (#6681) and the Swift "
        "guard, which measures the constant rather than the view, stays green."
    )

    assert ".lineLimit(1)" in name_render.group(0), (
        "The name render lost `.lineLimit(1)`. minimumScaleFactor only shrinks "
        "text that would otherwise truncate; with wrapping allowed the row "
        "grows instead and the measured budget stops describing it."
    )


def test_the_shipped_floor_is_low_enough_to_actually_fit_the_longest_name():
    """A floor that is present but too high is the defect wearing a fix."""
    src = _source()
    match = re.search(
        r"static let nameMinimumScaleFactor:\s*CGFloat\s*=\s*([0-9.]+)", src
    )
    assert match, "AffinityRowMetrics.nameMinimumScaleFactor is gone or renamed"

    shipped = float(match.group(1))
    assert shipped <= WORST_NEEDED_SCALE_AT_FILED_WIDTH, (
        f"The tile-name floor was raised to {shipped}, above the {WORST_NEEDED_SCALE_AT_FILED_WIDTH} "
        f'that "College Basketball" needs at 402pt — so it truncates again. '
        "Re-measure before changing this; do not raise the floor to a rounder number."
    )
    # Not a lower bound on legibility by accident: state the other side too.
    assert shipped >= 0.5, (
        f"A floor of {shipped} would shrink a long tile name below half size, "
        "which is not legible. If a name genuinely needs that, the row needs "
        "space back (tighter capsules or a wrapped name), not a lower floor."
    )


def test_the_row_geometry_is_read_from_the_shared_metrics_not_reinlined():
    """The Swift test models this row using AffinityRowMetrics.

    If any of these sites goes back to a bare literal, the model silently stops
    describing the view and every Swift assertion keeps passing against numbers
    the row no longer uses.  That is the failure this guard exists for.
    """
    src = _source()

    required_sites = {
        "row HStack spacing": "HStack(spacing: AffinityRowMetrics.rowSpacing)",
        "emoji/name spacing": "HStack(spacing: AffinityRowMetrics.emojiNameSpacing)",
        "emoji width": ".frame(width: AffinityRowMetrics.emojiWidth)",
        "capsule spacing": "HStack(spacing: AffinityRowMetrics.capsuleSpacing)",
        "capsule font size": "size: AffinityRowMetrics.capsuleFontSize",
        "capsule padding": ".padding(.horizontal, AffinityRowMetrics.capsuleHorizontalPadding)",
        "card padding": ".padding(.horizontal, AffinityRowMetrics.cardHorizontalPadding)",
    }

    missing = [name for name, snippet in required_sites.items() if snippet not in src]
    assert not missing, (
        "These affinity-row geometry sites no longer read AffinityRowMetrics: "
        f"{missing}. The Swift width model shares those constants with the view "
        "on purpose — re-inlining a literal makes the model describe a row that "
        "no longer exists, and it will keep passing."
    )
