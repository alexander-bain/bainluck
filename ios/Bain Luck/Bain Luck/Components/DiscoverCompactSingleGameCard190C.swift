import SwiftUI

/// #12616 (Ruling 190-C, 182-A, 187-A, 161-B + Atlas Column Type Spec) — Compact `Size M`
/// Discover single-game card from Atlas's `(a)` sheet on `#12616`.
///
/// Retires the tall empty hero box (`~50%` shorter), renders plain time once on the left
/// with a capsule ONLY for live status (`182-A`), places `Pregame` once as a column header
/// beside `Now` / `Result` with an `18 pt` breathing gutter after `Score` and `10 pt` pair
/// gap between `Pregame` and `Now`, puts `Draw` in the middle on three-way soccer (`187-A`),
/// and omits the probability bar once finished.
struct DiscoverCompactSingleGameCard190CView<ProjectionLines: View, FooterRow: View>: View {
    let event: FeedEventData
    let prematch: PrematchReading?
    let awayColor: Color
    let homeColor: Color
    var usesPictureLayout191A: Bool = false
    var preloadedChartHistory: EventHistoryResponse? = nil
    @ViewBuilder let projectionAndSuspendedLines: () -> ProjectionLines
    @ViewBuilder let footerRow: () -> FooterRow

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    // Unified onto HeadlineStyleTable199 (.card) so team names, scores, and chances
    // share one size and weight family with the event-page headline, feed card, widget, and Watch tile.
    @ScaledMetric(relativeTo: .body) private var compactNameSize: CGFloat = HeadlineStyleTable199.nameBaseSize(.card)
    @ScaledMetric(relativeTo: .caption2) private var headerFontSize: CGFloat = HeadlineStyleTable199.headerBaseSize(.card)
    @ScaledMetric(relativeTo: .body) private var compactScoreSize: CGFloat = HeadlineStyleTable199.secondNumberBaseSize(.card, prominent: false)
    @ScaledMetric(relativeTo: .subheadline) private var compactPregameSize: CGFloat = HeadlineStyleTable199.pregameNumberBaseSize(.card)
    @ScaledMetric(relativeTo: .title3) private var compactLargeSize: CGFloat = HeadlineStyleTable199.nowBaseSize(.card)

    @ScaledMetric(relativeTo: .body) private var scoreColWidth: CGFloat = 42
    @ScaledMetric(relativeTo: .subheadline) private var pregameColWidth: CGFloat = 48
    @ScaledMetric(relativeTo: .title3) private var primaryColWidth: CGFloat = 82
    @State private var measuredContentWidth: CGFloat = 0

    private let scoreToPregameGutter: CGFloat = 12
    private let pregameToPrimaryGap: CGFloat = 14

    private var shortNames: (away: String, home: String) {
        TeamShortName.shortPair(
            away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
    }

    private var showsInlinePregame: Bool {
        if dynamicTypeSize.isAccessibilitySize && event.status == "live" {
            return true
        }
        return CompactGameCard12616.liveInlinePregameFits(
            awayShortName: shortNames.away,
            homeShortName: shortNames.home,
            typeSize: dynamicTypeSize
        )
    }

    private var model: DiscoverSingleGameCard190C.Model {
        DiscoverSingleGameCard190C.build(
            event: event,
            prematch: prematch,
            showsInlinePregame: showsInlinePregame,
            usesPictureLayout: usesPictureLayout191A
        )
    }

    private var effectiveScoreWidth: CGFloat {
        dynamicTypeSize.isAccessibilitySize ? min(scoreColWidth, 62) : min(scoreColWidth, 58)
    }

    private var effectivePregameWidth: CGFloat {
        dynamicTypeSize.isAccessibilitySize ? min(pregameColWidth, 74) : min(pregameColWidth, 66)
    }

    private var effectivePrimaryWidth: CGFloat {
        if model.isFinished {
            return dynamicTypeSize.isAccessibilitySize ? min(scoreColWidth + 10, 64) : min(scoreColWidth + 6, 52)
        }
        return dynamicTypeSize.isAccessibilitySize ? min(primaryColWidth, 96) : min(primaryColWidth, 88)
    }

    private var gapAfterScore: CGFloat {
        model.headers.pregame != nil ? scoreToPregameGutter : pregameToPrimaryGap
    }

    private var trailingColumnsClusterWidth: CGFloat {
        let scoreW = model.headers.score != nil ? effectiveScoreWidth : 0
        let pregameW = model.headers.pregame != nil
            ? effectivePregameWidth + (model.headers.score != nil ? scoreToPregameGutter : 0)
            : 0
        let primaryW = model.headers.primary != nil
            ? effectivePrimaryWidth + (model.headers.pregame != nil
                ? pregameToPrimaryGap
                : (model.headers.score != nil ? gapAfterScore : 0))
            : 0
        return scoreW + pregameW + primaryW
    }

    private func sharedCompactTeamNameFontSize(forRowWidth rowWidth: CGFloat) -> CGFloat {
        let competitorNames = model.rows
            .filter { $0.kind != .draw }
            .map(\.shortName)
        let tickReserve: CGFloat = model.isFinished ? 16 : 0
        let availableWidth = max(rowWidth - 36 - 8 - tickReserve - trailingColumnsClusterWidth, 48)
        return CardTeamNameSizing.sharedWordSafeFontSize(
            names: competitorNames,
            baseSize: min(compactNameSize, 20),
            weight: .bold,
            availableWidth: availableWidth,
            minimumScale: 0.48
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            topHeaderSection

            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(model.rows.enumerated()), id: \.offset) { _, row in
                        accessibilityRowView(row)
                    }
                }
            } else {
                ViewThatFits(in: .horizontal) {
                    compactCompetitorStack(rowWidth: 333, isFallback: false)
                    compactCompetitorStack(rowWidth: 296, isFallback: false)
                    compactCompetitorStack(rowWidth: 264, isFallback: false)
                    compactCompetitorStack(rowWidth: 232, isFallback: true)
                }
            }

            if let bar = model.bar {
                segmentedBarView(bar)
            }

            if let livePregameSummary = model.livePregameSummary {
                LivePregameSummaryRow214A1(
                    summary: livePregameSummary,
                    surface: .card,
                    colors: (away: awayColor, home: homeColor),
                    accessibilityIdentifier: "discover-card-live-pregame-summary"
                )
            }

            if usesPictureLayout191A {
                DiscoverPictureChartPanel191AView(
                    event: event,
                    prematch: prematch,
                    awayColor: awayColor,
                    homeColor: homeColor,
                    preloadedHistory: preloadedChartHistory
                )
            }

            VStack(alignment: .leading, spacing: 6) {
                if let scheduledProjectedLine = model.scheduledProjectedLine {
                    Text(scheduledProjectedLine)
                        .font(HeadlineStyleTable199.quietText(.card, monospacedDigits: true))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)
                }

                projectionAndSuspendedLines()

                footerRow()
            }
        }
        .background(
            GeometryReader { geo in
                Color.clear
                    .onAppear { measuredContentWidth = geo.size.width }
                    .onChange(of: geo.size.width) { _, w in measuredContentWidth = w }
            }
        )
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    // MARK: - Top Row (182-A: plain league + plain time once, capsule ONLY for live)

    @ViewBuilder
    private var topHeaderSection: some View {
        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 6) {
                leagueAndStatusView
                if model.headers.hasAny {
                    HStack {
                        Spacer(minLength: 0)
                        columnHeadersCluster
                    }
                    Rectangle()
                        .fill(Color.primary.opacity(0.08))
                        .frame(height: 0.5)
                }
            }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .center, spacing: 6) {
                    leagueAndStatusInlineView
                    Spacer(minLength: 8)
                    if model.headers.hasAny {
                        columnHeadersCluster
                    }
                }

                VStack(alignment: .leading, spacing: 4) {
                    leagueAndStatusView
                    if model.headers.hasAny {
                        HStack {
                            Spacer(minLength: 0)
                            columnHeadersCluster
                        }
                    }
                }
            }
        }
    }

    private var leagueAndStatusInlineView: some View {
        HStack(spacing: 5) {
            Text(model.leagueName)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondaryReadable)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)

            statusBadgeView(leadingDot: true)
                .fixedSize(horizontal: true, vertical: false)
        }
    }

    private var leagueAndStatusView: some View {
        ViewThatFits(in: .horizontal) {
            leagueAndStatusInlineView

            VStack(alignment: .leading, spacing: 4) {
                Text(model.leagueName)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)

                statusBadgeView(leadingDot: false)
            }
        }
    }

    private func statusBadgeView(leadingDot: Bool) -> some View {
        StatusBadge(
            status: event.status,
            commenceTime: event.commenceTime,
            gameClock: event.espn?.gameClock,
            period: event.espn?.period,
            startIsTbd: event.startIsTbd == true,
            venueClosedNoWinner: event.venueClosedNoWinner == true,
            gameCardPlain182: true,
            gameCardLeadingDot: leadingDot
        )
    }

    private var headerFont: Font {
        let cap: CGFloat = dynamicTypeSize.isAccessibilitySize ? 14.5 : 13
        return HeadlineStyleTable199.headers(.card, scaledSize: min(headerFontSize, cap)).monospacedDigit()
    }

    private var columnHeadersCluster: some View {
        HStack(alignment: .firstTextBaseline, spacing: 0) {
            if let scoreHeader = model.headers.score {
                Text(scoreHeader)
                    .font(headerFont)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(width: effectiveScoreWidth, alignment: .trailing)
            }
            if let pregameHeader = model.headers.pregame {
                Text(pregameHeader)
                    .font(headerFont)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(width: effectivePregameWidth, alignment: .trailing)
                    .padding(.leading, model.headers.score != nil ? scoreToPregameGutter : 0)
            }
            if let primaryHeader = model.headers.primary {
                Text(primaryHeader)
                    .font(headerFont)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(width: effectivePrimaryWidth, alignment: .trailing)
                    .padding(.leading, model.headers.pregame != nil
                        ? pregameToPrimaryGap
                        : (model.headers.score != nil ? gapAfterScore : 0))
            }
        }
    }

    // MARK: - Competitor & 187-A Middle Draw Rows

    private func compactCompetitorStack(rowWidth: CGFloat, isFallback: Bool) -> some View {
        let fontSize = sharedCompactTeamNameFontSize(forRowWidth: rowWidth)
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(model.rows.enumerated()), id: \.offset) { _, row in
                compactRowView(row, nameFontSize: fontSize, preventSingleWordTruncation: !isFallback)
            }
        }
    }

    private func compactRowView(
        _ row: DiscoverSingleGameCard190C.RowModel,
        nameFontSize: CGFloat,
        preventSingleWordTruncation: Bool
    ) -> some View {
        let singleWord = !row.shortName.contains(" ")
        let isLoser = model.isFinished && !row.isWinner && row.isDimmedAfter
        return HStack(alignment: .center, spacing: 8) {
            rowBadgeView(row)

            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(row.shortName)
                    .font(HeadlineStyleTable199.names(.card, isLoser: isLoser, scaledSize: nameFontSize))
                    .foregroundStyle(row.isDimmedAfter ? .secondary : .primary)
                    .lineLimit(singleWord ? 1 : 2)
                    .allowsTightening(true)
                    .fixedSize(horizontal: singleWord && preventSingleWordTruncation, vertical: true)
                if model.isFinished {
                    Text("\u{2713}")
                        .font(HeadlineStyleTable199.secondNumbers(
                            .card,
                            prominent: true,
                            scaledSize: min(nameFontSize, 18) * 0.85
                        ))
                        .foregroundStyle(HeadlineStyleTable199.winnerTickInk)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .opacity(row.isWinner ? 1 : 0)
                        .accessibilityHidden(true)
                }
            }

            Spacer(minLength: 8)

            HStack(alignment: .firstTextBaseline, spacing: 0) {
                if model.headers.score != nil {
                    Text(row.scoreText ?? "")
                        .font(HeadlineStyleTable199.secondNumbers(
                            .card,
                            prominent: model.isFinished && row.isWinner,
                            scaledSize: model.isFinished && row.isWinner ? min(compactLargeSize, 24) : min(compactScoreSize, 20)
                        ))
                        .foregroundStyle(row.isDimmedAfter ? .secondary : .primary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(width: effectiveScoreWidth, alignment: .trailing)
                }

                if model.headers.pregame != nil {
                    let isProjColumn = model.headers.pregame == "Proj."
                    Text(row.pregameText ?? "")
                        .font(HeadlineStyleTable199.secondNumbers(
                            .card,
                            prominent: false,
                            scaledSize: isProjColumn ? min(compactScoreSize, 20) : min(compactPregameSize, 18)
                        ))
                        .foregroundStyle(model.isLive ? Color.primary : DS.textSecondaryReadable)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(width: effectivePregameWidth, alignment: .trailing)
                        .padding(.leading, model.headers.score != nil ? scoreToPregameGutter : 0)
                }

                if model.headers.primary != nil {
                    primaryCellView(row)
                        .frame(width: effectivePrimaryWidth, alignment: .trailing)
                        .padding(.leading, model.headers.pregame != nil
                            ? pregameToPrimaryGap
                            : (model.headers.score != nil ? gapAfterScore : 0))
                }
            }
        }
    }

    private func accessibilityDisplayLabel(for row: DiscoverSingleGameCard190C.RowModel) -> String {
        if row.kind == .draw { return row.fullName }
        return TeamShortName.isCollegeSport(sportKey: event.sport) ? row.shortName : row.fullName
    }

    private var sharedAccessibilityTeamNameFontSize: CGFloat {
        let names = model.rows
            .filter { $0.kind != .draw }
            .map(accessibilityDisplayLabel(for:))
        let contentW = measuredContentWidth > 0 ? measuredContentWidth : 333
        return CardTeamNameSizing.sharedUnboundedWordSafeFontSize(
            names: names,
            baseSize: compactNameSize,
            weight: .bold,
            availableWidth: max(contentW, 120),
            minimumScale: 0.55
        )
    }

    private func accessibilityRowView(_ row: DiscoverSingleGameCard190C.RowModel) -> some View {
        let displayLabel = accessibilityDisplayLabel(for: row)
        let weight: Font.Weight = model.isFinished ? (row.isWinner ? .bold : .medium) : .semibold
        return VStack(alignment: .leading, spacing: 4) {
            Text(displayLabel)
                .font(.system(size: sharedAccessibilityTeamNameFontSize, weight: weight))
                .foregroundStyle(row.isDimmedAfter ? .secondary : .primary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)

            HStack(alignment: .center, spacing: 8) {
                rowBadgeView(row, size: 24)
                Spacer(minLength: 0)
                if model.headers.hasAny {
                    HStack(alignment: .firstTextBaseline, spacing: 0) {
                        accessibilityAlignedCells(row)
                    }
                }
            }
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private func accessibilityAlignedCells(
        _ row: DiscoverSingleGameCard190C.RowModel
    ) -> some View {
        if model.headers.score != nil {
            Text(row.scoreText ?? "")
                .font(HeadlineStyleTable199.secondNumbers(
                    .card,
                    prominent: model.isFinished && row.isWinner,
                    scaledSize: min(compactScoreSize, 22)
                ))
                .foregroundStyle(row.isDimmedAfter ? .secondary : .primary)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
                .frame(width: effectiveScoreWidth, alignment: .trailing)
                .accessibilityLabel(row.scoreText.map { "Score \($0)" } ?? "")
        }
        if model.headers.pregame != nil {
            let isProjColumn = model.headers.pregame == "Proj."
            Text(row.pregameText ?? "")
                .font(HeadlineStyleTable199.secondNumbers(
                    .card,
                    prominent: false,
                    scaledSize: isProjColumn ? min(compactScoreSize, 22) : min(compactPregameSize, 19)
                ))
                .foregroundStyle(model.isLive ? Color.primary : DS.textSecondaryReadable)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
                .frame(width: effectivePregameWidth, alignment: .trailing)
                .padding(.leading, model.headers.score != nil ? scoreToPregameGutter : 0)
                .accessibilityLabel(row.pregameText.map { isProjColumn ? "Projected \($0)" : "Pregame \($0)" } ?? "")
        }
        if let primaryHeader = model.headers.primary {
            primaryCellView(row)
                .frame(width: effectivePrimaryWidth, alignment: .trailing)
                .padding(.leading, model.headers.pregame != nil
                    ? pregameToPrimaryGap
                    : (model.headers.score != nil ? gapAfterScore : 0))
                .accessibilityLabel(accessibilityPrimarySpoken(row, primaryHeader: primaryHeader))
        }
    }

    private func accessibilityPrimarySpoken(
        _ row: DiscoverSingleGameCard190C.RowModel,
        primaryHeader: String
    ) -> String {
        switch row.primaryCell {
        case .probability(let text):
            return "\(primaryHeader) \(text)"
        case .finalScore(let text, let won, _):
            if won {
                return text.map { "Final \($0), won" } ?? "Won"
            }
            return text.map { "Final \($0)" } ?? ""
        case .won(let text):
            return text
        case .settledDash, .none:
            return ""
        }
    }

    @ViewBuilder
    private func rowBadgeView(_ row: DiscoverSingleGameCard190C.RowModel, size: CGFloat = 28) -> some View {
        switch row.kind {
        case .away:
            let avatar = event.avatar(home: false)
            TeamLogoView(
                url: avatar.url,
                teamName: event.awayTeam,
                color: awayColor,
                size: size,
                sportKey: event.sport,
                isPhotograph: avatar.isPhotograph,
                opponentName: event.homeTeam,
                abbreviation: event.awayTeamData?.abbreviation,
                opponentAbbreviation: event.homeTeamData?.abbreviation
            )
        case .home:
            let avatar = event.avatar(home: true)
            TeamLogoView(
                url: avatar.url,
                teamName: event.homeTeam,
                color: homeColor,
                size: size,
                sportKey: event.sport,
                isPhotograph: avatar.isPhotograph,
                opponentName: event.awayTeam,
                abbreviation: event.homeTeamData?.abbreviation,
                opponentAbbreviation: event.awayTeamData?.abbreviation
            )
        case .draw:
            ZStack {
                Circle()
                    .fill(Color.secondary.opacity(0.15))
                    .frame(width: size, height: size)
                Text("\u{2013}")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(DS.textSecondaryReadable)
            }
            .accessibilityHidden(true)
        }
    }

    @ViewBuilder
    private func primaryCellView(_ row: DiscoverSingleGameCard190C.RowModel) -> some View {
        switch row.primaryCell {
        case .probability(let text):
            Text(text)
                .font(HeadlineStyleTable199.now(.card, scaledSize: min(compactLargeSize, 24)))
                .foregroundStyle(sideAccentColor(for: row.kind))
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        case .finalScore(let text, let won, let isDrawOutcome):
            if let text, !text.isEmpty {
                let prominent = won || isDrawOutcome
                Text(text)
                    .font(HeadlineStyleTable199.secondNumbers(
                        .card,
                        prominent: prominent,
                        scaledSize: prominent ? min(compactLargeSize, 24) : min(compactScoreSize, 20)
                    ))
                    .foregroundStyle(prominent ? .primary : .secondary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            } else {
                Text("0")
                    .font(HeadlineStyleTable199.secondNumbers(.card, prominent: false, scaledSize: min(compactScoreSize, 20)))
                    .opacity(0)
                    .accessibilityHidden(true)
            }
        case .won(let text):
            Text(text)
                .font(HeadlineStyleTable199.secondNumbers(.card, prominent: true, scaledSize: min(compactPregameSize, 18)))
                .foregroundStyle(DS.emerald)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        case .settledDash:
            Text(absentProbabilityMarker)
                .font(HeadlineStyleTable199.secondNumbers(.card, prominent: false, scaledSize: min(compactPregameSize, 18)))
                .foregroundStyle(DS.textSecondaryReadable)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        case .none:
            EmptyView()
        }
    }

    private func sideAccentColor(for kind: DiscoverSingleGameCard190C.RowKind) -> Color {
        switch kind {
        case .away: return awayColor
        case .home: return homeColor
        case .draw: return .primary
        }
    }

    // MARK: - Edge-to-Edge Segmented Bar (187-A Draw in Middle)

    private func segmentedBarView(_ bar: DiscoverSingleGameCard190C.BarSegments) -> some View {
        GeometryReader { geo in
            let gap: CGFloat = 2
            ZStack(alignment: .leading) {
                HStack(spacing: gap) {
                    if let drawShare = bar.drawShare, drawShare > 0 {
                        let usableWidth = max(12, geo.size.width - gap * 2)
                        RoundedRectangle(cornerRadius: 2.5)
                            .fill(awayColor)
                            .frame(width: max(4, usableWidth * bar.awayShare))
                        RoundedRectangle(cornerRadius: 2.5)
                            .fill(Color.secondary.opacity(0.32))
                            .frame(width: max(4, usableWidth * drawShare))
                        RoundedRectangle(cornerRadius: 2.5)
                            .fill(homeColor)
                            .frame(width: max(4, usableWidth * bar.homeShare))
                    } else {
                        let usableWidth = max(8, geo.size.width - gap)
                        RoundedRectangle(cornerRadius: 2.5)
                            .fill(bar.awayIsWithheld ? Color.secondary.opacity(0.25) : awayColor)
                            .frame(width: max(4, usableWidth * bar.awayShare))
                        RoundedRectangle(cornerRadius: 2.5)
                            .fill(homeColor)
                            .frame(width: max(4, usableWidth * bar.homeShare))
                    }
                }
                .frame(width: geo.size.width, height: 6)

                if let notch = bar.pregameNotch,
                   !bar.awayIsWithheld,
                   notch.isFinite, notch > 0, notch < 1,
                   geo.size.width > 8 {
                    let clampedX = min(max(geo.size.width * notch, 3), geo.size.width - 3)
                    ZStack {
                        RoundedRectangle(cornerRadius: 1)
                            .fill(Color.white)
                            .frame(width: 4, height: 8)
                        RoundedRectangle(cornerRadius: 0.75)
                            .fill(Color.primary.opacity(0.72))
                            .frame(width: 1.5, height: 8)
                    }
                    .position(x: clampedX, y: 3)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
                }
            }
        }
        .frame(height: 6)
        .accessibilityHidden(true)
    }
}
