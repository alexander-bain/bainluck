import SwiftUI

/// #10830 — a search field, one row of family pills and a bounded window onto
/// a complete market collection. The native twin of web's `MarketBrowser`
/// (#10809), shared by the maps, the player props, the game questions and the
/// related-markets catalog on the event page.
///
/// The browsing rule lives in ``MarketBrowserLogic``; this view only draws it.
/// Rows are drawn by the caller, so every section keeps its own renderer and
/// with it every truth rule that renderer already carries (settled wording,
/// verdicts, unpriced refusals). The browser decides WHICH rows are on screen,
/// never what a row says.
struct MarketBrowserView<Item: Identifiable, Row: View>: View {
    /// Names the collection for VoiceOver and the search placeholder.
    let label: String
    let items: [Item]
    let group: (Item) -> String
    let searchText: (Item) -> String
    var pageSize: Int = MarketBrowserLogic.pageSize
    var searchable: Bool = true
    /// What the search placeholder suggests — "player or stat", "team or market".
    var searchPrompt: String? = nil
    /// The ids of the rows on screen, for a host that must not send focus to a
    /// row the browser has filtered out or paged away (the game questions'
    /// focus return after their detail sheet closes).
    var visibleIDs: Binding<Set<Item.ID>>? = nil
    @ViewBuilder let row: (Item) -> Row

    @State private var selected: String?
    @State private var query = ""
    @State private var limit: Int?

    var body: some View {
        let groupNames = items.map(group)
        let families = MarketBrowserLogic.groups(groupNames)
        // A collection that fits in one window is drawn whole, with no search
        // and no pills — browse chrome over three rows is noise. A tabbed list
        // (`searchable: false`, the maps) always browses: it shows one at a time.
        let browses = MarketBrowserLogic.browses(
            itemCount: items.count, pageSize: pageSize, searchable: searchable)
        let active = MarketBrowserLogic.activeGroup(selected: selected, groups: families)
        let searching = browses && searchable && !MarketBrowserLogic.terms(query).isEmpty
        let matches = browses
            ? MarketBrowserLogic.matchingIndices(
                groupNames: groupNames,
                searchTexts: items.map(searchText),
                query: searchable ? query : "",
                selected: selected
            )
            : Array(items.indices)
        let window = browses ? (limit ?? pageSize) : items.count
        let shown = matches.prefix(window).map { items[$0] }

        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                if browses && searchable {
                    searchField
                }
                if browses && families.count > 1 {
                    familyPills(families, active: searching ? nil : active)
                }
                VStack(alignment: .leading, spacing: 0) {
                    // Keyed by the item's own id, so a refresh that reorders
                    // the collection keeps each row's state with its row.
                    ForEach(shown) { item in
                        row(item)
                    }
                }
                .onChange(of: shown.map(\.id), initial: true) { _, ids in
                    visibleIDs?.wrappedValue = Set(ids)
                }
                if matches.isEmpty {
                    Text("No matches. Try a player, team, or market name.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .padding(.vertical, 12)
                }
                if browses && matches.count > pageSize {
                    pager(matchCount: matches.count, window: window)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(label)
        }
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            TextField(
                "Search \(searchPrompt ?? label.lowercased())",
                text: Binding(
                    get: { query },
                    set: { query = $0; limit = nil }
                )
            )
            .textFieldStyle(.plain)
            .autocorrectionDisabled()
            #if os(iOS)
            .textInputAutocapitalization(.never)
            .submitLabel(.search)
            #endif
            .accessibilityLabel("Search \(label.lowercased())")
            if !query.isEmpty {
                Button {
                    query = ""
                    limit = nil
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                        .frame(minWidth: 44, minHeight: 44)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Clear search")
            }
        }
        .font(.subheadline)
        .padding(.leading, 12)
        .frame(minHeight: 44)
        .background(Color.secondary.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.barTrack.opacity(0.6), lineWidth: 0.5))
    }

    private func familyPills(_ families: [String], active: String?) -> some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(families, id: \.self) { family in
                        let isActive = family == active
                        Button {
                            selected = family
                            query = ""
                            limit = nil
                        } label: {
                            Text(family)
                                .font(.subheadline.weight(isActive ? .semibold : .medium))
                                .lineLimit(1)
                                .padding(.horizontal, 14)
                                .frame(minHeight: 44)
                                .foregroundStyle(isActive ? AnyShapeStyle(.background) : AnyShapeStyle(.secondary))
                                .background(isActive ? Color.primary : Color.secondary.opacity(0.08))
                                .clipShape(RoundedRectangle(cornerRadius: 10))
                        }
                        .buttonStyle(.plain)
                        .id(family)
                        .accessibilityAddTraits(isActive ? .isSelected : [])
                        .accessibilityHint("Shows \(family) in \(label.lowercased())")
                    }
                }
            }
            .accessibilityLabel("\(label) categories")
            .onChange(of: active) { _, newValue in
                guard let newValue else { return }
                withAnimation(.easeInOut(duration: 0.2)) {
                    proxy.scrollTo(newValue, anchor: .center)
                }
            }
        }
    }

    private func pager(matchCount: Int, window: Int) -> some View {
        HStack {
            Text(MarketBrowserLogic.windowStatus(limit: window, matchCount: matchCount))
                .font(.footnote)
                .monospacedDigit()
                .foregroundStyle(.secondary)
            Spacer()
            Button {
                withAnimation(.easeInOut(duration: 0.15)) {
                    limit = MarketBrowserLogic.nextLimit(
                        current: window, matchCount: matchCount, pageSize: pageSize
                    )
                }
            } label: {
                Text(window < matchCount ? "Show more" : "Show fewer")
                    .font(.subheadline.weight(.semibold))
                    .padding(.horizontal, 12)
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint(window < matchCount
                ? "Shows the next \(Swift.min(pageSize, matchCount - window))"
                : "Shows the first \(pageSize)")
        }
    }
}
