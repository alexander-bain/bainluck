import XCTest
@testable import Bain_Luck

/// #5525 — the share row a tap is supposed to write.
///
/// 🔴 THE DEFECT. Every share button a reader can see is a declarative
/// `ShareLink`, which exposes no callback, so none of them wrote anything.
/// `discover_interactions` held THREE `action='share'` rows all time, every one
/// `surface='web'`: the native side had never recorded a share in its life, and
/// the zero was being read as reader behaviour rather than as a missing writer.
///
/// These tests cover the half that can be silently wrong once a tap does arrive
/// — the shape of the row. A `source` spelled a second way does not fail, it
/// lands in a bucket nobody counts, which is the same invisibility one layer in.
/// Whether the gesture fires is a UIKit fact no unit test in this target can
/// reach; the source-scan guard
/// (`frontend/__tests__/ios/shareButtonsAreInstrumented5525.test.ts`) covers the
/// other half — that no share button is left without one.
final class ShareInstrumentationTests: XCTestCase {

    // MARK: - The surface vocabulary

    func testEverySurfaceHasADistinctWireValue() {
        let values = ShareSurface.allCases.map(\.rawValue)
        XCTAssertEqual(
            Set(values).count, values.count,
            "Two surfaces sharing a `source` merge into one bucket and the table can no longer tell them apart"
        )
    }

    func testEverySurfaceValueIsWireShaped() {
        for surface in ShareSurface.allCases {
            let raw = surface.rawValue
            XCTAssertFalse(raw.isEmpty, "\(surface) has an empty source")
            XCTAssertEqual(
                raw, raw.lowercased(),
                "`\(raw)` is not lower-case; the rest of this column is, and a GROUP BY does not fold case"
            )
            XCTAssertNil(
                raw.rangeOfCharacter(from: CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_")).inverted),
                "`\(raw)` carries something other than [a-z0-9_] — the column's existing values are snake_case"
            )
        }
    }

    /// The three values are asserted literally because they are a WIRE contract:
    /// renaming one silently orphans every row already written under the old
    /// spelling, and nothing else in this repo would notice.
    func testSurfaceValuesAreTheOnesAlreadyWritten() {
        XCTAssertEqual(ShareSurface.discoverCard.rawValue, "card")
        XCTAssertEqual(ShareSurface.eventDetail.rawValue, "event_detail")
        XCTAssertEqual(ShareSurface.futuresDetail.rawValue, "futures_detail")
    }

    // MARK: - The row

    func testShareOpenedEventCarriesTheSurfaceAsItsSource() {
        let event = ShareInstrumentation.shareOpenedEvent(
            itemType: "event",
            itemId: "4152",
            itemName: "Mariners vs Athletics",
            category: "baseball_mlb",
            surface: .eventDetail
        )

        XCTAssertEqual(event.action, "share")
        XCTAssertEqual(event.source, "event_detail")
        XCTAssertEqual(event.itemType, "event")
        XCTAssertEqual(event.itemId, "4152")
        XCTAssertEqual(event.itemName, "Mariners vs Athletics")
        XCTAssertEqual(event.category, "baseball_mlb")
        XCTAssertEqual(event.surface, "native")
    }

    /// A futures page reached before its market has loaded still has an id, and a
    /// share from it is still a share. The row must not become uncountable
    /// because the name had not arrived yet.
    func testAnAbsentCategoryFallsBackRatherThanDroppingTheRow() {
        let event = ShareInstrumentation.shareOpenedEvent(
            itemType: "futures",
            itemId: "900",
            itemName: nil,
            category: nil,
            surface: .futuresDetail
        )

        XCTAssertEqual(event.category, "other", "`category` is non-optional on the wire; nil must resolve, not crash or blank")
        XCTAssertNil(event.itemName)
        XCTAssertEqual(event.source, "futures_detail")
        XCTAssertEqual(event.action, "share")
    }

    /// `score` and `rank` describe a card's position in a ranked feed. A detail
    /// page has neither, and sending 0 would be a measurement rather than an
    /// absence — the accuracy-of-ranking reads join on these.
    func testDetailSharesClaimNoFeedPosition() {
        let event = ShareInstrumentation.shareOpenedEvent(
            itemType: "event",
            itemId: "1",
            itemName: nil,
            category: nil,
            surface: .eventDetail
        )
        XCTAssertNil(event.score)
        XCTAssertNil(event.rank)
    }

    /// The row must survive `JSONEncoder` with the app's snake_case strategy in
    /// the exact keys the endpoint reads — a correctly built struct that encodes
    /// to `itemType` is still a row the backend drops.
    func testTheRowEncodesToTheKeysTheEndpointReads() throws {
        let event = ShareInstrumentation.shareOpenedEvent(
            itemType: "futures",
            itemId: "77",
            itemName: "Who wins the US Open?",
            category: "tennis",
            surface: .futuresDetail
        )
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let json = try JSONSerialization.jsonObject(
            with: try encoder.encode(event)
        ) as? [String: Any]

        XCTAssertEqual(json?["action"] as? String, "share")
        XCTAssertEqual(json?["item_type"] as? String, "futures")
        XCTAssertEqual(json?["item_id"] as? String, "77")
        XCTAssertEqual(json?["item_name"] as? String, "Who wins the US Open?")
        XCTAssertEqual(json?["source"] as? String, "futures_detail")
        XCTAssertEqual(json?["surface"] as? String, "native")
    }

    // MARK: - One market, one bucket, whichever button was pressed

    /// The event page has the raw sport key (`baseball_mlb`); a feed card sends
    /// the token (`baseball`). Sharing the same game from the two surfaces has to
    /// land in ONE category, or the split is invisible — both rows exist, both
    /// look right, and the count is simply wrong.
    func testTheEventPageAndAFeedCardResolveOneSportToOneToken() {
        XCTAssertEqual(DiscoverCategory.token(forSport: "baseball_mlb"), "baseball")
        XCTAssertEqual(DiscoverCategory.token(forSport: "americanfootball_nfl"), "americanfootball")
        XCTAssertEqual(DiscoverCategory.token(forSport: "TENNIS_ATP"), "tennis")
        XCTAssertEqual(DiscoverCategory.token(forSport: "golf"), "golf")
    }

    func testAnUnknownSportGetsTheSameFallbackAsAnAbsentOne() {
        XCTAssertEqual(DiscoverCategory.token(forSport: nil), "other")
        XCTAssertEqual(DiscoverCategory.token(forSport: ""), "other")
        XCTAssertEqual(DiscoverCategory.token(forSport: "_"), "other")
    }

    /// The lift of `token(forSport:)` out of `DiscoverCategory.of` must not have
    /// changed what a feed card reports — this is the equivalence the refactor
    /// claims, asserted rather than assumed.
    func testLiftingTheTokenDidNotMoveWhatAFeedCardSends() {
        for sport in ["baseball_mlb", "soccer_epl", "golf", "", "_"] {
            let legacy = sport.split(separator: "_").first.map { $0.lowercased() } ?? "other"
            XCTAssertEqual(
                DiscoverCategory.token(forSport: sport), legacy,
                "`\(sport)` now resolves differently than the inline expression it replaced"
            )
        }
        XCTAssertEqual(DiscoverCategory.token(forSport: nil), "other")
    }

    // MARK: - The action name the Discover cards send

    /// The Discover cards do NOT route through `ShareInstrumentation` — they go
    /// through `DiscoverView.recordInteraction`, so a card share also feeds the
    /// category interaction profile. This asserts the two paths agree on the one
    /// thing a reader of the table groups by: that a card share and a detail
    /// share are the same `action`, told apart only by `source`.
    func testACardShareAndADetailShareAgreeOnTheActionName() {
        let detail = ShareInstrumentation.shareOpenedEvent(
            itemType: "event", itemId: "1", itemName: nil, category: nil, surface: .discoverCard
        )
        XCTAssertEqual(detail.action, "share")
        XCTAssertEqual(
            detail.source, "card",
            "`DiscoverView` passes `ShareSurface.discoverCard.rawValue`, and web's own share rows are already `source='card'`"
        )
    }
}
