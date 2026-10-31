import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — part five (`FieldEventPageInputAdapter10868`): the whole page input
/// and its manual story stream, composed from the retained REAL chess, rugby and
/// series bodies (`FieldEventAdapterFixtures10868`). PREPARED / NOT RUN.
@MainActor
final class FieldEventPageInputAdapter10868Tests: XCTestCase {
    private typealias P = FieldEventPageInputAdapter10868
    private typealias A = FieldEventPageAdapter10868
    private typealias S = FieldEventStoriesAdapter10868
    private typealias H = FieldEventHistoryAdapter10868
    private typealias F = FieldEventAdapterFixtures10868

    private func chessInput(_ state: P.StreamState = P.StreamState()) throws -> FieldEventPageInput10868 {
        let market = try F.market(F.chessBefore)
        let history = try F.history(F.chessHistory)
        let host = F.host(F.chessCapture)
        return P.input(market, history: H.history(history, market: market, host: host),
                       field: S.field(market, host: host), movement: S.movement(history, market: market, host: host),
                       originalsCount: 12, stream: state, host: host)
    }

    func testTheChessPageComposesEveryPartForOneSnapshot() throws {
        let market = try F.market(F.chessBefore)
        let host = F.host(F.chessCapture)
        let input = try chessInput()
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.headline, A.headline(market, host: host))
        XCTAssertEqual(input.reader, A.readerHeader(market))
        XCTAssertEqual(input.about, A.about(market))
        XCTAssertNotNil(input.field)
        XCTAssertNotNil(input.movement)
        XCTAssertEqual(input.stories, [FieldEventPageStory10868(cardID: "field", card: .field),
                                       FieldEventPageStory10868(cardID: "movement", card: .movement)])
        XCTAssertEqual(input.copy, FieldEventPageCopy10868(
            storiesLabel: "Field stories",
            storyUnavailable: "This story isn’t available right now. Every original is still in All props.",
            headlineUnavailable: "Headline unavailable right now",
            allPropsLabel: "All 12 original outcomes"))
        // The composed model mounts both stories and the headline.
        let model = FieldEventPageModel10868(input)
        XCTAssertNotNil(model.headline)
        XCTAssertEqual(model.storyCard("field"), .field)
        XCTAssertEqual(model.storyCard("movement"), .movement)
    }

    func testTheStreamIsManualAndHoldsTheHostsCard() throws {
        let first = try chessInput().stream
        XCTAssertEqual(first.scope, "field:62383719:before:stories")
        XCTAssertEqual(first.heading, "Field stories")
        XCTAssertEqual(first.cards.map(\.id), ["field", "movement"])
        XCTAssertEqual(first.cards.map(\.name), ["The field", "How chances moved"])
        XCTAssertEqual(first.primary?.id, "field")
        XCTAssertEqual(first.next?.id, "movement")
        XCTAssertEqual(first.previous?.id, "movement")
        XCTAssertEqual(first.position, "1 of 2")
        XCTAssertEqual(first.status, "Use Previous or Next to see each story")
        XCTAssertNil(first.playback)
        XCTAssertNil(first.dwellFraction)
        let held = try chessInput(P.StreamState(displayed: .movement, readerOpen: true, wide: true)).stream
        XCTAssertEqual(held.primary?.id, "movement")
        XCTAssertEqual(held.position, "2 of 2")
        XCTAssertTrue(held.readerOpen)
        XCTAssertTrue(held.wide)
    }

    func testAStoryWithoutInputIsNotOfferedAndTheStreamCanBeEmpty() throws {
        // Darts at its capture: no recent chance (no field card) and no retained history (no movement card).
        let darts = try F.market(F.dartsBefore)
        let host = F.host(F.dartsCapture)
        let input = P.input(darts, history: H.unavailable(darts, host: host),
                            field: S.field(darts, host: host), movement: S.movement(nil, market: darts, host: host),
                            originalsCount: 18, stream: P.StreamState(), host: host)
        XCTAssertEqual(input.stories, [])
        XCTAssertEqual(input.stream.cards, [])
        XCTAssertNil(input.stream.primary)
        XCTAssertEqual(input.copy.allPropsLabel, "All 18 original outcomes")
        // The page still has its headline and All props.
        XCTAssertNotNil(FieldEventPageModel10868(input).headline)
    }

    func testOnlyTheOwnScopesCardRefsNameACard() {
        let scope = "field:62383719:before:stories"
        XCTAssertEqual(P.card(.init(scope: scope, id: "movement"), scope: scope), .movement)
        XCTAssertNil(P.card(.init(scope: "field:62383719:final:stories", id: "movement"), scope: scope))
        XCTAssertNil(P.card(.init(scope: scope, id: "history"), scope: scope))
        XCTAssertNil(P.card(.init(scope: scope, id: "unknown"), scope: scope))
        XCTAssertNil(P.copy(originalsCount: 0).allPropsLabel)
        XCTAssertEqual(P.copy(originalsCount: 1).allPropsLabel, "1 original outcome")
    }
}
