import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the player-duel host glue and admission
/// (`PlayerDuelEventPageAdapter10868`). PREPARED, NOT RUN: these tests were
/// written and Swift-parsed only; they have never been compiled or executed.
///
/// SOURCE-CONTRACT TESTS. They check what the host does with owner values it
/// is given — admission fences, pass-through, routing and callback shape. They
/// are not runtime, real-data, real-page, full-range, real-live or
/// whole-phase evidence, and they earn no production-preparation credit.
///
/// REAL (retained or archived; values copied, sources cited):
///   - R1 `HockeyJourneyOriginalsAdapter10868Tests.wildBruinsDetail` — retained
///     production NHL 15169793 detail, completed (final phase).
///   - R1b `HockeyJourneyOriginalsAdapter10868Tests.devilsKnightsDetail` —
///     retained production NHL 15338496 detail, scheduled (before phase).
///   - R3 archived duel values (`PLAYER-DUEL-RETAINED-CASES.json`, as copied
///     at `PlayerContributionPresentation10868Tests.swift:923-935`): the two
///     KXNBAH2H3PT originals and titles, ESPN ids 4592479 / 3934719, names,
///     teams, final 5 made / 10 attempts and 3 / 6, results yes / no, outright
///     chance null.
///   - R4 archived contract values (`PLAYER-DUEL-VALUE-RETAINED-CASES.json`,
///     `PlayerContributionPresentation10868Tests.swift:1391-1404`): 62¢ → 57¢
///     and 52¢ → 47¢ before; 57¢ → 99¢ and 47¢ → 2¢ final, with their
///     minute-ending seconds.
///   - R5 archived game-winner trades (`FieldProbabilityHistoryPresentation10868Tests.swift`
///     :2591-2592, :2830-2831, :2820, :3059): KXNBAGAME-26JUN03NYKSAS-NYK 0.37
///     and -SAS 0.64 at 1780532940; last trades 0.99 and 0.01 at 1780542960.
///
/// CONSTRUCTED: every bundle and owner value in this file is CONSTRUCTED unless
/// named above as a retained/archived input. In particular:
///   - EVERY bundle here pairs a retained NHL event (R1/R1b) with NBA duel
///     inputs (R3/R4/R5). That pairing is an identity-mechanics control ONLY —
///     never a real page, a production binding or evidence that any owner
///     supplies such a bundle (none does at this base).
///   - Every owner word, label, rule, provenance row, catalogue identity and
///     scope string, route, mode and grade; the live status (R1b's decoded
///     status changed to "live" — no live specimen is retained); foreign
///     event ids; the mini anchor (two one-point runs per original from R5,
///     with constructed ids, ticks, actions and every defaulted field set to
///     a non-default value so a dropped field fails); live counts.
///   - The spies that record holds, opens and owner calls.
///
/// No NBA event detail, game-markets body or live capture is retained, so no
/// real-page test can be prepared. The 7 owner-data gaps, the threshold
/// obligation and every delivery obligation stay open.
@MainActor
enum PlayerDuelEventPageFixtures10868 {
    typealias A = PlayerDuelEventPageAdapter10868
    typealias Details = OriginalMarketDetails9483

    static let now = Date(timeIntervalSince1970: 1_780_600_000)

    // MARK: Retained events (REAL NHL bodies)

    static func detail(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    /// R1: NHL 15169793, completed — the page reads final.
    static func finalEvent() throws -> EventDetail {
        try detail(HockeyJourneyOriginalsAdapter10868Tests.wildBruinsDetail)
    }

    /// R1b: NHL 15338496, scheduled — the page reads before.
    static func beforeEvent() throws -> EventDetail {
        try detail(HockeyJourneyOriginalsAdapter10868Tests.devilsKnightsDetail)
    }

    /// CONSTRUCTED: R1b with its decoded status changed to "live".
    static func liveEvent() throws -> EventDetail {
        var event = try beforeEvent()
        event.status = "live"
        return event
    }

    // MARK: R3 — archived duel values, CONSTRUCTED words

    static let champagnieOriginal = "KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-JCHAMPAGNIE30"
    static let anunobyOriginal = "KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-OANUNOBY8"
    static let knicksOriginal = "KXNBAGAME-26JUN03NYKSAS-NYK"
    static let spursOriginal = "KXNBAGAME-26JUN03NYKSAS-SAS"
    static let champagnieTitle = "Will Julian Champagnie record more made three pointers than OG Anunoby?"
    static let anunobyTitle = "Will OG Anunoby record more made three pointers than Julian Champagnie?"

    static let unavailable = PlayerContributionReading10868.missing("Unavailable")
    static let noInGame = PlayerContributionReading10868.missing("No in-game reading")
    static let won = PlayerContributionResult10868.reached("Won")
    static let lost = PlayerContributionResult10868.missed("Lost")
    static let pending = PlayerContributionResult10868.unconfirmed("Result unconfirmed")
    static let countUnavailable = PlayerDuelActual10868.unavailable("Count unavailable")

    static func shots(_ made: Int, _ attempts: Int, detail: String = "final box score · ESPN") -> PlayerDuelActual10868 {
        .shots(PlayerDuelShots10868(made: made, attempts: attempts, figure: "\(made)", unit: "made",
                                    attemptsText: "\(attempts) attempts", accuracy: "50% from three",
                                    spoken: "\(made) made in \(attempts) attempts", accessibilityDetail: detail))
    }

    static func champagnie(actual: PlayerDuelActual10868 = shots(5, 10), result: PlayerContributionResult10868 = won,
                           current: PlayerContributionReading10868 = noInGame) -> PlayerDuelSide10868 {
        PlayerDuelSide10868(id: "4592479", originalID: champagnieOriginal, originalTitle: champagnieTitle,
                            name: "Julian Champagnie", team: "Spurs", pregame: unavailable, current: current,
                            actual: actual, result: result)
    }

    static func anunoby(actual: PlayerDuelActual10868 = shots(3, 6), result: PlayerContributionResult10868 = lost,
                        current: PlayerContributionReading10868 = noInGame) -> PlayerDuelSide10868 {
        PlayerDuelSide10868(id: "3934719", originalID: anunobyOriginal, originalTitle: anunobyTitle,
                            name: "OG Anunoby", team: "Knicks", pregame: unavailable, current: current,
                            actual: actual, result: result)
    }

    static func duel(_ phase: PlayerContributionPhase10868, sides: [PlayerDuelSide10868]? = nil,
                     selected: String? = nil) -> PlayerDuelInput10868 {
        PlayerDuelInput10868(
            phase: phase,
            eyebrow: "PLAYER HEAD-TO-HEAD · MADE THREES",
            title: phase == .final ? "Same accuracy.\nTwo more threes." : "Who makes more threes?",
            context: phase == .final ? "Knicks 105–95 Spurs · Final" : "Knicks vs Spurs · Before game",
            payoutRule: "A tie splits the payout. A separate win chance isn’t supplied.",
            sides: sides ?? [champagnie(), anunoby()],
            selectedOriginalID: selected)
    }

    // MARK: R4 — archived contract values, CONSTRUCTED words

    static func cents(_ original: String, _ fraction: Double, _ figure: String, _ minuteEnding: Int,
                      _ time: String) -> PlayerDuelValueObservation10868 {
        PlayerDuelValueObservation10868(originalID: original, observationID: "\(original)@\(minuteEnding)",
                                        fractionOfDollar: fraction, figure: figure, time: time,
                                        sourceWords: "Kalshi · traded minute close")
    }

    static func endpoint(_ label: String, _ observation: PlayerDuelValueObservation10868) -> PlayerDuelValueEndpoint10868 {
        PlayerDuelValueEndpoint10868(label: label, reading: .value(observation))
    }

    static let cBeforeFirst = cents(champagnieOriginal, 0.62, "62¢", 1780496520, "Jun 3, 7:22 AM")
    static let cPregame = cents(champagnieOriginal, 0.57, "57¢", 1780532940, "Jun 3, 5:29 PM")
    static let cLastTrade = cents(champagnieOriginal, 0.99, "99¢", 1780537500, "Jun 3, 6:45 PM")
    static let aBeforeFirst = cents(anunobyOriginal, 0.52, "52¢", 1780506360, "Jun 3, 10:06 AM")
    static let aPregame = cents(anunobyOriginal, 0.47, "47¢", 1780528980, "Jun 3, 4:23 PM")
    static let aLastTrade = cents(anunobyOriginal, 0.02, "2¢", 1780535280, "Jun 3, 6:08 PM")

    static func value(final isFinal: Bool, selected: String? = nil) -> PlayerDuelValueInput10868 {
        let rows = isFinal ? [
            PlayerDuelValueRow10868(playerID: "4592479", originalID: champagnieOriginal, originalTitle: champagnieTitle,
                                    name: "Julian Champagnie", earlier: endpoint("Pre-game", cPregame),
                                    later: endpoint("Last trade", cLastTrade), change: "+42¢"),
            PlayerDuelValueRow10868(playerID: "3934719", originalID: anunobyOriginal, originalTitle: anunobyTitle,
                                    name: "OG Anunoby", earlier: endpoint("Pre-game", aPregame),
                                    later: endpoint("Last trade", aLastTrade), change: "−45¢"),
        ] : [
            PlayerDuelValueRow10868(playerID: "4592479", originalID: champagnieOriginal, originalTitle: champagnieTitle,
                                    name: "Julian Champagnie", earlier: endpoint("First captured", cBeforeFirst),
                                    later: endpoint("Last before game", cPregame), change: "−5¢"),
            PlayerDuelValueRow10868(playerID: "3934719", originalID: anunobyOriginal, originalTitle: anunobyTitle,
                                    name: "OG Anunoby", earlier: endpoint("First captured", aBeforeFirst),
                                    later: endpoint("Last before game", aPregame), change: "−5¢"),
        ]
        return PlayerDuelValueInput10868(
            eyebrow: "MADE THREES · CONTRACT VALUES", title: "How the market moved",
            context: isFinal ? "Knicks 105–95 Spurs · Final" : "Knicks vs Spurs · Before game",
            quantity: "Value per $1 contract", tieRule: "A tie pays 50¢. This is not a win probability.",
            ticks: [PlayerDuelValueTick10868(fractionOfDollar: 0, text: "0¢"),
                    PlayerDuelValueTick10868(fractionOfDollar: 0.5, text: "50¢"),
                    PlayerDuelValueTick10868(fractionOfDollar: 1, text: "100¢")],
            rows: rows,
            phaseNote: isFinal ? "Last trade isn’t the final result. No values are filled in between these readings." : nil,
            selectedOriginalID: selected)
    }

    // MARK: R5 — mini anchor (CONSTRUCTED shape; no full-range credit)

    static func action(_ id: String, _ label: String, available: Bool = true) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: "\(label), constructed", isAvailable: available)
    }

    static let expandAction = action("constructed:expand", "Expand")
    static let ownerActionIDs = ["constructed:window.match", "constructed:window.all", "constructed:scale",
                                 "constructed:more", "constructed:details", "constructed:inspect",
                                 "constructed:previous", "constructed:next",
                                 "constructed:choose:\(knicksOriginal)", "constructed:choose:\(spursOriginal)"]

    static func winner(_ ticker: String, name: String, shape: FieldHistoryShape10868, tint: Color,
                       baseline: Double, baselineFigure: String, last: Double) -> FieldHistorySeries10868 {
        let before = "\(ticker)@1780532940", after = "\(ticker)@1780542960"
        return FieldHistorySeries10868(
            id: ticker, name: name, shape: shape, tint: tint,
            runs: [FieldHistoryRun10868(id: "\(ticker):run.before", points: [
                       FieldHistoryPoint10868(id: before, x: 1_780_532_940, probability: baseline, style: .hollow)]),
                   FieldHistoryRun10868(id: "\(ticker):run.after", points: [
                       FieldHistoryPoint10868(id: after, x: 1_780_542_960, probability: last, style: .filled)])],
            links: [],
            labelPointID: after,
            before: .observation(pointID: before, figure: baselineFigure,
                                 provenance: "Jun 3, 5:29 PM PT · last trade before listed start"),
            recorded: .absent(words: "No current probability after the final"),
            absentWords: "No captured trade",
            choose: action("constructed:choose:\(ticker)", name),
            keyContext: FieldHistoryKeyContext10868(label: "Before game", words: baselineFigure, spoken: nil))
    }

    /// Every defaulted `var` is set to a non-default value.
    static func anchor(expand: FieldHistoryAction10868? = expandAction) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: "Win probability",
            caption: "Kalshi minute closes",
            series: [winner(knicksOriginal, name: "Knicks", shape: .circle, tint: .blue,
                            baseline: 0.37, baselineFigure: "37%", last: 0.99),
                     winner(spursOriginal, name: "Spurs", shape: .diamond, tint: .teal,
                            baseline: 0.64, baselineFigure: "64%", last: 0.01)],
            selection: .series(id: knicksOriginal, missingWords: "Selected original unavailable"),
            domain: FieldHistoryDomain10868(lower: 1_780_529_400, upper: 1_780_542_960),
            ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0.5, lines: ["50%"])],
            xTicks: [FieldHistoryTick10868(value: 1_780_533_000, lines: ["Jun 3", "5:30 PM"])],
            guides: [FieldHistoryGuide10868(id: "constructed-guide:listed-start", x: 1_780_533_000, label: "Listed start")],
            breaks: [FieldHistoryBreak10868(id: "constructed-break", lower: 1_780_533_100, upper: 1_780_533_200, mark: "//")],
            readout: .beforeAndInspected(beforeLabel: "Before game", inspectedLabel: "Trade at selected minute"),
            markKey: FieldHistoryMarkKey10868(hollow: "Before the listed start", filled: "From the listed start"),
            comparisonExplanation: "Constructed comparison words",
            notes: ["Minute-ending Kalshi closes · Pacific time"],
            summary: "Knicks and Spurs game-winner trades (constructed summary)",
            plotHeight: 240,
            unboundReadingWords: "No trade at the selected minute",
            plotUnavailableWords: "Constructed unavailable words",
            windows: FieldHistoryWindows10868(groupLabel: "Window", choices: [
                FieldHistoryWindowChoice10868(action: action("constructed:window.match", "Around the game"), isSelected: true),
                FieldHistoryWindowChoice10868(action: action("constructed:window.all", "All captured trades"), isSelected: false),
            ]),
            scale: action("constructed:scale", "Full scale · 0–100%"),
            moreOriginals: action("constructed:more", "More originals"),
            details: action("constructed:details", "History & source details"),
            expand: expand,
            inspect: action("constructed:inspect", "Inspect history"),
            previous: action("constructed:previous", "Previous trade minute"),
            next: action("constructed:next", "Next trade minute"),
            inspection: FieldHistoryInspection10868(
                x: 1_780_542_960, caption: "Jun 3, 8:16 PM PT minute", selections: [:],
                choices: [FieldHistoryInspectionChoice10868(id: "constructed:minute:1780542960", lines: ["Jun 3", "8:16 PM"],
                                                            spoken: "Jun 3, 8:16 PM", isSelected: true)],
                choicePresentation: .buttons(groupLabel: "Trade minutes"), note: "Only exact captured minutes"),
            layout: .focused,
            probabilityLowerBound: 0.2,
            probabilityRangeExplanation: "Zoomed probability range · 20–100%",
            selectedReadout: FieldHistorySelectedReadout10868(beforeLabel: "Before game", inspectedLabel: "Trade at selected minute"),
            inspectionRingShape: .triangle,
            plotAbsence: FieldHistoryPlotAbsence10868(title: "Constructed absence", words: "Constructed absence words"),
            showsKey: false)
    }

    // MARK: Catalogue (CONSTRUCTED owner values over REAL tickers and R4/R5 values)

    static let scope = "constructed-owner-scope:player-duel"
    static let knicksIdentity = Details.Identity(source: "kalshi", market: "KXNBAGAME-26JUN03NYKSAS", side: knicksOriginal)
    static let champagnieIdentity = Details.Identity(source: "kalshi", market: "KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8",
                                                     side: champagnieOriginal)
    static let anunobyIdentity = Details.Identity(source: "kalshi", market: "KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8",
                                                  side: anunobyOriginal)
    static let noOutrightChance = "No outright win chance — a tie splits the payout"
    static let tieRules = Details.Rules.verified(["A Yes contract pays $1 if this player makes more, $0 if fewer, and 50¢ on a tie."])

    /// A genuine game-winner probability original: the owner's comparison,
    /// readings and placements (R5 37% → 99%).
    static let knicksWinner = Details.Original(
        identity: knicksIdentity, title: "Knicks vs Spurs · Game winner", outcome: "Knicks",
        mode: .comparison(.recorded),
        pregame: .value("37%", placement: 0.37, provenance: "Jun 3, 5:29 PM PT · last trade before listed start"),
        later: .value("99%", placement: 0.99, provenance: "Jun 3, 8:16 PM PT · Kalshi minute close"),
        grade: nil,
        about: Details.About(source: "Kalshi", rules: .omitted, provenance: [], historicalQuote: nil))

    /// A half-payout contract: explicit missing outright chance, no placement,
    /// no comparison, no historical quote; R4 values only in owner-labelled rows.
    static func tiePayout(_ identity: Details.Identity, title: String, outcome: String,
                          before: PlayerDuelValueObservation10868, last: PlayerDuelValueObservation10868,
                          grade: String) -> Details.Original {
        Details.Original(
            identity: identity, title: title, outcome: outcome,
            mode: .result,
            pregame: .missing(noOutrightChance),
            later: nil,
            grade: Details.Grade(words: grade, provenance: "Kalshi settlement (constructed words)"),
            about: Details.About(
                source: "Kalshi",
                rules: tieRules,
                provenance: [Details.Row(label: "Contract value before game", value: "\(before.figure) · \(before.time) PT"),
                             Details.Row(label: "Contract value at last trade", value: "\(last.figure) · \(last.time) PT")],
                historicalQuote: nil))
    }

    static let champagnieContract = tiePayout(champagnieIdentity, title: champagnieTitle, outcome: "Yes",
                                              before: cPregame, last: cLastTrade, grade: "Resolved Yes")
    static let anunobyContract = tiePayout(anunobyIdentity, title: anunobyTitle, outcome: "Yes",
                                           before: aPregame, last: aLastTrade, grade: "Resolved No")

    static func catalogue(_ originals: [Details.Original] = [knicksWinner, champagnieContract, anunobyContract]) -> Details.Catalogue {
        Details.Catalogue(scope: scope, originals: originals)
    }

    static let routes: [String: Details.Identity] = [champagnieOriginal: champagnieIdentity,
                                                    anunobyOriginal: anunobyIdentity]

    // MARK: Bundles (CONSTRUCTED identity-mechanics controls)

    static let header = PlayerDuelPageHeader10868(eyebrow: "NBA · GAME 1 · JUN 3", title: "Knicks 105–95 Spurs",
                                                  state: "Knicks won · Final", quality: nil,
                                                  aboutLabel: "About this game and threes duel")
    static let cards = PlayerDuelPageCardWords10868(streamHeading: "PLAYER PROPS", streamEyebrow: nil,
                                                    historyName: "Game win probability", duelName: "Threes head-to-head",
                                                    valueName: "Market value history", valueLink: "Market history & tie terms")
    static let catalogueWords = PlayerDuelPageCatalogueWords10868(heading: "All props in this capture", context: "3 markets",
                                                                  emptyWords: "No original markets in this capture",
                                                                  unavailableChoice: "Unnamed original")
    static let about = PlayerDuelPageAbout10868(title: "Win chances and tie payouts",
                                                paragraphs: ["Constructed About words."])

    static func supplied(eventID: Int, phase: HockeyJourneyPagePhase10868,
                         anchor: FieldHistoryInput10868? = Self.anchor(),
                         duel: PlayerDuelInput10868?, value: PlayerDuelValueInput10868?,
                         catalogue: Details.Catalogue? = Self.catalogue(),
                         routes: [String: Details.Identity] = Self.routes) -> A.Supplied {
        A.Supplied(eventID: eventID, phase: phase, header: header, anchor: anchor, duel: duel, value: value,
                   cards: cards, about: about, catalogue: catalogue,
                   catalogueLabels: [knicksIdentity: "Knicks to win"],
                   catalogueWords: catalogueWords, routes: routes)
    }

    /// The final bundle on R1 (15169793).
    static func finalSupplied(duel: PlayerDuelInput10868? = Self.duel(.final),
                              value: PlayerDuelValueInput10868? = Self.value(final: true),
                              catalogue: Details.Catalogue? = Self.catalogue(),
                              routes: [String: Details.Identity] = Self.routes) -> A.Supplied {
        supplied(eventID: 15_169_793, phase: .final, duel: duel, value: value, catalogue: catalogue, routes: routes)
    }

    /// Records holds, opens and owner calls in order.
    final class Spy {
        var events: [String] = []
        func hold() { events.append("hold") }
        func open() { events.append("open") }
        func owner(_ id: String) { events.append("owner:\(id)") }
        func choice(_ id: String) { events.append("choice:\(id)") }
        func plot(_ x: Double) { events.append("plot:\(x)") }
        func selected(_ selection: OriginalMarketDetails9483.Selection) {
            events.append("details:\(selection.scope)|\(selection.identity.side)")
        }
    }

    static func controls(_ spy: Spy, action: Bool = true, inspection: Bool = true,
                         plot: Bool = true) -> A.AnchorControls {
        A.AnchorControls(onAction: action ? { spy.owner($0) } : nil,
                         onInspectionChoice: inspection ? { spy.choice($0) } : nil,
                         onPlotPosition: plot ? { spy.plot($0) } : nil)
    }
}

@MainActor
final class PlayerDuelEventPageHostAdapter10868Tests: XCTestCase {
    private typealias F = PlayerDuelEventPageFixtures10868
    private typealias A = PlayerDuelEventPageAdapter10868
    private typealias Details = OriginalMarketDetails9483
    private typealias Model = PlayerDuelPageModel10868

    private func finalInput(held: A.Held = A.Held(), supplied: A.Supplied? = nil) throws -> PlayerDuelPageInput10868 {
        let event = try F.finalEvent()
        guard let input = A.build(event: event, supplied: supplied ?? F.finalSupplied(), now: F.now, held: held) else {
            XCTFail("CONSTRUCTED final bundle on R1 should be admitted")
            throw XCTSkip("not admitted")
        }
        return input
    }

    // MARK: PD3 — held presentation and admission fences

    func testNoSuppliedBundleIsAHeldPresentationThatDrawsNothing() throws {
        let event = try F.finalEvent()
        XCTAssertNil(A.build(event: event, supplied: nil, now: F.now))
        XCTAssertFalse(PlayerDuelEventPageHost10868.applies(event, supplied: nil, now: F.now))
    }

    func testABundleForAnotherEventIsNoBundle() throws {
        // CONSTRUCTED: the bundle names 15338034, the page is 15169793.
        let event = try F.finalEvent()
        let foreign = F.supplied(eventID: 15_338_034, phase: .final, duel: F.duel(.final), value: F.value(final: true))
        XCTAssertNil(A.admit(foreign, event: event, now: F.now))
        XCTAssertNil(A.build(event: event, supplied: foreign, now: F.now))
        XCTAssertFalse(PlayerDuelEventPageHost10868.applies(event, supplied: foreign, now: F.now))
        XCTAssertNil(A.detailsSelection(F.champagnieOriginal, supplied: A.admit(foreign, event: event, now: F.now)))
    }

    func testABundleForAnotherPhaseIsNoBundleSoNoFinalOrGradeLeaksEarlier() throws {
        let before = try F.beforeEvent(), finished = try F.finalEvent()
        // A final bundle (results, grades, final counts) on a before page.
        let finalOnBefore = F.supplied(eventID: 15_338_496, phase: .final, duel: F.duel(.final), value: F.value(final: true))
        XCTAssertNil(A.build(event: before, supplied: finalOnBefore, now: F.now))
        // A before bundle on a final page.
        let beforeOnFinal = F.supplied(eventID: 15_169_793, phase: .before, duel: F.duel(.before), value: F.value(final: false))
        XCTAssertNil(A.build(event: finished, supplied: beforeOnFinal, now: F.now))
        // The matching phases are admitted.
        XCTAssertNotNil(A.build(event: before, supplied: F.supplied(eventID: 15_338_496, phase: .before,
                                                                    duel: F.duel(.before), value: F.value(final: false)),
                                now: F.now))
        XCTAssertNotNil(A.build(event: finished, supplied: F.finalSupplied(), now: F.now))
    }

    func testABundleWhoseDuelIsForAnotherPhaseIsNoBundle() throws {
        let event = try F.finalEvent()
        XCTAssertNil(A.build(event: event, supplied: F.finalSupplied(duel: F.duel(.before)), now: F.now))
        XCTAssertNil(A.build(event: event, supplied: F.finalSupplied(duel: F.duel(.during)), now: F.now))
    }

    // MARK: Pass-through

    func testEveryOwnerValuePassesThroughUnchanged() throws {
        let supplied = F.finalSupplied()
        let input = try finalInput(supplied: supplied)
        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(input.header, supplied.header)
        XCTAssertEqual(input.anchor, supplied.anchor)
        XCTAssertTrue(input.anchorIsOwners)
        XCTAssertEqual(input.duel, supplied.duel)
        XCTAssertEqual(input.value, supplied.value)
        XCTAssertEqual(input.cards, supplied.cards)
        XCTAssertEqual(input.about, supplied.about)
        XCTAssertEqual(input.catalogue, supplied.catalogue)
        XCTAssertEqual(input.catalogueLabels, supplied.catalogueLabels)
        XCTAssertEqual(input.catalogueWords, supplied.catalogueWords)
        // Every owner original, in the owner's order; the scope is the owner's string.
        XCTAssertEqual(input.catalogue?.originals.map(\.identity), [F.knicksIdentity, F.champagnieIdentity, F.anunobyIdentity])
        XCTAssertEqual(input.catalogue?.scope, F.scope)
    }

    func testAMissingAnchorIsTheExistingUnavailableSlotNeverABlend() throws {
        let event = try F.finalEvent()
        let supplied = F.supplied(eventID: 15_169_793, phase: .final, anchor: nil,
                                  duel: F.duel(.final), value: F.value(final: true))
        let input = try XCTUnwrap(A.build(event: event, supplied: supplied, now: F.now))
        XCTAssertFalse(input.anchorIsOwners)
        XCTAssertEqual(input.anchor, HockeyJourneyHistoryAdapter10868.unavailable(event: event, phase: .final))
    }

    // MARK: PD2 — chart forwarding

    func testEveryOwnerActionIsForwardedExactlyOnceAfterTheHold() throws {
        let input = try finalInput()
        let spy = F.Spy()
        let display = A.anchorDisplay(input, reader: false, controls: F.controls(spy),
                                      hold: { spy.hold() }, openHistory: { spy.open() })
        XCTAssertEqual(display.input, input.anchor, "with an owner handler the owner's input is drawn unchanged")
        let onAction = try XCTUnwrap(display.onAction)
        let ids = FieldHistoryGeometry10868.actions(display.input).map(\.id).filter { $0 != F.expandAction.id }
        XCTAssertEqual(Set(ids), Set(F.ownerActionIDs))
        for id in ids {
            spy.events = []
            onAction(id)
            XCTAssertEqual(spy.events, ["hold", "owner:\(id)"], id)
        }
    }

    func testExpandOpensTheHistoryReaderLocallyAndNeverReachesTheOwner() throws {
        let input = try finalInput()
        let spy = F.Spy()
        let display = A.anchorDisplay(input, reader: false, controls: F.controls(spy),
                                      hold: { spy.hold() }, openHistory: { spy.open() })
        try XCTUnwrap(display.onAction)(F.expandAction.id)
        XCTAssertEqual(spy.events, ["hold", "open"])
    }

    func testAnIdTheInputDoesNotNameStillReachesTheOwnerNeverSwallowed() throws {
        let input = try finalInput()
        let spy = F.Spy()
        let display = A.anchorDisplay(input, reader: false, controls: F.controls(spy),
                                      hold: { spy.hold() }, openHistory: { spy.open() })
        try XCTUnwrap(display.onAction)("constructed:unknown")
        XCTAssertEqual(spy.events, ["hold", "owner:constructed:unknown"])
    }

    func testWithoutAnOwnerHandlerExpandWorksAndEveryOtherActionIsDisabled() throws {
        let input = try finalInput()
        let spy = F.Spy()
        let display = A.anchorDisplay(input, reader: false, controls: nil,
                                      hold: { spy.hold() }, openHistory: { spy.open() })
        let onAction = try XCTUnwrap(display.onAction, "a real, working, page-owned expand")
        XCTAssertNil(display.onInspectionChoice)
        XCTAssertNil(display.onPlotPosition)
        for action in FieldHistoryGeometry10868.actions(display.input) {
            if action.id == F.expandAction.id {
                XCTAssertTrue(action.isAvailable)
                XCTAssertEqual(FieldHistoryGeometry10868.controlState(action, informative: false, hasCallback: true,
                                                                      in: display.input), .live(id: action.id))
            } else {
                XCTAssertFalse(action.isAvailable, "\(action.id) must be drawn disabled, never an enabled no-op")
            }
        }
        // VoiceOver adjustment requires an available action.
        XCTAssertNil(FieldHistoryGeometry10868.adjustableID(display.input.previous, hasCallback: true, in: display.input))
        XCTAssertNil(FieldHistoryGeometry10868.adjustableID(display.input.next, hasCallback: true, in: display.input))
        onAction(F.expandAction.id)
        XCTAssertEqual(spy.events, ["hold", "open"])
        spy.events = []
        for id in F.ownerActionIDs { onAction(id) }
        XCTAssertEqual(spy.events, [], "the guard behind disabled controls holds and opens nothing")
    }

    func testWithoutAnOwnerHandlerOrAnExpandThereIsNoActionCallback() throws {
        let event = try F.finalEvent()
        let supplied = F.supplied(eventID: 15_169_793, phase: .final, anchor: F.anchor(expand: nil),
                                  duel: F.duel(.final), value: F.value(final: true))
        let input = try XCTUnwrap(A.build(event: event, supplied: supplied, now: F.now))
        let display = A.anchorDisplay(input, reader: false, controls: nil, hold: nil, openHistory: {})
        XCTAssertNil(display.onAction)
        XCTAssertEqual(display.input, input.anchor)
    }

    func testTheReaderOffersNoExpandAndForwardsEveryOwnerActionOnce() throws {
        let input = try finalInput()
        let spy = F.Spy()
        let display = A.anchorDisplay(input, reader: true, controls: F.controls(spy),
                                      hold: { spy.hold() }, openHistory: { spy.open() })
        XCTAssertNil(display.input.expand)
        XCTAssertEqual(display.input, Model.readerAnchor(input.anchor))
        let onAction = try XCTUnwrap(display.onAction)
        let ids = FieldHistoryGeometry10868.actions(display.input).map(\.id)
        XCTAssertEqual(Set(ids), Set(F.ownerActionIDs))
        for id in ids {
            spy.events = []
            onAction(id)
            XCTAssertEqual(spy.events, ["hold", "owner:\(id)"], id)
        }
        // Without an owner handler the reader has nothing it can act on.
        XCTAssertNil(A.anchorDisplay(input, reader: true, controls: nil, hold: nil, openHistory: {}).onAction)
    }

    func testInspectionAndPlotAreForwardedOnlyWhenTheOwnerSuppliesThem() throws {
        let input = try finalInput()
        let spy = F.Spy()
        let display = A.anchorDisplay(input, reader: false, controls: F.controls(spy),
                                      hold: { spy.hold() }, openHistory: { spy.open() })
        try XCTUnwrap(display.onInspectionChoice)("constructed:minute:1780542960")
        XCTAssertEqual(spy.events, ["hold", "choice:constructed:minute:1780542960"])
        spy.events = []
        try XCTUnwrap(display.onPlotPosition)(1_780_542_960)
        XCTAssertEqual(spy.events, ["hold", "plot:\(1_780_542_960.0)"])
        let none = A.anchorDisplay(input, reader: false, controls: F.controls(spy, action: true, inspection: false, plot: false),
                                   hold: nil, openHistory: {})
        XCTAssertNil(none.onInspectionChoice)
        XCTAssertNil(none.onPlotPosition)
    }

    func testOwnerChartHandlersNeverReachTheUnavailableSlot() throws {
        let event = try F.finalEvent()
        let supplied = F.supplied(eventID: 15_169_793, phase: .final, anchor: nil,
                                  duel: F.duel(.final), value: F.value(final: true))
        let input = try XCTUnwrap(A.build(event: event, supplied: supplied, now: F.now))
        let spy = F.Spy()
        let display = A.anchorDisplay(input, reader: false, controls: F.controls(spy), hold: nil, openHistory: {})
        XCTAssertNil(display.onAction)
        XCTAssertNil(display.onInspectionChoice)
        XCTAssertNil(display.onPlotPosition)
    }

    func testThePlayerSelectionLeavesTheOwnersAnchorUntouched() throws {
        let plain = try finalInput()
        let held = try finalInput(held: A.Held(selectedOriginalID: F.anunobyOriginal))
        XCTAssertEqual(held.anchor, plain.anchor)
        XCTAssertEqual(held.anchor, F.anchor())
    }

    // MARK: Held original selection

    func testTheHeldOriginalReachesBothLeavesExactlyAndNeverSubstitutes() throws {
        let held = try finalInput(held: A.Held(selectedOriginalID: F.champagnieOriginal))
        XCTAssertEqual(held.duel?.selection.side?.originalID, F.champagnieOriginal)
        XCTAssertEqual(held.value?.selection.row?.originalID, F.champagnieOriginal)
        // A game-winner original is no player's: nobody is selected, nobody substitutes.
        let foreign = try finalInput(held: A.Held(selectedOriginalID: F.knicksOriginal))
        XCTAssertEqual(foreign.duel?.selection, .missing(F.knicksOriginal))
        XCTAssertNil(foreign.value?.selection.row)
        // No held id keeps the owner's own selection.
        let owner = try finalInput(supplied: F.finalSupplied(duel: F.duel(.final, selected: F.anunobyOriginal),
                                                            value: F.value(final: true, selected: F.anunobyOriginal)))
        XCTAssertEqual(owner.duel?.selection.side?.originalID, F.anunobyOriginal)
        XCTAssertEqual(owner.value?.selection.row?.originalID, F.anunobyOriginal)
    }

    // MARK: Details identity

    func testDetailsOpenTheExactCatalogueOriginalForEachLeafsCurrentSelection() throws {
        let supplied = F.finalSupplied()
        let input = try finalInput(held: A.Held(selectedOriginalID: F.champagnieOriginal), supplied: supplied)
        let spy = F.Spy()
        let duel = try XCTUnwrap(A.detailsCallback(input.duel?.selection.side?.originalID, supplied: supplied,
                                                   hold: { spy.hold() }, open: { spy.selected($0) }))
        duel(F.champagnieOriginal)
        XCTAssertEqual(spy.events, ["hold", "details:\(F.scope)|\(F.champagnieOriginal)"])
        spy.events = []
        let value = try XCTUnwrap(A.detailsCallback(input.value?.selection.row?.originalID, supplied: supplied,
                                                    hold: { spy.hold() }, open: { spy.selected($0) }))
        value(F.champagnieOriginal)
        XCTAssertEqual(spy.events, ["hold", "details:\(F.scope)|\(F.champagnieOriginal)"])
        XCTAssertEqual(A.detailsSelection(F.champagnieOriginal, supplied: supplied),
                       Details.Selection(scope: F.scope, identity: F.champagnieIdentity))
    }

    func testDetailsAreDecidedAgainWhenTheSelectionChanges() throws {
        // CONSTRUCTED: the owner proved a route for Champagnie only.
        let supplied = F.finalSupplied(routes: [F.champagnieOriginal: F.champagnieIdentity])
        let first = try finalInput(held: A.Held(selectedOriginalID: F.champagnieOriginal), supplied: supplied)
        XCTAssertNotNil(A.detailsCallback(first.duel?.selection.side?.originalID, supplied: supplied, hold: nil, open: { _ in }))
        XCTAssertNotNil(A.detailsCallback(first.value?.selection.row?.originalID, supplied: supplied, hold: nil, open: { _ in }))
        let second = try finalInput(held: A.Held(selectedOriginalID: F.anunobyOriginal), supplied: supplied)
        XCTAssertNil(A.detailsCallback(second.duel?.selection.side?.originalID, supplied: supplied, hold: nil, open: { _ in }))
        XCTAssertNil(A.detailsCallback(second.value?.selection.row?.originalID, supplied: supplied, hold: nil, open: { _ in }))
        // With Anunoby's route proved, the same change opens Anunoby, never Champagnie.
        let both = F.finalSupplied()
        let third = try finalInput(held: A.Held(selectedOriginalID: F.anunobyOriginal), supplied: both)
        let spy = F.Spy()
        try XCTUnwrap(A.detailsCallback(third.duel?.selection.side?.originalID, supplied: both,
                                        hold: nil, open: { spy.selected($0) }))(F.anunobyOriginal)
        XCTAssertEqual(spy.events, ["details:\(F.scope)|\(F.anunobyOriginal)"])
    }

    func testMissingDuplicateForeignAndWithdrawnIdentitiesOfferNoDetails() throws {
        let supplied = F.finalSupplied()
        // No selection at all.
        let none = try finalInput(supplied: supplied)
        XCTAssertNil(A.detailsCallback(none.duel?.selection.side?.originalID, supplied: supplied, hold: nil, open: { _ in }))
        // A foreign id (the game-winner original) selects no player.
        let foreign = try finalInput(held: A.Held(selectedOriginalID: F.knicksOriginal), supplied: supplied)
        XCTAssertNil(A.detailsCallback(foreign.duel?.selection.side?.originalID, supplied: supplied, hold: nil, open: { _ in }))
        // CONSTRUCTED: a route to an identity the catalogue does not hold.
        let absent = F.finalSupplied(catalogue: F.catalogue([F.knicksWinner, F.champagnieContract]))
        XCTAssertNil(A.detailsSelection(F.anunobyOriginal, supplied: absent))
        // CONSTRUCTED: the catalogue holds the routed identity twice.
        let duplicated = F.finalSupplied(catalogue: F.catalogue([F.knicksWinner, F.champagnieContract, F.champagnieContract]))
        XCTAssertNil(A.detailsSelection(F.champagnieOriginal, supplied: duplicated))
        // No catalogue.
        XCTAssertNil(A.detailsSelection(F.champagnieOriginal, supplied: F.finalSupplied(catalogue: nil)))
        // CONSTRUCTED: Anunoby withdrawn from the duel; his held id moves to nobody.
        let withdrawn = F.finalSupplied(duel: F.duel(.final, sides: [F.champagnie()]))
        let held = try finalInput(held: A.Held(selectedOriginalID: F.anunobyOriginal), supplied: withdrawn)
        XCTAssertEqual(held.duel?.selection, .missing(F.anunobyOriginal))
        XCTAssertNil(A.detailsCallback(held.duel?.selection.side?.originalID, supplied: withdrawn, hold: nil, open: { _ in }))
    }

    // MARK: Mixed catalogue — SOURCE-CONTRACT test, not runtime or real-data acceptance

    func testAMixedCatalogueKeepsEachOriginalsSuppliedModeUnitsAndMarks() throws {
        // CONSTRUCTED parent bundle; REAL tickers, R5 probabilities and R4 cents.
        let supplied = F.finalSupplied()
        let input = try finalInput(supplied: supplied)
        XCTAssertEqual(input.catalogue, supplied.catalogue)
        let cards = OriginalMarketCatalogue9483.cards(catalogue: input.catalogue, selection: nil,
                                                      labels: input.catalogueLabels, unavailableChoice: "Unnamed original")
        XCTAssertEqual(cards.map(\.choice.selection?.identity), [F.knicksIdentity, F.champagnieIdentity, F.anunobyIdentity],
                       "every original stays reachable")

        // The genuine probability original keeps its comparison, readings and marks.
        let knicks = try XCTUnwrap(Details.content(catalogue: input.catalogue,
                                                   selection: Details.Selection(scope: F.scope, identity: F.knicksIdentity)))
        XCTAssertEqual(knicks.readings.map(\.label), [Details.pregameLabel, Details.Later.recorded.label])
        XCTAssertEqual(knicks.readings.map(\.text), ["37%", "99%"])
        XCTAssertEqual(knicks.marks.map(\.placement), [0.37, 0.99])

        // The half-payout contract keeps its missing outright chance, no mark, and its owner-labelled value rows.
        let champagnie = try XCTUnwrap(Details.content(catalogue: input.catalogue,
                                                       selection: try XCTUnwrap(A.detailsSelection(F.champagnieOriginal, supplied: supplied))))
        XCTAssertEqual(champagnie.readings.map(\.text), [F.noOutrightChance])
        XCTAssertEqual(champagnie.readings.map(\.isValue), [false])
        XCTAssertTrue(champagnie.marks.isEmpty)
        XCTAssertEqual(champagnie.result?.words, "Resolved Yes")
        XCTAssertTrue(champagnie.about.contains(Details.Row(label: "Contract value before game", value: "57¢ · Jun 3, 5:29 PM PT")))
        XCTAssertTrue(champagnie.about.contains(Details.Row(label: "Contract value at last trade", value: "99¢ · Jun 3, 6:45 PM PT")))
        XCTAssertEqual(champagnie.rules, F.tieRules)
        let anunoby = try XCTUnwrap(Details.content(catalogue: input.catalogue,
                                                    selection: try XCTUnwrap(A.detailsSelection(F.anunobyOriginal, supplied: supplied))))
        XCTAssertEqual(anunoby.result?.words, "Resolved No")
        XCTAssertTrue(anunoby.about.contains(Details.Row(label: "Contract value at last trade", value: "2¢ · Jun 3, 6:08 PM PT")))
    }

    func testCentsNeverReachAProbabilityMarkOrLabel() throws {
        let supplied = F.finalSupplied()
        let input = try finalInput(supplied: supplied)
        for original in [F.champagnieOriginal, F.anunobyOriginal] {
            let content = try XCTUnwrap(Details.content(catalogue: input.catalogue,
                                                        selection: try XCTUnwrap(A.detailsSelection(original, supplied: supplied))))
            XCTAssertFalse(content.readings.contains { $0.text.contains("¢") }, original)
            XCTAssertTrue(content.marks.isEmpty, original)
            XCTAssertFalse(content.about.contains { $0.label == Details.historicalLabel }, original)
        }
        // The duel's outright chances stay words; the value card keeps its cents in its own DTO, unchanged.
        XCTAssertEqual(input.duel?.sides.map(\.pregame), [F.unavailable, F.unavailable])
        XCTAssertEqual(input.value, F.value(final: true))
        XCTAssertEqual(input.value?.rows.map(\.change), ["+42¢", "−45¢"])
    }

    // MARK: Stories and phases

    func testTheStreamOffersOnlyThePairedDuelAndNeverTheValueCard() throws {
        let input = try finalInput()
        XCTAssertTrue(input.duelOffered)
        XCTAssertEqual(input.stream.cards.map(\.id), [PlayerDuelPageCard10868.duel.rawValue])
        XCTAssertEqual(input.stream.primary?.id, PlayerDuelPageCard10868.duel.rawValue)
        XCTAssertEqual(Model(input).readerCards, [.history, .duel, .value])
        let noValue = try finalInput(supplied: F.finalSupplied(value: nil))
        XCTAssertEqual(Model(noValue).readerCards, [.history, .duel])
        // CONSTRUCTED: an incomplete pair is not offered.
        let single = try finalInput(supplied: F.finalSupplied(duel: F.duel(.final, sides: [F.champagnie()])))
        XCTAssertFalse(single.duelOffered)
        XCTAssertTrue(single.stream.cards.isEmpty)
    }

    func testBeforeOffersThePairedDuelAndShowsNoCountOrResult() throws {
        let event = try F.beforeEvent()
        let input = try XCTUnwrap(A.build(event: event, supplied: F.supplied(eventID: 15_338_496, phase: .before,
                                                                             duel: F.duel(.before), value: F.value(final: false)),
                                          now: F.now))
        XCTAssertTrue(input.duelOffered)
        let duel = try XCTUnwrap(input.duel)
        for side in duel.sides {
            XCTAssertNil(duel.actualPresentation(side))
            XCTAssertNil(duel.result(side))
            XCTAssertNil(duel.current(side))
            XCTAssertEqual(duel.pregame(side), .words("Unavailable"))
        }
    }

    func testLiveCountsStayUnavailableUnlessSuppliedAndTheHostFillsNothing() throws {
        // CONSTRUCTED live status and live sides; no live specimen is retained.
        let event = try F.liveEvent()
        let unsupplied = F.duel(.during, sides: [F.champagnie(actual: F.countUnavailable, result: F.pending),
                                                 F.anunoby(actual: F.countUnavailable, result: F.pending)])
        let input = try XCTUnwrap(A.build(event: event, supplied: F.supplied(eventID: 15_338_496, phase: .live,
                                                                             duel: unsupplied, value: nil),
                                          now: F.now))
        XCTAssertEqual(input.duel, unsupplied, "the host supplies no count of its own")
        XCTAssertFalse(input.duelOffered)
        XCTAssertTrue(input.stream.cards.isEmpty)
        XCTAssertEqual(Model(input).readerCards, [.history])
        // Separately supplied counts so far (CONSTRUCTED) make the pair offerable.
        let counted = F.duel(.during, sides: [F.champagnie(actual: F.shots(2, 4, detail: "count so far · constructed"), result: F.pending),
                                               F.anunoby(actual: F.shots(1, 3, detail: "count so far · constructed"), result: F.pending)])
        let live = try XCTUnwrap(A.build(event: event, supplied: F.supplied(eventID: 15_338_496, phase: .live,
                                                                            duel: counted, value: nil),
                                         now: F.now))
        XCTAssertTrue(live.duelOffered)
        let duel = try XCTUnwrap(live.duel)
        for side in duel.sides {
            XCTAssertNil(duel.result(side), "no grade during play")
            XCTAssertEqual(duel.current(side), .words("No in-game reading"))
        }
    }

    func testFinalResultsStayIndependentOfTheCounts() throws {
        // CONSTRUCTED: Anunoby's result unconfirmed though his count is known.
        let input = try finalInput(supplied: F.finalSupplied(duel: F.duel(.final, sides: [F.champagnie(), F.anunoby(result: F.pending)])))
        let duel = try XCTUnwrap(input.duel)
        XCTAssertEqual(duel.sides.map { duel.result($0) }, [F.won, F.pending])
        XCTAssertEqual(duel.sides.map { duel.marks($0)?.filter { $0 }.count }, [5, 3])
        XCTAssertEqual(duel.sides.map { duel.marks($0)?.count }, [10, 6])
    }

    func testStreamIntentsRouteOnlyTheDuelInItsOwnScope() throws {
        let input = try finalInput()
        let scope = input.stream.scope
        let duel = StoryStreamPresentation10868.CardRef(scope: scope, id: PlayerDuelPageCard10868.duel.rawValue)
        XCTAssertEqual(A.route(.open(duel), scope: scope), .openReader(.duel))
        XCTAssertEqual(A.route(.interaction(scope: scope, card: duel), scope: scope), .hold)
        XCTAssertEqual(A.route(.open(StoryStreamPresentation10868.CardRef(scope: "constructed-foreign", id: duel.id)), scope: scope), .ignore)
        XCTAssertEqual(A.route(.open(StoryStreamPresentation10868.CardRef(scope: scope, id: "value")), scope: scope), .ignore)
        XCTAssertEqual(A.route(.browse(.next, to: duel), scope: scope), .ignore)
    }

    // MARK: PD4 — return context, driven through the real callbacks

    func testDetailsDoneFromTheDuelReaderRestoresThatReaderAndTheExactOriginal() throws {
        var session = A.Session()
        session.openReader(.duel)
        session.select(F.champagnieOriginal)
        let supplied = F.finalSupplied()
        let input = try finalInput(held: A.Held(selectedOriginalID: session.selectedOriginalID, readerOpen: session.isPresented),
                                   supplied: supplied)
        let details = try XCTUnwrap(A.detailsCallback(input.duel?.selection.side?.originalID, supplied: supplied,
                                                      hold: nil, open: { session.openDetails($0) }))
        details(F.champagnieOriginal)
        XCTAssertEqual(session.mode, .original)
        XCTAssertEqual(session.reader, .duel, "the card stays behind Details")
        let opened = Details.Selection(scope: F.scope, identity: F.champagnieIdentity)
        XCTAssertEqual(session.catalogueSelection, opened)
        session.close()
        XCTAssertEqual(session.mode, .reader(.duel), "Done returns to the same card")
        XCTAssertEqual(session.catalogueSelection, opened)
        XCTAssertEqual(session.selectedOriginalID, F.champagnieOriginal)
        XCTAssertEqual(Model.closeLabel(.reader(.duel)), "Back to game")
        session.close()
        XCTAssertNil(session.mode, "Back to game returns to the page")
        XCTAssertEqual(session.selectedOriginalID, F.champagnieOriginal)
    }

    func testDetailsDoneFromTheValueReaderRestoresTheValueReader() throws {
        var session = A.Session()
        session.openReader(.value)
        session.select(F.anunobyOriginal)
        let supplied = F.finalSupplied()
        let input = try finalInput(held: A.Held(selectedOriginalID: session.selectedOriginalID), supplied: supplied)
        try XCTUnwrap(A.detailsCallback(input.value?.selection.row?.originalID, supplied: supplied,
                                        hold: nil, open: { session.openDetails($0) }))(F.anunobyOriginal)
        XCTAssertEqual(session.mode, .original)
        XCTAssertEqual(Model.closeLabel(.original), "Done")
        session.close()
        XCTAssertEqual(session.mode, .reader(.value))
        XCTAssertEqual(session.catalogueSelection, Details.Selection(scope: F.scope, identity: F.anunobyIdentity))
        session.close()
        XCTAssertNil(session.mode)
    }

    func testAboutDoneFromTheHistoryReaderRestoresTheHistoryReader() throws {
        var session = A.Session()
        let input = try finalInput()
        // The page-owned expand opens the history reader through the real routed callback.
        let display = A.anchorDisplay(input, reader: false, controls: nil, hold: nil,
                                      openHistory: { session.openReader(.history) })
        try XCTUnwrap(display.onAction)(F.expandAction.id)
        XCTAssertEqual(session.mode, .reader(.history))
        XCTAssertTrue(Model(input).aboutEntry(mode: .reader(.history), canOpen: true))
        session.openAbout()
        XCTAssertEqual(session.mode, .about)
        session.close()
        XCTAssertEqual(session.mode, .reader(.history), "Done returns to the history reader")
        session.close()
        XCTAssertNil(session.mode)
    }

    func testDetailsAndAboutDoneFromThePageCloseToThePage() {
        var session = A.Session()
        session.openDetails(Details.Selection(scope: F.scope, identity: F.knicksIdentity))
        XCTAssertEqual(session.mode, .original)
        session.close()
        XCTAssertNil(session.mode)
        XCTAssertEqual(session.catalogueSelection, Details.Selection(scope: F.scope, identity: F.knicksIdentity))
        session.openAbout()
        XCTAssertEqual(session.mode, .about)
        session.close()
        XCTAssertNil(session.mode)
    }

    func testThePagerMovesBetweenReadersAndBackToGameClosesTheReader() throws {
        let input = try finalInput()
        var session = A.Session()
        session.openReader(.duel)
        let around = Model(input).neighbours(.duel)
        XCTAssertEqual(around.previous, .history)
        XCTAssertEqual(around.next, .value)
        session.openReader(try XCTUnwrap(around.next))
        XCTAssertEqual(session.mode, .reader(.value))
        session.close()
        XCTAssertNil(session.mode)
    }

    func testInteractiveDismissalReturnsToThePageAndKeepsTheChoices() {
        var session = A.Session()
        session.openReader(.duel)
        session.select(F.champagnieOriginal)
        session.openDetails(Details.Selection(scope: F.scope, identity: F.champagnieIdentity))
        session.dismiss()
        XCTAssertNil(session.mode)
        XCTAssertEqual(session.selectedOriginalID, F.champagnieOriginal)
        XCTAssertEqual(session.catalogueSelection, Details.Selection(scope: F.scope, identity: F.champagnieIdentity))
    }

    /// The host's sheet binding calls `dismiss()` on the native swipe-down and
    /// its toolbar calls `close()`; no custom swipe interceptor exists.
    func testSwipeDownDismissesTheWholeSheetButDoneUnwindsOneLayer() {
        var nested = A.Session()
        nested.openReader(.value)
        nested.select(F.champagnieOriginal)
        let opened = Details.Selection(scope: F.scope, identity: F.champagnieIdentity)
        nested.openDetails(opened)
        var done = nested, swiped = nested
        done.close()
        XCTAssertEqual(done.mode, .reader(.value), "Done on nested Details restores the same reader")
        swiped.dismiss()
        XCTAssertNil(swiped.mode, "swipe-down returns to the game")
        XCTAssertNil(swiped.reader)
        XCTAssertEqual(swiped.selectedOriginalID, F.champagnieOriginal, "the reader's choices are kept")
        XCTAssertEqual(swiped.catalogueSelection, opened)
        // The same distinction over nested About on the history reader.
        var about = A.Session()
        about.openReader(.history)
        about.openAbout()
        var aboutSwiped = about
        about.close()
        XCTAssertEqual(about.mode, .reader(.history))
        aboutSwiped.dismiss()
        XCTAssertNil(aboutSwiped.mode)
    }

    // MARK: PD5 — withdrawal inside an open reader (CONSTRUCTED changed input)

    func testAWithdrawnValueCardShowsItsOwnUnavailableReadingThenBack() throws {
        var session = A.Session()
        session.openReader(.value)
        session.select(F.champagnieOriginal)
        let before = try finalInput(held: A.Held(selectedOriginalID: session.selectedOriginalID))
        XCTAssertEqual(Model(before).readerContent(.value), .card(.value))
        // The owner withdraws the value input.
        let after = try finalInput(held: A.Held(selectedOriginalID: session.selectedOriginalID),
                                   supplied: F.finalSupplied(value: nil))
        XCTAssertEqual(Model(after).readerContent(.value), .unavailable(.value, name: "Market value history"))
        // What the sheet draws for the session's held card: that card's own unavailable reading, not a
        // fallback to a card the changed input still mounts.
        let held = try XCTUnwrap(session.reader)
        XCTAssertEqual(Model(after).readerCards, [.history, .duel])
        XCTAssertEqual(Model(after).readerContent(held), .unavailable(.value, name: "Market value history"))
        XCTAssertFalse(Model(after).readerCards.contains { Model(after).readerContent(held) == .card($0) })
        // The rebuilt input still carries the exact held original on the remaining leaf.
        XCTAssertEqual(after.duel?.selection.side?.originalID, F.champagnieOriginal, "the selection stays exact")
        session.close()
        XCTAssertNil(session.mode, "Back works")
        XCTAssertEqual(session.selectedOriginalID, F.champagnieOriginal)
    }

    func testAWithdrawnDuelCardShowsItsOwnUnavailableReadingNeverAnotherStory() throws {
        var session = A.Session()
        session.openReader(.duel)
        let before = try finalInput()
        XCTAssertEqual(Model(before).readerContent(.duel), .card(.duel))
        // CONSTRUCTED: the pair breaks (one player withdrawn), so the duel is no longer offered.
        let after = try finalInput(supplied: F.finalSupplied(duel: F.duel(.final, sides: [F.champagnie()])))
        XCTAssertEqual(Model(after).readerContent(.duel), .unavailable(.duel, name: "Threes head-to-head"))
        XCTAssertEqual(Model(after).readerContent(.value), .card(.value), "the value card is not moved into its place")
        // What the sheet draws for the session's held card after the change.
        let held = try XCTUnwrap(session.reader)
        XCTAssertEqual(Model(after).readerCards, [.history, .value])
        XCTAssertEqual(Model(after).readerContent(held), .unavailable(.duel, name: "Threes head-to-head"))
        XCTAssertNotEqual(Model(after).readerContent(held), .card(.value))
        session.close()
        XCTAssertNil(session.mode)
    }

    func testAWithdrawnOriginalUnderDetailsResolvesToNothingAndDoneReturns() throws {
        var session = A.Session()
        session.openReader(.duel)
        let held = Details.Selection(scope: F.scope, identity: F.anunobyIdentity)
        session.openDetails(held)
        // CONSTRUCTED: the owner's catalogue no longer holds Anunoby's contract.
        let after = try finalInput(supplied: F.finalSupplied(catalogue: F.catalogue([F.knicksWinner, F.champagnieContract])))
        XCTAssertFalse(Model(after).originalAvailable(held))
        XCTAssertNil(Details.original(in: after.catalogue, selection: held), "never a neighbour")
        // What Details draws for the session's held selection: nothing resolves, although the changed
        // catalogue still holds a neighbouring contract (Champagnie's) in the same scope.
        XCTAssertFalse(Model(after).originalAvailable(session.catalogueSelection))
        XCTAssertNotNil(Details.original(in: after.catalogue,
                                         selection: Details.Selection(scope: F.scope, identity: F.champagnieIdentity)))
        XCTAssertNil(Details.content(catalogue: after.catalogue, selection: session.catalogueSelection))
        session.close()
        XCTAssertEqual(session.mode, .reader(.duel))
    }

    /// Model flags only: the unavailable words and Back are drawn by a private view, not asserted here.
    func testAWithdrawnAboutIsReportedUnavailableAndOffersNoNewEntry() throws {
        let event = try F.finalEvent()
        var supplied = F.finalSupplied()
        supplied.about = nil
        let input = try XCTUnwrap(A.build(event: event, supplied: supplied, now: F.now))
        XCTAssertFalse(Model(input).aboutContentAvailable)
        XCTAssertFalse(Model(input).aboutEntry(mode: .page, canOpen: true), "no new About entry is offered")
    }
}
