import SwiftUI
import WidgetKit

/// Shared rectangular content; WidgetKit owns the surrounding widget context.
struct WatchSavedComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?
    @Environment(\.widgetRenderingMode) private var renderingMode

    private var forecastColor: Color { renderingMode == .fullColor ? .cyan : .primary }

    var body: some View {
        if let snapshot, let reading = snapshot.validatedCircularReading {
            GeometryReader { geometry in
                ViewThatFits(in: [.horizontal, .vertical]) {
                    if reading.kind != .forecast,
                       let awayScore = reading.awayScore, let homeScore = reading.homeScore,
                       geometry.size.width > 12 {
                        namedScoreColumns(snapshot, reading: reading, awayScore: awayScore,
                                          homeScore: homeScore, width: geometry.size.width)
                            .fixedSize()
                    }
                    namedReading(snapshot, reading: reading, width: geometry.size.width)
                        .fixedSize(horizontal: false, vertical: true)
                    if reading.kind == .forecast, let away = reading.away, away.isValid {
                        compactOpponentReading(snapshot, reading: reading, away: away)
                            .fixedSize()
                    }
                    if reading.kind != .forecast,
                       let home = reading.home, let away = reading.away,
                       home.isValid, away.isValid,
                       let homeScore = reading.homeScore, let awayScore = reading.awayScore,
                       homeScore >= 0, awayScore >= 0 {
                        compactScoreColumns(snapshot, reading: reading, home: home, away: away,
                                            homeScore: homeScore, awayScore: awayScore)
                            .fixedSize()
                    }
                    compactReading(snapshot, reading: reading)
                        .fixedSize()
                    savedLauncher(snapshot)
                }
                .frame(width: geometry.size.width, height: geometry.size.height, alignment: .leading)
            }
        } else if let snapshot {
            // Legacy or malformed optional typed data does not earn invented graphics.
            VStack(alignment: .leading, spacing: 1) {
                Text(snapshot.title)
                    .font(.system(size: 12, weight: .semibold))
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.complication.title")
                Text("Saved · \(snapshot.detail)")
                    .font(.system(size: 11))
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.complication.detail")
                Text("Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened))")
                    .font(.system(size: 9))
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.complication.observed")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            HStack(spacing: 8) {
                Image(systemName: "chart.bar.fill").font(.title2)
                VStack(alignment: .leading) {
                    Text("Your game").font(.headline)
                    Text("Open Bain Luck").font(.caption)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("watch.complication.fallback")
        }
    }

    /// Both complete name headers share one intrinsic row; score baselines align below it.
    /// The candidate reports its whole intrinsic size so existing fallbacks can reject it.
    private func namedScoreColumns(_ snapshot: WatchComplicationSnapshot,
                                   reading: WatchCircularReading, awayScore: Int,
                                   homeScore: Int, width: CGFloat) -> some View {
        let columnWidth = (width - 12) / 2
        return VStack(alignment: .leading, spacing: 3) {
            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 1) {
                GridRow(alignment: .top) {
                    Text(namedScoreTeam(reading, home: false))
                        .font(.system(size: 12, weight: .semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(width: columnWidth, alignment: .leading)
                    Text(namedScoreTeam(reading, home: true))
                        .font(.system(size: 12, weight: .semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(width: columnWidth, alignment: .leading)
                }
                GridRow(alignment: .firstTextBaseline) {
                    Text(String(awayScore))
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .monospacedDigit().fixedSize()
                    Text(String(homeScore))
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .monospacedDigit().fixedSize()
                }
            }
            metadata(snapshot, reading: reading,
                     stateLabel: reading.kind == .final && awayScore == homeScore ? "Final tie" : reading.stateLabel)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(namedAccessibilityReading(snapshot, reading: reading))
        .accessibilityIdentifier("watch.complication.rectangular.named-score-columns")
    }

    /// Full names wrap at the real proposed width; their full height must fit.
    /// No line limit can silently turn a long name into a fitting candidate.
    private func namedReading(_ snapshot: WatchComplicationSnapshot,
                              reading: WatchCircularReading, width: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            if reading.kind != .forecast,
               let awayScore = reading.awayScore, let homeScore = reading.homeScore {
                VStack(alignment: .leading, spacing: 1) {
                    namedScoreRow(team: namedScoreTeam(reading, home: false), score: awayScore)
                    namedScoreRow(team: namedScoreTeam(reading, home: true), score: homeScore)
                }
            } else {
                // Full title and 30pt probability share height; neither is clipped.
                HStack(alignment: .center, spacing: 6) {
                    Text(snapshot.title)
                        .font(.system(size: 12, weight: .semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Text(prominentValue(reading))
                        .font(.system(size: 30, weight: .bold, design: .rounded))
                        .foregroundStyle(forecastColor).monospacedDigit().fixedSize()
                }
            }
            metadata(snapshot, reading: reading)
        }
        .frame(width: width, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(namedAccessibilityReading(snapshot, reading: reading))
        .accessibilityIdentifier("watch.complication.rectangular.prominent")
    }

    /// Two explicit team-score associations; the full row height must earn its space.
    private func namedScoreRow(team: String, score: Int) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(team)
                .font(.system(size: 11, weight: .semibold))
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
            Text(String(score))
                .font(.system(size: 18, weight: .bold, design: .rounded))
                .monospacedDigit().fixedSize()
        }
    }

    private func namedScoreTeam(_ reading: WatchCircularReading, home: Bool) -> String {
        let name = home ? reading.homeName : reading.awayName
        guard reading.kind == .final, let homeScore = reading.homeScore,
              let awayScore = reading.awayScore, homeScore != awayScore else { return name }
        let won = home ? homeScore > awayScore : awayScore > homeScore
        return won ? "\(name) won" : name
    }

    private func namedAccessibilityReading(_ snapshot: WatchComplicationSnapshot,
                                           reading: WatchCircularReading) -> String {
        guard reading.kind != .forecast, let awayScore = reading.awayScore,
              let homeScore = reading.homeScore else { return accessibilityReading(snapshot) }
        let state = reading.kind == .final && awayScore == homeScore ? "Final tie" : reading.stateLabel
        return "Saved reading. \(namedScoreTeam(reading, home: false)), score \(awayScore). "
            + "\(namedScoreTeam(reading, home: true)), score \(homeScore). \(state). "
            + "Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck."
    }

    /// Canonical opponent context is optional; the existing compact reading remains the fallback.
    private func compactOpponentReading(_ snapshot: WatchComplicationSnapshot,
                                        reading: WatchCircularReading,
                                        away: WatchCompactTeamIdentity) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                Text(prominentValue(reading))
                    .font(.system(size: 24, weight: .bold, design: .rounded)).monospacedDigit()
                    .foregroundStyle(forecastColor)
                VStack(alignment: .leading, spacing: 1) {
                    Text(reading.subject).font(.system(size: 12, weight: .semibold))
                    Text("vs \(away.abbreviation)").font(.system(size: 12, weight: .semibold))
                }
            }
            metadata(snapshot, reading: reading)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Saved reading. \(reading.awayName) at \(reading.homeName). \(snapshot.title). \(snapshot.detail). Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck.")
        .accessibilityIdentifier("watch.complication.rectangular.opponent")
    }

    /// Full-name rows remain first. These canonical columns must fit in their entirety.
    private func compactScoreColumns(_ snapshot: WatchComplicationSnapshot,
                                     reading: WatchCircularReading,
                                     home: WatchCompactTeamIdentity, away: WatchCompactTeamIdentity,
                                     homeScore: Int, awayScore: Int) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .top, spacing: 12) {
                compactScoreColumn(identity: away.abbreviation, score: awayScore,
                                   won: reading.kind == .final && awayScore > homeScore)
                compactScoreColumn(identity: home.abbreviation, score: homeScore,
                                   won: reading.kind == .final && homeScore > awayScore)
            }
            metadata(snapshot, reading: reading)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(namedAccessibilityReading(snapshot, reading: reading))
        .accessibilityIdentifier("watch.complication.rectangular.score-columns")
    }

    private func compactScoreColumn(identity: String, score: Int, won: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Text(won ? "\(identity) won" : identity)
                .font(.system(size: 12, weight: .semibold)).fixedSize()
            Text(String(score))
                .font(.system(size: 22, weight: .bold, design: .rounded))
                .monospacedDigit().fixedSize()
        }
    }

    /// Canonical compact identities, never a truncated full name or guessed abbreviation.
    private func compactReading(_ snapshot: WatchComplicationSnapshot,
                                reading: WatchCircularReading) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                if reading.kind == .forecast {
                    Text(prominentValue(reading))
                        .font(.system(size: 24, weight: .bold, design: .rounded)).monospacedDigit()
                        .foregroundStyle(forecastColor)
                    Text(reading.subject).font(.system(size: 12, weight: .semibold))
                } else {
                    Text(reading.subject).font(.system(size: 12, weight: .semibold))
                    Text(prominentValue(reading))
                        .font(.system(size: reading.kind == .forecast ? 24 : 22, weight: .bold, design: .rounded)).monospacedDigit()
                        .foregroundStyle(reading.kind == .forecast ? forecastColor : .primary)
                }
            }
            metadata(snapshot, reading: reading)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(namedAccessibilityReading(snapshot, reading: reading))
        .accessibilityIdentifier("watch.complication.rectangular.compact")
    }

    private func metadata(_ snapshot: WatchComplicationSnapshot,
                          reading: WatchCircularReading, stateLabel: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("Saved · \(stateLabel ?? reading.stateLabel)").font(.system(size: 11, weight: .medium))
            Text("As of \(snapshot.observedAt.formatted(.dateTime.month(.abbreviated).day().year().hour().minute()))")
                .font(.system(size: 10))
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private func prominentValue(_ reading: WatchCircularReading) -> String {
        if reading.kind == .forecast { return reading.value }
        guard let home = reading.homeScore, let away = reading.awayScore else { return "" }
        // Match the named final winner; live/tied matchup scores keep away-home order.
        if reading.kind == .final, home > away { return "\(home)–\(away)" }
        return "\(away)–\(home)"
    }

    private func savedLauncher(_ snapshot: WatchComplicationSnapshot) -> some View {
        Label("Open saved game", systemImage: "chart.bar.fill").font(.caption)
            .accessibilityLabel("Open your saved game in Bain Luck. \(snapshot.title).")
            .accessibilityIdentifier("watch.complication.rectangular.launcher")
    }

    private func accessibilityReading(_ snapshot: WatchComplicationSnapshot) -> String {
        "Saved reading. \(snapshot.title). \(snapshot.detail). Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck."
    }
}

/// Complete named saved reading or launcher; no clipped shorthand or currentness claim.
struct WatchSavedCircularComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?

    var body: some View {
        if let snapshot, let reading = snapshot.validatedCircularReading {
            GeometryReader { geometry in
                // A rectangular fit alone cannot prove a fit inside the circle.
                // Reserve 40 points for the three readable lines, and derive the
                // largest centered rectangle whose corners stay inside this slot.
                let diameter = min(geometry.size.width, geometry.size.height)
                let contentHeight: CGFloat = 40
                let safeWidth = sqrt(max(0, diameter * diameter - contentHeight * contentHeight))
                ViewThatFits(in: [.horizontal, .vertical]) {
                    VStack(spacing: 0) {
                        Text(reading.subject).font(.system(size: 10, weight: .semibold))
                            .accessibilityIdentifier("watch.complication.circular.subject")
                        Text(reading.value).font(.system(size: reading.kind == .forecast ? 14 : 10, weight: .bold))
                            .accessibilityIdentifier("watch.complication.circular.value")
                        Text("Saved").font(.system(size: 9, weight: .medium))
                            .accessibilityIdentifier("watch.complication.circular.saved")
                    }
                    .fixedSize()
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(circularAccessibilityReading(snapshot, reading: reading))
                    .accessibilityValue("Saved · \(reading.subject) · \(reading.value)")
                    .accessibilityIdentifier("watch.complication.circular.reading")
                    launcher
                }
                .frame(width: safeWidth, height: min(contentHeight, diameter))
                .frame(width: geometry.size.width, height: geometry.size.height)
            }
        } else {
            launcher
        }
    }

    /// The ignored-child parent preserves both full names and their actual scores.
    private func circularAccessibilityReading(_ snapshot: WatchComplicationSnapshot,
                                              reading: WatchCircularReading) -> String {
        guard reading.kind != .forecast, let awayScore = reading.awayScore,
              let homeScore = reading.homeScore else {
            return "Saved reading. \(snapshot.title). \(snapshot.detail). Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck."
        }
        let awayName = reading.kind == .final && awayScore > homeScore
            ? "\(reading.awayName) won" : reading.awayName
        let homeName = reading.kind == .final && homeScore > awayScore
            ? "\(reading.homeName) won" : reading.homeName
        let state = reading.kind == .final && awayScore == homeScore ? "Final tie" : reading.stateLabel
        return "Saved reading. \(awayName), score \(awayScore). \(homeName), score \(homeScore). \(state). "
            + "Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck."
    }

    private var launcher: some View {
        Image(systemName: "chart.bar.fill")
            .font(.system(size: 18))
            .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
            .accessibilityIdentifier("watch.complication.circular.fallback")
    }
}

/// WidgetKit owns the curved label's font and placement. Its complete rendered
/// label is an actual-face acceptance gate, not a runtime presence signal.
struct WatchSavedCornerComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?
    @Environment(\.showsWidgetLabel) private var showsWidgetLabel
    @Environment(\.widgetRenderingMode) private var renderingMode

    var body: some View {
        if let snapshot, let reading = snapshot.validatedCornerForecast(showsWidgetLabel: showsWidgetLabel),
           let percent = reading.percent {
            ViewThatFits(in: [.horizontal, .vertical]) {
                VStack(spacing: 0) {
                    Text(percent.formatted(.number.grouping(.never)))
                        // Preserve16pt digits; separate the unit without parsing formatted value text.
                        .font(.system(size: 16, weight: .bold))
                        .fixedSize()
                    Text("%")
                        .font(.system(size: 12, weight: .medium))
                        .fixedSize()
                }
                    .fixedSize()
                    .accessibilityElement(children: .ignore)
                    .widgetLabel {
                        Text("Saved · \(reading.subject)")
                            .accessibilityIdentifier("watch.complication.corner.label")
                    }
                    .accessibilityLabel("Saved reading. \(reading.awayName) at \(reading.homeName). \(snapshot.title). \(snapshot.detail). Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck.")
                    .accessibilityValue("Saved · \(reading.subject) · \(reading.value)")
                    .accessibilityIdentifier("watch.complication.corner.reading")
                launcher
            }
        } else {
            launcher
        }
    }

    private var launcher: some View {
        Image(systemName: "chart.bar.fill")
            .font(.system(size: 18))
            .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
            .accessibilityIdentifier("watch.complication.corner.fallback")
    }
}
