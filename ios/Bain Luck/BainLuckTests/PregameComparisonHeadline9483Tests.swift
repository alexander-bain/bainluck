import XCTest
import SwiftUI
@testable import Bain_Luck

/// #9483 — the before-the-game comparison headline
/// (`PregameComparisonHeadline9483`): which value lands in which side's cell,
/// what stands where a value is absent or no longer current, which rows it
/// draws at all, the host's words it carries, and when the projected final is
/// a control.
///
/// FIXTURES, AND WHAT EACH IS:
///
///   - BEARS/EAGLES is the approved design reference CONTROL
///     (`football-comparison-headline-20261023/pregame-375.png`, event
///     14780549): chance 0.365 / 0.635, forecast 19.5 / 23. It is not a new
///     app capture and not production evidence. Its pair is built by the
///     production priced arm (`NFLPairedHeadline9483.priced`, as
///     `RecognizableNFLPage9483Tests` builds it) from `formatProbability` over
///     `renderedDuelPercents`, and its projection goes through the host's own
///     `projectionText` → `projectionFigure9483` → `projectedPair11285` chain
///     (as `NFLReaderBuild65Feedback11285Tests` reads it). Shared native
///     formatting is the authority, so the printed values are asserted against
///     that chain, never the reference's 36.5% or 19.5.
///   - Hand-built pairs (a decided side, a score centre, a `Side.pregame`
///     string), the NBA row, a 0 projection and other labels/contexts are
///     CONSTRUCTED and say so where they are built.
///
/// No wire payload was fabricated and nothing here reads live data. These are
/// model tests: not pixel, layout, interaction or VoiceOver evidence.
@MainActor
final class PregameComparisonHeadline9483Tests: XCTestCase {

    private typealias H = PregameComparisonHeadline9483<EmptyView>

    private static let nfl = "americanfootball_nfl"
    private static let nba = "basketball_nba"
    private static let label = "Projected final"
    private static let context = "ESPN · Sep 28, 5:15 PM"

    // MARK: - Builders

    /// The reference control's pair, through the production priced arm before
    /// kickoff (no score, so the centre is `.versus`).
    private var bearsPaired: NFLPairedHeadline9483 {
        let percents = renderedDuelPercents(away: 0.365, home: 0.635)
        return NFLPairedHeadline9483.priced(
            awayText: formatProbability(0.365, renderedPercent: percents[0]),
            homeText: formatProbability(0.635, renderedPercent: percents[1]),
            live: false, score: nil, pregame: nil)
    }

    /// The reference control's 19.5 / 23 projection, as the host prints it
    /// before kickoff: `projectionText` rounds, `projectionFigure9483` drops
    /// "Proj. ", `projectedPair11285` splits.
    private func bearsProjection() throws -> (away: Int, home: Int) {
        let now = Date(timeIntervalSince1970: 1_790_000_000)
        let text = try XCTUnwrap(EventDetailView.projectionText(
            sport: Self.nfl, status: "scheduled", commenceTime: now.addingTimeInterval(6 * 3_600),
            projectedHome: 23, projectedAway: 19.5, hasScore: false, now: now),
            "fixture: the host's gate must admit the control's pregame projection")
        return try XCTUnwrap(EventDetailView.projectedPair11285(EventDetailView.projectionFigure9483(text)))
    }

    private func resolve(
        sport: String? = PregameComparisonHeadline9483Tests.nfl, status: String? = "scheduled",
        hasStarted: Bool = false, isOpeningLine: Bool = false,
        paired: NFLPairedHeadline9483?, phase: EventHeadlinePhase9483? = .current,
        projected: (away: Int, home: Int)?,
        label: String = PregameComparisonHeadline9483Tests.label,
        away: String = "Chicago Bears", home: String = "Philadelphia Eagles",
        context: String? = PregameComparisonHeadline9483Tests.context, canInspect: Bool = false
    ) -> H.Resolved? {
        H.resolve(sportKey: sport, status: status, hasStarted: hasStarted, isOpeningLine: isOpeningLine,
                  paired: paired, chancePhase: phase, projectedPair: projected,
                  forecastLabel: label, awayName: away, homeName: home,
                  pregameContext: context, canInspect: canInspect)
    }

    private func bears(phase: EventHeadlinePhase9483? = .current, canInspect: Bool = false) throws -> H.Resolved {
        try XCTUnwrap(resolve(paired: bearsPaired, phase: phase, projected: try bearsProjection(),
                              canInspect: canInspect))
    }

    // MARK: - Binding

    func testEachValueLandsOnItsOwnSideAndColumn() throws {
        let r = try bears()
        XCTAssertEqual(r.headers, ["Win chance", "Projected final"])
        XCTAssertEqual(r.away.name, "Chicago Bears")
        XCTAssertEqual(r.home.name, "Philadelphia Eagles")
        XCTAssertFalse(r.away.isHome)
        XCTAssertTrue(r.home.isHome)
        XCTAssertEqual(r.away.chance.text, bearsPaired.away.figure)
        XCTAssertEqual(r.home.chance.text, bearsPaired.home.figure)
        let projection = try bearsProjection()
        XCTAssertEqual(r.away.forecast.text, "\(projection.away)")
        XCTAssertEqual(r.home.forecast.text, "\(projection.home)")
        XCTAssertNotEqual(r.away.chance.text, r.home.chance.text)
        XCTAssertTrue(r.rows.allSatisfy { $0.chance.isValue && $0.forecast.isValue })
    }

    /// The control's 36.5% and 19.5 are the reference's; the app prints what
    /// its shared formatter and the host chain print. Recorded, not "fixed".
    func testTheReferenceControlPrintsTheSharedNativeValuesNotTheImagesDecimals() throws {
        let r = try bears()
        let shown = r.rows.flatMap { $0.cells.map(\.text) }
        XCTAssertFalse(shown.contains("36.5%"))
        XCTAssertFalse(shown.contains("19.5"))
        XCTAssertEqual(r.away.forecast.text, "20", "the host rounds the half point before this view sees it")
        XCTAssertEqual(r.home.forecast.text, "23")
    }

    /// CONSTRUCTED: a pair whose sides carry pregame words. They are never
    /// parsed into a number or shown.
    func testTheChanceIsNeverReadFromTheSidesPregameWords() throws {
        let paired = NFLPairedHeadline9483(
            away: .init(figure: "37%", pregame: "Pre-match 41%", won: nil),
            home: .init(figure: "63%", pregame: "Pre-match 59%", won: nil),
            center: .versus)
        let r = try XCTUnwrap(resolve(paired: paired, projected: (away: 20, home: 23)))
        XCTAssertEqual(r.away.chance.text, "37%")
        XCTAssertEqual(r.home.chance.text, "63%")
        let everything = r.rows.flatMap { [$0.spokenSummary] + $0.cells.map(\.text) }
        XCTAssertFalse(everything.contains { $0.contains("41") || $0.contains("59") || $0.contains("Pre-match") })
    }

    // MARK: - Currentness

    func testOnlyACurrentPhasePrintsTheChance() throws {
        let current = try bears(phase: .current)
        XCTAssertTrue(current.away.chance.isValue)

        let recorded = try bears(phase: .lastRecorded)
        for row in recorded.rows {
            XCTAssertEqual(row.chance.text, "No recent probability")
            XCTAssertFalse(row.chance.isValue)
            XCTAssertFalse(row.chance.text.contains("%"), "no stale number beside the words")
        }

        let missing = try bears(phase: nil)
        for row in missing.rows {
            XCTAssertEqual(row.chance.text, "Unavailable")
            XCTAssertFalse(row.chance.isValue)
        }
    }

    /// A decided side, a score centre or the final arm is not a pregame price,
    /// so no verdict or terminal number ever reaches the chance column.
    func testADecidedOrScoredPairNeverPrintsAChance() throws {
        let projection = try bearsProjection()
        // The production final arm.
        XCTAssertNil(resolve(paired: NFLPairedHeadline9483.final(homeWon: true, score: nil, pregame: nil),
                             projected: projection))
        // CONSTRUCTED: one side decided, still on a versus centre.
        let decided = NFLPairedHeadline9483(
            away: .init(figure: "37%", pregame: nil, won: nil),
            home: .init(figure: "Won", pregame: nil, won: true), center: .versus)
        XCTAssertNil(resolve(paired: decided, projected: projection))
        // The production priced arm with a score (a live row) is not .versus.
        let scored = NFLPairedHeadline9483.priced(awayText: "14%", homeText: "86%", live: false,
                                                  score: (away: 0, home: 0), pregame: nil)
        XCTAssertNil(resolve(paired: scored, projected: projection))
    }

    // MARK: - Absence

    func testTheChanceAndTheForecastGoMissingIndependently() throws {
        let noForecast = try XCTUnwrap(resolve(paired: bearsPaired, projected: nil))
        for row in noForecast.rows {
            XCTAssertTrue(row.chance.isValue, "a missing projection keeps the chance")
            XCTAssertEqual(row.forecast.text, "Unavailable")
            XCTAssertFalse(row.forecast.isValue)
        }

        let noChance = try XCTUnwrap(resolve(paired: bearsPaired, phase: nil, projected: try bearsProjection()))
        for row in noChance.rows {
            XCTAssertEqual(row.chance.text, "Unavailable")
            XCTAssertTrue(row.forecast.isValue, "a missing phase keeps the projection")
        }

        let neither = try XCTUnwrap(resolve(paired: bearsPaired, phase: .lastRecorded, projected: nil))
        XCTAssertEqual(neither.away.cells.map(\.text), ["No recent probability", "Unavailable"])
    }

    /// CONSTRUCTED: a supplied 0 is a value, not an absence.
    func testAGenuineZeroForecastPrintsZero() throws {
        let r = try XCTUnwrap(resolve(paired: bearsPaired, projected: (away: 0, home: 3)))
        XCTAssertEqual(r.away.forecast.text, "0")
        XCTAssertTrue(r.away.forecast.isValue)
        XCTAssertEqual(r.away.forecast.spoken, "Projected final: 0")
        XCTAssertEqual(r.home.forecast.text, "3")
    }

    // MARK: - Applicability and host fallbacks

    func testOnlyAnUpcomingNFLOrNBARowApplies() {
        for status in [nil, "scheduled"] as [String?] {
            XCTAssertTrue(H.applies(sportKey: Self.nfl, status: status, hasStarted: false, isOpeningLine: false),
                          String(describing: status))
        }
        for status in ["live", "completed", "closed", "suspended", "postponed", "cancelled", "void", "unknown", ""] {
            XCTAssertFalse(H.applies(sportKey: Self.nfl, status: status, hasStarted: false, isOpeningLine: false),
                           status)
        }
        XCTAssertFalse(H.applies(sportKey: Self.nfl, status: "scheduled", hasStarted: true, isOpeningLine: false),
                       "the host's clock says it started (an undated game has)")
        XCTAssertFalse(H.applies(sportKey: Self.nfl, status: "scheduled", hasStarted: false, isOpeningLine: true),
                       "the opening line keeps its own hero")
        XCTAssertTrue(H.applies(sportKey: Self.nba, status: "scheduled", hasStarted: false, isOpeningLine: false))
        let otherSports: [String?] = ["baseball_mlb", "icehockey_nhl", "soccer_epl", "tennis_atp_us_open",
                                      "americanfootball_ncaaf", nil]
        for sport in otherSports {
            XCTAssertFalse(H.applies(sportKey: sport, status: "scheduled", hasStarted: false, isOpeningLine: false),
                           String(describing: sport))
        }
    }

    /// Each refusal returns nil, which is the host's cue to keep its existing
    /// renderer. A present pair with a missing phase still draws, unavailable.
    func testEveryRefusalLeavesTheHostsRenderer() throws {
        let projection = try bearsProjection()
        XCTAssertNil(resolve(paired: nil, projected: projection), "no pair: no reconstruction from a baseline")
        XCTAssertNil(resolve(status: "live", paired: bearsPaired, projected: projection))
        XCTAssertNil(resolve(hasStarted: true, paired: bearsPaired, projected: projection))
        XCTAssertNil(resolve(isOpeningLine: true, paired: bearsPaired, projected: projection))
        XCTAssertNil(resolve(sport: "baseball_mlb", paired: bearsPaired, projected: projection))
        XCTAssertNotNil(resolve(paired: bearsPaired, phase: nil, projected: projection))
        // CONSTRUCTED NBA row: same arm.
        XCTAssertNotNil(resolve(sport: Self.nba, paired: bearsPaired, projected: (away: 112, home: 108),
                                away: "Boston Celtics", home: "New York Knicks"))
    }

    // MARK: - The host's words

    func testTheContextAndTheForecastLabelAreCarriedAsGiven() throws {
        let r = try bears()
        XCTAssertEqual(r.context, Self.context)
        XCTAssertEqual(r.away.forecast.label, "Projected final")

        // CONSTRUCTED: other words pass through untouched.
        let tbd = "Sun, Sep 28 · TBD"
        let other = try XCTUnwrap(resolve(paired: bearsPaired, projected: (away: 20, home: 23),
                                          label: "Projected score", context: tbd))
        XCTAssertEqual(other.context, tbd)
        XCTAssertEqual(other.headers, ["Win chance", "Projected score"])
        XCTAssertEqual(other.home.forecast.spoken, "Projected score: 23")

        XCTAssertNil(try XCTUnwrap(resolve(paired: bearsPaired, projected: nil, context: nil)).context)
        XCTAssertNil(try XCTUnwrap(resolve(paired: bearsPaired, projected: nil, context: "")).context)
    }

    // MARK: - Speech

    func testTheContextThenEachTeamIsSpokenInReadingOrder() throws {
        let r = try bears()
        let away = r.away.chance.text, home = r.home.chance.text
        XCTAssertEqual(r.spokenOrder, [
            Self.context,
            "Chicago Bears. Win chance: \(away). Projected final: 20",
            "Philadelphia Eagles. Win chance: \(home). Projected final: 23",
        ])
        let recorded = try bears(phase: .lastRecorded)
        XCTAssertEqual(recorded.away.spokenSummary,
                       "Chicago Bears. Win chance: No recent probability. Projected final: 20")

        // No verdict, grading, venue or match-up words in anything shown or spoken.
        let chrome = r.headers + r.spokenOrder + r.rows.flatMap { $0.cells.map(\.text) }
        for word in ["vs", "won", "lost", "final score", "price", "odds", "market", "book", "?"] {
            XCTAssertFalse(chrome.contains { $0.lowercased().contains(word) }, word)
        }
    }

    // MARK: - Inspection

    func testTheForecastIsAControlOnlyWithAProjectionAndTheHostsCallback() throws {
        XCTAssertFalse(try bears(canInspect: false).rows.contains { $0.inspects }, "no callback: no fake arrow")
        XCTAssertNil(try bears(canInspect: false).away.actionLabel)
        let inspecting = try bears(canInspect: true)
        XCTAssertTrue(inspecting.rows.allSatisfy { $0.inspects })
        let none = try XCTUnwrap(resolve(paired: bearsPaired, projected: nil, canInspect: true))
        XCTAssertFalse(none.rows.contains { $0.inspects }, "nothing to inspect without a projection")
        // A missing chance does not remove the control.
        let noChance = try XCTUnwrap(resolve(paired: bearsPaired, phase: nil,
                                             projected: try bearsProjection(), canInspect: true))
        XCTAssertTrue(noChance.away.inspects)
    }

    func testInspectionCallsBackForItsExactSideAndIsNamedForIt() throws {
        var sides: [Bool] = []
        let inspect: (Bool) -> Void = { sides.append($0) }
        let r = try bears(canInspect: true)
        H.perform(r.home, inspect: inspect)
        H.perform(r.away, inspect: inspect)
        XCTAssertEqual(sides, [true, false])
        XCTAssertEqual(r.away.actionLabel, "Projected final, Chicago Bears")
        XCTAssertEqual(r.home.actionLabel, "Projected final, Philadelphia Eagles")

        H.perform(try bears(canInspect: false).away, inspect: inspect)
        H.perform(r.away, inspect: nil)
        XCTAssertEqual(sides, [true, false], "a plain row and a missing callback call nothing")
    }

    // MARK: - Layout decision

    func testAccessibilitySizesStackAndOthersTryTheColumns() {
        for size in DynamicTypeSize.allCases {
            XCTAssertEqual(H.arrangement(typeSize: size),
                           size.isAccessibilitySize ? .stackedValues : .columnsWhenTheyFit, "\(size)")
        }
    }
}
