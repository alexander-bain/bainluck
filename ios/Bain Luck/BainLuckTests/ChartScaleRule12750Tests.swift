import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #12750 (Rulings 201 & 202-A) — One Chart Scale Rule in One Place:
/// 1. Two-team / two-player games with no draw (`ChartScaleRule201.Mode.fittedTwoWay`):
///    fitted from the very first reading, including when `< 12` readings exist (never
///    falling back to `0...100` for sparse/early games).
/// 2. Soccer and any draw-capable sport (`ChartScaleRule201.Mode.fullZeroToHundred`):
///    always `0` to `100` (`ChartProbabilityAxis9483.full`).
/// 3. Golf, futures, tournament race charts, and many-way / multi-rung ladders
///    (`ChartScaleRule201.Mode.zeroToTopValue`, Ruling 202-A): `0` to a snapped ceiling
///    above the top value shown.
@MainActor
final class ChartScaleRule12750Tests: XCTestCase {

    private func makeDate(_ iso: String) -> Date {
        ISO8601DateFormatter().date(from: iso)!
    }

    private func decodeJSON<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(T.self, from: Data(json.utf8))
    }

    private func collectTexts(in view: UIView) -> [String] {
        var found: [String] = []
        if let label = view as? UILabel,
           let text = label.text,
           !text.isEmpty,
           !label.isHidden,
           label.alpha > 0.01 {
            found.append(text)
        }
        for sub in view.subviews {
            found.append(contentsOf: collectTexts(in: sub))
        }
        return found
    }

    // MARK: - 1. Guard Test (#12750 Item 4): Two-Team Game Never 0..100; Three-Way Always 0..100

    func testGuardTwoTeamGameChartNeverHasZeroToHundredWhileThreeWayAlwaysDoes() {
        let twoTeamSports = [
            "americanfootball_nfl",
            "americanfootball_ncaaf",
            "basketball_nba",
            "basketball_ncaab",
            "baseball_mlb",
            "icehockey_nhl",
            "tennis_atp_us_open",
            "tennis_wta_wimbledon",
            "mma_mixed_martial_arts",
        ]
        let threeWayDrawSports = [
            "soccer_epl",
            "soccer_uefa_champs_league",
            "soccer_usa_mls",
            "cricket_ipl",
            "boxing_boxing",
            "rugbyunion_six_nations",
            "rugbyleague_nrl",
            "chess_fide",
        ]

        // Test across 1 reading, 3 early readings, 7 mid-Q1 readings, 11 readings, and 18 late readings.
        let sampleSets: [[Double]] = [
            [0.58],
            [0.54, 0.57, 0.61],
            [0.48, 0.51, 0.53, 0.49, 0.55, 0.58, 0.60],
            Array(repeating: 0.62, count: 11),
            (0..<18).map { 0.47 + Double($0) * 0.014 },
        ]

        for sport in twoTeamSports {
            XCTAssertEqual(ChartScaleRule201.gameMode(sportKey: sport), .fittedTwoWay, "\(sport)")
            for readings in sampleSets {
                let win = ChartScaleRule201.gameWindow(
                    sportKey: sport,
                    readings: readings,
                    mustShow: [readings.last!]
                )
                XCTAssertNotEqual(
                    win,
                    ChartProbabilityAxis9483.full,
                    "\(sport) with \(readings.count) readings must fit around the readings, never 0..100"
                )
                XCTAssertFalse(
                    win.lowerPercent == 0 && win.upperPercent == 100,
                    "\(sport) with \(readings.count) readings must never span 0..100"
                )
                XCTAssertGreaterThanOrEqual(
                    win.upperPercent - win.lowerPercent,
                    ChartProbabilityAxis9483.minSpanPercent,
                    "\(sport) keeps at least the 20-point minimum span"
                )
                for r in readings {
                    XCTAssertTrue(win.domain.contains(r), "\(sport) window \(win.domain) must contain \(r)")
                }
            }
        }

        for drawSport in threeWayDrawSports {
            XCTAssertEqual(ChartScaleRule201.gameMode(sportKey: drawSport), .fullZeroToHundred, "\(drawSport)")
            for readings in sampleSets {
                let win = ChartScaleRule201.gameWindow(
                    sportKey: drawSport,
                    readings: readings,
                    mustShow: [readings.last!]
                )
                XCTAssertEqual(
                    win,
                    ChartProbabilityAxis9483.full,
                    "\(drawSport) is three-way / draw-capable and must always span 0..100"
                )
                XCTAssertEqual(win.lowerPercent, 0)
                XCTAssertEqual(win.upperPercent, 100)
            }
        }
    }

    // MARK: - 2. Discover 191-A Early (<12 Readings) & Many-Way (202-A) Guard

    func testDiscoverEarlyReadingsFitAndManyWayMarketsUseZeroToTopValue() {
        let t0 = makeDate("2026-11-16T18:00:00Z")
        let earlyPoints: [DiscoverPictureChart191A.Point] = [0.56, 0.59, 0.62, 0.64].enumerated().map { idx, p in
            DiscoverPictureChart191A.Point(
                id: idx,
                date: t0.addingTimeInterval(Double(idx) * 180),
                probability: p,
                isOpening: idx == 0,
                isSolidMark: true,
                isEndpoint: idx == 3
            )
        }
        let nflEarlyDiscover = DiscoverPictureChartPanel191AView.verticalWindow201(
            sportKey: "americanfootball_nfl",
            points: earlyPoints
        )
        XCTAssertNotEqual(nflEarlyDiscover, ChartProbabilityAxis9483.full, "4-reading Discover NFL game fits")
        XCTAssertEqual(nflEarlyDiscover.lowerPercent, 50)
        XCTAssertEqual(nflEarlyDiscover.upperPercent, 70)

        let soccerEarlyDiscover = DiscoverPictureChartPanel191AView.verticalWindow201(
            sportKey: "soccer_epl",
            points: earlyPoints
        )
        XCTAssertEqual(soccerEarlyDiscover, ChartProbabilityAxis9483.full, "Soccer Discover card stays 0..100")

        // Ruling 202-A: many-way / prop ladders anchor at 0 and stop above top value shown
        let lowPropLadder = ChartScaleRule201.manyWayWindow(values: [0.24, 0.13, 0.06, 0.02])
        XCTAssertEqual(lowPropLadder.domain, 0 ... 0.30)
        XCTAssertEqual(lowPropLadder.ticks, [0, 0.15, 0.30])

        let midPropLadder = ChartScaleRule201.manyWayWindow(values: [0.41, 0.22, 0.09])
        XCTAssertEqual(midPropLadder.domain, 0 ... 0.50)
        XCTAssertEqual(midPropLadder.ticks, [0, 0.25, 0.50])

        let highPropLadder = ChartScaleRule201.manyWayWindow(values: [0.84, 0.56, 0.29, 0.11])
        XCTAssertEqual(highPropLadder.domain, 0 ... 1.0)
        XCTAssertEqual(highPropLadder.ticks, [0, 0.50, 1.0])
    }

    // MARK: - 3. Source Wiring Guard: Every Probability Chart Uses ChartScaleRule201

    func testNoChartComponentHardcodesFixedZeroToOneYScale() throws {
        let componentsDir = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components")

        for file in [
            "OddsChartView.swift",
            "DiscoverPictureChartPanel191A.swift",
            "EvolutionChartView.swift",
            "EventAtlasGolfTournament11666.swift",
            "NBAEventCards9483.swift",
            "NFLEventCards9483.swift",
            "MLBFinalCards11284.swift",
            "PlayerMilestoneProfileView.swift",
        ] {
            let text = try String(contentsOf: componentsDir.appendingPathComponent(file), encoding: .utf8)
            XCTAssertTrue(text.contains("ChartScaleRule201."), "\(file) must route Y scale through ChartScaleRule201")
            XCTAssertFalse(
                text.contains(".chartYScale(domain: 0...1)"),
                "\(file) must not hardcode .chartYScale(domain: 0...1)"
            )
        }
    }

    // MARK: - 4. 390 px Contact Sheets: Every Sport Early in a Game & Late

    private struct GameChartSpecimen {
        let id: Int
        let title: String
        let sportKey: String
        let awayName: String
        let homeName: String
        let awayAbbrev: String
        let homeAbbrev: String
        let awayHex: String
        let homeHex: String
        let draws: Bool
        let earlyProbs: [Double]
        let lateProbs: [Double]
    }

    private func makeHistory(for spec: GameChartSpecimen, probs: [Double], stepMinutes: Int) throws -> EventHistoryResponse {
        let kickoff = makeDate("2026-11-16T18:00:00Z")
        let entries: [String] = probs.enumerated().map { idx, homeP in
            let tsDate = idx == 0
                ? kickoff.addingTimeInterval(-300)
                : kickoff.addingTimeInterval(Double(idx * stepMinutes * 60))
            let ts = ISO8601DateFormatter().string(from: tsDate)
            if spec.draws {
                return String(format: "{ \"timestamp\": \"%@\", \"home_probability\": %.4f }", ts, homeP)
            } else {
                return String(
                    format: "{ \"timestamp\": \"%@\", \"home_probability\": %.4f, \"away_probability\": %.4f }",
                    ts, homeP, 1.0 - homeP
                )
            }
        }
        let joined = entries.joined(separator: ",\n")
        let json = """
        {
          "event_id": \(spec.id),
          "home_team": "\(spec.homeName)",
          "away_team": "\(spec.awayName)",
          "commence_time": "2026-11-16T18:00:00Z",
          "status": "live",
          "win_prob_sources": {
            "aggregate": { "label": "Blended", "weight": 1.0 }
          },
          "history": [\(joined)],
          "aggregate_line": [\(joined)]
        }
        """
        return try decodeJSON(EventHistoryResponse.self, json)
    }

    private func renderGamePair(_ spec: GameChartSpecimen) throws -> AnyView {
        let earlyHistory = try makeHistory(for: spec, probs: spec.earlyProbs, stepMinutes: 3)
        let lateHistory = try makeHistory(for: spec, probs: spec.lateProbs, stepMinutes: 7)
        let awayColor = Color(hex: spec.awayHex)
        let homeColor = Color(hex: spec.homeHex)
        let earlyLast = spec.earlyProbs.last!
        let lateLast = spec.lateProbs.last!

        return AnyView(
            VStack(alignment: .leading, spacing: 10) {
                Text("\(spec.title) · Early (\(spec.earlyProbs.count) readings)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)

                OddsChartView(
                    eventId: spec.id * 10 + 1,
                    teamColors: (away: awayColor, home: homeColor),
                    commenceTime: "2026-11-16T18:00:00Z",
                    status: "live",
                    homeTeamName: spec.homeName,
                    awayTeamName: spec.awayName,
                    homeTeamAbbrev: spec.homeAbbrev,
                    awayTeamAbbrev: spec.awayAbbrev,
                    sportKey: spec.sportKey,
                    servedHomeProbability: earlyLast,
                    servedAwayProbability: spec.draws ? nil : (1.0 - earlyLast),
                    selectedRange: .constant(.sinceStart),
                    preloadedHistory: earlyHistory,
                    preloadedHistoryGeneration: 1
                )
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding(.horizontal, 16)

                Text("\(spec.title) · Late (\(spec.lateProbs.count) readings)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)

                OddsChartView(
                    eventId: spec.id * 10 + 2,
                    teamColors: (away: awayColor, home: homeColor),
                    commenceTime: "2026-11-16T18:00:00Z",
                    status: "live",
                    homeTeamName: spec.homeName,
                    awayTeamName: spec.awayName,
                    homeTeamAbbrev: spec.homeAbbrev,
                    awayTeamAbbrev: spec.awayAbbrev,
                    sportKey: spec.sportKey,
                    servedHomeProbability: lateLast,
                    servedAwayProbability: spec.draws ? nil : (1.0 - lateLast),
                    selectedRange: .constant(.sinceStart),
                    preloadedHistory: lateHistory,
                    preloadedHistoryGeneration: 1
                )
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding(.horizontal, 16)
            }
        )
    }

    private func renderSectionImage(_ content: AnyView) async throws -> UIImage {
        let wrapped = content
            .padding(.vertical, 10)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))
            .ignoresSafeArea()

        let host = hostForMeasurement(wrapped.environment(\.colorScheme, .light), at: .large)
        host.additionalSafeAreaInsets = .zero
        host.overrideUserInterfaceStyle = .light
        let fittedH = max(120, min(ceil(host.sizeThatFits(in: CGSize(width: 390, height: 2200)).height), 2200))
        host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: fittedH))

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: host.view.frame)
        }
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        try await Task.sleep(nanoseconds: 180_000_000)
        let until = Date().addingTimeInterval(0.18)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < until

        let texts = collectTexts(in: host.view).joined(separator: " | ")
        XCTAssertFalse(texts.contains("Recorded reading"), "No legend text in chart section")
        XCTAssertFalse(texts.contains("Tap any reading"), "No tap-hint text in chart section")

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
            UIColor.systemGroupedBackground.setFill()
            ctx.fill(host.view.bounds)
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func stitchImages(_ images: [UIImage], filename: String, outDir: String?) throws {
        guard let outDir, !outDir.isEmpty, !images.isEmpty else { return }
        let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
        let totalHeight = images.reduce(CGFloat(0)) { $0 + $1.size.height }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        let stitched = UIGraphicsImageRenderer(size: CGSize(width: 390, height: totalHeight), format: fmt).image { ctx in
            UIColor.systemGroupedBackground.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: 390, height: totalHeight))
            var y: CGFloat = 0
            for img in images {
                img.draw(in: CGRect(x: 0, y: y, width: 390, height: img.size.height))
                y += img.size.height
            }
        }
        if let png = stitched.pngData() {
            try png.write(to: dirURL.appendingPathComponent(filename))
        }
    }

    func testAllSportsEarlyAndLateChartsRenderOnOneScaleRule() async throws {
        let part1Specs: [GameChartSpecimen] = [
            GameChartSpecimen(
                id: 801, title: "NFL · Patriots @ Lions", sportKey: "americanfootball_nfl",
                awayName: "New England Patriots", homeName: "Detroit Lions",
                awayAbbrev: "NE", homeAbbrev: "DET", awayHex: "#C60C30", homeHex: "#0076B6", draws: false,
                earlyProbs: [0.58, 0.56, 0.61, 0.63],
                lateProbs: [0.58, 0.56, 0.53, 0.49, 0.52, 0.55, 0.58, 0.61, 0.59, 0.63, 0.66, 0.68, 0.65, 0.69, 0.71, 0.73]
            ),
            GameChartSpecimen(
                id: 802, title: "NBA · Celtics @ Knicks", sportKey: "basketball_nba",
                awayName: "Boston Celtics", homeName: "New York Knicks",
                awayAbbrev: "BOS", homeAbbrev: "NYK", awayHex: "#007A33", homeHex: "#F58426", draws: false,
                earlyProbs: [0.53, 0.56, 0.59],
                lateProbs: [0.53, 0.56, 0.59, 0.54, 0.48, 0.44, 0.47, 0.52, 0.57, 0.61, 0.64, 0.60, 0.65, 0.68, 0.72, 0.75]
            ),
            GameChartSpecimen(
                id: 803, title: "College Football · Alabama @ Georgia", sportKey: "americanfootball_ncaaf",
                awayName: "Alabama Crimson Tide", homeName: "Georgia Bulldogs",
                awayAbbrev: "ALA", homeAbbrev: "UGA", awayHex: "#64748B", homeHex: "#BA0C2F", draws: false,
                earlyProbs: [0.55, 0.58, 0.60],
                lateProbs: [0.55, 0.58, 0.60, 0.63, 0.59, 0.54, 0.51, 0.56, 0.61, 0.64, 0.67, 0.69, 0.66, 0.70, 0.74]
            ),
            GameChartSpecimen(
                id: 804, title: "College Basketball · Gonzaga @ Duke", sportKey: "basketball_ncaab",
                awayName: "Gonzaga Bulldogs", homeName: "Duke Blue Devils",
                awayAbbrev: "GONZ", homeAbbrev: "DUKE", awayHex: "#C8102E", homeHex: "#003087", draws: false,
                earlyProbs: [0.60, 0.62, 0.59, 0.64],
                lateProbs: [0.60, 0.62, 0.59, 0.64, 0.67, 0.63, 0.58, 0.55, 0.60, 0.65, 0.68, 0.71, 0.74, 0.76, 0.79]
            ),
            GameChartSpecimen(
                id: 805, title: "MLB · Yankees @ Dodgers", sportKey: "baseball_mlb",
                awayName: "New York Yankees", homeName: "Los Angeles Dodgers",
                awayAbbrev: "NYY", homeAbbrev: "LAD", awayHex: "#64748B", homeHex: "#005A9C", draws: false,
                earlyProbs: [0.54, 0.52, 0.56, 0.58],
                lateProbs: [0.54, 0.52, 0.56, 0.58, 0.61, 0.57, 0.51, 0.46, 0.49, 0.55, 0.60, 0.63, 0.66, 0.64, 0.69, 0.72]
            ),
        ]

        let part2Specs: [GameChartSpecimen] = [
            GameChartSpecimen(
                id: 806, title: "NHL · Bruins @ Maple Leafs", sportKey: "icehockey_nhl",
                awayName: "Boston Bruins", homeName: "Toronto Maple Leafs",
                awayAbbrev: "BOS", homeAbbrev: "TOR", awayHex: "#FFB81C", homeHex: "#00205B", draws: false,
                earlyProbs: [0.52, 0.55, 0.57],
                lateProbs: [0.52, 0.55, 0.57, 0.53, 0.47, 0.44, 0.49, 0.54, 0.58, 0.62, 0.59, 0.63, 0.66, 0.68, 0.71]
            ),
            GameChartSpecimen(
                id: 807, title: "Tennis · Sinner vs Alcaraz", sportKey: "tennis_atp_us_open",
                awayName: "Jannik Sinner", homeName: "Carlos Alcaraz",
                awayAbbrev: "SIN", homeAbbrev: "ALC", awayHex: "#D97706", homeHex: "#2563EB", draws: false,
                earlyProbs: [0.51, 0.54, 0.56, 0.53],
                lateProbs: [0.51, 0.54, 0.56, 0.53, 0.48, 0.45, 0.50, 0.55, 0.59, 0.62, 0.58, 0.64, 0.67, 0.70, 0.73]
            ),
            GameChartSpecimen(
                id: 808, title: "MMA · Oliveira vs Makhachev", sportKey: "mma_mixed_martial_arts",
                awayName: "Charles Oliveira", homeName: "Islam Makhachev",
                awayAbbrev: "OLI", homeAbbrev: "MAK", awayHex: "#CA8A04", homeHex: "#15803D", draws: false,
                earlyProbs: [0.68, 0.71, 0.74],
                lateProbs: [0.68, 0.71, 0.74, 0.70, 0.66, 0.72, 0.75, 0.78, 0.76, 0.80, 0.82, 0.84, 0.86, 0.88]
            ),
            GameChartSpecimen(
                id: 809, title: "Soccer (3-Way Draw) · Liverpool @ Arsenal · 0%–100%", sportKey: "soccer_epl",
                awayName: "Liverpool", homeName: "Arsenal",
                awayAbbrev: "LIV", homeAbbrev: "ARS", awayHex: "#00B2A9", homeHex: "#EF0107", draws: true,
                earlyProbs: [0.44, 0.46, 0.48, 0.47],
                lateProbs: [0.44, 0.46, 0.48, 0.47, 0.50, 0.53, 0.51, 0.55, 0.58, 0.56, 0.60, 0.62, 0.64, 0.63, 0.66, 0.68]
            ),
        ]

        // Golf Early (0-30%) & Late (0-50%)
        let t0 = makeDate("2026-11-16T14:00:00Z")
        func makeGolfPoints(golfer: String, count: Int, step: TimeInterval, p0: Double, dp: Double) -> [EventAtlasGolfTournament11666.JourneyPoint] {
            var pts: [EventAtlasGolfTournament11666.JourneyPoint] = []
            for idx in 0..<count {
                let d = t0.addingTimeInterval(Double(idx) * step)
                let p = p0 + Double(idx) * dp
                pts.append(EventAtlasGolfTournament11666.JourneyPoint(golferName: golfer, date: d, probability: p))
            }
            return pts
        }
        let golfEarlyContenders: [EventAtlasGolfTournament11666.JourneyContender] = [
            EventAtlasGolfTournament11666.JourneyContender(
                name: "Scottie Scheffler", colorIndex: 0,
                openingProbability: 0.19, currentProbability: 0.23, finalVerdict: nil,
                points: makeGolfPoints(golfer: "Scottie Scheffler", count: 4, step: 1800, p0: 0.19, dp: 0.013)
            ),
            EventAtlasGolfTournament11666.JourneyContender(
                name: "Rory McIlroy", colorIndex: 1,
                openingProbability: 0.14, currentProbability: 0.15, finalVerdict: nil,
                points: makeGolfPoints(golfer: "Rory McIlroy", count: 4, step: 1800, p0: 0.14, dp: 0.004)
            ),
            EventAtlasGolfTournament11666.JourneyContender(
                name: "Jon Rahm", colorIndex: 2,
                openingProbability: 0.11, currentProbability: 0.10, finalVerdict: nil,
                points: makeGolfPoints(golfer: "Jon Rahm", count: 4, step: 1800, p0: 0.11, dp: -0.003)
            ),
        ]
        let golfLateContenders: [EventAtlasGolfTournament11666.JourneyContender] = [
            EventAtlasGolfTournament11666.JourneyContender(
                name: "Scottie Scheffler", colorIndex: 0,
                openingProbability: 0.19, currentProbability: 0.41, finalVerdict: nil,
                points: makeGolfPoints(golfer: "Scottie Scheffler", count: 14, step: 3600, p0: 0.19, dp: 0.017)
            ),
            EventAtlasGolfTournament11666.JourneyContender(
                name: "Rory McIlroy", colorIndex: 1,
                openingProbability: 0.14, currentProbability: 0.24, finalVerdict: nil,
                points: makeGolfPoints(golfer: "Rory McIlroy", count: 14, step: 3600, p0: 0.14, dp: 0.008)
            ),
            EventAtlasGolfTournament11666.JourneyContender(
                name: "Jon Rahm", colorIndex: 2,
                openingProbability: 0.11, currentProbability: 0.08, finalVerdict: nil,
                points: makeGolfPoints(golfer: "Jon Rahm", count: 14, step: 3600, p0: 0.11, dp: -0.002)
            ),
        ]

        // Futures Early (0-30%) & Late (0-50%)
        let futuresEarlyJSON = """
        {
          "market_id": 9901,
          "market_name": "2027 NBA Champion",
          "sport_category": "basketball",
          "hours": 168,
          "top": 5,
          "bucket_seconds": 3600,
          "outcomes": [
            { "id": 1, "name": "Boston Celtics", "current_probability": 0.22, "primary_color": "#007A33" },
            { "id": 2, "name": "Oklahoma City Thunder", "current_probability": 0.18, "primary_color": "#007AC1" },
            { "id": 3, "name": "Denver Nuggets", "current_probability": 0.11, "primary_color": "#0E2240" }
          ],
          "timeline": [
            { "timestamp": "2026-11-10T12:00:00Z", "outcomes": { "Boston Celtics": 0.19, "Oklahoma City Thunder": 0.17, "Denver Nuggets": 0.12 } },
            { "timestamp": "2026-11-12T12:00:00Z", "outcomes": { "Boston Celtics": 0.20, "Oklahoma City Thunder": 0.175, "Denver Nuggets": 0.115 } },
            { "timestamp": "2026-11-14T12:00:00Z", "outcomes": { "Boston Celtics": 0.21, "Oklahoma City Thunder": 0.18, "Denver Nuggets": 0.11 } },
            { "timestamp": "2026-11-16T12:00:00Z", "outcomes": { "Boston Celtics": 0.22, "Oklahoma City Thunder": 0.18, "Denver Nuggets": 0.11 } }
          ]
        }
        """
        let futuresLateJSON = """
        {
          "market_id": 9902,
          "market_name": "2027 NBA Champion",
          "sport_category": "basketball",
          "hours": 168,
          "top": 5,
          "bucket_seconds": 3600,
          "outcomes": [
            { "id": 1, "name": "Boston Celtics", "current_probability": 0.36, "primary_color": "#007A33" },
            { "id": 2, "name": "Oklahoma City Thunder", "current_probability": 0.25, "primary_color": "#007AC1" },
            { "id": 3, "name": "Denver Nuggets", "current_probability": 0.12, "primary_color": "#0E2240" }
          ],
          "timeline": [
            { "timestamp": "2026-11-01T12:00:00Z", "outcomes": { "Boston Celtics": 0.19, "Oklahoma City Thunder": 0.17, "Denver Nuggets": 0.14 } },
            { "timestamp": "2026-11-04T12:00:00Z", "outcomes": { "Boston Celtics": 0.22, "Oklahoma City Thunder": 0.19, "Denver Nuggets": 0.13 } },
            { "timestamp": "2026-11-07T12:00:00Z", "outcomes": { "Boston Celtics": 0.26, "Oklahoma City Thunder": 0.21, "Denver Nuggets": 0.13 } },
            { "timestamp": "2026-11-10T12:00:00Z", "outcomes": { "Boston Celtics": 0.29, "Oklahoma City Thunder": 0.22, "Denver Nuggets": 0.12 } },
            { "timestamp": "2026-11-13T12:00:00Z", "outcomes": { "Boston Celtics": 0.33, "Oklahoma City Thunder": 0.24, "Denver Nuggets": 0.12 } },
            { "timestamp": "2026-11-16T12:00:00Z", "outcomes": { "Boston Celtics": 0.36, "Oklahoma City Thunder": 0.25, "Denver Nuggets": 0.12 } }
          ]
        }
        """
        let futuresEarly = try decodeJSON(ProbabilityTimelineResponse.self, futuresEarlyJSON)
        let futuresLate = try decodeJSON(ProbabilityTimelineResponse.self, futuresLateJSON)

        let outDir = ProcessInfo.processInfo.environment["EXPORT_12750_CHART_SHEET_DIR"]
        let part1Views: [AnyView] = try part1Specs.map { try renderGamePair($0) }
        let part2Views: [AnyView] = try part2Specs.map { try renderGamePair($0) }

        let golfBlock = AnyView(
            VStack(alignment: .leading, spacing: 10) {
                Text("Golf · The Masters (Ruling 202-A: 0% to Top Value) · Early R1 (0%–30%)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)
                EventAtlasGolfJourneyCardView11666(
                    contenders: golfEarlyContenders,
                    phase: .recorded,
                    fieldCount: 88,
                    liveRound: 1,
                    onOpenFullscreenChart: {},
                    onOpenFullField: {}
                )
                .padding(14)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding(.horizontal, 16)

                Text("Golf · The Masters (Ruling 202-A: 0% to Top Value) · Late R4 (0%–50%)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)
                EventAtlasGolfJourneyCardView11666(
                    contenders: golfLateContenders,
                    phase: .recorded,
                    fieldCount: 88,
                    liveRound: 4,
                    onOpenFullscreenChart: {},
                    onOpenFullField: {}
                )
                .padding(14)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding(.horizontal, 16)
            }
        )

        let futuresBlock = AnyView(
            VStack(alignment: .leading, spacing: 10) {
                Text("Futures · 2027 NBA Champion (Ruling 202-A: 0% to Top Value) · Early (0%–30%)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)
                EvolutionChartView(
                    marketId: 9901,
                    headlineContenderNames: ["Boston Celtics", "Oklahoma City Thunder", "Denver Nuggets"],
                    preloadedTimeline: futuresEarly,
                    referenceNow: makeDate("2026-11-16T13:00:00Z")
                )
                .padding(14)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding(.horizontal, 16)

                Text("Futures · 2027 NBA Champion (Ruling 202-A: 0% to Top Value) · Late (0%–50%)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)
                EvolutionChartView(
                    marketId: 9902,
                    headlineContenderNames: ["Boston Celtics", "Oklahoma City Thunder", "Denver Nuggets"],
                    preloadedTimeline: futuresLate,
                    referenceNow: makeDate("2026-11-16T13:00:00Z")
                )
                .padding(14)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding(.horizontal, 16)
            }
        )

        var allImages: [UIImage] = []
        let banner = AnyView(
            VStack(alignment: .leading, spacing: 4) {
                Text("#12750 · One Scale Rule · Early & Late (390 px)")
                    .font(.footnote.weight(.bold))
                    .foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)
                Text("2-team games fitted from 1st reading · Soccer 0%–100% · Golf & Futures 0% to top value")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16)
        )
        allImages.append(try await renderSectionImage(banner))

        for v in part1Views {
            allImages.append(try await renderSectionImage(v))
        }
        for v in part2Views {
            allImages.append(try await renderSectionImage(v))
        }
        allImages.append(try await renderSectionImage(golfBlock))
        allImages.append(try await renderSectionImage(futuresBlock))

        try stitchImages(Array(allImages[0...3]), filename: "12750-charts-slice1-nfl-nba-cfb-390.png", outDir: outDir)
        try stitchImages(Array(allImages[4...6]), filename: "12750-charts-slice2-cbb-mlb-nhl-390.png", outDir: outDir)
        try stitchImages(Array(allImages[7...9]), filename: "12750-charts-slice3-tennis-mma-soccer-390.png", outDir: outDir)
        try stitchImages(Array(allImages[10...11]), filename: "12750-charts-slice4-golf-futures-390.png", outDir: outDir)
        try stitchImages(allImages, filename: "12750-charts-all-sports-early-and-late-390.png", outDir: outDir)
    }
}
