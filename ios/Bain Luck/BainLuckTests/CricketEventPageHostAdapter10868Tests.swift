import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the cricket Test-match host glue: which events get the screen, and
/// the pure `build` the host recomputes on every pass. On the retained REAL
/// bodies of `CricketEventPageAdapter10868Tests` and
/// `CricketOriginalsAdapter10868Tests` (paths and sha256 values there).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// CONSTRUCTED, one key each and named where used: `sport` set to
/// `cricket_test_match` or `cricket_odi`; `status` set to `live`. The reader's
/// calendar, `now` and the displayed probability clock are host values.
@MainActor
final class CricketEventPageHostAdapter10868Tests: XCTestCase {
    private typealias Fixtures = CricketEventPageAdapter10868Tests
    private typealias Host = CricketEventPageHost10868

    func testOnlyATestMatchGetsThisScreen() throws {
        XCTAssertFalse(Host.applies(try Fixtures.detail(Fixtures.pakistanSriLanka)), "International T20: the cricket-t20 route")
        XCTAssertTrue(Host.applies(try Fixtures.detail(Fixtures.pakistanSriLanka, setting: "sport", to: "cricket_test_match")))
        XCTAssertFalse(Host.applies(try Fixtures.detail(Fixtures.pakistanSriLanka, setting: "sport", to: "cricket_odi")))
        XCTAssertFalse(Host.applies(try Fixtures.detail(Fixtures.pakistanSriLanka, setting: "sport", to: NSNull())))
    }

    /// CONSTRUCTED: `sport` set to `cricket_test_match`. Without a history response
    /// the page still composes its title, headline and originals; only the history
    /// says it is unavailable.
    func testWithoutAHistoryResponseThePageStillComposes() throws {
        let event = try Fixtures.detail(Fixtures.pakistanSriLanka, setting: "sport", to: "cricket_test_match")
        let now = Fixtures.capturedAt.asDate!
        let built = Host.build(event: event, history: nil, markets: nil, probabilityObservedAt: nil, now: now,
                               calendar: Fixtures.pacific, locale: Locale(identifier: "en_US"))
        XCTAssertEqual(built.input.history, CricketHistoryAdapter10868.unavailable(event))
        XCTAssertEqual(built.input.phase, .during)
        XCTAssertEqual(built.input.headline.rows.count, 3)
        XCTAssertEqual(built.input.headline.rows[0].before.observation?.text, "67%")
        XCTAssertEqual(built.input.title.title, "Pakistan · Sri Lanka")
        XCTAssertNil(built.originals.catalogue)
        XCTAssertNil(built.input.copy.allPropsLabel)
        XCTAssertNotNil(built.input.about)
        XCTAssertNil(built.input.stream)
    }

    /// The build reads every value it is handed, every pass: the same body read
    /// with a fresh displayed clock and with a stale one says two different things.
    /// CONSTRUCTED: `status` set to `live`.
    func testTheBuildFollowsEveryPassedValueWithNoMemo() throws {
        let event = try Fixtures.detail(Fixtures.pakistanSriLanka, setting: "status", to: "live")
        let observed = "2026-10-11T15:52:33.190244+00:00".asDate
        func label(at now: String) -> String {
            Host.build(event: event, history: nil, markets: nil, probabilityObservedAt: observed, now: now.asDate!,
                       calendar: Fixtures.pacific, locale: Locale(identifier: "en_US")).input.headline.comparisonLabel
        }
        XCTAssertEqual(label(at: "2026-10-11T15:55:00+00:00"), "Current")
        XCTAssertEqual(label(at: "2026-10-11T17:00:00+00:00"), "Last recorded")
        let reading = Host.Reading(story: .shifts, selection: nil, readerOpen: true, wide: true)
        let held = Host.build(event: event, history: nil, markets: nil, probabilityObservedAt: observed,
                              now: "2026-10-11T15:55:00+00:00".asDate!, reading: reading,
                              calendar: Fixtures.pacific, locale: Locale(identifier: "en_US"))
        XCTAssertEqual(held.input.stream?.readerOpen, true)
        XCTAssertEqual(held.input.stream?.wide, true)
        XCTAssertEqual(held.input.stream?.primary?.id, "shifts")
    }

    func testEveryPresentedModeHasItsOwnIdentity() {
        let ids = [
            Host.Presented(mode: .page).id,
            Host.Presented(mode: .reader(.history)).id,
            Host.Presented(mode: .reader(.shifts)).id,
            Host.Presented(mode: .catalogue).id,
            Host.Presented(mode: .original).id,
            Host.Presented(mode: .about).id,
        ]
        XCTAssertEqual(Set(ids).count, ids.count)
    }
}
