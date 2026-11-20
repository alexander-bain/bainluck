#if os(iOS) && canImport(ActivityKit)
import XCTest
@testable import Bain_Luck

final class GameActivityControlPresentationTests: XCTestCase {
    func testFinishedPageHasNoStartControlButActiveFinalCanStillStop() {
        let ended = GameActivityControlPresentation(isPhone: true, isEnabled: true,
                                                   isTerminal: true, isActive: false)
        XCTAssertFalse(ended.showsControl)
        let finishing = GameActivityControlPresentation(isPhone: true, isEnabled: true,
                                                       isTerminal: true, isActive: true)
        XCTAssertTrue(finishing.showsControl)
    }

    func testUnsupportedOrDisabledSurfaceHasNoActivityChrome() {
        for active in [false, true] {
            XCTAssertFalse(GameActivityControlPresentation(isPhone: false, isEnabled: true,
                isTerminal: false, isActive: active).showsControl)
            XCTAssertFalse(GameActivityControlPresentation(isPhone: true, isEnabled: false,
                isTerminal: false, isActive: active).showsControl)
        }
    }

    func testTheControlShowsBeforeAndAfterStartingThisGame() {
        let idle = GameActivityControlPresentation(isPhone: true, isEnabled: true,
                                                  isTerminal: false, isActive: false)
        XCTAssertTrue(idle.showsControl)
        let active = GameActivityControlPresentation(isPhone: true, isEnabled: true,
                                                    isTerminal: false, isActive: true)
        XCTAssertTrue(active.showsControl)
    }

    /// #12827 (Alex, TestFlight 5733): "We don't need a wall of grey text when
    /// someone wants a Live Activity." No standing note, no success sentence,
    /// and never the word "stale".
    func testTheControlCarriesNoStandingNoteOrStaleWording() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let control = try String(contentsOf: root.appendingPathComponent("Bain Luck/Components/GameActivityControl.swift"), encoding: .utf8)
        let controller = try String(contentsOf: root.appendingPathComponent("Bain Luck/Services/GameActivityController.swift"), encoding: .utf8)
        for removed in ["can become stale", "Updates while this game is open", "Updates arrive while this game is open"] {
            XCTAssertFalse(control.contains(removed), removed)
            XCTAssertFalse(controller.contains(removed), removed)
        }
        XCTAssertFalse(control.lowercased().contains("stale"))
    }
}
#endif
