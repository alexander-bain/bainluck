import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// #13604 — iPhone team page decodes and renders `futures_unavailable`, `futures_partial`,
/// and `futures_omitted_count` honestly with `"Try again"`, matching `#13578` for My Stuff.
@MainActor
final class TeamDetailFuturesHonestState13604Tests: XCTestCase {

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func decodeTeamPage(_ json: String) throws -> TeamPageResponse {
        try makeDecoder().decode(TeamPageResponse.self, from: Data(json.utf8))
    }

    private func unavailableJSON() -> String {
        """
        {
          "team": {
            "id": 12,
            "slug": "boston-celtics",
            "name": "Boston Celtics",
            "abbreviation": "BOS",
            "location": "Boston",
            "sport_key": "basketball_nba",
            "sport_name": "NBA",
            "primary_color": "#007A33"
          },
          "upcoming_events": [],
          "recent_events": [],
          "futures": [],
          "championship_path": [],
          "futures_unavailable": true
        }
        """
    }

    private func partialJSON(omittedCount: Int = 3) -> String {
        """
        {
          "team": {
            "id": 12,
            "slug": "boston-celtics",
            "name": "Boston Celtics",
            "abbreviation": "BOS",
            "location": "Boston",
            "sport_key": "basketball_nba",
            "sport_name": "NBA",
            "primary_color": "#007A33"
          },
          "upcoming_events": [],
          "recent_events": [],
          "futures": [
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
              "state": null
            }
          ],
          "championship_path": [],
          "futures_partial": true,
          "futures_omitted_count": \(omittedCount)
        }
        """
    }

    private func healthyJSON() -> String {
        """
        {
          "team": {
            "id": 12,
            "slug": "boston-celtics",
            "name": "Boston Celtics",
            "abbreviation": "BOS",
            "location": "Boston",
            "sport_key": "basketball_nba",
            "sport_name": "NBA",
            "primary_color": "#007A33"
          },
          "upcoming_events": [],
          "recent_events": [],
          "futures": [
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
              "state": null
            }
          ],
          "championship_path": []
        }
        """
    }

    func testDecodesUnavailablePartialAndHealthyFlags() throws {
        let unavailable = try decodeTeamPage(unavailableJSON())
        XCTAssertEqual(unavailable.futuresUnavailable, true)
        XCTAssertNil(unavailable.futuresPartial)
        XCTAssertTrue(unavailable.futures.isEmpty)

        let partial = try decodeTeamPage(partialJSON(omittedCount: 3))
        XCTAssertEqual(partial.futuresPartial, true)
        XCTAssertEqual(partial.futuresOmittedCount, 3)
        XCTAssertEqual(partial.futures.count, 1)

        let healthy = try decodeTeamPage(healthyJSON())
        XCTAssertNil(healthy.futuresUnavailable)
        XCTAssertNil(healthy.futuresPartial)
        XCTAssertNil(healthy.futuresOmittedCount)
        XCTAssertEqual(healthy.futures.count, 1)
    }

    func testRetryControllerRecoversOrRecordsRetryFailureWithoutLosingData() async throws {
        let healthy = try decodeTeamPage(healthyJSON())
        let controller = TeamFuturesRetryController13604()

        struct BoomError: Error {}
        let failedResult = await controller.retry {
            throw BoomError()
        }
        XCTAssertNil(failedResult)
        XCTAssertTrue(controller.retryFailed)
        XCTAssertNil(controller.pageOverride)

        let recovered = await controller.retry { healthy }
        XCTAssertEqual(recovered?.futures.count, 1)
        XCTAssertFalse(controller.retryFailed)
        XCTAssertEqual(controller.pageOverride?.futures.first?.outcomeId, 901)
    }

    #if canImport(UIKit)
    private func renderAndRecognize(
        page: TeamPageResponse,
        retryController: TeamFuturesRetryController13604? = nil,
        scheme: ColorScheme
    ) async throws -> (UIImage, [String]) {
        let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let auth = AuthManager()
        let root = NavigationStack {
            TeamDetailView(
                slug: "boston-celtics",
                loadedPageForTest: page,
                retryControllerForTest: retryController
            )
            .environmentObject(auth)
        }
        .frame(width: 390, height: 760)
        .environment(\.colorScheme, scheme)

        let host = hostForMeasurement(root, at: .large)
        host.overrideUserInterfaceStyle = uiStyle
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 760))
        window.frame = CGRect(x: 0, y: 0, width: 390, height: 760)
        window.overrideUserInterfaceStyle = uiStyle
        host.view.frame = window.bounds
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        await Task.yield()

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
            if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }

        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(img.cgImage), options: [:]).perform([req])
        let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        return (img, lines)
    }

    func testUnavailableAndPartialStatesRenderHonestlyAndRetryRecovers() async throws {
        let unavailable = try decodeTeamPage(unavailableJSON())
        let partial = try decodeTeamPage(partialJSON(omittedCount: 3))
        let healthy = try decodeTeamPage(healthyJSON())
        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_13604_RENDER_DIR"]

        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let tag = scheme == .dark ? "dark" : "light"

            let (unavailImg, unavailLines) = try await renderAndRecognize(page: unavailable, scheme: scheme)
            let unavailJoined = unavailLines.joined(separator: " ")
            XCTAssertTrue(unavailJoined.contains("Couldn't load season futures"), "Expected honest unavailable headline (\(scheme)): \(unavailJoined)")
            XCTAssertTrue(unavailJoined.contains("Try again"), "Expected Try again button (\(scheme)): \(unavailJoined)")
            XCTAssertFalse(unavailLines.contains(where: { $0.contains("…") || $0.contains("...") }), "Zero ellipsis (\(scheme)): \(unavailLines)")

            let (partialImg, partialLines) = try await renderAndRecognize(page: partial, scheme: scheme)
            let partialJoined = partialLines.joined(separator: " ")
            XCTAssertTrue(partialJoined.contains("Jayson Tatum"), "Partial must still show arrived future row (\(scheme)): \(partialJoined)")
            XCTAssertTrue(partialJoined.contains("3 more futures"), "Partial must show omitted count note (\(scheme)): \(partialJoined)")
            XCTAssertTrue(partialJoined.contains("Try again"), "Partial must surface Try again (\(scheme)): \(partialJoined)")
            XCTAssertFalse(partialLines.contains(where: { $0.contains("…") || $0.contains("...") }), "Zero ellipsis (\(scheme)): \(partialLines)")

            if let outDir, !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                try unavailImg.pngData()?.write(to: dirURL.appendingPathComponent("13604-unavailable-\(tag)-390.png"))
                try partialImg.pngData()?.write(to: dirURL.appendingPathComponent("13604-partial-\(tag)-390.png"))
            }
        }

        // Verify live Retry transition swaps from unavailable -> loaded future row on view controller
        let retryCtrl = TeamFuturesRetryController13604()
        let (_, beforeRetry) = try await renderAndRecognize(page: unavailable, retryController: retryCtrl, scheme: .light)
        XCTAssertTrue(beforeRetry.joined(separator: " ").contains("Couldn't load season futures"))
        _ = await retryCtrl.retry { healthy }
        let (afterImg, afterRetry) = try await renderAndRecognize(page: unavailable, retryController: retryCtrl, scheme: .light)
        let afterJoined = afterRetry.joined(separator: " ")
        XCTAssertTrue(afterJoined.contains("Jayson Tatum"), "Recovered view must render loaded futures: \(afterJoined)")
        XCTAssertFalse(afterJoined.contains("Couldn't load season futures"), "Recovered view clears unavailable state: \(afterJoined)")
        if let outDir, !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try afterImg.pngData()?.write(to: dirURL.appendingPathComponent("13604-recovered-light-390.png"))
        }
    }

    func testUnavailableFlagWithNonEmptyFuturesShowsOneLineNoteAndTryAgainUnderRows() async throws {
        let json = """
        {
          "team": {
            "id": 12,
            "slug": "boston-celtics",
            "name": "Boston Celtics",
            "abbreviation": "BOS",
            "location": "Boston",
            "sport_key": "basketball_nba",
            "sport_name": "NBA",
            "primary_color": "#007A33"
          },
          "upcoming_events": [],
          "recent_events": [],
          "futures": [
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
              "state": null
            }
          ],
          "championship_path": [],
          "futures_unavailable": true
        }
        """
        let page = try decodeTeamPage(json)
        XCTAssertEqual(page.futuresUnavailable, true)
        XCTAssertNil(page.futuresPartial)
        XCTAssertEqual(page.futures.count, 1)

        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let (_, lines) = try await renderAndRecognize(page: page, scheme: scheme)
            let joined = lines.joined(separator: " ")
            XCTAssertTrue(joined.contains("Jayson Tatum"), "Must keep arrived futures row (\(scheme)): \(joined)")
            XCTAssertTrue(joined.contains("Some season futures couldn't be loaded right now."), "Must show note under rows when unavailable=true with rows (\(scheme)): \(joined)")
            XCTAssertTrue(joined.contains("Try again"), "Must show Try again under rows (\(scheme)): \(joined)")
            XCTAssertFalse(lines.contains(where: { $0.contains("…") || $0.contains("...") }), "Zero ellipsis (\(scheme)): \(lines)")
        }
    }
    #endif
}
