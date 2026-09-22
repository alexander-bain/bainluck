import XCTest
@testable import Bain_Luck

/// #7926 — A SPORTSBOOK ROW THAT STOPPED MOVING LOOKED EXACTLY LIKE ONE THAT HAD NOT.
///
/// Measured on the event page during the 2026-09-21 NFL game `14780545`
/// (NYG 6 – LAR 21), 145 minutes after a 00:15Z kickoff. `GET /api/events/14780545`
/// served twelve priced books, every one of them carrying `captured_at`:
///
/// | book | home % | age |
/// |---|---|---|
/// | fanduel / draftkings / courtside / betmgm | 96.9–98.4 | 2–3m |
/// | williamhill_us / fanatics / espnbet | 95.4–97.6 | 3–6m |
/// | rebet | 92.2 | 18m |
/// | **betus** | **71.2** | **140m** |
/// | **betanysports** | **72.7** | **142m** |
/// | **lowvig** | **71.5** | **146m** |
/// | **betonlineag** | **71.5** | **146m** |
///
/// The event opened 28% – 72%, so the four slow rows are the OPENING LINE, never
/// replaced — two of them captured before the ball was kicked. They drew in the
/// same weight, the same colour and the same order as prices from two minutes
/// earlier, and by Q4, under a header reading "Rams 100%", four of the seven
/// surviving rows still offered the reader the Giants at 27–29%.
///
/// 🔴 THE RULE WAS ALREADY ON THIS PLATFORM AND ALREADY NAMED THIS SURFACE.
/// `SourceAge.liveStaleAfter`'s own comment reads "Sportsbook rows and live
/// blocks, restamped every 2 minutes by `poll_live_prediction_markets`", and
/// `BookmakerOdds.capturedAt` has been decoded all along. `namedBookmakerRows`
/// called neither. This is the `captured_at` half of the same shape #4959 fixed
/// for prop grades: the server computes it, ships it, and the app drops it.
///
/// The web half has shipped for some time — `BookmakerTable.tsx` dims a stale row
/// to `opacity-60`, prints its age, and holds it out of the consensus average —
/// so this is a parity gap on a rule both clients already agree the value of.
///
/// ═══ WHAT THESE TESTS PIN, AND THE MUTATION EACH ONE KILLS ═══
///
/// The load-bearing one is the CADENCE. `PriceAgeMarkView` takes a
/// `SourceAge.Cadence`, and `.futures` is a legal value that compiles, renders and
/// breaks nothing visible on a fixture of two-hour-old prices — it would simply
/// hold the mark back for six hours on a list restamped every two minutes and
/// hide the exact rows the mark exists to expose. That is #5843's defect wearing
/// the other sign, and no assertion about `SourceAge` itself can see it, which is
/// why the decision lives in `NamedBookmakerRow.priceAgeMark()` where a test can
/// reach it rather than inside a `body`.
///
/// `now` is an argument throughout (gotcha #44): every stamp below is a fixed
/// offset from one fixed instant, so the suite reads the same at any hour.
final class AStaleSportsbookRowSaysHowOldItIs7926Tests: XCTestCase {

    /// One fixed instant. Not `Date()`, and nothing here branches on the clock.
    private static let now = Date(timeIntervalSince1970: 1_790_044_800) // 2026-09-22T02:40:00Z

    private static func iso(minutesBefore minutes: Int) -> String {
        let at = now.addingTimeInterval(-Double(minutes) * 60)
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: at)
    }

    /// `limit` is explicit because the real payload is BIGGER THAN THE CAP —
    /// `14780545` served twelve priced books against a default `limit` of 10, and
    /// the first draft of the specimen test below quietly lost `betonlineag` off
    /// the end and read as "the mark landed on the wrong rows". The cap is
    /// #4406's rule with its own tests; these tests are about freshness, so the
    /// specimen raises the cap out of the way rather than trimming the payload
    /// down to a size that could never have shown the defect.
    private static func rows(
        _ json: String, limit: Int = 10
    ) throws -> [EventDetailView.NamedBookmakerRow] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let books = try decoder.decode([BookmakerOdds].self, from: Data(json.utf8))
        return EventDetailView.namedBookmakerRows(books, limit: limit)
    }

    /// A book, as the payload actually spells one.
    private static func book(
        _ key: String, home: Double, capturedMinutesAgo: Int?
    ) -> String {
        let stamp = capturedMinutesAgo.map { "\"captured_at\": \"\(iso(minutesBefore: $0))\"," } ?? ""
        return """
        {"bookmaker": "\(key)", \(stamp)
         "home_probability": \(home), "away_probability": \(1 - home)}
        """
    }

    // MARK: - The stamp reaches the row

    /// Snake case in, camel case out. This is the decode the whole fix stands on:
    /// if `captured_at` ever stopped mapping to `capturedAt`, every row would be
    /// undatable and the marks would vanish SILENTLY — a screen that looks exactly
    /// like a screen where every book is fresh.
    func testTheRowCarriesTheServedStamp() throws {
        let rows = try Self.rows("[\(Self.book("betus", home: 0.71, capturedMinutesAgo: 140))]")

        XCTAssertEqual(rows.count, 1)
        XCTAssertEqual(rows[0].capturedAt, Self.iso(minutesBefore: 140))
    }

    // MARK: - Which rows draw

    func testAFreshBookDrawsNoAge() throws {
        let rows = try Self.rows("[\(Self.book("draftkings", home: 0.98, capturedMinutesAgo: 2))]")

        XCTAssertNil(
            rows[0].priceAgeMark(now: Self.now),
            "a price 2 minutes old is inside its cadence; an age there is noise")
    }

    func testATwoHourOldBookSaysSo() throws {
        let rows = try Self.rows("[\(Self.book("betus", home: 0.71, capturedMinutesAgo: 140))]")

        let mark = try XCTUnwrap(rows[0].priceAgeMark(now: Self.now))
        XCTAssertEqual(mark.age, "2h ago")
    }

    /// 🔴 THE CADENCE GUARD. 45 minutes is past the live bound (30m) and nowhere
    /// near the futures one (6h), so this is the single assertion that separates
    /// them. Flip `.live` to `.futures` in `priceAgeMark()` and only this fails.
    func testTheBoundIsTheLiveOneNotTheFuturesOne() throws {
        let rows = try Self.rows("[\(Self.book("lowvig", home: 0.71, capturedMinutesAgo: 45))]")

        XCTAssertNotNil(
            rows[0].priceAgeMark(now: Self.now),
            """
            45 minutes must draw. These rows are restamped every 2 minutes, so the \
            6-hour futures bound would hide a price that is 90 polls stale.
            """)
    }

    /// The strict `>` web uses, at the boundary itself.
    func testExactlyThirtyMinutesIsNotYetStale() throws {
        let at30 = try Self.rows("[\(Self.book("betus", home: 0.71, capturedMinutesAgo: 30))]")
        let at31 = try Self.rows("[\(Self.book("betus", home: 0.71, capturedMinutesAgo: 31))]")

        XCTAssertNil(at30[0].priceAgeMark(now: Self.now))
        XCTAssertNotNil(at31[0].priceAgeMark(now: Self.now))
    }

    /// ABSENT IS NOT OLD. A book the payload never stamped must not be accused of
    /// being stale — `SourceAge.isStale` answers false for an unreadable stamp and
    /// the row draws clean, which is the conservative direction.
    func testAnUnstampedBookIsNotAccused() throws {
        let rows = try Self.rows("[\(Self.book("betus", home: 0.71, capturedMinutesAgo: nil))]")

        XCTAssertNil(rows[0].capturedAt)
        XCTAssertNil(rows[0].priceAgeMark(now: Self.now))
    }

    // MARK: - The specimen

    /// The measured payload, rebuilt: eight live books and four that stopped at
    /// kickoff. Exactly the four slow ones draw, and they are the four by NAME —
    /// a count alone would pass if the marks landed on the wrong rows.
    func testOnTheMeasuredSpecimenExactlyTheFourStoppedBooksDraw() throws {
        let live: [(String, Double, Int)] = [
            ("fanduel", 0.969, 2), ("draftkings", 0.984, 2),
            ("betmgm", 0.976, 3), ("williamhill_us", 0.954, 3),
            ("fanatics", 0.976, 4), ("espnbet", 0.969, 6),
            ("rebet", 0.922, 18),
        ]
        let stopped: [(String, Double, Int)] = [
            ("betus", 0.712, 140), ("betanysports", 0.727, 142),
            ("lowvig", 0.715, 146), ("betonlineag", 0.715, 146),
        ]
        let json = (live + stopped)
            .map { Self.book($0.0, home: $0.1, capturedMinutesAgo: $0.2) }
            .joined(separator: ",")

        let rows = try Self.rows("[\(json)]", limit: 20)
        let marked = Set(rows.filter { $0.priceAgeMark(now: Self.now) != nil }.map(\.id))

        XCTAssertEqual(marked, Set(stopped.map(\.0)))
        XCTAssertEqual(
            rows.count, live.count + stopped.count,
            "a stale book keeps its row — the mark is the fix, not a filter")
    }

    /// The cap and the ordering are #4284's and #4406's, and carrying a stamp must
    /// not disturb either: the reader loses no row they could have read.
    func testCarryingTheStampChangesNeitherTheOrderNorTheCount() throws {
        let books = ["betus", "draftkings", "fanduel", "betmgm", "espnbet"]
        let dated = books.enumerated()
            .map { Self.book($0.element, home: 0.5, capturedMinutesAgo: $0.offset * 60) }
            .joined(separator: ",")
        let undated = books
            .map { Self.book($0, home: 0.5, capturedMinutesAgo: nil) }
            .joined(separator: ",")

        XCTAssertEqual(
            try Self.rows("[\(dated)]").map(\.id),
            try Self.rows("[\(undated)]").map(\.id))
    }
}
