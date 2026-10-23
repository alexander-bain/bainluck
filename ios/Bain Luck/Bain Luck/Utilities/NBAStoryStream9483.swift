import Foundation

/// #9483 — the compact NBA story stream's pure policy (brief v445 + Lane1's
/// W1–W3). It orders the page's existing game-story cards by what their own
/// lines say, attaches one factual sentence to a ranked card, and holds the
/// stream's applied / pending / active / held state. No SwiftUI, no timer, no
/// network: event identity and `now` are arguments, so every rule is pinned at a
/// fixed instant (gotcha #44). The wrapper (`NBAStoryStreamView9483`) drives it,
/// the page's `NFLCardDeckState9483` stores it.
///
/// WHAT RANKS A CARD (C4/C5), read from `card.current(at: now)` only:
/// - before tip-off: nothing — the delivered margin → total → finish order;
/// - during play: a ladder's strongest own option, by how far its admitted
///   current quote sits from its admitted pregame pin;
/// - after the final: a ladder's own confirmed Won/Lost line against its pin —
///   `1 − pin` for a win, `pin` for a loss.
/// Both need the pin finite and STRICTLY between 0 and 1, dated; during play the
/// current quote also needs its own clock, so a quote `current(at:)` has aged out
/// is no candidate. A card ranks only when its whole sentence can be said:
/// ranking never moves a card without stating why.
///
/// The ordering value is private. It is not a probability, not a calibrated
/// surprise and not a product number: no reason, label or spoken string carries
/// it, and `Plan` does not expose it.
///
/// Isolation: the values are `nonisolated` (Native's frozen interface), so
/// `Plan` and `State` compare anywhere. The few members that read the page's
/// main-actor helpers — `NFLEventCard9483.current(at:)`, `String.asDate`, the
/// card's own `formatProbability` (so a sentence prints the card's number) and
/// the reader's own `NFLCardReaderHold9483.reconciled`, which W1 requires shelf
/// and reader to share — are `@MainActor`; every caller is a view or the page's
/// `ObservableObject`.
nonisolated enum NBAStoryStreamPolicy9483 {
    /// A factual reason attached to one card, for one exact option.
    nonisolated struct Reason: Equatable {
        let eventID: Int
        let cardID: String
        let optionKey: String
        /// `.during` (live template) or `.after` (final template).
        let phase: NBALadderCard9483.Phase
        let baseline: Double
        let baselineObservedAt: String
        /// During play: the admitted current quote and its clock.
        let current: Double?
        let currentObservedAt: String?
        /// Final: the matching admitted actual quantity, and the own result.
        let actual: Double?
        let won: Bool?
        /// During play: `observedAt.asDate + SourceAge.liveStaleAfter` (W2) —
        /// the last instant `current(at:)` still treats the quote as current.
        let expiry: Date?
        /// The option's own line, "Over 236.5" / "Knicks by 4+".
        let line: String
        let family: NBALadderCard9483.Family
        /// The actual in the card's own words: "242", "Knicks by 2", "Tie".
        let actualWords: String?

        /// The visible sentence (C6): "Over 236.5 points: 30% before tip-off ·
        /// 45% now." / "Over 236.5 points: 30% before tip-off; final total 242."
        /// No difference, no private value.
        @MainActor var text: String {
            let before = "\(line) points: \(Self.percent(baseline)) before tip-off"
            switch (phase, current, actualWords) {
            case (.after, _, let actual?): return "\(before); final \(family.rawValue) \(actual)."
            case (.during, let current?, _): return "\(before) · \(Self.percent(current)) now."
            default: return "\(before)."
            }
        }

        /// The spoken sentence: the visible facts plus their times.
        @MainActor var accessibilityText: String {
            let before = "\(line) points. \(Self.percent(baseline)) before tip-off, quoted "
                + "\(SourceAge.preciseStamp(baselineObservedAt) ?? "")."
            switch (phase, current, actualWords) {
            case (.after, _, let actual?): return "\(before) Final \(family.rawValue) \(actual)."
            case (.during, let current?, _):
                return "\(before) \(Self.percent(current)) now, quoted \(SourceAge.preciseStamp(currentObservedAt) ?? "")."
            default: return before
            }
        }

        /// The card's own formatter, with no `renderedPercent:` because the card
        /// passes none: the sentence prints the number the card under it prints,
        /// including the `<1%` / `>99%` a strict pin near 0 or 1 reads as.
        @MainActor private static func percent(_ probability: Double) -> String {
            formatProbability(probability)
        }
    }

    nonisolated struct Plan: Equatable {
        let eventID: Int
        /// Every admitted input card id, exactly once.
        let orderedIDs: [String]
        let reasons: [String: Reason]
        /// The nearest live reason deadline, or nil.
        var nearestExpiry: Date? { reasons.values.compactMap(\.expiry).min() }
    }

    /// The order and reasons for `cards` at `now`. Keeps every input card once
    /// (a repeated id keeps its first), manufactures none, and rewrites no card:
    /// ranked ladders first, by private value descending (exact `Double`, no
    /// rounding); equal values by their option key (`String <`), then margin
    /// before total. Then the unranked ladders, margin → total; then every other
    /// card — the finish — in its input order.
    @MainActor
    static func plan(eventID: Int, phase: NBALadderCard9483.Phase,
                     cards: [NFLEventCard9483], now: Date) -> Plan {
        var seen = Set<String>()
        let unique = cards.filter { seen.insert($0.id).inserted }

        var ranked: [(id: String, value: Double, reason: Reason)] = []
        var unranked: [(id: String, family: NBALadderCard9483.Family)] = []
        var others: [String] = []
        for card in unique {
            guard case .ladder(let ladder) = card.current(at: now) else {
                others.append(card.id)
                continue
            }
            if let best = strongest(ladder, cardID: card.id, eventID: eventID, phase: phase) {
                ranked.append((card.id, best.value, best.reason))
            } else {
                unranked.append((card.id, ladder.family))
            }
        }
        ranked.sort { a, b in
            if a.value != b.value { return a.value > b.value }
            if a.reason.optionKey != b.reason.optionKey { return a.reason.optionKey < b.reason.optionKey }
            return familyRank(a.reason.family) < familyRank(b.reason.family)
        }
        let ladders = unranked.enumerated().sorted { a, b in
            let (x, y) = (familyRank(a.element.family), familyRank(b.element.family))
            return x != y ? x < y : a.offset < b.offset
        }.map(\.element.id)
        return Plan(eventID: eventID,
                    orderedIDs: ranked.map(\.id) + ladders + others,
                    reasons: Dictionary(ranked.map { ($0.id, $0.reason) }, uniquingKeysWith: { first, _ in first }))
    }

    private static func familyRank(_ family: NBALadderCard9483.Family) -> Int {
        family == .margin ? 0 : 1
    }

    /// The ladder's strongest own option and its reason, or nil when no option
    /// can say its whole sentence. Equal values pick the lower option key.
    @MainActor
    private static func strongest(_ ladder: NBALadderCard9483, cardID: String, eventID: Int,
                                  phase: NBALadderCard9483.Phase) -> (value: Double, reason: Reason)? {
        guard ladder.phase == phase, phase != .before else { return nil }
        var best: (value: Double, reason: Reason)?
        for point in ladder.points {
            guard let candidate = candidate(point, in: ladder, cardID: cardID, eventID: eventID) else { continue }
            if let current = best,
               candidate.value < current.value
                || (candidate.value == current.value && candidate.reason.optionKey >= current.reason.optionKey) {
                continue
            }
            best = candidate
        }
        return best
    }

    @MainActor
    private static func candidate(_ point: NBALadderCard9483.Point, in ladder: NBALadderCard9483,
                                  cardID: String, eventID: Int) -> (value: Double, reason: Reason)? {
        // The admitted pregame pin, strictly a chance: an exact 0 or 1 is a
        // settlement value, whatever admitted it upstream. The number the card
        // draws must be that pin, and its clock must be readable to be spoken.
        guard let baseline = point.detail.baseline, baseline.isFinite, baseline > 0, baseline < 1,
              point.chance == baseline,
              let baselineAt = point.detail.baselineObservedAt, baselineAt.asDate != nil else { return nil }
        switch ladder.phase {
        case .before:
            return nil
        case .during:
            // `current(at:)` has already removed a quote no longer observed; an
            // undatable clock was never recent, so it has no deadline either.
            guard let current = point.now, current.isFinite, (0...1).contains(current),
                  let currentAt = point.observedAt, let quoted = currentAt.asDate else { return nil }
            let reason = Reason(
                eventID: eventID, cardID: cardID, optionKey: point.optionKey, phase: .during,
                baseline: baseline, baselineObservedAt: baselineAt,
                current: current, currentObservedAt: currentAt, actual: nil, won: nil,
                expiry: quoted.addingTimeInterval(SourceAge.liveStaleAfter),
                line: point.label, family: ladder.family, actualWords: nil)
            return (abs(current - baseline), reason)
        case .after:
            // The option's own confirmed verdict, and the actual on its own axis
            // that the sentence names. A verdict the actual contradicts says
            // nothing rather than one of the two.
            guard let won = point.result, let actual = ladder.actual, actual.isFinite,
                  won == (point.side == .away ? actual < point.x : actual > point.x) else { return nil }
            let reason = Reason(
                eventID: eventID, cardID: cardID, optionKey: point.optionKey, phase: .after,
                baseline: baseline, baselineObservedAt: baselineAt,
                current: nil, currentObservedAt: nil, actual: actual, won: won, expiry: nil,
                line: point.label, family: ladder.family, actualWords: ladder.words(actual))
            return (won ? 1 - baseline : baseline, reason)
        }
    }

    /// One shelf position: a present applied card, or the held active card
    /// that left the deck (W1's unavailable/Refresh slot). Same id space.
    nonisolated enum Slot: Equatable, Identifiable {
        case card(String)
        case unavailable(String)
        var id: String {
            switch self {
            case .card(let id), .unavailable(let id): return id
            }
        }
    }

    /// The stream for ONE event. Holds and pending orders defer ORDER only: the
    /// cards' values are always read fresh by the caller.
    nonisolated struct State: Equatable {
        private(set) var eventID: Int
        private(set) var appliedIDs: [String]
        private(set) var pendingIDs: [String]
        private(set) var activeID: String?
        private(set) var held: Bool

        /// Initial / reset: applied = pending = plan order, active = first,
        /// unheld. A new event's stream is a new value — nothing of the old
        /// event's order, hold or active card survives.
        init(plan: Plan) {
            eventID = plan.eventID
            appliedIDs = plan.orderedIDs
            pendingIDs = plan.orderedIDs
            activeID = plan.orderedIDs.first
            held = false
        }

        /// Guarded receive (W1). Refuses (false, no change) a plan for another
        /// event — a stale callback writes nothing. Replaces `pendingIDs`;
        /// reconciles `activeID` only when unheld and absent from the plan.
        /// Never touches `appliedIDs`.
        @MainActor @discardableResult
        mutating func receive(_ plan: Plan) -> Bool {
            guard plan.eventID == eventID else { return false }
            pendingIDs = plan.orderedIDs
            if !held, let activeID, !pendingIDs.contains(activeID) {
                self.activeID = NFLCardReaderHold9483.reconciled(visible: activeID, old: appliedIDs, new: pendingIDs)
            }
            return true
        }

        /// applied ← pending, with W1's reconciliation of `activeID` — the
        /// reader's own `reconciled`, so shelf and reader pick the same neighbour.
        @MainActor
        mutating func applyPending() {
            activeID = NFLCardReaderHold9483.reconciled(visible: activeID, old: appliedIDs, new: pendingIDs)
            appliedIDs = pendingIDs
        }

        mutating func hold() { held = true }

        /// Resume: applies pending, then releases the hold.
        @MainActor
        mutating func resume() {
            applyPending()
            held = false
        }

        /// Next over `appliedIDs ∩ present` from the active position (a
        /// held-active absent id keeps its applied position). `wrap` is the
        /// automatic last → first; manual stepping passes false.
        mutating func next(present: Set<String>, wrap: Bool) {
            move(by: 1, present: present, wrap: wrap)
        }

        mutating func previous(present: Set<String>) {
            move(by: -1, present: present, wrap: false)
        }

        /// Manual browsing landed on `cardID`: it becomes active and the
        /// stream holds. An id not on the shelf writes nothing.
        mutating func focus(_ cardID: String, present: Set<String>) {
            guard shelf(present: present).contains(where: { $0.id == cardID }) else { return }
            activeID = cardID
            held = true
        }

        /// The shelf: `appliedIDs ∩ present` in applied order, plus the
        /// active id as `.unavailable` at its applied position when it is
        /// absent from `present` (only while it is active). Present cards not
        /// yet applied are pending and withheld.
        func shelf(present: Set<String>) -> [Slot] {
            appliedIDs.compactMap { id in
                if present.contains(id) { return .card(id) }
                return id == activeID ? .unavailable(id) : nil
            }
        }

        private mutating func move(by delta: Int, present: Set<String>, wrap: Bool) {
            let ids = shelf(present: present).map(\.id)
            guard !ids.isEmpty else { activeID = nil; return }
            guard let activeID, let index = ids.firstIndex(of: activeID) else { self.activeID = ids.first; return }
            let target = index + delta
            if ids.indices.contains(target) { self.activeID = ids[target] }
            else if wrap { self.activeID = delta > 0 ? ids.first : ids.last }
        }
    }
}
