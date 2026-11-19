import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13013 (`246: A`, Item 6) — Team names render at the exact same font size on every
/// game card (`Buccaneers` and `Timberwolves` match neighbouring `Bills` / `Rams` cards
/// inside `FeedView`'s `318 pt` inset-grouped row on a `390 pt` iPhone, with zero truncation).
@MainActor
final class EvenCardTeamNames13013Tests: XCTestCase {

    private func decodeEvent(_ json: String) throws -> FeedEventData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func sampleCards() throws -> [FeedEventData] {
        let futureISO = "2026-11-22T18:00:00Z"
        let liveISO = "2026-11-19T01:00:00Z"
        let recentISO = "2026-11-19T00:00:00Z"

        let ramsChiefs = try decodeEvent("""
        {
          "id": 91301,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "scheduled",
          "away_team": "Kansas City Chiefs",
          "home_team": "Los Angeles Rams",
          "commence_time": "\(futureISO)",
          "away_team_data": { "abbreviation": "KC", "primary_color": "#E31837" },
          "home_team_data": { "abbreviation": "LAR", "primary_color": "#003594" },
          "current_odds": {
            "away_probability": 0.58,
            "home_probability": 0.42,
            "away_rendered_percent": 58,
            "home_rendered_percent": 42,
            "projected_away_score": 26.8,
            "projected_home_score": 23.4
          }
        }
        """)

        let bucsBills = try decodeEvent("""
        {
          "id": 91302,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "scheduled",
          "away_team": "Tampa Bay Buccaneers",
          "home_team": "Buffalo Bills",
          "commence_time": "\(futureISO)",
          "away_team_data": { "abbreviation": "TB", "primary_color": "#D50A0A" },
          "home_team_data": { "abbreviation": "BUF", "primary_color": "#00338D" },
          "current_odds": {
            "away_probability": 0.39,
            "home_probability": 0.61,
            "away_rendered_percent": 39,
            "home_rendered_percent": 61,
            "projected_away_score": 21.2,
            "projected_home_score": 26.7
          }
        }
        """)

        let wolvesWizardsLive = try decodeEvent("""
        {
          "id": 91303,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "status": "live",
          "away_team": "Minnesota Timberwolves",
          "home_team": "Washington Wizards",
          "away_score": 84,
          "home_score": 81,
          "commence_time": "\(liveISO)",
          "espn": { "period": "Q3", "game_clock": "2:14" },
          "away_team_data": { "abbreviation": "MIN", "primary_color": "#0C2340" },
          "home_team_data": { "abbreviation": "WAS", "primary_color": "#002B5C" },
          "current_odds": {
            "away_probability": 0.642,
            "home_probability": 0.358,
            "live_projected_away_score": 114.2,
            "live_projected_home_score": 109.1,
            "live_projected_source": "sportsbook_live_spread_total"
          },
          "prematch_odds": {
            "away_probability": 0.68,
            "home_probability": 0.32,
            "away_rendered_percent": 68,
            "home_rendered_percent": 32
          }
        }
        """)

        let bucsCommandersFinal = try decodeEvent("""
        {
          "id": 91304,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "completed",
          "away_team": "Washington Commanders",
          "home_team": "Tampa Bay Buccaneers",
          "away_score": 20,
          "home_score": 27,
          "commence_time": "\(recentISO)",
          "away_team_data": { "abbreviation": "WAS", "primary_color": "#5A1414" },
          "home_team_data": { "abbreviation": "TB", "primary_color": "#D50A0A" },
          "prematch_odds": {
            "away_probability": 0.46,
            "home_probability": 0.54,
            "away_rendered_percent": 46,
            "home_rendered_percent": 54
          }
        }
        """)

        return [ramsChiefs, bucsBills, wolvesWizardsLive, bucsCommandersFinal]
    }

    func testAllGameCardsShareExactUniformTeamNameFontSizeAndNeverTruncateBuccaneersOrTimberwolves() throws {
        let cards = try sampleCards()

        for typeSize in [DynamicTypeSize.large, DynamicTypeSize.xxxLarge] {
            let sportsCards = cards.map { EventCardView(event: $0, reason: nil) }
            let discoverCards = cards.map {
                DiscoverCompactSingleGameCard190CView(
                    event: $0,
                    prematch: PrematchReading.resolve(prematch: $0.prematchOdds, opening: $0.openingOdds),
                    awayColor: .red,
                    homeColor: .blue,
                    projectionAndSuspendedLines: { EmptyView() },
                    footerRow: { EmptyView() }
                )
            }

            // 1. Direct uniform font-size equality across every card at default scale:
            let baseSizes = Set(sportsCards.map(\.renderedCompactTeamNameFontSize13013) + discoverCards.map(\.renderedCompactTeamNameFontSize13013))
            XCTAssertEqual(baseSizes.count, 1, "Every Sports and Discover card must share one team-name font size")

            // 2. Render in an authentic 390 pt inset-grouped Sports stack (318 pt inner card row width)
            //    and verify via Vision OCR that Chiefs, Rams, Buccaneers, Bills, Timberwolves, Wizards,
            //    and Commanders all render whole with matching cap-height bounding boxes.
            let img = renderSportsStack(cards: cards, scheme: .light, typeSize: typeSize, height: typeSize == .xxxLarge ? 920 : 760)
            let observations = try ocrObservations(img)
            let recognizedText = observations.map(\.text).joined(separator: " ")

            for expected in ["Chiefs", "Rams", "Buccaneers", "Bills", "Timberwolves", "Wizards", "Commanders"] {
                XCTAssertTrue(
                    recognizedText.contains(expected),
                    "Expected full '\(expected)' without truncation at \(typeSize); OCR read: \(recognizedText)"
                )
            }
            XCTAssertFalse(recognizedText.contains("…"), "No ellipsis allowed at \(typeSize): \(recognizedText)")

            let heightChiefs = try XCTUnwrap(wordHeightPt(of: "Chiefs", in: observations))
            let heightBucs = try XCTUnwrap(wordHeightPt(of: "Buccaneers", in: observations))
            let heightWolves = try XCTUnwrap(wordHeightPt(of: "Timberwolves", in: observations, excludingLineContaining: "Pregame"))

            XCTAssertLessThanOrEqual(
                abs(heightBucs - heightChiefs),
                1.5,
                "Buccaneers (\(heightBucs) pt) must render at the same height as Chiefs (\(heightChiefs) pt) at \(typeSize)"
            )
            XCTAssertLessThanOrEqual(
                abs(heightWolves - heightChiefs),
                1.5,
                "Timberwolves (\(heightWolves) pt) must render at the same height as Chiefs (\(heightChiefs) pt) at \(typeSize)"
            )
        }
    }

    func testRenders390PtLightAndDarkLooksWhenRequested() throws {
        guard let outDir = ProcessInfo.processInfo.environment["RENDER_13013_EVEN_NAMES_DIR"],
              !outDir.isEmpty else { return }
        let dir = URL(fileURLWithPath: outDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        let cards = try sampleCards()
        for (fileName, typeSize, height) in [
            ("13013-even-card-names-default-390.png", DynamicTypeSize.large, CGFloat(760)),
            ("13013-even-card-names-largest-text-390.png", DynamicTypeSize.xxxLarge, CGFloat(920)),
        ] {
            let light = renderSportsStack(cards: cards, scheme: .light, typeSize: typeSize, height: height)
            let dark = renderSportsStack(cards: cards, scheme: .dark, typeSize: typeSize, height: height)
            let combined = sideBySide(light, dark)
            try XCTUnwrap(combined.pngData()).write(to: dir.appendingPathComponent(fileName))
        }
    }

    private struct OCRObs {
        let text: String
        let candidate: VNRecognizedText
        let imgHeightPt: CGFloat
    }

    private func wordHeightPt(
        of target: String,
        in observations: [OCRObs],
        excludingLineContaining excluded: String? = nil
    ) -> CGFloat? {
        for obs in observations {
            if let excluded, obs.text.contains(excluded) { continue }
            if let range = obs.text.range(of: target),
               let box = try? obs.candidate.boundingBox(for: range) {
                return box.boundingBox.height * obs.imgHeightPt
            }
        }
        return nil
    }

    private func ocrObservations(_ image: UIImage) throws -> [OCRObs] {
        let cg = try XCTUnwrap(image.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg).perform([req])
        let imgHeightPt = image.size.height
        return (req.results ?? []).compactMap { obs in
            guard let top = obs.topCandidates(1).first else { return nil }
            return OCRObs(text: top.string, candidate: top, imgHeightPt: imgHeightPt)
        }
    }

    private func renderSportsStack(
        cards: [FeedEventData],
        scheme: ColorScheme,
        typeSize: DynamicTypeSize,
        height: CGFloat
    ) -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let cardBg = scheme == .dark ? Color(UIColor.secondarySystemGroupedBackground) : Color.white

        // Matches FeedView `.insetGrouped` geometry on a 390 pt iPhone:
        // 20 pt outer horizontal margin -> 350 pt grouped section -> 16 pt inner padding -> 318 pt EventCardView width.
        let root = VStack(alignment: .leading, spacing: 10) {
            Text("Sports Tab · Even Team Names Across Every Card")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.top, 12)

            VStack(spacing: 0) {
                ForEach(Array(cards.enumerated()), id: \.element.id) { idx, ev in
                    EventCardView(event: ev, reason: nil)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 4)
                    if idx < cards.count - 1 {
                        Divider().padding(.leading, 16)
                    }
                }
            }
            .background(cardBg)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            Spacer(minLength: 0)
        }
        .padding(.horizontal, 20)
        .frame(width: 390, height: height, alignment: .topLeading)
        .background(bg)
        .environment(\.colorScheme, scheme)
        .environmentObject(PinManager())

        let host = hostForMeasurement(root, at: typeSize)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: height))
        window.frame = CGRect(x: 0, y: 0, width: 390, height: height)
        host.view.frame = window.bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        for _ in 0..<5 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width: 390, height: height), format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func sideBySide(_ left: UIImage, _ right: UIImage) -> UIImage {
        let gap: CGFloat = 16
        let size = CGSize(width: left.size.width + right.size.width + gap, height: max(left.size.height, right.size.height))
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: size, format: fmt).image { ctx in
            UIColor(white: 0.12, alpha: 1.0).setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            left.draw(at: .zero)
            right.draw(at: CGPoint(x: left.size.width + gap, y: 0))
        }
    }
}
