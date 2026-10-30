import SwiftUI

// #10868 — two named subjects' own chances of reaching the same stat
// milestone, grouped on one chart. One stateless leaf, two approved
// orientations: horizontal chance bars (team sacks, 2+…6+) and paired vertical
// columns (team field goals, 1+…4+), on one fixed 0–100% scale. Before play
// each group shows both subjects' saved pregame chances as outlined marks.
// During play each subject also carries its own owner-admitted in-game chance,
// filled beside its outlined pregame mark, or the owner's words for its
// absence. After the final the pregame marks stay and the selected milestone
// sets each subject's pregame chance beside that subject's own contract
// result. The exact count is a separate slot and is never read off a result.
//
// Presentation only, extracted from the approved design
// (totals-final-forecast-binding-20261024 `TeamMilestonesStory`,
// `teamMilestones.css`), rebuilt on the #10868 player-contribution semantics
// (`PlayerContributionObservation10868`, `…Current10868`, `…Result10868`,
// `…Phase10868`) and its shared geometry and axis layouts.
//
// The two chances in a group belong to two separate contracts. They are never
// complements, never normalized and never summed, and one subject's reading,
// result or count is never derived from the other's. Every figure, target,
// tick, status, movement, count, result and spoken detail arrives resolved by
// the owner and is shown verbatim. This layer never formats, rounds, ranks,
// sorts, filters, blends or joins, never reads a clock, never elects a
// baseline, a default or a nearest milestone, never pairs records by name and
// never decides that two contracts measure the same milestone: the owner puts
// each subject's original into that subject's slot of one group. A slot with
// no original keeps the owner's words and is never filled from its sibling. A
// result is words, never a 0% or 100% mark. A missing reading draws no bar; a
// real 0% draws a visible zero mark; a stale or withheld in-game chance draws
// no filled bar. Marks are never connected.
//
// Outlined marks are the earlier (pregame) chances and filled marks the later
// admitted in-game chances; a visible key says so whenever marks are drawn.
// Each subject keeps one tint and one identity shape (circle, diamond) beside
// its name in the key, the readouts and the counts, and the same shape and
// tint key each subject's compact bar rows, so the pair is never told apart by
// colour alone and no dash style is used for identity. VoiceOver names each
// subject in full.
//
// Milestone selection, previous/next, Details and expansion stay with the
// host: the view keeps no selected state, no sheet, no focus, no scroll and no
// subscription, and hands back exact owner ids only. With no callback, content
// is shown without a button and no tap is asked for.
//
// Host binding still owed — not available at this base. An owner must supply,
// for one card: the two subject identities, names and details; the milestone
// groups in the owner's order with each subject's exact original contract id
// (or the owner's words for its absence) proven to be that subject's own
// same-stat, full-game contract; each original's admitted pregame observation
// or words; during play an independently admitted in-game observation with
// currentness applied, or its words; each subject's clocked count so far and
// final count, each in its own owner-tagged channel, or words for their
// absence, independently of any grade; each original's
// independently admitted result; the selected group id, tick labels, card id
// and copy.

/// Which of the two subjects, in the owner's order.
nonisolated enum PairedMilestoneSide10868: CaseIterable, Hashable {
    case first
    case second
}

/// One of the two compared subjects ("Bears").
nonisolated struct PairedMilestoneSubject10868: Equatable {
    /// Opaque subject identity.
    let id: String
    let name: String
    /// "Chicago"; nil draws nothing.
    let detail: String?
    /// The count the owner resolved as this subject's count so far. Read only
    /// during play. A final count never goes here.
    let countSoFar: PlayerContributionActual10868?
    /// The count the owner resolved as this subject's final count. Read only
    /// after the final. A count so far never goes here.
    let finalCount: PlayerContributionActual10868?
    /// The owner's words when the phase's own channel is empty ("Count
    /// unavailable"). The other channel never stands in, and this layer never
    /// decides which kind a count is from a clock, unit, words, grade or game
    /// status. Neither channel is ever derived from any result.
    let countMissing: String
}

/// One subject's own contract at one milestone.
nonisolated struct PairedMilestoneOriginal10868: Equatable {
    /// Opaque original contract identity, passed back exactly.
    let id: String
    /// The whole milestone for this subject ("Bears 2+ sacks").
    let title: String
    let before: PlayerContributionObservation10868?
    /// The owner's words for a missing pregame chance ("Unavailable").
    let beforeMissing: String
    /// Read only during play.
    let current: PlayerContributionCurrent10868
    /// Read only after the final.
    let result: PlayerContributionResult10868
}

/// A subject's slot in a group: its own original, or the owner's words.
nonisolated enum PairedMilestoneEntry10868: Equatable {
    case original(PairedMilestoneOriginal10868)
    /// "No original for this milestone". Never synthesized from the sibling.
    case missing(String)

    var original: PairedMilestoneOriginal10868? {
        if case .original(let original) = self { return original }
        return nil
    }
}

/// One milestone, with each subject's own original in that subject's slot.
nonisolated struct PairedMilestoneGroup10868: Equatable {
    /// Opaque group identity, passed back exactly.
    let id: String
    /// The short axis label ("2+").
    let target: String
    /// The full milestone ("2+ sacks").
    let title: String
    let first: PairedMilestoneEntry10868
    let second: PairedMilestoneEntry10868

    func entry(_ side: PairedMilestoneSide10868) -> PairedMilestoneEntry10868 {
        side == .first ? first : second
    }
}

nonisolated enum PairedMilestoneSelection10868: Equatable {
    case none
    case selected(PairedMilestoneGroup10868)
    /// No group carries the selected id — including a withdrawn group.
    case missing(String)
    /// More than one group carries the selected id.
    case duplicate(String)

    var group: PairedMilestoneGroup10868? {
        if case .selected(let group) = self { return group }
        return nil
    }
}

/// One subject's readings at the selected milestone, phase applied.
nonisolated struct PairedMilestoneSideReading10868: Equatable {
    let side: PairedMilestoneSide10868
    let subject: PairedMilestoneSubject10868
    /// Nil when the subject has no original here.
    let originalID: String?
    /// The pregame chance or its words, every phase. Nil with no original.
    let pregame: PlayerDuelChanceDisplay10868?
    /// During play only.
    let current: PlayerContributionCurrentReading10868?
    /// During play, beside a recorded chance only.
    let movement: String?
    /// After the final only.
    let result: PlayerContributionResult10868?
    /// The owner's words when the subject has no original here; every
    /// reading above is then nil.
    let missing: String?
}

/// One row of a subject in a compact bar group: a mark with its direct value,
/// or a reading without a mark in the owner's words.
nonisolated enum PairedMilestoneSlot10868: Equatable {
    /// Outlined pregame or filled in-game. A nil fraction keeps the value's
    /// text and draws no bar.
    case mark(PlayerContributionObservation10868, fraction: Double?, filled: Bool)
    case status(PlayerContributionRowStatus10868)
}

/// How the bar groups are drawn: compact aligned rows, or stacked when those
/// do not fit the width.
nonisolated enum PairedMilestoneBarForm10868: Hashable {
    case compact
    case stacked
}

/// What one subject draws in one group of the chart.
nonisolated struct PairedMilestoneLane10868: Equatable {
    let side: PairedMilestoneSide10868
    let name: String
    /// The outlined pregame mark's direct value.
    let pregame: PlayerContributionObservation10868?
    let beforeFraction: Double?
    /// The filled in-game mark's direct value: during play, recorded only.
    let current: PlayerContributionObservation10868?
    let currentFraction: Double?
    /// During play the in-game lane exists even when it holds no mark.
    let hasCurrentLane: Bool
    /// Each reading without a mark, in the owner's words.
    let statuses: [PlayerContributionRowStatus10868]
}

nonisolated enum PairedMilestoneAction10868: Equatable {
    /// An exact group id — a group tap, or the neighbour for previous/next.
    case select(String)
    /// An exact original id.
    case details(String)
    /// The exact card id.
    case expand(String)

    func perform(onSelect: ((String) -> Void)?, onDetails: ((String) -> Void)?, onExpand: ((String) -> Void)?) {
        switch self {
        case .select(let id): onSelect?(id)
        case .details(let id): onDetails?(id)
        case .expand(let id): onExpand?(id)
        }
    }
}

nonisolated struct PairedMilestoneInput10868: Equatable {
    let phase: PlayerContributionPhase10868
    /// Field goals keep vertical columns; sacks horizontal bars.
    let orientation: PlayerContributionOrientation10868
    /// Opaque card identity for the host's expand; nil or empty offers none.
    let cardID: String?
    /// "TEAM MILESTONES".
    let eyebrow: String?
    /// "Quarterback pressure".
    let title: String
    /// "Each team’s chance belongs to its own contract. The two do not add to 100%."
    let definition: String?
    let first: PairedMilestoneSubject10868
    let second: PairedMilestoneSubject10868
    /// In the owner's order.
    let groups: [PairedMilestoneGroup10868]
    /// The owner's exact group selection.
    let selectedGroupID: String?
    /// "Pregame chances · at least this many sacks".
    let chartTitle: String?
    /// The owner's labelled ticks on the fixed 0...1 probability scale.
    let ticks: [PlayerContributionTick10868]

    static let pairUnavailable = "Paired subjects unresolved."
    static let previousTitle = "Previous milestone"
    static let nextTitle = "Next milestone"
    static let expandTitle = "Open card"
    static let outlinedKey = "Outlined · " + PlayerContributionInput10868.pregameTitle
    static let filledKey = "Filled · " + PlayerContributionInput10868.recordedTitle

    func subject(_ side: PairedMilestoneSide10868) -> PairedMilestoneSubject10868 {
        side == .first ? first : second
    }

    // MARK: Identity and selection

    /// Two subjects, each with its own identity.
    var isPairResolved: Bool {
        !first.id.isEmpty && !second.id.isEmpty && first.id != second.id
    }

    var pairNotice: String? {
        isPairResolved ? nil : Self.pairUnavailable
    }

    private func isUniqueGroup(_ id: String) -> Bool {
        !id.isEmpty && groups.filter { $0.id == id }.count == 1
    }

    /// An original id names exactly one slot on the card.
    private func isUniqueOriginal(_ id: String) -> Bool {
        guard !id.isEmpty else { return false }
        let slots = groups.flatMap { [$0.first.original, $0.second.original] }.compactMap { $0 }
        return slots.filter { $0.id == id }.count == 1
    }

    /// Exact id only. A missing, withdrawn or duplicated id gets no substitute
    /// and no neighbour.
    var selection: PairedMilestoneSelection10868 {
        guard let selectedGroupID else { return .none }
        let matches = groups.filter { $0.id == selectedGroupID }
        switch matches.count {
        case 0: return .missing(selectedGroupID)
        case 1: return .selected(matches[0])
        default: return .duplicate(selectedGroupID)
        }
    }

    func isSelected(_ group: PairedMilestoneGroup10868) -> Bool {
        guard let selected = selection.group else { return false }
        return selected.id == group.id
    }

    var selectionNotice: String? {
        switch selection {
        case .missing, .duplicate: return PlayerContributionInput10868.milestoneUnavailable
        case .none, .selected: return nil
        }
    }

    // MARK: Phase visibility

    /// The selected milestone's readings for one subject.
    func reading(_ group: PairedMilestoneGroup10868, side: PairedMilestoneSide10868) -> PairedMilestoneSideReading10868 {
        let subject = subject(side)
        switch group.entry(side) {
        case .missing(let words):
            return PairedMilestoneSideReading10868(side: side, subject: subject, originalID: nil, pregame: nil,
                                                   current: nil, movement: nil, result: nil, missing: words)
        case .original(let original):
            return PairedMilestoneSideReading10868(
                side: side,
                subject: subject,
                originalID: original.id,
                pregame: PlayerDuelInput10868.display(Self.beforeReading(original)),
                current: currentReading(original),
                movement: movement(original),
                result: phase == .final ? original.result : nil,
                missing: nil
            )
        }
    }

    static func beforeReading(_ original: PairedMilestoneOriginal10868) -> PlayerContributionReading10868 {
        original.before.map { .value($0) } ?? .missing(original.beforeMissing)
    }

    /// The in-game slot, during play only. A reached milestone stays
    /// performance ("Actual so far"), never a chance.
    func currentReading(_ original: PairedMilestoneOriginal10868) -> PlayerContributionCurrentReading10868? {
        guard phase == .during else { return nil }
        switch original.current {
        case .recorded(let observation, _): return .chance(observation)
        case .unavailable(let text), .withheld(let text): return .chanceStatus(text)
        case .reached(let text): return .actual(text)
        }
    }

    func movement(_ original: PairedMilestoneOriginal10868) -> String? {
        guard phase == .during, case .recorded(_, let movement) = original.current else { return nil }
        return movement
    }

    /// What one subject draws in one group, selected or not, in either form.
    func lane(_ group: PairedMilestoneGroup10868, side: PairedMilestoneSide10868) -> PairedMilestoneLane10868 {
        let name = subject(side).name
        let original: PairedMilestoneOriginal10868
        switch group.entry(side) {
        case .missing(let words):
            return PairedMilestoneLane10868(side: side, name: name, pregame: nil, beforeFraction: nil, current: nil,
                                            currentFraction: nil, hasCurrentLane: false,
                                            statuses: [PlayerContributionRowStatus10868(title: nil, words: words)])
        case .original(let own):
            original = own
        }
        let current = currentReading(original)
        var statuses: [PlayerContributionRowStatus10868] = []
        if original.before == nil {
            statuses.append(PlayerContributionRowStatus10868(
                title: current == nil ? nil : PlayerContributionInput10868.pregameTitle,
                words: original.beforeMissing))
        }
        var recorded: PlayerContributionObservation10868?
        switch current {
        case .chance(let observation)?:
            recorded = observation
        case .chanceStatus(let text)?, .actual(let text)?:
            statuses.append(PlayerContributionRowStatus10868(title: current?.title, words: text))
        case nil:
            break
        }
        return PairedMilestoneLane10868(
            side: side,
            name: name,
            pregame: original.before,
            beforeFraction: original.before.flatMap { PlayerContributionGeometry10868.fraction($0.probability) },
            current: recorded,
            currentFraction: recorded.flatMap { PlayerContributionGeometry10868.fraction($0.probability) },
            hasCurrentLane: current != nil,
            statuses: statuses
        )
    }

    /// The count block for one subject: none before play; during play only
    /// the owner's count so far; after the final only the owner's final count.
    /// An empty channel shows the owner's words — a count of the other kind
    /// never fills it. Its own slot, whatever the results say.
    func actualPresentation(_ side: PairedMilestoneSide10868) -> PlayerContributionActualPresentation10868? {
        let subject = subject(side)
        switch phase {
        case .before: return nil
        case .during: return PlayerContributionActualPresentation10868(title: PlayerContributionInput10868.countSoFarTitle,
                                                                       actual: subject.countSoFar ?? .unavailable(subject.countMissing))
        case .final: return PlayerContributionActualPresentation10868(title: PlayerContributionInput10868.finalCountTitle,
                                                                      actual: subject.finalCount ?? .unavailable(subject.countMissing))
        }
    }

    /// One shared line when both subjects' counts for this phase are the same
    /// owner words for an absence. Nil when either carries a count or the two
    /// reasons differ, so each keeps its own slot.
    var sharedActualAbsence: PlayerContributionRowStatus10868? {
        guard let first = actualPresentation(.first), first == actualPresentation(.second),
              case .unavailable(let words) = first.actual else { return nil }
        return PlayerContributionRowStatus10868(title: first.title, words: words)
    }

    /// One subject's rows in a compact bar group: the pregame mark or its
    /// words, then during play the in-game mark or its words. A subject with
    /// no original has one row of the owner's words.
    func slots(_ group: PairedMilestoneGroup10868, side: PairedMilestoneSide10868) -> [PairedMilestoneSlot10868] {
        let original: PairedMilestoneOriginal10868
        switch group.entry(side) {
        case .missing(let words): return [.status(PlayerContributionRowStatus10868(title: nil, words: words))]
        case .original(let own): original = own
        }
        let current = currentReading(original)
        var slots: [PairedMilestoneSlot10868] = []
        if let before = original.before {
            slots.append(.mark(before, fraction: PlayerContributionGeometry10868.fraction(before.probability), filled: false))
        } else {
            slots.append(.status(PlayerContributionRowStatus10868(
                title: current == nil ? nil : PlayerContributionInput10868.pregameTitle, words: original.beforeMissing)))
        }
        switch current {
        case .chance(let observation)?:
            slots.append(.mark(observation, fraction: PlayerContributionGeometry10868.fraction(observation.probability), filled: true))
        case .chanceStatus(let text)?, .actual(let text)?:
            slots.append(.status(PlayerContributionRowStatus10868(title: current?.title, words: text)))
        case nil:
            break
        }
        return slots
    }

    // MARK: Key

    /// The outlined key whenever any pregame mark is drawn.
    var showsOutlinedKey: Bool {
        groups.contains { group in
            PairedMilestoneSide10868.allCases.contains { lane(group, side: $0).beforeFraction != nil }
        }
    }

    /// The filled key only when an in-game mark is actually drawn.
    var showsFilledKey: Bool {
        groups.contains { group in
            PairedMilestoneSide10868.allCases.contains { lane(group, side: $0).currentFraction != nil }
        }
    }

    // MARK: Layout

    /// The selected readouts and the counts: side by side when they fit,
    /// otherwise stacked. Accessibility sizes always stack.
    func readoutLayouts(isAccessibilitySize: Bool) -> [PlayerDuelLayout10868] {
        isAccessibilitySize ? [.stacked] : [.paired, .stacked]
    }

    /// The chart forms to try, in order. Columns fall back to bars, every
    /// group kept, when they do not fit; accessibility sizes use bars.
    func chartForms(isAccessibilitySize: Bool) -> [PlayerContributionChartForm10868] {
        isAccessibilitySize ? [.bars] : orientation.forms
    }

    /// Compact aligned rows first, stacked when they do not fit the width;
    /// accessibility sizes stack. Every group and value is kept either way.
    func barForms(isAccessibilitySize: Bool) -> [PairedMilestoneBarForm10868] {
        isAccessibilitySize ? [.stacked] : [.compact, .stacked]
    }

    // MARK: Actions

    func groupAction(_ group: PairedMilestoneGroup10868, canSelect: Bool) -> PairedMilestoneAction10868? {
        canSelect && isUniqueGroup(group.id) ? .select(group.id) : nil
    }

    /// The neighbour in the owner's order, only from a resolved selection.
    func stepAction(_ offset: Int, canSelect: Bool) -> PairedMilestoneAction10868? {
        guard canSelect, let selected = selection.group,
              let index = groups.firstIndex(where: { $0.id == selected.id }) else { return nil }
        let target = index + offset
        guard offset != 0, groups.indices.contains(target), isUniqueGroup(groups[target].id) else { return nil }
        return .select(groups[target].id)
    }

    /// Details for one subject's original in the selected group only.
    func detailsAction(_ side: PairedMilestoneSide10868, canOpenDetails: Bool) -> PairedMilestoneAction10868? {
        guard canOpenDetails, isPairResolved, let group = selection.group,
              let original = group.entry(side).original, isUniqueOriginal(original.id) else { return nil }
        return .details(original.id)
    }

    func expandAction(canExpand: Bool) -> PairedMilestoneAction10868? {
        guard canExpand, let cardID, !cardID.isEmpty else { return nil }
        return .expand(cardID)
    }

    // MARK: VoiceOver

    var accessibilityHeader: String {
        ([eyebrow, title].compactMap { $0 }).joined(separator: ". ")
    }

    func accessibilitySubject(_ side: PairedMilestoneSide10868) -> String {
        let subject = subject(side)
        return ([subject.name, subject.detail].compactMap { $0 }).joined(separator: ", ")
    }

    /// A chart group: each subject's pregame chance and, during play, its
    /// in-game chance, status or "Actual so far".
    func accessibilityValue(for group: PairedMilestoneGroup10868) -> String {
        PairedMilestoneSide10868.allCases.map { side in
            let name = subject(side).name
            let original: PairedMilestoneOriginal10868
            switch group.entry(side) {
            case .missing(let words): return "\(name): \(words)"
            case .original(let own): original = own
            }
            var parts = [Self.spoken(Self.beforeReading(original), title: PlayerContributionInput10868.spokenPregame)]
            if let current = currentReading(original) {
                parts.append(Self.spoken(current.reading, title: current.spokenTitle))
            }
            return "\(name): " + parts.joined(separator: "; ")
        }
        .joined(separator: ". ")
    }

    /// One subject's selected readout: its pregame chance, then its in-game
    /// reading (and movement) or its own result.
    func accessibilityReading(_ reading: PairedMilestoneSideReading10868) -> String {
        if let missing = reading.missing { return missing }
        var parts: [String] = []
        if let pregame = reading.pregame {
            switch pregame {
            case .figure(let observation):
                parts.append("\(PlayerContributionInput10868.spokenPregame): \(observation.text), \(observation.accessibilityDetail)")
            case .words(let text):
                parts.append("\(PlayerContributionInput10868.spokenPregame): \(text)")
            }
        }
        if let current = reading.current {
            parts.append(Self.spoken(current.reading, title: current.spokenTitle))
        }
        if let movement = reading.movement {
            parts.append("\(PlayerContributionInput10868.spokenMovement): \(movement)")
        }
        if let result = reading.result {
            parts.append("\(PlayerContributionInput10868.spokenResult): \(result.text)")
        }
        return parts.joined(separator: "; ")
    }

    /// The shared count line names both subjects.
    var accessibilityBothSubjects: String {
        "\(first.name) and \(second.name)"
    }

    func accessibilityActual(_ presentation: PlayerContributionActualPresentation10868) -> String {
        switch presentation.actual {
        case .count(let count):
            var figure = count.count
            if let unit = count.unit { figure += " \(unit)" }
            var parts = [figure]
            if let breakdown = count.breakdown { parts.append(breakdown) }
            parts.append(count.accessibilityDetail)
            return parts.joined(separator: ", ")
        case .unavailable(let text):
            return text
        }
    }

    private static func spoken(_ reading: PlayerContributionReading10868, title: String) -> String {
        switch reading {
        case .value(let observation): "\(title): \(observation.text), \(observation.accessibilityDetail)"
        case .missing(let text): "\(title): \(text)"
        }
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum PairedMilestoneAccessibilityID10868 {
    static func group(_ id: String) -> String { "pairedMilestone10868.group.\(id)" }
    static func original(_ id: String) -> String { "pairedMilestone10868.original.\(id)" }
    static func actual(_ subjectID: String) -> String { "pairedMilestone10868.actual.\(subjectID)" }
    static let sharedActual = "pairedMilestone10868.actual.shared"
    static func expand(_ cardID: String) -> String { "pairedMilestone10868.expand.\(cardID)" }
    static let previous = "pairedMilestone10868.previous"
    static let next = "pairedMilestone10868.next"
}

struct PairedMilestonePresentation10868: View {
    let input: PairedMilestoneInput10868
    var onSelect: ((String) -> Void)? = nil
    var onDetails: ((String) -> Void)? = nil
    var onExpand: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 26
    @ScaledMetric(relativeTo: .title3) private var resultSize: CGFloat = 20
    @ScaledMetric(relativeTo: .title) private var countSize: CGFloat = 28
    @ScaledMetric(relativeTo: .body) private var plotHeight: CGFloat = 150
    @ScaledMetric(relativeTo: .body) private var columnWidth: CGFloat = 14
    @ScaledMetric(relativeTo: .body) private var laneHeight: CGFloat = 12
    @ScaledMetric(relativeTo: .body) private var glyphSize: CGFloat = 9
    @ScaledMetric(relativeTo: .subheadline) private var trackRowHeight: CGFloat = 20
    @ScaledMetric(relativeTo: .body) private var minTrackWidth: CGFloat = 120

    private let labelGap: CGFloat = 4
    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }
    private var canExpand: Bool { onExpand != nil }

    /// Each subject keeps one tint on every mark and name.
    private func tint(_ side: PairedMilestoneSide10868) -> Color { side == .first ? DS.blue : DS.purple }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            if let definition = input.definition {
                Text(definition)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(Array([input.pairNotice, input.selectionNotice].compactMap { $0 }.enumerated()), id: \.offset) { _, notice in
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let group = input.selection.group {
                comparison(group)
            }
            if input.phase != .before {
                counts
            }
            if !input.groups.isEmpty {
                chart
            }
            stepper
            expandButton
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let eyebrow = input.eyebrow {
                Text(eyebrow).font(.caption2).foregroundStyle(DS.textSecondary)
            }
            Text(input.title).font(.title2.bold()).foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader)
        .accessibilityAddTraits(.isHeader)
    }

    // MARK: Identity

    /// The noncolour identity cue: a circle for the first subject, a diamond for the second.
    @ViewBuilder private func glyph(_ side: PairedMilestoneSide10868) -> some View {
        switch side {
        case .first:
            Circle().fill(tint(side)).frame(width: glyphSize, height: glyphSize)
        case .second:
            Rectangle().fill(tint(side))
                .frame(width: glyphSize * 0.75, height: glyphSize * 0.75)
                .rotationEffect(.degrees(45))
                .frame(width: glyphSize, height: glyphSize)
        }
    }

    private func nameLine(_ side: PairedMilestoneSide10868, font: Font) -> some View {
        HStack(spacing: 6) {
            glyph(side).accessibilityHidden(true)
            Text(input.subject(side).name).font(font).foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: Paired readouts

    /// Two equal panels side by side while each whole name and figure fits,
    /// otherwise one above the other — never squeezed, truncated or scrolled.
    private func paired<Content: View>(@ViewBuilder _ content: @escaping (PairedMilestoneSide10868) -> Content) -> some View {
        ViewThatFits(in: .horizontal) {
            ForEach(input.readoutLayouts(isAccessibilitySize: typeSize.isAccessibilitySize), id: \.self) { layout in
                switch layout {
                case .paired:
                    HStack(alignment: .top, spacing: 10) {
                        ForEach(PairedMilestoneSide10868.allCases, id: \.self) { side in content(side) }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                case .stacked:
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(PairedMilestoneSide10868.allCases, id: \.self) { side in content(side) }
                    }
                }
            }
        }
    }

    // MARK: Selected comparison

    private func comparison(_ group: PairedMilestoneGroup10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(group.title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            paired { side in
                readoutPanel(input.reading(group, side: side))
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
    }

    private func readoutPanel(_ reading: PairedMilestoneSideReading10868) -> some View {
        let action = input.detailsAction(reading.side, canOpenDetails: canOpenDetails)
        return control(action) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    nameLine(reading.side, font: .headline)
                    Spacer(minLength: 0)
                    if action != nil {
                        Image(systemName: "chevron.right")
                            .font(.footnote)
                            .foregroundStyle(DS.blue)
                            .accessibilityHidden(true)
                    }
                }
                if let missing = reading.missing {
                    Text(missing).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let pregame = reading.pregame {
                    chanceValue(pregame, title: PlayerContributionInput10868.pregameTitle,
                                mark: input.phase == .during ? .outlined : nil, side: reading.side)
                }
                if let current = reading.current {
                    let display = current.reading.duelDisplay
                    chanceValue(display, title: current.title, mark: current.isChance && display.isFigure ? .filled : nil,
                                side: reading.side)
                }
                if let movement = reading.movement {
                    Text(movement)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let result = reading.result {
                    resultValue(result)
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .topLeading)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 10))
            .overlay(alignment: .leading) {
                Rectangle().fill(tint(reading.side)).frame(width: 3)
            }
            .contentShape(Rectangle())
        }
        .accessibilityLabel(input.accessibilitySubject(reading.side))
        .accessibilityValue(input.accessibilityReading(reading))
        .accessibilityHint(action == nil ? "" : PlayerContributionInput10868.detailsTitle)
        .accessibilityIdentifier(PairedMilestoneAccessibilityID10868.original(reading.originalID ?? input.subject(reading.side).id))
    }

    private enum KeyMark { case outlined, filled }

    /// A figure at full reading size, or the owner's words. Before and in-game
    /// readings share one size so neither is a footnote.
    private func chanceValue(_ display: PlayerDuelChanceDisplay10868, title: String, mark: KeyMark?,
                             side: PairedMilestoneSide10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 5) {
                if let mark { keyMark(mark, color: tint(side)) }
                Text(title).font(.caption).foregroundStyle(DS.textSecondary)
            }
            switch display {
            case .figure(let observation):
                Text(observation.text)
                    .font(.system(size: chanceSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: true, vertical: false)
            case .words(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// The owner's result words — never a 0% or 100%. Unconfirmed reads as status.
    private func resultValue(_ result: PlayerContributionResult10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(PlayerContributionInput10868.resultTitle).font(.caption).foregroundStyle(DS.textSecondary)
            if result.isAdmitted {
                Text(result.text).font(.system(size: resultSize, weight: .bold)).foregroundStyle(DS.textPrimary)
            } else {
                Text(result.text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private func keyMark(_ mark: KeyMark, color: Color) -> some View {
        switch mark {
        case .outlined:
            RoundedRectangle(cornerRadius: 2).fill(DS.cardBg)
                .overlay(RoundedRectangle(cornerRadius: 2).strokeBorder(color, lineWidth: 1.5))
                .frame(width: 10, height: 10)
        case .filled:
            RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 10, height: 10)
        }
    }

    // MARK: Counts

    /// Each subject's count in its own slot, apart from every chance and
    /// result — or one line when both are the same owner words for an absence.
    @ViewBuilder private var counts: some View {
        if let shared = input.sharedActualAbsence {
            sharedCountLine(shared)
        } else {
            paired { side in
                if let presentation = input.actualPresentation(side) {
                    countBlock(presentation, side: side)
                }
            }
        }
    }

    /// Both subjects' shapes, the phase's count title and the owner's words.
    /// Never a count and never a 0.
    private func sharedCountLine(_ status: PlayerContributionRowStatus10868) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            HStack(spacing: 3) {
                ForEach(PairedMilestoneSide10868.allCases, id: \.self) { side in glyph(side) }
            }
            .accessibilityHidden(true)
            statusText(status)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(input.accessibilityBothSubjects), \(status.title ?? "")")
        .accessibilityValue(status.words)
        .accessibilityIdentifier(PairedMilestoneAccessibilityID10868.sharedActual)
    }

    private func countBlock(_ presentation: PlayerContributionActualPresentation10868, side: PairedMilestoneSide10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            nameLine(side, font: .subheadline.weight(.semibold))
            Text(presentation.title).font(.caption).foregroundStyle(DS.textSecondary)
            switch presentation.actual {
            case .count(let count):
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(count.count)
                        .font(.system(size: countSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                    if let unit = count.unit {
                        Text(unit).font(.subheadline).foregroundStyle(DS.textSecondary)
                    }
                }
                if let breakdown = count.breakdown {
                    Text(breakdown).font(.footnote).foregroundStyle(DS.textSecondary)
                }
            case .unavailable(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.leading, 12)
        .overlay(alignment: .leading) { Rectangle().fill(DS.border).frame(width: 1) }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(input.accessibilitySubject(side)), \(presentation.title)")
        .accessibilityValue(input.accessibilityActual(presentation))
        .accessibilityIdentifier(PairedMilestoneAccessibilityID10868.actual(input.subject(side).id))
    }

    // MARK: Chart

    private var chart: some View {
        let ticks = PlayerContributionGeometry10868.visibleTicks(input.ticks)
        return VStack(alignment: .leading, spacing: 8) {
            Divider()
            if let chartTitle = input.chartTitle {
                Text(chartTitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            chartKey
            ViewThatFits(in: .horizontal) {
                ForEach(input.chartForms(isAccessibilitySize: typeSize.isAccessibilitySize), id: \.self) { form in
                    switch form {
                    case .columns: columnsChart(ticks)
                    case .bars: barsChart(ticks)
                    }
                }
            }
        }
    }

    /// Who is who (tint plus shape plus name), and what outlined and filled mean.
    private var chartKey: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 14) {
                ForEach(PairedMilestoneSide10868.allCases, id: \.self) { side in
                    nameLine(side, font: .caption.weight(.semibold))
                }
            }
            if input.showsOutlinedKey || input.showsFilledKey {
                HStack(spacing: 14) {
                    if input.showsOutlinedKey {
                        HStack(spacing: 5) {
                            keyMark(.outlined, color: DS.textSecondary)
                            Text(PairedMilestoneInput10868.outlinedKey)
                        }
                    }
                    if input.showsFilledKey {
                        HStack(spacing: 5) {
                            keyMark(.filled, color: DS.textSecondary)
                            Text(PairedMilestoneInput10868.filledKey)
                        }
                    }
                }
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityHidden(true)
    }

    // MARK: Columns (field goals)

    private func columnsChart(_ ticks: [PlayerContributionPlacedTick10868]) -> some View {
        let fractions = ticks.map(\.fraction)
        return HStack(alignment: .top, spacing: 0) {
            if !ticks.isEmpty {
                VStack(alignment: .trailing, spacing: labelGap) {
                    Text("0%").font(.caption2.bold()).fixedSize().frame(width: 0).hidden()
                    PlayerContributionAxisLabelsLayout10868(fractions: fractions, axis: .vertical, plotHeight: plotHeight) {
                        ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                            Text(tick.text)
                                .font(.caption2)
                                .monospacedDigit()
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize()
                        }
                    }
                }
                .padding(.trailing, 6)
                .accessibilityHidden(true)
            }
            ForEach(Array(input.groups.enumerated()), id: \.offset) { _, group in
                columnGroup(group, gridlines: fractions)
            }
        }
    }

    private func columnGroup(_ group: PairedMilestoneGroup10868, gridlines: [Double]) -> some View {
        let selected = input.isSelected(group)
        let action = input.groupAction(group, canSelect: canSelect)
        let lanes = PairedMilestoneSide10868.allCases.map { input.lane(group, side: $0) }
        return control(action) {
            VStack(spacing: 6) {
                HStack(alignment: .bottom, spacing: 6) {
                    ForEach(lanes, id: \.side) { lane in
                        VStack(spacing: 3) {
                            HStack(alignment: .bottom, spacing: 2) {
                                columnBar(lane.pregame, fraction: lane.beforeFraction, filled: false,
                                          selected: selected, side: lane.side)
                                if lane.hasCurrentLane {
                                    columnBar(lane.current, fraction: lane.currentFraction, filled: true,
                                              selected: selected, side: lane.side)
                                }
                            }
                            glyph(lane.side).accessibilityHidden(true)
                        }
                    }
                }
                .padding(.horizontal, 4)
                .frame(maxWidth: .infinity)
                // Each subject's shape sits under its bars at exactly `glyphSize`,
                // so the plot's baseline is that far above the stack's bottom.
                .background(alignment: .bottom) {
                    columnGridlines(gridlines).frame(height: plotHeight).padding(.bottom, glyphSize + 3)
                }
                VStack(spacing: 2) {
                    Text(group.target)
                        .font(.footnote.weight(selected ? .semibold : .regular))
                        .underline(selected)
                        .foregroundStyle(DS.textPrimary)
                    ForEach(lanes, id: \.side) { lane in
                        columnStatuses(lane)
                    }
                }
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 4)
            }
            .padding(.bottom, 4)
            .frame(minWidth: 44, maxWidth: .infinity, minHeight: 44)
            .background(selected ? DS.textPrimary.opacity(0.05) : Color.clear, in: RoundedRectangle(cornerRadius: 6))
            .overlay(alignment: .bottom) {
                if selected { Rectangle().fill(DS.textPrimary).frame(height: 3) }
            }
            .contentShape(Rectangle())
        }
        .accessibilityLabel(group.title)
        .accessibilityValue(input.accessibilityValue(for: group))
        .accessibilityHint(action == nil ? "" : "Selects this milestone’s comparison")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(PairedMilestoneAccessibilityID10868.group(group.id))
    }

    /// Each subject's own readings without a mark under its columns: its shape,
    /// then the label when the phase needs one and the owner's words, centred
    /// and wrapping. Never truncated, shrunk or drawn as a 0% column.
    private func columnStatuses(_ lane: PairedMilestoneLane10868) -> some View {
        ForEach(Array(lane.statuses.enumerated()), id: \.offset) { _, status in
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                glyph(lane.side).accessibilityHidden(true)
                statusText(status)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
            }
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func columnBar(_ observation: PlayerContributionObservation10868?, fraction: Double?, filled: Bool,
                           selected: Bool, side: PairedMilestoneSide10868) -> some View {
        PlayerContributionColumnBarLayout10868(fraction: fraction, plotHeight: plotHeight, barWidth: columnWidth, gap: labelGap) {
            if let observation {
                Text(observation.text).font(.caption2.bold()).monospacedDigit().foregroundStyle(DS.textPrimary).fixedSize()
            } else {
                Text("0%").font(.caption2.bold()).fixedSize().hidden()
            }
            if fraction != nil {
                barShape(filled: filled, selected: selected, side: side)
            } else {
                Color.clear
            }
        }
    }

    private func columnGridlines(_ fractions: [Double]) -> some View {
        GeometryReader { geo in
            Path { path in
                for fraction in fractions {
                    guard let y = PlayerContributionGeometry10868.y(fraction, height: geo.size.height) else { continue }
                    path.move(to: CGPoint(x: 0, y: y))
                    path.addLine(to: CGPoint(x: geo.size.width, y: y))
                }
            }
            .stroke(DS.border, style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
        }
        .accessibilityHidden(true)
    }

    // MARK: Bars (sacks, and the columns fallback)

    /// One compact group per milestone: each subject's rows keyed by its shape
    /// and tint (names live in the key and the readouts), on one shared track
    /// column and axis, with its direct values beside its bars. Stacks, every
    /// group and value kept, when the aligned rows do not fit.
    private func barsChart(_ ticks: [PlayerContributionPlacedTick10868]) -> some View {
        let gridlines = ticks.map(\.fraction)
        return ViewThatFits(in: .horizontal) {
            ForEach(input.barForms(isAccessibilitySize: typeSize.isAccessibilitySize), id: \.self) { form in
                switch form {
                case .compact: compactBars(ticks, gridlines: gridlines)
                case .stacked: stackedBars(ticks, gridlines: gridlines)
                }
            }
        }
    }

    private func axisLabels(_ ticks: [PlayerContributionPlacedTick10868]) -> some View {
        PlayerContributionAxisLabelsLayout10868(fractions: ticks.map(\.fraction), axis: .horizontal,
                                                inset: PlayerContributionGeometry10868.selectedLineWidth) {
            ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                Text(tick.text)
                    .font(.caption2)
                    .monospacedDigit()
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityHidden(true)
    }

    private func targetLabel(_ target: String, selected: Bool) -> some View {
        Text(target)
            .font(.subheadline.weight(selected ? .semibold : .regular))
            .underline(selected)
            .foregroundStyle(DS.textPrimary)
            .fixedSize(horizontal: false, vertical: true)
    }

    // Compact: three columns every row shares — target and shape, the track,
    // the direct values. Hidden reserves of every target and every value on the
    // card give each row the same lead and value widths, so every track, its
    // gridlines and the axis above start and end at the same x.

    private func compactBars(_ ticks: [PlayerContributionPlacedTick10868], gridlines: [Double]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if !ticks.isEmpty {
                compactColumns {
                    compactLead(nil, selected: false, side: nil)
                } track: {
                    axisLabels(ticks)
                } value: {
                    valueReserve
                }
                .padding(.horizontal, 8)
            }
            ForEach(Array(input.groups.enumerated()), id: \.offset) { _, group in
                compactGroup(group, gridlines: gridlines)
            }
        }
    }

    private func compactColumns<Lead: View, Track: View, Value: View>(
        @ViewBuilder lead: () -> Lead, @ViewBuilder track: () -> Track, @ViewBuilder value: () -> Value
    ) -> some View {
        HStack(alignment: .center, spacing: 8) {
            lead()
            track()
                .frame(minWidth: minTrackWidth, idealWidth: minTrackWidth, maxWidth: .infinity, alignment: .leading)
            value()
        }
    }

    /// The group's target on its first row only, then the subject's shape on
    /// the subject's first row only.
    private func compactLead(_ target: String?, selected: Bool, side: PairedMilestoneSide10868?) -> some View {
        HStack(spacing: 6) {
            ZStack(alignment: .leading) {
                ZStack(alignment: .leading) {
                    ForEach(Array(input.groups.enumerated()), id: \.offset) { _, group in
                        Text(group.target).font(.subheadline.weight(.semibold)).fixedSize()
                    }
                }
                .hidden()
                if let target { targetLabel(target, selected: selected) }
            }
            if let side {
                glyph(side).accessibilityHidden(true)
            } else {
                Color.clear.frame(width: glyphSize, height: glyphSize)
            }
        }
    }

    /// Every direct value on the card, hidden: the value column's width.
    private var valueReserve: some View {
        ZStack(alignment: .leading) {
            ForEach(Array(input.groups.enumerated()), id: \.offset) { _, group in
                ForEach(PairedMilestoneSide10868.allCases, id: \.self) { side in
                    ForEach(Array(input.slots(group, side: side).enumerated()), id: \.offset) { _, slot in
                        slotValue(slot, side: side)
                    }
                }
            }
        }
        .hidden()
    }

    private func compactGroup(_ group: PairedMilestoneGroup10868, gridlines: [Double]) -> some View {
        let selected = input.isSelected(group)
        let action = input.groupAction(group, canSelect: canSelect)
        return control(action) {
            VStack(alignment: .leading, spacing: 3) {
                ForEach(PairedMilestoneSide10868.allCases, id: \.self) { side in
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(input.slots(group, side: side).enumerated()), id: \.offset) { index, slot in
                            compactColumns {
                                compactLead(side == .first && index == 0 ? group.target : nil, selected: selected,
                                            side: index == 0 ? side : nil)
                            } track: {
                                slotTrack(slot, side: side, selected: selected, gridlines: gridlines)
                            } value: {
                                ZStack(alignment: .leading) {
                                    valueReserve
                                    slotValue(slot, side: side)
                                }
                                .frame(minHeight: trackRowHeight)
                            }
                        }
                    }
                }
            }
            .groupChrome(selected: selected)
        }
        .groupAccessibility(input: input, group: group, selected: selected, hasAction: action != nil)
    }

    // Stacked: the target, then per subject row its shape and direct value
    // above a full-width track, or its shape and words.

    private func stackedBars(_ ticks: [PlayerContributionPlacedTick10868], gridlines: [Double]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if !ticks.isEmpty {
                axisLabels(ticks).padding(.horizontal, 8)
            }
            ForEach(Array(input.groups.enumerated()), id: \.offset) { _, group in
                stackedGroup(group, gridlines: gridlines)
            }
        }
    }

    private func stackedGroup(_ group: PairedMilestoneGroup10868, gridlines: [Double]) -> some View {
        let selected = input.isSelected(group)
        let action = input.groupAction(group, canSelect: canSelect)
        return control(action) {
            VStack(alignment: .leading, spacing: 4) {
                targetLabel(group.target, selected: selected)
                ForEach(PairedMilestoneSide10868.allCases, id: \.self) { side in
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(input.slots(group, side: side).enumerated()), id: \.offset) { _, slot in
                            switch slot {
                            case .mark(_, let fraction, let filled):
                                HStack(spacing: 6) {
                                    glyph(side).accessibilityHidden(true)
                                    slotValue(slot, side: side)
                                }
                                laneTrack(fraction, filled: filled, selected: selected, side: side, gridlines: gridlines)
                            case .status(let status):
                                HStack(alignment: .firstTextBaseline, spacing: 6) {
                                    glyph(side).accessibilityHidden(true)
                                    statusText(status)
                                        .foregroundStyle(DS.textSecondary)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                        }
                    }
                }
            }
            .groupChrome(selected: selected)
        }
        .groupAccessibility(input: input, group: group, selected: selected, hasAction: action != nil)
    }

    // Shared by both bar forms.

    /// A mark's direct value with its outlined or filled key during play, or nothing for words.
    @ViewBuilder private func slotValue(_ slot: PairedMilestoneSlot10868, side: PairedMilestoneSide10868) -> some View {
        switch slot {
        case .mark(let observation, _, let filled):
            barValue(observation, mark: filled ? .filled : (input.phase == .during ? .outlined : nil), side: side)
        case .status:
            EmptyView()
        }
    }

    private func barValue(_ observation: PlayerContributionObservation10868, mark: KeyMark?, side: PairedMilestoneSide10868) -> some View {
        HStack(alignment: .center, spacing: 4) {
            if let mark { keyMark(mark, color: tint(side)) }
            Text(observation.text).font(.subheadline.bold()).monospacedDigit().foregroundStyle(DS.textPrimary).fixedSize()
        }
    }

    /// A mark's track, or the owner's words in the track's place — never a
    /// 0% bar standing in for an absence.
    @ViewBuilder private func slotTrack(_ slot: PairedMilestoneSlot10868, side: PairedMilestoneSide10868, selected: Bool,
                                        gridlines: [Double]) -> some View {
        switch slot {
        case .mark(_, let fraction, let filled):
            laneTrack(fraction, filled: filled, selected: selected, side: side, gridlines: gridlines)
        case .status(let status):
            statusText(status)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: trackRowHeight, alignment: .leading)
        }
    }

    /// A reading without a mark in one wrapping line: its label when the phase
    /// needs one, then the owner's words. Never truncated or shrunk.
    private func statusText(_ status: PlayerContributionRowStatus10868) -> Text {
        let words = Text(status.words).font(.caption.weight(.semibold))
        guard let title = status.title else { return words }
        return Text(title + " · ").font(.caption2) + words
    }

    /// Gridlines at the owner's ticks and one bar from the same origin on the
    /// same full-width scale. Nothing is drawn for a value the scale cannot place.
    private func laneTrack(_ fraction: Double?, filled: Bool, selected: Bool, side: PairedMilestoneSide10868,
                           gridlines: [Double]) -> some View {
        let inset = PlayerContributionGeometry10868.selectedLineWidth
        return GeometryReader { geo in
            ZStack(alignment: .leading) {
                Path { path in
                    for fraction in gridlines {
                        guard let x = PlayerContributionGeometry10868.x(fraction, width: geo.size.width, inset: inset) else { continue }
                        path.move(to: CGPoint(x: x, y: 0))
                        path.addLine(to: CGPoint(x: x, y: geo.size.height))
                    }
                }
                .stroke(DS.border, style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
                if let length = PlayerContributionGeometry10868.markLength(fraction, extent: geo.size.width - 2 * inset) {
                    barShape(filled: filled, selected: selected, side: side)
                        .frame(width: length, height: laneHeight)
                        .offset(x: inset)
                }
            }
        }
        .frame(height: trackRowHeight)
        .accessibilityHidden(true)
    }

    /// Outlined for pregame, filled for a recorded in-game chance, in the
    /// subject's tint. Selection thickens the outline, never colour alone.
    @ViewBuilder private func barShape(filled: Bool, selected: Bool, side: PairedMilestoneSide10868) -> some View {
        let lineWidth = selected ? PlayerContributionGeometry10868.selectedLineWidth : PlayerContributionGeometry10868.barLineWidth
        if filled {
            RoundedRectangle(cornerRadius: 3)
                .fill(tint(side))
                .overlay(RoundedRectangle(cornerRadius: 3).strokeBorder(selected ? DS.textPrimary : Color.clear, lineWidth: lineWidth))
        } else {
            RoundedRectangle(cornerRadius: 3)
                .fill(DS.cardBg)
                .overlay(RoundedRectangle(cornerRadius: 3).strokeBorder(tint(side), lineWidth: lineWidth))
        }
    }

    // MARK: Previous / next and expand

    /// Shown only from a resolved selection with a callback; each end is
    /// disabled rather than wrapping or jumping.
    @ViewBuilder private var stepper: some View {
        if canSelect, let group = input.selection.group {
            HStack(spacing: 8) {
                stepButton(input.stepAction(-1, canSelect: canSelect), systemName: "chevron.left",
                           title: PairedMilestoneInput10868.previousTitle, id: PairedMilestoneAccessibilityID10868.previous)
                Text(group.title)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .frame(maxWidth: .infinity)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                stepButton(input.stepAction(1, canSelect: canSelect), systemName: "chevron.right",
                           title: PairedMilestoneInput10868.nextTitle, id: PairedMilestoneAccessibilityID10868.next)
            }
        }
    }

    private func stepButton(_ action: PairedMilestoneAction10868?, systemName: String, title: String, id: String) -> some View {
        Button {
            action?.perform(onSelect: onSelect, onDetails: onDetails, onExpand: onExpand)
        } label: {
            Image(systemName: systemName)
                .font(.body.weight(.semibold))
                .foregroundStyle(action == nil ? DS.textMuted : DS.blue)
                .frame(minWidth: 44, minHeight: 44)
                .contentShape(Rectangle())
        }
        .disabled(action == nil)
        .accessibilityLabel(title)
        .accessibilityIdentifier(id)
    }

    @ViewBuilder private var expandButton: some View {
        if let action = input.expandAction(canExpand: canExpand), let cardID = input.cardID {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails, onExpand: onExpand)
            } label: {
                HStack {
                    Text(PairedMilestoneInput10868.expandTitle).fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "arrow.up.left.and.arrow.down.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityLabel("\(PairedMilestoneInput10868.expandTitle), \(input.title)")
            .accessibilityIdentifier(PairedMilestoneAccessibilityID10868.expand(cardID))
        }
    }

    // MARK: Controls

    /// A button only when the owner supplied the callback and an exact id;
    /// otherwise the same content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: PairedMilestoneAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails, onExpand: onExpand)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

private extension View {
    /// A bar group's selection chrome: a faint fill and a durable leading bar,
    /// never colour alone.
    func groupChrome(selected: Bool) -> some View {
        padding(.vertical, 4)
            .padding(.horizontal, 8)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(selected ? DS.textPrimary.opacity(0.05) : Color.clear, in: RoundedRectangle(cornerRadius: 6))
            .overlay(alignment: .leading) {
                if selected { Rectangle().fill(DS.textPrimary).frame(width: 3) }
            }
            .contentShape(Rectangle())
    }

    /// A bar group is one element naming each subject and its own readings.
    func groupAccessibility(input: PairedMilestoneInput10868, group: PairedMilestoneGroup10868, selected: Bool,
                            hasAction: Bool) -> some View {
        accessibilityLabel(group.title)
            .accessibilityValue(input.accessibilityValue(for: group))
            .accessibilityHint(hasAction ? "Selects this milestone’s comparison" : "")
            .accessibilityAddTraits(selected ? .isSelected : [])
            .accessibilityIdentifier(PairedMilestoneAccessibilityID10868.group(group.id))
    }
}

private extension PlayerContributionReading10868 {
    /// The same figure-or-words rule as the pregame readout.
    var duelDisplay: PlayerDuelChanceDisplay10868 { PlayerDuelInput10868.display(self) }
}

private extension PlayerDuelChanceDisplay10868 {
    var isFigure: Bool {
        if case .figure = self { return true }
        return false
    }
}

private extension PlayerContributionCurrentReading10868 {
    var isChance: Bool {
        if case .chance = self { return true }
        return false
    }
}
