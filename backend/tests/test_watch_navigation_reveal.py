"""Bounded app navigation must retain every reader assertion and safe gesture geometry."""

import hashlib
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
SWIFT = ROOT / "ios/Bain Luck/BainLuckWatchUITests"
FILES = [
    "PickerSelectedStateJourneyTests.swift",
    "PickerReturnJourneyTests.swift",
    "WidgetTapJourneyTests.swift",
]
EXPECTED = {
    "selected_outer": "1a55711d8e5031222b02dcb250e7962abcf7fad49c800716b91906244b86dc03",
    "selected_capture": "3dd15262266ba381a3165fb8078e085ba3be755a0fd9a50963ce22cc5cfce4f5",
    "return_outer": "83b72c06e1da67bae2ec4b754e5276c0cc1bf9a1046cece3e783da03a338bcff",
    "widget_outer": "4038d57aec63a9aadce1430759a8ea080ac1798fcd66b572c750a4ed19c3f79d",
}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


APPROVED_MORE_ACTIONS = {
    "LargeTextRecoveryJourneyTests.swift": '        let more = app.buttons["watch.more-actions"]\n        try reveal(more, in: app)\n        XCTAssertEqual(more.value as? String, "Collapsed")\n        more.tap()\n        XCTAssertEqual(more.value as? String, "Expanded")\n',
    "WidgetTapJourneyTests.swift": '        let more = app.buttons["watch.more-actions"]\n        try widgetWarmReveal(more, in: app)\n        XCTAssertEqual(more.value as? String, "Collapsed")\n        more.tap()\n        XCTAssertEqual(more.value as? String, "Expanded")\n',
}


def normalize_more_actions(name, text):
    if name not in APPROVED_MORE_ACTIONS:
        return text
    block = APPROVED_MORE_ACTIONS[name]
    assert text.count(block) == 1, "Missing or unreviewed More actions expansion"
    return text.replace(block, "", 1)


def source(name):
    return normalize_more_actions(name, (SWIFT / name).read_text())


# Exact approved additions are normalized away before the ORIGINAL hash check.
# Unknown helper/call-site changes must fail, not silently inherit that receipt.
APPROVED_HELPERS = {
    "expandPickerDetails": "755b425c0fa620896ec0606dfd45b5b9cfc187b8e1c5894b91a7598a85f25311",
    "refreshViewport": "aeb02a852757b634334645fd09b9c42a27fcf4d242ad71d3e3516b5f741b6273",
    "revealRefresh": "a4c71f55035b0e071fd3a2ce78e916068ec1ed28bfb319f5a38d52f952388906",
}
APPROVED_REFRESH_BLOCK = (
    "8d19650f759ed1fa7f0d421f123618a9a2696869a17448f0892683bed0f4ab42"
)
ORIGINAL_RECOVERY = {
    "ClearSelectionJourneyTests.swift": "0bc9ab18e65695765e1a85da54be3df652a56e0012807b6d066134caa5a5516c",
    "LargeTextRecoveryJourneyTests.swift": "c409b318d266880176c15fb6db744b805e4f9610afbe4b9a5c9d9948badce673",
}


def helper_block(text, name):
    signature = "    @MainActor\n    private func " + name + "("
    assert text.count(signature) == 1, "Expected exactly one approved helper"
    start = text.index(signature)
    end = text.index("    @MainActor", start + len(signature))
    return text[start:end]


def replace_exact(text, old, new, count=1):
    assert text.count(old) == count, "Unrecognized approved transformation count"
    return text.replace(old, new)


def normalize_disclosure(name, text):
    assert name in (*ORIGINAL_RECOVERY, "PickerReturnJourneyTests.swift")
    helper_names = ["expandPickerDetails"]
    if name != "LargeTextRecoveryJourneyTests.swift":
        helper_names += ["refreshViewport", "revealRefresh"]
    for helper in helper_names:
        added = helper_block(text, helper)
        assert digest(added) == APPROVED_HELPERS[helper], "Unreviewed helper change"
        text = replace_exact(text, added, "")
    counts = {
        "PickerReturnJourneyTests.swift": (1, 1),
        "ClearSelectionJourneyTests.swift": (1, 0),
        "LargeTextRecoveryJourneyTests.swift": (2, 0),
    }
    for indent, count in zip((8, 12), counts[name]):
        line = " " * indent + "try expandPickerDetails(in: app)\n"
        lines = text.splitlines(keepends=True)
        assert lines.count(line) == count, "Unrecognized disclosure call count"
        text = "".join(item for item in lines if item != line)
    if name == "PickerReturnJourneyTests.swift":
        start = text.index("            let refreshBounds = try revealRefresh(")
        end = text.index("            expectation(for:", start)
        added = text[start:end]
        assert digest(added) == APPROVED_REFRESH_BLOCK, "Unreviewed refresh call site"
        text = replace_exact(
            text,
            added,
            "            try reveal(refresh, in: app)\n"
            "            XCTAssertTrue(refresh.isEnabled)\n"
            "            refresh.tap()\n",
        )
    elif name == "ClearSelectionJourneyTests.swift":
        text = replace_exact(
            text,
            "        _ = try revealRefresh(refresh, in: app)\n",
            "        try reveal(refresh, in: app)\n",
        )
    return text


def check_refresh_geometry(text):
    viewport = helper_block(text, "refreshViewport")
    reveal = helper_block(text, "revealRefresh")
    assert "guard visible.count == 1 else" in viewport
    assert "$0.isHittable" in viewport
    for edge in ("minX", "minY", "maxX", "maxY"):
        assert f"bounds.{edge}.isFinite" in viewport
    assert "!bounds.isNull" in viewport and "!bounds.isEmpty" in viewport
    assert "app.navigationBars.allElementsBoundByIndex.filter" in viewport
    assert "let top = max(bounds.minY, chromeBottom + 3)" in viewport
    assert "height: bounds.maxY - top" in viewport
    assert "return bounds.insetBy(dx: 2, dy: 3)" in viewport
    assert "refresh.isHittable && bounds.contains(frame)" in reveal
    assert "for _ in 0..<24" in reveal
    assert "let earlier = frame.minY < bounds.minY" in reveal
    assert "earlier ? bounds.minY - frame.minY : frame.maxY - bounds.maxY" in reveal
    assert "min(0.50, max(0.15, distance / bounds.height))" in reveal
    assert "bounds.height * (earlier ? 0.25 : 0.75)" in reveal
    assert "bounds.height * (earlier ? fraction : -fraction)" in reveal
    # Endpoints remain inside the measured content area at maximum movement.
    assert 0 < 0.25 < 0.25 + 0.50 < 1
    assert 0 < 0.75 - 0.50 < 0.75 < 1
    if "let refreshBounds = try revealRefresh" in text:
        assert "refresh.isHittable && refreshBounds.contains(refreshFrame)" in text
        assert (
            "refreshBounds.contains(CGPoint(x: refreshFrame.midX, y: refreshFrame.midY))"
            in text
        )
        assert (
            "refresh.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()"
            in text
        )
        assert text.index("verified refresh target geometry") < text.index(
            "refresh.coordinate(withNormalizedOffset:"
        )


@pytest.mark.parametrize(
    "name", ["PickerReturnJourneyTests.swift", "ClearSelectionJourneyTests.swift"]
)
def test_refresh_is_fully_below_chrome_before_center_tap(name):
    check_refresh_geometry(source(name))


@pytest.mark.parametrize("name", ORIGINAL_RECOVERY)
def test_clear_and_large_disclosure_keep_all_original_reader_obligations(name):
    assert digest(normalize_disclosure(name, source(name))) == ORIGINAL_RECOVERY[name]


def test_normalization_rejects_unreviewed_helpers_or_duplicate_disclosure():
    text = source("PickerReturnJourneyTests.swift")
    for mutated in (
        text.replace("bounds.contains(frame)", "bounds.intersects(frame)"),
        text.replace(
            "        try expandPickerDetails(in: app)\n",
            "        try expandPickerDetails(in: app)\n" * 2,
            1,
        ),
    ):
        with pytest.raises(AssertionError):
            normalize_disclosure("PickerReturnJourneyTests.swift", mutated)
    with pytest.raises(AssertionError):
        check_refresh_geometry(
            text.replace("bounds.contains(frame)", "bounds.intersects(frame)")
        )


def test_original_return_hash_still_rejects_lost_reader_assertion():
    text = source("PickerReturnJourneyTests.swift")
    obligation = '        XCTAssertEqual(probability.label, reading, "Offline picker return must retain the saved named reading")\n'
    assert text.count(obligation) == 1
    normalized = normalize_disclosure(
        "PickerReturnJourneyTests.swift", text.replace(obligation, "")
    )
    outer = (
        normalized.split("    private func reveal(", 1)[0]
        + normalized.split("    @MainActor\n    private func capture(", 1)[1]
    )
    assert digest(outer) != EXPECTED["return_outer"]


def reveal(name):
    text = source(name)
    start = (
        "    func widgetWarmReveal("
        if name.startswith("Widget")
        else "    private func reveal("
    )
    return text.split(start, 1)[1].split("    @MainActor", 1)[0]


@pytest.mark.parametrize("name", FILES)
def test_far_reveal_moves_by_hidden_distance_with_safe_endpoints(name):
    helper = reveal(name)
    # A far-away element must move farther than the old 15/20 percent step.
    assert (
        "hiddenDistance = earlier ? bounds.minY - frame.minY : max(0, frame.maxY - bounds.maxY)"
        in helper
    )
    match = re.search(
        r"min\((0\.\d+), max\((0\.\d+), \(hiddenDistance \+ (\d+)\) / bounds.height\)\)",
        helper,
    )
    assert match, "Distance must be derived from current hidden geometry and clamped"
    maximum, minimum, padding = map(float, match.groups())
    starts = re.search(r"startY: CGFloat = earlier \? (0\.\d+) : (0\.\d+)", helper)
    assert starts
    up, down = map(float, starts.groups())
    assert 0 < minimum <= maximum <= 0.55
    assert maximum > 0.20
    assert 0 < up < up + maximum < 1
    assert 0 < down - maximum < down < 1
    assert padding > 0
    assert "bounds.midX - appFrame.minX" in helper
    assert "bounds.minY + bounds.height * startY - appFrame.minY" in helper
    assert "bounds.height * (earlier ? distance : -distance)" in helper
    assert "withVelocity: .slow, thenHoldForDuration: 0.4" in helper


@pytest.mark.parametrize("name", FILES)
def test_reveal_fails_closed_on_nonunique_or_invalid_actual_viewport(name):
    text = source(name)
    helper = reveal(name)
    scope = text if name.startswith("PickerSelected") else helper
    assert "app.scrollViews.allElementsBoundByIndex.filter" in scope
    assert "guard visible.count == 1 else" in scope
    assert "scroll.isHittable" in scope
    for edge in ["minX", "minY", "maxX", "maxY"]:
        assert f"bounds.{edge}.isFinite" in scope
    assert "!bounds.isNull && !bounds.isEmpty" in scope
    assert "let appFrame = app.frame" in helper
    assert "let frame = element.frame" in helper
    assert "scrollViews.containing" not in scope
    assert "for _ in 0..<" + ("32" if name.startswith("Widget") else "24") in helper
    if name.startswith("PickerSelected"):
        assert "let container = try scrollViewport(in: app)" in helper
        assert "let bounds = try viewport(container, appFrame: appFrame)" in helper
        assert "element.isHittable && bounds.intersects(frame)" in helper
        assert "scroll.frame.intersection(appFrame)" in text
    else:
        assert "container.frame.intersection(appFrame)" in helper
        assert "element.isHittable && appFrame.contains(frame)" in helper


def test_selected_capture_preserves_original_twenty_percent_overlapping_traversal():
    text = source(FILES[0])
    scroll = text.split("private func scroll(", 1)[1].split("    @MainActor", 1)[0]
    assert "bounds.height * 0.60" in scroll
    assert "towardTop ? 0.20 : -0.20" in scroll
    capture = text.split("    @MainActor\n    private func captureRow(", 1)[1].split(
        "    @MainActor\n    private func capture(", 1
    )[0]
    normalized = capture.replace(
        "        let container = try scrollViewport(in: app)\n", ""
    )
    normalized = normalized.replace(
        "            let appFrame = app.frame\n            let bounds = try viewport(container, appFrame: appFrame)",
        "            let bounds = viewport(for: row, in: app)",
    )
    normalized = normalized.replace(
        "scroll(bounds: bounds, appFrame: appFrame, towardTop: frame.minY < bounds.minY, in: app)",
        "scroll(row, towardTop: frame.minY < bounds.minY, in: app)",
    )
    normalized = normalized.replace(
        "scroll(bounds: bounds, appFrame: appFrame, towardTop: false, in: app)",
        "scroll(row, towardTop: false, in: app)",
    )
    assert digest(normalized) == EXPECTED["selected_capture"]


def test_all_scenarios_assertions_captures_gallery_and_cleanup_are_unchanged():
    selected, returning, widget = map(source, FILES)
    returning = normalize_disclosure("PickerReturnJourneyTests.swift", returning)
    boundary = (
        "scrollViewport" if "private func scrollViewport(" in selected else "viewport"
    )
    selected_outer = (
        selected.split("    @MainActor\n    private func " + boundary + "(", 1)[0]
        + selected.split("    @MainActor\n    private func captureRow(", 1)[1].split(
            "    @MainActor\n    private func capture(", 1
        )[1]
    )
    assert digest(selected_outer) == EXPECTED["selected_outer"]
    assert (
        digest(
            returning.split("    private func reveal(", 1)[0]
            + returning.split("    @MainActor\n    private func capture(", 1)[1]
        )
        == EXPECTED["return_outer"]
    )
    assert (
        digest(
            widget.split("    func widgetWarmReveal(", 1)[0]
            + widget.split("    @MainActor\n    private func widgetWarmCapture(", 1)[1]
        )
        == EXPECTED["widget_outer"]
    )


@pytest.mark.parametrize("name", FILES[1:])
def test_already_visible_toolbar_or_overlay_needs_no_scroll_query(name):
    helper = reveal(name)
    accepted = helper.index(
        "element.isHittable && initialAppFrame.contains(initialFrame)"
    )
    assert accepted < helper.index("app.scrollViews.allElementsBoundByIndex.filter")
    assert "{ return }" in helper[accepted : helper.index("let visible")]


@pytest.mark.parametrize("name", APPROVED_MORE_ACTIONS)
def test_more_actions_normalization_rejects_missing_duplicate_or_changed_expansion(
    name,
):
    raw = (SWIFT / name).read_text()
    block = APPROVED_MORE_ACTIONS[name]
    for altered in (
        raw.replace(block, ""),
        raw.replace(block, block * 2),
        raw.replace(block, block.replace('"Expanded"', '"Collapsed"')),
    ):
        with pytest.raises(AssertionError):
            normalize_more_actions(name, altered)
