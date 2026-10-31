import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the half-by-half card as a stateless presentation leaf across
/// pregame, live and final.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: the exact period/series/prop identities, which reading
/// each phase shows, which chances are plotted and joined, the exact-id
/// selection, the action each control carries, the spoken text and the plot
/// geometry's arithmetic. Nothing here claims a rendered fit.
///
/// ARCHIVED raw values come from Real Valladolid CF – Albacete Balompié, event
/// 15325054, as copied in `shipping-adoption-20261027/SOCCER-HALF-RETAINED-
/// CASES.json` (sources `SoccerHalfResultsCard.tsx` 91f1dc5e…, `soccerHalfResults.ts`
/// 3ed1b0de…, `soccer-final-payoff-v299/raw-final/game-markets.json` d9144e5b…):
///   First half, market 63178219, pregame pin 2026-10-12T11:47:12.564691Z
///     other:63178219:242338171  Real Valladolid CF  0.375  final won
///     other:63178219:242338170  Draw                0.425  final lost
///     other:63178219:242338172  Albacete Balompié   0.205  final lost
///   Second half, market 63178218, pregame pin 2026-10-12T11:47:12.547560Z
///     other:63178218:246041831  Real Valladolid CF  0.43   final won
///     other:63178218:245875499  Draw                0.38   final lost
///     other:63178218:245681743  Albacete Balompié   0.23   final lost
/// Every live current chance is null and every live result unconfirmed. Final
/// results are each market's own `api_settlement` rows; their quote times are
/// not half-end or settlement-arrival times, and their settlement prices
/// (0.999 / 0.0005 / 0.9995 …) are never an input here.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// opaque period and series identities, the short series labels, colours and
/// shapes, every display figure and spoken clock line, the words, headline and
/// captions, the 0–50% axis and its tick labels, every current reading and
/// every admitted-during-play, stale, missing, zero, out-of-scale, duplicate,
/// foreign, three-period and long-text case. Plot extents are CONSTRUCTED text
/// sizes and the geometry tests are arithmetic only — not a measured fit.
final class PeriodOutcomeComparisonPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static let firstID = "period:63178219"
    private static let secondID = "period:63178218"
    private static let first = PeriodOutcomePeriod10868(id: firstID, label: "First half")
    private static let second = PeriodOutcomePeriod10868(id: secondID, label: "Second half")
    private static let halves = [first, second]

    private static let homeID = "outcome:home"
    private static let drawID = "outcome:draw"
    private static let awayID = "outcome:away"

    // ARCHIVED keys.
    private static let homeFirst = "other:63178219:242338171"
    private static let drawFirst = "other:63178219:242338170"
    private static let awayFirst = "other:63178219:242338172"
    private static let homeSecond = "other:63178218:246041831"
    private static let drawSecond = "other:63178218:245875499"
    private static let awaySecond = "other:63178218:245681743"

    // ARCHIVED pins, CONSTRUCTED wording.
    private static let firstPin = "pinned Oct 12, 2026, 11:47:12.564691 UTC · Polymarket"
    private static let secondPin = "pinned Oct 12, 2026, 11:47:12.547560 UTC · Polymarket"

    private struct Archived {
        let key: String
        let periodID: String
        let series: Int
        let value: Double
        let text: String
        let pin: String
        let won: Bool
    }

    /// The six originals: ARCHIVED key, period, value, pin and final result;
    /// CONSTRUCTED display figure.
    private static let archived: [Archived] = [
        Archived(key: homeFirst, periodID: firstID, series: 0, value: 0.375, text: "37.5%", pin: firstPin, won: true),
        Archived(key: homeSecond, periodID: secondID, series: 0, value: 0.43, text: "43%", pin: secondPin, won: true),
        Archived(key: drawFirst, periodID: firstID, series: 1, value: 0.425, text: "42.5%", pin: firstPin, won: false),
        Archived(key: drawSecond, periodID: secondID, series: 1, value: 0.38, text: "38%", pin: secondPin, won: false),
        Archived(key: awayFirst, periodID: firstID, series: 2, value: 0.205, text: "20.5%", pin: firstPin, won: false),
        Archived(key: awaySecond, periodID: secondID, series: 2, value: 0.23, text: "23%", pin: secondPin, won: false),
    ]

    private static let seriesIDs = [homeID, drawID, awayID]
    private static let seriesLabels = ["Valladolid", "Draw", "Albacete"]
    private static let seriesTints: [Color] = [.blue, .gray, .orange]
    private static let seriesSymbols: [PeriodOutcomeSymbol10868] = [.circle, .diamond, .square]

    /// The retained live state: no admitted current chance (CONSTRUCTED words).
    private static let liveUnavailable = PeriodOutcomeCurrent10868.unavailable("Current chance unavailable")
    private static let unconfirmed = PeriodOutcomeResult10868.unconfirmed("Unconfirmed")
    private static let won = PeriodOutcomeResult10868.won("Won")
    private static let lost = PeriodOutcomeResult10868.lost("Lost")

    /// ARCHIVED final results, CONSTRUCTED words.
    private static var finalResults: [String: PeriodOutcomeResult10868] {
        Dictionary(uniqueKeysWithValues: archived.map { ($0.key, $0.won ? won : lost) })
    }

    private static func obs(_ probability: Double, _ text: String, _ detail: String) -> PeriodOutcomeObservation10868 {
        PeriodOutcomeObservation10868(probability: probability, text: text, accessibilityDetail: detail)
    }

    private static func original(
        _ key: String,
        _ periodID: String,
        _ pregame: PeriodOutcomeObservation10868?,
        current: PeriodOutcomeCurrent10868 = liveUnavailable,
        result: PeriodOutcomeResult10868 = unconfirmed
    ) -> PeriodOutcomeCell10868 {
        PeriodOutcomeCell10868(
            id: key,
            periodID: periodID,
            pregame: pregame,
            pregameMissing: "No pre-match chance",
            current: current,
            result: result
        )
    }

    /// The three series built from the six originals, with per-key overrides.
    private static func retained(
        pregame: [String: PeriodOutcomeObservation10868?] = [:],
        current: [String: PeriodOutcomeCurrent10868] = [:],
        result: [String: PeriodOutcomeResult10868] = [:]
    ) -> [PeriodOutcomeSeries10868] {
        (0..<3).map { index in
            let cells = archived.filter { $0.series == index }.map { a in
                original(
                    a.key,
                    a.periodID,
                    pregame[a.key] ?? obs(a.value, a.text, a.pin),
                    current: current[a.key] ?? liveUnavailable,
                    result: result[a.key] ?? unconfirmed
                )
            }
            return PeriodOutcomeSeries10868(
                id: seriesIDs[index],
                label: seriesLabels[index],
                tint: seriesTints[index],
                symbol: seriesSymbols[index],
                cells: cells
            )
        }
    }

    /// CONSTRUCTED 0–50% scale, the prototype's ceiling for these values.
    private static let fiftyPercent = PeriodOutcomeAxis10868(
        lower: 0,
        upper: 0.5,
        ticks: [
            PeriodOutcomeTick10868(value: 0, text: "0%"),
            PeriodOutcomeTick10868(value: 0.25, text: "25%"),
            PeriodOutcomeTick10868(value: 0.5, text: "50%"),
        ]
    )

    /// CONSTRUCTED words.
    private static let words = PeriodOutcomeWords10868(
        pregameTitle: "Pre-match chance",
        notStarted: "Not started",
        currentTitle: "Current chance",
        liveResultTitle: "Half result",
        finalResultTitle: "Final result",
        selectionUnavailable: "Selected outcome unavailable.",
        cellUnavailable: "Not offered for this half",
        selectHint: "Shows this outcome’s chances",
        detailsHint: "Opens the original prop"
    )

    private static func input(
        _ phase: PeriodOutcomePhase10868,
        _ series: [PeriodOutcomeSeries10868],
        selected: String? = homeID,
        periods: [PeriodOutcomePeriod10868] = halves,
        axis: PeriodOutcomeAxis10868 = fiftyPercent
    ) -> PeriodOutcomeComparisonInput10868 {
        PeriodOutcomeComparisonInput10868(
            phase: phase,
            eyebrow: "Half-by-half expectations",
            title: "Two halves. Two sets of expectations.",
            intro: "A draw had the highest pre-match chance for the first half.",
            periods: periods,
            series: series,
            selectedSeriesID: selected,
            plotTitle: "Pre-match chances",
            scaleCaption: "0–50% scale",
            axis: axis,
            pointExplanation: "Each dot is a pre-match chance for that half.",
            lineExplanation: "Lines compare halves, not changes over time.",
            resultsTitle: "Results · match not started",
            words: words
        )
    }

    private static func cell(_ input: PeriodOutcomeComparisonInput10868, _ seriesIndex: Int, _ periodIndex: Int) -> PeriodOutcomeCell10868? {
        input.cell(input.series[seriesIndex], periodIndex: periodIndex).cell
    }

    private static func allSpoken(_ input: PeriodOutcomeComparisonInput10868) -> String {
        ([input.accessibilityPlotValue] + input.series.map { input.accessibilitySummary($0) }).joined(separator: " | ")
    }

    // MARK: Retained originals

    func testTheSixRetainedOriginalsKeepTheirExactIdentitiesChancesAndOwnPins() {
        let input = Self.input(.before, Self.retained())

        XCTAssertEqual(input.series.map(\.id), Self.seriesIDs)
        XCTAssertEqual(input.series.map(\.label), Self.seriesLabels)
        XCTAssertEqual(input.periods.map(\.id), [Self.firstID, Self.secondID])
        XCTAssertNotEqual(Self.firstPin, Self.secondPin)
        for a in Self.archived {
            let periodIndex = a.periodID == Self.firstID ? 0 : 1
            guard let cell = Self.cell(input, a.series, periodIndex) else {
                XCTFail("missing \(a.key)")
                continue
            }
            XCTAssertEqual(cell.id, a.key)
            XCTAssertEqual(cell.periodID, a.periodID)
            XCTAssertEqual(cell.pregame?.probability, a.value)
            XCTAssertEqual(cell.pregame?.text, a.text)
            // Each half keeps its own pin; neither borrows the other's clock.
            XCTAssertEqual(cell.pregame?.accessibilityDetail, a.pin)
            XCTAssertTrue(input.accessibilityValue(cell).contains(a.pin))
            let point = input.plotPoints(for: input.series[a.series]).first { $0.periodIndex == periodIndex }
            XCTAssertEqual(point?.fraction ?? -1, a.value / 0.5, accuracy: 1e-12)
        }
        XCTAssertEqual(input.series.flatMap(\.cells).map(\.id).sorted(), Self.archived.map(\.key).sorted())
    }

    func testIndependentChancesAreShownUnnormalizedIncludingTheSecondHalfsHundredAndFourPercent() {
        let input = Self.input(.before, Self.retained())
        let firstSum = (0..<3).compactMap { Self.cell(input, $0, 0)?.pregame?.probability }.reduce(0, +)
        let secondSum = (0..<3).compactMap { Self.cell(input, $0, 1)?.pregame?.probability }.reduce(0, +)

        XCTAssertEqual(firstSum, 1.005, accuracy: 1e-9)
        XCTAssertEqual(secondSum, 1.04, accuracy: 1e-9)
        XCTAssertEqual((0..<3).compactMap { Self.cell(input, $0, 0)?.pregame?.text }, ["37.5%", "42.5%", "20.5%"])
        XCTAssertEqual((0..<3).compactMap { Self.cell(input, $0, 1)?.pregame?.text }, ["43%", "38%", "23%"])
        // Plotted positions are the raw values on the owner's scale — no
        // complement, no rescaling to 100%.
        let fractions = input.series.map { input.plotPoints(for: $0).map(\.fraction) }
        let expected: [[Double]] = [[0.75, 0.86], [0.85, 0.76], [0.41, 0.46]]
        for (got, want) in zip(fractions, expected) {
            XCTAssertEqual(got.count, 2)
            for (g, w) in zip(got, want) { XCTAssertEqual(g, w, accuracy: 1e-12) }
        }
    }

    func testDrawIsAFirstClassOutcome() {
        let input = Self.input(.final, Self.retained(result: Self.finalResults), selected: Self.drawID)
        let draw = input.series[1]

        XCTAssertEqual(input.selection, .selected(draw))
        XCTAssertEqual(input.annotations.map(\.text), ["42.5%", "38%"])
        XCTAssertEqual(input.segments(for: draw).count, 1)
        XCTAssertEqual(input.selectAction(draw, canSelect: true), .select(Self.drawID))
        XCTAssertEqual(input.emphasis(for: draw), .selected)
        XCTAssertEqual(input.drawOrder.last?.id, Self.drawID)
        XCTAssertEqual(Self.cell(input, 1, 0).flatMap { input.detailsAction($0, canOpenDetails: true) }, .details(Self.drawFirst))
        XCTAssertEqual(Self.cell(input, 1, 1).flatMap { input.detailsAction($0, canOpenDetails: true) }, .details(Self.drawSecond))
        XCTAssertEqual(
            input.accessibilitySummary(draw),
            "First half: Pre-match chance: 42.5%, \(Self.firstPin); Final result: Lost. "
                + "Second half: Pre-match chance: 38%, \(Self.secondPin); Final result: Lost"
        )
    }

    // MARK: Phases

    func testBeforeShowsEveryPregameChanceAsNotStartedAndHidesLaterReadings() {
        // CONSTRUCTED later readings the owner passed early.
        let recorded = PeriodOutcomeCurrent10868.recorded(Self.obs(0.91, "91%", "recorded Oct 12, 5:40 AM PT · Polymarket"))
        let series = Self.retained(
            current: Dictionary(uniqueKeysWithValues: Self.archived.map { ($0.key, recorded) }),
            result: Self.finalResults
        )
        let input = Self.input(.before, series)

        for one in input.series {
            for index in input.periods.indices {
                guard let cell = input.cell(one, periodIndex: index).cell else { return XCTFail("missing cell") }
                XCTAssertEqual(input.secondReading(cell), .notStarted("Not started"))
            }
        }
        let spoken = Self.allSpoken(input)
        for hidden in ["91%", "Won", "Lost", "Current chance", "Half result", "Final result"] {
            XCTAssertFalse(spoken.contains(hidden), hidden)
        }
        XCTAssertEqual(input.annotations.map(\.text), ["37.5%", "43%"])
    }

    func testDuringTheRetainedSnapshotShowsUnavailableAndRevivesNoRawQuote() {
        let input = Self.input(.during, Self.retained())

        for one in input.series {
            for index in input.periods.indices {
                guard let cell = input.cell(one, periodIndex: index).cell else { return XCTFail("missing cell") }
                XCTAssertEqual(input.secondReading(cell), .current(.missing("Current chance unavailable")))
            }
        }
        XCTAssertEqual(
            input.accessibilitySummary(input.series[0]),
            "First half: Pre-match chance: 37.5%, \(Self.firstPin); Current chance: Current chance unavailable. "
                + "Second half: Pre-match chance: 43%, \(Self.secondPin); Current chance: Current chance unavailable"
        )
        let spoken = Self.allSpoken(input)
        for raw in ["99.9", "99.95", "0.05", "0.0005", "100%", "Won", "Lost"] {
            XCTAssertFalse(spoken.contains(raw), raw)
        }
        // The chart stays the pregame comparison.
        XCTAssertEqual(input.annotations.map(\.text), ["37.5%", "43%"])
    }

    func testDuringEachPeriodKeepsItsOwnStateAndNeverBorrowsFromTheOther() {
        // CONSTRUCTED during-play readings; none is in the retained snapshot.
        let series = Self.retained(
            current: [
                Self.homeFirst: .recorded(Self.obs(0.99, "99%", "recorded Oct 12, 5:44 AM PT · Polymarket")),
                Self.homeSecond: .recorded(Self.obs(0.55, "55%", "recorded Oct 12, 5:20 AM PT · Polymarket")),
                Self.drawFirst: .stale("No update since 5:12 AM"),
            ],
            result: [Self.homeFirst: Self.won]
        )
        let input = Self.input(.during, series)

        // An admitted first-half result replaces that half's price.
        XCTAssertEqual(Self.cell(input, 0, 0).map { input.secondReading($0) }, .result(Self.won))
        XCTAssertEqual(
            Self.cell(input, 0, 1).map { input.secondReading($0) },
            .current(.value(Self.obs(0.55, "55%", "recorded Oct 12, 5:20 AM PT · Polymarket")))
        )
        XCTAssertEqual(Self.cell(input, 1, 0).map { input.secondReading($0) }, .current(.missing("No update since 5:12 AM")))
        XCTAssertEqual(Self.cell(input, 1, 1).map { input.secondReading($0) }, .current(.missing("Current chance unavailable")))

        let firstSpoken = Self.cell(input, 0, 0).map { input.accessibilityValue($0) } ?? ""
        let secondSpoken = Self.cell(input, 0, 1).map { input.accessibilityValue($0) } ?? ""
        XCTAssertEqual(firstSpoken, "Pre-match chance: 37.5%, \(Self.firstPin); Half result: Won")
        XCTAssertEqual(secondSpoken, "Pre-match chance: 43%, \(Self.secondPin); Current chance: 55%, recorded Oct 12, 5:20 AM PT · Polymarket")
        XCTAssertFalse(firstSpoken.contains("99%"))
        XCTAssertFalse(secondSpoken.contains("Won"))
        XCTAssertEqual(input.annotations.map(\.text), ["37.5%", "43%"])
    }

    func testFinalPairsEachHalfsOriginalChanceWithItsOwnRecordedResult() {
        // A CONSTRUCTED settlement-like current is supplied and must not be read.
        let settled = PeriodOutcomeCurrent10868.recorded(Self.obs(0.9995, "99.95%", "recorded Oct 12, 5:32 AM PT · Polymarket"))
        let series = Self.retained(
            current: Dictionary(uniqueKeysWithValues: Self.archived.map { ($0.key, settled) }),
            result: Self.finalResults
        )
        let input = Self.input(.final, series)

        XCTAssertEqual(input.resultTitle, "Final result")
        for a in Self.archived {
            let cell = Self.cell(input, a.series, a.periodID == Self.firstID ? 0 : 1)
            XCTAssertEqual(cell.map { input.secondReading($0) }, .result(a.won ? Self.won : Self.lost))
            XCTAssertEqual(
                cell.map { input.accessibilityValue($0) },
                "Pre-match chance: \(a.text), \(a.pin); Final result: \(a.won ? "Won" : "Lost")"
            )
        }
        let spoken = Self.allSpoken(input)
        XCTAssertFalse(spoken.contains("99.95%"))
        XCTAssertFalse(spoken.contains("Current chance"))
    }

    func testAnUnknownFinalResultIsNotALoss() {
        var results = Self.finalResults
        results[Self.drawSecond] = Self.unconfirmed
        let input = Self.input(.final, Self.retained(result: results), selected: Self.drawID)
        guard let cell = Self.cell(input, 1, 1) else { return XCTFail("missing cell") }

        XCTAssertEqual(input.secondReading(cell), .result(Self.unconfirmed))
        XCTAssertNil(Self.unconfirmed.mark)
        XCTAssertFalse(Self.unconfirmed.isAdmitted)
        XCTAssertEqual(input.accessibilityValue(cell), "Pre-match chance: 38%, \(Self.secondPin); Final result: Unconfirmed")
        XCTAssertFalse(input.accessibilityValue(cell).contains("Lost"))
        // The other half keeps its own recorded result.
        XCTAssertEqual(Self.cell(input, 1, 0).map { input.secondReading($0) }, .result(Self.lost))
    }

    func testOnlyTheFinalSpeaksTheFinalResultTitle() {
        let results = [Self.homeFirst: Self.won]
        let during = Self.input(.during, Self.retained(result: results))
        let final = Self.input(.final, Self.retained(result: results))
        let before = Self.input(.before, Self.retained(result: results))

        XCTAssertEqual(Self.cell(during, 0, 0).map { during.accessibilityValue($0) }, "Pre-match chance: 37.5%, \(Self.firstPin); Half result: Won")
        XCTAssertEqual(Self.cell(final, 0, 0).map { final.accessibilityValue($0) }, "Pre-match chance: 37.5%, \(Self.firstPin); Final result: Won")
        XCTAssertEqual(Self.cell(before, 0, 0).map { before.accessibilityValue($0) }, "Pre-match chance: 37.5%, \(Self.firstPin); Not started")
        XCTAssertEqual(during.resultTitle, "Half result")
        XCTAssertEqual(final.resultTitle, "Final result")
    }

    func testResultMarksNeverDrawUnknownAsALoss() {
        XCTAssertEqual(Self.won.mark, .positive)
        XCTAssertEqual(Self.lost.mark, .negative)
        XCTAssertNil(Self.unconfirmed.mark)
        XCTAssertEqual([Self.won, Self.lost, Self.unconfirmed].map(\.text), ["Won", "Lost", "Unconfirmed"])
        XCTAssertEqual([Self.won, Self.lost, Self.unconfirmed].map(\.isAdmitted), [true, true, false])
    }

    // MARK: Plotted chances

    func testAMissingPregameChanceKeepsTheOtherPointItsOwnWordsAndNoLine() {
        let input = Self.input(.before, Self.retained(pregame: [Self.homeFirst: nil]))
        let home = input.series[0]

        XCTAssertEqual(input.plotPoints(for: home).map(\.periodIndex), [1])
        XCTAssertEqual(input.plotPoints(for: home).first?.fraction ?? -1, 0.86, accuracy: 1e-12)
        XCTAssertEqual(input.segments(for: home), [])
        XCTAssertEqual(Self.cell(input, 0, 0).map { input.pregameReading($0) }, .missing("No pre-match chance"))
        XCTAssertEqual(Self.cell(input, 0, 0).map { input.accessibilityValue($0) }, "Pre-match chance: No pre-match chance; Not started")
        XCTAssertEqual(input.annotations.map(\.text), ["43%"])
        // The original stays reachable and the neighbours are untouched.
        XCTAssertEqual(Self.cell(input, 0, 0)?.id, Self.homeFirst)
        XCTAssertEqual(input.plotPoints(for: input.series[1]).count, 2)
        XCTAssertEqual(input.segments(for: input.series[2]).count, 1)
    }

    func testAZeroChanceIsARealPointAndConnects() {
        let input = Self.input(.before, Self.retained(pregame: [Self.awayFirst: Self.obs(0, "0%", Self.firstPin)]), selected: Self.awayID)
        let away = input.series[2]

        XCTAssertEqual(input.plotPoints(for: away).first, PeriodOutcomePlotPoint10868(periodIndex: 0, fraction: 0))
        XCTAssertEqual(input.segments(for: away).count, 1)
        XCTAssertEqual(input.annotations.map(\.text), ["0%", "23%"])
        XCTAssertEqual(Self.cell(input, 2, 0).map { input.pregameReading($0) }, .value(Self.obs(0, "0%", Self.firstPin)))
    }

    func testAnOutOfScaleOrNonFiniteChanceIsNeitherPlottedNorClamped() {
        for value in [0.6, -0.01, Double.nan, Double.infinity] {
            let bad = Self.obs(value, "60%", Self.firstPin)
            let input = Self.input(.before, Self.retained(pregame: [Self.homeFirst: bad]))
            let home = input.series[0]

            XCTAssertEqual(input.plotPoints(for: home).map(\.periodIndex), [1], "\(value)")
            XCTAssertEqual(input.segments(for: home), [], "\(value)")
            XCTAssertEqual(input.annotations.map(\.text), ["43%"], "\(value)")
            // The owner's figure is still the tile's text.
            XCTAssertEqual(Self.cell(input, 0, 0)?.pregame?.text, "60%")
        }
        let atBound = Self.input(.before, Self.retained(pregame: [Self.homeFirst: Self.obs(0.5, "50%", Self.firstPin)]))
        XCTAssertEqual(atBound.plotPoints(for: atBound.series[0]).first?.fraction, 1)
    }

    func testAnAxisThatIsNotAProbabilityScalePlacesNothing() {
        let ticks = Self.fiftyPercent.ticks
        for axis in [
            PeriodOutcomeAxis10868(lower: 0.5, upper: 0.5, ticks: ticks),
            PeriodOutcomeAxis10868(lower: 0, upper: 1.5, ticks: ticks),
            PeriodOutcomeAxis10868(lower: -0.5, upper: 0.5, ticks: ticks),
            PeriodOutcomeAxis10868(lower: 0, upper: .nan, ticks: ticks),
        ] {
            let input = Self.input(.before, Self.retained(), axis: axis)
            XCTAssertFalse(axis.isValid)
            XCTAssertEqual(PeriodOutcomeGeometry10868.visibleTicks(axis), [])
            XCTAssertTrue(input.series.allSatisfy { input.plotPoints(for: $0).isEmpty })
            XCTAssertEqual(input.annotations, [])
            XCTAssertEqual(Self.cell(input, 0, 0)?.pregame?.text, "37.5%")
        }
    }

    func testDuplicateTickValuesAreLabelledOnceAndOffScaleTicksNotAtAll() {
        let axis = PeriodOutcomeAxis10868(lower: 0, upper: 0.5, ticks: [
            PeriodOutcomeTick10868(value: 0, text: "0%"),
            PeriodOutcomeTick10868(value: 0.25, text: "25%"),
            PeriodOutcomeTick10868(value: 0.25, text: "25 percent"),
            PeriodOutcomeTick10868(value: 0.5, text: "50%"),
            PeriodOutcomeTick10868(value: 0.75, text: "75%"),
        ])
        let ticks = PeriodOutcomeGeometry10868.visibleTicks(axis)
        XCTAssertEqual(ticks.map(\.fraction), [0, 0.5, 1])
        XCTAssertEqual(ticks.map(\.text), ["0%", "25%", "50%"])
    }

    func testAGapInALongerSeriesBreaksTheLineAndAnAbsentPeriodIsNamed() {
        // CONSTRUCTED three-scope geometry check; it claims no new sport.
        let periods = [
            PeriodOutcomePeriod10868(id: "p1", label: "Scope 1"),
            PeriodOutcomePeriod10868(id: "p2", label: "Scope 2"),
            PeriodOutcomePeriod10868(id: "p3", label: "Scope 3"),
        ]
        func seriesOf(_ id: String, _ cells: [PeriodOutcomeCell10868]) -> PeriodOutcomeSeries10868 {
            PeriodOutcomeSeries10868(id: id, label: id, tint: .gray, symbol: .triangle, cells: cells)
        }
        let gap = seriesOf("gap", [
            Self.original("g1", "p1", Self.obs(0.2, "20%", "a")),
            Self.original("g2", "p2", nil),
            Self.original("g3", "p3", Self.obs(0.3, "30%", "c")),
        ])
        let absent = seriesOf("absent", [
            Self.original("a1", "p1", Self.obs(0.2, "20%", "a")),
            Self.original("a3", "p3", Self.obs(0.3, "30%", "c")),
        ])
        let whole = seriesOf("whole", [
            Self.original("w1", "p1", Self.obs(0.2, "20%", "a")),
            Self.original("w2", "p2", Self.obs(0.25, "25%", "b")),
            Self.original("w3", "p3", Self.obs(0.3, "30%", "c")),
        ])
        let input = Self.input(.before, [gap, absent, whole], selected: "gap", periods: periods)

        XCTAssertEqual(input.plotPoints(for: gap).map(\.periodIndex), [0, 2])
        XCTAssertEqual(input.segments(for: gap), [])
        XCTAssertEqual(input.cell(absent, periodIndex: 1), .absent)
        XCTAssertEqual(input.segments(for: absent), [])
        XCTAssertTrue(input.accessibilitySummary(absent).contains("Scope 2: Not offered for this half"))
        XCTAssertEqual(input.segments(for: whole).map { [$0.from.periodIndex, $0.to.periodIndex] }, [[0, 1], [1, 2]])
        XCTAssertEqual((0..<3).map { PeriodOutcomeGeometry10868.normalizedX($0, count: 3) }, [0, 0.5, 1])
        XCTAssertEqual(input.annotations.map(\.periodIndex), [0, 2])
    }

    // MARK: Selection and identity

    func testSelectionIsExactAndAMissingOrDuplicatedSeriesPicksNobody() {
        let series = Self.retained()

        let missing = Self.input(.before, series, selected: "outcome:nobody")
        XCTAssertEqual(missing.selection, .missing("outcome:nobody"))
        XCTAssertEqual(missing.selectionNotice, "Selected outcome unavailable.")
        XCTAssertEqual(missing.annotations, [])
        XCTAssertTrue(series.allSatisfy { missing.emphasis(for: $0) == .plain && !missing.isSelected($0) })

        let twin = PeriodOutcomeSeries10868(id: Self.homeID, label: "Valladolid (copy)", tint: .blue, symbol: .circle, cells: [])
        let duplicate = Self.input(.before, series + [twin], selected: Self.homeID)
        XCTAssertEqual(duplicate.selection, .duplicate(Self.homeID))
        XCTAssertEqual(duplicate.selectionNotice, "Selected outcome unavailable.")
        XCTAssertNil(duplicate.selection.series)
        XCTAssertEqual(duplicate.annotations, [])

        let none = Self.input(.before, series, selected: nil)
        XCTAssertEqual(none.selection, .none)
        XCTAssertNil(none.selectionNotice)
        XCTAssertEqual(none.accessibilityPlotValue.components(separatedBy: "Pre-match chance:").count - 1, 6)

        let draw = Self.input(.before, series, selected: Self.drawID)
        XCTAssertEqual(series.map { draw.emphasis(for: $0) }, [.muted, .selected, .muted])
        XCTAssertEqual(draw.drawOrder.map(\.id), [Self.homeID, Self.awayID, Self.drawID])
    }

    func testADuplicatedSeriesIdentityOffersNoSelectAction() {
        let twin = PeriodOutcomeSeries10868(id: Self.homeID, label: "Valladolid (copy)", tint: .blue, symbol: .circle, cells: [])
        let input = Self.input(.before, Self.retained() + [twin], selected: nil)

        XCTAssertNil(input.selectAction(input.series[0], canSelect: true))
        XCTAssertNil(input.selectAction(twin, canSelect: true))
        XCTAssertEqual(input.selectAction(input.series[1], canSelect: true), .select(Self.drawID))
        XCTAssertEqual(input.selectAction(input.series[2], canSelect: true), .select(Self.awayID))
    }

    func testADuplicatedPropIdentityOffersNoDetailsAction() {
        // CONSTRUCTED: the Draw second-half original carries Valladolid's id.
        var series = Self.retained()
        let drawCells = series[1].cells.map { cell in
            cell.periodID == Self.secondID
                ? Self.original(Self.homeSecond, cell.periodID, cell.pregame)
                : cell
        }
        series[1] = PeriodOutcomeSeries10868(id: Self.drawID, label: "Draw", tint: .gray, symbol: .diamond, cells: drawCells)
        let input = Self.input(.before, series)

        XCTAssertFalse(input.isUniqueProp(Self.homeSecond))
        XCTAssertNil(Self.cell(input, 0, 1).flatMap { input.detailsAction($0, canOpenDetails: true) })
        XCTAssertNil(Self.cell(input, 1, 1).flatMap { input.detailsAction($0, canOpenDetails: true) })
        XCTAssertEqual(Self.cell(input, 0, 0).flatMap { input.detailsAction($0, canOpenDetails: true) }, .details(Self.homeFirst))
    }

    func testTwoOriginalsForOnePeriodAreAmbiguousAndDrawNothing() {
        var series = Self.retained()
        let extra = Self.original("other:63178219:duplicate", Self.firstID, Self.obs(0.4, "40%", Self.firstPin))
        series[0] = PeriodOutcomeSeries10868(id: Self.homeID, label: "Valladolid", tint: .blue, symbol: .circle,
                                             cells: series[0].cells + [extra])
        let input = Self.input(.before, series)

        XCTAssertEqual(input.cell(input.series[0], periodIndex: 0), .ambiguous)
        XCTAssertEqual(input.plotPoints(for: input.series[0]).map(\.periodIndex), [1])
        XCTAssertEqual(input.segments(for: input.series[0]), [])
        XCTAssertTrue(input.accessibilitySummary(input.series[0]).hasPrefix("First half: Not offered for this half. "))

        let reused = Self.input(.before, Self.retained(), periods: [Self.first, PeriodOutcomePeriod10868(id: Self.firstID, label: "First half again")])
        XCTAssertEqual(reused.cell(reused.series[0], periodIndex: 0), .ambiguous)
        XCTAssertEqual(reused.cell(reused.series[0], periodIndex: 1), .ambiguous)
        XCTAssertEqual(reused.annotations, [])
    }

    func testACellForAPeriodNotOnTheCardIsNeverBorrowed() {
        var series = Self.retained()
        let foreign = Self.original("other:extra-time:1", "period:extra-time", Self.obs(0.45, "45%", "pinned elsewhere"))
        series[0] = PeriodOutcomeSeries10868(id: Self.homeID, label: "Valladolid", tint: .blue, symbol: .circle,
                                             cells: [foreign] + series[0].cells)
        let input = Self.input(.before, series)

        XCTAssertEqual(input.annotations.map(\.text), ["37.5%", "43%"])
        XCTAssertFalse(Self.allSpoken(input).contains("45%"))
        XCTAssertEqual(Self.cell(input, 0, 0)?.id, Self.homeFirst)
    }

    func testEveryOriginalIsReachableAndCarriesItsExactIdentity() {
        let input = Self.input(.final, Self.retained(result: Self.finalResults))
        var selected: [String] = []
        var details: [String] = []

        for one in input.series {
            input.selectAction(one, canSelect: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
            for index in input.periods.indices {
                guard let cell = input.cell(one, periodIndex: index).cell else { return XCTFail("missing cell") }
                input.detailsAction(cell, canOpenDetails: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
            }
        }
        XCTAssertEqual(selected, Self.seriesIDs)
        XCTAssertEqual(details, Self.archived.map(\.key))
    }

    func testWithoutCallbacksNoControlOffersAnAction() {
        let input = Self.input(.final, Self.retained(result: Self.finalResults))

        for one in input.series {
            XCTAssertNil(input.selectAction(one, canSelect: false))
            for cell in one.cells {
                XCTAssertNil(input.detailsAction(cell, canOpenDetails: false))
            }
        }
        // A present action with no closure does nothing.
        PeriodOutcomeAction10868.select(Self.homeID).perform(onSelect: nil, onDetails: nil)
        PeriodOutcomeAction10868.details(Self.homeFirst).perform(onSelect: nil, onDetails: nil)
    }

    // MARK: Spoken and shown text

    func testSpokenTextNamesOutcomePeriodChanceClockAndState() {
        let input = Self.input(.before, Self.retained())

        XCTAssertEqual(input.accessibilityHeader, "Half-by-half expectations. Two halves. Two sets of expectations.")
        XCTAssertEqual(input.accessibilityLabel(input.series[0], period: Self.first), "First half, Valladolid")
        XCTAssertEqual(
            input.accessibilityPlotLabel,
            "Pre-match chances. 0–50% scale. Each dot is a pre-match chance for that half. Lines compare halves, not changes over time."
        )
        XCTAssertEqual(
            input.accessibilityPlotValue,
            "Valladolid. First half: Pre-match chance: 37.5%, \(Self.firstPin); Not started. "
                + "Second half: Pre-match chance: 43%, \(Self.secondPin); Not started"
        )
        let none = Self.input(.before, Self.retained(), selected: nil)
        let order = ["Valladolid.", "Draw.", "Albacete."].compactMap { none.accessibilityPlotValue.range(of: $0)?.lowerBound }
        XCTAssertEqual(order.count, 3)
        XCTAssertEqual(order, order.sorted())
    }

    func testOwnerStringsLongNamesAndFiguresAreVerbatim() {
        let long = "Real Valladolid Club de Fútbol, Sociedad Anónima Deportiva"
        let longPeriod = PeriodOutcomePeriod10868(id: Self.firstID, label: "First half including stoppage time")
        var series = Self.retained(pregame: [Self.homeSecond: Self.obs(0.004, "<1%", Self.secondPin)])
        series[0] = PeriodOutcomeSeries10868(id: Self.homeID, label: long, tint: .blue, symbol: .circle, cells: series[0].cells)
        let input = Self.input(.before, series, periods: [longPeriod, Self.second])

        XCTAssertEqual(input.annotations.map(\.text), ["37.5%", "<1%"])
        XCTAssertEqual(input.accessibilityLabel(input.series[0], period: longPeriod), "First half including stoppage time, \(long)")
        XCTAssertTrue(input.accessibilityPlotValue.hasPrefix("\(long). First half including stoppage time: "))
        XCTAssertEqual(Self.cell(input, 0, 1)?.pregame?.text, "<1%")
    }

    func testAccessibilityIdentifiersCarryExactIdentities() {
        XCTAssertEqual(PeriodOutcomeAccessibilityID10868.series(Self.homeID), "periodOutcome10868.series.outcome:home")
        XCTAssertEqual(PeriodOutcomeAccessibilityID10868.tile(Self.homeFirst), "periodOutcome10868.tile.other:63178219:242338171")
        XCTAssertEqual(PeriodOutcomeAccessibilityID10868.plot, "periodOutcome10868.plot")
    }

    func testEmphasisKeepsTheSelectedSeriesStrongAndTheRestReadable() {
        XCTAssertEqual(PeriodOutcomeEmphasis10868.selected.lineWidth, 3)
        XCTAssertEqual(PeriodOutcomeEmphasis10868.muted.lineWidth, 1.5)
        XCTAssertEqual(PeriodOutcomeEmphasis10868.plain.lineWidth, 2)
        XCTAssertEqual(PeriodOutcomeEmphasis10868.selected.opacity, 1)
        XCTAssertEqual(PeriodOutcomeEmphasis10868.muted.opacity, 0.35)
        XCTAssertEqual(PeriodOutcomeEmphasis10868.plain.opacity, 1)
    }

    // MARK: Plot geometry (arithmetic on CONSTRUCTED text sizes — not a rendered fit)

    /// Emulates a label wrapped to `width`: whole lines of the one-line height.
    private static func wrapped(_ natural: CGSize, to width: CGFloat) -> CGSize {
        guard natural.width > width, width > 0 else { return natural }
        return CGSize(width: width, height: natural.height * (natural.width / width).rounded(.up))
    }

    private static func layout(
        width: CGFloat,
        ticks: [(Double, CGSize)],
        periods: [CGSize],
        values: [(Int, Double, CGSize)],
        baseHeight: CGFloat = 170,
        wrap: @escaping (CGSize, CGFloat) -> CGSize = { PeriodOutcomeComparisonPresentation10868Tests.wrapped($0, to: $1) }
    ) -> (PeriodOutcomeColumns10868, PeriodOutcomePlotPlan10868)? {
        guard let columns = PeriodOutcomeGeometry10868.columns(
            width: width,
            tickSizes: ticks.map(\.1),
            periodNatural: periods,
            annotationNatural: values.map(\.2)
        ) else { return nil }
        let fit: (CGSize) -> CGSize = { $0.width > columns.labelWidth ? wrap($0, columns.labelWidth) : $0 }
        guard let plan = PeriodOutcomeGeometry10868.plotPlan(
            columns: columns,
            tickFractions: ticks.map(\.0),
            tickSizes: ticks.map(\.1),
            periodSizes: periods.map(fit),
            annotationIndices: values.map(\.0),
            annotationSizes: values.map { fit($0.2) },
            baseHeight: baseHeight
        ) else { return nil }
        return (columns, plan)
    }

    private static func assertApart(_ frames: [CGRect], file: StaticString = #filePath, line: UInt = #line) {
        for i in frames.indices {
            for j in frames.indices where j > i {
                let a = frames[i], b = frames[j]
                // Strict: labels may touch the gap's edge but share no area.
                let overlaps = a.minX < b.maxX - 1e-9 && b.minX < a.maxX - 1e-9
                    && a.minY < b.maxY - 1e-9 && b.minY < a.maxY - 1e-9
                XCTAssertFalse(overlaps, "\(a) overlaps \(b)", file: file, line: line)
            }
        }
    }

    /// Every label inside its region: ticks in the gutter, value labels in the
    /// band above the plot — clear of the largest mark and the top tick label —
    /// period labels below the lowest tick label.
    private static func assertRegions(
        _ columns: PeriodOutcomeColumns10868, _ plan: PeriodOutcomePlotPlan10868,
        values: [(Int, Double, CGSize)], tickHeight: CGFloat,
        file: StaticString = #filePath, line: UInt = #line
    ) {
        for frame in plan.tickFrames {
            XCTAssertGreaterThanOrEqual(frame.minX, 0, file: file, line: line)
            XCTAssertLessThanOrEqual(frame.maxX, columns.gutter, file: file, line: line)
            XCTAssertGreaterThanOrEqual(frame.minY, 0, file: file, line: line)
        }
        let markRadius = PeriodOutcomeGeometry10868.markRadius
        XCTAssertLessThanOrEqual(plan.annotationBand.maxY + 6, plan.plotRect.minY - max(markRadius, tickHeight / 2),
                                 "the band ends a gap above the marks and the top tick label", file: file, line: line)
        for (frame, value) in zip(plan.annotationFrames, values) {
            XCTAssertGreaterThanOrEqual(frame.minX, columns.gutter, file: file, line: line)
            XCTAssertLessThanOrEqual(frame.maxX, plan.size.width, file: file, line: line)
            XCTAssertGreaterThanOrEqual(frame.minY, 0, file: file, line: line)
            XCTAssertTrue(plan.annotationBand.contains(frame), "\(frame) in the band", file: file, line: line)
            let pointY = plan.plotRect.minY + CGFloat(1 - value.1) * plan.plotRect.height
            XCTAssertLessThanOrEqual(frame.maxY, pointY - markRadius - 6, file: file, line: line)
        }
        for frame in plan.periodFrames {
            XCTAssertGreaterThanOrEqual(frame.minY, plan.plotRect.maxY + tickHeight / 2, file: file, line: line)
            XCTAssertGreaterThanOrEqual(frame.minX, columns.gutter, file: file, line: line)
        }
    }

    func testPlotLabelsAtPhoneWidthsStayWholeCentredAndApart() {
        // CONSTRUCTED one-line sizes at the default type size; content widths
        // for 320 / 375 / 393 pt screens less a CONSTRUCTED 34 pt padding a side.
        let ticks: [(Double, CGSize)] = [(0, CGSize(width: 20, height: 13)), (0.5, CGSize(width: 26, height: 13)), (1, CGSize(width: 26, height: 13))]
        let periods = [CGSize(width: 56, height: 16), CGSize(width: 72, height: 16)]
        let values: [(Int, Double, CGSize)] = [(0, 0.75, CGSize(width: 38, height: 18)), (1, 0.86, CGSize(width: 28, height: 18))]
        for width: CGFloat in [252, 307, 325] {
            guard case let (columns, plan)? = Self.layout(width: width, ticks: ticks, periods: periods, values: values) else {
                return XCTFail("no plan at \(width)")
            }
            XCTAssertEqual(columns.gutter, 32)
            XCTAssertEqual(columns.inset, 39, "half the widest label plus half the gap, not capped")
            XCTAssertEqual(columns.labelWidth, 72)
            XCTAssertEqual(columns.centers, [71, width - 39])
            // Whole and centred on their own period.
            XCTAssertEqual(plan.periodFrames.map(\.size), periods)
            XCTAssertEqual(plan.periodFrames.map(\.midX), columns.centers)
            XCTAssertEqual(plan.annotationFrames.map(\.midX), columns.centers)
            Self.assertApart(plan.periodFrames)
            Self.assertApart(plan.tickFrames)
            Self.assertApart(plan.annotationFrames)
            Self.assertRegions(columns, plan, values: values, tickHeight: 13)
            XCTAssertEqual(plan.size.width, width, "no overflow")
            XCTAssertEqual(plan.plotRect.height, 170)
            XCTAssertEqual(plan.markRect.minX, 71)
            XCTAssertEqual(plan.markRect.width, width - 39 - 71)
            // Neighbouring period labels keep at least the gap between them.
            XCTAssertGreaterThanOrEqual(plan.periodFrames[1].minX - plan.periodFrames[0].maxX, 6)
        }
    }

    func testPlotLabelsAtAccessibilitySizesWrapAndTheBlockGrows() {
        // CONSTRUCTED accessibility-size one-line sizes.
        let ticks: [(Double, CGSize)] = [(0, CGSize(width: 46, height: 30)), (0.5, CGSize(width: 46, height: 30)), (1, CGSize(width: 46, height: 30))]
        let periods = [CGSize(width: 150, height: 30), CGSize(width: 170, height: 30)]
        let values: [(Int, Double, CGSize)] = [(0, 0.75, CGSize(width: 92, height: 34)), (1, 0.86, CGSize(width: 70, height: 34))]
        guard case let (columns, plan)? = Self.layout(width: 252, ticks: ticks, periods: periods, values: values, baseHeight: 300) else {
            return XCTFail("no plan")
        }

        XCTAssertEqual(columns.gutter, 52)
        XCTAssertEqual(columns.inset, 50, "capped at an equal share")
        XCTAssertEqual(columns.labelWidth, 94)
        XCTAssertEqual(plan.periodFrames.map(\.size), [CGSize(width: 94, height: 60), CGSize(width: 94, height: 60)])
        XCTAssertEqual(plan.periodFrames.map(\.minY), [plan.periodFrames[0].minY, plan.periodFrames[0].minY], "one row")
        XCTAssertEqual(plan.annotationFrames.map(\.size), values.map(\.2), "value labels fit whole")
        Self.assertApart(plan.periodFrames)
        Self.assertApart(plan.tickFrames)
        Self.assertApart(plan.annotationFrames)
        Self.assertRegions(columns, plan, values: values, tickHeight: 30)
        XCTAssertEqual(plan.size.width, 252)
        XCTAssertEqual(plan.plotRect.height, 300)
        XCTAssertEqual(plan.size.height, plan.periodFrames[0].minY + 60)
    }

    func testTicksTooCloseForTheirLabelsMakeThePlotTaller() {
        let ticks: [(Double, CGSize)] = [(0, CGSize(width: 30, height: 30)), (0.1, CGSize(width: 30, height: 30)), (1, CGSize(width: 30, height: 30))]
        guard case let (_, plan)? = Self.layout(width: 300, ticks: ticks, periods: [CGSize(width: 60, height: 16)], values: []) else {
            return XCTFail("no plan")
        }

        // (30 + 6 gap) / 0.1 of the scale.
        XCTAssertEqual(plan.plotRect.height, 360, accuracy: 1e-9)
        Self.assertApart(plan.tickFrames)
    }

    func testAnUnbreakableLabelDropsBelowItsNeighbourAndReportsAnyOverflow() {
        let ticks: [(Double, CGSize)] = [(0, CGSize(width: 20, height: 13))]
        let periods = [CGSize(width: 300, height: 16), CGSize(width: 40, height: 16)]
        // CONSTRUCTED: the first label cannot wrap narrower than 180 pt.
        guard case let (columns, plan)? = Self.layout(
            width: 252, ticks: ticks, periods: periods, values: [],
            wrap: { natural, _ in CGSize(width: 180, height: natural.height * 2) }
        ) else { return XCTFail("no plan") }

        XCTAssertEqual(columns.labelWidth, 107)
        XCTAssertEqual(plan.periodFrames[0].size, CGSize(width: 180, height: 32))
        XCTAssertEqual(plan.periodFrames[1].size, periods[1], "the neighbour stays whole")
        XCTAssertEqual(plan.periodFrames[1].midX, columns.centers[1], "and on its own period")
        XCTAssertGreaterThanOrEqual(plan.periodFrames[1].minY, plan.periodFrames[0].maxY, "on a row below")
        Self.assertApart(plan.periodFrames)
        XCTAssertEqual(plan.size.height, plan.periodFrames[1].maxY)
        XCTAssertEqual(plan.size.width, 252)

        // Wider than the whole plot: the plan reports the overflow.
        guard case let (_, wide)? = Self.layout(
            width: 252, ticks: ticks, periods: periods, values: [],
            wrap: { natural, _ in CGSize(width: 400, height: natural.height) }
        ) else { return XCTFail("no plan") }
        XCTAssertEqual(wide.periodFrames[0].minX, 0)
        XCTAssertEqual(wide.size.width, 400)
        Self.assertApart(wide.periodFrames)
    }

    /// Every series' mark squares and line bounding boxes (widened by half the
    /// selected stroke), in plot-block coordinates, through the centre helper
    /// the view draws with.
    private static func markExtents(_ input: PeriodOutcomeComparisonInput10868, _ plan: PeriodOutcomePlotPlan10868) -> [CGRect] {
        let count = input.periods.count
        let radius = PeriodOutcomeGeometry10868.markRadius
        let half = PeriodOutcomeEmphasis10868.selected.lineWidth / 2
        let center = { (point: PeriodOutcomePlotPoint10868) -> CGPoint in
            PeriodOutcomeGeometry10868.center(point, count: count, in: plan.markRect)
        }
        return input.series.flatMap { one -> [CGRect] in
            let marks = input.plotPoints(for: one).map { point -> CGRect in
                let c = center(point)
                return CGRect(x: c.x - radius, y: c.y - radius, width: 2 * radius, height: 2 * radius)
            }
            let lines = input.segments(for: one).map { segment -> CGRect in
                let a = center(segment.from)
                let b = center(segment.to)
                return CGRect(x: min(a.x, b.x), y: min(a.y, b.y), width: abs(a.x - b.x), height: abs(a.y - b.y))
                    .insetBy(dx: -half, dy: -half)
            }
            return marks + lines
        }
    }

    func testValueLabelsClearEveryOutcomesMarksAndLinesAtTheRetainedHomeAndDrawSeparation() {
        // ARCHIVED first-half chances: Valladolid 37.5% and Draw 42.5% sit 0.1
        // apart on the CONSTRUCTED 0–50% scale — 17 pt on a 170 pt plot, so a
        // label set just above Valladolid's point would cover Draw's. CONSTRUCTED
        // label sizes at a compact (375 pt screen) and an accessibility size.
        struct Size {
            let width: CGFloat
            let tick: CGSize
            let periods: [CGSize]
            let charWidth: CGFloat
            let figureHeight: CGFloat
            let baseHeight: CGFloat
        }
        let sizes = [
            Size(width: 307, tick: CGSize(width: 26, height: 13), periods: [CGSize(width: 56, height: 16), CGSize(width: 72, height: 16)],
                 charWidth: 8, figureHeight: 18, baseHeight: 170),
            Size(width: 252, tick: CGSize(width: 46, height: 30), periods: [CGSize(width: 150, height: 30), CGSize(width: 170, height: 30)],
                 charWidth: 18, figureHeight: 34, baseHeight: 300),
        ]
        for size in sizes {
            let ticks = PeriodOutcomeGeometry10868.visibleTicks(Self.fiftyPercent).map { ($0.fraction, size.tick) }
            for selected in Self.seriesIDs {
                let input = Self.input(.before, Self.retained(), selected: selected)
                let values = input.annotations.map {
                    ($0.periodIndex, $0.fraction, CGSize(width: CGFloat($0.text.count) * size.charWidth, height: size.figureHeight))
                }
                guard case let (columns, plan)? = Self.layout(width: size.width, ticks: ticks, periods: size.periods,
                                                               values: values, baseHeight: size.baseHeight) else {
                    return XCTFail("no plan at \(size.width) for \(selected)")
                }
                let home = PeriodOutcomeGeometry10868.center(input.plotPoints(for: input.series[0])[0], count: 2, in: plan.markRect)
                let draw = PeriodOutcomeGeometry10868.center(input.plotPoints(for: input.series[1])[0], count: 2, in: plan.markRect)
                XCTAssertEqual(home.y - draw.y, 0.1 * plan.plotRect.height, accuracy: 1e-9, "the retained separation")
                if size.baseHeight == 170 { XCTAssertEqual(home.y - draw.y, 17, accuracy: 1e-9) }

                XCTAssertEqual(plan.annotationFrames.count, 2)
                XCTAssertEqual(plan.annotationFrames.map(\.midX), columns.centers, "each figure on its own period")
                let extents = Self.markExtents(input, plan)
                XCTAssertEqual(extents.count, 3 * 2 + 3, "six marks and three lines")
                for frame in plan.annotationFrames {
                    for extent in extents {
                        XCTAssertFalse(frame.intersects(extent), "\(selected): \(frame) meets \(extent)")
                    }
                    for tick in plan.tickFrames {
                        XCTAssertFalse(frame.intersects(tick), "\(selected): \(frame) meets tick \(tick)")
                    }
                }
                Self.assertApart(plan.annotationFrames)
                Self.assertRegions(columns, plan, values: values, tickHeight: size.tick.height)
            }
        }
    }

    func testAnUnbreakableWideFigureTakesARowOfItsOwnAndReportsAnyOverflow() {
        // CONSTRUCTED: an owner figure that cannot wrap narrower than 180 pt
        // beside a short one. Short fixture figures are not the input contract.
        let ticks: [(Double, CGSize)] = [(0, CGSize(width: 26, height: 13)), (0.5, CGSize(width: 26, height: 13)), (1, CGSize(width: 26, height: 13))]
        let periods = [CGSize(width: 56, height: 16), CGSize(width: 72, height: 16)]
        let values: [(Int, Double, CGSize)] = [(0, 0.75, CGSize(width: 260, height: 18)), (1, 0.85, CGSize(width: 28, height: 18))]
        guard case let (columns, plan)? = Self.layout(
            width: 252, ticks: ticks, periods: periods, values: values,
            wrap: { natural, _ in CGSize(width: 180, height: natural.height * 2) }
        ) else { return XCTFail("no plan") }

        XCTAssertEqual(columns.labelWidth, 104)
        XCTAssertEqual(plan.annotationFrames[0].size, CGSize(width: 180, height: 36), "wrapped as far as it goes")
        XCTAssertEqual(plan.annotationFrames[0].minX, 0, "held inside the leading edge")
        XCTAssertTrue(plan.annotationFrames[0].minX <= columns.centers[0] && columns.centers[0] <= plan.annotationFrames[0].maxX)
        XCTAssertEqual(plan.annotationFrames[1].size, values[1].2, "the neighbour stays whole")
        XCTAssertEqual(plan.annotationFrames[1].midX, columns.centers[1], "and on its own period")
        XCTAssertGreaterThanOrEqual(plan.annotationFrames[1].minY, plan.annotationFrames[0].maxY, "on a row below")
        Self.assertApart(plan.annotationFrames)
        XCTAssertEqual(plan.annotationBand.height, plan.annotationFrames[1].maxY)
        XCTAssertTrue(plan.annotationFrames.allSatisfy { plan.annotationBand.contains($0) })
        XCTAssertLessThanOrEqual(plan.annotationBand.maxY + 6, plan.plotRect.minY - PeriodOutcomeGeometry10868.markRadius)
        XCTAssertEqual(plan.size.width, 252)

        // Wider than the whole plot even unwrapped: the plan reports the overflow.
        guard case let (_, wide)? = Self.layout(
            width: 252, ticks: ticks, periods: periods, values: values,
            wrap: { natural, _ in natural.width > 100 ? CGSize(width: 400, height: natural.height) : natural }
        ) else { return XCTFail("no plan") }
        XCTAssertEqual(wide.annotationFrames[0].size, CGSize(width: 400, height: 18))
        XCTAssertEqual(wide.annotationFrames[1].midX, columns.centers[1])
        XCTAssertGreaterThanOrEqual(wide.annotationFrames[1].minY, wide.annotationFrames[0].maxY)
        Self.assertApart(wide.annotationFrames)
        XCTAssertEqual(wide.size.width, 400)
    }

    func testOnePeriodSitsInTheMiddleWithTheWholeWidthForItsLabel() {
        guard case let (columns, plan)? = Self.layout(
            width: 300,
            ticks: [(0, CGSize(width: 20, height: 13))],
            periods: [CGSize(width: 60, height: 16)],
            values: [(0, 0.5, CGSize(width: 30, height: 18))]
        ) else { return XCTFail("no plan") }

        XCTAssertEqual(columns.labelWidth, columns.plotWidth)
        XCTAssertEqual(columns.centers, [columns.gutter + columns.plotWidth / 2])
        XCTAssertEqual(PeriodOutcomeGeometry10868.normalizedX(0, count: 1), 0.5)
        XCTAssertEqual(plan.markRect.width, 0)
        XCTAssertEqual(plan.periodFrames[0].midX, columns.centers[0])
    }

    func testMalformedPlanInputsPlaceNothing() {
        XCTAssertNil(PeriodOutcomeGeometry10868.columns(width: 300, tickSizes: [], periodNatural: [], annotationNatural: []))
        guard let columns = PeriodOutcomeGeometry10868.columns(
            width: 300, tickSizes: [], periodNatural: [CGSize(width: 40, height: 16), CGSize(width: 40, height: 16)], annotationNatural: []
        ) else { return XCTFail("no columns") }
        let periods = [CGSize(width: 40, height: 16), CGSize(width: 40, height: 16)]
        let one = [CGSize(width: 30, height: 18)]
        // A value label on a period that does not exist.
        XCTAssertNil(PeriodOutcomeGeometry10868.plotPlan(columns: columns, tickFractions: [], tickSizes: [], periodSizes: periods,
                                                         annotationIndices: [2], annotationSizes: one, baseHeight: 170))
        // A position off the scale.
        XCTAssertNil(PeriodOutcomeGeometry10868.plotPlan(columns: columns, tickFractions: [1.2], tickSizes: one, periodSizes: periods,
                                                         annotationIndices: [], annotationSizes: [], baseHeight: 170))
        // Mismatched counts.
        XCTAssertNil(PeriodOutcomeGeometry10868.plotPlan(columns: columns, tickFractions: [], tickSizes: [], periodSizes: [periods[0]],
                                                         annotationIndices: [], annotationSizes: [], baseHeight: 170))
    }
}

/// #10868 — the final-only set card that composes the period comparison: each
/// finished set's reported score and winner beside both players' own original
/// pre-match chances on independent 0–100% bars.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: exact period/series/context/original association, which
/// phase shows anything, which score, winner, chance and bar each set shows,
/// the action each chance carries, the spoken text and the arrangement
/// arithmetic. Nothing here claims a rendered fit, executed accessibility or a
/// runtime binding.
///
/// ARCHIVED raw values come from Alejandro Davidovich Fokina – Frances Tiafoe,
/// event 15327291, as copied in `shipping-adoption-20261027/TENNIS-SET-COMPARISON-
/// RETAINED-CASES.json` (sources `TennisSetComparison.tsx` 2195ba7a…,
/// `tennisFinal.json` d5f83062…, `tennisPropPregame.json` 625e9ff0…):
///   Set 1 games 7–6; market 65138603, consensus 2026-10-11T12:45:25.328389Z
///     outcome 244929341 Fokina 0.5    raw final quote 0.9995  raw result true
///     outcome 244929342 Tiafoe 0.5    raw final quote null    raw result false
///   Set 2 games 4–6; market 65138604, same consensus clock
///     outcome 244929343 Fokina 0.475  raw final quote null    raw result false
///     outcome 244929344 Tiafoe 0.525  raw final quote 0.9995  raw result true
///   Set 3 games 7–6; no set-three market was supplied.
///   ESPN score captured 2026-10-11T17:06:47.950466Z — a capture time, not a
///   set-end time. Match 2–1 in sets, 18–18 in games.
/// The raw final quotes and raw results are fed only as later readings and
/// grades, to prove this card never reads them. The Kalshi match-winner
/// 45.5/54.5 (12:49:23Z) and the 22.5-game threshold are not inputs.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// period, series, context and action identity (the action ids carry the
/// ARCHIVED market and outcome numbers), the short player labels, colours and
/// shapes, every display figure ("50%", "47.5%", "52.5%"), every spoken clock
/// and provenance line, every score text, unit, winner word and missing word,
/// the headline, summary, heading and notes, and every later-reading, grade,
/// zero, missing, out-of-scale, duplicate, blank, foreign, long-text and
/// arrangement case. Reported set winners are supplied explicitly; the approved
/// web card computed them from the games, and this leaf never does.
final class PeriodOutcomeFinalScorePresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static let set1ID = "period:15327291:set-1"
    private static let set2ID = "period:15327291:set-2"
    private static let set3ID = "period:15327291:set-3"
    private static let set1 = PeriodOutcomePeriod10868(id: set1ID, label: "Set 1")
    private static let set2 = PeriodOutcomePeriod10868(id: set2ID, label: "Set 2")
    private static let set3 = PeriodOutcomePeriod10868(id: set3ID, label: "Set 3")
    private static let sets = [set1, set2, set3]

    private static let homeID = "series:15327291:home"
    private static let awayID = "series:15327291:away"

    // CONSTRUCTED action identities carrying the ARCHIVED market/outcome numbers.
    private static let homeSet1 = "constructed:15327291:polymarket:65138603:244929341"
    private static let awaySet1 = "constructed:15327291:polymarket:65138603:244929342"
    private static let homeSet2 = "constructed:15327291:polymarket:65138604:244929343"
    private static let awaySet2 = "constructed:15327291:polymarket:65138604:244929344"
    private static let retainedIDs = [homeSet1, awaySet1, homeSet2, awaySet2]

    // ARCHIVED clocks, CONSTRUCTED wording.
    private static let pin = "recorded Oct 11, 2026, 12:45:25.328389 UTC, before the match · Polymarket"
    private static let scoreProvenance = "ESPN · score captured Oct 11, 2026, 17:06:47.950466 UTC"

    private static let set3Missing = "No pre-match set chance recorded. Score only · no set-three prop supplied."
    private static let summary = "Fokina won 2–1 in sets. Games tied 18–18."

    // ARCHIVED later readings and grades, CONSTRUCTED words — never read by this card.
    private static let settledQuote = PeriodOutcomeCurrent10868.recorded(
        PeriodOutcomeObservation10868(probability: 0.9995, text: "99.95%", accessibilityDetail: "recorded Oct 11, 2026, 14:06:15 UTC · Polymarket")
    )
    private static let noQuote = PeriodOutcomeCurrent10868.unavailable("Current chance unavailable")
    private static let won = PeriodOutcomeResult10868.won("Won")
    private static let lost = PeriodOutcomeResult10868.lost("Lost")
    private static let unconfirmed = PeriodOutcomeResult10868.unconfirmed("Unconfirmed")

    private static func obs(_ probability: Double, _ text: String, _ detail: String = pin) -> PeriodOutcomeObservation10868 {
        PeriodOutcomeObservation10868(probability: probability, text: text, accessibilityDetail: detail)
    }

    /// One original with every field explicit: no lookup fills in a field for
    /// a constructed identity.
    private struct Original {
        let id: String
        let periodID: String
        let seriesID: String
        let pregame: PeriodOutcomeObservation10868?
        let current: PeriodOutcomeCurrent10868
        let result: PeriodOutcomeResult10868

        func with(id: String? = nil, periodID: String? = nil, pregame: PeriodOutcomeObservation10868?? = nil,
                  current: PeriodOutcomeCurrent10868? = nil, result: PeriodOutcomeResult10868? = nil) -> Original {
            Original(id: id ?? self.id, periodID: periodID ?? self.periodID, seriesID: seriesID,
                     pregame: pregame ?? self.pregame, current: current ?? self.current, result: result ?? self.result)
        }
    }

    /// The four retained originals, in order.
    private static let retainedOriginals: [Original] = [
        Original(id: homeSet1, periodID: set1ID, seriesID: homeID, pregame: obs(0.5, "50%"), current: settledQuote, result: won),
        Original(id: awaySet1, periodID: set1ID, seriesID: awayID, pregame: obs(0.5, "50%"), current: noQuote, result: lost),
        Original(id: homeSet2, periodID: set2ID, seriesID: homeID, pregame: obs(0.475, "47.5%"), current: noQuote, result: lost),
        Original(id: awaySet2, periodID: set2ID, seriesID: awayID, pregame: obs(0.525, "52.5%"), current: settledQuote, result: won),
    ]

    /// The retained originals with one replaced by its exact identity.
    private static func replacing(_ id: String, _ change: (Original) -> Original) -> [Original] {
        retainedOriginals.map { $0.id == id ? change($0) : $0 }
    }

    private static func oneSeries(_ id: String, _ label: String, _ tint: Color, _ symbol: PeriodOutcomeSymbol10868,
                                  _ originals: [Original], seriesID: String? = nil) -> PeriodOutcomeSeries10868 {
        PeriodOutcomeSeries10868(
            id: id,
            label: label,
            tint: tint,
            symbol: symbol,
            cells: originals.filter { $0.seriesID == (seriesID ?? id) }.map {
                PeriodOutcomeCell10868(id: $0.id, periodID: $0.periodID, pregame: $0.pregame,
                                       pregameMissing: "No pre-match chance", current: $0.current, result: $0.result)
            }
        )
    }

    private static func players(_ originals: [Original], home: String = "Fokina", away: String = "Tiafoe") -> [PeriodOutcomeSeries10868] {
        [oneSeries(homeID, home, .blue, .circle, originals), oneSeries(awayID, away, .orange, .square, originals)]
    }

    private static func score(_ seriesID: String, _ text: String) -> PeriodOutcomeActualScore10868 {
        PeriodOutcomeActualScore10868(seriesID: seriesID, text: text)
    }

    private static let fokinaWon = PeriodOutcomeActualWinner10868.reported(seriesID: homeID, text: "Fokina won")
    private static let tiafoeWon = PeriodOutcomeActualWinner10868.reported(seriesID: awayID, text: "Tiafoe won")

    private static func reported(_ home: String, _ away: String, _ winner: PeriodOutcomeActualWinner10868,
                                 unit: String = "games") -> PeriodOutcomeActualState10868 {
        .reported(PeriodOutcomeActualReport10868(scores: [score(homeID, home), score(awayID, away)], unit: unit, winner: winner))
    }

    private static func context(_ id: String, _ periodID: String, _ state: PeriodOutcomeActualState10868,
                                noOriginal: String = "No pre-match set chance recorded.") -> PeriodOutcomeActualContext10868 {
        PeriodOutcomeActualContext10868(id: id, periodID: periodID, state: state, provenance: scoreProvenance, noOriginal: noOriginal)
    }

    private static let set1Actual = context("actual:15327291:set-1", set1ID, reported("7", "6", fokinaWon))
    private static let set2Actual = context("actual:15327291:set-2", set2ID, reported("4", "6", tiafoeWon))
    private static let set3Actual = context("actual:15327291:set-3", set3ID, reported("7", "6", fokinaWon), noOriginal: set3Missing)
    private static let retainedActuals = [set1Actual, set2Actual, set3Actual]

    private static let comparisonWords = PeriodOutcomeWords10868(
        pregameTitle: "Pre-match chance",
        notStarted: "Not started",
        currentTitle: "Current chance",
        liveResultTitle: "Set result",
        finalResultTitle: "Final result",
        selectionUnavailable: "Selected player unavailable.",
        cellUnavailable: "Not offered for this set",
        selectHint: "Shows this player’s chances",
        detailsHint: "Opens the original outcome"
    )

    private static let finalWords = PeriodOutcomeFinalScoreWords10868(
        eyebrow: "SET WINNERS · FINAL",
        title: "Two tight sets decided it",
        summary: summary,
        pregameHeading: "Pre-match chance to win each set",
        scoreSeparator: "–",
        actualTitle: "Actual score",
        actualMissing: "No score reported for this set",
        winnerUnavailable: "Winner not reported",
        scaleNote: "Chance bars share a 0–100% scale.",
        detailsNote: "Tap a player for its original outcome and recorded time."
    )

    private static func input(
        _ phase: PeriodOutcomePhase10868 = .final,
        originals: [Original] = retainedOriginals,
        actuals: [PeriodOutcomeActualContext10868] = retainedActuals,
        periods: [PeriodOutcomePeriod10868] = sets,
        seriesOverride: [PeriodOutcomeSeries10868]? = nil,
        words: PeriodOutcomeFinalScoreWords10868 = finalWords
    ) -> PeriodOutcomeFinalScoreInput10868 {
        let comparison = PeriodOutcomeComparisonInput10868(
            phase: phase,
            eyebrow: nil,
            title: "Set-by-set expectations",
            intro: nil,
            periods: periods,
            series: seriesOverride ?? players(originals),
            selectedSeriesID: nil,
            plotTitle: nil,
            scaleCaption: nil,
            axis: PeriodOutcomeAxis10868(lower: 0, upper: 1, ticks: []),
            pointExplanation: "Each dot is a pre-match chance for that set.",
            lineExplanation: "Lines compare sets, not changes over time.",
            resultsTitle: nil,
            words: comparisonWords
        )
        return PeriodOutcomeFinalScoreInput10868(comparison: comparison, actuals: actuals, words: words)
    }

    private static func entries(_ line: PeriodOutcomeScoreLine10868) -> [String] {
        guard case .reported(let entries, _) = line else { return [] }
        return entries.map(\.text)
    }

    private static func winners(_ line: PeriodOutcomeScoreLine10868) -> [Bool] {
        guard case .reported(let entries, _) = line else { return [] }
        return entries.map(\.isReportedWinner)
    }

    /// Everything one period derives, as text, in owner order.
    private static func snapshot(_ input: PeriodOutcomeFinalScoreInput10868) -> [String] {
        input.periodIndices.map { index in
            let chances = input.comparison.series.map { one -> String in
                let lookup = input.chance(one, periodIndex: index)
                let fraction = lookup.cell.flatMap { input.barFraction($0) }.map { "\($0)" } ?? "no fill"
                let action = input.detailsAction(one, periodIndex: index, canOpenDetails: true).map { "\($0)" } ?? "static"
                return "\(input.accessibilityChanceLabel(one, periodIndex: index)) = \(input.accessibilityChanceValue(lookup)) [\(fraction)] [\(action)]"
            }
            return ([input.accessibilityPeriodValue(periodIndex: index), input.scoreOnlyText(periodIndex: index) ?? "-"] + chances)
                .joined(separator: " | ")
        }
    }

    private static func allSpoken(_ input: PeriodOutcomeFinalScoreInput10868) -> String {
        ([input.accessibilityHeader] + snapshot(input) + input.notes(canOpenDetails: true)).joined(separator: " || ")
    }

    // MARK: Retained sets

    func testTheThreeRetainedSetsKeepTheirOwnScoresWinnersAndBaselinesInOwnerOrder() {
        let input = Self.input()
        let home = input.comparison.series[0]
        let away = input.comparison.series[1]

        XCTAssertTrue(input.isShown)
        XCTAssertEqual(input.periodIndices, [0, 1, 2], "every set, no cap")
        XCTAssertEqual(input.words.summary, Self.summary)
        XCTAssertEqual(input.words.pregameHeading, "Pre-match chance to win each set")

        XCTAssertEqual((0..<3).map { Self.entries(input.scoreLine(periodIndex: $0)) }, [["7", "6"], ["4", "6"], ["7", "6"]])
        XCTAssertEqual((0..<3).map { Self.winners(input.scoreLine(periodIndex: $0)) }, [[true, false], [false, true], [true, false]])
        XCTAssertEqual(input.scoreLine(periodIndex: 0), .reported([
            PeriodOutcomeScoreEntry10868(series: home, text: "7", isReportedWinner: true),
            PeriodOutcomeScoreEntry10868(series: away, text: "6", isReportedWinner: false),
        ], unit: "games"))
        XCTAssertEqual(input.winnerLine(periodIndex: 0), .reported(home, "Fokina won"))
        XCTAssertEqual(input.winnerLine(periodIndex: 1), .reported(away, "Tiafoe won"))
        XCTAssertEqual(input.winnerLine(periodIndex: 2), .reported(home, "Fokina won"))

        // Each set's own independent baselines on the same 0–100% bar scale.
        let expected: [(Int, PeriodOutcomeSeries10868, String, Double, String)] = [
            (0, home, Self.homeSet1, 0.5, "50%"), (0, away, Self.awaySet1, 0.5, "50%"),
            (1, home, Self.homeSet2, 0.475, "47.5%"), (1, away, Self.awaySet2, 0.525, "52.5%"),
        ]
        for (index, one, id, value, text) in expected {
            guard let cell = input.chance(one, periodIndex: index).cell else {
                XCTFail("missing \(id)")
                continue
            }
            XCTAssertEqual(cell.id, id)
            XCTAssertEqual(cell.pregame?.probability, value)
            XCTAssertEqual(cell.pregame?.text, text)
            XCTAssertEqual(cell.pregame?.accessibilityDetail, Self.pin)
            XCTAssertEqual(input.barFraction(cell) ?? -1, value, accuracy: 1e-12)
        }
        // The two set-two chances sum to 100% here only because the owner's
        // figures do; nothing is complemented.
        XCTAssertNil(input.scoreOnlyText(periodIndex: 0))
        XCTAssertNil(input.scoreOnlyText(periodIndex: 1))
    }

    func testSetThreeIsScoreOnlyWithTheOwnersWordsAndNoInventedProp() {
        let input = Self.input()

        XCTAssertFalse(input.hasOriginals(periodIndex: 2))
        XCTAssertEqual(input.scoreOnlyText(periodIndex: 2), Self.set3Missing)
        XCTAssertEqual(Self.entries(input.scoreLine(periodIndex: 2)), ["7", "6"])
        for one in input.comparison.series {
            XCTAssertEqual(input.chance(one, periodIndex: 2), .absent)
            XCTAssertNil(input.detailsAction(one, periodIndex: 2, canOpenDetails: true))
        }
        // Exactly the four retained originals are on the card.
        let found = input.periodIndices.flatMap { index in
            input.comparison.series.compactMap { input.chance($0, periodIndex: index).cell?.id }
        }
        XCTAssertEqual(found, Self.retainedIDs)
        XCTAssertEqual(
            input.accessibilityPeriodValue(periodIndex: 2),
            "Fokina won; Actual score: Fokina 7, Tiafoe 6 games; \(Self.scoreProvenance)"
        )
        XCTAssertFalse(Self.snapshot(input)[2].contains("%"), "no chance, zero or complement for set three")
    }

    func testTheMatchHeadlineAndTheTotalGamesThresholdAreNotSetBaselinesOrScores() {
        let input = Self.input()
        let spoken = Self.allSpoken(input)

        for absent in ["45.5", "54.5", "22.5", "18–18 games", "2–1"] {
            XCTAssertFalse(spoken.contains(absent), absent)
        }
        // The summary is the owner's line, verbatim, and is never reconciled
        // against the per-set games.
        XCTAssertEqual(input.words.summary, "Fokina won 2–1 in sets. Games tied 18–18.")
        XCTAssertEqual((0..<2).flatMap { index in
            input.comparison.series.compactMap { input.chance($0, periodIndex: index).cell?.pregame?.text }
        }, ["50%", "50%", "47.5%", "52.5%"])
    }

    // MARK: Phases

    func testBeforeAndDuringNothingOnTheCardIsShownAndTheComparisonKeepsItsLifecycle() {
        for phase in [PeriodOutcomePhase10868.before, .during] {
            let input = Self.input(phase)

            XCTAssertFalse(input.isShown, "\(phase)")
            XCTAssertEqual(input.periodIndices, [])
            XCTAssertEqual(input.accessibilityHeader, "")
            XCTAssertEqual(input.notes(canOpenDetails: true), [])
            for index in 0..<3 {
                XCTAssertEqual(input.actual(periodIndex: index), .absent)
                XCTAssertNil(input.winnerLine(periodIndex: index))
                XCTAssertTrue(Self.entries(input.scoreLine(periodIndex: index)).isEmpty, "no score before the final")
                XCTAssertNil(input.scoreOnlyText(periodIndex: index))
                XCTAssertEqual(input.accessibilityPeriodValue(periodIndex: index), "")
                for one in input.comparison.series {
                    XCTAssertEqual(input.chance(one, periodIndex: index), .absent)
                    XCTAssertNil(input.detailsAction(one, periodIndex: index, canOpenDetails: true))
                }
            }
        }
        // The period comparison it composes is unchanged in every phase.
        let before = Self.input(.before).comparison
        let during = Self.input(.during).comparison
        guard let homeFirst = before.cell(before.series[0], periodIndex: 0).cell,
              let awaySecond = during.cell(during.series[1], periodIndex: 1).cell else { return XCTFail("missing cell") }
        XCTAssertEqual(before.secondReading(homeFirst), .notStarted("Not started"))
        XCTAssertEqual(during.secondReading(awaySecond), .result(Self.won))
        XCTAssertEqual(during.resultTitle, "Set result")
    }

    // MARK: Actual outcome versus grades and later readings

    func testTheReportedWinnerIsTheOwnersAndNeverFollowsTheScoresOrTheGrades() {
        // CONSTRUCTED: the owner reports Tiafoe as set-one winner beside 7–6.
        // The leaf neither checks nor corrects it.
        let conflicting = Self.context("actual:15327291:set-1", Self.set1ID, Self.reported("7", "6", Self.tiafoeWon))
        let input = Self.input(actuals: [conflicting, Self.set2Actual, Self.set3Actual])

        XCTAssertEqual(input.winnerLine(periodIndex: 0), .reported(input.comparison.series[1], "Tiafoe won"))
        XCTAssertEqual(Self.winners(input.scoreLine(periodIndex: 0)), [false, true])
        XCTAssertEqual(Self.entries(input.scoreLine(periodIndex: 0)), ["7", "6"])

        // Grades that contradict, or do not confirm, the reported winner change nothing.
        for grades in [(Self.lost, Self.won), (Self.unconfirmed, Self.unconfirmed), (Self.won, Self.won)] {
            let originals = Self.replacing(Self.homeSet1) { $0.with(result: grades.0) }
                .map { $0.id == Self.awaySet1 ? $0.with(result: grades.1) : $0 }
            let graded = Self.input(originals: originals)
            XCTAssertEqual(graded.winnerLine(periodIndex: 0), .reported(graded.comparison.series[0], "Fokina won"))
            XCTAssertEqual(Self.snapshot(graded), Self.snapshot(Self.input()))
        }
    }

    func testLaterQuotesAndGradesNeverChangeTheChancesOrTheSetOutcome() {
        let terminal = PeriodOutcomeCurrent10868.recorded(Self.obs(1, "100%", "settled Oct 11, 2026, 14:54:06 UTC · Polymarket"))
        let stale = PeriodOutcomeCurrent10868.stale("No update since 2:06 PM")
        let baseline = Self.snapshot(Self.input())
        for current in [Self.settledQuote, terminal, stale, Self.noQuote] {
            for result in [Self.won, Self.lost, Self.unconfirmed] {
                let originals = Self.retainedOriginals.map { $0.with(current: current, result: result) }
                let input = Self.input(originals: originals)
                XCTAssertEqual(Self.snapshot(input), baseline, "\(current) \(result)")
            }
        }
        // The retained input carries the 99.95% quotes and the Won/Lost grades;
        // no set reads them. (The notes' "0–100%" scale is not a set.)
        let spoken = Self.snapshot(Self.input()).joined(separator: " || ")
        for hidden in ["99.95%", "100%", "Won", "Lost", "Unconfirmed", "Final result", "Current chance", "No update since"] {
            XCTAssertFalse(spoken.contains(hidden), hidden)
        }
    }

    // MARK: Score-only, probability-only and missing context

    func testScoreAndChancesAreIndependentHalvesOfEachSet() {
        // CONSTRUCTED: set one has no admitted score; set two has no context;
        // set three keeps its own.
        let unavailable = Self.context("actual:15327291:set-1", Self.set1ID, .unavailable("Set score unavailable"))
        let input = Self.input(actuals: [unavailable, Self.set3Actual])

        XCTAssertEqual(input.scoreLine(periodIndex: 0), .missing("Set score unavailable"))
        XCTAssertNil(input.winnerLine(periodIndex: 0))
        XCTAssertEqual(input.accessibilityPeriodValue(periodIndex: 0), "Actual score: Set score unavailable")
        XCTAssertEqual(input.actual(periodIndex: 1), .absent)
        XCTAssertEqual(input.scoreLine(periodIndex: 1), .missing("No score reported for this set"))
        XCTAssertNil(input.winnerLine(periodIndex: 1))
        // The chances are untouched by the missing scores.
        let home = input.comparison.series[0]
        let away = input.comparison.series[1]
        XCTAssertEqual(input.chance(home, periodIndex: 0).cell?.pregame?.text, "50%")
        XCTAssertEqual(input.chance(away, periodIndex: 1).cell?.pregame?.text, "52.5%")
        XCTAssertEqual(input.detailsAction(away, periodIndex: 1, canOpenDetails: true), .details(Self.awaySet2))
        // And set three keeps its own score and words.
        XCTAssertEqual(Self.entries(input.scoreLine(periodIndex: 2)), ["7", "6"])
        XCTAssertEqual(input.scoreOnlyText(periodIndex: 2), Self.set3Missing)

        // With no set-three context either, its score is missing and the
        // score-only line falls back to the comparison's own unavailable words.
        let bare = Self.input(actuals: [Self.set1Actual, Self.set2Actual])
        XCTAssertEqual(bare.scoreLine(periodIndex: 2), .missing("No score reported for this set"))
        XCTAssertEqual(bare.scoreOnlyText(periodIndex: 2), "Not offered for this set")
    }

    func testDuplicateBlankOrForeignContextsAttachNothingAndBorrowNoNeighbour() {
        // Two contexts for set one.
        let second = Self.context("actual:15327291:set-1b", Self.set1ID, Self.reported("6", "7", Self.tiafoeWon))
        let doubled = Self.input(actuals: Self.retainedActuals + [second])
        XCTAssertEqual(doubled.actual(periodIndex: 0), .ambiguous)
        XCTAssertEqual(doubled.scoreLine(periodIndex: 0), .missing("No score reported for this set"))
        XCTAssertNil(doubled.winnerLine(periodIndex: 0))
        XCTAssertEqual(Self.entries(doubled.scoreLine(periodIndex: 1)), ["4", "6"])

        // A blank context identity.
        let blank = Self.context("  ", Self.set1ID, Self.reported("7", "6", Self.fokinaWon))
        let blankInput = Self.input(actuals: [blank, Self.set2Actual, Self.set3Actual])
        XCTAssertEqual(blankInput.actual(periodIndex: 0), .ambiguous)
        XCTAssertEqual(blankInput.scoreLine(periodIndex: 0), .missing("No score reported for this set"))

        // One context identity used for two sets: neither attaches.
        let reused = Self.context(Self.set1Actual.id, Self.set2ID, Self.reported("4", "6", Self.tiafoeWon))
        let reusedInput = Self.input(actuals: [Self.set1Actual, reused, Self.set3Actual])
        XCTAssertEqual(reusedInput.actual(periodIndex: 0), .ambiguous)
        XCTAssertEqual(reusedInput.actual(periodIndex: 1), .ambiguous)
        XCTAssertEqual(reusedInput.actual(periodIndex: 2), .context(Self.set3Actual))

        // A context for a period not on the card, or for a blank period, is never borrowed.
        let foreign = Self.context("actual:15327291:set-4", "period:15327291:set-4", Self.reported("9", "9", Self.fokinaWon))
        let noPeriod = Self.context("actual:15327291:none", "", Self.reported("8", "8", Self.fokinaWon))
        let strays = Self.input(actuals: [foreign, noPeriod, Self.set2Actual])
        XCTAssertEqual(strays.actual(periodIndex: 0), .absent)
        XCTAssertEqual(strays.actual(periodIndex: 2), .absent)
        let spoken = Self.allSpoken(strays)
        XCTAssertFalse(spoken.contains(" 9"))
        XCTAssertFalse(spoken.contains(" 8"))
        XCTAssertEqual(Self.entries(strays.scoreLine(periodIndex: 1)), ["4", "6"])
    }

    func testEachPlayerNeedsExactlyOneScoreAndTheWinnerMustBeOnTheCard() {
        func set1(_ scores: [PeriodOutcomeActualScore10868], _ winner: PeriodOutcomeActualWinner10868) -> PeriodOutcomeFinalScoreInput10868 {
            let state = PeriodOutcomeActualState10868.reported(PeriodOutcomeActualReport10868(scores: scores, unit: "games", winner: winner))
            return Self.input(actuals: [Self.context("actual:15327291:set-1", Self.set1ID, state), Self.set2Actual, Self.set3Actual])
        }
        let home = Self.score(Self.homeID, "7")
        let away = Self.score(Self.awayID, "6")

        // Half a score is never shown.
        XCTAssertEqual(set1([home], Self.fokinaWon).scoreLine(periodIndex: 0), .missing("No score reported for this set"))
        XCTAssertEqual(set1([home, Self.score(Self.homeID, "6"), away], Self.fokinaWon).scoreLine(periodIndex: 0),
                       .missing("No score reported for this set"))
        // A score for a series not on the card is ignored.
        let extra = set1([Self.score("series:other", "3"), away, home], Self.fokinaWon)
        XCTAssertEqual(Self.entries(extra.scoreLine(periodIndex: 0)), ["7", "6"], "series order, not score order")
        XCTAssertEqual(extra.accessibilityPeriodValue(periodIndex: 0),
                       "Fokina won; Actual score: Fokina 7, Tiafoe 6 games; \(Self.scoreProvenance)")

        // A winner that names no series on the card, or a blank one, decorates nothing.
        for winner in [PeriodOutcomeActualWinner10868.reported(seriesID: "series:other", text: "Someone won"),
                       .reported(seriesID: " ", text: "Fokina won")] {
            let input = set1([home, away], winner)
            XCTAssertEqual(input.winnerLine(periodIndex: 0), .unavailable("Winner not reported"))
            XCTAssertEqual(Self.winners(input.scoreLine(periodIndex: 0)), [false, false])
            XCTAssertEqual(Self.entries(input.scoreLine(periodIndex: 0)), ["7", "6"], "the score stays")
        }
        let unreported = set1([home, away], .unreported("Winner not yet reported by ESPN"))
        XCTAssertEqual(unreported.winnerLine(periodIndex: 0), .unavailable("Winner not yet reported by ESPN"))
        XCTAssertEqual(Self.winners(unreported.scoreLine(periodIndex: 0)), [false, false])
    }

    // MARK: Identity

    func testPeriodAndSeriesIdentitiesMustBeExact() {
        // A period identity used twice: neither copy attaches anything.
        let twice = Self.input(periods: [Self.set1, Self.set2, PeriodOutcomePeriod10868(id: Self.set1ID, label: "Set 3")])
        for index in [0, 2] {
            XCTAssertEqual(twice.actual(periodIndex: index), .ambiguous)
            XCTAssertTrue(twice.comparison.series.allSatisfy { twice.chance($0, periodIndex: index) == .ambiguous })
            XCTAssertTrue(twice.comparison.series.allSatisfy { twice.detailsAction($0, periodIndex: index, canOpenDetails: true) == nil })
        }
        XCTAssertEqual(twice.chance(twice.comparison.series[1], periodIndex: 1).cell?.id, Self.awaySet2)

        // A blank period identity matches no blank-named original or context.
        let blankOriginals = Self.retainedOriginals.map { $0.periodID == Self.set1ID ? $0.with(periodID: "") : $0 }
        let blankContext = Self.context("actual:15327291:set-1", "", Self.reported("7", "6", Self.fokinaWon))
        let blank = Self.input(originals: blankOriginals, actuals: [blankContext, Self.set2Actual, Self.set3Actual],
                               periods: [PeriodOutcomePeriod10868(id: "", label: "Set 1"), Self.set2, Self.set3])
        XCTAssertEqual(blank.actual(periodIndex: 0), .ambiguous)
        XCTAssertTrue(blank.comparison.series.allSatisfy { blank.chance($0, periodIndex: 0) == .ambiguous })
        XCTAssertNil(blank.scoreOnlyText(periodIndex: 0), "an unresolved original is shown unavailable, not dropped")
        XCTAssertTrue(Self.snapshot(blank)[0].contains("Not offered for this set"))
        XCTAssertEqual(Self.entries(blank.scoreLine(periodIndex: 1)), ["4", "6"])

        // Two series sharing an identity, or a blank series identity.
        for ids in [(Self.homeID, Self.homeID), (Self.homeID, " ")] {
            let series = [
                Self.oneSeries(ids.0, "Fokina", .blue, .circle, Self.retainedOriginals, seriesID: Self.homeID),
                Self.oneSeries(ids.1, "Tiafoe", .orange, .square, Self.retainedOriginals, seriesID: Self.awayID),
            ]
            let input = Self.input(seriesOverride: series)
            XCTAssertEqual(input.scoreLine(periodIndex: 0), .missing("No score reported for this set"), "\(ids)")
            XCTAssertEqual(input.chance(series[1], periodIndex: 0), .ambiguous)
            XCTAssertNil(input.detailsAction(series[1], periodIndex: 1, canOpenDetails: true))
            if ids.0 == ids.1 {
                XCTAssertEqual(input.winnerLine(periodIndex: 0), .unavailable("Winner not reported"))
                XCTAssertEqual(input.chance(series[0], periodIndex: 0), .ambiguous)
            } else {
                // The healthy series keeps its own chance and winner.
                XCTAssertEqual(input.winnerLine(periodIndex: 0), .reported(series[0], "Fokina won"))
                XCTAssertEqual(input.detailsAction(series[0], periodIndex: 0, canOpenDetails: true), .details(Self.homeSet1))
            }
        }
    }

    func testABlankOrDuplicatedOriginalIdentityStaysVisibleButStatic() {
        for blankID in ["", "   "] {
            let input = Self.input(originals: Self.replacing(Self.homeSet1) { $0.with(id: blankID) })
            let home = input.comparison.series[0]
            guard let cell = input.chance(home, periodIndex: 0).cell else { return XCTFail("missing cell") }

            XCTAssertEqual(cell.pregame?.text, "50%", "still shown")
            // The shared helper checks uniqueness only, so it would hand back a
            // blank identity; this card's structural guard does not.
            XCTAssertEqual(input.comparison.detailsAction(cell, canOpenDetails: true), .details(blankID))
            XCTAssertNil(input.detailsAction(home, periodIndex: 0, canOpenDetails: true))
            XCTAssertEqual(input.detailsAction(input.comparison.series[1], periodIndex: 0, canOpenDetails: true), .details(Self.awaySet1))
        }

        // Set-two Fokina carries set-one Fokina's identity: neither opens.
        let duplicated = Self.input(originals: Self.replacing(Self.homeSet2) { $0.with(id: Self.homeSet1) })
        let home = duplicated.comparison.series[0]
        XCTAssertNil(duplicated.detailsAction(home, periodIndex: 0, canOpenDetails: true))
        XCTAssertNil(duplicated.detailsAction(home, periodIndex: 1, canOpenDetails: true))
        XCTAssertEqual(duplicated.chance(home, periodIndex: 1).cell?.pregame?.text, "47.5%")
        XCTAssertEqual(duplicated.detailsAction(duplicated.comparison.series[1], periodIndex: 1, canOpenDetails: true), .details(Self.awaySet2))

        // Two set-one originals for Fokina: ambiguous, shown unavailable;
        // Tiafoe's healthy neighbour keeps its chance and action.
        let extra = Original(id: "constructed:15327291:polymarket:65138603:extra", periodID: Self.set1ID, seriesID: Self.homeID,
                             pregame: Self.obs(0.6, "60%"), current: Self.noQuote, result: Self.unconfirmed)
        let ambiguous = Self.input(originals: Self.retainedOriginals + [extra])
        XCTAssertEqual(ambiguous.chance(ambiguous.comparison.series[0], periodIndex: 0), .ambiguous)
        XCTAssertNil(ambiguous.detailsAction(ambiguous.comparison.series[0], periodIndex: 0, canOpenDetails: true))
        XCTAssertEqual(ambiguous.accessibilityChanceValue(ambiguous.chance(ambiguous.comparison.series[0], periodIndex: 0)),
                       "Not offered for this set")
        XCTAssertEqual(ambiguous.detailsAction(ambiguous.comparison.series[1], periodIndex: 0, canOpenDetails: true), .details(Self.awaySet1))
        XCTAssertFalse(Self.allSpoken(ambiguous).contains("60%"))
    }

    // MARK: Bars

    func testZeroMissingOutOfScaleAndNonFiniteChancesKeepTheOwnersTextAndNeverClamp() {
        // A genuine 0% is a value: an empty fill, not a missing bar.
        let zero = Self.input(originals: Self.replacing(Self.homeSet1) { $0.with(pregame: .some(Self.obs(0, "0%"))) })
        guard let zeroCell = zero.chance(zero.comparison.series[0], periodIndex: 0).cell else { return XCTFail("missing cell") }
        XCTAssertEqual(zero.barFraction(zeroCell), 0)
        XCTAssertEqual(zero.accessibilityChanceValue(.cell(zeroCell)), "Pre-match chance: 0%, \(Self.pin)")
        XCTAssertEqual(zero.detailsAction(zero.comparison.series[0], periodIndex: 0, canOpenDetails: true), .details(Self.homeSet1))

        // A missing baseline keeps its own words and its original stays reachable;
        // its neighbour is untouched.
        let missing = Self.input(originals: Self.replacing(Self.awaySet1) { $0.with(pregame: .some(nil)) })
        guard let missingCell = missing.chance(missing.comparison.series[1], periodIndex: 0).cell else { return XCTFail("missing cell") }
        XCTAssertNil(missing.barFraction(missingCell))
        XCTAssertEqual(missing.accessibilityChanceValue(.cell(missingCell)), "Pre-match chance: No pre-match chance")
        XCTAssertEqual(missing.detailsAction(missing.comparison.series[1], periodIndex: 0, canOpenDetails: true), .details(Self.awaySet1))
        XCTAssertEqual(missing.chance(missing.comparison.series[0], periodIndex: 0).cell.flatMap { missing.barFraction($0) }, 0.5)

        // Off the 0…1 scale — including a value on a 0–100 scale — or non-finite: no fill, text verbatim.
        for value in [1.2, -0.1, 47.5, Double.nan, Double.infinity, -Double.infinity] {
            let input = Self.input(originals: Self.replacing(Self.homeSet2) { $0.with(pregame: .some(Self.obs(value, "47.5%"))) })
            guard let cell = input.chance(input.comparison.series[0], periodIndex: 1).cell else { return XCTFail("missing cell") }
            XCTAssertNil(input.barFraction(cell), "\(value)")
            XCTAssertEqual(cell.pregame?.text, "47.5%")
            XCTAssertEqual(input.chance(input.comparison.series[1], periodIndex: 1).cell.flatMap { input.barFraction($0) }, 0.525)
        }
        let full = Self.input(originals: Self.replacing(Self.homeSet2) { $0.with(pregame: .some(Self.obs(1, "100%"))) })
        XCTAssertEqual(full.chance(full.comparison.series[0], periodIndex: 1).cell.flatMap { full.barFraction($0) }, 1)
        XCTAssertEqual(PeriodOutcomeFinalScoreInput10868.barAxis, PeriodOutcomeAxis10868(lower: 0, upper: 1, ticks: []))
    }

    // MARK: Actions

    func testEveryValidOriginalOpensItsExactIdentityThroughTheSharedDetailsAction() {
        let input = Self.input()
        var selected: [String] = []
        var details: [String] = []

        for index in input.periodIndices {
            for one in input.comparison.series {
                let action = input.detailsAction(one, periodIndex: index, canOpenDetails: true)
                if let cell = input.chance(one, periodIndex: index).cell {
                    // The same helper and Action the half-by-half card uses.
                    XCTAssertEqual(action, input.comparison.detailsAction(cell, canOpenDetails: true))
                }
                action?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
            }
        }
        XCTAssertEqual(details, Self.retainedIDs, "unchanged, in owner order")
        XCTAssertEqual(selected, [], "no selection")
    }

    func testWithoutACallbackEveryChanceIsStaticAndNothingIsCalledPassively() {
        let input = Self.input()
        var calls = 0

        for index in input.periodIndices {
            for one in input.comparison.series {
                XCTAssertNil(input.detailsAction(one, periodIndex: index, canOpenDetails: false))
            }
        }
        XCTAssertEqual(input.notes(canOpenDetails: false), ["Chance bars share a 0–100% scale."])
        XCTAssertEqual(input.notes(canOpenDetails: true),
                       ["Chance bars share a 0–100% scale.", "Tap a player for its original outcome and recorded time."])
        // Deriving every action, line and spoken string calls nothing.
        _ = Self.snapshot(input)
        _ = input.periodIndices.flatMap { index in
            input.comparison.series.map { input.detailsAction($0, periodIndex: index, canOpenDetails: true) }
        }
        XCTAssertEqual(calls, 0)
        PeriodOutcomeAction10868.details(Self.homeSet1).perform(onSelect: nil, onDetails: nil)
        PeriodOutcomeAction10868.details(Self.homeSet1).perform(onSelect: nil, onDetails: { _ in calls += 1 })
        XCTAssertEqual(calls, 1, "only an explicit perform calls back")
    }

    /// #10868 decision F: the owner's per-original Details availability.
    func testOwnerDetailsAvailabilityIsNilByDefaultAndOtherwiseOffersOnlyTheNamedExactOriginals() {
        func offered(_ input: PeriodOutcomeFinalScoreInput10868, canOpen: Bool = true) -> [String] {
            input.periodIndices.flatMap { index in
                input.comparison.series.compactMap { one -> String? in
                    guard case .details(let id)? = input.detailsAction(one, periodIndex: index, canOpenDetails: canOpen) else {
                        return nil
                    }
                    return id
                }
            }
        }
        /// What each chance shows, without its control.
        func shown(_ input: PeriodOutcomeFinalScoreInput10868) -> [String] {
            input.periodIndices.flatMap { index in
                input.comparison.series.map { one -> String in
                    let lookup = input.chance(one, periodIndex: index)
                    let fraction = lookup.cell.flatMap { input.barFraction($0) }.map { "\($0)" } ?? "no fill"
                    return "\(input.accessibilityChanceLabel(one, periodIndex: index)) = \(input.accessibilityChanceValue(lookup)) [\(fraction)]"
                }
            }
        }

        // Nil — every existing caller's default — is today's behaviour exactly.
        let open = Self.input()
        XCTAssertNil(open.detailsOriginalIDs)
        XCTAssertEqual(offered(open), Self.retainedIDs)
        XCTAssertEqual(open.notes(canOpenDetails: true),
                       ["Chance bars share a 0–100% scale.", "Tap a player for its original outcome and recorded time."])

        // Supplied: only the named exact originals offer Details; every chance
        // still shows, and an id the card does not show adds nothing.
        var some = Self.input()
        some.detailsOriginalIDs = [Self.awaySet1, "constructed:not-on-this-card"]
        XCTAssertEqual(offered(some), [Self.awaySet1])
        XCTAssertEqual(shown(some), shown(open), "every chance, figure and bar is unchanged")
        XCTAssertEqual(some.notes(canOpenDetails: true), open.notes(canOpenDetails: true),
                       "a chance that opens Details keeps the invitation")
        XCTAssertEqual(offered(some, canOpen: false), [], "still nothing without a callback")
        var details: [String] = []
        some.detailsAction(some.comparison.series[1], periodIndex: 0, canOpenDetails: true)?
            .perform(onSelect: nil, onDetails: { details.append($0) })
        XCTAssertEqual(details, [Self.awaySet1], "the named original, exactly")

        // None named: no control and no invitation; the card is unchanged.
        var none = Self.input()
        none.detailsOriginalIDs = []
        XCTAssertEqual(offered(none), [])
        XCTAssertEqual(shown(none), shown(open))
        XCTAssertEqual(none.notes(canOpenDetails: true), ["Chance bars share a 0–100% scale."])

        // Naming a repeated identity never opens it.
        var repeated = Self.input(originals: Self.replacing(Self.awaySet2) { $0.with(id: Self.homeSet2) })
        repeated.detailsOriginalIDs = [Self.homeSet2]
        XCTAssertEqual(offered(repeated), [])
    }

    // MARK: Spoken and shown text

    func testSpokenTextSeparatesEachScoreAndItsProvenanceFromEachChanceAndItsClock() {
        let input = Self.input()
        let home = input.comparison.series[0]
        let away = input.comparison.series[1]

        XCTAssertEqual(input.accessibilityHeader, "SET WINNERS · FINAL. Two tight sets decided it")
        XCTAssertEqual(input.accessibilityPeriodValue(periodIndex: 0),
                       "Fokina won; Actual score: Fokina 7, Tiafoe 6 games; \(Self.scoreProvenance)")
        XCTAssertEqual(input.accessibilityPeriodValue(periodIndex: 1),
                       "Tiafoe won; Actual score: Fokina 4, Tiafoe 6 games; \(Self.scoreProvenance)")
        XCTAssertEqual(input.accessibilityChanceLabel(home, periodIndex: 0), "Set 1, Fokina")
        XCTAssertEqual(input.accessibilityChanceLabel(away, periodIndex: 1), "Set 2, Tiafoe")
        XCTAssertEqual(input.accessibilityChanceValue(input.chance(home, periodIndex: 1)), "Pre-match chance: 47.5%, \(Self.pin)")
        XCTAssertEqual(input.accessibilityChanceValue(input.chance(away, periodIndex: 2)), "Not offered for this set")
        // The score's capture clock and the chances' pin never trade places.
        for index in 0..<3 {
            XCTAssertFalse(input.accessibilityPeriodValue(periodIndex: index).contains("12:45:25"))
            for one in input.comparison.series {
                XCTAssertFalse(input.accessibilityChanceValue(input.chance(one, periodIndex: index)).contains("ESPN"))
            }
        }
    }

    func testOwnerStringsLongNamesAndUncheckedScoresAreVerbatim() {
        let longHome = "Alejandro Davidovich Fokina"
        let longAway = "Frances Tiafoe"
        let longWinner = PeriodOutcomeActualWinner10868.reported(seriesID: Self.homeID, text: "Alejandro Davidovich Fokina won the tie-break")
        // CONSTRUCTED: tie-break notation and a score no arithmetic would accept.
        let tieBreak = Self.context("actual:15327291:set-1", Self.set1ID, Self.reported("7⁽⁷⁾", "6⁽⁴⁾", longWinner, unit: "games, tie-break points raised"))
        let unchecked = Self.context("actual:15327291:set-2", Self.set2ID, Self.reported("9", "6", Self.tiafoeWon))
        let periods = [PeriodOutcomePeriod10868(id: Self.set1ID, label: "Set 1 · decided in a tie-break"), Self.set2, Self.set3]
        let input = PeriodOutcomeFinalScoreInput10868(
            comparison: Self.input(periods: periods, seriesOverride: Self.players(Self.retainedOriginals, home: longHome, away: longAway)).comparison,
            actuals: [tieBreak, unchecked, Self.set3Actual],
            words: Self.finalWords
        )

        XCTAssertEqual(Self.entries(input.scoreLine(periodIndex: 0)), ["7⁽⁷⁾", "6⁽⁴⁾"])
        XCTAssertEqual(input.winnerLine(periodIndex: 0), .reported(input.comparison.series[0], "Alejandro Davidovich Fokina won the tie-break"))
        XCTAssertEqual(
            input.accessibilityPeriodValue(periodIndex: 0),
            "Alejandro Davidovich Fokina won the tie-break; Actual score: \(longHome) 7⁽⁷⁾, \(longAway) 6⁽⁴⁾ games, tie-break points raised; \(Self.scoreProvenance)"
        )
        XCTAssertEqual(input.accessibilityChanceLabel(input.comparison.series[0], periodIndex: 0), "Set 1 · decided in a tie-break, \(longHome)")
        // The reported 9–6 and Tiafoe as winner stand as given: no sum, no check
        // against the 18–18 summary, no winner inferred from the numbers.
        XCTAssertEqual(Self.entries(input.scoreLine(periodIndex: 1)), ["9", "6"])
        XCTAssertEqual(Self.winners(input.scoreLine(periodIndex: 1)), [false, true])
        XCTAssertEqual(input.words.summary, Self.summary)
    }

    func testAccessibilityIdentifiersCarryExactIdentities() {
        XCTAssertEqual(PeriodOutcomeFinalScoreAccessibilityID10868.period(Self.set1ID), "periodOutcomeFinal10868.period.period:15327291:set-1")
        XCTAssertEqual(PeriodOutcomeFinalScoreAccessibilityID10868.chance(Self.homeSet1),
                       "periodOutcomeFinal10868.chance.constructed:15327291:polymarket:65138603:244929341")
        XCTAssertNotEqual(PeriodOutcomeFinalScoreAccessibilityID10868.chance(Self.homeSet1),
                          PeriodOutcomeAccessibilityID10868.tile(Self.homeSet1), "distinct from the half-by-half tile")
    }

    // MARK: Arrangement (arithmetic on CONSTRUCTED one-line widths — not a rendered fit)

    func testTwoPlayersShareEqualColumnsOnlyWhenBothFitWholeAndStackOtherwise() {
        // CONSTRUCTED one-line widths: short labels with an 18 pt figure, and
        // the full names. Card content widths for 320 / 375 / 393 pt screens and
        // a 640 pt wide column, less CONSTRUCTED padding.
        let short: [CGFloat] = [92, 90]
        let full: [CGFloat] = [232, 150]
        for width: CGFloat in [228, 283, 301] {
            let column = (width - 16) / 2
            XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: width, idealWidths: short, spacing: 16,
                                                                     distribution: .equal, accessibilitySize: false),
                           .row([column, column]), "\(width)")
            XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: width, idealWidths: full, spacing: 16,
                                                                     distribution: .equal, accessibilitySize: false),
                           .stacked, "a full name stacks rather than shrinking at \(width)")
            XCTAssertEqual(PeriodOutcomeFinalGeometry10868.origins(width: width, columns: [column, column], spacing: 16, distribution: .equal),
                           [0, column + 16])
        }
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: 640, idealWidths: full, spacing: 16,
                                                                 distribution: .equal, accessibilitySize: false),
                       .row([312, 312]), "wide: full names side by side, equal widths")
        // Accessibility sizes always stack, however wide.
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: 640, idealWidths: short, spacing: 16,
                                                                 distribution: .equal, accessibilitySize: true),
                       .stacked)
    }

    func testTheSetHeaderSpreadsItsNameAndScoreOnlyWhenBothFitWhole() {
        // CONSTRUCTED: "Set 1 / Fokina won" beside "7 – 6 games".
        let ideals: [CGFloat] = [96, 104]
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: 228, idealWidths: ideals, spacing: 12,
                                                                 distribution: .spread, accessibilitySize: false),
                       .row(ideals))
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.origins(width: 228, columns: ideals, spacing: 12, distribution: .spread),
                       [0, 124], "the score ends at the trailing edge")
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: 200, idealWidths: ideals, spacing: 12,
                                                                 distribution: .spread, accessibilitySize: false),
                       .stacked)
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: 228, idealWidths: ideals, spacing: 12,
                                                                 distribution: .spread, accessibilitySize: true),
                       .stacked)
    }

    func testMalformedArrangementInputsStack() {
        let cases: [(CGFloat, [CGFloat])] = [
            (.nan, [10, 10]), (0, [10, 10]), (300, [10]), (300, []),
            (300, [.nan, 10]), (300, [-1, 10]), (.infinity, [10, 10]),
        ]
        for (width, ideals) in cases {
            XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: width, idealWidths: ideals, spacing: 16,
                                                                     distribution: .equal, accessibilitySize: false),
                           .stacked, "\(width) \(ideals)")
        }
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.origins(width: 300, columns: [], spacing: 16, distribution: .spread), [])
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.origins(width: 300, columns: [120], spacing: 16, distribution: .spread), [0])
    }
}

/// #10868 correction (Design CORRECTION_REQUIRED at 725045f6): the "Tap a
/// player…" note is offered only when at least one shown chance actually opens
/// an original through this card's own `detailsAction` — never on the callback
/// alone. Probability availability is not the gate: a valid original with a
/// missing or 0% pregame chance still opens and keeps the note. Every case is
/// CONSTRUCTED from the retained fixtures above.
extension PeriodOutcomeFinalScorePresentation10868Tests {

    private static let scaleOnly = ["Chance bars share a 0–100% scale."]
    private static let scaleAndDetails = ["Chance bars share a 0–100% scale.",
                                          "Tap a player for its original outcome and recorded time."]

    private static func words(scaleNote: String?) -> PeriodOutcomeFinalScoreWords10868 {
        PeriodOutcomeFinalScoreWords10868(
            eyebrow: finalWords.eyebrow,
            title: finalWords.title,
            summary: finalWords.summary,
            pregameHeading: finalWords.pregameHeading,
            scoreSeparator: finalWords.scoreSeparator,
            actualTitle: finalWords.actualTitle,
            actualMissing: finalWords.actualMissing,
            winnerUnavailable: finalWords.winnerUnavailable,
            scaleNote: scaleNote,
            detailsNote: finalWords.detailsNote
        )
    }

    /// Every Details action the view's chances carry, in owner order — the
    /// same per-chance call the view makes.
    private static func shownActions(_ input: PeriodOutcomeFinalScoreInput10868,
                                     canOpenDetails: Bool = true) -> [PeriodOutcomeAction10868] {
        input.periodIndices.flatMap { index in
            input.comparison.series.compactMap { input.detailsAction($0, periodIndex: index, canOpenDetails: canOpenDetails) }
        }
    }

    // MARK: No action, no invitation

    func testAllScoreOnlySetsWithACallbackDoNotInviteATap() {
        let input = Self.input(originals: [])

        XCTAssertTrue(input.isShown)
        XCTAssertEqual(input.periodIndices, [0, 1, 2])
        for index in input.periodIndices {
            XCTAssertNotNil(input.scoreOnlyText(periodIndex: index), "set \(index + 1) is score-only")
        }
        XCTAssertEqual((0..<3).map { Self.entries(input.scoreLine(periodIndex: $0)) }, [["7", "6"], ["4", "6"], ["7", "6"]],
                       "the scores are still shown")
        XCTAssertEqual(Self.shownActions(input), [])
        XCTAssertFalse(input.opensAnyDetails(canOpenDetails: true))
        XCTAssertEqual(input.notes(canOpenDetails: true), Self.scaleOnly, "a callback alone does not invite a tap")
        XCTAssertEqual(input.notes(canOpenDetails: false), Self.scaleOnly)
    }

    func testAllBlankDuplicatedOrAmbiguousOriginalsWithACallbackDoNotInviteATap() {
        let extras = Self.retainedOriginals.map { $0.with(id: $0.id + ":extra") }
        let sameSetID = [Self.set1, PeriodOutcomePeriod10868(id: Self.set1ID, label: "Set 2"),
                         PeriodOutcomePeriod10868(id: Self.set1ID, label: "Set 3")]
        let blankSetIDs = [PeriodOutcomePeriod10868(id: "", label: "Set 1"), PeriodOutcomePeriod10868(id: "   ", label: "Set 2")]
        let samePlayerID = [
            Self.oneSeries(Self.homeID, "Fokina", .blue, .circle, Self.retainedOriginals),
            Self.oneSeries(Self.homeID, "Tiafoe", .orange, .square, Self.retainedOriginals, seriesID: Self.awayID),
        ]
        let cases: [(String, PeriodOutcomeFinalScoreInput10868)] = [
            ("every original blank", Self.input(originals: Self.retainedOriginals.map { $0.with(id: "") })),
            ("every original spaces", Self.input(originals: Self.retainedOriginals.map { $0.with(id: "   ") })),
            ("every original one identity", Self.input(originals: Self.retainedOriginals.map { $0.with(id: Self.homeSet1) })),
            ("two originals per player per set", Self.input(originals: Self.retainedOriginals + extras)),
            ("every set one identity", Self.input(periods: sameSetID)),
            ("every set blank", Self.input(periods: blankSetIDs)),
            ("both players one identity", Self.input(seriesOverride: samePlayerID)),
        ]

        for (name, input) in cases {
            XCTAssertTrue(input.isShown, name)
            XCTAssertTrue(input.periodIndices.contains { input.scoreOnlyText(periodIndex: $0) == nil },
                          "\(name): chances are shown, but static")
            XCTAssertEqual(Self.shownActions(input), [], name)
            XCTAssertFalse(input.opensAnyDetails(canOpenDetails: true), name)
            XCTAssertEqual(input.notes(canOpenDetails: true), Self.scaleOnly, name)
        }
    }

    func testNoSetsOrNoPlayersWithACallbackDoNotInviteATap() {
        let noSets = Self.input(periods: [])
        XCTAssertTrue(noSets.isShown)
        XCTAssertEqual(noSets.periodIndices, [])
        XCTAssertFalse(noSets.opensAnyDetails(canOpenDetails: true))
        XCTAssertEqual(noSets.notes(canOpenDetails: true), Self.scaleOnly)

        let noPlayers = Self.input(seriesOverride: [])
        XCTAssertEqual(Self.shownActions(noPlayers), [])
        XCTAssertEqual(noPlayers.notes(canOpenDetails: true), Self.scaleOnly)

        // Without the owner's scale note, nothing at all.
        XCTAssertEqual(Self.input(periods: [], words: Self.words(scaleNote: nil)).notes(canOpenDetails: true), [])
    }

    // MARK: A valid original keeps its action and the invitation

    func testAValidOriginalWithAMissingOrZeroChanceKeepsItsActionAndTheInvitation() {
        for pregame in [PeriodOutcomeObservation10868?.none, .some(Self.obs(0, "0%"))] {
            let label = pregame == nil ? "missing" : "0%"

            // The only original on the card: set one Fokina.
            let alone = Self.input(originals: [Self.retainedOriginals[0].with(pregame: .some(pregame))])
            XCTAssertEqual(alone.detailsAction(alone.comparison.series[0], periodIndex: 0, canOpenDetails: true),
                           .details(Self.homeSet1), label)
            XCTAssertNil(alone.detailsAction(alone.comparison.series[1], periodIndex: 0, canOpenDetails: true), label)
            XCTAssertNotNil(alone.scoreOnlyText(periodIndex: 1), label)
            XCTAssertNotNil(alone.scoreOnlyText(periodIndex: 2), label)
            XCTAssertEqual(Self.shownActions(alone), [.details(Self.homeSet1)], label)
            XCTAssertTrue(alone.opensAnyDetails(canOpenDetails: true), label)
            XCTAssertEqual(alone.notes(canOpenDetails: true), Self.scaleAndDetails, label)
            XCTAssertEqual(alone.notes(canOpenDetails: false), Self.scaleOnly, label)

            // Every other original malformed: the one valid original still carries the note.
            let lastValid = Self.input(originals: Self.retainedOriginals.map {
                $0.id == Self.homeSet1 ? $0.with(pregame: .some(pregame)) : $0.with(id: "")
            })
            XCTAssertEqual(Self.shownActions(lastValid), [.details(Self.homeSet1)], label)
            XCTAssertEqual(lastValid.notes(canOpenDetails: true), Self.scaleAndDetails, label)

            // The action opens that exact original.
            var details: [String] = []
            for action in Self.shownActions(alone) {
                action.perform(onSelect: nil, onDetails: { details.append($0) })
            }
            XCTAssertEqual(details, [Self.homeSet1], label)
        }
    }

    // MARK: Separate notes and the final-only gate

    func testTheScaleNoteStaysSeparateAndNothingShowsBeforeTheFinal() {
        let detailsOnly = Self.input(words: Self.words(scaleNote: nil))
        XCTAssertEqual(detailsOnly.notes(canOpenDetails: true), ["Tap a player for its original outcome and recorded time."])
        XCTAssertEqual(detailsOnly.notes(canOpenDetails: false), [])

        for phase in [PeriodOutcomePhase10868.before, .during] {
            for originals in [Self.retainedOriginals, []] {
                let input = Self.input(phase, originals: originals)
                XCTAssertFalse(input.opensAnyDetails(canOpenDetails: true), "\(phase)")
                XCTAssertEqual(input.notes(canOpenDetails: true), [], "\(phase)")
            }
        }
    }

    func testTheInvitationFollowsTheShownActionsInEveryCase() {
        let cases: [PeriodOutcomeFinalScoreInput10868] = [
            Self.input(),
            Self.input(originals: []),
            Self.input(periods: []),
            Self.input(originals: Self.retainedOriginals.map { $0.with(id: "") }),
            Self.input(originals: Self.replacing(Self.homeSet1) { $0.with(id: "") }),
            Self.input(originals: Self.replacing(Self.awaySet2) { $0.with(pregame: .some(nil)) }),
            Self.input(originals: [Self.retainedOriginals[3]]),
        ]
        for (offset, input) in cases.enumerated() {
            let opens = !Self.shownActions(input).isEmpty
            XCTAssertEqual(input.opensAnyDetails(canOpenDetails: true), opens, "case \(offset)")
            XCTAssertEqual(input.notes(canOpenDetails: true).contains("Tap a player for its original outcome and recorded time."),
                           opens, "case \(offset)")
            XCTAssertFalse(input.opensAnyDetails(canOpenDetails: false), "case \(offset)")
            // A score-only set shows no chance, so it carries no action.
            for index in input.periodIndices where input.scoreOnlyText(periodIndex: index) != nil {
                for one in input.comparison.series {
                    XCTAssertNil(input.detailsAction(one, periodIndex: index, canOpenDetails: true), "case \(offset) set \(index + 1)")
                }
            }
        }
        XCTAssertEqual(cases.map { !Self.shownActions($0).isEmpty }, [true, false, false, false, true, true, true])
    }
}

/// #10868 — the live first-set card: the final-score card's explicit opt-in
/// (`completedDuringPlay`) shows, during play, the period the owner admits
/// completed, with both players' own panels — original pre-match chance on its
/// 0–100% bar, the owner's game blocks, the reported games, the reported set
/// state and that original's own result.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: the default stays final-only, the opt-in never shows
/// anything before play and never turns `.during` into `.final`, exact
/// period/series/panel/original association, what each panel shows, the
/// action each panel carries, the notes, the spoken text and the arrangement
/// arithmetic. Nothing here claims a rendered fit, executed accessibility or a
/// runtime binding.
///
/// RETAINED raw values (`Retained` below) come from Arthur Fils – Botic van de
/// Zandschulp, event 15327807, as copied in `shipping-adoption-20261027/TENNIS-
/// LIVE-FIRST-SET-RETAINED-CASES.json` (approved source `LiveTennis.tsx`
/// 50561474…, `liveTennis.json` 99d3b5d2…): Polymarket first-set market
/// 65197795, outcome 245152775 Fils 0.715 and outcome 245152776 Zandschulp
/// 0.285, both observed 2026-10-12T06:58:25.957874Z before the verified
/// 10:55Z start; both results pending, current probability unavailable; later
/// quotes 0.0005 (11:59:14.942512Z) and 0.999 (11:59:24.344917Z). Score
/// captured 12:20:44.471140Z — a capture time, not a set end: match 0–1 in
/// sets, first set 5–7 games, second set 3–3, 8–10 games in all. The match-win
/// 79.5/20.5 baseline and 20.5895/79.4105 headline belong to another market.
///
/// CONSTRUCTED owner inputs (`Constructed` below; this leaf does not resolve
/// them, and they are not a production binding): every period, series, panel,
/// context and action identity (the action ids carry the RETAINED market and
/// outcome numbers), the labels, colours and shapes, every display figure and
/// readable clock, the score texts, unit, winner, set-state and result words,
/// the game blocks, the headline, notes and every missing, duplicate, blank,
/// mis-scoped, contradictory and arrangement case.
final class PeriodOutcomeFirstSetDuringPlay10868Tests: XCTestCase {

    // MARK: Fixtures

    /// RETAINED raw facts, verbatim from the capture. Read only by assertions.
    private enum Retained {
        static let eventID = 15327807
        static let marketID = 65197795
        static let filsOutcomeID = 245152775
        static let zandschulpOutcomeID = 245152776
        static let filsPregame = 0.715
        static let zandschulpPregame = 0.285
        static let pregameAt = "2026-10-12T06:58:25.957874Z"
        static let verifiedStart = "2026-10-12T10:55:00Z"
        static let scoreCaptureAt = "2026-10-12T12:20:44.471140Z"
        static let filsLaterQuote = 0.0005
        static let filsLaterQuoteAt = "2026-10-12T11:59:14.942512Z"
        static let zandschulpLaterQuote = 0.999
        static let zandschulpLaterQuoteAt = "2026-10-12T11:59:24.344917Z"
    }

    /// CONSTRUCTED owner identities and words.
    private enum Constructed {
        static let firstSetID = "constructed:15327807:first-set"
        static let secondSetID = "constructed:15327807:second-set"
        static let filsID = "constructed:15327807:series:fils"
        static let zandschulpID = "constructed:15327807:series:zandschulp"
        static let filsAction = "constructed:15327807:polymarket:65197795:245152775"
        static let zandschulpAction = "constructed:15327807:polymarket:65197795:245152776"
        static let filsPanelID = "constructed:15327807:panel:first-set:fils"
        static let zandschulpPanelID = "constructed:15327807:panel:first-set:zandschulp"
        /// Readable clock words for the RETAINED 06:58:25Z pin and 10:55Z start.
        static let pin = "recorded Oct 11, 11:58:25 PM PT, before the 3:55 AM PT start · Polymarket"
        /// Readable clock words for the RETAINED 12:20:44Z score capture.
        static let scoreProvenance = "Scores · score captured Oct 12, 5:20:44 AM PT"
        static let pending = PeriodOutcomeResult10868.unconfirmed("Result pending")
        static let noRecentPrice = PeriodOutcomeCurrent10868.unavailable("No recent price")
        static let filsBlocks: [PeriodOutcomeCountBlock10868] =
            [PeriodOutcomeCountBlock10868](repeating: .filled, count: 5) + [PeriodOutcomeCountBlock10868](repeating: .empty, count: 2)
        static let zandschulpBlocks = [PeriodOutcomeCountBlock10868](repeating: .filled, count: 7)
        static let blocksNote = "Each block is one game won, not play-by-play order. Score and market settlement are separate."
        static let scaleNote = "Chance bars share a 0–100% scale."
        static let detailsNote = "Tap a player for the original market and recorded time."
    }

    private static func obs(_ probability: Double, _ text: String, _ detail: String = Constructed.pin) -> PeriodOutcomeObservation10868 {
        PeriodOutcomeObservation10868(probability: probability, text: text, accessibilityDetail: detail)
    }

    /// One original with every field explicit.
    private struct Original {
        let id: String
        let periodID: String
        let seriesID: String
        let pregame: PeriodOutcomeObservation10868?
        let current: PeriodOutcomeCurrent10868
        let result: PeriodOutcomeResult10868

        func with(id: String? = nil, pregame: PeriodOutcomeObservation10868?? = nil,
                  current: PeriodOutcomeCurrent10868? = nil, result: PeriodOutcomeResult10868? = nil) -> Original {
            Original(id: id ?? self.id, periodID: periodID, seriesID: seriesID,
                     pregame: pregame ?? self.pregame, current: current ?? self.current, result: result ?? self.result)
        }
    }

    /// The two RETAINED first-set originals, with CONSTRUCTED identities and figures.
    private static let retainedOriginals: [Original] = [
        Original(id: Constructed.filsAction, periodID: Constructed.firstSetID, seriesID: Constructed.filsID,
                 pregame: obs(Retained.filsPregame, "71.5%"), current: Constructed.noRecentPrice, result: Constructed.pending),
        Original(id: Constructed.zandschulpAction, periodID: Constructed.firstSetID, seriesID: Constructed.zandschulpID,
                 pregame: obs(Retained.zandschulpPregame, "28.5%"), current: Constructed.noRecentPrice, result: Constructed.pending),
    ]

    private static func replacing(_ id: String, _ change: (Original) -> Original) -> [Original] {
        retainedOriginals.map { $0.id == id ? change($0) : $0 }
    }

    private static func oneSeries(_ id: String, _ label: String, _ tint: Color, _ symbol: PeriodOutcomeSymbol10868,
                                  originals: [Original]) -> PeriodOutcomeSeries10868 {
        PeriodOutcomeSeries10868(
            id: id, label: label, tint: tint, symbol: symbol,
            cells: originals.filter { $0.seriesID == id }.map {
                PeriodOutcomeCell10868(id: $0.id, periodID: $0.periodID, pregame: $0.pregame,
                                       pregameMissing: "No pre-match chance", current: $0.current, result: $0.result)
            }
        )
    }

    private static func players(originals: [Original], filsLabel: String = "Fils",
                                zandschulpLabel: String = "Zandschulp") -> [PeriodOutcomeSeries10868] {
        [oneSeries(Constructed.filsID, filsLabel, .blue, .circle, originals: originals),
         oneSeries(Constructed.zandschulpID, zandschulpLabel, .orange, .diamond, originals: originals)]
    }

    private static let firstSet = PeriodOutcomePeriod10868(id: Constructed.firstSetID, label: "Set 1")
    private static let secondSet = PeriodOutcomePeriod10868(id: Constructed.secondSetID, label: "Set 2")
    private static let constructedPeriods = [firstSet, secondSet]

    private static func games(filsText: String, zandschulpText: String,
                              winner: PeriodOutcomeActualWinner10868) -> PeriodOutcomeActualState10868 {
        .reported(PeriodOutcomeActualReport10868(
            scores: [PeriodOutcomeActualScore10868(seriesID: Constructed.filsID, text: filsText),
                     PeriodOutcomeActualScore10868(seriesID: Constructed.zandschulpID, text: zandschulpText)],
            unit: "games",
            winner: winner
        ))
    }

    private static func context(id: String, periodID: String, state: PeriodOutcomeActualState10868) -> PeriodOutcomeActualContext10868 {
        PeriodOutcomeActualContext10868(id: id, periodID: periodID, state: state, provenance: Constructed.scoreProvenance,
                                        noOriginal: "Score only · no set chance supplied.")
    }

    private static let zandschulpWonSetOne = PeriodOutcomeActualWinner10868.reported(seriesID: Constructed.zandschulpID,
                                                                                  text: "Zandschulp won set one")
    /// RETAINED 5–7, CONSTRUCTED context.
    private static let firstSetActual = context(id: "constructed:15327807:actual:first-set", periodID: Constructed.firstSetID,
                                                state: games(filsText: "5", zandschulpText: "7", winner: zandschulpWonSetOne))
    /// RETAINED 3–3 of the set still in play, CONSTRUCTED context.
    private static let secondSetActual = context(id: "constructed:15327807:actual:second-set", periodID: Constructed.secondSetID,
                                                 state: games(filsText: "3", zandschulpText: "3", winner: .unreported("Set in progress")))
    private static let constructedActuals = [firstSetActual, secondSetActual]

    private static func panel(id: String, periodID: String = Constructed.firstSetID, seriesID: String,
                              blocks: [PeriodOutcomeCountBlock10868], state: String) -> PeriodOutcomeActualPanel10868 {
        PeriodOutcomeActualPanel10868(id: id, periodID: periodID, seriesID: seriesID, blocks: blocks, state: state)
    }

    private static let filsPanel = panel(id: Constructed.filsPanelID, seriesID: Constructed.filsID,
                                         blocks: Constructed.filsBlocks, state: "Set lost")
    private static let zandschulpPanel = panel(id: Constructed.zandschulpPanelID, seriesID: Constructed.zandschulpID,
                                               blocks: Constructed.zandschulpBlocks, state: "Set won")
    private static let constructedPanels = [filsPanel, zandschulpPanel]

    private static let inPlayWords = PeriodOutcomeCompletedDuringPlayWords10868(
        originalResultTitle: "Original market result",
        blocksNote: Constructed.blocksNote
    )

    private static func optIn(completedPeriodIDs: [String] = [Constructed.firstSetID],
                              panels: [PeriodOutcomeActualPanel10868] = constructedPanels,
                              words: PeriodOutcomeCompletedDuringPlayWords10868 = inPlayWords) -> PeriodOutcomeCompletedDuringPlay10868 {
        PeriodOutcomeCompletedDuringPlay10868(completedPeriodIDs: completedPeriodIDs, panels: panels, words: words)
    }

    private static let comparisonWords = PeriodOutcomeWords10868(
        pregameTitle: "Pre-match chance",
        notStarted: "Not started",
        currentTitle: "Current chance",
        liveResultTitle: "Set result",
        finalResultTitle: "Final result",
        selectionUnavailable: "Selected player unavailable.",
        cellUnavailable: "Not offered for this set",
        selectHint: "Shows this player’s chances",
        detailsHint: "Opens the original market"
    )

    private static let finalWords = PeriodOutcomeFinalScoreWords10868(
        eyebrow: "FIRST SET · EXPECTATION VS ACTUAL",
        title: "A 28.5% underdog took set one",
        summary: nil,
        pregameHeading: "Pre-match chance to win set one",
        scoreSeparator: "–",
        actualTitle: "Actual games",
        actualMissing: "No score reported for this set",
        winnerUnavailable: "Winner not reported",
        scaleNote: Constructed.scaleNote,
        detailsNote: Constructed.detailsNote
    )

    private static func comparison(_ phase: PeriodOutcomePhase10868, periods: [PeriodOutcomePeriod10868],
                                   series: [PeriodOutcomeSeries10868]) -> PeriodOutcomeComparisonInput10868 {
        PeriodOutcomeComparisonInput10868(
            phase: phase,
            eyebrow: nil,
            title: "Set-by-set expectations",
            intro: nil,
            periods: periods,
            series: series,
            selectedSeriesID: nil,
            plotTitle: nil,
            scaleCaption: nil,
            axis: PeriodOutcomeAxis10868(lower: 0, upper: 1, ticks: []),
            pointExplanation: "Each dot is a pre-match chance for that set.",
            lineExplanation: "Lines compare sets, not changes over time.",
            resultsTitle: nil,
            words: comparisonWords
        )
    }

    /// `completedDuringPlay: nil` is the default, final-only card.
    private static func input(
        _ phase: PeriodOutcomePhase10868 = .during,
        originals: [Original] = retainedOriginals,
        actuals: [PeriodOutcomeActualContext10868] = constructedActuals,
        periods: [PeriodOutcomePeriod10868] = constructedPeriods,
        seriesOverride: [PeriodOutcomeSeries10868]? = nil,
        completedDuringPlay: PeriodOutcomeCompletedDuringPlay10868? = optIn()
    ) -> PeriodOutcomeFinalScoreInput10868 {
        PeriodOutcomeFinalScoreInput10868(
            comparison: comparison(phase, periods: periods, series: seriesOverride ?? players(originals: originals)),
            actuals: actuals,
            words: finalWords,
            completedDuringPlay: completedDuringPlay
        )
    }

    /// Everything one shown period derives, as text, in owner order.
    private static func snapshot(_ input: PeriodOutcomeFinalScoreInput10868) -> [String] {
        input.periodIndices.map { index in
            let panels = input.comparison.series.map { one -> String in
                let lookup = input.chance(one, periodIndex: index)
                let fraction = lookup.cell.flatMap { input.barFraction($0) }.map { "\($0)" } ?? "no fill"
                let blocks = input.panelBlocks(one, periodIndex: index).map { list in
                    list.map { $0 == .filled ? "■" : "□" }.joined()
                } ?? "no blocks"
                let action = input.detailsAction(one, periodIndex: index, canOpenDetails: true).map { "\($0)" } ?? "static"
                return "\(input.accessibilityChanceLabel(one, periodIndex: index)) = "
                    + "\(input.accessibilityPanelValue(one, periodIndex: index)) [\(fraction)] [\(blocks)] [\(action)]"
            }
            return ([input.accessibilityPeriodValue(periodIndex: index), input.scoreOnlyText(periodIndex: index) ?? "-"] + panels)
                .joined(separator: " | ")
        }
    }

    private static func allSpoken(_ input: PeriodOutcomeFinalScoreInput10868) -> String {
        ([input.accessibilityHeader] + snapshot(input) + input.notes(canOpenDetails: true)).joined(separator: " || ")
    }

    /// Every Details action the shown panels carry, in owner order.
    private static func shownActions(_ input: PeriodOutcomeFinalScoreInput10868,
                                     canOpenDetails: Bool = true) -> [PeriodOutcomeAction10868] {
        input.periodIndices.flatMap { index in
            input.comparison.series.compactMap { input.detailsAction($0, periodIndex: index, canOpenDetails: canOpenDetails) }
        }
    }

    // MARK: Default and opt-in lifecycle

    func testWithoutTheOptInTheCardStaysFinalOnlyInEveryPhase() {
        for phase in [PeriodOutcomePhase10868.before, .during] {
            let input = Self.input(phase, completedDuringPlay: nil)
            let fils = input.comparison.series[0]

            XCTAssertFalse(input.isShown, "\(phase)")
            XCTAssertEqual(input.periodIndices, [])
            XCTAssertEqual(input.accessibilityHeader, "")
            XCTAssertEqual(input.notes(canOpenDetails: true), [])
            XCTAssertFalse(input.showsPanels(periodIndex: 0))
            XCTAssertEqual(input.panel(fils, periodIndex: 0), .absent)
            XCTAssertNil(input.panelCount(fils, periodIndex: 0))
            XCTAssertNil(input.panelBlocks(fils, periodIndex: 0))
            XCTAssertNil(input.originalResult(fils, periodIndex: 0))
            XCTAssertEqual(input.chance(fils, periodIndex: 0), .absent)
            XCTAssertEqual(input.accessibilityPeriodValue(periodIndex: 0), "")
        }

        // The memberwise call every existing caller makes still compiles and is off.
        let during = PeriodOutcomeFinalScoreInput10868(
            comparison: Self.comparison(.during, periods: Self.constructedPeriods, series: Self.players(originals: Self.retainedOriginals)),
            actuals: Self.constructedActuals,
            words: Self.finalWords
        )
        XCTAssertNil(during.completedDuringPlay)
        XCTAssertFalse(during.isShown)
        let atFinal = PeriodOutcomeFinalScoreInput10868(
            comparison: Self.comparison(.final, periods: Self.constructedPeriods, series: Self.players(originals: Self.retainedOriginals)),
            actuals: Self.constructedActuals,
            words: Self.finalWords
        )
        XCTAssertTrue(atFinal.isShown)
        XCTAssertEqual(atFinal.periodIndices, [0, 1], "after the final, every set")
        XCTAssertFalse(atFinal.showsPanels(periodIndex: 0))
    }

    func testTheOptInShowsOnlyTheAdmittedFirstSetDuringPlayAndNothingBeforePlay() {
        let input = Self.input(.during)

        XCTAssertEqual(input.comparison.phase, .during, "the input's phase is never turned into .final")
        XCTAssertTrue(input.isShown)
        XCTAssertEqual(input.periodIndices, [0], "set two is still in play and not admitted")
        XCTAssertTrue(input.showsPanels(periodIndex: 0))
        XCTAssertFalse(input.showsPanels(periodIndex: 1))
        XCTAssertEqual(input.actual(periodIndex: 1), .absent)
        XCTAssertEqual(input.accessibilityPeriodValue(periodIndex: 1), "")
        XCTAssertEqual(input.accessibilityHeader, "FIRST SET · EXPECTATION VS ACTUAL. A 28.5% underdog took set one")

        // The period comparison it composes keeps its own in-play reading.
        guard let fils = input.comparison.cell(input.comparison.series[0], periodIndex: 0).cell else { return XCTFail("missing cell") }
        XCTAssertEqual(input.comparison.secondReading(fils), .current(.missing("No recent price")))

        // Before play nothing is shown, even with the opt-in.
        let before = Self.input(.before)
        XCTAssertFalse(before.isShown)
        XCTAssertEqual(before.periodIndices, [])
        XCTAssertEqual(before.notes(canOpenDetails: true), [])
        XCTAssertEqual(Self.shownActions(before), [])
        for one in before.comparison.series {
            XCTAssertEqual(before.panel(one, periodIndex: 0), .absent)
            XCTAssertNil(before.panelState(one, periodIndex: 0))
        }
    }

    func testAtTheFinalTheOptInChangesNothing() {
        let plain = Self.input(.final, completedDuringPlay: nil)
        let optedIn = Self.input(.final)

        XCTAssertEqual(Self.snapshot(optedIn), Self.snapshot(plain))
        XCTAssertEqual(optedIn.periodIndices, [0, 1])
        XCTAssertEqual(optedIn.notes(canOpenDetails: true), plain.notes(canOpenDetails: true))
        XCTAssertFalse(optedIn.notes(canOpenDetails: true).contains(Constructed.blocksNote))
        for index in optedIn.periodIndices {
            XCTAssertFalse(optedIn.showsPanels(periodIndex: index))
            for one in optedIn.comparison.series {
                XCTAssertEqual(optedIn.panel(one, periodIndex: index), .absent)
                XCTAssertNil(optedIn.originalResult(one, periodIndex: index), "the final card never reads a grade")
            }
        }
    }

    // MARK: Retained originals

    func testTheTwoRetainedOriginalsKeepTheirOwnIdentitiesBaselinesAndPin() {
        let input = Self.input()
        let expected: [(Int, String, Double, String)] = [
            (0, Constructed.filsAction, Retained.filsPregame, "71.5%"),
            (1, Constructed.zandschulpAction, Retained.zandschulpPregame, "28.5%"),
        ]
        for (seriesIndex, id, value, text) in expected {
            guard let cell = input.chance(input.comparison.series[seriesIndex], periodIndex: 0).cell else {
                XCTFail("missing \(id)")
                continue
            }
            XCTAssertEqual(cell.id, id)
            XCTAssertEqual(cell.pregame?.probability, value)
            XCTAssertEqual(cell.pregame?.text, text)
            XCTAssertEqual(cell.pregame?.accessibilityDetail, Constructed.pin)
            XCTAssertEqual(input.barFraction(cell) ?? -1, value, accuracy: 1e-12)
        }
        XCTAssertTrue(Constructed.filsAction.hasSuffix("\(Retained.marketID):\(Retained.filsOutcomeID)"))
        XCTAssertTrue(Constructed.zandschulpAction.hasSuffix("\(Retained.marketID):\(Retained.zandschulpOutcomeID)"))
        XCTAssertTrue(Constructed.firstSetID.contains("\(Retained.eventID)"))
        // Same ISO form, so string order is time order: pinned before the start;
        // the score capture comes after both.
        XCTAssertLessThan(Retained.pregameAt, Retained.verifiedStart)
        XCTAssertLessThan(Retained.verifiedStart, Retained.scoreCaptureAt)

        // Independent, never complemented: moving one leaves the other.
        let moved = Self.input(originals: Self.replacing(Constructed.filsAction) { $0.with(pregame: .some(Self.obs(0.6, "60%"))) })
        XCTAssertEqual(moved.chance(moved.comparison.series[1], periodIndex: 0).cell?.pregame?.text, "28.5%")
        XCTAssertEqual(moved.chance(moved.comparison.series[1], periodIndex: 0).cell.flatMap { moved.barFraction($0) },
                       Retained.zandschulpPregame)
    }

    // MARK: Actual games and set state versus the original results

    func testFirstSetGamesBlocksAndStateAreTheOwnersAndSeparateFromThePendingResults() {
        let input = Self.input()
        let fils = input.comparison.series[0]
        let zandschulp = input.comparison.series[1]

        XCTAssertEqual(input.scoreLine(periodIndex: 0), .reported([
            PeriodOutcomeScoreEntry10868(series: fils, text: "5", isReportedWinner: false),
            PeriodOutcomeScoreEntry10868(series: zandschulp, text: "7", isReportedWinner: true),
        ], unit: "games"))
        XCTAssertEqual(input.winnerLine(periodIndex: 0), .reported(zandschulp, "Zandschulp won set one"))
        XCTAssertNil(input.panelScoreMissing(periodIndex: 0))

        XCTAssertEqual(input.panel(fils, periodIndex: 0), .panel(Self.filsPanel))
        XCTAssertEqual(input.panelCount(fils, periodIndex: 0), PeriodOutcomePanelCount10868(text: "5", unit: "games"))
        XCTAssertEqual(input.panelCount(zandschulp, periodIndex: 0), PeriodOutcomePanelCount10868(text: "7", unit: "games"))
        XCTAssertEqual(input.panelBlocks(fils, periodIndex: 0), Constructed.filsBlocks)
        XCTAssertEqual(input.panelBlocks(zandschulp, periodIndex: 0), Constructed.zandschulpBlocks)
        XCTAssertEqual(input.panelState(fils, periodIndex: 0), "Set lost")
        XCTAssertEqual(input.panelState(zandschulp, periodIndex: 0), "Set won")

        // Each original's own result, still pending: no mark, so pending never reads as lost.
        for one in [fils, zandschulp] {
            XCTAssertEqual(input.originalResult(one, periodIndex: 0), Constructed.pending)
            XCTAssertNil(input.originalResult(one, periodIndex: 0)?.mark)
        }
        XCTAssertEqual(input.notes(canOpenDetails: true), [Constructed.scaleNote, Constructed.blocksNote, Constructed.detailsNote])
    }

    func testAnAdmittedOrContradictoryOriginalResultStaysIndependentOfTheReportedSet() {
        // CONSTRUCTED control: Fils's original graded Won although he lost the set.
        let originals = Self.retainedOriginals.map {
            $0.seriesID == Constructed.filsID ? $0.with(result: .won("Won")) : $0.with(result: .lost("Lost"))
        }
        let graded = Self.input(originals: originals)
        let pending = Self.input()
        let fils = graded.comparison.series[0]
        let zandschulp = graded.comparison.series[1]

        XCTAssertEqual(graded.originalResult(fils, periodIndex: 0), .won("Won"))
        XCTAssertEqual(graded.originalResult(fils, periodIndex: 0)?.mark, .positive)
        XCTAssertEqual(graded.originalResult(zandschulp, periodIndex: 0)?.mark, .negative)
        // The reported set is untouched by the grades, and the grades by the set.
        XCTAssertEqual(graded.panelState(fils, periodIndex: 0), "Set lost")
        XCTAssertEqual(graded.winnerLine(periodIndex: 0), pending.winnerLine(periodIndex: 0))
        XCTAssertEqual(graded.scoreLine(periodIndex: 0), pending.scoreLine(periodIndex: 0))
        XCTAssertEqual(graded.panelBlocks(fils, periodIndex: 0), pending.panelBlocks(fils, periodIndex: 0))
        XCTAssertTrue(pending.comparison.series.allSatisfy { pending.originalResult($0, periodIndex: 0)?.isAdmitted == false },
                      "a reported set winner never settles an original")
    }

    func testTheMatchScoreSecondSetAggregateGamesAndHeadlineNeverStandInForTheFirstSet() {
        let input = Self.input()
        let spoken = Self.allSpoken(input)

        XCTAssertTrue(spoken.contains("Actual games: Fils 5, Zandschulp 7 games"))
        // "0–1 sets" and "Fils 0", not "0–1": the scale note reads "0–100%".
        for absent in ["Fils 3", "Zandschulp 3", "3 games", "0–1 sets", "Fils 0", "8–10", "18 games", "79.5", "20.5", "79.41", "Set in progress"] {
            XCTAssertFalse(spoken.contains(absent), absent)
        }

        // An owner that files the 3–3 context under the first-set identity gives
        // set one two contexts: neither is chosen, and the chances and the
        // owner's set state stay.
        let misfiled = Self.context(id: "constructed:15327807:actual:second-set:misfiled", periodID: Constructed.firstSetID,
                                    state: Self.games(filsText: "3", zandschulpText: "3", winner: .unreported("Set in progress")))
        let doubled = Self.input(actuals: [Self.firstSetActual, misfiled])
        let fils = doubled.comparison.series[0]
        XCTAssertEqual(doubled.actual(periodIndex: 0), .ambiguous)
        XCTAssertEqual(doubled.scoreLine(periodIndex: 0), .missing("No score reported for this set"))
        XCTAssertEqual(doubled.panelScoreMissing(periodIndex: 0), "No score reported for this set")
        XCTAssertNil(doubled.panelCount(fils, periodIndex: 0))
        XCTAssertNil(doubled.panelBlocks(fils, periodIndex: 0), "blocks never stand in for a missing score")
        XCTAssertEqual(doubled.chance(fils, periodIndex: 0).cell?.pregame?.text, "71.5%")
        XCTAssertEqual(doubled.panelState(fils, periodIndex: 0), "Set lost")
        XCTAssertFalse(Self.allSpoken(doubled).contains("Fils 3"))
    }

    func testLaterQuotesNeverBecomeChancesCountsOrResults() {
        // RETAINED later quotes, fed as current readings with CONSTRUCTED words.
        let quoted = Self.retainedOriginals.map { original -> Original in
            let isFils = original.seriesID == Constructed.filsID
            let reading = isFils
                ? Self.obs(Retained.filsLaterQuote, "0.05%", "recorded Oct 12, 4:59:14 AM PT · Polymarket")
                : Self.obs(Retained.zandschulpLaterQuote, "99.9%", "recorded Oct 12, 4:59:24 AM PT · Polymarket")
            return original.with(current: .recorded(reading))
        }
        let input = Self.input(originals: quoted)

        XCTAssertEqual(Self.snapshot(input), Self.snapshot(Self.input()))
        let spoken = Self.allSpoken(input)
        for hidden in ["0.05%", "99.9%", "4:59", "Current chance", "No recent price"] {
            XCTAssertFalse(spoken.contains(hidden), hidden)
        }
        XCTAssertLessThan(Retained.filsLaterQuoteAt, Retained.scoreCaptureAt)
        XCTAssertLessThan(Retained.zandschulpLaterQuoteAt, Retained.scoreCaptureAt)
    }

    // MARK: Artwork association

    func testMisScopedDuplicateOrBlankArtworkAttachesNothingAndTheUsefulContentStays() {
        let other = "constructed:15327807:series:other"
        let cases: [(String, [PeriodOutcomeActualPanel10868], PeriodOutcomePanelLookup10868, Bool)] = [
            ("panel for set two", [Self.panel(id: Constructed.filsPanelID, periodID: Constructed.secondSetID, seriesID: Constructed.filsID,
                                              blocks: Constructed.filsBlocks, state: "Set lost"), Self.zandschulpPanel], .absent, true),
            ("panel for a period not on the card", [Self.panel(id: Constructed.filsPanelID, periodID: "constructed:15327807:third-set",
                                                               seriesID: Constructed.filsID, blocks: Constructed.filsBlocks,
                                                               state: "Set lost"), Self.zandschulpPanel], .absent, true),
            ("panel for another series", [Self.panel(id: Constructed.filsPanelID, seriesID: other, blocks: Constructed.filsBlocks,
                                                     state: "Set lost"), Self.zandschulpPanel], .absent, true),
            ("blank period and series", [Self.panel(id: Constructed.filsPanelID, periodID: " ", seriesID: "", blocks: Constructed.filsBlocks,
                                                    state: "Set lost"), Self.zandschulpPanel], .absent, true),
            ("two panels for Fils", Self.constructedPanels + [Self.panel(id: "constructed:15327807:panel:first-set:fils-2",
                                                                         seriesID: Constructed.filsID, blocks: Constructed.zandschulpBlocks,
                                                                         state: "Set won")], .ambiguous, true),
            ("blank panel identity", [Self.panel(id: "  ", seriesID: Constructed.filsID, blocks: Constructed.filsBlocks, state: "Set lost"),
                                      Self.zandschulpPanel], .ambiguous, true),
            ("one panel identity for both players", [Self.filsPanel, Self.panel(id: Constructed.filsPanelID, seriesID: Constructed.zandschulpID,
                                                                                blocks: Constructed.zandschulpBlocks, state: "Set won")],
             .ambiguous, false),
        ]

        for (name, panels, filsLookup, zandschulpKeepsPanel) in cases {
            let input = Self.input(completedDuringPlay: Self.optIn(panels: panels))
            let fils = input.comparison.series[0]
            let zandschulp = input.comparison.series[1]

            XCTAssertEqual(input.panel(fils, periodIndex: 0), filsLookup, name)
            XCTAssertNil(input.panelBlocks(fils, periodIndex: 0), name)
            XCTAssertNil(input.panelState(fils, periodIndex: 0), name)
            // Score, chance, result and action stay.
            XCTAssertEqual(input.panelCount(fils, periodIndex: 0), PeriodOutcomePanelCount10868(text: "5", unit: "games"), name)
            XCTAssertEqual(input.chance(fils, periodIndex: 0).cell?.pregame?.text, "71.5%", name)
            XCTAssertEqual(input.originalResult(fils, periodIndex: 0), Constructed.pending, name)
            XCTAssertEqual(input.detailsAction(fils, periodIndex: 0, canOpenDetails: true), .details(Constructed.filsAction), name)
            // No neighbour lends or borrows.
            if zandschulpKeepsPanel {
                XCTAssertEqual(input.panel(zandschulp, periodIndex: 0), .panel(Self.zandschulpPanel), name)
                XCTAssertEqual(input.panelBlocks(zandschulp, periodIndex: 0), Constructed.zandschulpBlocks, name)
            } else {
                XCTAssertEqual(input.panel(zandschulp, periodIndex: 0), .ambiguous, name)
                XCTAssertNil(input.panelBlocks(zandschulp, periodIndex: 0), name)
            }
        }
    }

    func testBlocksNeedTheReportedScoreAndAreShownVerbatimNeverCounted() {
        // CONSTRUCTED: blocks out of play order, and blocks that do not match the
        // reported 5 — both shown exactly as given.
        let scattered: [PeriodOutcomeCountBlock10868] = [.empty, .filled, .filled, .empty, .filled, .filled, .filled]
        let three: [PeriodOutcomeCountBlock10868] = [.filled, .filled, .filled, .empty]
        for blocks in [scattered, three] {
            let panels = [Self.panel(id: Constructed.filsPanelID, seriesID: Constructed.filsID, blocks: blocks, state: "Set lost"),
                          Self.zandschulpPanel]
            let input = Self.input(completedDuringPlay: Self.optIn(panels: panels))
            XCTAssertEqual(input.panelBlocks(input.comparison.series[0], periodIndex: 0), blocks)
            XCTAssertEqual(input.panelCount(input.comparison.series[0], periodIndex: 0)?.text, "5", "the score is never recounted")
        }

        // No admitted score: no count and no blocks; the state and chances stay.
        let unavailable = Self.context(id: Self.firstSetActual.id, periodID: Constructed.firstSetID, state: .unavailable("Set score unavailable"))
        let noScore = Self.input(actuals: [unavailable, Self.secondSetActual])
        for one in noScore.comparison.series {
            XCTAssertNil(noScore.panelCount(one, periodIndex: 0))
            XCTAssertNil(noScore.panelBlocks(one, periodIndex: 0))
            XCTAssertNotNil(noScore.panelState(one, periodIndex: 0))
            XCTAssertNotNil(noScore.chance(one, periodIndex: 0).cell?.pregame)
        }
        XCTAssertEqual(noScore.panelScoreMissing(periodIndex: 0), "Set score unavailable")
        XCTAssertEqual(noScore.accessibilityPeriodValue(periodIndex: 0), "Actual games: Set score unavailable")
        XCTAssertEqual(noScore.notes(canOpenDetails: true), [Constructed.scaleNote, Constructed.detailsNote], "no blocks, no blocks note")

        // Empty block lists draw nothing and carry no note either.
        let empty = [Self.panel(id: Constructed.filsPanelID, seriesID: Constructed.filsID, blocks: [], state: "Set lost"),
                     Self.panel(id: Constructed.zandschulpPanelID, seriesID: Constructed.zandschulpID, blocks: [], state: "Set won")]
        let noBlocks = Self.input(completedDuringPlay: Self.optIn(panels: empty))
        XCTAssertFalse(noBlocks.showsAnyBlocks)
        XCTAssertEqual(noBlocks.panelState(noBlocks.comparison.series[1], periodIndex: 0), "Set won")
        XCTAssertFalse(noBlocks.notes(canOpenDetails: true).contains(Constructed.blocksNote))
    }

    // MARK: Admitted periods

    func testAdmittedPeriodIdentitiesMustBeExact() {
        let notShown: [(String, PeriodOutcomeFinalScoreInput10868)] = [
            ("nothing admitted", Self.input(completedDuringPlay: Self.optIn(completedPeriodIDs: []))),
            ("blank admitted", Self.input(completedDuringPlay: Self.optIn(completedPeriodIDs: ["", "  "]))),
            ("foreign admitted", Self.input(completedDuringPlay: Self.optIn(completedPeriodIDs: ["constructed:15327807:third-set"]))),
            ("set identity used twice", Self.input(periods: [Self.firstSet, PeriodOutcomePeriod10868(id: Constructed.firstSetID, label: "Set 2")])),
            ("blank set identity", Self.input(periods: [PeriodOutcomePeriod10868(id: "", label: "Set 1"), Self.secondSet],
                                              completedDuringPlay: Self.optIn(completedPeriodIDs: [""]))),
        ]
        for (name, input) in notShown {
            XCTAssertFalse(input.isShown, name)
            XCTAssertEqual(input.periodIndices, [], name)
            XCTAssertEqual(input.notes(canOpenDetails: true), [], name)
            XCTAssertEqual(Self.shownActions(input), [], name)
        }

        // Listing set one twice shows it once.
        XCTAssertEqual(Self.input(completedDuringPlay: Self.optIn(completedPeriodIDs: [Constructed.firstSetID, Constructed.firstSetID]))
            .periodIndices, [0])

        // When the owner also admits set two (which has no original here), it
        // is score-only: the owner's score and words, no panels. The leaf does
        // not check whether the set is really over.
        let both = Self.input(completedDuringPlay: Self.optIn(completedPeriodIDs: [Constructed.secondSetID, Constructed.firstSetID]))
        XCTAssertEqual(both.periodIndices, [0, 1], "the owner's period order")
        XCTAssertFalse(both.showsPanels(periodIndex: 1))
        XCTAssertEqual(both.scoreOnlyText(periodIndex: 1), "Score only · no set chance supplied.")
        guard case .reported(let entries, _) = both.scoreLine(periodIndex: 1) else { return XCTFail("missing set-two score") }
        XCTAssertEqual(entries.map(\.text), ["3", "3"])
        for one in both.comparison.series {
            XCTAssertEqual(both.panel(one, periodIndex: 1), .absent)
            XCTAssertNil(both.detailsAction(one, periodIndex: 1, canOpenDetails: true))
        }
    }

    // MARK: Chances and actions

    func testMissingAndZeroChancesKeepTheirValidOriginalAndTheInvitation() {
        for pregame in [PeriodOutcomeObservation10868?.none, .some(Self.obs(0, "0%"))] {
            let label = pregame == nil ? "missing" : "0%"
            let input = Self.input(originals: Self.replacing(Constructed.filsAction) { $0.with(pregame: .some(pregame)) })
            let fils = input.comparison.series[0]
            guard let cell = input.chance(fils, periodIndex: 0).cell else { return XCTFail("missing cell") }

            let expectedFraction: Double? = pregame == nil ? nil : 0
            XCTAssertEqual(input.barFraction(cell), expectedFraction, label)
            XCTAssertEqual(input.detailsAction(fils, periodIndex: 0, canOpenDetails: true), .details(Constructed.filsAction), label)
            XCTAssertTrue(input.notes(canOpenDetails: true).contains(Constructed.detailsNote), label)
            XCTAssertEqual(input.panelCount(fils, periodIndex: 0)?.text, "5", label)
            XCTAssertTrue(input.accessibilityPanelValue(fils, periodIndex: 0)
                .hasPrefix(pregame == nil ? "Pre-match chance: No pre-match chance;" : "Pre-match chance: 0%, "), label)
            // The neighbour is untouched.
            XCTAssertEqual(input.chance(input.comparison.series[1], periodIndex: 0).cell.flatMap { input.barFraction($0) },
                           Retained.zandschulpPregame, label)
        }
    }

    func testControlsFollowTheGenuineDetailsActionAndStayStaticWithoutACallback() {
        let input = Self.input()
        XCTAssertEqual(Self.shownActions(input), [.details(Constructed.filsAction), .details(Constructed.zandschulpAction)])
        var selected: [String] = []
        var details: [String] = []
        for action in Self.shownActions(input) {
            action.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        }
        XCTAssertEqual(details, [Constructed.filsAction, Constructed.zandschulpAction], "exact, in owner order")
        XCTAssertEqual(selected, [], "no selection")

        // No callback: static panels and no tap invitation.
        XCTAssertEqual(Self.shownActions(input, canOpenDetails: false), [])
        XCTAssertEqual(input.notes(canOpenDetails: false), [Constructed.scaleNote, Constructed.blocksNote])

        // A withdrawn original: its panel keeps the player's name, score and
        // state, says it is not offered, and opens nothing; the neighbour opens.
        let withdrawn = Self.input(originals: Self.retainedOriginals.filter { $0.id != Constructed.filsAction })
        let fils = withdrawn.comparison.series[0]
        XCTAssertEqual(withdrawn.chance(fils, periodIndex: 0), .absent)
        XCTAssertNil(withdrawn.originalResult(fils, periodIndex: 0))
        XCTAssertEqual(withdrawn.panelCount(fils, periodIndex: 0)?.text, "5")
        XCTAssertEqual(withdrawn.panelState(fils, periodIndex: 0), "Set lost")
        XCTAssertTrue(withdrawn.accessibilityPanelValue(fils, periodIndex: 0).hasPrefix("Not offered for this set;"))
        XCTAssertEqual(Self.shownActions(withdrawn), [.details(Constructed.zandschulpAction)])
        XCTAssertTrue(withdrawn.notes(canOpenDetails: true).contains(Constructed.detailsNote))

        // Both originals sharing one identity, or blank: shown, but static, and no invitation.
        for change in [{ (o: Original) in o.with(id: Constructed.filsAction) }, { (o: Original) in o.with(id: " ") }] {
            let broken = Self.input(originals: Self.retainedOriginals.map(change))
            XCTAssertEqual(Self.shownActions(broken), [])
            XCTAssertFalse(broken.notes(canOpenDetails: true).contains(Constructed.detailsNote))
            XCTAssertEqual(broken.chance(broken.comparison.series[1], periodIndex: 0).cell?.pregame?.text, "28.5%")
        }

        // Deriving everything calls nothing; a fresh input is read afresh.
        XCTAssertEqual(Self.snapshot(input), Self.snapshot(Self.input()))
        XCTAssertEqual(details.count, 2)
    }

    // MARK: Spoken and shown text

    func testSpokenPanelsSeparateChanceGamesStateAndResultEachWithItsOwnClock() {
        let input = Self.input()
        let fils = input.comparison.series[0]
        let zandschulp = input.comparison.series[1]

        XCTAssertEqual(input.accessibilityPeriodValue(periodIndex: 0),
                       "Zandschulp won set one; Actual games: Fils 5, Zandschulp 7 games; \(Constructed.scoreProvenance)")
        XCTAssertEqual(input.accessibilityChanceLabel(fils, periodIndex: 0), "Set 1, Fils")
        XCTAssertEqual(input.accessibilityPanelValue(fils, periodIndex: 0),
                       "Pre-match chance: 71.5%, \(Constructed.pin); Actual games: 5 games; Set lost; Original market result: Result pending")
        XCTAssertEqual(input.accessibilityPanelValue(zandschulp, periodIndex: 0),
                       "Pre-match chance: 28.5%, \(Constructed.pin); Actual games: 7 games; Set won; Original market result: Result pending")
        // The score's capture clock and the chances' pin never trade places.
        for one in [fils, zandschulp] {
            XCTAssertFalse(input.accessibilityPanelValue(one, periodIndex: 0).contains("5:20:44"))
        }
        XCTAssertFalse(input.accessibilityPeriodValue(periodIndex: 0).contains("11:58:25"))

        // Full owner names stay whole.
        let long = Self.input(seriesOverride: Self.players(originals: Self.retainedOriginals, filsLabel: "Arthur Fils",
                                                           zandschulpLabel: "Botic van de Zandschulp"))
        XCTAssertEqual(long.accessibilityChanceLabel(long.comparison.series[1], periodIndex: 0), "Set 1, Botic van de Zandschulp")
        XCTAssertEqual(long.accessibilityPeriodValue(periodIndex: 0),
                       "Zandschulp won set one; Actual games: Arthur Fils 5, Botic van de Zandschulp 7 games; \(Constructed.scoreProvenance)")
    }

    // MARK: Arrangement (arithmetic on CONSTRUCTED one-line widths — not a rendered fit)

    func testPanelsShareARowOnlyWhenBothWholePanelsFit() {
        // CONSTRUCTED ideal panel widths: short names (seven 12 pt blocks with
        // 3 pt gaps plus 10 pt padding each side), and one full name. Card
        // content widths for 320 / 375 / 393 pt screens and a 640 pt column.
        let short: [CGFloat] = [122, 122]
        let full: [CGFloat] = [122, 196]
        for width: CGFloat in [264, 319, 337] {
            let column = (width - 10) / 2
            XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: width, idealWidths: short, spacing: 10,
                                                                     distribution: .equal, accessibilitySize: false),
                           .row([column, column]), "\(width)")
            XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: width, idealWidths: full, spacing: 10,
                                                                     distribution: .equal, accessibilitySize: false),
                           .stacked, "a full name stacks both panels rather than shrinking at \(width)")
        }
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: 640, idealWidths: full, spacing: 10,
                                                                 distribution: .equal, accessibilitySize: false),
                       .row([315, 315]))
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: 640, idealWidths: short, spacing: 10,
                                                                 distribution: .equal, accessibilitySize: true),
                       .stacked, "accessibility sizes always stack")
    }

    // MARK: Block wrapping (arithmetic on CONSTRUCTED block sizes — not a rendered fit)

    func testBlocksWrapInTheOwnersOrderRatherThanOverflowANarrowPanel() {
        let block = CGSize(width: 12, height: 17)

        // Seven blocks fit one row exactly at 102 pt.
        let oneRow = PeriodOutcomeBlockGeometry10868.plan(count: 7, block: block, spacing: 3, width: 102)
        XCTAssertEqual(oneRow.origins.map(\.x), [0, 15, 30, 45, 60, 75, 90])
        XCTAssertEqual(Set(oneRow.origins.map(\.y)), [0])
        XCTAssertEqual(oneRow.size, CGSize(width: 102, height: 17))

        // A point narrower: six, then the seventh below — still in order.
        let twoRows = PeriodOutcomeBlockGeometry10868.plan(count: 7, block: block, spacing: 3, width: 101)
        XCTAssertEqual(twoRows.origins.last, CGPoint(x: 0, y: 20))
        XCTAssertEqual(twoRows.size, CGSize(width: 87, height: 37))

        // CONSTRUCTED accessibility-size blocks (29 × 41) in a 120 pt panel: three rows inside it.
        let large = PeriodOutcomeBlockGeometry10868.plan(count: 7, block: CGSize(width: 29, height: 41), spacing: 3, width: 120)
        XCTAssertEqual(large.origins.map(\.x), [0, 32, 64, 0, 32, 64, 0])
        XCTAssertEqual(large.origins.map(\.y), [0, 0, 0, 44, 44, 44, 88])
        XCTAssertEqual(large.size, CGSize(width: 93, height: 129))
        XCTAssertLessThanOrEqual(large.size.width, 120)

        // No finite width proposed: one row — the ideal the panel arrangement measures.
        for width in [CGFloat?.none, .some(.infinity), .some(0)] {
            let plan = PeriodOutcomeBlockGeometry10868.plan(count: 7, block: block, spacing: 3, width: width)
            XCTAssertEqual(plan.size, CGSize(width: 102, height: 17), "\(String(describing: width))")
            XCTAssertEqual(plan.origins.count, 7, "every block placed")
        }

        // A block wider than the panel sits alone on each row: whole, never shrunk or dropped.
        let wide = PeriodOutcomeBlockGeometry10868.plan(count: 3, block: CGSize(width: 50, height: 10), spacing: 3, width: 40)
        XCTAssertEqual(wide.origins, [CGPoint(x: 0, y: 0), CGPoint(x: 0, y: 13), CGPoint(x: 0, y: 26)])
        XCTAssertEqual(wide.size, CGSize(width: 50, height: 36))
    }

    func testMalformedBlockPlansPlaceNothing() {
        let empty = PeriodOutcomeBlockPlan10868(origins: [], size: .zero)
        let block = CGSize(width: 12, height: 17)
        let cases: [(Int, CGSize, CGFloat)] = [
            (0, block, 3), (-1, block, 3),
            (7, CGSize(width: .nan, height: 17), 3), (7, CGSize(width: .infinity, height: 17), 3),
            (7, CGSize(width: 0, height: 17), 3), (7, CGSize(width: 12, height: -1), 3),
            (7, block, -1), (7, block, .nan),
        ]
        for (count, size, spacing) in cases {
            XCTAssertEqual(PeriodOutcomeBlockGeometry10868.plan(count: count, block: size, spacing: spacing, width: 100), empty,
                           "\(count) \(size) \(spacing)")
        }
    }
}

/// #10868 — the pregame first-set card: the final-score card's explicit
/// before-play opt-in (`beforePlay`) shows, before play, the period the owner
/// names, with both players' own panels carrying only each original's
/// pre-match chance on its 0–100% bar, under the owner's pregame copy.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: the default shows nothing before play, the opt-in keeps
/// `.before` and changes nothing during play or after the final, exact
/// period/series/original association, what each panel shows and says, that
/// no later score, winner, artwork, count, set state, result, quote, clock or
/// card word reaches the shown or spoken projection, the action each panel
/// carries, the notes and the arrangement arithmetic. Nothing here claims a
/// rendered fit, executed accessibility or a runtime binding.
///
/// RETAINED raw values (`Retained` below) come from Arthur Fils – Botic van de
/// Zandschulp, event 15327807, as copied in `shipping-adoption-20261027/TENNIS-
/// PREGAME-FIRST-SET-RETAINED-CASES.json` (approved source `LiveTennis.tsx`
/// 50561474…, `liveTennis.json` 99d3b5d2…): Polymarket first-set market
/// 65197795, outcome 245152775 Fils 0.715 and outcome 245152776 Zandschulp
/// 0.285, both observed 2026-10-12T06:58:25.957874Z before the verified
/// 10:55Z start. Everything later is a suppression control only: first set
/// 5–7 games, match 0–1 in sets, second set 3–3, 8–10 games in all (score
/// captured 12:20:44.471140Z), both results pending, later quotes 0.0005
/// (11:59:14.942512Z) and 0.999 (11:59:24.344917Z), and the match-win
/// 79.5/20.5 baseline of another market.
///
/// CONSTRUCTED owner inputs (`Constructed` below; not a production binding):
/// every identity (the action ids carry the RETAINED market and outcome
/// numbers), the labels, colours and shapes, every display figure and
/// readable clock, the pregame copy ("Who takes the first set?", "Pre-match
/// chances"), every later word, block, panel, grade and context used as a
/// hostile control, and every missing, zero, non-finite, duplicate, blank,
/// foreign, withdrawn and arrangement case.
final class PeriodOutcomeFirstSetBeforePlay10868Tests: XCTestCase {

    // MARK: Fixtures

    /// RETAINED raw facts, verbatim from the capture. Read only by assertions.
    private enum Retained {
        static let eventID = 15327807
        static let marketID = 65197795
        static let filsOutcomeID = 245152775
        static let zandschulpOutcomeID = 245152776
        static let filsPregame = 0.715
        static let zandschulpPregame = 0.285
        static let pregameAt = "2026-10-12T06:58:25.957874Z"
        static let verifiedStart = "2026-10-12T10:55:00Z"
        static let scoreCaptureAt = "2026-10-12T12:20:44.471140Z"
        static let filsLaterQuote = 0.0005
        static let filsLaterQuoteAt = "2026-10-12T11:59:14.942512Z"
        static let zandschulpLaterQuote = 0.999
        static let zandschulpLaterQuoteAt = "2026-10-12T11:59:24.344917Z"
        static let matchWinBaseline = 0.795
    }

    /// CONSTRUCTED owner identities and words.
    private enum Constructed {
        static let firstSetID = "constructed:15327807:first-set"
        static let secondSetID = "constructed:15327807:second-set"
        static let filsID = "constructed:15327807:series:fils"
        static let zandschulpID = "constructed:15327807:series:zandschulp"
        static let filsAction = "constructed:15327807:polymarket:65197795:245152775"
        static let zandschulpAction = "constructed:15327807:polymarket:65197795:245152776"
        static let filsPanelID = "constructed:15327807:panel:first-set:fils"
        static let zandschulpPanelID = "constructed:15327807:panel:first-set:zandschulp"
        /// Readable clock words for the RETAINED 06:58:25Z pin and 10:55Z start.
        static let pin = "recorded Oct 11, 11:58:25 PM PT, before the 3:55 AM PT start · Polymarket"
        /// Readable clock words for the RETAINED 12:20:44Z score capture — a later control.
        static let scoreProvenance = "Scores · score captured Oct 12, 5:20:44 AM PT"
        static let pending = PeriodOutcomeResult10868.unconfirmed("Result pending")
        static let noRecentPrice = PeriodOutcomeCurrent10868.unavailable("No recent price")
        static let filsBlocks: [PeriodOutcomeCountBlock10868] =
            [PeriodOutcomeCountBlock10868](repeating: .filled, count: 5) + [PeriodOutcomeCountBlock10868](repeating: .empty, count: 2)
        static let zandschulpBlocks = [PeriodOutcomeCountBlock10868](repeating: .filled, count: 7)
        static let blocksNote = "Each block is one game won, not play-by-play order. Score and market settlement are separate."
        static let pregameScaleNote = "Both chances share one 0–100% scale."
        static let pregameDetailsNote = "Tap a player for the original market and recorded time."
        static let finalScaleNote = "Chance bars share a 0–100% scale."
        static let finalDetailsNote = "Tap a player for the original market and the settled result."
    }

    private static func obs(_ probability: Double, _ text: String, _ detail: String = Constructed.pin) -> PeriodOutcomeObservation10868 {
        PeriodOutcomeObservation10868(probability: probability, text: text, accessibilityDetail: detail)
    }

    /// One original with every field explicit.
    private struct Original {
        let id: String
        let periodID: String
        let seriesID: String
        let pregame: PeriodOutcomeObservation10868?
        let current: PeriodOutcomeCurrent10868
        let result: PeriodOutcomeResult10868

        func with(id: String? = nil, periodID: String? = nil, pregame: PeriodOutcomeObservation10868?? = nil,
                  current: PeriodOutcomeCurrent10868? = nil, result: PeriodOutcomeResult10868? = nil) -> Original {
            Original(id: id ?? self.id, periodID: periodID ?? self.periodID, seriesID: seriesID,
                     pregame: pregame ?? self.pregame, current: current ?? self.current, result: result ?? self.result)
        }
    }

    /// The two RETAINED first-set originals, with CONSTRUCTED identities and figures.
    private static let retainedOriginals: [Original] = [
        Original(id: Constructed.filsAction, periodID: Constructed.firstSetID, seriesID: Constructed.filsID,
                 pregame: obs(Retained.filsPregame, "71.5%"), current: Constructed.noRecentPrice, result: Constructed.pending),
        Original(id: Constructed.zandschulpAction, periodID: Constructed.firstSetID, seriesID: Constructed.zandschulpID,
                 pregame: obs(Retained.zandschulpPregame, "28.5%"), current: Constructed.noRecentPrice, result: Constructed.pending),
    ]

    /// Later controls on the same originals: the RETAINED later quotes as
    /// current readings and CONSTRUCTED contradictory grades (Fils graded Won
    /// although he lost the set).
    private static let laterOriginals: [Original] = retainedOriginals.map { original in
        let isFils = original.seriesID == Constructed.filsID
        let reading = isFils
            ? obs(Retained.filsLaterQuote, "0.05%", "recorded Oct 12, 4:59:14 AM PT · Polymarket")
            : obs(Retained.zandschulpLaterQuote, "99.9%", "recorded Oct 12, 4:59:24 AM PT · Polymarket")
        return original.with(current: .recorded(reading), result: isFils ? .won("Won") : .lost("Lost"))
    }

    private static func replacing(_ id: String, in originals: [Original] = retainedOriginals,
                                  _ change: (Original) -> Original) -> [Original] {
        originals.map { $0.id == id ? change($0) : $0 }
    }

    private static func oneSeries(_ id: String, _ label: String, _ tint: Color, _ symbol: PeriodOutcomeSymbol10868,
                                  originals: [Original]) -> PeriodOutcomeSeries10868 {
        PeriodOutcomeSeries10868(
            id: id, label: label, tint: tint, symbol: symbol,
            cells: originals.filter { $0.seriesID == id }.map {
                PeriodOutcomeCell10868(id: $0.id, periodID: $0.periodID, pregame: $0.pregame,
                                       pregameMissing: "No pre-match chance", current: $0.current, result: $0.result)
            }
        )
    }

    private static func players(originals: [Original], filsLabel: String = "Fils",
                                zandschulpLabel: String = "Zandschulp") -> [PeriodOutcomeSeries10868] {
        [oneSeries(Constructed.filsID, filsLabel, .blue, .circle, originals: originals),
         oneSeries(Constructed.zandschulpID, zandschulpLabel, .orange, .diamond, originals: originals)]
    }

    private static let firstSet = PeriodOutcomePeriod10868(id: Constructed.firstSetID, label: "Set 1")
    private static let secondSet = PeriodOutcomePeriod10868(id: Constructed.secondSetID, label: "Set 2")
    private static let constructedPeriods = [firstSet, secondSet]

    private static func games(filsText: String, zandschulpText: String,
                              winner: PeriodOutcomeActualWinner10868) -> PeriodOutcomeActualState10868 {
        .reported(PeriodOutcomeActualReport10868(
            scores: [PeriodOutcomeActualScore10868(seriesID: Constructed.filsID, text: filsText),
                     PeriodOutcomeActualScore10868(seriesID: Constructed.zandschulpID, text: zandschulpText)],
            unit: "games",
            winner: winner
        ))
    }

    private static func context(id: String, periodID: String, state: PeriodOutcomeActualState10868) -> PeriodOutcomeActualContext10868 {
        PeriodOutcomeActualContext10868(id: id, periodID: periodID, state: state, provenance: Constructed.scoreProvenance,
                                        noOriginal: "Score only · no set chance supplied.")
    }

    /// Later controls: the RETAINED 5–7 and 3–3 in CONSTRUCTED contexts.
    private static let laterActuals = [
        context(id: "constructed:15327807:actual:first-set", periodID: Constructed.firstSetID,
                state: games(filsText: "5", zandschulpText: "7",
                             winner: .reported(seriesID: Constructed.zandschulpID, text: "Zandschulp won set one"))),
        context(id: "constructed:15327807:actual:second-set", periodID: Constructed.secondSetID,
                state: games(filsText: "3", zandschulpText: "3", winner: .unreported("Set in progress"))),
    ]

    /// Later controls: completed-set artwork and the during-play opt-in naming set one.
    private static let laterOptIn = PeriodOutcomeCompletedDuringPlay10868(
        completedPeriodIDs: [Constructed.firstSetID],
        panels: [
            PeriodOutcomeActualPanel10868(id: Constructed.filsPanelID, periodID: Constructed.firstSetID,
                                          seriesID: Constructed.filsID, blocks: Constructed.filsBlocks, state: "Set lost"),
            PeriodOutcomeActualPanel10868(id: Constructed.zandschulpPanelID, periodID: Constructed.firstSetID,
                                          seriesID: Constructed.zandschulpID, blocks: Constructed.zandschulpBlocks, state: "Set won"),
        ],
        words: PeriodOutcomeCompletedDuringPlayWords10868(originalResultTitle: "Original market result",
                                                          blocksNote: Constructed.blocksNote)
    )

    private static let comparisonWords = PeriodOutcomeWords10868(
        pregameTitle: "Pre-match chance",
        notStarted: "Not started",
        currentTitle: "Current chance",
        liveResultTitle: "Set result",
        finalResultTitle: "Final result",
        selectionUnavailable: "Selected player unavailable.",
        cellUnavailable: "Not offered for this set",
        selectHint: "Shows this player’s chances",
        detailsHint: "Opens the original market"
    )

    /// The card's own words — after-start copy, a later control before play.
    private static let finalWords = PeriodOutcomeFinalScoreWords10868(
        eyebrow: "FIRST SET · EXPECTATION VS ACTUAL",
        title: "A 28.5% underdog took set one",
        summary: "Zandschulp leads by a set.",
        pregameHeading: "Pre-match chance to win set one",
        scoreSeparator: "–",
        actualTitle: "Actual games",
        actualMissing: "No score reported for this set",
        winnerUnavailable: "Winner not reported",
        scaleNote: Constructed.finalScaleNote,
        detailsNote: Constructed.finalDetailsNote
    )

    /// The owner's pregame copy, as the RETAINED-CASES `before_presentation` words.
    private static let pregameCopy = PeriodOutcomeCardCopy10868(
        eyebrow: nil,
        title: "Who takes the first set?",
        summary: nil,
        pregameHeading: "Pre-match chances",
        scaleNote: Constructed.pregameScaleNote,
        detailsNote: Constructed.pregameDetailsNote
    )

    private static func named(_ periodIDs: [String] = [Constructed.firstSetID],
                              copy: PeriodOutcomeCardCopy10868 = pregameCopy) -> PeriodOutcomeBeforePlay10868 {
        PeriodOutcomeBeforePlay10868(periodIDs: periodIDs, copy: copy)
    }

    private static func comparison(_ phase: PeriodOutcomePhase10868, periods: [PeriodOutcomePeriod10868],
                                   series: [PeriodOutcomeSeries10868]) -> PeriodOutcomeComparisonInput10868 {
        PeriodOutcomeComparisonInput10868(
            phase: phase,
            eyebrow: nil,
            title: "Set-by-set expectations",
            intro: nil,
            periods: periods,
            series: series,
            selectedSeriesID: nil,
            plotTitle: nil,
            scaleCaption: nil,
            axis: PeriodOutcomeAxis10868(lower: 0, upper: 1, ticks: []),
            pointExplanation: "Each dot is a pre-match chance for that set.",
            lineExplanation: "Lines compare sets, not changes over time.",
            resultsTitle: nil,
            words: comparisonWords
        )
    }

    /// Before play with the opt-in by default — and with every later control
    /// passed alongside (actuals, artwork and the during-play opt-in), so each
    /// test also exercises suppression. `clean` drops the later controls.
    private static func input(
        _ phase: PeriodOutcomePhase10868 = .before,
        originals: [Original] = retainedOriginals,
        actuals: [PeriodOutcomeActualContext10868] = laterActuals,
        periods: [PeriodOutcomePeriod10868] = constructedPeriods,
        seriesOverride: [PeriodOutcomeSeries10868]? = nil,
        completedDuringPlay: PeriodOutcomeCompletedDuringPlay10868? = laterOptIn,
        beforePlay: PeriodOutcomeBeforePlay10868? = named()
    ) -> PeriodOutcomeFinalScoreInput10868 {
        PeriodOutcomeFinalScoreInput10868(
            comparison: comparison(phase, periods: periods, series: seriesOverride ?? players(originals: originals)),
            actuals: actuals,
            words: finalWords,
            completedDuringPlay: completedDuringPlay,
            beforePlay: beforePlay
        )
    }

    private static var clean: PeriodOutcomeFinalScoreInput10868 {
        input(actuals: [], completedDuringPlay: nil)
    }

    /// Everything the card shows and says, as text, in owner order: the
    /// header copy and spoken header; per shown period its header channels
    /// and spoken value; per outcome its panel's every channel and spoken
    /// value; then the notes.
    private static func projection(_ input: PeriodOutcomeFinalScoreInput10868, canOpenDetails: Bool = true) -> [String] {
        let copy = input.copy
        let header = [copy.eyebrow ?? "-", copy.title, copy.summary ?? "-", copy.pregameHeading, input.accessibilityHeader]
        let periods = input.periodIndices.flatMap { index -> [String] in
            let period = input.comparison.periods[index]
            let periodLine = [
                period.label,
                "\(input.showsPanels(periodIndex: index))/\(input.showsPanelsBeforePlay(periodIndex: index))",
                input.winnerLine(periodIndex: index).map { "\($0)" } ?? "no winner",
                input.panelScoreMissing(periodIndex: index) ?? "no missing score",
                input.scoreOnlyText(periodIndex: index) ?? "-",
                input.accessibilityPeriodValue(periodIndex: index),
            ].joined(separator: " | ")
            let panels = input.comparison.series.map { one -> String in
                let lookup = input.chance(one, periodIndex: index)
                let shown = lookup.cell.map { input.comparison.pregameReading($0).text } ?? input.comparison.words.cellUnavailable
                let fraction = lookup.cell.flatMap { input.barFraction($0) }.map { "\($0)" } ?? "no fill"
                let blocks = input.panelBlocks(one, periodIndex: index).map { "\($0)" } ?? "no blocks"
                let count = input.panelCount(one, periodIndex: index).map { "\($0.text) \($0.unit)" } ?? "no count"
                let state = input.panelState(one, periodIndex: index) ?? "no state"
                let result = input.originalResult(one, periodIndex: index)?.text ?? "no result"
                let action = input.detailsAction(one, periodIndex: index, canOpenDetails: canOpenDetails).map { "\($0)" } ?? "static"
                return [one.label, shown, fraction, blocks, count, state, result, action,
                        input.accessibilityChanceLabel(one, periodIndex: index),
                        input.accessibilityPanelValue(one, periodIndex: index)].joined(separator: " | ")
            }
            return [periodLine] + panels
        }
        return header + periods + input.notes(canOpenDetails: canOpenDetails)
    }

    private static func allText(_ input: PeriodOutcomeFinalScoreInput10868) -> String {
        projection(input).joined(separator: " || ")
    }

    /// Every Details action the shown panels carry, in owner order.
    private static func shownActions(_ input: PeriodOutcomeFinalScoreInput10868,
                                     canOpenDetails: Bool = true) -> [PeriodOutcomeAction10868] {
        input.periodIndices.flatMap { index in
            input.comparison.series.compactMap { input.detailsAction($0, periodIndex: index, canOpenDetails: canOpenDetails) }
        }
    }

    /// Words and figures that belong after the start. None may be shown or
    /// spoken before play.
    private static let later = [
        "Actual games", "5 games", "7 games", "Zandschulp won", "Winner not reported", "Set lost", "Set won", "Set in progress",
        "Result pending", "Original market result", "Won", "Lost", "0.05%", "99.9%", "4:59", "5:20:44", "Scores ·",
        "No recent price", "Current chance", "Not started", "Final result", "Set result", "A 28.5% underdog", "leads by a set",
        "EXPECTATION VS ACTUAL", "Pre-match chance to win", "Each block", "Score only", "No score reported", "settled",
        Constructed.finalScaleNote, "filled", "79.5", "20.5", "0–1 sets", "3–3",
    ]

    // MARK: Default and opt-in lifecycle

    func testWithoutTheBeforeOptInNothingShowsBeforePlayAndDuringAndFinalIgnoreIt() {
        // Off by default before play, even with later actuals and the during-play opt-in passed.
        let off = Self.input(beforePlay: nil)
        XCTAssertFalse(off.isShown)
        XCTAssertEqual(off.periodIndices, [])
        XCTAssertEqual(off.periodIndicesBeforePlay, [])
        XCTAssertEqual(off.accessibilityHeader, "")
        XCTAssertEqual(off.notes(canOpenDetails: true), [])
        XCTAssertEqual(Self.shownActions(off), [])
        XCTAssertFalse(off.showsPanelsBeforePlay(periodIndex: 0))
        XCTAssertEqual(off.chance(off.comparison.series[0], periodIndex: 0), .absent)
        XCTAssertEqual(Self.projection(off), [off.copy.eyebrow ?? "-", off.copy.title, off.copy.summary ?? "-",
                                              off.copy.pregameHeading, ""], "nothing per period, no notes")

        // The memberwise calls every existing caller makes still compile and stay off.
        let series = Self.players(originals: Self.retainedOriginals)
        let fourArgs = PeriodOutcomeFinalScoreInput10868(
            comparison: Self.comparison(.before, periods: Self.constructedPeriods, series: series),
            actuals: Self.laterActuals, words: Self.finalWords, completedDuringPlay: Self.laterOptIn
        )
        let threeArgs = PeriodOutcomeFinalScoreInput10868(
            comparison: Self.comparison(.before, periods: Self.constructedPeriods, series: series),
            actuals: Self.laterActuals, words: Self.finalWords
        )
        for old in [fourArgs, threeArgs] {
            XCTAssertNil(old.beforePlay)
            XCTAssertFalse(old.isShown)
            XCTAssertEqual(old.periodIndices, [])
        }

        // During play and after the final the opt-in changes nothing, copy included.
        for phase in [PeriodOutcomePhase10868.during, .final] {
            let without = Self.input(phase, beforePlay: nil)
            let optedIn = Self.input(phase)
            XCTAssertEqual(Self.projection(optedIn), Self.projection(without), "\(phase)")
            XCTAssertEqual(optedIn.periodIndicesBeforePlay, [], "\(phase)")
            XCTAssertEqual(optedIn.copy, without.copy, "\(phase)")
            XCTAssertEqual(optedIn.copy.title, "A 28.5% underdog took set one", "\(phase)")
            XCTAssertFalse(optedIn.showsPanelsBeforePlay(periodIndex: 0), "\(phase)")
        }
        XCTAssertEqual(Self.input(.during).periodIndices, [0], "the during-play opt-in still shows set one")
        XCTAssertEqual(Self.input(.final).periodIndices, [0, 1], "after the final, every set")
    }

    func testTheOptInShowsTheNamedFirstSetBeforePlayAndKeepsTheBeforePhase() {
        let input = Self.input()

        XCTAssertEqual(input.comparison.phase, .before, "never turned into .during or .final")
        XCTAssertTrue(input.isShown)
        XCTAssertEqual(input.periodIndices, [0])
        XCTAssertEqual(input.periodIndicesBeforePlay, [0])
        XCTAssertTrue(input.showsPanelsBeforePlay(periodIndex: 0))
        XCTAssertFalse(input.showsPanelsBeforePlay(periodIndex: 1), "set two is not named")
        XCTAssertFalse(input.showsPanels(periodIndex: 0), "the during-play panels stay during play")
        XCTAssertEqual(input.completedPeriodIndicesDuringPlay, [], "the during-play opt-in is inert before play")
        XCTAssertEqual(input.copy, Self.pregameCopy)
        XCTAssertEqual(input.accessibilityHeader, "Who takes the first set?")

        // The period comparison it composes keeps its own before reading.
        guard let fils = input.comparison.cell(input.comparison.series[0], periodIndex: 0).cell else { return XCTFail("missing cell") }
        XCTAssertEqual(input.comparison.secondReading(fils), .notStarted("Not started"))
    }

    // MARK: Retained originals

    func testBothRetainedOriginalsShowTheirOwnChancesPinsAndBarsTogether() {
        let input = Self.input()
        XCTAssertNil(input.comparison.selectedSeriesID, "no selection is needed to see either chance")
        let expected: [(Int, String, Double, String)] = [
            (0, Constructed.filsAction, Retained.filsPregame, "71.5%"),
            (1, Constructed.zandschulpAction, Retained.zandschulpPregame, "28.5%"),
        ]
        for (seriesIndex, id, value, text) in expected {
            let one = input.comparison.series[seriesIndex]
            guard let cell = input.chance(one, periodIndex: 0).cell else {
                XCTFail("missing \(id)")
                continue
            }
            XCTAssertEqual(cell.id, id)
            XCTAssertEqual(cell.pregame?.probability, value)
            XCTAssertEqual(cell.pregame?.text, text)
            XCTAssertEqual(cell.pregame?.accessibilityDetail, Constructed.pin)
            XCTAssertEqual(input.barFraction(cell) ?? -1, value, accuracy: 1e-12, "the shared 0–100% bar")
            XCTAssertNotEqual(cell.pregame?.probability, Retained.matchWinBaseline, "another market's baseline")
            XCTAssertEqual(input.detailsAction(one, periodIndex: 0, canOpenDetails: true), .details(id))
        }
        XCTAssertTrue(Constructed.filsAction.hasSuffix("\(Retained.marketID):\(Retained.filsOutcomeID)"))
        XCTAssertTrue(Constructed.zandschulpAction.hasSuffix("\(Retained.marketID):\(Retained.zandschulpOutcomeID)"))
        XCTAssertTrue(Constructed.firstSetID.contains("\(Retained.eventID)"))
        // Same ISO form, so string order is time order: pinned before the start.
        XCTAssertLessThan(Retained.pregameAt, Retained.verifiedStart)

        // Independent, never complemented: moving one leaves the other.
        let moved = Self.input(originals: Self.replacing(Constructed.filsAction) { $0.with(pregame: .some(Self.obs(0.6, "60%"))) })
        XCTAssertEqual(moved.chance(moved.comparison.series[1], periodIndex: 0).cell?.pregame?.text, "28.5%")
        XCTAssertEqual(moved.chance(moved.comparison.series[1], periodIndex: 0).cell.flatMap { moved.barFraction($0) },
                       Retained.zandschulpPregame)
    }

    // MARK: Later channels stay out

    func testLaterScoresArtworkStatesResultsQuotesAndCardWordsNeverShowOrSpeakBeforePlay() {
        let clean = Self.clean
        let hostile: [(String, PeriodOutcomeFinalScoreInput10868)] = [
            ("later actuals, artwork and during opt-in", Self.input()),
            ("later quotes and contradictory grades", Self.input(originals: Self.laterOriginals)),
            ("non-finite later quote", Self.input(originals: Self.replacing(Constructed.filsAction, in: Self.laterOriginals) {
                $0.with(current: .recorded(Self.obs(.nan, "NaN%", "recorded Oct 12, 4:59:14 AM PT · Polymarket")))
            })),
            ("stale later reading", Self.input(originals: Self.retainedOriginals.map { $0.with(current: .stale("No update since 4:59 AM")) })),
        ]
        XCTAssertEqual(Self.projection(clean).filter { $0.contains("71.5%") }.count, 1, "the clean card shows Fils's chance once")
        for (name, input) in hostile {
            XCTAssertEqual(Self.projection(input), Self.projection(clean), name)
            let text = Self.allText(input)
            for word in Self.later {
                XCTAssertFalse(text.contains(word), "\(name): \(word)")
            }
            for one in input.comparison.series {
                XCTAssertEqual(input.panel(one, periodIndex: 0), .absent, name)
                XCTAssertNil(input.panelCount(one, periodIndex: 0), name)
                XCTAssertNil(input.panelBlocks(one, periodIndex: 0), name)
                XCTAssertNil(input.panelState(one, periodIndex: 0), name)
                XCTAssertNil(input.originalResult(one, periodIndex: 0), name)
            }
            XCTAssertEqual(input.actual(periodIndex: 0), .absent, name)
            XCTAssertNil(input.winnerLine(periodIndex: 0), name)
            XCTAssertNil(input.panelScoreMissing(periodIndex: 0), name)
            XCTAssertEqual(input.accessibilityPeriodValue(periodIndex: 0), "", name)
            XCTAssertFalse(input.showsAnyBlocks, name)
        }

        // Not vacuous: the same later controls do show during play.
        let during = Self.input(.during, originals: Self.laterOriginals, beforePlay: nil)
        XCTAssertEqual(during.panelCount(during.comparison.series[0], periodIndex: 0)?.text, "5")
        XCTAssertEqual(during.panelState(during.comparison.series[1], periodIndex: 0), "Set won")
        XCTAssertEqual(during.originalResult(during.comparison.series[0], periodIndex: 0), .won("Won"))
        XCTAssertTrue(Self.allText(during).contains("Zandschulp won set one"))
        XCTAssertLessThan(Retained.verifiedStart, Retained.filsLaterQuoteAt)
        XCTAssertLessThan(Retained.verifiedStart, Retained.zandschulpLaterQuoteAt)
        XCTAssertLessThan(Retained.verifiedStart, Retained.scoreCaptureAt)
    }

    func testOnlyTheOwnersPregameCopyHeadsAndNotesTheCardBeforePlay() {
        let input = Self.input()
        XCTAssertEqual(input.notes(canOpenDetails: true), [Constructed.pregameScaleNote, Constructed.pregameDetailsNote],
                       "no blocks note, no card note")
        XCTAssertEqual(input.notes(canOpenDetails: false), [Constructed.pregameScaleNote], "no invitation without a callback")
        XCTAssertEqual(Array(Self.projection(input).prefix(5)),
                       ["-", "Who takes the first set?", "-", "Pre-match chances", "Who takes the first set?"])

        // Owner copy is shown verbatim, never parsed: an eyebrow and a summary
        // that name figures, and a copy with no notes.
        let owned = PeriodOutcomeCardCopy10868(
            eyebrow: "FIRST SET · BEFORE PLAY",
            title: "Fils is the 71.5% favourite to take set one",
            summary: "Both players’ original chances, recorded before the start.",
            pregameHeading: "Pre-match chance to take set one, by player",
            scaleNote: nil,
            detailsNote: nil
        )
        let custom = Self.input(beforePlay: Self.named(copy: owned))
        XCTAssertEqual(custom.copy, owned)
        XCTAssertEqual(custom.accessibilityHeader, "FIRST SET · BEFORE PLAY. Fils is the 71.5% favourite to take set one")
        XCTAssertEqual(custom.notes(canOpenDetails: true), [])
        XCTAssertEqual(Self.shownActions(custom).count, 2, "copy without a note still keeps both actions")
    }

    // MARK: Named periods

    func testNamedPeriodsMustBeExactUniqueAndOnTheCard() {
        let notShown: [(String, PeriodOutcomeFinalScoreInput10868)] = [
            ("nothing named", Self.input(beforePlay: Self.named([]))),
            ("blank named", Self.input(beforePlay: Self.named(["", "  "]))),
            ("foreign named", Self.input(beforePlay: Self.named(["constructed:15327807:third-set"]))),
            ("set identity used twice", Self.input(periods: [Self.firstSet, PeriodOutcomePeriod10868(id: Constructed.firstSetID, label: "Set 2")])),
            ("blank set identity", Self.input(periods: [PeriodOutcomePeriod10868(id: "", label: "Set 1"), Self.secondSet],
                                              beforePlay: Self.named([""]))),
            ("no periods", Self.input(periods: [])),
        ]
        for (name, input) in notShown {
            XCTAssertFalse(input.isShown, name)
            XCTAssertEqual(input.periodIndices, [], name)
            XCTAssertEqual(input.accessibilityHeader, "", name)
            XCTAssertEqual(input.notes(canOpenDetails: true), [], name)
            XCTAssertEqual(Self.shownActions(input), [], name)
        }

        // Naming set one twice shows it once; naming set two only shows set two
        // and never falls back to set one.
        XCTAssertEqual(Self.input(beforePlay: Self.named([Constructed.firstSetID, Constructed.firstSetID])).periodIndices, [0])
        let onlySecond = Self.input(beforePlay: Self.named([Constructed.secondSetID]))
        XCTAssertEqual(onlySecond.periodIndices, [1])
        XCTAssertFalse(Self.allText(onlySecond).contains("71.5%"))

        // Both named, in reverse: the owner's period order. Set two has no
        // original here: each panel says so, opens nothing and borrows nothing.
        let both = Self.input(beforePlay: Self.named([Constructed.secondSetID, Constructed.firstSetID]))
        XCTAssertEqual(both.periodIndices, [0, 1])
        XCTAssertTrue(both.showsPanelsBeforePlay(periodIndex: 1))
        for one in both.comparison.series {
            XCTAssertEqual(both.chance(one, periodIndex: 1), .absent)
            XCTAssertNil(both.detailsAction(one, periodIndex: 1, canOpenDetails: true))
            XCTAssertEqual(both.accessibilityPanelValue(one, periodIndex: 1), "Not offered for this set")
            XCTAssertNil(both.panelCount(one, periodIndex: 1), "no 3–3")
        }
        XCTAssertEqual(Self.shownActions(both), [.details(Constructed.filsAction), .details(Constructed.zandschulpAction)])
        XCTAssertFalse(Self.allText(both).contains("Score only"))
    }

    // MARK: Chances and actions

    func testMissingZeroAndNonFiniteChancesKeepTheirOriginalAndTheInvitation() {
        let cases: [(String, PeriodOutcomeObservation10868?, String, Double?)] = [
            ("missing", nil, "No pre-match chance", nil),
            ("genuine 0%", Self.obs(0, "0%"), "0%", 0),
            ("non-finite", Self.obs(.nan, "Chance unavailable"), "Chance unavailable", nil),
            ("out of scale", Self.obs(1.2, "120%"), "120%", nil),
        ]
        for (name, pregame, shown, fraction) in cases {
            let input = Self.input(originals: Self.replacing(Constructed.filsAction) { $0.with(pregame: .some(pregame)) })
            let fils = input.comparison.series[0]
            guard let cell = input.chance(fils, periodIndex: 0).cell else { return XCTFail("missing cell \(name)") }

            XCTAssertEqual(input.comparison.pregameReading(cell).text, shown, name)
            XCTAssertEqual(input.barFraction(cell), fraction, "\(name): never clamped")
            XCTAssertEqual(input.detailsAction(fils, periodIndex: 0, canOpenDetails: true), .details(Constructed.filsAction), name)
            XCTAssertTrue(input.notes(canOpenDetails: true).contains(Constructed.pregameDetailsNote), name)
            XCTAssertTrue(input.accessibilityPanelValue(fils, periodIndex: 0).hasPrefix("Pre-match chance: \(shown)"), name)
            // The neighbour is untouched.
            XCTAssertEqual(input.chance(input.comparison.series[1], periodIndex: 0).cell.flatMap { input.barFraction($0) },
                           Retained.zandschulpPregame, name)
        }
    }

    func testControlsFollowTheGenuineDetailsActionAndStayStaticWithoutACallback() {
        let input = Self.input()
        XCTAssertEqual(Self.shownActions(input), [.details(Constructed.filsAction), .details(Constructed.zandschulpAction)])
        var selected: [String] = []
        var details: [String] = []
        for action in Self.shownActions(input) {
            action.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        }
        XCTAssertEqual(details, [Constructed.filsAction, Constructed.zandschulpAction], "exact, in owner order")
        XCTAssertEqual(selected, [], "no selection")

        // No callback: static panels and no tap invitation.
        XCTAssertEqual(Self.shownActions(input, canOpenDetails: false), [])
        XCTAssertTrue(Self.projection(input, canOpenDetails: false).filter { $0.contains("details(") }.isEmpty)

        // A withdrawn original, or one filed under set two: Fils's panel says
        // it is not offered and opens nothing; Zandschulp's still opens.
        let withdrawn = Self.retainedOriginals.filter { $0.id != Constructed.filsAction }
        let foreign = Self.replacing(Constructed.filsAction) { $0.with(periodID: Constructed.secondSetID) }
        for (name, originals) in [("withdrawn", withdrawn), ("filed under set two", foreign)] {
            let one = Self.input(originals: originals)
            let fils = one.comparison.series[0]
            XCTAssertEqual(one.chance(fils, periodIndex: 0), .absent, name)
            XCTAssertEqual(one.accessibilityPanelValue(fils, periodIndex: 0), "Not offered for this set", name)
            XCTAssertEqual(Self.shownActions(one), [.details(Constructed.zandschulpAction)], name)
            XCTAssertTrue(one.notes(canOpenDetails: true).contains(Constructed.pregameDetailsNote), name)
            XCTAssertEqual(one.chance(one.comparison.series[1], periodIndex: 0).cell?.pregame?.text, "28.5%", name)
        }

        // Both originals sharing one identity, or blank: shown, but static, and no invitation.
        for change in [{ (o: Original) in o.with(id: Constructed.filsAction) }, { (o: Original) in o.with(id: " ") }] {
            let broken = Self.input(originals: Self.retainedOriginals.map(change))
            XCTAssertEqual(Self.shownActions(broken), [])
            XCTAssertEqual(broken.notes(canOpenDetails: true), [Constructed.pregameScaleNote])
            XCTAssertEqual(broken.chance(broken.comparison.series[1], periodIndex: 0).cell?.pregame?.text, "28.5%")
        }

        // Deriving everything calls nothing; a fresh input is read afresh.
        XCTAssertEqual(Self.projection(input), Self.projection(Self.input()))
        XCTAssertEqual(details.count, 2)
    }

    // MARK: Spoken text

    func testSpokenPanelsCarryOnlyEachPreMatchChanceWithItsOwnPin() {
        let input = Self.input()
        let fils = input.comparison.series[0]
        let zandschulp = input.comparison.series[1]

        XCTAssertEqual(input.accessibilityChanceLabel(fils, periodIndex: 0), "Set 1, Fils")
        XCTAssertEqual(input.accessibilityPanelValue(fils, periodIndex: 0), "Pre-match chance: 71.5%, \(Constructed.pin)")
        XCTAssertEqual(input.accessibilityPanelValue(zandschulp, periodIndex: 0), "Pre-match chance: 28.5%, \(Constructed.pin)")
        XCTAssertEqual(input.accessibilityPeriodValue(periodIndex: 0), "", "no score, winner or provenance to say")

        // Full owner names stay whole.
        let long = Self.input(seriesOverride: Self.players(originals: Self.retainedOriginals, filsLabel: "Arthur Fils",
                                                           zandschulpLabel: "Botic van de Zandschulp"))
        XCTAssertEqual(long.accessibilityChanceLabel(long.comparison.series[1], periodIndex: 0), "Set 1, Botic van de Zandschulp")
        XCTAssertEqual(long.accessibilityPanelValue(long.comparison.series[1], periodIndex: 0), "Pre-match chance: 28.5%, \(Constructed.pin)")
    }

    // MARK: Arrangement (arithmetic on CONSTRUCTED one-line widths — not a rendered fit)

    func testPregamePanelsShareTheMeasuredEqualRowOnlyWhenBothWholePanelsFit() {
        // CONSTRUCTED ideal pregame panel widths — a name above a 28 pt figure,
        // 10 pt padding each side, no blocks: short names, and one full name.
        // Card content widths for 320 / 375 / 393 pt screens and a 640 pt column.
        let short: [CGFloat] = [105, 105]
        let full: [CGFloat] = [105, 200]
        for width: CGFloat in [264, 319, 337] {
            let column = (width - 10) / 2
            XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: width, idealWidths: short, spacing: 10,
                                                                     distribution: .equal, accessibilitySize: false),
                           .row([column, column]), "equal columns, so neither chance reads larger at \(width)")
            XCTAssertEqual(PeriodOutcomeFinalGeometry10868.origins(width: width, columns: [column, column], spacing: 10,
                                                                 distribution: .equal), [0, column + 10])
            XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: width, idealWidths: full, spacing: 10,
                                                                     distribution: .equal, accessibilitySize: false),
                           .stacked, "a full name stacks both panels rather than shrinking at \(width)")
        }
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: 640, idealWidths: full, spacing: 10,
                                                                 distribution: .equal, accessibilitySize: false),
                       .row([315, 315]))
        XCTAssertEqual(PeriodOutcomeFinalGeometry10868.arrangement(width: 640, idealWidths: short, spacing: 10,
                                                                 distribution: .equal, accessibilitySize: true),
                       .stacked, "accessibility sizes always stack")
    }
}
