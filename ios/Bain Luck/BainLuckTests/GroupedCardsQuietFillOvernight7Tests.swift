import CryptoKit
import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Overnight Item 7 (#12642 / #12675 follow-up): quiet proportional fill behind each
/// percentage number box (`94%` almost full, `36%` about a third full) across both
/// winning grouped-card looks (`paired_bars_top5_expandable` and `podium_and_tiers`).
@MainActor
final class GroupedCardsQuietFillOvernight7Tests: XCTestCase {

    private func decodeSet(_ json: String) throws -> PairedMetricSet {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(PairedMetricSet.self, from: Data(json.utf8))
    }

    func testQuietFillFractionMatches94PercentAnd36PercentAndSkipsSettledOrMissing() {
        let ninetyFour = FormattedPairedStageDisplay(kind: .percent, percent: 94, label: "94%")
        let thirtySix = FormattedPairedStageDisplay(kind: .percent, percent: 36, label: "36%")
        let one = FormattedPairedStageDisplay(kind: .percent, percent: 1, label: "1%")
        let tick = FormattedPairedStageDisplay(kind: .tick, percent: 100, symbol: "✓", label: "✓ Nominated")
        let cross = FormattedPairedStageDisplay(kind: .cross, percent: 0, symbol: "✗", label: "✗ Not nominated")
        let missing = FormattedPairedStageDisplay(kind: .missing, percent: nil, label: "Not listed to win")

        XCTAssertEqual(PairedMetricPresentation.quietFillFraction(for: ninetyFour) ?? -1, 0.94, accuracy: 0.0001)
        XCTAssertEqual(PairedMetricPresentation.quietFillFraction(for: thirtySix) ?? -1, 0.36, accuracy: 0.0001)
        XCTAssertEqual(PairedMetricPresentation.quietFillFraction(for: one) ?? -1, 0.01, accuracy: 0.0001)
        XCTAssertNil(PairedMetricPresentation.quietFillFraction(for: tick))
        XCTAssertNil(PairedMetricPresentation.quietFillFraction(for: cross))
        XCTAssertNil(PairedMetricPresentation.quietFillFraction(for: missing))
    }

    func testSubtitleOrderingDeduplicationSuppressesDuplicateFooterLine() {
        XCTAssertTrue(
            PairedMetricPresentation.subtitleStatesOrdering(
                "99th Academy Awards · Top 10 most likely to be nominated (ordered by win %, ties broken by nominated %)"
            )
        )
        XCTAssertTrue(
            PairedMetricPresentation.subtitleStatesOrdering(
                "All 9 NHL clubs at 5%+ to win the Cup (ties broken by playoff %)"
            )
        )
        XCTAssertFalse(
            PairedMetricPresentation.subtitleStatesOrdering(
                "99th Academy Awards · Best Picture contenders"
            )
        )
    }

    func testBothGroupedLooksRenderQuietFillBoxesCleanlyAt390pt() throws {
        let nhlWith36JSON = #"""
        {
          "set_id": "nhl-2026-27-playoffs-and-cup",
          "category": "hockey",
          "kicker": "NHL 2026–27 · PLAYOFF BERTH TO STANLEY CUP",
          "title": "Carolina leads the Stanley Cup race at 94% to make the playoffs",
          "subtitle": "NHL clubs ordered by Cup %, ties broken by playoff %",
          "stage_1_label": "Make Playoffs",
          "stage_2_label": "Win Cup",
          "stage_1_settled_yes_label": "Clinched",
          "stage_1_settled_no_label": "Eliminated",
          "entries": [
            {
              "subject_key": "team:nhl:carolina-hurricanes",
              "subject": "Carolina Hurricanes",
              "detail": "Metropolitan · Eastern Conference",
              "stage_1_market_id": 63068142,
              "stage_1_probability": 0.94,
              "stage_1_settled_state": null,
              "stage_2_market_id": 52755659,
              "stage_2_probability": 0.36,
              "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/car.png", "adult": false, "kid_safe_vetted": true }
            },
            {
              "subject_key": "team:nhl:colorado-avalanche",
              "subject": "Colorado Avalanche",
              "detail": "Central · Western Conference",
              "stage_1_market_id": 63068142,
              "stage_1_probability": 0.934,
              "stage_1_settled_state": null,
              "stage_2_market_id": 52755659,
              "stage_2_probability": 0.18,
              "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/col.png", "adult": false, "kid_safe_vetted": true }
            },
            {
              "subject_key": "team:nhl:minnesota-wild",
              "subject": "Minnesota Wild",
              "detail": "Central · Western Conference",
              "stage_1_market_id": 63068142,
              "stage_1_probability": 0.78,
              "stage_1_settled_state": null,
              "stage_2_market_id": 52755659,
              "stage_2_probability": 0.12,
              "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/min.png", "adult": false, "kid_safe_vetted": true }
            },
            {
              "subject_key": "team:nhl:edmonton-oilers",
              "subject": "Edmonton Oilers",
              "detail": "Pacific · Western Conference",
              "stage_1_market_id": 63068142,
              "stage_1_probability": 0.94,
              "stage_1_settled_state": null,
              "stage_2_market_id": 52755659,
              "stage_2_probability": 0.09,
              "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/edm.png", "adult": false, "kid_safe_vetted": true }
            },
            {
              "subject_key": "team:nhl:tampa-bay-lightning",
              "subject": "Tampa Bay Lightning",
              "detail": "Atlantic · Eastern Conference",
              "stage_1_market_id": 63068142,
              "stage_1_probability": 0.36,
              "stage_1_settled_state": null,
              "stage_2_market_id": 52755659,
              "stage_2_probability": 0.04,
              "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/tb.png", "adult": false, "kid_safe_vetted": true }
            }
          ]
        }
        """#

        let oscarsJSON = #"""
        {
          "set_id": "oscars-2027-best-picture",
          "category": "entertainment",
          "kicker": "OSCARS 2027 · BEST PICTURE",
          "title": "The Odyssey leads Best Picture, with 6 films at 75%+ to be nominated",
          "subtitle": "99th Academy Awards · Top 10 most likely to be nominated (ordered by win %, ties broken by nominated %)",
          "stage_1_label": "Nominated",
          "stage_2_label": "Wins",
          "stage_1_settled_yes_label": "Nominated",
          "stage_1_settled_no_label": "Not nominated",
          "entries": [
            {
              "subject_key": "film:the-odyssey-2026",
              "subject": "The Odyssey",
              "detail": "Christopher Nolan · Universal Pictures",
              "stage_1_market_id": 5165726,
              "stage_1_probability": 0.978,
              "stage_1_settled_state": null,
              "stage_2_market_id": 6173044,
              "stage_2_probability": 0.565,
              "art": { "kind": "tmdb_poster", "tmdb_id": 1368337, "poster_path": "/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg", "url": "https://image.tmdb.org/t/p/w342/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg", "genre_ids": [12, 28, 14], "adult": false, "kid_safe_vetted": true }
            },
            {
              "subject_key": "film:the-black-ball-2026",
              "subject": "The Black Ball",
              "detail": "Javier Ambrossi & Javier Calvo · Movistar Plus",
              "stage_1_market_id": 5165726,
              "stage_1_probability": 0.94,
              "stage_1_settled_state": null,
              "stage_2_market_id": 6173044,
              "stage_2_probability": 0.36,
              "art": { "kind": "tmdb_poster", "tmdb_id": 1422041, "poster_path": "/7HwFQTMghL6HOvzEnXYUvyuZXeh.jpg", "url": "https://image.tmdb.org/t/p/w342/7HwFQTMghL6HOvzEnXYUvyuZXeh.jpg", "genre_ids": [18, 10752], "adult": false, "kid_safe_vetted": true }
            },
            {
              "subject_key": "film:you-can-see-everything-2026",
              "subject": "You Can See Everything",
              "detail": "Nathan Fielder & Lance Oppenheim · Blow Out Productions",
              "stage_1_market_id": 5165726,
              "stage_1_probability": 0.8525,
              "stage_1_settled_state": null,
              "stage_2_market_id": 6173044,
              "stage_2_probability": 0.165,
              "art": { "kind": "tmdb_poster", "tmdb_id": 1765072, "poster_path": "/Ap8QwmKfSjYbWC4XIP8w9pdn72O.jpg", "url": "https://image.tmdb.org/t/p/w342/Ap8QwmKfSjYbWC4XIP8w9pdn72O.jpg", "genre_ids": [99], "adult": false, "kid_safe_vetted": true }
            },
            {
              "subject_key": "film:dune-part-three-2026",
              "subject": "Dune: Part Three",
              "detail": "Denis Villeneuve · Legendary Pictures",
              "stage_1_market_id": 5165726,
              "stage_1_probability": 0.94,
              "stage_1_settled_state": null,
              "stage_2_market_id": 6173044,
              "stage_2_probability": 0.075,
              "art": { "kind": "tmdb_poster", "tmdb_id": 1170608, "poster_path": "/glt0v4I89rMWstDNCaFXc5SNyO1.jpg", "url": "https://image.tmdb.org/t/p/w342/glt0v4I89rMWstDNCaFXc5SNyO1.jpg", "genre_ids": [878, 12], "adult": false, "kid_safe_vetted": true }
            },
            {
              "subject_key": "film:artificial-2026",
              "subject": "Artificial",
              "detail": "Luca Guadagnino · Heyday Films",
              "stage_1_market_id": 5165726,
              "stage_1_probability": 0.36,
              "stage_1_settled_state": null,
              "stage_2_market_id": 6173044,
              "stage_2_probability": 0.02,
              "art": { "kind": "tmdb_poster", "tmdb_id": 1492198, "poster_path": "/2bz0HPE8OFOqnyvl8sCdVDIg1KX.jpg", "url": "https://image.tmdb.org/t/p/w342/2bz0HPE8OFOqnyvl8sCdVDIg1KX.jpg", "genre_ids": [35, 18, 36], "adult": false, "kid_safe_vetted": true }
            },
            {
              "subject_key": "film:i-play-rocky-2026",
              "subject": "I Play Rocky",
              "detail": "Peter Farrelly · Eden Rock Media",
              "stage_1_market_id": 5165726,
              "stage_1_probability": 0.49,
              "stage_1_settled_state": null,
              "stage_2_market_id": 6173044,
              "stage_2_probability": null,
              "missing_stage_2_reason": "Not listed to win",
              "art": { "kind": "tmdb_poster", "tmdb_id": 1286656, "poster_path": "/xE5tY3lppZUyG7WKKThsuYHuAHr.jpg", "url": "https://image.tmdb.org/t/p/w342/xE5tY3lppZUyG7WKKThsuYHuAHr.jpg", "genre_ids": [18, 36], "adult": false, "kid_safe_vetted": true }
            }
          ]
        }
        """#

        let nhl = try decodeSet(nhlWith36JSON)
        let oscars = try decodeSet(oscarsJSON)

        for dt in [DynamicTypeSize.large, .accessibility3, .accessibility5] {
            for view in [
                AnyView(DiscoverPairedMetricCardView(set: oscars, form: .pairedBarsTop5Expandable).frame(width: 358)),
                AnyView(DiscoverPairedMetricCardView(set: oscars, form: .podiumAndTiers).frame(width: 358)),
                AnyView(DiscoverPairedMetricCardView(set: nhl, form: .podiumAndTiers).frame(width: 358)),
            ] {
                let host = hostForMeasurement(view.environment(\.colorScheme, .light), at: dt)
                let measured = host.sizeThatFits(in: CGSize(width: 358, height: 4000))
                XCTAssertLessThanOrEqual(measured.width, 358.5)
                XCTAssertGreaterThan(measured.height, 240)
            }
        }

        guard let outDir = ProcessInfo.processInfo.environment["BAINLUCK_OVERNIGHT7_RENDER_DIR"],
              !outDir.isEmpty else { return }
        let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

        var preloaded: [String: UIImage] = [:]
        let cacheDir = URL(fileURLWithPath: "/tmp/builderc-12642-art-cache", isDirectory: true)
        for set in [oscars, nhl] {
            for entry in set.entries {
                guard let urlStr = entry.art?.url else { continue }
                let digest = SHA256.hash(data: Data(urlStr.utf8))
                    .map { String(format: "%02x", $0) }
                    .joined()
                let fileKey = Array(digest)[0..<16].map(String.init).joined()
                let ext = urlStr.hasSuffix(".png") ? ".png" : ".jpg"
                let fileURL = cacheDir.appendingPathComponent(fileKey + ext)
                if let data = try? Data(contentsOf: fileURL), let img = UIImage(data: data) {
                    preloaded[urlStr] = img
                }
            }
        }

        func writeCardPNG<V: View>(_ content: V, filename: String) throws {
            let wrapped = content
                .padding(16)
                .frame(width: 390, alignment: .topLeading)
                .background(DS.surface)
                .environment(\.colorScheme, .light)
            let host = hostForMeasurement(wrapped, at: .large)
            host.overrideUserInterfaceStyle = .light
            let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 4000))
            let size = CGSize(width: 390, height: ceil(fitting.height))
            host.view.frame = CGRect(origin: .zero, size: size)
            let window = UIWindow(frame: host.view.frame)
            window.overrideUserInterfaceStyle = .light
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            for _ in 0..<8 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.02))
            }
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
            try XCTUnwrap(img.pngData()).write(to: dirURL.appendingPathComponent(filename))
        }

        try writeCardPNG(
            DiscoverPairedMetricCardView(
                set: oscars,
                form: .pairedBarsTop5Expandable,
                initialExpanded: true,
                preloadedImages: preloaded
            ),
            filename: "overnight7-look1-oscars-quiet-fill-390.png"
        )
        try writeCardPNG(
            DiscoverPairedMetricCardView(
                set: oscars,
                form: .podiumAndTiers,
                preloadedImages: preloaded
            ),
            filename: "overnight7-look2-oscars-podium-quiet-fill-390.png"
        )
        try writeCardPNG(
            DiscoverPairedMetricCardView(
                set: nhl,
                form: .podiumAndTiers,
                preloadedImages: preloaded
            ),
            filename: "overnight7-look2-nhl-podium-quiet-fill-390.png"
        )
    }
}
