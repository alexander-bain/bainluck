import SwiftUI
import XCTest
@testable import Bain_Luck

/// #9484 — Alex's phone: a finished CWS–CLE page showed the White Sox win AND a
/// large grey "Still trading" block. The venue quote is now compact secondary
/// context under its venue's name; the hero alone states the result.
@MainActor
final class FinalGameWinnerQuoteCompactContext9484Tests: XCTestCase {
    /// Alex's specimen shape (event 15323743, Polymarket 63624759): the bare
    /// matchup name and a postgame book pinned at the endpoints.
    private func polymarketSpecimen(name: String = "Chicago White Sox vs. Cleveland Guardians") -> FinalGameWinnerQuote {
        FinalGameWinnerQuote(eventId: 15323743, marketId: 63624759, marketName: name,
            source: "polymarket", status: "open", observedAt: nil, outcomes: [
                FinalGameWinnerQuoteOutcome(outcomeId: 1, side: .away, name: "Chicago White Sox",
                                           probability: 0.9995, observedAt: nil),
                FinalGameWinnerQuoteOutcome(outcomeId: 2, side: .home, name: "Cleveland Guardians",
                                           probability: 0.0005, observedAt: nil),
            ])
    }

    private func kalshiGame2() -> FinalGameWinnerQuote {
        FinalGameWinnerQuote(eventId: 15323743, marketId: 77, marketName: "Game 2: Chicago WS vs Cleveland",
            source: "kalshi", status: "open", observedAt: nil, outcomes: [
                FinalGameWinnerQuoteOutcome(outcomeId: 3, side: .away, name: "Chicago WS",
                                           probability: 0.99, observedAt: nil),
                FinalGameWinnerQuoteOutcome(outcomeId: 4, side: .home, name: "Cleveland",
                                           probability: 0.01, observedAt: nil),
            ])
    }

    func testHeaderNamesTheVenueMarketAndNeverClaimsTradingOrSettlement() {
        XCTAssertEqual(FinalGameWinnerQuoteView.header(source: "polymarket"), "Polymarket winner market")
        XCTAssertEqual(FinalGameWinnerQuoteView.header(source: "kalshi"), "Kalshi winner market")
        for text in [FinalGameWinnerQuoteView.header(source: "polymarket"),
                     FinalGameWinnerQuoteView.header(source: "kalshi"),
                     FinalGameWinnerQuoteView.caption] {
            for claim in ["trading", "settled", "venue", "live"] {
                XCTAssertFalse(text.lowercased().contains(claim), "\(text) claims \(claim)")
            }
        }
        XCTAssertEqual(FinalGameWinnerQuoteView.caption, "Last market price. The result is the score above.")
    }

    func testBareMatchupNameIsOmittedBecauseItRepeatsThePageTitle() {
        XCTAssertNil(FinalGameWinnerQuoteView.contextName(for: polymarketSpecimen()))
        XCTAssertNil(FinalGameWinnerQuoteView.contextName(for: polymarketSpecimen(name: "White Sox vs Guardians")))
        XCTAssertNil(FinalGameWinnerQuoteView.contextName(for: polymarketSpecimen(name: "Cleveland Guardians at Chicago White Sox")))
    }

    func testANameThatSaysMoreThanTheTeamsIsKeptVerbatim() {
        XCTAssertEqual(FinalGameWinnerQuoteView.contextName(for: kalshiGame2()), "Game 2: Chicago WS vs Cleveland")
        XCTAssertEqual(FinalGameWinnerQuoteView.contextName(for: polymarketSpecimen(name: "  ALDS Game 2: White Sox vs. Guardians ")),
                       "ALDS Game 2: White Sox vs. Guardians")
    }

    func testPostgameEndpointBookStillPrintsWithoutCertainty() {
        let quote = polymarketSpecimen()
        XCTAssertNotNil(FinalGameWinnerQuoteView(quote: quote, eventId: 15323743,
                                                 eventStatus: "completed", closedMarketIds: []))
        XCTAssertEqual(quote.printableProbabilities[1], ">99%")
        XCTAssertEqual(quote.printableProbabilities[2], "<1%")
    }

    /// The reader complaint was the panel's weight, so the proof is its height
    /// at phone width: two outcome rows plus one header and one caption.
    func testPanelIsCompactAtPhoneWidth() throws {
        let view = try XCTUnwrap(FinalGameWinnerQuoteView(quote: polymarketSpecimen(), eventId: 15323743,
                                                          eventStatus: "completed", closedMarketIds: []))
        let renderer = rendererForMeasurement(view.frame(width: 358))
        renderer.scale = 1
        let height = try XCTUnwrap(renderer.uiImage).size.height
        XCTAssertLessThanOrEqual(height, Self.compactHeightBound, "panel is \(height)pt tall")
    }

    /// Measured at .large: this panel 108pt; the pre-#9484 styling 140pt.
    static let compactHeightBound: CGFloat = 124
}
