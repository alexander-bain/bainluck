import XCTest
import SwiftUI
@testable import Bain_Luck

/// #4373 — the Evolution chart's leaderboard drew every probability with its
/// percent sign on a second line, because the `Prob` cell was 50pt holding a 24pt
/// mini bar, and 22pt is half of what `100%` needs.
///
/// ═══ WHAT EACH KIND OF TEST HERE IS WORTH ═══
///
/// **The width tests are the load-bearing ones.** The defect was an arithmetic
/// one — a column narrower than its contents — so the guards are arithmetic:
/// every string the row can draw, measured in the face it is drawn in, against
/// the column the model hands the view. Mutating the width formula (dropping the
/// header's ink, dropping the gutter, going back to a literal 50) fails them.
///
/// **The hosted-height tests carry a control, because on their own they would be
/// vacuous.** The shipped label is `lineLimit(1)`, so it CANNOT wrap: a "did it
/// wrap?" assertion against the production row passes even if the column is one
/// point wide. So the suite reproduces the pre-fix cell — 24pt bar, 50pt frame,
/// no line limit — and asserts THAT one wraps in the same camera. Without that
/// control the height assertions would be a green light wired to nothing, which
/// is the shape #4351's scan found and #4109 found again.
///
/// **What no test here can say** is that the name is legible at
/// `.accessibility5`; it is not, before or after. See the tail of
/// `EvolutionLeaderboardGeometry` and #4395.
@MainActor
final class EvolutionLeaderboardWidthTests: XCTestCase {

    // MARK: - Widths the app really has to draw at

    /// iPhone SE — the narrowest phone this lane sizes for.
    private let narrowPhone: CGFloat = 375
    /// iPhone 17.
    private let standardPhone: CGFloat = 402
    /// Wide enough that nothing can be forced to wrap, so a height measured here IS
    /// the one-line height — discovered rather than declared.
    private let unconstrained: CGFloat = 1200

    // MARK: - Fixtures

    /// A leaderboard shaped like production: an NFL futures market, where most
    /// deltas are absent and the names are long enough to be the thing competing
    /// for the width.
    private func productionShapedOutcomes() -> [TimelineOutcomeMeta] {
        [
            outcome(name: "Los Angeles Rams", prob: 0.14, change: nil),
            outcome(name: "Buffalo Bills", prob: 0.08, change: 0.015),
            outcome(name: "Baltimore Ravens", prob: 0.07, change: nil),
            outcome(name: "Los Angeles Chargers", prob: 0.055, change: -0.021),
            outcome(name: "Philadelphia Eagles", prob: 0.005, change: nil),
        ]
    }

    /// The same board once a favourite has been settled and a collapse is on it:
    /// `100%` is the widest probability the column can ever hold and `-100.0%` the
    /// widest delta.
    private func extremeOutcomes() -> [TimelineOutcomeMeta] {
        [
            outcome(name: "Los Angeles Rams", prob: 1.0, change: 1.0),
            outcome(name: "Buffalo Bills", prob: 0.0, change: -1.0),
        ]
    }

    /// 🔴 THE BOARD THAT LETS A HEADING FALL OUTSIDE ITS OWN COLUMN, and the most
    /// ordinary board there is: a futures market nobody has traded in a day, so
    /// every delta is `-` and every probability is one digit.
    ///
    /// Here because mutation found it. Dropping the header's ink from
    /// `columnWidth` — sizing each column to its VALUES alone — survived every
    /// other test in this file, since on any board with a `+1.5%` in it the values
    /// are wider than `24h` anyway. On this board the `24h` column would be about
    /// 10pt and its heading 21.
    private func untradedOutcomes() -> [TimelineOutcomeMeta] {
        [
            outcome(name: "Los Angeles Rams", prob: 0.08, change: nil),
            outcome(name: "Buffalo Bills", prob: 0.05, change: nil),
            outcome(name: "Baltimore Ravens", prob: 0.01, change: nil),
        ]
    }

    private func outcome(name: String, prob: Double, change: Double?) -> TimelineOutcomeMeta {
        var json: [String: Any] = ["name": name, "current_probability": prob]
        if let change { json["probability_change_24h"] = change }
        let data = try! JSONSerialization.data(withJSONObject: json)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(TimelineOutcomeMeta.self, from: data)
    }

    // MARK: - Measurement

    private func height<V: View>(
        of view: V, width: CGFloat, at size: DynamicTypeSize = .large
    ) -> CGFloat {
        let host = hostForMeasurement(view.frame(width: width), at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: 2000))
        window.rootViewController = host
        window.isHidden = false
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
        return host.sizeThatFits(
            in: CGSize(width: width, height: CGFloat.greatestFiniteMagnitude)).height
    }

    /// The width the view ASKS for, with nothing constraining it. Two of these,
    /// taken with different column models, say whether the view is really reading
    /// the model — see `testTheRowAndHeaderTakeTheirWidthsFromTheModel`.
    private func idealWidth<V: View>(of view: V, at size: DynamicTypeSize = .large) -> CGFloat {
        let host = hostForMeasurement(view, at: size)
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
    }

    private func row(
        _ outcome: TimelineOutcomeMeta, position: Int = 1,
        columns: EvolutionLeaderboardGeometry.Columns
    ) -> EvolutionLeaderboardRow {
        EvolutionLeaderboardRow(
            position: position, outcome: outcome, color: .red,
            isSelected: true, isHighlighted: true, columns: columns)
    }

    // MARK: - The acceptance: every probability fits its column, in full

    /// The whole issue, as arithmetic: at both phone widths and both ordinary type
    /// sizes, every string the `Prob` column can draw fits inside the `Prob`
    /// column.
    ///
    /// Both boards are checked, because they size the column differently — that is
    /// the point of measuring — and a fix that only worked on today's values would
    /// break on the first settled favourite.
    func testEveryProbabilityFitsItsColumnAtOrdinaryTypeSizes() {
        for size in [DynamicTypeSize.large, .xxxLarge] {
            for outcomes in [productionShapedOutcomes(), extremeOutcomes(), untradedOutcomes()] {
                let columns = EvolutionLeaderboardGeometry.columns(for: outcomes, at: size)
                for outcome in outcomes {
                    let label = EvolutionLeaderboardGeometry.probLabel(
                        (outcome.currentProbability ?? 0) * 100)
                    let ink = EvolutionLeaderboardGeometry.textWidth(
                        label, font: .probValue, typeSize: size)
                    XCTAssertLessThanOrEqual(
                        ink, columns.prob,
                        "\(label) needs \(ink)pt and the Prob column is \(columns.prob)pt at \(size)")
                }
                // The header sits over the same column and is drawn in a different
                // face; a column sized only to its values puts "Prob" outside it.
                let headerInk = EvolutionLeaderboardGeometry.textWidth(
                    "Prob", font: .header, typeSize: size)
                XCTAssertLessThanOrEqual(headerInk, columns.prob)
            }
        }
    }

    /// The same claim for the delta, which the issue asked to be checked "before it
    /// bites": today it holds `-` and `+1.5%`, and `-100.0%` is one settled
    /// favourite away.
    func testEveryDeltaFitsItsColumnAtOrdinaryTypeSizes() {
        for size in [DynamicTypeSize.large, .xxxLarge] {
            for outcomes in [productionShapedOutcomes(), extremeOutcomes(), untradedOutcomes()] {
                let columns = EvolutionLeaderboardGeometry.columns(for: outcomes, at: size)
                let change = try! XCTUnwrap(columns.change)
                for outcome in outcomes {
                    let label = EvolutionLeaderboardGeometry.changeLabel(
                        (outcome.probabilityChange24h ?? 0) * 100)
                    let ink = EvolutionLeaderboardGeometry.textWidth(
                        label, font: .changeValue, typeSize: size)
                    XCTAssertLessThanOrEqual(
                        ink, change,
                        "\(label) needs \(ink)pt and the 24h column is \(change)pt at \(size)")
                }
                XCTAssertLessThanOrEqual(
                    EvolutionLeaderboardGeometry.textWidth("24h", font: .header, typeSize: size),
                    change)
            }
        }
    }

    /// 🔴 THE DEFECT ITSELF, stated as the assertion that fails on master.
    ///
    /// The pre-fix cell gave the number whatever the 24pt bar and the 4pt gap left
    /// of 50pt. This is the arithmetic that produced a column of characters, and it
    /// is checked so that reinstating the bar inside the cell cannot be a quiet
    /// change.
    func testThePreFixCellCouldNotHoldTheNumberItDrew() {
        let availableToTheOldText = EvolutionLeaderboardGeometry.legacyColumnWidth - 24 - 4
        let ink = EvolutionLeaderboardGeometry.textWidth("100%", font: .probValue, typeSize: .large)
        XCTAssertGreaterThan(
            ink, availableToTheOldText,
            "if this ever stops being true the issue's premise has changed")
        XCTAssertGreaterThan(
            EvolutionLeaderboardGeometry.textWidth("14%", font: .probValue, typeSize: .large),
            availableToTheOldText,
            "14% is the value Alex photographed wrapping, not a worst case")
    }

    // MARK: - The name is no worse off — the trade the issue asked to be made on ink

    /// #4373's acceptance: "with the participant name no more truncated than it is
    /// today". The name gets whatever the two numeric columns do not, so that is
    /// the same claim as this one.
    ///
    /// On the board a reader actually meets it holds outright: the pair comes out
    /// NARROWER than the 100pt it replaces, so the name gains width in the same
    /// change that stops the number wrapping.
    func testTheNumericPairIsNarrowerThanTheFixedPairOnAProductionShapedBoard() {
        let columns = EvolutionLeaderboardGeometry.columns(
            for: productionShapedOutcomes(), at: .large)
        XCTAssertLessThan(
            columns.total, EvolutionLeaderboardGeometry.legacyPairWidth,
            "the name must not pay for the fix on today's data")
    }

    /// ⚠️ AND WHERE IT DOES NOT HOLD, BOUNDED RATHER THAN OMITTED. A board carrying
    /// BOTH a settled `100%` and a `-100.0%` collapse needs 109.6pt at `.large` —
    /// **9.6pt more than the fixed pair**, which is about half a character of the
    /// participant name, on the rarest board the leaderboard can draw.
    ///
    /// That is the honest cost of measuring instead of setting, and it is bounded
    /// here so that a future format change (a delta that grows a digit, a wider
    /// face) has to come past a test rather than past a paragraph. The strings
    /// themselves are deliberately unchanged — see
    /// `testTheLabelsAreExactlyWhatTheRowDrewBefore`; shortening `-100.0%` to
    /// `-100%` would buy the 9.6pt back and was not taken, because a wrap fix that
    /// quietly re-rounds a published number is two changes wearing one issue.
    func testTheExtremeBoardCostsTheNameUnderTenPoints() {
        let columns = EvolutionLeaderboardGeometry.columns(for: extremeOutcomes(), at: .large)
        XCTAssertLessThanOrEqual(
            columns.total, EvolutionLeaderboardGeometry.legacyPairWidth + 10)
        XCTAssertGreaterThan(
            columns.total, EvolutionLeaderboardGeometry.legacyPairWidth,
            "if this stops being true, say so in the geometry's comment — it currently "
            + "admits a cost that would no longer exist")
    }

    /// And the columns really are sized to content rather than set: a board of
    /// single-digit values with no deltas is narrower than one holding `100%` and
    /// `-100.0%`. A pair of literals would make these equal.
    func testColumnsAreSizedToTheStringsThisRenderDraws() {
        let quiet = EvolutionLeaderboardGeometry.columns(
            for: productionShapedOutcomes(), at: .large)
        let extreme = EvolutionLeaderboardGeometry.columns(for: extremeOutcomes(), at: .large)
        XCTAssertLessThan(quiet.prob, extreme.prob)
        XCTAssertLessThan(try! XCTUnwrap(quiet.change), try! XCTUnwrap(extreme.change))
    }

    // MARK: - Accessibility sizes: the delta leaves the screen, not the row

    /// Above `.xxxLarge` there is no arrangement in which a name, a probability and
    /// a delta fit on a 375pt row, so the delta is dropped and the probability
    /// keeps the space.
    func testTheDeltaColumnIsDroppedAtAccessibilitySizes() {
        for size in [DynamicTypeSize.accessibility1, .accessibility3, .accessibility5] {
            let columns = EvolutionLeaderboardGeometry.columns(
                for: productionShapedOutcomes(), at: size)
            XCTAssertNil(columns.change, "at \(size)")
            XCTAssertFalse(columns.drawsChange, "at \(size)")
        }
        // And it is still drawn at every size below that — the rule is a cliff at a
        // named boundary, not a slope somebody can drift.
        for size in [DynamicTypeSize.large, .xLarge, .xxLarge, .xxxLarge] {
            XCTAssertNotNil(
                EvolutionLeaderboardGeometry.columns(
                    for: productionShapedOutcomes(), at: size).change,
                "at \(size)")
        }
    }

    /// Dropping it buys the name room rather than spending it: at
    /// `.accessibility1`–`.accessibility3` the single remaining column is narrower
    /// than the fixed pair it replaces.
    func testTheNameIsBetterOffAtAccessibilitySizesThanItWasBefore() {
        for size in [DynamicTypeSize.accessibility1, .accessibility2, .accessibility3] {
            let columns = EvolutionLeaderboardGeometry.columns(
                for: productionShapedOutcomes(), at: size)
            XCTAssertLessThan(
                columns.total, EvolutionLeaderboardGeometry.legacyPairWidth, "at \(size)")
        }
    }

    /// ⚠️ AND THE ONE PLACE IT DOES NOT: at `.accessibility5` the probability alone
    /// is wider than the old pair, so the name is worse off than it was.
    ///
    /// This test exists to keep that admission true rather than to defend it. The
    /// row needs to reflow at those sizes (#4395); if someone ships that, this test
    /// fails and the comment in `EvolutionLeaderboardGeometry` is what they should
    /// come and delete.
    func testTheKnownResidueAtTheLargestAccessibilitySizeIsStillTrue() {
        let columns = EvolutionLeaderboardGeometry.columns(
            for: productionShapedOutcomes(), at: .accessibility5)
        XCTAssertGreaterThan(columns.total, EvolutionLeaderboardGeometry.legacyPairWidth)
    }

    /// The delta leaves the drawing and not the row: VoiceOver still gets it, and
    /// it gets it as a sentence rather than as the dash the eye reads.
    func testTheSpokenRowKeepsTheDeltaTheScreenDrops() {
        XCTAssertEqual(
            EvolutionLeaderboardGeometry.spokenChange(0), "unchanged over 24 hours")
        XCTAssertEqual(
            EvolutionLeaderboardGeometry.spokenChange(1.5), "+1.5% over 24 hours")
        XCTAssertEqual(
            EvolutionLeaderboardGeometry.spokenChange(-12.34), "-12.3% over 24 hours")
    }

    // MARK: - The drawn string and the measured string are one call

    /// A column sized against `14%` while the row draws `14.0%` is this defect
    /// again, so the formatters live in the geometry and the view calls them. These
    /// pin the formats the pre-fix row produced: the fix moved the strings, it did
    /// not change any of them.
    func testTheLabelsAreExactlyWhatTheRowDrewBefore() {
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(100), "100%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(14.4), "14%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(14.6), "15%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(0.5), "0.5%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(0), "0%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(1), "1%")

        XCTAssertEqual(EvolutionLeaderboardGeometry.changeLabel(0), "-")
        XCTAssertEqual(EvolutionLeaderboardGeometry.changeLabel(1.5), "+1.5%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.changeLabel(-12.34), "-12.3%")
    }

    // MARK: - Hosted: the row draws on one line, and the camera can see when it does not

    /// 🎥 THE CONTROL. The pre-fix cell, rebuilt, in the same camera as the
    /// assertion below it: a 24pt bar and a number in a 50pt box with nothing to
    /// stop it wrapping. It has to come out TALLER than one line, or the camera is
    /// not one that can see this defect and nothing measured with it means anything.
    func testTheCameraSeesThePreFixCellWrap() {
        let oneLine = height(of: preFixProbCell(width: unconstrained), width: unconstrained)
        let asShipped = height(of: preFixProbCell(width: 50), width: unconstrained)
        XCTAssertGreaterThan(
            asShipped, oneLine + 1,
            "the pre-fix 50pt cell must measure taller than one line, or this suite's "
            + "height assertions are wired to nothing")
    }

    /// And the row as shipped does not: at both phone widths, at both ordinary type
    /// sizes, the whole row is the height of a row whose text cannot wrap.
    func testTheShippedRowIsOneLineAtEveryPhoneWidth() {
        for size in [DynamicTypeSize.large, .xxxLarge] {
            let outcomes = extremeOutcomes()
            let columns = EvolutionLeaderboardGeometry.columns(for: outcomes, at: size)
            let unwrappable = height(
                of: row(outcomes[0], columns: columns), width: unconstrained, at: size)
            for width in [narrowPhone, standardPhone] {
                XCTAssertEqual(
                    height(of: row(outcomes[0], columns: columns), width: width, at: size),
                    unwrappable, accuracy: 0.5,
                    "row is taller at \(width)pt / \(size) than it is unconstrained")
            }
        }
    }

    /// The header is the same two widths as the rows under it, by construction —
    /// it takes the same `Columns` value. This checks the construction holds after
    /// layout: header and row put their trailing edges in the same place.
    func testTheHeaderIsTheSameHeightRegardlessOfWidthToo() {
        let columns = EvolutionLeaderboardGeometry.columns(for: extremeOutcomes(), at: .large)
        let unwrappable = height(
            of: EvolutionLeaderboardHeader(columns: columns), width: unconstrained)
        for width in [narrowPhone, standardPhone] {
            XCTAssertEqual(
                height(of: EvolutionLeaderboardHeader(columns: columns), width: width),
                unwrappable, accuracy: 0.5)
        }
    }

    // MARK: - The view really reads the model

    /// 🔴 THE MUTANT THAT SURVIVED EVERYTHING ELSE IN THIS FILE, and it is this
    /// issue coming back: put `.frame(width: 50)` on the row's probability cell
    /// again and every test above still passes. They measure the MODEL, and the
    /// model is still right — it is the view that has stopped listening. (At
    /// `.large` a bare 50 even fits `100%`, so nothing looks wrong until
    /// `.xxxLarge`, where the number is 59.1pt and `lineLimit(1)` turns the old
    /// wrap into a quiet truncation instead.)
    ///
    /// So this asks the view a question only a view that reads the model can
    /// answer: hand it a column model 20pt and 30pt wider, and see whether the
    /// width it asks for grows by 50. A literal does not move.
    func testTheRowAndHeaderTakeTheirWidthsFromTheModel() {
        let outcomes = extremeOutcomes()
        let base = EvolutionLeaderboardGeometry.columns(for: outcomes, at: .large)
        let widened = EvolutionLeaderboardGeometry.Columns(
            prob: base.prob + 20, change: try! XCTUnwrap(base.change) + 30)

        XCTAssertEqual(
            idealWidth(of: row(outcomes[0], columns: widened))
                - idealWidth(of: row(outcomes[0], columns: base)),
            50, accuracy: 0.5,
            "the row's numeric cells are not sized from the column model")

        XCTAssertEqual(
            idealWidth(of: EvolutionLeaderboardHeader(columns: widened))
                - idealWidth(of: EvolutionLeaderboardHeader(columns: base)),
            50, accuracy: 0.5,
            "the header's cells are not sized from the column model")
    }

    /// And the row spends nothing at all on the column it is told not to draw: a
    /// dropped delta must take its spacing with it, not leave a zero-width gap
    /// where the reader's name could be.
    func testADroppedDeltaColumnCostsTheRowNothing() {
        let outcomes = extremeOutcomes()
        let base = EvolutionLeaderboardGeometry.columns(for: outcomes, at: .large)
        let dropped = EvolutionLeaderboardGeometry.Columns(prob: base.prob, change: nil)
        let saved = idealWidth(of: row(outcomes[0], columns: base))
            - idealWidth(of: row(outcomes[0], columns: dropped))
        XCTAssertGreaterThan(
            saved, try! XCTUnwrap(base.change),
            "dropping the column should free its width AND the 6pt gap beside it")
    }

    /// The pre-fix `Prob` cell, verbatim from master, for the control above.
    private func preFixProbCell(width: CGFloat) -> some View {
        HStack(spacing: 4) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2).fill(Color.gray.opacity(0.3))
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.red.opacity(0.6))
                        .frame(width: geo.size.width * 0.14)
                }
            }
            .frame(width: 24, height: 4)

            Text("14%")
                .font(.subheadline)
                .fontWeight(.semibold)
                .monospacedDigit()
        }
        .frame(width: width, alignment: .trailing)
    }
}
