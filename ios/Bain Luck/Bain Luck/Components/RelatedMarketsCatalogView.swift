import SwiftUI

/// #10830 — the complete served season collection for both teams, browsable
/// by family and searchable, behind one "Browse related markets" control. The
/// native twin of web's compact `RelatedFutures` catalog (#10809).
///
/// The sections above it draw the categories that have a bespoke picture
/// (awards, season outlook, trade watch, …); this keeps EVERY other served row
/// reachable too — `categorizeFutures` drops `championship` rows entirely, and
/// before this they had no way onto the page.
enum RelatedMarketsCatalog {
    /// The family a served `display_category` is browsed under. A category
    /// with no entry, or no category at all, is "More questions" — a row is
    /// never given a classification the server did not make.
    static let familyNames: [String: String] = [
        "playoff_path": "Season outcomes",
        "conference": "Conference",
        "season_stat": "Season totals",
        "award": "Awards",
        "series": "Series",
        "trade": "Next team",
        "novelty": "More questions",
    ]
    static let fallbackFamily = "More questions"
    /// Pill order. Families not listed sort after these, by name.
    static let familyOrder = [
        "Season outcomes", "Conference", "Awards", "Season totals", "Series", "Next team",
        fallbackFamily,
    ]

    struct Row: Identifiable {
        let id: String
        let future: RelatedFuture
        let family: String
        /// A price is printed only for a row the server classified (web's rule:
        /// an unclassified record stays a link, never a number we vouch for).
        var printsPrice: Bool { future.displayCategory != nil && future.probability != nil }
    }

    /// Every served season row of both teams: the per-game rows (`game_prop`,
    /// `other`) are the game's own and are browsed on the game's sections, so
    /// they are left out; a leg filed under BOTH teams appears once (identity
    /// is market + outcome). Classified rows before unclassified ones, then by
    /// family, keeping the served order inside each.
    static func rows(home: [RelatedFuture], away: [RelatedFuture]) -> [Row] {
        var seen: Set<String> = []
        let all = (home + away).filter { future in
            future.displayCategory != "game_prop" && future.displayCategory != "other"
                && seen.insert(key(future)).inserted
        }
        let rows = all.map { future in
            Row(id: key(future), future: future,
                family: familyNames[future.displayCategory ?? ""] ?? fallbackFamily)
        }
        return rows.enumerated().sorted { a, b in
            let (ra, rb) = (rank(a.element), rank(b.element))
            return ra != rb ? ra < rb : a.offset < b.offset
        }
        .map(\.element)
    }

    static func key(_ future: RelatedFuture) -> String {
        "\(future.marketId)-\(future.outcomeId)"
    }

    private static func rank(_ row: Row) -> Int {
        let family = familyOrder.firstIndex(of: row.family) ?? familyOrder.count
        // Unclassified rows trail their family, as on web.
        return family * 2 + (row.future.displayCategory == nil ? 1 : 0)
    }

    /// What a search over one row reads.
    static func searchText(_ row: Row) -> String {
        [row.future.marketName, row.future.cleanLabel ?? "", row.future.outcomeName, row.family]
            .joined(separator: " ")
    }
}

struct RelatedMarketsCatalogView: View {
    let rows: [RelatedMarketsCatalog.Row]
    var accent: Color = DS.purple

    /// Closed by default: the catalog is complete, so it is long, and the
    /// sections above already carry the picture. One tap opens it (D102).
    @State private var isOpen = LaunchRig.expandsCollapsedSections()

    var body: some View {
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Button {
                    withAnimation(.easeInOut(duration: 0.15)) { isOpen.toggle() }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: isOpen ? "chevron.down" : "chevron.right")
                            .font(.caption.weight(.semibold))
                            .accessibilityHidden(true)
                        Text("Browse related markets")
                            .font(.subheadline.weight(.semibold))
                        Spacer()
                        Text("\(rows.count)")
                            .font(.caption)
                            .monospacedDigit()
                            .foregroundStyle(.secondary)
                    }
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Browse related markets, \(rows.count)")
                .accessibilityValue(isOpen ? "Expanded" : "Collapsed")

                if isOpen {
                    MarketBrowserView(
                        label: "Related markets",
                        items: rows,
                        group: \.family,
                        searchText: RelatedMarketsCatalog.searchText,
                        searchPrompt: "team, player or market"
                    ) { row in
                        catalogRow(row)
                    }
                }
            }
        }
    }

    private func catalogRow(_ row: RelatedMarketsCatalog.Row) -> some View {
        let future = row.future
        return NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(future.cleanLabel ?? future.marketName)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.primary)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(future.outcomeName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 8)
                if row.printsPrice, let probability = future.probability {
                    VStack(alignment: .trailing, spacing: 4) {
                        Text(formatProbability(probability))
                            .font(.subheadline.weight(.bold))
                            .monospacedDigit()
                            .foregroundStyle(.primary)
                        Capsule()
                            .fill(Color.secondary.opacity(0.1))
                            .frame(width: 56, height: 4)
                            .overlay(alignment: .leading) {
                                Capsule()
                                    .fill(accent)
                                    .frame(width: max(2, 56 * min(max(probability, 0), 1)), height: 4)
                            }
                            .accessibilityHidden(true)
                    }
                }
                Image(systemName: "chevron.right")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.tertiary)
                    .accessibilityHidden(true)
            }
            .padding(.vertical, 10)
            .frame(minHeight: 44)
            .contentShape(Rectangle())
            .overlay(alignment: .bottom) {
                Rectangle().fill(Color.barTrack.opacity(0.5)).frame(height: 0.5)
            }
        }
        .buttonStyle(.plain)
    }
}
