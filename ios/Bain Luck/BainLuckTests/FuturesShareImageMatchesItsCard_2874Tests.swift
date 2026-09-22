import XCTest
@testable import Bain_Luck

/// #2874, second half — **the picture that leaves the app prints the numbers the
/// futures card printed.**
///
/// `DiscoverFuturesCardSumsTo100Tests` guards the card. This file guards the other
/// output of the same affordance: the `contextMenu` behind the card's `ShareLink`
/// renders an image through `ShareCardRenderer.renderFuturesCard`, and that image
/// rounded its hero and every row on its own. Fixing only the card would have left
/// the exported picture printing `60% / 41%` under a card reading `60% / 40%` —
/// the defect #7998 closed on the EVENT card, still open on futures.
///
/// ## Two causes, and the second one survives any sum guard
///
/// 1. **THE ROUNDING.** Both surfaces formatted each row alone, so a complement
///    pair on the venues' half-cent grid rounded both sides up: 101.
/// 2. **THE LIST.** `renderedShareImage()` `compactMap`ped the unpriced outcomes
///    away before handing the field over. `renderedCardPercents` applies its pair
///    rule only to a TWO-outcome field, so a three-outcome market with one
///    unpriced side reached the image as a pair and was normalised — on a field
///    the card deliberately leaves alone. **Both surfaces then sum to 100 while
///    printing different numbers**, which is why every assertion here is equality
///    with the card rather than a sum.
///
/// So the two surfaces are not made to agree by rounding the same way; they have
/// to be asked the same question with the same list. `printedFuturesPercents` is a
/// `static func` for the reason `printedPercents` is (#7998): arithmetic inside a
/// `some View` is arithmetic no test can reach, which is how this class of defect
/// keeps being declared absent.
///
/// The fixture is the card file's — `Fixtures/feed-futures-binary-101.20260922.json`,
/// six cards lifted verbatim from one production response to the phone's own query.
/// Nobody typed these probabilities.
///
/// `test_theOldImageExpressionReallyDidDisagree` and
/// `test_theFilteredListReallyDidChangeTheAnswer` are the convicting controls: each
/// re-runs a pre-fix expression and fails if it never disagreed, so this file
/// cannot pass vacuously.
final class FuturesShareImageMatchesItsCard_2874Tests: XCTestCase {

    // MARK: - Harness

    private static var fixtureURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("feed-futures-binary-101.20260922.json")
    }

    private struct Page: Decodable { let items: [Row] }
    private struct Row: Decodable { let data: FeedFuturesData }

    private static func cards() throws -> [Int: FeedFuturesData] {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let page = try d.decode(Page.self, from: Data(contentsOf: fixtureURL))
        return Dictionary(uniqueKeysWithValues: page.items.map { ($0.data.id, $0.data) })
    }

    /// The list the card hands the renderer — the production function, not a copy
    /// of what it does.
    private func shareRows(_ card: FeedFuturesData) -> [(name: String, probability: Double?)] {
        discoverFuturesShareRows(card.topOutcomes ?? [])
    }

    /// The strings the IMAGE prints, through the production path.
    private func imageLabels(_ card: FeedFuturesData) -> [String] {
        ShareableFuturesCardView.printedFuturesPercents(shareRows(card))
            .map { discoverFuturesCardPercentLabel($0) }
    }

    /// The strings the CARD prints, through the production path.
    private func cardLabels(_ card: FeedFuturesData) -> [String] {
        discoverFuturesCardPercents(card.topOutcomes ?? [])
            .map { discoverFuturesCardPercentLabel($0) }
    }

    /// What the image did before: `compactMap` the field, then round each survivor
    /// on its own.
    private func theOldImage(_ card: FeedFuturesData) -> [String] {
        (card.topOutcomes ?? [])
            .compactMap(\.probability)
            .map { "\(Int(($0 * 100).rounded()))%" }
    }

    // MARK: - The three cards that printed 101

    func test_theThreeSpecimens_theImagePrintsWhatTheCardPrints() throws {
        let cards = try Self.cards()

        let dallas = try XCTUnwrap(cards[61380701])          // 0.595 / 0.405
        XCTAssertEqual(imageLabels(dallas), ["60%", "40%"])
        XCTAssertEqual(imageLabels(dallas), cardLabels(dallas))

        let panthers = try XCTUnwrap(cards[61380677])        // 0.535 / 0.465
        XCTAssertEqual(imageLabels(panthers), ["54%", "46%"])
        XCTAssertEqual(imageLabels(panthers), cardLabels(panthers))

        let anthropic = try XCTUnwrap(cards[22979756])       // 0.755 / 0.245
        XCTAssertEqual(imageLabels(anthropic), ["76%", "24%"])
        XCTAssertEqual(imageLabels(anthropic), cardLabels(anthropic))
    }

    /// The convicting control. If the old image expression had agreed with the
    /// card, every assertion above would pass on an image that was already right.
    func test_theOldImageExpressionReallyDidDisagree() throws {
        for id in [61380701, 61380677, 22979756] {
            let card = try XCTUnwrap(try Self.cards()[id])
            XCTAssertNotEqual(
                theOldImage(card), cardLabels(card),
                "card \(id) did not exhibit the defect — it is not a specimen"
            )
        }
    }

    // MARK: - Every card in the fixture, both surfaces, one pass

    func test_everyCardInTheFixture_theImageEqualsTheCard() throws {
        for (id, card) in try Self.cards() {
            XCTAssertEqual(
                imageLabels(card), cardLabels(card),
                "the image disagreed with its own card on \(id)"
            )
        }
    }

    /// The over-reach control, carried over from the card's file: a three-way field
    /// still prints 101 on BOTH surfaces, and that is correct. An image that
    /// "helpfully" normalised it would be a new defect that agrees with nothing.
    func test_aThreeWayFieldIsLeftAloneInTheImageToo() throws {
        let brazil = try XCTUnwrap(try Self.cards()[112996])
        XCTAssertEqual(imageLabels(brazil), ["59%", "41%", "1%"])
        XCTAssertEqual(imageLabels(brazil), cardLabels(brazil))
    }

    // MARK: - The list, which no sum guard can see

    /// A three-outcome field with one unpriced side. The card leaves it alone; the
    /// image must leave it alone for the same reason, which it can only do if it is
    /// handed the unpriced member.
    ///
    /// Synthetic — the fixture's six production cards happen to carry no nil
    /// probability — and said so plainly rather than implied.
    func test_theUnpricedTailReachesTheImage() {
        let served: [(name: String, probability: Double?)] = [
            ("Not Dallas Stars", 0.595),
            ("Dallas Stars", 0.405),
            ("Withdrawn", nil),
        ]

        XCTAssertEqual(ShareableFuturesCardView.printedFuturesPercents(served), [60, 41, nil])
    }

    /// The convicting control for the one above. Filtering really did change the
    /// answer, so the assertion is not a distinction without a difference — and the
    /// two results both sum to 100, which is the whole reason a sum guard is blind
    /// to this arm.
    func test_theFilteredListReallyDidChangeTheAnswer() {
        let whole: [Double?] = [0.595, 0.405, nil]
        let filtered: [Double?] = [0.595, 0.405]

        XCTAssertEqual(renderedCardPercents(whole), [60, 41, nil])
        XCTAssertEqual(renderedCardPercents(filtered), [60, 40])
        XCTAssertNotEqual(
            Array(renderedCardPercents(whole).prefix(2)),
            renderedCardPercents(filtered),
            "if filtering did not change the answer, the list is not load-bearing"
        )
    }

    func test_anEmptyFieldPrintsNothing() {
        XCTAssertEqual(ShareableFuturesCardView.printedFuturesPercents([]), [])
    }

    // MARK: - The two values the view itself derives

    /// The static function is only half the path: the VIEW has to ask it, and ask
    /// it for both the hero and the rows. A mutant emptying either derivation
    /// compiles, renders, and survives every assertion above — which is exactly the
    /// hole the card's own file found with its mutation battery (3 of 6 survivors,
    /// all view-layer). So the view is constructed and both are read.
    private func view(_ card: FeedFuturesData) -> ShareableFuturesCardView {
        ShareableFuturesCardView(
            marketName: card.name,
            leaderName: card.topOutcomes?.first?.name ?? "",
            category: "hockey",
            hookDescription: nil,
            outcomes: shareRows(card)
        )
    }

    func test_theViewDerivesItsHeroAndItsRowsFromTheCardsOneDecision() throws {
        let dallas = try XCTUnwrap(try Self.cards()[61380701])
        let subject = view(dallas)

        XCTAssertEqual(subject.heroPercent, 60, "the hero is the leader's own number, untouched")
        XCTAssertEqual(subject.rowPercents, [60, 40], "the rows are the card's pair")
        XCTAssertEqual(
            subject.rowPercents.map { discoverFuturesCardPercentLabel($0) },
            cardLabels(dallas),
            "the view's own rows must equal the card's"
        )
    }

    /// And the hero follows the leader rather than the largest or the first
    /// non-nil: a three-way field's hero is `outcomes[0]`, the served headline.
    func test_theHeroIsTheServedHeadlineNotTheBiggestNumber() throws {
        let brazil = try XCTUnwrap(try Self.cards()[112996])
        XCTAssertEqual(view(brazil).heroPercent, 59)
    }

    // MARK: - The wiring, which no behavioural test can reach

    /// A SwiftUI `body` is not reachable from XCTest here, and this ship is about
    /// two call sites. The card's file makes the same argument and scans the same
    /// way; this is the renderer's half.
    ///
    /// Comment lines are dropped first: both files describe the defect in prose,
    /// and a scanner that convicts its own explanation is one nobody can document
    /// around.
    func test_theRendererDrawsEveryPercentThroughTheCardsOneDecision() throws {
        let code = try Self.code("Utilities/ShareCardRenderer.swift")

        XCTAssertFalse(
            code.contains("* 100).rounded()"),
            "the share renderer rounds a probability in its own body again"
        )
        XCTAssertTrue(
            code.contains("discoverFuturesCardPercentLabel(heroPercent)"),
            "the image's hero numeral no longer shares the card's one decision"
        )
        XCTAssertTrue(
            code.contains("discoverFuturesCardPercentLabel(percent)"),
            "the image's outcome row no longer prints the percent it was handed"
        )
        XCTAssertTrue(
            code.contains("printed.indices.contains(idx) ? printed[idx] : nil"),
            "the image's row list no longer indexes the decision — rows are getting nil"
        )
    }

    /// The renderer cannot be handed a hero number of its own, and cannot be called
    /// without the field — the two omissions #7998 made deliberately on the event
    /// card, for the reason a defaulted parameter silently restores the old reading.
    func test_theRendererCannotBeHandedANumberTheCardDidNotPrint() throws {
        let code = try Self.code("Utilities/ShareCardRenderer.swift")

        XCTAssertFalse(
            code.contains("let probability: Double\n"),
            "ShareableFuturesCardView took back a hero probability of its own"
        )
        XCTAssertFalse(
            code.contains("outcomes: [(name: String, probability: Double)] = []"),
            "renderFuturesCard's outcome list is defaultable again — a forgetful caller gets no rows"
        )
    }

    /// And the caller hands over the WHOLE field.
    ///
    /// 🔴 **THIS USED TO BE A SOURCE SCAN AND THE MUTATION BATTERY KILLED IT.**
    /// The rule lived inline in `renderedShareImage()` and was guarded by a scan
    /// for the exact old spelling of the filter, so
    /// `caller-filters-the-field-again` — the same filtering in slightly different
    /// words — **SURVIVED**: the guard was aimed at one phrasing of a defect
    /// rather than at its behaviour. The mapping is now
    /// `discoverFuturesShareRows`, a function a test can call, and this asserts
    /// what it returns.
    func test_theShareRowsKeepEveryOutcomeIncludingTheUnpriced() {
        let field = [
            FeedFuturesOutcome(id: 1, name: "Not Dallas Stars", probability: 0.595, rank: 1, movement: nil),
            FeedFuturesOutcome(id: 2, name: "Dallas Stars", probability: 0.405, rank: 2, movement: nil),
            FeedFuturesOutcome(id: 3, name: "Withdrawn", probability: nil, rank: 3, movement: nil),
        ]

        let rows = discoverFuturesShareRows(field)

        XCTAssertEqual(rows.count, 3, "an unpriced outcome was dropped before the image saw it")
        XCTAssertEqual(rows.map(\.name), ["Not Dallas Stars", "Dallas Stars", "Withdrawn"])
        XCTAssertEqual(rows.map(\.probability), [0.595, 0.405, nil])
        XCTAssertEqual(
            ShareableFuturesCardView.printedFuturesPercents(rows), [60, 41, nil],
            "a filtered field would print the normalised pair 60/40 the card never printed"
        )
    }

    func test_theCardCallsThatFunctionRatherThanRestatingIt() throws {
        let code = try Self.code("Components/DiscoverFuturesCard.swift")
        XCTAssertTrue(
            code.contains("discoverFuturesShareRows(data.topOutcomes ?? [])"),
            "renderedShareImage() builds its own outcome list again"
        )
    }

    /// The control for the controls: the line filter must drop the prose and keep
    /// the code, or the three scans above are measuring their own commentary.
    func test_theLineFilterDropsProseAndKeepsCode() {
        let sample = """
        /// a doc comment mentioning * 100).rounded()
        // a plain comment mentioning * 100).rounded()
        let y = Int((p * 100).rounded())
        """

        let code = Self.droppingCommentLines(sample)
        XCTAssertEqual(
            code.components(separatedBy: "* 100).rounded()").count - 1, 1,
            "exactly the one real occurrence should survive"
        )
        XCTAssertTrue(code.contains("let y = Int((p * 100).rounded())"))
    }

    // MARK: - Source access

    private static func droppingCommentLines(_ text: String) -> String {
        text
            .components(separatedBy: .newlines)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    private static func code(_ relativePath: String) throws -> String {
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        let text = try String(contentsOf: appRoot.appendingPathComponent(relativePath), encoding: .utf8)
        return droppingCommentLines(text)
    }
}
