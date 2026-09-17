import XCTest
@testable import Bain_Luck

/// #2564, the native half — **the CPI card row shows six different releases.**
///
/// `CPIRelease.id` was the month label:
///
/// ```swift
/// var id: String { mo }
/// ```
///
/// `mo` is a short period hint the backend derives from the market's name, and
/// the venues' names carry no year, so it collides constantly. Read live at
/// 2026-09-17 09:xx Z, the six blocks `GET /api/economics` serves are:
///
/// | `mo`       | `q`                                          | `market_id` |
/// |------------|----------------------------------------------|-------------|
/// | `Aug`      | South Africa inflation rate MoM for August    | 59699946    |
/// | `Sep`      | Argentina Monthly Inflation - September       | 60760395    |
/// | `Sep`      | CPI in September                              | 364212      |
/// | `Sep`      | CPI core in September                         | 55686485    |
/// | `Sep 2026` | CPI year-over-year in Sep 2026?               | 109969      |
/// | `Sep 2026` | …                                             | …           |
///
/// Three ids of `Sep` and two of `Sep 2026` in one `ForEach`. SwiftUI keys its
/// children on `Identifiable.id`, so duplicates collapse: Alex's iPad render
/// photographed the same month three times over with byte-identical numbers and
/// an identical bar chart. The card row was never showing six releases.
///
/// So the key is the market, which is what the sibling `EconomicsMarket` on this
/// same page has always used (`"\(marketId ?? 0)-\(q)"`). `mo` cannot be repaired
/// upstream — ux/1311 measured that after PR #6738 made most labels unique, three
/// of six blocks still read `Sep`, because the *venue* names them that way.
///
/// ## Two riders, same card
///
/// **The badge.** `upcoming` is true on every block on purpose — the section
/// gates and counts on it (`releases.filter { $0.upcoming == true }`), so
/// narrowing it would cut the row from six cards to one. Badging `NEXT` off it
/// was clause 1 of this issue: six "next" releases. The payload states the
/// superlative separately as `is_next`, true on exactly one.
///
/// **The venue mark.** The card footer printed a hardcoded `"Kalshi"`, and the
/// section subtitle said "from Kalshi bracket markets". `market_id` 60760395 is
/// Polymarket (`futures_markets.source`, read the same morning). A CPI block
/// carries no `src`, so the mark is gone rather than guessed — an honest empty
/// space over a wrong attribution (notice 34). It comes back when the payload
/// can name the venue.
final class SixCPIBlocksAreSixDistinctReleases2564Tests: XCTestCase {

    // MARK: - The identity

    /// The exact collision from the render: three live blocks sharing one `mo`.
    func testBlocksSharingAMonthLabelDecodeToDistinctIds() throws {
        let releases = try decodeReleases(Self.liveShapedPayload)

        XCTAssertEqual(releases.count, 4, "the fixture lost a block before the assertion")

        let months = Set(releases.map(\.mo))
        XCTAssertLessThan(
            months.count, releases.count,
            """
            this fixture is the control: it must contain a repeated `mo`, or the \
            id assertion below passes without ever meeting the defect. Months \
            decoded: \(releases.map(\.mo))
            """)

        let ids = Set(releases.map(\.id))
        XCTAssertEqual(
            ids.count, releases.count,
            """
            \(releases.count) blocks collapsed to \(ids.count) ids — a `ForEach` \
            over these draws the same card more than once, which is what #2564 \
            photographed. Ids: \(releases.map(\.id).sorted())
            """)
    }

    /// Two blocks can share a question too (`CPI in September` on two venues);
    /// the market id is what separates them, so it has to be in the key.
    func testTheMarketIdIsPartOfTheKey() throws {
        let json = """
        [
          {"mo": "Sep", "q": "CPI in September", "market_id": 364212, "upcoming": true},
          {"mo": "Sep", "q": "CPI in September", "market_id": 999111, "upcoming": true}
        ]
        """
        let releases = try decodeReleases(json)

        XCTAssertNotEqual(
            releases[0].id, releases[1].id,
            "same label, same question, different markets — the id must still separate them")
    }

    /// A payload that predates `q` (a cached response, a rollback) must still
    /// render the section rather than fail the whole `EconomicsInflationTheme`.
    func testAPayloadWithoutTheQuestionStillDecodes() throws {
        let json = """
        [{"mo": "Sep", "market_id": 364212, "upcoming": true, "peakIs": 1}]
        """
        let releases = try decodeReleases(json)

        XCTAssertEqual(releases.count, 1)
        XCTAssertNil(releases[0].q)
        XCTAssertEqual(
            releases[0].id, "364212-Sep",
            "with no question the key falls back to the label, which the market id still separates")
    }

    // MARK: - The badge

    func testIsNextDecodesAndIsTrueOnExactlyOneBlock() throws {
        let releases = try decodeReleases(Self.liveShapedPayload)

        XCTAssertTrue(
            releases.allSatisfy { $0.upcoming == true },
            "`upcoming` gates and counts the whole section — every block carries it")

        XCTAssertEqual(
            releases.filter { $0.isNext == true }.count, 1,
            """
            `is_next` is the superlative and exactly one block may claim it. \
            Decoded: \(releases.map { "\($0.mo)=\(String(describing: $0.isNext))" })
            """)
    }

    /// `cpiCard` is `private` on a `View`, so the badge's condition is pinned by
    /// scanning its body rather than by calling it.
    func testTheNextBadgeIsGatedOnIsNextNotOnUpcoming() throws {
        let body = try cpiCardBody()

        XCTAssertTrue(
            body.contains("release.isNext == true"),
            "the NEXT badge must read the payload's superlative")
        XCTAssertFalse(
            body.contains("release.upcoming == true"),
            """
            the badge is back on `upcoming`, which is true on all six blocks — \
            every card will claim to be next, which is clause 1 of #2564
            """)
    }

    // MARK: - The question is on the card

    func testTheCardRendersTheQuestion() throws {
        let body = try cpiCardBody()

        XCTAssertTrue(
            body.contains("release.q ?? release.mo"),
            """
            the card must print the market's own question — the period label \
            alone names no release when three blocks share it
            """)
    }

    // MARK: - No guessed venue

    /// Scoped to the two CPI functions on purpose. The FOMC card one section up
    /// also prints a hardcoded `"Kalshi"`, and all five of its live meeting
    /// markets ARE Kalshi (`futures_markets.source`, read 2026-09-17) — so a
    /// whole-file scan would be red on behaviour this change is not about, and
    /// would drag another card into #2564's diff.
    func testNoHardcodedVenueOnTheCPICardOrInItsSubtitle() throws {
        XCTAssertFalse(
            try cpiCardBody().contains("\"Kalshi\""),
            """
            a venue name is hardcoded on the CPI card again. One of the six live \
            blocks is Polymarket (market 60760395), and the payload carries no \
            `src` for a block, so any literal venue here is a guess.
            """)

        XCTAssertFalse(
            try cpiSectionBody().contains("Modal outcome per month"),
            """
            the old subtitle is back. It was wrong twice: the blocks are per \
            market, not per month, and they are not all Kalshi.
            """)
    }

    // MARK: - Rig

    private func decodeReleases(_ json: String) throws -> [CPIRelease] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase   // as APIClient.fetch does
        return try decoder.decode([CPIRelease].self, from: Data(json.utf8))
    }

    /// Shaped after the live payload: a repeated `mo`, one `is_next`.
    private static let liveShapedPayload = """
    [
      {"mo": "Aug", "q": "South Africa inflation rate MoM for August",
       "market_id": 59699946, "upcoming": true, "is_next": true, "peakIs": 1},
      {"mo": "Sep", "q": "Argentina Monthly Inflation - September",
       "market_id": 60760395, "upcoming": true, "is_next": false, "peakIs": 0},
      {"mo": "Sep", "q": "CPI in September",
       "market_id": 364212, "upcoming": true, "is_next": false, "peakIs": 5},
      {"mo": "Sep", "q": "CPI core in September",
       "market_id": 55686485, "upcoming": true, "is_next": false, "peakIs": 1}
    ]
    """

    private static var projectRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
    }

    private static var economicsView: URL {
        projectRoot.appendingPathComponent("Bain Luck/Views/EconomicsView.swift")
    }

    /// Just `cpiCard`'s body.
    ///
    /// Scoped in both directions: `release.upcoming == true` is used legitimately
    /// in `cpiSection` one function above (it gates the section), so a whole-file
    /// scan for it would be red on correct code; and the badge lives here, so a
    /// scan that missed this span would be green on the defect.
    private func cpiCardBody() throws -> String {
        try slice(from: "private func cpiCard", to: "private func cpiHistogram")
    }

    /// Just `cpiSection`'s body — the subtitle's home.
    private func cpiSectionBody() throws -> String {
        try slice(from: "private func cpiSection", to: "private func cpiCard")
    }

    /// Both delimiters are asserted rather than defaulted — if either moves,
    /// this fails loudly instead of silently grading an empty string.
    private func slice(from opening: String, to closing: String) throws -> String {
        let source = try code(at: Self.economicsView)

        guard let start = source.range(of: opening) else {
            XCTFail("`\(opening)` not found — the scan has no subject")
            return ""
        }
        guard let end = source.range(of: closing, range: start.upperBound..<source.endIndex) else {
            XCTFail("`\(closing)` not found after the subject — the slice is unbounded")
            return ""
        }

        let body = String(source[start.upperBound..<end.lowerBound])
        XCTAssertGreaterThan(
            body.count, 500,
            "the sliced body is too short to be this function — the anchors have drifted")
        return body
    }

    /// Source with its comment lines removed.
    ///
    /// Load-bearing: the subject's comments quote the removed defect verbatim —
    /// `"Kalshi"`, "Modal outcome per month", `release.upcoming == true` — so the
    /// next reader knows what used to be there. A scan over raw source would read
    /// those comments and report the defect present on the correct code.
    private func code(at url: URL) throws -> String {
        let source = try String(contentsOf: url, encoding: .utf8)
        let stripped = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertTrue(
            stripped.contains("private func cpiCard"),
            "the comment strip left nothing to scan in \(url.lastPathComponent)")
        return stripped
    }
}
