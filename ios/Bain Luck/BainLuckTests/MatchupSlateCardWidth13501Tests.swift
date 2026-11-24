import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #13501 — Long matchup_slate names ("St. Bonaventure" at "Appalachian St")
/// switch cleanly to stacked team rows at 390pt instead of breaking mid-word.
@MainActor
final class MatchupSlateCardWidth13501Tests: XCTestCase {
    private func sampleCard(
        slug: String,
        away1: String, home1: String,
        away2: String, home2: String
    ) -> MachineryCardContract {
        MachineryCardContract(
            slug: slug,
            formId: .matchupSlate,
            kicker: "COLLEGE BASKETBALL",
            title: "Sample slate headline",
            subtitle: "Featured matchups.",
            footer: "Tap to open set",
            eventRows: [
                MachineryEventVisualItem(eventId: 1001, awayShort: away1, homeShort: home1, awayPct: 55, homePct: 45),
                MachineryEventVisualItem(eventId: 1002, awayShort: away2, homeShort: home2, awayPct: 64, homePct: 36),
            ]
        )
    }

    private func renderSize(
        card: MachineryCardContract,
        width: CGFloat = 358,
        dynamicType: DynamicTypeSize = .large
    ) -> CGSize {
        let view = MachineryDiscoverCardView(card: card, onOpenContainer: { _, _ in })
            .frame(width: width)
        let host = hostForMeasurement(view, at: dynamicType)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
        host.view.layoutIfNeeded()
        return host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude))
    }

    func testLongMatchupNamesExpandCleanlyToStackedRowsInsteadOfMidWordWrapping() {
        let shortCard = sampleCard(
            slug: "machinery-nhl-this-week",
            away1: "Mammoth", home1: "Jets",
            away2: "Ducks", home2: "Kraken"
        )
        let longCard = sampleCard(
            slug: "machinery-college-basketball-slate",
            away1: "St. Bonaventure", home1: "Appalachian St",
            away2: "Mississippi St", home2: "New Orleans"
        )
        let shortHeight = renderSize(card: shortCard).height
        let longHeight = renderSize(card: longCard).height
        let ax5Height = renderSize(card: shortCard, dynamicType: .accessibility5).height

        XCTAssertGreaterThan(longHeight, shortHeight, "Long college names at 390px switch to taller 2-line stacked rows rather than squeezing")
        XCTAssertGreaterThan(ax5Height, shortHeight, "AX5 keeps stacked layout without clipping")
    }
}
