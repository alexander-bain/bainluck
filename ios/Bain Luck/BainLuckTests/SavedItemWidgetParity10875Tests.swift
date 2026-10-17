import XCTest
@testable import Bain_Luck

/// #10875 — every rule the saved-item widget restates against its own decode,
/// held to the app rule it restates, on the same inputs. The widget extension
/// cannot compile the app's models, so these are the only thing standing
/// between a change to the detail page and a widget that quietly says
/// something else about the same game.
@MainActor
final class SavedItemWidgetParity10875Tests: XCTestCase {

    private let t0 = Date(timeIntervalSince1970: 1_792_000_000)

    private func iso(_ date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: date)
    }

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func eventJSON(status: String?, source: String, observed: Date?, commence: Date?,
                           home: Double = 0.62, away: Double = 0.38,
                           heroHome: Double? = 0.5996, heroAway: Double? = 0.4004,
                           served: (away: Int, home: Int)? = nil) -> Data {
        func field(_ v: Any?) -> String { v.map { "\($0)" } ?? "null" }
        let statusField = status.map { "\"\($0)\"" } ?? "null"
        let rendered = served.map { ", \"away_rendered_percent\": \($0.away), \"home_rendered_percent\": \($0.home)" } ?? ""
        return Data("""
        {"id": 14780556, "sport": "americanfootball_nfl", "home_team": "Chicago Bears", "away_team": "Green Bay Packers",
         "status": \(statusField), "commence_time": \(commence.map { "\"\(iso($0))\"" } ?? "null"),
         "current_odds": {"home_probability": \(home), "away_probability": \(away)\(rendered)},
         "hero_probability": \(field(heroHome)), "hero_probability_away": \(field(heroAway)),
         "hero_probability_source": "\(source)",
         "hero_probability_observed_at": \(observed.map { "\"\(iso($0))\"" } ?? "null")}
        """.utf8)
    }

    func testStalenessBoundsAreSourceAges() {
        XCTAssertEqual(SavedWidgetStaleness10875.liveStaleAfter, SourceAge.liveStaleAfter,
                       "the widget's live bound drifted from SourceAge")
        XCTAssertEqual(SavedWidgetStaleness10875.futuresStaleAfter, SourceAge.futuresStaleAfter,
                       "the widget's market bound drifted from SourceAge")
    }

    func testHeroPairIsOpeningLineHeroOnTheSameEvent() throws {
        for status in ["scheduled", "live", "completed", "suspended", nil] as [String?] {
            for source in ["opening", "blend", "settled"] {
                for (heroHome, heroAway) in [(0.5996, 0.4004), (1.0, 0.0), (nil, nil)] as [(Double?, Double?)] {
                    let json = eventJSON(status: status, source: source, observed: t0, commence: t0,
                                         heroHome: heroHome, heroAway: heroAway, served: (38, 62))
                    let app = try decoder().decode(EventDetail.self, from: json)
                    let widget = try decoder().decode(SavedWidgetEventDetail10875.self, from: json)
                    let expected = OpeningLineHero.resolve(try XCTUnwrap(app.currentOdds), for: app)
                    let got = try XCTUnwrap(SavedWidgetReadingRules10875.heroPair(widget))
                    let label = "\(status ?? "nil")/\(source)/\(String(describing: heroHome))"
                    XCTAssertEqual(got.isOpeningLine, expected.isOpeningLine, "opening arm differs: \(label)")
                    XCTAssertEqual(got.home, expected.homeProbability, "home differs: \(label)")
                    XCTAssertEqual(got.away, expected.awayProbability, "away differs: \(label)")
                    XCTAssertEqual(got.homeRenderedPercent, expected.homeRenderedPercent, "served home differs: \(label)")
                    XCTAssertEqual(got.awayRenderedPercent, expected.awayRenderedPercent, "served away differs: \(label)")
                }
            }
        }
    }

    func testPairPercentsAreTheHerosPercents() {
        let cases: [(Double, Double, Int?, Int?)] = [
            (0.495, 0.505, nil, nil), (0.445, 0.555, nil, nil), (0.38, 0.62, 38, 62), (0.495, 0.505, nil, 52), (0.3, 0.6, nil, nil),
        ]
        for (away, home, sa, sh) in cases {
            let appShown = OpeningLineHero(awayProbability: away, homeProbability: home,
                                           awayRenderedPercent: sa, homeRenderedPercent: sh, isOpeningLine: false)
            let widgetShown = SavedWidgetReadingRules10875.HeroPair(away: away, home: home, awayRenderedPercent: sa,
                                                                    homeRenderedPercent: sh, isOpeningLine: false)
            let expected = EventDetailView.heroPairPercents(appShown, away: away, home: home)
            let got = SavedWidgetReadingRules10875.heroPairPercents(widgetShown, away: away, home: home)
            XCTAssertEqual(got.away, expected.away, "away integer differs for \(away)/\(home)")
            XCTAssertEqual(got.home, expected.home, "home integer differs for \(away)/\(home)")
        }
    }

    func testCurrentIsTheHeadlinePhasesCurrent() {
        let statuses: [String?] = ["scheduled", "live", "suspended", "delayed", nil]
        let commences: [Date?] = [t0.addingTimeInterval(3600), t0.addingTimeInterval(-3600), nil]
        let observations: [Date?] = [t0.addingTimeInterval(-60), t0.addingTimeInterval(-30 * 60),
                                     t0.addingTimeInterval(-30 * 60 - 1), nil]
        for status in statuses {
            for commence in commences {
                for observed in observations {
                    let expected = EventHeadlinePhase9483.resolve(status: status, commenceTime: commence,
                                                                  isOpeningLine: false, observedAt: observed, now: t0)
                    let got = SavedWidgetReadingRules10875.isCurrentGamePrice(status: status, commence: commence,
                                                                              observedAt: observed, now: t0)
                    XCTAssertEqual(got, expected == .current,
                                   "current differs: \(status ?? "nil") commence \(String(describing: commence)) observed \(String(describing: observed))")
                }
            }
        }
    }

    private func marketJSON(status: String, lead: Int?) -> Data {
        let leadKey = lead.map { "\"lead_outcome_id\": \($0)," } ?? ""
        return Data("""
        {"id": 61778284, "name": "LoL: Cloud9 vs Team Liquid (BO5)", "status": "\(status)", \(leadKey)
         "outcomes": [
           {"id": 1, "name": "Over 3.5", "probability": 0.71},
           {"id": 2, "name": "Handicap", "probability": 0.44},
           {"id": 3, "name": "Game 2", "probability": 0.425},
           {"id": 4, "name": "Tie A", "probability": 0.2},
           {"id": 5, "name": "Tie B", "probability": 0.2},
           {"id": 6, "name": "Match Winner", "probability": 0.36},
           {"id": 7, "name": "Unpriced", "probability": null}
         ]}
        """.utf8)
    }

    func testMarketIntegersAndHeroLegAreTheMarketPagesOwn() throws {
        for (status, lead) in [("open", 6), ("open", nil), ("resolved", 6), ("open", 7)] as [(String, Int?)] {
            let json = marketJSON(status: status, lead: lead)
            let app = try decoder().decode(FuturesMarketDetail.self, from: json)
            let widget = try decoder().decode(SavedWidgetMarketDetail10875.self, from: json)
            XCTAssertEqual(SavedWidgetReadingRules10875.renderedPercents(widget.outcomes),
                           futuresDetailRenderedPercents(app.outcomes), "integers differ: \(status)/\(String(describing: lead))")
            XCTAssertEqual(SavedWidgetReadingRules10875.heroOutcome(widget)?.id, futuresDetailHeroOutcome(app)?.id,
                           "hero leg differs: \(status)/\(String(describing: lead))")
        }
    }

    func testMarketRowValueIsTheMarketPagesRowValue() throws {
        let json = Data("""
        {"id": 54069274, "name": "Boston vs Detroit: Team Total", "status": "resolved", "outcomes": [
          {"id": 1, "name": "Boston over 3.5", "probability": 0.99, "is_winner": true, "resolution_source": "game_score"},
          {"id": 2, "name": "Detroit over 3.5", "probability": 0.01, "is_winner": false, "resolution_source": "game_score"},
          {"id": 3, "name": "Detroit over 4.5", "probability": null, "is_winner": null, "resolution_source": null}
        ]}
        """.utf8)
        let app = try decoder().decode(FuturesMarketDetail.self, from: json)
        let widget = try decoder().decode(SavedWidgetMarketDetail10875.self, from: json)
        for outcome in app.outcomes {
            let reading = SavedWidgetReadingRules10875.market(widget, outcomeID: outcome.id, now: t0)
            switch FuturesDetailRowValue.of(outcome, marketStatus: app.status) {
            case .verdict(let verdict):
                XCTAssertEqual(reading.headline?.verdict, verdict.label, "verdict differs for \(outcome.name)")
            case .price:
                XCTAssertNotNil(reading.headline?.figure, "price missing for \(outcome.name)")
            case .none:
                XCTAssertNil(reading.headline?.figure, "a number appeared for \(outcome.name)")
                XCTAssertNil(reading.headline?.verdict, "a verdict appeared for \(outcome.name)")
            default:
                // Native's #698 consumer adds `.resultUnknown`; this arm keeps the
                // composed tree compiling and refuses any row value this test was
                // not written for. The #698 parity lives in
                // SavedItemWidgetSettledResult10875Tests.
                XCTFail("row value \(FuturesDetailRowValue.of(outcome, marketStatus: app.status)) for \(outcome.name) is not covered here")
            }
        }
    }

    func testEveryTapDestinationIsARouteTheAppOpens() {
        let nav = NavigationCoordinator()
        XCTAssertTrue(nav.handleURL(SavedWidgetSubject10875(kind: .game, id: 15327330).url!), "the game route is not handled")
        XCTAssertEqual(nav.selectedTab, .feed)
        XCTAssertTrue(nav.handleURL(SavedWidgetSubject10875(kind: .market, id: 65391342).url!), "the market route is not handled")
        XCTAssertTrue(nav.handleURL(URL(string: "bainluck://my-stuff")!), "the My Stuff route is not handled")
        XCTAssertEqual(nav.selectedTab, .myStuff)
    }
}
