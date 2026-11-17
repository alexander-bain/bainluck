#if os(iOS) && canImport(ActivityKit)
import XCTest
import SwiftUI
import UIKit
@testable import Bain_Luck

/// #12827: the real control drawn at 390 pt. Normal is one button row ("Start
/// Live Activity" or "Stop Live Activity") and nothing under it; only a failure
/// adds one plain line. Set TEST_RUNNER_BAINLUCK_RENDER_DIR to keep the PNGs.
@MainActor final class GameActivityControlRender12827Tests: XCTestCase {
    private final class Service: GameActivityServing {
        var isEnabled = true
        var records: [GameActivityRecord] = []
        var requestFails = false
        func request(_ snapshot: GameActivitySnapshot, staleDate: Date) throws {
            if requestFails { throw NSError(domain: "Render12827", code: 1) }
            records.append(GameActivityRecord(id: "a-\(snapshot.eventID)", eventID: snapshot.eventID, snapshot: snapshot))
        }
        func update(id: String, snapshot: GameActivitySnapshot, staleDate: Date) async {}
        func end(id: String, final: GameActivitySnapshot?) async {}
    }

    private func snapshot(_ id: Int) throws -> GameActivitySnapshot {
        try XCTUnwrap(GameActivitySnapshot(eventID: id, homeTeam: "Boston Celtics", awayTeam: "Orlando Magic",
                                           status: "live", homeScore: 54, awayScore: 49, homeProbability: 0.71,
                                           sport: "basketball_nba", scoreObservedAt: nil, probabilityObservedAt: nil))
    }

    private func render(_ name: String, _ snapshot: GameActivitySnapshot,
                        _ controller: GameActivityController) throws -> CGSize {
        let view = GameActivityControl(snapshot: snapshot, controller: controller)
            .environment(\.scenePhase, .active)
            .padding(.horizontal, 16).padding(.vertical, 8)
            .frame(width: 390, alignment: .leading)
            .background(Color(uiColor: .systemBackground))
        let renderer = ImageRenderer(content: view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, name)
        if let dir = ProcessInfo.processInfo.environment["BAINLUCK_RENDER_DIR"], !dir.isEmpty {
            try image.pngData()?.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"))
        }
        return image.size
    }

    func testNormalIsOneButtonRowAndOnlyAFailureAddsALine() throws {
        let game = try snapshot(1)

        let idle = Service()
        let start = try render("1-start", game, GameActivityController(service: idle, isForeground: { true }))

        let running = Service()
        let stopController = GameActivityController(service: running, isForeground: { true })
        stopController.start(snapshot: game)
        XCTAssertEqual(stopController.activeEventIDs, [1])
        XCTAssertNil(stopController.status(for: 1), "success prints nothing")
        let stop = try render("2-stop", game, stopController)

        let failing = Service()
        failing.requestFails = true
        let failController = GameActivityController(service: failing, isForeground: { true })
        failController.start(snapshot: game)
        XCTAssertEqual(failController.status(for: 1), "Couldn't start the Live Activity. Try again.")
        let failed = try render("3-failed", game, failController)

        let other = Service()
        let otherController = GameActivityController(service: other, isForeground: { true })
        otherController.start(snapshot: try snapshot(2))
        let blocked = try render("4-other-game", game, otherController)

        XCTAssertEqual(start.height, stop.height, accuracy: 0.5, "Start and Stop are the same single row")
        XCTAssertGreaterThan(failed.height, start.height + 8, "a failure adds its one line")
        XCTAssertGreaterThan(blocked.height, start.height + 8, "another game's activity adds its one line")
        XCTAssertLessThan(failed.height, start.height + 40, "one line, not a paragraph")
    }
}
#endif
