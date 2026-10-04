#if DEBUG
import SwiftUI

/// Shared content layout evidence only: this is not a WidgetKit gallery or shared-container test.
struct WatchComplicationLayoutFixture: View {
    let scenario: String
    @State private var snapshot: WatchComplicationSnapshot?
    @State private var ready = false

    var body: some View {
        VStack(spacing: 8) {
            if ready {
                WatchSavedComplicationContent(snapshot: snapshot)
                    .frame(width: 156, height: 76, alignment: .leading)
                    .border(.gray)
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("watch.complication.panel")
                Text("Rectangular content · \(scenario)")
                    .font(.caption2)
                    .accessibilityIdentifier("watch.complication.ready")
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Layout fixture")
        .task {
            guard !ready else { return }
            let now = ISO8601DateFormatter().date(from: "2026-10-04T12:02:00Z")!
            let timestamp = ISO8601DateFormatter().string(from: now.addingTimeInterval(-120))
            if scenario != "empty" {
                let final = scenario == "final"
                let fields: [String: Any] = [
                    "id": 101, "home_team": "San Francisco Giants", "away_team": "Los Angeles Dodgers",
                    "status": final ? "completed" : "live", "sport": "baseball_mlb",
                    "home_score": 4, "away_score": 2,
                    "hero_probability": 0.455, "hero_probability_away": 0.545,
                    "hero_probability_observed_at": timestamp, "score_observed_at": timestamp
                ]
                if let data = try? JSONSerialization.data(withJSONObject: fields),
                   let game = try? JSONDecoder().decode(WatchSelectedGame.self, from: data) {
                    snapshot = WatchComplicationProjection.snapshot(game: game, savedAt: now)
                }
            }
            ready = true
        }
    }
}
#endif
