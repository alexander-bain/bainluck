"""The configured Modular library preview cannot stand in for an active face."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_rectangular_host_activates_named_face_before_accepting_widget_content():
    source = (
        ROOT
        / "ios/Bain Luck/BainLuckWatchUITests/RectangularWidgetHostJourneyTests.swift"
    ).read_text()
    call = source.index("try activateConfiguredModularFace(in: host)")
    assert source.index("installed.tap()") < call < source.index("let center =")
    helper = source[
        source.index("private func activateConfiguredModularFace") : source.index(
            "private func swipeLeft"
        )
    ]
    for requirement in [
        "library.exists || face.exists",
        "if library.exists",
        'title.label == "Modular"',
        '"modular, Customizable"',
        "previews.count == 1",
        "preview.isHittable",
        "preview.tap()",
        "face.exists && !library.exists",
        "face.isHittable",
    ]:
        assert requirement in helper
    assert source.count("XCUIDevice.shared.press(.home)") == 2
    for assertion in [
        'XCTAssertEqual(title.label, "San Francisco Giants win")',
        'XCTAssertEqual(detail.label, "Saved · 64% · Live")',
        "contentBounds.contains(text.frame)",
        "center.isHittable",
    ]:
        assert assertion in source
