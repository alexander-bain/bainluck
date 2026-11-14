import SwiftUI

/// #12472 — Compact white event-page headline card for the Sheets 1–3 looks
/// Alex rated "amazing" (`NFL before`, `NBA during`, `soccer before`,
/// `soccer after`, `NHL during`).
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
    @ScaledMetric(relativeTo: .title3) private var pregameProjectedSize: CGFloat = 20
    @ScaledMetric(relativeTo: .body) private var liveScoreSize: CGFloat = 18
    @ScaledMetric(relativeTo: .subheadline) private var livePregameSize: CGFloat = 15
    @ScaledMetric(relativeTo: .title3) private var soccerBoxChanceSize: CGFloat = 21
    @ScaledMetric(relativeTo: .headline) private var soccerBoxVerdictSize: CGFloat = 19
    @ScaledMetric(relativeTo: .subheadline) private var soccerScorePillSize: CGFloat = 15
    @ScaledMetric(relativeTo: .body) private var liveScoreColWidth: CGFloat = 42
    @ScaledMetric(relativeTo: .caption2) private var livePregameColWidth: CGFloat = 54
    @ScaledMetric(relativeTo: .title3) private var liveNowColWidth: CGFloat = 80
    @ScaledMetric(relativeTo: .body) private var pregameProjectedColWidth: CGFloat = 60
    @ScaledMetric(relativeTo: .title2) private var pregameChanceColWidth: CGFloat = 80
    @ScaledMetric(relativeTo: .title3) private var finalResultColWidth: CGFloat = 58
    @ScaledMetric(relativeTo: .title3) private var finalScoreValueSize: CGFloat = 24
    @ScaledMetric(relativeTo: .body) private var tennisSetValueSize: CGFloat = 17
    @ScaledMetric(relativeTo: .subheadline) private var tennisPtsValueSize: CGFloat = 14
    @ScaledMetric(relativeTo: .body) private var tennisSetColWidth: CGFloat = 23
    @ScaledMetric(relativeTo: .body) private var tennisPtsColWidth: CGFloat = 31
    @ScaledMetric(relativeTo: .caption2) private var tennisPregameColWidth: CGFloat = 46
    @ScaledMetric(relativeTo: .title3) private var tennisNowColWidth: CGFloat = 66

    private static let soccerWonGreen = Color(red: 0.09, green: 0.56, blue: 0.30)
    private static let soccerDrawBarSlate = Color(red: 0.58, green: 0.63, blue: 0.70)

    private var stacksRowsVertically: Bool {
        dynamicTypeSize.isAccessibilitySize
    }

    private var effectiveScoreColWidth: CGFloat {
        stacksRowsVertically ? min(liveScoreColWidth, 64) : min(liveScoreColWidth, 44)
    }

    private var effectivePregameColWidth: CGFloat {
        stacksRowsVertically ? min(max(livePregameColWidth, 112), 120) : min(livePregameColWidth, 56)
    }

    private var effectiveNowColWidth: CGFloat {
        stacksRowsVertically ? min(liveNowColWidth, 118) : min(liveNowColWidth, 82)
    }

    private var effectivePregameProjectedColWidth: CGFloat {
        stacksRowsVertically ? min(max(pregameProjectedColWidth, 84), 104) : min(pregameProjectedColWidth, 66)
    }

    private var effectivePregameChanceColWidth: CGFloat {
        stacksRowsVertically ? min(max(pregameChanceColWidth, 108), 124) : min(pregameChanceColWidth, 84)
    }

    private var effectiveFinalResultColWidth: CGFloat {
        stacksRowsVertically ? min(max(finalResultColWidth, 84), 104) : min(finalResultColWidth, 64)
    }

    private var effectiveTennisSetColWidth: CGFloat {
        stacksRowsVertically ? min(max(tennisSetColWidth, 28), 36) : min(tennisSetColWidth, 25)
    }

    private var effectiveTennisPtsColWidth: CGFloat {
        stacksRowsVertically ? min(max(tennisPtsColWidth, 36), 44) : min(tennisPtsColWidth, 34)
    }

    private var effectiveTennisPregameColWidth: CGFloat {
        stacksRowsVertically ? min(max(tennisPregameColWidth, 84), 104) : min(tennisPregameColWidth, 50)
    }

    private var effectiveTennisNowColWidth: CGFloat {
        stacksRowsVertically ? min(max(tennisNowColWidth, 96), 116) : min(tennisNowColWidth, 70)
    }

    private var cardAccessibilityIdentifier: String {
        model.kind.accessibilityIdentifier
    }

    private var hasTrailingControls: Bool {
        if model.showsEkg { return true }
        return SourceMarkButton(
            model.sourceMark,
            number: model.home.rawProbability,
            numberSize: 20
        ) != nil
    }

    private static func livePregameMetaText(
        model: EventSportHeadlines12472.Model,
        now: Date
    ) -> String {
        var parts: [String] = [model.leagueLabel ?? "NFL"]
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

    @inline(never)
    private func cardStackBoundary12278<V: View>(@ViewBuilder _ make: () -> V) -> AnyView {
        AnyView(make())
    }

    var body: AnyView {
        cardStackBoundary12278 {
            VStack(alignment: .leading, spacing: 10) {
                cardStackBoundary12278 { topBar }
                if let threeWay = model.soccerThreeWay {
                    cardStackBoundary12278 { soccerThreeWayContent(threeWay) }
                } else if let scoreFirst = model.tennisScoreFirst {
                    cardStackBoundary12278 { tennisScoreFirstContent(scoreFirst) }
                    if model.showsBottomBar {
                        cardStackBoundary12278 { bottomProbabilityBar }
                    }
                } else {
                    cardStackBoundary12278 {
                        VStack(alignment: .leading, spacing: 8) {
                            if let pregameHeaders = model.pregameColumnHeaders {
                                pregameColumnHeaderRow(pregameHeaders)
                            } else if let headers = model.liveColumnHeaders, headers.hasAny {
                                liveColumnHeaderRow(headers)
                            } else if let finalHeaders = model.finalColumnHeaders {
                                finalColumnHeaderRow(finalHeaders)
                            }
                            teamRow(model.away, color: colors.away, isAway: true)
                            if model.showsRowDivider {
                                Rectangle()
                                    .fill(Color.primary.opacity(0.06))
                                    .frame(height: 0.5)
                                    .accessibilityHidden(true)
                            }
                            teamRow(model.home, color: colors.home, isAway: false)
                        }
                    }
                    if model.showsBottomBar {
                        cardStackBoundary12278 { bottomProbabilityBar }
                    }
                }
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
            .accessibilityIdentifier(cardAccessibilityIdentifier)
        }
    }

    // MARK: - Top Bar

    private var topBar: some View {
        let layout = stacksRowsVertically
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 6))
            : AnyLayout(HStackLayout(alignment: .center, spacing: 8))
        return layout {
            leadingMeta
            if hasTrailingControls {
                if !stacksRowsVertically {
                    Spacer(minLength: 6)
                }
                trailingControls
            }
        }
    }

    @ViewBuilder
    private var leadingMeta: some View {
        switch model.kind.phase {
        case .before:
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
        case .after:
            if let text = model.plainMetaText {
                Text(text)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .during:
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
            if model.showsEkg {
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

    // MARK: - Three-Way Soccer Content

    @ViewBuilder
    private func soccerThreeWayContent(_ threeWay: EventSportHeadlines12472.SoccerThreeWayModel) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            soccerMatchupRow(threeWay)
            soccerThreeWayBoxesSection(threeWay)
            if threeWay.showsBottomBar {
                soccerThreeWayBottomBar(threeWay)
            }
        }
    }

    @ViewBuilder
    private func soccerMatchupRow(_ threeWay: EventSportHeadlines12472.SoccerThreeWayModel) -> some View {
        if stacksRowsVertically {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    crest(model.home, color: colors.home, size: 30)
                    Text(model.home.shortName)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(Color.primary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                soccerCenterTag(threeWay)
                HStack(spacing: 8) {
                    crest(model.away, color: colors.away, size: 30)
                    Text(model.away.shortName)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(Color.primary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        } else {
            HStack(alignment: .center, spacing: 8) {
                HStack(spacing: 7) {
                    crest(model.home, color: colors.home, size: 30)
                    Text(model.home.shortName)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(Color.primary)
                        .lineLimit(2)
                        .minimumScaleFactor(0.8)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                soccerCenterTag(threeWay)

                HStack(spacing: 7) {
                    Text(model.away.shortName)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(Color.primary)
                        .multilineTextAlignment(.trailing)
                        .lineLimit(2)
                        .minimumScaleFactor(0.8)
                        .fixedSize(horizontal: false, vertical: true)
                    crest(model.away, color: colors.away, size: 30)
                }
                .frame(maxWidth: .infinity, alignment: .trailing)
            }
        }
    }

    @ViewBuilder
    private func soccerCenterTag(_ threeWay: EventSportHeadlines12472.SoccerThreeWayModel) -> some View {
        if threeWay.isScorePill {
            let spokenPrefix = model.kind == .soccerDuringGame ? "Score" : "Final score"
            Text(threeWay.centerTagText)
                .font(.system(size: min(soccerScorePillSize, 19), weight: .heavy, design: .rounded).monospacedDigit())
                .foregroundStyle(Color.white)
                .lineLimit(1)
                .padding(.horizontal, 11)
                .padding(.vertical, 4)
                .background(Capsule().fill(Color(red: 0.08, green: 0.11, blue: 0.16)))
                .fixedSize(horizontal: true, vertical: true)
                .accessibilityLabel("\(spokenPrefix) \(threeWay.centerTagText)")
        } else {
            Text(threeWay.centerTagText)
                .font(.caption.weight(.medium))
                .foregroundStyle(DS.textSecondaryReadable)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: true)
        }
    }

    @ViewBuilder
    private func soccerThreeWayBoxesSection(_ threeWay: EventSportHeadlines12472.SoccerThreeWayModel) -> some View {
        let boxes = [threeWay.homeBox, threeWay.drawBox, threeWay.awayBox]
        if stacksRowsVertically {
            VStack(alignment: .leading, spacing: 6) {
                if let pregameHeader = threeWay.pregameHeader {
                    HStack {
                        Spacer(minLength: 0)
                        Text(pregameHeader)
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(DS.textSecondaryReadable)
                            .lineLimit(1)
                    }
                    .accessibilityHidden(true)
                }
                ForEach(Array(boxes.enumerated()), id: \.offset) { _, box in
                    soccerStackedOutcomeBox(box, showsPregameColumn: threeWay.pregameHeader != nil)
                }
            }
        } else {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 8) {
                    soccerOutcomeBox(threeWay.homeBox)
                    soccerOutcomeBox(threeWay.drawBox)
                    soccerOutcomeBox(threeWay.awayBox)
                }
                if let pregameHeader = threeWay.pregameHeader {
                    VStack(spacing: 2) {
                        HStack(spacing: 6) {
                            Text(pregameHeader)
                                .font(.caption2.weight(.medium))
                                .foregroundStyle(DS.textSecondaryReadable)
                                .lineLimit(1)
                                .fixedSize(horizontal: true, vertical: false)
                            Rectangle()
                                .fill(Color.primary.opacity(0.08))
                                .frame(height: 0.5)
                        }
                        .accessibilityHidden(true)

                        HStack(spacing: 8) {
                            soccerPregameCell(threeWay.homeBox.pregameChanceText)
                            soccerPregameCell(threeWay.drawBox.pregameChanceText)
                            soccerPregameCell(threeWay.awayBox.pregameChanceText)
                        }
                    }
                }
            }
        }
    }

    private func soccerPregameCell(_ text: String?) -> some View {
        Text(text ?? "—")
            .font(.caption.weight(.medium).monospacedDigit())
            .foregroundStyle(DS.textSecondaryReadable)
            .lineLimit(1)
            .frame(maxWidth: .infinity, alignment: .center)
            .accessibilityLabel(text.map { "Pregame \($0)" } ?? "")
    }

    private func soccerToneColor(_ tone: EventSportHeadlines12472.SoccerBoxTone) -> Color {
        switch tone {
        case .homeClub: return colors.home
        case .awayClub: return colors.away
        case .drawNeutral: return DS.textSecondaryReadable
        case .wonOutcome: return Self.soccerWonGreen
        case .lostOutcome, .mutedDash: return DS.textSecondaryReadable
        }
    }

    private func soccerBoxFill(_ box: EventSportHeadlines12472.SoccerThreeWayBox) -> Color {
        switch box.boxTone {
        case .homeClub: return colors.home.opacity(0.06)
        case .awayClub: return colors.away.opacity(0.06)
        case .drawNeutral: return Color.primary.opacity(0.035)
        case .wonOutcome: return Self.soccerWonGreen.opacity(0.08)
        case .lostOutcome:
            let tint = box.dotTone == .homeClub ? colors.home : (box.dotTone == .awayClub ? colors.away : Color.primary)
            return tint.opacity(0.035)
        case .mutedDash:
            return Color.primary.opacity(0.03)
        }
    }

    private func soccerBoxStroke(_ box: EventSportHeadlines12472.SoccerThreeWayBox) -> Color {
        switch box.boxTone {
        case .homeClub: return colors.home.opacity(0.28)
        case .awayClub: return colors.away.opacity(0.28)
        case .drawNeutral: return Color.primary.opacity(0.12)
        case .wonOutcome: return Self.soccerWonGreen.opacity(0.65)
        case .lostOutcome:
            let tint = box.dotTone == .homeClub ? colors.home : (box.dotTone == .awayClub ? colors.away : Color.primary)
            return tint.opacity(0.20)
        case .mutedDash:
            return Color.primary.opacity(0.10)
        }
    }

    private func soccerOutcomeBox(_ box: EventSportHeadlines12472.SoccerThreeWayBox) -> some View {
        let dotColor = soccerToneColor(box.dotTone)
        return VStack(spacing: 4) {
            HStack(spacing: 4) {
                Circle()
                    .fill(dotColor)
                    .frame(width: 5.5, height: 5.5)
                Text(box.headerLabel)
                    .font(.system(size: 10.5, weight: .bold))
                    .foregroundStyle(dotColor)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }
            soccerBoxMainValue(box)
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 6)
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(soccerBoxFill(box))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(soccerBoxStroke(box), lineWidth: box.boxTone == .wonOutcome ? 1.4 : 1.0)
        )
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("headline-12472-soccer-box-\(box.role.rawValue)")
    }

    private func soccerStackedOutcomeBox(
        _ box: EventSportHeadlines12472.SoccerThreeWayBox,
        showsPregameColumn: Bool
    ) -> some View {
        let dotColor = soccerToneColor(box.dotTone)
        return HStack(spacing: 8) {
            Circle()
                .fill(dotColor)
                .frame(width: 7, height: 7)
            Text(box.headerLabel)
                .font(.caption.weight(.bold))
                .foregroundStyle(dotColor)
                .lineLimit(2)
            Spacer(minLength: 4)
            soccerBoxMainValue(box)
            if showsPregameColumn {
                Text(box.pregameChanceText ?? "—")
                    .font(.caption.weight(.medium).monospacedDigit())
                    .foregroundStyle(DS.textSecondaryReadable)
                    .frame(minWidth: 52, alignment: .trailing)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 10)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(soccerBoxFill(box))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(soccerBoxStroke(box), lineWidth: box.boxTone == .wonOutcome ? 1.4 : 1.0)
        )
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private func soccerBoxMainValue(_ box: EventSportHeadlines12472.SoccerThreeWayBox) -> some View {
        switch box.boxTone {
        case .homeClub:
            Text(box.mainText)
                .font(.system(size: min(soccerBoxChanceSize, 25), weight: .black, design: .rounded).monospacedDigit())
                .foregroundStyle(colors.home)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        case .awayClub:
            Text(box.mainText)
                .font(.system(size: min(soccerBoxChanceSize, 25), weight: .black, design: .rounded).monospacedDigit())
                .foregroundStyle(colors.away)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        case .drawNeutral:
            Text(box.mainText)
                .font(.system(size: min(soccerBoxChanceSize, 25), weight: .black, design: .rounded).monospacedDigit())
                .foregroundStyle(Color.primary.opacity(0.80))
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        case .wonOutcome:
            if box.mainText.hasPrefix("\u{2713} ") {
                let suffix = String(box.mainText.dropFirst(2))
                HStack(spacing: 3) {
                    Text("\u{2713}")
                        .foregroundStyle(Self.soccerWonGreen)
                    Text(suffix)
                        .foregroundStyle(Color.primary)
                }
                .font(.system(size: min(soccerBoxVerdictSize, 21), weight: .heavy, design: .rounded))
                .lineLimit(1)
                .minimumScaleFactor(0.75)
            } else {
                Text(box.mainText)
                    .font(.system(size: min(soccerBoxVerdictSize, 21), weight: .heavy, design: .rounded))
                    .foregroundStyle(Color.primary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
            }
        case .lostOutcome:
            Text(box.mainText)
                .font(.system(size: min(soccerBoxVerdictSize, 21), weight: .bold, design: .rounded))
                .foregroundStyle(Color.primary.opacity(0.55))
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        case .mutedDash:
            Text(box.mainText)
                .font(.system(size: min(soccerBoxVerdictSize, 21), weight: .bold, design: .rounded))
                .foregroundStyle(DS.textSecondaryReadable)
                .lineLimit(1)
        }
    }

    private func soccerThreeWayBottomBar(_ threeWay: EventSportHeadlines12472.SoccerThreeWayModel) -> some View {
        GeometryReader { geo in
            let homeP = max(threeWay.homeBox.rawShare ?? 0, 0)
            let drawP = max(threeWay.drawBox.rawShare ?? 0, 0)
            let awayP = max(threeWay.awayBox.rawShare ?? 0, 0)
            let total = max(homeP + drawP + awayP, 0.0001)
            let gap: CGFloat = 2
            let usableWidth = max(geo.size.width - gap * 2, 6)
            let homeW = max(usableWidth * (homeP / total), 2)
            let drawW = max(usableWidth * (drawP / total), 2)

            HStack(spacing: gap) {
                Rectangle()
                    .fill(colors.home)
                    .frame(width: homeW)
                Rectangle()
                    .fill(Self.soccerDrawBarSlate)
                    .frame(width: drawW)
                Rectangle()
                    .fill(colors.away)
                    .frame(maxWidth: .infinity)
            }
            .frame(height: 6)
            .clipShape(Capsule())
        }
        .frame(height: 6)
        .accessibilityHidden(true)
    }

    // MARK: - Pregame & Live Column Headers & Team Rows

    private func pregameColumnHeaderRow(_ headers: EventSportHeadlines12472.PregameColumnHeaders) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 8) {
                Spacer(minLength: 0)
                if let projectedHeader = headers.projected {
                    Text(projectedHeader)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .frame(width: effectivePregameProjectedColWidth, alignment: .trailing)
                }
                Text(headers.chance)
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .frame(width: effectivePregameChanceColWidth, alignment: .trailing)
            }
            Rectangle()
                .fill(Color.primary.opacity(0.08))
                .frame(height: 0.5)
        }
        .accessibilityHidden(true)
    }

    private func liveColumnHeaderRow(_ headers: EventSportHeadlines12472.LiveColumnHeaders) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 8) {
                Spacer(minLength: 0)
                if let scoreHeader = headers.score {
                    Text(scoreHeader)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .frame(width: effectiveScoreColWidth, alignment: .trailing)
                }
                if let pregameHeader = headers.pregame {
                    Text(pregameHeader)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                        .frame(width: effectivePregameColWidth, alignment: .trailing)
                }
                Text(headers.now)
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .frame(width: effectiveNowColWidth, alignment: .trailing)
            }
            Rectangle()
                .fill(Color.primary.opacity(0.08))
                .frame(height: 0.5)
        }
        .accessibilityHidden(true)
    }

    @ViewBuilder
    private func liveValueColumns(
        _ side: EventSportHeadlines12472.TeamRowModel,
        headers: EventSportHeadlines12472.LiveColumnHeaders,
        color: Color
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if headers.score != nil {
                Group {
                    if let score = side.liveScore {
                        scoreText(score)
                    }
                }
                .frame(width: effectiveScoreColWidth, alignment: .trailing)
            }
            if headers.pregame != nil {
                Group {
                    if let pregame = side.pregameChanceText {
                        pregameLabel(pregame)
                    }
                }
                .frame(width: effectivePregameColWidth, alignment: .trailing)
            }
            chanceText(side.winChanceText, color: color, hasInlineColumns: true)
                .frame(width: effectiveNowColWidth, alignment: .trailing)
        }
    }

    @ViewBuilder
    private func pregameValueColumns(
        _ side: EventSportHeadlines12472.TeamRowModel,
        color: Color
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if model.pregameColumnHeaders?.projected != nil {
                Group {
                    if let projectedNumber = side.pregameProjectedNumberText {
                        pregameProjectedNumberText(projectedNumber)
                    }
                }
                .frame(width: effectivePregameProjectedColWidth, alignment: .trailing)
            }

            chanceText(side.winChanceText, color: color)
                .frame(width: effectivePregameChanceColWidth, alignment: .trailing)
        }
    }

    private func finalColumnHeaderRow(_ headers: EventSportHeadlines12472.FinalColumnHeaders) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 8) {
                Spacer(minLength: 0)
                if let pregameHeader = headers.pregame {
                    Text(pregameHeader)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                        .frame(width: effectivePregameColWidth, alignment: .trailing)
                }
                Text(headers.finalLabel)
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .frame(width: effectiveFinalResultColWidth, alignment: .trailing)
            }
            Rectangle()
                .fill(Color.primary.opacity(0.08))
                .frame(height: 0.5)
        }
        .accessibilityHidden(true)
    }

    @ViewBuilder
    private func finalValueColumns(
        _ side: EventSportHeadlines12472.TeamRowModel,
        headers: EventSportHeadlines12472.FinalColumnHeaders
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if headers.pregame != nil {
                Group {
                    if let pregame = side.pregameChanceText {
                        pregameLabel(pregame)
                    } else {
                        Text("—")
                            .font(.system(size: min(livePregameSize, 17), weight: .medium, design: .rounded))
                            .foregroundStyle(DS.textSecondaryReadable)
                    }
                }
                .frame(width: effectivePregameColWidth, alignment: .trailing)
            }
            if let finalResult = side.finalResultText {
                finalResultValueText(
                    finalResult,
                    won: side.won,
                    isWordResult: finalResult == "Won" || finalResult == "Lost"
                )
                .frame(width: effectiveFinalResultColWidth, alignment: .trailing)
            }
        }
    }

    private func finalResultValueText(
        _ text: String,
        won: Bool?,
        isWordResult: Bool
    ) -> some View {
        let maxFont: CGFloat = isWordResult ? 20 : 27
        let baseFont: CGFloat = isWordResult ? soccerBoxVerdictSize : finalScoreValueSize
        let weight: Font.Weight = (won == true || won == nil) ? .black : .semibold
        let foreground: Color = (won == false) ? Color.primary.opacity(0.45) : Color.primary
        return Text(text)
            .font(.system(size: min(baseFont, maxFont), weight: weight, design: .rounded).monospacedDigit())
            .foregroundStyle(foreground)
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            .accessibilityLabel("Final \(text)")
    }

    // MARK: - Score-First Live Tennis Table

    @ViewBuilder
    private func tennisScoreFirstContent(
        _ scoreFirst: EventSportHeadlines12472.TennisScoreFirstModel
    ) -> some View {
        if stacksRowsVertically {
            VStack(alignment: .leading, spacing: 8) {
                if scoreFirst.pregameHeader != nil || !scoreFirst.nowHeader.isEmpty {
                    HStack(spacing: 8) {
                        Spacer(minLength: 0)
                        if let pregameHeader = scoreFirst.pregameHeader {
                            Text(pregameHeader)
                                .font(.caption2.weight(.medium))
                                .foregroundStyle(DS.textSecondaryReadable)
                                .frame(width: effectiveTennisPregameColWidth, alignment: .trailing)
                        }
                        Text(scoreFirst.nowHeader)
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(DS.textSecondaryReadable)
                            .frame(width: effectiveTennisNowColWidth, alignment: .trailing)
                    }
                    .accessibilityHidden(true)
                }
                tennisStackedPlayerRow(
                    model.away,
                    color: colors.away,
                    scoreFirst: scoreFirst,
                    isAway: true
                )
                Rectangle()
                    .fill(Color.primary.opacity(0.06))
                    .frame(height: 0.5)
                    .accessibilityHidden(true)
                tennisStackedPlayerRow(
                    model.home,
                    color: colors.home,
                    scoreFirst: scoreFirst,
                    isAway: false
                )
            }
        } else {
            VStack(alignment: .leading, spacing: 6) {
                tennisHeaderRow(scoreFirst)
                tennisInlinePlayerRow(
                    model.away,
                    color: colors.away,
                    scoreFirst: scoreFirst,
                    isAway: true
                )
                Rectangle()
                    .fill(Color.primary.opacity(0.06))
                    .frame(height: 0.5)
                    .accessibilityHidden(true)
                tennisInlinePlayerRow(
                    model.home,
                    color: colors.home,
                    scoreFirst: scoreFirst,
                    isAway: false
                )
            }
        }
    }

    private func tennisSetColumnWidth(for header: String) -> CGFloat {
        header == "Sets" ? max(effectiveTennisSetColWidth, 30) : effectiveTennisSetColWidth
    }

    private func tennisHeaderRow(
        _ scoreFirst: EventSportHeadlines12472.TennisScoreFirstModel
    ) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 6) {
                Text("Player")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                Spacer(minLength: 4)
                HStack(spacing: 4) {
                    ForEach(Array(scoreFirst.setColumns.enumerated()), id: \.offset) { _, col in
                        Text(col.header)
                            .font(.caption2.weight(.medium).monospacedDigit())
                            .foregroundStyle(DS.textSecondaryReadable)
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                            .frame(width: tennisSetColumnWidth(for: col.header), alignment: .center)
                    }
                    if scoreFirst.pointsColumn != nil {
                        Text("Pts")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(DS.greenReadable)
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                            .frame(width: effectiveTennisPtsColWidth, alignment: .center)
                    }
                }
                if !scoreFirst.setColumns.isEmpty || scoreFirst.pointsColumn != nil {
                    Color.clear
                        .frame(width: 5, height: 1)
                }
                HStack(spacing: 6) {
                    if let pregameHeader = scoreFirst.pregameHeader {
                        Text(pregameHeader)
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(DS.textSecondaryReadable)
                            .lineLimit(1)
                            .minimumScaleFactor(0.75)
                            .frame(width: effectiveTennisPregameColWidth, alignment: .trailing)
                    }
                    Text(scoreFirst.nowHeader)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .frame(width: effectiveTennisNowColWidth, alignment: .trailing)
                }
            }
            Rectangle()
                .fill(Color.primary.opacity(0.08))
                .frame(height: 0.5)
        }
        .accessibilityHidden(true)
    }

    private func tennisInlinePlayerRow(
        _ side: EventSportHeadlines12472.TeamRowModel,
        color: Color,
        scoreFirst: EventSportHeadlines12472.TennisScoreFirstModel,
        isAway: Bool
    ) -> some View {
        let ptsText = isAway ? scoreFirst.pointsColumn?.away : scoreFirst.pointsColumn?.home

        return HStack(alignment: .center, spacing: 6) {
            Text(side.shortName)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(Color.primary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .frame(maxWidth: .infinity, alignment: .leading)

            HStack(spacing: 4) {
                ForEach(Array(scoreFirst.setColumns.enumerated()), id: \.offset) { _, col in
                    let val = isAway ? col.awayValue : col.homeValue
                    let emphasized = isAway ? col.awayEmphasized : col.homeEmphasized
                    Text(val)
                        .font(.system(size: min(tennisSetValueSize, 20), weight: emphasized ? .bold : .medium, design: .rounded).monospacedDigit())
                        .foregroundStyle(emphasized ? Color.primary : DS.textSecondaryReadable)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .frame(width: tennisSetColumnWidth(for: col.header), alignment: .center)
                }
                if let ptsText {
                    Text(ptsText)
                        .font(.system(size: min(tennisPtsValueSize, 17), weight: .bold, design: .rounded).monospacedDigit())
                        .foregroundStyle(DS.greenReadable)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .padding(.vertical, 2)
                        .frame(width: effectiveTennisPtsColWidth, alignment: .center)
                        .background(
                            RoundedRectangle(cornerRadius: 6, style: .continuous)
                                .fill(DS.greenReadable.opacity(0.11))
                        )
                }
            }

            if !scoreFirst.setColumns.isEmpty || scoreFirst.pointsColumn != nil {
                Rectangle()
                    .fill(Color.primary.opacity(0.10))
                    .frame(width: 1, height: 22)
                    .padding(.horizontal, 2)
                    .accessibilityHidden(true)
            }

            HStack(alignment: .firstTextBaseline, spacing: 6) {
                if scoreFirst.pregameHeader != nil {
                    Group {
                        if let pregame = side.pregameChanceText {
                            pregameLabel(pregame)
                        } else {
                            Text("—")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(DS.textSecondaryReadable)
                        }
                    }
                    .frame(width: effectiveTennisPregameColWidth, alignment: .trailing)
                }
                Text(side.winChanceText)
                    .font(.system(size: min(liveTenthsChanceSize, 24), weight: .black, design: .rounded).monospacedDigit())
                    .foregroundStyle(color)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                    .frame(width: effectiveTennisNowColWidth, alignment: .trailing)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            tennisPlayerSpokenLabel(
                side: side,
                scoreFirst: scoreFirst,
                isAway: isAway
            )
        )
        .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
    }

    private func tennisStackedPlayerRow(
        _ side: EventSportHeadlines12472.TeamRowModel,
        color: Color,
        scoreFirst: EventSportHeadlines12472.TennisScoreFirstModel,
        isAway: Bool
    ) -> some View {
        let ptsText = isAway ? scoreFirst.pointsColumn?.away : scoreFirst.pointsColumn?.home

        return VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Text(side.shortName)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(Color.primary)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
                HStack(spacing: 6) {
                    ForEach(Array(scoreFirst.setColumns.enumerated()), id: \.offset) { _, col in
                        let val = isAway ? col.awayValue : col.homeValue
                        let emphasized = isAway ? col.awayEmphasized : col.homeEmphasized
                        Text(val)
                            .font(.body.weight(emphasized ? .bold : .regular).monospacedDigit())
                            .foregroundStyle(emphasized ? Color.primary : DS.textSecondaryReadable)
                    }
                    if let ptsText {
                        Text(ptsText)
                            .font(.subheadline.weight(.bold).monospacedDigit())
                            .foregroundStyle(DS.greenReadable)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(
                                RoundedRectangle(cornerRadius: 6, style: .continuous)
                                    .fill(DS.greenReadable.opacity(0.11))
                            )
                    }
                }
            }
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Spacer(minLength: 0)
                if scoreFirst.pregameHeader != nil, let pregame = side.pregameChanceText {
                    pregameLabel(pregame)
                        .frame(width: effectiveTennisPregameColWidth, alignment: .trailing)
                }
                chanceText(side.winChanceText, color: color, hasInlineColumns: true)
                    .frame(width: effectiveTennisNowColWidth, alignment: .trailing)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            tennisPlayerSpokenLabel(
                side: side,
                scoreFirst: scoreFirst,
                isAway: isAway
            )
        )
        .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
    }

    private func tennisPlayerSpokenLabel(
        side: EventSportHeadlines12472.TeamRowModel,
        scoreFirst: EventSportHeadlines12472.TennisScoreFirstModel,
        isAway: Bool
    ) -> String {
        var parts: [String] = [side.shortName]
        let setValues = scoreFirst.setColumns.map { col in
            "\(col.header) \(isAway ? col.awayValue : col.homeValue)"
        }
        if !setValues.isEmpty {
            parts.append(setValues.joined(separator: ", "))
        }
        if let pts = isAway ? scoreFirst.pointsColumn?.away : scoreFirst.pointsColumn?.home {
            parts.append("points \(pts)")
        }
        if let pregame = side.pregameChanceText {
            parts.append("pregame \(pregame)")
        }
        parts.append("now \(side.winChanceText)")
        return parts.joined(separator: ", ")
    }

    @ViewBuilder
    private func teamRow(
        _ side: EventSportHeadlines12472.TeamRowModel,
        color: Color,
        isAway: Bool
    ) -> some View {
        if let finalHeaders = model.finalColumnHeaders {
            if stacksRowsVertically {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        crest(side, color: color)
                        teamIdentityStack(side, color: color, stacksRecord: true)
                    }
                    HStack(spacing: 0) {
                        Spacer(minLength: 0)
                        finalValueColumns(side, headers: finalHeaders)
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
            } else {
                HStack(alignment: .center, spacing: 6) {
                    crest(side, color: color)
                    teamIdentityStack(side, color: color, stacksRecord: true)
                    Spacer(minLength: 4)
                    finalValueColumns(side, headers: finalHeaders)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
            }
        } else if model.pregameColumnHeaders != nil {
            if stacksRowsVertically {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        crest(side, color: color)
                        teamIdentityStack(side, color: color, stacksRecord: true)
                    }
                    HStack(spacing: 0) {
                        Spacer(minLength: 0)
                        pregameValueColumns(side, color: color)
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
            } else {
                HStack(alignment: .center, spacing: 6) {
                    crest(side, color: color)
                    teamIdentityStack(side, color: color, stacksRecord: true)
                    Spacer(minLength: 4)
                    pregameValueColumns(side, color: color)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
            }
        } else if let headers = model.liveColumnHeaders, headers.hasAny {
            if stacksRowsVertically {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        crest(side, color: color)
                        teamIdentityStack(side, color: color, stacksRecord: model.stacksRecordUnderName)
                    }
                    HStack(spacing: 0) {
                        Spacer(minLength: 0)
                        liveValueColumns(side, headers: headers, color: color)
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
            } else {
                HStack(alignment: .center, spacing: 6) {
                    crest(side, color: color)
                    teamIdentityStack(side, color: color, stacksRecord: model.stacksRecordUnderName)
                    Spacer(minLength: 4)
                    liveValueColumns(side, headers: headers, color: color)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
            }
        } else if stacksRowsVertically {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    crest(side, color: color)
                    teamIdentityStack(side, color: color, stacksRecord: model.stacksRecordUnderName)
                }
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Spacer(minLength: 4)
                    chanceText(side.winChanceText, color: color)
                        .fixedSize(horizontal: true, vertical: false)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
        } else {
            HStack(alignment: .center, spacing: 6) {
                crest(side, color: color)
                teamIdentityStack(side, color: color, stacksRecord: model.stacksRecordUnderName)
                Spacer(minLength: 4)
                chanceText(side.winChanceText, color: color)
                    .fixedSize(horizontal: true, vertical: false)
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(isAway ? "headline-12472-away-row" : "headline-12472-home-row")
        }
    }

    private func crest(
        _ side: EventSportHeadlines12472.TeamRowModel,
        color: Color,
        size: CGFloat = 32
    ) -> some View {
        TeamLogoView(
            url: side.logoURL,
            teamName: side.fullName,
            color: color,
            size: size,
            sportKey: model.sportKey,
            opponentName: side.opponentFullName
        )
    }

    private func teamIdentityStack(
        _ side: EventSportHeadlines12472.TeamRowModel,
        color: Color,
        stacksRecord: Bool = false
    ) -> some View {
        let isLoser = side.won == false
        return VStack(alignment: .leading, spacing: 1.5) {
            if stacksRecord {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(side.shortName)
                        .font(.subheadline.weight(isLoser ? .semibold : .bold))
                        .foregroundStyle(isLoser ? Color.primary.opacity(0.65) : Color.primary)
                        .lineLimit(2)
                        .minimumScaleFactor(0.85)
                        .fixedSize(horizontal: false, vertical: true)
                    if side.won == true {
                        Text("\u{2713}")
                            .font(.subheadline.weight(.heavy))
                            .foregroundStyle(Self.soccerWonGreen)
                            .accessibilityLabel("won")
                    }
                }
                if let subline = side.secondarySublineText {
                    Text(subline)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                } else if let record = side.record {
                    Text(record)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                }
                if let projected = side.projectedText, model.pregameColumnHeaders == nil {
                    Text(projected)
                        .font(.caption2.weight(.semibold).monospacedDigit())
                        .foregroundStyle(color)
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                }
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text(side.shortName)
                        .font(.subheadline.weight(isLoser ? .semibold : .bold))
                        .foregroundStyle(isLoser ? Color.primary.opacity(0.65) : Color.primary)
                        .lineLimit(2)
                        .minimumScaleFactor(0.85)
                        .fixedSize(horizontal: false, vertical: true)
                    if side.won == true {
                        Text("\u{2713}")
                            .font(.subheadline.weight(.heavy))
                            .foregroundStyle(Self.soccerWonGreen)
                            .accessibilityLabel("won")
                    }
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
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                }
            }
        }
    }

    private func pregameProjectedNumberText(_ number: String) -> some View {
        Text(number)
            .font(.system(size: min(pregameProjectedSize, 24), weight: .semibold, design: .rounded).monospacedDigit())
            .foregroundStyle(Color.primary)
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            .accessibilityLabel("Projected \(number)")
    }

    private func scoreText(_ score: Int) -> some View {
        Text("\(score)")
            .font(.system(size: min(liveScoreSize, 22), weight: .semibold, design: .rounded).monospacedDigit())
            .foregroundStyle(Color.primary)
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            .accessibilityLabel("Score \(score)")
    }

    private func pregameLabel(_ text: String) -> some View {
        Text(text)
            .font(.system(size: min(livePregameSize, 17), weight: .medium, design: .rounded).monospacedDigit())
            .foregroundStyle(DS.textSecondaryReadable)
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            .accessibilityLabel("Pregame \(text)")
    }

    private func chanceText(_ text: String, color: Color, hasInlineColumns: Bool = false) -> some View {
        let base = hasInlineColumns ? liveTenthsChanceSize : winChanceSize
        return Text(text)
            .font(.system(size: min(base, 30), weight: .black, design: .rounded).monospacedDigit())
            .foregroundStyle(color)
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            .accessibilityLabel(hasInlineColumns ? "Now \(text)" : text)
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
