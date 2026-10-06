#if DEBUG
import SwiftUI
import WidgetKit

/// Shared content layout evidence only: this is not a WidgetKit gallery or shared-container test.
struct WatchComplicationLayoutFixture: View {
    let scenario: String
    @State private var snapshot: WatchComplicationSnapshot?
    @State private var ready = false

    var body: some View {
        VStack(spacing: 8) {
            if ready {
                Group {
                    if scenario.hasPrefix("corner-") {
                        WatchSavedCornerComplicationContent(snapshot: snapshot)
                            .environment(\.showsWidgetLabel, scenario != "corner-no-label")
                            .frame(width: scenario == "corner-fit" ? 34 : 40, height: scenario == "corner-fit" ? 34 : 40)
                    } else if scenario.hasPrefix("circular-") {
                        WatchSavedCircularComplicationContent(snapshot: snapshot)
                            .frame(width: 40, height: 40)
                            .background(Circle().fill(.gray.opacity(0.2)))
                            .clipShape(Circle())
                    } else {
                        WatchSavedComplicationContent(snapshot: snapshot)
                            .frame(width: 156, height: 76, alignment: .leading)
                            .saturation(ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_MONOCHROME"] == "1" ? 0 : 1)
                            .dynamicTypeSize(ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_LARGE_TEXT"] == "1" ? .accessibility5 : .large)
                    }
                }
                    .border(.gray)
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("watch.complication.panel")
                Text("\(scenario.hasPrefix("corner-") ? "Shared corner content" : scenario.hasPrefix("circular-") ? "Shared circular content" : "Rectangular content") · \(scenario)")
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
            let state = scenario.replacingOccurrences(of: "circular-", with: "")
                .replacingOccurrences(of: "rectangular-", with: "")
                .replacingOccurrences(of: "corner-", with: "")
            if state != "empty" {
                let final = ["final", "away-final", "tie"].contains(state)
                var fields: [String: Any] = [
                    "id": 101, "home_team": "San Francisco Giants", "away_team": "Los Angeles Dodgers",
                    "status": final ? "completed" : "live", "sport": "baseball_mlb",
                    "home_score": state == "away-final" ? 2 : 4,
                    "away_score": state == "away-final" ? 4 : 2,
                    "home_team_data": ["team_id": 1, "abbreviation": state == "long" ? "ABCD" : "SF"],
                    "away_team_data": ["team_id": 2, "abbreviation": "LA"],
                    "hero_probability": state == "fit" ? 0.64 : 0.455, "hero_probability_away": state == "fit" ? 0.36 : 0.545,
                    "hero_probability_observed_at": timestamp, "score_observed_at": timestamp
                ]
                if scenario == "rectangular-long" {
                    fields["home_team"] = "Association Sportive de Saint-Étienne Full Canonical Name"
                    fields["away_team"] = "Club de Football Long Complete Opponent Name"
                }
                if state == "unknown" { fields["status"] = "unknown" }
                if ["low", "zero", "hundred"].contains(state) {
                    let probability = state == "low" ? 0.12 : state == "zero" ? 0.0 : 1.0
                    fields["hero_probability"] = probability
                    fields["hero_probability_away"] = 1 - probability
                }
                if state == "tie" { fields["home_score"] = 2; fields["away_score"] = 2 }
                if state == "draw" { fields["sport"] = "soccer_epl" }
                if state == "old" { fields.removeValue(forKey: "home_team_data"); fields.removeValue(forKey: "away_team_data") }
                if state == "invalid" { fields["hero_probability_observed_at"] = "unknown"; fields.removeValue(forKey: "score_observed_at") }
                if state == "score" {
                    fields.removeValue(forKey: "hero_probability")
                    fields.removeValue(forKey: "hero_probability_away")
                    fields.removeValue(forKey: "hero_probability_observed_at")
                }
                if let data = try? JSONSerialization.data(withJSONObject: fields),
                   let game = try? JSONDecoder().decode(WatchSelectedGame.self, from: data) {
                    snapshot = WatchComplicationProjection.snapshot(game: game, savedAt: now)
                    if state == "mismatch", let original = snapshot,
                       let data = try? JSONEncoder().encode(original),
                       var payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       var typed = payload["circularReading"] as? [String: Any] {
                        typed["eventID"] = 202 // Optional typed data must match parent identity.
                        payload["circularReading"] = typed
                        if let invalid = try? JSONSerialization.data(withJSONObject: payload) {
                            snapshot = try? JSONDecoder().decode(WatchComplicationSnapshot.self, from: invalid)
                        }
                    }
                }
            }
            ready = true
        }
    }
}
#endif
