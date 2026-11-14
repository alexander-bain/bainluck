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

    // Atlas Column Type Spec: one tabular SF Pro digit family at three gentle optical steps
    // (`20 pt Bold` primary, `17 pt Semibold` live score, `15 pt Regular` pregame, `10.5 pt Semibold` headers).
    @ScaledMetric(relativeTo: .body) private var compactNameSize: CGFloat = 17
    @ScaledMetric(relativeTo: .caption2) private var headerFontSize: CGFloat = 10.5
    @ScaledMetric(relativeTo: .body) private var compactScoreSize: CGFloat = 17
    @ScaledMetric(relativeTo: .subheadline) private var compactPregameSize: CGFloat = 15
    @ScaledMetric(relativeTo: .title3) private var compactLargeSize: CGFloat = 20

    @ScaledMetric(relativeTo: .body) private var scoreColWidth: CGFloat = 46
    @ScaledMetric(relativeTo: .subheadline) private var pregameColWidth: CGFloat = 58
    @ScaledMetric(relativeTo: .title3) private var primaryColWidth: CGFloat = 68

    private let scoreToPregameGutter: CGFloat = 18
    private let pregameToPrimaryGap: CGFloat = 10

    private var shortNames: (away: String, home: String) {
        TeamShortName.shortPair(
            away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
    }

    private var showsInlinePregame: Bool {
        CompactGameCard12616.liveInlinePregameFits(
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
        min(scoreColWidth, 54)
    }

    private var effectivePregameWidth: CGFloat {
        min(pregameColWidth, 66)
    }

    private var effectivePrimaryWidth: CGFloat {
        min(primaryColWidth, 78)
    }

    private var gapAfterScore: CGFloat {
        model.headers.pregame != nil ? scoreToPregameGutter : pregameToPrimaryGap
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            topHeaderSection

            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(model.rows.enumerated()), id: \.offset) { _, row in
                    if dynamicTypeSize.isAccessibilitySize {
                        accessibilityRowView(row)
                    } else {
                        compactRowView(row)
                    }
                }
            }

            if usesPictureLayout191A {
                DiscoverPictureChartPanel191AView(
                    event: event,
                    prematch: prematch,
                    awayColor: awayColor,
                    homeColor: homeColor,
                    preloadedHistory: preloadedChartHistory
                )
            } else if let bar = model.bar {
                segmentedBarView(bar)
            }

            VStack(alignment: .leading, spacing: 6) {
                if let scheduledProjectedLine = model.scheduledProjectedLine {
                    Text(scheduledProjectedLine)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)
                }

                projectionAndSuspendedLines()

                footerRow()
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    // MARK: - Top Row (182-A: plain league + plain time once, capsule ONLY for live)

    @ViewBuilder
    private var topHeaderSection: some View {
        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 4) {
                leagueAndStatusView
            }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .center, spacing: 6) {
                    leagueAndStatusView
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

    private var leagueAndStatusView: some View {
        HStack(spacing: 5) {
            Text(model.leagueName)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondaryReadable)
                .fixedSize(horizontal: !dynamicTypeSize.isAccessibilitySize, vertical: true)

            StatusBadge(
                status: event.status,
                commenceTime: event.commenceTime,
                gameClock: event.espn?.gameClock,
                period: event.espn?.period,
                startIsTbd: event.startIsTbd == true,
                venueClosedNoWinner: event.venueClosedNoWinner == true,
                gameCardPlain182: true,
                gameCardLeadingDot: true
            )
        }
    }

    private var headerFont: Font {
        .system(size: min(headerFontSize, 13), weight: .semibold).monospacedDigit()
    }

    private var columnHeadersCluster: some View {
        HStack(alignment: .firstTextBaseline, spacing: 0) {
            if let scoreHeader = model.headers.score {
                Text(scoreHeader.uppercased())
                    .font(headerFont)
                    .tracking(0.45)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                    .frame(width: effectiveScoreWidth, alignment: .trailing)
            }
            if let pregameHeader = model.headers.pregame {
                Text(pregameHeader.uppercased())
                    .font(headerFont)
                    .tracking(0.45)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                    .frame(width: effectivePregameWidth, alignment: .trailing)
                    .padding(.leading, model.headers.score != nil ? scoreToPregameGutter : 0)
            }
            if let primaryHeader = model.headers.primary {
                Text(primaryHeader.uppercased())
                    .font(headerFont)
                    .tracking(0.45)
                    .foregroundStyle(model.isLive || model.isFinished ? Color.primary.opacity(0.78) : DS.textSecondaryReadable)
                    .lineLimit(1)
                    .frame(width: effectivePrimaryWidth, alignment: .trailing)
                    .padding(.leading, model.headers.pregame != nil
                        ? pregameToPrimaryGap
                        : (model.headers.score != nil ? gapAfterScore : 0))
            }
        }
    }

    // MARK: - Competitor & 187-A Middle Draw Rows

    private func compactRowView(_ row: DiscoverSingleGameCard190C.RowModel) -> some View {
        let singleWord = !row.shortName.contains(" ")
        return HStack(alignment: .center, spacing: 8) {
            rowBadgeView(row)

            Text(row.shortName)
                .font(.system(size: min(compactNameSize, 20), weight: model.isFinished ? (row.isWinner ? .bold : .medium) : .semibold))
                .foregroundStyle(row.isDimmedAfter ? .secondary : .primary)
                .lineLimit(singleWord ? 1 : 2)
                .minimumScaleFactor(singleWord ? 0.82 : 0.88)
                .fixedSize(horizontal: false, vertical: !singleWord)

            Spacer(minLength: 8)

            HStack(alignment: .firstTextBaseline, spacing: 0) {
                if model.headers.score != nil {
                    Text(row.scoreText ?? "")
                        .font(.system(size: min(compactScoreSize, 20), weight: .semibold).monospacedDigit())
                        .foregroundStyle(row.isDimmedAfter ? .secondary : .primary)
                        .lineLimit(1)
                        .frame(width: effectiveScoreWidth, alignment: .trailing)
                }

                if model.headers.pregame != nil {
                    Text(row.pregameText ?? "")
                        .font(.system(size: min(compactPregameSize, 18), weight: .regular).monospacedDigit())
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
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

    private func accessibilityRowView(_ row: DiscoverSingleGameCard190C.RowModel) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .top, spacing: 8) {
                rowBadgeView(row)
                    .padding(.top, 3)
                Text(row.fullName)
                    .font(.body.weight(model.isFinished ? (row.isWinner ? .bold : .medium) : .semibold))
                    .foregroundStyle(row.isDimmedAfter ? .secondary : .primary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 14) {
                    accessibilityRowValues(row, singleLine: true)
                }
                VStack(alignment: .leading, spacing: 2) {
                    accessibilityRowValues(row, singleLine: false)
                }
            }
        }
    }

    @ViewBuilder
    private func accessibilityRowValues(
        _ row: DiscoverSingleGameCard190C.RowModel,
        singleLine: Bool
    ) -> some View {
        if let scoreText = row.scoreText {
            Text("Score \(scoreText)")
                .font(.subheadline.weight(.semibold).monospacedDigit())
                .foregroundStyle(row.isDimmedAfter ? .secondary : .primary)
                .fixedSize(horizontal: singleLine, vertical: true)
        }
        if let pregameText = row.pregameText {
            Text("Pregame \(pregameText)")
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(DS.textSecondaryReadable)
                .fixedSize(horizontal: singleLine, vertical: true)
        }
        switch row.primaryCell {
        case .probability(let text):
            Text("Now \(text)")
                .font(.headline.weight(.bold).monospacedDigit())
                .foregroundStyle(sideAccentColor(for: row.kind))
                .fixedSize(horizontal: singleLine, vertical: true)
        case .won(let text):
            Text(text)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(DS.emerald)
                .fixedSize(horizontal: singleLine, vertical: true)
        case .settledDash, .none:
            EmptyView()
        }
    }

    @ViewBuilder
    private func rowBadgeView(_ row: DiscoverSingleGameCard190C.RowModel) -> some View {
        switch row.kind {
        case .away:
            let avatar = event.avatar(home: false)
            TeamLogoView(
                url: avatar.url,
                teamName: event.awayTeam,
                color: awayColor,
                size: 28,
                sportKey: event.sport,
                isPhotograph: avatar.isPhotograph,
                opponentName: event.homeTeam
            )
        case .home:
            let avatar = event.avatar(home: true)
            TeamLogoView(
                url: avatar.url,
                teamName: event.homeTeam,
                color: homeColor,
                size: 28,
                sportKey: event.sport,
                isPhotograph: avatar.isPhotograph,
                opponentName: event.awayTeam
            )
        case .draw:
            ZStack {
                Circle()
                    .fill(Color.secondary.opacity(0.15))
                    .frame(width: 28, height: 28)
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
                .font(.system(size: min(compactLargeSize, 24), weight: .bold).monospacedDigit())
                .foregroundStyle(sideAccentColor(for: row.kind))
                .lineLimit(1)
        case .won(let text):
            Text(text)
                .font(.system(size: min(compactPregameSize, 18), weight: .bold))
                .foregroundStyle(DS.emerald)
                .lineLimit(1)
        case .settledDash:
            Text(absentProbabilityMarker)
                .font(.system(size: min(compactPregameSize, 18), weight: .regular).monospacedDigit())
                .foregroundStyle(DS.textSecondaryReadable)
                .lineLimit(1)
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
        }
        .frame(height: 5)
        .accessibilityHidden(true)
    }
}
