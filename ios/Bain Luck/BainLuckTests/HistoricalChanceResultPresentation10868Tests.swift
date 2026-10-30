import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the rugby-match and afl-match pages' shared final "chance → result"
/// card: one team's before-match chance beside one later recorded trade on one
/// common 0–100% scale, and the separately reported actual final, as a
/// stateless leaf.
///
/// What is asserted is the rules the view defers to: exact scoped identity
/// through the chooser's resolver, the one-admitted-reading / one-tied-
/// observation rule per endpoint, the reported actual's own association, bars
/// on one common scale and one inset, the arrangement choices the view
/// consumes, the actions each control hands back, the final-only gate and the
/// spoken summaries. One test hosts the view at compact, wide and accessibility
/// sizes only to prove that laying it out fires no callback. Nothing here
/// claims a rendered fit, a native runtime, VoiceOver behaviour or a
/// held-update qualification.
///
/// ARCHIVED raw values come from
/// `shipping-adoption-20261027/HISTORICAL-CHANCE-RESULT-RETAINED-CASES.json`
/// (sha256 dbf59ad8…), generated from the unchanged `rugbySeries`/`rugbyLow`
/// and `aflSeries`/`aflBrisbaneContext`:
/// - France vs England, Six Nations, listed start 1773519000: France
///   (KXSIXNATIONSMATCH-26MAR14ENGFRA-FRA) last admitted trade before the
///   listed start 0.81 at candle end 1773518880, lowest admitted match-window
///   minute-end (close) 0.02 at 1773521580; England 0.21 at 1773518940 and
///   Draw 0.02 at 1773517140 as independent baselines (together 104%);
///   reported final France 48–46 England.
/// - Brisbane vs Fremantle, AFL, listed start 1790397000: Brisbane
///   (KXAFLGAME-26SEP260030BRIFRE-BRI) 0.56 at 1790396940, lowest minute-end
///   (close) 0.03 at 1790406480; Fremantle 0.45 at 1790396880; reported final
///   Brisbane 96–89 Fremantle.
/// Every stamp is a candle-end minute, not a scoring time; the actual finish
/// and checkpoint wall clocks are unknown (null) and nothing here invents one.
/// The checkpoint is the lowest minute CLOSE the unchanged reference elects,
/// not the lowest trade inside a minute: Brisbane's 1790406480 minute closed at
/// 0.03 while its intraminute low was 0.01 (France's closed and lowed at 0.02).
/// So the constructed label is Design's approved "Lowest minute-end chance"
/// (`HISTORICAL-CHANCE-RESULT-COPY-CORRECTION.json`); the values, clocks and
/// keys are unchanged, and the card shows the owner's reading as given.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// scope and source strings, Kalshi tickers standing in for the production
/// outcome identity Native still has to map, every label and absence word, the
/// percent figure text and the local clock lines (Paris CET and Brisbane AEST,
/// computed from each unix stamp), the observation keys (ticker@candle-end,
/// chosen as opaque owner keys), the outcome words, the scale and its tick
/// labels, the phases and every missing, duplicate, mismatched, foreign, blank,
/// off-scale and invalid case.
final class HistoricalChanceResultPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private struct Trade {
        let p: Double
        let t: Int
        /// CONSTRUCTED owner text for this trade.
        let text: String
        let clock: String
    }

    private struct Team {
        let scope: String
        let ticker: String
        let name: String
        let before: Trade
        /// The owner's checkpoint; nil when the case retains none for this team.
        let checkpoint: Trade?

        var ref: FieldChooserOriginalRef10868 {
            FieldChooserOriginalRef10868(scope: scope, source: "kalshi", marketID: ticker, outcomeID: "yes")
        }

        func key(_ kind: HistoricalChanceEndpointKind10868) -> String {
            "\(ticker)@\(kind == .before ? before.t : checkpoint?.t ?? 0)"
        }
    }

    private struct Case {
        let scope: String
        let listedStart: Int
        let subject: Team
        let others: [Team]
        let score: String
        let source: String
        let outcome: String
        let eyebrow: String
        let title: String

        var teams: [Team] { [subject] + others }
    }

    /// CONSTRUCTED opaque scopes.
    private static let rugbyScope = "kalshi|KXSIXNATIONSMATCH-26MAR14ENGFRA|winner|held-final"
    private static let aflScope = "kalshi|KXAFLGAME-26SEP260030BRIFRE|winner|held-final"

    /// ARCHIVED France, with CONSTRUCTED text.
    private static let france = Team(
        scope: rugbyScope, ticker: "KXSIXNATIONSMATCH-26MAR14ENGFRA-FRA", name: "France",
        before: Trade(p: 0.81, t: 1_773_518_880, text: "81%", clock: "Mar 14, 9:08 PM CET · Kalshi"),
        checkpoint: Trade(p: 0.02, t: 1_773_521_580, text: "2%", clock: "Mar 14, 9:53 PM CET · Kalshi"))
    /// ARCHIVED England, its own independent baseline only.
    private static let england = Team(
        scope: rugbyScope, ticker: "KXSIXNATIONSMATCH-26MAR14ENGFRA-ENG", name: "England",
        before: Trade(p: 0.21, t: 1_773_518_940, text: "21%", clock: "Mar 14, 9:09 PM CET · Kalshi"),
        checkpoint: nil)
    /// ARCHIVED Draw (the venue's "Tie"), its own independent baseline only.
    private static let draw = Team(
        scope: rugbyScope, ticker: "KXSIXNATIONSMATCH-26MAR14ENGFRA-TIE", name: "Draw",
        before: Trade(p: 0.02, t: 1_773_517_140, text: "2%", clock: "Mar 14, 8:39 PM CET · Kalshi"),
        checkpoint: nil)
    /// ARCHIVED Brisbane, with CONSTRUCTED text.
    private static let brisbane = Team(
        scope: aflScope, ticker: "KXAFLGAME-26SEP260030BRIFRE-BRI", name: "Brisbane",
        before: Trade(p: 0.56, t: 1_790_396_940, text: "56%", clock: "Sep 26, 2:29 PM AEST · Kalshi"),
        checkpoint: Trade(p: 0.03, t: 1_790_406_480, text: "3%", clock: "Sep 26, 5:08 PM AEST · Kalshi"))
    /// ARCHIVED Fremantle, its own independent baseline only.
    private static let fremantle = Team(
        scope: aflScope, ticker: "KXAFLGAME-26SEP260030BRIFRE-FRE", name: "Fremantle",
        before: Trade(p: 0.45, t: 1_790_396_880, text: "45%", clock: "Sep 26, 2:28 PM AEST · Kalshi"),
        checkpoint: nil)

    private static let rugby = Case(
        scope: rugbyScope, listedStart: 1_773_519_000, subject: france, others: [england, draw],
        score: "France 48–46 England", source: "Retained ESPN final header; approved rugby reference",
        outcome: "France won", eyebrow: "FRANCE’S CHANGING CHANCE", title: "France’s changing chance")
    private static let afl = Case(
        scope: aflScope, listedStart: 1_790_397_000, subject: brisbane, others: [fremantle],
        score: "Brisbane 96–89 Fremantle", source: "Retained ESPN final header and scoreboard",
        outcome: "Brisbane won", eyebrow: "BRISBANE’S CHANCE → RESULT", title: "Brisbane’s chance → result")

    private static func copy(_ c: Case) -> HistoricalChanceCopy10868 {
        HistoricalChanceCopy10868(
            eyebrow: c.eyebrow,
            title: c.title,
            beforeLabel: "Before match",
            checkpointLabel: "Lowest minute-end chance",
            endpointUnavailable: "Not recorded for this comparison",
            beforeKey: "Outline: last trade before the listed start",
            checkpointKey: "Filled: a later recorded trade",
            graphicLabel: "Win chances",
            chanceUnplaced: "Not drawn on this scale",
            offScale: "Above this scale",
            actualTitle: "ACTUAL RESULT",
            actualLabel: "Reported final score",
            actualUnavailable: "Final score not confirmed",
            context: "Each chance is one dated trade. The score was reported separately.",
            expandLabel: "Open \(c.subject.name)’s chance story full size",
            expandHint: nil,
            detailsLabel: "How to read this story",
            detailsHint: nil,
            openHint: "Opens this trade in the history"
        )
    }

    private static let scale = FieldOutlookScale10868(
        ceiling: 1,
        ticks: [
            FieldOutlookTick10868(probability: 0, label: "0%"),
            FieldOutlookTick10868(probability: 0.5, label: "50%"),
            FieldOutlookTick10868(probability: 1, label: "100%"),
        ],
        words: "0–100% chance · independent Kalshi trades"
    )

    private static func label(_ kind: HistoricalChanceEndpointKind10868) -> String {
        kind == .before ? "Before match" : "Lowest minute-end chance"
    }

    private static func reading(_ kind: HistoricalChanceEndpointKind10868, _ trade: Trade) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: label(kind), value: .recorded(text: trade.text, detail: trade.clock))
    }

    /// A catalogue record carrying a settled CONTRACT result and movement the
    /// card must never read.
    private static func original(_ team: Team) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: team.ref, name: team.name,
            plan: .single(reading(.before, team.before)),
            preview: FieldChooserPreview10868(history: nil, absence: "No captured history"),
            movement: "Down 79 pts", clock: nil,
            result: FieldChooserResult10868(title: "Contract result", words: "Won"),
            browseStatus: "Recorded history available"
        )
    }

    private static func trades(_ team: Team) -> [(HistoricalChanceEndpointKind10868, Trade)] {
        [(.before, team.before)] + (team.checkpoint.map { [(.checkpoint, $0)] } ?? [])
    }

    private static func admitted(_ teams: [Team]) -> [HistoricalChanceReading10868] {
        teams.flatMap { team in
            trades(team).map { HistoricalChanceReading10868(ref: team.ref, endpoint: $0.0, reading: reading($0.0, $0.1)) }
        }
    }

    private static func observation(_ team: Team, _ kind: HistoricalChanceEndpointKind10868, _ trade: Trade) -> HistoricalChanceObservation10868 {
        HistoricalChanceObservation10868(
            ref: team.ref, endpoint: kind,
            observation: FieldMovementObservation10868(probability: trade.p, reading: reading(kind, trade)),
            key: team.key(kind)
        )
    }

    private static func observed(_ teams: [Team]) -> [HistoricalChanceObservation10868] {
        teams.flatMap { team in trades(team).map { observation(team, $0.0, $0.1) } }
    }

    private static func actual(_ team: Team, _ c: Case) -> HistoricalChanceActual10868 {
        HistoricalChanceActual10868(
            place: FieldFinishPlace10868(
                ref: team.ref,
                reading: FieldChooserReading10868(label: "Reported final score", value: .recorded(text: c.score, detail: c.source))),
            outcome: c.outcome)
    }

    private static func input(
        _ c: Case = HistoricalChanceResultPresentation10868Tests.rugby,
        subject: HistoricalChanceSubject10868? = nil,
        catalogue: [FieldChooserOriginal10868]? = nil,
        readings: [HistoricalChanceReading10868]? = nil,
        observations: [HistoricalChanceObservation10868]? = nil,
        actuals: [HistoricalChanceActual10868]? = nil,
        scale: FieldOutlookScale10868 = HistoricalChanceResultPresentation10868Tests.scale,
        phase: FieldOutlookPhase10868 = .final
    ) -> HistoricalChanceInput10868 {
        HistoricalChanceInput10868(
            scope: c.scope,
            catalogue: catalogue ?? c.teams.map(original),
            subject: subject ?? HistoricalChanceSubject10868(ref: c.subject.ref, name: c.subject.name),
            readings: readings ?? admitted(c.teams),
            observations: observations ?? observed(c.teams),
            actuals: actuals ?? [actual(c.subject, c)],
            scale: scale,
            phase: phase,
            copy: copy(c),
            unavailableWords: "Team unavailable in this update"
        )
    }

    private static func model(_ input: HistoricalChanceInput10868 = HistoricalChanceResultPresentation10868Tests.input()) -> HistoricalChanceModel10868 {
        HistoricalChanceModel10868(input)
    }

    private static func side(_ model: HistoricalChanceModel10868, _ kind: HistoricalChanceEndpointKind10868) -> HistoricalChanceSide10868? {
        model.sides.first { $0.kind == kind }
    }

    /// What the view's bar Canvas inks for an outline: the stroke's outer edge
    /// on `outline`, clipped to `outlineBounds` (the Canvas clips to it before
    /// it strokes). A model of the drawing, not a render.
    private static func outlineInk(_ plan: HistoricalChanceBarPlan10868, lineWidth: CGFloat) -> CGRect? {
        guard let stroke = plan.outline, let bounds = plan.outlineBounds else { return nil }
        return stroke.insetBy(dx: -lineWidth / 2, dy: -lineWidth / 2).intersection(bounds)
    }

    /// Two rects with the same edges, to floating-point rounding.
    private func assertSameRect(_ a: CGRect?, _ b: CGRect?, _ message: String = "", file: StaticString = #filePath, line: UInt = #line) {
        guard let a, let b else { return XCTFail("missing rect \(message)", file: file, line: line) }
        for (x, y) in [(a.minX, b.minX), (a.minY, b.minY), (a.maxX, b.maxX), (a.maxY, b.maxY)] {
            XCTAssertEqual(x, y, accuracy: 1e-9, message, file: file, line: line)
        }
    }

    private static let unavailableBefore = FieldMovementEndpoint10868.unavailable(label: "Before match", words: "Not recorded for this comparison")
    private static let unavailableCheckpoint = FieldMovementEndpoint10868.unavailable(label: "Lowest minute-end chance", words: "Not recorded for this comparison")
    private static let unavailableActual = FieldMovementEndpoint10868.unavailable(label: "Reported final score", words: "Final score not confirmed")

    // MARK: Real retained cases

    func testRugbyFranceKeepsItsOwnBeforeCheckpointAndSeparatelyReportedFinal() throws {
        try assertRetainedCase(Self.rugby)
    }

    func testAflBrisbaneKeepsItsOwnBeforeCheckpointAndSeparatelyReportedFinal() throws {
        try assertRetainedCase(Self.afl)
    }

    func testRetainedCheckpointsAreNamedLowestMinuteEndChanceWithTheirOwnClocksAndActuals() throws {
        // ARCHIVED minute closes, unchanged: Brisbane's 0.03 is its minute's
        // close (that minute's intraminute low, 0.01, is not this reading).
        let expected: [(Case, Double, Int, String, String)] = [
            (Self.rugby, 0.02, 1_773_521_580,
             "France. Lowest minute-end chance: 2%, Mar 14, 9:53 PM CET · Kalshi",
             "KXSIXNATIONSMATCH-26MAR14ENGFRA-FRA@1773521580"),
            (Self.afl, 0.03, 1_790_406_480,
             "Brisbane. Lowest minute-end chance: 3%, Sep 26, 5:08 PM AEST · Kalshi",
             "KXAFLGAME-26SEP260030BRIFRE-BRI@1790406480"),
        ]
        for (c, p, t, spoken, key) in expected {
            let name = c.subject.name
            let checkpoint = try XCTUnwrap(c.subject.checkpoint, name)
            XCTAssertEqual(checkpoint.p, p, name)
            XCTAssertEqual(checkpoint.t, t, name)
            let model = Self.model(Self.input(c))
            let side = try XCTUnwrap(Self.side(model, .checkpoint), name)
            XCTAssertEqual(FieldChaseModel10868.label(side.endpoint), "Lowest minute-end chance", name)
            XCTAssertEqual(FieldChaseModel10868.figure(side.endpoint), checkpoint.text, name)
            XCTAssertEqual(FieldChaseModel10868.detail(side.endpoint), checkpoint.clock, name)
            XCTAssertEqual(side.chance, .value(probability: p, fraction: p), name)
            XCTAssertEqual(model.endpointSummary(side), spoken, name)
            XCTAssertTrue(model.chancesSummary.hasSuffix(String(spoken.dropFirst(name.count + 2))), name)
            XCTAssertEqual(model.openAction(side, canOpen: true), FieldMovementOpen10868(ref: c.subject.ref, observation: key), name)
            XCTAssertEqual(model.actual, .reading(FieldChooserReading10868(
                label: "Reported final score", value: .recorded(text: c.score, detail: c.source))), name)
            XCTAssertEqual(model.outcome, c.outcome, name)
            XCTAssertFalse(model.summary.contains("Lowest recorded trade"), name)
        }
    }

    private func assertRetainedCase(_ c: Case, file: StaticString = #filePath, line: UInt = #line) throws {
        let team = c.subject
        let checkpoint = try XCTUnwrap(team.checkpoint, file: file, line: line)
        // ARCHIVED windows: before strictly precedes the listed start, the checkpoint does not.
        XCTAssertLessThan(team.before.t, c.listedStart, file: file, line: line)
        XCTAssertGreaterThanOrEqual(checkpoint.t, c.listedStart, file: file, line: line)

        let model = Self.model(Self.input(c))
        XCTAssertTrue(model.isShown, file: file, line: line)
        XCTAssertEqual(model.original?.ref, team.ref, file: file, line: line)
        XCTAssertEqual(model.subjectName, team.name, file: file, line: line)
        XCTAssertNil(model.subjectWords, file: file, line: line)
        XCTAssertEqual(model.sides.map(\.kind), [.before, .checkpoint], file: file, line: line)

        let before = try XCTUnwrap(Self.side(model, .before), file: file, line: line)
        XCTAssertEqual(before.endpoint, .reading(Self.reading(.before, team.before)), file: file, line: line)
        XCTAssertEqual(before.chance, .value(probability: team.before.p, fraction: team.before.p), file: file, line: line)
        XCTAssertEqual(before.key, team.key(.before), file: file, line: line)

        let later = try XCTUnwrap(Self.side(model, .checkpoint), file: file, line: line)
        XCTAssertEqual(later.endpoint, .reading(Self.reading(.checkpoint, checkpoint)), file: file, line: line)
        XCTAssertEqual(later.chance, .value(probability: checkpoint.p, fraction: checkpoint.p), file: file, line: line)
        XCTAssertEqual(later.key, team.key(.checkpoint), file: file, line: line)
        XCTAssertNotEqual(before.key, later.key, file: file, line: line)

        XCTAssertEqual(model.actual, .reading(FieldChooserReading10868(
            label: "Reported final score", value: .recorded(text: c.score, detail: c.source))), file: file, line: line)
        XCTAssertEqual(model.outcome, c.outcome, file: file, line: line)
        XCTAssertTrue(model.showsPlot, file: file, line: line)
        XCTAssertEqual(model.ticks.map(\.label), ["0%", "50%", "100%"], file: file, line: line)
        XCTAssertEqual(model.eyebrow, c.eyebrow, file: file, line: line)
        XCTAssertEqual(model.title, c.title, file: file, line: line)
    }

    func testBeforeAndDuringShowNothingEvenWhenFinalFieldsRideAlong() {
        for phase in [FieldOutlookPhase10868.before, .during] {
            let model = Self.model(Self.input(phase: phase))
            XCTAssertFalse(model.isShown)
            XCTAssertNil(model.eyebrow)
            XCTAssertNil(model.title)
            XCTAssertNil(model.context)
            XCTAssertNil(model.original)
            XCTAssertNil(model.subjectName)
            XCTAssertNil(model.subjectWords)
            XCTAssertTrue(model.sides.isEmpty)
            XCTAssertNil(model.actual)
            XCTAssertNil(model.outcome)
            XCTAssertFalse(model.showsPlot)
            XCTAssertTrue(model.ticks.isEmpty)
            XCTAssertFalse(model.showsExpand(canExpand: true))
            XCTAssertNil(model.detailsLabel(canShowDetails: true))
            XCTAssertEqual(model.summary, "")
            XCTAssertEqual(model.chancesSummary, "")
            XCTAssertEqual(model.actualSummary, "")
            // A side carried over from the final input opens nothing here.
            let finalSide = Self.side(Self.model(), .before)!
            XCTAssertNil(model.openAction(finalSide, canOpen: true))
        }
    }

    // MARK: Independence of chances and actual

    func testMissingChancesKeepTheActualAndAMissingActualKeepsTheChances() throws {
        // No chances at all: both labelled slots in words, no plot, the actual stays.
        let noChances = Self.model(Self.input(readings: [], observations: []))
        XCTAssertEqual(noChances.sides.map(\.endpoint), [Self.unavailableBefore, Self.unavailableCheckpoint])
        XCTAssertTrue(noChances.sides.allSatisfy { $0.chance == .unavailable && $0.key == nil })
        XCTAssertFalse(noChances.showsPlot)
        XCTAssertEqual(noChances.actual, Self.model().actual)
        XCTAssertEqual(noChances.outcome, "France won")

        // No actual: the panel keeps its label and the copy's words; both chances stay.
        let noActual = Self.model(Self.input(actuals: []))
        XCTAssertEqual(noActual.actual, Self.unavailableActual)
        XCTAssertNil(noActual.outcome)
        XCTAssertEqual(noActual.sides, Self.model().sides)
        XCTAssertTrue(noActual.showsPlot)

        // The owner's own absence words for the checkpoint: shown as they are, no
        // bar, no key; the before chance is untouched.
        let franceRef = Self.france.ref
        let absent = FieldChooserReading10868(label: "Lowest minute-end chance", value: .missing("No trade recorded after the listed start"))
        let readings = Self.admitted([Self.france]).filter { $0.endpoint == .before }
            + [HistoricalChanceReading10868(ref: franceRef, endpoint: .checkpoint, reading: absent)]
        let ownWords = Self.model(Self.input(readings: readings))
        let checkpoint = try XCTUnwrap(Self.side(ownWords, .checkpoint))
        XCTAssertEqual(checkpoint.endpoint, .reading(absent))
        XCTAssertEqual(checkpoint.chance, .unavailable)
        XCTAssertNil(checkpoint.key)
        XCTAssertEqual(ownWords.barWords(checkpoint), "Not drawn on this scale")
        XCTAssertEqual(Self.side(ownWords, .before), Self.side(Self.model(), .before))
        XCTAssertNil(ownWords.openAction(checkpoint, canOpen: true))

        // The owner's absence words for the actual stay, with the outcome words.
        let unscored = HistoricalChanceActual10868(
            place: FieldFinishPlace10868(ref: franceRef, reading: FieldChooserReading10868(
                label: "Reported final score", value: .missing("Score not captured"))),
            outcome: "France won")
        let wordsActual = Self.model(Self.input(actuals: [unscored]))
        XCTAssertEqual(wordsActual.actual, .reading(unscored.place.reading))
        XCTAssertEqual(wordsActual.outcome, "France won")
    }

    func testThePhysicalFinalIsNeverTheContractResultOrAChance() {
        // The catalogue says "Contract result: Won" and the movement words ride
        // along; with no reported actual, neither stands in.
        let model = Self.model(Self.input(actuals: []))
        XCTAssertEqual(model.original?.result?.words, "Won")
        XCTAssertEqual(model.actual, Self.unavailableActual)
        for words in ["Contract result", "Won", "Down 79 pts", "100%"] {
            XCTAssertFalse(model.summary.contains(words), words)
        }
        // A reported final is never placed on the probability scale or turned into a side.
        let reported = Self.model()
        XCTAssertEqual(reported.sides.count, 2)
        XCTAssertFalse(reported.sides.contains { $0.endpoint == reported.actual })
        XCTAssertFalse(reported.summary.contains("100%"))
        XCTAssertFalse(reported.summary.contains("Contract result"))
    }

    // MARK: Identity and associations

    func testScopedIdentityFailuresBorrowNoNeighbourValuesOrActions() {
        let france = Self.france
        let base = france.ref
        let teams = Self.rugby.teams
        let withdrawn = teams.filter { $0.ticker != france.ticker }.map(Self.original)
        let cases: [(String, FieldChooserOriginalRef10868, [FieldChooserOriginal10868])] = [
            ("unknown", FieldChooserOriginalRef10868(scope: base.scope, source: base.source, marketID: "KXSIXNATIONSMATCH-26MAR14ENGFRA-XXX", outcomeID: "yes"), teams.map(Self.original)),
            ("foreign scope", FieldChooserOriginalRef10868(scope: Self.aflScope, source: base.source, marketID: base.marketID, outcomeID: base.outcomeID), teams.map(Self.original)),
            ("blank outcome", FieldChooserOriginalRef10868(scope: base.scope, source: base.source, marketID: base.marketID, outcomeID: " "), teams.map(Self.original)),
            ("duplicate catalogue", base, teams.map(Self.original) + [Self.original(france)]),
            ("withdrawn", base, withdrawn),
        ]
        for (name, ref, catalogue) in cases {
            let model = Self.model(Self.input(subject: HistoricalChanceSubject10868(ref: ref, name: "France"), catalogue: catalogue))
            XCTAssertNil(model.original, name)
            XCTAssertEqual(model.subjectName, "France", name)
            XCTAssertEqual(model.subjectWords, "Team unavailable in this update", name)
            XCTAssertEqual(model.sides.map(\.endpoint), [Self.unavailableBefore, Self.unavailableCheckpoint], name)
            XCTAssertTrue(model.sides.allSatisfy { $0.key == nil && $0.chance == .unavailable }, name)
            XCTAssertEqual(model.actual, Self.unavailableActual, name)
            XCTAssertNil(model.outcome, name)
            XCTAssertFalse(model.showsPlot, name)
            XCTAssertTrue(model.sides.allSatisfy { model.openAction($0, canOpen: true) == nil }, name)
            // France's own and England's values, present in the input, never appear.
            for words in ["81%", "21%", "England", "48–46", "France won"] {
                XCTAssertFalse(model.summary.contains(words), "\(name): \(words)")
            }
        }
        // The draw's catalogue name stands as the venue's "Tie" original, by identity only.
        let drawModel = Self.model(Self.input(subject: HistoricalChanceSubject10868(ref: Self.draw.ref, name: "Draw")))
        XCTAssertEqual(drawModel.original?.ref, Self.draw.ref)
        XCTAssertEqual(drawModel.actual, Self.unavailableActual, "France's reported final is not the draw's")
    }

    func testUntiedMismatchedOrDuplicatedAssociationsBorrowNothing() throws {
        let france = Self.france
        let checkpoint = try XCTUnwrap(france.checkpoint)
        let readings = Self.admitted(Self.rugby.teams)
        let observations = Self.observed(Self.rugby.teams)

        // Two identical admitted readings for one endpoint are none.
        let doubled = Self.model(Self.input(readings: readings + [readings[0]]))
        XCTAssertEqual(Self.side(doubled, .before)?.endpoint, Self.unavailableBefore)
        XCTAssertEqual(Self.side(doubled, .checkpoint), Self.side(Self.model(), .checkpoint))

        // Two identical observations for one endpoint are none.
        let doubledObservation = Self.model(Self.input(observations: observations + [observations[0]]))
        XCTAssertEqual(Self.side(doubledObservation, .before)?.endpoint, Self.unavailableBefore)
        XCTAssertNil(Self.side(doubledObservation, .before)?.key)

        // An observation formatted with another clock line does not tie.
        var drifted = observations
        drifted[0] = HistoricalChanceObservation10868(
            ref: france.ref, endpoint: .before,
            observation: FieldMovementObservation10868(probability: 0.81, reading: FieldChooserReading10868(
                label: "Before match", value: .recorded(text: "81%", detail: "Mar 14, 9:09 PM CET · Kalshi"))),
            key: france.key(.before))
        XCTAssertEqual(Self.side(Self.model(Self.input(observations: drifted)), .before)?.endpoint, Self.unavailableBefore)

        // The checkpoint's observation filed under before ties nothing on either side.
        let misfiled = observations.filter { !($0.ref == france.ref) }
            + [HistoricalChanceObservation10868(
                ref: france.ref, endpoint: .before,
                observation: FieldMovementObservation10868(probability: checkpoint.p, reading: Self.reading(.checkpoint, checkpoint)),
                key: france.key(.checkpoint))]
        let misfiledModel = Self.model(Self.input(observations: misfiled))
        XCTAssertEqual(Self.side(misfiledModel, .before)?.endpoint, Self.unavailableBefore)
        XCTAssertEqual(Self.side(misfiledModel, .checkpoint)?.endpoint, Self.unavailableCheckpoint)

        // England's checkpoint-shaped reading is never France's.
        let foreign = readings.filter { !($0.ref == france.ref && $0.endpoint == .checkpoint) }
            + [HistoricalChanceReading10868(ref: Self.england.ref, endpoint: .checkpoint, reading: Self.reading(.checkpoint, checkpoint))]
        XCTAssertEqual(Self.side(Self.model(Self.input(readings: foreign)), .checkpoint)?.endpoint, Self.unavailableCheckpoint)

        // Actual associations: duplicated, blank, or only another original's.
        let reported = Self.actual(france, Self.rugby)
        XCTAssertEqual(Self.model(Self.input(actuals: [reported, reported])).actual, Self.unavailableActual)
        let blank = HistoricalChanceActual10868(
            place: FieldFinishPlace10868(ref: france.ref, reading: FieldChooserReading10868(
                label: "Reported final score", value: .recorded(text: "  ", detail: "ESPN"))),
            outcome: "France won")
        let blankModel = Self.model(Self.input(actuals: [blank]))
        XCTAssertEqual(blankModel.actual, Self.unavailableActual)
        XCTAssertNil(blankModel.outcome, "outcome words only beside a shown reading")
        let englandOnly = Self.model(Self.input(actuals: [Self.actual(Self.england, Self.rugby)]))
        XCTAssertEqual(englandOnly.actual, Self.unavailableActual)
        XCTAssertNil(englandOnly.outcome)
    }

    func testIndependentOpponentBaselinesAreNeverComplementsOrNormalized() throws {
        // ARCHIVED: the three independent baselines together are 104%.
        let sum = Self.rugby.teams.map(\.before.p).reduce(0, +)
        XCTAssertEqual(sum, 1.04, accuracy: 1e-9)
        let france = Self.model()
        let franceBefore = try XCTUnwrap(Self.side(france, .before)?.chance.fraction)
        XCTAssertEqual(franceBefore, 0.81, accuracy: 0)
        XCTAssertNotEqual(franceBefore, 1 - Self.england.before.p, "not England's complement (0.79)")
        XCTAssertNotEqual(franceBefore, 0.81 / sum, "not normalized across the three")

        // England as the subject: its own 21% before; no checkpoint of its own,
        // so none — never France's 2% complemented to 98%.
        let england = Self.model(Self.input(subject: HistoricalChanceSubject10868(ref: Self.england.ref, name: "England"), actuals: []))
        XCTAssertEqual(Self.side(england, .before)?.endpoint, .reading(Self.reading(.before, Self.england.before)))
        XCTAssertEqual(Self.side(england, .before)?.chance, .value(probability: 0.21, fraction: 0.21))
        XCTAssertEqual(Self.side(england, .checkpoint)?.endpoint, Self.unavailableCheckpoint)
        XCTAssertFalse(england.chancesSummary.contains("98%"))
        XCTAssertFalse(england.chancesSummary.contains("19%"))

        // Fremantle likewise keeps 45%, not Brisbane's complement (44%).
        let fremantle = Self.model(Self.input(Self.afl, subject: HistoricalChanceSubject10868(ref: Self.fremantle.ref, name: "Fremantle"), actuals: []))
        XCTAssertEqual(Self.side(fremantle, .before)?.chance, .value(probability: 0.45, fraction: 0.45))
        XCTAssertEqual(Self.side(fremantle, .checkpoint)?.endpoint, Self.unavailableCheckpoint)
    }

    // MARK: Values and the scale

    func testSameValueAtDifferentClocksStaysTwoEndpointsWithOwnKeysAndDistinctBars() throws {
        let team = Team(
            scope: Self.rugbyScope, ticker: Self.france.ticker, name: "France",
            before: Trade(p: 0.45, t: 1_773_518_880, text: "45%", clock: "Mar 14, 9:08 PM CET · Kalshi"),
            checkpoint: Trade(p: 0.45, t: 1_773_521_580, text: "45%", clock: "Mar 14, 9:53 PM CET · Kalshi"))
        let model = Self.model(Self.input(readings: Self.admitted([team]), observations: Self.observed([team])))
        let before = try XCTUnwrap(Self.side(model, .before))
        let later = try XCTUnwrap(Self.side(model, .checkpoint))
        XCTAssertEqual(before.chance, later.chance)
        XCTAssertNotEqual(before.endpoint, later.endpoint, "each keeps its own clock line")
        XCTAssertNotEqual(before.key, later.key)

        let size = CGSize(width: 300, height: 12)
        let outlined = try XCTUnwrap(HistoricalChanceGeometry10868.barPlan(kind: .before, fraction: 0.45, ticks: [], in: size, lineWidth: 2))
        let filled = try XCTUnwrap(HistoricalChanceGeometry10868.barPlan(kind: .checkpoint, fraction: 0.45, ticks: [], in: size, lineWidth: 2))
        XCTAssertNil(outlined.fill)
        XCTAssertNotNil(outlined.outline)
        XCTAssertNil(filled.outline)
        XCTAssertNotNil(filled.fill)
        let end = try XCTUnwrap(FieldFinishGeometry10868.x(of: 0.45, width: 300, inset: HistoricalChanceGeometry10868.inset(lineWidth: 2)))
        XCTAssertEqual(try XCTUnwrap(filled.fill).maxX, end, accuracy: 1e-9)
        XCTAssertEqual(try XCTUnwrap(outlined.outline).maxX, end - 1, accuracy: 1e-9, "outline ink stays inside the same extent")
        // The outline's bound is the filled bar's own extent; at the default
        // 2 pt stroke and 12 pt bar the stroke already fills it exactly, so the
        // clip changes nothing.
        XCTAssertEqual(outlined.outlineBounds, filled.fill)
        XCTAssertNil(filled.outlineBounds)
        assertSameRect(outlined.outline?.insetBy(dx: -1, dy: -1), outlined.outlineBounds)
        assertSameRect(Self.outlineInk(outlined, lineWidth: 2), outlined.outlineBounds)
    }

    func testGenuineZeroAndHundredReachTheRealEndsAndInvalidOrOffScaleValuesDrawNoBar() throws {
        let france = Self.france
        func model(before p: Double) -> HistoricalChanceModel10868 {
            let trade = Trade(p: p, t: france.before.t, text: "edge", clock: france.before.clock)
            let team = Team(scope: france.scope, ticker: france.ticker, name: "France", before: trade, checkpoint: france.checkpoint)
            return Self.model(Self.input(readings: Self.admitted([team]), observations: Self.observed([team])))
        }
        XCTAssertEqual(Self.side(model(before: 0), .before)?.chance, .value(probability: 0, fraction: 0))
        XCTAssertEqual(Self.side(model(before: 1), .before)?.chance, .value(probability: 1, fraction: 1))
        for invalid in [Double.nan, .infinity, -0.01, 1.01] {
            let side = Self.side(model(before: invalid), .before)
            XCTAssertEqual(side?.endpoint, Self.unavailableBefore, "\(invalid)")
            XCTAssertEqual(side?.chance, .unavailable, "\(invalid)")
            XCTAssertNil(side?.key, "\(invalid)")
        }
        // Above a 50% ceiling: the figure stays, no bar, the owner's off-scale words.
        let half = FieldOutlookScale10868(ceiling: 0.5, ticks: [FieldOutlookTick10868(probability: 0.5, label: "50%")], words: "0–50% chance")
        let above = Self.model(Self.input(scale: half))
        let offScale = try XCTUnwrap(Self.side(above, .before))
        XCTAssertEqual(offScale.chance, .offScale)
        XCTAssertEqual(FieldChaseModel10868.figure(offScale.endpoint), "81%")
        XCTAssertEqual(above.barWords(offScale), "Above this scale")
        XCTAssertTrue(above.endpointSummary(offScale).hasSuffix("Above this scale"))
        XCTAssertEqual(Self.side(above, .checkpoint)?.chance, .value(probability: 0.02, fraction: 0.04))

        // Geometry: 0 is a zero mark at zero; 1 reaches the ceiling; nothing else is clamped.
        let size = CGSize(width: 240, height: 12)
        let inset = HistoricalChanceGeometry10868.inset(lineWidth: 2)
        let zeroX = try XCTUnwrap(FieldFinishGeometry10868.x(of: 0, width: 240, inset: inset))
        let ceilingX = try XCTUnwrap(FieldFinishGeometry10868.x(of: 1, width: 240, inset: inset))
        for kind in HistoricalChanceEndpointKind10868.allCases {
            let zero = try XCTUnwrap(HistoricalChanceGeometry10868.barPlan(kind: kind, fraction: 0, ticks: [], in: size, lineWidth: 2))
            XCTAssertEqual(try XCTUnwrap(zero.zeroMark).minX, zeroX, accuracy: 1e-9)
            XCTAssertNil(zero.fill)
            XCTAssertNil(zero.outline)
            XCTAssertNil(zero.outlineBounds, "a genuine zero keeps its own zero cue")
            let full = try XCTUnwrap(HistoricalChanceGeometry10868.barPlan(kind: kind, fraction: 1, ticks: [], in: size, lineWidth: 2))
            let extent = try XCTUnwrap(full.fill ?? full.outline.map { $0.insetBy(dx: -1, dy: -1) })
            XCTAssertEqual(extent.minX, zeroX, accuracy: 1e-9)
            XCTAssertEqual(extent.maxX, ceilingX, accuracy: 1e-9)
            if kind == .before {
                assertSameRect(full.outlineBounds, extent)
            } else {
                XCTAssertNil(full.outlineBounds)
            }
            for none in [nil, Double.nan, 1.2, -0.1] as [Double?] {
                let plan = try XCTUnwrap(HistoricalChanceGeometry10868.barPlan(kind: kind, fraction: none, ticks: [], in: size, lineWidth: 2))
                XCTAssertNil(plan.fill)
                XCTAssertNil(plan.outline)
                XCTAssertNil(plan.outlineBounds)
                XCTAssertNil(plan.zeroMark)
                XCTAssertEqual(plan.track.minX, zeroX, accuracy: 1e-9)
            }
        }
        // Sizes or strokes that cannot be drawn draw nothing at all.
        let undrawable: [(CGSize, CGFloat)] = [
            (CGSize(width: 240, height: 0), 2), (CGSize(width: 240, height: .nan), 2),
            (CGSize(width: 2 * inset, height: 12), 2), (CGSize(width: 240, height: 12), 0),
        ]
        for (bad, line) in undrawable {
            XCTAssertNil(HistoricalChanceGeometry10868.barPlan(kind: .checkpoint, fraction: 0.5, ticks: [], in: bad, lineWidth: line))
        }
    }

    func testAnInvalidScaleOrBlankScaleWordsDrawNoPlotButKeepEveryFigure() {
        for ceiling in [0, -0.5, 1.5, Double.nan] {
            let model = Self.model(Self.input(scale: FieldOutlookScale10868(ceiling: ceiling, ticks: Self.scale.ticks, words: Self.scale.words)))
            XCTAssertFalse(model.showsPlot, "\(ceiling)")
            XCTAssertTrue(model.ticks.isEmpty, "\(ceiling)")
            XCTAssertTrue(model.sides.allSatisfy { $0.chance == .unavailable }, "\(ceiling)")
            XCTAssertEqual(model.sides.map { FieldChaseModel10868.figure($0.endpoint) }, ["81%", "2%"], "\(ceiling)")
            XCTAssertEqual(model.actual, Self.model().actual)
        }
        let blankWords = Self.model(Self.input(scale: FieldOutlookScale10868(ceiling: 1, ticks: Self.scale.ticks, words: " ")))
        XCTAssertFalse(blankWords.showsPlot)
        XCTAssertTrue(blankWords.ticks.isEmpty)
        // A tick beyond the ceiling is left out; the rest keep the owner's order.
        let extra = FieldOutlookScale10868(
            ceiling: 1,
            ticks: [FieldOutlookTick10868(probability: 1.5, label: "150%"), FieldOutlookTick10868(probability: 0.5, label: "50%")],
            words: Self.scale.words)
        XCTAssertEqual(Self.model(Self.input(scale: extra)).ticks.map(\.label), ["50%"])
    }

    func testBarsTicksAndAxisLabelsShareOneInset() throws {
        let inset = HistoricalChanceGeometry10868.inset(lineWidth: 2)
        XCTAssertEqual(inset, FieldExpectationsGeometry10868.inset(markDiameter: 2))
        let width: CGFloat = 320
        let plan = try XCTUnwrap(HistoricalChanceGeometry10868.barPlan(
            kind: .checkpoint, fraction: 0.81, ticks: [0.5, 1], in: CGSize(width: width, height: 12), lineWidth: 2))
        let expected = [0, 0.5, 1].compactMap { FieldFinishGeometry10868.x(of: $0, width: width, inset: inset) }
        XCTAssertEqual(plan.tickXs, expected)
        XCTAssertEqual(plan.track.minX, expected[0])
        XCTAssertEqual(plan.track.maxX, expected[2], accuracy: 1e-9)
        // The axis labels are placed by the same x for the same inset.
        let labels = FieldExpectationsGeometry10868.axisLabels(
            [FieldChaseMeasuredTick10868(unit: 0.5, size: CGSize(width: 24, height: 12))], width: width, inset: inset, spacing: 6)
        XCTAssertEqual(try XCTUnwrap(labels.first ?? nil).midX, expected[1], accuracy: 1e-9)

        // An outline stays inside its bar. One too thin for the inward stroke
        // is stroked on the bar itself, and only the bar's own extent — the
        // plan's bound, which the Canvas clips to — keeps that ink.
        let wide = CGRect(x: 10, y: 0, width: 40, height: 12)
        XCTAssertEqual(HistoricalChanceGeometry10868.outline(wide, lineWidth: 2), wide.insetBy(dx: 1, dy: 1))
        let track = width - 2 * inset
        let thin = try XCTUnwrap(HistoricalChanceGeometry10868.barPlan(
            kind: .before, fraction: Double(1.5 / track), ticks: [], in: CGSize(width: width, height: 12), lineWidth: 2))
        let thinBounds = try XCTUnwrap(thin.outlineBounds)
        XCTAssertEqual(thinBounds.width, 1.5, accuracy: 1e-9)
        assertSameRect(Self.outlineInk(thin, lineWidth: 2), thinBounds, "never wider than 1.5 pt")
    }

    func testThinAndShortPositiveBarsAreInkedOnlyOverTheirTrueExtent() throws {
        let lineWidth: CGFloat = 2
        let inset = HistoricalChanceGeometry10868.inset(lineWidth: lineWidth)
        // Positive fractions narrower than the 2 pt stroke, then short positive
        // heights, then both: every one is a real, nonzero chance.
        let cases: [(Double, CGSize)] = [
            (0.002, CGSize(width: 240, height: 12)), (0.005, CGSize(width: 240, height: 12)),
            (0.008, CGSize(width: 240, height: 12)), (0.5, CGSize(width: 240, height: 1.5)),
            (0.02, CGSize(width: 240, height: 1)), (0.005, CGSize(width: 240, height: 1.5)),
        ]
        for (fraction, size) in cases {
            let name = "\(fraction) in \(size)"
            let zeroX = try XCTUnwrap(FieldFinishGeometry10868.x(of: 0, width: size.width, inset: inset))
            let endX = try XCTUnwrap(FieldFinishGeometry10868.x(of: fraction, width: size.width, inset: inset))
            let plan = try XCTUnwrap(HistoricalChanceGeometry10868.barPlan(
                kind: .before, fraction: fraction, ticks: [], in: size, lineWidth: lineWidth), name)
            let bounds = try XCTUnwrap(plan.outlineBounds, name)
            let stroke = try XCTUnwrap(plan.outline, name)

            // The bound is the true extent: from zero to the value's own x, the
            // whole height — never widened, clamped or moved.
            XCTAssertEqual(bounds.minX, zeroX, accuracy: 1e-9, name)
            XCTAssertEqual(bounds.maxX, endX, accuracy: 1e-9, name)
            XCTAssertEqual(bounds.minY, 0, accuracy: 1e-9, name)
            XCTAssertEqual(bounds.height, size.height, accuracy: 1e-9, name)
            XCTAssertGreaterThan(bounds.width, 0, "\(name): a valid nonzero chance is not hidden")
            XCTAssertTrue(bounds.width < lineWidth || bounds.height < lineWidth, "\(name): narrower or shorter than the stroke")
            XCTAssertNil(plan.zeroMark, "\(name): only a genuine zero gets the zero cue")
            XCTAssertTrue(plan.track.contains(bounds), name)
            XCTAssertTrue(CGRect(origin: .zero, size: size).contains(bounds), "\(name): inside its own Canvas")

            // Too thin or too short for the inward stroke: stroked on the bar
            // itself, so the unclipped stroke would overdraw — the clip is what
            // keeps the ink to the true extent, and it fills it with no hole.
            XCTAssertEqual(stroke, bounds, name)
            XCTAssertFalse(bounds.contains(stroke.insetBy(dx: -lineWidth / 2, dy: -lineWidth / 2)), "\(name): unclipped would overdraw")
            let hole = stroke.insetBy(dx: lineWidth / 2, dy: lineWidth / 2)
            XCTAssertTrue(hole.isNull || hole.width <= 0 || hole.height <= 0, name)
            assertSameRect(Self.outlineInk(plan, lineWidth: lineWidth), bounds, name)

            // The checkpoint's solid bar of the same value has the same extent.
            let solid = try XCTUnwrap(HistoricalChanceGeometry10868.barPlan(
                kind: .checkpoint, fraction: fraction, ticks: [], in: size, lineWidth: lineWidth), name)
            XCTAssertEqual(solid.fill, bounds, name)
            XCTAssertNil(solid.outline, name)
            XCTAssertNil(solid.outlineBounds, name)
        }
    }

    // MARK: Layout the view consumes

    func testReadoutAndActualArrangementsAtCompactWideAndAccessibilitySizes() {
        XCTAssertEqual(HistoricalChanceGeometry10868.readoutArrangements(accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(HistoricalChanceGeometry10868.readoutArrangements(accessibilitySize: true), [.stacked])
        XCTAssertEqual(HistoricalChanceGeometry10868.actualArrangements(accessibilitySize: false, hasOutcome: true), [.sideBySide, .stacked])
        XCTAssertEqual(HistoricalChanceGeometry10868.actualArrangements(accessibilitySize: true, hasOutcome: true), [.stacked])
        XCTAssertEqual(HistoricalChanceGeometry10868.actualArrangements(accessibilitySize: false, hasOutcome: false), [.stacked])
    }

    @MainActor
    func testLayingOutAtCompactWideAndAccessibilitySizesFiresNoCallback() {
        var opened: [FieldMovementOpen10868] = []
        var expanded = 0
        var details = 0
        for c in [Self.rugby, Self.afl] {
            let view = HistoricalChanceResultPresentation10868(
                input: Self.input(c),
                onOpen: { opened.append($0) },
                onExpand: { expanded += 1 },
                onDetails: { details += 1 })
            let layouts: [(CGFloat, DynamicTypeSize)] = [(390, .large), (834, .large), (390, .accessibility3)]
            for (width, typeSize) in layouts {
                let host = hostForMeasurement(view, at: typeSize)
                host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                let size = host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude))
                XCTAssertTrue(size.height.isFinite && size.height > 0, "\(c.subject.name) \(width) \(typeSize)")
            }
        }
        XCTAssertTrue(opened.isEmpty)
        XCTAssertEqual(expanded, 0)
        XCTAssertEqual(details, 0)
    }

    // MARK: Actions and VoiceOver

    func testEndpointCallbacksHandBackTheExactOriginalAndOwnKeyAndNoCallbackIsStatic() throws {
        let france = Self.france
        let model = Self.model()
        let before = try XCTUnwrap(Self.side(model, .before))
        let later = try XCTUnwrap(Self.side(model, .checkpoint))
        XCTAssertEqual(model.openAction(before, canOpen: true), FieldMovementOpen10868(ref: france.ref, observation: france.key(.before)))
        XCTAssertEqual(model.openAction(later, canOpen: true), FieldMovementOpen10868(ref: france.ref, observation: france.key(.checkpoint)))
        XCTAssertEqual(model.hint(model.openAction(before, canOpen: true)), "Opens this trade in the history")

        // No callback: nothing acts and no hint pretends to.
        XCTAssertNil(model.openAction(before, canOpen: false))
        XCTAssertEqual(model.hint(nil), "")
        XCTAssertFalse(model.showsExpand(canExpand: false))
        XCTAssertNil(model.detailsLabel(canShowDetails: false))
        XCTAssertTrue(model.showsExpand(canExpand: true))
        XCTAssertEqual(model.detailsLabel(canShowDetails: true), "How to read this story")

        // A blank checkpoint key disables only that endpoint.
        var observations = Self.observed([france])
        let index = try XCTUnwrap(observations.firstIndex { $0.endpoint == .checkpoint })
        observations[index] = HistoricalChanceObservation10868(
            ref: france.ref, endpoint: .checkpoint, observation: observations[index].observation, key: "  ")
        let blankKey = Self.model(Self.input(readings: Self.admitted([france]), observations: observations))
        let keyless = try XCTUnwrap(Self.side(blankKey, .checkpoint))
        XCTAssertEqual(FieldChaseModel10868.figure(keyless.endpoint), "2%", "the figure stays")
        XCTAssertNil(keyless.key)
        XCTAssertNil(blankKey.openAction(keyless, canOpen: true))
        XCTAssertNotNil(blankKey.openAction(try XCTUnwrap(Self.side(blankKey, .before)), canOpen: true))

        // A side from an earlier input opens nothing once the reading changed.
        let moved = Team(
            scope: france.scope, ticker: france.ticker, name: "France", before: france.before,
            checkpoint: Trade(p: 0.05, t: 1_773_521_640, text: "5%", clock: "Mar 14, 9:54 PM CET · Kalshi"))
        let current = Self.model(Self.input(readings: Self.admitted([moved]), observations: Self.observed([moved])))
        XCTAssertNil(current.openAction(later, canOpen: true))
        XCTAssertEqual(current.openAction(try XCTUnwrap(Self.side(current, .checkpoint)), canOpen: true)?.observation, moved.key(.checkpoint))

        // A blank expand name or Details label draws no control.
        let input = Self.input()
        let unnamedInput = HistoricalChanceInput10868(
            scope: input.scope, catalogue: input.catalogue, subject: input.subject, readings: input.readings,
            observations: input.observations, actuals: input.actuals, scale: input.scale, phase: input.phase,
            copy: HistoricalChanceCopy10868(
                eyebrow: nil, title: input.copy.title, beforeLabel: input.copy.beforeLabel,
                checkpointLabel: input.copy.checkpointLabel, endpointUnavailable: input.copy.endpointUnavailable,
                beforeKey: input.copy.beforeKey, checkpointKey: input.copy.checkpointKey,
                graphicLabel: input.copy.graphicLabel, chanceUnplaced: input.copy.chanceUnplaced,
                offScale: input.copy.offScale, actualTitle: input.copy.actualTitle, actualLabel: input.copy.actualLabel,
                actualUnavailable: input.copy.actualUnavailable, context: nil, expandLabel: " ", expandHint: nil,
                detailsLabel: nil, detailsHint: nil, openHint: nil),
            unavailableWords: input.unavailableWords)
        let unnamed = Self.model(unnamedInput)
        XCTAssertFalse(unnamed.showsExpand(canExpand: true))
        XCTAssertNil(unnamed.detailsLabel(canShowDetails: true))
        XCTAssertEqual(unnamed.hint(unnamed.openAction(try XCTUnwrap(Self.side(unnamed, .before)), canOpen: true)), "")
    }

    func testSpokenSummariesNameTheSubjectBothClocksAndTheSeparateActual() throws {
        let model = Self.model()
        let before = try XCTUnwrap(Self.side(model, .before))
        XCTAssertEqual(model.endpointSummary(before), "France. Before match: 81%, Mar 14, 9:08 PM CET · Kalshi")
        XCTAssertEqual(
            model.chancesSummary,
            "France. Before match: 81%, Mar 14, 9:08 PM CET · Kalshi. Lowest minute-end chance: 2%, Mar 14, 9:53 PM CET · Kalshi")
        XCTAssertEqual(
            model.actualSummary,
            "ACTUAL RESULT. Reported final score: France 48–46 England, Retained ESPN final header; approved rugby reference. France won")
        XCTAssertEqual(
            model.summary,
            ["FRANCE’S CHANGING CHANCE", "France’s changing chance", model.chancesSummary, model.actualSummary,
             "Each chance is one dated trade. The score was reported separately."].joined(separator: ". "))

        // Absences are spoken with their labels; the actual keeps its panel words.
        let empty = Self.model(Self.input(readings: [], observations: [], actuals: []))
        XCTAssertEqual(
            empty.chancesSummary,
            "France. Before match: Not recorded for this comparison. Lowest minute-end chance: Not recorded for this comparison")
        XCTAssertEqual(empty.actualSummary, "ACTUAL RESULT. Reported final score: Final score not confirmed")
        XCTAssertFalse(empty.summary.contains("Won"))
    }
}
