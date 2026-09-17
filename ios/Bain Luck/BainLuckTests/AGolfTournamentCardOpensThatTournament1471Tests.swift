import XCTest
@testable import Bain_Luck

/// #1471 / #6444 — **a golf tournament card opens that tournament.**
///
/// ## The chain Alex hit on 2026-09-16, and every link of it was real
///
/// > "Golf → duplicate card → Biltmore error, retry fails."
///
/// 1. The Discover tournament card's tap appended
///    `Route.sportCategory(key: "golf", name: "Golf")` — unconditionally, with
///    the card's own slug sitting unread in `data.slug`. So a card about one
///    tournament opened a list of all of them.
/// 2. That list showed **the same Biltmore card again** — the "duplicate card".
/// 3. Tapping it appended `Route.tournamentHub(slug:)`, which calls
///    `/api/tournaments/{slug}`: the registered **tennis** hub.
/// 4. And `Route.golfTournament` — the route the Golf page's own rows used —
///    discarded its slug with `_` and rendered `SportCategoryView(categoryKey: "golf")`,
///    so it too led back to a golf-shaped list.
///
/// **Measured on production, 2026-09-16 (all in the same minute):**
///
/// ```
/// GET /api/tournaments/biltmore-championship-asheville      404  "No registered tournament …"
/// GET /api/tournaments/the-open                             404  "No registered tournament …"
/// GET /api/tournaments/us-open                              200  (tennis draws)
/// GET /api/golf/tournaments/biltmore-championship-asheville 200  132 golfers, 6 markets
/// ```
///
/// The data was there the whole time. There was simply nowhere for a golf
/// tournament to go, and the retry button could not help because the second
/// call was the same 404.
final class AGolfTournamentCardOpensThatTournament1471Tests: XCTestCase {

    // MARK: - The card's destination

    private func card(slug: String?) -> FeedTournamentData {
        FeedTournamentData(
            key: "biltmore_championship_asheville",
            name: "Biltmore Championship Asheville",
            slug: slug,
            tour: "pga",
            tourLabel: "PGA Tour",
            isMajor: false,
            venue: "The Cliffs at Walnut Cove",
            location: "Arden, NC",
            startDate: "2026-09-17T00:00:00+00:00",
            endDate: "2026-09-20T00:00:00+00:00",
            scheduleStatus: "upcoming",
            commenceTime: "2026-09-12T16:01:00+00:00",
            resolutionDate: "2026-09-20T00:00:00+00:00",
            golfers: nil,
            sourceCount: nil,
            isMarquee: nil,
            marqueeWhathit: nil
        )
    }

    func testTheCardOpensItsOwnTournament() {
        XCTAssertEqual(
            NativeTournamentDiscoverCard.destination(for: card(slug: "biltmore-championship-asheville")),
            .golfTournament(slug: "biltmore-championship-asheville", name: "Biltmore Championship Asheville"),
            "the card about one tournament opens something other than that tournament — Alex's first tap"
        )
    }

    func testTheCardNeverOpensTheGenericGolfPageWhenItKnowsItsSlug() {
        // Stated separately from the equality above because this is the defect
        // itself, and an equality assertion that someone later loosens would
        // stop saying it.
        let destination = NativeTournamentDiscoverCard.destination(for: card(slug: "biltmore-championship-asheville"))
        XCTAssertNotEqual(
            destination, .sportCategory(key: "golf", name: "Golf"),
            "the card leads to the generic Golf page, which is where the duplicate card was"
        )
    }

    /// No slug is the only case with nowhere to go, and the honest answer is the
    /// category — not a tournament screen that could only say it failed.
    func testWithoutASlugItFallsBackToTheCategoryRatherThanAScreenThatCannotLoad() {
        for missing in [nil, ""] as [String?] {
            XCTAssertEqual(
                NativeTournamentDiscoverCard.destination(for: card(slug: missing)),
                .sportCategory(key: "golf", name: "Golf"),
                "slug \(String(describing: missing)) should fall back, not open an unloadable tournament"
            )
        }
    }

    // MARK: - A golf slug must never reach the tennis hub

    /// The route table carried the defect literally: `case .golfTournament(_, let name)`.
    ///
    /// Read as source because the alternative is rendering a `View` and asking
    /// it what it is, and the thing that was wrong is a `_` in a pattern — a
    /// character no value-level test can see.
    func testTheRouteTableNoLongerDiscardsTheGolfSlug() throws {
        let source = Self.codeText(of: "Bain Luck/Views/Route.swift")

        XCTAssertTrue(
            source.contains("GolfTournamentView(slug: slug"),
            "Route.golfTournament does not build a GolfTournamentView from its slug, so every golf "
            + "tournament row still leads back to a golf-shaped list — Alex's duplicate card."
        )
        XCTAssertFalse(
            source.contains("case .golfTournament(_,"),
            "Route.golfTournament is discarding its slug with `_` again. That pattern IS the defect: "
            + "the slug is carried to be used."
        )
    }

    /// The two surfaces that route a FEED tournament card.
    ///
    /// A feed `tournament` card is golf — pinned server-side by
    /// `backend/tests/test_feed_tournament_destination_1471.py` — so a
    /// `tournamentHub` route from either of these is a guaranteed 404.
    ///
    /// ⚠️ The needle is the bare symbol, NOT `Route.tournamentHub`. Swift's
    /// leading-dot syntax means `.tournamentHub(slug:)` is the same route by
    /// another spelling, and a scan for the qualified form would wave it
    /// through. This test found that on itself: its first cut anchored on
    /// `"Route."`, which `DiscoverTournamentCard` stopped containing the moment
    /// the routing moved into `destination(for:)` and started returning
    /// `.golfTournament` — so the anchor is now each file's own.
    func testNoFeedTournamentRowRoutesToTheTennisHub() {
        let surfaces = [
            ("Bain Luck/Views/SportCategoryView.swift", "Route."),
            ("Bain Luck/Components/DiscoverTournamentCard.swift", "destination(for"),
        ]
        for (file, anchor) in surfaces {
            let code = Self.codeLines(of: file)
                .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
                .joined(separator: "\n")

            // The strip has to leave code standing, or every assertion here
            // passes on an empty string.
            XCTAssertTrue(
                code.contains(anchor),
                "\(file): the comment strip left no code to search, or the anchor '\(anchor)' has moved"
            )
            XCTAssertFalse(
                code.contains("tournamentHub"),
                "\(file) sends a feed tournament to Route.tournamentHub, which calls the registered "
                + "TENNIS hub /api/tournaments/{slug}. Measured 2026-09-16: that endpoint answers 404 "
                + "for every golf slug, which is the 'Couldn't load Biltmore Championship Asheville' "
                + "on Alex's phone and the reason its Retry could not help."
            )
        }
    }

    /// The client calls the golf endpoint, and it is not the hub's.
    func testTheClientAsksTheGolfEndpoint() {
        let source = Self.codeText(of: "Bain Luck/Services/APIClient.swift")
        XCTAssertTrue(
            source.contains("\"/api/golf/tournaments/\\(slug)\""),
            "fetchGolfTournament does not call /api/golf/tournaments/{slug}"
        )
    }

    // MARK: - What the screen shows

    /// The real payload shape, trimmed. The field arrives at the TOP LEVEL and
    /// `tournament.golfers` is empty — a decoder that reached for the latter
    /// would render an empty field against a 200.
    private static let payload = """
    {
      "tournament": {
        "name": "Biltmore Championship Asheville",
        "slug": "biltmore-championship-asheville",
        "key": "biltmore_championship_asheville",
        "is_major": false,
        "is_womens": false,
        "start_date": "2026-09-17T00:00:00+00:00",
        "end_date": "2026-09-20T00:00:00+00:00",
        "venue": "The Cliffs at Walnut Cove",
        "location": "Arden, NC",
        "schedule_status": "upcoming"
      },
      "golfers": [
        {"name": "Jackson Koivun", "probability": 0.061, "rank": 1, "movement_24h": null},
        {"name": "Jacob Bridgeman", "probability": 0.042, "rank": 2, "movement_24h": 0.012},
        {"name": "Doug Ghim", "probability": 0.032, "rank": 3, "movement_24h": -0.001},
        {"name": "Ben James", "probability": 0.030, "rank": 4, "movement_24h": null}
      ],
      "biggest_movers": []
    }
    """

    private func presentation(_ json: String = payload) throws -> GolfTournamentPresentation {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(
            GolfTournamentDetailResponse.self, from: Data(json.utf8))
        return GolfTournamentPresentation(response: response)
    }

    func testTheFieldDecodesFromTheTopLevelAndNotFromTheTournament() throws {
        let shown = try presentation()
        XCTAssertEqual(shown.name, "Biltmore Championship Asheville")
        XCTAssertEqual(shown.venue, "The Cliffs at Walnut Cove")
        XCTAssertEqual(
            shown.field.count, 4,
            "the field is empty, so the decoder is reading `tournament.golfers` — which this endpoint "
            + "leaves empty — rather than the top-level `golfers` it actually sends"
        )
        XCTAssertEqual(shown.field.first?.name, "Jackson Koivun")
    }

    /// THE ORDER IS OURS, NOT THE WIRE'S, and the printed position agrees with it.
    ///
    /// A field sorted by anything but the number we print would show a 6.1%
    /// favourite below a 2.7% golfer with no error anywhere — the kind of wrong
    /// that reads as a data outage.
    func testTheFieldIsOrderedByTheNumberItPrints() throws {
        let scrambled = """
        {
          "tournament": {"name": "Biltmore Championship Asheville", "slug": "b"},
          "golfers": [
            {"name": "Doug Ghim", "probability": 0.032, "rank": 3},
            {"name": "Jackson Koivun", "probability": 0.061, "rank": 1},
            {"name": "Ben James", "probability": 0.030, "rank": 4},
            {"name": "Jacob Bridgeman", "probability": 0.042, "rank": 2}
          ],
          "biggest_movers": []
        }
        """
        let field = try presentation(scrambled).field

        XCTAssertEqual(
            field.map(\.name),
            ["Jackson Koivun", "Jacob Bridgeman", "Doug Ghim", "Ben James"],
            "a scrambled field is drawn in the order it arrived"
        )
        XCTAssertEqual(
            field.map(\.position), [1, 2, 3, 4],
            "the printed position disagrees with the order the rows are in — the one thing this sort exists to prevent"
        )
        for (a, b) in zip(field, field.dropFirst()) {
            XCTAssertGreaterThanOrEqual(a.probability, b.probability)
        }
    }

    /// Ties keep a stable order rather than swapping under the reader's thumb.
    func testEqualProbabilitiesBreakOnRankSoTheOrderIsStable() throws {
        let tied = """
        {
          "tournament": {"name": "T", "slug": "t"},
          "golfers": [
            {"name": "Second", "probability": 0.05, "rank": 9},
            {"name": "First", "probability": 0.05, "rank": 2}
          ],
          "biggest_movers": []
        }
        """
        XCTAssertEqual(try presentation(tied).field.map(\.name), ["First", "Second"])
    }

    /// One threshold for one quantity: the card and the page it opens must not
    /// disagree about whether a golfer moved. `TournamentHeroCard` draws its
    /// arrow at `abs(movement) >= 0.005`.
    func testTheMovementThresholdMatchesTheCardTheReaderTappedFrom() throws {
        let field = try presentation().field
        let byName = Dictionary(uniqueKeysWithValues: field.map { ($0.name, $0) })

        XCTAssertEqual(byName["Jacob Bridgeman"]?.hasMeaningfulMovement, true, "1.2pp is a move")
        XCTAssertEqual(byName["Doug Ghim"]?.hasMeaningfulMovement, false, "0.1pp is noise")
        XCTAssertEqual(byName["Jackson Koivun"]?.hasMeaningfulMovement, false, "a null move is not a move")
    }

    /// A tournament with no published field is a normal state days out. It must
    /// decode, not throw — an empty field is not a broken response.
    func testAFieldlessTournamentStillOpens() throws {
        let bare = """
        {"tournament": {"name": "Next Week's Open", "slug": "nwo"}, "golfers": [], "biggest_movers": []}
        """
        let shown = try presentation(bare)
        XCTAssertEqual(shown.name, "Next Week's Open")
        XCTAssertTrue(shown.field.isEmpty)
    }

    /// Per-item tolerance (#1471's own rule): one malformed golfer must not
    /// blank a page whose subject decoded perfectly well.
    func testAMalformedFieldDoesNotBlankATournamentThatDecoded() throws {
        let broken = """
        {
          "tournament": {"name": "Biltmore Championship Asheville", "slug": "b"},
          "golfers": "not an array",
          "biggest_movers": []
        }
        """
        let shown = try presentation(broken)
        XCTAssertEqual(shown.name, "Biltmore Championship Asheville")
        XCTAssertTrue(shown.field.isEmpty, "a malformed field degrades to no field, never to no page")
    }

    // MARK: - Source reading

    private static func codeText(of relativePath: String, file: StaticString = #filePath) -> String {
        let root = URL(fileURLWithPath: "\(file)")
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck
        let url = root.appendingPathComponent(relativePath)
        guard let text = try? String(contentsOf: url, encoding: .utf8) else {
            XCTFail("could not read \(relativePath) at \(url.path)")
            return ""
        }
        return text
    }

    private static func codeLines(of relativePath: String) -> [String] {
        codeText(of: relativePath).components(separatedBy: .newlines)
    }
}
