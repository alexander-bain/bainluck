import SwiftUI
import UIKit
import Vision
import XCTest

@testable import Bain_Luck

@MainActor
final class SubOnePercentEveryNumberedRowTests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-27T16:00:00Z")!

    private func decodeSnake<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(T.self, from: Data(json.utf8))
    }

    private func renderView<V: View>(
        _ view: V,
        width: CGFloat = 390,
        scheme: ColorScheme
    ) -> UIImage {
        let bg = scheme == .dark
            ? Color(red: 0.05, green: 0.07, blue: 0.11)
            : Color(red: 0.96, green: 0.97, blue: 0.98)
        let wrapped = view
            .fixedSize(horizontal: false, vertical: true)
            .padding(16)
            .frame(width: width)
            .background(bg)
            .environment(\.colorScheme, scheme)
            .environmentObject(PinManager())

        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: 2600))
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let host = hostForMeasurement(wrapped, at: .large)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        host.sizingOptions = [.intrinsicContentSize]
        window.rootViewController = host
        window.makeKeyAndVisible()
        host.view.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        host.traitOverrides.preferredContentSizeCategory = .large
        host.view.layoutIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.08))
        host.view.layoutIfNeeded()

        let measured = host.sizeThatFits(in: CGSize(width: width, height: 10000))
        let height = max(ceil(measured.height), 120)
        window.frame = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.layoutIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.06))

        let format = UIGraphicsImageRendererFormat()
        format.scale = 3.0
        return UIGraphicsImageRenderer(size: CGSize(width: width, height: height), format: format).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        let cgImage = try XCTUnwrap(image.cgImage)
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func writePNG(_ image: UIImage, to url: URL) throws {
        let data = try XCTUnwrap(image.pngData())
        try data.write(to: url)
    }

    // MARK: - Pinned 0.4%, 0.6%, 0.99%, 1.0% & Open-Market Boundary Tests

    func testAllFormattersPinBoundaryValuesAndNeverPrintZeroOrHundredWhenOpen() throws {
        let expected: [(prob: Double, served: Int?, whole: String)] = [
            (0.004, 0, "<1%"),
            (0.004, 1, "<1%"),
            (0.004, nil, "<1%"),
            (0.006, 1, "<1%"),
            (0.006, nil, "<1%"),
            (0.0099, 1, "<1%"),
            (0.0099, nil, "<1%"),
            (0.01, 1, "1%"),
            (0.01, nil, "1%"),
        ]

        for sample in expected {
            XCTAssertEqual(
                formatProbability(sample.prob, renderedPercent: sample.served),
                sample.whole,
                "formatProbability(\(sample.prob), renderedPercent: \(String(describing: sample.served)))"
            )
            let expectedNum = sample.whole.replacingOccurrences(of: "%", with: "")
            XCTAssertEqual(
                percentNumber(sample.prob * 100.0, renderedPercent: sample.served),
                expectedNum,
                "percentNumber(\(sample.prob * 100), renderedPercent: \(String(describing: sample.served)))"
            )
            XCTAssertEqual(
                FeedProbabilityScale.percentLabel(fromFraction: sample.prob),
                sample.whole,
                "FeedProbabilityScale.percentLabel(\(sample.prob))"
            )
            XCTAssertEqual(
                DiscoverRoundupCardModel.probabilityText(probability: sample.prob, renderedPercent: sample.served),
                sample.whole,
                "DiscoverRoundupCardModel.probabilityText(\(sample.prob), renderedPercent: \(String(describing: sample.served)))"
            )
            XCTAssertEqual(
                discoverFuturesCardPercentLabel(sample.served, probability: sample.prob),
                sample.whole,
                "discoverFuturesCardPercentLabel(\(String(describing: sample.served)), probability: \(sample.prob))"
            )
            XCTAssertEqual(
                ChampionshipStageBadges.formatProb(sample.prob),
                sample.whole,
                "ChampionshipStageBadges.formatProb(\(sample.prob))"
            )
            XCTAssertEqual(
                EventAtlasCombatCards11666.formatPercent(sample.prob),
                sample.whole
            )
            XCTAssertEqual(
                EventAtlasCricketCards11666.formatPercent(sample.prob),
                sample.whole
            )
            XCTAssertEqual(
                EventAtlasEsportsCards11666.formatPercent(sample.prob),
                sample.whole
            )
            XCTAssertEqual(
                EventAtlasLacrosseDartsSquashCards11666.formatPercent(sample.prob),
                sample.whole
            )
            XCTAssertEqual(
                EventAtlasRugbyAflCards11666.formatPercent(sample.prob),
                sample.whole
            )

            // Non-division and division Machinery rows
            for settledOut: Bool? in [nil, false] {
                let visual = MachineryOutcomeVisual(
                    outcomeId: 1,
                    marketId: 10,
                    name: "Row",
                    probability: sample.prob,
                    renderedPercent: sample.served ?? Int((sample.prob * 100.0).rounded()),
                    unflooredPercent: sample.served,
                    settledOut: settledOut
                )
                XCTAssertEqual(
                    visual.probabilityLabel,
                    sample.whole,
                    "MachineryOutcomeVisual(\(sample.prob), settledOut: \(String(describing: settledOut)))"
                )
            }
        }

        // CompactGameCard live tenths helper
        XCTAssertEqual(CompactGameCard12616.formatSingleLiveTenths(0.004), "<1%")
        XCTAssertEqual(CompactGameCard12616.formatSingleLiveTenths(0.006), "<1%")
        XCTAssertEqual(CompactGameCard12616.formatSingleLiveTenths(0.0099), "<1%")
        XCTAssertEqual(CompactGameCard12616.formatSingleLiveTenths(0.01), "1.0%")

        // PairedMetricPresentation Stage 1 & Stage 2 with 0.4%, 0.6%, 0.99%, 1.0%
        let pairedSet = PairedMetricSet(
            setId: "paired-sub-one",
            category: "awards",
            kicker: "AWARDS",
            title: "Sub-one boundary check",
            subtitle: "Stages",
            stage1Label: "Nominated",
            stage2Label: "Wins",
            stage1SettledYesLabel: "Nominated",
            stage1SettledNoLabel: "Not nominated",
            entries: [],
            preferredVisualForm: nil,
            stage1Market: nil,
            stage2Market: nil,
            stage1Settled: false
        )
        for (p, exp) in [(0.004, "<1%"), (0.006, "<1%"), (0.0099, "<1%"), (0.01, "1%")] {
            var entry = PairedSubjectEntry(
                subjectKey: "s-\(p)",
                subject: "Contender",
                detail: "",
                stage1MarketId: 1,
                stage1Probability: p,
                stage2MarketId: 2,
                stage2Probability: p
            )
            entry.stage1RenderedPercent = (p >= 0.005 ? 1 : 0)
            entry.stage2RenderedPercent = (p >= 0.005 ? 1 : 0)
            XCTAssertEqual(PairedMetricPresentation.formatStage1Display(entry: entry, set: pairedSet).label, exp)
            XCTAssertEqual(PairedMetricPresentation.formatStage2Display(entry: entry, set: pairedSet).label, exp)
        }

        // Open markets strictly in (0, 1) NEVER print "0%" or "100%"
        let openLowProbs = [0.0001, 0.004, 0.005, 0.006, 0.0099]
        let openHighProbs = [0.9951, 0.996, 0.9999]
        for p in openLowProbs {
            XCTAssertEqual(formatProbability(p, renderedPercent: 0), "<1%")
            XCTAssertEqual(DiscoverRoundupCardModel.probabilityText(probability: p, renderedPercent: 0), "<1%")
            XCTAssertEqual(discoverFuturesCardPercentLabel(0, probability: p), "<1%")
            XCTAssertEqual(ChampionshipStageBadges.formatProb(p), "<1%")
            XCTAssertEqual(EventAtlasCombatCards11666.formatPercent(p), "<1%")
        }
        for p in openHighProbs {
            XCTAssertEqual(formatProbability(p, renderedPercent: 100), ">99%")
            XCTAssertEqual(DiscoverRoundupCardModel.probabilityText(probability: p, renderedPercent: 100), ">99%")
            XCTAssertEqual(discoverFuturesCardPercentLabel(100, probability: p), ">99%")
            XCTAssertEqual(ChampionshipStageBadges.formatProb(p), ">99%")
            XCTAssertEqual(EventAtlasCombatCards11666.formatPercent(p), ">99%")
        }

        // ChampionshipPathPresentation.value
        for (p, exp) in [(0.004, "<1%"), (0.006, "<1%"), (0.0099, "<1%"), (0.01, "1%"), (0.996, ">99%")] {
            let entry = ChampionshipPathEntry(
                tier: 1,
                label: "Title",
                marketName: "Title",
                marketId: 1,
                probability: p,
                rank: 10,
                movement: nil,
                state: nil,
                sourceMark: nil
            )
            XCTAssertEqual(ChampionshipPathPresentation.value(entry), .percent(exp))
        }

        // Soccer 3-way pre-game percentages (numberStreams == false)
        let soccerLow = EventSportHeadlines12472.soccerThreeWayChanceTexts(
            home: 0.99,
            draw: 0.004,
            away: 0.006,
            numberStreams: false
        )
        XCTAssertEqual(soccerLow.draw, "<1%")
        XCTAssertEqual(soccerLow.away, "<1%")
        let soccerSubOneEdge = EventSportHeadlines12472.soccerThreeWayChanceTexts(
            home: 0.9801,
            draw: 0.0099,
            away: 0.01,
            numberStreams: false
        )
        XCTAssertEqual(soccerSubOneEdge.draw, "<1%")
        XCTAssertEqual(soccerSubOneEdge.away, "1%")
        let soccerOpenHigh = EventSportHeadlines12472.soccerThreeWayChanceTexts(
            home: 0.996,
            draw: 0.002,
            away: 0.002,
            numberStreams: false
        )
        XCTAssertEqual(soccerOpenHigh.home, ">99%")

        // FuturesAtlasPresentation11666 open outcome + opening chance
        let atlasJSON = """
        {
          "id": 8801,
          "name": "Boundary Futures Market",
          "category": "politics",
          "llm_sport_category": "politics",
          "status": "active",
          "source": "kalshi",
          "mutually_exclusive": true,
          "outcomes": [
            {"id": 1, "name": "Leader 99.6%", "probability": 0.996, "opening_probability": 0.996},
            {"id": 2, "name": "Boundary 1.0%", "probability": 0.01, "opening_probability": 0.01},
            {"id": 3, "name": "Boundary 0.99%", "probability": 0.0099, "opening_probability": 0.0099},
            {"id": 4, "name": "Boundary 0.6%", "probability": 0.006, "opening_probability": 0.006},
            {"id": 5, "name": "Boundary 0.4%", "probability": 0.004, "opening_probability": 0.004}
          ]
        }
        """
        let atlasDetail = try decodeSnake(FuturesMarketDetail.self, atlasJSON)
        let atlasPage = FuturesAtlasPresentation11666.build(market: atlasDetail, now: fixedNow)
        XCTAssertEqual(atlasPage.header.primaryDisplay.primaryLabel, ">99%")
        XCTAssertEqual(atlasPage.header.openingChanceText, "Opening chance >99%")
        XCTAssertEqual(atlasPage.detailsSheet.openingChanceValue, ">99%")
        XCTAssertEqual(
            atlasPage.body.allRows.map { $0.displayValue.primaryLabel },
            [">99%", "1%", "<1%", "<1%", "<1%"]
        )
        XCTAssertEqual(
            atlasPage.body.allRows.compactMap(\.openingText),
            [
                "Opening chance >99%",
                "Opening chance 1%",
                "Opening chance <1%",
                "Opening chance <1%",
                "Opening chance <1%"
            ]
        )

        // Kit ring fallback speech & label formatting
        for (p, exp) in [(0.004, "<1%"), (0.006, "<1%"), (0.0099, "<1%"), (0.01, "1%"), (0.996, ">99%")] {
            XCTAssertEqual(DiscoverRoundupCardModel.probabilityText(probability: p, renderedPercent: nil), exp)
        }

        // MyStuffView.eventCopyProbabilityText (Copy Probability string outside Text(...))
        for (p, exp) in [(0.004, "<1%"), (0.006, "<1%"), (0.0099, "<1%"), (0.01, "1%"), (0.996, ">99%")] {
            let feedJSON = """
            [{
              "type": "event",
              "score": 40,
              "data": {
                "id": 99100,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "away_team": "Portland Trail Blazers",
                "home_team": "Minnesota Timberwolves",
                "status": "scheduled",
                "commence_time": "2026-11-28T01:00:00Z",
                "hero_probability_source": "blend",
                "hero_probability_observed_at": "2026-11-27T20:00:00Z",
                "current_odds": {
                  "away_probability": \(1.0 - p),
                  "home_probability": \(p)
                }
              }
            }]
            """
            let items = try decodeSnake([FeedItem].self, feedJSON)
            let event = try XCTUnwrap(items.first?.event)
            XCTAssertEqual(
                MyStuffView.eventCopyProbabilityText(event),
                "Minnesota Timberwolves: \(exp)",
                "MyStuffView.eventCopyProbabilityText at p=\(p)"
            )
        }
    }

    func testCaptureRepresentativeCards() throws {
        let outDir = ProcessInfo.processInfo.environment["SUB_ONE_RENDER_DIR"] ?? ""
        let outURL = outDir.isEmpty ? nil : URL(fileURLWithPath: outDir, isDirectory: true)
        if let outURL {
            try FileManager.default.createDirectory(at: outURL, withIntermediateDirectories: true)
        }

        // 1. DiscoverRoundupCardView (non-division roundup with 99.6%, 1.0%, 0.99%, 0.6%, 0.4%)
        let roundupContract = FeedRoundupContract(
            kicker: "LONG SHOTS",
            subtitle: "Exact boundaries: 99.6%, 1.0%, 0.99%, 0.6%, 0.4%",
            completeGroup: true,
            footer: "5 candidates",
            order: "probability",
            rows: [
                FeedRoundupRow(marketId: 901, label: "Candidate (99.6%)", probability: 0.996, renderedPercent: 100),
                FeedRoundupRow(marketId: 902, label: "Candidate (1.0%)", probability: 0.01, renderedPercent: 1),
                FeedRoundupRow(marketId: 903, label: "Candidate (0.99%)", probability: 0.0099, renderedPercent: 1),
                FeedRoundupRow(marketId: 904, label: "Candidate (0.6%)", probability: 0.006, renderedPercent: 1),
                FeedRoundupRow(marketId: 905, label: "Candidate (0.4%)", probability: 0.004, renderedPercent: 0),
            ]
        )
        let roundupModel = try XCTUnwrap(
            DiscoverRoundupCardModel.build(
                title: "Discover Roundup Boundary Check",
                contract: roundupContract,
                now: fixedNow
            )
        )
        let roundupRef = try XCTUnwrap(
            FeedThemeCollectionRef(slug: "roundup-sub-one", name: "Long Shots", revision: 1, collectionCount: 5)
        )
        XCTAssertEqual(
            roundupModel.rows.map(\.formattedPercentText),
            [">99%", "1%", "<1%", "<1%", "<1%"]
        )

        // 2. Non-division MachineryDiscoverCardView (settledOut: nil)
        let machineryCard = MachineryCardContract(
            slug: "machinery-sub-one-check",
            formId: .siblingFieldsGrid,
            kicker: "MACHINERY CARD",
            title: "Non-Division Ranked Contenders",
            subtitle: "Rows at 1.0%, 0.99%, 0.6% (non-division)",
            footer: "See all contenders",
            scaleOrdered: false,
            sectionCount: 1,
            outcomeRows: [
                MachineryOutcomeVisual(outcomeId: 11, marketId: 501, name: "Row (1.0%)", probability: 0.01, renderedPercent: 1, unflooredPercent: 1),
                MachineryOutcomeVisual(outcomeId: 12, marketId: 501, name: "Row (0.99%)", probability: 0.0099, renderedPercent: 1, unflooredPercent: 1),
                MachineryOutcomeVisual(outcomeId: 13, marketId: 501, name: "Row (0.6%)", probability: 0.006, renderedPercent: 1, unflooredPercent: 1),
            ]
        )
        XCTAssertEqual(machineryCard.displayOutcomeRows.map(\.probabilityLabel), ["1%", "<1%", "<1%"])

        // 3. NativeFuturesDiscoverCard (open market boundaries: 1.0%, 0.99%, 0.6% and 99.6%, 0.6%, 0.4%)
        let futuresCardA = try decodeSnake(FeedFuturesData.self, """
        {
          "id": 9101,
          "name": "Discover Futures (1.0%, 0.99%, 0.6%)",
          "llm_sport_category": "politics",
          "source": "kalshi",
          "status": "open",
          "top_outcomes": [
            {"id": 1, "name": "Boundary (1.0%)", "probability": 0.01, "rendered_percent": 1, "rank": 1},
            {"id": 2, "name": "Boundary (0.99%)", "probability": 0.0099, "rendered_percent": 1, "rank": 2},
            {"id": 3, "name": "Boundary (0.6%)", "probability": 0.006, "rendered_percent": 1, "rank": 3}
          ],
          "outcome_count": 3
        }
        """)
        let futuresCardB = try decodeSnake(FeedFuturesData.self, """
        {
          "id": 9102,
          "name": "Discover Futures (99.6% & 0.4%)",
          "llm_sport_category": "economics",
          "source": "polymarket",
          "status": "open",
          "top_outcomes": [
            {"id": 4, "name": "Near-Certain (99.6%)", "probability": 0.996, "rendered_percent": 100, "rank": 1},
            {"id": 5, "name": "Boundary (0.6%)", "probability": 0.006, "rendered_percent": 1, "rank": 2},
            {"id": 6, "name": "Boundary (0.4%)", "probability": 0.004, "rendered_percent": 0, "rank": 3}
          ],
          "outcome_count": 3
        }
        """)

        // 4. ChampionshipPath stages (1.0%, 0.99%, 0.6%, 0.4%)
        let stages = [
            try decodeSnake(ProgressionStageData.self, #"{"key":"make_playoffs","label":"Boundary (1.0%)","probability":0.01}"#),
            try decodeSnake(ProgressionStageData.self, #"{"key":"division","label":"Boundary (0.99%)","probability":0.0099}"#),
            try decodeSnake(ProgressionStageData.self, #"{"key":"pennant","label":"Boundary (0.6%)","probability":0.006}"#),
            try decodeSnake(ProgressionStageData.self, #"{"key":"championship","label":"Boundary (0.4%)","probability":0.004}"#),
        ]

        // 5. HeatMapCardView (99.6%, 1.0%, 0.99%, 0.6%, 0.4%)
        let heatMapData = try decodeSnake(FeedFuturesData.self, """
        {
          "id": 9103,
          "name": "HeatMap Thresholds (0.4% to 99.6%)",
          "llm_sport_category": "tech",
          "resolution_date": "2027-01-01T00:00:00Z",
          "top_outcomes": [{"id": 31, "name": "1.0%", "probability": 0.01, "rendered_percent": 1, "rank": 1}],
          "discover_card": {
            "suggested_format": "heatmap",
            "threshold_points": [
              {"label": "99.6%", "value": 1, "probability": 0.996},
              {"label": "1.0%", "value": 2, "probability": 0.01},
              {"label": "0.99%", "value": 3, "probability": 0.0099},
              {"label": "0.6%", "value": 4, "probability": 0.006},
              {"label": "0.4%", "value": 5, "probability": 0.004}
            ]
          }
        }
        """)

        for (schemeName, scheme) in [("light", ColorScheme.light), ("dark", ColorScheme.dark)] {
            let roundupImg = renderView(
                DiscoverRoundupCardView(model: roundupModel, collectionRef: roundupRef, now: fixedNow),
                scheme: scheme
            )
            let roundupOCR = try ocrLines(roundupImg).joined(separator: " ")
            XCTAssertTrue(roundupOCR.contains("<1%") || roundupOCR.contains("<1 %"), "roundup missing <1%: \(roundupOCR)")
            XCTAssertTrue(roundupOCR.contains(">99%") || roundupOCR.contains(">99 %"), "roundup missing >99%: \(roundupOCR)")
            XCTAssertFalse(roundupOCR.range(of: #"(?<![\d.])0%"#, options: .regularExpression) != nil, "roundup printed 0%: \(roundupOCR)")
            XCTAssertFalse(roundupOCR.range(of: #"(?<!\d)100%"#, options: .regularExpression) != nil, "roundup printed 100%: \(roundupOCR)")

            let machineryImg = renderView(
                MachineryDiscoverCardView(card: machineryCard),
                scheme: scheme
            )
            let machineryOCR = try ocrLines(machineryImg).joined(separator: " ")
            XCTAssertTrue(machineryOCR.contains("<1%"), "machinery missing <1%: \(machineryOCR)")
            XCTAssertTrue(machineryOCR.contains("1%"), "machinery missing 1%: \(machineryOCR)")

            let futuresStack = VStack(spacing: 12) {
                NativeFuturesDiscoverCard(
                    data: futuresCardA,
                    feedContext: nil,
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
                NativeFuturesDiscoverCard(
                    data: futuresCardB,
                    feedContext: nil,
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            }
            let futuresImg = renderView(futuresStack, scheme: scheme)
            let futuresOCR = try ocrLines(futuresImg).joined(separator: " ")
            XCTAssertTrue(futuresOCR.contains("<1%"), "futures missing <1%: \(futuresOCR)")
            XCTAssertTrue(futuresOCR.contains(">99%"), "futures missing >99%: \(futuresOCR)")
            XCTAssertFalse(futuresOCR.range(of: #"(?<![\d.])0%"#, options: .regularExpression) != nil, "futures printed 0%: \(futuresOCR)")
            XCTAssertFalse(futuresOCR.range(of: #"(?<!\d)100%"#, options: .regularExpression) != nil, "futures printed 100%: \(futuresOCR)")

            let champCard = VStack(alignment: .leading, spacing: 8) {
                Text("CHAMPIONSHIP PATH")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.secondary)
                ForEach(stages, id: \.key) { st in
                    HStack {
                        Text(st.label)
                            .font(.subheadline)
                        Spacer()
                        ChampionshipStageBadges(stage: st)
                    }
                }
            }
            .padding(14)
            .background(scheme == .dark ? Color(red: 0.11, green: 0.11, blue: 0.12) : .white,
                        in: RoundedRectangle(cornerRadius: 14))
            let champImg = renderView(champCard, scheme: scheme)
            let champOCR = try ocrLines(champImg).joined(separator: " ")
            XCTAssertTrue(champOCR.contains("<1%"), "championship missing <1%: \(champOCR)")

            let heatMapImg = renderView(
                HeatMapCardView(data: heatMapData, navigationPath: .constant(NavigationPath()), now: fixedNow),
                scheme: scheme
            )
            let heatMapOCR = try ocrLines(heatMapImg).joined(separator: " ")
            XCTAssertTrue(heatMapOCR.contains("<1%") || heatMapOCR.contains("<1 %"), "heatmap missing <1%: \(heatMapOCR)")
            XCTAssertTrue(heatMapOCR.contains(">99%") || heatMapOCR.contains(">99 %"), "heatmap missing >99%: \(heatMapOCR)")
            XCTAssertFalse(heatMapOCR.range(of: #"(?<![\d.])0%"#, options: .regularExpression) != nil, "heatmap printed 0%: \(heatMapOCR)")
            XCTAssertFalse(heatMapOCR.range(of: #"(?<!\d)100%"#, options: .regularExpression) != nil, "heatmap printed 100%: \(heatMapOCR)")

            if let outURL {
                try writePNG(roundupImg, to: outURL.appendingPathComponent("roundup-\(schemeName).png"))
                try writePNG(machineryImg, to: outURL.appendingPathComponent("machinery-\(schemeName).png"))
                try writePNG(futuresImg, to: outURL.appendingPathComponent("futures-\(schemeName).png"))
                try writePNG(champImg, to: outURL.appendingPathComponent("championship-\(schemeName).png"))
                try writePNG(heatMapImg, to: outURL.appendingPathComponent("heatmap-\(schemeName).png"))
            }
        }
    }
}
