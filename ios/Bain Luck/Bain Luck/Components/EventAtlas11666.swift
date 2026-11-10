import SwiftUI

/// #11666 (Step E1) — Native event-page atlas headline and shared details sheet,
/// matching the shipped web E1 contract (#11974 / PR #12113) behind
/// `ReleaseSurfaces.isEventPageAtlasEnabled()`.
///
/// Key guarantees:
/// 1. Settled games show `✓ Won` (`✗ Lost` on paired side, `Draw` on ties) with
///    the hollow pregame mark `○` (`"Upset · X% pregame"` when the winner was
///    priced below the side it beat on the same reading via
///    `PrematchReading.winnerWasUnderdog(homeWon:awayWon:pricesADraw:)`, #9490;
///    otherwise `"X% pregame"`).
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

    /// Resolves the settled `EventOutcome` for the Atlas headline and details sheet.
    ///
    /// When `isFinished` is true (`status` is `completed`/`closed`), resolves via
    /// `EventOutcome.resolve` (served result first, then final scoreboard).
    /// When `isFinished` is false (`venueSettledVerdict` is true while `status` is
    /// not yet `completed`/`closed`), uses only `heroSettledResult` (`homeScore: nil`,
    /// `awayScore: nil`) so a venue-settled live row without `heroSettledResult`
    /// never guesses a winner from mid-game scores.
    static func settledOutcome(for event: EventDetail, isFinished: Bool) -> EventOutcome {
        if isFinished {
            return EventOutcome.resolve(
                status: event.status,
                homeScore: event.homeScore,
                awayScore: event.awayScore,
                servedResult: event.heroSettledResult
            )
        }
        return EventOutcome.resolve(
            status: event.heroSettledResult != nil ? "completed" : event.status,
            homeScore: nil,
            awayScore: nil,
            servedResult: event.heroSettledResult
        )
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
        let awayWon = outcome == .away
        let pricesADraw = DrawPricedWinner.sportPricesADraw(sportKey)
        let duel = TeamShortName.shortPair(away: awayTeam, home: homeTeam, sportKey: sportKey)
        let winnerName = homeWon ? duel.home : duel.away

        var pregameMarkText: String?
        var isUpset = false
        if let pregame {
            let winnerProb: Double? = homeWon
                ? pregame.homeProbability
                : ((pricesADraw && pregame.awayIsComplement) ? nil : pregame.awayProbability)
            if let prob = winnerProb {
                // #9490 — against the side it beat on the same reading, not a
                // fixed cut: on a three-way board 39.5% can be the favourite.
                isUpset = pregame.winnerWasUnderdog(
                    homeWon: homeWon,
                    awayWon: awayWon,
                    pricesADraw: pricesADraw
                )
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

    /// Resolves the live/scheduled headline phase label against the supplied
    /// clock (`now`), honouring the 30-minute staleness bound and delivery state.
    static func resolvePhase(
        event: EventDetail,
        observedAt: Date?,
        liveStatus: LiveUpdateStatus,
        now: Date = Date()
    ) -> EventHeadlinePhase9483? {
        let isOpening = event.currentOdds.map {
            OpeningLineHero.resolve($0, for: event).isOpeningLine
        } ?? false
        return EventHeadlinePhase9483.resolve(
            status: event.status,
            commenceTime: event.commenceTime?.asDate,
            isOpeningLine: isOpening,
            observedAt: observedAt,
            deliveryInterrupted: liveStatus == .interrupted,
            now: now
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
    var statusLabel: String = "Context"
    let sourceLabel: String?
    var originalSections: [MLBOriginal11284.Section] = []

    /// Builds the headline details sheet model from an `EventDetail` payload.
    static func fromHeadline(
        event: EventDetail,
        phase: EventHeadlinePhase9483?,
        observedAt: Date?,
        liveStatus: LiveUpdateStatus,
        now: Date? = nil
    ) -> EventAtlasDetailsSheetModel11666 {
        let effectiveNow = now ?? observedAt ?? Date()
        let isFinished = EventState.isFinished(event.status)
        let venueSettledVerdict = EventState.showsVenueSettledVerdict(
            event.status,
            venueSettled: event.venueSettled,
            commenceTime: event.commenceTime?.asDate,
            now: effectiveNow
        )
        let isSettled = isFinished || venueSettledVerdict
        let isOpening = event.currentOdds.map {
            OpeningLineHero.resolve($0, for: event).isOpeningLine
        } ?? false
        let duel = TeamShortName.shortPair(
            away: event.awayTeam,
            home: event.homeTeam,
            sportKey: event.sport
        )
        let pregameText = isOpening
            ? nil
            : EventHeadlinePhase9483.baselineText(
                prematch: event.prematchOdds,
                opening: event.openingOdds,
                sport: event.sport,
                awayTeam: event.awayTeam,
                homeTeam: event.homeTeam
            )

        let primaryLabel: String
        let primaryValue: String
        if isSettled {
            primaryLabel = "Result"
            let badge = EventAtlasHeadline11666.settledBadge(
                outcome: EventAtlasHeadline11666.settledOutcome(for: event, isFinished: isFinished),
                awayTeam: event.awayTeam,
                homeTeam: event.homeTeam,
                sportKey: event.sport,
                prematch: event.prematchOdds,
                opening: event.openingOdds
            )
            primaryValue = badge.winnerLabel
        } else if let odds = event.currentOdds,
                  case let shown = OpeningLineHero.resolve(odds, for: event),
                  let pair = DrawPricedWinner.printablePair(
                    away: shown.awayProbability,
                    home: shown.homeProbability,
                    sport: event.sport
                  ) {
            primaryLabel = shown.isOpeningLine ? OpeningLineHero.caption : (phase?.label ?? "Win chance")
            if let away = pair.away {
                if shown.isOpeningLine {
                    let openDuel = duelPercents(
                        away: away,
                        home: pair.home,
                        servedAway: shown.awayRenderedPercent,
                        servedHome: shown.homeRenderedPercent
                    )
                    primaryValue = "\(duel.away) \(formatProbability(away, renderedPercent: openDuel[0])) · \(duel.home) \(formatProbability(pair.home, renderedPercent: openDuel[1]))"
                } else {
                    let printed = EventAtlasLivePath11666.tenthsPair(home: pair.home, away: away)
                    primaryValue = "\(duel.away) \(printed.away ?? "") · \(duel.home) \(printed.home)"
                }
            } else {
                if shown.isOpeningLine {
                    primaryValue = "\(duel.home) \(formatProbability(pair.home))"
                } else {
                    let printed = EventAtlasLivePath11666.tenthsPair(home: pair.home, away: nil)
                    primaryValue = "\(duel.home) \(printed.home)"
                }
            }
        } else {
            primaryLabel = phase?.label ?? "Win chance"
            primaryValue = "No recent probability"
        }

        let observedText = observedAt.map {
            EventAtlasChartMarks11666.formatExactTimestampPT($0)
        }

        let sourceLabel: String? = {
            if isSettled {
                let rawBaselineSource = event.prematchOdds?.source ?? event.heroProbabilitySource
                let trimmed = rawBaselineSource?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                let effectiveSingleSource: String?
                if let trimmed, !trimmed.isEmpty, trimmed != "blend", trimmed != "blended", trimmed != "final_result" {
                    effectiveSingleSource = trimmed
                } else if event.prematchOdds != nil || event.openingOdds != nil {
                    effectiveSingleSource = "sportsbooks"
                } else {
                    effectiveSingleSource = nil
                }
                return EventAtlasHeadline11666.sourceAttribution(
                    source: effectiveSingleSource,
                    sourceCount: effectiveSingleSource != nil ? 1 : nil,
                    winProbSources: nil
                )
            }
            return EventAtlasHeadline11666.sourceAttribution(
                source: event.heroProbabilitySource,
                sourceCount: nil,
                winProbSources: event.winProbabilitySources
            )
        }()

        return EventAtlasDetailsSheetModel11666(
            id: "headline-\(event.id)",
            outcomeTitle: "\(event.awayTeam) at \(event.homeTeam)",
            marketTitle: "Game winner",
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: EventAtlasStates11666.connectionStatusLabel(for: liveStatus),
            statusLabel: "Delivery",
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

/// Self-contained E1/E5 Atlas headline row mounted in `EventDetailView.heroSection`
/// when `ReleaseSurfaces.isEventPageAtlasEnabled()` is true.
struct EventAtlasHeadlineControlRow11666: View {
    let event: EventDetail
    let observedAt: Date?
    var confirmedAtShown: Date? = nil
    var preview: BlendPreviewState? = nil
    let liveStatus: LiveUpdateStatus
    var ekgTracker: EkgTracker = .empty
    var asOf: Date? = nil
    /// When `true` (mounted inside `EventDetailView.heroSection`), omits repeating
    /// elements the hero above already renders (phase label, live tenths pair,
    /// live pregame mark via `EventHeadlinePhaseLabel9483`, `heroEkg`, and the
    /// active-game `probabilityDetails`/`nflPairedDetails` control), keeping only
    /// the settled hollow pregame mark (`Upset · X% pregame` / `X% pregame`) and
    /// the single `(i)` Market details button where the hero has none.
    var embeddedInHero: Bool = false

    @State private var activeSheet: EventAtlasDetailsSheetModel11666?

    static func tenthsSummary(
        for reading: EventAtlasLivePath11666.OverlaidHeadlineReading,
        event: EventDetail
    ) -> String {
        let duel = TeamShortName.shortPair(
            away: event.awayTeam,
            home: event.homeTeam,
            sportKey: event.sport
        )
        if let awayText = reading.awayTenthsText {
            return "\(duel.away) \(awayText) · \(duel.home) \(reading.homeTenthsText)"
        }
        return "\(duel.home) \(reading.homeTenthsText)"
    }

    /// Computes the live tenths overlay for the headline row, returning `nil`
    /// when the event is finished, venue-settled (`EventState.showsVenueSettledVerdict`),
    /// or displaying an opening line (`OpeningLineHero.isOpeningLine`).
    static func rowOverlaidReading(
        event: EventDetail,
        preview: BlendPreviewState?,
        now: Date
    ) -> EventAtlasLivePath11666.OverlaidHeadlineReading? {
        let isFinished = EventState.isFinished(event.status)
        let venueSettledVerdict = EventState.showsVenueSettledVerdict(
            event.status,
            venueSettled: event.venueSettled,
            commenceTime: event.commenceTime?.asDate,
            now: now
        )
        let isOpening = event.currentOdds.map {
            OpeningLineHero.resolve($0, for: event).isOpeningLine
        } ?? false
        if isFinished || venueSettledVerdict || isOpening {
            return nil
        }
        return EventAtlasLivePath11666.overlaidHeadlineReading(
            event: event,
            preview: preview,
            now: now.timeIntervalSince1970
        )
    }

    /// Decides which elements of `EventAtlasHeadlineControlRow11666` render when
    /// `embeddedInHero == true` so the hero never duplicates its phase label,
    /// pregame baseline, EKG dot, or `(i)` details button.
    static func embeddedHeroVisibility(
        event: EventDetail,
        now: Date
    ) -> (showsSettledWinner: Bool, showsSettledMark: Bool, showsPhaseAndLiveMark: Bool, showsEkg: Bool, showsDetailsButton: Bool) {
        let isFinished = EventState.isFinished(event.status)
        let venueSettledVerdict = EventState.showsVenueSettledVerdict(
            event.status,
            venueSettled: event.venueSettled,
            commenceTime: event.commenceTime?.asDate,
            now: now
        )
        let isSettled = isFinished || venueSettledVerdict
        let isOpening = event.currentOdds.map {
            OpeningLineHero.resolve($0, for: event).isOpeningLine
        } ?? false
        if isSettled {
            // The hero above already prints `<Winner> Win` / `Draw` / `Final`;
            // keep the hollow pregame mark (`Upset · X% pregame` / `X% pregame`)
            // and the single `(i)` Market details button.
            return (
                showsSettledWinner: false,
                showsSettledMark: true,
                showsPhaseAndLiveMark: false,
                showsEkg: false,
                showsDetailsButton: true
            )
        }
        // On an active/scheduled game, `EventDetailView` already renders `headlinePhaseLabel`
        // (including `EventAtlasPregameMarkView11666` on live games), `heroEkg`, and
        // `probabilityDetails` / `nflPairedDetails` — except on an opening-line hero,
        // which has no `(i)` button of its own.
        return (
            showsSettledWinner: false,
            showsSettledMark: false,
            showsPhaseAndLiveMark: false,
            showsEkg: false,
            showsDetailsButton: isOpening
        )
    }

    var body: some View {
        TimelineView(.periodic(from: .now, by: 15)) { context in
            rowContent(now: asOf ?? context.date)
        }
    }

    @ViewBuilder
    private func rowContent(now: Date) -> some View {
        let isFinished = EventState.isFinished(event.status)
        let venueSettledVerdict = EventState.showsVenueSettledVerdict(
            event.status,
            venueSettled: event.venueSettled,
            commenceTime: event.commenceTime?.asDate,
            now: now
        )
        let isSettled = isFinished || venueSettledVerdict
        let isOpening = event.currentOdds.map {
            OpeningLineHero.resolve($0, for: event).isOpeningLine
        } ?? false
        let visibility = embeddedInHero
            ? Self.embeddedHeroVisibility(event: event, now: now)
            : (
                showsSettledWinner: true,
                showsSettledMark: true,
                showsPhaseAndLiveMark: true,
                showsEkg: EventAtlasLivePath11666.ekgDraws(
                    eventStatus: event.status,
                    finished: isFinished,
                    venueSettledVerdict: venueSettledVerdict,
                    isOpeningLine: isOpening
                ),
                showsDetailsButton: true
            )
        let overlaidReading = Self.rowOverlaidReading(
            event: event,
            preview: preview,
            now: now
        )
        let effectiveObservedAt = EventAtlasLivePath11666.resolveHeadlineObservedAt(
            EventAtlasLivePath11666.HeadlineObservedAtInput(
                acceptedPriceClock: overlaidReading?.observedAt ?? observedAt,
                confirmedAtShown: confirmedAtShown,
                freshestSourceStamp: EventAtlasLivePath11666.freshestSourceTimestamp(in: event.winProbabilitySources),
                currentOddsCapturedAt: event.currentOdds?.capturedAt?.asDate
            )
        )
        let phase = isSettled
            ? nil
            : EventHeadlinePhase9483.resolve(
                status: event.status,
                commenceTime: event.commenceTime?.asDate,
                isOpeningLine: isOpening,
                observedAt: effectiveObservedAt,
                deliveryInterrupted: liveStatus == .interrupted,
                now: now
            )
        let settledBadge: EventAtlasHeadline11666.SettledBadge? = isSettled
            ? EventAtlasHeadline11666.settledBadge(
                outcome: EventAtlasHeadline11666.settledOutcome(for: event, isFinished: isFinished),
                awayTeam: event.awayTeam,
                homeTeam: event.homeTeam,
                sportKey: event.sport,
                prematch: event.prematchOdds,
                opening: event.openingOdds
            )
            : nil

        let hasAnyVisibleElement = (settledBadge != nil && (visibility.showsSettledWinner || (visibility.showsSettledMark && settledBadge?.pregameMarkText != nil)))
            || (phase != nil && visibility.showsPhaseAndLiveMark)
            || visibility.showsEkg
            || visibility.showsDetailsButton

        if hasAnyVisibleElement {
            HStack(spacing: 8) {
                if let badge = settledBadge {
                    if visibility.showsSettledWinner {
                        if let icon = badge.systemImage {
                            Label(badge.winnerLabel, systemImage: icon)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.primary)
                        } else {
                            Text(badge.winnerLabel)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.primary)
                        }
                    }
                    if visibility.showsSettledMark, let markText = badge.pregameMarkText {
                        EventAtlasPregameMarkView11666(text: markText)
                    }
                } else if let phase, visibility.showsPhaseAndLiveMark {
                    Text(phase.label)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    if let reading = overlaidReading {
                        Text(Self.tenthsSummary(for: reading, event: event))
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                            .accessibilityIdentifier("atlas-headline-tenths-11666")
                    }
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
                if visibility.showsEkg {
                    let presentation = EkgHeartbeat.present(ekgTracker, status: liveStatus, now: now)
                    Circle()
                        .fill(EkgHeartbeatView.tone(presentation.mode))
                        .frame(width: 6, height: 6)
                        .accessibilityLabel(presentation.label)
                        .accessibilityIdentifier("atlas-ekg-indicator-11666")
                }
                if visibility.showsDetailsButton {
                    Button {
                        activeSheet = EventAtlasDetailsSheetModel11666.fromHeadline(
                            event: event,
                            phase: phase,
                            observedAt: effectiveObservedAt,
                            liveStatus: liveStatus,
                            now: now
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
            }
            .accessibilityIdentifier("event-atlas-headline-row-11666")
            .sheet(item: $activeSheet) { model in
                EventAtlasDetailsSheet11666(model: model)
            }
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
                    Section(model.statusLabel == "Delivery" ? "Source & Delivery" : "Source & Context") {
                        if let source = model.sourceLabel {
                            LabeledContent("Source", value: source)
                        }
                        if let status = model.statusSummary {
                            LabeledContent(model.statusLabel, value: status)
                        }
                    }
                }

                ForEach(Array(model.originalSections.enumerated()), id: \.offset) { _, section in
                    if !section.fields.isEmpty {
                        Section {
                            ForEach(Array(section.fields.enumerated()), id: \.offset) { _, field in
                                LabeledContent(field.label) {
                                    Text(field.value)
                                        .multilineTextAlignment(.trailing)
                                        .textSelection(.enabled)
                                }
                            }
                        } header: {
                            if let title = section.title {
                                Text(title)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Market details")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
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
