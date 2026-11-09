import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the combat method card as a stateless presentation leaf across
/// before, during and after the fight.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: which readings each phase shows, the independence of
/// every original side, zero versus unknown, the exact-id selection and lead
/// side, the action each control carries, the timing it may show, the ring,
/// column and pair geometry and the spoken text. Nothing here claims a
/// rendered fit, a native runtime or a populated boxing case.
///
/// ARCHIVED raw values come from Gautier–Kopylov, event 15318681 (mma), as
/// retained in `shipping-adoption-20261027/COMBAT-METHOD-RETAINED-CASES.json`
/// (sha256 0ec4699f…9e08). Three independent binary markets, six originals:
///   KO / TKO 63786874        Yes 240262496 0.55  No 240262497 0.45   @ 2026-10-03T23:27:48.847758Z
///   Submission 63634393      Yes 239735845 0.105 No 239735846 0.895  @ 2026-10-03T23:27:48.847758Z
///   Decision / draw 63786883 Yes 240262514 0.51  No 240262515 0.49   @ 2026-10-03T08:03:50.187004Z
///   Independent results: KO Yes Won / No Lost; Submission Yes Lost / No Won;
///   Decision Yes Lost / No Won. The Yes values sum to 1.165 at different
///   clocks — independent predicates, never one distribution.
///   No admitted in-fight chance is retained. The raw event stays suspended.
///   Later official UFC evidence: Kopylov def. Gautier, TKO (strikes), R1 3:12,
///   absoluteFinishAt null — separate context, never a contract grade.
///   The KO quotes of 1.0 / 0.0 at 2026-10-04T02:34:11Z are settlement-time
///   values, not baselines and not inputs.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// method ids, every display string, PT time and provenance line, the result
/// and unavailable words, the official-context wording, every in-fight
/// observation and movement line, held/withdrawn/duplicate updates, phase
/// arrivals, zero, malformed and long-label cases, and every measured width.
///
/// The fighter-knockout reuse (last section) feeds the same tiles four ARCHIVED
/// originals from `COMBAT-FIGHTER-KO-RETAINED-CASES.json`, with CONSTRUCTED row
/// ids, display strings and fighter words.
final class CombatMethodPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static let eventID = "15318681"
    private static let koID = "ko-tko"
    private static let subID = "submission"
    private static let decID = "decision-draw"

    private static let koYes = "240262496"
    private static let koNo = "240262497"
    private static let subYes = "239735845"
    private static let subNo = "239735846"
    private static let decYes = "240262514"
    private static let decNo = "240262515"

    /// ARCHIVED pre-start clocks (KO and Submission share one; Decision's is earlier).
    private static let lateClock = "2026-10-03T23:27:48.847758+00:00"
    private static let earlyClock = "2026-10-03T08:03:50.187004+00:00"

    private struct Retained {
        let methodID: String
        let marketID: String
        let outcomeID: String
        let side: String
        /// ARCHIVED.
        let probability: Double
        let clock: String
        let result: String
        /// CONSTRUCTED owner text.
        let text: String
        let time: String
    }

    private static let retained: [Retained] = [
        Retained(methodID: koID, marketID: "63786874", outcomeID: koYes, side: "Yes", probability: 0.55, clock: lateClock, result: "Won", text: "55%", time: "4:27 PM PT"),
        Retained(methodID: koID, marketID: "63786874", outcomeID: koNo, side: "No", probability: 0.45, clock: lateClock, result: "Lost", text: "45%", time: "4:27 PM PT"),
        Retained(methodID: subID, marketID: "63634393", outcomeID: subYes, side: "Yes", probability: 0.105, clock: lateClock, result: "Lost", text: "10.5%", time: "4:27 PM PT"),
        Retained(methodID: subID, marketID: "63634393", outcomeID: subNo, side: "No", probability: 0.895, clock: lateClock, result: "Won", text: "89.5%", time: "4:27 PM PT"),
        Retained(methodID: decID, marketID: "63786883", outcomeID: decYes, side: "Yes", probability: 0.51, clock: earlyClock, result: "Lost", text: "51%", time: "1:03 AM PT"),
        Retained(methodID: decID, marketID: "63786883", outcomeID: decNo, side: "No", probability: 0.49, clock: earlyClock, result: "Won", text: "49%", time: "1:03 AM PT"),
    ]

    private static let lateDetail = "Last recorded before start · Oct 3, 4:27 PM PT · Polymarket"
    private static let earlyDetail = "Last recorded before start · Oct 3, 1:03 AM PT · Polymarket"
    private static let noCurrent = CombatMethodCurrent10868.unavailable("No in-fight chance")
    private static let notRecorded = "Not recorded before start"

    private static func obs(_ probability: Double, _ text: String, _ time: String?, _ detail: String) -> CombatMethodObservation10868 {
        CombatMethodObservation10868(probability: probability, text: text, timeText: time, detail: detail)
    }

    private static func pregame(_ row: Retained) -> CombatMethodObservation10868 {
        obs(row.probability, row.text, row.time, "Last recorded before start · Oct 3, \(row.time) · Polymarket")
    }

    private static func grade(_ word: String) -> CombatMethodResult10868 {
        word == "Won" ? .won("Won") : .lost("Lost")
    }

    private static func row(_ id: String) -> Retained {
        (retained + fighterRetained).first { $0.outcomeID == id }!
    }

    private static func original(
        _ id: String,
        before: CombatMethodObservation10868?? = nil,
        current: CombatMethodCurrent10868 = noCurrent,
        result: CombatMethodResult10868? = nil
    ) -> CombatMethodOriginal10868 {
        let source = Self.row(id)
        let reading: CombatMethodObservation10868?
        switch before {
        case .some(let supplied): reading = supplied
        case .none: reading = pregame(source)
        }
        return CombatMethodOriginal10868(
            id: id,
            marketID: source.marketID,
            label: source.side,
            before: reading,
            beforeMissing: notRecorded,
            current: current,
            result: result ?? grade(source.result)
        )
    }

    private static func method(
        _ id: String,
        _ originals: [CombatMethodOriginal10868],
        overview: String? = nil
    ) -> CombatMethod10868 {
        switch id {
        case koID:
            return CombatMethod10868(id: id, label: "KO / TKO", question: "Will the fight be won by KO or TKO?", originals: originals, overviewOriginalID: overview)
        case subID:
            return CombatMethod10868(id: id, label: "Submission", question: "Will the fight be won by submission?", originals: originals, overviewOriginalID: overview)
        default:
            return CombatMethod10868(id: id, label: "Decision / draw", question: "Will the fight end in a decision or draw?", originals: originals, overviewOriginalID: overview)
        }
    }

    /// The three retained methods in the owner's order, results supplied (each
    /// phase decides what shows).
    private static func retainedMethods(overview: [String: String] = [:]) -> [CombatMethod10868] {
        [
            method(koID, [original(koYes), original(koNo)], overview: overview[koID]),
            method(subID, [original(subYes), original(subNo)], overview: overview[subID]),
            method(decID, [original(decYes), original(decNo)], overview: overview[decID]),
        ]
    }

    /// CONSTRUCTED wording of the ARCHIVED UFC reference; no finish clock exists.
    private static let official = CombatMethodActual10868(
        title: "Official bout result",
        lines: ["Roman Kopylov def. Ateba Gautier · TKO (strikes) · Round 1, 3:12"],
        accessibilityDetail: "UFC results page, captured Oct 13 · finish clock not recorded"
    )

    private static func input(
        _ phase: CombatMethodPhase10868,
        _ methods: [CombatMethod10868] = retainedMethods(),
        method: String? = koID,
        original: String? = koYes,
        actual: CombatMethodActual10868? = official,
        timing: CombatMethodTiming10868? = nil
    ) -> CombatMethodInput10868 {
        CombatMethodInput10868(
            phase: phase,
            eventID: eventID,
            eyebrow: "Polymarket · contract results",
            title: phase == .final ? "How the bout ended" : "How could the fight end?",
            caption: "Pre-match chances · select a tile for its quote time",
            methods: methods,
            selectedMethodID: method,
            selectedOriginalID: original,
            actual: actual,
            timing: timing
        )
    }

    /// CONSTRUCTED admitted in-fight observation (the packet retains none).
    private static let koYesCurrent = obs(0.71, "71%", "5:31 PM PT", "Recorded Oct 3, 5:31 PM PT · Polymarket")

    /// Every later input supplied, to prove the earlier phases hide them.
    private static var everythingSupplied: [CombatMethod10868] {
        [
            method(koID, [
                original(koYes, current: .recorded(koYesCurrent, movement: "+16 points since pre-match")),
                original(koNo, current: .withheld("Held since round 1")),
            ]),
            method(subID, [original(subYes), original(subNo)]),
            method(decID, [original(decYes), original(decNo)]),
        ]
    }

    private static func allOriginals(_ model: CombatMethodInput10868) -> [(CombatMethod10868, CombatMethodOriginal10868)] {
        model.methods.flatMap { method in method.originals.map { (method, $0) } }
    }

    private static func ref(_ methodID: String, _ originalID: String) -> CombatMethodOriginalRef10868 {
        CombatMethodOriginalRef10868(eventID: eventID, methodID: methodID, marketID: row(originalID).marketID, originalID: originalID)
    }

    // MARK: The six retained originals

    func testSixRetainedOriginalsKeepExactIdsOrderAndOwnBaselines() {
        let model = Self.input(.before)
        XCTAssertEqual(model.methods.map(\.id), [Self.koID, Self.subID, Self.decID])
        XCTAssertEqual(model.methods.map(\.label), ["KO / TKO", "Submission", "Decision / draw"])
        XCTAssertEqual(Self.allOriginals(model).map { $0.1.id }, [Self.koYes, Self.koNo, Self.subYes, Self.subNo, Self.decYes, Self.decNo])
        XCTAssertEqual(Self.allOriginals(model).map { $0.1.label }, ["Yes", "No", "Yes", "No", "Yes", "No"])
        XCTAssertEqual(Self.allOriginals(model).map { $0.1.marketID }, ["63786874", "63786874", "63634393", "63634393", "63786883", "63786883"])
        for (method, original) in Self.allOriginals(model) {
            let source = Self.row(original.id)
            XCTAssertEqual(source.methodID, method.id)
            guard case .value(let reading) = model.beforeReading(original) else { return XCTFail(original.id) }
            XCTAssertEqual(reading.probability, source.probability, original.id)
            XCTAssertEqual(reading.text, source.text, original.id)
            XCTAssertEqual(CombatMethodGeometry10868.ringFraction(reading.probability), source.probability, original.id)
        }
        // Two shared clocks for KO and Submission; Decision's own earlier clock.
        XCTAssertEqual(Set(Self.retained.map(\.clock)), [Self.lateClock, Self.earlyClock])
        XCTAssertEqual(Self.retained.filter { $0.methodID == Self.decID }.map(\.clock), [Self.earlyClock, Self.earlyClock])
        let decision = model.methods[2].originals[0]
        guard case .value(let decisionReading) = model.beforeReading(decision) else { return XCTFail("decision") }
        XCTAssertEqual(decisionReading.detail, Self.earlyDetail)
        // The KO settlement-time quote of 1.0 is not the baseline.
        guard case .value(let koReading) = model.beforeReading(model.methods[0].originals[0]) else { return XCTFail("ko") }
        XCTAssertEqual(koReading.probability, 0.55)
        XCTAssertEqual(koReading.detail, Self.lateDetail)
    }

    func testYesValuesSumAboveOneAndAreNeverNormalized() {
        let yes = Self.retained.filter { $0.side == "Yes" }.map(\.probability)
        XCTAssertEqual(yes.reduce(0, +), 1.165, accuracy: 1e-9)
        let model = Self.input(.before, Self.retainedMethods(overview: [Self.koID: Self.koYes, Self.subID: Self.subYes, Self.decID: Self.decYes]), method: nil, original: nil)
        var drawn: [Double] = []
        for method in model.methods {
            guard case .original(let lead, selected: false) = model.lead(method),
                  case .value(let reading) = model.beforeReading(lead),
                  let fraction = CombatMethodGeometry10868.ringFraction(reading.probability)
            else { return XCTFail(method.id) }
            drawn.append(fraction)
        }
        XCTAssertEqual(drawn, [0.55, 0.105, 0.51])
        XCTAssertEqual(drawn.reduce(0, +), 1.165, accuracy: 1e-9)
        for (fraction, raw) in zip(drawn, yes) {
            XCTAssertNotEqual(fraction, raw / 1.165, accuracy: 1e-6)
        }
    }

    func testSelectingNoKeepsItsOwnPreMatchAndNeverAComplement() {
        let model = Self.input(.before, method: Self.koID, original: Self.koNo)
        XCTAssertEqual(model.lead(model.methods[0]), .original(model.methods[0].originals[1], selected: true))
        XCTAssertEqual(model.beforeReading(model.methods[0].originals[1]), .value(Self.pregame(Self.row(Self.koNo))))

        // CONSTRUCTED: a No with no recorded baseline stays words, never 1 − 0.55.
        let missingNo = [
            Self.method(Self.koID, [Self.original(Self.koYes), Self.original(Self.koNo, before: .some(nil))]),
        ]
        let held = Self.input(.before, missingNo, method: Self.koID, original: Self.koNo)
        let no = held.methods[0].originals[1]
        XCTAssertEqual(held.lead(held.methods[0]), .original(no, selected: true))
        XCTAssertEqual(held.beforeReading(no), .missing(Self.notRecorded))
        XCTAssertFalse(held.accessibilityTileValue(held.methods[0]).contains("45%"))

        // CONSTRUCTED: independent sides that do not complement keep their own value.
        let skew = [
            Self.method(Self.koID, [Self.original(Self.koYes), Self.original(Self.koNo, before: .some(Self.obs(0.46, "46%", "4:27 PM PT", Self.lateDetail)))]),
        ]
        let skewed = Self.input(.before, skew, method: Self.koID, original: Self.koNo)
        guard case .value(let reading) = skewed.beforeReading(skewed.methods[0].originals[1]) else { return XCTFail("skew") }
        XCTAssertEqual(reading.probability, 0.46)
        XCTAssertNotEqual(reading.probability, 1 - 0.55, accuracy: 1e-9)
    }

    // MARK: Lead side and held updates

    func testTileLeadsWithHostSideThenOverviewThenListsEverySide() {
        let overview = [Self.koID: Self.koYes, Self.subID: Self.subNo]
        let model = Self.input(.before, Self.retainedMethods(overview: overview), method: Self.koID, original: Self.koNo)
        // Host-selected side wins over the overview side.
        XCTAssertEqual(model.lead(model.methods[0]), .original(model.methods[0].originals[1], selected: true))
        // The overview side is shown but not selected.
        XCTAssertEqual(model.lead(model.methods[1]), .original(model.methods[1].originals[1], selected: false))
        // No overview and no selection: every side, none chosen.
        XCTAssertEqual(model.lead(model.methods[2]), .sides)
        XCTAssertNil(model.tileAction(model.methods[2], canSelect: true))
        XCTAssertNotNil(model.sideAction(model.methods[2].originals[0], in: model.methods[2], canSelect: true))
        XCTAssertNotNil(model.sideAction(model.methods[2].originals[1], in: model.methods[2], canSelect: true))
    }

    func testHeldUpdateNeverSwitchesTheLeadSide() {
        // CONSTRUCTED arrival: the selected No's in-fight state changes; it stays the lead.
        let first = Self.input(.during, method: Self.koID, original: Self.koNo)
        let updated = Self.input(
            .during,
            [
                Self.method(Self.koID, [
                    Self.original(Self.koYes, current: .recorded(Self.koYesCurrent, movement: nil)),
                    Self.original(Self.koNo, current: .withheld("Held since round 1")),
                ]),
                Self.method(Self.subID, [Self.original(Self.subYes), Self.original(Self.subNo)]),
                Self.method(Self.decID, [Self.original(Self.decYes), Self.original(Self.decNo)]),
            ],
            method: Self.koID,
            original: Self.koNo
        )
        for model in [first, updated] {
            guard case .original(let lead, selected: true) = model.lead(model.methods[0]) else { return XCTFail("lead") }
            XCTAssertEqual(lead.id, Self.koNo)
        }
        // CONSTRUCTED withdrawal: the selected No leaves the update. Unavailable, never Yes.
        let withdrawn = Self.input(
            .during,
            [Self.method(Self.koID, [Self.original(Self.koYes)], overview: Self.koYes)],
            method: Self.koID,
            original: Self.koNo
        )
        XCTAssertEqual(withdrawn.selection, .sideUnavailable(withdrawn.methods[0], Self.koNo))
        XCTAssertEqual(withdrawn.lead(withdrawn.methods[0]), .unavailable(CombatMethodInput10868.sideUnavailableShort))
        XCTAssertEqual(withdrawn.selectionNotice, CombatMethodInput10868.sideUnavailable)
        XCTAssertNil(withdrawn.comparison)
        XCTAssertNil(withdrawn.tileAction(withdrawn.methods[0], canSelect: true))
        XCTAssertNil(withdrawn.detailsAction(canOpenDetails: true))
        XCTAssertTrue(withdrawn.isSelectedMethod(withdrawn.methods[0]))
    }

    // MARK: Before

    func testBeforeSuppressesInFightResultsMovementAndOfficialContext() {
        let model = Self.input(.before, Self.everythingSupplied)
        for (_, original) in Self.allOriginals(model) {
            XCTAssertNil(model.currentReading(original), original.id)
            XCTAssertNil(model.movement(original), original.id)
            XCTAssertNil(model.result(original), original.id)
            XCTAssertFalse(model.showsCurrentMark(original), original.id)
        }
        XCTAssertNil(model.visibleActual)
        XCTAssertNil(model.accessibilityActual)
        XCTAssertEqual(model.comparison, .before(model.methods[0].originals[0]))
        let spoken = model.methods.map { model.accessibilityTileValue($0) }.joined(separator: " | ")
            + " | " + (model.accessibilityComparison ?? "")
        for later in ["Won", "Lost", "In-fight", "71%", "Held", "Kopylov", "strikes", "Contract result", "+16"] {
            XCTAssertFalse(spoken.contains(later), later)
        }
        XCTAssertTrue(model.accessibilityHeader.hasSuffix("Before the fight"))
    }

    func testBeforeSpokenTilesNameSidePreMatchProvenanceAndEveryOtherSide() {
        let model = Self.input(.before)
        XCTAssertEqual(
            model.accessibilityTileValue(model.methods[0]),
            "Yes. Pre-match chance: 55%, \(Self.lateDetail). Selected. Also No. Pre-match chance: 45%"
        )
        XCTAssertEqual(
            model.accessibilityTileValue(model.methods[1]),
            "Yes. Pre-match chance: 10.5%. No. Pre-match chance: 89.5%"
        )
        XCTAssertEqual(
            model.accessibilityComparison,
            "Will the fight be won by KO or TKO?, original Yes. Pre-match chance: 55%, \(Self.lateDetail)"
        )
    }

    // MARK: During

    func testDuringRetainedPacketHasNoInFightChanceAndShowsWords() {
        let model = Self.input(.during)
        for (_, original) in Self.allOriginals(model) {
            XCTAssertEqual(model.currentReading(original), .missing("No in-fight chance"), original.id)
            XCTAssertFalse(model.showsCurrentMark(original), original.id)
            XCTAssertNil(model.result(original), original.id)
        }
        XCTAssertEqual(model.comparison, .during(model.methods[0].originals[0]))
        XCTAssertEqual(model.visibleActual, Self.official)
        XCTAssertTrue(model.accessibilityHeader.hasSuffix("During the fight"))
    }

    func testDuringComparesPreMatchAndInFightWithEachProvenance() {
        let model = Self.input(.during, Self.everythingSupplied)
        let yes = model.methods[0].originals[0]
        let no = model.methods[0].originals[1]
        XCTAssertEqual(model.beforeReading(yes), .value(Self.pregame(Self.row(Self.koYes))))
        XCTAssertEqual(model.currentReading(yes), .value(Self.koYesCurrent))
        XCTAssertTrue(model.showsCurrentMark(yes))
        XCTAssertEqual(model.movement(yes), "+16 points since pre-match")
        // Withheld stays words, has no filled key and never falls back to pre-match.
        XCTAssertEqual(model.currentReading(no), .missing("Held since round 1"))
        XCTAssertFalse(model.showsCurrentMark(no))
        XCTAssertNil(model.movement(no))
        XCTAssertEqual(
            model.accessibilityComparison,
            "Will the fight be won by KO or TKO?, original Yes. Pre-match chance: 55%, \(Self.lateDetail); In-fight chance: 71%, Recorded Oct 3, 5:31 PM PT · Polymarket; +16 points since pre-match"
        )
        XCTAssertEqual(
            model.accessibilityTileValue(model.methods[0]),
            "Yes. Pre-match chance: 55%, \(Self.lateDetail); In-fight chance: 71%, Recorded Oct 3, 5:31 PM PT · Polymarket; +16 points since pre-match. Selected. Also No. Pre-match chance: 45%; In-fight chance: Held since round 1"
        )
    }

    func testPhaseIsTheOwnersAndSettledContractsDoNotMakeItFinal() {
        // The raw event is suspended while contracts are settled: an owner
        // phase of `.during` hides every supplied result.
        let model = Self.input(.during)
        for (_, original) in Self.allOriginals(model) {
            XCTAssertNil(model.result(original), original.id)
        }
        XCTAssertFalse(model.accessibilityTileValue(model.methods[0]).contains("Won"))
    }

    // MARK: Final

    func testFinalKeepsEachPreMatchBesideItsOwnIndependentResult() {
        let model = Self.input(.final)
        let expected: [String: (CombatMethodResult10868, String)] = [
            Self.koYes: (.won("Won"), "checkmark.circle"),
            Self.koNo: (.lost("Lost"), "xmark.circle"),
            Self.subYes: (.lost("Lost"), "xmark.circle"),
            Self.subNo: (.won("Won"), "checkmark.circle"),
            Self.decYes: (.lost("Lost"), "xmark.circle"),
            Self.decNo: (.won("Won"), "checkmark.circle"),
        ]
        for (_, original) in Self.allOriginals(model) {
            XCTAssertEqual(model.result(original), expected[original.id]?.0, original.id)
            XCTAssertEqual(model.result(original)?.symbolName, expected[original.id]?.1, original.id)
            XCTAssertNil(model.currentReading(original), original.id)
            XCTAssertEqual(model.beforeReading(original), .value(Self.pregame(Self.row(original.id))), original.id)
        }
        XCTAssertEqual(model.comparison, .final(model.methods[0].originals[0], .won("Won")))
        XCTAssertTrue(model.accessibilityHeader.hasSuffix("Final"))
    }

    func testFinalIgnoresSettledQuotesAsChances() {
        // CONSTRUCTED: the settlement-time 100% / 0% quotes supplied as "current".
        let settled = [
            Self.method(Self.koID, [
                Self.original(Self.koYes, current: .recorded(Self.obs(1.0, "100%", "8:34 PM PT", "Recorded Oct 3, 8:34 PM PT"), movement: "+45 points")),
                Self.original(Self.koNo, current: .recorded(Self.obs(0.0, "0%", "8:34 PM PT", "Recorded Oct 3, 8:34 PM PT"), movement: nil)),
            ]),
        ]
        let model = Self.input(.final, settled)
        for original in model.methods[0].originals {
            XCTAssertNil(model.currentReading(original))
            XCTAssertNil(model.movement(original))
            XCTAssertFalse(model.showsCurrentMark(original))
        }
        let spoken = model.accessibilityTileValue(model.methods[0]) + (model.accessibilityComparison ?? "")
        for quote in ["100%", "0%", "+45", "In-fight"] {
            XCTAssertFalse(spoken.contains(quote), quote)
        }
    }

    func testResultSymbolFollowsTheDisplayedOriginalNotTheWinningSide() {
        let ko = Self.input(.final, method: Self.koID, original: Self.koNo)
        guard case .original(let koLead, selected: true) = ko.lead(ko.methods[0]) else { return XCTFail("ko") }
        XCTAssertEqual(koLead.id, Self.koNo)
        XCTAssertEqual(ko.result(koLead)?.symbolName, "xmark.circle")
        XCTAssertEqual(ko.result(ko.methods[0].originals[0])?.symbolName, "checkmark.circle")
        XCTAssertEqual(
            ko.accessibilitySideValue(koLead, in: ko.methods[0]),
            "Pre-match chance: 45%, \(Self.lateDetail); Contract result: Lost; Selected"
        )
        XCTAssertEqual(
            ko.accessibilityComparison,
            "Will the fight be won by KO or TKO?, original No. Pre-match chance: 45%, \(Self.lateDetail); Contract result: Lost"
        )

        let sub = Self.input(.final, method: Self.subID, original: Self.subNo)
        guard case .original(let subLead, selected: true) = sub.lead(sub.methods[1]) else { return XCTFail("sub") }
        XCTAssertEqual(sub.result(subLead)?.symbolName, "checkmark.circle")
        XCTAssertEqual(sub.result(sub.methods[1].originals[0])?.symbolName, "xmark.circle")
    }

    func testUnconfirmedIsNotALossAndOtherIsOwnerQualifiedWords() {
        // CONSTRUCTED results.
        let unconfirmed = CombatMethodResult10868.unconfirmed("Result unconfirmed")
        let other = CombatMethodResult10868.other("Under review")
        XCTAssertEqual(unconfirmed.symbolName, "questionmark.circle")
        XCTAssertFalse(unconfirmed.isSettled)
        XCTAssertEqual(other.symbolName, "info.circle")
        XCTAssertFalse(other.isSettled)
        XCTAssertTrue(CombatMethodResult10868.void("Void").isSettled)
        let model = Self.input(.final, [
            Self.method(Self.koID, [Self.original(Self.koYes, result: unconfirmed), Self.original(Self.koNo, result: other)]),
        ])
        XCTAssertEqual(model.result(model.methods[0].originals[0]), unconfirmed)
        XCTAssertEqual(model.result(model.methods[0].originals[1]), other)
        XCTAssertFalse(model.accessibilityTileValue(model.methods[0]).contains("Lost"))
        XCTAssertEqual(
            model.accessibilityTileValue(model.methods[0]),
            "Yes. Pre-match chance: 55%, \(Self.lateDetail); Contract result: Result unconfirmed. Selected. Also No. Pre-match chance: 45%; Contract result: Under review"
        )
    }

    // MARK: Official bout context

    func testOfficialBoutContextIsSeparateAndNeverGradesAContract() {
        XCTAssertNil(Self.input(.before).visibleActual)
        XCTAssertEqual(Self.input(.during).visibleActual, Self.official)
        let model = Self.input(.final)
        XCTAssertEqual(
            model.accessibilityActual,
            "Official bout result. Roman Kopylov def. Ateba Gautier · TKO (strikes) · Round 1, 3:12. UFC results page, captured Oct 13 · finish clock not recorded"
        )
        // CONSTRUCTED: the bout ended by TKO, but an unconfirmed KO contract stays unconfirmed.
        let held = Self.input(.final, [
            Self.method(Self.koID, [
                Self.original(Self.koYes, result: .unconfirmed("Result unconfirmed")),
                Self.original(Self.koNo, result: .unconfirmed("Result unconfirmed")),
            ]),
        ])
        for original in held.methods[0].originals {
            XCTAssertEqual(held.result(original), .unconfirmed("Result unconfirmed"))
        }
        XCTAssertFalse(held.accessibilityTileValue(held.methods[0]).contains("strikes"))
        XCTAssertFalse((held.accessibilityComparison ?? "").contains("strikes"))
        XCTAssertNil(Self.input(.final, actual: nil).accessibilityActual)
    }

    // MARK: Identity

    func testMissingSelectedSideStaysUnavailableAndAllSidesStayListed() {
        let model = Self.input(.final, method: Self.koID, original: "999")
        XCTAssertEqual(model.selection, .sideUnavailable(model.methods[0], "999"))
        XCTAssertEqual(model.lead(model.methods[0]), .unavailable(CombatMethodInput10868.sideUnavailableShort))
        XCTAssertEqual(model.selectionNotice, CombatMethodInput10868.sideUnavailable)
        XCTAssertNil(model.comparison)
        XCTAssertNil(model.accessibilityComparison)
        XCTAssertNil(model.tileAction(model.methods[0], canSelect: true))
        XCTAssertNil(model.detailsAction(canOpenDetails: true))
        XCTAssertEqual(
            model.accessibilityTileValue(model.methods[0]),
            "Selected side unavailable. Yes. Pre-match chance: 55%; Contract result: Won. No. Pre-match chance: 45%; Contract result: Lost. Method selected"
        )
        for original in model.methods[0].originals {
            XCTAssertEqual(model.sideAction(original, in: model.methods[0], canSelect: true), .select(Self.ref(Self.koID, original.id)))
            XCTAssertFalse(model.isSelected(original, in: model.methods[0]))
        }
    }

    func testMissingMethodKeepsOverviewTilesAndSelectsNothing() {
        let model = Self.input(.before, Self.retainedMethods(overview: [Self.subID: Self.subYes]), method: "retired-method", original: Self.koYes)
        XCTAssertEqual(model.selection, .unavailable("retired-method"))
        XCTAssertEqual(model.selectionNotice, CombatMethodInput10868.methodUnavailable)
        XCTAssertNil(model.comparison)
        XCTAssertFalse(model.methods.contains { model.isSelectedMethod($0) })
        XCTAssertEqual(model.lead(model.methods[0]), .sides)
        XCTAssertEqual(model.lead(model.methods[1]), .original(model.methods[1].originals[0], selected: false))
    }

    func testSideNamedWithoutItsMethodResolvesOnlyWhenUnique() {
        let found = Self.input(.before, method: nil, original: Self.subNo)
        XCTAssertEqual(found.selection, .original(found.methods[1], found.methods[1].originals[1]))
        XCTAssertTrue(found.isSelectedMethod(found.methods[1]))
        XCTAssertEqual(Self.input(.before, method: nil, original: "999").selection, .unavailable("999"))
        XCTAssertEqual(Self.input(.before, method: nil, original: nil).selection, .none)
        let methodOnly = Self.input(.before, method: Self.decID, original: nil)
        XCTAssertEqual(methodOnly.selection, .method(methodOnly.methods[2]))
        XCTAssertNil(methodOnly.comparison)
        XCTAssertNil(methodOnly.detailsAction(canOpenDetails: true))
        XCTAssertTrue(methodOnly.accessibilityTileValue(methodOnly.methods[2]).hasSuffix(CombatMethodInput10868.methodSelectedTag))
    }

    func testDuplicateOriginalIdsCarryNoActionAndCannotResolve() {
        // CONSTRUCTED: the Submission No arrives carrying the KO No id.
        let dupe = CombatMethodOriginal10868(
            id: Self.koNo,
            marketID: "63634393",
            label: "No",
            before: Self.pregame(Self.row(Self.subNo)),
            beforeMissing: Self.notRecorded,
            current: Self.noCurrent,
            result: .won("Won")
        )
        let methods = [
            Self.method(Self.koID, [Self.original(Self.koYes), Self.original(Self.koNo)], overview: Self.koNo),
            Self.method(Self.subID, [Self.original(Self.subYes), dupe]),
        ]
        let model = Self.input(.final, methods, method: Self.koID, original: Self.koNo)
        XCTAssertEqual(model.duplicateOriginalIDs, [Self.koNo])
        XCTAssertEqual(model.selection, .sideUnavailable(model.methods[0], Self.koNo))
        XCTAssertNil(model.sideAction(model.methods[0].originals[1], in: model.methods[0], canSelect: true))
        XCTAssertNil(model.sideAction(dupe, in: model.methods[1], canSelect: true))
        XCTAssertNotNil(model.sideAction(model.methods[0].originals[0], in: model.methods[0], canSelect: true))
        XCTAssertEqual(Self.input(.final, methods, method: nil, original: Self.koNo).selection, .unavailable(Self.koNo))
        let overview = Self.input(.final, methods, method: nil, original: nil)
        XCTAssertEqual(overview.lead(overview.methods[0]), .unavailable(CombatMethodInput10868.overviewUnavailable))
        XCTAssertNil(overview.tileAction(overview.methods[0], canSelect: true))
    }

    func testDuplicateMethodIdsCarryNoTileOrSideAction() {
        // CONSTRUCTED: two methods arrive with one id.
        let methods = [
            Self.method(Self.koID, [Self.original(Self.koYes), Self.original(Self.koNo)], overview: Self.koYes),
            Self.method(Self.koID, [Self.original(Self.subYes), Self.original(Self.subNo)], overview: Self.subYes),
        ]
        let model = Self.input(.before, methods, method: Self.koID, original: Self.koYes)
        XCTAssertEqual(model.duplicateMethodIDs, [Self.koID])
        XCTAssertEqual(model.selection, .unavailable(Self.koID))
        for method in model.methods {
            XCTAssertNil(model.tileAction(method, canSelect: true))
            XCTAssertFalse(model.isSelectedMethod(method))
            for original in method.originals {
                XCTAssertNil(model.sideAction(original, in: method, canSelect: true))
            }
        }
    }

    // MARK: Actions

    func testExactActionsCarryEventMethodMarketAndOriginal() {
        let model = Self.input(.final, Self.retainedMethods(overview: [Self.subID: Self.subNo]), method: Self.koID, original: Self.koYes)
        XCTAssertEqual(model.tileAction(model.methods[0], canSelect: true), .select(Self.ref(Self.koID, Self.koYes)))
        XCTAssertEqual(model.tileAction(model.methods[1], canSelect: true), .select(Self.ref(Self.subID, Self.subNo)))
        XCTAssertEqual(model.ref(model.methods[2].originals[1], in: model.methods[2]),
                       CombatMethodOriginalRef10868(eventID: "15318681", methodID: Self.decID, marketID: "63786883", originalID: Self.decNo))
        XCTAssertEqual(model.detailsAction(canOpenDetails: true), .details(Self.ref(Self.koID, Self.koYes)))

        var selected: [CombatMethodOriginalRef10868] = []
        var details: [CombatMethodOriginalRef10868] = []
        model.sideAction(model.methods[0].originals[1], in: model.methods[0], canSelect: true)?
            .perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        model.detailsAction(canOpenDetails: true)?
            .perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        XCTAssertEqual(selected, [Self.ref(Self.koID, Self.koNo)])
        XCTAssertEqual(details, [Self.ref(Self.koID, Self.koYes)])
    }

    func testNoCallbacksMeansStaticContentAndNoInstruction() {
        let model = Self.input(.during, Self.retainedMethods(overview: [Self.subID: Self.subYes]))
        XCTAssertNil(model.instruction(canSelect: false))
        XCTAssertEqual(model.instruction(canSelect: true), CombatMethodInput10868.chooseInstruction)
        XCTAssertNil(Self.input(.before, []).instruction(canSelect: true))
        XCTAssertNil(model.detailsAction(canOpenDetails: false))
        for (method, original) in Self.allOriginals(model) {
            XCTAssertNil(model.tileAction(method, canSelect: false))
            XCTAssertNil(model.sideAction(original, in: method, canSelect: false))
        }
    }

    func testEveryOriginalIsReachableBySightActionAndVoiceOver() {
        for phase in [CombatMethodPhase10868.before, .during, .final] {
            let model = Self.input(phase)
            var refs = Set<CombatMethodOriginalRef10868>()
            for method in model.methods {
                let spoken = model.accessibilityTileValue(method)
                for original in method.originals {
                    guard case .select(let ref)? = model.sideAction(original, in: method, canSelect: true) else {
                        return XCTFail("\(phase) \(original.id)")
                    }
                    refs.insert(ref)
                    XCTAssertTrue(spoken.contains("\(original.label). Pre-match chance: \(Self.row(original.id).text)"), "\(phase) \(original.id)")
                }
            }
            XCTAssertEqual(refs.map(\.originalID).sorted(), Self.retained.map(\.outcomeID).sorted())
        }
    }

    // MARK: Tile presentation (the View's own branch)

    private static let phases: [CombatMethodPhase10868] = [.before, .during, .final]

    private static func listed(_ method: CombatMethod10868, _ originals: [CombatMethodOriginal10868], actionable: Bool) -> [CombatMethodTileSide10868] {
        originals.map { CombatMethodTileSide10868(original: $0, action: actionable ? .select(ref(method.id, $0.id)) : nil) }
    }

    func testInvalidOverviewWithValidAlternativesListsEveryOriginalWithExactActions() {
        // CONSTRUCTED: KO's overview names an id it does not carry; Submission's
        // overview No was withdrawn. Decision's overview is valid.
        let methods = [
            Self.method(Self.koID, [Self.original(Self.koYes), Self.original(Self.koNo)], overview: "999"),
            Self.method(Self.subID, [Self.original(Self.subYes)], overview: Self.subNo),
            Self.method(Self.decID, [Self.original(Self.decYes), Self.original(Self.decNo)], overview: Self.decNo),
        ]
        let selections: [(String?, String?)] = [(nil, nil), (Self.decID, Self.decNo)]
        for phase in Self.phases {
            for (selectedMethod, selectedOriginal) in selections {
                let model = Self.input(phase, methods, method: selectedMethod, original: selectedOriginal)
                let label = "\(phase) \(selectedMethod ?? "none")"
                for method in model.methods.prefix(2) {
                    XCTAssertEqual(model.lead(method), .unavailable(CombatMethodInput10868.overviewUnavailable), label)
                    XCTAssertNil(model.tileAction(method, canSelect: true), label)
                    XCTAssertNotEqual(model.selection.method, method, label)
                    XCTAssertEqual(
                        model.tilePresentation(method, canSelect: true),
                        .unavailableWithSides(CombatMethodInput10868.overviewUnavailable, sides: Self.listed(method, method.originals, actionable: true)),
                        label
                    )
                    // Without a callback the same originals stay listed, static.
                    XCTAssertEqual(
                        model.tilePresentation(method, canSelect: false),
                        .unavailableWithSides(CombatMethodInput10868.overviewUnavailable, sides: Self.listed(method, method.originals, actionable: false)),
                        label
                    )
                }
                let decision = model.methods[2]
                XCTAssertEqual(
                    model.tilePresentation(decision, canSelect: true),
                    .ring(decision.originals[1], selected: selectedMethod != nil, action: .select(Self.ref(Self.decID, Self.decNo))),
                    label
                )
            }
        }
    }

    func testStaticOverviewOnUnselectedMethodKeepsRingAndListsOtherOriginals() {
        let overview = [Self.koID: Self.koYes, Self.subID: Self.subNo, Self.decID: Self.decYes]
        for phase in Self.phases {
            let model = Self.input(phase, Self.retainedMethods(overview: overview), method: Self.koID, original: Self.koYes)
            let ko = model.methods[0]
            let sub = model.methods[1]
            let dec = model.methods[2]
            // The selected method keeps its ring; the side row beneath lists its sides.
            XCTAssertEqual(model.selection.method, ko)
            XCTAssertEqual(model.tilePresentation(ko, canSelect: false), .ring(ko.originals[0], selected: true, action: nil))
            // Unselected static overviews keep the ring and list the other original.
            XCTAssertEqual(model.tilePresentation(sub, canSelect: false), .ringWithSides(sub.originals[1], others: Self.listed(sub, [sub.originals[0]], actionable: false)))
            XCTAssertEqual(model.tilePresentation(dec, canSelect: false), .ringWithSides(dec.originals[0], others: Self.listed(dec, [dec.originals[1]], actionable: false)))

            // Static rows keep each original's phase-specific readings and provenance.
            let later: (String, String)
            switch phase {
            case .before: later = ("", "")
            case .during: later = ("; In-fight chance: No in-fight chance", "; In-fight chance: No in-fight chance")
            case .final: later = ("; Contract result: Won", "; Contract result: Lost")
            }
            XCTAssertEqual(model.accessibilityLeadValue(sub.originals[1]), "No. Pre-match chance: 89.5%, \(Self.lateDetail)\(later.0)", "\(phase)")
            XCTAssertEqual(model.accessibilitySideValue(sub.originals[0], in: sub), "Pre-match chance: 10.5%, \(Self.lateDetail)\(later.1)", "\(phase)")
            XCTAssertEqual(model.accessibilitySideValue(dec.originals[1], in: dec), "Pre-match chance: 49%, \(Self.earlyDetail)\(phase == .final ? "; Contract result: Won" : later.0)", "\(phase)")

            // CONSTRUCTED: a method carrying one original has nothing else to list.
            let lone = Self.input(phase, [Self.method(Self.koID, [Self.original(Self.koYes)], overview: Self.koYes)], method: nil, original: nil)
            XCTAssertEqual(lone.tilePresentation(lone.methods[0], canSelect: false), .ring(lone.methods[0].originals[0], selected: false, action: nil))

            // With nothing selected every static overview lists its other side.
            let none = Self.input(phase, Self.retainedMethods(overview: overview), method: nil, original: nil)
            for method in none.methods {
                guard case .ringWithSides(let lead, let others) = none.tilePresentation(method, canSelect: false) else {
                    return XCTFail("\(phase) \(method.id)")
                }
                XCTAssertEqual(lead.id, method.overviewOriginalID)
                XCTAssertEqual(Set(others.map(\.original.id)).union([lead.id]), Set(method.originals.map(\.id)))
                XCTAssertTrue(others.allSatisfy { $0.action == nil })
            }
        }
    }

    func testDuplicatesKeepTheStaticFallbackWithoutAmbiguousActions() {
        for phase in Self.phases {
            // CONSTRUCTED: two methods arrive with one id, each with a valid overview.
            let twins = Self.input(phase, [
                Self.method(Self.koID, [Self.original(Self.koYes), Self.original(Self.koNo)], overview: Self.koYes),
                Self.method(Self.koID, [Self.original(Self.subYes), Self.original(Self.subNo)], overview: Self.subYes),
            ], method: nil, original: nil)
            for method in twins.methods {
                XCTAssertEqual(
                    twins.tilePresentation(method, canSelect: true),
                    .ringWithSides(method.originals[0], others: Self.listed(method, [method.originals[1]], actionable: false)),
                    "\(phase)"
                )
            }

            // CONSTRUCTED: the Submission No carries the KO No id, and KO's overview names it.
            let dupe = CombatMethodOriginal10868(
                id: Self.koNo,
                marketID: "63634393",
                label: "No",
                before: Self.pregame(Self.row(Self.subNo)),
                beforeMissing: Self.notRecorded,
                current: Self.noCurrent,
                result: .won("Won")
            )
            let model = Self.input(phase, [
                Self.method(Self.koID, [Self.original(Self.koYes), Self.original(Self.koNo)], overview: Self.koNo),
                Self.method(Self.subID, [Self.original(Self.subYes), dupe], overview: Self.subYes),
            ], method: nil, original: nil)
            let ko = model.methods[0]
            let sub = model.methods[1]
            XCTAssertEqual(
                model.tilePresentation(ko, canSelect: true),
                .unavailableWithSides(CombatMethodInput10868.overviewUnavailable, sides: [
                    CombatMethodTileSide10868(original: ko.originals[0], action: .select(Self.ref(Self.koID, Self.koYes))),
                    CombatMethodTileSide10868(original: ko.originals[1], action: nil),
                ]),
                "\(phase)"
            )
            XCTAssertEqual(model.tilePresentation(sub, canSelect: true), .ring(sub.originals[0], selected: false, action: .select(Self.ref(Self.subID, Self.subYes))))
            XCTAssertEqual(model.tilePresentation(sub, canSelect: false), .ringWithSides(sub.originals[0], others: [CombatMethodTileSide10868(original: dupe, action: nil)]))
        }
    }

    func testSelectedMethodTileNeverRepeatsItsSideRow() {
        for phase in Self.phases {
            // Withdrawn selected side: the notice alone; the side row beneath lists both.
            let missing = Self.input(phase, method: Self.koID, original: "999")
            let ko = missing.methods[0]
            XCTAssertEqual(missing.selection.method, ko)
            for canSelect in [true, false] {
                XCTAssertEqual(missing.tilePresentation(ko, canSelect: canSelect), .unavailable(CombatMethodInput10868.sideUnavailableShort), "\(phase)")
            }
            // Method selected without a side, static overview: the ring alone.
            let methodOnly = Self.input(phase, Self.retainedMethods(overview: [Self.subID: Self.subNo]), method: Self.subID, original: nil)
            XCTAssertEqual(methodOnly.selection.method, methodOnly.methods[1])
            XCTAssertEqual(methodOnly.tilePresentation(methodOnly.methods[1], canSelect: false), .ring(methodOnly.methods[1].originals[1], selected: false, action: nil))
            // Selected side, static: the ring alone.
            let picked = Self.input(phase, method: Self.subID, original: Self.subNo)
            XCTAssertEqual(picked.tilePresentation(picked.methods[1], canSelect: false), .ring(picked.methods[1].originals[1], selected: true, action: nil))
            // An unselected method whose overview is invalid still lists its sides.
            let elsewhere = Self.input(phase, Self.retainedMethods(overview: [Self.decID: "999"]), method: Self.koID, original: "999")
            XCTAssertEqual(elsewhere.tilePresentation(elsewhere.methods[0], canSelect: true), .unavailable(CombatMethodInput10868.sideUnavailableShort))
            XCTAssertEqual(
                elsewhere.tilePresentation(elsewhere.methods[2], canSelect: true),
                .unavailableWithSides(CombatMethodInput10868.overviewUnavailable, sides: Self.listed(elsewhere.methods[2], elsewhere.methods[2].originals, actionable: true))
            )
        }
    }

    func testActionableOverviewStaysTheCompactRingTile() {
        for phase in Self.phases {
            let model = Self.input(phase, Self.retainedMethods(overview: [Self.subID: Self.subYes, Self.decID: Self.decNo]), method: nil, original: nil)
            let ko = model.methods[0]
            let sub = model.methods[1]
            let dec = model.methods[2]
            XCTAssertEqual(model.tilePresentation(sub, canSelect: true), .ring(sub.originals[0], selected: false, action: .select(Self.ref(Self.subID, Self.subYes))))
            XCTAssertEqual(model.tilePresentation(dec, canSelect: true), .ring(dec.originals[1], selected: false, action: .select(Self.ref(Self.decID, Self.decNo))))
            XCTAssertTrue(model.tilePresentation(sub, canSelect: true).listed.isEmpty)
            XCTAssertTrue(model.tilePresentation(dec, canSelect: true).listed.isEmpty)
            // No overview: the side list is unchanged, actionable or static.
            XCTAssertEqual(model.tilePresentation(ko, canSelect: true), .sides(Self.listed(ko, ko.originals, actionable: true)))
            XCTAssertEqual(model.tilePresentation(ko, canSelect: false), .sides(Self.listed(ko, ko.originals, actionable: false)))
        }
    }

    func testEveryOriginalIsOnScreenOrOneTileActionFromItsSideRow() {
        let overviews: [[String: String]] = [
            [:],
            [Self.koID: Self.koYes, Self.subID: Self.subNo, Self.decID: Self.decYes],
            [Self.koID: "999", Self.subID: Self.subNo, Self.decID: Self.decYes],
        ]
        let selections: [(String?, String?)] = [
            (nil, nil), (Self.koID, Self.koYes), (Self.koID, "999"), (Self.subID, nil), ("retired-method", nil), (nil, Self.decNo),
        ]
        for phase in Self.phases {
            for overview in overviews {
                for (selectedMethod, selectedOriginal) in selections {
                    let model = Self.input(phase, Self.retainedMethods(overview: overview), method: selectedMethod, original: selectedOriginal)
                    for canSelect in [true, false] {
                        for method in model.methods {
                            let label = "\(phase) \(overview) \(selectedMethod ?? "-")/\(selectedOriginal ?? "-") \(canSelect) \(method.id)"
                            let presentation = model.tilePresentation(method, canSelect: canSelect)
                            var shown = Set(presentation.listed.map(\.original.id))
                            var tileAction: CombatMethodAction10868?
                            switch presentation {
                            case .ring(let lead, _, let action):
                                shown.insert(lead.id)
                                tileAction = action
                            case .ringWithSides(let lead, _):
                                shown.insert(lead.id)
                            case .unavailable, .unavailableWithSides, .sides:
                                break
                            }
                            // The rows the selected panel actually mounts for this method — the
                            // View's own list — counted where they are, never assumed.
                            let panel = model.panelSides(method, canSelect: canSelect)
                            shown.formUnion(panel.map(\.original.id))
                            if !panel.isEmpty {
                                XCTAssertEqual(model.selection.method, method, label)
                                XCTAssertEqual(panel.map(\.original.id), method.originals.map(\.id), label)
                            }
                            if model.selection.method == method {
                                // Exactly one place lists the selected method's sides: its tile or the panel.
                                XCTAssertNotEqual(panel.isEmpty, presentation.listed.isEmpty, label)
                            }
                            // No original is mounted as a side row twice.
                            let rows = presentation.listed.map(\.original.id) + panel.map(\.original.id)
                            XCTAssertEqual(rows.count, Set(rows).count, label)
                            if shown != Set(method.originals.map(\.id)) {
                                // Only an actionable ring may leave a side off screen: its action
                                // selects this method, whose side row then lists every side.
                                guard case .select(let ref)? = tileAction else { XCTFail(label); continue }
                                XCTAssertEqual(ref.methodID, method.id, label)
                            }
                            for side in presentation.listed + panel {
                                XCTAssertEqual(side.action, model.sideAction(side.original, in: method, canSelect: canSelect), label)
                            }
                            if !canSelect {
                                XCTAssertTrue(presentation.listed.allSatisfy { $0.action == nil }, label)
                                XCTAssertTrue(panel.allSatisfy { $0.action == nil }, label)
                                XCTAssertNil(tileAction, label)
                            }
                        }
                    }
                }
            }
        }
    }

    func testMethodChosenWithoutSideOrOverviewMountsEachOriginalOnce() {
        for phase in Self.phases {
            // The host chose Decision / draw but no side, and named no overview side.
            let model = Self.input(phase, method: Self.decID, original: nil)
            let dec = model.methods[2]
            XCTAssertEqual(model.selection, .method(dec), "\(phase)")
            XCTAssertEqual(model.lead(dec), .sides, "\(phase)")
            // The selected context stays: the panel keeps the full prop question; no
            // side is chosen for the reader, so no comparison or details action.
            XCTAssertEqual(model.selection.method?.question, "Will the fight end in a decision or draw?", "\(phase)")
            XCTAssertNil(model.comparison, "\(phase)")
            XCTAssertNil(model.detailsAction(canOpenDetails: true), "\(phase)")
            XCTAssertTrue(model.accessibilityTileValue(dec).hasSuffix(CombatMethodInput10868.methodSelectedTag), "\(phase)")
            XCTAssertFalse(model.panelListsSides(dec), "\(phase)")

            // Each phase's later reading, per original, as its row speaks it.
            let later: [String: String]
            switch phase {
            case .before: later = [Self.decYes: "", Self.decNo: ""]
            case .during: later = [Self.decYes: "; In-fight chance: No in-fight chance", Self.decNo: "; In-fight chance: No in-fight chance"]
            case .final: later = [Self.decYes: "; Contract result: Lost", Self.decNo: "; Contract result: Won"]
            }

            for canSelect in [true, false] {
                let label = "\(phase) \(canSelect)"
                let tile = model.tilePresentation(dec, canSelect: canSelect)
                let panel = model.panelSides(dec, canSelect: canSelect)
                // The tile keeps its compact list of every original; the panel lists none.
                XCTAssertEqual(tile, .sides(Self.listed(dec, dec.originals, actionable: canSelect)), label)
                XCTAssertEqual(panel, [], label)
                let rows = tile.listed + panel
                for original in dec.originals {
                    XCTAssertEqual(rows.filter { $0.original.id == original.id }.count, 1, "\(label) \(original.id)")
                }
                // Each row keeps its exact action (or none without a callback) and its
                // identifier is mounted once.
                var selected: [CombatMethodOriginalRef10868] = []
                for side in rows {
                    XCTAssertEqual(side.action, canSelect ? .select(Self.ref(Self.decID, side.original.id)) : nil, label)
                    side.action?.perform(onSelect: { selected.append($0) }, onDetails: { _ in XCTFail(label) })
                }
                XCTAssertEqual(selected, canSelect ? [Self.ref(Self.decID, Self.decYes), Self.ref(Self.decID, Self.decNo)] : [], label)
                let identifiers = rows.map { CombatMethodAccessibilityID10868.side(dec.id, $0.original.id) }
                XCTAssertEqual(identifiers.count, Set(identifiers).count, label)
                // VoiceOver: each row's readings with full provenance; nothing reads as Selected.
                for side in rows {
                    let spoken = model.accessibilitySideValue(side.original, in: dec)
                    XCTAssertEqual(
                        spoken,
                        "Pre-match chance: \(Self.row(side.original.id).text), \(Self.earlyDetail)\(later[side.original.id]!)",
                        "\(label) \(side.original.id)"
                    )
                    XCTAssertFalse(spoken.contains(CombatMethodInput10868.selectedTag), "\(label) \(side.original.id)")
                }
                // The unselected methods are unchanged: their own tile lists, no panel.
                for method in model.methods.prefix(2) {
                    XCTAssertEqual(model.tilePresentation(method, canSelect: canSelect), .sides(Self.listed(method, method.originals, actionable: canSelect)), label)
                    XCTAssertEqual(model.panelSides(method, canSelect: canSelect), [], label)
                }

                // Contrast: with an overview side, or a chosen side, the tile is the ring
                // and the panel mounts every side row, once.
                let withOverview = Self.input(phase, Self.retainedMethods(overview: [Self.decID: Self.decYes]), method: Self.decID, original: nil)
                let overviewDec = withOverview.methods[2]
                XCTAssertTrue(withOverview.panelListsSides(overviewDec), label)
                XCTAssertEqual(
                    withOverview.tilePresentation(overviewDec, canSelect: canSelect),
                    .ring(overviewDec.originals[0], selected: false, action: canSelect ? .select(Self.ref(Self.decID, Self.decYes)) : nil),
                    label
                )
                XCTAssertEqual(withOverview.panelSides(overviewDec, canSelect: canSelect), Self.listed(overviewDec, overviewDec.originals, actionable: canSelect), label)
                let picked = Self.input(phase, method: Self.decID, original: Self.decNo)
                let pickedDec = picked.methods[2]
                XCTAssertEqual(picked.tilePresentation(pickedDec, canSelect: canSelect), .ring(pickedDec.originals[1], selected: true, action: canSelect ? .select(Self.ref(Self.decID, Self.decNo)) : nil), label)
                XCTAssertEqual(picked.panelSides(pickedDec, canSelect: canSelect), Self.listed(pickedDec, pickedDec.originals, actionable: canSelect), label)
            }
        }
    }

    func testTimingOnlyForTheExactResolvedSelection() {
        let timing = CombatMethodTiming10868(originalID: Self.koYes, title: "Times", lines: ["Pre-match recorded Oct 3, 4:27 PM PT"])
        XCTAssertEqual(Self.input(.before, timing: timing).timingPresentation(hasBinding: false), .expanded(timing))
        XCTAssertEqual(Self.input(.before, timing: timing).timingPresentation(hasBinding: true), .disclosure(timing))
        XCTAssertNil(Self.input(.before, original: Self.koNo, timing: timing).timingPresentation(hasBinding: true))
        XCTAssertNil(Self.input(.before, original: "999", timing: timing).timingPresentation(hasBinding: true))
        XCTAssertNil(Self.input(.before, method: Self.koID, original: nil, timing: timing).timingPresentation(hasBinding: true))
    }

    // MARK: Non-colour keys

    func testResultSelectionAndSeriesKeysAreDistinctShapesAndWords() {
        let results: [CombatMethodResult10868] = [.won("Won"), .lost("Lost"), .void("Void"), .unconfirmed("Result unconfirmed"), .other("Under review")]
        let symbols = results.map(\.symbolName)
        XCTAssertEqual(Set(symbols).count, results.count)
        // The selection tag's plain checkmark is not any result's circled symbol.
        XCTAssertFalse(symbols.contains("checkmark"))
        XCTAssertEqual(CombatMethodInput10868.selectedTag, "Selected")
        XCTAssertEqual(CombatMethodInput10868.preMatchShort, "Pre-match")
        XCTAssertEqual(CombatMethodInput10868.currentShort, "In-fight")
        XCTAssertNotEqual(CombatMethodInput10868.resultTitle, CombatMethodInput10868.preMatchTitle)
        XCTAssertEqual(CombatMethodAccessibilityID10868.tile(Self.koID), "combatMethod10868.tile.ko-tko")
        XCTAssertEqual(CombatMethodAccessibilityID10868.side(Self.koID, Self.koNo), "combatMethod10868.side.ko-tko.240262497")
        XCTAssertEqual(CombatMethodAccessibilityID10868.details(Self.koYes), "combatMethod10868.details.240262496")
    }

    // MARK: Zero, absent and malformed

    func testZeroIsADrawnReadingAndAbsentIsWords() {
        // CONSTRUCTED.
        let methods = [
            Self.method(Self.koID, [
                Self.original(Self.koYes, before: .some(Self.obs(0.0, "0%", "4:27 PM PT", Self.lateDetail))),
                Self.original(Self.koNo, before: .some(nil)),
            ]),
        ]
        let model = Self.input(.before, methods)
        let yes = model.methods[0].originals[0]
        let no = model.methods[0].originals[1]
        guard case .value(let zero) = model.beforeReading(yes) else { return XCTFail("zero") }
        XCTAssertEqual(CombatMethodGeometry10868.ringFraction(zero.probability), 0)
        XCTAssertEqual(model.beforeReading(no), .missing(Self.notRecorded))
        XCTAssertEqual(
            model.accessibilityTileValue(model.methods[0]),
            "Yes. Pre-match chance: 0%, \(Self.lateDetail). Selected. Also No. Pre-match chance: \(Self.notRecorded)"
        )
    }

    func testMalformedProbabilityDrawsNoArcAndKeepsTheOwnersFigure() {
        for bad in [Double.nan, -0.01, 1.2, .infinity] {
            XCTAssertNil(CombatMethodGeometry10868.ringFraction(bad), "\(bad)")
        }
        XCTAssertEqual(CombatMethodGeometry10868.ringFraction(1), 1)
        XCTAssertEqual(CombatMethodGeometry10868.ringFraction(0.105), 0.105)
        let model = Self.input(.before, [
            Self.method(Self.koID, [Self.original(Self.koYes, before: .some(Self.obs(.nan, "55%", nil, Self.lateDetail))), Self.original(Self.koNo)]),
        ])
        guard case .value(let reading) = model.beforeReading(model.methods[0].originals[0]) else { return XCTFail("bad") }
        XCTAssertEqual(reading.text, "55%")
    }

    // MARK: Measured layout (arithmetic; CONSTRUCTED widths)

    func testRingGrowsForALongFigureAndNeverShrinksIt() {
        XCTAssertEqual(CombatMethodGeometry10868.ringSide(minimum: 60, figure: CGSize(width: 20, height: 10)), 60)
        // diagonal 44.72 + 2 × 9 inset → 63
        XCTAssertEqual(CombatMethodGeometry10868.ringSide(minimum: 60, figure: CGSize(width: 40, height: 20)), 63)
        XCTAssertEqual(CombatMethodGeometry10868.ringSide(minimum: 60, figure: CGSize(width: CGFloat.nan, height: 20)), 60)
    }

    func testThreeRetainedMethodsShareOneCompactRowAtPhoneWidth() {
        let all: (CGFloat) -> Bool = { _ in true }
        // 375 − 2 × 24 padding = 327; 393 → 345.
        for width: CGFloat in [327, 345] {
            XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: width, count: 3, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: all), 3)
        }
        XCTAssertEqual(CombatMethodGeometry10868.columnWidth(available: 327, columns: 3, spacing: 8), 311.0 / 3.0, accuracy: 1e-9)
        // 320 − 32 = 288: a column would be 90.7 < 96, so two columns then one.
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 288, count: 3, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: all), 2)
        XCTAssertEqual(CombatMethodGeometry10868.rows(count: 3, columns: 2), [[0, 1], [2]])
        XCTAssertEqual(CombatMethodGeometry10868.rows(count: 3, columns: 3), [[0, 1, 2]])
    }

    func testALongWordDropsAColumnInsteadOfBreakingOrShrinking() {
        // CONSTRUCTED: a "Disqualification" tile measures 120pt wide at its widest word.
        let needs120: (CGFloat) -> Bool = { $0 >= 120 }
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 327, count: 3, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: needs120), 2)
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 240, count: 3, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: needs120), 1)
        XCTAssertEqual(CombatMethodGeometry10868.words("Decision / draw"), ["Decision", "/", "draw"])
        XCTAssertEqual(CombatMethodGeometry10868.words("  KO\n/ TKO "), ["KO", "/", "TKO"])
        XCTAssertEqual(CombatMethodGeometry10868.words("Disqualification"), ["Disqualification"])
        XCTAssertEqual(CombatMethodGeometry10868.words(""), [])
    }

    func testEnlargedTextStacksAndWideHasNoThreeItemCeiling() {
        let all: (CGFloat) -> Bool = { _ in true }
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 327, count: 3, spacing: 8, minimumColumnWidth: 96, forceSingle: true, fits: all), 1)
        // A larger scaled minimum (enlarged, non-accessibility text) drops to two.
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 327, count: 3, spacing: 8, minimumColumnWidth: 150, forceSingle: false, fits: all), 2)
        // Six owner methods at 834 − 48 = 786 keep six columns.
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 786, count: 6, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: all), 6)
        XCTAssertEqual(CombatMethodGeometry10868.rows(count: 5, columns: 2), [[0, 1], [2, 3], [4]])
        // Ideal size and unbounded widths keep one row; nothing else is invented.
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: nil, count: 3, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: all), 3)
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: .infinity, count: 3, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: all), 3)
        // Malformed inputs fall back to one column, never an overlap.
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 0, count: 3, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: all), 1)
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 327, count: 3, spacing: 8, minimumColumnWidth: .nan, forceSingle: false, fits: all), 1)
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 327, count: 0, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: all), 0)
        XCTAssertEqual(CombatMethodGeometry10868.rows(count: 0, columns: 3), [])
        XCTAssertEqual(CombatMethodGeometry10868.rows(count: 3, columns: 0), [])
        XCTAssertEqual(CombatMethodGeometry10868.columnWidth(available: 327, columns: 0, spacing: 8), 0)
    }

    func testComparisonPairSitsSideBySideOnlyWhenBothFiguresStayWhole() {
        XCTAssertEqual(CombatMethodGeometry10868.pairArrangement(available: 327, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: false), .sideBySide)
        XCTAssertEqual(CombatMethodGeometry10868.pairArrangement(available: 240, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: false), .stacked)
        XCTAssertEqual(CombatMethodGeometry10868.pairArrangement(available: 327, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: true), .stacked)
        XCTAssertEqual(CombatMethodGeometry10868.pairArrangement(available: 327, first: .nan, second: 100, spacing: 16, equalColumns: true, forceStack: false), .stacked)
        XCTAssertEqual(CombatMethodGeometry10868.pairArrangement(available: nil, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: false), .sideBySide)
        XCTAssertEqual(CombatMethodGeometry10868.columns(total: 327, first: 120, spacing: 16, equalColumns: true), CombatMethodColumns10868(first: 155.5, second: 155.5))
    }

    // MARK: Fighter knockout (the same tiles, the owner's words)

    /// ARCHIVED from `shipping-adoption-20261027/COMBAT-FIGHTER-KO-RETAINED-CASES.json`
    /// (sha256 26579a33…fdf3), same event and pre-start clock as the methods:
    ///   Roman Kopylov by KO/TKO 63900810  Yes 240654996 0.125 Won   No 240654997 0.875 Lost
    ///   Ateba Gautier by KO/TKO 63786875  Yes 240262498 0.40  Lost  No 240262499 0.60  Won
    /// Two independent named-fighter predicates — not head-to-head win chances
    /// and not one distribution (the Yes values sum to 0.525). No in-fight quote
    /// is retained. CONSTRUCTED: the row ids, every display string, the fighter
    /// words and every in-fight, held, withdrawn, duplicate and long-name case.
    private static let kopylovID = "ko-kopylov"
    private static let gautierID = "ko-gautier"
    private static let kopYes = "240654996"
    private static let kopNo = "240654997"
    private static let gauYes = "240262498"
    private static let gauNo = "240262499"
    private static let fighterIDs = [kopYes, kopNo, gauYes, gauNo]

    private static let fighterRetained: [Retained] = [
        Retained(methodID: kopylovID, marketID: "63900810", outcomeID: kopYes, side: "Yes", probability: 0.125, clock: lateClock, result: "Won", text: "12.5%", time: "4:27 PM PT"),
        Retained(methodID: kopylovID, marketID: "63900810", outcomeID: kopNo, side: "No", probability: 0.875, clock: lateClock, result: "Lost", text: "87.5%", time: "4:27 PM PT"),
        Retained(methodID: gautierID, marketID: "63786875", outcomeID: gauYes, side: "Yes", probability: 0.4, clock: lateClock, result: "Lost", text: "40%", time: "4:27 PM PT"),
        Retained(methodID: gautierID, marketID: "63786875", outcomeID: gauNo, side: "No", probability: 0.6, clock: lateClock, result: "Won", text: "60%", time: "4:27 PM PT"),
    ]

    /// CONSTRUCTED owner words for the fighter card.
    private static let fighterCopy = CombatMethodCopy10868(
        chooseInstruction: "Choose a fighter or side to compare.",
        methodUnavailable: "Selected fighter unavailable in this update.",
        methodSelectedTag: "Fighter selected"
    )

    private static func fighter(_ id: String, _ originals: [CombatMethodOriginal10868], overview: String? = nil) -> CombatMethod10868 {
        id == kopylovID
            ? CombatMethod10868(id: id, label: "Roman Kopylov", question: "Will Roman Kopylov win by KO or TKO?", originals: originals, overviewOriginalID: overview)
            : CombatMethod10868(id: id, label: "Ateba Gautier", question: "Will Ateba Gautier win by KO or TKO?", originals: originals, overviewOriginalID: overview)
    }

    /// The two retained fighters in the approved order, results supplied.
    private static func fighterMethods(overview: [String: String] = [:]) -> [CombatMethod10868] {
        [
            fighter(kopylovID, [original(kopYes), original(kopNo)], overview: overview[kopylovID]),
            fighter(gautierID, [original(gauYes), original(gauNo)], overview: overview[gautierID]),
        ]
    }

    /// The owner-selected Kopylov No by default.
    private static func fighterInput(
        _ phase: CombatMethodPhase10868,
        _ methods: [CombatMethod10868] = fighterMethods(),
        method: String? = kopylovID,
        original: String? = kopNo,
        actual: CombatMethodActual10868? = official
    ) -> CombatMethodInput10868 {
        CombatMethodInput10868(
            phase: phase,
            eventID: eventID,
            eyebrow: "Polymarket · contract results",
            title: phase == .final ? "The knockout few expected" : "Who wins by knockout?",
            caption: "Pre-match chances · select a tile for its quote time",
            methods: methods,
            selectedMethodID: method,
            selectedOriginalID: original,
            actual: actual,
            timing: nil,
            copy: fighterCopy
        )
    }

    func testFourRetainedFighterOriginalsKeepExactIdsOwnBaselinesAndOwnResults() {
        let model = Self.fighterInput(.final, method: nil, original: nil)
        XCTAssertEqual(model.methods.map(\.id), [Self.kopylovID, Self.gautierID])
        XCTAssertEqual(model.methods.map(\.label), ["Roman Kopylov", "Ateba Gautier"])
        XCTAssertEqual(model.methods.map(\.question), ["Will Roman Kopylov win by KO or TKO?", "Will Ateba Gautier win by KO or TKO?"])
        XCTAssertEqual(Self.allOriginals(model).map { $0.1.id }, Self.fighterIDs)
        XCTAssertEqual(Self.allOriginals(model).map { $0.1.label }, ["Yes", "No", "Yes", "No"])
        XCTAssertEqual(Self.allOriginals(model).map { $0.1.marketID }, ["63900810", "63900810", "63786875", "63786875"])
        let expected: [String: (Double, String, CombatMethodResult10868, String)] = [
            Self.kopYes: (0.125, "12.5%", .won("Won"), "checkmark.circle"),
            Self.kopNo: (0.875, "87.5%", .lost("Lost"), "xmark.circle"),
            Self.gauYes: (0.4, "40%", .lost("Lost"), "xmark.circle"),
            Self.gauNo: (0.6, "60%", .won("Won"), "checkmark.circle"),
        ]
        for (method, original) in Self.allOriginals(model) {
            guard let want = expected[original.id], case .value(let reading) = model.beforeReading(original) else {
                return XCTFail(original.id)
            }
            XCTAssertEqual(Self.row(original.id).methodID, method.id, original.id)
            XCTAssertEqual(reading.probability, want.0, original.id)
            XCTAssertEqual(reading.text, want.1, original.id)
            XCTAssertEqual(reading.detail, Self.lateDetail, original.id)
            XCTAssertEqual(CombatMethodGeometry10868.ringFraction(reading.probability), want.0, original.id)
            XCTAssertEqual(model.result(original), want.2, original.id)
            XCTAssertEqual(model.result(original)?.symbolName, want.3, original.id)
            XCTAssertNil(model.currentReading(original), original.id)
            XCTAssertEqual(
                model.sideAction(original, in: method, canSelect: true),
                .select(CombatMethodOriginalRef10868(eventID: "15318681", methodID: method.id, marketID: original.marketID, originalID: original.id)),
                original.id
            )
        }
        // The two Yes chances are drawn as given, never shared out as one
        // head-to-head distribution.
        let overview = Self.fighterInput(.before, Self.fighterMethods(overview: [Self.kopylovID: Self.kopYes, Self.gautierID: Self.gauYes]), method: nil, original: nil)
        var drawn: [Double] = []
        for method in overview.methods {
            guard case .original(let lead, selected: false) = overview.lead(method),
                  case .value(let reading) = overview.beforeReading(lead),
                  let fraction = CombatMethodGeometry10868.ringFraction(reading.probability)
            else { return XCTFail(method.id) }
            drawn.append(fraction)
        }
        XCTAssertEqual(drawn, [0.125, 0.4])
        XCTAssertEqual(drawn.reduce(0, +), 0.525, accuracy: 1e-9)
        XCTAssertNotEqual(drawn[0], 0.125 / 0.525, accuracy: 1e-6)
        XCTAssertNotEqual(drawn[1], 0.4 / 0.525, accuracy: 1e-6)
        // CONSTRUCTED: a No with no recorded baseline stays words, never 1 − 0.125.
        let missingNo = Self.fighterInput(.before, [
            Self.fighter(Self.kopylovID, [Self.original(Self.kopYes), Self.original(Self.kopNo, before: .some(nil))]),
        ])
        XCTAssertEqual(missingNo.beforeReading(missingNo.methods[0].originals[1]), .missing(Self.notRecorded))
        XCTAssertFalse(missingNo.accessibilityTileValue(missingNo.methods[0]).contains("87.5%"))
    }

    func testFighterWordsReachTheLinesTheViewShowsAndSpeaksWhileMethodDefaultsStayByteForByte() {
        // The method card's words are the default, byte for byte, and no existing
        // call site changes (`Self.input` passes no copy).
        XCTAssertEqual(CombatMethodCopy10868.method, CombatMethodCopy10868(
            chooseInstruction: "Choose a method or side to compare.",
            methodUnavailable: "Selected method unavailable in this update.",
            methodSelectedTag: "Method selected"
        ))
        XCTAssertEqual(Self.input(.before).copy, .method)
        XCTAssertEqual(Self.input(.before).instruction(canSelect: true), "Choose a method or side to compare.")
        XCTAssertEqual(Self.input(.before, method: "retired-method", original: nil).selectionNotice, "Selected method unavailable in this update.")
        let methodOnly = Self.input(.before, method: Self.decID, original: nil)
        XCTAssertTrue(methodOnly.accessibilityTileValue(methodOnly.methods[2]).hasSuffix(". Method selected"))

        // The fighter words reach the same decisions the View reads.
        let model = Self.fighterInput(.before)
        XCTAssertEqual(model.instruction(canSelect: true), "Choose a fighter or side to compare.")
        XCTAssertNil(model.instruction(canSelect: false))
        XCTAssertNil(Self.fighterInput(.before, []).instruction(canSelect: true))
        let retired = Self.fighterInput(.before, method: "retired-fighter", original: nil)
        XCTAssertEqual(retired.selection, .unavailable("retired-fighter"))
        XCTAssertEqual(retired.selectionNotice, "Selected fighter unavailable in this update.")
        XCTAssertEqual(Self.fighterInput(.before, method: nil, original: "999").selectionNotice, "Selected fighter unavailable in this update.")
        // Side words are not method-specific and stay shared.
        XCTAssertEqual(Self.fighterInput(.before, method: Self.kopylovID, original: "999").selectionNotice, CombatMethodInput10868.sideUnavailable)
        let chosen = Self.fighterInput(.during, method: Self.gautierID, original: nil)
        XCTAssertEqual(
            chosen.accessibilityTileValue(chosen.methods[1]),
            "Yes. Pre-match chance: 40%; In-fight chance: No in-fight chance. No. Pre-match chance: 60%; In-fight chance: No in-fight chance. Fighter selected"
        )
        // The host hands the words to the View through its input.
        let view = CombatMethodPresentation10868(input: model, onSelect: { _ in })
        XCTAssertEqual(view.input.copy, Self.fighterCopy)

        // Nothing the fighter card shows or speaks — any phase or selection —
        // says "method".
        let selections: [(String?, String?)] = [
            (nil, nil), (Self.kopylovID, Self.kopNo), (Self.kopylovID, "999"), (Self.gautierID, nil), ("retired-fighter", nil), (nil, Self.gauNo),
        ]
        for phase in Self.phases {
            for (selectedMethod, selectedOriginal) in selections {
                let input = Self.fighterInput(phase, method: selectedMethod, original: selectedOriginal)
                var lines = [
                    input.accessibilityHeader, input.instruction(canSelect: true), input.selectionNotice,
                    input.accessibilityComparison, input.accessibilityActual,
                ].compactMap { $0 }
                for (method, original) in Self.allOriginals(input) {
                    lines.append(input.accessibilityTileValue(method))
                    lines.append(input.accessibilityLeadValue(original))
                    lines.append(input.accessibilitySideValue(original, in: method))
                }
                for line in lines {
                    XCTAssertFalse(line.lowercased().contains("method"), "\(phase) \(selectedMethod ?? "-")/\(selectedOriginal ?? "-"): \(line)")
                }
            }
        }
    }

    func testFighterLifecycleKeepsEachOwnPreMatchBesideItsCurrentOrResult() {
        for phase in Self.phases {
            // The owner selected Kopylov's No: it leads with its own 87.5%.
            let model = Self.fighterInput(phase)
            let kop = model.methods[0]
            let no = kop.originals[1]
            XCTAssertEqual(model.selection, .original(kop, no), "\(phase)")
            XCTAssertEqual(model.lead(kop), .original(no, selected: true), "\(phase)")
            XCTAssertEqual(model.beforeReading(no), .value(Self.pregame(Self.row(Self.kopNo))), "\(phase)")
            let later: String
            switch phase {
            case .before:
                later = ""
                XCTAssertEqual(model.comparison, .before(no))
                XCTAssertNil(model.visibleActual)
            case .during:
                later = "; In-fight chance: No in-fight chance"
                XCTAssertEqual(model.comparison, .during(no))
                XCTAssertEqual(model.visibleActual, Self.official)
            case .final:
                later = "; Contract result: Lost"
                XCTAssertEqual(model.comparison, .final(no, .lost("Lost")))
                XCTAssertEqual(model.visibleActual, Self.official)
            }
            XCTAssertEqual(
                model.accessibilityComparison,
                "Will Roman Kopylov win by KO or TKO?, original No. Pre-match chance: 87.5%, \(Self.lateDetail)\(later)",
                "\(phase)"
            )
            for (_, original) in Self.allOriginals(model) {
                XCTAssertFalse(model.showsCurrentMark(original), "\(phase) \(original.id)")
                XCTAssertNil(model.movement(original), "\(phase) \(original.id)")
                XCTAssertEqual(model.currentReading(original), phase == .during ? .missing("No in-fight chance") : nil, "\(phase) \(original.id)")
                XCTAssertEqual(model.result(original), phase == .final ? Self.grade(Self.row(original.id).result) : nil, "\(phase) \(original.id)")
            }
            // Gautier's owner-selected No keeps its own 60%.
            let gautier = Self.fighterInput(phase, method: Self.gautierID, original: Self.gauNo)
            let gauNo = gautier.methods[1].originals[1]
            XCTAssertEqual(gautier.lead(gautier.methods[1]), .original(gauNo, selected: true), "\(phase)")
            XCTAssertEqual(gautier.beforeReading(gauNo), .value(Self.pregame(Self.row(Self.gauNo))), "\(phase)")
        }

        // CONSTRUCTED: an admitted in-fight chance for Gautier's Yes and a held
        // one for Kopylov's No.
        let gauYesCurrent = Self.obs(0.22, "22%", "5:31 PM PT", "Recorded Oct 3, 5:31 PM PT · Polymarket")
        let live = [
            Self.fighter(Self.kopylovID, [Self.original(Self.kopYes), Self.original(Self.kopNo, current: .withheld("Held since round 1"))]),
            Self.fighter(Self.gautierID, [Self.original(Self.gauYes, current: .recorded(gauYesCurrent, movement: "−18 points since pre-match")), Self.original(Self.gauNo)]),
        ]
        let during = Self.fighterInput(.during, live, method: Self.gautierID, original: Self.gauYes)
        let gauYes = during.methods[1].originals[0]
        // Both figures are values, drawn by the same comparison figure.
        XCTAssertEqual(during.comparison, .during(gauYes))
        XCTAssertEqual(during.beforeReading(gauYes), .value(Self.pregame(Self.row(Self.gauYes))))
        XCTAssertEqual(during.currentReading(gauYes), .value(gauYesCurrent))
        XCTAssertTrue(during.showsCurrentMark(gauYes))
        XCTAssertEqual(
            during.accessibilityComparison,
            "Will Ateba Gautier win by KO or TKO?, original Yes. Pre-match chance: 40%, \(Self.lateDetail); In-fight chance: 22%, Recorded Oct 3, 5:31 PM PT · Polymarket; −18 points since pre-match"
        )
        let heldNo = during.methods[0].originals[1]
        XCTAssertEqual(during.currentReading(heldNo), .missing("Held since round 1"))
        XCTAssertFalse(during.showsCurrentMark(heldNo))
        XCTAssertNil(during.movement(heldNo))

        // The same supplied input before the fight shows only pre-match chances.
        let before = Self.fighterInput(.before, live, method: Self.gautierID, original: Self.gauYes)
        var spoken = [before.accessibilityComparison ?? ""]
        for (method, original) in Self.allOriginals(before) {
            XCTAssertNil(before.currentReading(original), original.id)
            XCTAssertNil(before.movement(original), original.id)
            XCTAssertNil(before.result(original), original.id)
            spoken.append(before.accessibilityTileValue(method))
        }
        for word in ["22%", "Held", "In-fight", "Won", "Lost", "Contract result", "−18", "strikes"] {
            XCTAssertFalse(spoken.joined(separator: " | ").contains(word), word)
        }

        // After the fight the supplied in-fight values are ignored and the
        // selected Yes keeps its 40% beside its own Lost.
        let final = Self.fighterInput(.final, live, method: Self.gautierID, original: Self.gauYes)
        XCTAssertNil(final.currentReading(final.methods[1].originals[0]))
        XCTAssertNil(final.movement(final.methods[1].originals[0]))
        XCTAssertEqual(final.comparison, .final(final.methods[1].originals[0], .lost("Lost")))
        // CONSTRUCTED: the official TKO never grades an unconfirmed contract.
        let unconfirmed = Self.fighterInput(.final, [
            Self.fighter(Self.kopylovID, [
                Self.original(Self.kopYes, result: .unconfirmed("Result unconfirmed")),
                Self.original(Self.kopNo, result: .unconfirmed("Result unconfirmed")),
            ]),
        ], method: Self.kopylovID, original: Self.kopYes)
        XCTAssertEqual(unconfirmed.comparison, .final(unconfirmed.methods[0].originals[0], .unconfirmed("Result unconfirmed")))
        XCTAssertEqual(unconfirmed.visibleActual, Self.official)
        XCTAssertFalse((unconfirmed.accessibilityComparison ?? "").contains("Won"))
    }

    func testEveryFighterOriginalStaysReachableAndNoSideRowIsMountedTwice() {
        let overviews: [[String: String]] = [
            [:],
            [Self.kopylovID: Self.kopYes, Self.gautierID: Self.gauYes],
            [Self.kopylovID: "999", Self.gautierID: Self.gauNo],
        ]
        let selections: [(String?, String?)] = [
            (nil, nil), (Self.kopylovID, Self.kopNo), (Self.kopylovID, "999"), (Self.gautierID, nil), ("retired-fighter", nil), (nil, Self.gauNo),
        ]
        let everyRef = Set(Self.fighterIDs.map { Self.ref(Self.row($0).methodID, $0) })
        for phase in Self.phases {
            for overview in overviews {
                for (selectedMethod, selectedOriginal) in selections {
                    let model = Self.fighterInput(phase, Self.fighterMethods(overview: overview), method: selectedMethod, original: selectedOriginal)
                    for canSelect in [true, false] {
                        let label = "\(phase) \(overview) \(selectedMethod ?? "-")/\(selectedOriginal ?? "-") \(canSelect)"
                        var onScreen = Set<String>()
                        var rows: [String] = []
                        var refs = Set<CombatMethodOriginalRef10868>()
                        for method in model.methods {
                            let tile = model.tilePresentation(method, canSelect: canSelect)
                            let sides = tile.listed + model.panelSides(method, canSelect: canSelect)
                            var shown = Set(sides.map(\.original.id))
                            rows += sides.map(\.original.id)
                            for side in sides {
                                XCTAssertEqual(side.action, model.sideAction(side.original, in: method, canSelect: canSelect), label)
                                if case .select(let ref)? = side.action { refs.insert(ref) }
                            }
                            var tileAction: CombatMethodAction10868?
                            switch tile {
                            case .ring(let lead, _, let action):
                                shown.insert(lead.id)
                                tileAction = action
                            case .ringWithSides(let lead, _):
                                shown.insert(lead.id)
                            case .unavailable, .unavailableWithSides, .sides:
                                break
                            }
                            if case .select(let ref)? = tileAction { refs.insert(ref) }
                            // Only an actionable ring may leave a side off screen; it
                            // selects its own fighter, whose panel then lists every side.
                            if shown != Set(method.originals.map(\.id)) {
                                guard case .select(let ref)? = tileAction else { XCTFail(label); continue }
                                XCTAssertEqual(ref.methodID, method.id, label)
                            }
                            onScreen.formUnion(shown)
                        }
                        XCTAssertEqual(rows.count, Set(rows).count, label)
                        if canSelect {
                            // Every exact original is one tap away, or two through its tile.
                            var reached = refs
                            for ref in refs {
                                let next = Self.fighterInput(phase, Self.fighterMethods(overview: overview), method: ref.methodID, original: ref.originalID)
                                for method in next.methods {
                                    for side in next.panelSides(method, canSelect: true) {
                                        if case .select(let sideRef)? = side.action { reached.insert(sideRef) }
                                    }
                                }
                            }
                            XCTAssertEqual(reached, everyRef, label)
                        } else {
                            XCTAssertEqual(onScreen, Set(Self.fighterIDs), label)
                            XCTAssertTrue(refs.isEmpty, label)
                        }
                    }
                }
            }
        }

        for phase in Self.phases {
            // CONSTRUCTED: Gautier's No arrives carrying Kopylov's No id. Every
            // original stays listed; the ambiguous pair carries no action.
            let dupe = CombatMethodOriginal10868(
                id: Self.kopNo,
                marketID: "63786875",
                label: "No",
                before: Self.pregame(Self.row(Self.gauNo)),
                beforeMissing: Self.notRecorded,
                current: Self.noCurrent,
                result: .won("Won")
            )
            let twins = Self.fighterInput(phase, [
                Self.fighter(Self.kopylovID, [Self.original(Self.kopYes), Self.original(Self.kopNo)]),
                Self.fighter(Self.gautierID, [Self.original(Self.gauYes), dupe]),
            ], method: nil, original: Self.kopNo)
            XCTAssertEqual(twins.selection, .unavailable(Self.kopNo), "\(phase)")
            XCTAssertEqual(twins.selectionNotice, "Selected fighter unavailable in this update.", "\(phase)")
            XCTAssertEqual(twins.tilePresentation(twins.methods[0], canSelect: true), .sides([
                CombatMethodTileSide10868(original: twins.methods[0].originals[0], action: .select(Self.ref(Self.kopylovID, Self.kopYes))),
                CombatMethodTileSide10868(original: twins.methods[0].originals[1], action: nil),
            ]), "\(phase)")
            XCTAssertEqual(twins.tilePresentation(twins.methods[1], canSelect: true), .sides([
                CombatMethodTileSide10868(original: twins.methods[1].originals[0], action: .select(Self.ref(Self.gautierID, Self.gauYes))),
                CombatMethodTileSide10868(original: dupe, action: nil),
            ]), "\(phase)")

            // CONSTRUCTED held update: the owner-selected No stays the lead.
            let held = Self.fighterInput(phase, [
                Self.fighter(Self.kopylovID, [Self.original(Self.kopYes), Self.original(Self.kopNo, current: .withheld("Held since round 1"))]),
                Self.fighter(Self.gautierID, [Self.original(Self.gauYes), Self.original(Self.gauNo)]),
            ])
            XCTAssertEqual(held.lead(held.methods[0]), .original(held.methods[0].originals[1], selected: true), "\(phase)")
            // CONSTRUCTED withdrawal: unavailable, never Yes; the panel lists what remains.
            let withdrawn = Self.fighterInput(phase, [
                Self.fighter(Self.kopylovID, [Self.original(Self.kopYes)], overview: Self.kopYes),
                Self.fighter(Self.gautierID, [Self.original(Self.gauYes), Self.original(Self.gauNo)]),
            ])
            let kop = withdrawn.methods[0]
            XCTAssertEqual(withdrawn.selection, .sideUnavailable(kop, Self.kopNo), "\(phase)")
            XCTAssertEqual(withdrawn.tilePresentation(kop, canSelect: true), .unavailable(CombatMethodInput10868.sideUnavailableShort), "\(phase)")
            XCTAssertEqual(withdrawn.panelSides(kop, canSelect: true), Self.listed(kop, kop.originals, actionable: true), "\(phase)")
            XCTAssertNil(withdrawn.comparison, "\(phase)")
        }
    }

    func testFighterNamesKeepWholeWordsAndAQualifiedFigureGrowsTheRing() {
        XCTAssertEqual(CombatMethodGeometry10868.words("Roman Kopylov"), ["Roman", "Kopylov"])
        XCTAssertEqual(CombatMethodGeometry10868.words("Ateba Gautier"), ["Ateba", "Gautier"])
        // Two fighter tiles share one row at 320, 375 and 393 (288, 327, 345 after padding).
        let all: (CGFloat) -> Bool = { _ in true }
        for width: CGFloat in [288, 327, 345] {
            XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: width, count: 2, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: all), 2, "\(width)")
        }
        XCTAssertEqual(CombatMethodGeometry10868.columnWidth(available: 288, columns: 2, spacing: 8), 140)
        // CONSTRUCTED: a full name whose widest word measures 168pt drops to one
        // column instead of breaking, shrinking or truncating it.
        XCTAssertEqual(CombatMethodGeometry10868.words("Alexandre Pantoja-Wojciechowski"), ["Alexandre", "Pantoja-Wojciechowski"])
        let needs168: (CGFloat) -> Bool = { $0 >= 168 }
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 288, count: 2, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: needs168), 1)
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 327, count: 2, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: needs168), 1)
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 345, count: 2, spacing: 8, minimumColumnWidth: 96, forceSingle: false, fits: needs168), 2)
        XCTAssertEqual(CombatMethodGeometry10868.columnCount(available: 345, count: 2, spacing: 8, minimumColumnWidth: 96, forceSingle: true, fits: all), 1)
        // CONSTRUCTED measures: "87.5%" at 44 × 22 → 68; a qualified "≥99.5%" at
        // 58 × 22 → 81. The ring grows; the figure is never shrunk.
        XCTAssertEqual(CombatMethodGeometry10868.ringSide(minimum: 60, figure: CGSize(width: 44, height: 22)), 68)
        XCTAssertEqual(CombatMethodGeometry10868.ringSide(minimum: 60, figure: CGSize(width: 58, height: 22)), 81)
    }
}
