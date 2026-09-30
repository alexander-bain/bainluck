import XCTest
@testable import Bain_Luck

/// #9777 — the Sports tab's red "N live" badge counts games being played.
///
/// On 2026-09-30 09:15Z the badge read "1 live" on every screen of the app. Its
/// only row was Luca Borando v Ian Escuza (`15320966`, `status=suspended`),
/// whose own card said "No result reported" under "Live & Paused". The badge
/// was `liveNow.count`, and `liveNow` holds `suspended` on purpose — the section
/// keeps it so the header can say "Live & Paused". These tests pin both halves:
/// the badge drops it, the section still has it.
@MainActor
final class TabBadgeLiveCount9777Tests: XCTestCase {

    private func item(id: Int, status: String) throws -> FeedItem {
        let json = """
        {"type":"event","score":80,"data":{"id":\(id),"sport":"mma_mixed_martial_arts",
         "home_team":"Home \(id)","away_team":"Away \(id)","status":"\(status)",
         "commence_time":"2026-09-29T23:40:00Z"}}
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedItem.self, from: Data(json.utf8))
    }

    /// The specimen: one suspended row, nothing live ⇒ no badge.
    func testASuspendedRowAloneLightsNoBadge() throws {
        let items = [try item(id: 15320966, status: "suspended")]
        XCTAssertEqual(FeedViewModel.tabBadgeLiveCount(items), 0)
        // The section rule is untouched: the row still files under live, so
        // the header can say "Live & Paused" over it.
        XCTAssertEqual(EventState.section(items[0].event?.status), .live)
    }

    /// Mixed: only the `live` rows count; suspended, scheduled and finished don't.
    func testOnlyLiveRowsCount() throws {
        let items = [
            try item(id: 1, status: "live"),
            try item(id: 2, status: "suspended"),
            try item(id: 3, status: "live"),
            try item(id: 4, status: "scheduled"),
            try item(id: 5, status: "completed"),
        ]
        XCTAssertEqual(FeedViewModel.tabBadgeLiveCount(items), 2)
    }

    /// Both assignment sites of the published count read the badge rule, not
    /// the section bucket — a third `liveNow.count` would bring the defect back.
    func testBothAssignmentSitesUseTheBadgeRule() throws {
        let src = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent().deletingLastPathComponent()
                .appendingPathComponent("Bain Luck/ViewModels/FeedViewModel.swift"),
            encoding: .utf8)
        XCTAssertFalse(src.contains("liveCount = liveNow.count"))
        XCTAssertEqual(
            src.components(separatedBy: "liveCount = Self.tabBadgeLiveCount(items)").count - 1, 2)
    }
}
