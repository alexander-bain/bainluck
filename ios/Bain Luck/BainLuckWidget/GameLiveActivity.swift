#if os(iOS) && canImport(ActivityKit)
import ActivityKit
import SwiftUI
import WidgetKit

/// Local ActivityKit content. Updates require the phone's foreground owner.
@available(iOS 17.0, *)
struct GameLiveActivity: Widget {
    @WidgetConfigurationBuilder
    var body: some WidgetConfiguration {
        if #available(iOS 18.0, *) {
            configuration.supplementalActivityFamilies([.small, .medium])
        } else {
            configuration
        }
    }

    private var configuration: some WidgetConfiguration {
        ActivityConfiguration(for: GameActivityAttributes.self) { context in
            if #available(iOS 18.0, *) {
                GameActivityFamilyView(context: context)
            } else {
                GameActivityReadingView(context: context, compact: false)
            }
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.center) {
                    GameActivityReadingView(context: context, compact: true)
                }
            } compactLeading: {
                Text(context.state.snapshot.eventID == context.attributes.eventID
                     ? context.state.snapshot.matchup : "Game unavailable")
                    .font(.caption2).lineLimit(1)
            } compactTrailing: {
                Text(compactReading(context))
                    .font(.caption2.bold()).monospacedDigit()
                    .accessibilityLabel(compactAccessibility(context))
            } minimal: {
                Text(compactReading(context))
                    .font(.caption2.bold()).monospacedDigit()
                    .accessibilityLabel(compactAccessibility(context))
            }
            .widgetURL(GameContinuation.url(eventID: context.attributes.eventID))
        }
    }

    private func compactReading(_ context: ActivityViewContext<GameActivityAttributes>) -> String {
        let snapshot = context.state.snapshot
        guard snapshot.eventID == context.attributes.eventID else { return "—" }
        if context.isStale { return "Stale" }
        if snapshot.isFinal { return "Final" }
        if snapshot.isTerminal { return "Closed" }
        if snapshot.lifecycle == .live || snapshot.lifecycle == .scheduled {
            return snapshot.probabilityText ?? "—"
        }
        return snapshot.lifecycle == .suspended ? "Paused" : "—"
    }

    private func compactAccessibility(_ context: ActivityViewContext<GameActivityAttributes>) -> String {
        let snapshot = context.state.snapshot
        guard snapshot.eventID == context.attributes.eventID else { return "Game reading unavailable" }
        let reading = snapshot.resultText ?? snapshot.probabilityLabel ?? "Probability unavailable"
        let scoreAge = ageLabel("Score", age: snapshot.scoreAge(at: Date()))
        let probabilityAge = snapshot.probabilityText == nil ? "" : ageLabel("Probability", age: snapshot.probabilityAge(at: Date()))
        return "\(snapshot.matchup). \(reading). \(scoreAge) \(probabilityAge) \(context.isStale ? "Stale reading. Open on iPhone to refresh." : "Reported reading. Open on iPhone for current details.")"
    }

    private func ageLabel(_ name: String, age: TimeInterval?) -> String {
        guard let age, age.isFinite, age >= 0 else { return "\(name) observation time unavailable." }
        if age / 60 >= Double(Int.max) {
            return "\(name) observed a long time ago."
        }
        return "\(name) observed \(Int(age / 60)) minutes ago."
    }
}

@available(iOS 18.0, *)
private struct GameActivityFamilyView: View {
    @Environment(\.activityFamily) private var family
    let context: ActivityViewContext<GameActivityAttributes>

    var body: some View {
        GameActivityReadingView(context: context, compact: family == .small)
    }
}

@available(iOS 17.0, *)
private struct GameActivityReadingView: View {
    let context: ActivityViewContext<GameActivityAttributes>
    let compact: Bool

    private var snapshot: GameActivitySnapshot { context.state.snapshot }
    private var showsForecast: Bool {
        snapshot.lifecycle == .live || snapshot.lifecycle == .scheduled
    }

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 3 : 6) {
            if snapshot.eventID != context.attributes.eventID {
                Text("Game reading unavailable").font(.headline)
                Text("Open on iPhone for current details.").font(.caption)
            } else {
                Text("Reported · \(snapshot.statusLabel)")
                    .font(.caption.bold()).fixedSize(horizontal: false, vertical: true)
                if context.isStale {
                    Text("Stale reading · open on iPhone to refresh")
                        .font(.caption.bold()).foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
                teamScore(snapshot.awayTeam, score: snapshot.awayScore)
                teamScore(snapshot.homeTeam, score: snapshot.homeScore)
                if let result = snapshot.resultText {
                    Text(result).font(.subheadline.bold())
                        .fixedSize(horizontal: false, vertical: true)
                } else if showsForecast {
                    Text(snapshot.probabilityLabel ?? "Win probability unavailable")
                        .font(.subheadline.bold()).monospacedDigit()
                        .fixedSize(horizontal: false, vertical: true)
                }
                observation("Score", date: snapshot.scoreObservedAt,
                            age: snapshot.scoreAge(at: Date()))
                if showsForecast && snapshot.probabilityText != nil {
                    observation("Probability", date: snapshot.probabilityObservedAt,
                                age: snapshot.probabilityAge(at: Date()))
                }
            }
        }
        .padding(compact ? 8 : 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .widgetURL(GameContinuation.url(eventID: context.attributes.eventID))
    }

    private func teamScore(_ team: String, score: Int?) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(team).font(compact ? .caption : .subheadline)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 2)
            Text(score.map(String.init) ?? "—")
                .font(.subheadline.bold()).monospacedDigit()
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(team), \(score.map { "score \($0)" } ?? "score unavailable")")
    }

    @ViewBuilder
    private func observation(_ name: String, date: Date?, age: TimeInterval?) -> some View {
        if let date, age != nil {
            Text("\(name) observed \(date, style: .relative) ago")
                .font(.caption2).foregroundStyle(.secondary)
        } else {
            Text("\(name) observation time unavailable")
                .font(.caption2).foregroundStyle(.secondary)
        }
    }
}
#endif
