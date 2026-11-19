import XCTest
import UIKit
@testable import Bain_Luck

/// The Live Activity's crests: fetched by the app while the game page is open,
/// one file per side of each game, read back by the activity's views.
final class GameActivityCrestsTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent("crests-\(UUID().uuidString)")
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    private static func png(_ color: UIColor) -> Data {
        UIGraphicsImageRenderer(size: CGSize(width: 300, height: 300)).pngData { context in
            color.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 300, height: 300))
        }
    }

    func testBothCrestsAreKeptUnderTheGameAndShrunk() async throws {
        let away = URL(string: "https://example.com/ne.png")!
        let home = URL(string: "https://example.com/det.png")!
        let bytes: [URL: Data] = [away: Self.png(.red), home: Self.png(.blue)]
        await GameActivityCrests.prefetch(eventID: 42, away: away, home: home, directory: directory,
                                          fetch: { bytes[$0] })
        let a = try XCTUnwrap(GameActivityCrests.image(eventID: 42, home: false, directory: directory))
        let h = try XCTUnwrap(GameActivityCrests.image(eventID: 42, home: true, directory: directory))
        XCTAssertLessThanOrEqual(max(a.size.width * a.scale, a.size.height * a.scale), 144)
        XCTAssertLessThanOrEqual(max(h.size.width * h.scale, h.size.height * h.scale), 144)
        XCTAssertNil(GameActivityCrests.data(eventID: 43, home: true, directory: directory), "another game has none")
    }

    func testAMissingCrestLeavesNoFileAndAPlainURLIsRefused() async {
        let http = URL(string: "http://example.com/ne.png")!
        await GameActivityCrests.prefetch(eventID: 7, away: http, home: nil, directory: directory,
                                          fetch: { _ in Self.png(.red) })
        XCTAssertNil(GameActivityCrests.data(eventID: 7, home: false, directory: directory))
        XCTAssertNil(GameActivityCrests.data(eventID: 7, home: true, directory: directory))
    }

    func testFilesOlderThanAWeekAreRemoved() throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let old = GameActivityCrests.file(eventID: 1, home: true, in: directory)
        let fresh = GameActivityCrests.file(eventID: 2, home: true, in: directory)
        try Self.png(.red).write(to: old)
        try Self.png(.red).write(to: fresh)
        let now = Date()
        try FileManager.default.setAttributes([.modificationDate: now.addingTimeInterval(-8 * 86_400)], ofItemAtPath: old.path)
        GameActivityCrests.prune(directory, now: now)
        XCTAssertFalse(FileManager.default.fileExists(atPath: old.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: fresh.path))
    }

    func testThePageUsesItsServedCrestElseTheESPNCrest() {
        XCTAssertEqual(EventDetailView.activityCrestURL(served: "https://cdn.example/x.png", team: "Detroit Lions")?.host,
                       "cdn.example")
        XCTAssertEqual(EventDetailView.activityCrestURL(served: nil, team: "Detroit Lions")?.host, "a.espncdn.com")
        XCTAssertNil(EventDetailView.activityCrestURL(served: nil, team: "Nobody FC"))
    }
}
