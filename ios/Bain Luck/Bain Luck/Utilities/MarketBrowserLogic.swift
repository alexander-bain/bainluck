import Foundation

/// #10830 — the rule behind ``MarketBrowserView``: a bounded window onto a
/// COMPLETE collection. The native twin of web's `MarketBrowser`
/// (`frontend/components/event/MarketBrowser.tsx`, #10809).
///
/// Pure so the reachability promise can be asserted without rendering a view:
/// every item is in exactly one family, a search crosses every family, and the
/// window only ever grows by whole pages until the last match is on screen.
/// Nothing here filters an item out of the collection; it only decides which
/// slice of it is drawn right now.
enum MarketBrowserLogic {
    /// How many rows a family shows before "Show more".
    static let pageSize = 12

    /// Whether a collection gets browse chrome at all. One that fits in a single
    /// window is drawn whole, with no search and no pills; a tabbed list (no
    /// search — the maps) always browses, because it shows one item at a time.
    static func browses(itemCount: Int, pageSize: Int = pageSize, searchable: Bool) -> Bool {
        !searchable || itemCount > pageSize
    }

    /// The families, in the order their first item appears. The caller's order
    /// IS the ranking (players by priced depth, maps by the page's own order),
    /// so this never re-sorts.
    static func groups(_ groupNames: [String]) -> [String] {
        var seen: Set<String> = []
        return groupNames.filter { seen.insert($0).inserted }
    }

    /// The family on screen: the reader's choice while it still exists,
    /// otherwise the first. A refresh that drops the chosen family falls back
    /// rather than showing an empty window.
    static func activeGroup(selected: String?, groups: [String]) -> String? {
        if let selected, groups.contains(selected) { return selected }
        return groups.first
    }

    /// The search terms, folded the way the haystack is. Empty when the query
    /// is blank, which is what switches the window back to families.
    static func terms(_ query: String) -> [String] {
        fold(query).split(whereSeparator: \.isWhitespace).map(String.init)
    }

    /// Case- and accent-blind, so "Ga" finds "Gaël" and "jeanty" finds
    /// "Ashton Jeanty".
    static func fold(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
    }

    /// The indices the window draws from: every item whose search text holds
    /// EVERY term (so "jeanty rushing" narrows rather than widens), or, with no
    /// query, every item of the active family. A search deliberately ignores
    /// the family — finding a player is the reason the field exists.
    static func matchingIndices(
        groupNames: [String], searchTexts: [String], query: String, selected: String?
    ) -> [Int] {
        let wanted = terms(query)
        if !wanted.isEmpty {
            return searchTexts.indices.filter { i in
                let haystack = fold(searchTexts[i])
                return wanted.allSatisfy { haystack.contains($0) }
            }
        }
        guard let active = activeGroup(selected: selected, groups: groups(groupNames)) else {
            return []
        }
        return groupNames.indices.filter { groupNames[$0] == active }
    }

    /// The paging control's next window. Grows by a page until every match is
    /// drawn, then collapses back to one page.
    static func nextLimit(current: Int, matchCount: Int, pageSize: Int = pageSize) -> Int {
        current < matchCount ? current + pageSize : pageSize
    }

    /// "12 of 77" — the status beside the paging control.
    static func windowStatus(limit: Int, matchCount: Int) -> String {
        "\(Swift.min(limit, matchCount)) of \(matchCount)"
    }

    /// The heading drawn above the row at `index`: its own heading when it
    /// starts a new run, nil when the row above already carries the same one.
    static func headingText(_ headings: [String], at index: Int) -> String? {
        guard headings.indices.contains(index) else { return nil }
        let text = headings[index].trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return nil }
        if index > 0, headings[index - 1].trimmingCharacters(in: .whitespaces) == text { return nil }
        return text
    }
}
