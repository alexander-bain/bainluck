import SwiftUI

/// #10830 — a search field, one row of family pills and a bounded window onto
/// a complete market collection. A guided browser (``chooserLabel``) leads
/// with a labelled chooser showing every family and keeps search optional.
/// The native twin of web's `MarketBrowser` (#10809), shared by the maps, the player props, the game questions and the
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
    /// A shared heading drawn ONCE above each run of rows that share it (the
    /// game odds' period, "Game" / "1st half"), instead of inside every row.
    /// nil, or an empty string for an item, draws no heading.
    var heading: ((Item) -> String)? = nil
    /// Alex 10/10 — "how could they possibly know what to type into this
    /// field?" Non-nil names a family chooser ("Stat") that LEADS the browser
    /// with every family in view, and demotes search to an optional
    /// ``findLabel`` control below it. nil keeps the search-led browser.
    var chooserLabel: String? = nil
    /// The words a family's chip prints; the family itself when nil.
    var groupTitle: ((String) -> String)? = nil
    /// A second line tied to one family's chip ("Participation rule").
    var groupNote: ((String) -> String?)? = nil
    /// What the optional search control says in a guided browser.
    var findLabel: String = "Find"
    @ViewBuilder let row: (Item) -> Row

    // `-launch_browse_family` (LaunchRig) lets the camera open a family the
    // rig cannot tap; nil for every reader.
    @State private var selected: String? = LaunchRig.browseFamily()
    @State private var query = ""
    @State private var limit: Int?
    /// A guided browser's search field is open.
    @State private var finding = false
    @FocusState private var searchFocused: Bool
    @Environment(\.dynamicTypeSize) private var typeSize

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
        let headings = heading.map { shown.map($0) } ?? []

        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                if browses, let chooserLabel {
                    if families.count > 1 {
                        chooser(chooserLabel, families: families, active: searching ? nil : active)
                    }
                    if searchable {
                        if finding || !query.isEmpty { searchField } else { findButton }
                    }
                } else {
                    if browses && searchable {
                        searchField
                    }
                    if browses && families.count > 1 {
                        familyPills(families, active: searching ? nil : active)
                    }
                }
                VStack(alignment: .leading, spacing: 0) {
                    // Keyed by the item's own id, so a refresh that reorders
                    // the collection keeps each row's state with its row.
                    ForEach(Array(shown.enumerated()), id: \.element.id) { index, item in
                        if let text = MarketBrowserLogic.headingText(headings, at: index) {
                            Text(text)
                                .font(.footnote.weight(.semibold))
                                .foregroundStyle(.secondary)
                                .padding(.top, index == 0 ? 0 : 10)
                                .padding(.bottom, 2)
                                .accessibilityAddTraits(.isHeader)
                        }
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
            .focused($searchFocused)
            // Opened from "Find": the field takes the keyboard as it appears.
            .onAppear { if chooserLabel != nil && finding { searchFocused = true } }
            if chooserLabel != nil {
                Button {
                    query = ""
                    limit = nil
                    finding = false
                } label: {
                    Text("Done")
                        .font(.subheadline.weight(.semibold))
                        .padding(.horizontal, 12)
                        .frame(minWidth: 44, minHeight: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .foregroundStyle(.blue)
                .accessibilityLabel("Close search")
            } else if !query.isEmpty {
                Button {
                    query = ""
                    limit = nil
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                        .frame(minWidth: 44, minHeight: 44)
                        .contentShape(Rectangle())
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

    private func title(_ family: String) -> String { groupTitle?(family) ?? family }
    private func note(_ family: String) -> String? { groupNote?(family) ?? nil }
    private func spoken(_ family: String) -> String {
        note(family).map { "\(title(family)), \($0)" } ?? title(family)
    }

    private func choose(_ family: String) {
        selected = family
        query = ""
        limit = nil
        finding = false
    }

    // MARK: - Guided chooser (Alex 10/10)

    /// The labelled family chooser: every family in the open as wrapped chips
    /// — no row to scroll sideways, no label cut off — or, for a long list or
    /// accessibility text, a labelled menu that names how many there are.
    private func chooser(_ name: String, families: [String], active: String?) -> some View {
        let menu = MarketBrowserLogic.choosesFromMenu(
            groupCount: families.count, accessibilityText: typeSize.isAccessibilitySize)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(name)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .accessibilityAddTraits(.isHeader)
                Spacer()
                if menu {
                    Text("\(families.count) to choose from")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                }
            }
            if menu {
                chooserMenu(name, families: families, active: active)
            } else {
                FlowLayout(spacing: 6) {
                    ForEach(families, id: \.self) { family in
                        chooserChip(family, isActive: family == active)
                    }
                }
            }
        }
    }

    private func chooserChip(_ family: String, isActive: Bool) -> some View {
        Button {
            choose(family)
        } label: {
            VStack(alignment: .leading, spacing: 1) {
                Text(title(family))
                    .font(.subheadline.weight(isActive ? .semibold : .medium))
                if let note = note(family) {
                    Label(note, systemImage: "info.circle")
                        .font(.caption2.weight(.medium))
                        .opacity(0.85)
                }
            }
            .lineLimit(1)
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .frame(minWidth: 44, minHeight: 44)
            .foregroundStyle(isActive ? AnyShapeStyle(.background) : AnyShapeStyle(.primary))
            .background(isActive ? Color.primary : Color.secondary.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .contentShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("market-browser-chip")
        .accessibilityLabel(spoken(family))
        .accessibilityAddTraits(isActive ? .isSelected : [])
        .accessibilityHint("Shows \(title(family)) in \(label.lowercased())")
    }

    private func chooserMenu(_ name: String, families: [String], active: String?) -> some View {
        Menu {
            ForEach(families, id: \.self) { family in
                // A toggle, not a button with a checkmark icon: the menu draws
                // a toggle's ON state itself at every text size (an icon is
                // dropped at accessibility sizes), and VoiceOver reads it.
                Toggle(isOn: Binding(
                    get: { family == active },
                    set: { if $0 { choose(family) } }
                )) {
                    Text(title(family))
                    if let note = note(family) { Text(note) }
                }
                .accessibilityLabel(spoken(family))
            }
        } label: {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(active.map(title) ?? "Choose")
                        .font(.subheadline.weight(.semibold))
                    if let note = active.flatMap(note) {
                        Label(note, systemImage: "info.circle")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(.secondary)
                    }
                }
                .multilineTextAlignment(.leading)
                Spacer(minLength: 8)
                Image(systemName: "chevron.up.chevron.down")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .accessibilityHidden(true)
            }
            .foregroundStyle(.primary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(Color.secondary.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .contentShape(RoundedRectangle(cornerRadius: 10))
        }
        .accessibilityIdentifier("market-browser-chooser")
        .accessibilityLabel("\(name): \(active.map(spoken) ?? "none chosen")")
        .accessibilityHint("Choose from \(families.count)")
    }

    /// Search, offered and never required: every row is reachable from the
    /// chooser, the team filter and "Show more".
    private var findButton: some View {
        Button {
            finding = true
        } label: {
            Label(findLabel, systemImage: "magnifyingglass")
                .font(.subheadline.weight(.medium))
                .padding(.trailing, 12)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(.blue)
        .accessibilityIdentifier("market-browser-find")
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
                            // Alex 10/10: a tap on the pill's padding has to
                            // land, not only a tap on its word. The shape is
                            // declared after the padding and frame, so the
                            // whole drawn pill (≥44×44) is the target.
                            Text(family)
                                .font(.subheadline.weight(isActive ? .semibold : .medium))
                                .lineLimit(1)
                                .padding(.horizontal, 14)
                                .frame(minWidth: 44, minHeight: 44)
                                .foregroundStyle(isActive ? AnyShapeStyle(.background) : AnyShapeStyle(.secondary))
                                .background(isActive ? Color.primary : Color.secondary.opacity(0.08))
                                .clipShape(RoundedRectangle(cornerRadius: 10))
                                .contentShape(RoundedRectangle(cornerRadius: 10))
                        }
                        .buttonStyle(.plain)
                        .id(family)
                        .accessibilityIdentifier("market-browser-pill")
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
                .accessibilityIdentifier("market-browser-status-\(label)")
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
            .accessibilityIdentifier("market-browser-more-\(label)")
            .accessibilityHint(window < matchCount
                ? "Shows the next \(Swift.min(pageSize, matchCount - window))"
                : "Shows the first \(pageSize)")
        }
    }
}
