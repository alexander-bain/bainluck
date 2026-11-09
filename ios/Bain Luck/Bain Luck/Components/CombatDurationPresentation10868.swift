import SwiftUI

// #10868 — "How long could the fight last?": one combat duration card across a
// bout's lifecycle. Each duration market (Over ½ round, Under 1½ rounds, Before
// Round 2, Go the distance in the retained Gautier–Kopylov bout) is its own
// market with its own original sides. A tile leads with ONE original side: a
// round rail shades THAT side's owner-proved time window, and the side's own
// PRE-MATCH chance sits beneath it. Shading is the window — never a chance,
// never elapsed time and never a winner. A Yes and its No are independent
// originals with their own windows, chances and results; nothing here
// complements, inverts or normalizes them, and a single captured Over or Under
// never gains an invented opposite side.
//
// Before the fight a tile shows only the window and its pre-match chance.
// During the fight the lead's pre-match and independently admitted in-fight
// chances sit at the same figure size with hollow and filled keys; an
// unavailable or withheld chance stays words; an owner-observed round may be
// outlined. After the fight the pre-match chance stays and the displayed
// original's own contract result appears beside it. The owner's independently
// known finish round is marked with a diamond on the round only — never at an
// invented point inside it — and never grades a contract here: the retained
// Under 1½ and Under 2½ results stay "Result unconfirmed" even though the
// official finish came in round 1.
//
// Presentation only, extracted from the approved design: `CombatDurationCard.tsx`,
// `combatDurationWindow.ts` (rail geometry), `combatDuration.css` (dense tiles),
// `CombatBaselineMark.tsx`. The reference's fixture admission, title and id
// maps, window table, latest-before-start election, result-conflict rule,
// automatic first-side selection and state are NOT ported.
//
// Every market id, label and order, every original identity and side label,
// every window label, span and final-bell meaning, every round label, figure,
// clock, provenance line, result word, heading, observed-round and finish
// context arrive resolved by the owner and are shown verbatim. This layer
// never formats or rounds a probability (owner text carries at most one
// decimal), never reads a clock, never infers a phase, a window, a grade or a
// round from a title or the bout outcome, and never turns a settled 0/100
// quote into a chance. Unknown is never a loss and absent is never zero.
//
// Selection, Details, timing disclosure, held updates and focus stay with the
// host: the view keeps no selected state, no sheet, no subscription and runs no
// animation, so reduced motion has nothing to stop. A tile leads with the
// host-selected side, else the host's explicit overview side, else lists every
// side — the leaf never picks Yes, the winner or a neighbour, and never
// switches sides on an update. Every original stays on screen, in its tile or
// in the selected market's side rows, never both. With no callback, content is
// shown without a button and no tap is asked for. Method, fighter-round and
// fighter-knockout cards are separate.
//
// Host binding still owed — not available at this base. An owner must supply
// proved market ids/labels/order and each market's original membership; each
// original's proved time window in round units and its final-bell meaning; the
// bout's round schedule; an admitted pre-match observation per original or its
// own missing words; during the fight an admitted current observation or its
// own unavailable / withheld words, with currentness already applied, and any
// observed round; after the fight each original's independently admitted
// contract result; and any independently known finish round and official
// context. COMBAT-DURATION-NATIVE-BINDING-MAP.md names the gaps.

/// One admitted reading. `probability` is carried for the owner's identity
/// only; the rail never draws it. `text` is what the reader sees.
nonisolated struct CombatDurationObservation10868: Equatable {
    let probability: Double
    /// The owner's whole figure ("37.5%", "≥99.5%").
    let text: String
    /// Short clock ("4:27 PM PT"); nil draws none.
    let timeText: String?
    /// Full provenance, shown in the selected comparison and spoken
    /// ("Last recorded before start · Oct 3, 4:27 PM PT · Polymarket").
    let detail: String
}

nonisolated enum CombatDurationPhase10868: Equatable {
    case before
    case during
    case final
}

/// The owner's in-fight state for one original, with currentness already applied.
nonisolated enum CombatDurationCurrent10868: Equatable {
    /// An admitted, current observation with the owner's optional movement line.
    case recorded(CombatDurationObservation10868, movement: String?)
    /// No admitted current reading ("No in-fight chance").
    case unavailable(String)
    /// A reading exists but is not admitted as current ("Held since round 1").
    case withheld(String)
}

/// The original side's contract result. There is no Bool: a missing result is
/// never a loss.
nonisolated enum CombatDurationResult10868: Equatable {
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

/// One owner-scheduled segment of the bout (a round), in the owner's order.
nonisolated struct CombatDurationSegment10868: Equatable {
    let id: String
    /// On the rail ("R1"); never truncated.
    let shortLabel: String
    /// Spoken ("Round 1").
    let spokenLabel: String
}

/// The owner's proved final-bell meaning for one window, with its words.
nonisolated enum CombatDurationFinalBell10868: Equatable {
    /// The window includes reaching the final bell ("Includes the final bell").
    case included(String)
    /// The window ends before the final bell ("Ends before the final bell").
    case excluded(String)

    var text: String {
        switch self {
        case .included(let text), .excluded(let text): text
        }
    }

    /// A native symbol, never colour alone: a bell, or a struck-through bell.
    var symbolName: String {
        switch self {
        case .included: "bell.fill"
        case .excluded: "bell.slash"
        }
    }
}

/// One original side's owner-proved time window in round units: 0 is the
/// opening bell and `segments.count` the scheduled final bell. A window may be
/// zero-length (reaching the final bell is a moment, not a span).
nonisolated struct CombatDurationWindow10868: Equatable {
    /// Full window label ("Under 1½ rounds"); never truncated.
    let label: String
    let start: Double
    let end: Double
    let finalBell: CombatDurationFinalBell10868?
}

/// One original side of one duration market. Each reading carries its own
/// missing words. `current` is read only during the fight, `result` and
/// `resultDetail` only after.
nonisolated struct CombatDurationOriginal10868: Equatable {
    /// Exact original outcome id, passed back to the owner unchanged.
    let id: String
    /// The original's market id, passed back unchanged.
    let marketID: String
    /// The original side name ("Under", "Yes", "No").
    let label: String
    /// Nil when the owner has not proved a window; `windowMissing` shows instead.
    let window: CombatDurationWindow10868?
    let windowMissing: String
    let before: CombatDurationObservation10868?
    let beforeMissing: String
    let current: CombatDurationCurrent10868
    let result: CombatDurationResult10868
    /// The owner's qualification of the result ("The game-prop capture and the
    /// market detail disagree on this side."); nil draws none.
    let resultDetail: String?
}

/// One owner-proved duration market with its original sides in the owner's order.
nonisolated struct CombatDurationMarket10868: Equatable {
    /// The owner's market id.
    let id: String
    /// Short market name ("Go the distance"); the tile title when no single
    /// side leads, never truncated.
    let label: String
    /// The full original prop text ("Fight to Go the Distance?").
    let question: String
    let originals: [CombatDurationOriginal10868]
    /// The owner's explicit overview side for this tile; nil lists every side.
    let overviewOriginalID: String?
}

/// The owner's observed round during the fight ("Round 2 in progress").
nonisolated struct CombatDurationObserved10868: Equatable {
    let segmentID: String
    let words: String
}

/// The owner's independently known finish. Only the round is marked — never a
/// point inside it, and never a grade.
nonisolated struct CombatDurationFinish10868: Equatable {
    /// The finish round's segment id; nil marks no round.
    let segmentID: String?
    /// Beside the diamond ("Finished in Round 1").
    let markerWords: String
    /// "Official bout result".
    let title: String
    let lines: [String]
    let accessibilityDetail: String?
}

/// The owner's timing disclosure for one original. Shown only while that exact
/// original is the resolved selection.
nonisolated struct CombatDurationTiming10868: Equatable {
    let originalID: String
    let title: String
    let lines: [String]
}

/// Exact original identity, handed back to the owner on select and Details.
nonisolated struct CombatDurationOriginalRef10868: Hashable {
    let eventID: String
    let durationMarketID: String
    let marketID: String
    let originalID: String
}

nonisolated enum CombatDurationSelection10868: Equatable {
    case none
    /// A market is selected with no side.
    case market(CombatDurationMarket10868)
    case original(CombatDurationMarket10868, CombatDurationOriginal10868)
    /// The market resolves; the selected side is absent, withdrawn or duplicated.
    case sideUnavailable(CombatDurationMarket10868, String)
    /// The selected market (or a side named without its market) does not
    /// resolve to exactly one.
    case unavailable(String)

    var market: CombatDurationMarket10868? {
        switch self {
        case .market(let market), .original(let market, _), .sideUnavailable(let market, _): market
        case .none, .unavailable: nil
        }
    }

    var original: CombatDurationOriginal10868? {
        if case .original(_, let original) = self { return original }
        return nil
    }
}

nonisolated enum CombatDurationReading10868: Equatable {
    case value(CombatDurationObservation10868)
    case missing(String)
}

/// The shaded part of one round, as fractions of that round (0...1).
nonisolated struct CombatDurationFill10868: Equatable {
    let from: Double
    let to: Double

    var isWhole: Bool { from == 0 && to == 1 }
}

/// What one rail draws for one window.
nonisolated enum CombatDurationRail10868: Equatable {
    /// Per-round shading in the owner's segment order; nil leaves a round clear.
    case shaded([CombatDurationFill10868?])
    /// A valid zero-length window: no round is shaded. Its final-bell symbol
    /// and words carry it; it is not an empty or impossible window.
    case zeroLength
    /// No window, no rounds, or geometry outside the schedule: nothing is
    /// shaded and the window words stay.
    case undrawn

    func fill(at index: Int) -> CombatDurationFill10868? {
        guard case .shaded(let fills) = self, fills.indices.contains(index) else { return nil }
        return fills[index]
    }
}

/// A round the card marks for the whole bout, with the owner's words.
nonisolated struct CombatDurationMark10868: Equatable {
    /// Nil when the owner's segment id does not name exactly one round: the
    /// words stay, no round is marked.
    let segmentIndex: Int?
    let words: String
}

/// One entry in the card's key. Each mark has its own shape and words.
nonisolated enum CombatDurationKeyItem10868: Equatable {
    /// Shaded rounds are a side's time window.
    case window
    /// The owner-observed round (dashed outline), during the fight only.
    case observed(CombatDurationMark10868)
    /// The independently known finish round (diamond), during and after.
    case finish(CombatDurationMark10868)
}

/// What a tile leads with.
nonisolated enum CombatDurationLead10868: Equatable {
    case original(CombatDurationOriginal10868, selected: Bool)
    /// The host named a side this market does not carry exactly once.
    case unavailable(String)
    /// No side is named: every side is listed, none is chosen.
    case sides
}

/// One original listed as its own row, with the exact action it may carry.
nonisolated struct CombatDurationTileSide10868: Equatable {
    let original: CombatDurationOriginal10868
    let action: CombatDurationAction10868?
}

/// What one tile draws — the View's own branch. Every original stays on screen:
/// in the tile itself, or in the selected market's side rows beneath the grid —
/// never both (`panelSides`).
nonisolated enum CombatDurationTilePresentation10868: Equatable {
    /// The approved compact rail tile: one control when `action` is set, else
    /// static. Its other sides are reached through that action or, for the
    /// selected market, the side rows that already list them.
    case rail(CombatDurationOriginal10868, selected: Bool, action: CombatDurationAction10868?)
    /// A static overview on an unselected market: the lead's rail stays and
    /// every other original is listed beneath it. The tile is not a button.
    case railWithSides(CombatDurationOriginal10868, others: [CombatDurationTileSide10868])
    /// The notice alone: the selected market's side rows list every side.
    case unavailable(String)
    /// The notice, then every original with its exact safe action. Not a button.
    case unavailableWithSides(String, sides: [CombatDurationTileSide10868])
    /// No side named: every side listed, none chosen. On the selected market
    /// these are its only side rows; the panel beneath lists none.
    case sides([CombatDurationTileSide10868])

    /// The originals this tile itself lists as their own rows.
    var listed: [CombatDurationTileSide10868] {
        switch self {
        case .rail, .unavailable: []
        case .railWithSides(_, let sides), .unavailableWithSides(_, let sides), .sides(let sides): sides
        }
    }
}

/// The selected original's comparison, by phase.
nonisolated enum CombatDurationComparison10868: Equatable {
    case before(CombatDurationOriginal10868)
    case during(CombatDurationOriginal10868)
    case final(CombatDurationOriginal10868, CombatDurationResult10868)
}

nonisolated enum CombatDurationAction10868: Equatable {
    case select(CombatDurationOriginalRef10868)
    case details(CombatDurationOriginalRef10868)

    func perform(
        onSelect: ((CombatDurationOriginalRef10868) -> Void)?,
        onDetails: ((CombatDurationOriginalRef10868) -> Void)?
    ) {
        switch self {
        case .select(let ref): onSelect?(ref)
        case .details(let ref): onDetails?(ref)
        }
    }
}

nonisolated enum CombatDurationTimingPresentation10868: Equatable {
    /// The page owns the expanded flag.
    case disclosure(CombatDurationTiming10868)
    /// No binding: the owner's timing content, already expanded.
    case expanded(CombatDurationTiming10868)
}

nonisolated struct CombatDurationInput10868: Equatable {
    let phase: CombatDurationPhase10868
    let eventID: String
    /// "Polymarket · contract results".
    let eyebrow: String
    /// The owner's headline ("How long could the fight last?"); nil draws none.
    let title: String?
    /// The owner's caption under the headline; nil draws none.
    let caption: String?
    /// The bout's round schedule in the owner's order — never assumed to be three.
    let segments: [CombatDurationSegment10868]
    /// Every market in the owner's order — never sorted, filtered or capped.
    let markets: [CombatDurationMarket10868]
    let selectedMarketID: String?
    let selectedOriginalID: String?
    /// Read only during the fight.
    let observed: CombatDurationObserved10868?
    /// Read only during and after the fight.
    let finish: CombatDurationFinish10868?
    let timing: CombatDurationTiming10868?

    static let preMatchTitle = "Pre-match chance"
    static let preMatchShort = "Pre-match"
    static let currentTitle = "In-fight chance"
    static let currentShort = "In-fight"
    static let resultTitle = "Contract result"
    static let windowTitle = "Time window"
    static let selectedTag = "Selected"
    static let marketSelectedTag = "Market selected"
    static let detailsTitle = "Original prop & evidence"
    static let chooseInstruction = "Choose a time window or side to compare."
    static let marketUnavailable = "Selected market unavailable in this update."
    static let sideUnavailable = "Selected side unavailable in this update."
    static let sideUnavailableShort = "Selected side unavailable"
    static let overviewUnavailable = "Side unavailable in this update"
    static let windowKey = "Shaded rounds: that side’s time window — not its chance, time elapsed or a winner"
    static let singleOriginalNote = "Only this original side was captured. No opposite side or result is inferred."
    static let noRoundShaded = "No round shaded"
    static let windowNotDrawn = "Window not drawn"
    static let partOf = "part of"

    // MARK: Identity

    private static func repeated(_ ids: [String]) -> Set<String> {
        var seen = Set<String>()
        var repeated = Set<String>()
        for id in ids where !seen.insert(id).inserted { repeated.insert(id) }
        return repeated
    }

    /// Market ids carried more than once. Such markets get no action.
    var duplicateMarketIDs: Set<String> { Self.repeated(markets.map(\.id)) }

    /// Original ids carried more than once anywhere on the card. Such originals
    /// get no action and cannot be selected.
    var duplicateOriginalIDs: Set<String> { Self.repeated(markets.flatMap { $0.originals.map(\.id) }) }

    func ref(_ original: CombatDurationOriginal10868, in market: CombatDurationMarket10868) -> CombatDurationOriginalRef10868 {
        CombatDurationOriginalRef10868(eventID: eventID, durationMarketID: market.id, marketID: original.marketID, originalID: original.id)
    }

    private func isUnique(_ original: CombatDurationOriginal10868, in market: CombatDurationMarket10868) -> Bool {
        !duplicateMarketIDs.contains(market.id) && !duplicateOriginalIDs.contains(original.id)
    }

    // MARK: Selection

    /// Exact ids only. A missing, withdrawn or duplicated id gets no substitute,
    /// and every original stays listed.
    var selection: CombatDurationSelection10868 {
        switch (selectedMarketID, selectedOriginalID) {
        case (nil, nil):
            return .none
        case (nil, let originalID?):
            guard !duplicateOriginalIDs.contains(originalID) else { return .unavailable(originalID) }
            let holders = markets.filter { $0.originals.contains { $0.id == originalID } }
            guard holders.count == 1, let market = holders.first, !duplicateMarketIDs.contains(market.id),
                  let original = market.originals.first(where: { $0.id == originalID })
            else { return .unavailable(originalID) }
            return .original(market, original)
        case (let marketID?, let originalID):
            let matches = markets.filter { $0.id == marketID }
            guard matches.count == 1, let market = matches.first else { return .unavailable(marketID) }
            guard let originalID else { return .market(market) }
            guard !duplicateOriginalIDs.contains(originalID),
                  let original = market.originals.first(where: { $0.id == originalID })
            else { return .sideUnavailable(market, originalID) }
            return .original(market, original)
        }
    }

    func isSelectedMarket(_ market: CombatDurationMarket10868) -> Bool {
        guard let selected = selection.market else { return false }
        return selected.id == market.id && !duplicateMarketIDs.contains(market.id)
    }

    func isSelected(_ original: CombatDurationOriginal10868, in market: CombatDurationMarket10868) -> Bool {
        guard case .original(let selectedMarket, let selectedOriginal) = selection else { return false }
        return selectedMarket.id == market.id && selectedOriginal.id == original.id
    }

    var selectionNotice: String? {
        switch selection {
        case .unavailable: Self.marketUnavailable
        case .sideUnavailable: Self.sideUnavailable
        case .none, .market, .original: nil
        }
    }

    /// The host-selected side, else the host's overview side, else every side.
    /// Never Yes, the winner or a neighbour by default.
    func lead(_ market: CombatDurationMarket10868) -> CombatDurationLead10868 {
        switch selection {
        case .original(let selected, let original) where selected.id == market.id:
            return .original(original, selected: true)
        case .sideUnavailable(let selected, _) where selected.id == market.id:
            return .unavailable(Self.sideUnavailableShort)
        default:
            break
        }
        guard let overviewID = market.overviewOriginalID else { return .sides }
        let matches = market.originals.filter { $0.id == overviewID }
        guard matches.count == 1, !duplicateOriginalIDs.contains(overviewID) else {
            return .unavailable(Self.overviewUnavailable)
        }
        return .original(matches[0], selected: false)
    }

    /// The tile's title: the leading side's full window label, else the
    /// market's own label. Never a parsed or shortened title.
    func tileTitle(_ market: CombatDurationMarket10868) -> String {
        if case .original(let original, _) = lead(market), let window = original.window { return window.label }
        return market.label
    }

    /// Whether a side row repeats its window label. A row inside a tile skips
    /// it only when the tile's title already reads exactly that label; the
    /// selected panel's rows always show it.
    func showsWindowLabel(_ original: CombatDurationOriginal10868, inTileOf market: CombatDurationMarket10868?) -> Bool {
        guard let window = original.window else { return false }
        guard let market else { return true }
        return window.label != tileTitle(market)
    }

    // MARK: Phase visibility

    func beforeReading(_ original: CombatDurationOriginal10868) -> CombatDurationReading10868 {
        original.before.map { .value($0) } ?? .missing(original.beforeMissing)
    }

    /// During the fight only. Never falls back to the pre-match reading.
    func currentReading(_ original: CombatDurationOriginal10868) -> CombatDurationReading10868? {
        guard phase == .during else { return nil }
        switch original.current {
        case .recorded(let observation, _): return .value(observation)
        case .unavailable(let text), .withheld(let text): return .missing(text)
        }
    }

    /// The owner's movement line, only beside an admitted current observation.
    func movement(_ original: CombatDurationOriginal10868) -> String? {
        guard phase == .during, case .recorded(_, let movement) = original.current else { return nil }
        return movement
    }

    /// The filled current key appears only beside an admitted current observation.
    func showsCurrentMark(_ original: CombatDurationOriginal10868) -> Bool {
        if case .value? = currentReading(original) { return true }
        return false
    }

    /// After the fight only. Any supplied current reading is ignored then, so a
    /// settled 0/100 price can never read as a chance.
    func result(_ original: CombatDurationOriginal10868) -> CombatDurationResult10868? {
        phase == .final ? original.result : nil
    }

    /// The owner's qualification beside the result, after the fight only.
    func resultDetail(_ original: CombatDurationOriginal10868) -> String? {
        phase == .final ? original.resultDetail : nil
    }

    private func segmentIndex(_ id: String?) -> Int? {
        guard let id else { return nil }
        let matches = segments.indices.filter { segments[$0].id == id }
        return matches.count == 1 ? matches[0] : nil
    }

    /// The owner-observed round, during the fight only.
    var observedMark: CombatDurationMark10868? {
        guard phase == .during, let observed else { return nil }
        return CombatDurationMark10868(segmentIndex: segmentIndex(observed.segmentID), words: observed.words)
    }

    /// The independently known finish round. Nil before the fight.
    var finishMark: CombatDurationMark10868? {
        guard phase != .before, let finish else { return nil }
        return CombatDurationMark10868(segmentIndex: segmentIndex(finish.segmentID), words: finish.markerWords)
    }

    /// Nil before the fight.
    var visibleFinish: CombatDurationFinish10868? { phase == .before ? nil : finish }

    /// The window key always (when there is a market), then any visible marks.
    var keyItems: [CombatDurationKeyItem10868] {
        guard !markets.isEmpty else { return [] }
        var items: [CombatDurationKeyItem10868] = [.window]
        if let observedMark { items.append(.observed(observedMark)) }
        if let finishMark { items.append(.finish(finishMark)) }
        return items
    }

    /// One original's rail. Geometry only: the owner's span on the owner's
    /// schedule, never a chance.
    func rail(_ original: CombatDurationOriginal10868) -> CombatDurationRail10868 {
        guard let window = original.window else { return .undrawn }
        return CombatDurationGeometry10868.rail(start: window.start, end: window.end, segments: segments.count)
    }

    var comparison: CombatDurationComparison10868? {
        guard let original = selection.original else { return nil }
        switch phase {
        case .before: return .before(original)
        case .during: return .during(original)
        case .final: return .final(original, original.result)
        }
    }

    /// The selected market carries one original: say so, and never invent the other.
    var showsSingleOriginalNote: Bool {
        selection.market?.originals.count == 1
    }

    /// Asks for a tap only when one does something.
    func instruction(canSelect: Bool) -> String? {
        canSelect && !markets.isEmpty ? Self.chooseInstruction : nil
    }

    // MARK: Actions and timing

    /// A tile selects the exact side it leads with — never a side it would have
    /// to choose.
    func tileAction(_ market: CombatDurationMarket10868, canSelect: Bool) -> CombatDurationAction10868? {
        guard canSelect, case .original(let original, _) = lead(market), isUnique(original, in: market) else { return nil }
        return .select(ref(original, in: market))
    }

    func sideAction(_ original: CombatDurationOriginal10868, in market: CombatDurationMarket10868, canSelect: Bool) -> CombatDurationAction10868? {
        guard canSelect, isUnique(original, in: market) else { return nil }
        return .select(ref(original, in: market))
    }

    /// Originals listed as rows, each with exactly the action `sideAction` permits.
    private func listed(
        _ originals: [CombatDurationOriginal10868],
        in market: CombatDurationMarket10868,
        canSelect: Bool
    ) -> [CombatDurationTileSide10868] {
        originals.map { CombatDurationTileSide10868(original: $0, action: sideAction($0, in: market, canSelect: canSelect)) }
    }

    /// Whether the panel beneath the grid lists this market's sides: only for
    /// the selected market, and not when its tile already lists every side
    /// (chosen with no side and no overview), so no side list is mounted twice.
    func panelListsSides(_ market: CombatDurationMarket10868) -> Bool {
        isSelectedMarket(market) && lead(market) != .sides
    }

    /// The side rows the selected panel mounts for this market — the View's own
    /// list. Empty unless `panelListsSides`.
    func panelSides(_ market: CombatDurationMarket10868, canSelect: Bool) -> [CombatDurationTileSide10868] {
        panelListsSides(market) ? listed(market.originals, in: market, canSelect: canSelect) : []
    }

    /// The tile the View draws. A rail that neither selects its side nor belongs
    /// to the selected market would hide any other originals, so they are listed
    /// in the tile; an unavailable side that is not the selected market's keeps
    /// its notice and lists every original. A tile never repeats side rows the
    /// panel beneath the grid mounts, and no duplicated id gains an action.
    func tilePresentation(_ market: CombatDurationMarket10868, canSelect: Bool) -> CombatDurationTilePresentation10868 {
        let panelLists = panelListsSides(market)
        switch lead(market) {
        case .sides:
            return .sides(listed(market.originals, in: market, canSelect: canSelect))
        case .unavailable(let words):
            return panelLists
                ? .unavailable(words)
                : .unavailableWithSides(words, sides: listed(market.originals, in: market, canSelect: canSelect))
        case .original(let original, let selected):
            let action = tileAction(market, canSelect: canSelect)
            let others = market.originals.filter { $0.id != original.id }
            if action != nil || panelLists || others.isEmpty {
                return .rail(original, selected: selected, action: action)
            }
            return .railWithSides(original, others: listed(others, in: market, canSelect: canSelect))
        }
    }

    func detailsAction(canOpenDetails: Bool) -> CombatDurationAction10868? {
        guard canOpenDetails, case .original(let market, let original) = selection else { return nil }
        return .details(ref(original, in: market))
    }

    /// Timing only for the exact resolved selection.
    func timingPresentation(hasBinding: Bool) -> CombatDurationTimingPresentation10868? {
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
            case .window: Self.windowKey
            case .observed(let mark), .finish(let mark): mark.words
            }
        }
        .joined(separator: ". ")
    }

    /// The window in words: its label, the rounds it shades and its final bell.
    /// A zero-length window with a bell is spoken by the bell alone.
    func accessibilityWindow(_ original: CombatDurationOriginal10868) -> String {
        guard let window = original.window else { return original.windowMissing }
        var parts = [window.label]
        switch rail(original) {
        case .shaded(let fills):
            let rounds = fills.indices.compactMap { index -> String? in
                guard let fill = fills[index] else { return nil }
                let name = segments[index].spokenLabel
                return fill.isWhole ? name : "\(Self.partOf) \(name)"
            }
            parts.append("Shaded: \(rounds.joined(separator: ", "))")
        case .zeroLength:
            if window.finalBell == nil { parts.append(Self.noRoundShaded) }
        case .undrawn:
            parts.append(Self.windowNotDrawn)
        }
        if let bell = window.finalBell { parts.append(bell.text) }
        return parts.joined(separator: ". ")
    }

    /// One original's readings for the phase: window, pre-match, then in-fight
    /// or result.
    func accessibilityReadings(_ original: CombatDurationOriginal10868, detailed: Bool) -> String {
        var parts = [
            "\(Self.windowTitle): \(accessibilityWindow(original))",
            "\(Self.preMatchTitle): \(Self.spoken(beforeReading(original), detailed: detailed))",
        ]
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

    /// A tile: its lead with full provenance, then every other side, so no side
    /// is reachable only by sight.
    func accessibilityTileValue(_ market: CombatDurationMarket10868) -> String {
        var parts: [String] = []
        var spokenIDs = Set<String>()
        switch lead(market) {
        case .original(let original, let selected):
            parts.append(accessibilityLeadValue(original))
            if selected { parts.append(Self.selectedTag) }
            spokenIDs.insert(original.id)
        case .unavailable(let words):
            parts.append(words)
        case .sides:
            break
        }
        let others = market.originals.filter { !spokenIDs.contains($0.id) }
        let prefix = spokenIDs.isEmpty ? "" : "Also "
        for original in others {
            parts.append("\(prefix)\(original.label). \(accessibilityReadings(original, detailed: false))")
        }
        if market.originals.count == 1 { parts.append(Self.singleOriginalNote) }
        if isSelectedMarket(market), selection.original == nil { parts.append(Self.marketSelectedTag) }
        return parts.joined(separator: ". ")
    }

    /// A lead side alone, with full provenance. A static overview's rail speaks
    /// this; the originals listed beside it speak for themselves.
    func accessibilityLeadValue(_ original: CombatDurationOriginal10868) -> String {
        "\(original.label). \(accessibilityReadings(original, detailed: true))"
    }

    func accessibilitySideValue(_ original: CombatDurationOriginal10868, in market: CombatDurationMarket10868) -> String {
        var parts = [accessibilityReadings(original, detailed: true)]
        if isSelected(original, in: market) { parts.append(Self.selectedTag) }
        return parts.joined(separator: "; ")
    }

    /// The selected original's comparison, each reading with its provenance.
    var accessibilityComparison: String? {
        guard let comparison, let market = selection.market else { return nil }
        let original: CombatDurationOriginal10868
        switch comparison {
        case .before(let selected), .during(let selected), .final(let selected, _): original = selected
        }
        return "\(market.question), original \(original.label). \(accessibilityReadings(original, detailed: true))"
    }

    var accessibilityFinish: String? {
        guard let finish = visibleFinish else { return nil }
        let lines = ([finish.title] + finish.lines).joined(separator: ". ")
        return ([lines, finish.accessibilityDetail].compactMap { $0 }).joined(separator: ". ")
    }

    private static func spoken(_ reading: CombatDurationReading10868, detailed: Bool) -> String {
        switch reading {
        case .value(let observation): detailed ? "\(observation.text), \(observation.detail)" : observation.text
        case .missing(let text): text
        }
    }
}

nonisolated enum CombatDurationArrangement10868: Equatable {
    /// One subview, or more than two: stacked in order.
    case single
    case sideBySide
    case stacked
}

nonisolated struct CombatDurationColumns10868: Equatable {
    let first: CGFloat
    let second: CGFloat
}

nonisolated enum CombatDurationGeometry10868 {
    /// The owner's window on the owner's schedule, round by round. Anything
    /// non-finite, reversed or outside 0...segments draws nothing — never a
    /// clipped, reordered or guessed span. A valid zero-length window is
    /// `.zeroLength`, not malformed.
    static func rail(start: Double, end: Double, segments: Int) -> CombatDurationRail10868 {
        guard segments > 0, start.isFinite, end.isFinite, start >= 0, end <= Double(segments), start <= end else {
            return .undrawn
        }
        guard start < end else { return .zeroLength }
        return .shaded((0..<segments).map { index in
            let lower = max(start, Double(index))
            let upper = min(end, Double(index + 1))
            guard upper > lower else { return nil }
            return CombatDurationFill10868(from: lower - Double(index), to: upper - Double(index))
        })
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

    /// As many equal columns as keep every tile whole: from one per market down
    /// to one. A column must reach the scaled minimum and every tile's measured
    /// width (its rail, figure and widest word) must fit it. There is no fixed
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

    /// Item indices row by row, in the owner's order.
    static func rows(count: Int, columns: Int) -> [[Int]] {
        guard count > 0, columns > 0 else { return [] }
        return stride(from: 0, to: count, by: columns).map { start in Array(start..<min(start + columns, count)) }
    }

    /// Rounds per rail row: every round on one row while each keeps its widest
    /// label, else the rail wraps onto more rows in order. A label is never
    /// shrunk or cut; there is no fixed three-round assumption.
    static func segmentsPerRow(available: CGFloat?, count: Int, minimum: CGFloat, spacing: CGFloat) -> Int {
        guard count > 0 else { return 0 }
        guard let available, available.isFinite, minimum.isFinite, minimum > 0 else { return count }
        let fitting = Int(((available + spacing) / (minimum + spacing)).rounded(.down))
        return min(count, max(1, fitting))
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
    ) -> CombatDurationArrangement10868 {
        if forceStack { return .stacked }
        guard first.isFinite, second.isFinite, first >= 0, second >= 0 else { return .stacked }
        guard let available, available.isFinite else { return .sideBySide }
        return neededWidth(first: first, second: second, spacing: spacing, equalColumns: equalColumns) <= available
            ? .sideBySide : .stacked
    }

    static func neededWidth(first: CGFloat, second: CGFloat, spacing: CGFloat, equalColumns: Bool) -> CGFloat {
        equalColumns ? 2 * max(first, second) + spacing : first + second + spacing
    }

    static func columns(total: CGFloat, first: CGFloat, spacing: CGFloat, equalColumns: Bool) -> CombatDurationColumns10868 {
        if equalColumns {
            let half = max(0, (total - spacing) / 2)
            return CombatDurationColumns10868(first: half, second: half)
        }
        let leading = min(max(0, first), max(0, total - spacing))
        return CombatDurationColumns10868(first: leading, second: max(0, total - spacing - leading))
    }
}

/// The duration tiles in equal columns, row by row in the owner's order. Tiles
/// in one row share the row's height.
struct CombatDurationTileGridLayout10868: Layout {
    var spacing: CGFloat
    var minimumColumnWidth: CGFloat
    var forceSingleColumn: Bool

    private func columnCount(_ width: CGFloat?, _ subviews: Subviews) -> Int {
        CombatDurationGeometry10868.columnCount(
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
            return CombatDurationGeometry10868.columnWidth(available: width, columns: columns, spacing: spacing)
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
        let rows = CombatDurationGeometry10868.rows(count: subviews.count, columns: columns)
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
        for row in CombatDurationGeometry10868.rows(count: subviews.count, columns: columns) {
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

/// The round rail: equal segments in the owner's order, each at least as wide
/// as the widest round label. When they do not all fit, the rail wraps onto
/// more rows instead of shrinking or cutting a label.
struct CombatDurationRailLayout10868: Layout {
    var spacing: CGFloat

    private func minimum(_ subviews: Subviews) -> CGFloat {
        subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0
    }

    private func perRow(_ width: CGFloat?, _ subviews: Subviews) -> Int {
        CombatDurationGeometry10868.segmentsPerRow(available: width, count: subviews.count, minimum: minimum(subviews), spacing: spacing)
    }

    private func railWidth(_ width: CGFloat?, perRow: Int, _ subviews: Subviews) -> CGFloat {
        let natural = minimum(subviews) * CGFloat(perRow) + spacing * CGFloat(max(0, perRow - 1))
        guard let width, width.isFinite else { return natural }
        // Never narrower than one whole label, so a column too narrow for it is
        // measured as not fitting.
        return max(width, minimum(subviews))
    }

    private func segmentHeight(_ row: [Int], segment: CGFloat, _ subviews: Subviews) -> CGFloat {
        row.map { subviews[$0].sizeThatFits(ProposedViewSize(width: segment, height: nil)).height }.max() ?? 0
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        let count = perRow(proposal.width, subviews)
        let width = railWidth(proposal.width, perRow: count, subviews)
        let segment = CombatDurationGeometry10868.columnWidth(available: width, columns: count, spacing: spacing)
        let rows = CombatDurationGeometry10868.rows(count: subviews.count, columns: count)
        let height = rows.map { segmentHeight($0, segment: segment, subviews) }.reduce(0, +)
            + spacing * CGFloat(max(0, rows.count - 1))
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        let count = perRow(bounds.width, subviews)
        let width = railWidth(bounds.width, perRow: count, subviews)
        let segment = CombatDurationGeometry10868.columnWidth(available: width, columns: count, spacing: spacing)
        var y = bounds.minY
        for row in CombatDurationGeometry10868.rows(count: subviews.count, columns: count) {
            let height = segmentHeight(row, segment: segment, subviews)
            for (position, index) in row.enumerated() {
                subviews[index].place(
                    at: CGPoint(x: bounds.minX + CGFloat(position) * (segment + spacing), y: y),
                    anchor: .topLeading,
                    proposal: ProposedViewSize(width: segment, height: height)
                )
            }
            y += height + spacing
        }
    }
}

/// Two subviews side by side while both keep their whole measured width, else
/// stacked at full width. Used for the selected comparison pair.
struct CombatDurationPairLayout10868: Layout {
    var spacing: CGFloat
    var equalColumns: Bool
    var forceStack: Bool

    private func idealWidths(_ subviews: Subviews) -> CombatDurationColumns10868 {
        CombatDurationColumns10868(
            first: subviews[0].sizeThatFits(.unspecified).width,
            second: subviews[1].sizeThatFits(.unspecified).width
        )
    }

    private func arrangement(_ width: CGFloat?, _ subviews: Subviews) -> CombatDurationArrangement10868 {
        guard subviews.count == 2 else { return .single }
        let ideal = idealWidths(subviews)
        return CombatDurationGeometry10868.pairArrangement(
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
            let total = proposal.width ?? CombatDurationGeometry10868.neededWidth(
                first: ideal.first, second: ideal.second, spacing: spacing, equalColumns: equalColumns
            )
            let widths = CombatDurationGeometry10868.columns(total: total, first: ideal.first, spacing: spacing, equalColumns: equalColumns)
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
            let widths = CombatDurationGeometry10868.columns(total: bounds.width, first: ideal.first, spacing: spacing, equalColumns: equalColumns)
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
/// tile grid drops a column before any word would split.
private struct CombatDurationWrappedText10868: View {
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
                ForEach(Array(CombatDurationGeometry10868.words(text).enumerated()), id: \.offset) { _, word in
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

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum CombatDurationAccessibilityID10868 {
    static let key = "combatDuration10868.key"
    static let comparison = "combatDuration10868.comparison"
    static let finish = "combatDuration10868.finish"
    static func tile(_ marketID: String) -> String { "combatDuration10868.tile.\(marketID)" }
    static func side(_ marketID: String, _ originalID: String) -> String { "combatDuration10868.side.\(marketID).\(originalID)" }
    static func details(_ originalID: String) -> String { "combatDuration10868.details.\(originalID)" }
}

struct CombatDurationPresentation10868: View {
    let input: CombatDurationInput10868
    var onSelect: ((CombatDurationOriginalRef10868) -> Void)? = nil
    var onDetails: ((CombatDurationOriginalRef10868) -> Void)? = nil
    /// Page-owned. Nil shows the owner's timing content already expanded.
    var timingExpanded: Binding<Bool>? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .headline) private var tileFigureSize: CGFloat = 20
    @ScaledMetric(relativeTo: .caption) private var railHeight: CGFloat = 24
    @ScaledMetric(relativeTo: .caption) private var markSize: CGFloat = 9
    @ScaledMetric(relativeTo: .caption) private var minimumColumnWidth: CGFloat = 140
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .title3) private var sideFigureSize: CGFloat = 20

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }

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
            CombatDurationTileGridLayout10868(
                spacing: 8,
                minimumColumnWidth: minimumColumnWidth,
                forceSingleColumn: typeSize.isAccessibilitySize
            ) {
                ForEach(Array(input.markets.enumerated()), id: \.offset) { _, market in
                    tile(market)
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

    /// Shape plus words for every mark the rails can carry — never colour alone.
    @ViewBuilder private var key: some View {
        let items = input.keyItems
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
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
            .accessibilityIdentifier(CombatDurationAccessibilityID10868.key)
        }
    }

    private func keyWords(_ item: CombatDurationKeyItem10868) -> String {
        switch item {
        case .window: CombatDurationInput10868.windowKey
        case .observed(let mark), .finish(let mark): mark.words
        }
    }

    /// Each key shape matches its mark on the rail. A mark whose round did not
    /// resolve keeps its words and draws no shape.
    @ViewBuilder private func keySwatch(_ item: CombatDurationKeyItem10868) -> some View {
        switch item {
        case .window:
            RoundedRectangle(cornerRadius: 2).fill(shading).frame(width: 14, height: 10)
                .overlay(RoundedRectangle(cornerRadius: 2).strokeBorder(DS.border, lineWidth: 1))
        case .observed(let mark):
            if mark.segmentIndex != nil {
                RoundedRectangle(cornerRadius: 2)
                    .strokeBorder(DS.textPrimary, style: StrokeStyle(lineWidth: 1.5, dash: [3, 2]))
                    .frame(width: 14, height: 10)
            }
        case .finish(let mark):
            if mark.segmentIndex != nil {
                Image(systemName: "diamond.fill").font(.caption2).foregroundStyle(DS.textPrimary)
            }
        }
    }

    private var shading: Color { DS.blue.opacity(0.28) }

    // MARK: Tiles

    @ViewBuilder private func tile(_ market: CombatDurationMarket10868) -> some View {
        switch input.tilePresentation(market, canSelect: canSelect) {
        case .rail(let original, let selected, let action):
            control(action) {
                tileFrame(market) { leadContent(.original(original, selected: selected)) }
            }
            .accessibilityLabel(market.label)
            .accessibilityValue(input.accessibilityTileValue(market))
            .accessibilityHint(action == nil ? "" : "Selects this side’s comparison")
            .accessibilityAddTraits(input.isSelectedMarket(market) ? .isSelected : [])
            .accessibilityIdentifier(CombatDurationAccessibilityID10868.tile(market.id))
        case .unavailable(let words):
            control(nil) {
                tileFrame(market) { leadContent(.unavailable(words)) }
            }
            .accessibilityLabel(market.label)
            .accessibilityValue(input.accessibilityTileValue(market))
            .accessibilityAddTraits(input.isSelectedMarket(market) ? .isSelected : [])
            .accessibilityIdentifier(CombatDurationAccessibilityID10868.tile(market.id))
        case .railWithSides(let original, let others):
            // The lead is static; each other original is its own row. The tile
            // only groups them, so no side control sits inside a button.
            tileFrame(market) {
                leadContent(.original(original, selected: false))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(market.label), \(original.label)")
                    .accessibilityValue(input.accessibilityLeadValue(original))
                tileSides(market, others)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(market.label)
            .accessibilityIdentifier(CombatDurationAccessibilityID10868.tile(market.id))
        case .unavailableWithSides(let words, let sides):
            tileFrame(market) {
                leadContent(.unavailable(words))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(market.label), \(words)")
                tileSides(market, sides)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(market.label)
            .accessibilityIdentifier(CombatDurationAccessibilityID10868.tile(market.id))
        case .sides(let sides):
            // Every side is its own control; the tile only groups them.
            tileFrame(market) { tileSides(market, sides) }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(market.label)
                .accessibilityIdentifier(CombatDurationAccessibilityID10868.tile(market.id))
        }
    }

    /// The originals a tile lists itself, compact, each with its own action.
    private func tileSides(_ market: CombatDurationMarket10868, _ sides: [CombatDurationTileSide10868]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(sides.enumerated()), id: \.offset) { _, side in
                sideControl(side.original, in: market, compact: true, action: side.action)
            }
        }
    }

    /// Selection is an outline plus a named tag — never colour alone, and never
    /// the same shape as a result symbol, the shading or a round mark.
    private func tileFrame<Content: View>(_ market: CombatDurationMarket10868, @ViewBuilder content: () -> Content) -> some View {
        let selected = input.isSelectedMarket(market)
        return VStack(alignment: .leading, spacing: 8) {
            CombatDurationWrappedText10868(
                text: input.tileTitle(market),
                font: .footnote.weight(.semibold),
                color: DS.textPrimary,
                alignment: .leading
            )
            if selected { selectedTag }
            content()
        }
        .padding(.vertical, 12)
        .padding(.horizontal, 10)
        .frame(maxWidth: .infinity, minHeight: 44, maxHeight: .infinity, alignment: .topLeading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(selected ? DS.textPrimary : DS.border, lineWidth: selected ? 2 : 1)
        )
        .contentShape(Rectangle())
    }

    private var selectedTag: some View {
        Label(CombatDurationInput10868.selectedTag, systemImage: "checkmark")
            .font(.caption2.weight(.semibold))
            .foregroundStyle(DS.textPrimary)
            .fixedSize()
    }

    @ViewBuilder private func leadContent(_ lead: CombatDurationLead10868) -> some View {
        switch lead {
        case .original(let original, _):
            VStack(alignment: .leading, spacing: 6) {
                railBlock(original)
                tileFigure(input.beforeReading(original))
                HStack(spacing: 4) {
                    if input.phase == .during { keyMark(.hollow) }
                    CombatDurationWrappedText10868(
                        text: "\(original.label) · \(CombatDurationInput10868.preMatchShort)",
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
            VStack(alignment: .leading, spacing: 6) {
                unshadedRail
                CombatDurationWrappedText10868(text: words, font: .caption2.weight(.semibold), color: DS.textSecondary, alignment: .leading)
            }
        case .sides:
            EmptyView()
        }
    }

    /// The window's rail, its final-bell symbol and words, or the owner's
    /// missing-window words beneath an unshaded rail.
    private func railBlock(_ original: CombatDurationOriginal10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .center, spacing: 4) {
                rail(input.rail(original))
                if let bell = original.window?.finalBell {
                    Image(systemName: bell.symbolName)
                        .font(.caption)
                        .foregroundStyle(DS.textPrimary)
                        .accessibilityHidden(true)
                }
            }
            if let bell = original.window?.finalBell {
                CombatDurationWrappedText10868(text: bell.text, font: .caption2, color: DS.textSecondary, alignment: .leading)
            }
            if original.window == nil {
                CombatDurationWrappedText10868(text: original.windowMissing, font: .caption2.weight(.semibold), color: DS.textSecondary, alignment: .leading)
            }
        }
    }

    private var unshadedRail: some View { rail(.undrawn) }

    private func rail(_ shape: CombatDurationRail10868) -> some View {
        CombatDurationRailLayout10868(spacing: 3) {
            ForEach(Array(input.segments.enumerated()), id: \.offset) { index, segment in
                railSegment(segment, index: index, fill: shape.fill(at: index))
            }
        }
    }

    /// One round: its label, any shaded part of the window, a dashed outline
    /// for the observed round and a diamond for the finish round. The finish
    /// marks the round, never a point inside it.
    private func railSegment(_ segment: CombatDurationSegment10868, index: Int, fill: CombatDurationFill10868?) -> some View {
        let finish = input.finishMark?.segmentIndex == index
        let observed = input.observedMark?.segmentIndex == index
        return HStack(spacing: 2) {
            if finish {
                Image(systemName: "diamond.fill").font(.caption2).accessibilityHidden(true)
            }
            Text(segment.shortLabel).font(.caption2.weight(.semibold)).monospacedDigit()
        }
        .fixedSize()
        .foregroundStyle(DS.textPrimary)
        .padding(.horizontal, 3)
        .frame(maxWidth: .infinity, minHeight: railHeight)
        .background {
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    DS.surface
                    if let fill {
                        Rectangle()
                            .fill(shading)
                            .frame(width: geometry.size.width * (fill.to - fill.from))
                            .offset(x: geometry.size.width * fill.from)
                    }
                }
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .strokeBorder(
                    observed ? DS.textPrimary : DS.border,
                    style: observed ? StrokeStyle(lineWidth: 1.5, dash: [3, 2]) : StrokeStyle(lineWidth: 1)
                )
        )
        .overlay(alignment: .top) {
            if finish { Rectangle().fill(DS.textPrimary).frame(height: 2) }
        }
    }

    /// A figure at the tile size, or the owner's words. Never shrunk.
    @ViewBuilder private func tileFigure(_ reading: CombatDurationReading10868) -> some View {
        switch reading {
        case .value(let observation):
            Text(observation.text)
                .font(.system(size: tileFigureSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize()
        case .missing(let words):
            CombatDurationWrappedText10868(text: words, font: .caption.weight(.semibold), color: DS.textSecondary, alignment: .leading)
        }
    }

    /// The in-fight figure at the pre-match figure's size: equal prominence.
    private func tileCurrent(_ reading: CombatDurationReading10868, marked: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            tileFigure(reading)
            HStack(spacing: 4) {
                if marked { keyMark(.filled) }
                Text(CombatDurationInput10868.currentShort).font(.caption2).foregroundStyle(DS.textSecondary)
            }
        }
    }

    private enum KeyMark { case hollow, filled }

    @ViewBuilder private func keyMark(_ mark: KeyMark) -> some View {
        switch mark {
        case .hollow:
            Circle().fill(DS.cardBg).overlay(Circle().stroke(DS.blue, lineWidth: 2)).frame(width: markSize, height: markSize)
        case .filled:
            Circle().fill(DS.blue).frame(width: markSize, height: markSize)
        }
    }

    /// The displayed original's own result: symbol and words agree with it.
    private func resultLine(_ result: CombatDurationResult10868, text: String, font: Font) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Image(systemName: result.symbolName).accessibilityHidden(true)
            CombatDurationWrappedText10868(
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

    /// The selected market's side rows (`panelSides`), each with its own window
    /// and readings. Tiles list theirs compactly through `tileSides`.
    @ViewBuilder private func sideList(_ market: CombatDurationMarket10868, _ sides: [CombatDurationTileSide10868]) -> some View {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 6) { sideControls(market, sides) }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 8) { sideControls(market, sides) }
                VStack(alignment: .leading, spacing: 8) { sideControls(market, sides) }
            }
        }
    }

    private func sideControls(_ market: CombatDurationMarket10868, _ sides: [CombatDurationTileSide10868]) -> some View {
        ForEach(Array(sides.enumerated()), id: \.offset) { _, side in
            sideControl(side.original, in: market, compact: false, action: side.action)
        }
    }

    private func sideControl(
        _ original: CombatDurationOriginal10868,
        in market: CombatDurationMarket10868,
        compact: Bool,
        action: CombatDurationAction10868?
    ) -> some View {
        let selected = input.isSelected(original, in: market)
        // Tile rows (compact) sit under the tile's title; panel rows do not.
        let showsWindowLabel = input.showsWindowLabel(original, inTileOf: compact ? market : nil)
        return control(action) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    CombatDurationWrappedText10868(
                        text: original.label,
                        font: (compact ? Font.caption : Font.subheadline).weight(.semibold),
                        color: DS.textPrimary,
                        alignment: .leading
                    )
                    if selected { selectedTag }
                }
                if showsWindowLabel, let window = original.window {
                    CombatDurationWrappedText10868(text: window.label, font: .caption2, color: DS.textSecondary, alignment: .leading)
                }
                railBlock(original)
                sideReading(input.beforeReading(original), title: CombatDurationInput10868.preMatchShort, mark: input.phase == .during ? .hollow : nil)
                if let current = input.currentReading(original) {
                    sideReading(current, title: CombatDurationInput10868.currentShort, mark: input.showsCurrentMark(original) ? .filled : nil)
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
        .accessibilityLabel("\(market.label), \(original.label)")
        .accessibilityValue(input.accessibilitySideValue(original, in: market))
        .accessibilityHint(action == nil ? "" : "Selects this side’s comparison")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(CombatDurationAccessibilityID10868.side(market.id, original.id))
    }

    private func sideReading(_ reading: CombatDurationReading10868, title: String, mark: KeyMark?) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            switch reading {
            case .value(let observation):
                Text(observation.text)
                    .font(.system(size: sideFigureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            case .missing(let text):
                CombatDurationWrappedText10868(text: text, font: .caption.weight(.semibold), color: DS.textSecondary, alignment: .leading)
            }
            HStack(spacing: 4) {
                if let mark { keyMark(mark) }
                Text(title).font(.caption2).foregroundStyle(DS.textSecondary)
            }
        }
    }

    // MARK: Selected market

    @ViewBuilder private var selectedPanel: some View {
        if let market = input.selection.market {
            VStack(alignment: .leading, spacing: 10) {
                Divider()
                CombatDurationWrappedText10868(
                    text: market.question,
                    font: .subheadline.weight(.semibold),
                    color: DS.textPrimary,
                    alignment: .leading
                )
                if let original = input.selection.original {
                    CombatDurationWrappedText10868(
                        text: "Original \(original.label) · \(original.window?.label ?? original.windowMissing)",
                        font: .caption,
                        color: DS.textSecondary,
                        alignment: .leading
                    )
                }
                if input.showsSingleOriginalNote {
                    Text(CombatDurationInput10868.singleOriginalNote)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let comparison = input.comparison {
                    comparisonFigures(comparison)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(input.accessibilityComparison ?? "")
                        .accessibilityIdentifier(CombatDurationAccessibilityID10868.comparison)
                }
                // None when the market's own tile already lists every side.
                let sides = input.panelSides(market, canSelect: canSelect)
                if !sides.isEmpty {
                    sideList(market, sides)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder private func comparisonFigures(_ comparison: CombatDurationComparison10868) -> some View {
        switch comparison {
        case .before(let original):
            comparisonValue(input.beforeReading(original), title: preMatchTitle(original), mark: nil, movement: nil)
        case .during(let original):
            CombatDurationPairLayout10868(spacing: 16, equalColumns: true, forceStack: typeSize.isAccessibilitySize) {
                comparisonValue(input.beforeReading(original), title: preMatchTitle(original), mark: .hollow, movement: nil)
                if let current = input.currentReading(original) {
                    comparisonValue(
                        current,
                        title: CombatDurationInput10868.currentTitle,
                        mark: input.showsCurrentMark(original) ? .filled : nil,
                        movement: input.movement(original)
                    )
                }
            }
        case .final(let original, let result):
            CombatDurationPairLayout10868(spacing: 16, equalColumns: true, forceStack: typeSize.isAccessibilitySize) {
                comparisonValue(input.beforeReading(original), title: preMatchTitle(original), mark: nil, movement: nil)
                VStack(alignment: .leading, spacing: 5) {
                    Text("\(CombatDurationInput10868.resultTitle) · \(original.label)")
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
        }
    }

    private func preMatchTitle(_ original: CombatDurationOriginal10868) -> String {
        "\(CombatDurationInput10868.preMatchTitle) · \(original.label)"
    }

    /// One figure with its own visible provenance.
    private func comparisonValue(_ reading: CombatDurationReading10868, title: String, mark: KeyMark?, movement: String?) -> some View {
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
            .accessibilityIdentifier(CombatDurationAccessibilityID10868.finish)
        }
    }

    // MARK: Details and timing

    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails), let original = input.selection.original {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails)
            } label: {
                HStack {
                    Text("Original \(original.label) · \(CombatDurationInput10868.detailsTitle)")
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier(CombatDurationAccessibilityID10868.details(original.id))
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

    private func timingLines(_ content: CombatDurationTiming10868) -> some View {
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
    private func control<Content: View>(_ action: CombatDurationAction10868?, @ViewBuilder content: () -> Content) -> some View {
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
