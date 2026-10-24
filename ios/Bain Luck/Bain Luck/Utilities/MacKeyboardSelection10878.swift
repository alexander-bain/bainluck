import Foundation

/// #10878 / #4940 — Command-K on a Mac asks its own window's Search field for
/// focus.
///
/// A count, not a flag, for the reason `pendingSearchQuery` is drained on
/// mount AND on change (#3157): Command-K from Discover selects Search and asks
/// in the same tick, before SearchView exists, so only the mount can see it;
/// Command-K while Search is already up changes nothing but the ask, so only
/// the change can. A flag that was still set from an undrained ask would not
/// change again and the second press would do nothing. Each ask is answered
/// once, by whichever of the two drains it first.
nonisolated struct MacSearchFocusTicket10878: Equatable {
    private(set) var requested = 0
    private(set) var consumed = 0

    var isPending: Bool { requested != consumed }

    mutating func request() {
        requested &+= 1
    }

    /// True once per outstanding ask; any number of asks made before a drain
    /// are one focus, not several.
    mutating func consume() -> Bool {
        guard isPending else { return false }
        consumed = requested
        return true
    }
}

/// #10878 / #4940 — the row the arrow keys have picked in Mac search results.
///
/// The pick is a canonical identity (SearchView uses the row's own `Route`),
/// never a position: when an answer is replaced — a retry, a sport filter, a
/// slower response landing — the same game stays picked wherever it now draws,
/// and a game that is no longer drawn is not silently swapped for whatever took
/// its slot. Return opens only a row that is on screen now.
nonisolated struct MacKeyboardSelection10878<Key: Hashable>: Equatable {
    private(set) var selected: Key?

    /// The rows in the order the page draws them, each identity once. A
    /// destination drawn twice (it can appear as a family member and a flat
    /// market) is one stop for the arrows, at its first position.
    static func order(_ sections: [[Key]]) -> [Key] {
        var seen = Set<Key>()
        return sections.joined().filter { seen.insert($0).inserted }
    }

    /// Down from the field picks the first row; down on the last row stays.
    /// Up from the first row hands back to the field, so Return searches again.
    /// Returns false when there was nothing to move through — the caller then
    /// lets the key do its ordinary text-field work.
    @discardableResult
    mutating func moveDown(in keys: [Key]) -> Bool {
        guard !keys.isEmpty else { return false }
        guard let selected, let index = keys.firstIndex(of: selected) else {
            self.selected = keys[0]
            return true
        }
        self.selected = keys[min(index + 1, keys.count - 1)]
        return true
    }

    @discardableResult
    mutating func moveUp(in keys: [Key]) -> Bool {
        guard let selected, let index = keys.firstIndex(of: selected) else {
            self.selected = nil
            return false
        }
        self.selected = index == 0 ? nil : keys[index - 1]
        return true
    }

    /// A new answer keeps the same pick if it still draws it, else drops it.
    mutating func reconcile(with keys: [Key]) {
        if let selected, !keys.contains(selected) {
            self.selected = nil
        }
    }

    /// What Return opens: the pick, only while it is drawn. `nil` means Return
    /// keeps its existing meaning (run the search).
    func activation(in keys: [Key]) -> Key? {
        guard let selected, keys.contains(selected) else { return nil }
        return selected
    }

    func isSelected(_ key: Key) -> Bool { selected == key }

    /// Escape: drops a pick. False when there was none, so the next Escape can
    /// mean "leave the field".
    @discardableResult
    mutating func clear() -> Bool {
        guard selected != nil else { return false }
        selected = nil
        return true
    }
}
