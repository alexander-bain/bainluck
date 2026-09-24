import SwiftUI
import XCTest
@testable import Bain_Luck

/// #8109 — the futures chart's participant table stops printing 101.
///
/// THE SPECIMEN, from production: `GET /api/futures/61993906/probability-timeline`
/// ("Republican Senate odds dip to 25% by October 31?"), read 2026-09-22, two
/// outcomes, `No 0.925` and `Yes 0.075`. Photographed in the iPhone simulator at
/// 16:14 PDT:
///
///     #  Participant   Prob   24h
///     1  No             93%    -
///     2  Yes             8%    -      <- 101%
///
/// An exact complement quoted on the venues' half-cent grid, so both sides sat on
/// the `.5` rounding boundary at once and `probLabel`, which rounds each outcome
/// on its own, rounded both up. Measured on production the same day: **7,362 open
/// two-outcome complement markets print a sum other than 100 in this table —
/// 7,102 at 101, 173 at 99, 549 of them tier 1.**
///
/// This is a FOURTH renderer on a page #8097 had already fixed three of, and it
/// sits directly above the All Outcomes list that ship makes read `93% / 7%`. The
/// reader-visible cost is one screen answering one question two ways.
///
/// ## What this suite pins that is not the arithmetic
///
/// The fix is not "make two numbers add up". Three things it must NOT do are
/// asserted as hard as the sum:
///
/// - **`probLabel`'s sub-one-percent rule still wins** (#5899). A card-level
///   integer may not turn a priced `0.5%` into `0%`.
/// - **The decision is taken over the WHOLE SERVED FIELD**, never over the rows on
///   screen — which are filtered (`Field`) and truncated (`Top N`).
/// - **The measured string and the drawn string stay one call** (#4373), so the
///   column cannot be sized on a number the row no longer draws.
final class ChartTableSumsTo100_8109Tests: XCTestCase {

    // MARK: - Specimens

    /// The served field of `61993906` at the minute it was photographed, in the
    /// order the endpoint returned it.
    private func specimen() -> [TimelineOutcomeMeta] {
        [outcome(id: 234_022_578, "No", 0.925), outcome(id: 234_022_577, "Yes", 0.075)]
    }

    private func outcome(
        id: Int?, _ name: String, _ probability: Double?, change: Double? = nil
    ) -> TimelineOutcomeMeta {
        // Decoded rather than constructed: `TimelineOutcomeMeta` is `Decodable`
        // with a `@TolerantNumeric` wrapper and a hand-written key for
        // `probabilityChange24H`, so building one by hand would be a model of the
        // model. A malformed fake reaches a helper's unknown branch and reads
        // exactly like a principled refusal.
        var json: [String: Any] = ["name": name]
        if let id { json["id"] = id }
        if let probability { json["current_probability"] = probability }
        if let change { json["probability_change_24h"] = change }
        let data = try! JSONSerialization.data(withJSONObject: json)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(TimelineOutcomeMeta.self, from: data)
    }

    /// What the table actually draws for a served field, top row first — the same
    /// two calls `EvolutionLeaderboardRow` makes.
    private func drawn(_ served: [TimelineOutcomeMeta]) -> [String] {
        let percents = EvolutionLeaderboardGeometry.renderedPercents(forServedField: served)
        return served.enumerated().map { index, o in
            EvolutionLeaderboardGeometry.probLabel(
                o.currentProbability.map { $0 * 100 }, renderedPercent: percents[index])
        }
    }

    private func wholeNumbers(_ labels: [String]) -> [Int] {
        labels.compactMap { Int($0.replacingOccurrences(of: "%", with: "")) }
    }

    // MARK: - The defect

    func testTheSpecimenAddsUpToOneHundred() {
        let labels = drawn(specimen())
        XCTAssertEqual(labels, ["93%", "7%"])
        XCTAssertEqual(wholeNumbers(labels).reduce(0, +), 100)
    }

    /// The pre-fix behaviour, kept as the BEFORE half so the test above cannot
    /// quietly become true for a reason other than this fix. `probLabel` with no
    /// decision is the rule the table used on 2026-09-22, and it still prints 101
    /// — that is correct, and it is why the decision has to be handed in.
    func testWithoutTheDecisionTheSameRowsStillPrintOneHundredAndOne() {
        let undecided = specimen().map {
            EvolutionLeaderboardGeometry.probLabel($0.currentProbability.map { $0 * 100 })
        }
        XCTAssertEqual(undecided, ["93%", "8%"])
        XCTAssertEqual(wholeNumbers(undecided).reduce(0, +), 101)
    }

    /// The 99 half of the measured population — 173 markets — because a fix aimed
    /// only at 101 can miss it entirely. `0.60 / 0.39` sums to 0.99, inside the
    /// contract's band, and neither side is near a rounding boundary: the table
    /// simply printed 60 + 39 and lost a point that exists.
    ///
    /// ⚠️ The pair this arm was FIRST written with, `0.545 / 0.445`, does not
    /// reproduce it — both sides sit on `.5` and round away from zero to 55 + 45,
    /// which already sums to 100. The 99 case is the one where the served field is
    /// short of 1.0, not the one where the rounding is delicate.
    func testAPairThatPrintedNinetyNineAlsoAddsUpToOneHundred() {
        let served = [outcome(id: 1, "Under", 0.60), outcome(id: 2, "Over", 0.39)]
        let labels = drawn(served)
        XCTAssertEqual(wholeNumbers(labels).reduce(0, +), 100)
        XCTAssertEqual(
            wholeNumbers(
                served.map {
                    EvolutionLeaderboardGeometry.probLabel($0.currentProbability.map { $0 * 100 })
                }
            ).reduce(0, +),
            99,
            "the BEFORE of this arm: if this stops being 99 the specimen has gone stale")
    }

    // MARK: - The leader keeps its own number

    /// A sum-only guard is satisfied by moving EITHER side, and moving the leader
    /// is the wrong one: the derived point belongs on the side nobody is quoting.
    /// `No` is quoted at 92.5 and must print 93, not 92.
    func testTheDerivedPointLandsOnTheUnderdogAndNotTheLeader() {
        XCTAssertEqual(drawn(specimen()), ["93%", "7%"])
    }

    /// And the leader is decided by PROBABILITY, not by arrival order. If the
    /// endpoint ever served ascending, taking index 0 as the headline would keep
    /// the underdog exact and move the favourite — the one outcome of this fix
    /// nobody would notice on screen.
    func testTheHeadlineIsTheFavouriteEvenWhenTheFieldArrivesAscending() {
        let ascending = [outcome(id: 234_022_577, "Yes", 0.075),
                         outcome(id: 234_022_578, "No", 0.925)]
        XCTAssertEqual(drawn(ascending), ["7%", "93%"],
                       "the favourite keeps 93 wherever in the payload it arrived")
    }

    // MARK: - The decision is over the served field, not the rows on screen

    /// A `Top N` chip and a `Field` filter hide rows. Neither may REPRICE the rows
    /// it leaves — the same refusal #8097 made for the sort control, and a sharper
    /// one here, because a filtered subset can become a complement pair the served
    /// field never was.
    ///
    /// `A 0.55 / B 0.44 / Field 0.01` displays two rows summing to 0.99, which is
    /// inside the contract's band. Decided over the subset it "corrects" to
    /// **56 / 44** — printing 56 for an outcome the venue quotes at 0.55, to buy a
    /// sum, using a point that belongs to an outcome named in the chart beside it.
    /// Decided over the served field it is a three-way field, so nothing moves.
    func testHidingTheFieldRowDoesNotRepriceTheRowsThatRemain() {
        let served = [outcome(id: 1, "A", 0.55), outcome(id: 2, "B", 0.44),
                      outcome(id: 3, "Field", 0.01)]
        let percents = EvolutionLeaderboardGeometry.renderedPercents(forServedField: served)
        let onScreen = zip(served, percents).filter { $0.0.name != "Field" }

        XCTAssertEqual(
            onScreen.map { row -> String in
                EvolutionLeaderboardGeometry.probLabel(
                    row.0.currentProbability.map { $0 * 100 }, renderedPercent: row.1)
            },
            ["55%", "44%"],
            "a three-way field is not a complement pair and must not be normalised")

        // The trap, stated positively: deciding over what is DISPLAYED gives a
        // different answer, so this assertion has something to fail against.
        let overTheSubset = renderedCardPercents(onScreen.map { $0.0.currentProbability })
        XCTAssertEqual(overTheSubset, [56, 44],
                       "if this ever equals [55, 44] the subset stopped being a pair "
                       + "and the test above proves nothing")
    }

    /// The same refusal for the `Top N` chip: a truncated view of a wide field must
    /// not turn its top two rows into a pair.
    func testTruncatingToTheTopTwoDoesNotInventAComplementPair() {
        let served = [outcome(id: 1, "A", 0.6), outcome(id: 2, "B", 0.39),
                      outcome(id: 3, "C", 0.005), outcome(id: 4, "D", 0.005)]
        let percents = EvolutionLeaderboardGeometry.renderedPercents(forServedField: served)
        XCTAssertEqual(percents, [60, 39, 1, 1],
                       "every row is rounded on its own; a four-way field is not a pair")
        XCTAssertEqual(renderedCardPercents(Array(served.prefix(2)).map(\.currentProbability)),
                       [61, 39],
                       "and the top two ARE a pair by the band, which is the hazard")
    }

    // MARK: - What must not move

    /// #5899's pin, in the direction that costs the sum. `0.995 / 0.005` decides
    /// `[100, 0]`, and printing `0%` for an outcome the venue is still pricing is a
    /// false claim. The decimal wins, the pair reads `100%` / `0.5%`, and that is
    /// the honest answer even though it does not add to 100.
    func testASubOnePercentOutcomeKeepsItsDecimalAgainstTheCardLevelInteger() {
        let served = [outcome(id: 1, "Yes", 0.995), outcome(id: 2, "No", 0.005)]
        XCTAssertEqual(EvolutionLeaderboardGeometry.renderedPercents(forServedField: served),
                       [100, 0],
                       "the card-level decision really does say 0 here")
        XCTAssertEqual(drawn(served), ["100%", "0.5%"],
                       "and the <1% rule overrides it — a priced outcome is never 0%")
    }

    /// The same pin through the spoken form, which is a different call site and so
    /// a different chance to get it wrong.
    func testTheSpokenRowAgreesWithTheDrawnRow() {
        let served = specimen()
        let percents = EvolutionLeaderboardGeometry.renderedPercents(forServedField: served)
        for (index, o) in served.enumerated() {
            let points = o.currentProbability.map { $0 * 100 }
            XCTAssertEqual(
                EvolutionLeaderboardGeometry.spokenProb(points, renderedPercent: percents[index]),
                EvolutionLeaderboardGeometry.probLabel(points, renderedPercent: percents[index]),
                "VoiceOver may not read a different number than the screen draws")
        }
        XCTAssertEqual(
            EvolutionLeaderboardGeometry.spokenProb(7.5, renderedPercent: 7), "7%",
            "and it is the DECIDED number, not the row's own rounding")
        XCTAssertEqual(EvolutionLeaderboardGeometry.spokenProb(nil, renderedPercent: 7),
                       "probability not available",
                       "a decision may not manufacture a probability we do not have")
    }

    /// An absent probability is still absent. A card-level integer cannot conjure
    /// one — `renderedCardPercents` never fires on a field with a `nil` in it, and
    /// the label refuses independently.
    func testAnAbsentProbabilityStaysAbsent() {
        let served = [outcome(id: 1, "Yes", 0.925), outcome(id: 2, "No", nil)]
        XCTAssertEqual(EvolutionLeaderboardGeometry.renderedPercents(forServedField: served),
                       [93, nil])
        XCTAssertEqual(drawn(served), ["93%", absentProbabilityMarker],
                       "the nil row draws the absent marker, never a percent")
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(nil, renderedPercent: 7),
                       absentProbabilityMarker)
    }

    /// A pair already summing to 100 does not move. The fix is invisible to the
    /// markets that were right.
    func testAPairThatWasAlreadyRightIsUntouched() {
        let served = [outcome(id: 1, "Yes", 0.93), outcome(id: 2, "No", 0.07)]
        XCTAssertEqual(drawn(served), ["93%", "7%"])
        XCTAssertEqual(
            drawn(served),
            served.map {
                EvolutionLeaderboardGeometry.probLabel($0.currentProbability.map { $0 * 100 })
            },
            "identical to the undecided rule, which is what 'untouched' means")
    }

    /// A settled winner still reads `100%` and its loser `0%`. #5899's `>99%` end
    /// deliberately did not come along and neither does anything here.
    func testASettledMarketStillReadsOneHundredAndZero() {
        let served = [outcome(id: 1, "Yes", 1.0), outcome(id: 2, "No", 0.0)]
        XCTAssertEqual(drawn(served), ["100%", "0%"])
    }

    // MARK: - The measured string is the drawn string (#4373)

    /// The column is sized by `columns(for:at:renderedPercents:)` and the row is
    /// drawn by `probLabel`. If the sizing call does not carry the decision, a
    /// board holding a decided `100%` gets measured as `99%` and clips a digit —
    /// this file's original defect arriving through the new fix.
    /// ⚠️ THE SPECIMEN THIS ARM WAS FIRST WRITTEN WITH PROVED NOTHING. `0.995 /
    /// 0.005` decides `[100, 0]`, and `Int(99.5.rounded())` is ALSO 100, so both
    /// sizings measured the identical string and the assertion compared a number
    /// with itself. A width test needs a board where the decision changes the
    /// WIDEST string, and the integer only ever moves by one — so the specimen has
    /// to straddle a digit-count boundary. `0.9955 / 0.0145` sums to 1.01, the top
    /// of the band: rounded alone the leader is `100%`, decided it is `99%`.
    func testTheColumnIsSizedOnTheStringsTheDecisionMakesTheRowsDraw() {
        let served = [outcome(id: 1, "Yes", 0.9955), outcome(id: 2, "No", 0.0145)]
        let percents = EvolutionLeaderboardGeometry.renderedPercents(forServedField: served)

        XCTAssertEqual(drawn(served), ["99%", "1%"], "the strings the rows will draw")

        let sized = EvolutionLeaderboardGeometry.columns(
            for: served, at: .large, renderedPercents: percents)

        XCTAssertEqual(
            sized.prob,
            EvolutionLeaderboardGeometry.columns(
                probs: ["99%", "1%"], changes: ["-", "-"], typeSize: .large).prob,
            "the column is measured on the strings the decision makes the rows draw")
        XCTAssertNotEqual(
            sized.prob,
            EvolutionLeaderboardGeometry.columns(
                probs: ["100%", "1%"], changes: ["-", "-"], typeSize: .large).prob,
            "…and NOT on the strings they would have drawn without it — if these "
            + "are equal the sizing call is ignoring its own argument")
    }

    /// And the control for that assertion: on a board the decision does not move,
    /// the two sizings are identical. Without this, the test above passes for a
    /// sizing call that merely widens everything it is handed.
    func testSizingIsUnchangedOnABoardTheDecisionDoesNotMove() {
        let served = [outcome(id: 1, "Yes", 0.93, change: 0.01),
                      outcome(id: 2, "No", 0.07, change: -0.01)]
        let percents = EvolutionLeaderboardGeometry.renderedPercents(forServedField: served)
        XCTAssertEqual(
            EvolutionLeaderboardGeometry.columns(
                for: served, at: .large, renderedPercents: percents).prob,
            EvolutionLeaderboardGeometry.columns(
                for: served, at: .large, renderedPercents: []).prob)
    }

    // MARK: - The view still ASKS for the decision

    /// 🔴 EVERY ASSERTION ABOVE THIS ONE PASSES WITH THE DEFECT FULLY RESTORED.
    ///
    /// They exercise `probLabel` and `renderedPercents(forServedField:)` directly.
    /// The wiring that carries one to the other lives in a `some View` body and in
    /// computed properties, which no behavioural test in this target can reach —
    /// so `drawn-row-rounds-alone`, the first mutant of
    /// `tools/n300-8109-chart-table-mutants.sh` and the literal defect this issue
    /// is about, **SURVIVED** the suite's first complete run. The helpers being
    /// correct proves nothing about whether the row calls them.
    ///
    /// This is the third time the family has learned it (#8035's
    /// `caller-filters-the-field-again`, #8097's `list-passes-nil-to-every-row`),
    /// and the scan is the established answer — #7285's
    /// `testTheRowCarriesTheOptionalToBothLabels` guards this same file this way.
    ///
    /// ⚠️ **COUNTED, NOT FOUND.** #8097's battery caught a scan that asserted
    /// `contains("renderedPercent: percent")` while a sibling branch one line below
    /// spelled the same substring: an anchor two call sites can satisfy only ever
    /// proves ONE of them is alive. Each wiring below is therefore pinned by an
    /// exact, unique string, and the reverted spellings are asserted ABSENT — a
    /// positive scan alone goes stale the moment someone writes the call a second
    /// way.
    func testTheRowAndTheGridStillAskForTheDecision() throws {
        let source = try String(contentsOf: viewSource(), encoding: .utf8)

        XCTAssertTrue(source.contains("struct EvolutionLeaderboardRow"),
                      "this scan no longer holds the thing it aims at — re-aim it")

        // The six wirings, each the subject of one mutant, each pinned by an EXACT
        // COUNT.
        //
        // ⚠️ The obvious anchor for the first two is `probPct, renderedPercent:
        // renderedPercent))` — and it occurs TWICE, because the spoken call ends
        // the same way inside its string interpolation. Reverting the drawn row
        // alone would leave that substring present and a `contains` scan green on
        // the literal defect. Counting is what makes each site prove itself.
        let required: [(String, Int, String)] = [
            // #8429 moved the drawn number into the row's `numbers` builder, shared
            // by its one-line and two-line arrangements — still ONE call site.
            ("EvolutionLeaderboardGeometry.probLabel(\n            probPct, renderedPercent: renderedPercent))",
             1, "the DRAWN number went back to rounding alone — this is the defect"),
            ("EvolutionLeaderboardGeometry.spokenProb(probPct, renderedPercent: renderedPercent)",
             1, "the SPOKEN number went back to rounding alone; no screenshot catches that"),
            ("renderedPercent: percents[index])",
             1, "the list stopped feeding the rows their decision"),
            ("at: dynamicTypeSize, renderedPercents: percents)",
             1, "the COLUMN is sized without the decision — #4373 clips a digit"),
            ("renderedPercents(forServedField: data?.outcomes ?? [])",
             1, "the decision moved off the SERVED field onto the rows on screen"),
            ("servedRenderedPercents[row.servedIndex]",
             1, "the lookup stopped using the served index"),
        ]
        for (needle, expected, why) in required {
            XCTAssertEqual(source.components(separatedBy: needle).count - 1, expected,
                           "\(why) — expected \(expected)x: `\(needle)`")
        }

        // The reverted spellings, absent. Without these the scan passes for a file
        // that calls BOTH ways, which is how a half-revert hides.
        let forbidden: [(String, String)] = [
            ("probLabel(\n                probPct))", "the drawn row's un-overridden call is back"),
            ("spokenProb(probPct))", "the spoken row's un-overridden call is back"),
            ("renderedPercent: nil)", "a row is being handed a hard-coded nil decision"),
            ("at: dynamicTypeSize, renderedPercents: [])", "the grid is sized on no decision"),
        ]
        for (needle, why) in forbidden {
            XCTAssertFalse(source.contains(needle), "\(why) — found: `\(needle)`")
        }
    }

    /// The scan above is only worth its assertions if it is reading the file it
    /// thinks it is. A scan over a path that does not resolve reads `""`, every
    /// `contains` is false, every `XCTAssertFalse` passes, and half the test
    /// silently convicts nothing.
    func testTheScanIsReadingTheRealViewFile() throws {
        let source = try String(contentsOf: viewSource(), encoding: .utf8)
        XCTAssertGreaterThan(source.count, 10_000,
                             "EvolutionChartView.swift is a large file; a short read is a bad path")
        XCTAssertTrue(source.contains("private var displayedRows"),
                      "the file read does not contain the property the fix added")
    }

    private func viewSource() -> URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Components/EvolutionChartView.swift")
    }

    // MARK: - The page answers its own question once

    /// The whole reason this issue exists: four renderers on one screen each
    /// rounded alone. This table now takes its integer from
    /// `renderedCardPercents` — the shared card rule of
    /// `contracts/rendered_percent.json` (#2060) that the Discover futures card
    /// already calls on master (#8035) — rather than from a fourth local rule.
    ///
    /// Asserted as "the printed integers ARE the contract's answer", which a local
    /// re-round of any kind breaks. The All Outcomes list one inch below reaches
    /// the same answer through `percentNumber` under #8097, which is a separate
    /// sha; this arm does not depend on it having landed.
    func testTheTablesIntegersAreTheSharedCardRulesAnswer() {
        let served = specimen()
        XCTAssertEqual(
            EvolutionLeaderboardGeometry.renderedPercents(forServedField: served),
            renderedCardPercents(served.map(\.currentProbability)),
            "a fourth local rounding rule on this page is the defect")
        XCTAssertEqual(drawn(served), ["93%", "7%"])
    }
}
