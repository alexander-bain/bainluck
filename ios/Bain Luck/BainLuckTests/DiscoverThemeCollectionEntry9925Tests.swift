import XCTest
@testable import Bain_Luck

/// #9925 — a grouped Discover theme card opens its already-published collection.
///
/// The server's `collection_ref` (`backend/app/utils/theme_collection_ref.py`,
/// web `FeedThemeCollectionRef`) is the only source of the destination. These pin
/// that the iPhone reads exactly that contract: a valid ref survives decoding and
/// every bundle rebuild, a missing or malformed one costs the link and never the
/// bundle, a comparison bundle never links, and the card's route is the existing
/// hub keyed by the server's slug alone.
///
/// The card body is not reachable from XCTest here (see
/// `DiscoverCardsKeepWholeWordsAtAccessibilitySizes10313Tests`), so its wiring is
/// pinned by source census; the tap → hub → member → Back path is a simulator walk.
final class DiscoverThemeCollectionEntry9925Tests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-07-27T12:00:00Z")!

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func futuresChildJSON(id: Int, status: String = "open", category: String = "entertainment") -> String {
        """
        {
          "type": "futures",
          "score": 90,
          "data": {
            "id": \(id),
            "name": "Who wins market \(id)?",
            "llm_sport_category": "\(category)",
            "source": "kalshi",
            "status": "\(status)",
            "resolution_date": null,
            "top_outcomes": [{"id": \(id * 10), "name": "Nominee", "probability": 0.55, "rank": 1, "movement": 0.02}],
            "outcome_count": 1
          }
        }
        """
    }

    private static let validRef = #"{"slug":"oscars-2027","name":"Oscars 2027","revision":4,"collection_count":37}"#

    /// A bundle feed item whose `collection_ref` is the raw JSON given (or absent).
    private func bundleItem(kind: String = "theme", ref: String?, children: [String]? = nil) throws -> FeedItem {
        let kids = children ?? [futuresChildJSON(id: 1), futuresChildJSON(id: 2)]
        let refField = ref.map { #","collection_ref":\#($0)"# } ?? ""
        let json = """
        {
          "type": "bundle",
          "score": 95,
          "data": {
            "id": "theme:oscars",
            "title": "Oscars",
            "kind": "\(kind)",
            "shared_question": "Who wins at the Oscars?",
            "items": [\(kids.joined(separator: ","))]\(refField)
          }
        }
        """
        return try decoder().decode(FeedItem.self, from: Data(json.utf8))
    }

    private func bundle(kind: String = "theme", ref: String?) throws -> FeedBundle {
        try XCTUnwrap(try bundleItem(kind: kind, ref: ref).bundle, "the bundle itself must decode")
    }

    // MARK: - Decoding the four-field contract

    func testAValidRefDecodesExactlyTheFourFields() throws {
        let ref = try XCTUnwrap(try bundle(ref: Self.validRef).collectionRef)
        XCTAssertEqual(ref.slug, "oscars-2027")
        XCTAssertEqual(ref.name, "Oscars 2027")
        XCTAssertEqual(ref.revision, 4)
        XCTAssertEqual(ref.collectionCount, 37)
    }

    func testAbsentOrNullRefIsNoLinkAndTheBundleIsWhole() throws {
        for raw in [nil, "null"] as [String?] {
            let b = try bundle(ref: raw)
            XCTAssertNil(b.collectionRef, "ref \(raw ?? "absent") must read as no link")
            XCTAssertEqual(b.items.count, 2)
            XCTAssertEqual(b.title, "Oscars")
            XCTAssertEqual(b.sharedQuestion, "Who wins at the Oscars?")
        }
    }

    func testAMalformedRefCostsTheLinkNeverTheBundle() throws {
        let malformed: [String: String] = [
            "missing name": #"{"slug":"oscars-2027","revision":4,"collection_count":37}"#,
            "missing count": #"{"slug":"oscars-2027","name":"Oscars 2027","revision":4}"#,
            "revision as string": #"{"slug":"oscars-2027","name":"Oscars 2027","revision":"4","collection_count":37}"#,
            "count as bool": #"{"slug":"oscars-2027","name":"Oscars 2027","revision":4,"collection_count":true}"#,
            "slug as number": #"{"slug":2027,"name":"Oscars 2027","revision":4,"collection_count":37}"#,
            "zero revision": #"{"slug":"oscars-2027","name":"Oscars 2027","revision":0,"collection_count":37}"#,
            "negative count": #"{"slug":"oscars-2027","name":"Oscars 2027","revision":4,"collection_count":-1}"#,
            "zero count": #"{"slug":"oscars-2027","name":"Oscars 2027","revision":4,"collection_count":0}"#,
            "empty name": #"{"slug":"oscars-2027","name":"","revision":4,"collection_count":37}"#,
            "blank name": #"{"slug":"oscars-2027","name":"   ","revision":4,"collection_count":37}"#,
            "empty slug": #"{"slug":"","name":"Oscars 2027","revision":4,"collection_count":37}"#,
            "uppercase slug": #"{"slug":"Oscars-2027","name":"Oscars 2027","revision":4,"collection_count":37}"#,
            "path slug": #"{"slug":"oscars/2027","name":"Oscars 2027","revision":4,"collection_count":37}"#,
            "traversal slug": #"{"slug":"../admin","name":"Oscars 2027","revision":4,"collection_count":37}"#,
            "leading hyphen": #"{"slug":"-oscars","name":"Oscars 2027","revision":4,"collection_count":37}"#,
            "trailing hyphen": #"{"slug":"oscars-","name":"Oscars 2027","revision":4,"collection_count":37}"#,
            "double hyphen": #"{"slug":"oscars--2027","name":"Oscars 2027","revision":4,"collection_count":37}"#,
            "trailing newline": #"{"slug":"oscars-2027\n","name":"Oscars 2027","revision":4,"collection_count":37}"#,
            "non-ascii slug": #"{"slug":"óscars-2027","name":"Oscars 2027","revision":4,"collection_count":37}"#,
            "over-long slug": #"{"slug":"\#(String(repeating: "a", count: 201))","name":"Oscars 2027","revision":4,"collection_count":37}"#,
            "string ref": #""oscars-2027""#,
            "array ref": #"["oscars-2027"]"#,
            "number ref": "7",
        ]
        for (label, raw) in malformed {
            let b = try bundle(ref: raw)
            XCTAssertNil(b.collectionRef, "\(label): a ref that fails admission is no ref")
            XCTAssertEqual(b.items.map(\.id), ["futures-1", "futures-2"], "\(label): the bundle and its members survive")
            XCTAssertEqual(b.kind, "theme", "\(label)")
        }
    }

    func testTheLongestAdmittedSlugStillLinks() throws {
        let slug = String(repeating: "a", count: 200)
        let raw = #"{"slug":"\#(slug)","name":"Long","revision":1,"collection_count":1}"#
        XCTAssertEqual(try bundle(ref: raw).collectionRef?.slug, slug)
    }

    func testTheNameIsTrimmedNotRewritten() throws {
        let raw = #"{"slug":"oscars-2027","name":"  Oscars 2027 ","revision":4,"collection_count":37}"#
        XCTAssertEqual(try bundle(ref: raw).collectionRef?.name, "Oscars 2027")
    }

    func testTheMemberwiseInitAdmitsByTheSameRule() {
        XCTAssertNotNil(FeedThemeCollectionRef(slug: "ai-2026", name: "AI", revision: 1, collectionCount: 3))
        XCTAssertNil(FeedThemeCollectionRef(slug: "AI", name: "AI", revision: 1, collectionCount: 3))
        XCTAssertNil(FeedThemeCollectionRef(slug: "ai", name: " ", revision: 1, collectionCount: 3))
        XCTAssertNil(FeedThemeCollectionRef(slug: "ai", name: "AI", revision: 0, collectionCount: 3))
        XCTAssertNil(FeedThemeCollectionRef(slug: "ai", name: "AI", revision: 1, collectionCount: 0))
    }

    // MARK: - Only a theme links

    func testOnlyAThemeBundleOffersItsRef() throws {
        XCTAssertNotNil(try bundle(kind: "theme", ref: Self.validRef).themeCollectionRef)
        let comparison = try bundle(kind: "comparison", ref: Self.validRef)
        XCTAssertNotNil(comparison.collectionRef, "the payload is decoded as served")
        XCTAssertNil(comparison.themeCollectionRef, "a comparison card never links, whatever it carries")
        XCTAssertNil(try bundle(kind: "theme", ref: nil).themeCollectionRef)
    }

    // MARK: - Every rebuild keeps the exact ref and only the admitted members

    func testWithItemsPreservesTheExactRef() throws {
        let b = try bundle(ref: Self.validRef)
        let rebuilt = b.withItems(Array(b.items.prefix(1)))
        XCTAssertEqual(rebuilt.collectionRef, b.collectionRef)
        XCTAssertEqual(rebuilt.items.map(\.id), ["futures-1"])
        XCTAssertEqual(rebuilt.id, b.id)
        XCTAssertEqual(rebuilt.kind, b.kind)
        XCTAssertEqual(rebuilt.sharedQuestion, b.sharedQuestion)
        XCTAssertEqual(b.withItems([]).collectionRef, b.collectionRef)
    }

    func testTheMemberwiseInitDefaultsToNoLink() {
        XCTAssertNil(FeedBundle(id: "x", title: "X", items: [], kind: "theme", comparisonTheme: nil).collectionRef)
    }

    func testSanitizingKeepsTheRefWithoutResurrectingAnExcludedMember() throws {
        let item = try bundleItem(ref: Self.validRef, children: [
            futuresChildJSON(id: 1, status: "resolved"),
            futuresChildJSON(id: 2),
        ])
        let sanitized = DiscoverView.sanitizedFeedItems([item], now: now)
        let b = try XCTUnwrap(sanitized.first?.bundle)
        XCTAssertEqual(b.items.map(\.id), ["futures-2"], "the resolved member stays out")
        XCTAssertEqual(b.themeCollectionRef?.slug, "oscars-2027", "the link survives the rebuild")
        XCTAssertEqual(b.collectionRef?.collectionCount, 37, "the page count is the server's, not the shown preview")
        XCTAssertEqual(DiscoverView.eligibleBundleItems(b, now: now).map(\.id), ["futures-2"])
    }

    func testAnAllStaleThemeIsDroppedLinkAndAll() throws {
        let item = try bundleItem(ref: Self.validRef, children: [futuresChildJSON(id: 1, status: "resolved")])
        XCTAssertTrue(DiscoverView.sanitizedFeedItems([item], now: now).isEmpty,
                      "a ref never keeps a settled card alive")
    }

    // MARK: - The row's words and route

    func testTheRowNamesTheCollectionAndItsFullCount() throws {
        let ref = try XCTUnwrap(FeedThemeCollectionRef(slug: "oscars-2027", name: "Oscars 2027", revision: 4, collectionCount: 37))
        XCTAssertEqual(DiscoverGroupRows.collectionTitle(for: ref), "View the Oscars 2027 collection")
        XCTAssertEqual(DiscoverGroupRows.collectionCountLabel(for: ref), "37 markets")
        let one = try XCTUnwrap(FeedThemeCollectionRef(slug: "oscars-2027", name: "Oscars 2027", revision: 4, collectionCount: 1))
        XCTAssertEqual(DiscoverGroupRows.collectionCountLabel(for: one), "1 market")
    }

    func testTheRouteIsTheExistingHubKeyedByTheServerSlug() throws {
        let ref = try XCTUnwrap(FeedThemeCollectionRef(slug: "oscars-2027", name: "Oscars 2027", revision: 4, collectionCount: 37))
        XCTAssertEqual(DiscoverGroupRows.collectionRoute(for: ref), .containerHub(slug: "oscars-2027", name: "Oscars 2027"))
    }

    // MARK: - Wiring (source census)

    private func discoverViewSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Views/DiscoverView.swift")
        return try String(contentsOf: url, encoding: .utf8)
            .components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
    }

    private func occurrences(of needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }

    func testTheGroupedPathCarriesOnlyTheThemeRefToTheCard() throws {
        let text = try discoverViewSource()
        XCTAssertEqual(occurrences(of: "sharedQuestion: bundle.sharedQuestion, collectionRef: bundle.themeCollectionRef ))", in: text), 1,
                       "the API bundle's grouped card takes the theme-only ref")
        XCTAssertEqual(occurrences(of: "collectionRef: bundle.collectionRef", in: text), 0,
                       "the raw ref would let a comparison card link")
        XCTAssertEqual(occurrences(of: "sharedQuestion: sharedQuestion, collectionRef: collectionRef, navigationPath: $navigationPath)", in: text), 1,
                       "the card receives the ref the grouping produced")
        XCTAssertEqual(occurrences(of: "result.append(.group(title: groupTitles[grouping.key] ?? grouping.title, items: group))", in: text), 1,
                       "client-side futures groups have no server ref and must never invent one")
    }

    func testTheRowIsAButtonOnTheCardsOwnStack() throws {
        let text = try discoverViewSource()
        XCTAssertEqual(occurrences(of: "if let collectionRef { Divider() collectionRow(collectionRef) }", in: text), 1)
        XCTAssertEqual(occurrences(of: "return Button { navigationPath.append(DiscoverGroupRows.collectionRoute(for: ref)) } label:", in: text), 1,
                       "a Button, not a NavigationLink: a link turns a swipe into navigation (#7074)")
        XCTAssertEqual(occurrences(of: ".accessibilityIdentifier(\"discover.group.collection\")", in: text), 1)
        XCTAssertEqual(occurrences(of: "let countOnOwnLine = dynamicTypeSize.isAccessibilitySize", in: text), 1,
                       "at accessibility sizes the count takes its own line so the name reads whole")
    }
}
