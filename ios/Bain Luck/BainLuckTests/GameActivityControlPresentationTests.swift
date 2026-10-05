#if os(iOS) && canImport(ActivityKit)
import XCTest
@testable import Bain_Luck

final class GameActivityControlPresentationTests: XCTestCase {
    func testFinishedPageHasNoStartControlButActiveFinalCanStillStop() {
        let ended = GameActivityControlPresentation(isPhone: true, isEnabled: true,
                                                   isTerminal: true, isActive: false)
        XCTAssertFalse(ended.showsControl)
        XCTAssertFalse(ended.showsUpdateNote)
        let finishing = GameActivityControlPresentation(isPhone: true, isEnabled: true,
                                                       isTerminal: true, isActive: true)
        XCTAssertTrue(finishing.showsControl)
        XCTAssertFalse(finishing.showsUpdateNote)
    }

    func testUnsupportedOrDisabledSurfaceHasNoActivityChrome() {
        for active in [false, true] {
            XCTAssertFalse(GameActivityControlPresentation(isPhone: false, isEnabled: true,
                isTerminal: false, isActive: active).showsControl)
            XCTAssertFalse(GameActivityControlPresentation(isPhone: true, isEnabled: false,
                isTerminal: false, isActive: active).showsControl)
        }
    }

    func testUpdateCaveatAppearsOnlyAfterStartingThisGame() {
        let idle = GameActivityControlPresentation(isPhone: true, isEnabled: true,
                                                  isTerminal: false, isActive: false)
        XCTAssertTrue(idle.showsControl)
        XCTAssertFalse(idle.showsUpdateNote)
        let active = GameActivityControlPresentation(isPhone: true, isEnabled: true,
                                                    isTerminal: false, isActive: true)
        XCTAssertTrue(active.showsControl)
        XCTAssertTrue(active.showsUpdateNote)
    }
}
#endif
