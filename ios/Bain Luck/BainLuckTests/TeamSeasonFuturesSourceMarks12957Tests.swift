import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Item 7 (#12957 / #12581) — Team Season Futures & Your Teams' Futures `source_mark`
/// served on `GET /api/teams/{slug}` (`futures[].source_mark`) and `GET /api/me/teams/futures`.
/// - Active rows pass `row.probability` (`item.probability`) and `subject` to `SourceMarkButton`.
/// - Settled (`Won` / `Out`) rows pass `number: nil` so the sheet prints the settled line
///   with no residual percentage.
/// - `MyStuffView.mergedFutureRow` draws `item.sourceMark` only on single-row (`!isMultiSource`)
///   items, never attaching a single row's mark to a client-computed multi-source average (137: A).
@MainActor
final class TeamSeasonFuturesSourceMarks12957Tests: XCTestCase {

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func sampleTeam() throws -> TeamPageTeam {
        try makeDecoder().decode(
            TeamPageTeam.self,
            from: Data("""
            {
              "id": 12,
              "slug": "boston-celtics",
              "name": "Boston Celtics",
              "abbreviation": "BOS",
              "location": "Boston",
              "sport_key": "basketball_nba",
              "sport_name": "NBA",
              "primary_color": "#007A33"
            }
            """.utf8)
        )
    }

    func testActiveSeasonFutureRowPreservesProbabilityAndSourceMark() throws {
        let item = try makeDecoder().decode(
            TeamFutureItem.self,
            from: Data("""
            {
              "outcome_id": 901,
              "outcome_name": "Jayson Tatum",
              "market_id": 60901,
              "market_name": "NBA: 2026-27 Regular Season MVP",
              "market_tier": 2,
              "category": "awards",
              "source": "polymarket",
              "probability": 0.184,
              "probability_change_24h": 0.012,
              "rank": 3,
              "total_outcomes": 30,
              "resolution_date": null,
              "is_winner": null,
              "matched_team": null,
              "canonical_market_key": null,
              "state": null,
              "source_mark": {
                "state": "single",
                "sources": [
                  {
                    "key": "polymarket",
                    "name": "Polymarket",
                    "probability": 0.184,
                    "observed_at": null,
                    "reason": "observation_unknown"
                  }
                ]
              }
            }
            """.utf8)
        )

        let row = try XCTUnwrap(TeamFutureRowPresentation.fastCutRow12823(item, team: try sampleTeam()))
        XCTAssertEqual(row.title, "Jayson Tatum")
        XCTAssertEqual(try XCTUnwrap(row.probability), 0.184, accuracy: 0.0001)
        XCTAssertEqual(row.sourceMark?.state, SourceMark.State.single)

        let btn = try XCTUnwrap(
            SourceMarkButton(row.sourceMark, number: row.probability, subject: row.title, subtitle: row.caption, numberSize: 16, compactRow: true)
        )
        XCTAssertEqual(try XCTUnwrap(btn.number), 0.184, accuracy: 0.0001)
        XCTAssertEqual(btn.subject, "Jayson Tatum")
        XCTAssertEqual(btn.subtitle, "Regular Season MVP")
        XCTAssertEqual(SourceMarkSheet.subtitleLine(btn.subtitle), "Regular Season MVP")
        XCTAssertEqual(SourceMarkSheet.subtitleLine("   "), nil)
        XCTAssertEqual(SourceMarkSheet.headline(btn.number), "18%")
    }

    func testSettledAndNoneSeasonFutureRowsFollowVerdictAndNoClientInference() throws {
        let settledItem = try makeDecoder().decode(
            TeamFutureItem.self,
            from: Data("""
            {
              "outcome_id": 902,
              "outcome_name": "Boston Celtics",
              "market_id": 60902,
              "market_name": "NBA Eastern Conference Playoffs",
              "market_tier": 3,
              "category": "playoffs",
              "source": "kalshi",
              "probability": 1.0,
              "probability_change_24h": null,
              "rank": 1,
              "total_outcomes": 15,
              "resolution_date": null,
              "is_winner": true,
              "matched_team": null,
              "canonical_market_key": null,
              "state": "won",
              "source_mark": {
                "state": "settled",
                "sources": [],
                "settled": {"source": "api_settlement", "result": "Won", "at": null}
              }
            }
            """.utf8)
        )

        let row = try XCTUnwrap(TeamFutureRowPresentation.fastCutRow12823(settledItem, team: try sampleTeam()))
        XCTAssertTrue(row.settledWon)
        let mark = try XCTUnwrap(row.sourceMark)
        let btn = try XCTUnwrap(SourceMarkButton(mark, number: nil, subject: row.title, numberSize: 14, compactRow: true))
        XCTAssertNil(btn.number)
        XCTAssertEqual(
            SourceMarkSheet.settledLine(mark),
            .init(name: "Official result", price: "Won", age: nil)
        )

        let noneItem = try makeDecoder().decode(
            TeamFutureItem.self,
            from: Data("""
            {
              "outcome_id": 903,
              "outcome_name": "Boston Celtics",
              "market_id": 60903,
              "market_name": "NBA In-Season Cup Winner",
              "market_tier": 3,
              "category": "tournament",
              "source": "polymarket",
              "probability": 0.12,
              "probability_change_24h": null,
              "rank": 4,
              "total_outcomes": 30,
              "resolution_date": null,
              "is_winner": null,
              "matched_team": null,
              "canonical_market_key": null,
              "state": null,
              "source_mark": {"state": "none", "sources": []}
            }
            """.utf8)
        )
        let noneRow = try XCTUnwrap(TeamFutureRowPresentation.fastCutRow12823(noneItem, team: try sampleTeam()))
        XCTAssertNil(SourceMarkButton(noneRow.sourceMark, number: noneRow.probability, subject: noneRow.title, numberSize: 16, compactRow: true))
    }

    func testTeamDetailAndMyStuffWireSourceMarkWithoutMisattributingClientAverages() throws {
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")

        let teamDetail = try String(contentsOf: appRoot.appendingPathComponent("Views/TeamDetailView.swift"), encoding: .utf8)
        XCTAssertTrue(teamDetail.contains("SourceMarkButton(row.sourceMark, number: row.probability, subject: row.title, subtitle: row.caption"))
        XCTAssertTrue(teamDetail.contains("SourceMarkButton(row.sourceMark, number: nil, subject: row.title, subtitle: row.caption"))

        let myStuff = try String(contentsOf: appRoot.appendingPathComponent("Views/MyStuffView.swift"), encoding: .utf8)
        let start = try XCTUnwrap(myStuff.range(of: "private func mergedFutureRow("))
        let end = try XCTUnwrap(myStuff.range(of: "private func cleanMarketName(", range: start.upperBound..<myStuff.endIndex))
        let fn = String(myStuff[start.lowerBound..<end.lowerBound])
        XCTAssertTrue(fn.contains("SourceMarkButton(item.sourceMark, number: prob, subject: item.outcomeName, subtitle: cleanMarketName(item.marketName)"))
        // `isMultiSource` branch uses `merged.avgProbability` and must NOT attach `item.sourceMark`.
        let multiBranchEnd = try XCTUnwrap(fn.range(of: "} else if let prob = displayProb {"))
        let multiBranch = String(fn[..<multiBranchEnd.lowerBound])
        XCTAssertFalse(multiBranch.contains("SourceMarkButton("))
    }

    // MARK: - Live 390 pt Render Export

    private func captureWindowSnapshot<V: View>(
        _ content: V,
        scheme: ColorScheme = .light,
        width: CGFloat = 390,
        fixedHeight: CGFloat
    ) async throws -> UIImage {
        let host = hostForMeasurement(content.environment(\.colorScheme, scheme), at: .large)
        let uiStyle: UIUserInterfaceStyle = scheme == .light ? .light : .dark
        host.overrideUserInterfaceStyle = uiStyle
        host.traitOverrides.preferredContentSizeCategory = .large

        let bounds = CGRect(x: 0, y: 0, width: width, height: fixedHeight)
        let scene = try XCTUnwrap(
            UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        )
        let existingWindows = scene.windows
        existingWindows.forEach { $0.isHidden = true }
        let window = UIWindow(windowScene: scene)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.traitOverrides.preferredContentSizeCategory = .large
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            existingWindows.forEach { $0.isHidden = false }
        }

        host.view.frame = bounds
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        try await Task.sleep(nanoseconds: 700_000_000)
        for _ in 0..<6 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
            if !window.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                window.layer.render(in: ctx.cgContext)
            }
        }
    }

    func testRenderLiveTeamSeasonFuturesSourceMarks390() async throws {
        let env = ProcessInfo.processInfo.environment
        guard let outDir = env["RENDER_12957_DIR"], !outDir.isEmpty,
              let jsonPath = env["RENDER_12957_JSON"], !jsonPath.isEmpty else {
            return
        }
        try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

        let rawData = try Data(contentsOf: URL(fileURLWithPath: jsonPath))
        let page = try makeDecoder().decode(TeamPageResponse.self, from: rawData)

        // Build a trim page copy with empty schedule so `Season Futures` sits immediately
        // visible inside the 390 pt viewport under `Championship Path`!
        let seasonOnlyPage = TeamPageResponse(
            team: page.team,
            upcomingEvents: [],
            recentEvents: [],
            futures: Array(page.futures.prefix(8)),
            championshipPath: page.championshipPath
        )

        let markedFuture = try XCTUnwrap(
            page.futures.first(where: { $0.sourceMark?.draws == true && $0.isWinner != true && $0.gridVerdict == nil })
                ?? page.futures.first(where: { $0.sourceMark?.draws == true })
        )
        let mark = try XCTUnwrap(markedFuture.sourceMark)

        var preloadedImages: [URL: Image] = [:]
        var candidateURLs: [URL] = []
        if let logoStr = page.team.logoLarge ?? page.team.logoSmall, let u = URL(string: logoStr) {
            candidateURLs.append(u)
        }
        for member in page.team.rosterMembers.prefix(10) {
            if let hs = member.headshot, let u = URL(string: hs) {
                candidateURLs.append(u)
            }
        }
        for url in candidateURLs {
            if let (imgData, _) = try? await URLSession.shared.data(from: url),
               let uiImg = UIImage(data: imgData) {
                preloadedImages[url] = Image(uiImage: uiImg)
            }
        }

        let suiteName = "Render12957.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults)

        let pageView = NavigationStack {
            TeamDetailView(
                slug: seasonOnlyPage.team.slug,
                loadedPageForTest: seasonOnlyPage,
                preloadedAvatarImagesForTest: preloadedImages
            )
        }
        .environmentObject(pinManager)

        let pageImg = try await captureWindowSnapshot(pageView, scheme: .light, width: 390, fixedHeight: 780)
        try XCTUnwrap(pageImg.pngData()).write(
            to: URL(fileURLWithPath: "\(outDir)/12957-team-season-futures-390.png")
        )

        let markedRow = TeamFutureRowPresentation.fastCutRow12823(markedFuture, team: page.team)
        let sheetView = SourceMarkSheet(
            mark: mark,
            number: (markedFuture.isWinner == true || markedFuture.gridVerdict != nil) ? nil : markedFuture.probability,
            subject: markedRow?.title ?? markedFuture.outcomeName,
            subtitle: markedRow?.caption
        )
        let sheetImg = try await captureWindowSnapshot(sheetView, scheme: .light, width: 390, fixedHeight: 420)
        try XCTUnwrap(sheetImg.pngData()).write(
            to: URL(fileURLWithPath: "\(outDir)/12957-team-season-futures-sheet-caption-390.png")
        )
    }
}
