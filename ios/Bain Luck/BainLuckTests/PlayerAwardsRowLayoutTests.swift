import XCTest
import SwiftUI
@testable import Bain_Luck

/// #4109 — "Mike Trout's Season Futures render the market names one character per
/// line (a label column ~1 char wide)", Alex, 2026-09-08.
///
/// Two defects share that row and only one of them is the wrap:
///
/// 1. Every sibling in the awards `HStack` is fixed width except the label, so an
///    overrunning row compresses the label, and a `Text` with no `lineLimit`
///    compresses by **wrapping**. At about a character of width it wraps a
///    character at a time.
/// 2. The label is `.font(.system(size: 9))` — a POINT size. At accessibility
///    sizes the player's name above it triples and the market name does not move,
///    so the acceptance ("readable at default AND accessibility text sizes")
///    could never have been met by a `lineLimit` change.
///
/// The fixtures are the real payload of `/api/events/15308048/related-futures`,
/// read 2026-09-09: Mike Trout carries **five** tier-3 awards on the away side and
/// Garrett Crochet three on the home side. That matters — the row's own output
/// looks capped at two, and it is not capped at all.
final class PlayerAwardsRowLayoutTests: XCTestCase {

    // MARK: - Fixtures

    private func award(
        _ label: String, _ probability: Double?, outcome: String = "Mike Trout", id: Int = 1
    ) throws -> (label: String, prob: Double, future: RelatedFuture) {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let json = """
        {"market_id": \(id), "market_name": "\(label)", "outcome_id": \(id),
         "outcome_name": "\(outcome)",
         "probability": \(probability.map { "\($0)" } ?? "null"), "market_tier": 3}
        """
        let future = try dec.decode(RelatedFuture.self, from: Data(json.utf8))
        return (label: label, prob: probability ?? 0, future: future)
    }

    /// Mike Trout as production serves him: five tier-3 awards, longest label
    /// "AL Comeback Player of the Year".
    private func troutsAwards() throws -> [(label: String, prob: Double, future: RelatedFuture)] {
        try [
            award("AL MVP", 0.0068, id: 1),
            award("AL Hank Aaron Award", 0.0051, id: 2),
            award("AL Comeback Player of the Year", 0.0325, id: 3),
            award("AL MVP", 0.0068, id: 4),
            award("AL Comeback Player of the Year", 0.0325, id: 5),
        ]
    }

    /// The common shape: two awards, both short.
    private func twoAwards() throws -> [(label: String, prob: Double, future: RelatedFuture)] {
        try [award("AL MVP", 0.0068, id: 1), award("AL Hank Aaron Award", 0.0051, id: 2)]
    }

    // MARK: - Measuring

    /// The width the awards row would take if nothing constrained it.
    @MainActor
    private func naturalWidth(
        _ awards: [(label: String, prob: Double, future: RelatedFuture)],
        at size: DynamicTypeSize = .large
    ) -> CGFloat {
        let host = hostForMeasurement(PlayerAwardsRow(awards: awards), at: size)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
    }

    /// What it actually comes out as inside `width`.
    @MainActor
    private func size(
        _ awards: [(label: String, prob: Double, future: RelatedFuture)],
        in width: CGFloat, at size: DynamicTypeSize = .large
    ) -> CGSize {
        let host = hostForMeasurement(PlayerAwardsRow(awards: awards), at: size)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: width, height: CGFloat.greatestFiniteMagnitude))
    }

    /// What `awardPlayerRow` actually leaves the awards on the narrowest phone.
    ///
    /// 🔴 EVERY TERM IS TRACED TO THE LINE THAT SPENDS IT. #4199 spent a whole
    /// ship on an *assumed* content width — `375 − 32`, which measured 335 pt,
    /// passed its own test, and was ~50 pt wrong, in the direction that reads as
    /// a pass. So:
    ///
    /// ```
    ///  375   iPhone SE, the narrowest phone
    ///  -32   EventDetailView's `.padding(.horizontal)` on the section stack
    ///  -32   the Season Futures card's own `.padding()`
    ///  =311  the LazyVGrid's container. `GridItem(.adaptive(minimum: 280))`
    ///        gives ONE column here, so the cell is the whole 311
    ///  -16   awardPlayerRow's `.padding(.horizontal, 8)`
    ///  -28   the headshot
    ///   -8   the HStack spacing beside it
    ///  =259
    /// ```
    ///
    /// The trailing `Spacer()` takes what is left over and cannot take any of
    /// this: it collapses to zero before the row is squeezed.
    private let phoneAwardsWidth: CGFloat = 259

    // MARK: - The defect

    /// The row Alex photographed, stated as a measurement.
    @MainActor
    func testTroutsAwardsCannotFitOneLineOnAPhone() throws {
        let trout = try troutsAwards()
        XCTAssertEqual(trout.count, 5, "precondition: the fixture is the real five")

        let wanted = naturalWidth(trout)
        XCTAssertGreaterThan(
            wanted, phoneAwardsWidth,
            "five awards want \(wanted) pt on one line and the row has "
            + "\(phoneAwardsWidth) — wider than the whole 375 pt screen, in fact. "
            + "This is the overrun that made the only compressible child, the "
            + "label, wrap by the character (#4109)")
        XCTAssertGreaterThan(
            wanted, 375,
            "and it is not close: no arrangement of a phone can give this row "
            + "\(wanted) pt, so the reflow is forced rather than chosen")
    }

    /// 🔴 THE CAP THE ROW LOOKS LIKE IT HAS DOES NOT EXIST.
    ///
    /// native/082 reproduced this and found no rendered row drawing more than two
    /// awards, and reasonably wondered where the other nine of Trout's markets
    /// were going. They are going to the other categories: `awardPlayerRow` draws
    /// every TIER-3 award and most players have two. Nothing truncates the list,
    /// so a fix that assumed a cap would have been building on air.
    @MainActor
    func testTheRowDrawsEveryAwardItIsGiven() throws {
        let two = naturalWidth(try twoAwards())
        let five = naturalWidth(try troutsAwards())
        XCTAssertGreaterThan(
            five, two * 1.8,
            "a five-award row measures \(five) pt against a two-award row's \(two). "
            + "If those were equal something upstream would be capping the list at "
            + "two, and this ship's premise would be wrong")
    }

    // MARK: - The fix

    /// The ship: squeezed to a real phone's width, the row reflows instead of
    /// shredding a word.
    @MainActor
    func testTheAwardsTakeALineEachRatherThanAColumnOfCharacters() throws {
        let trout = try troutsAwards()
        let oneLine = size(trout, in: CGFloat.greatestFiniteMagnitude)
        let squeezed = size(trout, in: phoneAwardsWidth)

        XCTAssertLessThanOrEqual(
            squeezed.width, phoneAwardsWidth,
            "offered \(phoneAwardsWidth) pt it came out \(squeezed.width) pt wide, so "
            + "it overflowed rather than reflowing — which is #3978's page bleed, "
            + "the failure this fix is specifically not allowed to cause")

        // Five lines, not one shredded line. A wrap would also make it taller, so
        // height alone cannot testify — pair it with the width above, which a
        // wrapping row would NOT satisfy at 259 pt.
        XCTAssertGreaterThan(
            squeezed.height, oneLine.height * 3,
            "the squeezed row is \(squeezed.height) pt tall against \(oneLine.height) "
            + "on one line. Five awards on five lines is roughly five times; "
            + "anything near 1x means they are still sharing a line and the label "
            + "is losing characters instead")
    }

    /// The half that must not move: two short awards still share a line.
    ///
    /// Without this, a row that ALWAYS stacked would pass every assertion above,
    /// and every player on every event page would grow a paragraph.
    @MainActor
    func testTwoShortAwardsStillShareOneLine() throws {
        let two = try twoAwards()
        let free = size(two, in: CGFloat.greatestFiniteMagnitude)
        let onThePhone = size(two, in: phoneAwardsWidth)

        XCTAssertLessThanOrEqual(
            naturalWidth(two), phoneAwardsWidth,
            "precondition: two short awards fit the phone row, so the one-line arm "
            + "is the one that should be chosen")
        XCTAssertEqual(
            onThePhone.height, free.height, accuracy: 0.5,
            "the common case must render exactly as it does today — same height, "
            + "one line")
    }

    /// 🔴 AND THE NAME ITSELF SURVIVES, WHICH `lineLimit(1)` WOULD HAVE PREVENTED.
    ///
    /// The obvious companion to a reflow is `lineLimit(1)` — stop the label
    /// shredding by stopping it wrapping. Mutation said removing it killed
    /// nothing, so I measured what it did: at `.accessibility5` one
    /// "AL Comeback Player of the Year" wants 534.7 pt, and inside the row's 259
    /// it came out 249 × 40 — a single line, the name cut off. This issue's
    /// acceptance is that every market name renders *readably* at accessibility
    /// sizes, and a truncated name is not the name.
    ///
    /// The stacked arm is what makes wrapping safe: the label has the whole row
    /// instead of competing with four other awards, so it breaks at spaces rather
    /// than by the character.
    @MainActor
    func testALongMarketNameWrapsRatherThanBeingCutOff() throws {
        let long = try [award("AL Comeback Player of the Year", 0.0325, id: 3)]

        for (name, size) in [("a11y3", DynamicTypeSize.accessibility3),
                             ("a11y5", .accessibility5)] {
            let oneLine = self.size(long, in: CGFloat.greatestFiniteMagnitude, at: size)
            let inTheRow = self.size(long, in: phoneAwardsWidth, at: size)

            XCTAssertGreaterThan(
                oneLine.width, phoneAwardsWidth,
                "\(name): precondition — the label must not fit on one line, or "
                + "this proves nothing")
            XCTAssertGreaterThan(
                inTheRow.height, oneLine.height * 1.5,
                "\(name): given \(phoneAwardsWidth) pt the chip came out "
                + "\(inTheRow.height) pt tall against \(oneLine.height) on one line. "
                + "Unchanged height means the name was truncated to fit instead of "
                + "wrapping — measured at 249 × 40 with `lineLimit(1)` in place")
        }
    }

    /// The other direction: a short name at the default size is still one line.
    /// Without this, wrapping everything would pass the test above.
    @MainActor
    func testAShortMarketNameStaysOnOneLine() throws {
        let short = try [award("AL MVP", 0.0068, id: 1)]
        let free = size(short, in: CGFloat.greatestFiniteMagnitude)
        XCTAssertEqual(
            size(short, in: phoneAwardsWidth).height, free.height, accuracy: 0.5,
            "a short award has room and must not gain a line")
    }

    // MARK: - The second defect: the label ignored the reader

    /// 🔴 A `lineLimit` COULD NEVER HAVE SATISFIED THIS ISSUE'S OWN ACCEPTANCE.
    ///
    /// "Renders every market name readably at default AND accessibility text
    /// sizes." At accessibility sizes the label was 9 pt whatever the reader
    /// asked for — unreadable for a reason that has nothing to do with wrapping.
    @MainActor
    func testTheAwardLabelFollowsTheReadersTextSize() throws {
        let two = try twoAwards()
        let atLarge = naturalWidth(two, at: .large)

        var widths: [(String, CGFloat)] = []
        for (name, size) in [("xLarge", DynamicTypeSize.xLarge),
                             ("xxxLarge", .xxxLarge),
                             ("a11y1", .accessibility1),
                             ("a11y5", .accessibility5)] {
            widths.append((name, naturalWidth(two, at: size)))
        }

        for (name, width) in widths {
            XCTAssertGreaterThan(
                width, atLarge,
                "\(name): the row wants \(width) pt against \(atLarge) pt at `.large`. "
                + "Equal means the type is still a fixed 9 pt and the reader's "
                + "setting is being ignored (#4109 item 4)")
        }

        let biggest = try XCTUnwrap(widths.last)
        XCTAssertGreaterThan(
            biggest.1, atLarge * 2,
            "at `.accessibility5` the label should be well over twice its default "
            + "width; measured \(biggest.1) against \(atLarge)")
    }

    /// And the default size does not move — the reason this is `@ScaledMetric`
    /// seeded at 9 rather than `.caption2`, which is 11 pt at `.large` and would
    /// have enlarged this label on every screen to fix something that only
    /// happens above it.
    @MainActor
    func testTheDefaultSizeRowIsUnchanged() throws {
        let two = try twoAwards()
        let host = hostForMeasurement(
            Text("AL MVP").font(.system(size: 9)), at: .large)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        let ninePoint = host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude))

        let rowHost = hostForMeasurement(PlayerAwardsRow(awards: two), at: .large)
        rowHost.view.setNeedsLayout()
        rowHost.view.layoutIfNeeded()
        let rowHeight = rowHost.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).height

        XCTAssertEqual(
            rowHeight, ninePoint.height, accuracy: 0.5,
            "at `.large` the row is exactly as tall as a 9 pt line of text — the "
            + "scaled metric is seeded at 9 and `.large` is its identity. Anything "
            + "taller means the default render grew")
    }
}
