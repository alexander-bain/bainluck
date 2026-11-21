import XCTest
import ImageIO
#if canImport(UIKit)
import UIKit
#endif
@testable import Bain_Luck

final class WatchComplicationDiagnosis13339Tests: XCTestCase {
    private let utc = TimeZone(identifier: "UTC")!

    private func makeSolidPNG(width: Int, height: Int) throws -> Data {
        #if canImport(UIKit)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1.0
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: width, height: height), format: format)
        let image = renderer.image { ctx in
            UIColor.red.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
        }
        return try XCTUnwrap(image.pngData())
        #else
        throw XCTSkip("UIKit unavailable on this platform")
        #endif
    }

    func testOversized500pxCrestIsDownsampledOnCacheAndInComplicationImage() async throws {
        #if canImport(UIKit)
        let bigPNG = try makeSolidPNG(width: 500, height: 500)
        let dims = try XCTUnwrap(WatchMatchupCrests217.pixelDimensions(of: bigPNG))
        XCTAssertEqual(dims.width, 500)
        XCTAssertEqual(dims.height, 500)
        XCTAssertFalse(WatchMatchupCrests217.isWithinPixelLimit(bigPNG))

        let prepared = WatchMatchupCrests217.prepareForCache(bigPNG)
        let preparedDims = try XCTUnwrap(WatchMatchupCrests217.pixelDimensions(of: prepared))
        XCTAssertLessThanOrEqual(max(preparedDims.width, preparedDims.height), WatchMatchupCrests217.maxPixelSize)
        XCTAssertLessThan(prepared.count, bigPNG.count)

        let rendered = try XCTUnwrap(WatchMatchupCrests217.complicationImage(from: bigPNG))
        XCTAssertLessThanOrEqual(rendered.size.width * rendered.scale, CGFloat(WatchMatchupCrests217.complicationMaxPixelSize))
        XCTAssertLessThanOrEqual(rendered.size.height * rendered.scale, CGFloat(WatchMatchupCrests217.complicationMaxPixelSize))
        XCTAssertEqual(rendered.scale, 2.0)

        // Pre-existing 500x500 cached file (e.g. from build 5844) must shrink in place on fetchMissing.
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("crest13339-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        try bigPNG.write(to: WatchMatchupCrests217.file(teamID: 15326, in: dir))

        let repaired = await WatchMatchupCrests217.fetchMissing(
            [(teamID: 15326, logo: "https://a.espncdn.com/i/teamlogos/ncaa/500/24.png")],
            directory: dir,
            fetch: { _ in
                XCTFail("Repairing an already-cached oversized PNG must not hit the network")
                return nil
            }
        )
        XCTAssertTrue(repaired)
        let updatedBytes = try XCTUnwrap(WatchMatchupCrests217.data(teamID: 15326, directory: dir))
        let updatedDims = try XCTUnwrap(WatchMatchupCrests217.pixelDimensions(of: updatedBytes))
        XCTAssertLessThanOrEqual(max(updatedDims.width, updatedDims.height), WatchMatchupCrests217.maxPixelSize)

        let secondPass = await WatchMatchupCrests217.fetchMissing(
            [(teamID: 15326, logo: "https://a.espncdn.com/i/teamlogos/ncaa/500/24.png")],
            directory: dir,
            fetch: { _ in nil }
        )
        XCTAssertFalse(secondPass, "Already-shrunk cached crest must not trigger another reload")
        #endif
    }

    func testMatchupTimelineDatesStayMinimalAcrossStages() {
        let now = Date(timeIntervalSinceReferenceDate: 100_000)
        let cal = WatchCompactTeamIdentity(teamID: 81, abbreviation: "CAL")
        let stan = WatchCompactTeamIdentity(teamID: 15326, abbreviation: "STAN")

        let schedReading = WatchRectangularReading(
            version: 1,
            eventID: 15349272,
            kind: .scheduledForecast,
            homeName: "California",
            awayName: "Stanford",
            home: cal,
            away: stan,
            homePercent: 43,
            homeScore: nil,
            awayScore: nil,
            commenceTime: now.addingTimeInterval(2 * 86_400),
            stateLabel: "Scheduled",
            observedAt: now.addingTimeInterval(-60),
            scoreObservedAt: nil
        )
        let schedSnap = WatchComplicationSnapshot(
            eventID: 15349272,
            title: "California win",
            detail: "43% · Scheduled",
            observedAt: schedReading.observedAt,
            savedAt: now,
            rectangularReading: schedReading,
            matchup: WatchMatchupFacts217()
        )
        let schedDates = WatchMatchupReading217.timelineDates(for: schedSnap, now: now, timeZone: utc)
        XCTAssertNotNil(schedDates)
        XCTAssertGreaterThanOrEqual(schedDates?.count ?? 0, 2)
        XCTAssertLessThanOrEqual(schedDates?.count ?? 99, 4)

        let liveReading = WatchRectangularReading(
            version: 1,
            eventID: 15349272,
            kind: .liveForecast,
            homeName: "California",
            awayName: "Stanford",
            home: cal,
            away: stan,
            homePercent: 52,
            homeScore: 14,
            awayScore: 10,
            commenceTime: nil,
            stateLabel: "Live",
            observedAt: now.addingTimeInterval(-30),
            scoreObservedAt: now.addingTimeInterval(-30)
        )
        let liveSnap = WatchComplicationSnapshot(
            eventID: 15349272,
            title: "California win",
            detail: "52% · Live",
            observedAt: liveReading.observedAt,
            savedAt: now,
            rectangularReading: liveReading,
            matchup: WatchMatchupFacts217(clock: "Q2 4:10")
        )
        let liveDates = WatchMatchupReading217.timelineDates(for: liveSnap, now: now, timeZone: utc)
        XCTAssertEqual(liveDates?.count, 2)

        let finalReading = WatchRectangularReading(
            version: 1,
            eventID: 15349272,
            kind: .finalResult,
            homeName: "California",
            awayName: "Stanford",
            home: cal,
            away: stan,
            homePercent: nil,
            homeScore: 28,
            awayScore: 21,
            commenceTime: nil,
            stateLabel: "Final",
            observedAt: now.addingTimeInterval(-600),
            scoreObservedAt: now.addingTimeInterval(-600)
        )
        let finalSnap = WatchComplicationSnapshot(
            eventID: 15349272,
            title: "California won",
            detail: "Final · 28–21",
            observedAt: finalReading.observedAt,
            savedAt: now,
            rectangularReading: finalReading,
            matchup: WatchMatchupFacts217(pregameHomePercent: 43, pregameAwayPercent: 57)
        )
        let finalDates = WatchMatchupReading217.timelineDates(for: finalSnap, now: now, timeZone: utc)
        XCTAssertEqual(finalDates?.count, 2)
    }

    func testUnavailableReasonsAndPayloadAreDistinctAndFailClosed() throws {
        for reason in WatchFaceUnavailableReason13339.allCases {
            XCTAssertNotEqual(reason.complicationHeadline, "Your game")
            XCTAssertFalse(reason.appNotice.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            let spoken = reason.accessibilityDescription(title: "Stanford at California")
            for copy in [reason.complicationHeadline, reason.complicationDetail, reason.appNotice, spoken] {
                for forbidden in ["saved", "stale", "checked", "question"] {
                    XCTAssertFalse(copy.localizedCaseInsensitiveContains(forbidden), "\(reason): '\(copy)' contained '\(forbidden)'")
                }
            }
        }

        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("status13339-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let file = dir.appendingPathComponent(WatchFaceStatusPayload13339.filename)

        try Data("{}".utf8).write(to: file)
        XCTAssertNil(WatchFaceStatusPayload13339.read(from: dir))

        let payload = WatchFaceStatusPayload13339(
            targetID: 15349272,
            title: "Stanford at California",
            reason: .finalEnded,
            updatedAt: Date(timeIntervalSinceReferenceDate: 100_000)
        )
        try JSONEncoder().encode(payload).write(to: file)
        XCTAssertEqual(WatchFaceStatusPayload13339.read(from: dir), payload)
    }

    func testPinsStoreAndComplicationSourceWiringInvariants() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("BainLuckWatch Watch App")
        let storeSource = try String(contentsOf: root.appendingPathComponent("WatchPinsStore12640.swift"), encoding: .utf8)
        let viewSource = try String(contentsOf: root.appendingPathComponent("WatchPinnedHomeView12640.swift"), encoding: .utf8)
        let widgetSource = try String(contentsOf: root.appendingPathComponent("BainLuckComplication.swift"), encoding: .utf8)

        XCTAssertTrue(storeSource.contains("republishSelectedFaceSnapshot(forceReload: false)"))
        XCTAssertTrue(storeSource.contains("republishSelectedFaceSnapshot(forceReload: true)"))
        XCTAssertTrue(storeSource.contains("emitFaceState(.noSelection, true)"))
        XCTAssertTrue(viewSource.contains("watch.pins.face-status"))
        XCTAssertTrue(viewSource.contains("store.triggerRefresh(userInitiated: true)"))
        XCTAssertTrue(widgetSource.contains("WatchUnavailableComplicationContent13339"))
    }
}
