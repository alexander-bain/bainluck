import SwiftUI

// #10868 — "Both teams to score": one card across a soccer match's lifecycle.
// The ring always encodes ONE number, the selected original outcome's PREGAME
// chance. Its unfilled remainder is geometry, never the other outcome's quote:
// Yes and No are independent readings (55% and 45.5% in the retained match), so
// each outcome keeps its own figure in its own tile. Beside the ring sit both
// teams' actual goals once play has started. During play the selected outcome's
// pregame and current chances sit side by side at the same size, each with its
// own clock. After the final the ring keeps the pregame chance, the counts read
// as final goals and the outcome's independently admitted result appears.
//
// Presentation only, extracted from the approved design: `LiveSoccer.tsx`
// (SoccerStory "both"), `SoccerFinalPage.tsx` (SoccerFinalCard "both"),
// `MovingFeed.tsx` (Snack "both" before/during) and the native
// `LiveSoccer.swift` `bothTeams` panel; frames moving-feed-v102
// `both-score-phone.png`, native-card-focus-v106 `focus-both-393*.png` and
// soccer-lifecycle-journey-v301 `final-both-reader.png`.
//
// Every figure, clock, source, team name, scoring status, headline and result
// arrives resolved by the owner and is shown verbatim. This layer never formats,
// rounds, complements or normalizes a probability, never reads a clock, cache,
// subscription or admission rule, never compares the two counts to decide who
// is "still waiting", never infers a projected final, and never turns a score,
// a reached state or a settlement into a probability or a result. A last raw
// quote that the owner has not admitted as current stays in the owner's
// Details; it is not an input here. Unknown is never zero.
//
// Selection, Details, timing disclosure and focus stay with the host: the view
// keeps no selected state, no sheet and no subscription. With no callback,
// content is shown without a button and no tap is asked for. Goal milestones,
// first team to score and half-by-half expectations are separate cards.
//
// Host binding still owed — not available at this base. An owner must supply
// the exact event, market and original outcome ids; an admitted pregame
// observation per outcome (raw value, formatted figure, short and full
// time/source) or its own missing words; during play an admitted current
// observation or its own unavailable / withheld / reached words, with
// currentness already applied; a same-event clocked home/away actual goal pair
// (or each team's own unavailable words); and after the final each outcome's
// independently admitted contract result or its unconfirmed words.

/// One admitted reading. `probability` drives ring geometry only; `text` is what
/// the reader sees.
nonisolated struct BothTeamsObservation10868: Equatable {
    let probability: Double
    /// The owner's whole figure ("55%", "45.5%").
    let text: String
    /// Short clock under the figure ("4:47 AM PT"); nil draws none.
    let timeText: String?
    /// Full time and source for VoiceOver ("recorded Oct 12, 4:47 AM PT · Polymarket").
    let accessibilityDetail: String
}

nonisolated enum BothTeamsPhase10868: Equatable {
    case before
    case during
    case final
}

/// The owner's in-game state for one outcome, with currentness already applied.
nonisolated enum BothTeamsCurrent10868: Equatable {
    /// An admitted, current observation with the owner's optional movement line.
    case recorded(BothTeamsObservation10868, movement: String?)
    /// No admitted current reading ("No current chance").
    case unavailable(String)
    /// A reading exists but is not admitted as current ("No update since goal").
    case withheld(String)
    /// The sporting condition has happened ("Both teams have scored") — never a
    /// 100% chance and never a market settlement.
    case reached(String)
}

/// The original outcome's contract result. There is no Bool: a missing result is
/// never a loss.
nonisolated enum BothTeamsResult10868: Equatable {
    case won(String)
    case lost(String)
    case void(String)
    /// Not yet independently admitted ("Result pending").
    case unconfirmed(String)

    var text: String {
        switch self {
        case .won(let text), .lost(let text), .void(let text), .unconfirmed(let text): text
        }
    }
}

/// One original outcome of the both-teams-to-score market. Each reading carries
/// its own missing words. `current` is read only during play, `result` only
/// after the final.
nonisolated struct BothTeamsOutcome10868: Equatable {
    /// Exact original outcome id, passed back to the owner unchanged.
    let id: String
    /// The original outcome name ("Yes", "No").
    let label: String
    let before: BothTeamsObservation10868?
    let beforeMissing: String
    let current: BothTeamsCurrent10868
    let result: BothTeamsResult10868
}

/// One team's actual goals. `unavailable` is distinct from a real zero.
nonisolated enum BothTeamsActual10868: Equatable {
    /// The owner's whole figure ("4", "0") and optional scoring status
    /// ("has scored", "yet to score") — a sporting state, never a settlement.
    case count(text: String, status: String?)
    /// The owner's words ("Score unavailable").
    case unavailable(String)
}

nonisolated struct BothTeamsTeam10868: Equatable {
    let name: String
    let actual: BothTeamsActual10868
}

/// The same-event home/away actual pair, read only during play and after the final.
nonisolated struct BothTeamsScoring10868: Equatable {
    /// "Actual goals", "Final goals".
    let title: String
    let home: BothTeamsTeam10868
    let away: BothTeamsTeam10868
    /// Short score clock ("Recorded 5:54 AM PT"); nil draws none.
    let clock: String?
    /// Full score provenance for VoiceOver.
    let accessibilityDetail: String?
}

/// The owner's timing disclosure for one outcome. Shown only while that exact
/// outcome is the resolved selection.
nonisolated struct BothTeamsTiming10868: Equatable {
    let outcomeID: String
    let title: String
    let lines: [String]
}

/// Exact original identity, handed back to the owner on select and Details.
nonisolated struct BothTeamsOutcomeRef10868: Hashable {
    let eventID: String
    let marketID: String
    let outcomeID: String
}

nonisolated enum BothTeamsSelection10868: Equatable {
    case none
    case resolved(BothTeamsOutcome10868)
    /// No outcome carries the selected id.
    case missing(String)
    /// More than one outcome carries the selected id.
    case duplicate(String)

    var outcome: BothTeamsOutcome10868? {
        if case .resolved(let outcome) = self { return outcome }
        return nil
    }
}

nonisolated enum BothTeamsReading10868: Equatable {
    case value(BothTeamsObservation10868)
    case missing(String)
    case reached(String)
}

/// What the pregame ring shows.
nonisolated enum BothTeamsRing10868: Equatable {
    case value(label: String, observation: BothTeamsObservation10868)
    /// The selected outcome has no pregame reading: the owner's words, no arc.
    case missing(label: String, words: String)
    /// Nothing is resolved: the ring stays, named, with no arc and no figure.
    case unselected(String)
}

nonisolated enum BothTeamsAction10868: Equatable {
    case select(BothTeamsOutcomeRef10868)
    case details(BothTeamsOutcomeRef10868)

    func perform(
        onSelect: ((BothTeamsOutcomeRef10868) -> Void)?,
        onDetails: ((BothTeamsOutcomeRef10868) -> Void)?
    ) {
        switch self {
        case .select(let ref): onSelect?(ref)
        case .details(let ref): onDetails?(ref)
        }
    }
}

nonisolated enum BothTeamsTimingPresentation10868: Equatable {
    /// The page owns the expanded flag.
    case disclosure(BothTeamsTiming10868)
    /// No binding: the owner's timing content, already expanded.
    case expanded(BothTeamsTiming10868)
}

nonisolated struct BothTeamsScoreInput10868: Equatable {
    let phase: BothTeamsPhase10868
    let eventID: String
    let marketID: String
    /// "Both teams to score".
    let eyebrow: String
    /// The owner's context line ("One team is still scoreless"); nil draws none.
    let subtitle: String?
    /// The owner's headline; nil draws none. Never derived from the counts here.
    let title: String?
    /// Before play only, beside the ring ("At least one goal each").
    let beforeContext: String?
    /// Every original outcome in the owner's order — never sorted, filtered or capped.
    let outcomes: [BothTeamsOutcome10868]
    let selectedOutcomeID: String?
    let scoring: BothTeamsScoring10868
    let timing: BothTeamsTiming10868?

    static let pregameTitle = "Pregame chance"
    static let currentTitle = "Current chance"
    static let reachedTitle = "Actual so far"
    static let resultTitle = "Result"
    static let pregameShort = "Pregame"
    static let currentShort = "Current"
    static let noSelection = "No outcome selected"
    static let selectionUnavailable = "Selected outcome unavailable."
    static let chooseInstruction = "Choose an outcome to compare."
    static let detailsTitle = "Original prop & times"
    static let selectedTag = "Selected"

    // MARK: Selection

    /// Exact id only. A missing or duplicated id gets no substitute outcome, and
    /// every original outcome stays listed.
    var selection: BothTeamsSelection10868 {
        guard let selectedOutcomeID else { return .none }
        let matches = outcomes.filter { $0.id == selectedOutcomeID }
        switch matches.count {
        case 1: return .resolved(matches[0])
        case 0: return .missing(selectedOutcomeID)
        default: return .duplicate(selectedOutcomeID)
        }
    }

    func isSelected(_ outcome: BothTeamsOutcome10868) -> Bool {
        selection.outcome?.id == outcome.id
    }

    var selectionNotice: String? {
        switch selection {
        case .missing, .duplicate: Self.selectionUnavailable
        case .none, .resolved: nil
        }
    }

    func ref(_ outcome: BothTeamsOutcome10868) -> BothTeamsOutcomeRef10868 {
        BothTeamsOutcomeRef10868(eventID: eventID, marketID: marketID, outcomeID: outcome.id)
    }

    // MARK: Phase visibility

    var showsScoring: Bool { phase != .before }

    /// Nil before play — no counts, and never an invented zero.
    var visibleScoring: BothTeamsScoring10868? { showsScoring ? scoring : nil }

    var visibleBeforeContext: String? { phase == .before ? beforeContext : nil }

    /// The pregame ring, in every phase.
    var ring: BothTeamsRing10868 {
        switch selection {
        case .resolved(let outcome):
            if let before = outcome.before { return .value(label: outcome.label, observation: before) }
            return .missing(label: outcome.label, words: outcome.beforeMissing)
        case .none:
            return .unselected(Self.noSelection)
        case .missing, .duplicate:
            return .unselected(Self.selectionUnavailable)
        }
    }

    /// Names the ring and the outcome it encodes.
    var ringCaption: String {
        switch ring {
        case .value(let label, _), .missing(let label, _): "\(Self.pregameShort) · \(label)"
        case .unselected: Self.pregameTitle
        }
    }

    /// The ring's own clock before play and after the final; during play the
    /// selected comparison carries it beside the current clock.
    var ringTimeText: String? {
        guard phase != .during, case .value(_, let observation) = ring else { return nil }
        return observation.timeText
    }

    func beforeReading(_ outcome: BothTeamsOutcome10868) -> BothTeamsReading10868 {
        outcome.before.map { .value($0) } ?? .missing(outcome.beforeMissing)
    }

    /// During play only.
    func currentReading(_ outcome: BothTeamsOutcome10868) -> BothTeamsReading10868? {
        guard phase == .during else { return nil }
        switch outcome.current {
        case .recorded(let observation, _): return .value(observation)
        case .unavailable(let text), .withheld(let text): return .missing(text)
        case .reached(let text): return .reached(text)
        }
    }

    /// A reached condition is labelled as what happened, not as a chance.
    func currentTitle(_ outcome: BothTeamsOutcome10868) -> String? {
        switch currentReading(outcome) {
        case .reached?: Self.reachedTitle
        case .value?, .missing?: Self.currentTitle
        case nil: nil
        }
    }

    func currentShortTitle(_ outcome: BothTeamsOutcome10868) -> String? {
        switch currentReading(outcome) {
        case .reached?: Self.reachedTitle
        case .value?, .missing?: Self.currentShort
        case nil: nil
        }
    }

    /// The owner's movement line, only beside an admitted current observation.
    func movement(_ outcome: BothTeamsOutcome10868) -> String? {
        guard phase == .during, case .recorded(_, let movement) = outcome.current else { return nil }
        return movement
    }

    /// The filled current key appears only beside an admitted current observation.
    func showsCurrentMark(_ outcome: BothTeamsOutcome10868) -> Bool {
        if case .value? = currentReading(outcome) { return true }
        return false
    }

    /// After the final only. Any supplied current reading is ignored then, so a
    /// settled 0/100 price can never read as a chance.
    func result(_ outcome: BothTeamsOutcome10868) -> BothTeamsResult10868? {
        phase == .final ? outcome.result : nil
    }

    /// The equal pregame/current pair is a during-play comparison.
    var comparisonOutcome: BothTeamsOutcome10868? {
        phase == .during ? selection.outcome : nil
    }

    var selectedResult: (outcome: BothTeamsOutcome10868, result: BothTeamsResult10868)? {
        guard let outcome = selection.outcome, let result = result(outcome) else { return nil }
        return (outcome, result)
    }

    /// Asks for a tap only when one does something.
    func instruction(canSelect: Bool) -> String? {
        canSelect && !outcomes.isEmpty ? Self.chooseInstruction : nil
    }

    // MARK: Actions and timing

    func optionAction(_ outcome: BothTeamsOutcome10868, canSelect: Bool) -> BothTeamsAction10868? {
        canSelect ? .select(ref(outcome)) : nil
    }

    func detailsAction(canOpenDetails: Bool) -> BothTeamsAction10868? {
        guard canOpenDetails, let outcome = selection.outcome else { return nil }
        return .details(ref(outcome))
    }

    /// Timing only for the exact resolved selection.
    func timingPresentation(hasBinding: Bool) -> BothTeamsTimingPresentation10868? {
        guard let timing, let outcome = selection.outcome, outcome.id == timing.outcomeID else { return nil }
        return hasBinding ? .disclosure(timing) : .expanded(timing)
    }

    // MARK: VoiceOver

    var phaseSpoken: String {
        switch phase {
        case .before: "Before play"
        case .during: "During play"
        case .final: "Final"
        }
    }

    var accessibilityHeader: String {
        ([eyebrow, subtitle, title, phaseSpoken].compactMap { $0 }).joined(separator: ". ")
    }

    var accessibilityRing: String {
        switch ring {
        case .value(let label, let observation):
            "\(Self.pregameTitle), \(label): \(observation.text), \(observation.accessibilityDetail)"
        case .missing(let label, let words):
            "\(Self.pregameTitle), \(label): \(words)"
        case .unselected(let words):
            "\(Self.pregameTitle): \(words)"
        }
    }

    var accessibilityScoring: String? {
        guard let scoring = visibleScoring else { return nil }
        let teams = [Self.spoken(scoring.home), Self.spoken(scoring.away)].joined(separator: "; ")
        return (["\(scoring.title): \(teams)", scoring.accessibilityDetail].compactMap { $0 }).joined(separator: ". ")
    }

    /// The during-play pair: each reading with its own provenance.
    func accessibilityComparison(_ outcome: BothTeamsOutcome10868) -> String {
        var parts = [Self.spoken(beforeReading(outcome), title: Self.pregameTitle)]
        if let current = currentReading(outcome), let title = currentTitle(outcome) {
            parts.append(Self.spoken(current, title: title))
        }
        if let movement = movement(outcome) { parts.append(movement) }
        return parts.joined(separator: "; ")
    }

    /// An outcome tile: its own pregame figure, then the phase's state.
    func accessibilityOptionValue(_ outcome: BothTeamsOutcome10868) -> String {
        var parts = [Self.spokenShort(beforeReading(outcome), title: Self.pregameTitle)]
        if let current = currentReading(outcome), let title = currentTitle(outcome) {
            parts.append(Self.spokenShort(current, title: title))
        }
        if let result = result(outcome) { parts.append("\(Self.resultTitle): \(result.text)") }
        if isSelected(outcome) { parts.append(Self.selectedTag) }
        return parts.joined(separator: "; ")
    }

    func accessibilityResult(_ outcome: BothTeamsOutcome10868, _ result: BothTeamsResult10868) -> String {
        "\(Self.resultTitle) for \(outcome.label): \(result.text)"
    }

    private static func spoken(_ reading: BothTeamsReading10868, title: String) -> String {
        switch reading {
        case .value(let observation): "\(title): \(observation.text), \(observation.accessibilityDetail)"
        case .missing(let text), .reached(let text): "\(title): \(text)"
        }
    }

    private static func spokenShort(_ reading: BothTeamsReading10868, title: String) -> String {
        switch reading {
        case .value(let observation): "\(title): \(observation.text)"
        case .missing(let text), .reached(let text): "\(title): \(text)"
        }
    }

    private static func spoken(_ team: BothTeamsTeam10868) -> String {
        switch team.actual {
        case .count(let text, let status):
            (["\(team.name) \(text)", status].compactMap { $0 }).joined(separator: ", ")
        case .unavailable(let text):
            "\(team.name): \(text)"
        }
    }
}

nonisolated enum BothTeamsArrangement10868: Equatable {
    /// One subview, or more than two: stacked in order.
    case single
    case sideBySide
    case stacked
}

nonisolated struct BothTeamsColumns10868: Equatable {
    let first: CGFloat
    let second: CGFloat
}

nonisolated enum BothTeamsGeometry10868 {
    static let ringLineWidth: CGFloat = 8

    /// The ring's arc. Nil for anything outside 0...1 — bad input draws no arc,
    /// never a clipped or normalized one. A real zero is 0.
    static func ringFraction(_ probability: Double) -> Double? {
        guard probability.isFinite, probability >= 0, probability <= 1 else { return nil }
        return probability
    }

    /// Clear space from the ring's frame edge to its interior: the whole stroke
    /// (it is drawn inside the frame) plus a 4pt gap before the figure.
    static let ringInset: CGFloat = ringLineWidth + 4

    /// The ring's diameter for a figure of this measured size. The compact
    /// minimum while the figure's whole box fits inside the ring (its diagonal
    /// within the interior); otherwise just wide enough that it does. Only the
    /// ring grows — the figure is never shrunk, clipped or wrapped.
    static func ringSide(minimum: CGFloat, figure: CGSize, inset: CGFloat = ringInset) -> CGFloat {
        let diagonal = (figure.width * figure.width + figure.height * figure.height).squareRoot()
        let needed = (diagonal + 2 * inset).rounded(.up)
        guard needed.isFinite else { return minimum }
        return max(minimum, needed)
    }

    /// Side by side only when both subviews keep their whole measured width
    /// (equal columns: each column fits the wider one). Otherwise stacked.
    /// Nothing shrinks to fit.
    static func pairArrangement(
        available: CGFloat?,
        first: CGFloat,
        second: CGFloat,
        spacing: CGFloat,
        equalColumns: Bool,
        forceStack: Bool
    ) -> BothTeamsArrangement10868 {
        if forceStack { return .stacked }
        guard first.isFinite, second.isFinite, first >= 0, second >= 0 else { return .stacked }
        guard let available, available.isFinite else { return .sideBySide }
        return neededWidth(first: first, second: second, spacing: spacing, equalColumns: equalColumns) <= available
            ? .sideBySide : .stacked
    }

    static func neededWidth(first: CGFloat, second: CGFloat, spacing: CGFloat, equalColumns: Bool) -> CGFloat {
        equalColumns ? 2 * max(first, second) + spacing : first + second + spacing
    }

    /// Column widths for a side-by-side pair. Equal columns split the width;
    /// otherwise the first keeps its measured width and the second takes the rest.
    static func columns(total: CGFloat, first: CGFloat, spacing: CGFloat, equalColumns: Bool) -> BothTeamsColumns10868 {
        if equalColumns {
            let half = max(0, (total - spacing) / 2)
            return BothTeamsColumns10868(first: half, second: half)
        }
        let leading = min(max(0, first), max(0, total - spacing))
        return BothTeamsColumns10868(first: leading, second: max(0, total - spacing - leading))
    }
}

/// Two subviews side by side while both keep their whole measured width, else
/// stacked at full width. Used for the ring beside the goals, and for the
/// equal pregame/current pair.
struct BothTeamsPairLayout10868: Layout {
    var spacing: CGFloat
    var equalColumns: Bool
    var forceStack: Bool

    private func idealWidths(_ subviews: Subviews) -> BothTeamsColumns10868 {
        BothTeamsColumns10868(
            first: subviews[0].sizeThatFits(.unspecified).width,
            second: subviews[1].sizeThatFits(.unspecified).width
        )
    }

    private func arrangement(_ width: CGFloat?, _ subviews: Subviews) -> BothTeamsArrangement10868 {
        guard subviews.count == 2 else { return .single }
        let ideal = idealWidths(subviews)
        return BothTeamsGeometry10868.pairArrangement(
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
            let total = proposal.width ?? BothTeamsGeometry10868.neededWidth(
                first: ideal.first, second: ideal.second, spacing: spacing, equalColumns: equalColumns
            )
            let widths = BothTeamsGeometry10868.columns(total: total, first: ideal.first, spacing: spacing, equalColumns: equalColumns)
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
            let widths = BothTeamsGeometry10868.columns(total: bounds.width, first: ideal.first, spacing: spacing, equalColumns: equalColumns)
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

/// The pregame ring sized to its figure. Two subviews: the ring, then the
/// owner's figure. The square it reports is what the pair layout measures, so a
/// long or qualified figure ("≥99.5%") claims its real space.
struct BothTeamsRingLayout10868: Layout {
    let minimumSide: CGFloat

    private func side(_ subviews: Subviews) -> CGFloat {
        BothTeamsGeometry10868.ringSide(minimum: minimumSide, figure: subviews[1].sizeThatFits(.unspecified))
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

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum BothTeamsAccessibilityID10868 {
    static let ring = "bothTeams10868.ring"
    static let scoring = "bothTeams10868.scoring"
    static func option(_ id: String) -> String { "bothTeams10868.option.\(id)" }
    static func comparison(_ id: String) -> String { "bothTeams10868.comparison.\(id)" }
    static func result(_ id: String) -> String { "bothTeams10868.result.\(id)" }
    static func details(_ id: String) -> String { "bothTeams10868.details.\(id)" }
}

struct BothTeamsScorePresentation10868: View {
    let input: BothTeamsScoreInput10868
    var onSelect: ((BothTeamsOutcomeRef10868) -> Void)? = nil
    var onDetails: ((BothTeamsOutcomeRef10868) -> Void)? = nil
    /// Page-owned. Nil shows the owner's timing content already expanded.
    var timingExpanded: Binding<Bool>? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 30
    @ScaledMetric(relativeTo: .title) private var ringFigureSize: CGFloat = 32
    @ScaledMetric(relativeTo: .title) private var ringSize: CGFloat = 104
    @ScaledMetric(relativeTo: .title2) private var countSize: CGFloat = 28
    @ScaledMetric(relativeTo: .title3) private var optionFigureSize: CGFloat = 22

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            BothTeamsPairLayout10868(spacing: 18, equalColumns: false, forceStack: typeSize.isAccessibilitySize) {
                ringBlock
                if let scoring = input.visibleScoring {
                    scoringBlock(scoring)
                } else if let context = input.visibleBeforeContext {
                    Text(context)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if let notice = input.selectionNotice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let outcome = input.comparisonOutcome {
                comparison(outcome)
            }
            if let selected = input.selectedResult {
                resultRow(selected.outcome, selected.result)
            }
            options
            timing
            detailsButton
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
            if let subtitle = input.subtitle {
                Text(subtitle).font(.footnote).foregroundStyle(DS.textSecondary)
            }
            if let title = input.title {
                Text(title).font(.title2.bold()).foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader)
        .accessibilityAddTraits(.isHeader)
    }

    // MARK: Ring

    /// The selected outcome's pregame chance. A malformed value keeps the
    /// owner's figure on a dashed ring with no arc; a missing one, or no
    /// resolved selection, keeps the dashed ring with the words beneath — never
    /// an empty solid ring that would read as 0%.
    private var ringBlock: some View {
        VStack(alignment: .center, spacing: 6) {
            switch input.ring {
            case .value(_, let observation):
                BothTeamsRingLayout10868(minimumSide: ringSize) {
                    if let fraction = BothTeamsGeometry10868.ringFraction(observation.probability) {
                        ZStack {
                            Circle().strokeBorder(DS.trackBg, lineWidth: BothTeamsGeometry10868.ringLineWidth)
                            Circle()
                                .inset(by: BothTeamsGeometry10868.ringLineWidth / 2)
                                .trim(from: 0, to: fraction)
                                .stroke(DS.blue, style: StrokeStyle(lineWidth: BothTeamsGeometry10868.ringLineWidth, lineCap: .butt))
                                .rotationEffect(.degrees(-90))
                        }
                    } else {
                        dashedRing
                    }
                    Text(observation.text)
                        .font(.system(size: ringFigureSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                }
            case .missing(_, let words), .unselected(let words):
                dashedRing.frame(width: ringSize, height: ringSize)
                Text(words)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(input.ringCaption)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            if let time = input.ringTimeText {
                Text(time)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityRing)
        .accessibilityIdentifier(BothTeamsAccessibilityID10868.ring)
    }

    private var dashedRing: some View {
        Circle()
            .inset(by: 1)
            .stroke(DS.border, style: StrokeStyle(lineWidth: 2, dash: [4, 4]))
    }

    // MARK: Actual goals

    private func scoringBlock(_ scoring: BothTeamsScoring10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(scoring.title)
                .font(.caption.weight(.semibold))
                .textCase(.uppercase)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            teamRow(scoring.home)
            teamRow(scoring.away)
            if let clock = scoring.clock {
                Text(clock)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityScoring ?? "")
        .accessibilityIdentifier(BothTeamsAccessibilityID10868.scoring)
    }

    /// The owner's whole count; unavailable is a dash plus the owner's words, never "0".
    private func teamRow(_ team: BothTeamsTeam10868) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(team.name).font(.subheadline).foregroundStyle(DS.textPrimary)
                switch team.actual {
                case .count(_, let status):
                    if let status {
                        Text(status).font(.caption).foregroundStyle(DS.textSecondary)
                    }
                case .unavailable(let words):
                    Text(words).font(.caption).foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 12)
            Group {
                switch team.actual {
                case .count(let text, _): Text(text)
                case .unavailable: Text("—")
                }
            }
            .font(.system(size: countSize, weight: .bold))
            .monospacedDigit()
            .foregroundStyle(DS.textPrimary)
            .fixedSize()
        }
    }

    // MARK: During-play comparison

    private func comparison(_ outcome: BothTeamsOutcome10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()
            BothTeamsPairLayout10868(spacing: 16, equalColumns: true, forceStack: typeSize.isAccessibilitySize) {
                comparisonValue(
                    input.beforeReading(outcome),
                    title: "\(BothTeamsScoreInput10868.pregameTitle) · \(outcome.label)",
                    mark: .hollow,
                    movement: nil
                )
                if let current = input.currentReading(outcome), let title = input.currentTitle(outcome) {
                    comparisonValue(
                        current,
                        title: title,
                        mark: input.showsCurrentMark(outcome) ? .filled : nil,
                        movement: input.movement(outcome)
                    )
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(outcome.label)
        .accessibilityValue(input.accessibilityComparison(outcome))
        .accessibilityIdentifier(BothTeamsAccessibilityID10868.comparison(outcome.id))
    }

    private enum KeyMark { case hollow, filled }

    private func comparisonValue(_ reading: BothTeamsReading10868, title: String, mark: KeyMark?, movement: String?) -> some View {
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
                if let time = observation.timeText {
                    Text(time).font(.caption2).foregroundStyle(DS.textSecondary)
                }
            case .missing(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            case .reached(let text):
                Label(text, systemImage: "checkmark")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.emeraldDark)
            }
            if let movement {
                Text(movement).font(.caption).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func keyMark(_ mark: KeyMark) -> some View {
        switch mark {
        case .hollow:
            Circle().fill(DS.cardBg).overlay(Circle().stroke(DS.blue, lineWidth: 2)).frame(width: 9, height: 9)
        case .filled:
            Circle().fill(DS.blue).frame(width: 9, height: 9)
        }
    }

    // MARK: Final result

    private func resultRow(_ outcome: BothTeamsOutcome10868, _ result: BothTeamsResult10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: Self.resultSymbol(result))
                    .foregroundStyle(Self.isSettled(result) ? DS.textPrimary : DS.textSecondary)
                Text("\(BothTeamsScoreInput10868.resultTitle) · \(outcome.label)")
                    .foregroundStyle(DS.textSecondary)
                Text(result.text)
                    .fontWeight(.semibold)
                    .foregroundStyle(Self.isSettled(result) ? DS.textPrimary : DS.textSecondary)
            }
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityResult(outcome, result))
        .accessibilityIdentifier(BothTeamsAccessibilityID10868.result(outcome.id))
    }

    private static func resultSymbol(_ result: BothTeamsResult10868) -> String {
        switch result {
        case .won: "checkmark.circle"
        case .lost: "xmark.circle"
        case .void: "minus.circle"
        case .unconfirmed: "clock"
        }
    }

    private static func isSettled(_ result: BothTeamsResult10868) -> Bool {
        if case .unconfirmed = result { return false }
        return true
    }

    // MARK: Original outcomes

    /// Every original outcome with its own readings — the ring never stands in
    /// for the other outcome.
    @ViewBuilder private var options: some View {
        if !input.outcomes.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                if let instruction = input.instruction(canSelect: canSelect) {
                    Text(instruction)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 8) { optionTiles }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: 8) { optionTiles }
                        VStack(alignment: .leading, spacing: 8) { optionTiles }
                    }
                }
            }
        }
    }

    private var optionTiles: some View {
        ForEach(Array(input.outcomes.enumerated()), id: \.offset) { _, outcome in
            optionTile(outcome)
        }
    }

    private func optionTile(_ outcome: BothTeamsOutcome10868) -> some View {
        let selected = input.isSelected(outcome)
        let action = input.optionAction(outcome, canSelect: canSelect)
        return control(action) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(outcome.label).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textPrimary)
                    if selected {
                        Label(BothTeamsScoreInput10868.selectedTag, systemImage: "checkmark")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.blue)
                    }
                }
                optionReading(input.beforeReading(outcome), title: BothTeamsScoreInput10868.pregameShort)
                if let current = input.currentReading(outcome), let title = input.currentShortTitle(outcome) {
                    optionReading(current, title: title)
                }
                if let result = input.result(outcome) {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Image(systemName: Self.resultSymbol(result))
                        Text(result.text)
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Self.isSettled(result) ? DS.textPrimary : DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .padding(11)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(selected ? DS.blue.opacity(0.06) : DS.surface, in: RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(selected ? DS.textPrimary : DS.border, lineWidth: selected ? 2 : 1)
            )
            .contentShape(Rectangle())
        }
        .accessibilityLabel(outcome.label)
        .accessibilityValue(input.accessibilityOptionValue(outcome))
        .accessibilityHint(action == nil ? "" : "Selects this outcome’s comparison")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(BothTeamsAccessibilityID10868.option(outcome.id))
    }

    private func optionReading(_ reading: BothTeamsReading10868, title: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            switch reading {
            case .value(let observation):
                Text(observation.text)
                    .font(.system(size: optionFigureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            case .missing(let text):
                Text(text).font(.caption.weight(.semibold)).foregroundStyle(DS.textSecondary)
            case .reached(let text):
                Label(text, systemImage: "checkmark")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.emeraldDark)
            }
            Text(title).font(.caption2).foregroundStyle(DS.textSecondary)
        }
    }

    // MARK: Details and timing

    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails), let outcome = input.selection.outcome {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails)
            } label: {
                HStack {
                    Text("\(outcome.label) · \(BothTeamsScoreInput10868.detailsTitle)")
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier(BothTeamsAccessibilityID10868.details(outcome.id))
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

    private func timingLines(_ content: BothTeamsTiming10868) -> some View {
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
    private func control<Content: View>(_ action: BothTeamsAction10868?, @ViewBuilder content: () -> Content) -> some View {
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
