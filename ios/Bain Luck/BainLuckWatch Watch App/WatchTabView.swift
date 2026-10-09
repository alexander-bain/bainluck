import SwiftUI

struct WatchTabView: View {
    var body: some View {
        NavigationStack {
            #if DEBUG
            if ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_SEED_URL"] == "1",
               WatchUIFixture.current != nil {
                // Seed configuration only; do not initialize selection or networking.
                Text("URL fixture ready").accessibilityIdentifier("watch.url-fixture-ready")
            } else if WatchUIFixture.current != nil,
                      let scenario = ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_COMPLICATION"],
                      ["live", "score", "final", "empty", "circular-live", "circular-zero", "circular-hundred", "circular-draw", "circular-final",
                       "circular-away-final", "circular-tie", "circular-score", "circular-old",
                       "circular-invalid", "circular-long", "circular-empty",
                       "rectangular-live", "rectangular-low", "rectangular-zero", "rectangular-hundred",
                       "rectangular-final", "rectangular-away-final", "rectangular-tie", "rectangular-score",
                       "rectangular-long", "rectangular-old", "rectangular-mismatch",
                       "rectangular-invalid", "rectangular-unknown", "rectangular-empty",
                       "corner-fit", "corner-zero", "corner-hundred", "corner-no-label", "corner-old", "corner-invalid", "corner-long",
                       "corner-final", "corner-score", "corner-empty"].contains(scenario) {
                WatchComplicationLayoutFixture(scenario: scenario)
            } else if let fixture = WatchUIFixture.current, fixture.rectangularScoreScenario != nil {
                WatchRectangularScoreHostFixtureView(fixture: fixture)
            } else if WatchUIFixture.current != nil,
               ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_LARGE_TEXT"] == "1" {
                // Layout stress only: watchOS Simulator cannot apply simctl content_size.
                WatchSelectedGameView().dynamicTypeSize(.accessibility5)
            } else {
                WatchSelectedGameView()
            }
            #else
            WatchSelectedGameView()
            #endif
        }
    }
}

#if DEBUG
/// Only the explicit host fixture receives this nonvisual store receipt.
private struct WatchRectangularScoreHostFixtureView: View {
    let fixture: WatchUIFixture
    @State private var receipt = ""

    var body: some View {
        WatchSelectedGameView()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("watch.rectangular-score.store")
            .accessibilityValue(receipt)
            .onAppear {
                // StateObject creation is lazy: read after the real selected view
                // has appeared, never assume its initializer already restored data.
                receipt = fixture.rectangularScoreStoreReceipt
            }
    }
}
#endif
