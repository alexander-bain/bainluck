#if os(iOS) && canImport(ActivityKit)
import ActivityKit
import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #13659 — Watch Smart Stack live pill must never truncate the game clock (`"LIVE · Q4 4…"`).
/// When the full `"LIVE · <clock>"` pill + trailing `"BADGE NN%"` exceed a narrow Watch Smart Stack
/// width (41 / 45 / 49 mm), the red live pill drops `"LIVE · "` first (retaining the red fill and white
/// dot) so the complete clock (`"Q4 12:00"`, `"OT 10:00"`, `"2nd 45+7'"`, `"Bot 11th"`) always fits whole.
final class WatchSmartStackPill13659Tests: XCTestCase {
    private static let fixedClock = ISO8601DateFormatter().date(from: "2026-11-24T21:45:00Z")!

    private struct Sample {
        let key: String
        let periodLabel: String
        let sport: String
        let homeTeam: String
        let awayTeam: String
        let homeAbbr: String
        let awayAbbr: String
        let homeScore: Int
        let awayScore: Int
        let homeProb: Double
        let awayProb: Double
    }

    private static let longestServedCases: [Sample] = [
        Sample(
            key: "q4-412",
            periodLabel: "Q4 4:12",
            sport: "americanfootball_nfl",
            homeTeam: "Kansas City Chiefs",
            awayTeam: "Buffalo Bills",
            homeAbbr: "KC",
            awayAbbr: "BUF",
            homeScore: 24,
            awayScore: 21,
            homeProb: 0.66,
            awayProb: 0.34
        ),
        Sample(
            key: "q4-1200",
            periodLabel: "Q4 12:00",
            sport: "basketball_nba",
            homeTeam: "Oklahoma City Thunder",
            awayTeam: "Denver Nuggets",
            homeAbbr: "OKC",
            awayAbbr: "DEN",
            homeScore: 98,
            awayScore: 95,
            homeProb: 0.68,
            awayProb: 0.32
        ),
        Sample(
            key: "ot-1000",
            periodLabel: "OT 10:00",
            sport: "americanfootball_nfl",
            homeTeam: "Texas A&M Aggies",
            awayTeam: "Texas Longhorns",
            homeAbbr: "TA&M",
            awayAbbr: "TEX",
            homeScore: 28,
            awayScore: 28,
            homeProb: 0.54,
            awayProb: 0.46
        ),
        Sample(
            key: "2nd-45plus7",
            periodLabel: "2nd 45+7'",
            sport: "soccer_epl",
            homeTeam: "Manchester City",
            awayTeam: "Real Madrid",
            homeAbbr: "MCI",
            awayAbbr: "RMA",
            homeScore: 2,
            awayScore: 2,
            homeProb: 0.62,
            awayProb: 0.38
        ),
        Sample(
            key: "bot-11th",
            periodLabel: "Bot 11th",
            sport: "baseball_mlb",
            homeTeam: "Los Angeles Dodgers",
            awayTeam: "New York Yankees",
            homeAbbr: "LAD",
            awayAbbr: "NYY",
            homeScore: 5,
            awayScore: 4,
            homeProb: 0.78,
            awayProb: 0.22
        ),
    ]

    private func snapshot(for s: Sample) throws -> GameActivitySnapshot {
        try XCTUnwrap(GameActivitySnapshot(
            eventID: 136590,
            homeTeam: s.homeTeam,
            awayTeam: s.awayTeam,
            lifecycle: .live,
            homeScore: s.homeScore,
            awayScore: s.awayScore,
            homeProbability: s.homeProb,
            awayProbability: s.awayProb,
            sport: s.sport,
            scoreObservedAt: Self.fixedClock,
            probabilityObservedAt: Self.fixedClock,
            homeAbbreviation: s.homeAbbr,
            awayAbbreviation: s.awayAbbr,
            homeColorHex: "#D70015",
            awayColorHex: "#1D4ED8",
            periodLabel: s.periodLabel
        ))
    }

    func testCompactStatusPreservesFullClockAcrossLongestServedLabels() throws {
        for sample in Self.longestServedCases {
            let snap = try snapshot(for: sample)
            let reading = GameActivityReading(snapshot: snap, eventID: snap.eventID)
            XCTAssertEqual(reading.statusText, "LIVE · \(sample.periodLabel)")
            XCTAssertEqual(reading.compactStatusText, sample.periodLabel)
            XCTAssertFalse(reading.compactStatusText.contains("LIVE"))
            XCTAssertFalse(reading.compactStatusText.contains("…"))
        }

        let src = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("BainLuckWidget/GameLiveActivity.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(src.contains("var compactStatusText: String"))
        XCTAssertTrue(src.contains("ViewThatFits(in: .horizontal)"))
        XCTAssertTrue(src.contains("compactStatusPill"))
    }

    @MainActor
    func testRenderWatchSmartStack13659() throws {
        // Measured Watch Smart Stack card widths corresponding to 41 / 45 / 49 mm faces.
        let watchWidths: [(label: String, width: CGFloat)] = [
            ("41mm", 171.5),
            ("45mm", 185.0),
            ("49mm", 199.0),
        ]

        let exportDir = ProcessInfo.processInfo.environment["BAINLUCK_EXPORT_13659_DIR"]
            .flatMap { $0.isEmpty ? nil : URL(fileURLWithPath: $0, isDirectory: true) }
        if let exportDir {
            try FileManager.default.createDirectory(at: exportDir, withIntermediateDirectories: true)
        }

        for sample in Self.longestServedCases {
            let snap = try snapshot(for: sample)
            let reading = GameActivityReading(snapshot: snap, eventID: snap.eventID)
            for size in watchWidths {
                let tile = GameActivitySmallView(reading: reading)
                    .frame(width: size.width, height: 78)
                    .background(
                        Color(red: 0.11, green: 0.11, blue: 0.13),
                        in: RoundedRectangle(cornerRadius: 16, style: .continuous)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(Color.white.opacity(0.16), lineWidth: 1)
                    )
                    .padding(4)
                    .background(Color.black)
                    .environment(\.colorScheme, .dark)

                let renderer = rendererForMeasurement(tile, at: .large)
                renderer.scale = 3
                let image = try XCTUnwrap(renderer.uiImage, "Expected Smart Stack render for \(sample.key) \(size.label)")
                let data = try XCTUnwrap(image.pngData())
                XCTAssertGreaterThan(data.count, 512)

                let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.png")
                attachment.name = "\(sample.key)_\(size.label)"
                attachment.lifetime = .keepAlways
                add(attachment)

                if let exportDir {
                    try data.write(to: exportDir.appendingPathComponent("\(sample.key)_\(size.label).png"))
                }
            }
        }
    }
}
#endif
