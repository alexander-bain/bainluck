import SwiftUI

// #10868 — "How could the fight end?": one combat method card across a bout's
// lifecycle. Each method (KO / TKO, Submission, Decision / draw in the retained
// Gautier–Kopylov bout) is its own binary market with its own original Yes and
// No. A tile leads with ONE original side and its ring encodes that side's own
// PRE-MATCH chance; the unfilled remainder is geometry, never the other side's
// quote and never a share of the other methods. The retained Yes values sum to
// 116.5% at different clocks: they are independent predicates, so nothing here
// complements, normalizes or draws them as one distribution.
//
// Before the fight a tile shows only its pre-match chance. During the fight the
// lead's pre-match and independently admitted in-fight chances sit at the same
// figure size with hollow and filled keys; an unavailable or withheld chance
// stays words. After the fight the ring keeps the pre-match chance and the
// displayed original's own contract result appears beside it, with a symbol
// that follows that original — a No that lost reads ✕ even when its Yes won.
// The official bout result is the owner's separate context and never grades a
// contract here.
//
// Presentation only, extracted from the approved design: `CombatOutcomeCards.tsx`
// (CombatOutcomeCard "methods"), `CombatBaselineMark.tsx`,
// `combatOutcomeCards.css` (dense tiles) and the native reference
// `CombatOutcomeCards.swift` (NativeCombatOutcomeCard). The reference's fixture
// admission, title matching, latest-before-start election, result-conflict
// rule, automatic first-side selection, sheet and state are NOT ported.
//
// Every method id, label and order, every original identity and side label,
// every figure, clock, provenance line, result word, heading and the official
// context arrive resolved by the owner and are shown verbatim. This layer never
// formats or rounds a probability (owner text carries at most one decimal),
// never reads a clock, never infers a phase, a grade or a method from the bout
// outcome, and never turns a settled 0/100 quote into a chance. Unknown is never
// a loss and absent is never zero.
//
// Selection, Details, timing disclosure, held updates and focus stay with the
// host: the view keeps no selected state, no sheet, no subscription and runs no
// animation, so reduced motion has nothing to stop. A tile leads with the
// host-selected side, else the host's explicit overview side, else lists every
// side — the leaf never picks Yes, the winner or a neighbour, and never
// switches sides on an update. Every original stays on screen: a ring tile that
// neither selects its side nor belongs to the selected method lists its other
// originals beneath the ring, and an unavailable side keeps its notice and lists
// every original. With no callback, content is shown without a
// button and no tap is asked for.
//
// The fighter-knockout card reuses these tiles unchanged: its owner supplies
// each fighter's own KO / TKO market as one row (the fighter's full name as the
// label, the original question, its own Yes and No) plus its own words for the
// three lines that say "method" (`CombatMethodCopy10868`). Each ring is still
// that original's own pre-match chance — never a head-to-head win chance or a
// share of the other fighter's. Duration and fighter-round cards are separate.
//
// Host binding still owed — not available at this base. An owner must supply
// proved method ids/labels/order and each method's original Yes/No membership;
// an admitted pre-match observation per original or its own missing words;
// during the fight an admitted current observation or its own unavailable /
// withheld words, with currentness already applied; after the fight each
// original's independently admitted contract result; and any admitted official
// bout context. COMBAT-METHOD-NATIVE-BINDING-MAP.md and
// COMBAT-FIGHTER-KO-NATIVE-BINDING-MAP.md name the gaps.

/// One admitted reading. `probability` drives ring geometry only; `text` is what
/// the reader sees.
nonisolated struct CombatMethodObservation10868: Equatable {
    let probability: Double
    /// The owner's whole figure ("55%", "10.5%").
    let text: String
    /// Short clock ("4:27 PM PT"); nil draws none.
    let timeText: String?
    /// Full provenance, shown in the selected comparison and spoken
    /// ("Last recorded before start · Oct 3, 4:27 PM PT · Polymarket").
    let detail: String
}

nonisolated enum CombatMethodPhase10868: Equatable {
    case before
    case during
    case final
}

/// The owner's in-fight state for one original, with currentness already applied.
nonisolated enum CombatMethodCurrent10868: Equatable {
    /// An admitted, current observation with the owner's optional movement line.
    case recorded(CombatMethodObservation10868, movement: String?)
    /// No admitted current reading ("No in-fight chance").
    case unavailable(String)
    /// A reading exists but is not admitted as current ("Held since round 1").
    case withheld(String)
}

/// The original side's contract result. There is no Bool: a missing result is
/// never a loss.
nonisolated enum CombatMethodResult10868: Equatable {
    case won(String)
    case lost(String)
    case void(String)
    /// Not yet independently admitted ("Result unconfirmed").
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

/// One original side of one method's market. Each reading carries its own
/// missing words. `current` is read only during the fight, `result` only after.
nonisolated struct CombatMethodOriginal10868: Equatable {
    /// Exact original outcome id, passed back to the owner unchanged.
    let id: String
    /// The original's market id, passed back unchanged.
    let marketID: String
    /// The original side name ("Yes", "No").
    let label: String
    let before: CombatMethodObservation10868?
    let beforeMissing: String
    let current: CombatMethodCurrent10868
    let result: CombatMethodResult10868
}

/// One owner-proved finish method with its original sides in the owner's order.
nonisolated struct CombatMethod10868: Equatable {
    /// The owner's method id.
    let id: String
    /// Full tile name ("KO / TKO"); never truncated.
    let label: String
    /// The original question ("Will the fight be won by KO or TKO?").
    let question: String
    let originals: [CombatMethodOriginal10868]
    /// The owner's explicit overview side for this tile; nil lists every side.
    let overviewOriginalID: String?
}

/// The owner's official bout context ("Official bout result"), read only during
/// and after the fight. It is never a contract result.
nonisolated struct CombatMethodActual10868: Equatable {
    let title: String
    let lines: [String]
    let accessibilityDetail: String?
}

/// The owner's timing disclosure for one original. Shown only while that exact
/// original is the resolved selection.
nonisolated struct CombatMethodTiming10868: Equatable {
    let originalID: String
    let title: String
    let lines: [String]
}

/// Exact original identity, handed back to the owner on select and Details.
nonisolated struct CombatMethodOriginalRef10868: Hashable {
    let eventID: String
    let methodID: String
    let marketID: String
    let originalID: String
}

nonisolated enum CombatMethodSelection10868: Equatable {
    case none
    /// A method is selected with no side.
    case method(CombatMethod10868)
    case original(CombatMethod10868, CombatMethodOriginal10868)
    /// The method resolves; the selected side is absent, withdrawn or duplicated.
    case sideUnavailable(CombatMethod10868, String)
    /// The selected method (or a side named without its method) does not resolve
    /// to exactly one.
    case unavailable(String)

    var method: CombatMethod10868? {
        switch self {
        case .method(let method), .original(let method, _), .sideUnavailable(let method, _): method
        case .none, .unavailable: nil
        }
    }

    var original: CombatMethodOriginal10868? {
        if case .original(_, let original) = self { return original }
        return nil
    }
}

nonisolated enum CombatMethodReading10868: Equatable {
    case value(CombatMethodObservation10868)
    case missing(String)
}

/// What a tile leads with.
nonisolated enum CombatMethodLead10868: Equatable {
    case original(CombatMethodOriginal10868, selected: Bool)
    /// The host named a side this method does not carry exactly once.
    case unavailable(String)
    /// No side is named: every side is listed, none is chosen.
    case sides
}

/// One original listed inside a tile, with the exact action it may carry.
nonisolated struct CombatMethodTileSide10868: Equatable {
    let original: CombatMethodOriginal10868
    let action: CombatMethodAction10868?
}

/// What one tile draws — the View's own branch. Every original stays on screen:
/// in the tile itself, or in the selected method's side row beneath the grid —
/// never both (`panelSides`).
nonisolated enum CombatMethodTilePresentation10868: Equatable {
    /// The approved compact ring tile: one control when `action` is set, else
    /// static. Its other sides are reached through that action or, for the
    /// selected method, the side row that already lists them.
    case ring(CombatMethodOriginal10868, selected: Bool, action: CombatMethodAction10868?)
    /// A static overview on an unselected method: the ring stays and every other
    /// original is listed beneath it. The tile itself is not a button.
    case ringWithSides(CombatMethodOriginal10868, others: [CombatMethodTileSide10868])
    /// The notice alone: the selected method's side row lists every side.
    case unavailable(String)
    /// The notice, then every original with its exact safe action. Not a button.
    case unavailableWithSides(String, sides: [CombatMethodTileSide10868])
    /// No side named: every side listed, none chosen. On the selected method
    /// these are its only side rows; the panel beneath lists none.
    case sides([CombatMethodTileSide10868])

    /// The originals this tile itself lists as their own rows.
    var listed: [CombatMethodTileSide10868] {
        switch self {
        case .ring, .unavailable: []
        case .ringWithSides(_, let sides), .unavailableWithSides(_, let sides), .sides(let sides): sides
        }
    }
}

/// The selected original's comparison, by phase.
nonisolated enum CombatMethodComparison10868: Equatable {
    case before(CombatMethodOriginal10868)
    case during(CombatMethodOriginal10868)
    case final(CombatMethodOriginal10868, CombatMethodResult10868)
}

nonisolated enum CombatMethodAction10868: Equatable {
    case select(CombatMethodOriginalRef10868)
    case details(CombatMethodOriginalRef10868)

    func perform(
        onSelect: ((CombatMethodOriginalRef10868) -> Void)?,
        onDetails: ((CombatMethodOriginalRef10868) -> Void)?
    ) {
        switch self {
        case .select(let ref): onSelect?(ref)
        case .details(let ref): onDetails?(ref)
        }
    }
}

nonisolated enum CombatMethodTimingPresentation10868: Equatable {
    /// The page owns the expanded flag.
    case disclosure(CombatMethodTiming10868)
    /// No binding: the owner's timing content, already expanded.
    case expanded(CombatMethodTiming10868)
}

/// The owner's words for the card's three method-specific lines. The default
/// is the method card's own text; a host reusing the tiles for another
/// owner-proved row kind supplies its own. Shown and spoken verbatim.
nonisolated struct CombatMethodCopy10868: Equatable {
    /// Shown above the tiles when a tap does something.
    let chooseInstruction: String
    /// Shown when the selected row does not resolve to exactly one.
    let methodUnavailable: String
    /// Spoken on a row's tile when it is selected with no side.
    let methodSelectedTag: String

    static let method = CombatMethodCopy10868(
        chooseInstruction: CombatMethodInput10868.chooseInstruction,
        methodUnavailable: CombatMethodInput10868.methodUnavailable,
        methodSelectedTag: CombatMethodInput10868.methodSelectedTag
    )
}

nonisolated struct CombatMethodInput10868: Equatable {
    let phase: CombatMethodPhase10868
    let eventID: String
    /// "Polymarket · contract results".
    let eyebrow: String
    /// The owner's headline ("How could the fight end?"); nil draws none.
    let title: String?
    /// The owner's caption under the headline; nil draws none.
    let caption: String?
    /// Every method in the owner's order — never sorted, filtered or capped.
    let methods: [CombatMethod10868]
    let selectedMethodID: String?
    let selectedOriginalID: String?
    let actual: CombatMethodActual10868?
    let timing: CombatMethodTiming10868?
    /// The owner's words for the method-specific lines; the method card's own by default.
    var copy: CombatMethodCopy10868 = .method

    static let preMatchTitle = "Pre-match chance"
    static let preMatchShort = "Pre-match"
    static let currentTitle = "In-fight chance"
    static let currentShort = "In-fight"
    static let resultTitle = "Contract result"
    static let selectedTag = "Selected"
    static let methodSelectedTag = "Method selected"
    static let detailsTitle = "Original prop & evidence"
    static let chooseInstruction = "Choose a method or side to compare."
    static let methodUnavailable = "Selected method unavailable in this update."
    static let sideUnavailable = "Selected side unavailable in this update."
    static let sideUnavailableShort = "Selected side unavailable"
    static let overviewUnavailable = "Side unavailable in this update"

    // MARK: Identity

    private static func repeated(_ ids: [String]) -> Set<String> {
        var seen = Set<String>()
        var repeated = Set<String>()
        for id in ids where !seen.insert(id).inserted { repeated.insert(id) }
        return repeated
    }

    /// Method ids carried more than once. Such methods get no action.
    var duplicateMethodIDs: Set<String> { Self.repeated(methods.map(\.id)) }

    /// Original ids carried more than once anywhere on the card. Such originals
    /// get no action and cannot be selected.
    var duplicateOriginalIDs: Set<String> { Self.repeated(methods.flatMap { $0.originals.map(\.id) }) }

    func ref(_ original: CombatMethodOriginal10868, in method: CombatMethod10868) -> CombatMethodOriginalRef10868 {
        CombatMethodOriginalRef10868(eventID: eventID, methodID: method.id, marketID: original.marketID, originalID: original.id)
    }

    private func isUnique(_ original: CombatMethodOriginal10868, in method: CombatMethod10868) -> Bool {
        !duplicateMethodIDs.contains(method.id) && !duplicateOriginalIDs.contains(original.id)
    }

    // MARK: Selection

    /// Exact ids only. A missing, withdrawn or duplicated id gets no substitute,
    /// and every original stays listed.
    var selection: CombatMethodSelection10868 {
        switch (selectedMethodID, selectedOriginalID) {
        case (nil, nil):
            return .none
        case (nil, let originalID?):
            guard !duplicateOriginalIDs.contains(originalID) else { return .unavailable(originalID) }
            let holders = methods.filter { $0.originals.contains { $0.id == originalID } }
            guard holders.count == 1, let method = holders.first, !duplicateMethodIDs.contains(method.id),
                  let original = method.originals.first(where: { $0.id == originalID })
            else { return .unavailable(originalID) }
            return .original(method, original)
        case (let methodID?, let originalID):
            let matches = methods.filter { $0.id == methodID }
            guard matches.count == 1, let method = matches.first else { return .unavailable(methodID) }
            guard let originalID else { return .method(method) }
            guard !duplicateOriginalIDs.contains(originalID),
                  let original = method.originals.first(where: { $0.id == originalID })
            else { return .sideUnavailable(method, originalID) }
            return .original(method, original)
        }
    }

    func isSelectedMethod(_ method: CombatMethod10868) -> Bool {
        guard let selected = selection.method else { return false }
        return selected.id == method.id && !duplicateMethodIDs.contains(method.id)
    }

    func isSelected(_ original: CombatMethodOriginal10868, in method: CombatMethod10868) -> Bool {
        guard case .original(let selectedMethod, let selectedOriginal) = selection else { return false }
        return selectedMethod.id == method.id && selectedOriginal.id == original.id
    }

    var selectionNotice: String? {
        switch selection {
        case .unavailable: copy.methodUnavailable
        case .sideUnavailable: Self.sideUnavailable
        case .none, .method, .original: nil
        }
    }

    /// The host-selected side, else the host's overview side, else every side.
    /// Never Yes, the winner or a neighbour by default.
    func lead(_ method: CombatMethod10868) -> CombatMethodLead10868 {
        switch selection {
        case .original(let selected, let original) where selected.id == method.id:
            return .original(original, selected: true)
        case .sideUnavailable(let selected, _) where selected.id == method.id:
            return .unavailable(Self.sideUnavailableShort)
        default:
            break
        }
        guard let overviewID = method.overviewOriginalID else { return .sides }
        let matches = method.originals.filter { $0.id == overviewID }
        guard matches.count == 1, !duplicateOriginalIDs.contains(overviewID) else {
            return .unavailable(Self.overviewUnavailable)
        }
        return .original(matches[0], selected: false)
    }

    // MARK: Phase visibility

    func beforeReading(_ original: CombatMethodOriginal10868) -> CombatMethodReading10868 {
        original.before.map { .value($0) } ?? .missing(original.beforeMissing)
    }

    /// During the fight only. Never falls back to the pre-match reading.
    func currentReading(_ original: CombatMethodOriginal10868) -> CombatMethodReading10868? {
        guard phase == .during else { return nil }
        switch original.current {
        case .recorded(let observation, _): return .value(observation)
        case .unavailable(let text), .withheld(let text): return .missing(text)
        }
    }

    /// The owner's movement line, only beside an admitted current observation.
    func movement(_ original: CombatMethodOriginal10868) -> String? {
        guard phase == .during, case .recorded(_, let movement) = original.current else { return nil }
        return movement
    }

    /// The filled current key appears only beside an admitted current observation.
    func showsCurrentMark(_ original: CombatMethodOriginal10868) -> Bool {
        if case .value? = currentReading(original) { return true }
        return false
    }

    /// After the fight only. Any supplied current reading is ignored then, so a
    /// settled 0/100 price can never read as a chance.
    func result(_ original: CombatMethodOriginal10868) -> CombatMethodResult10868? {
        phase == .final ? original.result : nil
    }

    /// Nil before the fight.
    var visibleActual: CombatMethodActual10868? { phase == .before ? nil : actual }

    var comparison: CombatMethodComparison10868? {
        guard let original = selection.original else { return nil }
        switch phase {
        case .before: return .before(original)
        case .during: return .during(original)
        case .final: return .final(original, original.result)
        }
    }

    /// Asks for a tap only when one does something.
    func instruction(canSelect: Bool) -> String? {
        canSelect && !methods.isEmpty ? copy.chooseInstruction : nil
    }

    // MARK: Actions and timing

    /// A tile selects the exact side it leads with — never a side it would have
    /// to choose.
    func tileAction(_ method: CombatMethod10868, canSelect: Bool) -> CombatMethodAction10868? {
        guard canSelect, case .original(let original, _) = lead(method), isUnique(original, in: method) else { return nil }
        return .select(ref(original, in: method))
    }

    func sideAction(_ original: CombatMethodOriginal10868, in method: CombatMethod10868, canSelect: Bool) -> CombatMethodAction10868? {
        guard canSelect, isUnique(original, in: method) else { return nil }
        return .select(ref(original, in: method))
    }

    /// Originals listed as rows, each with exactly the action `sideAction` permits.
    private func listed(
        _ originals: [CombatMethodOriginal10868],
        in method: CombatMethod10868,
        canSelect: Bool
    ) -> [CombatMethodTileSide10868] {
        originals.map { CombatMethodTileSide10868(original: $0, action: sideAction($0, in: method, canSelect: canSelect)) }
    }

    /// Whether the panel beneath the grid lists this method's sides: only for the
    /// selected method, and not when its tile already lists every side (chosen
    /// with no side and no overview), so no side list is mounted twice.
    func panelListsSides(_ method: CombatMethod10868) -> Bool {
        isSelectedMethod(method) && lead(method) != .sides
    }

    /// The side rows the selected panel mounts for this method — the View's own
    /// list. Empty unless `panelListsSides`.
    func panelSides(_ method: CombatMethod10868, canSelect: Bool) -> [CombatMethodTileSide10868] {
        panelListsSides(method) ? listed(method.originals, in: method, canSelect: canSelect) : []
    }

    /// The tile the View draws. A ring that neither selects its side nor belongs
    /// to the selected method would hide any other originals, so they are listed
    /// in the tile; an unavailable side that is not the selected method's keeps
    /// its notice and lists every original. A tile never repeats side rows the
    /// panel beneath the grid mounts, and no duplicated id gains an action.
    func tilePresentation(_ method: CombatMethod10868, canSelect: Bool) -> CombatMethodTilePresentation10868 {
        let panelLists = panelListsSides(method)
        switch lead(method) {
        case .sides:
            return .sides(listed(method.originals, in: method, canSelect: canSelect))
        case .unavailable(let words):
            return panelLists
                ? .unavailable(words)
                : .unavailableWithSides(words, sides: listed(method.originals, in: method, canSelect: canSelect))
        case .original(let original, let selected):
            let action = tileAction(method, canSelect: canSelect)
            let others = method.originals.filter { $0.id != original.id }
            if action != nil || panelLists || others.isEmpty {
                return .ring(original, selected: selected, action: action)
            }
            return .ringWithSides(original, others: listed(others, in: method, canSelect: canSelect))
        }
    }

    func detailsAction(canOpenDetails: Bool) -> CombatMethodAction10868? {
        guard canOpenDetails, case .original(let method, let original) = selection else { return nil }
        return .details(ref(original, in: method))
    }

    /// Timing only for the exact resolved selection.
    func timingPresentation(hasBinding: Bool) -> CombatMethodTimingPresentation10868? {
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

    /// One original's readings for the phase: pre-match, then in-fight or result.
    func accessibilityReadings(_ original: CombatMethodOriginal10868, detailed: Bool) -> String {
        var parts = ["\(Self.preMatchTitle): \(Self.spoken(beforeReading(original), detailed: detailed))"]
        if let current = currentReading(original) {
            parts.append("\(Self.currentTitle): \(Self.spoken(current, detailed: detailed))")
        }
        if let movement = movement(original) { parts.append(movement) }
        if let result = result(original) { parts.append("\(Self.resultTitle): \(result.text)") }
        return parts.joined(separator: "; ")
    }

    /// A tile: its lead with full provenance, then every other side, so no side
    /// is reachable only by sight.
    func accessibilityTileValue(_ method: CombatMethod10868) -> String {
        var parts: [String] = []
        var spokenIDs = Set<String>()
        switch lead(method) {
        case .original(let original, let selected):
            parts.append(accessibilityLeadValue(original))
            if selected { parts.append(Self.selectedTag) }
            spokenIDs.insert(original.id)
        case .unavailable(let words):
            parts.append(words)
        case .sides:
            break
        }
        let others = method.originals.filter { !spokenIDs.contains($0.id) }
        let prefix = spokenIDs.isEmpty ? "" : "Also "
        for original in others {
            parts.append("\(prefix)\(original.label). \(accessibilityReadings(original, detailed: false))")
        }
        if isSelectedMethod(method), selection.original == nil { parts.append(copy.methodSelectedTag) }
        return parts.joined(separator: ". ")
    }

    /// A lead side alone, with full provenance. A static overview's ring speaks
    /// this; the originals listed beside it speak for themselves.
    func accessibilityLeadValue(_ original: CombatMethodOriginal10868) -> String {
        "\(original.label). \(accessibilityReadings(original, detailed: true))"
    }

    func accessibilitySideValue(_ original: CombatMethodOriginal10868, in method: CombatMethod10868) -> String {
        var parts = [accessibilityReadings(original, detailed: true)]
        if isSelected(original, in: method) { parts.append(Self.selectedTag) }
        return parts.joined(separator: "; ")
    }

    /// The selected original's comparison, each reading with its provenance.
    var accessibilityComparison: String? {
        guard let comparison, let method = selection.method else { return nil }
        let original: CombatMethodOriginal10868
        switch comparison {
        case .before(let selected), .during(let selected), .final(let selected, _): original = selected
        }
        return "\(method.question), original \(original.label). \(accessibilityReadings(original, detailed: true))"
    }

    var accessibilityActual: String? {
        guard let actual = visibleActual else { return nil }
        let lines = ([actual.title] + actual.lines).joined(separator: ". ")
        return ([lines, actual.accessibilityDetail].compactMap { $0 }).joined(separator: ". ")
    }

    private static func spoken(_ reading: CombatMethodReading10868, detailed: Bool) -> String {
        switch reading {
        case .value(let observation): detailed ? "\(observation.text), \(observation.detail)" : observation.text
        case .missing(let text): text
        }
    }
}

nonisolated enum CombatMethodArrangement10868: Equatable {
    /// One subview, or more than two: stacked in order.
    case single
    case sideBySide
    case stacked
}

nonisolated struct CombatMethodColumns10868: Equatable {
    let first: CGFloat
    let second: CGFloat
}

nonisolated enum CombatMethodGeometry10868 {
    static let ringLineWidth: CGFloat = 5

    /// The ring's arc. Nil for anything outside 0...1 — bad input draws no arc,
    /// never a clipped or normalized one. A real zero is 0.
    static func ringFraction(_ probability: Double) -> Double? {
        guard probability.isFinite, probability >= 0, probability <= 1 else { return nil }
        return probability
    }

    /// Clear space from the ring's frame edge to its interior: the whole stroke
    /// plus a 4pt gap before the figure.
    static let ringInset: CGFloat = ringLineWidth + 4

    /// The ring's diameter for a figure of this measured size: the minimum while
    /// the figure's whole box fits inside, otherwise just wide enough that it
    /// does. Only the ring grows — the figure is never shrunk or clipped.
    static func ringSide(minimum: CGFloat, figure: CGSize, inset: CGFloat = ringInset) -> CGFloat {
        let diagonal = (figure.width * figure.width + figure.height * figure.height).squareRoot()
        let needed = (diagonal + 2 * inset).rounded(.up)
        guard needed.isFinite else { return minimum }
        return max(minimum, needed)
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

    /// As many equal columns as keep every tile whole: from one per method down
    /// to one. A column must reach the scaled minimum and every tile's measured
    /// width (its ring, figure and widest word) must fit it. There is no fixed
    /// ceiling of three; nothing shrinks or truncates to fit.
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

    /// Tile indices row by row, in the owner's order.
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
    ) -> CombatMethodArrangement10868 {
        if forceStack { return .stacked }
        guard first.isFinite, second.isFinite, first >= 0, second >= 0 else { return .stacked }
        guard let available, available.isFinite else { return .sideBySide }
        return neededWidth(first: first, second: second, spacing: spacing, equalColumns: equalColumns) <= available
            ? .sideBySide : .stacked
    }

    static func neededWidth(first: CGFloat, second: CGFloat, spacing: CGFloat, equalColumns: Bool) -> CGFloat {
        equalColumns ? 2 * max(first, second) + spacing : first + second + spacing
    }

    static func columns(total: CGFloat, first: CGFloat, spacing: CGFloat, equalColumns: Bool) -> CombatMethodColumns10868 {
        if equalColumns {
            let half = max(0, (total - spacing) / 2)
            return CombatMethodColumns10868(first: half, second: half)
        }
        let leading = min(max(0, first), max(0, total - spacing))
        return CombatMethodColumns10868(first: leading, second: max(0, total - spacing - leading))
    }
}

/// The method tiles in equal columns, row by row in the owner's order. Tiles in
/// one row share the row's height.
struct CombatMethodTileGridLayout10868: Layout {
    var spacing: CGFloat
    var minimumColumnWidth: CGFloat
    var forceSingleColumn: Bool

    private func columnCount(_ width: CGFloat?, _ subviews: Subviews) -> Int {
        CombatMethodGeometry10868.columnCount(
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
            return CombatMethodGeometry10868.columnWidth(available: width, columns: columns, spacing: spacing)
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
        let rows = CombatMethodGeometry10868.rows(count: subviews.count, columns: columns)
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
        for row in CombatMethodGeometry10868.rows(count: subviews.count, columns: columns) {
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
struct CombatMethodPairLayout10868: Layout {
    var spacing: CGFloat
    var equalColumns: Bool
    var forceStack: Bool

    private func idealWidths(_ subviews: Subviews) -> CombatMethodColumns10868 {
        CombatMethodColumns10868(
            first: subviews[0].sizeThatFits(.unspecified).width,
            second: subviews[1].sizeThatFits(.unspecified).width
        )
    }

    private func arrangement(_ width: CGFloat?, _ subviews: Subviews) -> CombatMethodArrangement10868 {
        guard subviews.count == 2 else { return .single }
        let ideal = idealWidths(subviews)
        return CombatMethodGeometry10868.pairArrangement(
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
            let total = proposal.width ?? CombatMethodGeometry10868.neededWidth(
                first: ideal.first, second: ideal.second, spacing: spacing, equalColumns: equalColumns
            )
            let widths = CombatMethodGeometry10868.columns(total: total, first: ideal.first, spacing: spacing, equalColumns: equalColumns)
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
            let widths = CombatMethodGeometry10868.columns(total: bounds.width, first: ideal.first, spacing: spacing, equalColumns: equalColumns)
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

/// The pre-match ring sized to its figure. Two subviews: the ring, then the
/// owner's figure. A long or qualified figure ("≥99.5%") claims its real space.
struct CombatMethodRingLayout10868: Layout {
    let minimumSide: CGFloat

    private func side(_ subviews: Subviews) -> CGFloat {
        CombatMethodGeometry10868.ringSide(minimum: minimumSide, figure: subviews[1].sizeThatFits(.unspecified))
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard subviews.count == 2 else { return .zero }
        let length = side(subviews)
        return CGSize(width: length, height: length)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count == 2 else { return }
        let length = side(subviews)
        let center = CGPoint(x: bounds.midX, y: bounds.midY)
        subviews[0].place(at: center, anchor: .center, proposal: ProposedViewSize(width: length, height: length))
        subviews[1].place(at: center, anchor: .center, proposal: .unspecified)
    }
}

/// Wrapping owner text that never breaks inside a word: a hidden, zero-height
/// strut of its words makes the widest word part of the measured width, so the
/// tile grid drops a column before any word would split.
private struct CombatMethodWrappedText10868: View {
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
                ForEach(Array(CombatMethodGeometry10868.words(text).enumerated()), id: \.offset) { _, word in
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
nonisolated enum CombatMethodAccessibilityID10868 {
    static let comparison = "combatMethod10868.comparison"
    static let actual = "combatMethod10868.actual"
    static func tile(_ methodID: String) -> String { "combatMethod10868.tile.\(methodID)" }
    static func side(_ methodID: String, _ originalID: String) -> String { "combatMethod10868.side.\(methodID).\(originalID)" }
    static func details(_ originalID: String) -> String { "combatMethod10868.details.\(originalID)" }
}

struct CombatMethodPresentation10868: View {
    let input: CombatMethodInput10868
    var onSelect: ((CombatMethodOriginalRef10868) -> Void)? = nil
    var onDetails: ((CombatMethodOriginalRef10868) -> Void)? = nil
    /// Page-owned. Nil shows the owner's timing content already expanded.
    var timingExpanded: Binding<Bool>? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .headline) private var tileFigureSize: CGFloat = 17
    @ScaledMetric(relativeTo: .headline) private var tileRingSize: CGFloat = 60
    @ScaledMetric(relativeTo: .caption) private var minimumColumnWidth: CGFloat = 96
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .title3) private var sideFigureSize: CGFloat = 20

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            if let instruction = input.instruction(canSelect: canSelect) {
                Text(instruction)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            CombatMethodTileGridLayout10868(
                spacing: 8,
                minimumColumnWidth: minimumColumnWidth,
                forceSingleColumn: typeSize.isAccessibilitySize
            ) {
                ForEach(Array(input.methods.enumerated()), id: \.offset) { _, method in
                    tile(method)
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
            actualContext
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Header

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

    // MARK: Tiles

    @ViewBuilder private func tile(_ method: CombatMethod10868) -> some View {
        switch input.tilePresentation(method, canSelect: canSelect) {
        case .ring(let original, let selected, let action):
            control(action) {
                tileFrame(method) { leadContent(.original(original, selected: selected)) }
            }
            .accessibilityLabel(method.label)
            .accessibilityValue(input.accessibilityTileValue(method))
            .accessibilityHint(action == nil ? "" : "Selects this side’s comparison")
            .accessibilityAddTraits(input.isSelectedMethod(method) ? .isSelected : [])
            .accessibilityIdentifier(CombatMethodAccessibilityID10868.tile(method.id))
        case .unavailable(let words):
            control(nil) {
                tileFrame(method) { leadContent(.unavailable(words)) }
            }
            .accessibilityLabel(method.label)
            .accessibilityValue(input.accessibilityTileValue(method))
            .accessibilityAddTraits(input.isSelectedMethod(method) ? .isSelected : [])
            .accessibilityIdentifier(CombatMethodAccessibilityID10868.tile(method.id))
        case .ringWithSides(let original, let others):
            // The ring is static; each other original is its own row. The tile
            // only groups them, so no side control sits inside a button.
            tileFrame(method) {
                leadContent(.original(original, selected: false))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(method.label), \(original.label)")
                    .accessibilityValue(input.accessibilityLeadValue(original))
                tileSides(method, others)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(method.label)
            .accessibilityIdentifier(CombatMethodAccessibilityID10868.tile(method.id))
        case .unavailableWithSides(let words, let sides):
            tileFrame(method) {
                leadContent(.unavailable(words))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(method.label), \(words)")
                tileSides(method, sides)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(method.label)
            .accessibilityIdentifier(CombatMethodAccessibilityID10868.tile(method.id))
        case .sides(let sides):
            // Every side is its own control; the tile only groups them.
            tileFrame(method) { tileSides(method, sides) }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(method.label)
                .accessibilityIdentifier(CombatMethodAccessibilityID10868.tile(method.id))
        }
    }

    /// The originals a tile lists itself, compact, each with its own action.
    private func tileSides(_ method: CombatMethod10868, _ sides: [CombatMethodTileSide10868]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(sides.enumerated()), id: \.offset) { _, side in
                sideControl(side.original, in: method, compact: true, action: side.action)
            }
        }
    }

    /// Selection is an outline plus a named tag — never colour alone, and never
    /// the same shape as a result symbol or the ring.
    private func tileFrame<Content: View>(_ method: CombatMethod10868, @ViewBuilder content: () -> Content) -> some View {
        let selected = input.isSelectedMethod(method)
        return VStack(alignment: .center, spacing: 8) {
            CombatMethodWrappedText10868(text: method.label, font: .caption.weight(.semibold), color: DS.textPrimary)
            if selected { selectedTag }
            content()
        }
        .padding(.vertical, 12)
        .padding(.horizontal, 6)
        .frame(maxWidth: .infinity, minHeight: 44, maxHeight: .infinity, alignment: .top)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(selected ? DS.textPrimary : DS.border, lineWidth: selected ? 2 : 1)
        )
        .contentShape(Rectangle())
    }

    private var selectedTag: some View {
        Label(CombatMethodInput10868.selectedTag, systemImage: "checkmark")
            .font(.caption2.weight(.semibold))
            .foregroundStyle(DS.textPrimary)
            .fixedSize()
    }

    @ViewBuilder private func leadContent(_ lead: CombatMethodLead10868) -> some View {
        switch lead {
        case .original(let original, _):
            VStack(alignment: .center, spacing: 6) {
                tileRing(input.beforeReading(original))
                HStack(spacing: 4) {
                    if input.phase == .during { keyMark(.hollow) }
                    CombatMethodWrappedText10868(
                        text: "\(original.label) · \(CombatMethodInput10868.preMatchShort)",
                        font: .caption2,
                        color: DS.textSecondary
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
            VStack(alignment: .center, spacing: 6) {
                dashedRing.frame(width: tileRingSize, height: tileRingSize)
                CombatMethodWrappedText10868(text: words, font: .caption2.weight(.semibold), color: DS.textSecondary)
            }
        case .sides:
            EmptyView()
        }
    }

    /// The lead side's pre-match chance. A malformed value keeps the owner's
    /// figure on a dashed ring with no arc; a missing one keeps the dashed ring
    /// with the words beneath — never an empty solid ring that would read as 0%.
    @ViewBuilder private func tileRing(_ reading: CombatMethodReading10868) -> some View {
        switch reading {
        case .value(let observation):
            CombatMethodRingLayout10868(minimumSide: tileRingSize) {
                if let fraction = CombatMethodGeometry10868.ringFraction(observation.probability) {
                    ZStack {
                        Circle().strokeBorder(DS.trackBg, lineWidth: CombatMethodGeometry10868.ringLineWidth)
                        Circle()
                            .inset(by: CombatMethodGeometry10868.ringLineWidth / 2)
                            .trim(from: 0, to: fraction)
                            .stroke(DS.blue, style: StrokeStyle(lineWidth: CombatMethodGeometry10868.ringLineWidth, lineCap: .butt))
                            .rotationEffect(.degrees(-90))
                    }
                } else {
                    dashedRing
                }
                Text(observation.text)
                    .font(.system(size: tileFigureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            }
        case .missing(let words):
            VStack(alignment: .center, spacing: 4) {
                dashedRing.frame(width: tileRingSize, height: tileRingSize)
                CombatMethodWrappedText10868(text: words, font: .caption2.weight(.semibold), color: DS.textSecondary)
            }
        }
    }

    /// The in-fight figure at the ring figure's size: equal prominence.
    private func tileCurrent(_ reading: CombatMethodReading10868, marked: Bool) -> some View {
        VStack(alignment: .center, spacing: 2) {
            HStack(spacing: 4) {
                if marked { keyMark(.filled) }
                Text(CombatMethodInput10868.currentShort).font(.caption2).foregroundStyle(DS.textSecondary)
            }
            switch reading {
            case .value(let observation):
                Text(observation.text)
                    .font(.system(size: tileFigureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            case .missing(let words):
                CombatMethodWrappedText10868(text: words, font: .caption2.weight(.semibold), color: DS.textSecondary)
            }
        }
    }

    private var dashedRing: some View {
        Circle()
            .inset(by: 1)
            .stroke(DS.border, style: StrokeStyle(lineWidth: 2, dash: [4, 4]))
    }

    private enum KeyMark { case hollow, filled }

    @ViewBuilder private func keyMark(_ mark: KeyMark) -> some View {
        switch mark {
        case .hollow:
            Circle().fill(DS.cardBg).overlay(Circle().stroke(DS.blue, lineWidth: 2)).frame(width: 9, height: 9)
        case .filled:
            Circle().fill(DS.blue).frame(width: 9, height: 9)
        }
    }

    /// The displayed original's own result: symbol and words agree with it.
    private func resultLine(_ result: CombatMethodResult10868, text: String, font: Font) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Image(systemName: result.symbolName).accessibilityHidden(true)
            CombatMethodWrappedText10868(
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

    /// The selected method's side rows (`panelSides`), each with its own readings.
    /// Tiles list theirs compactly through `tileSides`.
    @ViewBuilder private func sideList(_ method: CombatMethod10868, _ sides: [CombatMethodTileSide10868]) -> some View {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 6) { sideControls(method, sides) }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 8) { sideControls(method, sides) }
                VStack(alignment: .leading, spacing: 8) { sideControls(method, sides) }
            }
        }
    }

    private func sideControls(_ method: CombatMethod10868, _ sides: [CombatMethodTileSide10868]) -> some View {
        ForEach(Array(sides.enumerated()), id: \.offset) { _, side in
            sideControl(side.original, in: method, compact: false, action: side.action)
        }
    }

    private func sideControl(
        _ original: CombatMethodOriginal10868,
        in method: CombatMethod10868,
        compact: Bool,
        action: CombatMethodAction10868?
    ) -> some View {
        let selected = input.isSelected(original, in: method)
        return control(action) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    CombatMethodWrappedText10868(
                        text: original.label,
                        font: (compact ? Font.caption : Font.subheadline).weight(.semibold),
                        color: DS.textPrimary,
                        alignment: .leading
                    )
                    if selected { selectedTag }
                }
                sideReading(input.beforeReading(original), title: CombatMethodInput10868.preMatchShort, marked: false)
                if let current = input.currentReading(original) {
                    sideReading(current, title: CombatMethodInput10868.currentShort, marked: input.showsCurrentMark(original))
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
        .accessibilityLabel("\(method.label), \(original.label)")
        .accessibilityValue(input.accessibilitySideValue(original, in: method))
        .accessibilityHint(action == nil ? "" : "Selects this side’s comparison")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(CombatMethodAccessibilityID10868.side(method.id, original.id))
    }

    private func sideReading(_ reading: CombatMethodReading10868, title: String, marked: Bool) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            switch reading {
            case .value(let observation):
                Text(observation.text)
                    .font(.system(size: sideFigureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            case .missing(let text):
                CombatMethodWrappedText10868(text: text, font: .caption.weight(.semibold), color: DS.textSecondary, alignment: .leading)
            }
            HStack(spacing: 4) {
                if marked { keyMark(.filled) }
                Text(title).font(.caption2).foregroundStyle(DS.textSecondary)
            }
        }
    }

    // MARK: Selected method

    @ViewBuilder private var selectedPanel: some View {
        if let method = input.selection.method {
            VStack(alignment: .leading, spacing: 10) {
                Divider()
                CombatMethodWrappedText10868(
                    text: method.question,
                    font: .subheadline.weight(.semibold),
                    color: DS.textPrimary,
                    alignment: .leading
                )
                if let comparison = input.comparison {
                    comparisonFigures(comparison)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(input.accessibilityComparison ?? "")
                        .accessibilityIdentifier(CombatMethodAccessibilityID10868.comparison)
                }
                // None when the method's own tile already lists every side.
                let sides = input.panelSides(method, canSelect: canSelect)
                if !sides.isEmpty {
                    sideList(method, sides)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder private func comparisonFigures(_ comparison: CombatMethodComparison10868) -> some View {
        switch comparison {
        case .before(let original):
            comparisonValue(input.beforeReading(original), title: preMatchTitle(original), mark: nil, movement: nil)
        case .during(let original):
            CombatMethodPairLayout10868(spacing: 16, equalColumns: true, forceStack: typeSize.isAccessibilitySize) {
                comparisonValue(input.beforeReading(original), title: preMatchTitle(original), mark: .hollow, movement: nil)
                if let current = input.currentReading(original) {
                    comparisonValue(
                        current,
                        title: CombatMethodInput10868.currentTitle,
                        mark: input.showsCurrentMark(original) ? .filled : nil,
                        movement: input.movement(original)
                    )
                }
            }
        case .final(let original, let result):
            CombatMethodPairLayout10868(spacing: 16, equalColumns: true, forceStack: typeSize.isAccessibilitySize) {
                comparisonValue(input.beforeReading(original), title: preMatchTitle(original), mark: nil, movement: nil)
                VStack(alignment: .leading, spacing: 5) {
                    Text("\(CombatMethodInput10868.resultTitle) · \(original.label)")
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    resultLine(result, text: result.text, font: .title3.weight(.semibold))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private func preMatchTitle(_ original: CombatMethodOriginal10868) -> String {
        "\(CombatMethodInput10868.preMatchTitle) · \(original.label)"
    }

    /// One figure with its own visible provenance.
    private func comparisonValue(_ reading: CombatMethodReading10868, title: String, mark: KeyMark?, movement: String?) -> some View {
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

    // MARK: Official bout context

    @ViewBuilder private var actualContext: some View {
        if let actual = input.visibleActual {
            VStack(alignment: .leading, spacing: 4) {
                Text(actual.title)
                    .font(.caption.weight(.semibold))
                    .textCase(.uppercase)
                    .foregroundStyle(DS.textSecondary)
                ForEach(Array(actual.lines.enumerated()), id: \.offset) { _, line in
                    Text(line).font(.footnote).foregroundStyle(DS.textPrimary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityActual ?? "")
            .accessibilityIdentifier(CombatMethodAccessibilityID10868.actual)
        }
    }

    // MARK: Details and timing

    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails), let original = input.selection.original {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails)
            } label: {
                HStack {
                    Text("Original \(original.label) · \(CombatMethodInput10868.detailsTitle)")
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier(CombatMethodAccessibilityID10868.details(original.id))
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

    private func timingLines(_ content: CombatMethodTiming10868) -> some View {
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
    private func control<Content: View>(_ action: CombatMethodAction10868?, @ViewBuilder content: () -> Content) -> some View {
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
