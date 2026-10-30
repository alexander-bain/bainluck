import SwiftUI

// #10868 — "Which round for each fighter?": one combat fighter-round card
// across a bout's lifecycle. Each fighter is a group; each of that fighter's
// round slots is either one captured market (the original "will this fighter
// win in this round?" prop) with its own original Yes and No, or the owner's
// explicit words for a slot with no market ("No captured prop", "Unavailable
// in this update"). A tile leads with ONE original side and shows that side's own
// PRE-MATCH chance as a figure and as a hollow mark on a slim track that runs
// from 0% to 100% — a No keeps its own 89%, never the Yes figure and never a
// winner-side swap. Every slot is its own independent question: nothing here
// complements, inverts or normalizes a side, sums a fighter's rounds into one
// distribution or conditions a round on the fight reaching it, and an
// uncaptured slot never gains a figure, a result or an action.
//
// Before the fight a tile shows only the pre-match chance. During the fight
// the lead's pre-match and independently admitted in-fight chances sit at the
// same figure size, hollow and filled marks on the same track; an unavailable
// or withheld chance stays words and draws no mark. After the fight the
// pre-match chance stays and the displayed original's own contract result
// appears beside it. The owner's independently known physical finish is
// separate context beneath the card — it never grades, moves or marks a tile
// and never fills an uncaptured slot.
//
// Presentation only, extracted from the approved design: `CombatOutcomeCards.tsx`
// (the rounds family), `CombatBaselineMark.tsx` (the rail style),
// `combatOutcomeCards.css` (dense round map, probability rail, dashed absent
// slot). The reference's fixture admission, fighter and round tables, title
// and id maps, latest-before-start election, result-conflict rule, automatic
// first-side selection and state are NOT ported.
//
// Every group id, fighter name and order, every slot id, round label, order
// and state, every market id and original prop text, every original identity
// and side label, every figure, provenance line, result word, heading and
// finish context arrive resolved by the owner and are shown verbatim. This
// layer never formats or rounds a probability (owner text carries at most one
// decimal), never reads a clock, never infers a phase, a fighter, a round or
// a grade from a title or the bout outcome, and never turns a settled 0/100
// quote into a chance. Unknown is never a loss and absent is never zero.
//
// Selection, Details, timing disclosure, held updates and focus stay with the
// host: the view keeps no selected state, no sheet, no subscription and runs no
// animation, so reduced motion has nothing to stop. A tile leads with the
// host-selected side, else the host's explicit overview side, else lists every
// side — the leaf never picks Yes, the winner, the first or the nearest slot,
// and never switches sides on an update. Every original stays on screen, in
// its tile or in the selected slot's side rows, never both. With no callback,
// content is shown without a button and no tap is asked for. Method,
// duration and fighter-knockout cards are separate.
//
// Host binding still owed — not available at this base. An owner must supply
// proved fighter groups and round slots, each slot's market membership and
// exact original ids (never a parsed title); an admitted pre-match
// observation per original from its own history, or its own missing words;
// during the fight an admitted current observation or its own unavailable /
// withheld words, with currentness already applied; after the fight each
// original's independently admitted contract result; and any independently
// known finish context. COMBAT-ROUND-NATIVE-BINDING-MAP.md names the gaps.

/// One admitted reading. `probability` places the mark on the 0–100% track;
/// `text` is what the reader sees.
nonisolated struct CombatRoundObservation10868: Equatable {
    /// 0...1. Anything else draws no mark and keeps the owner's text.
    let probability: Double
    /// The owner's whole figure ("20.5%", "≥99.5%").
    let text: String
    /// Full provenance, shown in the selected comparison and spoken
    /// ("Last recorded before start · Oct 3, 4:27 PM PT · Polymarket").
    let detail: String
}

nonisolated enum CombatRoundPhase10868: Equatable {
    case before
    case during
    case final
}

/// The owner's in-fight state for one original, with currentness already applied.
nonisolated enum CombatRoundCurrent10868: Equatable {
    /// An admitted, current observation with the owner's optional movement line.
    case recorded(CombatRoundObservation10868, movement: String?)
    /// No admitted current reading ("No in-fight chance").
    case unavailable(String)
    /// A reading exists but is not admitted as current ("Held since round 1").
    case withheld(String)
}

/// The original side's contract result. There is no Bool: a missing result is
/// never a loss.
nonisolated enum CombatRoundResult10868: Equatable {
    case won(String)
    case lost(String)
    case void(String)
    /// Not independently admitted, including sources that disagree
    /// ("Result unconfirmed").
    case unconfirmed(String)
    /// Any other owner-qualified state ("Under review"), shown as words.
    case other(String)

    var text: String {
        switch self {
        case .won(let text), .lost(let text), .void(let text), .unconfirmed(let text), .other(let text): text
        }
    }

    /// The non-colour key. Each state has its own shape.
    var symbolName: String {
        switch self {
        case .won: "checkmark.circle"
        case .lost: "xmark.circle"
        case .void: "minus.circle"
        case .unconfirmed: "questionmark.circle"
        case .other: "info.circle"
        }
    }

    var isSettled: Bool {
        switch self {
        case .won, .lost, .void: true
        case .unconfirmed, .other: false
        }
    }
}

/// One original side of one round market. Each reading carries its own
/// missing words. `current` is read only during the fight, `result` and
/// `resultDetail` only after.
nonisolated struct CombatRoundOriginal10868: Equatable {
    /// Exact original outcome id, passed back to the owner unchanged.
    let id: String
    /// The original's market id, passed back unchanged.
    let marketID: String
    /// The original side name ("Yes", "No").
    let label: String
    let before: CombatRoundObservation10868?
    let beforeMissing: String
    let current: CombatRoundCurrent10868
    let result: CombatRoundResult10868
    /// The owner's qualification of the result; nil draws none.
    let resultDetail: String?
}

/// One owner-proved round market with its original sides in the owner's order.
nonisolated struct CombatRoundMarket10868: Equatable {
    /// The owner's market id.
    let id: String
    /// The full original prop text, verbatim.
    let question: String
    let originals: [CombatRoundOriginal10868]
    /// The owner's explicit overview side for this tile; nil lists every side.
    let overviewOriginalID: String?
}

/// What the owner proved for one fighter's round.
nonisolated enum CombatRoundSlotState10868: Equatable {
    case market(CombatRoundMarket10868)
    /// The capture holds no market for this slot ("No captured prop"). Not a
    /// claim that the venue never offered one, not 0% and not a loss.
    case noCapturedProp(String)
    /// A market was known but is not in this update ("Unavailable in this update").
    case unavailable(String)

    var market: CombatRoundMarket10868? {
        if case .market(let market) = self { return market }
        return nil
    }

    /// The owner's words for a slot with no market.
    var absentWords: String? {
        switch self {
        case .market: nil
        case .noCapturedProp(let words), .unavailable(let words): words
        }
    }
}

/// One fighter's round, in the owner's order.
nonisolated struct CombatRoundSlot10868: Equatable {
    /// The owner's slot id — the fighter-and-round identity.
    let id: String
    /// "Round 1"; never truncated.
    let label: String
    let state: CombatRoundSlotState10868
}

/// One fighter and that fighter's round slots, in the owner's order.
nonisolated struct CombatRoundGroup10868: Equatable {
    let id: String
    /// The fighter's full name; never truncated or shortened.
    let label: String
    /// Never assumed to be three rounds.
    let slots: [CombatRoundSlot10868]
}

/// One captured slot located on the card.
nonisolated struct CombatRoundPlace10868: Equatable {
    let group: CombatRoundGroup10868
    let slot: CombatRoundSlot10868
    let market: CombatRoundMarket10868

    func isAt(_ group: CombatRoundGroup10868, _ slot: CombatRoundSlot10868) -> Bool {
        self.group.id == group.id && self.slot.id == slot.id
    }
}

/// The owner's independently known physical finish. Context only — never a
/// grade, a phase, a mark on a tile or a value for an uncaptured slot.
nonisolated struct CombatRoundFinish10868: Equatable {
    /// "Official bout result".
    let title: String
    let lines: [String]
    let accessibilityDetail: String?
}

/// The owner's timing disclosure for one original. Shown only while that exact
/// original is the resolved selection.
nonisolated struct CombatRoundTiming10868: Equatable {
    let originalID: String
    let title: String
    let lines: [String]
}

/// Exact original identity, handed back to the owner on select and Details.
nonisolated struct CombatRoundOriginalRef10868: Hashable {
    let eventID: String
    let groupID: String
    let slotID: String
    let marketID: String
    let originalID: String
}

nonisolated enum CombatRoundSelection10868: Equatable {
    case none
    /// A captured slot is selected with no side.
    case slot(CombatRoundPlace10868)
    case original(CombatRoundPlace10868, CombatRoundOriginal10868)
    /// The slot resolves; the selected side is absent, withdrawn or duplicated.
    case sideUnavailable(CombatRoundPlace10868, String)
    /// The selected slot resolves but carries no market in this update.
    case slotWithoutMarket(CombatRoundGroup10868, CombatRoundSlot10868)
    /// The selected slot (or a side named without its slot) does not resolve
    /// to exactly one.
    case unavailable(String)

    var place: CombatRoundPlace10868? {
        switch self {
        case .slot(let place), .original(let place, _), .sideUnavailable(let place, _): place
        case .none, .slotWithoutMarket, .unavailable: nil
        }
    }

    var original: CombatRoundOriginal10868? {
        if case .original(_, let original) = self { return original }
        return nil
    }
}

nonisolated enum CombatRoundReading10868: Equatable {
    case value(CombatRoundObservation10868)
    case missing(String)
}

/// Where the track's marks sit, as fractions of 0...1. Nil draws no mark.
nonisolated struct CombatRoundRailMarks10868: Equatable {
    /// The hollow pre-match mark.
    let before: Double?
    /// The filled in-fight mark, during the fight only.
    let current: Double?

    /// The movement segment between the marks, only when both are drawn.
    var segment: ClosedRange<Double>? {
        guard let before, let current else { return nil }
        return min(before, current)...max(before, current)
    }
}

/// One entry in the card's key. Each mark has its own shape and words.
nonisolated enum CombatRoundKeyItem10868: Equatable {
    /// The track runs 0% to 100%.
    case scale
    /// Hollow mark: pre-match chance.
    case preMatch
    /// Filled mark: in-fight chance, during the fight only.
    case current
}

/// What a tile leads with.
nonisolated enum CombatRoundLead10868: Equatable {
    case original(CombatRoundOriginal10868, selected: Bool)
    /// The host named a side this market does not carry exactly once.
    case unavailable(String)
    /// No side is named: every side is listed, none is chosen.
    case sides
}

/// One original listed as its own row, with the exact action it may carry.
nonisolated struct CombatRoundTileSide10868: Equatable {
    let original: CombatRoundOriginal10868
    let action: CombatRoundAction10868?
}

/// What one tile draws — the View's own branch. Every original stays on screen:
/// in the tile itself, or in the selected slot's side rows beneath the map —
/// never both (`panelSides`).
nonisolated enum CombatRoundTilePresentation10868: Equatable {
    /// The approved compact rail tile: one control when `action` is set, else
    /// static. Its other side is reached through that action or, for the
    /// selected slot, the side rows that already list it.
    case rail(CombatRoundOriginal10868, selected: Bool, action: CombatRoundAction10868?)
    /// A static overview on an unselected slot: the lead's rail stays and every
    /// other original is listed beneath it. The tile is not a button.
    case railWithSides(CombatRoundOriginal10868, others: [CombatRoundTileSide10868])
    /// The notice alone: the selected slot's side rows list every side.
    case unavailable(String)
    /// The notice, then every original with its exact safe action. Not a button.
    case unavailableWithSides(String, sides: [CombatRoundTileSide10868])
    /// No side named: every side listed, none chosen. On the selected slot
    /// these are its only side rows; the panel beneath lists none.
    case sides([CombatRoundTileSide10868])
    /// A slot with no market: the owner's words, no figure, no result and no
    /// action.
    case absent(String)

    /// The originals this tile itself lists as their own rows.
    var listed: [CombatRoundTileSide10868] {
        switch self {
        case .rail, .unavailable, .absent: []
        case .railWithSides(_, let sides), .unavailableWithSides(_, let sides), .sides(let sides): sides
        }
    }
}

/// The selected original's comparison, by phase.
nonisolated enum CombatRoundComparison10868: Equatable {
    case before(CombatRoundOriginal10868)
    case during(CombatRoundOriginal10868)
    case final(CombatRoundOriginal10868, CombatRoundResult10868)
}

nonisolated enum CombatRoundAction10868: Equatable {
    case select(CombatRoundOriginalRef10868)
    case details(CombatRoundOriginalRef10868)

    func perform(
        onSelect: ((CombatRoundOriginalRef10868) -> Void)?,
        onDetails: ((CombatRoundOriginalRef10868) -> Void)?
    ) {
        switch self {
        case .select(let ref): onSelect?(ref)
        case .details(let ref): onDetails?(ref)
        }
    }
}

nonisolated enum CombatRoundTimingPresentation10868: Equatable {
    /// The page owns the expanded flag.
    case disclosure(CombatRoundTiming10868)
    /// No binding: the owner's timing content, already expanded.
    case expanded(CombatRoundTiming10868)
}

nonisolated struct CombatRoundInput10868: Equatable {
    let phase: CombatRoundPhase10868
    let eventID: String
    /// "Polymarket · contract results".
    let eyebrow: String
    /// The owner's headline ("Which round for each fighter?"); nil draws none.
    let title: String?
    /// The owner's caption under the headline; nil draws none.
    let caption: String?
    /// Every fighter in the owner's order — never sorted, filtered or capped.
    let groups: [CombatRoundGroup10868]
    let selectedSlotID: String?
    let selectedOriginalID: String?
    /// Read only during and after the fight.
    let finish: CombatRoundFinish10868?
    let timing: CombatRoundTiming10868?

    static let preMatchTitle = "Pre-match chance"
    static let preMatchShort = "Pre-match"
    static let currentTitle = "In-fight chance"
    static let currentShort = "In-fight"
    static let resultTitle = "Contract result"
    static let selectedTag = "Selected"
    static let slotSelectedTag = "Round selected"
    static let detailsTitle = "Original prop & evidence"
    static let chooseInstruction = "Choose a fighter’s round or side to compare."
    static let slotUnavailable = "Selected round unavailable in this update."
    static let sideUnavailable = "Selected side unavailable in this update."
    static let sideUnavailableShort = "Selected side unavailable"
    static let overviewUnavailable = "Side unavailable in this update"
    static let scaleKey = "Track runs from 0% to 100% · each mark is that side’s own chance"
    static let preMatchKey = "Hollow mark: pre-match chance"
    static let currentKey = "Filled mark: in-fight chance"
    static let notDrawn = "Not drawn on the track"
    static let scaleStart = "0%"
    static let scaleEnd = "100%"

    // MARK: Identity

    private static func repeated(_ ids: [String]) -> Set<String> {
        var seen = Set<String>()
        var repeated = Set<String>()
        for id in ids where !seen.insert(id).inserted { repeated.insert(id) }
        return repeated
    }

    /// Fighter group ids carried more than once. Their slots get no action.
    var duplicateGroupIDs: Set<String> { Self.repeated(groups.map(\.id)) }

    /// Slot ids carried more than once anywhere on the card. Such slots get no
    /// action and cannot be selected.
    var duplicateSlotIDs: Set<String> { Self.repeated(groups.flatMap { $0.slots.map(\.id) }) }

    /// Original ids carried more than once anywhere on the card. Such originals
    /// get no action and cannot be selected.
    var duplicateOriginalIDs: Set<String> {
        Self.repeated(places.flatMap { $0.market.originals.map(\.id) })
    }

    /// Every captured slot in the owner's order.
    var places: [CombatRoundPlace10868] {
        groups.flatMap { group in
            group.slots.compactMap { slot in
                slot.state.market.map { CombatRoundPlace10868(group: group, slot: slot, market: $0) }
            }
        }
    }

    func place(_ group: CombatRoundGroup10868, _ slot: CombatRoundSlot10868) -> CombatRoundPlace10868? {
        slot.state.market.map { CombatRoundPlace10868(group: group, slot: slot, market: $0) }
    }

    func ref(_ original: CombatRoundOriginal10868, at place: CombatRoundPlace10868) -> CombatRoundOriginalRef10868 {
        CombatRoundOriginalRef10868(
            eventID: eventID,
            groupID: place.group.id,
            slotID: place.slot.id,
            marketID: original.marketID,
            originalID: original.id
        )
    }

    private func isUniqueSlot(_ group: CombatRoundGroup10868, _ slot: CombatRoundSlot10868) -> Bool {
        !duplicateGroupIDs.contains(group.id) && !duplicateSlotIDs.contains(slot.id)
    }

    private func isUnique(_ original: CombatRoundOriginal10868, at place: CombatRoundPlace10868) -> Bool {
        isUniqueSlot(place.group, place.slot) && !duplicateOriginalIDs.contains(original.id)
    }

    // MARK: Selection

    /// Exact ids only. A missing, withdrawn or duplicated id gets no substitute,
    /// and every original stays listed.
    var selection: CombatRoundSelection10868 {
        switch (selectedSlotID, selectedOriginalID) {
        case (nil, nil):
            return .none
        case (nil, let originalID?):
            guard !duplicateOriginalIDs.contains(originalID) else { return .unavailable(originalID) }
            let holders = places.filter { $0.market.originals.contains { $0.id == originalID } }
            guard holders.count == 1, let place = holders.first, isUniqueSlot(place.group, place.slot),
                  let original = place.market.originals.first(where: { $0.id == originalID })
            else { return .unavailable(originalID) }
            return .original(place, original)
        case (let slotID?, let originalID):
            let matches = groups.flatMap { group in
                group.slots.filter { $0.id == slotID }.map { (group, $0) }
            }
            guard matches.count == 1, let match = matches.first, !duplicateGroupIDs.contains(match.0.id) else {
                return .unavailable(slotID)
            }
            let (group, slot) = match
            guard let place = self.place(group, slot) else { return .slotWithoutMarket(group, slot) }
            guard let originalID else { return .slot(place) }
            guard !duplicateOriginalIDs.contains(originalID),
                  let original = place.market.originals.first(where: { $0.id == originalID })
            else { return .sideUnavailable(place, originalID) }
            return .original(place, original)
        }
    }

    /// The selected slot, captured or not.
    func isSelectedSlot(_ group: CombatRoundGroup10868, _ slot: CombatRoundSlot10868) -> Bool {
        if let place = selection.place { return place.isAt(group, slot) }
        if case .slotWithoutMarket(let selectedGroup, let selectedSlot) = selection {
            return selectedGroup.id == group.id && selectedSlot.id == slot.id
        }
        return false
    }

    func isSelected(_ original: CombatRoundOriginal10868, at place: CombatRoundPlace10868) -> Bool {
        guard case .original(let selected, let selectedOriginal) = selection else { return false }
        return selected.isAt(place.group, place.slot) && selectedOriginal.id == original.id
    }

    var selectionNotice: String? {
        switch selection {
        case .unavailable, .slotWithoutMarket: Self.slotUnavailable
        case .sideUnavailable: Self.sideUnavailable
        case .none, .slot, .original: nil
        }
    }

    /// The host-selected side, else the host's overview side, else every side.
    /// Never Yes, the winner, the first or a neighbour by default.
    func lead(_ place: CombatRoundPlace10868) -> CombatRoundLead10868 {
        switch selection {
        case .original(let selected, let original) where selected.isAt(place.group, place.slot):
            return .original(original, selected: true)
        case .sideUnavailable(let selected, _) where selected.isAt(place.group, place.slot):
            return .unavailable(Self.sideUnavailableShort)
        default:
            break
        }
        guard let overviewID = place.market.overviewOriginalID else { return .sides }
        let matches = place.market.originals.filter { $0.id == overviewID }
        guard matches.count == 1, !duplicateOriginalIDs.contains(overviewID) else {
            return .unavailable(Self.overviewUnavailable)
        }
        return .original(matches[0], selected: false)
    }

    // MARK: Phase visibility

    func beforeReading(_ original: CombatRoundOriginal10868) -> CombatRoundReading10868 {
        original.before.map { .value($0) } ?? .missing(original.beforeMissing)
    }

    /// During the fight only. Never falls back to the pre-match reading.
    func currentReading(_ original: CombatRoundOriginal10868) -> CombatRoundReading10868? {
        guard phase == .during else { return nil }
        switch original.current {
        case .recorded(let observation, _): return .value(observation)
        case .unavailable(let text), .withheld(let text): return .missing(text)
        }
    }

    /// The owner's movement line, only beside an admitted current observation.
    func movement(_ original: CombatRoundOriginal10868) -> String? {
        guard phase == .during, case .recorded(_, let movement) = original.current else { return nil }
        return movement
    }

    /// The filled current key appears only beside an admitted current observation.
    func showsCurrentMark(_ original: CombatRoundOriginal10868) -> Bool {
        if case .value? = currentReading(original) { return true }
        return false
    }

    /// After the fight only. Any supplied current reading is ignored then, so a
    /// settled 0/100 price can never read as a chance.
    func result(_ original: CombatRoundOriginal10868) -> CombatRoundResult10868? {
        phase == .final ? original.result : nil
    }

    /// The owner's qualification beside the result, after the fight only.
    func resultDetail(_ original: CombatRoundOriginal10868) -> String? {
        phase == .final ? original.resultDetail : nil
    }

    /// Nil before the fight.
    var visibleFinish: CombatRoundFinish10868? { phase == .before ? nil : finish }

    /// The track's marks for one original. Each mark is that original's own
    /// reading; nothing is complemented, normalized or borrowed from the other
    /// side, and a missing, withheld or out-of-range reading draws no mark.
    func railMarks(_ original: CombatRoundOriginal10868) -> CombatRoundRailMarks10868 {
        let before = original.before.flatMap { CombatRoundGeometry10868.position($0.probability) }
        var current: Double?
        if phase == .during, case .recorded(let observation, _) = original.current {
            current = CombatRoundGeometry10868.position(observation.probability)
        }
        return CombatRoundRailMarks10868(before: before, current: current)
    }

    /// The scale always (when there is a captured slot), the hollow pre-match
    /// mark, then the filled in-fight mark during the fight.
    var keyItems: [CombatRoundKeyItem10868] {
        guard !places.isEmpty else { return [] }
        return phase == .during ? [.scale, .preMatch, .current] : [.scale, .preMatch]
    }

    var comparison: CombatRoundComparison10868? {
        guard let original = selection.original else { return nil }
        switch phase {
        case .before: return .before(original)
        case .during: return .during(original)
        case .final: return .final(original, original.result)
        }
    }

    /// Asks for a tap only when one does something.
    func instruction(canSelect: Bool) -> String? {
        canSelect && !places.isEmpty ? Self.chooseInstruction : nil
    }

    // MARK: Actions and timing

    /// A tile selects the exact side it leads with — never a side it would have
    /// to choose.
    func tileAction(_ place: CombatRoundPlace10868, canSelect: Bool) -> CombatRoundAction10868? {
        guard canSelect, case .original(let original, _) = lead(place), isUnique(original, at: place) else { return nil }
        return .select(ref(original, at: place))
    }

    func sideAction(_ original: CombatRoundOriginal10868, at place: CombatRoundPlace10868, canSelect: Bool) -> CombatRoundAction10868? {
        guard canSelect, isUnique(original, at: place) else { return nil }
        return .select(ref(original, at: place))
    }

    /// Originals listed as rows, each with exactly the action `sideAction` permits.
    private func listed(
        _ originals: [CombatRoundOriginal10868],
        at place: CombatRoundPlace10868,
        canSelect: Bool
    ) -> [CombatRoundTileSide10868] {
        originals.map { CombatRoundTileSide10868(original: $0, action: sideAction($0, at: place, canSelect: canSelect)) }
    }

    /// Whether the panel beneath the map lists this slot's sides: only for the
    /// selected slot, and not when its tile already lists every side (chosen
    /// with no side and no overview), so no side list is mounted twice.
    func panelListsSides(_ place: CombatRoundPlace10868) -> Bool {
        guard let selected = selection.place, selected.isAt(place.group, place.slot) else { return false }
        return lead(place) != .sides
    }

    /// The side rows the selected panel mounts for this slot — the View's own
    /// list. Empty unless `panelListsSides`.
    func panelSides(_ place: CombatRoundPlace10868, canSelect: Bool) -> [CombatRoundTileSide10868] {
        panelListsSides(place) ? listed(place.market.originals, at: place, canSelect: canSelect) : []
    }

    /// The tile the View draws. A slot with no market keeps its owner's words
    /// and nothing else. A rail that neither selects its side nor belongs to
    /// the selected slot would hide the other original, so it is listed in the
    /// tile; an unavailable side that is not the selected slot's keeps its
    /// notice and lists every original. A tile never repeats side rows the
    /// panel beneath the map mounts, and no duplicated id gains an action.
    func tilePresentation(
        _ group: CombatRoundGroup10868,
        _ slot: CombatRoundSlot10868,
        canSelect: Bool
    ) -> CombatRoundTilePresentation10868 {
        guard let place = self.place(group, slot) else { return .absent(slot.state.absentWords ?? "") }
        let panelLists = panelListsSides(place)
        switch lead(place) {
        case .sides:
            return .sides(listed(place.market.originals, at: place, canSelect: canSelect))
        case .unavailable(let words):
            return panelLists
                ? .unavailable(words)
                : .unavailableWithSides(words, sides: listed(place.market.originals, at: place, canSelect: canSelect))
        case .original(let original, let selected):
            let action = tileAction(place, canSelect: canSelect)
            let others = place.market.originals.filter { $0.id != original.id }
            if action != nil || panelLists || others.isEmpty {
                return .rail(original, selected: selected, action: action)
            }
            return .railWithSides(original, others: listed(others, at: place, canSelect: canSelect))
        }
    }

    func detailsAction(canOpenDetails: Bool) -> CombatRoundAction10868? {
        guard canOpenDetails, case .original(let place, let original) = selection else { return nil }
        return .details(ref(original, at: place))
    }

    /// Timing only for the exact resolved selection.
    func timingPresentation(hasBinding: Bool) -> CombatRoundTimingPresentation10868? {
        guard let timing, let original = selection.original, original.id == timing.originalID else { return nil }
        return hasBinding ? .disclosure(timing) : .expanded(timing)
    }

    // MARK: VoiceOver

    var phaseSpoken: String {
        switch phase {
        case .before: "Before the fight"
        case .during: "During the fight"
        case .final: "Final"
        }
    }

    var accessibilityHeader: String {
        ([eyebrow, title, caption, phaseSpoken].compactMap { $0 }).joined(separator: ". ")
    }

    /// The key, spoken once for the card.
    var accessibilityKey: String? {
        guard !keyItems.isEmpty else { return nil }
        return keyItems.map { item -> String in
            switch item {
            case .scale: Self.scaleKey
            case .preMatch: Self.preMatchKey
            case .current: Self.currentKey
            }
        }
        .joined(separator: ". ")
    }

    /// "<fighter>, <round>" in the owner's words.
    func accessibilitySlotLabel(_ group: CombatRoundGroup10868, _ slot: CombatRoundSlot10868) -> String {
        "\(group.label), \(slot.label)"
    }

    /// One original's readings for the phase: pre-match, then in-fight or result.
    func accessibilityReadings(_ original: CombatRoundOriginal10868, detailed: Bool) -> String {
        var parts = ["\(Self.preMatchTitle): \(Self.spoken(beforeReading(original), detailed: detailed))"]
        if let current = currentReading(original) {
            parts.append("\(Self.currentTitle): \(Self.spoken(current, detailed: detailed))")
        }
        if let movement = movement(original) { parts.append(movement) }
        if let result = result(original) {
            if detailed, let detail = resultDetail(original) {
                parts.append("\(Self.resultTitle): \(result.text), \(detail)")
            } else {
                parts.append("\(Self.resultTitle): \(result.text)")
            }
        }
        return parts.joined(separator: "; ")
    }

    /// A captured tile: its lead with full provenance, then every other side, so
    /// no side is reachable only by sight. A slot with no market speaks its
    /// owner's words.
    func accessibilityTileValue(_ group: CombatRoundGroup10868, _ slot: CombatRoundSlot10868) -> String {
        guard let place = self.place(group, slot) else {
            var parts = [slot.state.absentWords ?? ""]
            if isSelectedSlot(group, slot) { parts.append(Self.selectedTag) }
            return parts.joined(separator: ". ")
        }
        var parts: [String] = []
        var spokenIDs = Set<String>()
        switch lead(place) {
        case .original(let original, let selected):
            parts.append(accessibilityLeadValue(original))
            if selected { parts.append(Self.selectedTag) }
            spokenIDs.insert(original.id)
        case .unavailable(let words):
            parts.append(words)
        case .sides:
            break
        }
        let others = place.market.originals.filter { !spokenIDs.contains($0.id) }
        let prefix = spokenIDs.isEmpty ? "" : "Also "
        for original in others {
            parts.append("\(prefix)\(original.label). \(accessibilityReadings(original, detailed: false))")
        }
        if isSelectedSlot(group, slot), selection.original == nil { parts.append(Self.slotSelectedTag) }
        return parts.joined(separator: ". ")
    }

    /// A lead side alone, with full provenance. A static overview's rail speaks
    /// this; the originals listed beside it speak for themselves.
    func accessibilityLeadValue(_ original: CombatRoundOriginal10868) -> String {
        "\(original.label). \(accessibilityReadings(original, detailed: true))"
    }

    func accessibilitySideValue(_ original: CombatRoundOriginal10868, at place: CombatRoundPlace10868) -> String {
        var parts = [accessibilityReadings(original, detailed: true)]
        if isSelected(original, at: place) { parts.append(Self.selectedTag) }
        return parts.joined(separator: "; ")
    }

    /// The selected original's comparison, each reading with its provenance.
    var accessibilityComparison: String? {
        guard comparison != nil, case .original(let place, let original) = selection else { return nil }
        return "\(place.market.question), original \(original.label). "
            + "\(accessibilitySlotLabel(place.group, place.slot)). "
            + accessibilityReadings(original, detailed: true)
    }

    var accessibilityFinish: String? {
        guard let finish = visibleFinish else { return nil }
        let lines = ([finish.title] + finish.lines).joined(separator: ". ")
        return ([lines, finish.accessibilityDetail].compactMap { $0 }).joined(separator: ". ")
    }

    /// A figure with its provenance; a figure the track cannot place says so.
    private static func spoken(_ reading: CombatRoundReading10868, detailed: Bool) -> String {
        switch reading {
        case .value(let observation):
            var parts = [observation.text]
            if detailed { parts.append(observation.detail) }
            if CombatRoundGeometry10868.position(observation.probability) == nil { parts.append(notDrawn) }
            return parts.joined(separator: ", ")
        case .missing(let text):
            return text
        }
    }
}

nonisolated enum CombatRoundArrangement10868: Equatable {
    /// One subview, or more than two: stacked in order.
    case single
    case sideBySide
    case stacked
}

nonisolated struct CombatRoundColumns10868: Equatable {
    let first: CGFloat
    let second: CGFloat
}

nonisolated enum CombatRoundGeometry10868 {
    /// A probability's place on the 0–100% track. Zero is a place; anything
    /// non-finite or outside 0...1 is none — never clamped or guessed.
    static func position(_ probability: Double) -> Double? {
        guard probability.isFinite, probability >= 0, probability <= 1 else { return nil }
        return probability
    }

    /// A mark's x on a track of `width`, inset so a 0% or 100% mark stays whole.
    static func markX(_ position: Double, width: CGFloat, inset: CGFloat) -> CGFloat {
        let usable = max(0, width - 2 * inset)
        return inset + usable * CGFloat(position)
    }

    /// The owner's words, split only at whitespace, for measuring the widest
    /// unbreakable word. Typography, not parsing: nothing is interpreted.
    static func words(_ text: String) -> [String] {
        text.split(whereSeparator: \.isWhitespace).map(String.init)
    }

    static func columnWidth(available: CGFloat, columns: Int, spacing: CGFloat) -> CGFloat {
        guard columns > 0 else { return 0 }
        return max(0, (available - CGFloat(columns - 1) * spacing) / CGFloat(columns))
    }

    /// As many equal columns as keep every item whole: from one per item down
    /// to one. A column must reach the scaled minimum and every item's measured
    /// width (its figure and widest word) must fit it. There is no fixed
    /// ceiling; nothing shrinks or truncates to fit.
    static func columnCount(
        available: CGFloat?,
        count: Int,
        spacing: CGFloat,
        minimumColumnWidth: CGFloat,
        forceSingle: Bool,
        fits: (CGFloat) -> Bool
    ) -> Int {
        guard count > 0 else { return 0 }
        if forceSingle { return 1 }
        // No width proposed (ideal size) or an unbounded one: one row.
        guard let available, available.isFinite else { return count }
        guard available > 0 else { return 1 }
        var columns = count
        while columns > 1 {
            let width = columnWidth(available: available, columns: columns, spacing: spacing)
            if width >= minimumColumnWidth, fits(width) { return columns }
            columns -= 1
        }
        return 1
    }

    /// The narrowest a fighter group may be beside another: its widest row of
    /// round tiles at their minimum. Fighters sit side by side only when each
    /// keeps every round on one row.
    static func groupMinimumWidth(slots: Int, tileMinimum: CGFloat, spacing: CGFloat) -> CGFloat {
        guard slots > 0 else { return 0 }
        return CGFloat(slots) * tileMinimum + CGFloat(slots - 1) * spacing
    }

    /// Item indices row by row, in the owner's order.
    static func rows(count: Int, columns: Int) -> [[Int]] {
        guard count > 0, columns > 0 else { return [] }
        return stride(from: 0, to: count, by: columns).map { start in Array(start..<min(start + columns, count)) }
    }

    /// Side by side only when both subviews keep their whole measured width.
    /// Otherwise stacked. Nothing shrinks to fit.
    static func pairArrangement(
        available: CGFloat?,
        first: CGFloat,
        second: CGFloat,
        spacing: CGFloat,
        equalColumns: Bool,
        forceStack: Bool
    ) -> CombatRoundArrangement10868 {
        if forceStack { return .stacked }
        guard first.isFinite, second.isFinite, first >= 0, second >= 0 else { return .stacked }
        guard let available, available.isFinite else { return .sideBySide }
        return neededWidth(first: first, second: second, spacing: spacing, equalColumns: equalColumns) <= available
            ? .sideBySide : .stacked
    }

    static func neededWidth(first: CGFloat, second: CGFloat, spacing: CGFloat, equalColumns: Bool) -> CGFloat {
        equalColumns ? 2 * max(first, second) + spacing : first + second + spacing
    }

    static func columns(total: CGFloat, first: CGFloat, spacing: CGFloat, equalColumns: Bool) -> CombatRoundColumns10868 {
        if equalColumns {
            let half = max(0, (total - spacing) / 2)
            return CombatRoundColumns10868(first: half, second: half)
        }
        let leading = min(max(0, first), max(0, total - spacing))
        return CombatRoundColumns10868(first: leading, second: max(0, total - spacing - leading))
    }
}

/// Items in equal columns, row by row in the owner's order. Items in one row
/// share the row's height. Used for the fighter groups and for each group's
/// round tiles.
struct CombatRoundGridLayout10868: Layout {
    var spacing: CGFloat
    var minimumColumnWidth: CGFloat
    var forceSingleColumn: Bool

    private func columnCount(_ width: CGFloat?, _ subviews: Subviews) -> Int {
        CombatRoundGeometry10868.columnCount(
            available: width,
            count: subviews.count,
            spacing: spacing,
            minimumColumnWidth: minimumColumnWidth,
            forceSingle: forceSingleColumn
        ) { column in
            subviews.allSatisfy { $0.sizeThatFits(ProposedViewSize(width: column, height: nil)).width <= column + 0.5 }
        }
    }

    private func columnWidth(_ width: CGFloat?, columns: Int, _ subviews: Subviews) -> CGFloat {
        if let width, width.isFinite {
            return CombatRoundGeometry10868.columnWidth(available: width, columns: columns, spacing: spacing)
        }
        return subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0
    }

    private func rowHeight(_ row: [Int], column: CGFloat, _ subviews: Subviews) -> CGFloat {
        row.map { subviews[$0].sizeThatFits(ProposedViewSize(width: column, height: nil)).height }.max() ?? 0
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        let columns = columnCount(proposal.width, subviews)
        let column = columnWidth(proposal.width, columns: columns, subviews)
        let rows = CombatRoundGeometry10868.rows(count: subviews.count, columns: columns)
        let height = rows.map { rowHeight($0, column: column, subviews) }.reduce(0, +)
            + spacing * CGFloat(max(0, rows.count - 1))
        let width = proposal.width ?? (column * CGFloat(columns) + spacing * CGFloat(max(0, columns - 1)))
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        let columns = columnCount(bounds.width, subviews)
        let column = columnWidth(bounds.width, columns: columns, subviews)
        var y = bounds.minY
        for row in CombatRoundGeometry10868.rows(count: subviews.count, columns: columns) {
            let height = rowHeight(row, column: column, subviews)
            for (position, index) in row.enumerated() {
                subviews[index].place(
                    at: CGPoint(x: bounds.minX + CGFloat(position) * (column + spacing), y: y),
                    anchor: .topLeading,
                    proposal: ProposedViewSize(width: column, height: height)
                )
            }
            y += height + spacing
        }
    }
}

/// Two subviews side by side while both keep their whole measured width, else
/// stacked at full width. Used for the selected comparison pair.
struct CombatRoundPairLayout10868: Layout {
    var spacing: CGFloat
    var equalColumns: Bool
    var forceStack: Bool

    private func idealWidths(_ subviews: Subviews) -> CombatRoundColumns10868 {
        CombatRoundColumns10868(
            first: subviews[0].sizeThatFits(.unspecified).width,
            second: subviews[1].sizeThatFits(.unspecified).width
        )
    }

    private func arrangement(_ width: CGFloat?, _ subviews: Subviews) -> CombatRoundArrangement10868 {
        guard subviews.count == 2 else { return .single }
        let ideal = idealWidths(subviews)
        return CombatRoundGeometry10868.pairArrangement(
            available: width,
            first: ideal.first,
            second: ideal.second,
            spacing: spacing,
            equalColumns: equalColumns,
            forceStack: forceStack
        )
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        switch arrangement(proposal.width, subviews) {
        case .single, .stacked:
            return stackedSize(width: proposal.width, subviews: subviews)
        case .sideBySide:
            let ideal = idealWidths(subviews)
            let total = proposal.width ?? CombatRoundGeometry10868.neededWidth(
                first: ideal.first, second: ideal.second, spacing: spacing, equalColumns: equalColumns
            )
            let widths = CombatRoundGeometry10868.columns(total: total, first: ideal.first, spacing: spacing, equalColumns: equalColumns)
            let height = max(
                subviews[0].sizeThatFits(ProposedViewSize(width: widths.first, height: nil)).height,
                subviews[1].sizeThatFits(ProposedViewSize(width: widths.second, height: nil)).height
            )
            return CGSize(width: total, height: height)
        }
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        switch arrangement(bounds.width, subviews) {
        case .single, .stacked:
            var y = bounds.minY
            for subview in subviews {
                let size = subview.sizeThatFits(ProposedViewSize(width: bounds.width, height: nil))
                subview.place(
                    at: CGPoint(x: bounds.minX, y: y),
                    anchor: .topLeading,
                    proposal: ProposedViewSize(width: bounds.width, height: size.height)
                )
                y += size.height + spacing
            }
        case .sideBySide:
            let ideal = idealWidths(subviews)
            let widths = CombatRoundGeometry10868.columns(total: bounds.width, first: ideal.first, spacing: spacing, equalColumns: equalColumns)
            subviews[0].place(
                at: CGPoint(x: bounds.minX, y: bounds.minY),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: widths.first, height: nil)
            )
            subviews[1].place(
                at: CGPoint(x: bounds.minX + widths.first + spacing, y: bounds.minY),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: widths.second, height: nil)
            )
        }
    }

    private func stackedSize(width: CGFloat?, subviews: Subviews) -> CGSize {
        var height: CGFloat = 0
        var widest: CGFloat = 0
        for (index, subview) in subviews.enumerated() {
            let size = subview.sizeThatFits(ProposedViewSize(width: width, height: nil))
            height += size.height + (index > 0 ? spacing : 0)
            widest = max(widest, size.width)
        }
        return CGSize(width: width ?? widest, height: height)
    }
}

/// Wrapping owner text that never breaks inside a word: a hidden, zero-height
/// strut of its words makes the widest word part of the measured width, so the
/// grid drops a column before any word would split.
private struct CombatRoundWrappedText10868: View {
    let text: String
    let font: Font
    let color: Color
    var alignment: TextAlignment = .center

    private var frameAlignment: Alignment {
        switch alignment {
        case .leading: .leading
        case .trailing: .trailing
        default: .center
        }
    }

    var body: some View {
        ZStack(alignment: frameAlignment) {
            VStack(spacing: 0) {
                ForEach(Array(CombatRoundGeometry10868.words(text).enumerated()), id: \.offset) { _, word in
                    Text(word).font(font).fixedSize()
                }
            }
            .frame(height: 0)
            .hidden()
            Text(text)
                .font(font)
                .foregroundStyle(color)
                .multilineTextAlignment(alignment)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// The slim 0–100% track: a hollow pre-match mark, a filled in-fight mark and
/// the segment between them when both are drawn. Decorative — every reading
/// it carries is also a figure and is spoken by its control.
private struct CombatRoundTrack10868: View {
    let marks: CombatRoundRailMarks10868
    let height: CGFloat
    let markSize: CGFloat

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width
            let inset = markSize / 2
            let middle = geometry.size.height / 2
            ZStack(alignment: .topLeading) {
                Capsule()
                    .fill(DS.border)
                    .frame(width: width, height: 2)
                    .position(x: width / 2, y: middle)
                if let segment = marks.segment {
                    let from = CombatRoundGeometry10868.markX(segment.lowerBound, width: width, inset: inset)
                    let to = CombatRoundGeometry10868.markX(segment.upperBound, width: width, inset: inset)
                    Capsule()
                        .fill(DS.blue.opacity(0.45))
                        .frame(width: max(0, to - from), height: 3)
                        .position(x: (from + to) / 2, y: middle)
                }
                if let before = marks.before {
                    Circle()
                        .fill(DS.cardBg)
                        .overlay(Circle().strokeBorder(DS.blue, lineWidth: 2))
                        .frame(width: markSize, height: markSize)
                        .position(x: CombatRoundGeometry10868.markX(before, width: width, inset: inset), y: middle)
                }
                if let current = marks.current {
                    Circle()
                        .fill(DS.blue)
                        .frame(width: markSize, height: markSize)
                        .position(x: CombatRoundGeometry10868.markX(current, width: width, inset: inset), y: middle)
                }
            }
        }
        .frame(maxWidth: .infinity, minHeight: height, maxHeight: height)
        .accessibilityHidden(true)
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum CombatRoundAccessibilityID10868 {
    static let key = "combatRound10868.key"
    static let comparison = "combatRound10868.comparison"
    static let finish = "combatRound10868.finish"
    static func group(_ groupID: String) -> String { "combatRound10868.group.\(groupID)" }
    static func tile(_ slotID: String) -> String { "combatRound10868.tile.\(slotID)" }
    static func side(_ slotID: String, _ originalID: String) -> String { "combatRound10868.side.\(slotID).\(originalID)" }
    static func details(_ originalID: String) -> String { "combatRound10868.details.\(originalID)" }
}

struct CombatRoundPresentation10868: View {
    let input: CombatRoundInput10868
    var onSelect: ((CombatRoundOriginalRef10868) -> Void)? = nil
    var onDetails: ((CombatRoundOriginalRef10868) -> Void)? = nil
    /// Page-owned. Nil shows the owner's timing content already expanded.
    var timingExpanded: Binding<Bool>? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .headline) private var tileFigureSize: CGFloat = 20
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 14
    @ScaledMetric(relativeTo: .caption) private var markSize: CGFloat = 10
    @ScaledMetric(relativeTo: .caption) private var minimumTileWidth: CGFloat = 88
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .title3) private var sideFigureSize: CGFloat = 20

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }
    private let tileSpacing: CGFloat = 8

    /// Fighters sit side by side only when each keeps its widest row of rounds.
    private var minimumGroupWidth: CGFloat {
        CombatRoundGeometry10868.groupMinimumWidth(
            slots: input.groups.map(\.slots.count).max() ?? 0,
            tileMinimum: minimumTileWidth,
            spacing: tileSpacing
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            key
            if let instruction = input.instruction(canSelect: canSelect) {
                Text(instruction)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            CombatRoundGridLayout10868(
                spacing: 16,
                minimumColumnWidth: minimumGroupWidth,
                forceSingleColumn: typeSize.isAccessibilitySize
            ) {
                ForEach(Array(input.groups.enumerated()), id: \.offset) { _, group in
                    groupSection(group)
                }
            }
            if let notice = input.selectionNotice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            selectedPanel
            timing
            detailsButton
            finishContext
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Header and key

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.eyebrow)
                .font(.caption.weight(.semibold))
                .textCase(.uppercase)
                .foregroundStyle(DS.blue)
            if let title = input.title {
                Text(title).font(.title2.bold()).foregroundStyle(DS.textPrimary)
            }
            if let caption = input.caption {
                Text(caption).font(.caption).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader)
        .accessibilityAddTraits(.isHeader)
    }

    /// Shape plus words for every mark the tracks can carry — never colour alone.
    @ViewBuilder private var key: some View {
        let items = input.keyItems
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .center, spacing: 6) {
                        keySwatch(item)
                        Text(keyWords(item))
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityKey ?? "")
            .accessibilityIdentifier(CombatRoundAccessibilityID10868.key)
        }
    }

    private func keyWords(_ item: CombatRoundKeyItem10868) -> String {
        switch item {
        case .scale: CombatRoundInput10868.scaleKey
        case .preMatch: CombatRoundInput10868.preMatchKey
        case .current: CombatRoundInput10868.currentKey
        }
    }

    @ViewBuilder private func keySwatch(_ item: CombatRoundKeyItem10868) -> some View {
        switch item {
        case .scale:
            HStack(spacing: 2) {
                Text(CombatRoundInput10868.scaleStart)
                Capsule().fill(DS.border).frame(width: 18, height: 2)
                Text(CombatRoundInput10868.scaleEnd)
            }
            .font(.caption2.weight(.semibold))
            .monospacedDigit()
            .foregroundStyle(DS.textPrimary)
            .fixedSize()
        case .preMatch:
            keyMark(.hollow)
        case .current:
            keyMark(.filled)
        }
    }

    // MARK: Fighter groups and round tiles

    private func groupSection(_ group: CombatRoundGroup10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            CombatRoundWrappedText10868(
                text: group.label,
                font: .subheadline.weight(.semibold),
                color: DS.textPrimary,
                alignment: .leading
            )
            .accessibilityAddTraits(.isHeader)
            .accessibilityIdentifier(CombatRoundAccessibilityID10868.group(group.id))
            CombatRoundGridLayout10868(
                spacing: tileSpacing,
                minimumColumnWidth: minimumTileWidth,
                forceSingleColumn: typeSize.isAccessibilitySize
            ) {
                ForEach(Array(group.slots.enumerated()), id: \.offset) { _, slot in
                    tile(group, slot)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
    }

    @ViewBuilder private func tile(_ group: CombatRoundGroup10868, _ slot: CombatRoundSlot10868) -> some View {
        let label = input.accessibilitySlotLabel(group, slot)
        let selectedTraits: AccessibilityTraits = input.isSelectedSlot(group, slot) ? .isSelected : []
        switch input.tilePresentation(group, slot, canSelect: canSelect) {
        case .absent(let words):
            // No market: the owner's words only. No figure, track, result or action.
            tileFrame(group, slot, absent: true) {
                Text("—")
                    .font(.system(size: tileFigureSize, weight: .medium))
                    .foregroundStyle(DS.textSecondary)
                    .accessibilityHidden(true)
                CombatRoundWrappedText10868(text: words, font: .caption2.weight(.semibold), color: DS.textSecondary, alignment: .leading)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(label)
            .accessibilityValue(input.accessibilityTileValue(group, slot))
            .accessibilityAddTraits(selectedTraits)
            .accessibilityIdentifier(CombatRoundAccessibilityID10868.tile(slot.id))
        case .rail(let original, let selected, let action):
            control(action) {
                tileFrame(group, slot, absent: false) { leadContent(.original(original, selected: selected)) }
            }
            .accessibilityLabel(label)
            .accessibilityValue(input.accessibilityTileValue(group, slot))
            .accessibilityHint(action == nil ? "" : "Selects this side’s comparison")
            .accessibilityAddTraits(selectedTraits)
            .accessibilityIdentifier(CombatRoundAccessibilityID10868.tile(slot.id))
        case .unavailable(let words):
            control(nil) {
                tileFrame(group, slot, absent: false) { leadContent(.unavailable(words)) }
            }
            .accessibilityLabel(label)
            .accessibilityValue(input.accessibilityTileValue(group, slot))
            .accessibilityAddTraits(selectedTraits)
            .accessibilityIdentifier(CombatRoundAccessibilityID10868.tile(slot.id))
        case .railWithSides(let original, let others):
            // The lead is static; each other original is its own row. The tile
            // only groups them, so no side control sits inside a button.
            if let place = input.place(group, slot) {
                tileFrame(group, slot, absent: false) {
                    leadContent(.original(original, selected: false))
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel("\(label), \(original.label)")
                        .accessibilityValue(input.accessibilityLeadValue(original))
                    tileSides(place, others)
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(label)
                .accessibilityIdentifier(CombatRoundAccessibilityID10868.tile(slot.id))
            }
        case .unavailableWithSides(let words, let sides):
            if let place = input.place(group, slot) {
                tileFrame(group, slot, absent: false) {
                    leadContent(.unavailable(words))
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel("\(label), \(words)")
                    tileSides(place, sides)
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(label)
                .accessibilityIdentifier(CombatRoundAccessibilityID10868.tile(slot.id))
            }
        case .sides(let sides):
            // Every side is its own control; the tile only groups them.
            if let place = input.place(group, slot) {
                tileFrame(group, slot, absent: false) { tileSides(place, sides) }
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel(label)
                    .accessibilityIdentifier(CombatRoundAccessibilityID10868.tile(slot.id))
            }
        }
    }

    /// The originals a tile lists itself, compact, each with its own action.
    private func tileSides(_ place: CombatRoundPlace10868, _ sides: [CombatRoundTileSide10868]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(sides.enumerated()), id: \.offset) { _, side in
                sideControl(side.original, at: place, compact: true, action: side.action)
            }
        }
    }

    /// Selection is an outline plus a named tag; a slot with no market is a
    /// dashed outline — never colour alone, and never a result symbol's shape.
    private func tileFrame<Content: View>(
        _ group: CombatRoundGroup10868,
        _ slot: CombatRoundSlot10868,
        absent: Bool,
        @ViewBuilder content: () -> Content
    ) -> some View {
        let selected = input.isSelectedSlot(group, slot)
        return VStack(alignment: .leading, spacing: 8) {
            CombatRoundWrappedText10868(
                text: slot.label,
                font: .footnote.weight(.semibold),
                color: DS.textPrimary,
                alignment: .leading
            )
            if selected { selectedTag }
            content()
        }
        .padding(.vertical, 12)
        .padding(.horizontal, 8)
        .frame(maxWidth: .infinity, minHeight: 44, maxHeight: .infinity, alignment: .topLeading)
        .background(absent ? DS.surface : DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(
                    selected ? DS.textPrimary : DS.border,
                    style: absent
                        ? StrokeStyle(lineWidth: selected ? 2 : 1, dash: [4, 3])
                        : StrokeStyle(lineWidth: selected ? 2 : 1)
                )
        )
        .contentShape(Rectangle())
    }

    private var selectedTag: some View {
        Label(CombatRoundInput10868.selectedTag, systemImage: "checkmark")
            .font(.caption2.weight(.semibold))
            .foregroundStyle(DS.textPrimary)
            .fixedSize()
    }

    @ViewBuilder private func leadContent(_ lead: CombatRoundLead10868) -> some View {
        switch lead {
        case .original(let original, _):
            VStack(alignment: .leading, spacing: 5) {
                tileFigure(input.beforeReading(original))
                CombatRoundTrack10868(marks: input.railMarks(original), height: trackHeight, markSize: markSize)
                notDrawnNote(original.before)
                HStack(alignment: .center, spacing: 4) {
                    keyMark(.hollow)
                    CombatRoundWrappedText10868(
                        text: "\(original.label) · \(CombatRoundInput10868.preMatchShort)",
                        font: .caption2,
                        color: DS.textSecondary,
                        alignment: .leading
                    )
                }
                if let current = input.currentReading(original) {
                    tileCurrent(current, marked: input.showsCurrentMark(original))
                }
                if let result = input.result(original) {
                    resultLine(result, text: "\(original.label) · \(result.text)", font: .caption.weight(.semibold))
                }
            }
        case .unavailable(let words):
            VStack(alignment: .leading, spacing: 5) {
                CombatRoundTrack10868(marks: CombatRoundRailMarks10868(before: nil, current: nil), height: trackHeight, markSize: markSize)
                CombatRoundWrappedText10868(text: words, font: .caption2.weight(.semibold), color: DS.textSecondary, alignment: .leading)
            }
        case .sides:
            EmptyView()
        }
    }

    /// Visible words when an admitted figure has no place on the track.
    @ViewBuilder private func notDrawnNote(_ observation: CombatRoundObservation10868?) -> some View {
        if let observation, CombatRoundGeometry10868.position(observation.probability) == nil {
            CombatRoundWrappedText10868(
                text: CombatRoundInput10868.notDrawn,
                font: .caption2,
                color: DS.textSecondary,
                alignment: .leading
            )
        }
    }

    /// A figure at the tile size, or the owner's words. Never shrunk.
    @ViewBuilder private func tileFigure(_ reading: CombatRoundReading10868) -> some View {
        switch reading {
        case .value(let observation):
            Text(observation.text)
                .font(.system(size: tileFigureSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize()
        case .missing(let words):
            CombatRoundWrappedText10868(text: words, font: .caption.weight(.semibold), color: DS.textSecondary, alignment: .leading)
        }
    }

    /// The in-fight figure at the pre-match figure's size: equal prominence.
    private func tileCurrent(_ reading: CombatRoundReading10868, marked: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            tileFigure(reading)
            if case .value(let observation) = reading {
                notDrawnNote(observation)
            }
            HStack(spacing: 4) {
                if marked { keyMark(.filled) }
                Text(CombatRoundInput10868.currentShort).font(.caption2).foregroundStyle(DS.textSecondary)
            }
        }
    }

    private enum KeyMark { case hollow, filled }

    @ViewBuilder private func keyMark(_ mark: KeyMark) -> some View {
        switch mark {
        case .hollow:
            Circle().fill(DS.cardBg).overlay(Circle().strokeBorder(DS.blue, lineWidth: 2)).frame(width: markSize, height: markSize)
        case .filled:
            Circle().fill(DS.blue).frame(width: markSize, height: markSize)
        }
    }

    /// The displayed original's own result: symbol and words agree with it.
    private func resultLine(_ result: CombatRoundResult10868, text: String, font: Font) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Image(systemName: result.symbolName).accessibilityHidden(true)
            CombatRoundWrappedText10868(
                text: text,
                font: font,
                color: result.isSettled ? DS.textPrimary : DS.textSecondary,
                alignment: .leading
            )
        }
        .font(font)
        .foregroundStyle(result.isSettled ? DS.textPrimary : DS.textSecondary)
    }

    // MARK: Original sides

    /// The selected slot's side rows (`panelSides`), each with its own track and
    /// readings. Tiles list theirs compactly through `tileSides`.
    @ViewBuilder private func sideList(_ place: CombatRoundPlace10868, _ sides: [CombatRoundTileSide10868]) -> some View {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 6) { sideControls(place, sides) }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 8) { sideControls(place, sides) }
                VStack(alignment: .leading, spacing: 8) { sideControls(place, sides) }
            }
        }
    }

    private func sideControls(_ place: CombatRoundPlace10868, _ sides: [CombatRoundTileSide10868]) -> some View {
        ForEach(Array(sides.enumerated()), id: \.offset) { _, side in
            sideControl(side.original, at: place, compact: false, action: side.action)
        }
    }

    private func sideControl(
        _ original: CombatRoundOriginal10868,
        at place: CombatRoundPlace10868,
        compact: Bool,
        action: CombatRoundAction10868?
    ) -> some View {
        let selected = input.isSelected(original, at: place)
        return control(action) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    CombatRoundWrappedText10868(
                        text: original.label,
                        font: (compact ? Font.caption : Font.subheadline).weight(.semibold),
                        color: DS.textPrimary,
                        alignment: .leading
                    )
                    if selected { selectedTag }
                }
                sideReading(input.beforeReading(original), title: CombatRoundInput10868.preMatchShort, mark: .hollow)
                CombatRoundTrack10868(marks: input.railMarks(original), height: trackHeight, markSize: markSize)
                notDrawnNote(original.before)
                if let current = input.currentReading(original) {
                    sideReading(current, title: CombatRoundInput10868.currentShort, mark: input.showsCurrentMark(original) ? .filled : nil)
                }
                if let result = input.result(original) {
                    resultLine(result, text: result.text, font: .caption.weight(.semibold))
                }
            }
            .padding(compact ? 6 : 10)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 9))
            .overlay(
                RoundedRectangle(cornerRadius: 9)
                    .strokeBorder(selected ? DS.textPrimary : DS.border, lineWidth: selected ? 2 : 1)
            )
            .contentShape(Rectangle())
        }
        .accessibilityLabel("\(input.accessibilitySlotLabel(place.group, place.slot)), \(original.label)")
        .accessibilityValue(input.accessibilitySideValue(original, at: place))
        .accessibilityHint(action == nil ? "" : "Selects this side’s comparison")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(CombatRoundAccessibilityID10868.side(place.slot.id, original.id))
    }

    private func sideReading(_ reading: CombatRoundReading10868, title: String, mark: KeyMark?) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            switch reading {
            case .value(let observation):
                Text(observation.text)
                    .font(.system(size: sideFigureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            case .missing(let text):
                CombatRoundWrappedText10868(text: text, font: .caption.weight(.semibold), color: DS.textSecondary, alignment: .leading)
            }
            HStack(spacing: 4) {
                if let mark { keyMark(mark) }
                Text(title).font(.caption2).foregroundStyle(DS.textSecondary)
            }
        }
    }

    // MARK: Selected slot

    @ViewBuilder private var selectedPanel: some View {
        if let place = input.selection.place {
            VStack(alignment: .leading, spacing: 10) {
                Divider()
                CombatRoundWrappedText10868(
                    text: place.market.question,
                    font: .subheadline.weight(.semibold),
                    color: DS.textPrimary,
                    alignment: .leading
                )
                if let original = input.selection.original {
                    CombatRoundWrappedText10868(
                        text: "Original \(original.label) · \(place.group.label) · \(place.slot.label)",
                        font: .caption,
                        color: DS.textSecondary,
                        alignment: .leading
                    )
                }
                if let comparison = input.comparison {
                    comparisonFigures(comparison)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(input.accessibilityComparison ?? "")
                        .accessibilityIdentifier(CombatRoundAccessibilityID10868.comparison)
                }
                // None when the slot's own tile already lists every side.
                let sides = input.panelSides(place, canSelect: canSelect)
                if !sides.isEmpty {
                    sideList(place, sides)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder private func comparisonFigures(_ comparison: CombatRoundComparison10868) -> some View {
        switch comparison {
        case .before(let original):
            VStack(alignment: .leading, spacing: 8) {
                comparisonValue(input.beforeReading(original), title: preMatchTitle(original), mark: .hollow, movement: nil)
                comparisonTrack(original)
            }
        case .during(let original):
            VStack(alignment: .leading, spacing: 8) {
                CombatRoundPairLayout10868(spacing: 16, equalColumns: true, forceStack: typeSize.isAccessibilitySize) {
                    comparisonValue(input.beforeReading(original), title: preMatchTitle(original), mark: .hollow, movement: nil)
                    if let current = input.currentReading(original) {
                        comparisonValue(
                            current,
                            title: CombatRoundInput10868.currentTitle,
                            mark: input.showsCurrentMark(original) ? .filled : nil,
                            movement: input.movement(original)
                        )
                    }
                }
                comparisonTrack(original)
            }
        case .final(let original, let result):
            VStack(alignment: .leading, spacing: 8) {
                CombatRoundPairLayout10868(spacing: 16, equalColumns: true, forceStack: typeSize.isAccessibilitySize) {
                    comparisonValue(input.beforeReading(original), title: preMatchTitle(original), mark: .hollow, movement: nil)
                    VStack(alignment: .leading, spacing: 5) {
                        Text("\(CombatRoundInput10868.resultTitle) · \(original.label)")
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                        resultLine(result, text: result.text, font: .title3.weight(.semibold))
                        if let detail = input.resultDetail(original) {
                            Text(detail)
                                .font(.caption)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                comparisonTrack(original)
            }
        }
    }

    /// The selected original's track with its 0% and 100% ends named.
    private func comparisonTrack(_ original: CombatRoundOriginal10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            CombatRoundTrack10868(marks: input.railMarks(original), height: trackHeight, markSize: markSize)
            HStack {
                Text(CombatRoundInput10868.scaleStart)
                Spacer(minLength: 8)
                Text(CombatRoundInput10868.scaleEnd)
            }
            .font(.caption2)
            .monospacedDigit()
            .foregroundStyle(DS.textSecondary)
        }
        .accessibilityHidden(true)
    }

    private func preMatchTitle(_ original: CombatRoundOriginal10868) -> String {
        "\(CombatRoundInput10868.preMatchTitle) · \(original.label)"
    }

    /// One figure with its own visible provenance.
    private func comparisonValue(_ reading: CombatRoundReading10868, title: String, mark: KeyMark?, movement: String?) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 5) {
                if let mark { keyMark(mark) }
                Text(title).font(.caption).foregroundStyle(DS.textSecondary)
            }
            switch reading {
            case .value(let observation):
                // The whole figure keeps its width; a narrow row stacks the pair
                // instead of squeezing or splitting a number.
                Text(observation.text)
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
                Text(observation.detail).font(.caption2).foregroundStyle(DS.textSecondary)
                notDrawnNote(observation)
            case .missing(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
            if let movement {
                Text(movement).font(.caption).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Official finish context

    @ViewBuilder private var finishContext: some View {
        if let finish = input.visibleFinish {
            VStack(alignment: .leading, spacing: 4) {
                Text(finish.title)
                    .font(.caption.weight(.semibold))
                    .textCase(.uppercase)
                    .foregroundStyle(DS.textSecondary)
                ForEach(Array(finish.lines.enumerated()), id: \.offset) { _, line in
                    Text(line).font(.footnote).foregroundStyle(DS.textPrimary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityFinish ?? "")
            .accessibilityIdentifier(CombatRoundAccessibilityID10868.finish)
        }
    }

    // MARK: Details and timing

    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails), let original = input.selection.original {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails)
            } label: {
                HStack {
                    Text("Original \(original.label) · \(CombatRoundInput10868.detailsTitle)")
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier(CombatRoundAccessibilityID10868.details(original.id))
        }
    }

    @ViewBuilder private var timing: some View {
        switch input.timingPresentation(hasBinding: timingExpanded != nil) {
        case .disclosure(let content)?:
            if let timingExpanded {
                DisclosureGroup(isExpanded: timingExpanded) {
                    timingLines(content)
                } label: {
                    Text(content.title)
                        .font(.footnote.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(minHeight: 44, alignment: .leading)
                }
            }
        case .expanded(let content)?:
            VStack(alignment: .leading, spacing: 6) {
                Text(content.title).font(.footnote.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                timingLines(content)
            }
        case nil:
            EmptyView()
        }
    }

    private func timingLines(_ content: CombatRoundTiming10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(content.lines.enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: Controls

    /// A button only when the owner supplied the callback; otherwise the same
    /// content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: CombatRoundAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}
