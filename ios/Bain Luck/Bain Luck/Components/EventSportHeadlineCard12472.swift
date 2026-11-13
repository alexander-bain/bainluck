import SwiftUI

/// #12472 — Compact white event-page headline card for the two Sheet 1 looks
/// Alex rated "amazing" (NFL before a game, NBA during a game).
struct EventSportHeadlineCard12472: View {
    let model: EventSportHeadlines12472.Model
    let colors: (away: Color, home: Color)
    let ekgTracker: EkgTracker
    let liveUpdateStatus: LiveUpdateStatus
    let displayAsOf: Date?
    let updateStream: LiveUpdateStream
    @Binding var showUpdateStream: Bool
    @Binding var showProbabilityDetails: Bool
    let priceStreamingEligible: Bool
    let lastReceivedAt: Date?
    let confirmedAt: Date?
    let revealForecast: LivePregameComparison11296.Headline?

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .title2) private var winChanceSize: CGFloat = 25
    @ScaledMetric(relativeTo: .title3) private var liveTenthsChanceSize: CGFloat = 22
    @ScaledMetric(relativeTo: .body) private var liveScoreSize: CGFloat = 17

    private var stacksRowsVertically: Bool {
        dynamicTypeSize.isAccessibilitySize
    }

    private static func livePregameMetaText(
        model: EventSportHeadlines12472.Model,
        now: Date
    ) -> String {
        var parts: [String] = ["NFL"]
        if let timeText = EventSportHeadlines12472.pregameStartText(
            commenceTime: model.commenceTime,
            startIsTbd: model.startIsTbd,
            now: now
        ) {
            parts.append(timeText)
        }
        if let broadcast = model.broadcast,
           !EventState.isFinished(model.eventStatus),
           !EventState.isSuspendedAndStarted(
               model.eventStatus,
               commenceTime: model.commenceTime?.asDate,
               now: now
           ) {
            parts.append(broadcast)
        }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            topBar
            VStack(alignment: .leading, spacing: 8) {
                teamRow(model.away, color: colors.away, isAway: true)
                teamRow(model.home, color: colors.home, isAway: false)
            }
            bottomProbabilityBar
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        )
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(
            model.kind == .nflBeforeGame
                ? "event-headline-12472-nfl-before"
                : "event-headline-12472-nba-during"
        )
    }

    // MARK: - Top Bar

    private var topBar: some View {
        let layout = stacksRowsVertically
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 6))
            : AnyLayout(HStackLayout(alignment: .center, spacing: 8))
        return layout {
            leadingMeta
            if !stacksRowsVertically {
                Spacer(minLength: 6)
            }
            trailingControls
        }
    }

    @ViewBuilder
    private var leadingMeta: some View {
        switch model.kind {
        case .nflBeforeGame:
            TimelineView(.periodic(from: .now, by: 60)) { tick in
                let text = displayAsOf != nil
                    ? model.plainMetaText
                    : Self.livePregameMetaText(model: model, now: tick.date)
                if let text {
                    Text(text)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        case .nbaDuringGame:
            HStack(spacing: 8) {
                if let liveBadge = model.liveBadgeText {
                    HStack(spacing: 5) {
                        Circle()
                            .fill(Color.white)
                            .frame(width: 6, height: 6)
                        Text(liveBadge)
                            .font(.caption2.weight(.bold).monospacedDigit())
                            .foregroundStyle(Color.white)
                            .lineLimit(1)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3.5)
                    .background(Capsule().fill(Color.red))
                    .fixedSize(horizontal: !stacksRowsVertically, vertical: true)
                }
                if let league = model.leagueLabel {
                    Text(league)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondaryReadable)
                }
            }
        }
    }

    private var trailingControls: some View {
        HStack(spacing: 2) {
            ekgButton
            if liveUpdateStatus == .interrupted {
                Button { showProbabilityDetails.toggle() } label: {
                    CompactEventPriceStatusView(
                        status: liveUpdateStatus,
                        sequence: 0,
                        receivedAt: lastReceivedAt,
                        isDisclosure: true,
                        statusInDetails: true,
                        ekgDrawn: true
                    )
                }
                .buttonStyle(.plain)
            }
            if let markButton = SourceMarkButton(
                model.sourceMark,
                number: model.home.rawProbability,
                numberSize: 20
            ) {
                markButton
                    .padding(.vertical, -10)
            }
        }
        .popover(isPresented: $showProbabilityDetails, arrowEdge: .top) {
            FreshnessRevealView(
                status: liveUpdateStatus,
                lastReceivedAt: lastReceivedAt,
                confirmedAt: confirmedAt,
                confidenceTier: model.confidenceTier,
                forecast: revealForecast
            )
            .frame(idealWidth: 300, maxWidth: 300)
            #if os(iOS)
            .presentationCompactAdaptation(.popover)
            #endif
        }
    }

    private var ekgButton: some View {
        Button { showUpdateStream = true } label: {
            EkgHeartbeatView(
                tracker: ekgTracker,
                status: liveUpdateStatus,
                asOf: displayAsOf
            )
            .frame(minWidth: 40, minHeight: 44)
            .contentShape(Rectangle())
            .padding(.vertical, -12)
        }
        .buttonStyle(.plain)
        .accessibilityHint("Shows the venue updates feeding this number")
        .accessibilityIdentifier("ekg-heartbeat-button")
        .popover(isPresented: $showUpdateStream, arrowEdge: .top) {
            LiveUpdateStreamView(
                stream: updateStream,
                homeTeam: model.home.shortName,
                onDetails: {
                    showUpdateStream = false
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                        showProbabilityDetails = true
                    }
                }
            )
            .frame(idealWidth: 280, maxWidth: 300)
            #if os(iOS)
            .presentationCompactAdaptation(.popover)
            #endif
        }
    }

    // MARK: - Team Rows

    @ViewBuilder
    private func teamRow(
        _ side: EventSportHeadlines12472.TeamRowModel,
        color: Color,
        isAway: Bool
    ) -> some View {
        if stacksRowsVertically {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    crest(side, color: color)
                    teamIdentityStack(side, color: color)
                }
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        if let score = side.liveScore {
                            scoreText(score)
                        }
                        if let pregame = side.pregameChanceText {
                            pregameLabel(pregame)
                                .fixedSize(horizontal: true, vertical: false)
                        }
                        Spacer(minLength: 4)
                        chanceText(side.winChanceText, color: color)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    HStack(alignment: .center, spacing: 8) {
                        if let score = side.liveScore {
                            scoreText(score)
                        }
                        Spacer(minLength: 4)
                        VStack(alignment: .trailing, spacing: 2) {
                            chanceText(side.winChanceText, color: color)
                                .fixedSize(horizontal: true, vertical: false)
                            if let pregame = side.pregameChanceText {
                                pregameLabel(pregame)
                                    .fixedSize(horizontal: true, vertical: false)
                            }
                        }
                    }
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
        } else {
            ViewThatFits(in: .horizontal) {
                // Primary layout: small grey "49% pregame" sits inline beside the win chance.
                HStack(alignment: .center, spacing: 6) {
                    crest(side, color: color)
                    teamIdentityStack(side, color: color)
                    Spacer(minLength: 4)
                    if let score = side.liveScore {
                        scoreText(score)
                    }
                    if let pregame = side.pregameChanceText {
                        pregameLabel(pregame)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    chanceText(side.winChanceText, color: color, hasInlinePregame: side.pregameChanceText != nil)
                        .fixedSize(horizontal: true, vertical: false)
                }
                // Tight-width fallback: keep "49% pregame" tucked right beneath its own win chance, never truncated.
                HStack(alignment: .center, spacing: 6) {
                    crest(side, color: color)
                    teamIdentityStack(side, color: color)
                    Spacer(minLength: 4)
                    if let score = side.liveScore {
                        scoreText(score)
                    }
                    VStack(alignment: .trailing, spacing: 1) {
                        chanceText(side.winChanceText, color: color, hasInlinePregame: side.pregameChanceText != nil)
                            .fixedSize(horizontal: true, vertical: false)
                        if let pregame = side.pregameChanceText {
                            pregameLabel(pregame)
                                .fixedSize(horizontal: true, vertical: false)
                        }
                    }
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
        }
    }

    private func crest(_ side: EventSportHeadlines12472.TeamRowModel, color: Color) -> some View {
        TeamLogoView(
            url: side.logoURL,
            teamName: side.fullName,
            color: color,
            size: 32,
            sportKey: model.sportKey,
            opponentName: side.opponentFullName
        )
    }

    private func teamIdentityStack(
        _ side: EventSportHeadlines12472.TeamRowModel,
        color: Color
    ) -> some View {
        VStack(alignment: .leading, spacing: 1.5) {
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Text(side.shortName)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(Color.primary)
                    .fixedSize(horizontal: false, vertical: true)
                if let record = side.record {
                    Text(record)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: true, vertical: false)
                }
            }
            if let projected = side.projectedText {
                Text(projected)
                    .font(.caption2.weight(.semibold).monospacedDigit())
                    .foregroundStyle(color)
                    .fixedSize(horizontal: true, vertical: false)
            }
        }
    }

    private func scoreText(_ score: Int) -> some View {
        Text("\(score)")
            .font(.system(size: min(liveScoreSize, 24), weight: .bold, design: .rounded).monospacedDigit())
            .foregroundStyle(Color.primary)
            .fixedSize(horizontal: true, vertical: false)
    }

    private func pregameLabel(_ text: String) -> some View {
        Text(text)
            .font(.caption2.monospacedDigit())
            .foregroundStyle(DS.textSecondaryReadable)
    }

    private func chanceText(_ text: String, color: Color, hasInlinePregame: Bool = false) -> some View {
        let base = hasInlinePregame ? liveTenthsChanceSize : winChanceSize
        return Text(text)
            .font(.system(size: min(base, 32), weight: .black, design: .rounded).monospacedDigit())
            .foregroundStyle(color)
    }

    // MARK: - Segmented Bar + Pregame Notch

    private var bottomProbabilityBar: some View {
        GeometryReader { geo in
            let width = max(geo.size.width, 1)
            let total = max(model.away.rawProbability + model.home.rawProbability, 0.0001)
            let awayShare = min(max(model.away.rawProbability / total, 0), 1)
            ZStack(alignment: .leading) {
                HStack(spacing: 0) {
                    Rectangle()
                        .fill(colors.away)
                        .frame(width: max(width * awayShare, 2))
                    Rectangle()
                        .fill(colors.home)
                        .frame(maxWidth: .infinity)
                }
                .frame(height: 6)
                .clipShape(Capsule())

                if let marker = model.pregameAwayMarker, marker > 0, marker < 1 {
                    let markerX = min(max(width * marker, 2), max(width - 2, 2))
                    RoundedRectangle(cornerRadius: 1)
                        .fill(Color.primary.opacity(0.85))
                        .frame(width: 2, height: 10)
                        .offset(x: markerX - 1)
                        .accessibilityHidden(true)
                }
            }
        }
        .frame(height: 10)
    }
}
