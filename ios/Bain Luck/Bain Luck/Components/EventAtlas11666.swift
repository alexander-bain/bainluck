import SwiftUI

/// #11666 (Step E1) — Native event-page atlas headline and shared details sheet,
/// matching the shipped web E1 contract (#11974 / PR #12113) behind
/// `ReleaseSurfaces.isEventPageAtlasEnabled()`.
///
/// Key guarantees:
/// 1. Settled games show `✓ Won` (`✗ Lost` on paired side, `Draw` on ties) with
///    the hollow pregame mark `○` (`"Upset · X% pregame"` when the winner's
///    pregame chance was `< 45%`, otherwise `"X% pregame"`).
/// 2. Live and upcoming games show the phase label (`"Current win chance"` vs
///    `"Last recorded win chance"` on the 30-minute staleness bound,
///    interrupted delivery, or started-and-not-live) and the hollow pregame
///    mark `○` (`"Pregame X% – Y%"` / `"Opened X% – Y%"`) during play.
/// 3. The shared `EventAtlasDetailsSheet11666` displays the outcome/matchup
///    name, market title, settled result or current probability, pregame
///    baseline, observed timestamp, and source label — saying `"Blended"`
///    only when `source == "blended"` or `sourceCount > 1`, and naming the
///    single venue (`SourceLabels`) when `sourceCount == 1`.
nonisolated enum EventAtlasHeadline11666 {

    /// Settled headline badge model for the native event page.
    nonisolated struct SettledBadge: Equatable, Sendable {
        let winnerLabel: String
        let systemImage: String?
        let pregameMarkText: String?
        let isUpset: Bool
    }

    /// Resolves the settled Atlas headline badge and hollow pregame mark `○`.
    static func settledBadge(
        outcome: EventOutcome,
        awayTeam: String,
        homeTeam: String,
        sportKey: String?,
        prematch: PrematchOdds?,
        opening: OpeningOdds?
    ) -> SettledBadge {
        let pregame = PrematchReading.resolve(prematch: prematch, opening: opening)
        let pregamePair = pregame.flatMap { reading in
            DrawPricedWinner.printablePair(
                away: reading.awayProbability,
                home: reading.homeProbability,
                sport: sportKey
            )
        }

        if let drawLabel = outcome.drawLabel {
            let markText: String?
            if let pregame, let pair = pregamePair, let away = pair.away {
                let percents = pregame.percents
                markText = "\(pregame.captionWord) \(formatProbability(away, renderedPercent: percents[0])) – \(formatProbability(pair.home, renderedPercent: percents[1]))"
            } else {
                markText = nil
            }
            return SettledBadge(
                winnerLabel: drawLabel,
                systemImage: nil,
                pregameMarkText: markText,
                isUpset: false
            )
        }

        guard outcome == .home || outcome == .away else {
            return SettledBadge(
                winnerLabel: "Final",
                systemImage: nil,
                pregameMarkText: nil,
                isUpset: false
            )
        }

        let homeWon = outcome == .home
        let duel = TeamShortName.shortPair(away: awayTeam, home: homeTeam, sportKey: sportKey)
        let winnerName = homeWon ? duel.home : duel.away

        var pregameMarkText: String?
        var isUpset = false
        if let pregame, let pair = pregamePair {
            let winnerProb: Double? = homeWon ? pair.home : pair.away
            if let prob = winnerProb {
                let pct = Int((prob * 100).rounded())
                isUpset = pct < 45
                let formatted = formatProbability(
                    prob,
                    renderedPercent: homeWon ? pregame.percents[1] : pregame.percents[0]
                )
                let word = pregame.captionWord == "Opened" ? "opened" : "pregame"
                pregameMarkText = isUpset
                    ? "Upset · \(formatted) \(word)"
                    : "\(formatted) \(word)"
            }
        }

        return SettledBadge(
            winnerLabel: "\(winnerName) Won",
            systemImage: "checkmark",
            pregameMarkText: pregameMarkText,
            isUpset: isUpset
        )
    }

    /// Formats the source attribution line for `EventAtlasDetailsSheet11666`.
    /// Never calls a single venue `"Blended"`; `"Blended"` is printed only when
    /// `source == "blended"` or `sourceCount > 1`.
    static func sourceAttribution(
        source: String?,
        sourceCount: Int?,
        winProbSources: [String: WinProbSource]? = nil
    ) -> String? {
        let entries = WinProbSourceCatalog.entries(from: winProbSources)
            .filter { $0.key != "final_result" }
        let effectiveCount = sourceCount ?? (entries.isEmpty ? nil : entries.count)

        if let count = effectiveCount, count > 1 {
            let names = entries.map(\.label)
            if !names.isEmpty {
                return "Blended (\(names.joined(separator: ", ")))"
            }
            return "Blended (\(count) sources)"
        }

        if let singleEntry = entries.first, (effectiveCount == nil || effectiveCount == 1) {
            return singleEntry.label
        }

        guard let raw = source?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
            return nil
        }
        let lowered = raw.lowercased()
        if lowered == "blended" || lowered == "blend" {
            if let count = effectiveCount, count == 1, let singleEntry = entries.first {
                return singleEntry.label
            }
            return "Blended"
        }
        if let marketLabel = SourceLabels.label(for: lowered) {
            return marketLabel
        }
        if let bookLabel = SourceLabels.sportsbookName(for: lowered) {
            return bookLabel
        }
        switch lowered {
        case "betting", "sportsbooks":
            return "Sportsbooks"
        case "espn":
            return "ESPN"
        case "stat_model":
            return "Model"
        case "mlb", "mlb_stats":
            return "MLB"
        default:
            return nil
        }
    }
}

/// Model for the shared native Atlas details sheet (`EventAtlasDetailsSheet11666`),
/// used by the E1 headline `(i)` control and E3–E6c story cards.
nonisolated struct EventAtlasDetailsSheetModel11666: Identifiable, Equatable, Sendable {
    let id: String
    let outcomeTitle: String
    let marketTitle: String
    let primaryReadingLabel: String
    let primaryReadingValue: String
    let pregameBaseline: String?
    let observedAtText: String?
    let statusSummary: String?
    let sourceLabel: String?

    /// Builds the headline details sheet model from an `EventDetail` payload.
    static func fromHeadline(
        event: EventDetail,
        phase: EventHeadlinePhase9483?,
        observedAt: Date?,
        liveStatus: LiveUpdateStatus
    ) -> EventAtlasDetailsSheetModel11666 {
        let isFinished = EventState.isFinished(event.status)
        let duel = TeamShortName.shortPair(
            away: event.awayTeam,
            home: event.homeTeam,
            sportKey: event.sport
        )
        let pregameText = EventHeadlinePhase9483.baselineText(
            prematch: event.prematchOdds,
            opening: event.openingOdds,
            sport: event.sport,
            awayTeam: event.awayTeam,
            homeTeam: event.homeTeam
        )

        let primaryLabel: String
        let primaryValue: String
        if isFinished {
            primaryLabel = "Result"
            let badge = EventAtlasHeadline11666.settledBadge(
                outcome: EventOutcome.resolve(
                    status: event.status,
                    homeScore: event.homeScore,
                    awayScore: event.awayScore,
                    servedResult: event.heroSettledResult
                ),
                awayTeam: event.awayTeam,
                homeTeam: event.homeTeam,
                sportKey: event.sport,
                prematch: event.prematchOdds,
                opening: event.openingOdds
            )
            primaryValue = badge.winnerLabel
        } else if let odds = event.currentOdds,
                  let pair = DrawPricedWinner.printablePair(
                    away: odds.awayProbability,
                    home: odds.homeProbability,
                    sport: event.sport
                  ) {
            primaryLabel = phase?.label ?? "Win chance"
            if let away = pair.away {
                let printed = EventHeadlineTenths10090.pair(home: pair.home, away: away)
                primaryValue = "\(duel.away) \(printed.away ?? "") · \(duel.home) \(printed.home)"
            } else {
                primaryValue = "\(duel.home) \(formatProbability(pair.home))"
            }
        } else {
            primaryLabel = phase?.label ?? "Win chance"
            primaryValue = "No recent probability"
        }

        let observedText = observedAt.map {
            $0.formatted(date: .abbreviated, time: .shortened)
        }

        let sourceLabel = EventAtlasHeadline11666.sourceAttribution(
            source: event.heroProbabilitySource,
            sourceCount: nil,
            winProbSources: event.winProbabilitySources
        )

        return EventAtlasDetailsSheetModel11666(
            id: "headline-\(event.id)",
            outcomeTitle: "\(event.awayTeam) at \(event.homeTeam)",
            marketTitle: "Game winner",
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: liveStatus == .hidden ? nil : liveStatus.title,
            sourceLabel: sourceLabel
        )
    }
}

/// Hollow circle `○` pregame baseline badge used by the E1 Atlas headline.
struct EventAtlasPregameMarkView11666: View {
    let text: String

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .strokeBorder(Color.secondary, lineWidth: 1.25)
                .frame(width: 7, height: 7)
                .accessibilityHidden(true)
            Text(text)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("atlas-pregame-mark-11666")
    }
}

/// Self-contained E1 Atlas headline row mounted in `EventDetailView.heroSection`
/// when `ReleaseSurfaces.isEventPageAtlasEnabled()` is true.
struct EventAtlasHeadlineControlRow11666: View {
    let event: EventDetail
    let observedAt: Date?
    let liveStatus: LiveUpdateStatus

    @State private var activeSheet: EventAtlasDetailsSheetModel11666?

    var body: some View {
        let isFinished = EventState.isFinished(event.status)
        let isOpening = event.currentOdds.map {
            OpeningLineHero.resolve($0, for: event).isOpeningLine
        } ?? false
        let phase = EventHeadlinePhase9483.resolve(
            status: event.status,
            commenceTime: event.commenceTime?.asDate,
            isOpeningLine: isOpening,
            observedAt: observedAt,
            deliveryInterrupted: liveStatus == .interrupted
        )
        let settledBadge: EventAtlasHeadline11666.SettledBadge? = isFinished
            ? EventAtlasHeadline11666.settledBadge(
                outcome: EventOutcome.resolve(
                    status: event.status,
                    homeScore: event.homeScore,
                    awayScore: event.awayScore,
                    servedResult: event.heroSettledResult
                ),
                awayTeam: event.awayTeam,
                homeTeam: event.homeTeam,
                sportKey: event.sport,
                prematch: event.prematchOdds,
                opening: event.openingOdds
            )
            : nil

        HStack(spacing: 8) {
            if let badge = settledBadge {
                if let icon = badge.systemImage {
                    Label(badge.winnerLabel, systemImage: icon)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.primary)
                } else {
                    Text(badge.winnerLabel)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.primary)
                }
                if let markText = badge.pregameMarkText {
                    EventAtlasPregameMarkView11666(text: markText)
                }
            } else if let phase {
                Text(phase.label)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                if event.status == "live",
                   let baseline = EventHeadlinePhase9483.baselineText(
                    prematch: event.prematchOdds,
                    opening: event.openingOdds,
                    sport: event.sport,
                    awayTeam: event.awayTeam,
                    homeTeam: event.homeTeam
                   ) {
                    EventAtlasPregameMarkView11666(text: baseline)
                }
            }
            Spacer(minLength: 0)
            Button {
                activeSheet = EventAtlasDetailsSheetModel11666.fromHeadline(
                    event: event,
                    phase: phase,
                    observedAt: observedAt,
                    liveStatus: liveStatus
                )
            } label: {
                Image(systemName: "info.circle")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .frame(minWidth: 44, minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Market details")
            .accessibilityIdentifier("event-atlas-headline-details-button-11666")
        }
        .accessibilityIdentifier("event-atlas-headline-row-11666")
        .sheet(item: $activeSheet) { model in
            EventAtlasDetailsSheet11666(model: model)
        }
    }
}

/// Shared native Atlas details sheet (`#11666` E1/E3).
struct EventAtlasDetailsSheet11666: View {
    let model: EventAtlasDetailsSheetModel11666
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(model.outcomeTitle)
                            .font(.headline)
                            .foregroundStyle(.primary)
                        Text(model.marketTitle)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }

                Section("Reading") {
                    LabeledContent(model.primaryReadingLabel, value: model.primaryReadingValue)
                    if let pregame = model.pregameBaseline {
                        HStack {
                            Text("Pregame baseline")
                            Spacer()
                            EventAtlasPregameMarkView11666(text: pregame)
                        }
                    }
                    if let observed = model.observedAtText {
                        LabeledContent("Observed", value: observed)
                    }
                }

                if model.sourceLabel != nil || model.statusSummary != nil {
                    Section("Source & Delivery") {
                        if let source = model.sourceLabel {
                            LabeledContent("Source", value: source)
                        }
                        if let status = model.statusSummary {
                            LabeledContent("Delivery", value: status)
                        }
                    }
                }
            }
            .navigationTitle("Market details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
        .accessibilityIdentifier("event-atlas-details-sheet-11666")
    }
}
