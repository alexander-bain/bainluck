import SwiftUI
import XCTest
@testable import Bain_Luck

/// #13103 Part 2 (`1.0.8`): Every set has a Share button on its page (`ContainerHubView` toolbar)
/// and in its card's press-and-hold menu, sharing `https://bainluck.com/collections/<slug>`.
@MainActor
final class SetShareButton13103Tests: XCTestCase {

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func decodeItem(_ dict: [String: Any]) throws -> FeedItem {
        let data = try JSONSerialization.data(withJSONObject: dict)
        return try makeDecoder().decode(FeedItem.self, from: data)
    }

    func testCollectionShareURLBuildsCanonicalPlainLink() {
        XCTAssertEqual(
            collectionShareURL("oscars-2027"),
            "https://bainluck.com/collections/oscars-2027"
        )
        XCTAssertEqual(
            collectionShareURL("machinery-nfl-week"),
            "https://bainluck.com/collections/machinery-nfl-week"
        )
        XCTAssertEqual(
            collectionShareURL("roundup-cfb-playoff-picture"),
            "https://bainluck.com/collections/roundup-cfb-playoff-picture"
        )
        XCTAssertFalse(
            collectionShareURL("oscars-2027").contains("?"),
            "Set share URLs must be clean `bainluck.com/collections/<slug>` links for message previews"
        )
        XCTAssertEqual(
            collectionShareURL("  oscars-2027  "),
            "https://bainluck.com/collections/oscars-2027"
        )
    }

    func testContainerHubShareLinkURLAndShareInstrumentationRow() {
        XCTAssertEqual(
            ContainerHubView.shareLinkURL(slug: "oscars-2027").absoluteString,
            "https://bainluck.com/collections/oscars-2027"
        )

        let event = ShareInstrumentation.shareOpenedEvent(
            itemType: "collection",
            itemId: "oscars-2027",
            itemName: "Oscars 2027",
            category: nil,
            surface: .collectionDetail
        )
        XCTAssertEqual(event.action, "share")
        XCTAssertEqual(event.source, "collection_detail")
        XCTAssertEqual(event.itemType, "collection")
        XCTAssertEqual(event.itemId, "oscars-2027")
        XCTAssertEqual(event.itemName, "Oscars 2027")
        XCTAssertEqual(event.category, "other")
        XCTAssertEqual(event.surface, "native")
    }

    func testEverySetCardFormResolvesCanonicalCollectionSlug() throws {
        // 1. Producer collection FeedItem (`DiscoverCollectionCard`)
        let collectionItem = try decodeItem([
            "type": "collection",
            "score": 35,
            "data": [
                "type": "collection",
                "id": 901,
                "name": "NFL Week 11",
                "text": "NFL Week 11",
                "slug": "nfl-2026-week-11",
                "state": "published",
                "revision": 1,
                "edition": ["kind": "nfl_week", "league": "nfl", "season": 2026, "stage": "Regular Season", "week": 11],
                "status": "upcoming",
                "game_count": 14,
                "question_count": 3,
                "matched_event_ids": [15330001],
                "destination": [
                    "kind": "container",
                    "slug": "nfl-2026-week-11",
                    "web": "/collection/nfl-2026-week-11",
                    "api": "/api/containers/nfl-2026-week-11"
                ]
            ]
        ])
        XCTAssertEqual(CardContextMenu.collectionSlug(for: collectionItem), "nfl-2026-week-11")

        // 2. Theme bundle (`NativeGroupCard` with `themeCollectionRef`)
        let themeMember = try decodeItem([
            "type": "futures",
            "score": 88,
            "data": [
                "id": 6173044,
                "name": "Oscar Winner: Best Picture",
                "llm_sport_category": "entertainment",
                "top_outcomes": [["id": 1, "name": "One Battle After Another", "probability": 0.42]]
            ]
        ])
        let themeRef = try makeDecoder().decode(
            FeedThemeCollectionRef.self,
            from: JSONSerialization.data(withJSONObject: [
                "slug": "oscars-2027",
                "name": "Oscars 2027",
                "revision": 1,
                "collection_count": 419
            ])
        )
        XCTAssertEqual(
            DiscoverView.groupCollectionSlug(
                title: "Where do the Oscars races stand?",
                kind: "theme",
                theme: "oscars",
                collectionRef: themeRef,
                groupItems: [themeMember],
                feedItems: [themeMember]
            ),
            "oscars-2027"
        )

        // 3. Machinery roundup bundle (`MachineryDiscoverEntryCardView`)
        let machineryBundleItem = try decodeItem([
            "type": "bundle",
            "score": 90,
            "data": [
                "kind": "roundup",
                "title": "NFL Week 11 Slate",
                "collection_ref": [
                    "slug": "machinery-nfl-week",
                    "name": "NFL Week 11 Slate",
                    "revision": 1,
                    "collection_count": 14
                ],
                "roundup": [
                    "machinery_card": [
                        "slug": "machinery-nfl-week",
                        "title": "NFL Week 11 Slate",
                        "card_form": "slate_card",
                        "rows": [
                            [
                                "id": "r1",
                                "label": "Chiefs at Bills",
                                "right_value": "54%"
                            ]
                        ]
                    ]
                ],
                "items": []
            ]
        ])
        XCTAssertEqual(CardContextMenu.collectionSlug(for: machineryBundleItem), "machinery-nfl-week")
        XCTAssertEqual(
            DiscoverView.groupCollectionSlug(
                title: "NFL Week 11 Slate",
                kind: "roundup",
                theme: nil,
                collectionRef: nil,
                groupItems: [machineryBundleItem],
                feedItems: [machineryBundleItem]
            ),
            "machinery-nfl-week"
        )

        // 4. Unbacked 2-market prefix group has no container slug (must never invent one)
        XCTAssertNil(
            DiscoverView.groupCollectionSlug(
                title: "Ad-hoc Pair",
                kind: nil,
                theme: nil,
                collectionRef: nil,
                groupItems: [themeMember],
                feedItems: [themeMember]
            )
        )
    }

    func testSetShareSheetPresenterForwardsCanonicalURL() {
        var captured: [URL] = []
        SetShareSheetPresenter13103.shared.testInterceptPresent = { captured.append($0) }
        defer { SetShareSheetPresenter13103.shared.testInterceptPresent = nil }

        SetShareSheetPresenter13103.shared.present(urlString: collectionShareURL("oscars-2027"))
        XCTAssertEqual(captured.map(\.absoluteString), ["https://bainluck.com/collections/oscars-2027"])
    }

    func testEverySetSurfaceWiresShareButtonAndPressAndHoldMenu() throws {
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")

        let hubSource = try String(contentsOf: appRoot.appendingPathComponent("Views/ContainerHubView.swift"), encoding: .utf8)
        XCTAssertTrue(hubSource.contains("ToolbarItem(placement: .confirmationAction)"))
        XCTAssertTrue(hubSource.contains("ShareLink("))
        XCTAssertTrue(hubSource.contains(".accessibilityIdentifier(\"hub.shareButton\")"))
        XCTAssertTrue(hubSource.contains(".recordsShareOpened { recordShareOpened() }"))
        XCTAssertTrue(hubSource.contains("surface: .collectionDetail"))

        let menuSource = try String(contentsOf: appRoot.appendingPathComponent("Components/CardContextMenu.swift"), encoding: .utf8)
        XCTAssertTrue(menuSource.contains("struct CollectionContextMenuItems: View"))
        XCTAssertTrue(menuSource.contains("let url = collectionShareURL(slug)"))
        XCTAssertTrue(menuSource.contains("SetShareSheetPresenter13103.shared.present(urlString: url)"))

        let discoverSource = try String(contentsOf: appRoot.appendingPathComponent("Views/DiscoverView.swift"), encoding: .utf8)
        XCTAssertTrue(discoverSource.contains("discoverGroupCardMenu("))
        XCTAssertTrue(discoverSource.contains("static func groupCollectionSlug("))

        let browseSource = try String(contentsOf: appRoot.appendingPathComponent("Views/BrowseCollectionsView.swift"), encoding: .utf8)
        XCTAssertTrue(browseSource.contains("CollectionContextMenuItems("))

        let searchRowSource = try String(contentsOf: appRoot.appendingPathComponent("Views/SearchCollectionRow.swift"), encoding: .utf8)
        XCTAssertTrue(searchRowSource.contains("CollectionContextMenuItems("))

        // #13111 follow-up 2: owner-only unpublished preview cards must NOT offer Copy Link or Share.
        let previewStart = try XCTUnwrap(discoverSource.range(of: "let unservedPreviewItems ="))
        let previewEnd = try XCTUnwrap(discoverSource.range(of: ".accessibilityIdentifier(\"discover.ownerMachineryPreview\")", range: previewStart.upperBound..<discoverSource.endIndex))
        let previewBlock = String(discoverSource[previewStart.lowerBound..<previewEnd.upperBound])
        XCTAssertFalse(previewBlock.contains("CollectionContextMenuItems("))
        XCTAssertFalse(previewBlock.contains(".contextMenu"))
        XCTAssertTrue(hubSource.contains("if isPubliclyShareable {"))
    }

    func testSetLandingBarCarriesSetNameAndHeaderCarriesReasonInsteadOfPlumbingCount() throws {
        // Deep links enter with fallback `displayName == "Collection"`; bar stays empty until loaded, then shows the set's name.
        XCTAssertEqual(
            ContainerHubView.resolvedNavigationTitle(displayName: "Collection", slug: "oscars-2027", loadedTitle: nil),
            ""
        )
        XCTAssertEqual(
            ContainerHubView.resolvedNavigationTitle(displayName: "Collection", slug: "oscars-2027", loadedTitle: "Oscars 2027"),
            "Oscars 2027"
        )
        XCTAssertEqual(
            ContainerHubView.resolvedNavigationTitle(
                displayName: "Collection",
                slug: "machinery-nfl-week",
                loadedTitle: "Broncos at Steelers headlines the Nov 19–27 slate"
            ),
            ""
        )

        let aiPage = try ContainerHubFixture.decode("representative_ai_page_1")
        let aiPresentation = ContainerHubPresentation(response: aiPage)
        XCTAssertEqual(
            aiPresentation.headerReasonLine,
            "Live market chances across AI models, milestones, and regulation."
        )
        XCTAssertEqual(aiPresentation.pagerCountLabel, "1 of 2 markets")
        XCTAssertEqual(aiPresentation.countLabel, "1 of 2 markets loaded")

        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
        let hubSource = try String(contentsOf: appRoot.appendingPathComponent("Views/ContainerHubView.swift"), encoding: .utf8)
        XCTAssertFalse(hubSource.contains("presentation.countLabel"), "Top header must show headerReasonLine, never plumbing 'loaded' counts")
        XCTAssertTrue(hubSource.contains("presentation.headerReasonLine"))
        XCTAssertTrue(hubSource.contains("presentation.pagerCountLabel"))
    }
}
