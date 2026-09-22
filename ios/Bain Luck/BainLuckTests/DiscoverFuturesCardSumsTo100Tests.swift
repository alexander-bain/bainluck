import XCTest
@testable import Bain_Luck

private extension String {
    /// Swift source with `//` line comments and block comments removed.
    ///
    /// A private copy of `PriceAgeMarkTests`' stripper, deliberately naive for the
    /// same reason: its only job is to stop a source scan being satisfied by the
    /// pattern appearing in the prose that explains the pattern. Over-removal
    /// makes a scan fail closed, which is the safe direction.
    func strippingSwiftComments() -> String {
        var out = ""
        var rest = Substring(self)
        while let open = rest.range(of: "/*") {
            out += rest[rest.startIndex..<open.lowerBound]
            guard let close = rest.range(of: "*/", range: open.upperBound..<rest.endIndex) else {
                rest = rest[rest.endIndex...]
                break
            }
            rest = rest[close.upperBound...]
        }
        out += rest

        return out
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let slashes = line.range(of: "//") else { return line }
                return line[line.startIndex..<slashes.lowerBound]
            }
            .joined(separator: "\n")
    }
}

/// **A Discover futures card's two outcome rows add up to 100.**
///
/// Seen on the phone, simulator against production, 2026-09-22:
///
///     Will Dallas Stars advance to the Second Round…?
///       Not Dallas Stars    60%
///       Dallas Stars        41%      <- 101%
///
/// The quotes are `0.595 / 0.405` — an exact complement. Venues quote on a
/// half-cent grid, so both sides of one question land on the `.5` rounding
/// boundary at once and a row that formats each outcome on its own rounds both
/// up. That is #2060 clause (1): "two-outcome sides rounded independently — must
/// render p and 100−p".
///
/// ## What this file is guarding against, specifically
///
/// The rule already existed. `renderedCardPercents`
/// (`Utilities/RenderedPercent.swift`, native's arm of
/// `contracts/rendered_percent.json`) was written for this exact defect and had
/// **zero call sites in the app target** — a contract-tested function nothing called.
/// So the thing that can regress is not the arithmetic, it is the WIRING, and
/// what is asserted here is the string `outcomeRow` prints
/// (`discoverFuturesCardPercentLabel` over `discoverFuturesCardPercents`, the
/// exact expression the view uses), not that a helper returns the right array.
///
/// ## The fixture
///
/// `Fixtures/feed-futures-binary-101.20260922.json` is PRODUCTION: six cards
/// lifted verbatim out of one response to the phone's own query,
/// `GET /api/feed?limit=50&offset=0&event_pct=0.15` (2026-09-22, page sha256
/// `dfb2d5ee…`, fixture sha256 `c8157789…`). Nobody typed these probabilities.
/// Three of them printed 101 on that page — 3 of the 39 futures cards served.
///
/// The three CONTROLS are the other direction, and they are the half of this
/// test that can actually catch over-reach:
///
/// | control | why it must not move |
/// |---|---|
/// | Treasury yield, `0.9305 / 0.0695` | a complement pair that was ALREADY right (93/7). The pair rule must be a no-op on it. |
/// | MLB World Series, 3 outcomes summing 0.50 | a partial field — not a pair, renders as three scalars. |
/// | Brazil Presidential, 3 outcomes summing 1.006 | **still prints 101 after this change, deliberately.** A three-way field is not a complement pair; #2088's `card_sum_reason` sentence is what explains those, not this rule. A version of this fix that "helpfully" normalised it would be wrong. |
final class DiscoverFuturesCardSumsTo100Tests: XCTestCase {

    // MARK: - Harness

    private static var fixtureURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("feed-futures-binary-101.20260922.json")
    }

    private struct Page: Decodable { let items: [Row] }
    private struct Row: Decodable { let data: FeedFuturesData }

    /// The card's own source, comments stripped.
    private static func cardSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Components/DiscoverFuturesCard.swift")
        return try String(contentsOf: url, encoding: .utf8).strippingSwiftComments()
    }

    /// The app's own strategy (`APIClient.init`).
    private static func cards() throws -> [Int: FeedFuturesData] {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let page = try d.decode(Page.self, from: Data(contentsOf: fixtureURL))
        return Dictionary(uniqueKeysWithValues: page.items.map { ($0.data.id, $0.data) })
    }

    /// The strings the card's rows print, in served order — the composition the
    /// view performs.
    private func labels(_ card: FeedFuturesData) -> [String] {
        discoverFuturesCardPercents(card.topOutcomes ?? [])
            .map { discoverFuturesCardPercentLabel($0) }
    }

    private func sum(_ card: FeedFuturesData) -> Int {
        discoverFuturesCardPercents(card.topOutcomes ?? []).reduce(0) { $0 + ($1 ?? 0) }
    }

    // MARK: - The defect

    func testTheThreeCardsThatPrinted101NowPrint100() throws {
        let cards = try Self.cards()

        // Dallas Stars — the card in the docstring. Was 60 / 41.
        let dallas = try XCTUnwrap(cards[61380701])
        XCTAssertEqual(labels(dallas), ["60%", "40%"])
        XCTAssertEqual(sum(dallas), 100)

        // Florida Panthers — was 54 / 47.
        let panthers = try XCTUnwrap(cards[61380677])
        XCTAssertEqual(labels(panthers), ["54%", "46%"])
        XCTAssertEqual(sum(panthers), 100)

        // Anthropic valuation — was 76 / 25.
        let anthropic = try XCTUnwrap(cards[22979756])
        XCTAssertEqual(labels(anthropic), ["76%", "24%"])
        XCTAssertEqual(sum(anthropic), 100)
    }

    /// The favourite is the side that survives untouched; the derived point lands
    /// on the side nobody is quoting. Asserted separately because "sums to 100"
    /// alone is satisfied by moving the WRONG side (59/41 also sums to 100, and
    /// would be a different, quieter bug).
    func testTheLeaderKeepsItsOwnNumberAndTheDerivedPointLandsOnTheUnderdog() throws {
        let dallas = try XCTUnwrap(try Self.cards()[61380701])
        let percents = discoverFuturesCardPercents(dallas.topOutcomes ?? [])

        XCTAssertEqual(percents.first ?? nil, 60, "0.595 rounds to 60 on its own and must stay 60")
        XCTAssertEqual(percents.last ?? nil, 40, "the underdog absorbs the point")
    }

    // MARK: - The controls

    func testAPairThatWasAlreadyRightDoesNotMove() throws {
        let treasury = try XCTUnwrap(try Self.cards()[61836902])
        XCTAssertEqual(labels(treasury), ["93%", "7%"], "0.9305 / 0.0695 printed 93 / 7 before this change")
        XCTAssertEqual(sum(treasury), 100)
    }

    func testAPartialFieldRendersAsScalarsAndIsNotForcedToASum() throws {
        let mlb = try XCTUnwrap(try Self.cards()[1])
        XCTAssertEqual(labels(mlb), ["28%", "13%", "10%"])
        XCTAssertEqual(sum(mlb), 51, "three outcomes summing to 0.50 are a partial field, not a pair")
    }

    /// The over-reach control, and the one worth reading twice: this card STILL
    /// prints 101 and that is the correct outcome of this change.
    func testAThreeWayFieldIsLeftAloneEvenThoughItSumsTo101() throws {
        let brazil = try XCTUnwrap(try Self.cards()[112996])
        XCTAssertEqual(labels(brazil), ["59%", "41%", "1%"])
        XCTAssertEqual(sum(brazil), 101, "not a two-outcome complement pair — out of scope for the card rule")
    }

    // MARK: - The row's own contract

    func testAnUnpricedOutcomeStillPrintsZeroPercent() {
        XCTAssertEqual(discoverFuturesCardPercentLabel(nil), "0%")
    }

    // MARK: - The wiring

    /// 🔴 **EVERY TEST ABOVE DRIVES THE PURE FUNCTIONS, AND THIS SHIP IS ABOUT A
    /// CALL SITE.** The first cut of this file stopped at the functions, and the
    /// mutation battery (`tools/n297-8035-mutants.sh`) said so: 3 of 6 mutants
    /// SURVIVED, and all three were view-layer — the row ignoring the percent it
    /// is handed and re-deriving from the raw value, the list handing every row
    /// `nil`, and the hero rounding on its own again. Each of those puts 101 back
    /// on the screen with every assertion above still green.
    ///
    /// That is the same hole this ship exists to close. `renderedCardPercents` was
    /// contract-tested and had no callers; a guard that tests the rule and not the
    /// wiring reproduces the defect one level up. So the wiring gets a source
    /// scan, which is what the codebase already uses to ask "did every renderer
    /// adopt it" (`PriceAgeMarkTests.testEveryFuturesCardViewDrawsTheMark`).
    ///
    /// Comments are stripped first, or the scan would be satisfied by the doc
    /// comment above `discoverFuturesCardPercents`, which quotes the very
    /// expression this asserts is gone.
    func testTheCardDrawsEveryPercentThroughTheCardsOneDecision() throws {
        let code = try Self.cardSource()

        XCTAssertFalse(
            code.contains("* 100).rounded()"),
            """
            DiscoverFuturesCard.swift rounds a percent on its own again. Every \
            number on this card is one answer to one question and must come from \
            `renderedPercents` — a lone `* 100).rounded()` is how #8035 printed 101.
            """
        )
        XCTAssertTrue(
            code.contains("discoverFuturesCardPercentLabel(percent)"),
            "the outcome row no longer prints the percent the card handed it"
        )
        XCTAssertTrue(
            code.contains("percents[idx]"),
            "the outcome list no longer indexes the card's decision — rows are getting nil"
        )
        XCTAssertTrue(
            code.contains(#"Text("\(leaderRenderedPercent)")"#),
            "the hero numeral no longer shares the card's decision with the rows beneath it"
        )
    }

    /// The control for the control: the stripper must remove the prose and keep
    /// the code, or the scan above is measuring its own commentary.
    func testTheStripperRemovesProseAndKeepsCode() {
        let sample = """
        // a comment mentioning * 100).rounded()
        let x = 1  // trailing * 100).rounded()
        let y = Int((p * 100).rounded())
        """
        let stripped = sample.strippingSwiftComments()
        XCTAssertEqual(stripped.components(separatedBy: "* 100).rounded()").count - 1, 1,
                       "exactly the one real occurrence should survive")
        XCTAssertTrue(stripped.contains("let y = Int((p * 100).rounded())"))
    }

    /// Every card in the fixture, driven through the composition in one pass, so
    /// a future fixture row cannot be added without being covered.
    func testNoTwoOutcomeComplementCardInTheFixtureSumsToAnythingButOneHundred() throws {
        for (id, card) in try Self.cards() {
            let outcomes = card.topOutcomes ?? []
            let probabilities = outcomes.compactMap(\.probability)
            guard outcomes.count == 2, probabilities.count == 2 else { continue }
            let total = probabilities[0] + probabilities[1]
            guard total >= 0.99, total <= 1.01 else { continue }
            XCTAssertEqual(sum(card), 100, "card \(id) is a complement pair and must print a sum of 100")
        }
    }
}
