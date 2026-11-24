import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

#if canImport(UIKit)
import UIKit
import Vision
#endif

/// #13386 (1.0.7):
/// 1. Futures chart end labels keep full team/city identity with zero "…" truncation
///    and two-word city badges take initials of both words rather than the last word alone.
/// 2. Benchmark strip set pages read `item_noun` from the server (e.g. "couples") and
///    fall back to "markets", never "benchmarks".
/// 3. Futures headline eyebrows (e.g. Oscars Best Picture "Entertainment · Ceremony & Release Outlook")
///    wrap without truncating at 390 pt.
/// 4. Preferences "Your Interests" rows fit "College Basketball", "College Football", and
///    "Entertainment" completely without truncation at 390 pt.
/// 5. Watch Upcoming game hero (Look 1A) fits its "As of" line inside the first screen at
///    41 mm, 45 mm, and 46 mm.
/// 6. Watch rectangular complication 3-digit final ("TOR pregame · Final") is verified.
@MainActor
final class CutoffsAndSetNoun13386Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-22T02:00:00Z")!
    private let pt = TimeZone(identifier: "America/Los_Angeles")!

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    // MARK: - 1 & 3: Futures chart labels, badges & eyebrow

    func testFuturesChartLabelsAndTwoWordCityBadgesPreserveTeamNamesAndPeopleAndClubs() throws {
        // 2027 Pro Basketball Champion (52755651)
        let nbaCases: [(name: String, pct: Double, expectedLabel: String, expectedBadge: String)] = [
            ("San Antonio", 22, "San Antonio 22%", "SA"),
            ("Oklahoma City", 14, "Oklahoma City 14%", "OKC"),
            ("Philadelphia", 11, "Philadelphia 11%", "PHI"),
            ("Boston", 10, "Boston 10%", "BOS"),
            ("New York", 9, "New York 9%", "NY"),
            ("New Orleans", 4, "New Orleans 4%", "NO"),
            ("Golden State", 6, "Golden State 6%", "GS"),
            ("Los Angeles", 7, "Los Angeles 7%", "LA"),
        ]
        for entry in nbaCases {
            let chartLabel = EvolutionChartView.shortEndLabel192A(name: entry.name, percentValue: entry.pct)
            XCTAssertEqual(chartLabel, entry.expectedLabel)
            XCTAssertFalse(chartLabel.contains("…"), "Zero ellipsis allowed: \(chartLabel)")
            XCTAssertEqual(TeamShortName.futuresBadgeInitials(entry.name), entry.expectedBadge)
        }
        XCTAssertNotEqual(TeamShortName.futuresBadgeInitials("San Antonio"), "ANT")
        XCTAssertNotEqual(TeamShortName.futuresBadgeInitials("Oklahoma City"), "CIT")

        // People — Heisman Trophy (57792807)
        let heismanCases: [(name: String, pct: Double, expectedLabel: String, expectedBadge: String)] = [
            ("Jeremiah Smith", 25, "Smith 25%", "SMI"),
            ("Darian Mensah", 18, "Mensah 18%", "MEN"),
            ("CJ Carr", 15, "Carr 15%", "CAR"),
            ("Trinidad Chambliss", 6, "Chambliss 6%", "CHA"),
        ]
        for entry in heismanCases {
            let chartLabel = EvolutionChartView.shortEndLabel192A(name: entry.name, percentValue: entry.pct)
            XCTAssertEqual(chartLabel, entry.expectedLabel)
            XCTAssertFalse(chartLabel.contains("…"))
            XCTAssertEqual(TeamShortName.futuresBadgeInitials(entry.name), entry.expectedBadge)
        }

        // Clubs with nicknames — Stanley Cup (52755659)
        let nhlCases: [(name: String, pct: Double, expectedLabel: String, expectedBadge: String)] = [
            ("Carolina Hurricanes", 14, "Hurricanes 14%", "HUR"),
            ("Vegas Golden Knights", 10, "Golden Knights 10%", "VGK"),
            ("Colorado Avalanche", 11, "Avalanche 11%", "AVA"),
            ("Florida Panthers", 9, "Panthers 9%", "PAN"),
        ]
        for entry in nhlCases {
            let chartLabel = EvolutionChartView.shortEndLabel192A(name: entry.name, percentValue: entry.pct)
            XCTAssertEqual(chartLabel, entry.expectedLabel)
            XCTAssertFalse(chartLabel.contains("…"))
            XCTAssertEqual(TeamShortName.futuresBadgeInitials(entry.name), entry.expectedBadge)
        }
    }

    // MARK: - 2: Benchmark strip item_noun + "markets" fallback

    func testBenchmarkStripDecodesServerItemNounAndFallsBackToMarkets() throws {
        let withCouples = try JSONDecoder().decode(MachineryVisualBlock.self, from: Data(#"""
        {
          "form_id": "benchmark_strip",
          "initial_visible_limit": 3,
          "item_noun": "couples",
          "items": [
            {"market_id": 1, "title": "Couple A", "outcomes": [{"outcome_id": 10, "name": "Yes", "probability": 0.29, "rendered_percent": 29}]},
            {"market_id": 2, "title": "Couple B", "outcomes": [{"outcome_id": 20, "name": "Yes", "probability": 0.23, "rendered_percent": 23}]},
            {"market_id": 3, "title": "Couple C", "outcomes": [{"outcome_id": 30, "name": "Yes", "probability": 0.16, "rendered_percent": 16}]},
            {"market_id": 4, "title": "Couple D", "outcomes": [{"outcome_id": 40, "name": "Yes", "probability": 0.11, "rendered_percent": 11}]}
          ]
        }
        """#.utf8))
        XCTAssertEqual(withCouples.effectiveItemNoun, "couples")

        let withoutNoun = try JSONDecoder().decode(MachineryVisualBlock.self, from: Data(#"""
        {
          "form_id": "benchmark_strip",
          "initial_visible_limit": 3,
          "items": [
            {"market_id": 1, "title": "Market A", "outcomes": [{"outcome_id": 10, "name": "Yes", "probability": 0.42, "rendered_percent": 42}]},
            {"market_id": 2, "title": "Market B", "outcomes": [{"outcome_id": 20, "name": "Yes", "probability": 0.31, "rendered_percent": 31}]},
            {"market_id": 3, "title": "Market C", "outcomes": [{"outcome_id": 30, "name": "Yes", "probability": 0.22, "rendered_percent": 22}]},
            {"market_id": 4, "title": "Market D", "outcomes": [{"outcome_id": 40, "name": "Yes", "probability": 0.11, "rendered_percent": 11}]}
          ]
        }
        """#.utf8))
        XCTAssertEqual(withoutNoun.effectiveItemNoun, "markets")
        XCTAssertNotEqual(withoutNoun.effectiveItemNoun, "benchmarks")
    }

    // MARK: - 5 & 6: Watch scheduled hero fit & 3-digit Final complication model

    func testWatchScheduledHeroFitsWithAsOfAcrossAllThreeWatchSizes() throws {
        let scheduledJSON = #"""
        {
          "id": 14781148,
          "away_team": "Pittsburgh Steelers",
          "home_team": "Philadelphia Eagles",
          "away_team_data": {"team_id": 23, "abbreviation": "PIT", "primary_color": "#FFB612", "secondary_color": "#101820"},
          "home_team_data": {"team_id": 21, "abbreviation": "PHI", "primary_color": "#004C54", "secondary_color": "#A5ACAF"},
          "status": "scheduled",
          "sport": "americanfootball_nfl",
          "commence_time": "2026-11-22T18:00:00Z",
          "hero_probability": 0.35,
          "hero_probability_away": 0.65,
          "hero_probability_observed_at": "2026-11-21T21:48:00Z"
        }
        """#
        let game = try JSONDecoder().decode(WatchSelectedGame.self, from: Data(scheduledJSON.utf8))
        let now = ISO8601DateFormatter().date(from: "2026-11-21T21:49:00Z")!
        let model = WatchMatchupGameHeroModel297A.build(from: game, now: now, timeZone: pt, crestForTeamID: { _ in nil })
        XCTAssertEqual(model.stage, .before)
        XCTAssertEqual(model.bottomSummaryText, "As of 1m ago")

        // Model exact older clock so "As of 1:48 PM" appears too
        let laterNow = ISO8601DateFormatter().date(from: "2026-11-22T01:52:00Z")!
        let olderModel = WatchMatchupGameHeroModel297A.build(from: game, now: laterNow, timeZone: pt, crestForTeamID: { _ in nil })
        XCTAssertEqual(olderModel.bottomSummaryText, "As of 1:48 PM")

        #if canImport(UIKit)
        let topNavReserve: CGFloat = 64.5
        let cases: [(label: String, width: CGFloat, height: CGFloat)] = [
            ("41 mm", 176, 215),
            ("45 mm", 198, 242),
            ("46 mm", 208, 248),
        ]
        for watchCase in cases {
            let contentWidth = watchCase.width - 12
            let hero = WatchMatchupGamePageHeroView297A(model: olderModel, caseWidth: watchCase.width)
                .frame(width: contentWidth)
                .environment(\.colorScheme, .dark)
            let host = hostForMeasurement(hero, at: .large)
            host.overrideUserInterfaceStyle = .dark
            let measured = host.sizeThatFits(in: CGSize(width: contentWidth, height: 1000))
            let available = watchCase.height - topNavReserve
            XCTAssertLessThanOrEqual(
                measured.height,
                available,
                "\(watchCase.label) Scheduled hero (\(measured.height) pt) must fit first screen (\(available) pt) without clipping 'As of'"
            )
        }
        #endif
    }

    func testThreeDigitFinalWatchComplicationReading() throws {
        let tor = WatchCompactTeamIdentity(teamID: 28, abbreviation: "TOR")
        let det = WatchCompactTeamIdentity(teamID: 8, abbreviation: "DET")
        let observed = fixedNow.addingTimeInterval(-300)
        let reading = WatchRectangularReading(
            version: 1, eventID: 21705, kind: .finalResult,
            homeName: "Detroit Pistons", awayName: "Toronto Raptors", home: det, away: tor,
            homePercent: nil, homeScore: 102, awayScore: 105, commenceTime: nil,
            stateLabel: "Final", observedAt: observed, scoreObservedAt: observed
        )
        let snap = WatchComplicationSnapshot(
            eventID: 21705, title: "Toronto Raptors won", detail: "Final · 105–102",
            observedAt: observed, savedAt: fixedNow, rectangularReading: reading,
            matchup: WatchMatchupFacts217(pregameHomePercent: 71, pregameAwayPercent: 29)
        )
        let made = try XCTUnwrap(WatchMatchupReading217.make(snapshot: snap, now: fixedNow, timeZone: pt, crest: { _ in nil }))
        XCTAssertEqual(made.away.score, 105)
        XCTAssertEqual(made.home.score, 102)
        XCTAssertEqual(made.bigOwnerLabel, "TOR")
        XCTAssertEqual(made.smallLine, "Pregame · Final")
    }

    // MARK: - Windowed OCR Checks & Optional Render Exports

    #if canImport(UIKit)
    private func makeFuturesFixture(
        id: Int,
        name: String,
        category: String,
        sportCategory: String? = nil,
        outcomes: [(id: Int, name: String, pct: Double, earlyPct: Double)],
        abbreviations: [Int: String] = [:]
    ) throws -> (market: FuturesMarketDetail, timeline: ProbabilityTimelineResponse) {
        let outcomeDicts: [[String: Any]] = outcomes.map { o in
            [
                "id": o.id,
                "name": o.name,
                "probability": o.pct,
                "opening_probability": o.earlyPct,
                "observed_at": "2026-11-22T01:55:00Z",
            ]
        }
        var mDict: [String: Any] = [
            "id": id,
            "name": name,
            "category": category,
            "status": "open",
            "source": "polymarket",
            "updated_at": "2026-11-22T01:55:00Z",
            "outcomes": outcomeDicts,
        ]
        if let sportCategory {
            mDict["llm_sport_category"] = sportCategory
        }
        let market = try makeDecoder().decode(
            FuturesMarketDetail.self,
            from: try JSONSerialization.data(withJSONObject: mDict)
        )

        let earlyMap = Dictionary(uniqueKeysWithValues: outcomes.map { ($0.name, $0.earlyPct) })
        let midMap = Dictionary(uniqueKeysWithValues: outcomes.map { ($0.name, ($0.earlyPct + $0.pct) / 2.0) })
        let nowMap = Dictionary(uniqueKeysWithValues: outcomes.map { ($0.name, $0.pct) })
        let tlOutcomes: [[String: Any]] = outcomes.enumerated().map { idx, o in
            var entry: [String: Any] = [
                "id": o.id,
                "name": o.name,
                "current_probability": o.pct,
                "rank": idx + 1,
                "opening_probability": o.earlyPct,
            ]
            if let abbr = abbreviations[o.id] {
                entry["abbreviation"] = abbr
            }
            return entry
        }
        let tlDict: [String: Any] = [
            "market_id": id,
            "market_name": name,
            "sport_category": sportCategory ?? category,
            "source": "polymarket",
            "hours": 168,
            "top": 20,
            "bucket_seconds": 3600,
            "representation": "source",
            "timeline": [
                ["timestamp": "2026-11-15T01:55:00Z", "outcomes": earlyMap],
                ["timestamp": "2026-11-18T14:00:00Z", "outcomes": midMap],
                ["timestamp": "2026-11-22T01:55:00Z", "outcomes": nowMap],
            ],
            "outcomes": tlOutcomes,
            "coverage_hours": 168.0,
            "observation_times": 3,
        ]
        let timeline = try makeDecoder().decode(
            ProbabilityTimelineResponse.self,
            from: try JSONSerialization.data(withJSONObject: tlDict)
        )
        return (market, timeline)
    }

    private func renderAndOCR<V: View>(
        _ root: V,
        width: CGFloat,
        height: CGFloat? = nil,
        scheme: ColorScheme,
        scale: CGFloat = 2.0
    ) throws -> (image: UIImage, lines: [String]) {
        let style: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let styled = root
            .environment(\.colorScheme, scheme)
            .environment(\.horizontalSizeClass, .compact)
        let host = hostForMeasurement(styled, at: .large)
        host.overrideUserInterfaceStyle = style
        host.traitOverrides.horizontalSizeClass = .compact
        let targetH: CGFloat = {
            if let height { return height }
            let fit = host.sizeThatFits(in: CGSize(width: width, height: 3200))
            return max(120, ceil(fit.height) + 8)
        }()
        let bounds = CGRect(origin: .zero, size: CGSize(width: width, height: targetH))

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: bounds)
        }
        window.frame = bounds
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        host.view.frame = bounds
        let until = Date().addingTimeInterval(0.30)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < until

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = scale
        let img = UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
            if !host.view.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(img.cgImage), options: [:]).perform([req])
        let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        return (img, lines)
    }

    func testRenderedPagesZeroTruncationAndOptionalCaptures() throws {
        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13386_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(
                at: URL(fileURLWithPath: outDir, isDirectory: true),
                withIntermediateDirectories: true
            )
        }
        func maybeSave(_ img: UIImage, _ filename: String) throws {
            guard let outDir, !outDir.isEmpty, let png = img.pngData() else { return }
            try png.write(to: URL(fileURLWithPath: outDir, isDirectory: true).appendingPathComponent(filename))
        }

        // 1. 2027 Pro Basketball Champion (390 & 440, light & dark) + Heisman & Stanley Cup (390)
        let nba = try makeFuturesFixture(
            id: 52755651,
            name: "2027 Pro Basketball Champion",
            category: "championship",
            sportCategory: "basketball",
            outcomes: [
                (1, "San Antonio", 0.22, 0.16),
                (2, "Oklahoma City", 0.14, 0.15),
                (3, "Philadelphia", 0.11, 0.08),
                (4, "Boston", 0.10, 0.12),
                (5, "New York", 0.09, 0.08),
            ]
        )
        for width in [CGFloat(390), CGFloat(440)] {
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let bg = scheme == .dark ? Color.black : Color(uiColor: .systemGroupedBackground)
                let page = NavigationStack {
                    ScrollView {
                        FuturesAtlasPageView11666(
                            market: nba.market,
                            marketId: nba.market.id,
                            shareMessage: "",
                            onShare: {},
                            golfTournamentStart: nil,
                            golfTournamentEnd: nil,
                            chartRefreshToken: 0,
                            representation: .source,
                            preloadedTimeline: nba.timeline,
                            referenceNow: fixedNow
                        )
                    }
                    .background(bg)
                    .navigationTitle("Market Details")
                    .navigationBarTitleDisplayMode(.inline)
                }
                let (img, lines) = try renderAndOCR(page, width: width, height: 760, scheme: scheme)
                let joined = lines.joined(separator: " ")
                XCTAssertFalse(lines.contains { $0.contains("…") || $0.contains("...") }, "NBA \(width) \(scheme) must have zero ellipsis:\n\(lines.joined(separator: "\n"))")
                XCTAssertTrue(joined.contains("San Antonio 22%"), "NBA \(width) \(scheme):\n\(joined)")
                XCTAssertTrue(joined.contains("Oklahoma City 14%"), "NBA \(width) \(scheme):\n\(joined)")
                XCTAssertTrue(joined.contains("Philadelphia 11%"), "NBA \(width) \(scheme):\n\(joined)")
                XCTAssertTrue(joined.contains("Boston 10%"), "NBA \(width) \(scheme):\n\(joined)")
                XCTAssertTrue(lines.contains { $0 == "SA" }, "Expected SA badge on NBA \(width) \(scheme):\n\(joined)")
                let tag = scheme == .dark ? "dark" : "light"
                try maybeSave(img, "13386-nba-\(Int(width))-\(tag).png")
            }
        }

        // Control: Heisman & Stanley Cup (390, light)
        let heisman = try makeFuturesFixture(
            id: 57792807,
            name: "NCAA Football: 2026 Heisman Award Winner",
            category: "championship",
            sportCategory: "football",
            outcomes: [
                (1, "Jeremiah Smith", 0.25, 0.19),
                (2, "Darian Mensah", 0.18, 0.14),
                (3, "CJ Carr", 0.15, 0.16),
                (4, "Trinidad Chambliss", 0.06, 0.04),
            ]
        )
        let stanley = try makeFuturesFixture(
            id: 52755659,
            name: "2026-27 Stanley Cup Final Winner",
            category: "championship",
            sportCategory: "hockey",
            outcomes: [
                (1, "Carolina Hurricanes", 0.14, 0.11),
                (2, "Colorado Avalanche", 0.11, 0.10),
                (3, "Vegas Golden Knights", 0.10, 0.12),
                (4, "Florida Panthers", 0.09, 0.08),
            ]
        )
        for (slug, fx, expectedChart) in [
            ("heisman", heisman, "Smith 25%"),
            ("stanley", stanley, "Golden Knights 10%"),
        ] {
            let page = NavigationStack {
                ScrollView {
                    FuturesAtlasPageView11666(
                        market: fx.market,
                        marketId: fx.market.id,
                        shareMessage: "",
                        onShare: {},
                        golfTournamentStart: nil,
                        golfTournamentEnd: nil,
                        chartRefreshToken: 0,
                        representation: .source,
                        preloadedTimeline: fx.timeline,
                        referenceNow: fixedNow
                    )
                }
                .background(Color(uiColor: .systemGroupedBackground))
                .navigationTitle("Market Details")
                .navigationBarTitleDisplayMode(.inline)
            }
            let (img, lines) = try renderAndOCR(page, width: 390, height: 740, scheme: .light)
            let joined = lines.joined(separator: "\n")
            XCTAssertFalse(lines.contains { $0.contains("…") || $0.contains("...") }, "\(slug):\n\(joined)")
            XCTAssertTrue(joined.contains(expectedChart), "\(slug) missing \(expectedChart):\n\(joined)")
            try maybeSave(img, "13386-\(slug)-390-light.png")
        }

        // 2. Set page noun ("couples" vs fallback "markets", never "benchmarks") at 390 light/dark
        func makeBenchBlock(count: Int, noun: String?) -> MachineryVisualBlock {
            let items = (1...count).map { idx in
                MachineryMarketVisualItem(
                    marketId: idx,
                    title: noun == nil ? "Market Question \(idx)?" : "Celebrity Couple \(idx)",
                    outcomes: [
                        MachineryOutcomeVisual(
                            outcomeId: idx * 10,
                            marketId: idx,
                            name: "Yes",
                            probability: Double(max(5, 35 - idx * 3)) / 100.0,
                            renderedPercent: max(5, 35 - idx * 3)
                        )
                    ]
                )
            }
            return MachineryVisualBlock(
                formId: .benchmarkStrip,
                initialVisibleLimit: 3,
                itemNoun: noun,
                marketItems: items
            )
        }
        let couplesBlock = makeBenchBlock(count: 16, noun: "couples")
        let fallbackBlock = makeBenchBlock(count: 6, noun: nil)
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let bg = scheme == .dark ? Color.black : Color(uiColor: .systemGroupedBackground)
            let view = VStack(alignment: .leading, spacing: 18) {
                MachinerySectionBlockView(visualBlock: couplesBlock, members: [])
                MachinerySectionBlockView(visualBlock: fallbackBlock, members: [])
            }
            .padding(16)
            .background(bg)
            let (img, lines) = try renderAndOCR(view, width: 390, scheme: scheme)
            let joined = lines.joined(separator: "\n")
            XCTAssertTrue(joined.contains("Show all 16 couples (+13 more)"), "Set noun couples missing (\(scheme)):\n\(joined)")
            XCTAssertTrue(joined.contains("Show all 6 markets (+3 more)"), "Fallback noun markets missing (\(scheme)):\n\(joined)")
            XCTAssertFalse(joined.localizedCaseInsensitiveContains("benchmarks"), "benchmarks leaked (\(scheme)):\n\(joined)")
            try maybeSave(img, "13386-set-noun-390-\(scheme == .dark ? "dark" : "light").png")
        }

        // 3. Oscars Best Picture eyebrow at 390 light/dark
        let oscars = try makeFuturesFixture(
            id: 6173044,
            name: "Oscar Winner: Best Picture",
            category: "entertainment",
            sportCategory: "entertainment",
            outcomes: [
                (1, "The Odyssey", 0.54, 0.45),
                (2, "You Can See Everything", 0.21, 0.18),
                (3, "The Black Ball", 0.11, 0.10),
                (4, "Dune: Part Three", 0.10, 0.09),
            ]
        )
        let oscarPage = FuturesAtlasPresentation11666.build(market: oscars.market, now: fixedNow)
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let bg = scheme == .dark ? Color.black : Color(uiColor: .systemGroupedBackground)
            let card = FuturesAtlasHeadlineCard192A(
                market: oscars.market,
                header: oscarPage.header,
                headlineRows: FuturesAtlasPresentation11666.firstScreenHeadlineRows192A(for: oscarPage.body),
                allFieldLabel: "All 41 outcomes ›",
                timelineOutcomes: oscars.timeline.outcomes,
                onOpenDetails: {},
                onOpenFullField: {}
            )
            .padding(16)
            .background(bg)
            let (img, lines) = try renderAndOCR(card, width: 390, scheme: scheme)
            let joined = lines.joined(separator: " ").replacingOccurrences(of: "•", with: "·")
            XCTAssertTrue(joined.contains("Entertainment · Ceremony & Release Outlook"), "Oscars eyebrow truncated (\(scheme)):\n\(joined)")
            XCTAssertFalse(lines.contains { $0.contains("…") || $0.contains("...") }, "Oscars eyebrow has ellipsis (\(scheme)):\n\(joined)")
            try maybeSave(img, "13386-oscars-eyebrow-390-\(scheme == .dark ? "dark" : "light").png")
        }

        // 4. Preferences "College Basketball" row at 390 light/dark
        let prefs = try makeDecoder().decode(PreferencesResponse.self, from: Data(#"""
        {
          "home_location": "San Francisco, CA",
          "sport_affinities": {"nfl": 1.0, "ncaaf": 0.75, "ncaab": 0.5, "entertainment": 0.25},
          "onboarding_completed": true,
          "favorites": []
        }
        """#.utf8))
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let prefsView = NavigationStack {
                PreferencesView(loadedPrefsForTest: prefs)
            }
            .environmentObject(AuthManager())
            let (img, lines) = try renderAndOCR(prefsView, width: 390, height: 1150, scheme: scheme)
            let joined = lines.joined(separator: " ")
            XCTAssertTrue(joined.contains("College Football"), "Preferences 390 \(scheme):\n\(joined)")
            XCTAssertTrue(joined.contains("College Basketball"), "Preferences 390 \(scheme) truncated College Basketball:\n\(joined)")
            XCTAssertFalse(lines.contains { $0.contains("Basket...") || $0.contains("Basket…") }, "Preferences 390 \(scheme) ellipsis:\n\(joined)")
            try maybeSave(img, "13386-prefs-390-\(scheme == .dark ? "dark" : "light").png")
        }

        // 5. Watch Scheduled game hero (41, 45, 46 mm) with "As of"
        let scheduledJSON = #"""
        {
          "id": 14781148,
          "away_team": "Pittsburgh Steelers",
          "home_team": "Philadelphia Eagles",
          "away_team_data": {"team_id": 23, "abbreviation": "PIT", "primary_color": "#FFB612", "secondary_color": "#101820"},
          "home_team_data": {"team_id": 21, "abbreviation": "PHI", "primary_color": "#004C54", "secondary_color": "#A5ACAF"},
          "status": "scheduled",
          "sport": "americanfootball_nfl",
          "commence_time": "2026-11-22T18:00:00Z",
          "hero_probability": 0.35,
          "hero_probability_away": 0.65,
          "hero_probability_observed_at": "2026-11-21T21:48:00Z"
        }
        """#
        let schedGame = try JSONDecoder().decode(WatchSelectedGame.self, from: Data(scheduledJSON.utf8))
        let laterNow = ISO8601DateFormatter().date(from: "2026-11-22T01:52:00Z")!
        let schedModel = WatchMatchupGameHeroModel297A.build(from: schedGame, now: laterNow, timeZone: pt, crestForTeamID: { _ in nil })
        let topNavReserve: CGFloat = 64.5
        let watchCases: [(label: String, width: CGFloat, height: CGFloat)] = [
            ("41 mm", 176, 215),
            ("45 mm", 198, 242),
            ("46 mm", 208, 248),
        ]
        let strip = HStack(alignment: .top, spacing: 14) {
            ForEach(watchCases, id: \.label) { watchCase in
                VStack(alignment: .leading, spacing: 6) {
                    Text("\(watchCase.label) (\(Int(watchCase.width))×\(Int(watchCase.height)))")
                        .font(.caption.bold())
                        .foregroundStyle(.white.opacity(0.85))
                    ZStack(alignment: .top) {
                        Color.black
                        VStack(alignment: .leading, spacing: 0) {
                            VStack(alignment: .trailing, spacing: 0) {
                                Text("1:52")
                                    .font(.system(size: 13, weight: .semibold).monospacedDigit())
                                    .foregroundStyle(.white)
                                Text("Your game")
                                    .font(.system(size: 14, weight: .semibold))
                                    .foregroundStyle(.white.opacity(0.65))
                            }
                            .frame(maxWidth: .infinity, alignment: .trailing)
                            .padding(.trailing, 10)
                            .frame(height: topNavReserve, alignment: .bottom)
                            .padding(.bottom, 4)

                            WatchMatchupGamePageHeroView297A(model: schedModel, caseWidth: watchCase.width)
                                .padding(.horizontal, 6)
                        }
                    }
                    .frame(width: watchCase.width, height: watchCase.height, alignment: .top)
                    .clipped()
                    .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 28, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.26), lineWidth: 1.5)
                    )
                }
            }
        }
        .padding(16)
        .background(Color(red: 0.06, green: 0.07, blue: 0.09))

        let (watchImg, watchLines) = try renderAndOCR(strip, width: 670, height: 310, scheme: .dark)
        let watchJoined = watchLines.joined(separator: "\n")
        XCTAssertEqual(
            watchJoined.components(separatedBy: "As of 1:48 PM").count - 1,
            3,
            "All 3 Watch sizes must show unclipped 'As of 1:48 PM':\n\(watchJoined)"
        )
        try maybeSave(watchImg, "13386-watch-upcoming-41-45-46mm.png")
    }

    func testServedShortNamesOverrideFallbackInitialsAndPreserveAbsentFallbacks() throws {
        let stanleyMeta = try makeDecoder().decode(
            [TimelineOutcomeMeta].self,
            from: Data(#"""
            [
              {"id": 198632542, "name": "Minnesota Wild", "abbreviation": "MIN"},
              {"id": 198632538, "name": "Carolina Hurricanes", "abbreviation": "CAR"},
              {"id": 198632537, "name": "Colorado Avalanche", "abbreviation": "COL"},
              {"id": 198632540, "name": "Edmonton Oilers", "abbreviation": "EDM"},
              {"id": 198632536, "name": "Florida Panthers", "abbreviation": "FLA"},
              {"id": 198632549, "name": "New Jersey Devils", "abbreviation": "NJ"},
              {"id": 198632539, "name": "Vegas Golden Knights", "abbreviation": "VGK"},
              {"id": 198632541, "name": "Tampa Bay Lightning", "abbreviation": "TB"}
            ]
            """#.utf8)
        )
        for (id, name, expected) in [
            (198632538, "Carolina Hurricanes", "CAR"),
            (198632537, "Colorado Avalanche", "COL"),
            (198632536, "Florida Panthers", "FLA"),
            (198632539, "Vegas Golden Knights", "VGK"),
            (198632542, "Minnesota Wild", "MIN"),
            (198632540, "Edmonton Oilers", "EDM"),
            (198632549, "New Jersey Devils", "NJ"),
            (198632541, "Tampa Bay Lightning", "TB"),
        ] {
            XCTAssertEqual(
                FuturesAtlasHeadlineCard192A.resolvedBadgeInitials(
                    for: name,
                    outcomeId: id,
                    timelineOutcomes: stanleyMeta
                ),
                expected
            )
            XCTAssertEqual(
                TeamLogoView.badge(teamName: name, opponentName: nil, servedAbbreviation: expected),
                expected
            )
        }
        XCTAssertNotEqual(
            FuturesAtlasHeadlineCard192A.resolvedBadgeInitials(for: "Carolina Hurricanes", outcomeId: 198632538, timelineOutcomes: stanleyMeta),
            "HUR"
        )
        XCTAssertNotEqual(
            FuturesAtlasHeadlineCard192A.resolvedBadgeInitials(for: "Colorado Avalanche", outcomeId: 198632537, timelineOutcomes: stanleyMeta),
            "AVA"
        )
        XCTAssertNotEqual(
            FuturesAtlasHeadlineCard192A.resolvedBadgeInitials(for: "Florida Panthers", outcomeId: 198632536, timelineOutcomes: stanleyMeta),
            "PAN"
        )

        let mlbMeta = try makeDecoder().decode(
            [TimelineOutcomeMeta].self,
            from: Data(#"""
            [
              {"id": 259554125, "name": "Los Angeles Dodgers", "abbreviation": "LAD"},
              {"id": 259554124, "name": "Milwaukee Brewers", "abbreviation": "MIL"},
              {"id": 259217597, "name": "New York Yankees", "abbreviation": "NYY"},
              {"id": 256920354, "name": "San Diego Padres", "abbreviation": "SD"}
            ]
            """#.utf8)
        )
        for (id, name, expected) in [
            (259554125, "Los Angeles Dodgers", "LAD"),
            (259554124, "Milwaukee Brewers", "MIL"),
            (259217597, "New York Yankees", "NYY"),
            (256920354, "San Diego Padres", "SD"),
        ] {
            XCTAssertEqual(
                FuturesAtlasHeadlineCard192A.resolvedBadgeInitials(
                    for: name,
                    outcomeId: id,
                    timelineOutcomes: mlbMeta
                ),
                expected
            )
            XCTAssertEqual(
                TeamLogoView.badge(teamName: name, opponentName: nil, servedAbbreviation: expected),
                expected
            )
        }

        // Absent or whitespace-only abbreviations fall back to futuresBadgeInitials; result words remain refused.
        let fallbackMeta = try makeDecoder().decode(
            [TimelineOutcomeMeta].self,
            from: Data(#"""
            [
              {"id": 1, "name": "San Antonio"},
              {"id": 2, "name": "Oklahoma City", "abbreviation": "   "},
              {"id": 3, "name": "Minnesota Wild", "abbreviation": "WIN"}
            ]
            """#.utf8)
        )
        XCTAssertEqual(
            FuturesAtlasHeadlineCard192A.resolvedBadgeInitials(for: "San Antonio", outcomeId: 1, timelineOutcomes: fallbackMeta),
            "SA"
        )
        XCTAssertEqual(
            FuturesAtlasHeadlineCard192A.resolvedBadgeInitials(for: "Oklahoma City", outcomeId: 2, timelineOutcomes: fallbackMeta),
            "OKC"
        )
        XCTAssertEqual(
            FuturesAtlasHeadlineCard192A.resolvedBadgeInitials(for: "Philadelphia", timelineOutcomes: nil),
            "PHI"
        )
        XCTAssertEqual(
            FuturesAtlasHeadlineCard192A.resolvedBadgeInitials(for: "Jeremiah Smith", timelineOutcomes: nil),
            "SMI"
        )
        XCTAssertEqual(
            FuturesAtlasHeadlineCard192A.resolvedBadgeInitials(for: "Minnesota Wild", outcomeId: 3, timelineOutcomes: fallbackMeta),
            "MW"
        )
    }

    func testRenderedServedBadgeAbbreviationsAt390LightAndDark() throws {
        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13386_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(
                at: URL(fileURLWithPath: outDir, isDirectory: true),
                withIntermediateDirectories: true
            )
        }
        let stanley = try makeFuturesFixture(
            id: 52755659,
            name: "2026-27 Stanley Cup Final Winner",
            category: "championship",
            sportCategory: "hockey",
            outcomes: [
                (198632538, "Carolina Hurricanes", 0.14, 0.11),
                (198632537, "Colorado Avalanche", 0.11, 0.10),
                (198632539, "Vegas Golden Knights", 0.10, 0.12),
                (198632536, "Florida Panthers", 0.09, 0.08),
            ],
            abbreviations: [
                198632538: "CAR",
                198632537: "COL",
                198632539: "VGK",
                198632536: "FLA",
            ]
        )
        let ws = try makeFuturesFixture(
            id: 68198529,
            name: "MLB World Series Champion 2027",
            category: "championship",
            sportCategory: "baseball",
            outcomes: [
                (259554125, "Los Angeles Dodgers", 0.24, 0.22),
                (259554124, "Milwaukee Brewers", 0.16, 0.14),
                (256920354, "San Diego Padres", 0.12, 0.10),
                (259217597, "New York Yankees", 0.11, 0.12),
            ],
            abbreviations: [
                259554125: "LAD",
                259554124: "MIL",
                256920354: "SD",
                259217597: "NYY",
            ]
        )
        let nbaFallback = try makeFuturesFixture(
            id: 52755651,
            name: "2027 Pro Basketball Champion",
            category: "championship",
            sportCategory: "basketball",
            outcomes: [
                (198632415, "San Antonio", 0.22, 0.16),
                (198632414, "Oklahoma City", 0.14, 0.15),
                (198632416, "Philadelphia", 0.11, 0.08),
                (198632418, "Boston", 0.10, 0.12),
            ]
        )

        let stanleyPage = FuturesAtlasPresentation11666.build(market: stanley.market, now: fixedNow)
        let wsPage = FuturesAtlasPresentation11666.build(market: ws.market, now: fixedNow)
        let nbaPage = FuturesAtlasPresentation11666.build(market: nbaFallback.market, now: fixedNow)

        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let bg = scheme == .dark ? Color.black : Color(uiColor: .systemGroupedBackground)
            let view = VStack(alignment: .leading, spacing: 14) {
                FuturesAtlasHeadlineCard192A(
                    market: stanley.market,
                    header: stanleyPage.header,
                    headlineRows: FuturesAtlasPresentation11666.firstScreenHeadlineRows192A(for: stanleyPage.body),
                    allFieldLabel: "All 32 teams ›",
                    timelineOutcomes: stanley.timeline.outcomes,
                    onOpenDetails: {},
                    onOpenFullField: {}
                )
                FuturesAtlasHeadlineCard192A(
                    market: ws.market,
                    header: wsPage.header,
                    headlineRows: FuturesAtlasPresentation11666.firstScreenHeadlineRows192A(for: wsPage.body),
                    allFieldLabel: "All 30 teams ›",
                    timelineOutcomes: ws.timeline.outcomes,
                    onOpenDetails: {},
                    onOpenFullField: {}
                )
                FuturesAtlasHeadlineCard192A(
                    market: nbaFallback.market,
                    header: nbaPage.header,
                    headlineRows: FuturesAtlasPresentation11666.firstScreenHeadlineRows192A(for: nbaPage.body),
                    allFieldLabel: "All 30 teams ›",
                    timelineOutcomes: nbaFallback.timeline.outcomes,
                    onOpenDetails: {},
                    onOpenFullField: {}
                )
            }
            .padding(16)
            .background(bg)

            let (img, lines) = try renderAndOCR(view, width: 390, scheme: scheme)
            let tokenSet = Set(lines)
            for expected in ["CAR", "COL", "VGK", "FLA", "LAD", "MIL", "SD", "NYY", "SA", "OKC", "PHI", "BOS"] {
                XCTAssertTrue(tokenSet.contains(expected), "Missing badge \(expected) at 390 \(scheme):\n\(lines.joined(separator: "\n"))")
            }
            for forbidden in ["HUR", "AVA", "PAN", "BRE", "SDP"] {
                XCTAssertFalse(tokenSet.contains(forbidden), "Stale fallback badge \(forbidden) leaked at 390 \(scheme):\n\(lines.joined(separator: "\n"))")
            }
            if let outDir, !outDir.isEmpty, let png = img.pngData() {
                let tag = scheme == .dark ? "dark" : "light"
                try png.write(to: URL(fileURLWithPath: outDir, isDirectory: true).appendingPathComponent("13386-served-badges-390-\(tag).png"))
            }
        }
    }
    #endif
}
