import Foundation

#if DEBUG
// MARK: - #683 a local render fixture for the real Evolution chart
//
// Root admitted (10/15) the smallest DEBUG-only seam that renders the ACTUAL
// `EvolutionChartView` — its chart, caption and selected readout — over synthetic
// decoded responses, so the recovered-history labels can be looked at before any
// real archive is imported. Without it the chart can only load through
// `APIClient.shared`, i.e. production.
//
// The seam is three inputs and nothing else: the client every read goes through
// (a test's own `APIClient(session:)` over a stubbed URLProtocol), the chip the
// chart opens on, and an instant to read out as if a finger held it there. It
// exists only in DEBUG builds and no production caller passes it, so an ordinary
// reader's chart cannot select it. A render through it pays LOCAL rendering only:
// the served imported specimen and the installed build are still owed.
struct EvolutionChartFixture {
    let client: APIClient
    var range: EvolutionTimeRange = .season
    var selectAt: Date? = nil
}
#endif
