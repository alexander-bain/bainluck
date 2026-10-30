import SwiftUI

// #10868 — a player's points or assists across a match's lifecycle. One card,
// two approved chart orientations: points keep vertical probability columns,
// assists horizontal probability bars. Before play the card shows the saved
// pregame chances of reaching each milestone. During play each milestone also
// carries an independently admitted in-game chance, filled beside the hollow
// pregame mark on the same 0–100% scale, while the count so far and any
// performance status sit apart from every probability. After the final the
// pregame marks stay, and the selected milestone's pregame chance is compared
// with the owner-admitted contract result and the final count.
//
// Presentation only, extracted from the approved design
// (hockey-contributions-v436, hockey-before-milestones-v437 and
// hockey-live-intake-v438 frames; totals-final-forecast-binding-20261024
// `HockeyContributionVisual`, `HockeyLiveCard`, the latest equal-prominence
// `HockeyChancePair`, and the native `HockeyContributionCard.swift`).
//
// Every figure, target label, tick, count, breakdown, status, movement, date,
// source, missing qualifier and result arrives resolved by the owner and is
// shown verbatim. This layer never formats, rounds, ranks, filters, caps or
// joins, never reads a clock, cache, subscription or admission rule, never
// elects a baseline or decides whether a reading is recent, never derives a
// movement, never infers a result from a count, and never shows a settled
// 0%/100% as a pregame or in-game chance. A reached milestone is performance,
// not settlement and not 100%, and reads as "Actual so far". A missing
// observation draws no zero bar; 0% is a real observation and draws a visible
// zero mark. A reading without a mark keeps its owner's words on every
// milestone, selected or not. An actual count is never put on a probability
// axis.
//
// Milestone selection, player choice, timing disclosure and Details stay with
// the host: the view keeps no selected state, no sheet, no focus and no
// subscription. With no callback, content is shown without a button and no tap
// is asked for.
//
// Host binding still owed — not available at this base (see
// PLAYER-CONTRIBUTION-NATIVE-BINDING-MAP.md). An owner must supply, for the
// exact stat contract of one player:
//   • each milestone's exact original contract id and formatted target labels,
//   • an admitted same-stat, same-predicate pregame observation (raw value,
//     formatted figure, full time/source) or its own missing words,
//   • during play, an independently admitted in-game observation with
//     currentness already applied, or its own unavailable / withheld /
//     reached words, and any movement already formatted,
//   • the player's clocked count so far, and the final count, or their words,
//   • an independently admitted contract result (reached, missed or
//     unconfirmed) with its words;
// and for the card: the player identity, milestone membership and order, the
// selected milestone id, tick labels, header and definition copy, the player
// choices and the timing lines.

/// One admitted milestone chance. `probability` drives chart geometry only;
/// `text` is what the reader sees.
nonisolated struct PlayerContributionObservation10868: Equatable {
    let probability: Double
    let text: String
    /// Full time and source for VoiceOver ("minute ending Oct 3, 4:51 PM PT · Kalshi").
    let accessibilityDetail: String
}

/// The owner's in-game chance for one milestone, currentness applied. Only
/// `.recorded` draws a mark.
nonisolated enum PlayerContributionCurrent10868: Equatable {
    /// An independently admitted, current in-game observation, with the
    /// owner's already-formatted movement since pregame, if any.
    case recorded(PlayerContributionObservation10868, movement: String?)
    /// No in-game reading ("No in-game reading").
    case unavailable(String)
    /// A reading exists but the owner withholds it ("No recent probability
    /// update", "No update since goal").
    case withheld(String)
    /// The player has already reached this milestone in play ("Reached so
    /// far"). Performance, not a settlement, so no chance is shown: it reads
    /// as "Actual so far", never under a chance label.
    case reached(String)
}

/// The owner-admitted contract result. Availability is explicit: there is no
/// Bool, so an absent result can never read as missed, and it is never
/// derived from a count.
nonisolated enum PlayerContributionResult10868: Equatable {
    /// "Reached".
    case reached(String)
    /// "Missed".
    case missed(String)
    /// No admitted result — pending, missing, ambiguous or conflicting
    /// ("Result unconfirmed").
    case unconfirmed(String)

    var text: String {
        switch self {
        case .reached(let text), .missed(let text), .unconfirmed(let text): text
        }
    }

    var isAdmitted: Bool {
        if case .unconfirmed = self { return false }
        return true
    }
}

/// The owner's performance status toward one milestone during play.
nonisolated struct PlayerContributionProgress10868: Equatable {
    /// "1 more for 2+", "Milestone reached so far".
    let status: String
    /// Owner-computed share of the target already achieved, 0...1, for the
    /// progress strip. Nil or invalid draws no strip.
    let fraction: Double?
}

/// One milestone of the player's stat contract.
nonisolated struct PlayerContributionMilestone10868: Equatable {
    /// Opaque original contract identity, passed back exactly.
    let id: String
    /// The short axis label ("2+").
    let target: String
    /// The full milestone ("2+ points").
    let title: String
    let before: PlayerContributionObservation10868?
    /// The owner's words for a missing pregame chance ("Unavailable").
    let beforeMissing: String
    /// Read only during play.
    let current: PlayerContributionCurrent10868
    /// Read only during play.
    let progress: PlayerContributionProgress10868?
    /// Read only after the final.
    let result: PlayerContributionResult10868
}

/// An owner-admitted count.
nonisolated struct PlayerContributionCount10868: Equatable {
    /// "2".
    let count: String
    /// "points", "point so far"; nil draws no unit.
    let unit: String?
    /// "1 goal + 1 assist".
    let breakdown: String?
    /// Clock and source for VoiceOver ("as of 6:45 PM PT, 2nd period, 4:09 left · ESPN").
    let accessibilityDetail: String
}

nonisolated enum PlayerContributionActual10868: Equatable {
    case count(PlayerContributionCount10868)
    /// "Count unavailable", "Exact final count unavailable".
    case unavailable(String)
}

/// The player the card is about, with its milestones in the owner's order.
nonisolated struct PlayerContributionPlayer10868: Equatable {
    /// Opaque player identity, compared exactly with the choices.
    let id: String
    let name: String
    /// "Minnesota"; nil draws no team line.
    let team: String?
    let milestones: [PlayerContributionMilestone10868]
    /// Read only during play (count so far) and after the final (final count).
    let actual: PlayerContributionActual10868
}

nonisolated enum PlayerContributionPhase10868: Equatable {
    case before
    case during
    case final
}

nonisolated enum PlayerContributionChartForm10868: Hashable {
    case columns
    case bars
}

/// Points keep vertical columns; assists horizontal bars.
nonisolated enum PlayerContributionOrientation10868: Equatable {
    case columns
    case bars

    /// The forms to try, in order. Columns fall back to bars, with every
    /// milestone kept, when the owner's milestones do not fit as columns.
    var forms: [PlayerContributionChartForm10868] {
        switch self {
        case .columns: [.columns, .bars]
        case .bars: [.bars]
        }
    }
}

nonisolated struct PlayerContributionTick10868: Equatable {
    /// Raw probability, 0...1.
    let value: Double
    /// The owner's label ("50%").
    let text: String
}

/// The owner's timing disclosure for one milestone. Shown only while that
/// exact milestone is the resolved selection.
nonisolated struct PlayerContributionTiming10868: Equatable {
    let milestoneID: String
    /// "Kirill Kaprizov 2+ points · probability timing".
    let title: String
    let lines: [String]
}

nonisolated struct PlayerContributionChoice10868: Equatable {
    /// Opaque player identity, passed back exactly.
    let id: String
    let name: String
    /// "Minnesota"; nil draws nothing.
    let detail: String?
}

/// The page's player choices. The page owns navigation; this only lists them.
nonisolated struct PlayerContributionChooser10868: Equatable {
    /// "Choose player · 11".
    let title: String
    /// In the owner's order.
    let choices: [PlayerContributionChoice10868]
}

nonisolated enum PlayerContributionSelection10868: Equatable {
    case none
    case selected(PlayerContributionMilestone10868)
    /// No milestone carries the selected id.
    case missing(String)
    /// More than one milestone carries the selected id.
    case duplicate(String)

    var milestone: PlayerContributionMilestone10868? {
        if case .selected(let milestone) = self { return milestone }
        return nil
    }
}

nonisolated enum PlayerContributionReading10868: Equatable {
    case value(PlayerContributionObservation10868)
    case missing(String)

    var text: String {
        switch self {
        case .value(let observation): observation.text
        case .missing(let text): text
        }
    }
}

/// The in-game slot beside a milestone's pregame chance, during play. A
/// reached milestone is performance, so it is kept apart from every chance
/// state rather than collapsed with a missing one.
nonisolated enum PlayerContributionCurrentReading10868: Equatable {
    /// A recorded in-game chance — the only state drawn as a filled mark.
    case chance(PlayerContributionObservation10868)
    /// The owner's words for an unavailable or withheld in-game chance.
    case chanceStatus(String)
    /// The owner's words for a milestone already reached in play.
    case actual(String)

    var title: String {
        switch self {
        case .chance: PlayerContributionInput10868.recordedTitle
        case .chanceStatus: PlayerContributionInput10868.currentStatusTitle
        case .actual: PlayerContributionInput10868.actualSoFarTitle
        }
    }

    var spokenTitle: String {
        switch self {
        case .chance: PlayerContributionInput10868.spokenRecorded
        case .chanceStatus: PlayerContributionInput10868.spokenCurrentStatus
        case .actual: PlayerContributionInput10868.spokenActualSoFar
        }
    }

    var text: String {
        switch self {
        case .chance(let observation): observation.text
        case .chanceStatus(let text), .actual(let text): text
        }
    }

    /// The figure or the words, for the shared value styling.
    var reading: PlayerContributionReading10868 {
        switch self {
        case .chance(let observation): .value(observation)
        case .chanceStatus(let text), .actual(let text): .missing(text)
        }
    }
}

/// A milestone reading shown in words because it has no mark: whose it is
/// and the owner's words.
nonisolated struct PlayerContributionRowStatus10868: Equatable {
    /// "Pregame chance", "In-game chance", "Actual so far". Nil when the phase
    /// shows only the pregame reading, so nothing can be confused with it.
    let title: String?
    let words: String
}

/// What one milestone prints beside its marks. Columns and bar rows (the
/// assists chart and the points fallback) both draw exactly this, selected or
/// not, so an unselected milestone never loses its status.
nonisolated struct PlayerContributionRowPresentation10868: Equatable {
    /// The hollow pregame mark's direct value.
    let pregame: PlayerContributionObservation10868?
    /// The filled in-game mark's direct value: during play, recorded only.
    let current: PlayerContributionObservation10868?
    /// During play the in-game lane exists even when it holds no mark.
    let hasCurrentLane: Bool
    /// Each reading without a mark, pregame first, in the owner's words.
    let statuses: [PlayerContributionRowStatus10868]
}

/// What sits beside the pregame chance in the selected comparison.
nonisolated enum PlayerContributionSecondReading10868: Equatable {
    /// During play: the in-game chance, its status or the actual reached state.
    case current(PlayerContributionCurrentReading10868)
    /// After the final: the contract result.
    case result(PlayerContributionResult10868)
}

/// The count block: its fixed title and the owner's count or words.
nonisolated struct PlayerContributionActualPresentation10868: Equatable {
    let title: String
    let actual: PlayerContributionActual10868
}

nonisolated enum PlayerContributionAction10868: Equatable {
    case select(String)
    case choosePlayer(String)
    case details(String)

    func perform(onSelect: ((String) -> Void)?, onChoosePlayer: ((String) -> Void)?, onDetails: ((String) -> Void)?) {
        switch self {
        case .select(let id): onSelect?(id)
        case .choosePlayer(let id): onChoosePlayer?(id)
        case .details(let id): onDetails?(id)
        }
    }
}

nonisolated enum PlayerContributionTimingPresentation10868: Equatable {
    /// The page owns the expanded flag.
    case disclosure(PlayerContributionTiming10868)
    /// No binding: the owner's timing content, already expanded.
    case expanded(PlayerContributionTiming10868)
}

nonisolated enum PlayerContributionChooserPresentation10868: Equatable {
    /// The page owns the expanded flag.
    case disclosure(PlayerContributionChooser10868)
    /// No binding: the choices, already expanded.
    case expanded(PlayerContributionChooser10868)
}

nonisolated struct PlayerContributionInput10868: Equatable {
    let phase: PlayerContributionPhase10868
    let orientation: PlayerContributionOrientation10868
    /// "PLAYER POINTS".
    let eyebrow: String?
    /// "Points in context".
    let title: String
    /// Fixed sports definition ("One point for each goal or assist.").
    let definition: String?
    /// Nil when the owner has no player to show.
    let player: PlayerContributionPlayer10868?
    /// The owner's exact milestone selection.
    let selectedMilestoneID: String?
    /// "Pre-game chances · at least this many points".
    let chartTitle: String?
    /// The owner's labelled ticks on the fixed 0...1 probability scale.
    let ticks: [PlayerContributionTick10868]
    let chooser: PlayerContributionChooser10868?
    let timing: PlayerContributionTiming10868?

    static let pregameTitle = "Pregame chance"
    static let recordedTitle = "Recorded in-game"
    static let currentStatusTitle = "In-game chance"
    static let actualSoFarTitle = "Actual so far"
    static let resultTitle = "Final result"
    static let countSoFarTitle = "Count so far"
    static let finalCountTitle = "Final count"
    static let detailsTitle = "Details & recorded times"
    static let milestoneUnavailable = "Selected milestone unavailable."
    static let playerUnavailable = "Selected player unavailable."
    static let spokenPregame = "Pregame chance"
    static let spokenRecorded = "Recorded in-game chance"
    static let spokenCurrentStatus = "In-game chance"
    static let spokenActualSoFar = "Actual so far"
    static let spokenMovement = "Change since pregame"
    static let spokenResult = "Final result"
    static let spokenProgress = "Progress toward"

    var milestones: [PlayerContributionMilestone10868] { player?.milestones ?? [] }

    /// Exact id only. A missing or duplicated id gets no substitute milestone.
    var selection: PlayerContributionSelection10868 {
        guard player != nil, let selectedMilestoneID else { return .none }
        let matches = milestones.filter { $0.id == selectedMilestoneID }
        switch matches.count {
        case 1: return .selected(matches[0])
        case 0: return .missing(selectedMilestoneID)
        default: return .duplicate(selectedMilestoneID)
        }
    }

    func isSelected(_ milestone: PlayerContributionMilestone10868) -> Bool {
        selection.milestone?.id == milestone.id
    }

    var selectionNotice: String? {
        guard player != nil else { return Self.playerUnavailable }
        switch selection {
        case .missing, .duplicate: return Self.milestoneUnavailable
        case .none, .selected: return nil
        }
    }

    // MARK: Phase visibility

    func beforeReading(_ milestone: PlayerContributionMilestone10868) -> PlayerContributionReading10868 {
        milestone.before.map { .value($0) } ?? .missing(milestone.beforeMissing)
    }

    /// The in-game slot, during play only — never before play, never after
    /// the final. A reached milestone stays performance ("Actual so far").
    func currentReading(_ milestone: PlayerContributionMilestone10868) -> PlayerContributionCurrentReading10868? {
        guard phase == .during else { return nil }
        switch milestone.current {
        case .recorded(let observation, _): return .chance(observation)
        case .unavailable(let text), .withheld(let text): return .chanceStatus(text)
        case .reached(let text): return .actual(text)
        }
    }

    /// What the milestone's column or bar row prints, in either orientation,
    /// whether or not it is selected. Every reading without a mark keeps its
    /// owner's words; during play each carries its own label, so a missing
    /// pregame chance, a missing in-game chance and a reached milestone can
    /// never be read as one another.
    func row(_ milestone: PlayerContributionMilestone10868) -> PlayerContributionRowPresentation10868 {
        let current = currentReading(milestone)
        var statuses: [PlayerContributionRowStatus10868] = []
        if milestone.before == nil {
            statuses.append(PlayerContributionRowStatus10868(title: current == nil ? nil : Self.pregameTitle,
                                                             words: milestone.beforeMissing))
        }
        switch current {
        case .chanceStatus(let text)?, .actual(let text)?:
            statuses.append(PlayerContributionRowStatus10868(title: current?.title, words: text))
        case .chance?, nil:
            break
        }
        var recorded: PlayerContributionObservation10868?
        if case .chance(let observation)? = current { recorded = observation }
        return PlayerContributionRowPresentation10868(
            pregame: milestone.before,
            current: recorded,
            hasCurrentLane: current != nil,
            statuses: statuses
        )
    }

    /// The owner's movement, during play and only beside a recorded reading.
    func movement(_ milestone: PlayerContributionMilestone10868) -> String? {
        guard phase == .during, case .recorded(_, let movement) = milestone.current else { return nil }
        return movement
    }

    /// The performance status, during play only.
    func progress(_ milestone: PlayerContributionMilestone10868) -> PlayerContributionProgress10868? {
        phase == .during ? milestone.progress : nil
    }

    /// The contract result, after the final only.
    func result(_ milestone: PlayerContributionMilestone10868) -> PlayerContributionResult10868? {
        phase == .final ? milestone.result : nil
    }

    /// Nil before play: no current, result or actual column.
    func secondReading(_ milestone: PlayerContributionMilestone10868) -> PlayerContributionSecondReading10868? {
        if let result = result(milestone) { return .result(result) }
        return currentReading(milestone).map { .current($0) }
    }

    /// The count block: none before play; "Count so far" during; "Final count" after.
    var actualPresentation: PlayerContributionActualPresentation10868? {
        guard let player else { return nil }
        switch phase {
        case .before: return nil
        case .during: return PlayerContributionActualPresentation10868(title: Self.countSoFarTitle, actual: player.actual)
        case .final: return PlayerContributionActualPresentation10868(title: Self.finalCountTitle, actual: player.actual)
        }
    }

    // MARK: Marks

    /// The hollow pregame mark's position on the 0...1 scale, any phase.
    func beforeFraction(_ milestone: PlayerContributionMilestone10868) -> Double? {
        milestone.before.flatMap { PlayerContributionGeometry10868.fraction($0.probability) }
    }

    /// The filled in-game mark, during play and only for a recorded reading.
    func currentFraction(_ milestone: PlayerContributionMilestone10868) -> Double? {
        guard case .chance(let observation)? = currentReading(milestone) else { return nil }
        return PlayerContributionGeometry10868.fraction(observation.probability)
    }

    /// The comparison's filled key appears only beside a recorded reading.
    func showsCurrentKey(_ milestone: PlayerContributionMilestone10868) -> Bool {
        if case .chance? = currentReading(milestone) { return true }
        return false
    }

    /// A small key under the chart title only when filled marks are drawn and
    /// the selected comparison does not already carry the hollow/filled key.
    var showsChartKey: Bool {
        guard phase == .during, milestones.contains(where: { currentFraction($0) != nil }) else { return false }
        if let selected = selection.milestone, showsCurrentKey(selected) { return false }
        return true
    }

    // MARK: Choices and timing

    /// The choice is marked only when exactly one carries the player's id.
    func isChosen(_ choice: PlayerContributionChoice10868) -> Bool {
        guard let player, let chooser, choice.id == player.id else { return false }
        return chooser.choices.filter { $0.id == player.id }.count == 1
    }

    func chooserPresentation(hasBinding: Bool) -> PlayerContributionChooserPresentation10868? {
        guard let chooser, !chooser.choices.isEmpty else { return nil }
        return hasBinding ? .disclosure(chooser) : .expanded(chooser)
    }

    /// Timing only for the exact resolved selection.
    func timingPresentation(hasBinding: Bool) -> PlayerContributionTimingPresentation10868? {
        guard let timing, let selected = selection.milestone, selected.id == timing.milestoneID else { return nil }
        return hasBinding ? .disclosure(timing) : .expanded(timing)
    }

    // MARK: Actions

    func milestoneAction(_ milestone: PlayerContributionMilestone10868, canSelect: Bool) -> PlayerContributionAction10868? {
        canSelect ? .select(milestone.id) : nil
    }

    func choiceAction(_ choice: PlayerContributionChoice10868, canChoose: Bool) -> PlayerContributionAction10868? {
        canChoose ? .choosePlayer(choice.id) : nil
    }

    func detailsAction(canOpenDetails: Bool) -> PlayerContributionAction10868? {
        guard canOpenDetails, let milestone = selection.milestone else { return nil }
        return .details(milestone.id)
    }

    // MARK: VoiceOver

    var accessibilityHeader: String {
        ([eyebrow, title].compactMap { $0 }).joined(separator: ". ")
    }

    var accessibilityPlayer: String? {
        player.map { ([$0.name, $0.team].compactMap { $0 }).joined(separator: ", ") }
    }

    /// A chart milestone: its pregame chance and, during play, its in-game
    /// chance, its status or "Actual so far".
    func accessibilityValue(for milestone: PlayerContributionMilestone10868) -> String {
        var parts = [Self.spoken(beforeReading(milestone), title: Self.spokenPregame)]
        if let current = currentReading(milestone) {
            parts.append(Self.spoken(current.reading, title: current.spokenTitle))
        }
        return parts.joined(separator: "; ")
    }

    /// The selected comparison: baseline, then the separately timed in-game
    /// chance (and the owner's movement) or the result.
    func accessibilityComparison(for milestone: PlayerContributionMilestone10868) -> String {
        var parts = [Self.spoken(beforeReading(milestone), title: Self.spokenPregame)]
        switch secondReading(milestone) {
        case .current(let current)?:
            parts.append(Self.spoken(current.reading, title: current.spokenTitle))
            if let movement = movement(milestone) { parts.append("\(Self.spokenMovement): \(movement)") }
        case .result(let result)?:
            parts.append("\(Self.spokenResult): \(result.text)")
        case nil:
            break
        }
        return parts.joined(separator: "; ")
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

    func accessibilityProgressLabel(for milestone: PlayerContributionMilestone10868) -> String {
        "\(Self.spokenProgress) \(milestone.title)"
    }

    private static func spoken(_ reading: PlayerContributionReading10868, title: String) -> String {
        switch reading {
        case .value(let observation): "\(title): \(observation.text), \(observation.accessibilityDetail)"
        case .missing(let text): "\(title): \(text)"
        }
    }
}

/// A tick the scale can place: its fraction and the owner's label.
nonisolated struct PlayerContributionPlacedTick10868: Equatable {
    let fraction: Double
    let text: String
}

/// One label's place along an axis: its start, and the lane (row for a
/// horizontal axis, column for a vertical one) it was given.
nonisolated struct PlayerContributionLanePlacement10868: Equatable {
    /// The owner's index.
    let index: Int
    let origin: CGFloat
    let lane: Int
    /// Longer than the whole axis, so placed alone on its own lane at the start.
    let oversize: Bool
}

/// Every axis label placed, in the owner's order, and the block they need.
nonisolated struct PlayerContributionAxisPlan10868: Equatable {
    /// Each label's frame within the block, in the owner's order.
    let frames: [CGRect]
    /// The space actually used, every lane included, and any extent past the axis.
    let size: CGSize
}

nonisolated enum PlayerContributionGeometry10868 {
    /// The shortest mark drawn for a real 0% so it reads as an observation,
    /// never as a missing one.
    static let minimumMark: CGFloat = 3
    static let barLineWidth: CGFloat = 1.5
    static let selectedLineWidth: CGFloat = 3

    /// A raw probability's place on the fixed 0...1 scale. Nil for a
    /// non-finite or out-of-range value — the mark is omitted, never clamped
    /// or drawn at zero.
    static func fraction(_ value: Double) -> Double? {
        guard value.isFinite, value >= 0, value <= 1 else { return nil }
        return value
    }

    /// How long a mark is within this extent. Nil draws nothing; a real 0%
    /// still gets the minimum visible mark.
    static func markLength(_ fraction: Double?, extent: CGFloat) -> CGFloat? {
        guard let fraction, fraction.isFinite, fraction >= 0, fraction <= 1,
              extent.isFinite, extent > 0 else { return nil }
        return min(extent, max(minimumMark, extent * CGFloat(fraction)))
    }

    /// The x of a fraction along a horizontal track of this width, inside the end insets.
    static func x(_ fraction: Double, width: CGFloat, inset: CGFloat) -> CGFloat? {
        let usable = width - 2 * inset
        guard usable.isFinite, usable > 0, fraction.isFinite, fraction >= 0, fraction <= 1 else { return nil }
        return inset + usable * CGFloat(fraction)
    }

    /// The y of a fraction in a vertical plot of this height (0 at the bottom).
    static func y(_ fraction: Double, height: CGFloat) -> CGFloat? {
        guard height.isFinite, height > 0, fraction.isFinite, fraction >= 0, fraction <= 1 else { return nil }
        return height - height * CGFloat(fraction)
    }

    /// The ticks the scale can place, in the owner's order.
    static func visibleTicks(_ ticks: [PlayerContributionTick10868]) -> [PlayerContributionPlacedTick10868] {
        ticks.compactMap { tick in
            fraction(tick.value).map { PlayerContributionPlacedTick10868(fraction: $0, text: tick.text) }
        }
    }

    /// Lanes for labels along one axis. Each label is centred on its position
    /// and kept inside the axis; when it would come within `gap` of a label
    /// already on a lane it moves to the next lane rather than away from its
    /// position or shrinking. A label longer than the whole axis gets a lane
    /// of its own at the start. Every label is placed, in the owner's order;
    /// positions need not be sorted, and ties keep the owner's order.
    static func lanes(centers: [CGFloat], lengths: [CGFloat], extent: CGFloat, gap: CGFloat = 4) -> [PlayerContributionLanePlacement10868] {
        guard centers.count == lengths.count, !centers.isEmpty else { return [] }
        let extent = extent.isFinite ? max(0, extent) : 0
        let order = centers.indices.sorted { a, b in
            let ca = centers[a].isFinite ? centers[a] : 0
            let cb = centers[b].isFinite ? centers[b] : 0
            return ca == cb ? a < b : ca < cb
        }
        var laneEnds: [CGFloat] = []   // end of the last label on each lane; .infinity = full
        var placed = [PlayerContributionLanePlacement10868?](repeating: nil, count: centers.count)
        for i in order {
            let length = lengths[i].isFinite ? max(0, lengths[i]) : 0
            if length > extent {
                laneEnds.append(.infinity)
                placed[i] = PlayerContributionLanePlacement10868(index: i, origin: 0, lane: laneEnds.count - 1, oversize: true)
                continue
            }
            let center = centers[i].isFinite ? centers[i] : 0
            let origin = min(max(0, center - length / 2), extent - length)
            let lane: Int
            if let free = laneEnds.firstIndex(where: { $0 + gap <= origin }) {
                lane = free
            } else {
                laneEnds.append(0)
                lane = laneEnds.count - 1
            }
            laneEnds[lane] = origin + length
            placed[i] = PlayerContributionLanePlacement10868(index: i, origin: origin, lane: lane, oversize: false)
        }
        return placed.compactMap { $0 }
    }

    /// Frames for axis labels. A horizontal axis stacks its lanes as rows
    /// below one another; a vertical axis stacks them as columns, the first
    /// lane beside the plot (trailing) and each label trailing-aligned in its
    /// column. A horizontal label wider than the axis is given its size at
    /// the axis width (`atExtent`, it wraps); if even that is wider, the plan's
    /// width says so instead of hiding the overflow.
    ///
    /// - Parameters:
    ///   - centers: each label's position along the axis, in the owner's order.
    ///   - natural: each label's one-line size.
    ///   - atExtent: each label's size when offered the axis width; read only
    ///     for an oversize horizontal label.
    static func axisPlan(axis: Axis, centers: [CGFloat], natural: [CGSize], atExtent: [CGSize],
                         extent: CGFloat, gap: CGFloat = 4, laneGap: CGFloat = 2) -> PlayerContributionAxisPlan10868 {
        guard centers.count == natural.count, centers.count == atExtent.count, !centers.isEmpty else {
            return PlayerContributionAxisPlan10868(frames: [], size: .zero)
        }
        let extent = extent.isFinite ? max(0, extent) : 0
        let horizontal = axis == .horizontal
        let lengths = natural.map { horizontal ? $0.width : $0.height }
        let placements = lanes(centers: centers, lengths: lengths, extent: extent, gap: gap)
        let laneCount = (placements.map(\.lane).max() ?? -1) + 1
        var sizes = natural
        for placement in placements where placement.oversize && horizontal {
            sizes[placement.index] = atExtent[placement.index]
        }
        var depths = [CGFloat](repeating: 0, count: laneCount)
        for placement in placements {
            let size = sizes[placement.index]
            depths[placement.lane] = max(depths[placement.lane], horizontal ? size.height : size.width)
        }
        var offsets: [CGFloat] = []
        var running: CGFloat = 0
        for depth in depths {
            offsets.append(running)
            running += depth + laneGap
        }
        let total = max(0, running - laneGap)
        var frames = [CGRect](repeating: .zero, count: centers.count)
        for placement in placements {
            let size = sizes[placement.index]
            let origin = horizontal
                ? CGPoint(x: placement.origin, y: offsets[placement.lane])
                : CGPoint(x: total - offsets[placement.lane] - size.width, y: placement.origin)
            frames[placement.index] = CGRect(origin: origin, size: size)
        }
        let reach = horizontal ? (frames.map(\.maxX).max() ?? 0) : (frames.map(\.maxY).max() ?? 0)
        let size = horizontal
            ? CGSize(width: max(extent, reach), height: total)
            : CGSize(width: total, height: max(extent, reach))
        return PlayerContributionAxisPlan10868(frames: frames, size: size)
    }
}

/// Tick labels laid out along a horizontal track or a vertical plot: one
/// subview per placeable tick, in order. The size it reports is the plan it
/// places, every lane included.
struct PlayerContributionAxisLabelsLayout10868: Layout {
    let fractions: [Double]
    let axis: Axis
    /// The vertical plot's height. Ignored for a horizontal axis, which uses
    /// the proposed width.
    var plotHeight: CGFloat = 0
    /// The horizontal track's end inset, so labels centre on its gridlines.
    var inset: CGFloat = 0
    var gap: CGFloat = 4

    private var laneGap: CGFloat { axis == .horizontal ? 2 : 6 }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let extent = extent(proposal: proposal, subviews: subviews)
        return plan(extent: extent, subviews: subviews)?.size ?? .zero
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let extent = axis == .horizontal ? bounds.width : plotHeight
        guard let plan = plan(extent: extent, subviews: subviews) else { return }
        for (subview, frame) in zip(subviews, plan.frames) {
            subview.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                          anchor: .topLeading,
                          proposal: ProposedViewSize(width: frame.width, height: frame.height))
        }
    }

    private func extent(proposal: ProposedViewSize, subviews: Subviews) -> CGFloat {
        guard axis == .horizontal else { return plotHeight }
        if let width = proposal.width, width.isFinite, width > 0 { return width }
        let natural = subviews.map { $0.sizeThatFits(.unspecified) }
        return natural.map(\.width).reduce(0, +) + gap * CGFloat(max(0, natural.count - 1))
    }

    private func plan(extent: CGFloat, subviews: Subviews) -> PlayerContributionAxisPlan10868? {
        guard subviews.count == fractions.count, !subviews.isEmpty else { return nil }
        let natural = subviews.map { $0.sizeThatFits(.unspecified) }
        let horizontal = axis == .horizontal
        let atExtent = zip(subviews, natural).map { subview, size in
            horizontal && size.width > extent ? subview.sizeThatFits(ProposedViewSize(width: extent, height: nil)) : size
        }
        let centers = fractions.map { fraction in
            horizontal
                ? PlayerContributionGeometry10868.x(fraction, width: extent, inset: inset) ?? 0
                : PlayerContributionGeometry10868.y(fraction, height: extent) ?? 0
        }
        return PlayerContributionGeometry10868.axisPlan(axis: axis, centers: centers, natural: natural, atExtent: atExtent,
                                                       extent: extent, gap: gap, laneGap: laneGap)
    }
}

/// One vertical bar with its direct label above it. Subviews: the label, then
/// the bar. The label's height is always reserved above the full plot, so a
/// 100% bar's label stays inside; nothing is placed by a fixed offset.
struct PlayerContributionColumnBarLayout10868: Layout {
    let fraction: Double?
    let plotHeight: CGFloat
    let barWidth: CGFloat
    var gap: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard subviews.count == 2 else { return .zero }
        let label = subviews[0].sizeThatFits(.unspecified)
        return CGSize(width: max(label.width, barWidth), height: label.height + gap + plotHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count == 2 else { return }
        let label = subviews[0].sizeThatFits(.unspecified)
        let length = PlayerContributionGeometry10868.markLength(fraction, extent: plotHeight) ?? 0
        subviews[1].place(at: CGPoint(x: bounds.midX, y: bounds.maxY), anchor: .bottom,
                          proposal: ProposedViewSize(width: barWidth, height: length))
        subviews[0].place(at: CGPoint(x: bounds.midX, y: bounds.maxY - length - gap), anchor: .bottom,
                          proposal: ProposedViewSize(width: label.width, height: label.height))
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum PlayerContributionAccessibilityID10868 {
    static func milestone(_ id: String) -> String { "playerContribution10868.milestone.\(id)" }
    static func comparison(_ id: String) -> String { "playerContribution10868.comparison.\(id)" }
    static func details(_ id: String) -> String { "playerContribution10868.details.\(id)" }
    static func actual(_ playerID: String) -> String { "playerContribution10868.actual.\(playerID)" }
    static func choice(_ id: String) -> String { "playerContribution10868.choice.\(id)" }
}

struct PlayerContributionPresentation10868: View {
    let input: PlayerContributionInput10868
    var onSelect: ((String) -> Void)? = nil
    var onChoosePlayer: ((String) -> Void)? = nil
    var onDetails: ((String) -> Void)? = nil
    /// Page-owned. Nil shows the choices already expanded.
    var choicesExpanded: Binding<Bool>? = nil
    /// Page-owned. Nil shows the owner's timing content already expanded.
    var timingExpanded: Binding<Bool>? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var chanceSize: CGFloat = 30
    @ScaledMetric(relativeTo: .title) private var countSize: CGFloat = 34
    @ScaledMetric(relativeTo: .title3) private var resultSize: CGFloat = 22
    @ScaledMetric(relativeTo: .body) private var plotHeight: CGFloat = 150
    @ScaledMetric(relativeTo: .body) private var columnWidth: CGFloat = 26
    @ScaledMetric(relativeTo: .body) private var laneHeight: CGFloat = 14

    private let labelGap: CGFloat = 4
    private var canSelect: Bool { onSelect != nil }
    private var canChoose: Bool { onChoosePlayer != nil }
    private var canOpenDetails: Bool { onDetails != nil }
    private var tint: Color { input.orientation == .columns ? DS.blue : DS.emeraldDark }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            if let player = input.player {
                playerLine(player)
            }
            if let definition = input.definition {
                Text(definition)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let notice = input.selectionNotice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let milestone = input.selection.milestone {
                comparison(milestone)
                if let progress = input.progress(milestone) {
                    progressView(progress, milestone: milestone)
                }
            }
            if !input.milestones.isEmpty {
                chart
            }
            chooser
            timing
            detailsButton
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Header and player

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

    @ViewBuilder private func playerLine(_ player: PlayerContributionPlayer10868) -> some View {
        let actual = input.actualPresentation
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 10) { playerParts(player, actual: actual) }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 12) {
                    playerParts(player, actual: actual, spaced: true)
                }
                VStack(alignment: .leading, spacing: 10) { playerParts(player, actual: actual) }
            }
        }
    }

    @ViewBuilder private func playerParts(_ player: PlayerContributionPlayer10868,
                                          actual: PlayerContributionActualPresentation10868?,
                                          spaced: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(player.name).font(.title3.bold()).foregroundStyle(DS.textPrimary)
            if let team = player.team {
                Text(team).font(.subheadline).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityPlayer ?? player.name)
        if spaced { Spacer(minLength: 0) }
        if let actual {
            actualBlock(actual, playerID: player.id)
        }
    }

    /// The count — prominent, labelled, and never on a probability axis.
    private func actualBlock(_ presentation: PlayerContributionActualPresentation10868, playerID: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
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
        .padding(.leading, 12)
        .overlay(alignment: .leading) { Rectangle().fill(DS.border).frame(width: 1) }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(presentation.title)
        .accessibilityValue(input.accessibilityActual(presentation))
        .accessibilityIdentifier(PlayerContributionAccessibilityID10868.actual(playerID))
    }

    // MARK: Selected comparison

    private func comparison(_ milestone: PlayerContributionMilestone10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(milestone.title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 14) { comparisonValues(milestone) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 12) { comparisonValues(milestone) }
                    VStack(alignment: .leading, spacing: 14) { comparisonValues(milestone) }
                }
            }
            if let movement = input.movement(milestone) {
                Text(movement)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(tint)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(milestone.title)
        .accessibilityValue(input.accessibilityComparison(for: milestone))
        .accessibilityIdentifier(PlayerContributionAccessibilityID10868.comparison(milestone.id))
    }

    @ViewBuilder private func comparisonValues(_ milestone: PlayerContributionMilestone10868) -> some View {
        // The hollow/filled key only when two chances can sit side by side.
        chanceValue(
            input.beforeReading(milestone),
            title: PlayerContributionInput10868.pregameTitle,
            mark: input.phase == .during ? .hollow : nil
        )
        switch input.secondReading(milestone) {
        case .current(let current)?:
            chanceValue(current.reading, title: current.title, mark: input.showsCurrentKey(milestone) ? .filled : nil)
        case .result(let result)?:
            resultValue(result)
        case nil:
            EmptyView()
        }
    }

    private enum KeyMark { case hollow, filled }

    private func chanceValue(_ reading: PlayerContributionReading10868, title: String, mark: KeyMark?) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                if let mark { keyMark(mark) }
                Text(title).font(.caption).foregroundStyle(DS.textSecondary)
            }
            switch reading {
            case .value(let observation):
                // The whole figure keeps its width, so a narrow row stacks the
                // pair instead of squeezing or splitting a number.
                Text(observation.text)
                    .font(.system(size: chanceSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: true, vertical: false)
            case .missing(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The owner's result words — never a 0% or 100%. Unconfirmed reads as status.
    private func resultValue(_ result: PlayerContributionResult10868) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(PlayerContributionInput10868.resultTitle).font(.caption).foregroundStyle(DS.textSecondary)
            if result.isAdmitted {
                Text(result.text)
                    .font(.system(size: resultSize, weight: .bold))
                    .foregroundStyle(DS.textPrimary)
            } else {
                Text(result.text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func keyMark(_ mark: KeyMark) -> some View {
        switch mark {
        case .hollow:
            RoundedRectangle(cornerRadius: 2).fill(DS.cardBg)
                .overlay(RoundedRectangle(cornerRadius: 2).strokeBorder(tint, lineWidth: 1.5))
                .frame(width: 10, height: 10)
        case .filled:
            RoundedRectangle(cornerRadius: 2).fill(tint).frame(width: 10, height: 10)
        }
    }

    // MARK: Performance

    /// The owner's status toward the selected milestone — performance, kept
    /// apart from every chance and never shown as one.
    private func progressView(_ progress: PlayerContributionProgress10868, milestone: PlayerContributionMilestone10868) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(progress.status)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if let share = progress.fraction.flatMap({ PlayerContributionGeometry10868.fraction($0) }) {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(DS.trackBg)
                        Capsule().fill(DS.textSecondary).frame(width: geo.size.width * CGFloat(share))
                    }
                }
                .frame(height: 6)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityProgressLabel(for: milestone))
        .accessibilityValue(progress.status)
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
            if input.showsChartKey {
                chartKey
            }
            // Every milestone as a column when they fit; otherwise the same
            // milestones as bars — never clipped, capped or shrunk.
            ViewThatFits(in: .horizontal) {
                ForEach(input.orientation.forms, id: \.self) { form in
                    chartForm(form, ticks: ticks)
                }
            }
        }
    }

    @ViewBuilder private func chartForm(_ form: PlayerContributionChartForm10868,
                                        ticks: [PlayerContributionPlacedTick10868]) -> some View {
        switch form {
        case .columns: columnsChart(ticks)
        case .bars: barsChart(ticks)
        }
    }

    private var chartKey: some View {
        HStack(spacing: 14) {
            HStack(spacing: 5) {
                keyMark(.hollow)
                Text(PlayerContributionInput10868.pregameTitle)
            }
            HStack(spacing: 5) {
                keyMark(.filled)
                Text(PlayerContributionInput10868.recordedTitle)
            }
        }
        .font(.caption)
        .foregroundStyle(DS.textSecondary)
        .accessibilityHidden(true)
    }

    // MARK: Columns (points)

    private func columnsChart(_ ticks: [PlayerContributionPlacedTick10868]) -> some View {
        let fractions = ticks.map(\.fraction)
        return HStack(alignment: .top, spacing: 0) {
            if !ticks.isEmpty {
                VStack(alignment: .trailing, spacing: labelGap) {
                    valueLabelReserve
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
            ForEach(Array(input.milestones.enumerated()), id: \.offset) { _, milestone in
                column(milestone, gridlines: fractions)
            }
        }
    }

    /// A hidden one-line direct label: the axis column reserves the same
    /// height the columns reserve above their plot, so the scales line up.
    private var valueLabelReserve: some View {
        Text("0%")
            .font(.caption.bold())
            .fixedSize()
            .frame(width: 0)
            .hidden()
            .accessibilityHidden(true)
    }

    private func column(_ milestone: PlayerContributionMilestone10868, gridlines: [Double]) -> some View {
        let selected = input.isSelected(milestone)
        let action = input.milestoneAction(milestone, canSelect: canSelect)
        let row = input.row(milestone)
        return control(action) {
            VStack(spacing: 6) {
                HStack(alignment: .bottom, spacing: 4) {
                    columnBar(row.pregame, fraction: input.beforeFraction(milestone), filled: false, selected: selected)
                    if row.hasCurrentLane {
                        columnBar(row.current, fraction: input.currentFraction(milestone), filled: true, selected: selected)
                    }
                }
                .padding(.horizontal, 6)
                .frame(maxWidth: .infinity)
                .background(alignment: .bottom) {
                    columnGridlines(gridlines).frame(height: plotHeight)
                }
                VStack(spacing: 2) {
                    Text(milestone.target)
                        .font(.footnote.weight(selected ? .semibold : .regular))
                        .underline(selected)
                        .foregroundStyle(DS.textPrimary)
                    ForEach(Array(row.statuses.enumerated()), id: \.offset) { _, status in
                        statusLabel(status, alignment: .center)
                    }
                }
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 4)
            }
            .padding(.bottom, 4)
            .frame(minWidth: 44, maxWidth: .infinity, minHeight: 44)
            .background(selected ? tint.opacity(0.06) : Color.clear, in: RoundedRectangle(cornerRadius: 6))
            .contentShape(Rectangle())
        }
        .accessibilityLabel(milestone.title)
        .accessibilityValue(input.accessibilityValue(for: milestone))
        .accessibilityHint(action == nil ? "" : "Selects this milestone’s comparison")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(PlayerContributionAccessibilityID10868.milestone(milestone.id))
    }

    /// A bar with its direct label. A value the scale cannot place keeps its
    /// label and draws no bar; a reading without a mark draws neither — its
    /// words sit under the target.
    private func columnBar(_ observation: PlayerContributionObservation10868?, fraction: Double?, filled: Bool, selected: Bool) -> some View {
        PlayerContributionColumnBarLayout10868(fraction: fraction, plotHeight: plotHeight, barWidth: columnWidth, gap: labelGap) {
            if let observation {
                Text(observation.text).font(.caption.bold()).monospacedDigit().foregroundStyle(DS.textPrimary).fixedSize()
            } else {
                Text("0%").font(.caption.bold()).fixedSize().hidden()
            }
            if fraction != nil {
                barShape(filled: filled, selected: selected, dashed: false)
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

    // MARK: Bars (assists, and the columns fallback)

    private func barsChart(_ ticks: [PlayerContributionPlacedTick10868]) -> some View {
        let fractions = ticks.map(\.fraction)
        return VStack(alignment: .leading, spacing: 6) {
            if !ticks.isEmpty {
                PlayerContributionAxisLabelsLayout10868(fractions: fractions, axis: .horizontal,
                                                        inset: PlayerContributionGeometry10868.selectedLineWidth) {
                    ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                        Text(tick.text)
                            .font(.caption2)
                            .monospacedDigit()
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(.horizontal, 8)
                .accessibilityHidden(true)
            }
            ForEach(Array(input.milestones.enumerated()), id: \.offset) { _, milestone in
                barRow(milestone, gridlines: fractions)
            }
        }
    }

    private func barRow(_ milestone: PlayerContributionMilestone10868, gridlines: [Double]) -> some View {
        let selected = input.isSelected(milestone)
        let action = input.milestoneAction(milestone, canSelect: canSelect)
        let row = input.row(milestone)
        return control(action) {
            VStack(alignment: .leading, spacing: 4) {
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 4) { barLabels(milestone, row: row, selected: selected) }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .firstTextBaseline, spacing: 12) {
                            barLabels(milestone, row: row, selected: selected, spaced: true)
                        }
                        VStack(alignment: .leading, spacing: 4) { barLabels(milestone, row: row, selected: selected) }
                    }
                }
                // Readings without a mark keep their words at full row width.
                ForEach(Array(row.statuses.enumerated()), id: \.offset) { _, status in
                    statusLabel(status, alignment: .leading)
                }
                barTrack(milestone, selected: selected, gridlines: gridlines)
            }
            .padding(.vertical, 4)
            .padding(.horizontal, 8)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(selected ? tint.opacity(0.06) : Color.clear, in: RoundedRectangle(cornerRadius: 6))
            // A durable leading bar marks selection without relying on colour.
            .overlay(alignment: .leading) {
                if selected {
                    Rectangle().fill(DS.textPrimary).frame(width: 3)
                }
            }
            .contentShape(Rectangle())
        }
        .accessibilityLabel(milestone.title)
        .accessibilityValue(input.accessibilityValue(for: milestone))
        .accessibilityHint(action == nil ? "" : "Selects this milestone’s comparison")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(PlayerContributionAccessibilityID10868.milestone(milestone.id))
    }

    /// The target, then the direct values at their whole intrinsic width.
    @ViewBuilder private func barLabels(_ milestone: PlayerContributionMilestone10868, row: PlayerContributionRowPresentation10868,
                                        selected: Bool, spaced: Bool = false) -> some View {
        Text(milestone.target)
            .font(.subheadline.weight(selected ? .semibold : .regular))
            .underline(selected)
            .foregroundStyle(DS.textPrimary)
            .fixedSize(horizontal: false, vertical: true)
        if spaced { Spacer(minLength: 0) }
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            if let pregame = row.pregame {
                barValue(pregame, mark: input.phase == .during ? .hollow : nil)
            }
            if let current = row.current {
                barValue(current, mark: .filled)
            }
        }
    }

    private func barValue(_ observation: PlayerContributionObservation10868, mark: KeyMark?) -> some View {
        HStack(alignment: .center, spacing: 4) {
            if let mark { keyMark(mark) }
            Text(observation.text).font(.subheadline.bold()).monospacedDigit().foregroundStyle(DS.textPrimary).fixedSize()
        }
    }

    /// A reading without a mark: its label, when the phase needs one, then
    /// the owner's words. Wraps; never truncated or shrunk.
    private func statusLabel(_ status: PlayerContributionRowStatus10868, alignment: HorizontalAlignment) -> some View {
        VStack(alignment: alignment, spacing: 1) {
            if let title = status.title {
                Text(title).font(.caption2).foregroundStyle(DS.textSecondary)
            }
            Text(status.words).font(.caption.weight(.semibold)).foregroundStyle(DS.textSecondary)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// Gridlines at the owner's ticks, the hollow pregame bar and, during
    /// play, the filled in-game bar below it, from the same origin on the same
    /// full-width scale. Nothing is drawn for a value the scale cannot place.
    private func barTrack(_ milestone: PlayerContributionMilestone10868, selected: Bool, gridlines: [Double]) -> some View {
        let before = input.beforeFraction(milestone)
        let current = input.currentFraction(milestone)
        let lanes: CGFloat = input.phase == .during ? 2 : 1
        let laneGap: CGFloat = 3
        let inset = PlayerContributionGeometry10868.selectedLineWidth
        return GeometryReader { geo in
            let usable = geo.size.width - 2 * inset
            ZStack(alignment: .topLeading) {
                Path { path in
                    for fraction in gridlines {
                        guard let x = PlayerContributionGeometry10868.x(fraction, width: geo.size.width, inset: inset) else { continue }
                        path.move(to: CGPoint(x: x, y: 0))
                        path.addLine(to: CGPoint(x: x, y: geo.size.height))
                    }
                }
                .stroke(DS.border, style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
                if let length = PlayerContributionGeometry10868.markLength(before, extent: usable) {
                    barShape(filled: false, selected: selected, dashed: input.orientation == .bars)
                        .frame(width: length, height: laneHeight)
                        .offset(x: inset, y: 0)
                }
                if let length = PlayerContributionGeometry10868.markLength(current, extent: usable) {
                    barShape(filled: true, selected: selected, dashed: false)
                        .frame(width: length, height: laneHeight)
                        .offset(x: inset, y: laneHeight + laneGap)
                }
            }
        }
        .frame(height: laneHeight * lanes + laneGap * (lanes - 1))
        .accessibilityHidden(true)
    }

    // MARK: Marks

    /// Hollow (outlined) for pregame, filled for a recorded in-game chance.
    /// Selection thickens the outline, so it never relies on colour alone.
    @ViewBuilder private func barShape(filled: Bool, selected: Bool, dashed: Bool) -> some View {
        let lineWidth = selected ? PlayerContributionGeometry10868.selectedLineWidth : PlayerContributionGeometry10868.barLineWidth
        if filled {
            RoundedRectangle(cornerRadius: 3)
                .fill(tint.opacity(selected ? 1 : 0.7))
                .overlay(RoundedRectangle(cornerRadius: 3).strokeBorder(selected ? DS.textPrimary : Color.clear, lineWidth: lineWidth))
        } else {
            RoundedRectangle(cornerRadius: 3)
                .fill(DS.cardBg)
                .overlay(RoundedRectangle(cornerRadius: 3).strokeBorder(tint, style: StrokeStyle(lineWidth: lineWidth, dash: dashed ? [5, 3] : [])))
        }
    }

    // MARK: Choices, timing and Details

    @ViewBuilder private var chooser: some View {
        switch input.chooserPresentation(hasBinding: choicesExpanded != nil) {
        case .disclosure(let content)?:
            if let choicesExpanded {
                DisclosureGroup(isExpanded: choicesExpanded) {
                    choiceList(content)
                } label: {
                    Text(content.title)
                        .font(.footnote.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(minHeight: 44, alignment: .leading)
                }
            }
        case .expanded(let content)?:
            VStack(alignment: .leading, spacing: 4) {
                Text(content.title).font(.footnote.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                choiceList(content)
            }
        case nil:
            EmptyView()
        }
    }

    private func choiceList(_ content: PlayerContributionChooser10868) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(content.choices.enumerated()), id: \.offset) { _, choice in
                let chosen = input.isChosen(choice)
                let action = input.choiceAction(choice, canChoose: canChoose)
                control(action) {
                    HStack(spacing: 8) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(choice.name)
                                .font(.subheadline.weight(chosen ? .semibold : .regular))
                                .foregroundStyle(DS.textPrimary)
                            if let detail = choice.detail {
                                Text(detail).font(.caption).foregroundStyle(DS.textSecondary)
                            }
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 8)
                        if chosen {
                            Image(systemName: "checkmark").foregroundStyle(DS.textPrimary).accessibilityHidden(true)
                        }
                    }
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .accessibilityLabel(([choice.name, choice.detail].compactMap { $0 }).joined(separator: ", "))
                .accessibilityHint(action == nil ? "" : "Shows this player")
                .accessibilityAddTraits(chosen ? .isSelected : [])
                .accessibilityIdentifier(PlayerContributionAccessibilityID10868.choice(choice.id))
            }
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

    private func timingLines(_ content: PlayerContributionTiming10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(content.lines.enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails), let milestone = input.selection.milestone {
            Button {
                action.perform(onSelect: onSelect, onChoosePlayer: onChoosePlayer, onDetails: onDetails)
            } label: {
                HStack {
                    Text(PlayerContributionInput10868.detailsTitle)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityLabel("\(PlayerContributionInput10868.detailsTitle), \(milestone.title)")
            .accessibilityIdentifier(PlayerContributionAccessibilityID10868.details(milestone.id))
        }
    }

    // MARK: Controls

    /// A button only when the owner supplied the callback; otherwise the same
    /// content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: PlayerContributionAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                action.perform(onSelect: onSelect, onChoosePlayer: onChoosePlayer, onDetails: onDetails)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: - Player head-to-head (#10868 player-duel)

// #10868 — two named players' made and missed threes side by side, each
// beside that player's own head-to-head contract. One stateless card across
// the match: before play it shows only each player's earlier win chance or
// its explicit absence; during play it adds each player's owner-admitted
// in-game chance (or words) and actual count so far; after the final it keeps
// the earlier chance or absence and adds the final count and each contract's
// independently admitted result.
//
// Presentation only, extracted from the approved design
// (totals-final-forecast-binding-20261024 `PlayerDuelMatch` `pd-duel` card
// and `playerDuel.css`): title and context, the visible tie-payout rule, two
// equally prominent named player panels with a visible selected cue, the
// prominent made count and attempts, grouped filled/outlined shot marks beside
// each player, and each player's own labelled pregame win chance or the
// owner's words for its absence.
//
// A head-to-head contract that pays half on a tie has a contract value but no
// outright win chance, so a value in cents has no input slot here: the owner
// supplies an admitted win chance or its words, and this layer never converts,
// complements or normalizes. Made counts, attempts and shooting accuracy are
// performance, never a probability, and a result is never derived from the
// counts or from the other player's result. Every figure, unit, title, team,
// rule, result and spoken detail arrives resolved by the owner and is shown
// verbatim. Grouped marks are counts, not a shot sequence, and say so. A
// missing count draws no marks; 0 made with attempts draws missed rings; a
// count that cannot be drawn keeps the owner's words and draws nothing. Every
// valid count is drawn in full, never capped.
//
// Selection, Details and the reader stay with the host: the view keeps no
// selected state, sheet, focus or subscription, and with no callback the
// content is static. Portraits are caller-supplied views; nothing is fetched.
//
// Host binding still owed — not available at this base (see
// PLAYER-DUEL-NATIVE-BINDING-MAP.md). An owner must supply, for each player:
// the player identity, the exact original contract id and title, whole name
// and team, an admitted same-original outright pregame chance or its words,
// during play an admitted current chance or its words, the clocked count so
// far and the final count (made, attempts and their words) independently of
// any contract grade, and the independently admitted contract result; and for
// the card: the title, context, tie-payout rule and the selected original id.

/// An owner-admitted made/attempted count. `made` and `attempts` drive the
/// shot marks only; the strings are what the reader sees and hears.
nonisolated struct PlayerDuelShots10868: Equatable {
    let made: Int
    let attempts: Int
    /// "5".
    let figure: String
    /// "made"; nil draws no unit.
    let unit: String?
    /// "10 attempts".
    let attemptsText: String
    /// The owner's shooting-accuracy words ("50% from three"). Performance,
    /// never a chance. Nil draws nothing.
    let accuracy: String?
    /// "5 made in 10 attempts".
    let spoken: String
    /// Clock and source for VoiceOver ("final box score · ESPN").
    let accessibilityDetail: String
}

nonisolated enum PlayerDuelActual10868: Equatable {
    case shots(PlayerDuelShots10868)
    /// "Count unavailable".
    case unavailable(String)
}

/// One player and that player's own head-to-head contract.
nonisolated struct PlayerDuelSide10868: Equatable {
    /// Opaque player identity.
    let id: String
    /// Opaque original contract identity, passed back exactly.
    let originalID: String
    /// The original's whole title ("Will Julian Champagnie record more made
    /// three pointers than OG Anunoby?").
    let originalTitle: String
    let name: String
    /// "Spurs"; nil draws no team line.
    let team: String?
    /// An admitted outright pregame win chance, or the owner's words for its
    /// absence ("Unavailable"). Read in every phase.
    let pregame: PlayerContributionReading10868
    /// An admitted in-game win chance, currentness applied, or its words.
    /// Read only during play.
    let current: PlayerContributionReading10868
    /// Read only during play (count so far) and after the final (final count).
    let actual: PlayerDuelActual10868
    /// The owner-admitted contract result: `.reached` is a Yes resolution
    /// ("Won"), `.missed` a No ("Lost"). Read only after the final.
    let result: PlayerContributionResult10868
}

nonisolated enum PlayerDuelSelection10868: Equatable {
    case none
    case selected(PlayerDuelSide10868)
    /// No player carries the selected original id.
    case missing(String)
    /// More than one player carries the selected original id, or the one that
    /// does shares its player identity.
    case duplicate(String)

    var side: PlayerDuelSide10868? {
        if case .selected(let side) = self { return side }
        return nil
    }
}

/// How a chance is drawn: a prominent figure only for a value the 0–100%
/// scale can hold; otherwise the owner's words at reading size.
nonisolated enum PlayerDuelChanceDisplay10868: Equatable {
    case figure(PlayerContributionObservation10868)
    case words(String)
}

nonisolated enum PlayerDuelActualContent10868: Equatable {
    /// A drawable count and its marks, made first, in full.
    case counted(PlayerDuelShots10868, marks: [Bool])
    /// The owner's words: an unavailable count, or a count that cannot be drawn.
    case words(String)
}

/// The count block: its fixed title and the owner's count or words.
nonisolated struct PlayerDuelActualPresentation10868: Equatable {
    let title: String
    let content: PlayerDuelActualContent10868
}

/// Two panels side by side, or one above the other.
nonisolated enum PlayerDuelLayout10868: Hashable {
    case paired
    case stacked
}

nonisolated struct PlayerDuelInput10868: Equatable {
    let phase: PlayerContributionPhase10868
    /// "PLAYER HEAD-TO-HEAD · MADE THREES".
    let eyebrow: String?
    /// The owner's explanatory title ("Same accuracy.\nTwo more threes.").
    let title: String
    /// "Knicks 105–95 Spurs · Final"; nil draws nothing.
    let context: String?
    /// "A tie splits the payout. A separate win chance isn’t supplied."
    let payoutRule: String?
    /// In the owner's order.
    let sides: [PlayerDuelSide10868]
    /// The owner's exact original selection.
    let selectedOriginalID: String?

    static let pregameTitle = "Pregame win chance"
    static let currentTitle = "In-game win chance"
    static let selectedTitle = "Selected"
    static let shotKey = "Filled: made · outlined: missed"
    static let shotOrder = "Grouped counts, not shot order"
    static let pairUnavailable = "Head-to-head pair incomplete."
    static let selectionUnavailable = "Selected head-to-head unavailable."

    // MARK: Identity and selection

    private func isUnique(_ side: PlayerDuelSide10868) -> Bool {
        sides.filter { $0.originalID == side.originalID }.count == 1
            && sides.filter { $0.id == side.id }.count == 1
    }

    /// Exactly two players, each with its own identity and its own original.
    var isPairResolved: Bool {
        sides.count == 2 && sides.allSatisfy(isUnique)
    }

    var pairNotice: String? {
        isPairResolved ? nil : Self.pairUnavailable
    }

    /// Exact id only. A missing or shared identity gets no substitute.
    var selection: PlayerDuelSelection10868 {
        guard let selectedOriginalID else { return .none }
        let matches = sides.filter { $0.originalID == selectedOriginalID }
        switch matches.count {
        case 0: return .missing(selectedOriginalID)
        case 1: return isUnique(matches[0]) ? .selected(matches[0]) : .duplicate(selectedOriginalID)
        default: return .duplicate(selectedOriginalID)
        }
    }

    func isSelected(_ side: PlayerDuelSide10868) -> Bool {
        guard let selected = selection.side else { return false }
        return selected.originalID == side.originalID && selected.id == side.id
    }

    var selectionNotice: String? {
        switch selection {
        case .missing, .duplicate: return Self.selectionUnavailable
        case .none, .selected: return nil
        }
    }

    // MARK: Phase visibility

    static func display(_ reading: PlayerContributionReading10868) -> PlayerDuelChanceDisplay10868 {
        switch reading {
        case .value(let observation):
            PlayerContributionGeometry10868.fraction(observation.probability) == nil ? .words(observation.text) : .figure(observation)
        case .missing(let text):
            .words(text)
        }
    }

    /// The earlier chance or its words, in every phase.
    func pregame(_ side: PlayerDuelSide10868) -> PlayerDuelChanceDisplay10868 {
        Self.display(side.pregame)
    }

    /// During play only.
    func current(_ side: PlayerDuelSide10868) -> PlayerDuelChanceDisplay10868? {
        phase == .during ? Self.display(side.current) : nil
    }

    /// After the final only.
    func result(_ side: PlayerDuelSide10868) -> PlayerContributionResult10868? {
        phase == .final ? side.result : nil
    }

    /// The count block: none before play; "Count so far" during; "Final count" after.
    func actualPresentation(_ side: PlayerDuelSide10868) -> PlayerDuelActualPresentation10868? {
        let title: String
        switch phase {
        case .before: return nil
        case .during: title = PlayerContributionInput10868.countSoFarTitle
        case .final: title = PlayerContributionInput10868.finalCountTitle
        }
        switch side.actual {
        case .shots(let shots):
            if let marks = PlayerDuelGeometry10868.marks(made: shots.made, attempts: shots.attempts) {
                return PlayerDuelActualPresentation10868(title: title, content: .counted(shots, marks: marks))
            }
            return PlayerDuelActualPresentation10868(title: title, content: .words(shots.spoken))
        case .unavailable(let text):
            return PlayerDuelActualPresentation10868(title: title, content: .words(text))
        }
    }

    /// The marks drawn beside a player, or nil when none are.
    func marks(_ side: PlayerDuelSide10868) -> [Bool]? {
        guard case .counted(_, let marks)? = actualPresentation(side)?.content, !marks.isEmpty else { return nil }
        return marks
    }

    /// The filled/outlined key and the grouped-counts line, whenever marks are drawn.
    var showsShotKey: Bool {
        sides.contains { marks($0) != nil }
    }

    // MARK: Layout

    /// The forms to try, in order. Accessibility sizes always stack.
    func layouts(isAccessibilitySize: Bool) -> [PlayerDuelLayout10868] {
        isAccessibilitySize ? [.stacked] : [.paired, .stacked]
    }

    // MARK: Actions

    /// Only a player whose identity and original are its own can be selected.
    func sideAction(_ side: PlayerDuelSide10868, canSelect: Bool) -> PlayerContributionAction10868? {
        canSelect && isUnique(side) ? .select(side.originalID) : nil
    }

    func detailsAction(canOpenDetails: Bool) -> PlayerContributionAction10868? {
        guard canOpenDetails, let side = selection.side else { return nil }
        return .details(side.originalID)
    }

    // MARK: VoiceOver

    var accessibilityHeader: String {
        ([eyebrow, title].compactMap { $0 }).joined(separator: ". ")
    }

    var accessibilityShotKey: String {
        "\(Self.shotKey). \(Self.shotOrder)"
    }

    func accessibilityLabel(for side: PlayerDuelSide10868) -> String {
        ([side.name, side.team].compactMap { $0 }).joined(separator: ", ")
    }

    /// The count (and that its marks are grouped), then the pregame chance or
    /// its words, the in-game chance during play, and the result after the final.
    func accessibilityValue(for side: PlayerDuelSide10868) -> String {
        var parts: [String] = []
        if let actual = actualPresentation(side) {
            switch actual.content {
            case .counted(let shots, let marks):
                parts.append("\(actual.title): " + ([shots.spoken, shots.accuracy, shots.accessibilityDetail].compactMap { $0 }).joined(separator: ", "))
                if !marks.isEmpty { parts.append(Self.shotOrder) }
            case .words(let text):
                parts.append("\(actual.title): \(text)")
            }
        }
        parts.append(Self.spoken(side.pregame, title: Self.pregameTitle))
        if phase == .during {
            parts.append(Self.spoken(side.current, title: Self.currentTitle))
        }
        if let result = result(side) {
            parts.append("\(PlayerContributionInput10868.spokenResult): \(result.text)")
        }
        return parts.joined(separator: "; ")
    }

    private static func spoken(_ reading: PlayerContributionReading10868, title: String) -> String {
        switch reading {
        case .value(let observation): "\(title): \(observation.text), \(observation.accessibilityDetail)"
        case .missing(let text): "\(title): \(text)"
        }
    }
}

nonisolated enum PlayerDuelGeometry10868 {
    static let marksPerRow = 5

    /// One mark per attempt, made first (filled) then missed (outlined), every
    /// one kept. Nil for a count that cannot be drawn — negative, or more made
    /// than attempted — never clamped.
    static func marks(made: Int, attempts: Int) -> [Bool]? {
        guard made >= 0, attempts >= made else { return nil }
        return Array(repeating: true, count: made) + Array(repeating: false, count: attempts - made)
    }

    /// The marks in rows of `perRow`, in order; the last row may be short.
    static func rows(_ marks: [Bool], perRow: Int = marksPerRow) -> [[Bool]] {
        guard !marks.isEmpty else { return [] }
        guard perRow > 0 else { return [marks] }
        return stride(from: 0, to: marks.count, by: perRow).map { Array(marks[$0..<min($0 + perRow, marks.count)]) }
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum PlayerDuelAccessibilityID10868 {
    static func side(_ originalID: String) -> String { "playerDuel10868.side.\(originalID)" }
    static func details(_ originalID: String) -> String { "playerDuel10868.details.\(originalID)" }
    static let shotKey = "playerDuel10868.shotKey"
}

struct PlayerDuelPresentation10868: View {
    let input: PlayerDuelInput10868
    var onSelect: ((String) -> Void)? = nil
    var onDetails: ((String) -> Void)? = nil
    /// Caller-supplied portrait for an exact player id. Nil draws none; nothing
    /// is downloaded here.
    var portrait: ((String) -> AnyView)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var countSize: CGFloat = 32
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 23
    @ScaledMetric(relativeTo: .title3) private var resultSize: CGFloat = 18
    @ScaledMetric(relativeTo: .body) private var markSize: CGFloat = 12
    @ScaledMetric(relativeTo: .body) private var markGap: CGFloat = 5

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }
    /// Each panel's marks keep one token; filled and outlined carry the meaning.
    private func markTint(_ index: Int) -> Color { index % 2 == 0 ? DS.blue : DS.purple }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            if let context = input.context {
                Text(context)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let rule = input.payoutRule {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Image(systemName: "info.circle").accessibilityHidden(true)
                    Text(rule).fixedSize(horizontal: false, vertical: true)
                }
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
                .accessibilityElement(children: .combine)
            }
            ForEach(Array([input.pairNotice, input.selectionNotice].compactMap { $0 }.enumerated()), id: \.offset) { _, notice in
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !input.sides.isEmpty {
                pair
            }
            if input.showsShotKey {
                VStack(alignment: .leading, spacing: 2) {
                    Text(PlayerDuelInput10868.shotKey)
                    Text(PlayerDuelInput10868.shotOrder)
                }
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(input.accessibilityShotKey)
                .accessibilityIdentifier(PlayerDuelAccessibilityID10868.shotKey)
            }
            selectedLine
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

    // MARK: Panels

    /// Side by side while each whole name and figure fits at its natural
    /// width; otherwise stacked — never squeezed, truncated or scrolled.
    private var pair: some View {
        ViewThatFits(in: .horizontal) {
            ForEach(input.layouts(isAccessibilitySize: typeSize.isAccessibilitySize), id: \.self) { layout in
                pairForm(layout)
            }
        }
    }

    @ViewBuilder private func pairForm(_ layout: PlayerDuelLayout10868) -> some View {
        switch layout {
        case .paired:
            HStack(alignment: .top, spacing: 10) { panels(equalHeight: true) }
                .fixedSize(horizontal: false, vertical: true)
        case .stacked:
            VStack(alignment: .leading, spacing: 10) { panels(equalHeight: false) }
        }
    }

    private func panels(equalHeight: Bool) -> some View {
        ForEach(Array(input.sides.enumerated()), id: \.offset) { index, side in
            panel(side, tint: markTint(index), equalHeight: equalHeight)
        }
    }

    private func panel(_ side: PlayerDuelSide10868, tint: Color, equalHeight: Bool) -> some View {
        let selected = input.isSelected(side)
        let action = input.sideAction(side, canSelect: canSelect)
        return control(action) {
            VStack(alignment: .leading, spacing: 6) {
                identity(side, selected: selected)
                if let actual = input.actualPresentation(side) {
                    actualBlock(actual, tint: tint)
                }
                Divider()
                chanceBlock(PlayerDuelInput10868.pregameTitle, input.pregame(side))
                if let current = input.current(side) {
                    chanceBlock(PlayerDuelInput10868.currentTitle, current)
                }
                if let result = input.result(side) {
                    resultBlock(result)
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, maxHeight: equalHeight ? CGFloat.infinity : nil, alignment: .topLeading)
            .frame(minHeight: 44)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14))
            // A thicker dark outline and the "Selected" words mark selection
            // without relying on colour.
            .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(selected ? DS.textPrimary : DS.border, lineWidth: selected ? 2 : 1))
            .contentShape(RoundedRectangle(cornerRadius: 14))
        }
        .accessibilityLabel(input.accessibilityLabel(for: side))
        .accessibilityValue(input.accessibilityValue(for: side))
        .accessibilityHint(action == nil ? "" : "Selects this player’s head-to-head contract")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(PlayerDuelAccessibilityID10868.side(side.originalID))
    }

    private func identity(_ side: PlayerDuelSide10868, selected: Bool) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            if let portrait {
                portrait(side.id).accessibilityHidden(true)
            }
            if let team = side.team {
                Text(team).font(.caption2.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
            Text(side.name).font(.headline).foregroundStyle(DS.textPrimary)
            if selected {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark.circle.fill").accessibilityHidden(true)
                    Text(PlayerDuelInput10868.selectedTitle)
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// The count — prominent, labelled, with its marks beside it, and never on
    /// a probability axis.
    private func actualBlock(_ presentation: PlayerDuelActualPresentation10868, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(presentation.title).font(.caption).foregroundStyle(DS.textSecondary)
            switch presentation.content {
            case .counted(let shots, let marks):
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(shots.figure)
                        .font(.system(size: countSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                    if let unit = shots.unit {
                        Text(unit).font(.subheadline).foregroundStyle(DS.textSecondary)
                    }
                }
                Text(shots.attemptsText).font(.footnote).foregroundStyle(DS.textSecondary)
                shotMarks(marks, tint: tint)
                if let accuracy = shots.accuracy {
                    Text(accuracy).font(.footnote).foregroundStyle(DS.textSecondary)
                }
            case .words(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// Every attempt as a mark, made filled then missed outlined, in rows.
    @ViewBuilder private func shotMarks(_ marks: [Bool], tint: Color) -> some View {
        let rows = PlayerDuelGeometry10868.rows(marks)
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: markGap) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    HStack(spacing: markGap) {
                        ForEach(Array(row.enumerated()), id: \.offset) { _, made in
                            Circle()
                                .fill(made ? tint : DS.cardBg)
                                .overlay(Circle().strokeBorder(tint, lineWidth: 1.5))
                                .frame(width: markSize, height: markSize)
                        }
                    }
                }
            }
            .padding(.vertical, 2)
            .accessibilityHidden(true)
        }
    }

    private func chanceBlock(_ title: String, _ display: PlayerDuelChanceDisplay10868) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption).foregroundStyle(DS.textSecondary)
            switch display {
            case .figure(let observation):
                Text(observation.text)
                    .font(.system(size: chanceSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            case .words(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// The owner's result words — never a 0% or 100%. Unconfirmed reads as status.
    private func resultBlock(_ result: PlayerContributionResult10868) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(PlayerContributionInput10868.resultTitle).font(.caption).foregroundStyle(DS.textSecondary)
            if result.isAdmitted {
                Text(result.text).font(.system(size: resultSize, weight: .bold)).foregroundStyle(DS.textPrimary)
            } else {
                Text(result.text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: Selected original

    /// The exact selected original's title: a Details control only with the
    /// owner's callback, otherwise static text.
    @ViewBuilder private var selectedLine: some View {
        if let side = input.selection.side {
            if let action = input.detailsAction(canOpenDetails: canOpenDetails) {
                Button {
                    action.perform(onSelect: onSelect, onChoosePlayer: nil, onDetails: onDetails)
                } label: {
                    HStack {
                        Text(side.originalTitle).fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 8)
                        Image(systemName: "chevron.right").accessibilityHidden(true)
                    }
                    .font(.footnote)
                    .foregroundStyle(DS.blue)
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
                }
                .accessibilityLabel(side.originalTitle)
                .accessibilityIdentifier(PlayerDuelAccessibilityID10868.details(side.originalID))
            } else {
                Text(side.originalTitle)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: Controls

    /// A button only when the owner supplied the callback; otherwise the same
    /// content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: PlayerContributionAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                action.perform(onSelect: onSelect, onChoosePlayer: nil, onDetails: onDetails)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: - Player contract value history (#10868 player-duel)

// #10868 — the player-duel "Market value history" card: each named player's
// own head-to-head contract, its earlier and later value in cents per $1
// contract, on one 0–100¢ scale. One stateless card for one owner-admitted
// frame: before play, during play or after the final, the owner supplies the
// two endpoints, their labels, times and source words, and the change.
//
// Presentation only, extracted from the approved design
// (totals-final-forecast-binding-20261024 `PlayerDuelMovement` and
// `playerDuelMovement.css`): context and title, the visible value-per-$1 and
// tie-payout terms, an owner-labelled scale, one named row per original in
// the owner's order with its prominent change words, a neutral full track, a
// hollow earlier mark and a filled later mark joined by one solid connector
// (the same for every row), equally prominent earlier and later values each
// with its own label and time, a visible mark key, and the owner's phase
// qualifier.
//
// A contract that pays half on a tie has a value, not an outright win chance,
// so these values have their own DTO and never enter a chance slot. The
// fraction of the $1 payout drives geometry only; every figure, label, time,
// source, change, absence, tick, rule and qualifier arrives resolved by the
// owner and is shown verbatim. This layer never formats, converts to cents,
// derives a movement, normalizes, complements, interpolates, infers a result
// or settlement, ranks, combines players, reads a clock or fetches anything,
// and it never elects a phase, baseline, cutoff or endpoint. The connector
// compares two values; its length is never elapsed time and nothing between
// the two readings is drawn. Each player keeps its own times.
//
// A reading is drawn only for the row whose exact original it names, that
// original is on no other row, and its observation identity (where supplied)
// is not also the row's other own reading's; a missing, foreign or ambiguous
// reading borrows nothing and keeps words. Observation identities are opaque
// and scoped to their original: distinct originals may reuse one, and a
// foreign endpoint never takes a reading from its neighbour. A
// value of exactly 0 or 1 is a real endpoint; a non-finite or off-scale value
// keeps the owner's figure at reading size and draws no mark or connector. A
// connector needs two drawn endpoints of the same row.
//
// Selection, Details, focus and the reader stay with the host: the view keeps
// no selected state, sheet, focus or subscription, and with no callback the
// content is static.
//
// Host binding still owed — not available at this base. An owner must supply,
// for each player: the player identity, the exact original contract id and
// whole title, the whole name, the admitted earlier and later readings of that
// original (opaque observation id, raw fraction of the $1 payout, formatted
// figure, its own time and source words) or the words for each absence, the
// endpoint labels and the formatted change or its words; and for the card:
// the title, context, value and tie terms, scale ticks, the phase qualifier
// and the selected original id.

/// One owner-admitted contract value. `fractionOfDollar` drives geometry
/// only; the strings are what the reader sees and hears.
nonisolated struct PlayerDuelValueObservation10868: Equatable {
    /// The exact original this reading belongs to.
    let originalID: String
    /// Opaque observation identity, where the owner supplies one.
    let observationID: String?
    /// The raw value as a fraction of the $1 payout.
    let fractionOfDollar: Double
    /// The owner's figure ("48¢").
    let figure: String
    /// The owner's time for this reading ("Oct 3, 4:51 PM").
    let time: String
    /// The owner's source words ("traded minute close"); nil draws none.
    let source: String?
}

nonisolated enum PlayerDuelValueReading10868: Equatable {
    case value(PlayerDuelValueObservation10868)
    /// The owner's words for an absent reading ("No later captured trade").
    case missing(String)
}

/// One end of a row's comparison: the owner's label and its reading.
nonisolated struct PlayerDuelValueEndpoint10868: Equatable {
    /// "First captured", "Pre-game", "Last trade".
    let label: String
    let reading: PlayerDuelValueReading10868
}

/// One player and that player's own original contract.
nonisolated struct PlayerDuelValueRow10868: Equatable {
    /// Opaque player identity.
    let playerID: String
    /// Opaque original contract identity, passed back exactly.
    let originalID: String
    /// The original's whole title.
    let originalTitle: String
    /// The player's whole name.
    let name: String
    let earlier: PlayerDuelValueEndpoint10868
    let later: PlayerDuelValueEndpoint10868
    /// The owner's change or its words ("−3¢", "Unchanged", "No later trade").
    let change: String
}

/// A scale tick: its place as a fraction of the $1 payout and the owner's label.
nonisolated struct PlayerDuelValueTick10868: Equatable {
    let fractionOfDollar: Double
    /// "50¢".
    let text: String
}

/// How one endpoint is drawn.
nonisolated enum PlayerDuelValueDisplay10868: Equatable {
    /// The row's own value the scale can place: a mark and a prominent figure.
    case marked(PlayerDuelValueObservation10868, fraction: Double)
    /// The row's own value the scale cannot place: its figure at reading
    /// size, no mark.
    case unplaced(PlayerDuelValueObservation10868)
    /// The owner's words for an absence, or the fixed words for a reading
    /// that is not the row's own.
    case words(String)

    var fraction: Double? {
        if case .marked(_, let fraction) = self { return fraction }
        return nil
    }
}

/// The two drawn endpoints a connector joins, earlier then later.
nonisolated struct PlayerDuelValueConnector10868: Equatable {
    let earlier: Double
    let later: Double
}

nonisolated enum PlayerDuelValueSelection10868: Equatable {
    case none
    case selected(PlayerDuelValueRow10868)
    /// No row carries the selected original id.
    case missing(String)
    /// More than one row carries the selected original id, or the one that
    /// does shares its player identity.
    case duplicate(String)

    var row: PlayerDuelValueRow10868? {
        if case .selected(let row) = self { return row }
        return nil
    }
}

nonisolated struct PlayerDuelValueInput10868: Equatable {
    /// "MADE THREES · CONTRACT VALUES".
    let eyebrow: String?
    /// "How the market moved".
    let title: String
    /// The owner's matchup and phase words; nil draws nothing.
    let context: String?
    /// The owner's quantity words ("Value per $1 contract").
    let quantity: String
    /// The owner's tie terms ("A tie pays half. This is not a win probability.").
    let tieRule: String
    /// In the owner's order; only placeable ticks are drawn.
    let ticks: [PlayerDuelValueTick10868]
    /// In the owner's order.
    let rows: [PlayerDuelValueRow10868]
    /// The owner's phase qualifier ("Last trade isn’t the final result.");
    /// nil draws nothing.
    let phaseNote: String?
    /// The owner's exact original selection.
    let selectedOriginalID: String?

    static let markKey = "Hollow: earlier value · filled: later value"
    static let timesKey = "Each player has their own trade times. The line compares values, not elapsed time."
    static let valueUnavailable = "Value unavailable"
    static let selectionUnavailable = "Selected contract unavailable."
    static let spokenChange = "Change"

    // MARK: Identity and selection

    private func hasOwnOriginal(_ row: PlayerDuelValueRow10868) -> Bool {
        rows.filter { $0.originalID == row.originalID }.count == 1
    }

    private func isUnique(_ row: PlayerDuelValueRow10868) -> Bool {
        hasOwnOriginal(row) && rows.filter { $0.playerID == row.playerID }.count == 1
    }

    /// Exact id only. A missing or shared identity gets no substitute.
    var selection: PlayerDuelValueSelection10868 {
        guard let selectedOriginalID else { return .none }
        let matches = rows.filter { $0.originalID == selectedOriginalID }
        switch matches.count {
        case 0: return .missing(selectedOriginalID)
        case 1: return isUnique(matches[0]) ? .selected(matches[0]) : .duplicate(selectedOriginalID)
        default: return .duplicate(selectedOriginalID)
        }
    }

    func isSelected(_ row: PlayerDuelValueRow10868) -> Bool {
        guard let selected = selection.row else { return false }
        return selected.originalID == row.originalID && selected.playerID == row.playerID
    }

    var selectionNotice: String? {
        switch selection {
        case .missing, .duplicate: return Self.selectionUnavailable
        case .none, .selected: return nil
        }
    }

    // MARK: Endpoints

    /// True when both of this row's endpoints are own readings of its
    /// original carrying this same observation id. Ids are opaque and scoped
    /// to their original: another original may reuse one, and a foreign
    /// endpoint is refused on its own without poisoning its neighbour.
    private func repeatsWithinRow(_ observation: PlayerDuelValueObservation10868, of row: PlayerDuelValueRow10868) -> Bool {
        guard let id = observation.observationID else { return false }
        let ownIDs = [row.earlier, row.later].compactMap { endpoint -> String? in
            guard case .value(let own) = endpoint.reading, own.originalID == row.originalID else { return nil }
            return own.observationID
        }
        return ownIDs.filter { $0 == id }.count > 1
    }

    /// A reading is the row's own only when it names the row's original, that
    /// original is on no other row, and its observation id is not also the
    /// row's other own reading's.
    func display(_ endpoint: PlayerDuelValueEndpoint10868, of row: PlayerDuelValueRow10868) -> PlayerDuelValueDisplay10868 {
        switch endpoint.reading {
        case .missing(let text):
            return .words(text)
        case .value(let observation):
            guard observation.originalID == row.originalID, hasOwnOriginal(row), !repeatsWithinRow(observation, of: row) else {
                return .words(Self.valueUnavailable)
            }
            if let fraction = PlayerContributionGeometry10868.fraction(observation.fractionOfDollar) {
                return .marked(observation, fraction: fraction)
            }
            return .unplaced(observation)
        }
    }

    func earlier(_ row: PlayerDuelValueRow10868) -> PlayerDuelValueDisplay10868 {
        display(row.earlier, of: row)
    }

    func later(_ row: PlayerDuelValueRow10868) -> PlayerDuelValueDisplay10868 {
        display(row.later, of: row)
    }

    /// Only between two drawn endpoints of this row.
    func connector(_ row: PlayerDuelValueRow10868) -> PlayerDuelValueConnector10868? {
        guard let earlier = earlier(row).fraction, let later = later(row).fraction else { return nil }
        return PlayerDuelValueConnector10868(earlier: earlier, later: later)
    }

    /// The hollow/filled key, whenever any mark is drawn.
    var showsMarkKey: Bool {
        rows.contains { earlier($0).fraction != nil || later($0).fraction != nil }
    }

    /// The ticks the scale can place, in the owner's order.
    var visibleTicks: [PlayerContributionPlacedTick10868] {
        ticks.compactMap { tick in
            PlayerContributionGeometry10868.fraction(tick.fractionOfDollar).map { PlayerContributionPlacedTick10868(fraction: $0, text: tick.text) }
        }
    }

    /// The quantity and tie terms as one visible line.
    var ruleText: String {
        "\(quantity) · \(tieRule)"
    }

    // MARK: Layout

    /// The value pair's forms to try, in order. Accessibility sizes always stack.
    func layouts(isAccessibilitySize: Bool) -> [PlayerDuelLayout10868] {
        isAccessibilitySize ? [.stacked] : [.paired, .stacked]
    }

    // MARK: Actions

    /// Only a row whose identity and original are its own can be selected.
    func rowAction(_ row: PlayerDuelValueRow10868, canSelect: Bool) -> PlayerContributionAction10868? {
        canSelect && isUnique(row) ? .select(row.originalID) : nil
    }

    func detailsAction(canOpenDetails: Bool) -> PlayerContributionAction10868? {
        guard canOpenDetails, let row = selection.row else { return nil }
        return .details(row.originalID)
    }

    // MARK: VoiceOver

    var accessibilityHeader: String {
        ([eyebrow, title].compactMap { $0 }).joined(separator: ". ")
    }

    var accessibilityRule: String {
        "\(quantity). \(tieRule)"
    }

    var accessibilityKey: String {
        "\(Self.markKey). \(Self.timesKey)"
    }

    /// The quantity, the change, then each endpoint with its own label, time and source.
    func accessibilityValue(for row: PlayerDuelValueRow10868) -> String {
        [
            quantity,
            "\(Self.spokenChange): \(row.change)",
            Self.spoken(row.earlier.label, earlier(row)),
            Self.spoken(row.later.label, later(row)),
        ].joined(separator: "; ")
    }

    private static func spoken(_ label: String, _ display: PlayerDuelValueDisplay10868) -> String {
        switch display {
        case .marked(let observation, _), .unplaced(let observation):
            "\(label): " + ([observation.figure, observation.time, observation.source].compactMap { $0 }).joined(separator: ", ")
        case .words(let text):
            "\(label): \(text)"
        }
    }
}

nonisolated enum PlayerDuelValueGeometry10868 {
    static let trackLineWidth: CGFloat = 1.5
    static let tickLength: CGFloat = 12
    static let connectorLineWidth: CGFloat = 3
    static let ringLineWidth: CGFloat = 2.5

    /// The track's end inset for marks of this diameter, so a real 0 or 1
    /// mark sits wholly inside the track.
    static func inset(markDiameter: CGFloat) -> CGFloat {
        guard markDiameter.isFinite, markDiameter > 0 else { return 0 }
        return markDiameter / 2 + 1
    }

    /// The x of a drawn endpoint, or nil when it has no mark.
    static func x(_ display: PlayerDuelValueDisplay10868, width: CGFloat, inset: CGFloat) -> CGFloat? {
        guard let fraction = display.fraction else { return nil }
        return PlayerContributionGeometry10868.x(fraction, width: width, inset: inset)
    }

    /// The connector's two ends, earlier then later, or nil when there is none.
    static func span(_ connector: PlayerDuelValueConnector10868?, width: CGFloat, inset: CGFloat) -> [CGFloat]? {
        guard let connector,
              let earlier = PlayerContributionGeometry10868.x(connector.earlier, width: width, inset: inset),
              let later = PlayerContributionGeometry10868.x(connector.later, width: width, inset: inset) else { return nil }
        return [earlier, later]
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum PlayerDuelValueAccessibilityID10868 {
    static func row(_ originalID: String) -> String { "playerDuelValue10868.row.\(originalID)" }
    static func details(_ originalID: String) -> String { "playerDuelValue10868.details.\(originalID)" }
    static let key = "playerDuelValue10868.key"
}

struct PlayerDuelValuePresentation10868: View {
    let input: PlayerDuelValueInput10868
    var onSelect: ((String) -> Void)? = nil
    var onDetails: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 23
    @ScaledMetric(relativeTo: .body) private var ringSize: CGFloat = 14
    @ScaledMetric(relativeTo: .body) private var dotSize: CGFloat = 10
    @ScaledMetric(relativeTo: .body) private var keyMarkSize: CGFloat = 9
    @ScaledMetric(relativeTo: .body) private var trackHeight: CGFloat = 36

    private let rowPadding: CGFloat = 10
    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }
    private var trackInset: CGFloat { PlayerDuelValueGeometry10868.inset(markDiameter: ringSize) }
    /// Each row keeps one token; hollow and filled carry the meaning, the
    /// whole name the player.
    private func rowTint(_ index: Int) -> Color { index % 2 == 0 ? DS.blue : DS.purple }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            if let context = input.context {
                Text(context)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: "info.circle").accessibilityHidden(true)
                Text(input.ruleText).fixedSize(horizontal: false, vertical: true)
            }
            .font(.footnote)
            .foregroundStyle(DS.textSecondary)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityRule)
            if let notice = input.selectionNotice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !input.rows.isEmpty {
                rowsBlock
            }
            if input.showsMarkKey {
                markKey
            }
            if let note = input.phaseNote {
                Text(note)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            selectedLine
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

    // MARK: Rows

    private var rowsBlock: some View {
        let ticks = input.visibleTicks
        return VStack(alignment: .leading, spacing: 8) {
            if !ticks.isEmpty {
                PlayerContributionAxisLabelsLayout10868(fractions: ticks.map(\.fraction), axis: .horizontal, inset: trackInset) {
                    ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                        Text(tick.text)
                            .font(.caption2)
                            .monospacedDigit()
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                // Aligned with the track inside each row's padding and outline.
                .padding(.horizontal, rowPadding + 1)
                .accessibilityHidden(true)
            }
            ForEach(Array(input.rows.enumerated()), id: \.offset) { index, row in
                rowView(row, tint: rowTint(index), gridlines: ticks.map(\.fraction))
            }
        }
    }

    private func rowView(_ row: PlayerDuelValueRow10868, tint: Color, gridlines: [Double]) -> some View {
        let selected = input.isSelected(row)
        let action = input.rowAction(row, canSelect: canSelect)
        return control(action) {
            VStack(alignment: .leading, spacing: 6) {
                nameLine(row, selected: selected)
                track(row, tint: tint, gridlines: gridlines)
                values(row, tint: tint)
            }
            .padding(rowPadding)
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .frame(minHeight: 44)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14))
            // A thicker dark outline and the "Selected" words mark selection
            // without relying on colour.
            .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(selected ? DS.textPrimary : DS.border, lineWidth: selected ? 2 : 1))
            .contentShape(RoundedRectangle(cornerRadius: 14))
        }
        .accessibilityLabel(row.name)
        .accessibilityValue(input.accessibilityValue(for: row))
        .accessibilityHint(action == nil ? "" : "Selects this player’s contract")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(PlayerDuelValueAccessibilityID10868.row(row.originalID))
    }

    /// The whole name and the change on one line while both fit; otherwise
    /// the change below the name. Accessibility sizes always stack.
    @ViewBuilder private func nameLine(_ row: PlayerDuelValueRow10868, selected: Bool) -> some View {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 4) { nameParts(row, selected: selected) }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 10) { nameParts(row, selected: selected, spaced: true) }
                VStack(alignment: .leading, spacing: 4) { nameParts(row, selected: selected) }
            }
        }
    }

    @ViewBuilder private func nameParts(_ row: PlayerDuelValueRow10868, selected: Bool, spaced: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(row.name).font(.headline).foregroundStyle(DS.textPrimary)
            if selected {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark.circle.fill").accessibilityHidden(true)
                    Text(PlayerDuelInput10868.selectedTitle)
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        if spaced {
            Spacer(minLength: 8)
        }
        Text(row.change)
            .font(.headline.bold())
            .monospacedDigit()
            .foregroundStyle(DS.textPrimary)
            .fixedSize(horizontal: false, vertical: true)
    }

    /// The neutral full track, the owner's gridlines, one solid connector
    /// between two drawn endpoints, the hollow earlier mark and the filled
    /// later mark. Nothing is drawn for an endpoint without a mark.
    private func track(_ row: PlayerDuelValueRow10868, tint: Color, gridlines: [Double]) -> some View {
        let earlier = input.earlier(row)
        let later = input.later(row)
        let connector = input.connector(row)
        let inset = trackInset
        return GeometryReader { geo in
            let width = geo.size.width
            let mid = geo.size.height / 2
            ZStack(alignment: .topLeading) {
                Path { path in
                    path.move(to: CGPoint(x: inset, y: mid))
                    path.addLine(to: CGPoint(x: max(inset, width - inset), y: mid))
                    for fraction in gridlines {
                        guard let x = PlayerContributionGeometry10868.x(fraction, width: width, inset: inset) else { continue }
                        path.move(to: CGPoint(x: x, y: mid - PlayerDuelValueGeometry10868.tickLength / 2))
                        path.addLine(to: CGPoint(x: x, y: mid + PlayerDuelValueGeometry10868.tickLength / 2))
                    }
                }
                .stroke(DS.border, lineWidth: PlayerDuelValueGeometry10868.trackLineWidth)
                if let span = PlayerDuelValueGeometry10868.span(connector, width: width, inset: inset) {
                    Path { path in
                        path.move(to: CGPoint(x: span[0], y: mid))
                        path.addLine(to: CGPoint(x: span[1], y: mid))
                    }
                    .stroke(tint, style: StrokeStyle(lineWidth: PlayerDuelValueGeometry10868.connectorLineWidth, lineCap: .round))
                }
                if let x = PlayerDuelValueGeometry10868.x(earlier, width: width, inset: inset) {
                    Circle()
                        .fill(DS.cardBg)
                        .overlay(Circle().strokeBorder(tint, lineWidth: PlayerDuelValueGeometry10868.ringLineWidth))
                        .frame(width: ringSize, height: ringSize)
                        .position(x: x, y: mid)
                }
                // Smaller than the ring, so an unchanged value still shows both.
                if let x = PlayerDuelValueGeometry10868.x(later, width: width, inset: inset) {
                    Circle()
                        .fill(tint)
                        .frame(width: dotSize, height: dotSize)
                        .position(x: x, y: mid)
                }
            }
        }
        .frame(height: trackHeight)
        .accessibilityHidden(true)
    }

    // MARK: Values

    /// Earlier and later side by side while each whole label, figure and time
    /// fits at its natural width; otherwise stacked — never squeezed,
    /// truncated or scrolled.
    private func values(_ row: PlayerDuelValueRow10868, tint: Color) -> some View {
        ViewThatFits(in: .horizontal) {
            ForEach(input.layouts(isAccessibilitySize: typeSize.isAccessibilitySize), id: \.self) { layout in
                valuesForm(row, layout: layout, tint: tint)
            }
        }
    }

    @ViewBuilder private func valuesForm(_ row: PlayerDuelValueRow10868, layout: PlayerDuelLayout10868, tint: Color) -> some View {
        switch layout {
        case .paired:
            HStack(alignment: .top, spacing: 12) {
                endpointBlock(row.earlier.label, input.earlier(row), hollow: true, tint: tint, alignment: .leading)
                Spacer(minLength: 12)
                endpointBlock(row.later.label, input.later(row), hollow: false, tint: tint, alignment: .trailing)
            }
        case .stacked:
            VStack(alignment: .leading, spacing: 8) {
                endpointBlock(row.earlier.label, input.earlier(row), hollow: true, tint: tint, alignment: .leading)
                endpointBlock(row.later.label, input.later(row), hollow: false, tint: tint, alignment: .leading)
            }
        }
    }

    /// One endpoint: its own label beside its mark's shape, the figure (or
    /// words) and its own time and source. Earlier and later share one style.
    private func endpointBlock(_ label: String, _ display: PlayerDuelValueDisplay10868, hollow: Bool, tint: Color,
                               alignment: HorizontalAlignment) -> some View {
        let textAlignment: TextAlignment = alignment == .trailing ? .trailing : .leading
        return VStack(alignment: alignment, spacing: 3) {
            HStack(spacing: 5) {
                keyMark(hollow: hollow, tint: tint)
                Text(label)
            }
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            switch display {
            case .marked(let observation, _):
                Text(observation.figure)
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
                observationLines(observation)
            case .unplaced(let observation):
                Text(observation.figure).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
                observationLines(observation)
            case .words(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .multilineTextAlignment(textAlignment)
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private func observationLines(_ observation: PlayerDuelValueObservation10868) -> some View {
        Text(observation.time).font(.footnote).foregroundStyle(DS.textSecondary)
        if let source = observation.source {
            Text(source).font(.caption2).foregroundStyle(DS.textSecondary)
        }
    }

    private func keyMark(hollow: Bool, tint: Color) -> some View {
        Circle()
            .fill(hollow ? DS.cardBg : tint)
            .overlay(Circle().strokeBorder(tint, lineWidth: 1.5))
            .frame(width: keyMarkSize, height: keyMarkSize)
            .accessibilityHidden(true)
    }

    private var markKey: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 5) {
                keyMark(hollow: true, tint: DS.textSecondary)
                keyMark(hollow: false, tint: DS.textSecondary)
                Text(PlayerDuelValueInput10868.markKey)
            }
            Text(PlayerDuelValueInput10868.timesKey)
        }
        .font(.caption)
        .foregroundStyle(DS.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityKey)
        .accessibilityIdentifier(PlayerDuelValueAccessibilityID10868.key)
    }

    // MARK: Selected original

    /// The exact selected original's title: a Details control only with the
    /// owner's callback, otherwise static text.
    @ViewBuilder private var selectedLine: some View {
        if let row = input.selection.row {
            if let action = input.detailsAction(canOpenDetails: canOpenDetails) {
                Button {
                    action.perform(onSelect: onSelect, onChoosePlayer: nil, onDetails: onDetails)
                } label: {
                    HStack {
                        Text(row.originalTitle).fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 8)
                        Image(systemName: "chevron.right").accessibilityHidden(true)
                    }
                    .font(.footnote)
                    .foregroundStyle(DS.blue)
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
                }
                .accessibilityLabel(row.originalTitle)
                .accessibilityIdentifier(PlayerDuelValueAccessibilityID10868.details(row.originalID))
            } else {
                Text(row.originalTitle)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: Controls

    /// A button only when the owner supplied the callback; otherwise the same
    /// content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: PlayerContributionAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                action.perform(onSelect: onSelect, onChoosePlayer: nil, onDetails: onDetails)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}
