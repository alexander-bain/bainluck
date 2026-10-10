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


def source(name):
    return (SWIFT / name).read_text()


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
