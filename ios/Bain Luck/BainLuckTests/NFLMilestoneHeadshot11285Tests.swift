import SwiftUI
import XCTest
@testable import Bain_Luck

/// #11285 (optional refinement) — a player's story card shows the headshot its
/// OWN ladder rows serve: never a loose name join, never a guess between two
/// served images, never a non-https url. Absent means no image and no slot.
@MainActor
final class NFLMilestoneHeadshot11285Tests: XCTestCase {

    private let now = Date(timeIntervalSince1970: 1_800_000_000)
    private func iso(_ date: Date) -> String { ISO8601DateFormatter().string(from: date) }

    private func row(_ subject: String, _ line: Double, price: Double, headshot: String?) -> GameMarketPlayerProp {
        GameMarketPlayerProp(marketName: "Receiving Yards",
                             outcomeName: "\(subject): \(PlayerPropsFamily.targetLabel(line)) Receiving Yards",
                             threshold: line, overProbability: price, source: "kalshi", movement: nil,
                             playerHeadshot: headshot, playerTeam: "home", actual: nil, hit: nil, pregameMark: nil,
                             observedAt: iso(now.addingTimeInterval(-300)), _inverted: nil)
    }

    private func ladder(_ subject: String, headshots: [String?]) -> [GameMarketPlayerProp] {
        let lines: [Double] = [40, 60, 80]
        let prices = [0.7, 0.5, 0.3]
        return lines.indices.map { row(subject, lines[$0], price: prices[$0], headshot: headshots[$0]) }
    }

    private let purdy = "https://a.espncdn.com/i/headshots/nfl/players/full/4361741.png"

    func testOneAgreedHttpsHeadshotIsKept() {
        XCTAssertEqual(NFLMilestoneCard9483.headshot(of: ladder("A", headshots: [purdy, purdy, nil])),
                       URL(string: purdy))
    }

    func testNoneEmptyDisagreeingOrInsecureIsNoHeadshot() {
        XCTAssertNil(NFLMilestoneCard9483.headshot(of: ladder("A", headshots: [nil, nil, nil])))
        XCTAssertNil(NFLMilestoneCard9483.headshot(of: ladder("A", headshots: ["", " ", nil])))
        XCTAssertNil(NFLMilestoneCard9483.headshot(of: ladder("A", headshots: [purdy, purdy + "?v=2", purdy])),
                     "two served images for one ladder: no guess")
        XCTAssertNil(NFLMilestoneCard9483.headshot(of: ladder("A", headshots: ["http://example.com/a.png", nil, nil])))
    }

    /// Each card carries its own ladder's image, so two players never swap.
    func testEachCardCarriesItsOwnLaddersHeadshot() throws {
        let other = "https://a.espncdn.com/i/headshots/nfl/players/full/3116365.png"
        let cards = NFLMilestoneCard9483.cards(
            props: ladder("George Kittle", headshots: [purdy, purdy, purdy])
                + ladder("Terry McLaurin", headshots: [other, nil, other]),
            eventStatus: "scheduled", commenceTime: now.addingTimeInterval(3600),
            homeTeam: "San Francisco 49ers", awayTeam: "Washington Commanders", now: now)
        XCTAssertEqual(cards.count, 2, "control: both ladders deal a card")
        XCTAssertEqual(cards.first { $0.player == "George Kittle" }?.headshot, URL(string: purdy))
        XCTAssertEqual(cards.first { $0.player == "Terry McLaurin" }?.headshot, URL(string: other))
    }

    /// A card aged on the page keeps its image (only prices expire).
    func testAgingTheCardKeepsItsHeadshot() throws {
        let card = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: ladder("George Kittle", headshots: [purdy, purdy, purdy]),
            eventStatus: "scheduled", commenceTime: now.addingTimeInterval(3600),
            homeTeam: "San Francisco 49ers", awayTeam: "Washington Commanders", now: now).first)
        let aged = card.current(at: now.addingTimeInterval(3 * 3600))
        XCTAssertNotEqual(aged.rungs.map(\.chance), card.rungs.map(\.chance), "control: the prices did age")
        XCTAssertEqual(aged.headshot, URL(string: purdy))
    }

    // MARK: - Fit (#11285 N2)

    /// The card's drawn height for `subject` at `size` on a 375pt phone's card.
    private func height(_ subject: String, headshot: String?, at size: DynamicTypeSize) throws -> CGFloat {
        let card = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: ladder(subject, headshots: [headshot, headshot, headshot]),
            eventStatus: "scheduled", commenceTime: now.addingTimeInterval(3600),
            homeTeam: "San Francisco 49ers", awayTeam: "Washington Commanders", now: now).first)
        XCTAssertEqual(card.headshot?.absoluteString, headshot, "control: the card carries the case")
        let host = hostForMeasurement(
            NFLMilestoneCardView9483(card: card, color: .orange, state: NFLCardDeckState9483()), at: size)
        return host.sizeThatFits(in: CGSize(width: 311, height: CGFloat.greatestFiniteMagnitude)).height
    }

    /// At accessibility sizes the headshot takes no name width: the card lays out
    /// exactly as it does with no headshot served, so "McCaffrey" stays one word
    /// (with the cue drawn, AX5 at 311pt broke it "McCaf-/frey").
    func testAtAccessibilitySizesTheHeadshotTakesNoNameWidth() throws {
        for subject in ["Christian McCaffrey", "Jaxon Smith-Njigba"] {
            for size in [DynamicTypeSize.accessibility3, .accessibility5] {
                XCTAssertEqual(try height(subject, headshot: purdy, at: size),
                               try height(subject, headshot: nil, at: size), accuracy: 0.5,
                               "\(subject) at \(size): the headshot changed the layout")
            }
        }
    }
}
