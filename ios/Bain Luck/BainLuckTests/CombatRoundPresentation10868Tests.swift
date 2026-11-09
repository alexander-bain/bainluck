import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the combat fighter-round card as a stateless presentation leaf
/// across before, during and after the fight.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: which readings and marks each phase shows, the
/// independence of every fighter/round original, the explicit uncaptured slot,
/// zero versus unknown versus malformed, the exact-id selection and lead side,
/// the action each control carries, the tile and side-row placement the View
/// branches on, the timing it may show, the track, column and pair geometry
/// and the spoken text. Nothing here claims a rendered fit, a native runtime
/// or a populated boxing case.
///
/// ARCHIVED raw values come from Gautier–Kopylov, event 15318681 (mma, raw
/// status suspended, verified start 2026-10-04T00:20:00Z), as retained in
/// `shipping-adoption-20261027/COMBAT-ROUND-RETAINED-CASES.json`
/// (sha256 7114db93…d0ec). Five captured binary markets, ten originals, six
/// approved fighter/round slots:
///   Kopylov R1 63900818  Yes 240655012 0.11  Won;  No 240655013 0.89  Lost
///   Kopylov R2 63900819  Yes 240655014 0.10  Lost; No 240655015 0.90  Won
///   Kopylov R3 63900820  Yes 240655016 0.09  Lost; No 240655017 0.91  Won
///   Gautier R1 63786882  Yes 240262512 0.205 Lost; No 240262513 0.795 Won
///   Gautier R2           no captured prop — no market, ids, figures or result
///   Gautier R3 63900822  Yes 240655020 0.11  Lost; No 240655021 0.89  Won
///   Pre-match clocks (consensus): Gautier R1 2026-10-03T16:42:41.515378Z;
///   every other market 2026-10-03T23:27:48.847758Z. Every raw period is
///   null. The settlement-time 1.0 / 0.0 quotes are not baselines. No admitted
///   in-fight chance is retained. Later official UFC evidence: Kopylov def.
///   Gautier, TKO (strikes), Round 1, 3:12, absoluteFinishAt null — separate
///   context, never a contract grade or a phase.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// group and slot ids, fighter and round labels and their order, the
/// uncaptured/unavailable words, every display string, PT time and provenance
/// line, every result word, the official-context wording, every in-fight
/// observation and movement line, held/withdrawn/duplicate updates, phase
/// arrivals, zero, malformed, long-label and other-schedule cases, and every
/// measured width.
final class CombatRoundPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static let eventID = "15318681"

    private static let kopylov = "kopylov"
    private static let gautier = "gautier"
    private static let kR1 = "kopylov-r1"
    private static let kR2 = "kopylov-r2"
    private static let kR3 = "kopylov-r3"
    private static let gR1 = "gautier-r1"
    private static let gR2 = "gautier-r2"
    private static let gR3 = "gautier-r3"

    private static let kR1Yes = "240655012"
    private static let kR1No = "240655013"
    private static let kR2Yes = "240655014"
    private static let kR2No = "240655015"
    private static let kR3Yes = "240655016"
    private static let kR3No = "240655017"
    private static let gR1Yes = "240262512"
    private static let gR1No = "240262513"
    private static let gR3Yes = "240655020"
    private static let gR3No = "240655021"

    /// CONSTRUCTED provenance lines for the two ARCHIVED pre-start clocks.
    private static let earlyDetail = "Last recorded before start · Oct 3, 9:42 AM PT · Polymarket"
    private static let lateDetail = "Last recorded before start · Oct 3, 4:27 PM PT · Polymarket"

    private struct Retained {
        let slotID: String
        let marketID: String
        let outcomeID: String
        let side: String
        /// ARCHIVED.
        let probability: Double
        let result: String
        /// ARCHIVED clock; the detail line is CONSTRUCTED from it.
        let clock: String
        /// CONSTRUCTED owner text.
        let text: String

        var detail: String {
            clock == CombatRoundPresentation10868Tests.earlyClock
                ? CombatRoundPresentation10868Tests.earlyDetail
                : CombatRoundPresentation10868Tests.lateDetail
        }
    }

    /// ARCHIVED clocks.
    private static let earlyClock = "2026-10-03T16:42:41.515378+00:00"
    private static let lateClock = "2026-10-03T23:27:48.847758+00:00"

    private static let retained: [Retained] = [
        Retained(slotID: kR1, marketID: "63900818", outcomeID: kR1Yes, side: "Yes", probability: 0.11, result: "Won", clock: lateClock, text: "11%"),
        Retained(slotID: kR1, marketID: "63900818", outcomeID: kR1No, side: "No", probability: 0.89, result: "Lost", clock: lateClock, text: "89%"),
        Retained(slotID: kR2, marketID: "63900819", outcomeID: kR2Yes, side: "Yes", probability: 0.1, result: "Lost", clock: lateClock, text: "10%"),
        Retained(slotID: kR2, marketID: "63900819", outcomeID: kR2No, side: "No", probability: 0.9, result: "Won", clock: lateClock, text: "90%"),
        Retained(slotID: kR3, marketID: "63900820", outcomeID: kR3Yes, side: "Yes", probability: 0.09, result: "Lost", clock: lateClock, text: "9%"),
        Retained(slotID: kR3, marketID: "63900820", outcomeID: kR3No, side: "No", probability: 0.91, result: "Won", clock: lateClock, text: "91%"),
        Retained(slotID: gR1, marketID: "63786882", outcomeID: gR1Yes, side: "Yes", probability: 0.205, result: "Lost", clock: earlyClock, text: "20.5%"),
        Retained(slotID: gR1, marketID: "63786882", outcomeID: gR1No, side: "No", probability: 0.795, result: "Won", clock: earlyClock, text: "79.5%"),
        Retained(slotID: gR3, marketID: "63900822", outcomeID: gR3Yes, side: "Yes", probability: 0.11, result: "Lost", clock: lateClock, text: "11%"),
        Retained(slotID: gR3, marketID: "63900822", outcomeID: gR3No, side: "No", probability: 0.89, result: "Won", clock: lateClock, text: "89%"),
    ]

    /// ARCHIVED original prop text per captured slot.
    private static let questions: [String: String] = [
        kR1: "Will Roman Kopylov win in Round 1?",
        kR2: "Will Roman Kopylov win in Round 2?",
        kR3: "Will Roman Kopylov win in Round 3?",
        gR1: "Will Ateba Gautier win in Round 1?",
        gR3: "Will Ateba Gautier win in Round 3?",
    ]

    private static let noCurrent = CombatRoundCurrent10868.unavailable("No in-fight chance")
    private static let notRecorded = "Not recorded before start"
    private static let noCapturedProp = "No captured prop"
    private static let unavailableInUpdate = "Unavailable in this update"

    private static func obs(_ probability: Double, _ text: String, _ detail: String) -> CombatRoundObservation10868 {
        CombatRoundObservation10868(probability: probability, text: text, detail: detail)
    }

    private static func pregame(_ row: Retained) -> CombatRoundObservation10868 {
        obs(row.probability, row.text, row.detail)
    }

    private static func grade(_ word: String) -> CombatRoundResult10868 {
        switch word {
        case "Won": .won("Won")
        case "Lost": .lost("Lost")
        default: .unconfirmed(word)
        }
    }

    private static func row(_ id: String) -> Retained {
        retained.first { $0.outcomeID == id }!
    }

    private static func original(
        _ id: String,
        before: CombatRoundObservation10868?? = nil,
        current: CombatRoundCurrent10868 = noCurrent,
        result: CombatRoundResult10868? = nil
    ) -> CombatRoundOriginal10868 {
        let source = Self.row(id)
        let reading: CombatRoundObservation10868?
        switch before {
        case .some(let value): reading = value
        case .none: reading = pregame(source)
        }
        return CombatRoundOriginal10868(
            id: id,
            marketID: source.marketID,
            label: source.side,
            before: reading,
            beforeMissing: notRecorded,
            current: current,
            result: result ?? grade(source.result),
            resultDetail: nil
        )
    }

    private static func market(_ slotID: String, _ originals: [CombatRoundOriginal10868], overview: String? = nil) -> CombatRoundMarket10868 {
        CombatRoundMarket10868(id: row(originals.first?.id ?? kR1Yes).marketID, question: questions[slotID]!, originals: originals, overviewOriginalID: overview)
    }

    private static func slot(_ id: String, _ label: String, _ state: CombatRoundSlotState10868) -> CombatRoundSlot10868 {
        CombatRoundSlot10868(id: id, label: label, state: state)
    }

    private static func captured(_ slotID: String, _ label: String, _ ids: [String], overview: [String: String], originals: [String: CombatRoundOriginal10868] = [:]) -> CombatRoundSlot10868 {
        slot(slotID, label, .market(market(slotID, ids.map { originals[$0] ?? original($0) }, overview: overview[slotID])))
    }

    /// The two retained fighters and six slots in the owner's order, results
    /// supplied (each phase decides what shows). `originals` swaps in a
    /// CONSTRUCTED original by id.
    private static func retainedGroups(
        overview: [String: String] = [:],
        originals: [String: CombatRoundOriginal10868] = [:]
    ) -> [CombatRoundGroup10868] {
        [
            CombatRoundGroup10868(id: kopylov, label: "Roman Kopylov", slots: [
                captured(kR1, "Round 1", [kR1Yes, kR1No], overview: overview, originals: originals),
                captured(kR2, "Round 2", [kR2Yes, kR2No], overview: overview, originals: originals),
                captured(kR3, "Round 3", [kR3Yes, kR3No], overview: overview, originals: originals),
            ]),
            CombatRoundGroup10868(id: gautier, label: "Ateba Gautier", slots: [
                captured(gR1, "Round 1", [gR1Yes, gR1No], overview: overview, originals: originals),
                slot(gR2, "Round 2", .noCapturedProp(noCapturedProp)),
                captured(gR3, "Round 3", [gR3Yes, gR3No], overview: overview, originals: originals),
            ]),
        ]
    }

    /// CONSTRUCTED wording of the ARCHIVED UFC reference; no finish clock exists.
    private static let official = CombatRoundFinish10868(
        title: "Official bout result",
        lines: ["Roman Kopylov def. Ateba Gautier · TKO (strikes) · Round 1, 3:12"],
        accessibilityDetail: "UFC results page, captured Oct 13 · finish clock not recorded"
    )

    private static func input(
        _ phase: CombatRoundPhase10868,
        _ groups: [CombatRoundGroup10868] = retainedGroups(),
        slot: String? = kR1,
        original: String? = kR1Yes,
        finish: CombatRoundFinish10868? = official,
        timing: CombatRoundTiming10868? = nil
    ) -> CombatRoundInput10868 {
        CombatRoundInput10868(
            phase: phase,
            eventID: eventID,
            eyebrow: "Polymarket · contract results",
            title: "Which round for each fighter?",
            caption: "Pre-match chance · tracks run from 0 to 100%",
            groups: groups,
            selectedSlotID: slot,
            selectedOriginalID: original,
            finish: finish,
            timing: timing
        )
    }

    /// CONSTRUCTED admitted in-fight observation (the packet retains none).
    private static let kR1YesCurrent = obs(0.62, "62%", "Recorded Oct 3, 5:31 PM PT · Polymarket")
    private static let movementLine = "+51 points since pre-match"

    /// Every later input supplied, to prove the earlier phases hide them.
    private static var everythingSupplied: [CombatRoundGroup10868] {
        retainedGroups(originals: [
            kR1Yes: original(kR1Yes, current: .recorded(kR1YesCurrent, movement: movementLine)),
            kR1No: original(kR1No, current: .withheld("Held since round 1")),
        ])
    }

    private static let phases: [CombatRoundPhase10868] = [.before, .during, .final]

    private static func group(_ model: CombatRoundInput10868, _ slotID: String) -> CombatRoundGroup10868 {
        model.groups.first { $0.slots.contains { $0.id == slotID } }!
    }

    private static func slotOf(_ model: CombatRoundInput10868, _ slotID: String) -> CombatRoundSlot10868 {
        model.groups.flatMap(\.slots).first { $0.id == slotID }!
    }

    private static func placeOf(_ model: CombatRoundInput10868, _ slotID: String) -> CombatRoundPlace10868 {
        model.place(group(model, slotID), slotOf(model, slotID))!
    }

    private static func presentation(_ model: CombatRoundInput10868, _ slotID: String, canSelect: Bool) -> CombatRoundTilePresentation10868 {
        model.tilePresentation(group(model, slotID), slotOf(model, slotID), canSelect: canSelect)
    }

    private static func tileValue(_ model: CombatRoundInput10868, _ slotID: String) -> String {
        model.accessibilityTileValue(group(model, slotID), slotOf(model, slotID))
    }

    private static func allOriginals(_ model: CombatRoundInput10868) -> [(CombatRoundPlace10868, CombatRoundOriginal10868)] {
        model.places.flatMap { place in place.market.originals.map { (place, $0) } }
    }

    private static func ref(_ slotID: String, _ originalID: String) -> CombatRoundOriginalRef10868 {
        let groupID = slotID.hasPrefix(kopylov) ? kopylov : gautier
        return CombatRoundOriginalRef10868(eventID: eventID, groupID: groupID, slotID: slotID, marketID: row(originalID).marketID, originalID: originalID)
    }

    private static func listed(_ place: CombatRoundPlace10868, _ originals: [CombatRoundOriginal10868], actionable: Bool) -> [CombatRoundTileSide10868] {
        originals.map { CombatRoundTileSide10868(original: $0, action: actionable ? .select(ref(place.slot.id, $0.id)) : nil) }
    }

    /// What a side row speaks after its pre-match chance, per phase.
    private static func later(_ phase: CombatRoundPhase10868, _ id: String) -> String {
        switch phase {
        case .before: return ""
        case .during: return "; In-fight chance: No in-fight chance"
        case .final: return "; Contract result: \(row(id).result)"
        }
    }

    private static func spokenDetailed(_ phase: CombatRoundPhase10868, _ id: String) -> String {
        let source = row(id)
        return "Pre-match chance: \(source.text), \(source.detail)\(later(phase, id))"
    }

    // MARK: The ten retained originals and six slots

    func testTenRetainedOriginalsKeepExactIdsOrderSidesAndOwnBaselines() {
        let model = Self.input(.before)
        XCTAssertEqual(model.groups.map(\.id), [Self.kopylov, Self.gautier])
        XCTAssertEqual(model.groups.map(\.label), ["Roman Kopylov", "Ateba Gautier"])
        XCTAssertEqual(model.groups.flatMap { $0.slots.map(\.id) }, [Self.kR1, Self.kR2, Self.kR3, Self.gR1, Self.gR2, Self.gR3])
        XCTAssertEqual(model.groups.flatMap { $0.slots.map(\.label) }, ["Round 1", "Round 2", "Round 3", "Round 1", "Round 2", "Round 3"])
        XCTAssertEqual(model.places.map(\.slot.id), [Self.kR1, Self.kR2, Self.kR3, Self.gR1, Self.gR3])
        XCTAssertEqual(model.places.map(\.market.id), ["63900818", "63900819", "63900820", "63786882", "63900822"])
        XCTAssertEqual(model.places.map(\.market.question), [
            "Will Roman Kopylov win in Round 1?", "Will Roman Kopylov win in Round 2?", "Will Roman Kopylov win in Round 3?",
            "Will Ateba Gautier win in Round 1?", "Will Ateba Gautier win in Round 3?",
        ])
        XCTAssertEqual(Self.allOriginals(model).map { $0.1.id }, Self.retained.map(\.outcomeID))
        XCTAssertEqual(Self.allOriginals(model).map { $0.1.label }, ["Yes", "No", "Yes", "No", "Yes", "No", "Yes", "No", "Yes", "No"])
        for (place, original) in Self.allOriginals(model) {
            let source = Self.row(original.id)
            XCTAssertEqual(source.slotID, place.slot.id, original.id)
            XCTAssertEqual(original.marketID, place.market.id, original.id)
            guard case .value(let reading) = model.beforeReading(original) else { return XCTFail(original.id) }
            XCTAssertEqual(reading.probability, source.probability, original.id)
            XCTAssertEqual(reading.text, source.text, original.id)
            XCTAssertEqual(reading.detail, source.detail, original.id)
            // The track places the original's own figure.
            XCTAssertEqual(model.railMarks(original), CombatRoundRailMarks10868(before: source.probability, current: nil), original.id)
            // No settlement-time 1.0 / 0.0 quote is a baseline.
            XCTAssertNotEqual(reading.probability, 1.0, original.id)
            XCTAssertNotEqual(reading.probability, 0.0, original.id)
        }
        XCTAssertEqual(Self.retained.count, 10)
        XCTAssertEqual(Set(Self.retained.map(\.marketID)).count, 5)
    }

    func testGautierRoundOneKeepsItsEarlierClockAndNoProvenanceIsShared() {
        let model = Self.input(.before, slot: Self.gR1, original: Self.gR1No)
        for (_, original) in Self.allOriginals(model) {
            guard case .value(let reading) = model.beforeReading(original) else { return XCTFail(original.id) }
            let early = [Self.gR1Yes, Self.gR1No].contains(original.id)
            XCTAssertEqual(reading.detail, early ? Self.earlyDetail : Self.lateDetail, original.id)
            XCTAssertEqual(Self.row(original.id).clock, early ? Self.earlyClock : Self.lateClock, original.id)
        }
        XCTAssertEqual(
            model.accessibilityComparison,
            "Will Ateba Gautier win in Round 1?, original No. Ateba Gautier, Round 1. Pre-match chance: 79.5%, \(Self.earlyDetail)"
        )
        // The neighbouring Gautier Round 3 keeps the later clock.
        XCTAssertTrue(Self.tileValue(model, Self.gR3).contains("No. Pre-match chance: 89%"))
        let gR3 = Self.placeOf(model, Self.gR3)
        XCTAssertEqual(model.accessibilitySideValue(gR3.market.originals[1], at: gR3), "Pre-match chance: 89%, \(Self.lateDetail)")
    }

    func testGautierRoundTwoStaysAnExplicitUncapturedSlot() {
        for phase in Self.phases {
            for (slot, original) in [(nil, nil), (Self.kR1, Self.kR1Yes), (Self.gR2, nil), (Self.gR2, Self.gR1Yes)] as [(String?, String?)] {
                let model = Self.input(phase, slot: slot, original: original)
                let label = "\(phase) \(slot ?? "-")/\(original ?? "-")"
                let group = Self.group(model, Self.gR2)
                let gR2 = Self.slotOf(model, Self.gR2)
                XCTAssertNil(model.place(group, gR2), label)
                XCTAssertNil(gR2.state.market, label)
                XCTAssertEqual(gR2.state.absentWords, Self.noCapturedProp, label)
                for canSelect in [true, false] {
                    XCTAssertEqual(model.tilePresentation(group, gR2, canSelect: canSelect), .absent(Self.noCapturedProp), label)
                    XCTAssertEqual(model.tilePresentation(group, gR2, canSelect: canSelect).listed, [], label)
                }
                let spoken = model.accessibilityTileValue(group, gR2)
                XCTAssertTrue(spoken.hasPrefix(Self.noCapturedProp), label)
                for word in ["%", "Won", "Lost", "Pre-match", "In-fight", "Contract result"] {
                    XCTAssertFalse(spoken.contains(word), "\(label) \(word)")
                }
                XCTAssertEqual(model.accessibilitySlotLabel(group, gR2), "Ateba Gautier, Round 2", label)
                // No reference anywhere on the card names the uncaptured slot.
                for (place, original) in Self.allOriginals(model) {
                    XCTAssertNotEqual(model.ref(original, at: place).slotID, Self.gR2, label)
                }
            }
            // Selecting it keeps the slot outlined, names the update and offers nothing to compare.
            let chosen = Self.input(phase, slot: Self.gR2, original: nil)
            let group = Self.group(chosen, Self.gR2)
            let gR2 = Self.slotOf(chosen, Self.gR2)
            XCTAssertEqual(chosen.selection, .slotWithoutMarket(group, gR2), "\(phase)")
            XCTAssertTrue(chosen.isSelectedSlot(group, gR2), "\(phase)")
            XCTAssertEqual(chosen.selectionNotice, CombatRoundInput10868.slotUnavailable, "\(phase)")
            XCTAssertNil(chosen.comparison, "\(phase)")
            XCTAssertNil(chosen.detailsAction(canOpenDetails: true), "\(phase)")
            XCTAssertNil(chosen.timingPresentation(hasBinding: false), "\(phase)")
            XCTAssertEqual(chosen.accessibilityTileValue(group, gR2), "\(Self.noCapturedProp). \(CombatRoundInput10868.selectedTag)", "\(phase)")
            // A side id from another slot does not pull Gautier Round 1 into the uncaptured slot.
            let crossed = Self.input(phase, slot: Self.gR2, original: Self.gR1Yes)
            XCTAssertEqual(crossed.selection, .slotWithoutMarket(group, gR2), "\(phase)")
            XCTAssertEqual(Self.presentation(crossed, Self.gR1, canSelect: true), .sides(Self.listed(Self.placeOf(crossed, Self.gR1), Self.placeOf(crossed, Self.gR1).market.originals, actionable: true)), "\(phase)")
        }
    }

    func testUnavailableInUpdateSlotKeepsItsOwnWordsDistinctFromNoCapturedProp() {
        // CONSTRUCTED: Kopylov Round 2 drops out of an update.
        var groups = Self.retainedGroups()
        groups[0] = CombatRoundGroup10868(id: Self.kopylov, label: "Roman Kopylov", slots: [
            groups[0].slots[0],
            Self.slot(Self.kR2, "Round 2", .unavailable(Self.unavailableInUpdate)),
            groups[0].slots[2],
        ])
        for phase in Self.phases {
            let model = Self.input(phase, groups, slot: Self.kR2, original: Self.kR2No)
            XCTAssertEqual(Self.presentation(model, Self.kR2, canSelect: true), .absent(Self.unavailableInUpdate), "\(phase)")
            XCTAssertEqual(Self.presentation(model, Self.gR2, canSelect: true), .absent(Self.noCapturedProp), "\(phase)")
            // The held selection stays on its slot, named, with no substitute.
            XCTAssertEqual(model.selection, .slotWithoutMarket(groups[0], groups[0].slots[1]), "\(phase)")
            XCTAssertEqual(model.selectionNotice, CombatRoundInput10868.slotUnavailable, "\(phase)")
            XCTAssertEqual(Self.tileValue(model, Self.kR2), "\(Self.unavailableInUpdate). \(CombatRoundInput10868.selectedTag)", "\(phase)")
            // Every remaining original stays reachable.
            var refs = Set<String>()
            for place in model.places {
                for original in place.market.originals {
                    if case .select(let ref)? = model.sideAction(original, at: place, canSelect: true) { refs.insert(ref.originalID) }
                }
            }
            XCTAssertEqual(refs, Set(Self.retained.map(\.outcomeID)).subtracting([Self.kR2Yes, Self.kR2No]), "\(phase)")
        }
    }

    // MARK: Independence

    func testYesAndNoKeepIndependentOwnFiguresAndMarksWithoutComplement() {
        let model = Self.input(.before)
        for place in model.places {
            let marks = place.market.originals.map { model.railMarks($0).before }
            XCTAssertEqual(marks, place.market.originals.map { Self.row($0.id).probability }, place.slot.id)
        }
        // CONSTRUCTED: Gautier Round 1's No has no admitted baseline. It stays
        // words and draws no mark — never 1 − 0.205.
        let missing = Self.input(.before, Self.retainedGroups(originals: [Self.gR1No: Self.original(Self.gR1No, before: .some(nil))]), slot: Self.gR1, original: Self.gR1No)
        let gR1 = Self.placeOf(missing, Self.gR1)
        XCTAssertEqual(missing.beforeReading(gR1.market.originals[1]), .missing(Self.notRecorded))
        XCTAssertEqual(missing.railMarks(gR1.market.originals[1]), CombatRoundRailMarks10868(before: nil, current: nil))
        XCTAssertEqual(missing.railMarks(gR1.market.originals[0]).before, 0.205)
        XCTAssertEqual(missing.accessibilityComparison, "Will Ateba Gautier win in Round 1?, original No. Ateba Gautier, Round 1. Pre-match chance: \(Self.notRecorded)")
        // CONSTRUCTED: a pair whose sides do not sum to one is shown as supplied.
        let loose = Self.input(.before, Self.retainedGroups(originals: [
            Self.kR3Yes: Self.original(Self.kR3Yes, before: Self.obs(0.3, "30%", Self.lateDetail)),
            Self.kR3No: Self.original(Self.kR3No, before: Self.obs(0.3, "30%", Self.lateDetail)),
        ]), slot: nil, original: nil)
        let kR3 = Self.placeOf(loose, Self.kR3)
        XCTAssertEqual(kR3.market.originals.map { loose.railMarks($0).before }, [0.3, 0.3])
    }

    func testFighterRoundsAreIndependentQuestionsNotOneDistribution() {
        let model = Self.input(.before, slot: nil, original: nil)
        // Kopylov's three Yes figures sum to 0.30 and Gautier's two to 0.315; neither
        // is rescaled, and no round is conditioned on reaching it.
        let kopylovYes = [Self.kR1, Self.kR2, Self.kR3].map { model.railMarks(Self.placeOf(model, $0).market.originals[0]).before ?? -1 }
        let gautierYes = [Self.gR1, Self.gR3].map { model.railMarks(Self.placeOf(model, $0).market.originals[0]).before ?? -1 }
        XCTAssertEqual(kopylovYes, [0.11, 0.1, 0.09])
        XCTAssertEqual(gautierYes, [0.205, 0.11])
        XCTAssertEqual(kopylovYes.reduce(0, +), 0.3, accuracy: 1e-9)
        XCTAssertEqual(gautierYes.reduce(0, +), 0.315, accuracy: 1e-9)
        // Removing a round changes no other round's mark.
        var groups = Self.retainedGroups()
        groups[0] = CombatRoundGroup10868(id: Self.kopylov, label: "Roman Kopylov", slots: [groups[0].slots[0], groups[0].slots[2]])
        let fewer = Self.input(.before, groups, slot: nil, original: nil)
        XCTAssertEqual(fewer.railMarks(Self.placeOf(fewer, Self.kR3).market.originals[0]).before, 0.09)
        XCTAssertEqual(fewer.railMarks(Self.placeOf(fewer, Self.kR1).market.originals[0]).before, 0.11)
    }

    func testANoLeadKeepsItsOwnFigureNeverTheWinnerOrTheYes() {
        let overview = [Self.kR1: Self.kR1No, Self.kR2: Self.kR2No, Self.kR3: Self.kR3No, Self.gR1: Self.gR1No, Self.gR3: Self.gR3No]
        for phase in Self.phases {
            let model = Self.input(phase, Self.retainedGroups(overview: overview), slot: nil, original: nil)
            for place in model.places {
                let no = place.market.originals[1]
                XCTAssertEqual(model.lead(place), .original(no, selected: false), "\(phase) \(place.slot.id)")
                XCTAssertEqual(model.tilePresentation(place.group, place.slot, canSelect: true), .rail(no, selected: false, action: .select(Self.ref(place.slot.id, no.id))), "\(phase) \(place.slot.id)")
                XCTAssertEqual(model.railMarks(no).before, Self.row(no.id).probability, "\(phase) \(place.slot.id)")
            }
            // Kopylov Round 1's No lost; the tile keeps the No and its own Lost — no swap to the winning Yes.
            let kR1 = Self.placeOf(model, Self.kR1)
            if phase == .final {
                XCTAssertEqual(model.result(kR1.market.originals[1]), .lost("Lost"))
                XCTAssertTrue(Self.tileValue(model, Self.kR1).hasPrefix("No. Pre-match chance: 89%, \(Self.lateDetail); Contract result: Lost"))
            } else {
                XCTAssertNil(model.result(kR1.market.originals[1]))
            }
        }
    }

    // MARK: Lead and selection

    func testTileLeadsWithHostSideThenOverviewThenListsEverySide() {
        let model = Self.input(.before, Self.retainedGroups(overview: [Self.kR2: Self.kR2No, Self.gR3: Self.gR3Yes]), slot: Self.kR1, original: Self.kR1No)
        let kR1 = Self.placeOf(model, Self.kR1)
        XCTAssertEqual(model.lead(kR1), .original(kR1.market.originals[1], selected: true))
        let kR2 = Self.placeOf(model, Self.kR2)
        XCTAssertEqual(model.lead(kR2), .original(kR2.market.originals[1], selected: false))
        let gR3 = Self.placeOf(model, Self.gR3)
        XCTAssertEqual(model.lead(gR3), .original(gR3.market.originals[0], selected: false))
        // No host side and no overview: every side listed, none chosen — never Yes by default.
        for slotID in [Self.kR3, Self.gR1] {
            XCTAssertEqual(model.lead(Self.placeOf(model, slotID)), .sides, slotID)
        }
    }

    func testHeldUpdateNeverSwitchesTheLeadSide() {
        for phase in Self.phases {
            // CONSTRUCTED update: the originals arrive in the other order with new figures.
            let reordered = Self.retainedGroups(originals: [
                Self.kR2No: Self.original(Self.kR2No, before: Self.obs(0.92, "92%", Self.lateDetail)),
            ])
            var groups = reordered
            let kR2Slot = groups[0].slots[1]
            if case .market(let market) = kR2Slot.state {
                let flipped = CombatRoundMarket10868(id: market.id, question: market.question, originals: market.originals.reversed(), overviewOriginalID: nil)
                groups[0] = CombatRoundGroup10868(id: Self.kopylov, label: "Roman Kopylov", slots: [groups[0].slots[0], Self.slot(Self.kR2, "Round 2", .market(flipped)), groups[0].slots[2]])
            }
            let model = Self.input(phase, groups, slot: Self.kR2, original: Self.kR2No)
            let kR2 = Self.placeOf(model, Self.kR2)
            guard case .original(let lead, true) = model.lead(kR2) else { return XCTFail("\(phase)") }
            XCTAssertEqual(lead.id, Self.kR2No, "\(phase)")
            XCTAssertEqual(model.railMarks(lead).before, 0.92, "\(phase)")
            // Withdrawn: the No leaves the update. Never Yes; the remaining side stays listed.
            var withdrawn = Self.retainedGroups()
            withdrawn[0] = CombatRoundGroup10868(id: Self.kopylov, label: "Roman Kopylov", slots: [
                withdrawn[0].slots[0],
                Self.slot(Self.kR2, "Round 2", .market(Self.market(Self.kR2, [Self.original(Self.kR2Yes)]))),
                withdrawn[0].slots[2],
            ])
            let gone = Self.input(phase, withdrawn, slot: Self.kR2, original: Self.kR2No)
            let goneKR2 = Self.placeOf(gone, Self.kR2)
            XCTAssertEqual(gone.selection, .sideUnavailable(goneKR2, Self.kR2No), "\(phase)")
            XCTAssertEqual(gone.selectionNotice, CombatRoundInput10868.sideUnavailable, "\(phase)")
            XCTAssertEqual(gone.tilePresentation(goneKR2.group, goneKR2.slot, canSelect: true), .unavailable(CombatRoundInput10868.sideUnavailableShort), "\(phase)")
            XCTAssertEqual(gone.panelSides(goneKR2, canSelect: true), Self.listed(goneKR2, goneKR2.market.originals, actionable: true), "\(phase)")
            XCTAssertNil(gone.comparison, "\(phase)")
        }
    }

    // MARK: Phases

    func testBeforeSuppressesInFightResultsAndFinishContext() {
        let model = Self.input(.before, Self.everythingSupplied, slot: Self.kR1, original: Self.kR1Yes)
        for (place, original) in Self.allOriginals(model) {
            XCTAssertNil(model.currentReading(original), original.id)
            XCTAssertNil(model.movement(original), original.id)
            XCTAssertNil(model.result(original), original.id)
            XCTAssertNil(model.resultDetail(original), original.id)
            XCTAssertFalse(model.showsCurrentMark(original), original.id)
            XCTAssertNil(model.railMarks(original).current, original.id)
            XCTAssertNil(model.railMarks(original).segment, original.id)
            let spoken = model.accessibilitySideValue(original, at: place)
            for word in ["In-fight", "Contract result", "Won", "Lost", "62%", Self.movementLine, "Held"] {
                XCTAssertFalse(spoken.contains(word), "\(original.id) \(word)")
            }
        }
        for place in model.places {
            let spoken = model.accessibilityTileValue(place.group, place.slot)
            for word in ["In-fight", "Contract result", "Won", "Lost", "62%", Self.movementLine] {
                XCTAssertFalse(spoken.contains(word), "\(place.slot.id) \(word)")
            }
        }
        XCTAssertEqual(model.keyItems, [.scale, .preMatch])
        XCTAssertNil(model.visibleFinish)
        XCTAssertNil(model.accessibilityFinish)
        XCTAssertEqual(model.comparison, .before(Self.placeOf(model, Self.kR1).market.originals[0]))
        XCTAssertFalse((model.accessibilityComparison ?? "").contains("62%"))
    }

    func testBeforeSpokenTileAndComparisonCarryPreMatchAndProvenance() {
        let model = Self.input(.before, slot: Self.kR1, original: Self.kR1No)
        XCTAssertEqual(model.accessibilityHeader, "Polymarket · contract results. Which round for each fighter?. Pre-match chance · tracks run from 0 to 100%. Before the fight")
        XCTAssertEqual(
            model.accessibilityKey,
            "\(CombatRoundInput10868.scaleKey). \(CombatRoundInput10868.preMatchKey)"
        )
        XCTAssertEqual(
            Self.tileValue(model, Self.kR1),
            "No. Pre-match chance: 89%, \(Self.lateDetail). Selected. Also Yes. Pre-match chance: 11%"
        )
        XCTAssertEqual(
            model.accessibilityComparison,
            "Will Roman Kopylov win in Round 1?, original No. Roman Kopylov, Round 1. Pre-match chance: 89%, \(Self.lateDetail)"
        )
        // An unselected slot with no overview speaks both sides, neither chosen.
        XCTAssertEqual(Self.tileValue(model, Self.kR3), "Yes. Pre-match chance: 9%. No. Pre-match chance: 91%")
    }

    func testDuringRetainedPacketHasNoInFightChanceAndShowsWords() {
        let model = Self.input(.during)
        for (_, original) in Self.allOriginals(model) {
            XCTAssertEqual(model.currentReading(original), .missing("No in-fight chance"), original.id)
            XCTAssertFalse(model.showsCurrentMark(original), original.id)
            XCTAssertNil(model.movement(original), original.id)
            XCTAssertNil(model.railMarks(original).current, original.id)
            XCTAssertNil(model.railMarks(original).segment, original.id)
            XCTAssertNil(model.result(original), original.id)
        }
        XCTAssertEqual(model.keyItems, [.scale, .preMatch, .current])
        XCTAssertEqual(
            model.accessibilityComparison,
            "Will Roman Kopylov win in Round 1?, original Yes. Roman Kopylov, Round 1. Pre-match chance: 11%, \(Self.lateDetail); In-fight chance: No in-fight chance"
        )
    }

    func testDuringComparesPreMatchAndInFightWithEachProvenance() {
        let model = Self.input(.during, Self.everythingSupplied, slot: Self.kR1, original: Self.kR1Yes)
        let kR1 = Self.placeOf(model, Self.kR1)
        let yes = kR1.market.originals[0]
        XCTAssertEqual(model.beforeReading(yes), .value(Self.obs(0.11, "11%", Self.lateDetail)))
        XCTAssertEqual(model.currentReading(yes), .value(Self.kR1YesCurrent))
        XCTAssertTrue(model.showsCurrentMark(yes))
        XCTAssertEqual(model.movement(yes), Self.movementLine)
        XCTAssertEqual(model.railMarks(yes), CombatRoundRailMarks10868(before: 0.11, current: 0.62))
        XCTAssertEqual(model.railMarks(yes).segment, 0.11...0.62)
        XCTAssertEqual(model.comparison, .during(yes))
        XCTAssertEqual(
            model.accessibilityComparison,
            "Will Roman Kopylov win in Round 1?, original Yes. Roman Kopylov, Round 1. Pre-match chance: 11%, \(Self.lateDetail); In-fight chance: 62%, Recorded Oct 3, 5:31 PM PT · Polymarket; \(Self.movementLine)"
        )
        XCTAssertEqual(
            model.accessibilityKey,
            "\(CombatRoundInput10868.scaleKey). \(CombatRoundInput10868.preMatchKey). \(CombatRoundInput10868.currentKey)"
        )
        // A mark that moved down draws the same segment from the lower end.
        let down = CombatRoundRailMarks10868(before: 0.89, current: 0.4)
        XCTAssertEqual(down.segment, 0.4...0.89)
    }

    func testWithheldAndUnavailableCurrentDrawNoMarkSegmentOrFigure() {
        let model = Self.input(.during, Self.everythingSupplied, slot: Self.kR1, original: Self.kR1No)
        let no = Self.placeOf(model, Self.kR1).market.originals[1]
        XCTAssertEqual(model.currentReading(no), .missing("Held since round 1"))
        XCTAssertFalse(model.showsCurrentMark(no))
        XCTAssertNil(model.movement(no))
        XCTAssertEqual(model.railMarks(no), CombatRoundRailMarks10868(before: 0.89, current: nil))
        XCTAssertNil(model.railMarks(no).segment)
        // Never the pre-match reading posing as current.
        XCTAssertNotEqual(model.currentReading(no), .value(Self.obs(0.89, "89%", Self.lateDetail)))
        XCTAssertEqual(
            model.accessibilityComparison,
            "Will Roman Kopylov win in Round 1?, original No. Roman Kopylov, Round 1. Pre-match chance: 89%, \(Self.lateDetail); In-fight chance: Held since round 1"
        )
        // A movement line on a withheld reading is never shown (CONSTRUCTED: none can be supplied there).
        let unavailable = Self.input(.during, Self.retainedGroups(originals: [Self.kR1No: Self.original(Self.kR1No, current: .unavailable("No in-fight chance"))]))
        let unavailableNo = Self.placeOf(unavailable, Self.kR1).market.originals[1]
        XCTAssertEqual(unavailable.railMarks(unavailableNo).current, nil)
    }

    func testPhaseIsTheOwnersAndSettledContractsDoNotMakeItFinal() {
        // Every retained contract is settled, but the owner says the fight is on.
        let model = Self.input(.during)
        for (_, original) in Self.allOriginals(model) {
            XCTAssertNil(model.result(original), original.id)
        }
        XCTAssertEqual(model.phaseSpoken, "During the fight")
        XCTAssertEqual(model.comparison, .during(Self.placeOf(model, Self.kR1).market.originals[0]))
    }

    func testFinalKeepsEachPreMatchBesideItsOwnIndependentResult() {
        let model = Self.input(.final)
        for (place, original) in Self.allOriginals(model) {
            let source = Self.row(original.id)
            XCTAssertEqual(model.beforeReading(original), .value(Self.pregame(source)), original.id)
            XCTAssertEqual(model.result(original), Self.grade(source.result), original.id)
            XCTAssertEqual(model.result(original)?.symbolName, source.result == "Won" ? "checkmark.circle" : "xmark.circle", original.id)
            XCTAssertNil(model.currentReading(original), original.id)
            XCTAssertEqual(model.railMarks(original), CombatRoundRailMarks10868(before: source.probability, current: nil), original.id)
            XCTAssertEqual(model.accessibilitySideValue(original, at: place).hasPrefix(Self.spokenDetailed(.final, original.id)), true, original.id)
        }
        let kR1 = Self.placeOf(model, Self.kR1)
        XCTAssertEqual(model.comparison, .final(kR1.market.originals[0], .won("Won")))
        XCTAssertEqual(
            model.accessibilityComparison,
            "Will Roman Kopylov win in Round 1?, original Yes. Roman Kopylov, Round 1. Pre-match chance: 11%, \(Self.lateDetail); Contract result: Won"
        )
        XCTAssertEqual(model.keyItems, [.scale, .preMatch])
    }

    func testFinalIgnoresSettledQuotesAsChances() {
        // CONSTRUCTED: the owner forwards the settlement-time 1.0 / 0.0 quotes as current readings.
        let settled = Self.retainedGroups(originals: [
            Self.kR1Yes: Self.original(Self.kR1Yes, current: .recorded(Self.obs(1.0, "100%", "Settlement"), movement: nil)),
            Self.kR1No: Self.original(Self.kR1No, current: .recorded(Self.obs(0.0, "0%", "Settlement"), movement: nil)),
        ])
        let model = Self.input(.final, settled, slot: Self.kR1, original: Self.kR1No)
        for original in Self.placeOf(model, Self.kR1).market.originals {
            XCTAssertNil(model.currentReading(original), original.id)
            XCTAssertNil(model.railMarks(original).current, original.id)
            XCTAssertFalse(model.showsCurrentMark(original), original.id)
        }
        let spoken = (model.accessibilityComparison ?? "") + Self.tileValue(model, Self.kR1)
        XCTAssertFalse(spoken.contains("100%"))
        XCTAssertFalse(spoken.contains("Settlement"))
        XCTAssertEqual(model.railMarks(Self.placeOf(model, Self.kR1).market.originals[1]).before, 0.89)
    }

    func testPairResultsAreIndependentAndTheSymbolFollowsTheDisplayedOriginal() {
        // CONSTRUCTED: the Yes result is not admitted while the No reads Won. Nothing is inferred across the pair.
        let groups = Self.retainedGroups(originals: [
            Self.kR2Yes: Self.original(Self.kR2Yes, result: .unconfirmed("Result unconfirmed")),
        ])
        let model = Self.input(.final, groups, slot: Self.kR2, original: Self.kR2Yes)
        let kR2 = Self.placeOf(model, Self.kR2)
        XCTAssertEqual(model.result(kR2.market.originals[0]), .unconfirmed("Result unconfirmed"))
        XCTAssertEqual(model.result(kR2.market.originals[0])?.symbolName, "questionmark.circle")
        XCTAssertEqual(model.result(kR2.market.originals[1]), .won("Won"))
        XCTAssertEqual(model.comparison, .final(kR2.market.originals[0], .unconfirmed("Result unconfirmed")))
        // The retained Kopylov Round 1 pair: the Yes won, the No lost, each with its own symbol.
        let retainedModel = Self.input(.final, slot: Self.kR1, original: Self.kR1No)
        let kR1 = Self.placeOf(retainedModel, Self.kR1)
        XCTAssertEqual(kR1.market.originals.compactMap { retainedModel.result($0)?.symbolName }, ["checkmark.circle", "xmark.circle"])
        XCTAssertEqual(retainedModel.comparison, .final(kR1.market.originals[1], .lost("Lost")))
    }

    func testUnconfirmedVoidAndOtherAreNotLosses() {
        for result in [CombatRoundResult10868.unconfirmed("Result unconfirmed"), .void("Void"), .other("Under review")] {
            XCTAssertNotEqual(result.symbolName, CombatRoundResult10868.lost("Lost").symbolName)
            XCTAssertNotEqual(result.text, "Lost")
        }
        XCTAssertFalse(CombatRoundResult10868.unconfirmed("Result unconfirmed").isSettled)
        XCTAssertFalse(CombatRoundResult10868.other("Under review").isSettled)
        XCTAssertTrue(CombatRoundResult10868.void("Void").isSettled)
    }

    func testPhysicalFinishIsSeparateContextAndNeverGradesMovesOrFillsASlot() {
        // CONSTRUCTED: Kopylov Round 1's Yes result is not admitted, although the official finish names Round 1.
        let groups = Self.retainedGroups(originals: [
            Self.kR1Yes: Self.original(Self.kR1Yes, result: .unconfirmed("Result unconfirmed")),
        ])
        for phase in Self.phases {
            let with = Self.input(phase, groups, slot: Self.kR1, original: Self.kR1Yes, finish: Self.official)
            let without = Self.input(phase, groups, slot: Self.kR1, original: Self.kR1Yes, finish: nil)
            for group in with.groups {
                for slot in group.slots {
                    let label = "\(phase) \(slot.id)"
                    XCTAssertEqual(with.tilePresentation(group, slot, canSelect: true), without.tilePresentation(group, slot, canSelect: true), label)
                    XCTAssertEqual(with.accessibilityTileValue(group, slot), without.accessibilityTileValue(group, slot), label)
                }
            }
            for (left, right) in zip(Self.allOriginals(with), Self.allOriginals(without)) {
                XCTAssertEqual(with.railMarks(left.1), without.railMarks(right.1), "\(phase) \(left.1.id)")
                XCTAssertEqual(with.result(left.1), without.result(right.1), "\(phase) \(left.1.id)")
            }
            XCTAssertEqual(with.accessibilityComparison, without.accessibilityComparison, "\(phase)")
            XCTAssertEqual(Self.presentation(with, Self.gR2, canSelect: true), .absent(Self.noCapturedProp), "\(phase)")
            if phase == .final {
                XCTAssertEqual(with.result(Self.placeOf(with, Self.kR1).market.originals[0]), .unconfirmed("Result unconfirmed"))
            }
            if phase == .before {
                XCTAssertNil(with.visibleFinish)
                XCTAssertNil(with.accessibilityFinish)
            } else {
                XCTAssertEqual(with.visibleFinish, Self.official, "\(phase)")
                XCTAssertEqual(
                    with.accessibilityFinish,
                    "Official bout result. Roman Kopylov def. Ateba Gautier · TKO (strikes) · Round 1, 3:12. UFC results page, captured Oct 13 · finish clock not recorded",
                    "\(phase)"
                )
            }
            XCTAssertNil(without.visibleFinish)
        }
    }

    // MARK: Identity, duplicates and actions

    func testMissingSelectedSideStaysUnavailableAndAllSidesStayListed() {
        for phase in Self.phases {
            let model = Self.input(phase, slot: Self.gR3, original: "999")
            let gR3 = Self.placeOf(model, Self.gR3)
            XCTAssertEqual(model.selection, .sideUnavailable(gR3, "999"), "\(phase)")
            XCTAssertEqual(model.lead(gR3), .unavailable(CombatRoundInput10868.sideUnavailableShort), "\(phase)")
            XCTAssertNil(model.tileAction(gR3, canSelect: true), "\(phase)")
            XCTAssertEqual(model.panelSides(gR3, canSelect: true), Self.listed(gR3, gR3.market.originals, actionable: true), "\(phase)")
            XCTAssertNil(model.comparison, "\(phase)")
            XCTAssertNil(model.detailsAction(canOpenDetails: true), "\(phase)")
            XCTAssertTrue(Self.tileValue(model, Self.gR3).hasPrefix(CombatRoundInput10868.sideUnavailableShort), "\(phase)")
        }
    }

    func testMissingSlotKeepsTilesAndSelectsNothing() {
        for phase in Self.phases {
            let model = Self.input(phase, slot: "retired-slot", original: nil)
            XCTAssertEqual(model.selection, .unavailable("retired-slot"), "\(phase)")
            XCTAssertEqual(model.selectionNotice, CombatRoundInput10868.slotUnavailable, "\(phase)")
            XCTAssertNil(model.comparison, "\(phase)")
            for group in model.groups {
                for slot in group.slots {
                    XCTAssertFalse(model.isSelectedSlot(group, slot), "\(phase) \(slot.id)")
                }
            }
            for place in model.places {
                XCTAssertEqual(model.lead(place), .sides, "\(phase) \(place.slot.id)")
            }
        }
    }

    func testSideNamedWithoutItsSlotResolvesOnlyWhenUnique() {
        let model = Self.input(.before, slot: nil, original: Self.gR3No)
        let gR3 = Self.placeOf(model, Self.gR3)
        XCTAssertEqual(model.selection, .original(gR3, gR3.market.originals[1]))
        XCTAssertEqual(Self.input(.before, slot: nil, original: "999").selection, .unavailable("999"))
    }

    func testDuplicateOriginalIdsCarryNoActionAndCannotResolve() {
        // CONSTRUCTED: Gautier Round 3's No carries Kopylov Round 1's No id.
        let twin = CombatRoundOriginal10868(id: Self.kR1No, marketID: "63900822", label: "No", before: Self.obs(0.89, "89%", Self.lateDetail), beforeMissing: Self.notRecorded, current: Self.noCurrent, result: .won("Won"), resultDetail: nil)
        let groups = Self.retainedGroups(originals: [Self.gR3No: twin])
        for phase in Self.phases {
            for (slot, original) in [(Self.kR1, Self.kR1No), (nil, Self.kR1No), (Self.gR3, Self.kR1No)] as [(String?, String?)] {
                let model = Self.input(phase, groups, slot: slot, original: original)
                let label = "\(phase) \(slot ?? "-")"
                XCTAssertEqual(model.duplicateOriginalIDs, [Self.kR1No], label)
                XCTAssertNil(model.selection.original, label)
                for slotID in [Self.kR1, Self.gR3] {
                    let place = Self.placeOf(model, slotID)
                    let twinSide = place.market.originals.first { $0.id == Self.kR1No }!
                    XCTAssertNil(model.sideAction(twinSide, at: place, canSelect: true), label)
                    let rows = model.tilePresentation(place.group, place.slot, canSelect: true).listed + model.panelSides(place, canSelect: true)
                    XCTAssertTrue(rows.contains { $0.original.id == Self.kR1No }, "\(label) \(slotID)")
                    XCTAssertNil(rows.first { $0.original.id == Self.kR1No }?.action, "\(label) \(slotID)")
                }
                // The unambiguous Yes beside each twin stays selectable.
                let kR1 = Self.placeOf(model, Self.kR1)
                XCTAssertEqual(model.sideAction(kR1.market.originals[0], at: kR1, canSelect: true), .select(Self.ref(Self.kR1, Self.kR1Yes)), label)
            }
        }
    }

    func testDuplicateSlotAndGroupIdsCarryNoTileOrSideAction() {
        // CONSTRUCTED: Gautier Round 3 reuses Kopylov Round 1's slot id.
        var slotTwins = Self.retainedGroups(overview: [Self.kR1: Self.kR1Yes, Self.gR3: Self.gR3Yes])
        let gR3State = slotTwins[1].slots[2].state
        slotTwins[1] = CombatRoundGroup10868(id: Self.gautier, label: "Ateba Gautier", slots: [slotTwins[1].slots[0], slotTwins[1].slots[1], Self.slot(Self.kR1, "Round 3", gR3State)])
        // CONSTRUCTED: both fighters carry one group id.
        var groupTwins = Self.retainedGroups(overview: [Self.kR1: Self.kR1Yes, Self.gR3: Self.gR3Yes])
        groupTwins[1] = CombatRoundGroup10868(id: Self.kopylov, label: "Ateba Gautier", slots: groupTwins[1].slots)
        for phase in Self.phases {
            let model = Self.input(phase, slotTwins, slot: Self.kR1, original: Self.kR1Yes)
            XCTAssertEqual(model.duplicateSlotIDs, [Self.kR1], "\(phase)")
            XCTAssertEqual(model.selection, .unavailable(Self.kR1), "\(phase)")
            for place in model.places where place.slot.id == Self.kR1 {
                XCTAssertNil(model.tileAction(place, canSelect: true), "\(phase)")
                guard case .railWithSides(let lead, let others) = model.tilePresentation(place.group, place.slot, canSelect: true) else {
                    return XCTFail("\(phase) \(place.group.id)")
                }
                XCTAssertEqual(lead.label, "Yes", "\(phase)")
                XCTAssertTrue(others.allSatisfy { $0.action == nil }, "\(phase)")
            }
            let grouped = Self.input(phase, groupTwins, slot: nil, original: nil)
            XCTAssertEqual(grouped.duplicateGroupIDs, [Self.kopylov], "\(phase)")
            for place in grouped.places {
                XCTAssertNil(grouped.tileAction(place, canSelect: true), "\(phase) \(place.slot.id)")
                for original in place.market.originals {
                    XCTAssertNil(grouped.sideAction(original, at: place, canSelect: true), "\(phase) \(original.id)")
                }
            }
            XCTAssertEqual(Self.input(phase, groupTwins, slot: Self.kR2, original: Self.kR2No).selection, .unavailable(Self.kR2), "\(phase)")
        }
    }

    func testExactActionsCarryEventGroupSlotMarketAndOriginal() {
        let model = Self.input(.final, Self.retainedGroups(overview: [Self.gR1: Self.gR1No]), slot: Self.kR3, original: Self.kR3No)
        let kR3 = Self.placeOf(model, Self.kR3)
        XCTAssertEqual(model.tileAction(kR3, canSelect: true), .select(Self.ref(Self.kR3, Self.kR3No)))
        XCTAssertEqual(Self.ref(Self.kR3, Self.kR3No), CombatRoundOriginalRef10868(eventID: "15318681", groupID: "kopylov", slotID: "kopylov-r3", marketID: "63900820", originalID: "240655017"))
        let gR1 = Self.placeOf(model, Self.gR1)
        XCTAssertEqual(model.tileAction(gR1, canSelect: true), .select(Self.ref(Self.gR1, Self.gR1No)))
        XCTAssertEqual(model.sideAction(gR1.market.originals[0], at: gR1, canSelect: true), .select(Self.ref(Self.gR1, Self.gR1Yes)))
        XCTAssertEqual(model.detailsAction(canOpenDetails: true), .details(Self.ref(Self.kR3, Self.kR3No)))
        XCTAssertNil(model.detailsAction(canOpenDetails: false))
        var selected: [CombatRoundOriginalRef10868] = []
        var details: [CombatRoundOriginalRef10868] = []
        model.tileAction(gR1, canSelect: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        model.detailsAction(canOpenDetails: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        XCTAssertEqual(selected, [Self.ref(Self.gR1, Self.gR1No)])
        XCTAssertEqual(details, [Self.ref(Self.kR3, Self.kR3No)])
        // Details only while an exact original resolves.
        XCTAssertNil(Self.input(.final, slot: Self.kR3, original: nil).detailsAction(canOpenDetails: true))
    }

    func testNoCallbacksMeansStaticContentAndNoInstruction() {
        for phase in Self.phases {
            let model = Self.input(phase, Self.retainedGroups(overview: [Self.kR2: Self.kR2No]), slot: Self.kR1, original: Self.kR1Yes)
            XCTAssertNil(model.instruction(canSelect: false), "\(phase)")
            XCTAssertEqual(model.instruction(canSelect: true), CombatRoundInput10868.chooseInstruction, "\(phase)")
            for group in model.groups {
                for slot in group.slots {
                    let presentation = model.tilePresentation(group, slot, canSelect: false)
                    XCTAssertTrue(presentation.listed.allSatisfy { $0.action == nil }, "\(phase) \(slot.id)")
                    if case .rail(_, _, let action) = presentation { XCTAssertNil(action, "\(phase) \(slot.id)") }
                }
            }
            for place in model.places {
                XCTAssertNil(model.tileAction(place, canSelect: false), "\(phase)")
                XCTAssertTrue(model.panelSides(place, canSelect: false).allSatisfy { $0.action == nil }, "\(phase)")
            }
            // No captured slot at all: no instruction even with a callback.
            let empty = Self.input(phase, [CombatRoundGroup10868(id: Self.gautier, label: "Ateba Gautier", slots: [Self.slot(Self.gR2, "Round 2", .noCapturedProp(Self.noCapturedProp))])], slot: nil, original: nil)
            XCTAssertNil(empty.instruction(canSelect: true), "\(phase)")
            XCTAssertEqual(empty.keyItems, [], "\(phase)")
            XCTAssertNil(empty.accessibilityKey, "\(phase)")
        }
    }

    func testInvalidOverviewWithValidAlternativesListsEveryOriginalWithExactActions() {
        // CONSTRUCTED: Kopylov Round 1's overview names an unknown id; Kopylov
        // Round 3's names Kopylov Round 1's Yes; Gautier Round 3's No was
        // withdrawn while its overview still names it. Gautier Round 1 is valid.
        var groups = Self.retainedGroups(overview: [Self.kR1: "999", Self.kR3: Self.kR1Yes, Self.gR1: Self.gR1No, Self.gR3: Self.gR3No])
        groups[1] = CombatRoundGroup10868(id: Self.gautier, label: "Ateba Gautier", slots: [
            groups[1].slots[0],
            groups[1].slots[1],
            Self.slot(Self.gR3, "Round 3", .market(Self.market(Self.gR3, [Self.original(Self.gR3Yes)], overview: Self.gR3No))),
        ])
        for phase in Self.phases {
            for (slot, original) in [(nil, nil), (Self.gR1, Self.gR1No)] as [(String?, String?)] {
                let model = Self.input(phase, groups, slot: slot, original: original)
                let label = "\(phase) \(slot ?? "none")"
                for slotID in [Self.kR1, Self.kR3, Self.gR3] {
                    let place = Self.placeOf(model, slotID)
                    XCTAssertEqual(model.lead(place), .unavailable(CombatRoundInput10868.overviewUnavailable), "\(label) \(slotID)")
                    XCTAssertNil(model.tileAction(place, canSelect: true), "\(label) \(slotID)")
                    for canSelect in [true, false] {
                        XCTAssertEqual(
                            model.tilePresentation(place.group, place.slot, canSelect: canSelect),
                            .unavailableWithSides(CombatRoundInput10868.overviewUnavailable, sides: Self.listed(place, place.market.originals, actionable: canSelect)),
                            "\(label) \(slotID)"
                        )
                    }
                }
                let gR1 = Self.placeOf(model, Self.gR1)
                XCTAssertEqual(
                    model.tilePresentation(gR1.group, gR1.slot, canSelect: true),
                    .rail(gR1.market.originals[1], selected: slot != nil, action: .select(Self.ref(Self.gR1, Self.gR1No))),
                    label
                )
            }
        }
    }

    func testStaticOverviewOnUnselectedSlotKeepsRailAndListsTheOtherOriginal() {
        let overview = [Self.kR1: Self.kR1Yes, Self.kR2: Self.kR2No, Self.gR1: Self.gR1Yes, Self.gR3: Self.gR3No]
        for phase in Self.phases {
            let model = Self.input(phase, Self.retainedGroups(overview: overview), slot: Self.kR1, original: Self.kR1Yes)
            let kR1 = Self.placeOf(model, Self.kR1)
            let kR2 = Self.placeOf(model, Self.kR2)
            XCTAssertEqual(model.tilePresentation(kR1.group, kR1.slot, canSelect: false), .rail(kR1.market.originals[0], selected: true, action: nil), "\(phase)")
            XCTAssertEqual(
                model.tilePresentation(kR2.group, kR2.slot, canSelect: false),
                .railWithSides(kR2.market.originals[1], others: Self.listed(kR2, [kR2.market.originals[0]], actionable: false)),
                "\(phase)"
            )
            XCTAssertEqual(model.accessibilityLeadValue(kR2.market.originals[1]), "No. \(Self.spokenDetailed(phase, Self.kR2No))", "\(phase)")
            XCTAssertEqual(model.accessibilitySideValue(kR2.market.originals[0], at: kR2), Self.spokenDetailed(phase, Self.kR2Yes), "\(phase)")
            let none = Self.input(phase, Self.retainedGroups(overview: overview), slot: nil, original: nil)
            for place in none.places where place.market.overviewOriginalID != nil {
                guard case .railWithSides(let lead, let others) = none.tilePresentation(place.group, place.slot, canSelect: false) else {
                    return XCTFail("\(phase) \(place.slot.id)")
                }
                XCTAssertEqual(lead.id, place.market.overviewOriginalID)
                XCTAssertEqual(Set(others.map(\.original.id)).union([lead.id]), Set(place.market.originals.map(\.id)))
                XCTAssertTrue(others.allSatisfy { $0.action == nil })
            }
        }
    }

    func testSelectedSlotTileNeverRepeatsItsSideRows() {
        for phase in Self.phases {
            let missing = Self.input(phase, slot: Self.kR2, original: "999")
            let kR2 = Self.placeOf(missing, Self.kR2)
            for canSelect in [true, false] {
                XCTAssertEqual(missing.tilePresentation(kR2.group, kR2.slot, canSelect: canSelect), .unavailable(CombatRoundInput10868.sideUnavailableShort), "\(phase)")
                XCTAssertEqual(missing.panelSides(kR2, canSelect: canSelect), Self.listed(kR2, kR2.market.originals, actionable: canSelect), "\(phase)")
            }
            let picked = Self.input(phase, slot: Self.gR3, original: Self.gR3No)
            let gR3 = Self.placeOf(picked, Self.gR3)
            XCTAssertEqual(picked.tilePresentation(gR3.group, gR3.slot, canSelect: false), .rail(gR3.market.originals[1], selected: true, action: nil), "\(phase)")
            XCTAssertEqual(picked.panelSides(gR3, canSelect: false), Self.listed(gR3, gR3.market.originals, actionable: false), "\(phase)")
        }
    }

    func testEveryOriginalIsOnScreenOrOneTileActionFromItsSideRow() {
        let overviews: [[String: String]] = [
            [:],
            [Self.kR1: Self.kR1No, Self.kR2: Self.kR2Yes, Self.gR1: Self.gR1No, Self.gR3: Self.gR3Yes],
            [Self.kR1: "999", Self.kR3: Self.kR3No, Self.gR3: Self.kR1Yes],
        ]
        let selections: [(String?, String?)] = [
            (nil, nil), (Self.kR1, Self.kR1Yes), (Self.kR1, "999"), (Self.kR3, nil), (Self.gR2, nil),
            ("retired-slot", nil), (nil, Self.gR3No), (nil, Self.kR2Yes), (Self.gR1, Self.gR1No),
        ]
        for phase in Self.phases {
            for overview in overviews {
                for (selectedSlot, selectedOriginal) in selections {
                    let model = Self.input(phase, Self.retainedGroups(overview: overview), slot: selectedSlot, original: selectedOriginal)
                    for canSelect in [true, false] {
                        var everyRef = Set<CombatRoundOriginalRef10868>()
                        for group in model.groups {
                            for slot in group.slots {
                                let label = "\(phase) \(overview) \(selectedSlot ?? "-")/\(selectedOriginal ?? "-") \(canSelect) \(slot.id)"
                                let presentation = model.tilePresentation(group, slot, canSelect: canSelect)
                                guard let place = model.place(group, slot) else {
                                    // The uncaptured slot: its words, never an original or an action.
                                    XCTAssertEqual(presentation, .absent(Self.noCapturedProp), label)
                                    continue
                                }
                                var shown = Set(presentation.listed.map(\.original.id))
                                var tileAction: CombatRoundAction10868?
                                switch presentation {
                                case .rail(let lead, _, let action):
                                    shown.insert(lead.id)
                                    tileAction = action
                                case .railWithSides(let lead, _):
                                    shown.insert(lead.id)
                                case .unavailable, .unavailableWithSides, .sides:
                                    break
                                case .absent:
                                    XCTFail(label)
                                }
                                // The rows the selected panel actually mounts — counted where they are.
                                let panel = model.panelSides(place, canSelect: canSelect)
                                shown.formUnion(panel.map(\.original.id))
                                if !panel.isEmpty {
                                    XCTAssertEqual(model.selection.place, place, label)
                                    XCTAssertEqual(panel.map(\.original.id), place.market.originals.map(\.id), label)
                                }
                                if model.selection.place == place {
                                    // Exactly one place lists the selected slot's sides: its tile or the panel.
                                    XCTAssertNotEqual(panel.isEmpty, presentation.listed.isEmpty, label)
                                }
                                let rows = presentation.listed.map(\.original.id) + panel.map(\.original.id)
                                XCTAssertEqual(rows.count, Set(rows).count, label)
                                if shown != Set(place.market.originals.map(\.id)) {
                                    // Only an actionable rail may leave a side off screen: its action
                                    // selects this slot, whose side rows then list every side.
                                    guard case .select(let ref)? = tileAction else { XCTFail(label); continue }
                                    XCTAssertEqual(ref.slotID, slot.id, label)
                                }
                                for side in presentation.listed + panel {
                                    XCTAssertEqual(side.action, model.sideAction(side.original, at: place, canSelect: canSelect), label)
                                }
                                if !canSelect {
                                    XCTAssertTrue(presentation.listed.allSatisfy { $0.action == nil }, label)
                                    XCTAssertTrue(panel.allSatisfy { $0.action == nil }, label)
                                    XCTAssertNil(tileAction, label)
                                }
                                // Every original is spoken by its tile, whatever the lead.
                                let spoken = model.accessibilityTileValue(group, slot)
                                for original in place.market.originals {
                                    XCTAssertTrue(spoken.contains("\(original.label). Pre-match chance: \(Self.row(original.id).text)"), "\(label) \(original.id)")
                                    if case .select(let ref)? = model.sideAction(original, at: place, canSelect: canSelect) { everyRef.insert(ref) }
                                }
                            }
                        }
                        if canSelect {
                            XCTAssertEqual(everyRef.map(\.originalID).sorted(), Self.retained.map(\.outcomeID).sorted())
                            XCTAssertFalse(everyRef.contains { $0.slotID == Self.gR2 })
                        } else {
                            XCTAssertTrue(everyRef.isEmpty)
                        }
                    }
                }
            }
        }
    }

    func testSlotChosenWithoutSideOrOverviewMountsEachOriginalOnce() {
        for phase in Self.phases {
            let model = Self.input(phase, slot: Self.gR1, original: nil)
            let gR1 = Self.placeOf(model, Self.gR1)
            XCTAssertEqual(model.selection, .slot(gR1), "\(phase)")
            XCTAssertEqual(model.lead(gR1), .sides, "\(phase)")
            XCTAssertNil(model.comparison, "\(phase)")
            XCTAssertNil(model.detailsAction(canOpenDetails: true), "\(phase)")
            XCTAssertTrue(Self.tileValue(model, Self.gR1).hasSuffix(CombatRoundInput10868.slotSelectedTag), "\(phase)")
            XCTAssertFalse(model.panelListsSides(gR1), "\(phase)")
            for canSelect in [true, false] {
                let label = "\(phase) \(canSelect)"
                let tile = model.tilePresentation(gR1.group, gR1.slot, canSelect: canSelect)
                let panel = model.panelSides(gR1, canSelect: canSelect)
                XCTAssertEqual(tile, .sides(Self.listed(gR1, gR1.market.originals, actionable: canSelect)), label)
                XCTAssertEqual(panel, [], label)
                let rows = tile.listed + panel
                for original in gR1.market.originals {
                    XCTAssertEqual(rows.filter { $0.original.id == original.id }.count, 1, "\(label) \(original.id)")
                }
                var selected: [CombatRoundOriginalRef10868] = []
                for side in rows {
                    side.action?.perform(onSelect: { selected.append($0) }, onDetails: { _ in XCTFail(label) })
                }
                XCTAssertEqual(selected, canSelect ? [Self.ref(Self.gR1, Self.gR1Yes), Self.ref(Self.gR1, Self.gR1No)] : [], label)
                let identifiers = rows.map { CombatRoundAccessibilityID10868.side(gR1.slot.id, $0.original.id) }
                XCTAssertEqual(identifiers.count, Set(identifiers).count, label)
                for side in rows {
                    let spoken = model.accessibilitySideValue(side.original, at: gR1)
                    XCTAssertEqual(spoken, Self.spokenDetailed(phase, side.original.id), "\(label) \(side.original.id)")
                    XCTAssertFalse(spoken.contains(CombatRoundInput10868.selectedTag), "\(label) \(side.original.id)")
                }
                // Contrast: a chosen side makes the tile the rail and the panel lists every side once.
                let picked = Self.input(phase, slot: Self.gR1, original: Self.gR1Yes)
                let pickedGR1 = Self.placeOf(picked, Self.gR1)
                XCTAssertEqual(picked.tilePresentation(pickedGR1.group, pickedGR1.slot, canSelect: canSelect), .rail(pickedGR1.market.originals[0], selected: true, action: canSelect ? .select(Self.ref(Self.gR1, Self.gR1Yes)) : nil), label)
                XCTAssertEqual(picked.panelSides(pickedGR1, canSelect: canSelect), Self.listed(pickedGR1, pickedGR1.market.originals, actionable: canSelect), label)
            }
        }
    }

    func testTimingOnlyForTheExactResolvedSelection() {
        let timing = CombatRoundTiming10868(originalID: Self.gR1Yes, title: "Quote time", lines: ["Last recorded Oct 3, 9:42 AM PT, 7 h 37 min before the scheduled start"])
        let exact = Self.input(.before, slot: Self.gR1, original: Self.gR1Yes, timing: timing)
        XCTAssertEqual(exact.timingPresentation(hasBinding: true), .disclosure(timing))
        XCTAssertEqual(exact.timingPresentation(hasBinding: false), .expanded(timing))
        XCTAssertNil(Self.input(.before, slot: Self.gR1, original: Self.gR1No, timing: timing).timingPresentation(hasBinding: true))
        XCTAssertNil(Self.input(.before, slot: Self.gR1, original: nil, timing: timing).timingPresentation(hasBinding: true))
        XCTAssertNil(Self.input(.before, slot: Self.gR2, original: nil, timing: timing).timingPresentation(hasBinding: true))
    }

    // MARK: Shapes, words and geometry

    func testSelectionResultAndTrackKeysAreDistinctShapesAndWords() {
        let symbols = [
            CombatRoundResult10868.won("Won"), .lost("Lost"), .void("Void"), .unconfirmed("Result unconfirmed"), .other("Under review"),
        ].map(\.symbolName)
        XCTAssertEqual(Set(symbols).count, 5)
        XCTAssertFalse(symbols.contains("checkmark"))
        let words = [
            CombatRoundInput10868.scaleKey, CombatRoundInput10868.preMatchKey, CombatRoundInput10868.currentKey,
            CombatRoundInput10868.selectedTag, CombatRoundInput10868.slotSelectedTag, CombatRoundInput10868.notDrawn,
        ]
        XCTAssertEqual(Set(words).count, words.count)
        XCTAssertTrue(CombatRoundInput10868.preMatchKey.contains("Hollow"))
        XCTAssertTrue(CombatRoundInput10868.currentKey.contains("Filled"))
        XCTAssertTrue(CombatRoundInput10868.scaleKey.contains(CombatRoundInput10868.scaleStart))
        XCTAssertTrue(CombatRoundInput10868.scaleKey.contains(CombatRoundInput10868.scaleEnd))
    }

    func testZeroIsAPlaceOnTheTrackAndAbsentIsWords() {
        XCTAssertEqual(CombatRoundGeometry10868.position(0), 0)
        XCTAssertEqual(CombatRoundGeometry10868.position(1), 1)
        // CONSTRUCTED: a real 0% reading draws at the start; an absent one is words.
        let groups = Self.retainedGroups(originals: [
            Self.kR3Yes: Self.original(Self.kR3Yes, before: Self.obs(0, "0%", Self.lateDetail)),
            Self.kR3No: Self.original(Self.kR3No, before: .some(nil)),
        ])
        let model = Self.input(.before, groups, slot: Self.kR3, original: Self.kR3Yes)
        let kR3 = Self.placeOf(model, Self.kR3)
        XCTAssertEqual(model.railMarks(kR3.market.originals[0]).before, 0)
        XCTAssertEqual(model.beforeReading(kR3.market.originals[0]), .value(Self.obs(0, "0%", Self.lateDetail)))
        XCTAssertNil(model.railMarks(kR3.market.originals[1]).before)
        XCTAssertEqual(model.beforeReading(kR3.market.originals[1]), .missing(Self.notRecorded))
        XCTAssertEqual(Self.tileValue(model, Self.kR3), "Yes. Pre-match chance: 0%, \(Self.lateDetail). Selected. Also No. Pre-match chance: \(Self.notRecorded)")
    }

    func testMalformedProbabilityDrawsNoMarkAndKeepsTheFigureWithWords() {
        for bad in [Double.nan, .infinity, -.infinity, -0.01, 1.01] {
            XCTAssertNil(CombatRoundGeometry10868.position(bad), "\(bad)")
        }
        // CONSTRUCTED owner values outside 0...1.
        let groups = Self.retainedGroups(originals: [
            Self.gR3Yes: Self.original(Self.gR3Yes, before: Self.obs(1.5, "150%", Self.lateDetail), current: .recorded(Self.obs(.nan, "—%", "Recorded Oct 3, 5:31 PM PT · Polymarket"), movement: nil)),
        ])
        let before = Self.input(.before, groups, slot: Self.gR3, original: Self.gR3Yes)
        let yes = Self.placeOf(before, Self.gR3).market.originals[0]
        XCTAssertEqual(before.railMarks(yes), CombatRoundRailMarks10868(before: nil, current: nil))
        XCTAssertEqual(before.beforeReading(yes), .value(Self.obs(1.5, "150%", Self.lateDetail)))
        XCTAssertEqual(
            before.accessibilityComparison,
            "Will Ateba Gautier win in Round 3?, original Yes. Ateba Gautier, Round 3. Pre-match chance: 150%, \(Self.lateDetail), \(CombatRoundInput10868.notDrawn)"
        )
        let during = Self.input(.during, groups, slot: Self.gR3, original: Self.gR3Yes)
        let duringYes = Self.placeOf(during, Self.gR3).market.originals[0]
        XCTAssertEqual(during.railMarks(duringYes), CombatRoundRailMarks10868(before: nil, current: nil))
        XCTAssertNil(during.railMarks(duringYes).segment)
        XCTAssertTrue((during.accessibilityComparison ?? "").contains("In-fight chance: —%, Recorded Oct 3, 5:31 PM PT · Polymarket, \(CombatRoundInput10868.notDrawn)"))
        // The tile names the unplaced figure too.
        XCTAssertTrue(Self.tileValue(during, Self.gR3).hasPrefix("Yes. Pre-match chance: 150%, \(Self.lateDetail), \(CombatRoundInput10868.notDrawn)"))
    }

    func testMarkPositionKeepsZeroAndHundredWholeOnTheTrack() {
        XCTAssertEqual(CombatRoundGeometry10868.markX(0, width: 100, inset: 5), 5)
        XCTAssertEqual(CombatRoundGeometry10868.markX(1, width: 100, inset: 5), 95)
        XCTAssertEqual(CombatRoundGeometry10868.markX(0.5, width: 100, inset: 5), 50)
        XCTAssertEqual(CombatRoundGeometry10868.markX(0.25, width: 110, inset: 5), 30)
        XCTAssertEqual(CombatRoundGeometry10868.markX(1, width: 6, inset: 5), 5)
    }

    func testLongNamesAndQualifiedFiguresAreShownVerbatim() {
        // CONSTRUCTED long owner strings and a qualified figure.
        let longName = "Alexander Volkanovski-Rodríguez de la Fuente"
        let longRound = "Round 1 (five minutes)"
        let figure = Self.obs(0.996, "≥99.5%", Self.lateDetail)
        let groups = [CombatRoundGroup10868(id: Self.kopylov, label: longName, slots: [
            Self.slot(Self.kR1, longRound, .market(Self.market(Self.kR1, [Self.original(Self.kR1Yes, before: figure), Self.original(Self.kR1No)]))),
        ])]
        let model = Self.input(.before, groups, slot: Self.kR1, original: Self.kR1Yes)
        let place = Self.placeOf(model, Self.kR1)
        XCTAssertEqual(model.accessibilitySlotLabel(place.group, place.slot), "\(longName), \(longRound)")
        XCTAssertEqual(model.beforeReading(place.market.originals[0]), .value(figure))
        XCTAssertTrue(Self.tileValue(model, Self.kR1).hasPrefix("Yes. Pre-match chance: ≥99.5%, \(Self.lateDetail)"))
        XCTAssertTrue((model.accessibilityComparison ?? "").contains("\(longName), \(longRound)"))
        XCTAssertEqual(CombatRoundGeometry10868.words(longName), ["Alexander", "Volkanovski-Rodríguez", "de", "la", "Fuente"])
        XCTAssertEqual(CombatRoundGeometry10868.words("≥99.5%"), ["≥99.5%"])
    }

    func testIdentifiersAreDistinctPerSlotAndOriginal() {
        let model = Self.input(.before)
        let tiles = model.groups.flatMap { $0.slots.map { CombatRoundAccessibilityID10868.tile($0.id) } }
        XCTAssertEqual(Set(tiles).count, 6)
        let sides = Self.allOriginals(model).map { CombatRoundAccessibilityID10868.side($0.0.slot.id, $0.1.id) }
        XCTAssertEqual(Set(sides).count, 10)
        XCTAssertEqual(Set(model.groups.map { CombatRoundAccessibilityID10868.group($0.id) }).count, 2)
    }

    // MARK: Measured layout (arithmetic; CONSTRUCTED widths)

    func testThreeRoundsKeepThreeColumnsAtPhoneWidthsAndFightersStack() {
        // 320 / 375 / 393 pt phones minus 16 pt margins each side.
        for available: CGFloat in [288, 343, 361] {
            XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: available, count: 3, spacing: 8, minimumColumnWidth: 88, forceSingle: false) { _ in true }, 3, "\(available)")
        }
        XCTAssertEqual(CombatRoundGeometry10868.columnWidth(available: 288, columns: 3, spacing: 8), 272.0 / 3.0, accuracy: 1e-9)
        XCTAssertEqual(CombatRoundGeometry10868.columnWidth(available: 343, columns: 3, spacing: 8), 109)
        // A fighter needs 3 × 88 + 2 × 8 = 280 to keep its rounds on one row.
        let group = CombatRoundGeometry10868.groupMinimumWidth(slots: 3, tileMinimum: 88, spacing: 8)
        XCTAssertEqual(group, 280)
        for available: CGFloat in [288, 343, 361] {
            XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: available, count: 2, spacing: 16, minimumColumnWidth: group, forceSingle: false) { _ in true }, 1, "\(available)")
        }
        // Wide: the two fighters sit side by side.
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 1180, count: 2, spacing: 16, minimumColumnWidth: group, forceSingle: false) { _ in true }, 2)
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 576, count: 2, spacing: 16, minimumColumnWidth: group, forceSingle: false) { _ in true }, 2)
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 575, count: 2, spacing: 16, minimumColumnWidth: group, forceSingle: false) { _ in true }, 1)
        XCTAssertEqual(CombatRoundGeometry10868.groupMinimumWidth(slots: 0, tileMinimum: 88, spacing: 8), 0)
    }

    func testALongWordDropsAColumnInsteadOfBreakingOrShrinking() {
        // CONSTRUCTED: a 100 pt unbreakable word at 320 pt keeps two rounds per row, then one.
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 288, count: 3, spacing: 8, minimumColumnWidth: 88, forceSingle: false) { $0 >= 100 }, 2)
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 288, count: 3, spacing: 8, minimumColumnWidth: 88, forceSingle: false) { $0 >= 200 }, 1)
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 288, count: 3, spacing: 8, minimumColumnWidth: 88, forceSingle: false) { _ in false }, 1)
        XCTAssertEqual(CombatRoundGeometry10868.rows(count: 3, columns: 2), [[0, 1], [2]])
    }

    func testEnlargedTextStacksAndWideHasNoFighterOrRoundCeiling() {
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 1180, count: 3, spacing: 8, minimumColumnWidth: 88, forceSingle: true) { _ in true }, 1)
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 1180, count: 2, spacing: 16, minimumColumnWidth: 280, forceSingle: true) { _ in true }, 1)
        // CONSTRUCTED five-round bout: five columns on a wide window, no three-round ceiling.
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 560, count: 5, spacing: 8, minimumColumnWidth: 88, forceSingle: false) { _ in true }, 5)
        XCTAssertEqual(CombatRoundGeometry10868.groupMinimumWidth(slots: 5, tileMinimum: 88, spacing: 8), 472)
        // CONSTRUCTED three fighters: three groups wide, no two-fighter ceiling.
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 1180, count: 3, spacing: 16, minimumColumnWidth: 280, forceSingle: false) { _ in true }, 3)
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: nil, count: 5, spacing: 8, minimumColumnWidth: 88, forceSingle: false) { _ in true }, 5)
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 0, count: 5, spacing: 8, minimumColumnWidth: 88, forceSingle: false) { _ in true }, 1)
        XCTAssertEqual(CombatRoundGeometry10868.columnCount(available: 343, count: 0, spacing: 8, minimumColumnWidth: 88, forceSingle: false) { _ in true }, 0)
    }

    func testComparisonPairSitsSideBySideOnlyWhenBothFiguresStayWhole() {
        XCTAssertEqual(CombatRoundGeometry10868.pairArrangement(available: 327, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: false), .sideBySide)
        XCTAssertEqual(CombatRoundGeometry10868.pairArrangement(available: 240, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: false), .stacked)
        XCTAssertEqual(CombatRoundGeometry10868.pairArrangement(available: 327, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: true), .stacked)
        XCTAssertEqual(CombatRoundGeometry10868.pairArrangement(available: 327, first: .nan, second: 100, spacing: 16, equalColumns: true, forceStack: false), .stacked)
        XCTAssertEqual(CombatRoundGeometry10868.pairArrangement(available: nil, first: 120, second: 100, spacing: 16, equalColumns: true, forceStack: false), .sideBySide)
        XCTAssertEqual(CombatRoundGeometry10868.columns(total: 327, first: 120, spacing: 16, equalColumns: true), CombatRoundColumns10868(first: 155.5, second: 155.5))
    }
}
