#if os(iOS) && canImport(ActivityKit)
import ActivityKit
import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Direction 395 (`#12538`): decimals appear ONLY where live DNPL updates feed a surface.
/// Live Activities receive 15s backend APNs pushes (and foreground committed event updates,
/// never DNPL preview), so every Live Activity form prints whole percents (`66%`, not `66.2%`).
final class LiveActivityWholePercents395Tests: XCTestCase {
    private static let fixedClock = ISO8601DateFormatter().date(from: "2026-11-24T21:45:00Z")!

    private func makeChiefsBillsSnapshot(observedAt: Date = fixedClock) throws -> GameActivitySnapshot {
        try XCTUnwrap(GameActivitySnapshot(
            eventID: 15342099,
            homeTeam: "Kansas City Chiefs",
            awayTeam: "Buffalo Bills",
            lifecycle: .live,
            homeScore: 24,
            awayScore: 21,
            homeProbability: 0.662,
            awayProbability: 0.338,
            sport: "americanfootball_nfl",
            scoreObservedAt: observedAt,
            probabilityObservedAt: observedAt,
            homeAbbreviation: "KC",
            awayAbbreviation: "BUF",
            homeColorHex: "#E31837",
            awayColorHex: "#00338D",
            periodLabel: "Q4 4:12"
        ))
    }

    private func makeHoustonWVUSnapshot(withScore: Bool = true, observedAt: Date = fixedClock) throws -> GameActivitySnapshot {
        try XCTUnwrap(GameActivitySnapshot(
            eventID: 15342100,
            homeTeam: "West Virginia Mountaineers",
            awayTeam: "Houston Cougars",
            lifecycle: .live,
            homeScore: withScore ? 31 : nil,
            awayScore: withScore ? 31 : nil,
            homeProbability: 0.428,
            awayProbability: 0.572,
            sport: "americanfootball_ncaaf",
            scoreObservedAt: withScore ? observedAt : nil,
            probabilityObservedAt: observedAt,
            homeAbbreviation: "WVU",
            awayAbbreviation: "HOU",
            homeColorHex: "#002855",
            awayColorHex: "#C8102E",
            periodLabel: "Q4 2:15",
            scoreSourceUnavailable: withScore ? nil : true
        ))
    }

    func testLiveTwoWayGameUsesWholePercentsAndDropsTenths() throws {
        let chiefs = try makeChiefsBillsSnapshot()
        // Wire payload retains homeHeadlineTenths for backward/in-flight Codable compatibility.
        XCTAssertEqual(chiefs.homeHeadlineTenths, 662)

        let chiefsReading = GameActivityReading(snapshot: chiefs, eventID: chiefs.eventID)
        XCTAssertEqual(chiefsReading.nowText(.home), "66%")
        XCTAssertEqual(chiefsReading.nowText(.away), "34%")
        XCTAssertEqual(chiefsReading.minimalNowText(.home), "66%")
        let decimalPercentPattern = #"\d+\.\d+%"#
        XCTAssertNil(chiefsReading.rowSpoken(.home).range(of: decimalPercentPattern, options: .regularExpression))
        XCTAssertNil(chiefsReading.rowSpoken(.away).range(of: decimalPercentPattern, options: .regularExpression))
        XCTAssertNil(chiefsReading.chanceSpoken.range(of: decimalPercentPattern, options: .regularExpression))
        XCTAssertTrue(chiefsReading.chanceSpoken.contains("34%"))
        XCTAssertTrue(chiefsReading.chanceSpoken.contains("66%"))

        let houston = try makeHoustonWVUSnapshot()
        let houstonReading = GameActivityReading(snapshot: houston, eventID: houston.eventID)
        XCTAssertEqual(houstonReading.nowText(.away), "57%")
        XCTAssertEqual(houstonReading.nowText(.home), "43%")
        XCTAssertEqual(houstonReading.minimalNowText(.away), "57%")
        XCTAssertNil(houstonReading.compactSpoken.range(of: decimalPercentPattern, options: .regularExpression))
        XCTAssertTrue(houstonReading.compactSpoken.contains("57%"))

        let liveActivitySource = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("BainLuckWidget/GameLiveActivity.swift"),
            encoding: .utf8
        )
        XCTAssertFalse(
            liveActivitySource.contains("headlineNowText"),
            "GameLiveActivity must render whole percents across all surfaces under rule 395"
        )
    }

    @MainActor
    func testRenderLiveActivitySurfaces395() throws {
        let chiefs = try makeChiefsBillsSnapshot()
        let chiefsReading = GameActivityReading(snapshot: chiefs, eventID: chiefs.eventID)
        let houstonScored = try makeHoustonWVUSnapshot(withScore: true)
        let houstonScoredReading = GameActivityReading(snapshot: houstonScored, eventID: houstonScored.eventID)
        let houstonScoreless = try makeHoustonWVUSnapshot(withScore: false)
        let houstonScorelessReading = GameActivityReading(snapshot: houstonScoreless, eventID: houstonScoreless.eventID)

        let lockLight = GameActivityLockScreenView(reading: chiefsReading)
            .frame(width: 358)
            .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(Color.black.opacity(0.08), lineWidth: 1))
            .padding(8)
            .background(Color(white: 0.94))
            .environment(\.colorScheme, .light)

        let lockDark = GameActivityLockScreenView(reading: chiefsReading)
            .frame(width: 358)
            .background(Color(red: 0.11, green: 0.11, blue: 0.13), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(Color.white.opacity(0.14), lineWidth: 1))
            .padding(8)
            .background(Color(red: 0.05, green: 0.05, blue: 0.06))
            .environment(\.colorScheme, .dark)

        let islandExpanded = VStack(spacing: 8) {
            HStack(alignment: .center, spacing: 6) {
                GameActivityExpandedSide(reading: chiefsReading, side: .away)
                GameActivityStatusPill(reading: chiefsReading)
                GameActivityExpandedSide(reading: chiefsReading, side: .home)
            }
            VStack(spacing: 5) {
                GameActivityChanceLine(reading: chiefsReading)
                GameActivityFooter(reading: chiefsReading)
            }
            .padding(.horizontal, 8)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(width: 358)
        .background(Color.black, in: RoundedRectangle(cornerRadius: 34, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 34, style: .continuous).stroke(Color.white.opacity(0.16), lineWidth: 1))
        .padding(8)
        .background(Color(white: 0.14))
        .environment(\.colorScheme, .dark)

        let islandCompactAndMinimal = HStack(spacing: 12) {
            // Compact (score active: leading shows percentage, trailing shows live score)
            HStack(spacing: 16) {
                GameActivityCompactLeading(reading: houstonScoredReading)
                Spacer(minLength: 20)
                GameActivityCompactTrailing(reading: houstonScoredReading)
            }
            .padding(.horizontal, 12)
            .frame(width: 196, height: 36)
            .background(Color.black, in: Capsule())
            .overlay(Capsule().stroke(Color.white.opacity(0.18), lineWidth: 1))

            // Compact without score feed (both sides show chance)
            HStack(spacing: 10) {
                GameActivityCompactLeading(reading: houstonScorelessReading)
                Spacer(minLength: 10)
                GameActivityCompactTrailing(reading: houstonScorelessReading)
            }
            .padding(.horizontal, 12)
            .frame(width: 196, height: 36)
            .background(Color.black, in: Capsule())
            .overlay(Capsule().stroke(Color.white.opacity(0.18), lineWidth: 1))

            // Minimal
            GameActivityMinimal(reading: houstonScoredReading)
                .frame(width: 36, height: 36)
                .background(Color.black, in: Circle())
                .overlay(Circle().stroke(Color.white.opacity(0.18), lineWidth: 1))
        }
        .padding(10)
        .background(Color(white: 0.14))
        .environment(\.colorScheme, .dark)

        let watchSmartStack = GameActivitySmallView(reading: chiefsReading)
            .frame(width: 172, height: 78)
            .background(Color(red: 0.11, green: 0.11, blue: 0.13), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Color.white.opacity(0.16), lineWidth: 1))
            .padding(8)
            .background(Color(white: 0.14))
            .environment(\.colorScheme, .dark)

        let captures: [(String, AnyView)] = [
            ("lock-light", AnyView(lockLight)),
            ("lock-dark", AnyView(lockDark)),
            ("island-expanded", AnyView(islandExpanded)),
            ("island-compact-minimal", AnyView(islandCompactAndMinimal)),
            ("watch-smart-stack", AnyView(watchSmartStack)),
        ]

        let exportDir = ProcessInfo.processInfo.environment["BAINLUCK_EXPORT_LA_395_DIR"]
            .flatMap { $0.isEmpty ? nil : URL(fileURLWithPath: $0, isDirectory: true) }
        if let exportDir {
            try FileManager.default.createDirectory(at: exportDir, withIntermediateDirectories: true)
        }

        for (name, view) in captures {
            let renderer = rendererForMeasurement(view, at: .large)
            renderer.scale = 3
            let image = try XCTUnwrap(renderer.uiImage, "Expected rendered image for \(name)")
            let data = try XCTUnwrap(image.pngData(), "Expected PNG data for \(name)")
            XCTAssertGreaterThan(data.count, 512)

            let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.png")
            attachment.name = name
            attachment.lifetime = .keepAlways
            add(attachment)

            if let exportDir {
                try data.write(to: exportDir.appendingPathComponent("\(name).png"))
            }
        }
    }
}
#endif
