import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the combat duration card as a stateless presentation leaf across
/// before, during and after the fight.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: which readings and marks each phase shows, the
/// independence of every original side and its window, zero versus unknown,
/// the exact-id selection and lead side, the action each control carries, the
/// tile and side-row placement the View branches on, the timing it may show,
/// the rail, column and pair geometry and the spoken text. Nothing here claims
/// a rendered fit, a native runtime or a populated boxing case.
///
/// ARCHIVED raw values come from Gautier–Kopylov, event 15318681 (mma), as
/// retained in `shipping-adoption-20261027/COMBAT-DURATION-RETAINED-CASES.json`
/// (sha256 41f55e11…2a3b). Six markets, nine originals, every pre-match quote
/// at 2026-10-03T23:27:48.847758Z (consensus):
///   O/U 0.5 Rounds 63786877   Over  240262502 0.825 Won
///   O/U 1.5 Rounds 63254895   Under 238409899 0.375 Result unconfirmed (raw false / detail true)
///   O/U 2.5 Rounds 63455521   Under 239081307 0.55  Result unconfirmed (raw false / detail true)
///   Before Round 2 63786880   Yes 240262508 0.325 Won;  No 240262509 0.675 Lost
///   Before Round 3 63786881   Yes 240262510 0.53  Won;  No 240262511 0.47  Lost
///   Go the distance 63254894  Yes 238409896 0.37  Lost; No 238409897 0.63  Won
///   Only one totals side of each O/U market was captured; no opposite side
///   exists in the packet. The raw totals `over_probability` for O/U 1.5 and
///   O/U 2.5 is 0.0 — an OVER-axis settlement-time display field, not the Under
///   side's chance. The settlement-time 1.0 / 0.0 quotes are not baselines.
///   Approved windows in round units (start, end, final bell): Over ½ 0.5–3;
///   Under 1½ 0–1.5; Under 2½ 0–2.5; Before Round 2 Yes 0–1 / No 1–3; Before
///   Round 3 Yes 0–2 / No 2–3; Go the distance Yes 3–3 included / No 0–3
///   excluded. No admitted in-fight chance is retained. The raw event stays
///   suspended. Later official UFC evidence: Kopylov def. Gautier, TKO
///   (strikes), Round 1, 3:12, absoluteFinishAt null — separate context, never
///   a contract grade and never a point on a rail.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// round schedule and its labels, every display string, PT time and
/// provenance line, the final-bell, result, result-detail and unavailable
/// words, the official-context wording, every in-fight observation, movement
/// line and observed round, held/withdrawn/duplicate updates, phase arrivals,
/// zero, malformed, long-label and other-schedule cases, and every measured
/// width.
final class CombatDurationPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static let eventID = "15318681"

    private static let overID = "63786877"
    private static let u15ID = "63254895"
    private static let u25ID = "63455521"
    private static let r2ID = "63786880"
    private static let r3ID = "63786881"
    private static let distID = "63254894"

    private static let overSide = "240262502"
    private static let u15Side = "238409899"
    private static let u25Side = "239081307"
    private static let r2Yes = "240262508"
    private static let r2No = "240262509"
    private static let r3Yes = "240262510"
    private static let r3No = "240262511"
    private static let distYes = "238409896"
    private static let distNo = "238409897"

    /// ARCHIVED shared pre-start clock.
    private static let clock = "2026-10-03T23:27:48.847758+00:00"

    private struct Retained {
        let marketID: String
        let outcomeID: String
        let side: String
        /// ARCHIVED.
        let probability: Double
        let result: String
        let windowLabel: String
        let start: Double
        let end: Double
        let bell: String?
        /// CONSTRUCTED owner text.
        let text: String
    }

    private static let retained: [Retained] = [
        Retained(marketID: overID, outcomeID: overSide, side: "Over", probability: 0.825, result: "Won", windowLabel: "Over ½ round", start: 0.5, end: 3, bell: nil, text: "82.5%"),
        Retained(marketID: u15ID, outcomeID: u15Side, side: "Under", probability: 0.375, result: "Result unconfirmed", windowLabel: "Under 1½ rounds", start: 0, end: 1.5, bell: nil, text: "37.5%"),
        Retained(marketID: u25ID, outcomeID: u25Side, side: "Under", probability: 0.55, result: "Result unconfirmed", windowLabel: "Under 2½ rounds", start: 0, end: 2.5, bell: nil, text: "55%"),
        Retained(marketID: r2ID, outcomeID: r2Yes, side: "Yes", probability: 0.325, result: "Won", windowLabel: "Before Round 2", start: 0, end: 1, bell: nil, text: "32.5%"),
        Retained(marketID: r2ID, outcomeID: r2No, side: "No", probability: 0.675, result: "Lost", windowLabel: "Round 2 or later", start: 1, end: 3, bell: nil, text: "67.5%"),
        Retained(marketID: r3ID, outcomeID: r3Yes, side: "Yes", probability: 0.53, result: "Won", windowLabel: "Before Round 3", start: 0, end: 2, bell: nil, text: "53%"),
        Retained(marketID: r3ID, outcomeID: r3No, side: "No", probability: 0.47, result: "Lost", windowLabel: "Round 3 or later", start: 2, end: 3, bell: nil, text: "47%"),
        Retained(marketID: distID, outcomeID: distYes, side: "Yes", probability: 0.37, result: "Lost", windowLabel: "Reaches final bell", start: 3, end: 3, bell: "included", text: "37%"),
        Retained(marketID: distID, outcomeID: distNo, side: "No", probability: 0.63, result: "Won", windowLabel: "Ends before final bell", start: 0, end: 3, bell: "excluded", text: "63%"),
    ]

    /// ARCHIVED raw totals OVER-axis display values (settlement time).
    private static let rawOverAxis: [String: Double] = [u15Side: 0.0, u25Side: 0.0, overSide: 1.0]

    private static let detail = "Last recorded before start · Oct 3, 4:27 PM PT · Polymarket"
    private static let noCurrent = CombatDurationCurrent10868.unavailable("No in-fight chance")
    private static let notRecorded = "Not recorded before start"
    private static let noWindow = "Time window unavailable"
    private static let conflict = "The game-prop capture and the market detail disagree on this side."
    private static let bellIncluded = "Includes the final bell"
    private static let bellExcluded = "Ends before the final bell"
    private static let unconfirmed = "Result unconfirmed"

    private static let threeRounds = [
        CombatDurationSegment10868(id: "r1", shortLabel: "R1", spokenLabel: "Round 1"),
        CombatDurationSegment10868(id: "r2", shortLabel: "R2", spokenLabel: "Round 2"),
        CombatDurationSegment10868(id: "r3", shortLabel: "R3", spokenLabel: "Round 3"),
    ]

    private static func rounds(_ count: Int) -> [CombatDurationSegment10868] {
        (1...count).map { CombatDurationSegment10868(id: "r\($0)", shortLabel: "R\($0)", spokenLabel: "Round \($0)") }
    }

    private static func obs(_ probability: Double, _ text: String, _ time: String?, _ detail: String) -> CombatDurationObservation10868 {
        CombatDurationObservation10868(probability: probability, text: text, timeText: time, detail: detail)
    }

    private static func pregame(_ row: Retained) -> CombatDurationObservation10868 {
        obs(row.probability, row.text, "4:27 PM PT", detail)
    }

    private static func grade(_ word: String) -> CombatDurationResult10868 {
        switch word {
        case "Won": .won("Won")
        case "Lost": .lost("Lost")
        default: .unconfirmed(word)
        }
    }

    private static func window(_ row: Retained) -> CombatDurationWindow10868 {
        let bell: CombatDurationFinalBell10868?
        switch row.bell {
        case "included"?: bell = .included(bellIncluded)
        case "excluded"?: bell = .excluded(bellExcluded)
        default: bell = nil
        }
        return CombatDurationWindow10868(label: row.windowLabel, start: row.start, end: row.end, finalBell: bell)
    }

    private static func row(_ id: String) -> Retained {
        retained.first { $0.outcomeID == id }!
    }

    private static func original(
        _ id: String,
        before: CombatDurationObservation10868?? = nil,
        current: CombatDurationCurrent10868 = noCurrent,
        result: CombatDurationResult10868? = nil,
        window supplied: CombatDurationWindow10868?? = nil
    ) -> CombatDurationOriginal10868 {
        let source = Self.row(id)
        let reading: CombatDurationObservation10868?
        switch before {
        case .some(let value): reading = value
        case .none: reading = pregame(source)
        }
        let span: CombatDurationWindow10868?
        switch supplied {
        case .some(let value): span = value
        case .none: span = window(source)
        }
        let resolved = result ?? grade(source.result)
        let qualified: String?
        if case .unconfirmed = resolved, source.result == unconfirmed { qualified = conflict } else { qualified = nil }
        return CombatDurationOriginal10868(
            id: id,
            marketID: source.marketID,
            label: source.side,
            window: span,
            windowMissing: noWindow,
            before: reading,
            beforeMissing: notRecorded,
            current: current,
            result: resolved,
            resultDetail: qualified
        )
    }

    private static func market(
        _ id: String,
        _ originals: [CombatDurationOriginal10868],
        overview: String? = nil
    ) -> CombatDurationMarket10868 {
        let names: (String, String)
        switch id {
        case overID: names = ("Over ½ round", "O/U 0.5 Rounds")
        case u15ID: names = ("Under 1½ rounds", "O/U 1.5 Rounds")
        case u25ID: names = ("Under 2½ rounds", "O/U 2.5 Rounds")
        case r2ID: names = ("Before Round 2", "Will the fight end before Round 2?")
        case r3ID: names = ("Before Round 3", "Will the fight end before Round 3?")
        default: names = ("Go the distance", "Fight to Go the Distance?")
        }
        return CombatDurationMarket10868(id: id, label: names.0, question: names.1, originals: originals, overviewOriginalID: overview)
    }

    /// The six retained markets in the owner's order, results supplied (each
    /// phase decides what shows).
    private static func retainedMarkets(overview: [String: String] = [:]) -> [CombatDurationMarket10868] {
        [
            market(overID, [original(overSide)], overview: overview[overID]),
            market(u15ID, [original(u15Side)], overview: overview[u15ID]),
            market(u25ID, [original(u25Side)], overview: overview[u25ID]),
            market(r2ID, [original(r2Yes), original(r2No)], overview: overview[r2ID]),
            market(r3ID, [original(r3Yes), original(r3No)], overview: overview[r3ID]),
            market(distID, [original(distYes), original(distNo)], overview: overview[distID]),
        ]
    }

    /// CONSTRUCTED wording of the ARCHIVED UFC reference; no finish clock exists.
    private static let official = CombatDurationFinish10868(
        segmentID: "r1",
        markerWords: "Finished in Round 1",
        title: "Official bout result",
        lines: ["Roman Kopylov def. Ateba Gautier · TKO (strikes) · Round 1, 3:12"],
        accessibilityDetail: "UFC results page, captured Oct 13 · finish clock not recorded"
    )

    /// CONSTRUCTED owner-observed round.
    private static let roundTwo = CombatDurationObserved10868(segmentID: "r2", words: "Round 2 in progress")

    private static func input(
        _ phase: CombatDurationPhase10868,
        _ markets: [CombatDurationMarket10868] = retainedMarkets(),
        market: String? = r2ID,
        original: String? = r2Yes,
        segments: [CombatDurationSegment10868] = threeRounds,
        observed: CombatDurationObserved10868? = nil,
        finish: CombatDurationFinish10868? = official,
        timing: CombatDurationTiming10868? = nil
    ) -> CombatDurationInput10868 {
        CombatDurationInput10868(
            phase: phase,
            eventID: eventID,
            eyebrow: "Polymarket · contract results",
            title: "How long could the fight last?",
            caption: "Pre-match chances · select a tile for its quote time",
            segments: segments,
            markets: markets,
            selectedMarketID: market,
            selectedOriginalID: original,
            observed: observed,
            finish: finish,
            timing: timing
        )
    }

    /// CONSTRUCTED admitted in-fight observation (the packet retains none).
    private static let r2YesCurrent = obs(0.71, "71%", "5:31 PM PT", "Recorded Oct 3, 5:31 PM PT · Polymarket")

    /// Every later input supplied, to prove the earlier phases hide them.
    private static var everythingSupplied: [CombatDurationMarket10868] {
        [
            market(overID, [original(overSide)]),
            market(u15ID, [original(u15Side)]),
            market(u25ID, [original(u25Side)]),
            market(r2ID, [
                original(r2Yes, current: .recorded(r2YesCurrent, movement: "+38.5 points since pre-match")),
                original(r2No, current: .withheld("Held since round 1")),
            ]),
            market(r3ID, [original(r3Yes), original(r3No)]),
            market(distID, [original(distYes), original(distNo)]),
        ]
    }

    private static func allOriginals(_ model: CombatDurationInput10868) -> [(CombatDurationMarket10868, CombatDurationOriginal10868)] {
        model.markets.flatMap { market in market.originals.map { (market, $0) } }
    }

    private static func ref(_ marketID: String, _ originalID: String) -> CombatDurationOriginalRef10868 {
        CombatDurationOriginalRef10868(eventID: eventID, durationMarketID: marketID, marketID: row(originalID).marketID, originalID: originalID)
    }

    private static func fill(_ from: Double, _ to: Double) -> CombatDurationFill10868 {
        CombatDurationFill10868(from: from, to: to)
    }

    private static let whole = fill(0, 1)

    /// The spoken window of each retained original on the three-round schedule.
    private static let spokenWindow: [String: String] = [
        overSide: "Over ½ round. Shaded: part of Round 1, Round 2, Round 3",
        u15Side: "Under 1½ rounds. Shaded: Round 1, part of Round 2",
        u25Side: "Under 2½ rounds. Shaded: Round 1, Round 2, part of Round 3",
        r2Yes: "Before Round 2. Shaded: Round 1",
        r2No: "Round 2 or later. Shaded: Round 2, Round 3",
        r3Yes: "Before Round 3. Shaded: Round 1, Round 2",
        r3No: "Round 3 or later. Shaded: Round 3",
        distYes: "Reaches final bell. Includes the final bell",
        distNo: "Ends before final bell. Shaded: Round 1, Round 2, Round 3. Ends before the final bell",
    ]

    private static let phases: [CombatDurationPhase10868] = [.before, .during, .final]

    private static func listed(_ market: CombatDurationMarket10868, _ originals: [CombatDurationOriginal10868], actionable: Bool) -> [CombatDurationTileSide10868] {
        originals.map { CombatDurationTileSide10868(original: $0, action: actionable ? .select(ref(market.id, $0.id)) : nil) }
    }

    /// What a side row speaks after its window and pre-match chance, per phase.
    private static func later(_ phase: CombatDurationPhase10868, _ id: String, detailed: Bool) -> String {
        switch phase {
        case .before: return ""
        case .during: return "; In-fight chance: No in-fight chance"
        case .final:
            let source = row(id)
            if source.result == unconfirmed, detailed { return "; Contract result: \(unconfirmed), \(conflict)" }
            return "; Contract result: \(source.result)"
        }
    }

    // MARK: The nine retained originals

    func testNineRetainedOriginalsKeepExactIdsOrderSidesAndOwnBaselines() {
        let model = Self.input(.before)
        XCTAssertEqual(model.markets.map(\.id), [Self.overID, Self.u15ID, Self.u25ID, Self.r2ID, Self.r3ID, Self.distID])
        XCTAssertEqual(model.markets.map(\.label), ["Over ½ round", "Under 1½ rounds", "Under 2½ rounds", "Before Round 2", "Before Round 3", "Go the distance"])
        XCTAssertEqual(model.markets.map(\.question), ["O/U 0.5 Rounds", "O/U 1.5 Rounds", "O/U 2.5 Rounds", "Will the fight end before Round 2?", "Will the fight end before Round 3?", "Fight to Go the Distance?"])
        XCTAssertEqual(Self.allOriginals(model).map { $0.1.id }, Self.retained.map(\.outcomeID))
        XCTAssertEqual(Self.allOriginals(model).map { $0.1.label }, ["Over", "Under", "Under", "Yes", "No", "Yes", "No", "Yes", "No"])
        XCTAssertEqual(Self.allOriginals(model).map { $0.1.marketID }, Self.retained.map(\.marketID))
        for (market, original) in Self.allOriginals(model) {
            let source = Self.row(original.id)
            XCTAssertEqual(source.marketID, market.id, original.id)
            guard case .value(let reading) = model.beforeReading(original) else { return XCTFail(original.id) }
            XCTAssertEqual(reading.probability, source.probability, original.id)
            XCTAssertEqual(reading.text, source.text, original.id)
            XCTAssertEqual(reading.detail, Self.detail, original.id)
            // No settlement-time 1.0 / 0.0 quote is a baseline.
            XCTAssertNotEqual(reading.probability, 1.0, original.id)
            XCTAssertNotEqual(reading.probability, 0.0, original.id)
        }
        XCTAssertEqual(Self.retained.count, 9)
    }

    func testOnlyTheThreeCapturedTotalsSidesExistAndNoOppositeIsFabricated() {
        for phase in Self.phases {
            let model = Self.input(phase, market: nil, original: nil)
            for market in model.markets.prefix(3) {
                XCTAssertEqual(market.originals.count, 1, "\(phase) \(market.id)")
                // Listed alone, never beside an invented Over or Under.
                XCTAssertEqual(model.lead(market), .sides, "\(phase)")
                XCTAssertEqual(model.tilePresentation(market, canSelect: true), .sides(Self.listed(market, market.originals, actionable: true)))
                let spoken = model.accessibilityTileValue(market)
                XCTAssertTrue(spoken.hasSuffix(CombatDurationInput10868.singleOriginalNote), "\(phase) \(market.id)")
                let opposite = market.originals[0].label == "Over" ? "Under." : "Over."
                XCTAssertFalse(spoken.contains(opposite), "\(phase) \(market.id)")
            }
            // Selecting the captured Under says only that original was captured.
            let selected = Self.input(phase, market: Self.u15ID, original: Self.u15Side)
            XCTAssertTrue(selected.showsSingleOriginalNote)
            XCTAssertEqual(selected.panelSides(selected.markets[1], canSelect: true), Self.listed(selected.markets[1], selected.markets[1].originals, actionable: true))
            // A Yes / No pair carries no such note.
            XCTAssertFalse(Self.input(phase).showsSingleOriginalNote)
        }
    }

    func testUnderShowsItsOwnChanceNotTheOverAxisValueOrItsComplement() {
        let model = Self.input(.final, market: Self.u15ID, original: Self.u15Side)
        for id in [Self.u15Side, Self.u25Side] {
            let original = Self.allOriginals(model).first { $0.1.id == id }!.1
            guard case .value(let reading) = model.beforeReading(original) else { return XCTFail(id) }
            let axis = Self.rawOverAxis[id]!
            XCTAssertEqual(reading.probability, Self.row(id).probability, id)
            XCTAssertNotEqual(reading.probability, axis, id)
            XCTAssertNotEqual(reading.probability, 1 - axis, id)
            XCTAssertNotEqual(reading.text, "0%", id)
            XCTAssertNotEqual(reading.text, "100%", id)
        }
        XCTAssertEqual(
            model.accessibilityComparison,
            "O/U 1.5 Rounds, original Under. Time window: \(Self.spokenWindow[Self.u15Side]!); Pre-match chance: 37.5%, \(Self.detail); Contract result: \(Self.unconfirmed), \(Self.conflict)"
        )
    }

    func testYesAndNoKeepIndependentBaselinesAndNeverAComplement() {
        let model = Self.input(.before, market: Self.r3ID, original: Self.r3No)
        let r3 = model.markets[4]
        XCTAssertEqual(model.lead(r3), .original(r3.originals[1], selected: true))
        XCTAssertEqual(model.beforeReading(r3.originals[1]), .value(Self.pregame(Self.row(Self.r3No))))

        // CONSTRUCTED: a No with no recorded baseline stays words, never 1 − 0.53.
        let missingNo = Self.input(.before, [Self.market(Self.r3ID, [Self.original(Self.r3Yes), Self.original(Self.r3No, before: .some(nil))])], market: Self.r3ID, original: Self.r3No)
        let no = missingNo.markets[0].originals[1]
        XCTAssertEqual(missingNo.beforeReading(no), .missing(Self.notRecorded))
        XCTAssertFalse(missingNo.accessibilityTileValue(missingNo.markets[0]).contains("47%"))

        // CONSTRUCTED: sides that do not complement keep their own values.
        let skew = Self.input(.before, [Self.market(Self.r3ID, [Self.original(Self.r3Yes), Self.original(Self.r3No, before: .some(Self.obs(0.5, "50%", "4:27 PM PT", Self.detail)))])], market: Self.r3ID, original: Self.r3No)
        guard case .value(let reading) = skew.beforeReading(skew.markets[0].originals[1]) else { return XCTFail("skew") }
        XCTAssertEqual(reading.probability, 0.5)
        XCTAssertNotEqual(reading.probability, 1 - 0.53, accuracy: 1e-9)
    }

    // MARK: Windows and the rail

    func testOwnerWindowsShadeTheirOwnRoundsOnTheRail() {
        let model = Self.input(.before)
        let expected: [String: CombatDurationRail10868] = [
            Self.overSide: .shaded([Self.fill(0.5, 1), Self.whole, Self.whole]),
            Self.u15Side: .shaded([Self.whole, Self.fill(0, 0.5), nil]),
            Self.u25Side: .shaded([Self.whole, Self.whole, Self.fill(0, 0.5)]),
            Self.r2Yes: .shaded([Self.whole, nil, nil]),
            Self.r2No: .shaded([nil, Self.whole, Self.whole]),
            Self.r3Yes: .shaded([Self.whole, Self.whole, nil]),
            Self.r3No: .shaded([nil, nil, Self.whole]),
            Self.distYes: .zeroLength,
            Self.distNo: .shaded([Self.whole, Self.whole, Self.whole]),
        ]
        for (_, original) in Self.allOriginals(model) {
            XCTAssertEqual(model.rail(original), expected[original.id], original.id)
            XCTAssertEqual(model.accessibilityWindow(original), Self.spokenWindow[original.id], original.id)
        }
        // A Yes and its No shade different rounds: each side its own window.
        XCTAssertNotEqual(model.rail(model.markets[3].originals[0]), model.rail(model.markets[3].originals[1]))
        XCTAssertNil(CombatDurationRail10868.shaded([Self.whole, nil]).fill(at: 1))
        XCTAssertNil(CombatDurationRail10868.shaded([Self.whole]).fill(at: 5))
        XCTAssertEqual(CombatDurationRail10868.shaded([Self.whole]).fill(at: 0), Self.whole)
        XCTAssertNil(CombatDurationRail10868.zeroLength.fill(at: 0))
    }

    func testFinalBellIsASymbolPlusWordsAndAZeroLengthWindowIsNotEmpty() {
        XCTAssertEqual(CombatDurationFinalBell10868.included(Self.bellIncluded).symbolName, "bell.fill")
        XCTAssertEqual(CombatDurationFinalBell10868.excluded(Self.bellExcluded).symbolName, "bell.slash")
        XCTAssertEqual(CombatDurationFinalBell10868.included(Self.bellIncluded).text, Self.bellIncluded)
        let model = Self.input(.before, market: Self.distID, original: Self.distYes)
        let yes = model.markets[5].originals[0]
        let no = model.markets[5].originals[1]
        XCTAssertEqual(yes.window?.finalBell, .included(Self.bellIncluded))
        XCTAssertEqual(no.window?.finalBell, .excluded(Self.bellExcluded))
        // Reaching the final bell is a moment: nothing shaded, and nothing calls it empty.
        XCTAssertEqual(model.rail(yes), .zeroLength)
        XCTAssertFalse(model.accessibilityWindow(yes).contains(CombatDurationInput10868.noRoundShaded))
        XCTAssertFalse(model.accessibilityWindow(yes).contains(CombatDurationInput10868.windowNotDrawn))
        XCTAssertEqual(model.tileTitle(model.markets[5]), "Reaches final bell")
        // CONSTRUCTED: a zero-length window with no bell is said plainly.
        let bare = Self.original(Self.distYes, window: .some(CombatDurationWindow10868(label: "At the end of Round 1", start: 1, end: 1, finalBell: nil)))
        let bareModel = Self.input(.before, [Self.market(Self.distID, [bare, Self.original(Self.distNo)])], market: nil, original: nil)
        XCTAssertEqual(bareModel.accessibilityWindow(bare), "At the end of Round 1. \(CombatDurationInput10868.noRoundShaded)")
    }

    func testShadingIsTheWindowNeverTheChanceOrTheResult() {
        // CONSTRUCTED: the same window with a different chance and result draws
        // the same rail.
        let a = Self.original(Self.r2No)
        let b = Self.original(Self.r2No, before: .some(Self.obs(0.1, "10%", nil, Self.detail)), result: .won("Won"))
        let model = Self.input(.final, [Self.market(Self.r2ID, [a]), Self.market(Self.r3ID, [b])], market: nil, original: nil)
        XCTAssertEqual(model.rail(a), model.rail(b))
        XCTAssertEqual(model.accessibilityWindow(a), model.accessibilityWindow(b))
        XCTAssertTrue(CombatDurationInput10868.windowKey.contains("not its chance, time elapsed or a winner"))
        // No proved window: nothing shaded, the owner's words stay, the market label titles the tile.
        let unproved = Self.original(Self.r2Yes, window: .some(nil))
        let missing = Self.input(.before, [Self.market(Self.r2ID, [unproved, Self.original(Self.r2No)])], market: Self.r2ID, original: Self.r2Yes)
        XCTAssertEqual(missing.rail(unproved), .undrawn)
        XCTAssertEqual(missing.accessibilityWindow(unproved), Self.noWindow)
        XCTAssertEqual(missing.tileTitle(missing.markets[0]), "Before Round 2")
        XCTAssertFalse(missing.showsWindowLabel(unproved, inTileOf: nil))
    }

    func testAnOwnerScheduleOfAnyLengthHasNoThreeRoundCeiling() {
        // CONSTRUCTED five-round schedule: the same owner span reaches rounds 4 and 5.
        let five = Self.input(.before, [Self.market(Self.u25ID, [Self.original(Self.u25Side, window: .some(CombatDurationWindow10868(label: "Over 3½ rounds", start: 3.5, end: 5, finalBell: nil)))])], market: nil, original: nil, segments: Self.rounds(5))
        XCTAssertEqual(five.rail(five.markets[0].originals[0]), .shaded([nil, nil, nil, Self.fill(0.5, 1), Self.whole]))
        XCTAssertEqual(five.accessibilityWindow(five.markets[0].originals[0]), "Over 3½ rounds. Shaded: part of Round 4, Round 5")
        // CONSTRUCTED twelve-round schedule.
        XCTAssertEqual(CombatDurationGeometry10868.rail(start: 0, end: 12, segments: 12), .shaded(Array(repeating: Self.whole, count: 12)))
        // The retained three-round windows do not fit a two-round schedule and are not clipped.
        let two = Self.input(.before, segments: Self.rounds(2))
        XCTAssertEqual(two.rail(two.markets[0].originals[0]), .undrawn)
        XCTAssertEqual(two.rail(two.markets[3].originals[0]), .shaded([Self.whole, nil]))
    }

    func testMalformedOrAbsentGeometryDrawsNothingAndKeepsTheWords() {
        let bad: [(Double, Double, Int)] = [
            (.nan, 1, 3), (0, .nan, 3), (0, .infinity, 3), (-0.5, 1, 3), (0, 3.5, 3), (2, 1, 3), (0, 1, 0), (0, 0, 0), (0, 1, -1),
        ]
        for (start, end, segments) in bad {
            XCTAssertEqual(CombatDurationGeometry10868.rail(start: start, end: end, segments: segments), .undrawn, "\(start) \(end) \(segments)")
        }
        XCTAssertEqual(CombatDurationGeometry10868.rail(start: 0, end: 0, segments: 3), .zeroLength)
        XCTAssertEqual(CombatDurationGeometry10868.rail(start: 3, end: 3, segments: 3), .zeroLength)
        XCTAssertEqual(CombatDurationGeometry10868.rail(start: 0, end: 3, segments: 3), .shaded([Self.whole, Self.whole, Self.whole]))
        // CONSTRUCTED reversed window keeps its label and says it is not drawn.
        let reversed = Self.original(Self.r2Yes, window: .some(CombatDurationWindow10868(label: "Before Round 2", start: 1, end: 0, finalBell: nil)))
        let model = Self.input(.before, [Self.market(Self.r2ID, [reversed, Self.original(Self.r2No)])], market: nil, original: nil)
        XCTAssertEqual(model.accessibilityWindow(reversed), "Before Round 2. \(CombatDurationInput10868.windowNotDrawn)")
        // No schedule: nothing shaded on any original, every label stays.
        let unscheduled = Self.input(.before, segments: [])
        for (_, original) in Self.allOriginals(unscheduled) {
            XCTAssertEqual(unscheduled.rail(original), .undrawn, original.id)
            XCTAssertTrue(unscheduled.accessibilityWindow(original).hasPrefix(Self.row(original.id).windowLabel), original.id)
        }
    }

    // MARK: Lead side, title and held updates

    func testTileLeadsWithHostSideThenOverviewThenListsEverySide() {
        let overview = [Self.r2ID: Self.r2Yes, Self.r3ID: Self.r3No]
        let model = Self.input(.before, Self.retainedMarkets(overview: overview), market: Self.r2ID, original: Self.r2No)
        // Host-selected side wins over the overview side.
        XCTAssertEqual(model.lead(model.markets[3]), .original(model.markets[3].originals[1], selected: true))
        // The overview side is shown but not selected.
        XCTAssertEqual(model.lead(model.markets[4]), .original(model.markets[4].originals[1], selected: false))
        // No overview and no selection: every side, none chosen.
        XCTAssertEqual(model.lead(model.markets[5]), .sides)
        XCTAssertNil(model.tileAction(model.markets[5], canSelect: true))
        for original in model.markets[5].originals {
            XCTAssertEqual(model.sideAction(original, in: model.markets[5], canSelect: true), .select(Self.ref(Self.distID, original.id)))
        }
    }

    func testTileTitleIsTheLeadWindowLabelElseTheMarketLabel() {
        let picked = Self.input(.before, market: Self.r2ID, original: Self.r2No)
        XCTAssertEqual(picked.tileTitle(picked.markets[3]), "Round 2 or later")
        XCTAssertEqual(picked.tileTitle(picked.markets[5]), "Go the distance")
        let overview = Self.input(.before, Self.retainedMarkets(overview: [Self.distID: Self.distNo]), market: nil, original: nil)
        XCTAssertEqual(overview.tileTitle(overview.markets[5]), "Ends before final bell")
        let withdrawn = Self.input(.before, market: Self.r2ID, original: "999")
        XCTAssertEqual(withdrawn.tileTitle(withdrawn.markets[3]), "Before Round 2")
    }

    func testHeldUpdateNeverSwitchesTheLeadSide() {
        // CONSTRUCTED arrival: the selected No's in-fight state changes; it stays the lead.
        let first = Self.input(.during, market: Self.r2ID, original: Self.r2No)
        let updated = Self.input(.during, Self.everythingSupplied, market: Self.r2ID, original: Self.r2No)
        for model in [first, updated] {
            guard case .original(let lead, selected: true) = model.lead(model.markets[3]) else { return XCTFail("lead") }
            XCTAssertEqual(lead.id, Self.r2No)
            XCTAssertEqual(model.rail(lead), .shaded([nil, Self.whole, Self.whole]))
        }
        // CONSTRUCTED withdrawal: the selected No leaves the update. Unavailable, never Yes.
        let withdrawn = Self.input(.during, [Self.market(Self.r2ID, [Self.original(Self.r2Yes)], overview: Self.r2Yes)], market: Self.r2ID, original: Self.r2No)
        XCTAssertEqual(withdrawn.selection, .sideUnavailable(withdrawn.markets[0], Self.r2No))
        XCTAssertEqual(withdrawn.lead(withdrawn.markets[0]), .unavailable(CombatDurationInput10868.sideUnavailableShort))
        XCTAssertEqual(withdrawn.selectionNotice, CombatDurationInput10868.sideUnavailable)
        XCTAssertNil(withdrawn.comparison)
        XCTAssertNil(withdrawn.tileAction(withdrawn.markets[0], canSelect: true))
        XCTAssertNil(withdrawn.detailsAction(canOpenDetails: true))
        XCTAssertTrue(withdrawn.isSelectedMarket(withdrawn.markets[0]))
        XCTAssertEqual(withdrawn.panelSides(withdrawn.markets[0], canSelect: true), Self.listed(withdrawn.markets[0], withdrawn.markets[0].originals, actionable: true))
    }

    // MARK: Before

    func testBeforeSuppressesInFightResultsMarksAndFinishContext() {
        let model = Self.input(.before, Self.everythingSupplied, observed: Self.roundTwo)
        for (_, original) in Self.allOriginals(model) {
            XCTAssertNil(model.currentReading(original), original.id)
            XCTAssertNil(model.movement(original), original.id)
            XCTAssertNil(model.result(original), original.id)
            XCTAssertNil(model.resultDetail(original), original.id)
            XCTAssertFalse(model.showsCurrentMark(original), original.id)
        }
        XCTAssertNil(model.observedMark)
        XCTAssertNil(model.finishMark)
        XCTAssertNil(model.visibleFinish)
        XCTAssertNil(model.accessibilityFinish)
        XCTAssertEqual(model.keyItems, [.window])
        XCTAssertEqual(model.accessibilityKey, CombatDurationInput10868.windowKey)
        XCTAssertEqual(model.comparison, .before(model.markets[3].originals[0]))
        let spoken = model.markets.map { model.accessibilityTileValue($0) }.joined(separator: " | ")
            + " | " + (model.accessibilityComparison ?? "")
            + " | " + model.markets.flatMap { market in market.originals.map { model.accessibilitySideValue($0, in: market) } }.joined(separator: " | ")
        for later in ["Won", "Lost", "unconfirmed", "disagree", "In-fight", "71%", "Held", "+38.5", "Kopylov", "Finished", "3:12", "in progress", "Contract result"] {
            XCTAssertFalse(spoken.contains(later), later)
        }
        XCTAssertTrue(model.accessibilityHeader.hasSuffix("Before the fight"))
    }

    func testBeforeSpokenTileAndComparisonCarryWindowPreMatchAndProvenance() {
        let model = Self.input(.before)
        XCTAssertEqual(
            model.accessibilityTileValue(model.markets[3]),
            "Yes. Time window: Before Round 2. Shaded: Round 1; Pre-match chance: 32.5%, \(Self.detail). Selected. Also No. Time window: Round 2 or later. Shaded: Round 2, Round 3; Pre-match chance: 67.5%"
        )
        XCTAssertEqual(
            model.accessibilityTileValue(model.markets[1]),
            "Under. Time window: Under 1½ rounds. Shaded: Round 1, part of Round 2; Pre-match chance: 37.5%. \(CombatDurationInput10868.singleOriginalNote)"
        )
        XCTAssertEqual(
            model.accessibilityTileValue(model.markets[5]),
            "Yes. Time window: Reaches final bell. Includes the final bell; Pre-match chance: 37%. No. Time window: Ends before final bell. Shaded: Round 1, Round 2, Round 3. Ends before the final bell; Pre-match chance: 63%"
        )
        XCTAssertEqual(
            model.accessibilityComparison,
            "Will the fight end before Round 2?, original Yes. Time window: Before Round 2. Shaded: Round 1; Pre-match chance: 32.5%, \(Self.detail)"
        )
    }

    // MARK: During

    func testDuringRetainedPacketHasNoInFightChanceAndShowsWords() {
        let model = Self.input(.during)
        for (_, original) in Self.allOriginals(model) {
            XCTAssertEqual(model.currentReading(original), .missing("No in-fight chance"), original.id)
            XCTAssertFalse(model.showsCurrentMark(original), original.id)
            XCTAssertNil(model.result(original), original.id)
            // Missing never substitutes the pre-match figure.
            XCTAssertNotEqual(model.currentReading(original), .value(Self.pregame(Self.row(original.id))), original.id)
        }
        XCTAssertEqual(model.comparison, .during(model.markets[3].originals[0]))
        XCTAssertTrue(model.accessibilityHeader.hasSuffix("During the fight"))
    }

    func testDuringComparesPreMatchAndInFightWithEachProvenance() {
        let model = Self.input(.during, Self.everythingSupplied)
        let yes = model.markets[3].originals[0]
        let no = model.markets[3].originals[1]
        XCTAssertEqual(model.beforeReading(yes), .value(Self.pregame(Self.row(Self.r2Yes))))
        XCTAssertEqual(model.currentReading(yes), .value(Self.r2YesCurrent))
        XCTAssertTrue(model.showsCurrentMark(yes))
        XCTAssertEqual(model.movement(yes), "+38.5 points since pre-match")
        // Withheld stays words, has no filled key and never falls back to pre-match.
        XCTAssertEqual(model.currentReading(no), .missing("Held since round 1"))
        XCTAssertFalse(model.showsCurrentMark(no))
        XCTAssertNil(model.movement(no))
        XCTAssertEqual(
            model.accessibilityComparison,
            "Will the fight end before Round 2?, original Yes. Time window: Before Round 2. Shaded: Round 1; Pre-match chance: 32.5%, \(Self.detail); In-fight chance: 71%, Recorded Oct 3, 5:31 PM PT · Polymarket; +38.5 points since pre-match"
        )
        XCTAssertEqual(
            model.accessibilityTileValue(model.markets[3]),
            "Yes. Time window: Before Round 2. Shaded: Round 1; Pre-match chance: 32.5%, \(Self.detail); In-fight chance: 71%, Recorded Oct 3, 5:31 PM PT · Polymarket; +38.5 points since pre-match. Selected. Also No. Time window: Round 2 or later. Shaded: Round 2, Round 3; Pre-match chance: 67.5%; In-fight chance: Held since round 1"
        )
    }

    func testObservedRoundShowsOnlyDuringAndOnlyWhenSupplied() {
        XCTAssertNil(Self.input(.during).observedMark)
        let during = Self.input(.during, observed: Self.roundTwo, finish: nil)
        XCTAssertEqual(during.observedMark, CombatDurationMark10868(segmentIndex: 1, words: "Round 2 in progress"))
        XCTAssertEqual(during.keyItems, [.window, .observed(CombatDurationMark10868(segmentIndex: 1, words: "Round 2 in progress"))])
        XCTAssertEqual(during.accessibilityKey, "\(CombatDurationInput10868.windowKey). Round 2 in progress")
        // The observed round never changes a window or a reading.
        XCTAssertEqual(during.rail(during.markets[3].originals[0]), Self.input(.during, finish: nil).rail(during.markets[3].originals[0]))
        XCTAssertNil(Self.input(.before, observed: Self.roundTwo).observedMark)
        XCTAssertNil(Self.input(.final, observed: Self.roundTwo).observedMark)
        // An id that names no round, or two, keeps the words and marks nothing.
        let unknown = Self.input(.during, observed: CombatDurationObserved10868(segmentID: "r9", words: "Between rounds"), finish: nil)
        XCTAssertEqual(unknown.observedMark, CombatDurationMark10868(segmentIndex: nil, words: "Between rounds"))
        let twins = Self.input(.during, segments: Self.threeRounds + [CombatDurationSegment10868(id: "r2", shortLabel: "R2", spokenLabel: "Round 2")], observed: Self.roundTwo, finish: nil)
        XCTAssertNil(twins.observedMark?.segmentIndex)
    }

    func testPhaseIsTheOwnersAndSettledContractsDoNotMakeItFinal() {
        // The raw event is suspended while contracts are settled: an owner phase
        // of `.during` hides every supplied result.
        let model = Self.input(.during)
        for (_, original) in Self.allOriginals(model) {
            XCTAssertNil(model.result(original), original.id)
            XCTAssertNil(model.resultDetail(original), original.id)
        }
        XCTAssertFalse(model.accessibilityTileValue(model.markets[3]).contains("Won"))
        XCTAssertFalse(model.accessibilityTileValue(model.markets[1]).contains(Self.unconfirmed))
    }

    // MARK: Final

    func testFinalKeepsEachPreMatchBesideItsOwnIndependentResult() {
        let model = Self.input(.final)
        let expected: [String: (CombatDurationResult10868, String)] = [
            Self.overSide: (.won("Won"), "checkmark.circle"),
            Self.u15Side: (.unconfirmed(Self.unconfirmed), "questionmark.circle"),
            Self.u25Side: (.unconfirmed(Self.unconfirmed), "questionmark.circle"),
            Self.r2Yes: (.won("Won"), "checkmark.circle"),
            Self.r2No: (.lost("Lost"), "xmark.circle"),
            Self.r3Yes: (.won("Won"), "checkmark.circle"),
            Self.r3No: (.lost("Lost"), "xmark.circle"),
            Self.distYes: (.lost("Lost"), "xmark.circle"),
            Self.distNo: (.won("Won"), "checkmark.circle"),
        ]
        for (market, original) in Self.allOriginals(model) {
            XCTAssertEqual(model.result(original), expected[original.id]?.0, original.id)
            XCTAssertEqual(model.result(original)?.symbolName, expected[original.id]?.1, original.id)
            XCTAssertEqual(model.beforeReading(original), .value(Self.pregame(Self.row(original.id))), original.id)
            XCTAssertNil(model.currentReading(original), original.id)
            XCTAssertEqual(
                model.accessibilitySideValue(original, in: market),
                "Time window: \(Self.spokenWindow[original.id]!); Pre-match chance: \(Self.row(original.id).text), \(Self.detail)\(Self.later(.final, original.id, detailed: true))\(model.isSelected(original, in: market) ? "; Selected" : "")",
                original.id
            )
        }
        XCTAssertEqual(model.comparison, .final(model.markets[3].originals[0], .won("Won")))
        XCTAssertTrue(model.accessibilityHeader.hasSuffix("Final"))
    }

    func testContradictoryUnderGradesStayUnconfirmedAndAreNeverReadFromTheFinishRound() {
        // The official finish came in round 1, inside both Under windows. The
        // card still shows the owner's "Result unconfirmed" and its reason.
        for finish in [Self.official, nil, CombatDurationFinish10868(segmentID: "r3", markerWords: "Finished in Round 3", title: "Official bout result", lines: [], accessibilityDetail: nil)] {
            let model = Self.input(.final, market: Self.u25ID, original: Self.u25Side, finish: finish)
            for market in model.markets[1...2] {
                let under = market.originals[0]
                XCTAssertEqual(model.result(under), .unconfirmed(Self.unconfirmed), market.id)
                XCTAssertFalse(model.result(under)?.isSettled ?? true, market.id)
                XCTAssertEqual(model.resultDetail(under), Self.conflict, market.id)
                XCTAssertFalse(model.accessibilityTileValue(market).contains("Won"), market.id)
                XCTAssertFalse(model.accessibilityTileValue(market).contains("Lost"), market.id)
            }
            XCTAssertEqual(model.comparison, .final(model.markets[2].originals[0], .unconfirmed(Self.unconfirmed)))
        }
        // The tile speaks the word; the detailed side row and comparison add the reason.
        let model = Self.input(.final, market: nil, original: nil)
        XCTAssertTrue(model.accessibilityTileValue(model.markets[1]).contains("; Contract result: \(Self.unconfirmed). "))
        XCTAssertTrue(model.accessibilitySideValue(model.markets[1].originals[0], in: model.markets[1]).hasSuffix("; Contract result: \(Self.unconfirmed), \(Self.conflict)"))
    }

    func testFinalIgnoresSettledQuotesAsChances() {
        // CONSTRUCTED: a settlement-time 100 / 0 quote arrives as "current".
        let settled = Self.input(.final, [
            Self.market(Self.r2ID, [
                Self.original(Self.r2Yes, current: .recorded(Self.obs(1, "100%", nil, "Settlement"), movement: nil)),
                Self.original(Self.r2No, current: .recorded(Self.obs(0, "0%", nil, "Settlement"), movement: nil)),
            ]),
        ])
        for original in settled.markets[0].originals {
            XCTAssertNil(settled.currentReading(original), original.id)
            XCTAssertFalse(settled.showsCurrentMark(original), original.id)
        }
        let spoken = settled.accessibilityTileValue(settled.markets[0]) + (settled.accessibilityComparison ?? "")
        XCTAssertFalse(spoken.contains("100%"))
        XCTAssertFalse(spoken.contains("Settlement"))
        XCTAssertTrue(spoken.contains("32.5%"))
    }

    func testPairResultsAreIndependentAndTheSymbolFollowsTheDisplayedOriginal() {
        let model = Self.input(.final, market: Self.r2ID, original: Self.r2No)
        let no = model.markets[3].originals[1]
        XCTAssertEqual(model.comparison, .final(no, .lost("Lost")))
        XCTAssertEqual(model.result(no)?.symbolName, "xmark.circle")
        // CONSTRUCTED: the No's result unconfirmed while its Yes is Won — never
        // inferred from the partner.
        let partial = Self.input(.final, [Self.market(Self.r2ID, [Self.original(Self.r2Yes), Self.original(Self.r2No, result: .unconfirmed(Self.unconfirmed))])], market: Self.r2ID, original: Self.r2No)
        XCTAssertEqual(partial.result(partial.markets[0].originals[1]), .unconfirmed(Self.unconfirmed))
        XCTAssertEqual(partial.result(partial.markets[0].originals[0]), .won("Won"))
        // CONSTRUCTED: both sides Won as supplied — shown as supplied, never reconciled.
        let both = Self.input(.final, [Self.market(Self.r2ID, [Self.original(Self.r2Yes), Self.original(Self.r2No, result: .won("Won"))])], market: nil, original: nil)
        XCTAssertEqual(both.markets[0].originals.map { both.result($0) }, [.won("Won"), .won("Won")])
    }

    func testUnconfirmedVoidAndOtherAreNotLosses() {
        let results: [CombatDurationResult10868] = [.unconfirmed(Self.unconfirmed), .void("Void"), .other("Under review")]
        XCTAssertEqual(results.map(\.isSettled), [false, true, false])
        XCTAssertEqual(results.map(\.text), [Self.unconfirmed, "Void", "Under review"])
        for result in results {
            XCTAssertNotEqual(result.symbolName, CombatDurationResult10868.lost("Lost").symbolName)
        }
    }

    func testFinishMarksOnlyTheRoundAndStaysSeparateContext() {
        for phase in [CombatDurationPhase10868.during, .final] {
            let model = Self.input(phase, market: nil, original: nil)
            XCTAssertEqual(model.finishMark, CombatDurationMark10868(segmentIndex: 0, words: "Finished in Round 1"), "\(phase)")
            XCTAssertEqual(model.keyItems, [.window, .finish(CombatDurationMark10868(segmentIndex: 0, words: "Finished in Round 1"))], "\(phase)")
            XCTAssertEqual(model.visibleFinish, Self.official, "\(phase)")
            XCTAssertEqual(
                model.accessibilityFinish,
                "Official bout result. Roman Kopylov def. Ateba Gautier · TKO (strikes) · Round 1, 3:12. UFC results page, captured Oct 13 · finish clock not recorded"
            )
            // The elapsed time is the official context's words only — never a rail
            // position, tile reading or window.
            let tiles = model.markets.map { model.accessibilityTileValue($0) }.joined(separator: " | ")
                + model.markets.flatMap { $0.originals.map { model.accessibilityWindow($0) } }.joined(separator: " | ")
            XCTAssertFalse(tiles.contains("3:12"), "\(phase)")
            XCTAssertFalse(tiles.contains("Finished"), "\(phase)")
            // Rails are unchanged by the finish.
            let unknown = Self.input(phase, market: nil, original: nil, finish: nil)
            for (index, market) in model.markets.enumerated() {
                for (side, original) in market.originals.enumerated() {
                    XCTAssertEqual(model.rail(original), unknown.rail(unknown.markets[index].originals[side]), original.id)
                }
            }
        }
        // A finish whose round is not one known segment keeps its words and marks no round.
        let roundless = CombatDurationFinish10868(segmentID: nil, markerWords: "Finish round not recorded", title: "Official bout result", lines: [], accessibilityDetail: nil)
        XCTAssertEqual(Self.input(.final, finish: roundless).finishMark, CombatDurationMark10868(segmentIndex: nil, words: "Finish round not recorded"))
        let elsewhere = CombatDurationFinish10868(segmentID: "r7", markerWords: "Finished in Round 7", title: "Official bout result", lines: [], accessibilityDetail: nil)
        XCTAssertNil(Self.input(.final, finish: elsewhere).finishMark?.segmentIndex)
    }

    // MARK: Identity, selection and actions

    func testMissingSelectedSideStaysUnavailableAndAllSidesStayListed() {
        let model = Self.input(.final, market: Self.distID, original: "999")
        let dist = model.markets[5]
        XCTAssertEqual(model.selection, .sideUnavailable(dist, "999"))
        XCTAssertEqual(model.lead(dist), .unavailable(CombatDurationInput10868.sideUnavailableShort))
        XCTAssertEqual(model.selectionNotice, CombatDurationInput10868.sideUnavailable)
        XCTAssertNil(model.comparison)
        XCTAssertNil(model.accessibilityComparison)
        XCTAssertNil(model.tileAction(dist, canSelect: true))
        XCTAssertNil(model.detailsAction(canOpenDetails: true))
        XCTAssertEqual(
            model.accessibilityTileValue(dist),
            "Selected side unavailable. Yes. Time window: \(Self.spokenWindow[Self.distYes]!); Pre-match chance: 37%; Contract result: Lost. No. Time window: \(Self.spokenWindow[Self.distNo]!); Pre-match chance: 63%; Contract result: Won. Market selected"
        )
        for original in dist.originals {
            XCTAssertEqual(model.sideAction(original, in: dist, canSelect: true), .select(Self.ref(Self.distID, original.id)))
            XCTAssertFalse(model.isSelected(original, in: dist))
        }
    }

    func testMissingMarketKeepsTilesAndSelectsNothing() {
        let model = Self.input(.before, Self.retainedMarkets(overview: [Self.r3ID: Self.r3Yes]), market: "retired-market", original: Self.r2Yes)
        XCTAssertEqual(model.selection, .unavailable("retired-market"))
        XCTAssertEqual(model.selectionNotice, CombatDurationInput10868.marketUnavailable)
        XCTAssertNil(model.comparison)
        XCTAssertFalse(model.markets.contains { model.isSelectedMarket($0) })
        XCTAssertEqual(model.lead(model.markets[3]), .sides)
        XCTAssertEqual(model.lead(model.markets[4]), .original(model.markets[4].originals[0], selected: false))
    }

    func testSideNamedWithoutItsMarketResolvesOnlyWhenUnique() {
        let model = Self.input(.before, market: nil, original: Self.distNo)
        XCTAssertEqual(model.selection, .original(model.markets[5], model.markets[5].originals[1]))
        XCTAssertNil(Self.input(.before, market: nil, original: "999").selection.original)
        XCTAssertEqual(Self.input(.before, market: nil, original: "999").selection, .unavailable("999"))
    }

    func testDuplicateOriginalIdsCarryNoActionAndCannotResolve() {
        // CONSTRUCTED: the Before Round 3 No arrives carrying the Before Round 2 No id.
        let dupe = CombatDurationOriginal10868(
            id: Self.r2No, marketID: Self.r3ID, label: "No", window: Self.window(Self.row(Self.r3No)), windowMissing: Self.noWindow,
            before: Self.pregame(Self.row(Self.r3No)), beforeMissing: Self.notRecorded, current: Self.noCurrent, result: .lost("Lost"), resultDetail: nil
        )
        let markets = [
            Self.market(Self.r2ID, [Self.original(Self.r2Yes), Self.original(Self.r2No)]),
            Self.market(Self.r3ID, [Self.original(Self.r3Yes), dupe]),
        ]
        let model = Self.input(.before, markets, market: Self.r2ID, original: Self.r2No)
        XCTAssertEqual(model.duplicateOriginalIDs, [Self.r2No])
        XCTAssertEqual(model.selection, .sideUnavailable(model.markets[0], Self.r2No))
        XCTAssertNil(model.sideAction(model.markets[0].originals[1], in: model.markets[0], canSelect: true))
        XCTAssertNil(model.sideAction(dupe, in: model.markets[1], canSelect: true))
        XCTAssertNotNil(model.sideAction(model.markets[0].originals[0], in: model.markets[0], canSelect: true))
        XCTAssertEqual(Self.input(.before, markets, market: nil, original: Self.r2No).selection, .unavailable(Self.r2No))
    }

    func testDuplicateMarketIdsCarryNoTileOrSideAction() {
        let twins = Self.input(.before, [
            Self.market(Self.r2ID, [Self.original(Self.r2Yes), Self.original(Self.r2No)], overview: Self.r2Yes),
            Self.market(Self.r2ID, [Self.original(Self.r3Yes), Self.original(Self.r3No)], overview: Self.r3Yes),
        ], market: Self.r2ID, original: Self.r2Yes)
        XCTAssertEqual(twins.duplicateMarketIDs, [Self.r2ID])
        XCTAssertEqual(twins.selection, .unavailable(Self.r2ID))
        for market in twins.markets {
            XCTAssertNil(twins.tileAction(market, canSelect: true))
            XCTAssertFalse(twins.isSelectedMarket(market))
            for original in market.originals {
                XCTAssertNil(twins.sideAction(original, in: market, canSelect: true), original.id)
            }
        }
    }

    func testExactActionsCarryEventMarketAndOriginal() {
        let model = Self.input(.final, Self.retainedMarkets(overview: [Self.distID: Self.distNo]), market: Self.u15ID, original: Self.u15Side)
        XCTAssertEqual(model.tileAction(model.markets[5], canSelect: true), .select(Self.ref(Self.distID, Self.distNo)))
        XCTAssertEqual(model.detailsAction(canOpenDetails: true), .details(Self.ref(Self.u15ID, Self.u15Side)))
        XCTAssertNil(model.detailsAction(canOpenDetails: false))
        var selected: [CombatDurationOriginalRef10868] = []
        var details: [CombatDurationOriginalRef10868] = []
        model.tileAction(model.markets[5], canSelect: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        model.detailsAction(canOpenDetails: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        XCTAssertEqual(selected, [CombatDurationOriginalRef10868(eventID: "15318681", durationMarketID: Self.distID, marketID: Self.distID, originalID: Self.distNo)])
        XCTAssertEqual(details, [CombatDurationOriginalRef10868(eventID: "15318681", durationMarketID: Self.u15ID, marketID: Self.u15ID, originalID: Self.u15Side)])
    }

    func testNoCallbacksMeansStaticContentAndNoInstruction() {
        let model = Self.input(.before, Self.retainedMarkets(overview: [Self.r2ID: Self.r2Yes]))
        XCTAssertNil(model.instruction(canSelect: false))
        XCTAssertEqual(model.instruction(canSelect: true), CombatDurationInput10868.chooseInstruction)
        XCTAssertNil(Self.input(.before, []).instruction(canSelect: true))
        for market in model.markets {
            XCTAssertNil(model.tileAction(market, canSelect: false), market.id)
            XCTAssertTrue(model.tilePresentation(market, canSelect: false).listed.allSatisfy { $0.action == nil }, market.id)
            XCTAssertTrue(model.panelSides(market, canSelect: false).allSatisfy { $0.action == nil }, market.id)
        }
        XCTAssertEqual(Self.input(.before, []).keyItems, [])
        XCTAssertNil(Self.input(.before, []).accessibilityKey)
    }

    // MARK: Tile presentation (the View's own branch)

    func testInvalidOverviewWithValidAlternativesListsEveryOriginalWithExactActions() {
        // CONSTRUCTED: Before Round 2's overview names an id it does not carry;
        // Before Round 3's overview No was withdrawn. Go the distance is valid.
        let markets = [
            Self.market(Self.r2ID, [Self.original(Self.r2Yes), Self.original(Self.r2No)], overview: "999"),
            Self.market(Self.r3ID, [Self.original(Self.r3Yes)], overview: Self.r3No),
            Self.market(Self.distID, [Self.original(Self.distYes), Self.original(Self.distNo)], overview: Self.distNo),
        ]
        for phase in Self.phases {
            for (selectedMarket, selectedOriginal) in [(nil, nil), (Self.distID, Self.distNo)] as [(String?, String?)] {
                let model = Self.input(phase, markets, market: selectedMarket, original: selectedOriginal)
                let label = "\(phase) \(selectedMarket ?? "none")"
                for market in model.markets.prefix(2) {
                    XCTAssertEqual(model.lead(market), .unavailable(CombatDurationInput10868.overviewUnavailable), label)
                    XCTAssertNil(model.tileAction(market, canSelect: true), label)
                    XCTAssertEqual(
                        model.tilePresentation(market, canSelect: true),
                        .unavailableWithSides(CombatDurationInput10868.overviewUnavailable, sides: Self.listed(market, market.originals, actionable: true)),
                        label
                    )
                    XCTAssertEqual(
                        model.tilePresentation(market, canSelect: false),
                        .unavailableWithSides(CombatDurationInput10868.overviewUnavailable, sides: Self.listed(market, market.originals, actionable: false)),
                        label
                    )
                    XCTAssertEqual(model.tileTitle(market), market.label, label)
                }
                let dist = model.markets[2]
                XCTAssertEqual(
                    model.tilePresentation(dist, canSelect: true),
                    .rail(dist.originals[1], selected: selectedMarket != nil, action: .select(Self.ref(Self.distID, Self.distNo))),
                    label
                )
            }
        }
    }

    func testStaticOverviewOnUnselectedMarketKeepsRailAndListsOtherOriginals() {
        let overview = [Self.r2ID: Self.r2Yes, Self.r3ID: Self.r3No, Self.distID: Self.distYes, Self.u15ID: Self.u15Side]
        for phase in Self.phases {
            let model = Self.input(phase, Self.retainedMarkets(overview: overview), market: Self.r2ID, original: Self.r2Yes)
            let r2 = model.markets[3]
            let r3 = model.markets[4]
            let dist = model.markets[5]
            XCTAssertEqual(model.tilePresentation(r2, canSelect: false), .rail(r2.originals[0], selected: true, action: nil))
            XCTAssertEqual(model.tilePresentation(r3, canSelect: false), .railWithSides(r3.originals[1], others: Self.listed(r3, [r3.originals[0]], actionable: false)))
            XCTAssertEqual(model.tilePresentation(dist, canSelect: false), .railWithSides(dist.originals[0], others: Self.listed(dist, [dist.originals[1]], actionable: false)))
            // A single-original market with its own overview has nothing else to list.
            XCTAssertEqual(model.tilePresentation(model.markets[1], canSelect: false), .rail(model.markets[1].originals[0], selected: false, action: nil))

            // Static rows keep each original's window and phase-specific readings.
            XCTAssertEqual(
                model.accessibilityLeadValue(r3.originals[1]),
                "No. Time window: \(Self.spokenWindow[Self.r3No]!); Pre-match chance: 47%, \(Self.detail)\(Self.later(phase, Self.r3No, detailed: true))",
                "\(phase)"
            )
            XCTAssertEqual(
                model.accessibilitySideValue(r3.originals[0], in: r3),
                "Time window: \(Self.spokenWindow[Self.r3Yes]!); Pre-match chance: 53%, \(Self.detail)\(Self.later(phase, Self.r3Yes, detailed: true))",
                "\(phase)"
            )

            let none = Self.input(phase, Self.retainedMarkets(overview: overview), market: nil, original: nil)
            for market in none.markets where market.originals.count > 1 {
                guard case .railWithSides(let lead, let others) = none.tilePresentation(market, canSelect: false) else {
                    return XCTFail("\(phase) \(market.id)")
                }
                XCTAssertEqual(lead.id, market.overviewOriginalID)
                XCTAssertEqual(Set(others.map(\.original.id)).union([lead.id]), Set(market.originals.map(\.id)))
                XCTAssertTrue(others.allSatisfy { $0.action == nil })
            }
        }
    }

    func testDuplicatesKeepTheStaticFallbackWithoutAmbiguousActions() {
        for phase in Self.phases {
            let twins = Self.input(phase, [
                Self.market(Self.r2ID, [Self.original(Self.r2Yes), Self.original(Self.r2No)], overview: Self.r2Yes),
                Self.market(Self.r2ID, [Self.original(Self.r3Yes), Self.original(Self.r3No)], overview: Self.r3Yes),
            ], market: nil, original: nil)
            for market in twins.markets {
                XCTAssertEqual(
                    twins.tilePresentation(market, canSelect: true),
                    .railWithSides(market.originals[0], others: Self.listed(market, [market.originals[1]], actionable: false)),
                    "\(phase)"
                )
            }
        }
    }

    func testSelectedMarketTileNeverRepeatsItsSideRows() {
        for phase in Self.phases {
            let missing = Self.input(phase, market: Self.r2ID, original: "999")
            let r2 = missing.markets[3]
            for canSelect in [true, false] {
                XCTAssertEqual(missing.tilePresentation(r2, canSelect: canSelect), .unavailable(CombatDurationInput10868.sideUnavailableShort), "\(phase)")
                XCTAssertEqual(missing.panelSides(r2, canSelect: canSelect), Self.listed(r2, r2.originals, actionable: canSelect), "\(phase)")
            }
            let picked = Self.input(phase, market: Self.r3ID, original: Self.r3No)
            XCTAssertEqual(picked.tilePresentation(picked.markets[4], canSelect: false), .rail(picked.markets[4].originals[1], selected: true, action: nil))
            XCTAssertEqual(picked.panelSides(picked.markets[4], canSelect: false), Self.listed(picked.markets[4], picked.markets[4].originals, actionable: false))
        }
    }

    func testEveryOriginalIsOnScreenOrOneTileActionFromItsSideRow() {
        let overviews: [[String: String]] = [
            [:],
            [Self.overID: Self.overSide, Self.r2ID: Self.r2No, Self.r3ID: Self.r3Yes, Self.distID: Self.distYes],
            [Self.u15ID: Self.u15Side, Self.r2ID: "999", Self.r3ID: Self.r3Yes, Self.distID: Self.distNo],
        ]
        let selections: [(String?, String?)] = [
            (nil, nil), (Self.r2ID, Self.r2Yes), (Self.r2ID, "999"), (Self.r3ID, nil), (Self.u15ID, nil), ("retired-market", nil), (nil, Self.distNo), (nil, Self.u25Side),
        ]
        for phase in Self.phases {
            for overview in overviews {
                for (selectedMarket, selectedOriginal) in selections {
                    let model = Self.input(phase, Self.retainedMarkets(overview: overview), market: selectedMarket, original: selectedOriginal)
                    for canSelect in [true, false] {
                        var everyRef = Set<CombatDurationOriginalRef10868>()
                        for market in model.markets {
                            let label = "\(phase) \(overview) \(selectedMarket ?? "-")/\(selectedOriginal ?? "-") \(canSelect) \(market.id)"
                            let presentation = model.tilePresentation(market, canSelect: canSelect)
                            var shown = Set(presentation.listed.map(\.original.id))
                            var tileAction: CombatDurationAction10868?
                            switch presentation {
                            case .rail(let lead, _, let action):
                                shown.insert(lead.id)
                                tileAction = action
                            case .railWithSides(let lead, _):
                                shown.insert(lead.id)
                            case .unavailable, .unavailableWithSides, .sides:
                                break
                            }
                            // The rows the selected panel actually mounts — counted where they are.
                            let panel = model.panelSides(market, canSelect: canSelect)
                            shown.formUnion(panel.map(\.original.id))
                            if !panel.isEmpty {
                                XCTAssertEqual(model.selection.market, market, label)
                                XCTAssertEqual(panel.map(\.original.id), market.originals.map(\.id), label)
                            }
                            if model.selection.market == market {
                                // Exactly one place lists the selected market's sides: its tile or the panel.
                                XCTAssertNotEqual(panel.isEmpty, presentation.listed.isEmpty, label)
                            }
                            let rows = presentation.listed.map(\.original.id) + panel.map(\.original.id)
                            XCTAssertEqual(rows.count, Set(rows).count, label)
                            if shown != Set(market.originals.map(\.id)) {
                                // Only an actionable rail may leave a side off screen: its action
                                // selects this market, whose side rows then list every side.
                                guard case .select(let ref)? = tileAction else { XCTFail(label); continue }
                                XCTAssertEqual(ref.durationMarketID, market.id, label)
                            }
                            for side in presentation.listed + panel {
                                XCTAssertEqual(side.action, model.sideAction(side.original, in: market, canSelect: canSelect), label)
                            }
                            if !canSelect {
                                XCTAssertTrue(presentation.listed.allSatisfy { $0.action == nil }, label)
                                XCTAssertTrue(panel.allSatisfy { $0.action == nil }, label)
                                XCTAssertNil(tileAction, label)
                            }
                            // Every original is spoken by its tile, whatever the lead.
                            let spoken = model.accessibilityTileValue(market)
                            for original in market.originals {
                                XCTAssertTrue(spoken.contains("\(original.label). Time window: \(Self.spokenWindow[original.id]!)"), "\(label) \(original.id)")
                                if case .select(let ref)? = model.sideAction(original, in: market, canSelect: canSelect) { everyRef.insert(ref) }
                            }
                        }
                        if canSelect {
                            XCTAssertEqual(everyRef.map(\.originalID).sorted(), Self.retained.map(\.outcomeID).sorted())
                        }
                    }
                }
            }
        }
    }

    func testMarketChosenWithoutSideOrOverviewMountsEachOriginalOnce() {
        for phase in Self.phases {
            // The host chose Go the distance but no side, and named no overview side.
            let model = Self.input(phase, market: Self.distID, original: nil)
            let dist = model.markets[5]
            XCTAssertEqual(model.selection, .market(dist), "\(phase)")
            XCTAssertEqual(model.lead(dist), .sides, "\(phase)")
            XCTAssertEqual(model.selection.market?.question, "Fight to Go the Distance?", "\(phase)")
            XCTAssertNil(model.comparison, "\(phase)")
            XCTAssertNil(model.detailsAction(canOpenDetails: true), "\(phase)")
            XCTAssertTrue(model.accessibilityTileValue(dist).hasSuffix(CombatDurationInput10868.marketSelectedTag), "\(phase)")
            XCTAssertFalse(model.panelListsSides(dist), "\(phase)")
            for canSelect in [true, false] {
                let label = "\(phase) \(canSelect)"
                let tile = model.tilePresentation(dist, canSelect: canSelect)
                let panel = model.panelSides(dist, canSelect: canSelect)
                XCTAssertEqual(tile, .sides(Self.listed(dist, dist.originals, actionable: canSelect)), label)
                XCTAssertEqual(panel, [], label)
                let rows = tile.listed + panel
                for original in dist.originals {
                    XCTAssertEqual(rows.filter { $0.original.id == original.id }.count, 1, "\(label) \(original.id)")
                }
                var selected: [CombatDurationOriginalRef10868] = []
                for side in rows {
                    XCTAssertEqual(side.action, canSelect ? .select(Self.ref(Self.distID, side.original.id)) : nil, label)
                    side.action?.perform(onSelect: { selected.append($0) }, onDetails: { _ in XCTFail(label) })
                }
                XCTAssertEqual(selected, canSelect ? [Self.ref(Self.distID, Self.distYes), Self.ref(Self.distID, Self.distNo)] : [], label)
                let identifiers = rows.map { CombatDurationAccessibilityID10868.side(dist.id, $0.original.id) }
                XCTAssertEqual(identifiers.count, Set(identifiers).count, label)
                for side in rows {
                    let spoken = model.accessibilitySideValue(side.original, in: dist)
                    XCTAssertEqual(
                        spoken,
                        "Time window: \(Self.spokenWindow[side.original.id]!); Pre-match chance: \(Self.row(side.original.id).text), \(Self.detail)\(Self.later(phase, side.original.id, detailed: true))",
                        "\(label) \(side.original.id)"
                    )
                    XCTAssertFalse(spoken.contains(CombatDurationInput10868.selectedTag), "\(label) \(side.original.id)")
                }
                // A single-original market chosen without a side: listed once, in its tile.
                let lone = Self.input(phase, market: Self.u15ID, original: nil)
                XCTAssertEqual(lone.tilePresentation(lone.markets[1], canSelect: canSelect), .sides(Self.listed(lone.markets[1], lone.markets[1].originals, actionable: canSelect)), label)
                XCTAssertEqual(lone.panelSides(lone.markets[1], canSelect: canSelect), [], label)
                XCTAssertTrue(lone.showsSingleOriginalNote, label)
                // Contrast: a chosen side makes the tile the rail and the panel lists every side once.
                let picked = Self.input(phase, market: Self.distID, original: Self.distNo)
                let pickedDist = picked.markets[5]
                XCTAssertEqual(picked.tilePresentation(pickedDist, canSelect: canSelect), .rail(pickedDist.originals[1], selected: true, action: canSelect ? .select(Self.ref(Self.distID, Self.distNo)) : nil), label)
                XCTAssertEqual(picked.panelSides(pickedDist, canSelect: canSelect), Self.listed(pickedDist, pickedDist.originals, actionable: canSelect), label)
            }
        }
    }

    func testTileRowsSkipOnlyAWindowLabelTheTileTitleAlreadyReads() {
        let model = Self.input(.before, market: nil, original: nil)
        // Under 1½ listed alone: the tile title already reads its window.
        let u15 = model.markets[1]
        XCTAssertEqual(model.tileTitle(u15), "Under 1½ rounds")
        XCTAssertFalse(model.showsWindowLabel(u15.originals[0], inTileOf: u15))
        // Yes / No rows each keep their own window under the market's title.
        let r2 = model.markets[3]
        XCTAssertEqual(model.tileTitle(r2), "Before Round 2")
        XCTAssertFalse(model.showsWindowLabel(r2.originals[0], inTileOf: r2))
        XCTAssertTrue(model.showsWindowLabel(r2.originals[1], inTileOf: r2))
        let dist = model.markets[5]
        XCTAssertTrue(model.showsWindowLabel(dist.originals[0], inTileOf: dist))
        XCTAssertTrue(model.showsWindowLabel(dist.originals[1], inTileOf: dist))
        // Panel rows always show it.
        for original in r2.originals { XCTAssertTrue(model.showsWindowLabel(original, inTileOf: nil)) }
    }

    func testTimingOnlyForTheExactResolvedSelection() {
        let timing = CombatDurationTiming10868(originalID: Self.r2Yes, title: "Times", lines: ["Pre-match recorded Oct 3, 4:27 PM PT"])
        XCTAssertEqual(Self.input(.before, timing: timing).timingPresentation(hasBinding: false), .expanded(timing))
        XCTAssertEqual(Self.input(.before, timing: timing).timingPresentation(hasBinding: true), .disclosure(timing))
        XCTAssertNil(Self.input(.before, original: Self.r2No, timing: timing).timingPresentation(hasBinding: true))
        XCTAssertNil(Self.input(.before, original: "999", timing: timing).timingPresentation(hasBinding: true))
        XCTAssertNil(Self.input(.before, market: Self.r2ID, original: nil, timing: timing).timingPresentation(hasBinding: true))
    }

    // MARK: Non-colour keys

    func testSelectionResultBellAndRoundMarksAreDistinctShapesAndWords() {
        let results: [CombatDurationResult10868] = [.won("Won"), .lost("Lost"), .void("Void"), .unconfirmed(Self.unconfirmed), .other("Under review")]
        let symbols = results.map(\.symbolName)
        XCTAssertEqual(Set(symbols).count, results.count)
        let bells = [CombatDurationFinalBell10868.included(""), .excluded("")].map(\.symbolName)
        // Selection's plain checkmark, the bells and the finish diamond are not result symbols.
        XCTAssertTrue(Set(symbols).isDisjoint(with: Set(bells + ["checkmark", "diamond.fill"])))
        XCTAssertEqual(Set(bells).count, 2)
        XCTAssertEqual(CombatDurationInput10868.selectedTag, "Selected")
        XCTAssertEqual(CombatDurationInput10868.preMatchShort, "Pre-match")
        XCTAssertEqual(CombatDurationInput10868.currentShort, "In-fight")
        XCTAssertNotEqual(CombatDurationInput10868.resultTitle, CombatDurationInput10868.preMatchTitle)
        let keyed = Self.input(.during, observed: Self.roundTwo)
        XCTAssertEqual(keyed.keyItems.count, 3)
        XCTAssertEqual(Set(keyed.accessibilityKey!.components(separatedBy: ". ")).count, keyed.accessibilityKey!.components(separatedBy: ". ").count)
        XCTAssertEqual(CombatDurationAccessibilityID10868.tile(Self.distID), "combatDuration10868.tile.63254894")
        XCTAssertEqual(CombatDurationAccessibilityID10868.side(Self.distID, Self.distNo), "combatDuration10868.side.63254894.238409897")
        XCTAssertEqual(CombatDurationAccessibilityID10868.details(Self.distNo), "combatDuration10868.details.238409897")
    }

    // MARK: Zero, absent, long and qualified

    func testZeroIsAReadingAndAbsentIsWords() {
        // CONSTRUCTED.
        let model = Self.input(.before, [
            Self.market(Self.r2ID, [
                Self.original(Self.r2Yes, before: .some(Self.obs(0.0, "0%", "4:27 PM PT", Self.detail))),
                Self.original(Self.r2No, before: .some(nil)),
            ]),
        ])
        XCTAssertEqual(model.beforeReading(model.markets[0].originals[0]), .value(Self.obs(0.0, "0%", "4:27 PM PT", Self.detail)))
        XCTAssertEqual(model.beforeReading(model.markets[0].originals[1]), .missing(Self.notRecorded))
        XCTAssertEqual(
            model.accessibilityTileValue(model.markets[0]),
            "Yes. Time window: \(Self.spokenWindow[Self.r2Yes]!); Pre-match chance: 0%, \(Self.detail). Selected. Also No. Time window: \(Self.spokenWindow[Self.r2No]!); Pre-match chance: \(Self.notRecorded)"
        )
    }

    func testLongLabelsAndQualifiedFiguresAreShownVerbatim() {
        // CONSTRUCTED.
        let long = "Ends inside the scheduled distance of a five-round championship bout"
        let figure = "≥99.5%"
        let original = Self.original(
            Self.distNo,
            before: .some(Self.obs(0.996, figure, nil, Self.detail)),
            window: .some(CombatDurationWindow10868(label: long, start: 0, end: 3, finalBell: .excluded(Self.bellExcluded)))
        )
        let model = Self.input(.before, [Self.market(Self.distID, [Self.original(Self.distYes), original])], market: Self.distID, original: Self.distNo)
        XCTAssertEqual(model.tileTitle(model.markets[0]), long)
        XCTAssertEqual(model.beforeReading(original), .value(Self.obs(0.996, figure, nil, Self.detail)))
        XCTAssertTrue(model.accessibilityComparison!.contains("Time window: \(long). Shaded: Round 1, Round 2, Round 3. \(Self.bellExcluded); Pre-match chance: \(figure), "))
        XCTAssertEqual(CombatDurationGeometry10868.words(long).count, 10)
        XCTAssertEqual(CombatDurationGeometry10868.words("  Under\t1½\nrounds "), ["Under", "1½", "rounds"])
    }

    // MARK: Measured layout (arithmetic; CONSTRUCTED widths)

    func testSixRetainedTilesTakeTwoColumnsAtPhoneWidth() {
        // 375 pt phone minus 16 pt margins each side.
        XCTAssertEqual(CombatDurationGeometry10868.columnCount(available: 343, count: 6, spacing: 8, minimumColumnWidth: 140, forceSingle: false) { _ in true }, 2)
        XCTAssertEqual(CombatDurationGeometry10868.columnWidth(available: 343, columns: 2, spacing: 8), 167.5)
        XCTAssertEqual(CombatDurationGeometry10868.columnWidth(available: 343, columns: 3, spacing: 8), 109)
        // 320 pt: still two columns of 140.
        XCTAssertEqual(CombatDurationGeometry10868.columnCount(available: 288, count: 6, spacing: 8, minimumColumnWidth: 140, forceSingle: false) { _ in true }, 2)
        XCTAssertEqual(CombatDurationGeometry10868.rows(count: 6, columns: 2), [[0, 1], [2, 3], [4, 5]])
    }

    func testALongWordDropsAColumnInsteadOfBreakingOrShrinking() {
        XCTAssertEqual(CombatDurationGeometry10868.columnCount(available: 343, count: 6, spacing: 8, minimumColumnWidth: 140, forceSingle: false) { $0 >= 200 }, 1)
        XCTAssertEqual(CombatDurationGeometry10868.columnCount(available: 343, count: 6, spacing: 8, minimumColumnWidth: 140, forceSingle: false) { _ in false }, 1)
    }

    func testEnlargedTextStacksAndWideHasNoMarketOrRoundCeiling() {
        XCTAssertEqual(CombatDurationGeometry10868.columnCount(available: 1180, count: 6, spacing: 8, minimumColumnWidth: 140, forceSingle: true) { _ in true }, 1)
        XCTAssertEqual(CombatDurationGeometry10868.columnCount(available: 1180, count: 6, spacing: 8, minimumColumnWidth: 140, forceSingle: false) { _ in true }, 6)
        // CONSTRUCTED nine markets on a wide window: nine columns, no six-market ceiling.
        XCTAssertEqual(CombatDurationGeometry10868.columnCount(available: 1400, count: 9, spacing: 8, minimumColumnWidth: 140, forceSingle: false) { _ in true }, 9)
        XCTAssertEqual(CombatDurationGeometry10868.columnCount(available: nil, count: 9, spacing: 8, minimumColumnWidth: 140, forceSingle: false) { _ in true }, 9)
        XCTAssertEqual(CombatDurationGeometry10868.columnCount(available: 0, count: 9, spacing: 8, minimumColumnWidth: 140, forceSingle: false) { _ in true }, 1)
        XCTAssertEqual(CombatDurationGeometry10868.columnCount(available: 343, count: 0, spacing: 8, minimumColumnWidth: 140, forceSingle: false) { _ in true }, 0)
    }

    func testRailWrapsRoundsOntoMoreRowsInsteadOfShrinkingLabels() {
        // Three rounds in a 147 pt rail (167.5 column less padding) stay on one row.
        XCTAssertEqual(CombatDurationGeometry10868.segmentsPerRow(available: 147, count: 3, minimum: 22, spacing: 3), 3)
        // CONSTRUCTED twelve rounds: five per row, three rows, every label whole.
        XCTAssertEqual(CombatDurationGeometry10868.segmentsPerRow(available: 147, count: 12, minimum: 26, spacing: 3), 5)
        XCTAssertEqual(CombatDurationGeometry10868.rows(count: 12, columns: 5), [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [10, 11]])
        XCTAssertEqual(CombatDurationGeometry10868.segmentsPerRow(available: 10, count: 3, minimum: 26, spacing: 3), 1)
        XCTAssertEqual(CombatDurationGeometry10868.segmentsPerRow(available: nil, count: 12, minimum: 26, spacing: 3), 12)
        XCTAssertEqual(CombatDurationGeometry10868.segmentsPerRow(available: 147, count: 3, minimum: 0, spacing: 3), 3)
        XCTAssertEqual(CombatDurationGeometry10868.segmentsPerRow(available: 147, count: 0, minimum: 26, spacing: 3), 0)
    }

    func testComparisonPairSitsSideBySideOnlyWhenBothFiguresStayWhole() {
        XCTAssertEqual(CombatDurationGeometry10868.pairArrangement(available: 327, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: false), .sideBySide)
        XCTAssertEqual(CombatDurationGeometry10868.pairArrangement(available: 240, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: false), .stacked)
        XCTAssertEqual(CombatDurationGeometry10868.pairArrangement(available: 327, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: true), .stacked)
        XCTAssertEqual(CombatDurationGeometry10868.pairArrangement(available: 327, first: .nan, second: 100, spacing: 16, equalColumns: true, forceStack: false), .stacked)
        XCTAssertEqual(CombatDurationGeometry10868.pairArrangement(available: nil, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: false), .sideBySide)
        XCTAssertEqual(CombatDurationGeometry10868.columns(total: 327, first: 120, spacing: 16, equalColumns: true), CombatDurationColumns10868(first: 155.5, second: 155.5))
    }
}
