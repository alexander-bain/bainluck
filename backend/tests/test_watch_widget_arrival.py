"""Widget navigation must wait for actual destination and unobscured Add."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_gallery_waits_for_complete_parent_or_detail_before_normalization():
    source = (
        ROOT / "ios/Bain Luck/BainLuckWatchUITests/WidgetTapJourneyTests.swift"
    ).read_text()
    helper = source.split("static func bainLuckAppRow", 1)[1].split(
        "static func requireBainLuckDetail", 1
    )[0]
    arrival = helper.index("let arrived = XCTNSPredicateExpectation")
    assert arrival < helper.index("for _ in 0..<3")
    for requirement in [
        "detailPage.exists && details.firstMatch.exists && back.exists",
        "parentPage.exists && appRows.firstMatch.exists && !detailPage.exists && !back.exists",
        "return retainedDetail || appGallery",
        "XCTWaiter.wait(for: [arrived], timeout: 15) == .completed",
        "parentPage.waitForExistence(timeout: 15)",
        "for step in 0..<32",
        "visits[position, default: 0] <= 3",
    ]:
        assert requirement in helper


def test_modular_add_is_below_real_chrome_and_editor_arrives_before_swipes():
    source = (
        ROOT
        / "ios/Bain Luck/BainLuckWatchUITests/RectangularWidgetHostJourneyTests.swift"
    ).read_text()
    assert "try reveal(add, in: host, belowNavigationChrome: true)" in source
    assert (
        source.index("add.tap()")
        < source.index("XCTWaiter.wait(for: [editorArrived], timeout: 15)")
        < source.index("for _ in 0..<8")
    )
    for requirement in [
        '"identifier BEGINSWITH %@", "ActiveEditMode-"',
        '"label ==[c] %@", "modular"',
        "editors.count == 1 && namedEditors.count == 1 && !library.exists",
        "app.navigationBars.allElementsBoundByIndex",
        "bar.exists && bar.frame.intersects(app.frame)",
        "element.frame.minY > chromeBottom",
        "element.frame.minY <= chromeBottom",
        "app.frame.contains(element.frame)",
        "slot.exists && slot.isHittable && host.frame.contains(slot.frame)",
        'XCTAssertEqual(modular.buttons.matching(identifier: "Add").count, 1)',
        'let modular = host.cells["Modular"].firstMatch',
    ]:
        assert requirement in source


def test_siri_modular_library_reentry_is_named_once_and_swipes_stay_bounded():
    source = (
        ROOT / "ios/Bain Luck/BainLuckWatchUITests/WidgetTapJourneyTests.swift"
    ).read_text()
    helper = source.split("private func requireSiriModularEditor", 1)[1].split(
        "private func activateConfiguredSiriModularFace", 1
    )[0]
    for requirement in [
        '"ActiveEditMode-"',
        '"siri modular"',
        "editors.count == 1 || library.exists",
        "if library.exists",
        "freshFaceRequire(!didReenter",
        'title.label == "Siri Modular"',
        '"siri modular, Customizable"',
        "previews.count == 1",
        "preview.isHittable",
        "edits.count == 1 && edit.isHittable && host.frame.contains(edit.frame)",
        "didReenter = true",
        "edit.tap()",
        "editors.count == 1 && namedEditors.count == 1 && !library.exists",
        "XCTWaiter.wait(for: [editing], timeout: 15) == .completed",
    ]:
        assert requirement in helper
    mount = source.split("var didReenterEditor = false", 1)[1].split("slot.tap()", 1)[0]
    assert "for _ in 0..<8" in mount
    assert mount.index("requireSiriModularEditor") < mount.index("freshFaceSwipeLeft")
    assert "slot.exists && slot.isHittable && host.frame.contains(slot.frame)" in mount
