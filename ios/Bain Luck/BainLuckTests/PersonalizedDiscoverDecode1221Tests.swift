import XCTest
@testable import Bain_Luck

final class PersonalizedDiscoverDecode1221Tests: XCTestCase {
    // Values and card shapes from the signed-in phone response captured on
    // 2026-09-16 at 15:38 PDT. No account identifiers or preferences are stored.
    // The same production decoder retained only the UFC and golf cards because
    // personalized base_score values (including bundle children) have decimals.
    private let page = #"""
    {
      "total": 114, "limit": 50, "offset": 0, "has_more": true,
      "items": [
        {"type":"futures", "score":62, "base_score":82.738,
         "personalized":true, "multiplier":0.75,
         "data":{"id":1,"name":"Big Brother Season 28 · Winner",
                 "llm_sport_category":"entertainment"}},
        {"type":"futures", "score":62, "base_score":81.656,
         "personalized":true, "multiplier":0.76,
         "data":{"id":2,"name":"Will the Iranian regime fall before 2027?",
                 "llm_sport_category":"politics"}},
        {"type":"bundle", "score":62.0,
         "data":{"id":"ratings","title":"Rotten Tomatoes score ranges",
                 "items":[
                   {"type":"futures","score":62,"base_score":71.184,
                    "personalized":true,
                    "data":{"id":3,"name":"Upcoming movie score range",
                            "llm_sport_category":"entertainment"}},
                   {"type":"futures","score":61,"base_score":70,
                    "personalized":true,
                    "data":{"id":4,"name":"Another movie score range",
                            "llm_sport_category":"entertainment"}}
                 ]}},
        {"type":"concept","score":71,
         "data":{"key":"event:ufc:26sep19","name":"331: Van vs Pantoja",
                 "domain":"ufc"}},
        {"type":"tournament","score":90,
         "data":{"key":"biltmore_championship_asheville",
                 "name":"Biltmore Championship Asheville"}}
      ]
    }
    """#

    private func decode(_ json: String) throws -> FeedResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedResponse.self, from: Data(json.utf8))
    }

    func testSignedInPageKeepsEntertainmentPoliticsAndSportsTogether() throws {
        let response = try decode(page)
        XCTAssertEqual(response.items.map(\.type),
                       ["futures", "futures", "bundle", "concept", "tournament"])
        XCTAssertEqual(response.items.compactMap(\.futures).map(\.id), [1, 2])
        XCTAssertEqual(response.items.compactMap(\.bundle).first?.items.compactMap(\.futures).map(\.id),
                       [3, 4], "one fractional child must not discard a whole story")
        XCTAssertEqual(response.total, 114)
        XCTAssertTrue(response.hasMore)
    }

    func testPersonalizationMetadataDoesNotChangeWhichCardsDecode() throws {
        var anonymous = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(page.utf8)) as? [String: Any])
        func withoutPersonalization(_ input: [String: Any]) -> [String: Any] {
            var item = input
            item.removeValue(forKey: "base_score")
            item.removeValue(forKey: "personalized")
            item.removeValue(forKey: "multiplier")
            if var data = item["data"] as? [String: Any],
               let children = data["items"] as? [[String: Any]] {
                data["items"] = children.map(withoutPersonalization)
                item["data"] = data
            }
            return item
        }
        anonymous["items"] = try XCTUnwrap(anonymous["items"] as? [[String: Any]])
            .map(withoutPersonalization)
        let anonymousJSON = try XCTUnwrap(String(data: JSONSerialization.data(withJSONObject: anonymous),
                                               encoding: .utf8))
        XCTAssertEqual(try decode(page).items.map(\.id),
                       try decode(anonymousJSON).items.map(\.id),
                       "anonymous-only testing must not conceal signed-in card loss")
    }

    func testFractionalScoreSurvivesDecodeAndBundleCopyWithoutRounding() throws {
        let response = try decode(page)
        let first = try XCTUnwrap(response.items.first(where: { $0.futures?.id == 1 }))
        XCTAssertEqual(Double(try XCTUnwrap(first.baseScore)), 82.738, accuracy: 0.000001)
        XCTAssertEqual(first.score, 62, "the served ranking score is a separate field")
        let group = try XCTUnwrap(response.items.first(where: { $0.bundle != nil }))
        let bundle = try XCTUnwrap(group.bundle)
        let copied = group.withBundle(bundle.withItems(bundle.items))
        let child = try XCTUnwrap(copied.bundle?.items.first)
        XCTAssertEqual(Double(try XCTUnwrap(child.baseScore)), 71.184, accuracy: 0.000001)
        XCTAssertEqual(bundle.items.last?.baseScore, 70)
        XCTAssertNil(response.items.last?.baseScore)
    }

    func testMalformedRequiredCardStillSkipsWithoutLosingValidNeighbors() throws {
        let response = try decode(#"""
        {"items":[
          {"type":"futures","score":1,"base_score":10.125,"data":{"id":11,"name":"First"}},
          {"type":"futures","score":1,"base_score":10.125,"data":{"id":12}},
          {"type":"futures","score":1,"base_score":null,"data":{"id":13,"name":"Last"}}
        ]}
        """#)
        XCTAssertEqual(response.items.compactMap(\.futures).map(\.id), [11, 13])
        XCTAssertNil(response.items.last?.baseScore)
    }
}
