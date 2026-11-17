import SwiftUI

/// Direction 199 & Rulings 200-B, 197, 194-A — The single unified event-page
/// headline card for **every** sport and state (`before`, `during`, `after`).
///
/// All sports render through one column-header + competitor-rows table driven by
/// `EventSportHeadlines12472.Model`, using `HeadlineStyleTable199` exclusively
/// for typography and semantic colours.
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
    @ScaledMetric(relativeTo: .title2) private var nowScaledSize: CGFloat = HeadlineStyleTable199.nowBaseSize(.page)
    @ScaledMetric(relativeTo: .title3) private var secondProminentScaledSize: CGFloat = HeadlineStyleTable199.secondNumberBaseSize(.page, prominent: true)
    @ScaledMetric(relativeTo: .body) private var secondRegularScaledSize: CGFloat = HeadlineStyleTable199.secondNumberBaseSize(.page, prominent: false)
    @ScaledMetric(relativeTo: .subheadline) private var baseNameSize: CGFloat = HeadlineStyleTable199.nameBaseSize(.page)
    @ScaledMetric(relativeTo: .caption) private var baseQuietSize: CGFloat = HeadlineStyleTable199.quietTextBaseSize(.page)
    @ScaledMetric(relativeTo: .caption2) private var headerScaledSize: CGFloat = HeadlineStyleTable199.headerBaseSize(.page)

    private var stacksRowsVertically: Bool {
        dynamicTypeSize.isAccessibilitySize
    }

    private var isManyColumnScoreboard: Bool {
        model.columns.count >= 5
    }

    private var columnSpacing: CGFloat {
        isManyColumnScoreboard ? 4 : 6
    }

    private var crestSize: CGFloat {
        if stacksRowsVertically { return 28 }
        if isManyColumnScoreboard { return 24 }
        return model.rows.count >= 3 ? 28 : 30
    }

    private func columnWidth(for role: EventSportHeadlines12472.ColumnRole) -> CGFloat {
        switch role {
        case .setScore:
            return stacksRowsVertically ? 27 : 22
        case .gamePoints:
            return stacksRowsVertically ? 36 : 31
        case .score:
            return stacksRowsVertically ? 48 : 34
        case .projected:
            if model.kind.phase == .before {
                return stacksRowsVertically ? 68 : 48
            }
            return stacksRowsVertically ? 56 : 44
        case .pregame:
            if model.columns.count >= 4 {
                return stacksRowsVertically ? 68 : 48
            }
            return stacksRowsVertically ? 76 : 56
        case .finalResult:
            return stacksRowsVertically ? 78 : 62
        case .chance:
            return stacksRowsVertically ? 104 : 80
        case .now:
            if isManyColumnScoreboard {
                return stacksRowsVertically ? 88 : 70
            }
            return stacksRowsVertically ? 104 : 84
        }
    }

    private func resolvedColumnWidth(for column: EventSportHeadlines12472.ColumnSpec, at index: Int) -> CGFloat {
        let base = columnWidth(for: column.role)
        guard case .setScore = column.role else { return base }
        if column.header == "Sets" {
            return stacksRowsVertically ? 34 : 30
        }
        let hasSuperscript = model.rows.contains { row in
            guard let sup = row.cellSuperscripts[index] else { return false }
            return !sup.isEmpty
        }
        return hasSuperscript ? base + 6 : base
    }

    private func rowTint(for role: EventSportHeadlines12472.RowRole) -> Color {
        switch role {
        case .away:
            return colors.away
        case .home:
            return colors.home
        case .draw:
            return HeadlineStyleTable199.drawInk
        }
    }

    private func rowAccessibilityIdentifier(for role: EventSportHeadlines12472.RowRole) -> String {
        switch role {
        case .away:
            return "headline-12472-away-row"
        case .home:
            return "headline-12472-home-row"
        case .draw:
            return "headline-12472-draw-row"
        }
    }

    private var showsActiveEkgControl: Bool {
        guard model.showsEkg,
              model.kind.phase == .during,
              priceStreamingEligible else { return false }
        let presentation = EkgHeartbeat.present(
            ekgTracker,
            status: liveUpdateStatus,
            now: displayAsOf ?? Date()
        )
        return presentation.mode != .flat
    }

    private func extraLeadingGap(at index: Int) -> CGFloat {
        guard index > 0, !isManyColumnScoreboard else { return 0 }
        if model.columns[index].role == .now {
            return 8
        }
        return 0
    }

    private var totalColumnsWidth: CGFloat {
        let widths = model.columns.enumerated().reduce(CGFloat(0)) { $0 + resolvedColumnWidth(for: $1.element, at: $1.offset) }
        let gaps = CGFloat(max(model.columns.count - 1, 0)) * columnSpacing
        let extra = model.columns.indices.reduce(CGFloat(0)) { $0 + extraLeadingGap(at: $1) }
        return widths + gaps + extra
    }

    private var sharedTeamNameFontSize: CGFloat {
        let cappedBase = min(baseNameSize, stacksRowsVertically ? 30 : 20)
        let availableWidth: CGFloat = stacksRowsVertically
            ? max(330 - crestSize - 8, 120)
            : max(330 - crestSize - 10 - totalColumnsWidth, 64)
        return CardTeamNameSizing.sharedSingleLineFontSize(
            names: model.rows.map(\.shortName),
            baseSize: cappedBase,
            weight: .bold,
            availableWidth: availableWidth,
            minimumScale: stacksRowsVertically ? 0.58 : 0.72
        )
    }

    private var sharedRecordFontSize: CGFloat {
        let cappedQuiet = min(baseQuietSize, stacksRowsVertically ? 22 : 15)
        return CardTeamNameSizing.cappedRecordFontSize(
            baseRecordSize: cappedQuiet,
            teamNameFontSize: sharedTeamNameFontSize
        )
    }

    private var hasTrailingControls: Bool {
        if showsActiveEkgControl { return true }
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
        var parts: [String] = [model.leagueLabel ?? "Game"]
        if let timeText = EventSportHeadlines12472.pregameStartText(
            commenceTime: model.commenceTime,
            startIsTbd: model.startIsTbd,
            now: now
        ) {
            parts.append(timeText)
        }
        if let broadcast = model.broadcast,
           EventDetailView.showsBroadcast(
               status: model.eventStatus,
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
                cardStackBoundary12278 { unifiedTableSection }
                if let bottomBar = model.bottomBar {
                    cardStackBoundary12278 { bottomBarView(bottomBar) }
                }
                if let pregameSummary = model.livePregameSummary {
                    cardStackBoundary12278 { livePregameSummaryRow(pregameSummary) }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(Color.cardBackground)
            .preference(key: HeadlineMountedKindPreferenceKey199.self, value: model.kind)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1)
            )
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(model.kind.accessibilityIdentifier)
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
                        .font(HeadlineStyleTable199.quietText(.page, monospacedDigits: true))
                        .foregroundStyle(HeadlineStyleTable199.quietInk)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        case .after:
            if let text = model.plainMetaText {
                Text(text)
                    .font(HeadlineStyleTable199.quietText(.page, monospacedDigits: true))
                    .foregroundStyle(HeadlineStyleTable199.quietInk)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .during:
            if let badgeText = model.liveBadgeText {
                let metaLayout = stacksRowsVertically
                    ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
                    : AnyLayout(HStackLayout(alignment: .center, spacing: 8))
                metaLayout {
                    liveBadgePill(badgeText)
                        .fixedSize(horizontal: true, vertical: true)
                    if let league = model.leagueLabel {
                        Text(league)
                            .font(HeadlineStyleTable199.quietText(.page, monospacedDigits: false))
                            .foregroundStyle(HeadlineStyleTable199.quietInk)
                            .fixedSize(horizontal: !stacksRowsVertically, vertical: stacksRowsVertically)
                    }
                }
            } else if let plain = model.plainMetaText {
                Text(plain)
                    .font(HeadlineStyleTable199.quietText(.page, monospacedDigits: true))
                    .foregroundStyle(HeadlineStyleTable199.quietInk)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func liveBadgePill(_ badgeText: String) -> some View {
        HStack(spacing: 5) {
            Circle()
                .fill(HeadlineStyleTable199.livePillForegroundInk)
                .frame(width: 6, height: 6)
            Text(badgeText)
                .font(HeadlineStyleTable199.headers(.page, scaledSize: headerScaledSize).monospacedDigit())
                .foregroundStyle(HeadlineStyleTable199.livePillForegroundInk)
                .lineLimit(1)
                .minimumScaleFactor(0.82)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3.5)
        .background(Capsule().fill(HeadlineStyleTable199.livePillInk))
    }

    private var trailingControls: some View {
        HStack(spacing: 2) {
            if showsActiveEkgControl {
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

    // MARK: - Unified Column-Header + Competitor-Rows Table

    private var unifiedTableSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !model.columns.isEmpty {
                columnHeaderRow
            }
            ForEach(Array(model.rows.enumerated()), id: \.offset) { index, row in
                if index > 0 && model.showsRowDivider {
                    Rectangle()
                        .fill(HeadlineStyleTable199.rowDividerInk)
                        .frame(height: 0.5)
                        .accessibilityHidden(true)
                }
                competitorRowView(row)
            }
        }
    }

    private var columnHeaderRow: some View {
        HStack(alignment: .firstTextBaseline, spacing: columnSpacing) {
            Spacer(minLength: 4)
            ForEach(Array(model.columns.enumerated()), id: \.offset) { idx, col in
                Text(col.header)
                    .font(HeadlineStyleTable199.headers(.page, scaledSize: headerScaledSize))
                    .foregroundStyle(HeadlineStyleTable199.quietInk)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(width: resolvedColumnWidth(for: col, at: idx), alignment: .trailing)
                    .padding(.leading, extraLeadingGap(at: idx))
            }
        }
        .accessibilityHidden(true)
    }

    @ViewBuilder
    private func competitorRowView(_ row: EventSportHeadlines12472.CompetitorRow) -> some View {
        let tint = rowTint(for: row.role)
        if stacksRowsVertically {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .center, spacing: 8) {
                    rowBadge(row, tint: tint)
                    competitorIdentityStack(row)
                }
                HStack(alignment: .firstTextBaseline, spacing: columnSpacing) {
                    Spacer(minLength: 0)
                    rowCellsStrip(row, tint: tint)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(rowAccessibilityIdentifier(for: row.role))
        } else {
            HStack(alignment: .center, spacing: 6) {
                rowBadge(row, tint: tint)
                competitorIdentityStack(row)
                Spacer(minLength: 4)
                HStack(alignment: .firstTextBaseline, spacing: columnSpacing) {
                    rowCellsStrip(row, tint: tint)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(rowAccessibilityIdentifier(for: row.role))
        }
    }

    @ViewBuilder
    private func rowBadge(_ row: EventSportHeadlines12472.CompetitorRow, tint: Color) -> some View {
        switch row.role {
        case .away, .home:
            TeamLogoView(
                url: row.logoURL,
                teamName: row.fullName,
                color: tint,
                size: crestSize,
                sportKey: model.sportKey,
                opponentName: row.opponentFullName,
                abbreviation: row.abbreviation,
                opponentAbbreviation: row.opponentAbbreviation
            )
        case .draw:
            ZStack {
                Circle()
                    .fill(HeadlineStyleTable199.drawInk.opacity(0.12))
                Capsule()
                    .fill(HeadlineStyleTable199.drawInk)
                    .frame(width: crestSize * 0.42, height: 2.2)
            }
            .frame(width: crestSize, height: crestSize)
            .accessibilityHidden(true)
        }
    }

    private func competitorIdentityStack(_ row: EventSportHeadlines12472.CompetitorRow) -> some View {
        let isLoser = row.won == false
        let nameInk: Color = {
            if row.role == .draw && row.won != true {
                return HeadlineStyleTable199.drawInk
            }
            return isLoser ? HeadlineStyleTable199.loserInk : HeadlineStyleTable199.primaryNumberInk
        }()
        return VStack(alignment: .leading, spacing: stacksRowsVertically ? 2 : 1.5) {
            Text(row.shortName)
                .font(HeadlineStyleTable199.names(.page, isLoser: isLoser, scaledSize: sharedTeamNameFontSize))
                .foregroundStyle(nameInk)
                .lineLimit(1)
                .minimumScaleFactor(stacksRowsVertically ? 0.72 : 0.80)
                .truncationMode(.tail)
                .allowsTightening(true)
                .fixedSize(horizontal: false, vertical: true)
            if let record = row.record, !record.isEmpty {
                Text(record)
                    .font(HeadlineStyleTable199.quietText(.page, monospacedDigits: true, scaledSize: sharedRecordFontSize))
                    .foregroundStyle(HeadlineStyleTable199.quietInk)
                    .lineLimit(1)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder
    private func rowCellsStrip(
        _ row: EventSportHeadlines12472.CompetitorRow,
        tint: Color
    ) -> some View {
        ForEach(Array(model.columns.enumerated()), id: \.offset) { idx, col in
            let cellText = idx < row.cells.count ? row.cells[idx] : ""
            cellView(
                text: cellText,
                column: col,
                columnIndex: idx,
                row: row,
                tint: tint
            )
            .frame(width: resolvedColumnWidth(for: col, at: idx), alignment: .trailing)
            .padding(.leading, extraLeadingGap(at: idx))
        }
    }

    @ViewBuilder
    private func cellView(
        text: String,
        column: EventSportHeadlines12472.ColumnSpec,
        columnIndex: Int,
        row: EventSportHeadlines12472.CompetitorRow,
        tint: Color
    ) -> some View {
        switch column.role {
        case .now, .chance:
            if text.isEmpty {
                Color.clear.frame(height: 1)
            } else {
                Text(text)
                    .font(HeadlineStyleTable199.now(.page, scaledSize: nowScaledSize))
                    .foregroundStyle(tint)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("\(column.header.isEmpty ? "Chance" : column.header) \(text)")
            }

        case .score, .projected:
            if text.isEmpty {
                Color.clear.frame(height: 1)
            } else {
                Text(text)
                    .font(HeadlineStyleTable199.secondNumbers(.page, prominent: false, scaledSize: secondRegularScaledSize))
                    .foregroundStyle(HeadlineStyleTable199.primaryNumberInk)
                    .lineLimit(1)
                    .minimumScaleFactor(0.80)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("\(column.header) \(text)")
            }

        case .pregame:
            if text.isEmpty {
                Color.clear.frame(height: 1)
            } else {
                Text(text)
                    .font(HeadlineStyleTable199.secondNumbers(.page, prominent: false, scaledSize: secondRegularScaledSize))
                    .foregroundStyle(HeadlineStyleTable199.quietInk)
                    .lineLimit(1)
                    .minimumScaleFactor(0.80)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("Pregame \(text)")
            }

        case .setScore:
            if text.isEmpty {
                Color.clear.frame(height: 1)
            } else {
                let emphasized = row.emphasizedColumns.contains(columnIndex)
                let setFont = HeadlineStyleTable199.secondNumbers(
                    .page,
                    prominent: emphasized,
                    scaledSize: emphasized ? secondProminentScaledSize * 0.84 : secondRegularScaledSize
                )
                let setInk = emphasized ? HeadlineStyleTable199.primaryNumberInk : HeadlineStyleTable199.quietInk
                if let tb = row.cellSuperscripts[columnIndex], !tb.isEmpty {
                    HStack(alignment: .firstTextBaseline, spacing: 0.5) {
                        Text(text)
                            .font(setFont)
                            .foregroundStyle(setInk)
                        Text(tb)
                            .font(HeadlineStyleTable199.headers(.page, scaledSize: headerScaledSize * 0.90).monospacedDigit())
                            .foregroundStyle(HeadlineStyleTable199.quietInk)
                            .baselineOffset(5)
                    }
                    .lineLimit(1)
                    .minimumScaleFactor(0.80)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("\(column.header) \(text) tiebreak \(tb)")
                } else {
                    Text(text)
                        .font(setFont)
                        .foregroundStyle(setInk)
                        .lineLimit(1)
                        .minimumScaleFactor(0.80)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityLabel("\(column.header) \(text)")
                }
            }

        case .gamePoints:
            if text.isEmpty {
                Color.clear.frame(height: 1)
            } else {
                Text(text)
                    .font(HeadlineStyleTable199.secondNumbers(.page, prominent: false, scaledSize: secondRegularScaledSize * 0.85))
                    .foregroundStyle(HeadlineStyleTable199.primaryNumberInk)
                    .lineLimit(1)
                    .minimumScaleFactor(0.80)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1.5)
                    .background(
                        RoundedRectangle(cornerRadius: 5, style: .continuous)
                            .fill(HeadlineStyleTable199.rowDividerInk)
                    )
                    .accessibilityLabel("\(column.header == "TB" ? "Tiebreak" : "Points") \(text)")
            }

        case .finalResult:
            if row.won == true {
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    if !text.isEmpty {
                        Text(text)
                            .font(HeadlineStyleTable199.secondNumbers(.page, prominent: true, scaledSize: secondProminentScaledSize))
                            .foregroundStyle(HeadlineStyleTable199.primaryNumberInk)
                            .lineLimit(1)
                            .minimumScaleFactor(0.75)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Text("\u{2713}")
                        .font(HeadlineStyleTable199.secondNumbers(.page, prominent: true, scaledSize: secondProminentScaledSize * 0.82))
                        .foregroundStyle(HeadlineStyleTable199.winnerTickInk)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .accessibilityLabel(text.isEmpty ? "Won" : "Final \(text), won")
            } else if text.isEmpty {
                Color.clear.frame(height: 1)
            } else {
                let ink = row.role == .draw ? HeadlineStyleTable199.drawInk : (row.won == false ? HeadlineStyleTable199.loserInk : HeadlineStyleTable199.primaryNumberInk)
                Text(text)
                    .font(HeadlineStyleTable199.secondNumbers(.page, prominent: false, scaledSize: secondRegularScaledSize))
                    .foregroundStyle(ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.80)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("Final \(text)")
            }
        }
    }

    // MARK: - Single-Line Team-Coloured Pregame Summary (Rulings 200-B, 213-A, 214-A1)

    private func livePregameSummaryRow(_ summary: EventSportHeadlines12472.LivePregameSummary) -> some View {
        let cappedSummarySize = min(baseQuietSize, stacksRowsVertically ? 20 : 14)
        return LivePregameSummaryRow214A1(
            summary: summary,
            surface: .page,
            colors: colors,
            scaledSize: cappedSummarySize,
            minScale: stacksRowsVertically ? 0.45 : 0.78,
            accessibilityIdentifier: "headline-12472-pregame-summary"
        )
        .background(
            GeometryReader { geo in
                Color.clear.preference(key: LivePregameSummaryHeightPreferenceKey199.self, value: geo.size.height)
            }
        )
    }

    // MARK: - Segmented Bottom Bar

    @ViewBuilder
    private func bottomBarView(_ bar: EventSportHeadlines12472.BottomBar) -> some View {
        switch bar {
        case let .twoWay(awayShare, homeShare, pregameAwayMarker):
            GeometryReader { geo in
                let width = max(geo.size.width, 1)
                let total = max(awayShare + homeShare, 0.0001)
                let normalizedAway = min(max(awayShare / total, 0), 1)
                ZStack(alignment: .leading) {
                    HStack(spacing: 0) {
                        Rectangle()
                            .fill(colors.away)
                            .frame(width: max(width * normalizedAway, 2))
                        Rectangle()
                            .fill(colors.home)
                            .frame(maxWidth: .infinity)
                    }
                    .frame(height: 6)
                    .clipShape(Capsule())

                    if let marker = pregameAwayMarker, marker > 0, marker < 1 {
                        let markerX = min(max(width * marker, 2), max(width - 2, 2))
                        RoundedRectangle(cornerRadius: 1)
                            .fill(HeadlineStyleTable199.primaryNumberInk.opacity(0.85))
                            .frame(width: 2, height: 10)
                            .offset(x: markerX - 1)
                            .accessibilityHidden(true)
                    }
                }
            }
            .frame(height: 10)
            .accessibilityHidden(true)

        case let .threeWay(homeShare, drawShare, awayShare):
            GeometryReader { geo in
                let width = max(geo.size.width, 1)
                let total = max(homeShare + drawShare + awayShare, 0.0001)
                let hFrac = min(max(homeShare / total, 0), 1)
                let dFrac = min(max(drawShare / total, 0), 1)
                HStack(spacing: 1.5) {
                    Rectangle()
                        .fill(colors.home)
                        .frame(width: max(width * hFrac - 1, 2))
                    Rectangle()
                        .fill(HeadlineStyleTable199.drawBarInk)
                        .frame(width: max(width * dFrac - 1, 2))
                    Rectangle()
                        .fill(colors.away)
                        .frame(maxWidth: .infinity)
                }
                .frame(height: 6)
                .clipShape(Capsule())
            }
            .frame(height: 8)
            .accessibilityHidden(true)
        }
    }
}

struct HeadlineMountedKindPreferenceKey199: PreferenceKey {
    static let defaultValue: EventSportHeadlines12472.Kind? = nil
    static func reduce(value: inout EventSportHeadlines12472.Kind?, nextValue: () -> EventSportHeadlines12472.Kind?) {
        value = nextValue() ?? value
    }
}

struct LivePregameSummaryHeightPreferenceKey199: PreferenceKey {
    static let defaultValue: CGFloat? = nil
    static func reduce(value: inout CGFloat?, nextValue: () -> CGFloat?) {
        value = nextValue() ?? value
    }
}
