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
    "selected_outer": "ce52ac82f842940b22b3c237089f1e7bce139a0e89b9966fe17d82efd4b748c3",
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
    text = (SWIFT / name).read_text()
    if name == "WidgetTapJourneyTests.swift":
        text = restore_launcher_scope(text)
    if name in COST_READ_TRANSFORMS:
        text = restore_cost_reads(name, text)
    if name == "PickerReturnJourneyTests.swift":
        text = normalize_picker_frame_reads(text)
    return normalize_more_actions(name, text)


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
# Exact retained-state repair: only the recovered row tap uses the existing
# chrome-aware helper. Original scenario/assertion hashes remain the authority.
RECOVERED_SELECTION_REVEAL = (
    "            XCTAssertTrue(retained.waitForExistence(timeout: 15))\n"
    "            // isHittable includes rows under the native Games bar. Reuse the\n"
    "            // existing chrome-free viewport before this same selection tap.\n"
    "            _ = try revealRefresh(retained, in: app)\n"
    "            retained.tap()\n"
)
ORIGINAL_RECOVERED_SELECTION_REVEAL = (
    "            XCTAssertTrue(retained.waitForExistence(timeout: 15))\n"
    "            try reveal(retained, in: app)\n"
    "            retained.tap()\n"
)
LARGE_TEXT_CHANGE_HELPERS = {
    "changeViewport": "39f275d30ca7681f295e0523992b7bc48e701015136b6081486521da0c94e19a",
    "revealChange": "305e4904e2e23ca60049ed888fca95dc099218260037137a7db8becf73a26c3b",
}
LARGE_TEXT_CHANGE_CALL = "        _ = try revealChange(change, in: app)\n"
LARGE_TEXT_ORIGINAL_CHANGE_CALL = "        try reveal(change, in: app)\n"
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
    if name == "LargeTextRecoveryJourneyTests.swift":
        for helper, expected in LARGE_TEXT_CHANGE_HELPERS.items():
            added = helper_block(text, helper)
            assert digest(added) == expected, "Unreviewed largest-text change viewport"
            text = replace_exact(text, added, "")
        text = replace_exact(
            text, LARGE_TEXT_CHANGE_CALL, LARGE_TEXT_ORIGINAL_CHANGE_CALL
        )
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
        text = replace_exact(
            text, RECOVERED_SELECTION_REVEAL, ORIGINAL_RECOVERED_SELECTION_REVEAL
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


@pytest.mark.parametrize(
    "mutation", ["old_helper", "missing", "duplicate", "after_tap"]
)
def test_recovered_selection_requires_chrome_free_reveal_before_unchanged_tap(mutation):
    text = source("PickerReturnJourneyTests.swift")
    line = "            _ = try revealRefresh(retained, in: app)\n"
    block = RECOVERED_SELECTION_REVEAL
    replacements = {
        "old_helper": ORIGINAL_RECOVERED_SELECTION_REVEAL,
        "missing": block.replace(line, ""),
        "duplicate": block.replace(line, line * 2),
        "after_tap": block.replace(line, "").replace(
            "            retained.tap()\n", "            retained.tap()\n" + line
        ),
    }
    assert text.count(block) == 1
    with pytest.raises(AssertionError):
        normalize_disclosure(
            "PickerReturnJourneyTests.swift",
            text.replace(block, replacements[mutation]),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "old",
        "missing",
        "duplicate",
        "direction",
        "containment",
        "budget",
        "hittability",
        "reading",
    ],
)
def test_largest_text_change_rejects_weakened_or_missing_viewport(mutation):
    text = source("LargeTextRecoveryJourneyTests.swift")
    replacements = {
        "old": text.replace(LARGE_TEXT_CHANGE_CALL, LARGE_TEXT_ORIGINAL_CHANGE_CALL),
        "missing": text.replace(LARGE_TEXT_CHANGE_CALL, ""),
        "duplicate": text.replace(LARGE_TEXT_CHANGE_CALL, LARGE_TEXT_CHANGE_CALL * 2),
        "direction": text.replace(
            "let earlier = frame.minY < bounds.minY",
            "let earlier = frame.minY < app.frame.minY",
        ),
        "containment": text.replace(
            "bounds.contains(frame)", "bounds.intersects(frame)"
        ),
        "budget": text.replace("for _ in 0..<32", "for _ in 0..<64"),
        "hittability": text.replace(
            "change.isHittable && bounds.contains", "bounds.contains"
        ),
        "reading": text.replace(
            "        XCTAssertEqual(probability.label, reading)\n", ""
        ),
    }
    assert replacements[mutation] != text
    with pytest.raises(AssertionError):
        normalized = normalize_disclosure(
            "LargeTextRecoveryJourneyTests.swift", replacements[mutation]
        )
        assert (
            digest(normalized)
            == ORIGINAL_RECOVERY["LargeTextRecoveryJourneyTests.swift"]
        )


def test_largest_text_change_uses_finite_unique_unobscured_viewport_and_original_gesture_cap():
    text = source("LargeTextRecoveryJourneyTests.swift")
    viewport = helper_block(text, "changeViewport")
    reveal = helper_block(text, "revealChange")
    assert "guard visible.count == 1 else" in viewport
    assert "$0.isHittable" in viewport
    for edge in ("minX", "maxX", "minY", "maxY"):
        assert f"bounds.{edge}.isFinite" in viewport
    assert "app.navigationBars.allElementsBoundByIndex.filter" in viewport
    assert "let top = max(bounds.minY, chromeBottom + 3)" in viewport
    assert "bounds.height > 30" in viewport
    assert "return bounds.insetBy(dx: 2, dy: 3)" in viewport
    assert "change.isHittable && bounds.contains(frame)" in reveal
    assert "let earlier = frame.minY < bounds.minY" in reveal
    assert "for _ in 0..<32" in reveal
    assert "waitForExistence(timeout: 15)" in reveal
    assert "thenHoldForDuration: 0.4" in reveal
    assert "min(0.50, max(0.15, distance / bounds.height))" in reveal
    assert "bounds.height * (earlier ? 0.25 : 0.75)" in reveal
    assert "bounds.height * (earlier ? fraction : -fraction)" in reveal


@pytest.mark.parametrize(
    "top,y,height,earlier",
    [
        (6, 0.5, 44, True),
        (68, 0.5, 44, True),
        (68, -20, 44, True),
        (68, 230, 44, False),
        (68, 300, 44, False),
        (6, -60, 44, True),
    ],
)
def test_largest_text_change_geometry_model_keeps_both_endpoints_inside_content(
    top, y, height, earlier
):
    # Synthetic content bounds, not a claim about retained navigation-bar dimensions.
    # Source hashes bind the modeled formula; Swift and gestures remain unexecuted.
    bottom = 245
    assert (y < top) is earlier
    distance = top - y if earlier else y + height - bottom
    fraction = min(0.50, max(0.15, distance / (bottom - top)))
    start = top + (bottom - top) * (0.25 if earlier else 0.75)
    end = start + (bottom - top) * (fraction if earlier else -fraction)
    assert top < min(start, end) < max(start, end) < bottom
    if y == 0.5:
        assert not (
            y < 0
        ), "Original whole-app direction pushes top-edge target outward"
        assert end > start


# This candidate only coalesces geometry reads within one reveal attempt.
# Reconstruct exact prior helpers before the unchanged original-obligation gate.
PICKER_FRAME_READS_BEFORE = '    @MainActor\n    private func refreshViewport(in app: XCUIApplication) throws -> CGRect {\n        let visible = app.scrollViews.allElementsBoundByIndex.filter {\n            let bounds = $0.frame.intersection(app.frame)\n            return $0.isHittable && !bounds.isNull && !bounds.isEmpty\n                && bounds.minX.isFinite && bounds.maxX.isFinite\n                && bounds.minY.isFinite && bounds.maxY.isFinite\n        }\n        guard visible.count == 1 else {\n            XCTFail("Expected one visible refresh scroll viewport")\n            throw NSError(domain: "WatchPickerRefreshViewport", code: 1)\n        }\n        var bounds = visible[0].frame.intersection(app.frame)\n        let bars = app.navigationBars.allElementsBoundByIndex.filter {\n            $0.exists && $0.frame.intersects(bounds)\n        }\n        if let chromeBottom = bars.map({ $0.frame.maxY }).max() {\n            let top = max(bounds.minY, chromeBottom + 3)\n            bounds = CGRect(x: bounds.minX, y: top, width: bounds.width, height: bounds.maxY - top)\n        }\n        guard !bounds.isEmpty, !bounds.isNull, bounds.height > 30,\n              bounds.minX.isFinite, bounds.maxX.isFinite,\n              bounds.minY.isFinite, bounds.maxY.isFinite else {\n            XCTFail("Invalid unobscured refresh viewport")\n            throw NSError(domain: "WatchPickerRefreshViewport", code: 2)\n        }\n        return bounds.insetBy(dx: 2, dy: 3)\n    }\n\n    @MainActor\n    private func revealRefresh(_ refresh: XCUIElement, in app: XCUIApplication) throws -> CGRect {\n        for _ in 0..<24 {\n            let bounds = try refreshViewport(in: app)\n            let frame = refresh.frame\n            if refresh.isHittable && bounds.contains(frame) { return bounds }\n            let earlier = frame.minY < bounds.minY\n            let distance = earlier ? bounds.minY - frame.minY : frame.maxY - bounds.maxY\n            let fraction = min(0.50, max(0.15, distance / bounds.height))\n            let origin = app.coordinate(withNormalizedOffset: .zero)\n            let start = origin.withOffset(CGVector(dx: bounds.midX - app.frame.minX,\n                dy: bounds.minY + bounds.height * (earlier ? 0.25 : 0.75) - app.frame.minY))\n            let end = start.withOffset(CGVector(dx: 0, dy: bounds.height * (earlier ? fraction : -fraction)))\n            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.3)\n        }\n        XCTFail("Cannot bring full refresh control below navigation chrome")\n        throw NSError(domain: "WatchPickerRefreshViewport", code: 3)\n    }\n\n'
PICKER_FRAME_READS_SHA256 = (
    "6e1f11359349df7fa451139546138d79cbc9258005f8c97f79e67f063371a404"
)


def normalize_picker_frame_reads(text):
    start = text.index("    @MainActor\n    private func refreshViewport(")
    end = text.index("    @MainActor\n    private func reveal(", start)
    block = text[start:end]
    assert (
        digest(block) == PICKER_FRAME_READS_SHA256
    ), "Unreviewed picker frame-read change"
    return text[:start] + PICKER_FRAME_READS_BEFORE + text[end:]


def test_picker_frame_reads_are_attempt_local_and_not_requeried_for_coordinates():
    raw = (SWIFT / "PickerReturnJourneyTests.swift").read_text()
    viewport = helper_block(raw, "refreshViewport")
    reveal = helper_block(raw, "revealRefresh")
    assert "app.frame" not in viewport
    assert viewport.count("scroll.frame") == 1
    assert viewport.count("bar.frame") == 1
    assert "var bounds = visible[0]" in viewport
    assert reveal.count("app.frame") == 1
    assert reveal.index("for _ in 0..<24") < reveal.index("let appFrame = app.frame")
    assert "refreshViewport(in: app, appFrame: appFrame)" in reveal
    assert "bounds.midX - appFrame.minX" in reveal
    assert "- appFrame.minY" in reveal
    # Every next drag attempt remeasures all geometry and rechecks hittability.
    assert reveal.index("let appFrame = app.frame") < reveal.index("refresh.isHittable")
    assert "guard visible.count == 1 else" in viewport
    assert "guard bar.exists else" in viewport


@pytest.mark.parametrize(
    "mutation",
    ["old", "containment", "hittability", "budget", "stale", "ambiguous", "chrome"],
)
def test_picker_frame_read_normalization_refuses_scope_or_gate_changes(mutation):
    raw = (SWIFT / "PickerReturnJourneyTests.swift").read_text()
    start = raw.index("    @MainActor\n    private func refreshViewport(")
    end = raw.index("    @MainActor\n    private func reveal(", start)
    changes = {
        "old": raw[:start] + PICKER_FRAME_READS_BEFORE + raw[end:],
        "containment": raw.replace(
            "bounds.contains(frame)", "bounds.intersects(frame)"
        ),
        "hittability": raw.replace(
            "refresh.isHittable && bounds.contains", "bounds.contains"
        ),
        "budget": raw.replace("for _ in 0..<24", "for _ in 0..<48"),
        "stale": raw.replace(
            "        for _ in 0..<24 {\n            let appFrame = app.frame",
            "        let appFrame = app.frame\n        for _ in 0..<24 {",
        ),
        "ambiguous": raw.replace(
            "guard visible.count == 1 else", "guard !visible.isEmpty else"
        ),
        "chrome": raw.replace("chromeBottom + 3", "chromeBottom - 3"),
    }
    assert changes[mutation] != raw
    with pytest.raises(AssertionError):
        normalize_picker_frame_reads(changes[mutation])


LARGE_TEXT_FIXED_STEP = (
    "            if element.isHittable && appFrame.contains(frame) { return }\n"
    "            let earlier = frame.minY < appFrame.minY\n"
    "            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.60))\n"
    "            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: earlier ? 0.75 : 0.45))\n"
)
LARGE_TEXT_DISTANCE_STEP = (
    "            if element.isHittable && appFrame.contains(frame) { return }\n"
    "            // Contained but not hittable in the upper half means under the navigation bar (the\n"
    "            // Watch app has no bottom chrome); dragging it up again oscillated until the cap.\n"
    "            let earlier = frame.minY < appFrame.minY || (appFrame.contains(frame) && frame.midY < appFrame.midY)\n"
    "            // Size each drag to the remaining offset, as revealChange does; a fixed 15% step\n"
    "            // spent most of the 3-minute allowance on drags at accessibility5.\n"
    "            let distance = earlier ? appFrame.minY - frame.minY : frame.maxY - appFrame.maxY\n"
    "            let fraction = min(0.50, max(0.15, distance / appFrame.height))\n"
    "            let from: CGFloat = earlier ? 0.35 : 0.75\n"
    "            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: from))\n"
    "            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: earlier ? from + fraction : from - fraction))\n"
)

# Exact, attempt-local cost changes are undone before all preexisting guards.
COST_READ_TRANSFORMS = {
    "LargeTextRecoveryJourneyTests.swift": [
        (
            "changeViewport(in app: XCUIApplication) throws",
            "changeViewport(in app: XCUIApplication, appFrame: CGRect) throws",
            1,
        ),
        (
            "        let visible = app.scrollViews.allElementsBoundByIndex.filter {\n            let bounds = $0.frame.intersection(app.frame)\n            return $0.isHittable && !bounds.isNull && !bounds.isEmpty\n                && bounds.minX.isFinite && bounds.maxX.isFinite\n                && bounds.minY.isFinite && bounds.maxY.isFinite\n        }",
            "        let visible = app.scrollViews.allElementsBoundByIndex.compactMap { scroll -> CGRect? in\n            let bounds = scroll.frame.intersection(appFrame)\n            guard scroll.isHittable && !bounds.isNull && !bounds.isEmpty\n                && bounds.minX.isFinite && bounds.maxX.isFinite\n                && bounds.minY.isFinite && bounds.maxY.isFinite else { return nil }\n            return bounds\n        }",
            1,
        ),
        (
            "var bounds = visible[0].frame.intersection(app.frame)",
            "var bounds = visible[0]",
            1,
        ),
        (
            "        let bars = app.navigationBars.allElementsBoundByIndex.filter {\n            $0.exists && $0.frame.intersects(bounds)\n        }\n        if let chromeBottom = bars.map({ $0.frame.maxY }).max() {",
            "        let chromeBottom = app.navigationBars.allElementsBoundByIndex.compactMap { bar -> CGFloat? in\n            guard bar.exists else { return nil }\n            let frame = bar.frame\n            return frame.intersects(bounds) ? frame.maxY : nil\n        }.max()\n        if let chromeBottom = chromeBottom {",
            1,
        ),
        (
            "            let bounds = try changeViewport(in: app)",
            "            let appFrame = app.frame\n            let bounds = try changeViewport(in: app, appFrame: appFrame)",
            1,
        ),
        ("dx: bounds.midX - app.frame.minX", "dx: bounds.midX - appFrame.minX", 1),
        (
            "dy: bounds.minY + bounds.height * (earlier ? 0.25 : 0.75) - app.frame.minY",
            "dy: bounds.minY + bounds.height * (earlier ? 0.25 : 0.75) - appFrame.minY",
            1,
        ),
        (
            "            if element.isHittable && app.frame.contains(element.frame) { return }\n            let earlier = element.frame.minY < app.frame.minY",
            "            let appFrame = app.frame\n            let frame = element.frame\n            if element.isHittable && appFrame.contains(frame) { return }\n            let earlier = frame.minY < appFrame.minY",
            1,
        ),
        # #10090: the generic reveal drags by the remaining offset (revealChange's clamp),
        # not a fixed 15% step, and moves a contained-but-unhittable upper element down from
        # under the navigation bar; the visibility test and the 32-attempt cap are untouched.
        (
            LARGE_TEXT_FIXED_STEP,
            LARGE_TEXT_DISTANCE_STEP,
            1,
        ),
    ],
    "PickerAliasJourneyTests.swift": [
        (
            "            if row.isHittable && frame.minY >= bounds.minY && frame.minY <= bounds.midY {",
            "            // A complete row already in view needs the same retained capture,\n            // not an extra scroll solely to move its top into the upper half.\n            let complete = !frame.isNull && !frame.isEmpty\n                && frame.minX.isFinite && frame.minY.isFinite\n                && frame.maxX.isFinite && frame.maxY.isFinite && bounds.contains(frame)\n            if row.isHittable && (complete || (frame.minY >= bounds.minY && frame.minY <= bounds.midY)) {",
            1,
        )
    ],
    "WatchDiagnosticsJourneyTests.swift": [
        (
            "bounds(_ app: XCUIApplication) -> CGRect",
            "bounds(_ app: XCUIApplication, appFrame: CGRect) -> CGRect",
            1,
        ),
        (
            "(collection.exists ? collection.frame : app.frame)",
            "(collection.exists ? collection.frame : appFrame)",
            1,
        ),
        (
            "height: max(1, content.maxY - top)).intersection(app.frame)",
            "height: max(1, content.maxY - top)).intersection(appFrame)",
            1,
        ),
        (
            "    @MainActor private func scroll(_ app: XCUIApplication, earlier: Bool, fraction: CGFloat = 0.20) {\n        let box = bounds(app)",
            "    @MainActor private func scroll(_ app: XCUIApplication, earlier: Bool, fraction: CGFloat = 0.20) {\n        let appFrame = app.frame\n        let box = bounds(app, appFrame: appFrame)\n        scroll(app, box: box, appFrame: appFrame, earlier: earlier, fraction: fraction)\n    }\n\n    @MainActor private func scroll(_ app: XCUIApplication, box: CGRect, appFrame: CGRect, earlier: Bool, fraction: CGFloat = 0.20) {",
            1,
        ),
        (
            "CGVector(dx: box.midX - app.frame.minX, dy: box.minY + box.height * startFraction - app.frame.minY)",
            "CGVector(dx: box.midX - appFrame.minX, dy: box.minY + box.height * startFraction - appFrame.minY)",
            1,
        ),
        (
            "            let box = bounds(app)\n            // Form lazily mounts offscreen rows; never read a missing row's frame or label.\n            if !element.exists { scroll(app, earlier: earlierWhenMissing); continue }\n            if element.isHittable && (box.contains(element.frame) ||\n                (element.frame.height > box.height && box.intersects(element.frame))) { return }\n            let distance = abs(element.frame.midY - box.midY) / box.height\n            let fraction = min(maxScrollFraction, max(0.20, distance))\n            scroll(app, earlier: element.frame.midY < box.midY, fraction: fraction)",
            "            let appFrame = app.frame\n            let box = bounds(app, appFrame: appFrame)\n            // Form lazily mounts offscreen rows; never read a missing row's frame or label.\n            if !element.exists { scroll(app, box: box, appFrame: appFrame, earlier: earlierWhenMissing); continue }\n            let frame = element.frame\n            if element.isHittable && (box.contains(frame) ||\n                (frame.height > box.height && box.intersects(frame))) { return }\n            let distance = abs(frame.midY - box.midY) / box.height\n            let fraction = min(maxScrollFraction, max(0.20, distance))\n            scroll(app, box: box, appFrame: appFrame, earlier: frame.midY < box.midY, fraction: fraction)",
            1,
        ),
        (
            "            let box = bounds(app), frame = element.frame",
            "            let appFrame = app.frame\n            let box = bounds(app, appFrame: appFrame), frame = element.frame",
            2,
        ),
        (
            "            scroll(app, earlier: frame.minY < box.minY)",
            "            scroll(app, box: box, appFrame: appFrame, earlier: frame.minY < box.minY)",
            1,
        ),
    ],
}
COST_ORIGINAL_SHA256 = {
    "LargeTextRecoveryJourneyTests.swift": "7e4f629bf67eb20f63159762e436981a19e89a200772d65bb7b21df9eb97c297",
    "PickerAliasJourneyTests.swift": "50eea733c272411164cda151f5cb7387fb669d6364022c228aec96594deb124d",
    "WatchDiagnosticsJourneyTests.swift": "2d1319539f2648876a5dd8b1e451c66c64651a0c3ad5c27e914980c1d5f8ec1a",
}
COST_PROPOSED_SHA256 = {
    "LargeTextRecoveryJourneyTests.swift": "7082122150c61f86892dd9f6a72582561bba0ac58e2dc1b95b3e2621c5a50106",
    "PickerAliasJourneyTests.swift": "ae6767e2c5563d30604e2f25a574f5ff3c2e20ba22478e8dd6a178161e1d3d1e",
    "WatchDiagnosticsJourneyTests.swift": "21680343a8a45c392958f2b41b6dd2437ba5b5875c13c89c898535314fed9591",
}


def restore_cost_reads(name, text):
    if name == "WatchDiagnosticsJourneyTests.swift":
        text = restore_controls_traversal(text)
    assert digest(text) == COST_PROPOSED_SHA256[name], "Unreviewed cost-reduction scope"
    for old, new, count in reversed(COST_READ_TRANSFORMS[name]):
        assert text.count(new) == count
        text = text.replace(new, old)
    assert digest(text) == COST_ORIGINAL_SHA256[name], "Original obligations changed"
    return text


@pytest.mark.parametrize("name", COST_READ_TRANSFORMS)
def test_cost_reduction_reconstructs_every_original_assertion_capture_and_loop(name):
    raw = (SWIFT / name).read_text()
    restored = restore_cost_reads(name, raw)
    # Raw Swift assertion/capture call lines are not normalized away by the packet.
    for token in (
        "XCTAssert",
        "capture(app,",
        "captureContent(",
        "try captureElement(",
        "for _ in 0..<",
        "for attempt in 0..<",
        "waitForExistence(timeout:",
        "waitForExpectations(timeout:",
    ):
        old_lines = [line.strip() for line in restored.splitlines() if token in line]
        new_lines = [line.strip() for line in raw.splitlines() if token in line]
        assert old_lines == new_lines


@pytest.mark.parametrize("name", COST_READ_TRANSFORMS)
@pytest.mark.parametrize("mutation", ["original", "allowance", "capture", "assertion"])
def test_cost_guard_rejects_original_or_lost_obligations(name, mutation):
    raw = (SWIFT / name).read_text()
    altered = raw
    if mutation == "original":
        altered = restore_cost_reads(name, raw)
    elif mutation == "allowance":
        altered = raw.replace("0..<24", "0..<48").replace("0..<32", "0..<64")
    elif mutation == "capture":
        line = next(line for line in raw.splitlines(True) if "capture(app," in line)
        altered = raw.replace(line, "", 1)
    else:
        altered = raw.replace("XCTAssert", "removedAssertion", 1)
    assert altered != raw
    with pytest.raises(AssertionError):
        restore_cost_reads(name, altered)


def check_large_text_distance_step(text):
    generic = helper_block(text, "reveal")
    assert generic.count(LARGE_TEXT_DISTANCE_STEP) == 1
    assert LARGE_TEXT_FIXED_STEP not in generic
    # Unchanged visibility gate and attempt cap: a larger stride cannot admit a partial node.
    assert "element.isHittable && appFrame.contains(frame)" in generic
    assert "for _ in 0..<32" in generic
    assert "withVelocity: .slow, thenHoldForDuration: 0.4" in generic


def test_large_text_reveal_moves_by_remaining_offset_within_the_window():
    check_large_text_distance_step((SWIFT / "LargeTextRecoveryJourneyTests.swift").read_text())
    # Both endpoints stay inside the window at the clamp's extremes.
    for earlier, origin in ((True, 0.35), (False, 0.75)):
        for fraction in (0.15, 0.50):
            end = origin + fraction if earlier else origin - fraction
            assert 0 < min(origin, end) < max(origin, end) < 1


@pytest.mark.parametrize(
    "old,new",
    [
        (LARGE_TEXT_DISTANCE_STEP, LARGE_TEXT_FIXED_STEP),
        ("appFrame.contains(frame) { return }", "appFrame.intersects(frame) { return }"),
        ("min(0.50, max(0.15, distance / appFrame.height))", "0.50"),
        ("earlier ? 0.35 : 0.75", "earlier ? 0.60 : 0.60"),
        (" || (appFrame.contains(frame) && frame.midY < appFrame.midY)", ""),
    ],
)
def test_large_text_reveal_rejects_fixed_step_partial_visibility_or_unbounded_drag(old, new):
    raw = (SWIFT / "LargeTextRecoveryJourneyTests.swift").read_text()
    assert raw.count(old) == 1
    with pytest.raises(AssertionError):
        check_large_text_distance_step(raw.replace(old, new))
        restore_cost_reads("LargeTextRecoveryJourneyTests.swift", raw.replace(old, new))


def test_large_text_frames_are_measured_once_per_attempt():
    raw = (SWIFT / "LargeTextRecoveryJourneyTests.swift").read_text()
    viewport = helper_block(raw, "changeViewport")
    change = helper_block(raw, "revealChange")
    generic = helper_block(raw, "reveal")
    assert "app.frame" not in viewport
    assert viewport.count("scroll.frame") == viewport.count("bar.frame") == 1
    for helper in (change, generic):
        assert helper.count("let appFrame = app.frame") == 1
        assert helper.index("for _ in 0..<32") < helper.index(
            "let appFrame = app.frame"
        )
    assert "change.isHittable && bounds.contains(frame)" in change
    assert "element.isHittable && appFrame.contains(frame)" in generic


def test_diagnostics_reuses_only_current_attempt_geometry_and_checks_missing_first():
    raw = (SWIFT / "WatchDiagnosticsJourneyTests.swift").read_text()
    reveal = raw.split("private func reveal(", 1)[1].split("    @MainActor", 1)[0]
    assert reveal.count("element.frame") == 1
    assert reveal.index("if !element.exists") < reveal.index(
        "let frame = element.frame"
    )
    assert reveal.index("for _ in 0..<24") < reveal.index("let appFrame = app.frame")
    assert reveal.count("scroll(app, box: box, appFrame: appFrame,") == 2
    capture = raw.split("private func captureContent(", 1)[1].split(
        "    @MainActor", 1
    )[0]
    # The continuation loop remeasures after dragging; never reuse pre-drag frames.
    assert (
        "scroll(app, earlier: false)\n            let appFrame = app.frame" in capture
    )
    scroll = raw.split("private func scroll(_ app: XCUIApplication, box:", 1)[1].split(
        "    @MainActor", 1
    )[0]
    assert "bounds(app" not in scroll and "app.frame" not in scroll


def test_alias_complete_row_keeps_same_capture_and_oversized_overlap_path():
    raw = (SWIFT / "PickerAliasJourneyTests.swift").read_text()
    capture = helper_block(raw, "captureElement")
    assert "let complete = !frame.isNull && !frame.isEmpty" in capture
    for edge in ("minX", "minY", "maxX", "maxY"):
        assert f"frame.{edge}.isFinite" in capture
    assert "&& bounds.contains(frame)" in capture
    assert (
        "if row.isHittable && (complete || (frame.minY >= bounds.minY && frame.minY <= bounds.midY))"
        in capture
    )
    assert 'capture(app, name + " - top")' in capture
    assert "if bounds.contains(frame) { return }" in capture
    assert "XCTAssertLessThanOrEqual(visibleStart, coveredEnd + 1" in capture
    assert "if atBottom { return }" in capture


@pytest.mark.parametrize(
    "name,old,new",
    [
        (
            "LargeTextRecoveryJourneyTests.swift",
            "change.isHittable && bounds.contains(frame)",
            "bounds.intersects(frame)",
        ),
        (
            "LargeTextRecoveryJourneyTests.swift",
            "            let appFrame = app.frame",
            "            let appFrame = cachedFrame",
        ),
        (
            "PickerAliasJourneyTests.swift",
            "&& bounds.contains(frame)",
            "&& bounds.intersects(frame)",
        ),
        ("PickerAliasJourneyTests.swift", "!frame.isNull && !frame.isEmpty", "true"),
        (
            "PickerAliasJourneyTests.swift",
            "visibleStart, coveredEnd + 1",
            "0, coveredEnd + 100",
        ),
        ("WatchDiagnosticsJourneyTests.swift", "if !element.exists", "if false"),
        (
            "WatchDiagnosticsJourneyTests.swift",
            "let frame = element.frame",
            "let frame = cachedFrame",
        ),
        (
            "WatchDiagnosticsJourneyTests.swift",
            '"Refusal must survive relaunch"',
            '"ignored"',
        ),
    ],
)
def test_cost_reduction_refuses_stale_geometry_weakened_fit_or_lost_consent(
    name, old, new
):
    raw = (SWIFT / name).read_text()
    assert old in raw
    with pytest.raises(AssertionError):
        restore_cost_reads(name, raw.replace(old, new))


# Exact selected-game rescope: these face contracts become launcher checks.
# Restore ONLY these blocks before the original retained-navigation hashes.
LAUNCHER_SCOPE_TRANSFORMS = [
    (
        "    }\n\n    @MainActor\n    func testActualCornerLauncherAndTap() throws {\n        continueAfterFailure = false\n        let app = XCUIApplication()\n        let originalObservation = Date().addingTimeInterval(-120)\n",
        "    }\n\n    @MainActor\n    func testActualCornerSavedReadingAndTap() throws {\n        continueAfterFailure = false\n        let app = XCUIApplication()\n        let originalObservation = Date().addingTimeInterval(-120)\n",
    ),
    (
        '        let picker = try assertWidgetWarmPickerIsPresented(in: app)\n        XCUIDevice.shared.press(.home)\n        let host = XCUIApplication(bundleIdentifier: "com.apple.Carousel")\n        let reading = try mountLauncherOnFreshExactographFace(in: host)\n        XCTAssertEqual(reading.label, "Open your selected game in Bain Luck, or choose a game")\n        XCTAssertFalse(host.descendants(matching: .any)["watch.complication.corner.reading"].firstMatch.exists)\n        freshFaceCapture(host, name: "Actual configured Exactograph explicit launcher")\n        try tapActualWidgetHostAndAssertWarmReturn(host: host, widget: reading, app: app,\n            baseline: baseline, tapOrdinal: 1, dismissedOverlays: picker, phase: "Exactograph corner launcher")\n        print("WATCH_UI_ACTUAL_CORNER_LAUNCHER=PASS")\n    }\n\n    @MainActor\n    func testActualCircularLauncherAndTap() throws {\n        continueAfterFailure = false\n        let app = XCUIApplication()\n        app.launchEnvironment = [\n',
        '        let picker = try assertWidgetWarmPickerIsPresented(in: app)\n        XCUIDevice.shared.press(.home)\n        let host = XCUIApplication(bundleIdentifier: "com.apple.Carousel")\n        let reading = try mountSavedCornerOnFreshExactographFace(in: host)\n        XCTAssertEqual(reading.value as? String, "Saved · SF win · 64%")\n        XCTAssertTrue(reading.label.contains("San Francisco Giants") && reading.label.contains("Los Angeles Dodgers") && reading.label.contains("64%"))\n        XCTAssertTrue(reading.label.contains("Observed \\(originalObservation.formatted(date: .abbreviated, time: .shortened))"))\n        // This must be the separate rendered label, not the reading\'s synthesized\n        // accessible value. Missing/ignored/truncated label is an unpaid feature.\n        let curvedLabel = host.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Saved · SF win")).firstMatch\n        try freshFaceRequire(curvedLabel.waitForExistence(timeout: 15)\n                             && curvedLabel.frame.width > 0 && curvedLabel.frame.height > 0\n                             && host.frame.contains(curvedLabel.frame),\n                             "Actual corner lacks complete rendered Saved + named win label", host: host)\n        freshFaceCapture(host, name: "Actual configured Exactograph corner 64 percent and full Saved SF win curve")\n        try tapActualWidgetHostAndAssertWarmReturn(host: host, widget: reading, app: app,\n            baseline: baseline, tapOrdinal: 1, dismissedOverlays: picker, phase: "saved Exactograph corner forecast")\n        print("WATCH_UI_ACTUAL_CORNER_SAVED=PASS")\n    }\n\n    @MainActor\n    func testActualCircularSavedReadingAndTap() throws {\n        continueAfterFailure = false\n        let app = XCUIApplication()\n        app.launchEnvironment = [\n',
    ),
    (
        '        let picker = try assertWidgetWarmPickerIsPresented(in: app)\n        XCUIDevice.shared.press(.home)\n        let host = XCUIApplication(bundleIdentifier: "com.apple.Carousel")\n        let widget = try mountLauncherOnFreshSiriModularFace(in: host)\n        let launcher = widget.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Open your selected game in Bain Luck, or choose a game")).firstMatch\n        try freshFaceRequire(launcher.exists && launcher.frame.width > 0 && launcher.frame.height > 0,\n                             "Configured circular slot lacks a complete explicit launcher", host: host)\n        XCTAssertFalse(widget.descendants(matching: .any)["watch.complication.circular.reading"].firstMatch.exists)\n        freshFaceCapture(host, name: "Actual configured circular explicit launcher")\n        try tapActualWidgetHostAndAssertWarmReturn(host: host, widget: widget, app: app,\n            baseline: baseline, tapOrdinal: 1, dismissedOverlays: picker, phase: "circular launcher")\n        print("WATCH_UI_ACTUAL_CIRCULAR_LAUNCHER=PASS")\n    }\n\n    @MainActor\n',
        '        let picker = try assertWidgetWarmPickerIsPresented(in: app)\n        XCUIDevice.shared.press(.home)\n        let host = XCUIApplication(bundleIdentifier: "com.apple.Carousel")\n        let widget = try mountLauncherOnFreshSiriModularFace(in: host, savedCircular: true)\n        let reading = widget.descendants(matching: .any).matching(NSPredicate(format: "label BEGINSWITH %@", "Saved reading.")).firstMatch\n        try freshFaceRequire(reading.exists && reading.label.contains("San Francisco Giants")\n                             && reading.label.contains("64%") && reading.label.contains("Observed"),\n                             "Configured circular slot lacks full saved named forecast and original observation", host: host)\n        XCTAssertEqual(reading.value as? String, "Saved · SF win · 64%")\n        freshFaceCapture(host, name: "Actual configured circular Saved SF win 64 percent")\n        try tapActualWidgetHostAndAssertWarmReturn(host: host, widget: widget, app: app,\n            baseline: baseline, tapOrdinal: 1, dismissedOverlays: picker, phase: "saved circular forecast")\n        print("WATCH_UI_ACTUAL_CIRCULAR_SAVED=PASS")\n    }\n\n    @MainActor\n',
    ),
    (
        '// current gallery journey. No URL opening, app activation or seeded-face state.\nextension WidgetTapJourneyTests {\n    @MainActor\n    func mountLauncherOnFreshSiriModularFace(in host: XCUIApplication) throws -> XCUIElement {\n        try freshFaceRequire(host.wait(for: .runningForeground, timeout: 15), "Watch host is not foreground", host: host)\n        let face = host.otherElements["Watch Face"].firstMatch\n        try freshFaceRequire(face.waitForExistence(timeout: 15), "No actual Watch Face", host: host)\n',
        '// current gallery journey. No URL opening, app activation or seeded-face state.\nextension WidgetTapJourneyTests {\n    @MainActor\n    func mountLauncherOnFreshSiriModularFace(in host: XCUIApplication, savedCircular: Bool = false) throws -> XCUIElement {\n        try freshFaceRequire(host.wait(for: .runningForeground, timeout: 15), "Watch host is not foreground", host: host)\n        let face = host.otherElements["Watch Face"].firstMatch\n        try freshFaceRequire(face.waitForExistence(timeout: 15), "No actual Watch Face", host: host)\n',
    ),
    (
        '        try activateConfiguredSiriModularFace(in: host)\n        let widget = host.otherElements["bottom-left"].firstMatch\n        try freshFaceRequire(host.wait(for: .runningForeground, timeout: 15)\n                             && widget.waitForExistence(timeout: 15) && widget.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Open your selected game in Bain Luck, or choose a game")).firstMatch.exists\n                             && widget.isHittable && host.frame.contains(widget.frame),\n                             "Fresh installed face has no reachable BainLuckWatch launcher", host: host)\n        freshFaceCapture(host, name: "Fresh face actual mounted BainLuckWatch launcher")\n',
        '        try activateConfiguredSiriModularFace(in: host)\n        let widget = host.otherElements["bottom-left"].firstMatch\n        try freshFaceRequire(host.wait(for: .runningForeground, timeout: 15)\n                             && widget.waitForExistence(timeout: 15) && widget.descendants(matching: .any).matching(savedCircular\n                                ? NSPredicate(format: "label BEGINSWITH %@", "Saved reading.")\n                                : NSPredicate(format: "label == %@", "Open your selected game in Bain Luck, or choose a game")).firstMatch.exists\n                             && widget.isHittable && host.frame.contains(widget.frame),\n                             "Fresh installed face has no reachable BainLuckWatch launcher", host: host)\n        freshFaceCapture(host, name: "Fresh face actual mounted BainLuckWatch launcher")\n',
    ),
    (
        '    }\n\n    @MainActor\n    private func mountLauncherOnFreshExactographFace(in host: XCUIApplication) throws -> XCUIElement {\n        try freshFaceRequire(host.wait(for: .runningForeground, timeout: 15), "Corner host not foreground", host: host)\n        let face = host.otherElements["Watch Face"].firstMatch\n        try freshFaceRequire(face.waitForExistence(timeout: 15), "No actual corner Watch Face", host: host)\n',
        '    }\n\n    @MainActor\n    private func mountSavedCornerOnFreshExactographFace(in host: XCUIApplication) throws -> XCUIElement {\n        try freshFaceRequire(host.wait(for: .runningForeground, timeout: 15), "Corner host not foreground", host: host)\n        let face = host.otherElements["Watch Face"].firstMatch\n        try freshFaceRequire(face.waitForExistence(timeout: 15), "No actual corner Watch Face", host: host)\n',
    ),
    (
        '        let activated = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in face.exists && !library.exists }, object: host)\n        try freshFaceRequire(XCTWaiter.wait(for: [activated], timeout: 15) == .completed,\n                             "Configured Exactograph did not become active", host: host)\n        let reading = host.descendants(matching: .any)["watch.complication.corner.fallback"].firstMatch\n        try freshFaceRequire(reading.waitForExistence(timeout: 15) && reading.isHittable && host.frame.contains(reading.frame),\n                             "Actual configured Exactograph has no fitting explicit launcher", host: host)\n        return reading\n    }\n\n',
        '        let activated = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in face.exists && !library.exists }, object: host)\n        try freshFaceRequire(XCTWaiter.wait(for: [activated], timeout: 15) == .completed,\n                             "Configured Exactograph did not become active", host: host)\n        let reading = host.descendants(matching: .any)["watch.complication.corner.reading"].firstMatch\n        try freshFaceRequire(reading.waitForExistence(timeout: 15) && reading.isHittable && host.frame.contains(reading.frame),\n                             "Actual configured Exactograph has no fitting saved corner forecast", host: host)\n        return reading\n    }\n\n',
    ),
]


def restore_launcher_scope(text):
    for current, previous in LAUNCHER_SCOPE_TRANSFORMS:
        assert text.count(current) == 1, "Missing or altered launcher scope block"
        text = text.replace(current, previous, 1)
    return text


def test_launcher_scope_normalization_rejects_missing_retained_tap_assertion():
    raw = (SWIFT / "WidgetTapJourneyTests.swift").read_text()
    with pytest.raises(AssertionError):
        restore_launcher_scope(
            raw.replace(
                'tapOrdinal: 1, dismissedOverlays: picker, phase: "Exactograph corner launcher"',
                "REMOVED_TAP_ASSERTION",
                1,
            )
        )


# Bounded 756d controls correction. Normalize ONLY these traversal changes
# before existing original cost/assertion hashes; lifecycle adds fatal cleanup checks.
CONTROLS_TRAVERSAL = [
    (
        "try reveal(more, app: app)",
        "try reveal(more, app: app, maxScrollFraction: 0.55)",
        1,
    ),
    (
        "try reveal(choice, app: app, earlierWhenMissing: true)",
        "try reveal(choice, app: app, earlierWhenMissing: true, maxScrollFraction: 0.55)",
        2,
    ),
    (
        "if !element.exists { scroll(app, box: box, appFrame: appFrame, earlier: earlierWhenMissing); continue }",
        "if !element.exists { scroll(app, box: box, appFrame: appFrame, earlier: earlierWhenMissing, fraction: maxScrollFraction); continue }",
        1,
    ),
]
FLAT_CLEANUP = '        defer {\n            // Let the selected-game foreground task cancel through its normal\n            // scene transition before asking XCTest to terminate this process.\n            // A failed transition or termination still fails this case.\n            XCUIDevice.shared.press(.home)\n            let backgrounded = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in\n                let state = app.state\n                return state == .runningBackground || state == .runningBackgroundSuspended || state == .notRunning\n            }, object: app)\n            XCTAssertEqual(XCTWaiter.wait(for: [backgrounded], timeout: 5), .completed,\n                           "Layout fixture must leave foreground before cleanup")\n            if app.state != .notRunning { app.terminate() }\n            XCTAssertEqual(app.state, .notRunning, "Layout fixture cleanup must stop the app")\n        }\n'
FLAT_ORIGINAL_CLEANUP = "        defer { app.terminate() }\n"
FLAT_ORIGINAL_SHA256 = (
    "81714894e7b460b17173ff0db17b7a158ef315d884e48d4c9e5b745f83bb062b"
)


def restore_controls_traversal(text):
    for previous, current, count in reversed(CONTROLS_TRAVERSAL):
        assert text.count(current) == count, "Unreviewed diagnostics traversal"
        text = text.replace(current, previous)
    return text


def require_flat_cleanup(raw):
    assert (
        raw.count(FLAT_CLEANUP) == 1
    ), "Cleanup transition must be exact and fail closed"
    restored = raw.replace(FLAT_CLEANUP, FLAT_ORIGINAL_CLEANUP, 1)
    assert (
        digest(restored) == FLAT_ORIGINAL_SHA256
    ), "Layout assertions, captures or other cases changed"


def test_flat_cleanup_preserves_whole_original_file_and_fails_closed():
    raw = (SWIFT / "PickerCurrentGameJourneyTests.swift").read_text()
    require_flat_cleanup(raw)
    ordered = [
        "XCUIDevice.shared.press(.home)",
        "let backgrounded =",
        "XCTWaiter.wait(for: [backgrounded], timeout: 5)",
        "if app.state != .notRunning { app.terminate() }",
        "XCTAssertEqual(app.state, .notRunning",
    ]
    positions = [FLAT_CLEANUP.index(part) for part in ordered]
    assert positions == sorted(positions)
    for bypass in (
        "try?",
        "catch",
        "record(",
        "XCTSkip",
        "continueAfterFailure = true",
    ):
        assert bypass not in FLAT_CLEANUP


@pytest.mark.parametrize(
    "required",
    [
        "XCUIDevice.shared.press(.home)",
        "state == .runningBackground || state == .runningBackgroundSuspended || state == .notRunning",
        "XCTWaiter.wait(for: [backgrounded], timeout: 5)",
        "if app.state != .notRunning { app.terminate() }",
        'XCTAssertEqual(app.state, .notRunning, "Layout fixture cleanup must stop the app")',
        'XCTAssertEqual(probability.label, "Association Sportive de Saint-Étienne Full Canonical Name win probability, 64%")',
    ],
)
def test_cleanup_or_retained_content_cannot_be_dropped(required):
    raw = (SWIFT / "PickerCurrentGameJourneyTests.swift").read_text()
    assert required in raw
    with pytest.raises(AssertionError):
        require_flat_cleanup(raw.replace(required, "REMOVED", 1))


def test_original_foreground_only_cleanup_is_rejected():
    raw = (SWIFT / "PickerCurrentGameJourneyTests.swift").read_text()
    with pytest.raises(AssertionError):
        require_flat_cleanup(raw.replace(FLAT_CLEANUP, FLAT_ORIGINAL_CLEANUP))


def test_distant_controls_use_existing_bounded_reveal_without_bypassing_content():
    raw = (SWIFT / "WatchDiagnosticsJourneyTests.swift").read_text()
    restored = restore_controls_traversal(raw)
    assert (
        digest(restored) == COST_PROPOSED_SHA256["WatchDiagnosticsJourneyTests.swift"]
    )
    # Disclosure captures, consent assertions, three launches and terminations
    # remain exact. Only navigation call arguments and absent-row stride differ.
    for token in (
        "XCTAssert",
        "capture(app,",
        "captureContent(",
        "app.launch()",
        "app.terminate()",
        "for _ in 0..<24",
    ):
        assert [line.strip() for line in raw.splitlines() if token in line] == [
            line.strip() for line in restored.splitlines() if token in line
        ]
    reveal = raw.split("private func reveal(", 1)[1].split("    @MainActor", 1)[0]
    assert "for _ in 0..<24" in reveal
    assert reveal.index("if !element.exists") < reveal.index(
        "let frame = element.frame"
    )
    assert "let fraction = min(maxScrollFraction, max(0.20, distance))" in reveal
    assert "element.isHittable && (box.contains(frame) ||" in reveal
    assert "(frame.height > box.height && box.intersects(frame)))" in reveal


@pytest.mark.parametrize("index", range(3))
def test_each_distant_traversal_change_is_required(index):
    raw = (SWIFT / "WatchDiagnosticsJourneyTests.swift").read_text()
    previous, current, count = CONTROLS_TRAVERSAL[index]
    with pytest.raises(AssertionError):
        restore_controls_traversal(raw.replace(current, previous))


def test_large_and_small_drag_endpoints_stay_inside_measured_viewport():
    raw = (SWIFT / "WatchDiagnosticsJourneyTests.swift").read_text()
    assert "fraction > 0.20 ? (earlier ? 0.20 : 0.80) : 0.60" in raw
    assert "box.height * (earlier ? fraction : -fraction)" in raw
    # Synthetic geometry checks the unchanged gesture formula, not UI runtime.
    for earlier in (False, True):
        for fraction in (0.20, 0.21, 0.35, 0.55):
            start = (0.20 if earlier else 0.80) if fraction > 0.20 else 0.60
            end = start + (fraction if earlier else -fraction)
            assert 0 < start < 1 and 0 < end < 1
    assert 186 * 0.55 > 186 * 0.20
