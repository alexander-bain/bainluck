import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// Item 3 — Largest-text (`.accessibility5`) sweep of this week's new screens across
/// `320 pt` and `390 pt` (iPhone) and `834 pt` (iPad), in both Light and Dark appearances:
/// 1. Division race cards (`MachineryDiscoverCardView` & container hub `MachinerySectionBlockView`)
/// 2. Sports tab on iPad (`FeedView` at `834 pt` Light & Dark)
/// 3. Usage-stats card (`TelemetryConsentPrompt`) & Checklist (`FirstRunChecklistView364A`)
/// 4. App icon row (`PreferencesView`) & picker (`AppIconPickerView423A`)
/// 5. Soccer withheld away cells (`EventSportHeadlineCard12472`: `"No probability yet"` & `"No recent probability"`)
/// 6. Like heart (`DiscoverCardActionBar420D`, `NativeEventDiscoverCard`, `NativeFuturesDiscoverCard`)
@MainActor
final class LargestTextWeekSweepAX5Tests: XCTestCase {

    #if os(iOS)
    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-27T20:00:00Z")!

    private nonisolated final class SportsFeedStub: SportsFeedProviding, @unchecked Sendable {
        let feed: FeedResponse
        init(feed: FeedResponse) { self.feed = feed }
        nonisolated func fetchSportsFeed() async throws -> FeedResponse { feed }
        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse {
            let d = JSONDecoder()
            d.keyDecodingStrategy = .convertFromSnakeCase
            return try d.decode(
                FeedResponse.self,
                from: Data(#"{"items":[],"total":0,"limit":50,"offset":0,"has_more":false}"#.utf8)
            )
        }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse {
            let d = JSONDecoder()
            d.keyDecodingStrategy = .convertFromSnakeCase
            return try d.decode(
                GroupedFeedResponse.self,
                from: Data(#"{"feed":[],"total":0,"limit":50,"offset":0}"#.utf8)
            )
        }
    }

    // MARK: - Renderers

    private func renderIntrinsic<V: View>(
        _ view: V,
        width: CGFloat,
        colorScheme: ColorScheme,
        padOuter: Bool = true
    ) -> UIImage {
        let bg = colorScheme == .dark
            ? Color.black
            : Color(uiColor: .systemGroupedBackground)
        let styled = Group {
            if padOuter {
                view
                    .frame(width: max(1, width - 32))
                    .padding(16)
            } else {
                view
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(width: width)
        .background(bg)
        .ignoresSafeArea()
        .environment(\.colorScheme, colorScheme)
        .environment(\.dynamicTypeSize, .accessibility5)
        .environment(\.horizontalSizeClass, width >= 700 ? .regular : .compact)

        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let host = hostForMeasurement(styled, at: .accessibility5)
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.insetsLayoutMarginsFromSafeArea = false
        host.traitOverrides.horizontalSizeClass = width >= 700 ? .regular : .compact
        host.traitOverrides.preferredContentSizeCategory = .accessibilityExtraExtraExtraLarge
        host.view.traitOverrides.preferredContentSizeCategory = .accessibilityExtraExtraExtraLarge
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 10)

        let measuredInitial = host.sizeThatFits(in: CGSize(width: width, height: 6000))
        let initialBounds = CGRect(origin: .zero, size: CGSize(width: width, height: max(120, ceil(measuredInitial.height) + 16)))

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: initialBounds)
        window.frame = initialBounds
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        host.view.frame = initialBounds
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let measuredFinal = host.sizeThatFits(in: CGSize(width: width, height: 6000))
        XCTAssertLessThanOrEqual(
            measuredFinal.width,
            width + 1.0,
            "AX5 card exceeded \(width) pt viewport width (\(measuredFinal.width) pt)"
        )
        let finalHeight = max(120, ceil(measuredFinal.height))
        let finalBounds = CGRect(origin: .zero, size: CGSize(width: width, height: finalHeight))
        window.frame = finalBounds
        host.view.frame = finalBounds
        host.view.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: finalBounds.size, format: fmt).image { _ in
            _ = window.drawHierarchy(in: finalBounds, afterScreenUpdates: true)
        }
    }

    private func renderFixedViewport<V: View>(
        _ view: V,
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme
    ) -> UIImage {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let wrapped = view
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, .accessibility5)
            .environment(\.horizontalSizeClass, width >= 700 ? .regular : .compact)
            .frame(width: width, height: height)
            .clipped()

        let host = hostForMeasurement(wrapped, at: .accessibility5)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.insetsLayoutMarginsFromSafeArea = false
        host.traitOverrides.horizontalSizeClass = width >= 700 ? .regular : .compact
        host.traitOverrides.preferredContentSizeCategory = .accessibilityExtraExtraExtraLarge
        host.view.traitOverrides.preferredContentSizeCategory = .accessibilityExtraExtraExtraLarge

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        host.view.frame = bounds
        host.view.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        for _ in 0..<8 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = height > 2300 ? 1.25 : (height > 1950 ? 1.5 : 2.0)
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            _ = window.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
    }

    private func assertCleanOCR(
        in image: UIImage,
        label: String,
        requiredTokens: [String],
        forbiddenSubstrings: [String] = ["\u{2026}", "...", "Preferen\u{2026}", "Preferen...", "Go to Disco\u{2026}", "Go to Disco...", "anony-", "analyt-", "Notifica-", "school s"],
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws {
        let obs = try ocrObservations(in: image)
        let flat = obs.map(\.text).joined(separator: " ")
        XCTAssertFalse(obs.isEmpty, "\(label): OCR found no text (blank render)", file: file, line: line)
        for bad in forbiddenSubstrings {
            XCTAssertFalse(
                flat.contains(bad),
                "\(label): forbidden truncation/hyphenation '\(bad)' in OCR: \(flat)",
                file: file,
                line: line
            )
        }
        for token in requiredTokens {
            XCTAssertTrue(
                flat.localizedCaseInsensitiveContains(token),
                "\(label): missing required '\(token)' in OCR: \(flat)",
                file: file,
                line: line
            )
        }
    }

    private func ocrObservations(in image: UIImage) throws -> [(text: String, box: CGRect)] {
        let cg = try XCTUnwrap(image.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { obs in
            guard let s = obs.topCandidates(1).first?.string else { return nil }
            return (s, obs.boundingBox)
        }
    }

    private func maybeSave(_ image: UIImage, name: String) throws {
        let dir = ProcessInfo.processInfo.environment["TEST_RUNNER_AX5_SWEEP_DIR"]
            ?? ProcessInfo.processInfo.environment["AX5_SWEEP_DIR"]
        guard let dir, !dir.isEmpty else { return }
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        try XCTUnwrap(image.pngData()).write(
            to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"),
            options: .atomic
        )
    }

    // MARK: - Fixtures

    private func makeDivisionRaceFixtures() -> (discoverCard: MachineryCardContract, hubBlock: MachineryVisualBlock) {
        let discoverCard = MachineryCardContract(
            slug: "machinery-afc-west-duel",
            formId: .siblingFieldsGrid,
            kicker: "AFC WEST",
            title: "AFC West Title Race",
            subtitle: "All four AFC West teams in the division title race.",
            footer: "See all 4 divisions",
            scaleOrdered: false,
            sectionCount: 2,
            outcomeRows: [
                MachineryOutcomeVisual(outcomeId: 846594, marketId: 53675, name: "Denver Broncos", probability: 0.525, renderedPercent: 53, unflooredPercent: 53, art: MachinerySubjectArt(kind: "monogram", accentColor: "#FB4F14", initials: "DEN"), settledOut: false),
                MachineryOutcomeVisual(outcomeId: 846593, marketId: 53675, name: "Kansas City Chiefs", probability: 0.0099, renderedPercent: 1, unflooredPercent: 1, art: MachinerySubjectArt(kind: "monogram", accentColor: "#E31837", initials: "KC"), settledOut: false),
            ],
            unpricedOutcomes: [
                MachineryOutcomeVisual(outcomeId: 846592, marketId: 53675, name: "Los Angeles Chargers", probability: 0, renderedPercent: 0, art: MachinerySubjectArt(kind: "monogram", accentColor: "#0080C6", initials: "LAC"), settledOut: false),
                MachineryOutcomeVisual(outcomeId: 846591, marketId: 53675, name: "Las Vegas Raiders", probability: 0, renderedPercent: 0, art: MachinerySubjectArt(kind: "monogram", accentColor: "#000000", initials: "LV"), settledOut: true),
            ]
        )

        let hubBlock = MachineryVisualBlock(
            formId: .siblingFieldsGrid,
            initialVisibleLimit: 3,
            itemNoun: "divisions",
            marketItems: [
                MachineryMarketVisualItem(
                    marketId: 53680,
                    title: "NFC West Championship",
                    outcomes: [
                        MachineryOutcomeVisual(outcomeId: 11, name: "San Francisco 49ers", probability: 0.61, renderedPercent: 61, unflooredPercent: 61, art: MachinerySubjectArt(kind: "monogram", accentColor: "#AA0000", initials: "SF"), settledOut: false),
                        MachineryOutcomeVisual(outcomeId: 12, name: "Los Angeles Rams", probability: 0.38, renderedPercent: 38, unflooredPercent: 38, art: MachinerySubjectArt(kind: "monogram", accentColor: "#003594", initials: "LAR"), settledOut: false),
                        MachineryOutcomeVisual(outcomeId: 13, name: "Seattle Seahawks", probability: 0.004, renderedPercent: 1, unflooredPercent: 0, art: MachinerySubjectArt(kind: "monogram", accentColor: "#002244", initials: "SEA"), settledOut: false),
                    ],
                    unpricedOutcomes: [
                        MachineryOutcomeVisual(outcomeId: 14, name: "Arizona Cardinals", probability: 0, renderedPercent: 0, art: MachinerySubjectArt(kind: "monogram", accentColor: "#97233F", initials: "ARI"), settledOut: false),
                    ]
                ),
                MachineryMarketVisualItem(
                    marketId: 53681,
                    title: "AFC South",
                    outcomes: [
                        MachineryOutcomeVisual(outcomeId: 21, name: "Houston Texans", probability: 0.57, renderedPercent: 57, unflooredPercent: 57, art: MachinerySubjectArt(kind: "monogram", accentColor: "#03202F", initials: "HOU"), settledOut: false),
                        MachineryOutcomeVisual(outcomeId: 22, name: "Indianapolis Colts", probability: 0.42, renderedPercent: 42, unflooredPercent: 42, art: MachinerySubjectArt(kind: "monogram", accentColor: "#002C5F", initials: "IND"), settledOut: false),
                        MachineryOutcomeVisual(outcomeId: 23, name: "Jacksonville Jaguars", probability: 0.005, renderedPercent: 1, unflooredPercent: 0, art: MachinerySubjectArt(kind: "monogram", accentColor: "#006778", initials: "JAX"), settledOut: false),
                    ],
                    unpricedOutcomes: [
                        MachineryOutcomeVisual(outcomeId: 24, name: "Tennessee Titans", probability: 0, renderedPercent: 0, art: MachinerySubjectArt(kind: "monogram", accentColor: "#4B92DB", initials: "TEN"), settledOut: true),
                    ]
                ),
            ]
        )

        return (discoverCard, hubBlock)
    }

    private func makeMultiLeagueSportsFeed() throws -> FeedResponse {
        let iso = ISO8601DateFormatter()
        let live1 = iso.string(from: fixedNow.addingTimeInterval(-3600))
        let live2 = iso.string(from: fixedNow.addingTimeInterval(-2400))
        let soon1 = iso.string(from: fixedNow.addingTimeInterval(3600))
        let soon2 = iso.string(from: fixedNow.addingTimeInterval(5400))
        let soon3 = iso.string(from: fixedNow.addingTimeInterval(7200))

        let json = """
        {
          "items": [
            {
              "type": "event",
              "score": 98,
              "data": {
                "id": 9138691,
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "home_team": "Kansas City Chiefs",
                "away_team": "Buffalo Bills",
                "home_team_data": {"team_id": 12, "name": "Kansas City Chiefs", "short_name": "Chiefs", "abbreviation": "KC", "primary_color": "#E31837"},
                "away_team_data": {"team_id": 2, "name": "Buffalo Bills", "short_name": "Bills", "abbreviation": "BUF", "primary_color": "#00338D"},
                "commence_time": "\(live1)",
                "status": "live",
                "home_score": 21,
                "away_score": 17,
                "espn": {"period": "Q3", "clock": "4:18"},
                "current_odds": {"home_probability": 0.58, "away_probability": 0.42}
              }
            },
            {
              "type": "event",
              "score": 95,
              "data": {
                "id": 9138692,
                "sport": "americanfootball_ncaaf",
                "sport_name": "NCAAF",
                "home_team": "Ohio State Buckeyes",
                "away_team": "Michigan Wolverines",
                "home_team_data": {"team_id": 194, "name": "Ohio State Buckeyes", "short_name": "Ohio State", "abbreviation": "OSU", "primary_color": "#BB0000"},
                "away_team_data": {"team_id": 130, "name": "Michigan Wolverines", "short_name": "Michigan", "abbreviation": "MICH", "primary_color": "#00274C"},
                "commence_time": "\(live2)",
                "status": "live",
                "home_score": 14,
                "away_score": 10,
                "espn": {"period": "Q2", "clock": "2:05"},
                "current_odds": {"home_probability": 0.64, "away_probability": 0.36}
              }
            },
            {
              "type": "event",
              "score": 91,
              "data": {
                "id": 9138694,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "home_team": "Boston Celtics",
                "away_team": "New York Knicks",
                "home_team_data": {"team_id": 2, "name": "Boston Celtics", "short_name": "Celtics", "abbreviation": "BOS", "primary_color": "#007A33"},
                "away_team_data": {"team_id": 18, "name": "New York Knicks", "short_name": "Knicks", "abbreviation": "NYK", "primary_color": "#006BB6"},
                "commence_time": "\(soon1)",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.62, "away_probability": 0.38}
              }
            },
            {
              "type": "event",
              "score": 89,
              "data": {
                "id": 9138695,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "home_team": "Los Angeles Lakers",
                "away_team": "Golden State Warriors",
                "home_team_data": {"team_id": 13, "name": "Los Angeles Lakers", "short_name": "Lakers", "abbreviation": "LAL", "primary_color": "#552583"},
                "away_team_data": {"team_id": 9, "name": "Golden State Warriors", "short_name": "Warriors", "abbreviation": "GSW", "primary_color": "#1D428A"},
                "commence_time": "\(soon2)",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.51, "away_probability": 0.49}
              }
            },
            {
              "type": "event",
              "score": 85,
              "data": {
                "id": 9138697,
                "sport": "soccer_epl",
                "sport_name": "Premier League",
                "home_team": "Arsenal",
                "away_team": "Liverpool",
                "home_team_data": {"team_id": 359, "name": "Arsenal", "short_name": "Arsenal", "abbreviation": "ARS", "primary_color": "#EF0107"},
                "away_team_data": {"team_id": 364, "name": "Liverpool", "short_name": "Liverpool", "abbreviation": "LIV", "primary_color": "#C8102E"},
                "commence_time": "\(soon3)",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.43, "away_probability": 0.31, "draw_probability": 0.26}
              }
            }
          ],
          "total": 5,
          "limit": 50,
          "offset": 0,
          "has_more": false
        }
        """
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FeedResponse.self, from: Data(json.utf8))
    }

    private func makeChecklistContent() -> FirstRunChecklistContent364A {
        FirstRunChecklistContent364A(
            lookupExamples: [],
            startWithTonight: [],
            discoverSets: [],
            rowPreviews: [
                .lookUp: FirstRunChecklistRowPreview364A(
                    subtitle: "Search any game, team, award, or election",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "magnifyingglass",
                    accentHex: "#005CC2"
                ),
                .follow: FirstRunChecklistRowPreview364A(
                    subtitle: "Teams, cities, schools, or topics",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "star.fill",
                    accentHex: "#047857"
                ),
                .exploreSets: FirstRunChecklistRowPreview364A(
                    subtitle: "Pick topics to shape your Discover feed",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "square.grid.2x2.fill",
                    accentHex: "#7C3AED"
                ),
                .syncDevices: FirstRunChecklistRowPreview364A(
                    subtitle: "Sign in to sync across devices",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "laptopcomputer.and.iphone",
                    accentHex: "#005CC2"
                ),
                .alerts: FirstRunChecklistRowPreview364A(
                    subtitle: "Game starts & 15+ point swings",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "bell.badge.fill",
                    accentHex: "#D97706"
                ),
            ],
            subjectArtByCategory: [:]
        )
    }

    private func makeSoccerDetail(status: String) throws -> (EventDetail, EventSportHeadlines12472.Model) {
        let isLive = status == "live"
        let json = """
        {
          "id": 15344943,
          "sport": "soccer_epl",
          "sport_name": "EPL",
          "home_team": "Nottingham Forest",
          "away_team": "Chelsea",
          "commence_time": "\(isLive ? "2026-11-27T18:40:00Z" : "2026-11-28T20:00:00Z")",
          "start_is_tbd": false,
          "status": "\(status)",
          "home_score": \(isLive ? "1" : "null"),
          "away_score": \(isLive ? "0" : "null"),
          "home_team_data": {"abbreviation": "NFO", "primary_color": "#c8102e", "secondary_color": "#1B3624", "record": "2-3-6"},
          "away_team_data": {"abbreviation": "CHE", "primary_color": "#144992", "secondary_color": "#FFFFFF", "record": "5-1-5"},
          "espn": \(isLive ? #"{"period":"2nd Half","game_clock":"67'"}"# : #"{"broadcast":"USA Net, Universo"}"#),
          "current_odds": {
            "captured_at": "2026-11-27T19:59:30Z",
            "home_probability": 0.62,
            "home_rendered_percent": 62,
            "away_probability": 0.38,
            "away_rendered_percent": 38,
            "draw_probability": null
          },
          "hero_probability": 0.62,
          "hero_probability_source": "kalshi",
          "hero_probability_observed_at": "2026-11-27T19:59:30Z"
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let event = try dec.decode(EventDetail.self, from: Data(json.utf8))
        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: isLive ? "67'" : nil,
                hasScore: isLive,
                numberStreams: isLive,
                now: fixedNow
            )
        )
        return (event, model)
    }

    private func teamColors(for event: EventDetail, colorScheme: ColorScheme) -> (away: Color, home: Color) {
        if colorScheme == .dark {
            let darkHexes = EventDetailView.teamColorHexes(event, colorScheme: .dark)
            return (Color(hex: darkHexes.away), Color(hex: darkHexes.home))
        }
        return TeamTextContrast.cardColors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor,
            awaySecondaryHex: event.awayTeamData?.secondaryColor,
            checkHueFamily: true
        )
    }

    // MARK: - Sweep Test

    func testSweepThisWeeksNewScreensAtAX5AcrossWidthsAndAppearances() async throws {
        let suiteName = "ax5-sweep-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        let navCoordinator = NavigationCoordinator()
        let authManager = AuthManager(restoreOnInit: false)
        authManager.user = nil

        let widths: [CGFloat] = [320, 390, 834]
        let schemes: [(ColorScheme, String)] = [(.light, "light"), (.dark, "dark")]
        let (discoverRaceCard, hubRaceBlock) = makeDivisionRaceFixtures()

        // 1. Division race cards (Discover + Container Hub grid)
        for width in widths {
            let isIPad = width >= 700
            let hubCols = ContainerHubGridLayout13417.columnCount(
                horizontalSizeClass: isIPad ? .regular : .compact,
                dynamicTypeSize: .accessibility5,
                availableWidth: ContainerHubGridLayout13417.innerContentWidth(containerWidth: width)
            )
            for (scheme, schemeName) in schemes {
                let discoverImg = renderIntrinsic(
                    MachineryDiscoverCardView(card: discoverRaceCard)
                        .environmentObject(pinManager)
                        .environmentObject(navCoordinator)
                        .environmentObject(authManager),
                    width: width,
                    colorScheme: scheme
                )
                try assertCleanOCR(
                    in: discoverImg,
                    label: "1_division_discover_\(Int(width))_\(schemeName)",
                    requiredTokens: ["Denver Broncos", "53%", "Kansas City Chiefs", "<1%", "Los Angeles Chargers", "No recent probability", "Las Vegas Raiders", "Eliminated"]
                )
                try maybeSave(discoverImg, name: "1_division_discover_\(Int(width))_\(schemeName)")

                let hubImg = renderIntrinsic(
                    MachinerySectionBlockView(
                        visualBlock: hubRaceBlock,
                        members: [],
                        columnCount: hubCols
                    )
                    .environmentObject(pinManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(authManager),
                    width: width,
                    colorScheme: scheme
                )
                try assertCleanOCR(
                    in: hubImg,
                    label: "1_division_hub_\(Int(width))_\(schemeName)",
                    requiredTokens: ["San Francisco 49ers", "61%", "Seattle Seahawks", "<1%", "Arizona Cardinals", "No recent probability", "Tennessee Titans", "Eliminated"]
                )
                try maybeSave(hubImg, name: "1_division_hub_\(Int(width))_\(schemeName)")
            }
        }

        // 2. Sports tab on iPad (834 pt Light & Dark at AX5)
        let sportsFeed = try makeMultiLeagueSportsFeed()
        let sportsVM = FeedViewModel(client: SportsFeedStub(feed: sportsFeed), telemetry: nil, autoRefreshEnabled: false)
        await sportsVM.startLoad()
        for (scheme, schemeName) in schemes {
            let sportsImg = renderFixedViewport(
                FeedView(viewModel: sportsVM)
                    .environmentObject(pinManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(authManager),
                width: 834,
                height: 2150,
                colorScheme: scheme
            )
            try assertCleanOCR(
                in: sportsImg,
                label: "2_sports_ipad_834_\(schemeName)",
                requiredTokens: ["Live Now", "NFL", "Chiefs", "Bills", "Upcoming"]
            )
            try maybeSave(sportsImg, name: "2_sports_ipad_834_\(schemeName)")
        }

        // 3. Usage-stats card & First-run checklist
        let checklistContent = makeChecklistContent()
        let partialChecklist = FirstRunChecklistState364A(
            completedRows: [.lookUp, .follow],
            selectedSetSlugs: [],
            followedCount: 2,
            dismissedFromMyStuff: false
        )
        for width in widths {
            let consentHeight: CGFloat = width >= 700 ? 1650 : (width <= 320 ? 2420 : 2020)
            let checklistHeight: CGFloat = width >= 700 ? 1850 : (width <= 320 ? 2550 : 2150)
            let checklistForbidden = ["\u{2026}", "...", "Preferen\u{2026}", "Preferen...", "Go to Disco\u{2026}", "Go to Disco...", "anony-", "analyt-", "Notifica-", "school s", "any-", "ex-", "de-"]
            for (scheme, schemeName) in schemes {
                let consentImg = renderFixedViewport(
                    TelemetryConsentPrompt { _ in }
                        .environmentObject(authManager),
                    width: width,
                    height: consentHeight,
                    colorScheme: scheme
                )
                try assertCleanOCR(
                    in: consentImg,
                    label: "3_usage_stats_\(Int(width))_\(schemeName)",
                    requiredTokens: ["Help us find", "Allow", "No thanks", "Preferences"]
                )
                try maybeSave(consentImg, name: "3_usage_stats_\(Int(width))_\(schemeName)")

                let partialImg = renderFixedViewport(
                    NavigationStack {
                        FirstRunChecklistView364A(
                            content: checklistContent,
                            state: .constant(partialChecklist)
                        )
                    }
                    .environmentObject(authManager),
                    width: width,
                    height: checklistHeight,
                    colorScheme: scheme
                )
                try assertCleanOCR(
                    in: partialImg,
                    label: "3_checklist_partial_\(Int(width))_\(schemeName)",
                    requiredTokens: ["Bain Luck", "2 of 5 done", "Skip", "Sign in to sync", "across devices", "2 followed"],
                    forbiddenSubstrings: checklistForbidden
                )
                try maybeSave(partialImg, name: "3_checklist_partial_\(Int(width))_\(schemeName)")

                let doneImg = renderFixedViewport(
                    NavigationStack {
                        FirstRunChecklistView364A(
                            content: checklistContent,
                            state: .constant(.allDone)
                        )
                    }
                    .environmentObject(authManager),
                    width: width,
                    height: checklistHeight,
                    colorScheme: scheme
                )
                try assertCleanOCR(
                    in: doneImg,
                    label: "3_checklist_done_\(Int(width))_\(schemeName)",
                    requiredTokens: ["Bain Luck", "5 of 5 done", "Go to Discover"],
                    forbiddenSubstrings: checklistForbidden
                )
                try maybeSave(doneImg, name: "3_checklist_done_\(Int(width))_\(schemeName)")
            }
        }

        // 4. App icon row & picker
        let nyeSwitcher = AppIconSwitcher423A(
            supportsAlternateIcons: { true },
            currentIconName: { "AppIconNewYearsEve" },
            setIconName: { _ in }
        )
        for width in widths {
            let prefsHeight: CGFloat = width >= 700 ? 1550 : (width <= 320 ? 2080 : 1920)
            let pickerHeight: CGFloat = width >= 700 ? 780 : 920
            for (scheme, schemeName) in schemes {
                let prefsImg = renderFixedViewport(
                    NavigationStack {
                        PreferencesView(appIconSwitcherForTest: nyeSwitcher)
                    }
                    .environmentObject(authManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(pinManager),
                    width: width,
                    height: prefsHeight,
                    colorScheme: scheme
                )
                try assertCleanOCR(
                    in: prefsImg,
                    label: "4_app_icon_row_\(Int(width))_\(schemeName)",
                    requiredTokens: ["Preferences", "Notifications", "App icon", "New Year's Eve", "Share usage analytics"]
                )
                try maybeSave(prefsImg, name: "4_app_icon_row_\(Int(width))_\(schemeName)")

                let pickerImg = renderFixedViewport(
                    NavigationStack {
                        AppIconPickerView423A(switcher: nyeSwitcher)
                    },
                    width: width,
                    height: pickerHeight,
                    colorScheme: scheme
                )
                try assertCleanOCR(
                    in: pickerImg,
                    label: "4_app_icon_picker_\(Int(width))_\(schemeName)",
                    requiredTokens: ["Original", "Winter", "New Year's Eve"]
                )
                try maybeSave(pickerImg, name: "4_app_icon_picker_\(Int(width))_\(schemeName)")
            }
        }

        // 5. Soccer withheld away cells ("No probability yet" & "No recent probability")
        let (schedEvent, schedModel) = try makeSoccerDetail(status: "scheduled")
        let (liveEvent, liveModel) = try makeSoccerDetail(status: "live")
        for width in widths {
            for (scheme, schemeName) in schemes {
                for (tag, ev, mod) in [("scheduled_no_prob_yet", schedEvent, schedModel), ("live_no_recent_prob", liveEvent, liveModel)] {
                    let colors = teamColors(for: ev, colorScheme: scheme)
                    let card = EventSportHeadlineCard12472(
                        model: mod,
                        colors: colors,
                        ekgTracker: .empty,
                        liveUpdateStatus: .hidden,
                        displayAsOf: fixedNow,
                        updateStream: LiveUpdateStream(),
                        showUpdateStream: .constant(false),
                        showProbabilityDetails: .constant(false),
                        priceStreamingEligible: false,
                        lastReceivedAt: nil,
                        confirmedAt: nil,
                        revealForecast: nil
                    )
                    let img = renderIntrinsic(card, width: width, colorScheme: scheme)
                    let expectedNotice = tag == "scheduled_no_prob_yet" ? "No probability yet" : "No recent probability"
                    try assertCleanOCR(
                        in: img,
                        label: "5_soccer_\(tag)_\(Int(width))_\(schemeName)",
                        requiredTokens: ["Chelsea", "Nottingham Forest", expectedNotice, "62"]
                    )
                    try maybeSave(img, name: "5_soccer_\(tag)_\(Int(width))_\(schemeName)")
                }
            }
        }

        // 6. Like heart (Action bar Like/Liked + DiscoverFuturesCard + DiscoverEventCard footers)
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let futuresData = try dec.decode(FeedFuturesData.self, from: Data(#"""
        {
          "id": 901,
          "name": "Who will win the NBA Championship?",
          "category": "sports",
          "llm_sport_category": "basketball",
          "source": "kalshi",
          "status": "open",
          "source_count": 2,
          "confidence_tier": "high",
          "top_outcomes": [
            {"id": 1, "name": "Boston Celtics", "probability": 0.42, "rendered_percent": 42, "rank": 1, "movement": 0.03},
            {"id": 2, "name": "Oklahoma City Thunder", "probability": 0.31, "rendered_percent": 31, "rank": 2, "movement": -0.02}
          ],
          "outcome_count": 2
        }
        """#.utf8))
        let likedAction = DiscoverCardLikeAction420D(
            itemKey: "futures-901",
            isLiked: true,
            pinType: "future",
            pinId: 901,
            shareURL: URL(string: "https://bainluck.com/futures/901"),
            shareTitle: "Who will win the NBA Championship?",
            shareMessage: "Boston Celtics lead at 42%",
            onToggle: {},
            onShare: {}
        )
        let unlikedAction = DiscoverCardLikeAction420D(
            itemKey: "futures-902",
            isLiked: false,
            pinType: "future",
            pinId: 902,
            shareURL: URL(string: "https://bainluck.com/futures/902"),
            shareTitle: "Who will win the NBA Championship?",
            shareMessage: "Boston Celtics lead at 42%",
            onToggle: {},
            onShare: {}
        )

        let eventData = try dec.decode(FeedEventData.self, from: Data("""
        {
          "id": 9138691,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "Kansas City Chiefs",
          "away_team": "Buffalo Bills",
          "home_team_data": {"team_id": 12, "name": "Kansas City Chiefs", "short_name": "Chiefs", "abbreviation": "KC", "primary_color": "#E31837"},
          "away_team_data": {"team_id": 2, "name": "Buffalo Bills", "short_name": "Bills", "abbreviation": "BUF", "primary_color": "#00338D"},
          "commence_time": "\(ISO8601DateFormatter().string(from: fixedNow.addingTimeInterval(-1800)))",
          "status": "live",
          "home_score": 21,
          "away_score": 17,
          "espn": {"period": "Q3", "clock": "4:18"},
          "current_odds": {"home_probability": 0.58, "away_probability": 0.42}
        }
        """.utf8))

        for width in widths {
            for (scheme, schemeName) in schemes {
                let bars = VStack(spacing: 12) {
                    DiscoverCardActionBar420D(
                        actions: unlikedAction,
                        topDivider: false,
                        surfaceColor: scheme == .dark ? Color(white: 0.12) : .white
                    )
                    DiscoverCardActionBar420D(
                        actions: likedAction,
                        topDivider: false,
                        surfaceColor: scheme == .dark ? Color(white: 0.12) : .white
                    )
                }
                .environmentObject(pinManager)
                .environmentObject(authManager)
                let barImg = renderIntrinsic(bars, width: width, colorScheme: scheme)
                try assertCleanOCR(
                    in: barImg,
                    label: "6_like_action_bar_\(Int(width))_\(schemeName)",
                    requiredTokens: ["Like", "Liked"]
                )
                try maybeSave(barImg, name: "6_like_action_bar_\(Int(width))_\(schemeName)")

                let futuresCard = NativeFuturesDiscoverCard(
                    data: futuresData,
                    feedContext: "Celtics lead the Eastern Conference entering December.",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
                .environment(\.discoverCardLikeAction420D, likedAction)
                .environmentObject(pinManager)
                .environmentObject(authManager)
                let futuresImg = renderIntrinsic(futuresCard, width: width, colorScheme: scheme)
                try assertCleanOCR(
                    in: futuresImg,
                    label: "6_like_futures_card_\(Int(width))_\(schemeName)",
                    requiredTokens: ["Boston Celtics", "42%", "Oklahoma City Thunder", "31%", "2 sources", "Liked"]
                )
                try maybeSave(futuresImg, name: "6_like_futures_card_\(Int(width))_\(schemeName)")

                let eventCard = NativeEventDiscoverCard(
                    event: eventData,
                    feedContext: "Week 13 AFC marquee matchup between two division leaders.",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
                .environment(\.discoverCardLikeAction420D, likedAction)
                .environmentObject(pinManager)
                .environmentObject(authManager)
                let eventImg = renderIntrinsic(eventCard, width: width, colorScheme: scheme)
                try assertCleanOCR(
                    in: eventImg,
                    label: "6_like_event_card_\(Int(width))_\(schemeName)",
                    requiredTokens: ["Buffalo Bills", "Kansas City Chiefs", "58%", "Liked"]
                )
                try maybeSave(eventImg, name: "6_like_event_card_\(Int(width))_\(schemeName)")
            }
        }
    }
    #endif
}
