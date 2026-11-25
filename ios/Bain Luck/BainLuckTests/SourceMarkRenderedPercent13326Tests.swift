import Foundation
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13326: the "Where this number comes from" sheet's headline number always matches the
/// `rendered_percent` printed on the row/card that opened it (for example, `"No 86%"` when raw
/// `probability` is `0.865` paired with `"Yes 14%"` so both rows total 100%).
@MainActor
final class SourceMarkRenderedPercent13326Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-21T16:00:00Z")!

    private func decodeSnake<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: Data(json.utf8))
    }

    private func renderView<V: View>(
        _ view: V,
        width: CGFloat = 390,
        fixedHeight: CGFloat? = nil,
        scheme: ColorScheme = .light
    ) -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let sized: AnyView = {
            if let fixedHeight {
                return AnyView(
                    view
                        .frame(width: width, height: fixedHeight, alignment: .topLeading)
                        .background(bg)
                        .environment(\.colorScheme, scheme)
                )
            }
            return AnyView(
                view
                    .frame(width: width, alignment: .topLeading)
                    .fixedSize(horizontal: false, vertical: true)
                    .background(bg)
                    .environment(\.colorScheme, scheme)
            )
        }()

        let measureHost = hostForMeasurement(sized, at: .large)
        measureHost.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let fittingH = fixedHeight ?? min(max(measureHost.sizeThatFits(in: CGSize(width: width, height: 1_800)).height + 16, 160), 1_800)

        let root: AnyView = fixedHeight != nil
            ? sized
            : AnyView(NavigationStack { sized.toolbar(.hidden, for: .navigationBar) })

        let host = hostForMeasurement(root, at: .large)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: fittingH))
        window.frame = CGRect(x: 0, y: 0, width: width, height: fittingH)
        host.view.frame = window.bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<3 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        return UIGraphicsImageRenderer(size: host.view.bounds.size, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: CGRect(origin: .zero, size: host.view.bounds.size), afterScreenUpdates: true)
        }
    }

    private func ocrStrings(_ image: UIImage) throws -> [String] {
        guard let cgImage = image.cgImage else { return [] }
        var lines: [String] = []
        let request = VNRecognizeTextRequest { req, _ in
            let obs = (req.results as? [VNRecognizedTextObservation]) ?? []
            lines = obs.compactMap { $0.topCandidates(1).first?.string }
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
        return lines
    }

    func testSheetHeadlineHonorsRenderedPercentAndKeepsPolymarketAttributionRow() throws {
        let mark = try decodeSnake(SourceMark.self, """
        {
          "state": "single",
          "sources": [
            {
              "key": "polymarket",
              "name": "Polymarket",
              "probability": 0.865,
              "observed_at": null,
              "reason": "observation_unknown"
            }
          ],
          "method": "Rounded with Yes so the two rows total 100%"
        }
        """)

        // Without renderedPercent, 0.865 rounds half-away-from-zero to 87%; with renderedPercent: 86,
        // the headline prints 86% to match the row while source lines keep Polymarket's raw 87%.
        XCTAssertEqual(SourceMarkSheet.headline(0.865), "87%")
        XCTAssertEqual(SourceMarkSheet.headline(0.865, renderedPercent: 86), "86%")
        XCTAssertEqual(SourceMarkSheet.headline(0.865, renderedPercent: 86, showsTenths: true), "86.5%")
        XCTAssertEqual(SourceMarkSheet.headline(nil, renderedPercent: 86), "86%")
        XCTAssertEqual(SourceMarkSheet.headline(0.004, renderedPercent: 0), "<1%")
        XCTAssertEqual(SourceMarkSheet.headline(0.996, renderedPercent: 100), ">99%")

        XCTAssertEqual(
            SourceMarkSheet.parsedWholePercent(from: "86%"),
            86
        )
        XCTAssertNil(SourceMarkSheet.parsedWholePercent(from: "86.5%"))
        XCTAssertNil(SourceMarkSheet.parsedWholePercent(from: "<1%"))

        let lines = SourceMarkSheet.lines(mark, showsTenths: false, now: fixedNow)
        XCTAssertEqual(lines.count, 1)
        XCTAssertEqual(lines.first?.price, "87%")
        XCTAssertNil(
            SourceMarkSheet.singleUnscaledAttribution(mark, headline: "86%", now: fixedNow),
            "Must keep 'Polymarket 87%' visible when the headline shows pair-rounded '86%'"
        )
    }

    func testLiveGtaDeadlineCardAndOpenSheetBothPrint86Percent() throws {
        let gtaJSON = """
        {
          "id": 66907859,
          "name": "Another GTA VI trailer released by November 30?",
          "category": "entertainment",
          "llm_sport_category": "entertainment",
          "market_tier": 2,
          "market_type": "yes_no",
          "status": "open",
          "source": "polymarket",
          "sources": ["polymarket"],
          "source_count": 1,
          "mutually_exclusive": true,
          "top_outcomes": [
            {
              "id": 251306316,
              "name": "Yes",
              "probability": 0.135,
              "rendered_percent": 14,
              "rank": 1,
              "source_mark": {
                "state": "single",
                "sources": [
                  {"key": "polymarket", "name": "Polymarket", "probability": 0.135, "reason": "observation_unknown"}
                ]
              }
            },
            {
              "id": 251306317,
              "name": "No",
              "probability": 0.865,
              "rendered_percent": 86,
              "rank": 2,
              "source_mark": {
                "state": "single",
                "sources": [
                  {"key": "polymarket", "name": "Polymarket", "probability": 0.865, "reason": "observation_unknown"}
                ],
                "method": "Rounded with Yes so the two rows total 100%"
              }
            }
          ]
        }
        """
        let data = try decodeSnake(FeedFuturesData.self, gtaJSON)
        let percents = discoverFuturesCardPercents(data.topOutcomes ?? [])
        XCTAssertEqual(percents, [14, 86])

        let noOutcome = try XCTUnwrap(data.topOutcomes?.last)
        let noMark = try XCTUnwrap(data.resolvedSourceMark(for: noOutcome))
        let noRenderedPct = try XCTUnwrap(percents.last ?? nil)
        XCTAssertEqual(noRenderedPct, 86)

        let suiteName = "Test13326.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults)

        let cardImg = renderView(
            NativeFuturesDiscoverCard(
                data: data,
                feedContext: "By November 30",
                expandedContext: nil,
                navigationPath: .constant(NavigationPath())
            )
            .environmentObject(pinManager)
            .padding(16)
        )
        let cardText = try ocrStrings(cardImg).joined(separator: " ")
        XCTAssertTrue(cardText.contains("86%"), "Card row must print 86%: \(cardText)")

        let sheetImg = renderView(
            SourceMarkSheet(
                mark: noMark,
                number: noOutcome.probability,
                renderedPercent: noRenderedPct,
                subject: noOutcome.name,
                now: fixedNow
            ),
            fixedHeight: 360
        )
        let sheetLines = try ocrStrings(sheetImg)
        let sheetText = sheetLines.joined(separator: " ")
        XCTAssertTrue(sheetLines.contains("86%"), "Sheet big headline must print 86%, got: \(sheetLines)")
        XCTAssertTrue(sheetText.contains("Polymarket"), "Sheet must keep Polymarket attribution row: \(sheetLines)")
        XCTAssertTrue(sheetLines.contains("87%"), "Sheet source line should keep venue price 87%: \(sheetLines)")
        XCTAssertTrue(sheetText.contains("Rounded with Yes"), "Sheet must keep method note: \(sheetLines)")
    }

    func testRoundupAndGroupSummaryAndGameResolversCarryRenderedPercent() throws {
        // 1. Round-up model
        let polymarketNo = try decodeSnake(SourceMark.self, """
        {"state":"single","sources":[{"key":"polymarket","name":"Polymarket","probability":0.865}],"method":"Rounded with Yes so the two rows total 100%"}
        """)
        let contract = FeedRoundupContract(
            kicker: "ENTERTAINMENT",
            footer: "Polymarket",
            rows: [
                FeedRoundupRow(
                    marketId: 66907859,
                    outcomeId: 251306316,
                    label: "Yes · GTA VI trailer by Nov 30",
                    probability: 0.135,
                    renderedPercent: 14,
                    observedAt: "2026-11-21T15:50:00Z",
                    sourceMark: polymarketNo
                ),
                FeedRoundupRow(
                    marketId: 66907859,
                    outcomeId: 251306317,
                    label: "No · GTA VI trailer by Nov 30",
                    probability: 0.865,
                    renderedPercent: 86,
                    observedAt: "2026-11-21T15:50:00Z",
                    sourceMark: polymarketNo
                ),
                FeedRoundupRow(
                    marketId: 66907860,
                    outcomeId: 251306318,
                    label: "Other market",
                    probability: 0.42,
                    renderedPercent: 42,
                    observedAt: "2026-11-21T15:50:00Z",
                    sourceMark: polymarketNo
                )
            ]
        )
        let roundupModel = try XCTUnwrap(
            DiscoverRoundupCardModel.build(title: "By November 30", contract: contract, now: fixedNow)
        )
        let noRow = try XCTUnwrap(roundupModel.rows.first(where: { $0.label.hasPrefix("No") }))
        XCTAssertEqual(noRow.renderedPercent, 86)
        XCTAssertEqual(
            SourceMarkSheet.headline(noRow.rawProbability, renderedPercent: noRow.renderedPercent),
            "86%"
        )

        // 2. DiscoverGroupRows compactSummary
        let futures = try decodeSnake(FeedFuturesData.self, """
        {
          "id": 66907859,
          "name": "Another GTA VI trailer released by November 30?",
          "mutually_exclusive": true,
          "top_outcomes": [
            {"id": 1, "name": "No", "probability": 0.865, "rendered_percent": 86, "rank": 1},
            {"id": 2, "name": "Yes", "probability": 0.135, "rendered_percent": 14, "rank": 2}
          ]
        }
        """)
        let summary = DiscoverGroupRows.compactSummary(for: futures)
        XCTAssertEqual(summary.renderedPercent, 86)
        XCTAssertEqual(formatProbability(try XCTUnwrap(summary.probability), renderedPercent: summary.renderedPercent), "86%")

        // 3. Game card presentation
        let event = try decodeSnake(FeedEventData.self, """
        {
          "id": 99326,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Chicago Bulls",
          "home_team": "Boston Celtics",
          "commence_time": "2026-11-21T20:00:00Z",
          "status": "scheduled",
          "current_odds": {
            "away_probability": 0.135,
            "home_probability": 0.865,
            "away_rendered_percent": 14,
            "home_rendered_percent": 86
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              {"key": "betting", "name": "Sportsbooks", "count": 8, "probability": 0.865, "observed_at": "2026-11-21T15:59:00Z"},
              {"key": "kalshi", "name": "Kalshi", "probability": 0.865, "observed_at": "2026-11-21T15:59:00Z"}
            ]
          }
        }
        """)
        let cardPres = try XCTUnwrap(
            EventCardView.resolvedCardSourceMarkPresentation(
                event: event,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false
            )
        )
        XCTAssertEqual(cardPres.renderedPercent, 86)
        XCTAssertEqual(SourceMarkSheet.headline(cardPres.number, renderedPercent: cardPres.renderedPercent), "86%")
    }
}
