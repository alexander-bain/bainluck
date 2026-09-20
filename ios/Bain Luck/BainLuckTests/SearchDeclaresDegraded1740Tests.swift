import XCTest
@testable import Bain_Luck

/// #1740 site 2 — the phone stops claiming absence it cannot prove.
///
/// Two halves, and the first is the one that bites: a `Decodable` that omits a
/// key does not fail, it silently yields a model with less in it. That is exactly
/// how `degraded` came to be served, correct, for months while `SearchView` drew
/// "No results found for X" over the top of it. So the decode half runs the real
/// `JSONDecoder` against raw JSON — a test that built `SearchResponse` in Swift
/// would pass just as happily on a tree where the property is never populated.
///
/// The decision half exercises `SearchAnswerState` directly, including each of
/// the six content flags on its own: a five-flag `||` chain is still green under
/// any test that sets the wrong one.
final class SearchDeclaresDegraded1740Tests: XCTestCase {

    private func decode(_ json: String) throws -> SearchResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SearchResponse.self, from: Data(json.utf8))
    }

    // MARK: - The key arrives at all

    func testDegradedStageListIsDecodedAndNotDropped() throws {
        let response = try decode(#"{"query":"lakers","results":[],"futures":[],"degraded":["futures"]}"#)
        XCTAssertEqual(response.degraded, ["futures"])
    }

    /// The route can shed more than one stage in a single answer.
    func testEveryShedStageIsKept() throws {
        let response = try decode(
            #"{"query":"lakers","results":[],"futures":[],"degraded":["teams","futures","event_count"]}"#
        )
        XCTAssertEqual(response.degraded, ["teams", "futures", "event_count"])
    }

    /// ADDITIVE on the wire: the key is absent on a complete answer and on any
    /// payload cached before the field existed. Absent must decode, not throw.
    func testAbsentKeyDecodesAsNil() throws {
        let response = try decode(#"{"query":"lakers","results":[],"futures":[]}"#)
        XCTAssertNil(response.degraded)
    }

    /// The verbatim production payload still decodes with the new property on the
    /// model — the regression an additive field is supposed to be incapable of,
    /// asserted rather than assumed.
    func testProductionFixtureStillDecodes() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(
            SearchResponse.self, from: Data(SearchProdFixture.usOpenJSON.utf8)
        )
        XCTAssertEqual(response.query, "US Open")
        // A complete answer declares nothing, which is the contract's whole point.
        XCTAssertNil(response.degraded)
    }

    // MARK: - Which of the three states

    private func state(
        events: Bool = false, futures: Bool = false, families: Bool = false,
        concepts: Bool = false, teams: Bool = false, hubs: Bool = false,
        degraded: [String]? = nil
    ) -> SearchAnswerState {
        SearchAnswerState.resolve(
            hasEvents: events, hasFutures: futures, hasFamilies: families,
            hasConcepts: concepts, hasTeams: teams, hasHubs: hubs,
            degraded: degraded
        )
    }

    /// The defect, stated as a test: nothing to draw AND the server said it could
    /// not finish ⇒ we may not say the entity is absent.
    func testShedStageWithNothingToDrawIsDegradedNotEmpty() {
        XCTAssertEqual(state(degraded: ["futures"]), .degraded)
    }

    /// An honest zero stays an honest zero. Without this the fix would just swap
    /// one wrong answer for another.
    func testCompleteAnswerWithNothingToDrawIsEmpty() {
        XCTAssertEqual(state(degraded: nil), .empty)
    }

    /// `degraded: []` is a complete answer. The route only ever emits the key
    /// non-empty, but the client decides from the list's CONTENT, not from the
    /// key's presence, so an empty list must not read as a failure.
    func testEmptyStageListIsCompleteNotDegraded() {
        XCTAssertEqual(state(degraded: []), .empty)
    }

    // MARK: - Content wins, on every one of the six sections

    /// Each flag alone must beat `degraded`. Run one at a time: a chain that
    /// forgot `hasHubs` is green under any test that also sets `hasEvents`, and
    /// the hub case is the one that shipped a self-contradicting screen before.
    func testAnySingleSectionWithContentBeatsDegraded() {
        let each: [(String, SearchAnswerState)] = [
            ("events", state(events: true, degraded: ["futures"])),
            ("futures", state(futures: true, degraded: ["futures"])),
            ("families", state(families: true, degraded: ["futures"])),
            ("concepts", state(concepts: true, degraded: ["futures"])),
            ("teams", state(teams: true, degraded: ["futures"])),
            ("hubs", state(hubs: true, degraded: ["futures"])),
        ]
        for (section, resolved) in each {
            XCTAssertEqual(
                resolved, .present,
                "a search showing \(section) is a partial answer, not a failed one"
            )
        }
    }

    /// The same six, with no shed at all — proves the flags are wired to
    /// `.present` rather than merely to "not `.degraded`".
    func testAnySingleSectionWithContentIsPresentOnACompleteAnswer() {
        XCTAssertEqual(state(events: true), .present)
        XCTAssertEqual(state(futures: true), .present)
        XCTAssertEqual(state(families: true), .present)
        XCTAssertEqual(state(concepts: true), .present)
        XCTAssertEqual(state(teams: true), .present)
        XCTAssertEqual(state(hubs: true), .present)
    }

    // MARK: - End to end, from the wire

    /// The whole path a shed answer takes: JSON in, state out. This is the one
    /// that would have caught the original defect on its own.
    func testShedPayloadResolvesToDegradedFromRawJSON() throws {
        let response = try decode(
            #"{"query":"alcaraz","results":[],"futures":[],"teams":[],"degraded":["futures","teams"]}"#
        )
        let resolved = SearchAnswerState.resolve(
            hasEvents: !response.results.isEmpty,
            hasFutures: !response.futures.isEmpty,
            hasFamilies: !(response.futuresFamilies ?? []).isEmpty,
            hasConcepts: !(response.eventConcepts ?? []).isEmpty,
            hasTeams: !(response.teams ?? []).isEmpty,
            hasHubs: false,
            degraded: response.degraded
        )
        XCTAssertEqual(resolved, .degraded)
    }
}
