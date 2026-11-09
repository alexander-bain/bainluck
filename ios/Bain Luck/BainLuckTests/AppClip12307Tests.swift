import XCTest

@testable import Bain_Luck

/// #12307 — the App Clip opens only bainluck.com's game and market pages, reads
/// them exactly as the saved widget does, and says plainly when it can't.
///
/// The clip is its own app (`BainLuckClip/`); the decisions it makes live in
/// `AppClip12307/ClipInvocation12307.swift`, compiled into both, and are held
/// here. The system handing a tapped link to the clip is not something a unit
/// test, or the simulator's command-line launch, can show; the issue says so.
@MainActor
final class AppClip12307Tests: XCTestCase {
    private let t0 = Date(timeIntervalSince1970: 1_794_000_000)

    private func iso(_ date: Date) -> String { ISO8601DateFormatter().string(from: date) }

    private static func repoFile(_ relative: String) -> URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(relative)
    }

    private func eventJSON(id: Int = 14780576, status: String = "live", observed: Date? = nil,
                           homeScore: Int? = 2, awayScore: Int? = 1, extra: String = "") -> Data {
        let obs = "\"\(iso(observed ?? t0))\""
        let scores = "\"home_score\": \(homeScore.map(String.init) ?? "null"), \"away_score\": \(awayScore.map(String.init) ?? "null"),"
        return Data("""
        {"id": \(id), "sport": "americanfootball_nfl", "home_team": "Minnesota Vikings", "away_team": "Buffalo Bills",
         "status": "\(status)", "commence_time": "\(iso(t0.addingTimeInterval(-3600)))", \(scores)
         "current_odds": {"home_probability": 0.38, "away_probability": 0.62},
         "hero_probability_source": "blend", "hero_probability_observed_at": \(obs)\(extra)}
        """.utf8)
    }

    private let marketJSON = Data("""
    {"id": 52755659, "name": "2026-27 Stanley Cup Final Winner", "status": "open",
     "outcomes": [{"id": 1, "name": "Carolina Hurricanes", "probability": 0.12, "last_updated": "2026-11-09T17:43:00Z"},
                  {"id": 2, "name": "Colorado Avalanche", "probability": 0.11, "last_updated": "2026-11-09T17:43:00Z"}]}
    """.utf8)

    // MARK: - Which links open a page

    func testBothHostsOpenAGameOrAMarket() {
        XCTAssertEqual(ClipInvocation12307.subject(from: URL(string: "https://www.bainluck.com/events/14780576")),
                       SavedWidgetSubject10875(kind: .game, id: 14780576))
        XCTAssertEqual(ClipInvocation12307.subject(from: URL(string: "https://bainluck.com/futures/52755659")),
                       SavedWidgetSubject10875(kind: .market, id: 52755659))
        XCTAssertEqual(ClipInvocation12307.subject(from: URL(string: "https://WWW.BainLuck.com/events/7?ref=qr")),
                       SavedWidgetSubject10875(kind: .game, id: 7), "a host's case and a query don't change the page")
    }

    func testAnythingElseOpensNoPage() {
        for raw in [
            "https://www.bainluck.com/about", "https://www.bainluck.com/events", "https://www.bainluck.com/events/abc",
            "https://www.bainluck.com/events/0", "https://www.bainluck.com/events/-3",
            "https://www.bainluck.com/events/7/props", "http://www.bainluck.com/events/7",
            "https://evil.example/events/7", "https://bainluck.com.evil.example/events/7",
            "bainluck://events/7", "https://www.bainluck.com/tournaments/us-open",
        ] {
            XCTAssertNil(ClipInvocation12307.subject(from: URL(string: raw)), raw)
        }
        XCTAssertNil(ClipInvocation12307.subject(from: nil))
    }

    // MARK: - The read is the saved widget's

    func testTheDetailURLsAreTheSavedWidgetsOwn() throws {
        // `SavedItemWidgetFetch10875` is in the widget target, so its lines are read from source.
        let widget = try String(contentsOf: Self.repoFile("BainLuckWidget/SavedItemWidgetIntent10875.swift"), encoding: .utf8)
        XCTAssertTrue(widget.contains(#"static let baseURL = "\#(ClipInvocation12307.apiBase)""#))
        XCTAssertTrue(widget.contains(#"URL(string: "\(baseURL)/api/events/\(subject.id)")"#))
        XCTAssertTrue(widget.contains(#"URL(string: "\(baseURL)/api/futures/\(subject.id)?representation=verified_title")"#))
        XCTAssertTrue(widget.contains("http.statusCode == 404 || http.statusCode == 410"), "the widget's gone rule moved")

        XCTAssertEqual(ClipInvocation12307.detailURL(for: .init(kind: .game, id: 5))?.absoluteString,
                       "https://api.bainluck.com/api/events/5")
        XCTAssertEqual(ClipInvocation12307.detailURL(for: .init(kind: .market, id: 9))?.absoluteString,
                       "https://api.bainluck.com/api/futures/9?representation=verified_title")
    }

    // MARK: - Loading

    func testAGameIsShownAsServedFromItsOwnURL() async {
        var asked: [URL] = []
        let subject = SavedWidgetSubject10875(kind: .game, id: 14780576)
        let load = await ClipLoader12307.load(subject) { url in
            asked.append(url)
            return (self.eventJSON(), 200)
        }
        XCTAssertEqual(asked, [ClipInvocation12307.detailURL(for: subject)!])
        guard case .detail(.game(let event)) = load else { return XCTFail("\(load)") }
        XCTAssertEqual(event.id, 14780576)
    }

    func testAGameServedAsItsCanonicalRowIsShownAsTheEventPageShowsIt() async {
        let load = await ClipLoader12307.load(.init(kind: .game, id: 1)) { _ in (self.eventJSON(id: 2), 200) }
        guard case .detail(.game(let event)) = load else { return XCTFail("\(load)") }
        XCTAssertEqual(event.id, 2)
    }

    func testAMarketAnsweringForAnotherIDIsRefused() async {
        let load = await ClipLoader12307.load(.init(kind: .market, id: 9)) { _ in (self.marketJSON, 200) }
        XCTAssertEqual(load, .unreachable, "the market page refuses another id's answer, so the clip does")
    }

    func testNotFoundAndRetiredAreGoneNotUnreachable() async {
        for status in [404, 410] {
            let load = await ClipLoader12307.load(.init(kind: .game, id: 99999999)) { _ in (Data(), status) }
            XCTAssertEqual(load, .gone, "\(status)")
        }
    }

    func testAFailedReadIsUnreachable() async {
        for status in [429, 500, 503] {
            let load = await ClipLoader12307.load(.init(kind: .game, id: 1)) { _ in (self.eventJSON(), status) }
            XCTAssertEqual(load, .unreachable, "\(status)")
        }
        let garbled = await ClipLoader12307.load(.init(kind: .game, id: 1)) { _ in (Data("<html>".utf8), 200) }
        XCTAssertEqual(garbled, .unreachable)
        let offline = await ClipLoader12307.load(.init(kind: .game, id: 1)) { _ in throw URLError(.notConnectedToInternet) }
        XCTAssertEqual(offline, .unreachable)
    }

    func testALinkThatNamesNoPageNeverFetches() async {
        var fetches = 0
        let load = await ClipLoader12307.load(nil) { _ in
            fetches += 1
            return (Data(), 200)
        }
        XCTAssertEqual(load, .unsupported)
        XCTAssertEqual(fetches, 0)
    }

    // MARK: - What the page says

    func testAGameReadsAsTheWidgetReadsIt() throws {
        let payload = try SavedWidgetDetailPayload10875.decode(eventJSON(observed: t0), as: .game)
        guard case .game(let event) = payload else { return XCTFail() }
        for at in [t0, t0.addingTimeInterval(31 * 60)] {
            XCTAssertEqual(ClipLoader12307.reading(payload, at: at), SavedWidgetReadingRules10875.game(event, side: nil, now: at),
                           "the favourite leads, as on the event page and an unconfigured widget")
        }
    }

    func testALivePriceSaysWhenItWasObservedThenThatItIsTheLastRecorded() throws {
        let payload = try SavedWidgetDetailPayload10875.decode(eventJSON(observed: t0), as: .game)
        let clock = t0.formatted(date: .omitted, time: .shortened)

        let fresh = ClipLoader12307.reading(payload, at: t0)
        XCTAssertEqual(fresh.phase, .current)
        XCTAssertEqual(ClipLoader12307.caption(fresh, now: t0), "As of \(clock)")

        let later = t0.addingTimeInterval(31 * 60)
        let old = ClipLoader12307.reading(payload, at: later)
        XCTAssertEqual(old.phase, .lastRecorded, "past the live bound the same price stops being current")
        XCTAssertEqual(ClipLoader12307.caption(old, now: later), "Last recorded \(clock)")
    }

    func testAFinishedGameShowsItsResultAndNoPriceCaption() throws {
        let payload = try SavedWidgetDetailPayload10875.decode(
            eventJSON(status: "completed", homeScore: 27, awayScore: 24, extra: #", "hero_settled_result": "home""#), as: .game)
        let reading = ClipLoader12307.reading(payload, at: t0)
        XCTAssertEqual(reading.phase, .result)
        XCTAssertEqual(reading.rows.map(\.verdict), ["Lost", "Won"])
        XCTAssertNil(ClipLoader12307.caption(reading, now: t0), "a result is not a price, so it has no clock line")
    }

    func testAMarketLeadsWithItsHeroLeg() throws {
        let payload = try SavedWidgetDetailPayload10875.decode(marketJSON, as: .market)
        guard case .market(let market) = payload else { return XCTFail() }
        let now = SavedWidgetDetailDecoding10875.date("2026-11-09T17:45:00Z")!
        XCTAssertEqual(ClipLoader12307.reading(payload, at: now),
                       SavedWidgetReadingRules10875.market(market, outcomeID: nil, now: now))
        XCTAssertEqual(ClipLoader12307.reading(payload, at: now).headline?.label, "Carolina Hurricanes")
    }

    func testTheOtherCaptionsAreTheWidgetsWords() {
        func reading(_ phase: SavedWidgetReading10875.Phase, observed: Date?, figure: String? = nil) -> SavedWidgetReading10875 {
            SavedWidgetReading10875(phase: phase, subject: "A vs B", shortSubject: "A vs B", status: "Final", rows: [],
                                    headline: nil, priceCaption: nil, observedAt: observed, becomesLastRecordedAt: nil,
                                    spoken: "", lastRecordedFigure: figure)
        }
        let clock = t0.formatted(date: .omitted, time: .shortened)
        XCTAssertEqual(ClipLoader12307.caption(reading(.openingLine, observed: nil), now: t0), "Opening line")
        XCTAssertEqual(ClipLoader12307.caption(reading(.lastRecorded, observed: nil), now: t0), "Last recorded · time unknown")
        XCTAssertEqual(ClipLoader12307.caption(reading(.noResult, observed: t0, figure: "50%"), now: t0),
                       "Last recorded 50% · \(clock)")
        XCTAssertNil(ClipLoader12307.caption(reading(.noResult, observed: t0), now: t0))
        XCTAssertNil(ClipLoader12307.caption(reading(.unavailable, observed: t0), now: t0))
        XCTAssertEqual(ClipLoader12307.clock(t0, relativeTo: t0.addingTimeInterval(3 * 86_400)),
                       t0.formatted(.dateTime.month(.abbreviated).day().hour().minute()), "another day names the date")
    }
}
