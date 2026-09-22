import SwiftUI

// The palette, the emoji ladder and the hero backdrop used to be declared here
// as `private` copies of the Discover card's — under a comment that called them
// "shared with Discover card", which they were not. All three now come from
// `Utilities/DiscoverCardVisuals.swift`; see `FuturesHero` for what the second
// copy cost (#4111).

// MARK: - Sort

private enum FuturesSortField: String, CaseIterable {
    case probability = "Probability"
    case change = "24h Change"
    case name = "Name"
}

// MARK: - One decision per market

/// The whole percent this page prints for each outcome, keyed by outcome id.
///
/// #8097. Three renderers on this page rounded a probability on their own — the
/// share sentence, the 52pt hero numeral, and every row — so a two-outcome
/// complement pair quoted on the venues' half-cent grid printed `60%` and `41%`
/// in one frame. Measured on production 2026-09-22: **6,743 open two-outcome
/// complement markets sit exactly on the `.5` boundary, 227 of them tier 1** —
/// "Set 2 Winner: Elise Mertens vs Barbora Krejcikova" at `59.5 / 40.5` is one.
/// It is #8035's defect one tap deeper: that ship fixed the Discover card and the
/// image it shares, and a reader who tapped the fixed card landed here on 101.
///
/// ## The order this is decided in is NOT the order the reader sees
///
/// `renderedCardPercents` takes SERVED order and treats index 0 as the headline —
/// the number that survives untouched, so the derived point lands on the side
/// nobody is quoting. This page lets the reader re-sort the table by name, by
/// 24-hour change, and in either direction. Deciding over the DISPLAYED order
/// would therefore let the printed numbers change when a reader sorts by name and
/// back — the same question answered two ways by a control that is supposed to
/// reorder rows, not reprice them. So the decision is taken over probability-
/// descending order and looked up by identity, and the sort moves rows only.
///
/// Ties are broken by id so the headline is stable across reloads rather than
/// left to `sorted(by:)`, which is not guaranteed stable.
nonisolated func futuresDetailRenderedPercents(_ outcomes: [FuturesOutcome]) -> [Int: Int] {
    let headlineOrder = outcomes.sorted { a, b in
        let lhs = a.probability ?? -1
        let rhs = b.probability ?? -1
        if lhs != rhs { return lhs > rhs }
        return a.id < b.id
    }
    let printed = renderedCardPercents(headlineOrder.map(\.probability))
    var byOutcomeId: [Int: Int] = [:]
    for (index, outcome) in headlineOrder.enumerated() {
        guard printed.indices.contains(index), let percent = printed[index] else { continue }
        byOutcomeId[outcome.id] = percent
    }
    return byOutcomeId
}

// MARK: - View

struct FuturesDetailView: View {
    private let marketId: Int
    @StateObject private var viewModel: FuturesDetailViewModel
    @State private var sortField: FuturesSortField = .probability
    @State private var sortAscending = false
    @State private var showAllOutcomes = false

    init(marketId: Int) {
        self.marketId = marketId
        _viewModel = StateObject(wrappedValue: FuturesDetailViewModel(marketId: marketId))
    }

    private var shareMessage: String {
        guard let market = viewModel.market else { return "Check this out on Bain Luck" }
        let leader = market.outcomes.max(by: { ($0.probability ?? 0) < ($1.probability ?? 0) })
        if let leader, let prob = leader.probability {
            // The sentence quotes the same integer the hero and the leader row
            // print. Rounding it here again is how a share read "60%" off a page
            // that said 59% — and the share is the copy that leaves the app.
            let percent = futuresDetailRenderedPercents(market.outcomes)[leader.id]
                ?? renderedPercent(prob)
                ?? Int((prob * 100).rounded())
            return "\(leader.name) at \(percent)% — \(market.name) on Bain Luck"
        }
        return "\(market.name) on Bain Luck"
    }

    /// Both share buttons on this page — toolbar and hero — record the same
    /// `futures_detail` source on purpose: they share the same market and the
    /// same page, and splitting them would ask a reader of the table to care
    /// about a placement decision rather than a surface. #5525.
    private func recordShareOpened() {
        ShareInstrumentation.recordShareOpened(
            itemType: "futures",
            itemId: String(marketId),
            itemName: viewModel.market?.name,
            // `llmSportCategory` alone, lower-cased, because that is exactly what
            // `DiscoverCategory.of` sends for this same market from a feed card.
            // Falling back to `market.category` here would put a share of one
            // market in two buckets depending on which button was pressed.
            category: viewModel.market?.llmSportCategory?.lowercased(),
            surface: .futuresDetail
        )
    }

    var body: some View {
        Group {
            if viewModel.loading {
                ProgressView()
            } else if let error = viewModel.error, viewModel.market == nil {
                ContentUnavailableView(
                    "Error",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else if let market = viewModel.market {
                ScrollView {
                    VStack(spacing: 0) {
                        // Hero section (matches Discover card visual quality)
                        heroSection(market)

                        VStack(spacing: 20) {
                            // Hook description (journalist-style blurb)
                            if let hook = market.hookDescription, !hook.isEmpty {
                                Text(hook)
                                    .font(.system(size: 15))
                                    .foregroundStyle(DS.textSecondary)
                                    .lineSpacing(4)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(16)
                                    .background(DS.cardBg)
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 12)
                                            .stroke(DS.border, lineWidth: 0.5)
                                    )
                            }

                            // Market metadata (status, outcomes, dates, bookmakers)
                            metadataSection(market)

                            // Probability evolution chart
                            if market.outcomes.count >= 1 {
                                EvolutionChartView(
                                    marketId: marketId,
                                    hours: 168,
                                    tournamentStart: golfTournamentStart(market),
                                    tournamentEnd: golfTournamentEnd(market)
                                )
                            }

                            outcomesSection(market)
                        }
                        .padding()
                    }
                    #if os(macOS)
                    .frame(maxWidth: 1000)
                    #else
                    .frame(maxWidth: 700)
                    #endif
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .navigationTitle("Market Details")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                HStack(spacing: 4) {
                    ShareLink(
                        item: URL(string: futuresShareURL(marketId, style: .nativeCard)) ?? bainLuckFallbackURL,
                        subject: Text(viewModel.market?.name ?? "Bain Luck"),
                        message: Text(shareMessage)
                    ) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.system(size: 14))
                    }
                    .recordsShareOpened { recordShareOpened() }
                    PinButton(type: "future", id: marketId)
                }
            }
        }
        .task {
            await viewModel.load()
            if let market = viewModel.market {
                AnalyticsService.trackScreen(name: "futures_detail", type: "futures_detail")
                AnalyticsService.trackFuturesDetailView(marketId: marketId, category: market.category)
            }
        }
        .refreshable {
            await viewModel.load()
        }
    }

    // MARK: - Hero Section

    private func heroSection(_ market: FuturesMarketDetail) -> some View {
        let leader = market.outcomes.max(by: { ($0.probability ?? 0) < ($1.probability ?? 0) })
        let isResolved = market.status == "resolved"
        // One decision for the whole market, shared with the rows below and the
        // share sentence above (#8097).
        let heroPercent = leader.flatMap { futuresDetailRenderedPercents(market.outcomes)[$0.id] }

        // #7074, the second instance. The Discover card had this exact shape — a
        // backdrop pinned to a height, a sibling overlay free to exceed it, and a
        // `ZStack` that takes the taller — and it drew its own pills off the top
        // of its own photograph on Alex's phone. This hero is the same two
        // heights with a larger floor and MORE overlay: the pill row here can
        // carry a RESOLVED badge, and the content below the 52pt numeral can
        // carry a winner row the card has no equivalent of. A bigger floor is
        // later, not never. Backdrop is the content's background; 220 is a floor.
        return VStack(alignment: .leading, spacing: 10) {
            // Top row: category pill + status badges
            HStack {
                if let category = market.llmSportCategory {
                    // #5723: `.uppercased()` on the raw key put the
                    // underscore on the hero — a table-tennis page's pill
                    // read "TABLE_TENNIS". The four Discover cards already
                    // upper-case the shared rule's output; this is the same
                    // form, so the pill and the card agree.
                    Text(sportCategoryDisplayName(category).uppercased())
                        .font(.system(size: 9, weight: .heavy))
                        .tracking(0.8)
                        .foregroundStyle(.white.opacity(0.78))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(.black.opacity(0.24), in: Capsule())
                }
                Spacer()
                if isResolved {
                    Text("RESOLVED")
                        .font(.system(size: 9, weight: .heavy))
                        .tracking(0.8)
                        .foregroundStyle(.white.opacity(0.78))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(.black.opacity(0.24), in: Capsule())
                }
                if let source = market.source, let label = sourceLabel(source) {
                    Text(label.uppercased())
                        .font(.system(size: 9, weight: .heavy))
                        .tracking(0.8)
                        .foregroundStyle(.white.opacity(0.78))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(.black.opacity(0.24), in: Capsule())
                }
            }

            Spacer(minLength: 16)

            // Probability + movement
            if let leader, let prob = leader.probability {
                HStack(alignment: .bottom, spacing: 10) {
                    // #5899: the 52pt figure said `0%` for a leader the venue
                    // prices at 0.05%, three scrolls above `<1%` on every
                    // other row of the same market.
                    Text("\(percentNumber(prob * 100, renderedPercent: heroPercent))%")
                        .font(.system(size: 52, weight: .black).monospacedDigit())
                        .minimumScaleFactor(0.76)
                        .foregroundStyle(.white)
                        .shadow(color: .black.opacity(0.25), radius: 8, x: 0, y: 3)

                    detailMovementBadge(leader.probabilityChange24h)
                        .padding(.bottom, 8)
                }

                Text(leader.name)
                    .font(.headline.weight(.bold))
                    .foregroundStyle(.white.opacity(0.92))
                    .lineLimit(3)
                    .minimumScaleFactor(0.92)
                    .fixedSize(horizontal: false, vertical: true)

                if leader.isWinner == true {
                    Text("Winner")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(DS.emerald.opacity(0.6), in: Capsule())
                }
            }

            // Market name — larger and bolder
            Text(market.name)
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(.white)
                .lineLimit(4)
                .fixedSize(horizontal: false, vertical: true)

            // Share button
            ShareLink(
                item: URL(string: futuresShareURL(marketId, style: .nativeCard)) ?? bainLuckFallbackURL,
                subject: Text(market.name),
                message: Text(shareMessage)
            ) {
                Label("Share", systemImage: "square.and.arrow.up")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(.white.opacity(0.20), in: Capsule())
            }
            .recordsShareOpened { recordShareOpened() }
            .padding(.top, 2)
        }
        .padding(14)
        .frame(
            maxWidth: .infinity,
            minHeight: FuturesHero.detailPageMinimumHeight,
            alignment: .bottomLeading
        )
        .background { heroBackground(market: market) }
        .clipShape(RoundedRectangle(cornerRadius: 18))
    }

    private func heroBackground(market: FuturesMarketDetail) -> some View {
        FuturesHeroBackground(imageURL: market.imageUrl, category: market.llmSportCategory)
    }

    /// #6931: the arrow carries the direction, so the number is a magnitude — and
    /// it is the SHARED magnitude. This badge used to round to an integer while the
    /// chart's participant table three inches below drew the same field to one
    /// decimal: `0.005` printed `↑1%` up here and `+0.5%` down there, in one frame.
    /// The gate is `abs >= 0.005`, so the doubling landed on the smallest move the
    /// badge is ever allowed to show.
    ///
    /// The gate and the string are both `futuresHeroMoveText`'s, so a test asserts
    /// what this badge says instead of scanning for how it says it.
    @ViewBuilder
    private func detailMovementBadge(_ change: Double?) -> some View {
        if let m = change, let text = futuresHeroMoveText(m) {
            let up = m > 0
            HStack(spacing: 2) {
                Image(systemName: up ? "arrow.up" : "arrow.down")
                    .font(.system(size: 7, weight: .black))
                Text(text)
                    .font(.system(size: 10, weight: .bold).monospacedDigit())
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background((up ? DS.emerald : DS.danger).opacity(0.5))
            .clipShape(Capsule())
        }
    }

    private func sourceLabel(_ source: String) -> String? {
        SourceLabels.label(for: source)
    }

    // MARK: - Metadata Section

    private func metadataSection(_ market: FuturesMarketDetail) -> some View {
        let isResolved = market.status == "resolved"

        return VStack(alignment: .leading, spacing: 12) {
            if let desc = market.description, !desc.isEmpty {
                Text(desc)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
            }

            // Info rows — structured vertical layout for clarity
            VStack(alignment: .leading, spacing: 8) {
                // Status row
                if let status = market.status {
                    HStack(spacing: 6) {
                        Image(systemName: "circle.fill")
                            .font(.system(size: 6))
                            .foregroundStyle(
                                isResolved ? DS.textMuted :
                                (status == "active" || status == "open") ? DS.emerald : DS.textMuted
                            )
                        Text("Status")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        Text(status.capitalized)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(
                                isResolved ? DS.textMuted :
                                (status == "active" || status == "open") ? DS.emerald : DS.textSecondary
                            )
                    }
                }

                // Source row
                if let source = market.source {
                    HStack(spacing: 6) {
                        Image(systemName: "building.2")
                            .font(.system(size: 9))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 6, alignment: .center)
                        Text("Source")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        SourceChip(source: source)
                    }
                }

                // Outcomes count
                HStack(spacing: 6) {
                    Image(systemName: "list.bullet")
                        .font(.system(size: 9))
                        .foregroundStyle(DS.textMuted)
                        .frame(width: 6, alignment: .center)
                    Text("Outcomes")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(DS.textMuted)
                    Text("\(market.outcomes.count)")
                        .font(.system(size: 12, weight: .semibold, design: .monospaced))
                        .foregroundStyle(DS.textSecondary)
                }

                // Commence time
                if let commence = market.commenceTime, let date = commence.asDate {
                    HStack(spacing: 6) {
                        Image(systemName: "calendar")
                            .font(.system(size: 9))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 6, alignment: .center)
                        Text("Starts")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        Text(date, format: .dateTime.month(.abbreviated).day().year())
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .foregroundStyle(DS.textSecondary)
                    }
                }

                // Resolution date — a "by end of <period>" deadline is a CALENDAR
                // DATE serialised as UTC midnight, and localising it printed the
                // day before for every reader west of UTC (#4081: this row read
                // "Resolves Dec 30, 2026" on a market resolving 2026-12-31). A
                // real intraday deadline is still an instant and still local;
                // `CalendarDeadline` is what tells them apart.
                if let text = CalendarDeadline.format(market.resolutionDate, style: .monthDayYear) {
                    HStack(spacing: 6) {
                        Image(systemName: "flag.checkered")
                            .font(.system(size: 9))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 6, alignment: .center)
                        Text("Resolves")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        Text(text)
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .foregroundStyle(DS.textSecondary)
                    }
                } else if let resolution = market.resolutionDate {
                    // Fallback: show the RelativeTimeText if asDate parsing fails
                    HStack(spacing: 6) {
                        Image(systemName: "flag.checkered")
                            .font(.system(size: 9))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 6, alignment: .center)
                        Text("Resolves")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        RelativeTimeText(dateString: resolution)
                    }
                }

                // Last updated — the age of the PRICES this page draws, never
                // the moment the market ROW was touched (#6018; the reasoning,
                // the production measurements and the floor-not-ceiling rule
                // are in `Utilities/FuturesPriceAge`). `nil` renders nothing:
                // there is no fall back to `market.updatedAt`, which is the
                // wrong clock in both directions.
                if let date = FuturesPriceAge.pricesAsOf(market.outcomes) {
                    HStack(spacing: 6) {
                        Image(systemName: "clock")
                            .font(.system(size: 9))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 6, alignment: .center)
                        Text("Updated")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        Text(date, format: .dateTime.month(.abbreviated).day().hour().minute())
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .foregroundStyle(DS.textMuted)
                    }
                }
            }

            // Where the probabilities came from. The noun follows what the sources
            // actually ARE — a model is named, not counted as a sportsbook (#4135).
            if let attribution = SourceLabels.attribution(for: market.bookmakers ?? []) {
                let chips = SourceLabels.sportsbookChips(for: market.bookmakers ?? [])
                VStack(alignment: .leading, spacing: 6) {
                    Divider()
                        .overlay(DS.border)
                    Text(attribution)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(DS.textMuted)
                    if !chips.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                // Keyed by position, not by name: two keys can map
                                // to one brand (`caesars`, `williamhill_us`), and a
                                // duplicated ForEach id is undefined behaviour.
                                ForEach(Array(chips.enumerated()), id: \.offset) { _, name in
                                    Text(name)
                                        .font(.system(size: 10, weight: .medium))
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 3)
                                        .background(DS.trackBg)
                                        .clipShape(Capsule())
                                        .foregroundStyle(DS.textSecondary)
                                }
                            }
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
    }

    // MARK: - Category Color

    private func categoryColor(_ market: FuturesMarketDetail) -> Color {
        switch market.llmSportCategory?.lowercased() {
        case "basketball": return DS.amber
        case "football": return DS.emerald
        case "baseball": return DS.danger
        case "hockey": return DS.blue
        case "soccer": return DS.emerald
        case "golf": return DS.emerald
        case "tennis": return DS.amber
        case "mma", "boxing": return DS.danger
        case "politics": return DS.purple
        case "entertainment": return Color(red: 0.75, green: 0.15, blue: 0.83)
        case "crypto": return DS.amber
        default: return DS.blue
        }
    }

    // MARK: - Outcomes

    private func outcomesSection(_ market: FuturesMarketDetail) -> some View {
        let color = categoryColor(market)
        let sorted = sortedOutcomes(market.outcomes)
        // Decided over the SERVED field, not `sorted` — re-sorting the table must
        // move rows without repricing them (#8097).
        let percents = futuresDetailRenderedPercents(market.outcomes)
        let displayed = showAllOutcomes ? sorted : Array(sorted.prefix(25))
        let hasMore = sorted.count > 25

        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "chart.bar.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(DS.textMuted)
                Text("All Outcomes")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(DS.textPrimary)
                Spacer()
                if hasMore {
                    Button(showAllOutcomes ? "Show less" : "Show all \(sorted.count)") {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showAllOutcomes.toggle()
                        }
                    }
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(DS.emerald)
                }
            }

            // Sort controls
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(FuturesSortField.allCases, id: \.self) { field in
                        sortChip(field)
                    }
                }
            }

            ForEach(Array(displayed.enumerated()), id: \.element.id) { index, outcome in
                outcomeRow(
                    outcome,
                    rank: index + 1,
                    color: color,
                    leaderId: sorted.first?.id,
                    percent: percents[outcome.id]
                )
                if index < displayed.count - 1 {
                    Divider()
                        .overlay(DS.border)
                }
            }

            if hasMore && !showAllOutcomes {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showAllOutcomes = true
                    }
                } label: {
                    Text("Show \(sorted.count - 25) more outcomes")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(DS.textSecondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                }
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(DS.border, lineWidth: 1)
                )
            }
        }
        .padding(16)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
    }

    private func sortChip(_ field: FuturesSortField) -> some View {
        let isActive = sortField == field
        return Button {
            if sortField == field {
                sortAscending.toggle()
            } else {
                sortField = field
                sortAscending = field == .name
            }
        } label: {
            HStack(spacing: 3) {
                Text(field.rawValue)
                    .font(.system(size: 11, weight: .medium))
                if isActive {
                    Image(systemName: sortAscending ? "chevron.up" : "chevron.down")
                        .font(.system(size: 8, weight: .bold))
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(isActive ? DS.emerald.opacity(0.12) : DS.trackBg)
            .foregroundStyle(isActive ? DS.emerald : DS.textSecondary)
            .clipShape(Capsule())
        }
    }

    private func sortedOutcomes(_ outcomes: [FuturesOutcome]) -> [FuturesOutcome] {
        outcomes.sorted { a, b in
            let comparison: ComparisonResult
            switch sortField {
            case .probability:
                comparison = compareOptionalDoubles(a.probability, b.probability)
            case .change:
                comparison = compareOptionalDoubles(a.probabilityChange24h, b.probabilityChange24h)
            case .name:
                comparison = a.name.localizedCompare(b.name)
            }

            if comparison != .orderedSame {
                return sortAscending ? comparison == .orderedAscending : comparison == .orderedDescending
            }

            let nameComparison = a.name.localizedCompare(b.name)
            if nameComparison != .orderedSame {
                return nameComparison == .orderedAscending
            }
            return a.id < b.id
        }
    }

    private func compareOptionalDoubles(_ lhs: Double?, _ rhs: Double?) -> ComparisonResult {
        switch (lhs, rhs) {
        case let (lhs?, rhs?):
            if lhs < rhs { return .orderedAscending }
            if lhs > rhs { return .orderedDescending }
            return .orderedSame
        case (.some, .none):
            return .orderedDescending
        case (.none, .some):
            return .orderedAscending
        case (.none, .none):
            return .orderedSame
        }
    }

    /// `percent` is the card-level decision for THIS outcome (#8097). It is the
    /// only thing printed; `probability` still drives the bar and the colour,
    /// because a length and a hue are not printed numbers and moving them by up
    /// to half a point would buy a reader nothing.
    private func outcomeRow(
        _ outcome: FuturesOutcome,
        rank: Int,
        color: Color,
        leaderId: Int?,
        percent: Int?
    ) -> some View {
        let isLeader = outcome.id == leaderId
        let probPct = (outcome.probability ?? 0) * 100

        return VStack(spacing: 6) {
            HStack(alignment: .top) {
                // Rank number
                Text("#\(rank)")
                    .font(.system(size: 13, weight: .semibold, design: .monospaced))
                    .foregroundStyle(isLeader ? DS.amber : DS.textMuted)
                    .frame(width: 30, alignment: .leading)

                // Rank change indicator
                if let rankChange = outcome.rankChange24h, rankChange != 0 {
                    HStack(spacing: 1) {
                        Image(systemName: rankChange < 0 ? "arrow.up" : "arrow.down")
                            .font(.system(size: 7))
                        Text("\(abs(rankChange))")
                            .font(.system(size: 9, weight: .medium))
                    }
                    .foregroundStyle(rankChange < 0 ? DS.emerald : DS.danger)
                    .frame(width: 24, alignment: .leading)
                } else {
                    Spacer().frame(width: 24)
                }

                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text(outcome.name)
                            .font(.system(size: 15, weight: isLeader ? .semibold : .medium))
                            .foregroundStyle(DS.textPrimary)
                        if outcome.isWinner == true {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 13))
                                .foregroundStyle(DS.emerald)
                        }
                    }

                    HStack(spacing: 8) {
                        // L2-48: American moneyline removed — probability only
                        // (no-odds thesis: "60% vs 40%", never "-150/+130").
                        // 24h movement via DeltaBadge
                        if let change = outcome.probabilityChange24h, abs(change) >= 0.005 {
                            DeltaBadge(value: change * 100)
                        }
                        if let opening = outcome.openingProbability, let current = outcome.probability {
                            let diff = current - opening
                            if abs(diff) >= 0.005 {
                                Text("from \(formatProbability(opening))")
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(DS.textMuted)
                            }
                        }
                    }
                }

                Spacer()

                // Lead probability via ProbabilityNumber
                if let prob = outcome.probability {
                    if isLeader {
                        ProbabilityNumber(
                            value: prob * 100,
                            size: 28,
                            color: DS.probColor(prob * 100),
                            renderedPercent: percent
                        )
                    } else {
                        Text(formatProbability(prob, renderedPercent: percent))
                            .font(.system(size: 18, weight: .semibold, design: .monospaced))
                            .foregroundStyle(DS.probColor(probPct))
                    }
                }
            }

            // Probability bar via DSProbabilityBar
            if outcome.probability != nil {
                DSProbabilityBar(
                    value: probPct,
                    maxValue: 100,
                    height: 5,
                    color: isLeader ? color : color.opacity(0.6)
                )
            }
        }
        .padding(.vertical, 6)
    }

    // MARK: - Golf Tournament Dates

    /// Return commence_time as tournament start for golf markets (used for round markers).
    private func golfTournamentStart(_ market: FuturesMarketDetail) -> String? {
        guard market.llmSportCategory?.lowercased() == "golf" else { return nil }
        return market.commenceTime
    }

    /// Derive tournament end from commence_time + 4 days for golf.
    /// Returns nil for non-golf markets.
    private func golfTournamentEnd(_ market: FuturesMarketDetail) -> String? {
        guard market.llmSportCategory?.lowercased() == "golf",
              let startStr = market.commenceTime,
              let startDate = startStr.asDate else { return nil }
        let endDate = Calendar.current.date(byAdding: .day, value: 4, to: startDate)
        return endDate?.ISO8601Format()
    }

}
