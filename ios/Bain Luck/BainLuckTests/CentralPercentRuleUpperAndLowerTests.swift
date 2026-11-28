import SwiftUI
import XCTest

@testable import Bain_Luck

/// Item 3 / #13662: every whole-percent probability formatter in the app shares the
/// central `formatProbability` rule (`>99%` strictly above 99%, `<1%` strictly below 1%),
/// while tenths/decimal formatters keep their existing behavior for product review.
final class CentralPercentRuleUpperAndLowerTests: XCTestCase {

    // MARK: - Pinned Upper & Lower Boundaries (0.4%, 0.6%, 0.99%, 1.0%, 99.0%, 99.2%, 99.5%, 99.6%)

    func testWholePercentFormattersShareExactBoundsBelowOneAndAboveNinetyNine() {
        let cases: [(prob: Double, served: Int?, expected: String)] = [
            (0.004, 0, "<1%"),
            (0.004, nil, "<1%"),
            (0.006, 1, "<1%"),
            (0.006, nil, "<1%"),
            (0.0099, 1, "<1%"),
            (0.0099, nil, "<1%"),
            (0.01, 1, "1%"),
            (0.01, nil, "1%"),
            (0.99, 99, "99%"),
            (0.99, nil, "99%"),
            (0.992, 99, ">99%"),
            (0.992, nil, ">99%"),
            (0.995, 100, ">99%"),
            (0.995, nil, ">99%"),
            (0.996, 100, ">99%"),
            (0.996, nil, ">99%"),
        ]

        for c in cases {
            XCTAssertEqual(
                formatProbability(c.prob, renderedPercent: c.served),
                c.expected,
                "formatProbability(\(c.prob), renderedPercent: \(String(describing: c.served)))"
            )
            XCTAssertEqual(
                DiscoverRoundupCardModel.probabilityText(probability: c.prob, renderedPercent: c.served),
                c.expected,
                "DiscoverRoundupCardModel.probabilityText(\(c.prob), renderedPercent: \(String(describing: c.served)))"
            )
            let parts = DiscoverRoundupCardModel.probabilityParts(probability: c.prob, renderedPercent: c.served)
            XCTAssertEqual(
                "\(parts.marker ?? "")\(parts.digits)%",
                c.expected,
                "DiscoverRoundupCardModel.probabilityParts(\(c.prob))"
            )
            XCTAssertEqual(
                discoverFuturesCardPercentLabel(c.served, probability: c.prob),
                c.expected,
                "discoverFuturesCardPercentLabel(\(String(describing: c.served)), probability: \(c.prob))"
            )
            let fParts = discoverFuturesCardPercentParts(c.served, probability: c.prob)
            XCTAssertEqual(
                "\(fParts.marker ?? "")\(fParts.digits)%",
                c.expected,
                "discoverFuturesCardPercentParts(\(c.prob))"
            )
            XCTAssertEqual(
                ChampionshipStageBadges.formatProb(c.prob),
                c.expected,
                "ChampionshipStageBadges.formatProb(\(c.prob))"
            )
            XCTAssertEqual(
                EventAtlasGolfTournament11666.wholePercentProbabilityText(c.prob),
                c.expected,
                "EventAtlasGolfTournament11666.wholePercentProbabilityText(\(c.prob))"
            )
            XCTAssertEqual(
                KitAxisBodyView366B.formatPercentDotValue(c.prob * 100.0),
                c.expected,
                "KitAxisBodyView366B.formatPercentDotValue(\(c.prob * 100.0))"
            )
            XCTAssertEqual(
                PlayerPropsCardView.propPercentText(c.prob, settled: false),
                c.expected,
                "PlayerPropsCardView.propPercentText(\(c.prob), settled: false)"
            )
            XCTAssertEqual(EventAtlasCombatCards11666.formatPercent(c.prob), c.expected)
            XCTAssertEqual(EventAtlasCricketCards11666.formatPercent(c.prob), c.expected)
            XCTAssertEqual(EventAtlasEsportsCards11666.formatPercent(c.prob), c.expected)
            XCTAssertEqual(EventAtlasLacrosseDartsSquashCards11666.formatPercent(c.prob), c.expected)
            XCTAssertEqual(EventAtlasRugbyAflCards11666.formatPercent(c.prob), c.expected)

            let visual = MachineryOutcomeVisual(
                outcomeId: 1,
                marketId: 10,
                name: "Outcome",
                probability: c.prob,
                renderedPercent: c.served ?? Int((c.prob * 100.0).rounded()),
                unflooredPercent: c.served,
                settledOut: false
            )
            XCTAssertEqual(visual.probabilityLabel, c.expected, "MachineryOutcomeVisual(\(c.prob))")
        }

        // Exact settled endpoints preserve "0%" / "100%" where contracts expect them.
        XCTAssertEqual(DiscoverRoundupCardModel.probabilityText(probability: 0.0, renderedPercent: nil), "0%")
        XCTAssertEqual(DiscoverRoundupCardModel.probabilityText(probability: 1.0, renderedPercent: nil), "100%")
        XCTAssertEqual(KitAxisBodyView366B.formatPercentDotValue(0.0), "0%")
        XCTAssertEqual(KitAxisBodyView366B.formatPercentDotValue(100.0), "100%")
        XCTAssertEqual(PlayerPropsCardView.propPercentText(0.0, settled: true), "0%")
        XCTAssertEqual(PlayerPropsCardView.propPercentText(1.0, settled: true), "100%")
    }

    func testSoccerThreeWayWholePercentUsesAboveNinetyNineAndBelowOneAtNinetyNinePointTwo() {
        let high = EventSportHeadlines12472.soccerThreeWayChanceTexts(
            home: 0.992,
            draw: 0.004,
            away: 0.004,
            numberStreams: false
        )
        XCTAssertEqual(high.home, ">99%")
        XCTAssertEqual(high.draw, "<1%")
        XCTAssertEqual(high.away, "<1%")

        let mid = EventSportHeadlines12472.soccerThreeWayChanceTexts(
            home: 0.990,
            draw: 0.005,
            away: 0.005,
            numberStreams: false
        )
        XCTAssertEqual(mid.home, "99%")
        XCTAssertEqual(mid.draw, "<1%")
        XCTAssertEqual(mid.away, "<1%")

        let edgeSubOne = EventSportHeadlines12472.soccerThreeWayChanceTexts(
            home: 0.984,
            draw: 0.010,
            away: 0.006,
            numberStreams: false
        )
        XCTAssertEqual(edgeSubOne.home, "98%")
        XCTAssertEqual(edgeSubOne.draw, "1%")
        XCTAssertEqual(edgeSubOne.away, "<1%")
    }

    func testPairedMetricPresentationStage2AndStage1RespectNinetyNinePointTwoAndZeroPointSix() throws {
        let pairedSet = PairedMetricSet(
            setId: "central-percent-paired",
            category: "awards",
            kicker: "AWARDS",
            title: "Boundary Check",
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
        var entry = PairedSubjectEntry(
            subjectKey: "sub",
            subject: "Favorite",
            detail: "",
            stage1MarketId: 1,
            stage1Probability: 0.992,
            stage2MarketId: 2,
            stage2Probability: 0.006
        )
        entry.stage1RenderedPercent = 99
        entry.stage2RenderedPercent = 1
        XCTAssertEqual(PairedMetricPresentation.formatStage1Display(entry: entry, set: pairedSet).label, ">99%")
        XCTAssertEqual(PairedMetricPresentation.formatStage2Display(entry: entry, set: pairedSet).label, "<1%")
    }

    func testSeriesProbabilityOpenSeriesUsesCentralRuleEvenAboveNinetyNinePointFive() {
        let open992 = SeriesProbabilityView.barLabels(
            homeSeriesProb: 0.992,
            homeTeam: "BOS",
            awayTeam: "MIA",
            isSeriesOver: false,
            homeClinched: false,
            awayClinched: false
        )
        XCTAssertNil(open992.clinched)
        XCTAssertEqual(open992.home, ">99%")
        XCTAssertEqual(open992.away, "<1%")

        let open996 = SeriesProbabilityView.barLabels(
            homeSeriesProb: 0.996,
            homeTeam: "BOS",
            awayTeam: "MIA",
            isSeriesOver: false,
            homeClinched: false,
            awayClinched: false
        )
        XCTAssertNil(open996.clinched)
        XCTAssertEqual(open996.home, ">99%")
        XCTAssertEqual(open996.away, "<1%")

        let open006 = SeriesProbabilityView.barLabels(
            homeSeriesProb: 0.006,
            homeTeam: "MIA",
            awayTeam: "BOS",
            isSeriesOver: false,
            homeClinched: false,
            awayClinched: false
        )
        XCTAssertNil(open006.clinched)
        XCTAssertEqual(open006.home, "<1%")
        XCTAssertEqual(open006.away, ">99%")

        let clinched = SeriesProbabilityView.barLabels(
            homeSeriesProb: 1.0,
            homeTeam: "BOS",
            awayTeam: "MIA",
            isSeriesOver: true,
            homeClinched: true,
            awayClinched: false
        )
        XCTAssertEqual(clinched.clinched, "BOS 100%")
    }

    func testPlayerMilestoneProfileSpokenSummaryUsesCentralPercentRule() {
        let profile = PlayerMilestoneProfile.Profile(
            milestones: [
                .init(index: 0, threshold: 25, probability: 0.992),
                .init(index: 1, threshold: 50, probability: 0.01),
                .init(index: 2, threshold: 100, probability: 0.006),
            ],
            domain: 20...105
        )
        let summary = PlayerMilestoneProfile.spokenSummary(profile, stat: "Receiving Yards")
        XCTAssertEqual(summary, "Receiving Yards, chance to reach each line: 25+ >99%, 50+ 1%, 100+ <1%")
    }

    // MARK: - Source Guard Against Threshold Drift

    func testWholePercentHelpersDoNotDriftBackToNinetyNinePointFiveOrZeroPointFive() throws {
        let iosRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()

        func source(_ rel: String) throws -> String {
            try String(contentsOf: iosRoot.appendingPathComponent(rel), encoding: .utf8)
        }

        // 1. Unified whole-percent files must never revert to 0.995 / 0.005 bounds.
        let roundup = try source("Bain Luck/Utilities/DiscoverRoundupModels.swift")
        XCTAssertFalse(roundup.contains("0.995"))
        XCTAssertTrue(roundup.contains("clamped > 0.99 && clamped < 1.0"))

        let champ = try source("Bain Luck/Components/ChampionshipPathView.swift")
        XCTAssertFalse(champ.contains("0.995"))
        XCTAssertTrue(champ.contains("formatProbability(p)"))

        let golf = try source("Bain Luck/Components/EventAtlasGolfTournament11666.swift")
        let wholeGolfStart = try XCTUnwrap(golf.range(of: "func wholePercentProbabilityText"))
        let wholeGolfEnd = try XCTUnwrap(golf.range(of: "func liveStreamingProbabilityText", range: wholeGolfStart.upperBound..<golf.endIndex))
        let wholeGolfBody = String(golf[wholeGolfStart.upperBound..<wholeGolfEnd.lowerBound])
        XCTAssertTrue(wholeGolfBody.contains("formatProbability("))
        XCTAssertFalse(wholeGolfBody.contains("< 0.5"))

        let sportHeadlines = try source("Bain Luck/Utilities/EventSportHeadlines12472.swift")
        let wholeSoccerStart = try XCTUnwrap(sportHeadlines.range(of: "if numberStreams {"))
        let wholeSoccerEnd = try XCTUnwrap(sportHeadlines.range(of: "nonisolated private static func largestRemainderUnits", range: wholeSoccerStart.upperBound..<sportHeadlines.endIndex))
        let wholeSoccerElse = String(sportHeadlines[wholeSoccerStart.upperBound..<wholeSoccerEnd.lowerBound])
            .components(separatedBy: "} else {").last ?? ""
        XCTAssertFalse(wholeSoccerElse.contains("0.995"))
        XCTAssertTrue(wholeSoccerElse.contains("> 0.99"))
        XCTAssertTrue(wholeSoccerElse.contains("formatProbability("))

        let kit = try source("Bain Luck/Components/KitCardView366B.swift")
        XCTAssertTrue(kit.contains("formatProbability(scaledPercent / 100.0)"))

        let watchPins = try source("BainLuckWatch Watch App/WatchPinsModels12640.swift")
        XCTAssertFalse(watchPins.contains("0.005"))
        XCTAssertFalse(watchPins.contains("0.995"))

        let watchPub = try source("BainLuckWatch Watch App/WatchComplicationPublisher.swift")
        XCTAssertFalse(watchPub.contains("0.005"))
        XCTAssertFalse(watchPub.contains("0.995"))

        // 2. Category, series, and player-prop views must route whole percents through formatProbability.
        let politics = try source("Bain Luck/Views/PoliticsView.swift")
        XCTAssertFalse(politics.contains("Int(o.prob)"))
        XCTAssertFalse(politics.contains("Int(probs.gop)"))
        XCTAssertFalse(politics.contains("Int(probs.dem)"))
        XCTAssertFalse(politics.contains("Int(c.merged.rounded())"))
        XCTAssertFalse(politics.contains("Int(m.kalshi.rounded())"))
        XCTAssertFalse(politics.contains("Int(m.poly.rounded())"))
        XCTAssertTrue(politics.contains("formatProbability("))

        let economics = try source("Bain Luck/Views/EconomicsView.swift")
        XCTAssertFalse(economics.contains("Text(\"\\(Int(prob))%\")"))
        XCTAssertTrue(economics.contains("formatProbability(prob / 100.0)"))

        let entertainment = try source("Bain Luck/Views/EntertainmentView.swift")
        XCTAssertFalse(entertainment.contains("YES \\(Int(yes))%"))
        XCTAssertFalse(entertainment.contains("NO \\(Int(no))%"))
        XCTAssertTrue(entertainment.contains("formatProbability(yes / 100.0)"))
        XCTAssertTrue(entertainment.contains("formatProbability(no / 100.0)"))

        let leagueGrid = try source("Bain Luck/Views/LeagueGridView.swift")
        XCTAssertFalse(leagueGrid.contains("Int(o.prob)"))
        XCTAssertTrue(leagueGrid.contains("formatProbability(o.prob / 100.0)"))

        let sportCategory = try source("Bain Luck/Views/SportCategoryView.swift")
        XCTAssertFalse(sportCategory.contains("Int(o.prob)"))
        XCTAssertTrue(sportCategory.contains("formatProbability(o.prob / 100.0)"))
        XCTAssertTrue(sportCategory.contains("formatProbability(prob, renderedPercent: p)"))

        let series = try source("Bain Luck/Components/SeriesProbabilityView.swift")
        XCTAssertTrue(series.contains("home: formatProbability(homeSeriesProb)"))
        XCTAssertTrue(series.contains("away: formatProbability(1.0 - homeSeriesProb)"))

        let props = try source("Bain Luck/Components/PlayerPropsCardView.swift")
        XCTAssertTrue(props.contains("formatProbability("))
        XCTAssertFalse(props.contains("Text(\"\\(PlayerPropsPricing.displayPercent("))
    }
}
