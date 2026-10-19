import XCTest
import SwiftUI
import UIKit
@testable import Bain_Luck

/// #10090 — the hosted chart is offered every history payload the page takes,
/// not only one whose live edge moved.
///
/// The chart adopts the page's payload from an `onChange`. Keyed on the live
/// edge alone, a same-edge correction — a withdrawn source's series leaving a
/// payload whose aggregate edge is unchanged — was never offered, so the chart
/// kept drawing the withdrawn line while the page held the corrected payload
/// and a reconcile floor could be paid by a chart the reader never saw. The
/// offer now also keys on the page's write counter; `OddsChartViewModel.adopt`
/// still decides, so a payload behind the drawn edge is still refused.
@MainActor
final class TheChartIsOfferedEveryPagePayload10090Tests: XCTestCase {
    private final class PageInput: ObservableObject {
        @Published var payload: EventHistoryResponse
        @Published var generation: Int?
        init(payload: EventHistoryResponse, generation: Int?) {
            self.payload = payload
            self.generation = generation
        }
    }

    private struct PageFixture: View {
        @ObservedObject var input: PageInput
        let model: OddsChartViewModel
        var body: some View {
            OddsChartView(eventId: 1, status: "live", homeTeamName: "Home", awayTeamName: "Away",
                          preloadedHistory: input.payload,
                          preloadedHistoryEdge: .some(EventHistoryFreshness.lastReading(in: input.payload)),
                          preloadedHistoryGeneration: input.generation,
                          model: model)
                .environment(\.scenePhase, .active)
        }
    }

    private static let kalshi = #""kalshi":[{"timestamp":"2026-09-21T12:06:00Z","home_probability":0.55}]"#
    private static let polymarket = #""polymarket":[{"timestamp":"2026-09-21T12:07:00Z","home_probability":0.82}]"#

    /// `edge` is the aggregate line's last stamp, which holds the live edge.
    private func payload(_ series: String, edge: String = "2026-09-21T12:10:00Z") throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":1,"home_team":"Home","away_team":"Away","status":"live","history":[],
         "win_prob_history":{\(series)},
         "aggregate_line":[{"timestamp":"2026-09-21T12:00:00Z","home_probability":0.5},
                           {"timestamp":"\(edge)","home_probability":0.6}]}
        """.utf8))
    }

    private func pump(_ host: UIViewController, times: Int = 6) {
        for _ in 0..<times {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
    }

    private func hosted(_ input: PageInput, _ model: OddsChartViewModel) -> (UIViewController, UIWindow) {
        let host = hostForMeasurement(PageFixture(input: input, model: model).frame(width: 390), at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        pump(host)
        return (host, window)
    }

    func testASameEdgeCorrectionIsOfferedAndTakenAndABehindEdgeOneIsStillRefused() throws {
        let both = try payload("\(Self.kalshi),\(Self.polymarket)")
        let withdrawn = try payload(Self.kalshi)
        let behind = try payload(Self.kalshi, edge: "2026-09-21T12:08:00Z")
        XCTAssertEqual(EventHistoryFreshness.lastReading(in: both), EventHistoryFreshness.lastReading(in: withdrawn),
                       "the correction leaves the live edge where it was")
        XCTAssertNotEqual(both, withdrawn)
        let model = OddsChartViewModel(eventId: 1, preloaded: both)
        let input = PageInput(payload: both, generation: 1)
        let (host, window) = hosted(input, model)
        defer { window.isHidden = true }
        XCTAssertEqual(model.history, both)

        input.payload = withdrawn
        input.generation = 2
        pump(host)
        XCTAssertEqual(model.history, withdrawn, "the chart draws the corrected payload")
        XCTAssertNil(model.history?.winProbHistory?["polymarket"])

        input.payload = behind
        input.generation = 3
        pump(host)
        XCTAssertEqual(model.history, withdrawn, "a payload behind the drawn edge is still refused")
    }

    /// A caller that supplies no counter keeps the edge-only offer.
    func testWithNoCounterTheOfferIsKeyedOnTheEdgeAlone() throws {
        let both = try payload("\(Self.kalshi),\(Self.polymarket)")
        let withdrawn = try payload(Self.kalshi)
        let model = OddsChartViewModel(eventId: 1, preloaded: both)
        let input = PageInput(payload: both, generation: nil)
        let (host, window) = hosted(input, model)
        defer { window.isHidden = true }
        input.payload = withdrawn
        pump(host)
        XCTAssertEqual(model.history, both)
    }
}
