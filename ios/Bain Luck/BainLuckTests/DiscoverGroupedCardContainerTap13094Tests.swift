import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13094 (Ruling 31: A — "containers feel like cards"):
/// Tapping anywhere on a Discover grouped card that has a container opens that
/// container, on every grouped card form (`NativeGroupCard`,
/// `DiscoverPairedMetricCardView`, `MachineryDiscoverEntryCardView`,
/// `DiscoverRoundupCardView`), while keeping the card's footer link.
@MainActor
final class DiscoverGroupedCardContainerTap13094Tests: XCTestCase {

    private func makeFuturesItem(id: Int, name: String, leader: String, prob: Double, category: String) throws -> FeedItem {
        let json = """
        {
          "type": "futures",
          "headline": "\(name)",
          "data": {
            "id": \(id),
            "name": "\(name)",
            "status": "active",
            "llm_sport_category": "\(category)",
            "top_outcomes": [
              { "name": "\(leader)", "probability": \(prob) }
            ]
          }
        }
        """
        let dec = JSONDecoder()
        return try dec.decode(FeedItem.self, from: Data(json.utf8))
    }

    private func decodePairedSet(setId: String, kicker: String, title: String, s1: String, s2: String) throws -> PairedMetricSet {
        let json = """
        {
          "set_id": "\(setId)",
          "category": "entertainment",
          "kicker": "\(kicker)",
          "title": "\(title)",
          "subtitle": "Sorted by \(s2.lowercased()) %, ties broken by \(s1.lowercased()) %",
          "stage_1_label": "\(s1)",
          "stage_2_label": "\(s2)",
          "stage_1_settled": false,
          "stage_1_market": { "id": 5165726 },
          "stage_2_market": { "id": 6173044 },
          "entries": [
            {
              "subject_key": "item-1",
              "subject": "The Odyssey",
              "detail": "Universal Pictures",
              "stage_1_market_id": 5165726,
              "stage_1_probability": 0.978,
              "stage_2_market_id": 6173044,
              "stage_2_probability": 0.525
            },
            {
              "subject_key": "item-2",
              "subject": "You Can See Everything",
              "detail": "Blow Out Productions",
              "stage_1_market_id": 5165726,
              "stage_1_probability": 0.865,
              "stage_2_market_id": 6173044,
              "stage_2_probability": 0.205
            },
            {
              "subject_key": "item-3",
              "subject": "Dune: Messiah",
              "detail": "Warner Bros.",
              "stage_1_market_id": 5165726,
              "stage_1_probability": 0.790,
              "stage_2_market_id": 6173044,
              "stage_2_probability": 0.145
            }
          ]
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(PairedMetricSet.self, from: Data(json.utf8))
    }

    private func ocrStrings<V: View>(for view: V, width: CGFloat = 358) throws -> String {
        let framed = view
            .frame(width: width)
            .padding(12)
            .background(Color.white)
            .environment(\.colorScheme, .light)
        let renderer = rendererForMeasurement(framed, at: .large)
        renderer.scale = 3.0
        let cgImage = try XCTUnwrap(renderer.cgImage)
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try handler.perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        return lines.joined(separator: " | ")
    }

    func testNativeGroupCardWithContainerKeepsFooterLinkAndSuppressesInlineExpand() throws {
        let oscarsRef = try XCTUnwrap(FeedThemeCollectionRef(
            slug: "oscars-2027",
            name: "Oscars 2027",
            revision: 74,
            collectionCount: 419
        ))
        let items = try [
            makeFuturesItem(id: 901, name: "Oscars 2027: Best Picture Winner", leader: "The Odyssey", prob: 0.34, category: "entertainment"),
            makeFuturesItem(id: 902, name: "Oscars 2027: Best Director Winner", leader: "Christopher Nolan", prob: 0.31, category: "entertainment"),
            makeFuturesItem(id: 903, name: "Oscars 2027: Best Production Design Winner", leader: "The Odyssey", prob: 0.70, category: "entertainment"),
            makeFuturesItem(id: 904, name: "Oscars 2027: Best International Feature Film Winner", leader: "La Bola Negra", prob: 0.84, category: "entertainment"),
            makeFuturesItem(id: 905, name: "Oscars 2027: Best Original Score Winner", leader: "Dune: Messiah", prob: 0.29, category: "entertainment"),
        ]

        var path = NavigationPath()
        let card = NativeGroupCard(
            title: "Oscars",
            items: items,
            kind: "theme",
            theme: "oscars",
            sharedQuestion: "Where do the Oscars races stand?",
            collectionRef: oscarsRef,
            navigationPath: Binding(get: { path }, set: { path = $0 })
        )
        let texts = try ocrStrings(for: card)

        XCTAssertTrue(texts.localizedCaseInsensitiveContains("Oscars 2027 collection"), "Footer link must be kept on container-backed NativeGroupCard; got: \(texts)")
        XCTAssertTrue(texts.localizedCaseInsensitiveContains("419 markets"), "Footer market count must be kept; got: \(texts)")
        XCTAssertFalse(texts.localizedCaseInsensitiveContains("All 5 markets"), "Container-backed NativeGroupCard must not trap taps on an inline 'All 5 markets' expand row; got: \(texts)")

        // Route resolution: banner/header/card (marketId == nil) AND member rows (marketId != nil)
        // both route to the container hub when `collectionRef` is present.
        XCTAssertEqual(
            NativeGroupCard.tapDestinationRoute(collectionRef: oscarsRef, marketId: nil),
            .containerHub(slug: "oscars-2027", name: "Oscars 2027")
        )
        XCTAssertEqual(
            NativeGroupCard.tapDestinationRoute(collectionRef: oscarsRef, marketId: 901),
            .containerHub(slug: "oscars-2027", name: "Oscars 2027")
        )
        let aiRef = try XCTUnwrap(FeedThemeCollectionRef(slug: "ai", name: "AI", revision: 170, collectionCount: 595))
        XCTAssertEqual(
            NativeGroupCard.tapDestinationRoute(collectionRef: aiRef, marketId: 905),
            .containerHub(slug: "ai", name: "AI")
        )
    }

    func testNativeGroupCardWithoutContainerPreservesInlineExpandControl() throws {
        let items = try (1...5).map { idx in
            try makeFuturesItem(id: 950 + idx, name: "Fed Rate Decision \(idx)", leader: "Hold", prob: 0.62, category: "economics")
        }
        var path = NavigationPath()
        let card = NativeGroupCard(
            title: "Fed & Rates",
            items: items,
            kind: "theme",
            theme: "fed",
            sharedQuestion: "What does the Fed do next?",
            collectionRef: nil,
            navigationPath: Binding(get: { path }, set: { path = $0 })
        )
        let texts = try ocrStrings(for: card)
        XCTAssertTrue(texts.localizedCaseInsensitiveContains("All 5 markets"), "Non-container NativeGroupCard must keep its inline expand footer; got: \(texts)")
        XCTAssertNil(NativeGroupCard.tapDestinationRoute(collectionRef: nil, marketId: nil))
        XCTAssertEqual(NativeGroupCard.tapDestinationRoute(collectionRef: nil, marketId: 951), .futuresDetail(id: 951))
    }

    func testPairedMetricCardResolvesContainerDestinationOnOscarsAndGenericBundles() throws {
        let oscarsSet = try decodePairedSet(
            setId: "oscars-2027-best-picture",
            kicker: "OSCARS 2027 · BEST PICTURE",
            title: "The Odyssey leads Best Picture",
            s1: "Nominated",
            s2: "Wins"
        )

        // 1. Discover Oscars paired-metric card: resolves oscars-2027 and keeps "All Oscars categories" footer link
        let oscarsCard = DiscoverPairedMetricCardView(
            set: oscarsSet,
            form: .pairedBarsTop5Expandable,
            onOpenMarket: { _ in },
            onOpenCollection: { _, _ in }
        )
        XCTAssertEqual(oscarsCard.resolvedContainerDestination?.slug, "oscars-2027")
        XCTAssertEqual(oscarsCard.resolvedContainerDestination?.name, "Oscars 2027")
        let oscarsTexts = try ocrStrings(for: oscarsCard)
        XCTAssertTrue(oscarsTexts.localizedCaseInsensitiveContains("All Oscars categories"), "Oscars paired-metric card must keep its footer link; got: \(oscarsTexts)")

        // 2. Inside the already-open Oscars container page (`isOscarsCollectionSurface: true`, no explicit override):
        // must NOT resolve a duplicate self-link
        let inHubCard = DiscoverPairedMetricCardView(
            set: oscarsSet,
            form: .pairedBarsTop5Expandable,
            isOscarsCollectionSurface: true
        )
        XCTAssertNil(inHubCard.resolvedContainerDestination)

        // 3. Second container-backed paired-metric card (e.g. NHL Playoffs): resolves containerDestination and keeps footer link
        let nhlSet = try decodePairedSet(
            setId: "nhl-playoffs-cup",
            kicker: "NHL 2026-27",
            title: "Playoffs & Stanley Cup",
            s1: "Playoffs",
            s2: "Wins Cup"
        )
        let nhlCard = DiscoverPairedMetricCardView(
            set: nhlSet,
            form: .pairedBarsTop5Expandable,
            containerDestination: ("nhl-playoffs-2026-27", "NHL Playoffs"),
            onOpenMarket: { _ in },
            onOpenCollection: { _, _ in }
        )
        XCTAssertEqual(nhlCard.resolvedContainerDestination?.slug, "nhl-playoffs-2026-27")
        let nhlTexts = try ocrStrings(for: nhlCard)
        XCTAssertTrue(nhlTexts.localizedCaseInsensitiveContains("NHL Playoffs collection"), "Generic container-backed paired-metric card must keep its collection footer link; got: \(nhlTexts)")
    }
}
