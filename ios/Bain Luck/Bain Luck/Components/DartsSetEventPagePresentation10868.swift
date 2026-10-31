import SwiftUI

// #10868 — the darts set-comeback screen (`darts-sets`): one native
// presentation for a darts match decided in sets, before, during and after
// play, composed from the accepted shared leaves. A fan sees, in this order:
// the match headline — the owner's eyebrow, title and About entry; each named
// player's pre-match chance or its explicit absence; during play that chance
// beside the owner's recorded chance or its words; at the final that chance
// beside the player's separately reported final sets — then the shared,
// named, shape-keyed win probability history under a paired, dated comparison
// of each player's readings at one size; then, when the owner supplies it,
// the actual-set story; then the original outcomes with the held original's
// Details. Each card opens as full-size content made of the same View and
// input; the held original's Details and the match About are further content
// modes.
//
// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: fans see both named and dated
// winner chances plus an independently selectable actual set-by-set comeback,
// full-size readers and exact original outcomes.
//
// Presentation only, from the approved `DartsSetMatch.tsx`,
// `DartsChanceReading.tsx`, `dartsReadingComparison.ts`, `DartsTradeMark.tsx`,
// `HistoryTeamMark.tsx` and `dartsSetMatch.css`, and the native adoption
// record. The references' evidence loader, trade and quote elections,
// baseline selection, exact-time lookup, set-path construction, leader and
// verdict words, clock and percent formatting and every paragraph are NOT
// ported. The leaves are the actual accepted Views, unchanged:
//
//   • `FieldPhaseHeadlinePresentation10868` — the two named players;
//   • `FieldProbabilityHistoryPresentation10868` — the anchor, its isolated
//     trade marks, exact-time inspection and key;
//   • `RugbyMatchEventPageComparisonPresentation10868` — the accepted paired,
//     dated comparison: each history original's readout slots exactly as
//     `FieldHistoryGeometry10868.readoutSlots` resolves them and as
//     `spokenSlot` speaks them, every figure at one scaled size, a missing
//     slot as its own words, separate dates, the same observation bound the
//     same way. It sits over the history inline and full size, read from the
//     same history copy the leaf beside it draws;
//   • `StoryStreamPresentationView10868` — the owner's controlled stream;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     the original outcomes and the held original's Details;
//   • `DartsEventPageAboutContent10868` — the owner's About with sources.
//
// While every history original has no choose control and no key context, the
// comparison stands in for the shared key: a presentation copy of the history
// hides that key, and the owner's history input is never changed. Otherwise
// the owner's key stays. Full-size plots use the accepted
// `RugbyMatchEventPageModel10868.readerPlotHeight`: a usable owner height,
// never shorter than inline; any other height keeps the inline one.
//
// One small immutable presentation is drawn here because no accepted leaf
// carries its grammar:
//
//   • the actual-set story — two cumulative step lines, one per player, over
//     the owner's completed sets in the owner's order, where x is a set's
//     position in that order and never elapsed time, on the owner's neutral
//     set-count scale. The owner's separately supplied origin starts each
//     line and is never a probability point and never selectable. It shows
//     the held set's cumulative score per player with the owner's unit and
//     state words, a set picker, the owner's order ticks and checkpoints, and
//     the owner's historical pre-match context: the same comparison View over
//     a presentation copy of the same history that resolves only each
//     original's own pre-match slot under the owner's own pre-match label. Its
//     order geometry, plot frame, step points, selection and identity rules
//     are the accepted `AflMatchScoringGeometry10868`, `AflMatchStepPoint10868`
//     and `AflMatchCardRules10868`; its marks are the headline's own key
//     shapes (`FieldHeadlineKeyPlan10868`).
//
// Both take arbitrary inputs — any players, any number of sets, a lead that
// changes hands — and contain no specimen name, number, id or clock.
//
// The page's phase is the owner's explicit `DartsSetEventPagePhase10868`,
// never read from a status, a clock, a quote, a score or a settlement. Before
// play only the pre-match chances, the owner's history and the originals are
// shown: an actual-set story, a later reading or a final count never is.
// During play and at the final the actual-set story shows exactly as the owner
// supplies it. A headline from another phase is not coerced: the owner's
// unavailable words show instead.
//
// OWNER-RESOLVED, NEVER DERIVED HERE: the phase and status words; each
// player's identity, name, tint, key shape and dated readings; the final
// counts; every set row's cumulative counts (geometry only), figures, winner,
// readout and state words and spoken words; the origin; the scale, its ticks
// and words; the order ticks; the checkpoints; the history's series, runs,
// marks, readouts, inspection and controls; the stream; the originals, their
// modes, readings, grades and rules; every held selection; the About and its
// sources. This layer never sums sets, never converts sets to legs or points,
// never counts total sets, never infers a winner, leader or baseline, never
// complements or normalizes two chances, never joins two trades with a line,
// never adds a settled endpoint, never aligns a set to a probability
// observation, never grades a contract from the actual score, and never
// deduplicates two observations because their figures match. A held set or
// original absent from an arrival shows the owner's unavailable words; no
// neighbour stands in, and only that exact identity restores it.
//
// INTERACTION. On the page — the headline's open and About, the anchor
// history's actions, inspection choices and plot taps, a directly mounted
// set story's expand, set, checkpoint and report controls, and the originals'
// selection — and in the Details content, the action calls the owner's
// interaction hook once and then the owner's exact callback with its exact
// value. A card inside the owner's stream calls the stream's activation hook
// instead, never the page hook as well. Full-size content, its reader controls
// and the About keep the exact callbacks: their host already holds. Selecting
// a set hands back only that set's id: it never moves the probability cursor,
// the headline, the held original or another card. Building or reading the
// view calls nothing. Without a callback there is no control and no hook call.
//
// LAYOUT. Phone and accessibility sizes stack the headline, the anchor, then
// the stories and originals. A regular or unspecified width (a Mac window)
// places the anchor beside the stories while both keep their minimum widths,
// otherwise it stacks. The comparison keeps its accepted equal-share columns
// or full-width rows; the set readout reflows by its intrinsic width; both
// stack at accessibility sizes. Plot heights are the
// owner's, never shrunk; full-size heights are never shorter than inline.
//
// The host owns the scroll, navigation, sheets, Back/Done, next/previous card,
// focus, routing, every held selection, how a hook request holds the stream,
// subscriptions and every genuine update. This view keeps no state, runs no
// timer or animation, holds no subscription and presents nothing of its own.
//
// Host binding still owed: no darts set-match page input adapter exists at
// this base. Phase and status words, player identities and dated readings,
// final counts, set rows, origin, scale, order ticks, checkpoints, history,
// stream, originals and About are unbound owner channels (named in the
// handback).

// MARK: - Phase, cards, modes

/// The owner's explicit phase for the whole screen.
nonisolated enum DartsSetEventPagePhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final
}

/// One card the page can show full size, in the page's order. `history` is the anchor.
nonisolated enum DartsSetEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// Each player's cumulative actual sets after every completed set.
    case sets
}

/// What the host's container is showing, chosen by the host.
nonisolated enum DartsSetEventPageMode10868: Equatable {
    /// The match screen body.
    case page
    /// One card's full-size content.
    case reader(DartsSetEventPageCard10868)
    /// The held original's Details.
    case original
    /// The owner's match About with its sources.
    case about
}

/// A full-size content control, handed to the host exactly.
nonisolated enum DartsSetReaderIntent10868: Equatable {
    /// The mounted card before the shown one.
    case previous(DartsSetEventPageCard10868)
    /// The mounted card after the shown one.
    case next(DartsSetEventPageCard10868)
    /// Leave full-size content for the match.
    case back
    /// Close the held original's Details or the About.
    case done
}

nonisolated enum DartsSetEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

/// The page's regions in reading order.
nonisolated enum DartsSetEventPageBlock10868: String, CaseIterable {
    case headline
    case notice
    case anchor
    case cards
    case originals
}

// MARK: - Actual-set input

/// One player in the actual-set story, in the owner's order.
nonisolated struct DartsSetPlayer10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The owner's name for the key and the readout.
    let name: String
}

/// One player's cumulative actual sets at one position, in the owner's words.
nonisolated struct DartsSetCount10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// Cumulative sets won on the owner's set-count scale; geometry only. Nil,
    /// invalid or off the scale draws no mark and breaks this player's line.
    let value: Double?
    /// The owner's figure for the count, shown verbatim.
    let figure: String
}

/// The owner's separately supplied actual origin before the first set: an
/// actual count, never a probability point, never selectable.
nonisolated struct DartsSetOrigin10868: Equatable {
    let id: String
    let counts: [DartsSetCount10868]
}

/// One completed set, in the owner's order. Its x is its position in that order.
nonisolated struct DartsSetRow10868: Equatable {
    let id: String
    /// The picker's short words.
    let label: String
    /// The readout heading for the state after this set.
    let readoutLabel: String
    /// Each player's cumulative sets after this set.
    let counts: [DartsSetCount10868]
    /// The owner's winner of this set, for its colour; nil draws the neutral
    /// colour. Never inferred from the counts.
    let winner: FieldChooserOriginalRef10868?
    /// The owner's words for the state after this set.
    let stateWords: String
    let spoken: String
}

/// One owner tick on the set-count scale.
nonisolated struct DartsSetTick10868: Equatable {
    let value: Double
    let label: String
}

/// The owner's neutral set-count scale: its extent, ticks and words. Never
/// derived from the rows.
nonisolated struct DartsSetScale10868: Equatable {
    let lower: Double
    let upper: Double
    let ticks: [DartsSetTick10868]
    /// The axis's own words; nil draws none.
    let label: String?
}

/// The owner's words under one position on the order axis (the origin or a set).
nonisolated struct DartsSetOrderTick10868: Equatable {
    let rowID: String
    let label: String
}

/// One owner checkpoint: a named set the reader can jump to.
nonisolated struct DartsSetCheckpoint10868: Equatable {
    let id: String
    let setID: String
    let label: String
    let detail: String?
}

nonisolated struct DartsSetStoryCopy10868: Equatable {
    let eyebrow: String?
    let title: String
    /// The readout's explicit unit.
    let unit: String
    /// The order axis's own words: completed sets in order, not time.
    let orderLabel: String
    /// Spoken name of the plot.
    let graphicLabel: String
    /// A note under the plot; nil draws none.
    let note: String?
    let rowsEmpty: String
    let selectionPrompt: String?
    let selectionMissing: String
    let selectHint: String?
    /// Spoken name of the set picker.
    let pickerLabel: String
    /// Spoken name of the checkpoints group.
    let checkpointsLabel: String
    /// Shown for a count whose player names no single entry.
    let countUnavailable: String
    /// The report entry (the match About); nil draws none.
    let reportLabel: String?
    let expandLabel: String
    /// The heading and spoken name of the historical pre-match context; nil
    /// draws no context.
    var contextLabel: String? = nil
}

nonisolated struct DartsSetStory10868: Equatable {
    /// The owner's players in the owner's order: one line each.
    let players: [DartsSetPlayer10868]
    var origin: DartsSetOrigin10868? = nil
    /// The owner's completed sets in the owner's order; never sorted or filtered here.
    let rows: [DartsSetRow10868]
    let scale: DartsSetScale10868
    let orderTicks: [DartsSetOrderTick10868]
    let checkpoints: [DartsSetCheckpoint10868]
    /// Host-owned exact set id.
    let selectedSetID: String?
    let plotHeight: CGFloat
    var readerPlotHeight: CGFloat? = nil
    let copy: DartsSetStoryCopy10868
}

// MARK: - Page input

/// The owner's link from a stream card id to a page card.
nonisolated struct DartsSetEventPageStory10868: Equatable {
    let cardID: String
    let card: DartsSetEventPageCard10868
    var reason: String? = nil
}

nonisolated struct DartsSetEventPageCopy10868: Equatable {
    let storiesLabel: String
    let storyUnavailable: String
    let headlineUnavailable: String
    /// Spoken name of the paired comparison.
    let comparisonLabel: String
    let heldOriginalUnavailable: String
    let backLabel: String
    let doneLabel: String
    let previousLabel: String
    let nextLabel: String
    let historyName: String
    let setsName: String
}

struct DartsSetEventPageInput10868: Equatable {
    let phase: DartsSetEventPagePhase10868
    let reader: DartsEventPageReaderHeader10868
    let headline: FieldHeadlineInput10868
    var notice: String? = nil
    let history: FieldHistoryInput10868
    /// The owner's full-size history height; never shorter than inline.
    var readerPlotHeight: CGFloat? = nil
    var sets: DartsSetStory10868? = nil
    var stream: StoryStreamPresentation10868? = nil
    var stories: [DartsSetEventPageStory10868] = []
    var about: DartsEventPageAbout10868? = nil
    let copy: DartsSetEventPageCopy10868
}

nonisolated enum DartsSetEventPageAccessibilityID10868 {
    static let page = "dartsSetEventPage10868.page"
    static let header = "dartsSetEventPage10868.header"
    static let headlineUnavailable = "dartsSetEventPage10868.headline.unavailable"
    static let notice = "dartsSetEventPage10868.notice"
    static let anchor = "dartsSetEventPage10868.anchor"
    static let stories = "dartsSetEventPage10868.stories"
    static let storyUnavailable = "dartsSetEventPage10868.story.unavailable"
    static let sets = "dartsSetEventPage10868.sets"
    static let setsPlot = "dartsSetEventPage10868.sets.plot"
    static let setsReadout = "dartsSetEventPage10868.sets.readout"
    static let setsKey = "dartsSetEventPage10868.sets.key"
    static let setsPicker = "dartsSetEventPage10868.sets.picker"
    static let checkpoints = "dartsSetEventPage10868.sets.checkpoints"
    static let report = "dartsSetEventPage10868.sets.report"
    static let setsContext = "dartsSetEventPage10868.sets.context"
    static let originals = "dartsSetEventPage10868.originals"
    static let heldUnavailable = "dartsSetEventPage10868.originals.heldUnavailable"
    static let readerHeader = "dartsSetEventPage10868.readerHeader"
    static let readerAbout = "dartsSetEventPage10868.readerHeader.about"
    static let readerBack = "dartsSetEventPage10868.reader.back"
    static let readerPrevious = "dartsSetEventPage10868.reader.previous"
    static let readerNext = "dartsSetEventPage10868.reader.next"
    static let done = "dartsSetEventPage10868.done"
    static let original = "dartsSetEventPage10868.original"
    static let about = "dartsSetEventPage10868.about"
    static func card(_ card: DartsSetEventPageCard10868) -> String { "dartsSetEventPage10868.card.\(card.rawValue)" }
    static func expand(_ card: DartsSetEventPageCard10868) -> String { "dartsSetEventPage10868.expand.\(card.rawValue)" }
    static func setPick(_ id: String) -> String { "dartsSetEventPage10868.sets.pick.\(id)" }
    static func checkpoint(_ id: String) -> String { "dartsSetEventPage10868.sets.checkpoint.\(id)" }
}

// MARK: - Actual-set geometry and model

/// One position on the order axis: the owner's origin or one completed set.
nonisolated struct DartsSetPosition10868: Equatable {
    /// Its place in the owner's order, the origin first when supplied.
    let index: Int
    let rowID: String
    /// Its place as a fraction of the plot width. Order only, never time.
    let x: Double
    /// The completed set; nil for the origin.
    let row: DartsSetRow10868?
    /// The exact id it hands back; nil for the origin or an id that is not unique.
    let selectableID: String?
    let isSelected: Bool
}

/// One player's cumulative step line.
nonisolated struct DartsSetLine10868: Equatable {
    let player: DartsSetPlayer10868
    let style: AflMatchTeamStyle10868
    /// Each position's count on the owner's scale as a fraction, in position
    /// order; nil where the count does not resolve or does not place.
    let ys: [Double?]
    let segments: [[AflMatchStepPoint10868]]
}

/// An owner tick placed on its axis as a fraction.
nonisolated struct DartsSetPlacedTick10868: Equatable {
    let position: Double
    let label: String
}

/// One owner checkpoint as the card shows it.
nonisolated struct DartsSetPlacedCheckpoint10868: Equatable {
    let checkpoint: DartsSetCheckpoint10868
    /// The exact set id it hands back; nil when its set is not exactly one owner set.
    let setID: String?
    let isSelected: Bool
}

/// One player's count in the held set's readout.
nonisolated struct DartsSetShownCount10868: Equatable {
    let player: DartsSetPlayer10868
    let style: AflMatchTeamStyle10868
    /// The owner's figure; nil when this player's count names no single entry.
    let figure: String?
}

/// The historical pre-match context the set story shows, with its owner label.
nonisolated struct DartsSetContext10868: Equatable {
    let history: FieldHistoryInput10868
    let label: String
}

/// Pure rules the set plot draws from. Unit-tested without rendering.
nonisolated enum DartsSetGeometry10868 {
    static func isValid(_ scale: DartsSetScale10868) -> Bool {
        scale.lower.isFinite && scale.upper.isFinite && scale.upper > scale.lower
    }

    /// A count's place on the owner's scale, from its lower end; nil when the
    /// scale or the count is invalid or outside it. Never clamped.
    static func fraction(_ value: Double?, in scale: DartsSetScale10868) -> Double? {
        guard let value, value.isFinite, isValid(scale), value >= scale.lower, value <= scale.upper else { return nil }
        return (value - scale.lower) / (scale.upper - scale.lower)
    }

    /// The owner's readable ticks inside the scale.
    static func ticks(_ scale: DartsSetScale10868) -> [DartsSetPlacedTick10868] {
        scale.ticks.compactMap { tick in
            guard DartsEventPageModel10868.readable(tick.label) != nil, let position = fraction(tick.value, in: scale) else { return nil }
            return DartsSetPlacedTick10868(position: position, label: tick.label)
        }
    }

    /// A cumulative step line: each placed position holds its count until the
    /// next placed position; a position that does not place breaks the line.
    static func segments(xs: [Double], ys: [Double?]) -> [[AflMatchStepPoint10868]] {
        var runs: [[AflMatchStepPoint10868]] = []
        var previous: AflMatchStepPoint10868?
        for (index, x) in xs.enumerated() {
            guard ys.indices.contains(index), let y = ys[index] else {
                previous = nil
                continue
            }
            let point = AflMatchStepPoint10868(x: x, y: y)
            if let previous, !runs.isEmpty {
                runs[runs.count - 1].append(AflMatchStepPoint10868(x: point.x, y: previous.y))
                runs[runs.count - 1].append(point)
            } else {
                runs.append([point])
            }
            previous = point
        }
        return runs
    }

    static func x(_ fraction: Double, in frame: CGRect) -> CGFloat {
        frame.minX + CGFloat(fraction) * frame.width
    }

    /// The scale's lower end at the frame's lower edge.
    static func y(_ fraction: Double, in frame: CGRect) -> CGFloat {
        frame.maxY - CGFloat(fraction) * frame.height
    }
}

nonisolated struct DartsSetStoryModel10868: Equatable {
    let story: DartsSetStory10868
    /// The page's headline at its phase, for player colours and key shapes only.
    let headline: FieldHeadlineInput10868?
    /// The page's historical pre-match context; nil draws none. Never moved by
    /// a held set, and never a source of counts.
    var context: FieldHistoryInput10868? = nil

    var copy: DartsSetStoryCopy10868 { story.copy }

    /// The context and its owner label, while both are present.
    var shownContext: DartsSetContext10868? {
        guard let context, let label = DartsEventPageModel10868.readable(copy.contextLabel) else { return nil }
        return DartsSetContext10868(history: context, label: label)
    }

    /// Only completed sets are selectable; the origin never is.
    private var ids: [String] { story.rows.map(\.id) }

    /// Every position in the owner's order: the origin first when supplied,
    /// then each completed set, evenly spaced by order.
    var positions: [DartsSetPosition10868] {
        let ids = self.ids
        let selected = selectedID
        let lead = story.origin == nil ? 0 : 1
        let count = story.rows.count + lead
        var shown: [DartsSetPosition10868] = []
        if let origin = story.origin, let x = AflMatchScoringGeometry10868.x(index: 0, count: count) {
            shown.append(DartsSetPosition10868(index: 0, rowID: origin.id, x: x, row: nil, selectableID: nil, isSelected: false))
        }
        for (offset, row) in story.rows.enumerated() {
            guard let x = AflMatchScoringGeometry10868.x(index: lead + offset, count: count) else { continue }
            let selectable = AflMatchCardRules10868.selectableID(row.id, among: ids)
            shown.append(DartsSetPosition10868(index: lead + offset, rowID: row.id, x: x, row: row,
                                               selectableID: selectable,
                                               isSelected: selectable != nil && selectable == selected))
        }
        return shown
    }

    /// The counts at one position: the origin's or the set's own.
    private func counts(_ position: DartsSetPosition10868) -> [DartsSetCount10868] {
        position.row?.counts ?? story.origin?.counts ?? []
    }

    /// The player's own count among `counts`: exactly one entry with the
    /// player's exact reference, for a player listed once. Never by position.
    static func count(_ player: DartsSetPlayer10868, in counts: [DartsSetCount10868],
                      players: [DartsSetPlayer10868]) -> DartsSetCount10868? {
        guard players.filter({ $0.ref == player.ref }).count == 1 else { return nil }
        let matches = counts.filter { $0.ref == player.ref }
        return matches.count == 1 ? matches[0] : nil
    }

    func style(_ ref: FieldChooserOriginalRef10868?) -> AflMatchTeamStyle10868 {
        AflMatchCardRules10868.style(ref, headline: headline)
    }

    /// One cumulative step line per owner player, in the owner's order.
    var lines: [DartsSetLine10868] {
        let positions = self.positions
        let xs = positions.map(\.x)
        return story.players.map { player in
            let ys = positions.map { position -> Double? in
                Self.count(player, in: counts(position), players: story.players)
                    .flatMap { DartsSetGeometry10868.fraction($0.value, in: story.scale) }
            }
            return DartsSetLine10868(player: player, style: style(player.ref), ys: ys,
                                     segments: DartsSetGeometry10868.segments(xs: xs, ys: ys))
        }
    }

    var selection: AflMatchSelection10868<DartsSetRow10868> {
        AflMatchCardRules10868.selection(story.selectedSetID, rows: story.rows, id: { $0.id },
                                         prompt: copy.selectionPrompt, missing: copy.selectionMissing)
    }

    /// The held set's id while it is exactly one owner set.
    var selectedID: String? {
        if case .row(let row, _) = selection { return row.id }
        return nil
    }

    /// The set just before or after the held one in the owner's order, while
    /// that set has its own unique id. Nothing without an exact held set.
    func neighbour(_ offset: Int) -> String? {
        guard case .row(_, let index) = selection else { return nil }
        let target = index + offset
        guard story.rows.indices.contains(target) else { return nil }
        return AflMatchCardRules10868.selectableID(story.rows[target].id, among: ids)
    }

    var earlierID: String? { neighbour(-1) }

    var laterID: String? { neighbour(1) }

    /// The held set's count per owner player, in the owner's player order.
    func shownCounts(_ row: DartsSetRow10868) -> [DartsSetShownCount10868] {
        story.players.map { player in
            DartsSetShownCount10868(
                player: player, style: style(player.ref),
                figure: Self.count(player, in: row.counts, players: story.players)
                    .flatMap { DartsEventPageModel10868.readable($0.figure) })
        }
    }

    /// The owner's order ticks whose position is exactly one origin or set.
    var orderTicks: [DartsSetPlacedTick10868] {
        let positions = self.positions
        return story.orderTicks.compactMap { tick in
            let matches = positions.filter { $0.rowID == tick.rowID }
            guard matches.count == 1, DartsEventPageModel10868.readable(tick.label) != nil else { return nil }
            return DartsSetPlacedTick10868(position: matches[0].x, label: tick.label)
        }
    }

    var scaleTicks: [DartsSetPlacedTick10868] { DartsSetGeometry10868.ticks(story.scale) }

    var checkpoints: [DartsSetPlacedCheckpoint10868] {
        let ids = self.ids
        let selected = selectedID
        return story.checkpoints.map { checkpoint in
            let id = AflMatchCardRules10868.selectableID(checkpoint.setID, among: ids)
            return DartsSetPlacedCheckpoint10868(checkpoint: checkpoint, setID: id, isSelected: id != nil && id == selected)
        }
    }

    /// The tapped position's set id, while it is a selectable set. The origin
    /// hands back nothing.
    func setID(atFraction fraction: Double) -> String? {
        let positions = self.positions
        guard let index = AflMatchScoringGeometry10868.index(atFraction: fraction, count: positions.count) else { return nil }
        return positions.first { $0.index == index }?.selectableID
    }

    /// The only way a set position acts: the host's callback with its own exact id.
    static func selectAction(_ position: DartsSetPosition10868, onSelect: ((String) -> Void)?) -> (() -> Void)? {
        guard let onSelect, let id = position.selectableID else { return nil }
        return { onSelect(id) }
    }
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
struct DartsSetEventPageModel10868: Equatable {
    let input: DartsSetEventPageInput10868

    init(_ input: DartsSetEventPageInput10868) {
        self.input = input
    }

    static func headlinePhase(_ phase: DartsSetEventPagePhase10868) -> FieldOutlookPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    static func readable(_ words: String?) -> String? {
        DartsEventPageModel10868.readable(words)
    }

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == Self.headlinePhase(input.phase) ? input.headline : nil
    }

    /// The actual-set story: never before play; during play and at the final
    /// exactly as the owner supplies it.
    var sets: DartsSetStory10868? { input.phase == .before ? nil : input.sets }

    /// The set story on the page, with the owner's historical pre-match context.
    var setsModel: DartsSetStoryModel10868? {
        sets.map { DartsSetStoryModel10868(story: $0, headline: headline, context: preMatchContext) }
    }

    /// The full-size set story: the same story and context at the owner's
    /// full-size height while usable, never shorter than inline; any other
    /// height keeps the inline one.
    var readerSetsModel: DartsSetStoryModel10868? {
        guard let shown = sets else { return nil }
        let full = DartsSetStory10868(
            players: shown.players, origin: shown.origin, rows: shown.rows, scale: shown.scale,
            orderTicks: shown.orderTicks, checkpoints: shown.checkpoints, selectedSetID: shown.selectedSetID,
            plotHeight: RugbyMatchEventPageModel10868.readerPlotHeight(shown.readerPlotHeight, history: shown.plotHeight),
            readerPlotHeight: shown.readerPlotHeight, copy: shown.copy)
        return DartsSetStoryModel10868(story: full, headline: headline, context: preMatchContext)
    }

    func isMounted(_ card: DartsSetEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .sets: sets != nil
        }
    }

    /// The mounted cards in the page's order.
    var mountedCards: [DartsSetEventPageCard10868] {
        DartsSetEventPageCard10868.allCases.filter(isMounted)
    }

    /// The mounted card just before or after `card`; nothing past either end
    /// or for a card this phase does not mount.
    func neighbour(of card: DartsSetEventPageCard10868, offset: Int) -> DartsSetEventPageCard10868? {
        let cards = mountedCards
        guard let index = cards.firstIndex(of: card), cards.indices.contains(index + offset) else { return nil }
        return cards[index + offset]
    }

    func cardName(_ card: DartsSetEventPageCard10868) -> String {
        switch card {
        case .history: input.copy.historyName
        case .sets: input.copy.setsName
        }
    }

    /// The owner's link a stream card id names: exactly one link with that id,
    /// to a story card this phase mounts. Otherwise nothing.
    func storyLink(_ cardID: String) -> DartsSetEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    /// Without a stream the mounted cards sit directly on the page.
    var showsCardsDirectly: Bool { input.stream == nil }

    func readerShows(_ card: DartsSetEventPageCard10868) -> Bool { isMounted(card) }

    /// Whether the comparison stands in for the shared key: only while the key
    /// would show nothing but the readouts the comparison shows — no original's
    /// choose control and no owner key context. Otherwise the owner's key stays.
    var hidesSharedKey: Bool {
        input.history.series.allSatisfy { $0.choose == nil && FieldHistoryGeometry10868.keyContext($0) == nil }
    }

    /// The owner's own pre-match label, from its readout intent.
    static func beforeLabel(_ readout: FieldHistoryReadoutIntent10868) -> String {
        switch readout {
        case .singleBefore(let label): label
        case .beforeAndRecorded(let label, _): label
        case .beforeAndInspected(let label, _): label
        }
    }

    /// A presentation copy of the owner's history: every series, run, mark,
    /// reading, key word, action and plot field exactly as supplied, with only
    /// the given height, expand control, readout, inspection and key
    /// visibility. The owner's input is never changed.
    static func presentationCopy(_ history: FieldHistoryInput10868, plotHeight: CGFloat,
                                 expand: FieldHistoryAction10868?, readout: FieldHistoryReadoutIntent10868,
                                 inspection: FieldHistoryInspection10868?, showsKey: Bool) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: plotHeight,
            unboundReadingWords: history.unboundReadingWords, plotUnavailableWords: history.plotUnavailableWords,
            windows: history.windows, scale: history.scale, moreOriginals: history.moreOriginals,
            details: history.details, expand: expand, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: inspection,
            layout: history.layout,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: showsKey
        )
    }

    /// The key's visibility in both history copies.
    private var presentedKey: Bool { hidesSharedKey ? false : input.history.showsKey }

    /// The history on the page: the owner's input with the duplicate key hidden.
    var presentedHistory: FieldHistoryInput10868 {
        let history = input.history
        return Self.presentationCopy(history, plotHeight: history.plotHeight, expand: history.expand,
                                     readout: history.readout, inspection: history.inspection, showsKey: presentedKey)
    }

    /// The full-size history: the same input — its series, runs, readouts and
    /// inspection unchanged — at the owner's full-size height while usable,
    /// never shorter than inline (any other height keeps the inline one),
    /// without its own expand control, with the page's key visibility.
    var readerHistory: FieldHistoryInput10868 {
        let history = input.history
        return Self.presentationCopy(
            history, plotHeight: RugbyMatchEventPageModel10868.readerPlotHeight(input.readerPlotHeight, history: history.plotHeight),
            expand: nil, readout: history.readout, inspection: history.inspection, showsKey: presentedKey)
    }

    /// The set story's historical pre-match context: a presentation copy of
    /// the same history that resolves only each original's own pre-match slot
    /// under the owner's own pre-match label, through the same shared
    /// resolver. The probability cursor is not carried, so a held trade never
    /// changes it, and no other reading, baseline or date enters it.
    var preMatchContext: FieldHistoryInput10868 {
        let history = input.history
        return Self.presentationCopy(history, plotHeight: history.plotHeight, expand: nil,
                                     readout: .singleBefore(label: Self.beforeLabel(history.readout)),
                                     inspection: nil, showsKey: false)
    }

    // MARK: Originals

    /// The owner holds a selection that opens nothing in this update. It stays
    /// the owner's; it is shown as unavailable, never replaced.
    static func heldOriginalIsUnavailable(_ originals: DartsEventPageOriginals10868?) -> Bool {
        guard let originals, originals.selection != nil else { return false }
        return OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: originals.selection) == nil
    }

    // MARK: About and entries

    var about: DartsEventPageAbout10868? {
        guard let about = input.about,
              Self.readable(about.title) != nil || about.sections.contains(where: DartsEventPageModel10868.hasWords)
        else { return nil }
        return about
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil
    }

    /// Full-size content's compact heading shows the About entry; the page has
    /// the headline's own control.
    func aboutEntry(mode: DartsSetEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode, Self.readable(input.headline.copy.aboutLabel) != nil else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    // MARK: Layout and reading order

    /// Accessibility sizes and a compact width stack; a regular or unspecified
    /// width tries the anchor beside the stories, then stacks.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [DartsSetEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }

    /// The set readout's score and words side by side while they fit; stacked
    /// at accessibility sizes.
    static func readoutArrangements(accessibilitySize: Bool) -> [DartsSetEventPageArrangement10868] {
        accessibilitySize ? [.stacked] : [.sideBySide, .stacked]
    }

    static let readingOrder: [DartsSetEventPageBlock10868] = [.headline, .notice, .anchor, .cards, .originals]

    /// VoiceOver reads the same order in every arrangement.
    static func sortPriority(_ block: DartsSetEventPageBlock10868) -> Double {
        Double(readingOrder.count - (readingOrder.firstIndex(of: block) ?? readingOrder.count))
    }
}

// MARK: - Shared drawing pieces

/// The reference's white card on the page surface.
private struct DartsSetCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}

/// The headline's own key shape in the player's colour.
private struct DartsSetIdentityKey10868: View {
    let shape: FieldHeadlineKeyShape10868
    let accent: Color

    @ScaledMetric(relativeTo: .caption) private var diameter: CGFloat = 10

    var body: some View {
        let diameter = self.diameter
        let side = FieldHeadlineGeometry10868.keyFrameSide(diameter: diameter) ?? 0
        let accent = self.accent
        let shape = self.shape
        return Canvas { context, size in
            guard let plan = FieldHeadlineGeometry10868.keyPlan(shape, hollow: false, in: size, diameter: diameter, lineWidth: 2) else { return }
            context.fill(plan.fill, with: .color(accent))
        }
        .frame(width: side, height: side)
        .accessibilityHidden(true)
    }
}

/// A card's header: the owner's eyebrow and title, and the full-card entry
/// only with a callback.
private struct DartsSetCardHeader10868: View {
    let eyebrow: String?
    let title: String
    let expandLabel: String
    let expandID: String
    var onExpand: (() -> Void)?

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                if let eyebrow = DartsEventPageModel10868.readable(eyebrow) {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let title = DartsEventPageModel10868.readable(title) {
                    Text(title)
                        .font(.title2.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.isHeader)
            if let onExpand {
                Button(action: onExpand) {
                    Image(systemName: "arrow.up.right")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(expandLabel)
                .accessibilityIdentifier(expandID)
            }
        }
    }
}

/// A text control in the reference's link style; nothing without a callback.
private struct DartsSetLink10868: View {
    let label: String
    let id: String
    var action: (() -> Void)?

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        if let action {
            Button(action: action) {
                Text(label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.blue)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(minHeight: controlSize, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(id)
        }
    }
}

private func dartsSetOwnerWords(_ words: String) -> some View {
    Text(words)
        .font(.caption)
        .foregroundStyle(DS.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
}

// MARK: - Actual-set story card

/// Each owner player's cumulative actual sets over the owner's completed sets,
/// in order, the held set's score, a set picker and the owner's checkpoints.
/// Every word and number is the owner's; it keeps no state.
struct DartsSetStoryCard10868: View {
    let model: DartsSetStoryModel10868
    var onExpand: (() -> Void)? = nil
    /// A set's exact id, for the host to hold. Never moves the probability
    /// cursor, the headline, the held original or another card.
    var onSelect: ((String) -> Void)? = nil
    /// The owner's report entry: opens the match About.
    var onReport: (() -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @ScaledMetric(relativeTo: .caption) private var gutter: CGFloat = 32
    @ScaledMetric(relativeTo: .caption) private var room: CGFloat = 12
    @ScaledMetric(relativeTo: .caption) private var markDiameter: CGFloat = 7
    @ScaledMetric(relativeTo: .caption) private var selectedDiameter: CGFloat = 12
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 26
    @ScaledMetric(relativeTo: .caption) private var tickHeight: CGFloat = 22

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            DartsSetCardHeader10868(eyebrow: model.copy.eyebrow, title: model.copy.title,
                                    expandLabel: model.copy.expandLabel,
                                    expandID: DartsSetEventPageAccessibilityID10868.expand(.sets),
                                    onExpand: onExpand)
            readout
            key
            if model.positions.isEmpty {
                dartsSetOwnerWords(model.copy.rowsEmpty)
            } else {
                if let label = DartsEventPageModel10868.readable(model.story.scale.label) {
                    Text(label)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                plot
                orderTickLabels
                    .frame(height: tickHeight)
                dartsSetOwnerWords(model.copy.orderLabel)
            }
            if let note = DartsEventPageModel10868.readable(model.copy.note) {
                dartsSetOwnerWords(note)
            }
            picker
            checkpoints
            context
            if let label = DartsEventPageModel10868.readable(model.copy.reportLabel) {
                DartsSetLink10868(label: label, id: DartsSetEventPageAccessibilityID10868.report, action: onReport)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.sets)
    }

    // MARK: Readout

    /// The held set's heading, each player's cumulative count, the owner's
    /// state words and unit — or the owner's words.
    @ViewBuilder private var readout: some View {
        switch model.selection {
        case .row(let row, _):
            let arrangements = DartsSetEventPageModel10868.readoutArrangements(accessibilitySize: typeSize.isAccessibilitySize)
            Group {
                if arrangements == [.stacked] {
                    readoutStacked(row)
                } else {
                    ViewThatFits(in: .horizontal) {
                        readoutSideBySide(row)
                        readoutStacked(row)
                    }
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(row.spoken)
            .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.setsReadout)
        case .missing(let words):
            dartsSetOwnerWords(words)
                .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.setsReadout)
        case .unheld(let prompt):
            if let prompt {
                dartsSetOwnerWords(prompt)
                    .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.setsReadout)
            }
        }
    }

    private func readoutSideBySide(_ row: DartsSetRow10868) -> some View {
        HStack(alignment: .top, spacing: 16) {
            score(row)
                .frame(maxWidth: .infinity, alignment: .leading)
            stateWords(row, alignment: .trailing)
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
    }

    private func readoutStacked(_ row: DartsSetRow10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            score(row)
            stateWords(row, alignment: .leading)
        }
    }

    /// The heading, then each player's count in the player's colour at one
    /// size, joined by a dash, then the names.
    private func score(_ row: DartsSetRow10868) -> some View {
        let shown = model.shownCounts(row)
        return VStack(alignment: .leading, spacing: 4) {
            Text(row.readoutLabel)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                ForEach(Array(shown.enumerated()), id: \.offset) { index, count in
                    if index > 0 {
                        Text("–")
                            .font(.system(size: figureSize * 0.7, weight: .regular))
                            .foregroundStyle(DS.textSecondary)
                            .accessibilityHidden(true)
                    }
                    if let figure = count.figure {
                        Text(figure)
                            .font(.system(size: figureSize, weight: .bold))
                            .monospacedDigit()
                            .foregroundStyle(count.style.accent ?? DS.textPrimary)
                            .fixedSize()
                    } else {
                        Text(model.copy.countUnavailable)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            names(shown.map { ($0.player, $0.style) })
        }
    }

    private func stateWords(_ row: DartsSetRow10868, alignment: HorizontalAlignment) -> some View {
        VStack(alignment: alignment, spacing: 4) {
            Text(row.stateWords)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            Text(model.copy.unit)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Each player's key shape and name, side by side while they fit.
    private func names(_ players: [(DartsSetPlayer10868, AflMatchTeamStyle10868)]) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) { nameViews(players) }
            VStack(alignment: .leading, spacing: 4) { nameViews(players) }
        }
    }

    private func nameViews(_ players: [(DartsSetPlayer10868, AflMatchTeamStyle10868)]) -> some View {
        ForEach(Array(players.enumerated()), id: \.offset) { _, entry in
            HStack(spacing: 4) {
                if let shape = entry.1.shape, let accent = entry.1.accent {
                    DartsSetIdentityKey10868(shape: shape, accent: accent)
                }
                Text(entry.0.name)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// The plot's key: each line's own shape, colour and name.
    private var key: some View {
        names(model.lines.map { ($0.player, $0.style) })
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.setsKey)
    }

    // MARK: Plot

    /// The owner's scale ticks in the gutter, the held set's line, each
    /// player's step line and one mark per placed position. A tap hands back
    /// the nearest selectable set's exact id; VoiceOver adjusts to the
    /// earlier or later set.
    private var plot: some View {
        let positions = model.positions
        let lines = model.lines
        let ticks = model.scaleTicks
        let gutter = self.gutter
        let room = self.room
        let markDiameter = self.markDiameter
        let selectedDiameter = self.selectedDiameter
        let gridColor = DS.border
        let labelColor = DS.textSecondary
        let heldColor = DS.textSecondary
        let neutral = DS.textSecondary
        let ring = DS.cardBg
        let model = self.model
        let onSelect = self.onSelect
        return GeometryReader { proxy in
            let size = proxy.size
            Canvas { context, size in
                guard let frame = AflMatchScoringGeometry10868.plotFrame(in: size, gutter: gutter, room: room) else { return }
                func point(_ x: Double, _ y: Double) -> CGPoint {
                    CGPoint(x: DartsSetGeometry10868.x(x, in: frame), y: DartsSetGeometry10868.y(y, in: frame))
                }
                for tick in ticks {
                    var line = Path()
                    let y = DartsSetGeometry10868.y(tick.position, in: frame)
                    line.move(to: CGPoint(x: frame.minX, y: y))
                    line.addLine(to: CGPoint(x: frame.maxX, y: y))
                    context.stroke(line, with: .color(gridColor), lineWidth: 1)
                    var text = context.resolve(Text(tick.label).font(.caption2))
                    text.shading = .color(labelColor)
                    context.draw(text, at: CGPoint(x: frame.minX - 6, y: y), anchor: .trailing)
                }
                if let held = positions.first(where: \.isSelected) {
                    var line = Path()
                    let x = DartsSetGeometry10868.x(held.x, in: frame)
                    line.move(to: CGPoint(x: x, y: frame.minY))
                    line.addLine(to: CGPoint(x: x, y: frame.maxY))
                    context.stroke(line, with: .color(heldColor), style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
                }
                for line in lines {
                    let tint = line.style.accent ?? neutral
                    for run in line.segments where run.count > 1 {
                        var path = Path()
                        path.move(to: point(run[0].x, run[0].y))
                        for step in run.dropFirst() {
                            path.addLine(to: point(step.x, step.y))
                        }
                        context.stroke(path, with: .color(tint), lineWidth: 3)
                    }
                }
                for line in lines {
                    let tint = line.style.accent ?? neutral
                    let shape = line.style.shape ?? .circle
                    for (index, position) in positions.enumerated() {
                        guard line.ys.indices.contains(index), let y = line.ys[index] else { continue }
                        let diameter = position.isSelected ? selectedDiameter : markDiameter
                        let extent = diameter * FieldHeadlineGeometry10868.keyExtent(shape)
                        let center = point(position.x, y)
                        let rect = CGRect(x: center.x - extent / 2, y: center.y - extent / 2, width: extent, height: extent)
                        let mark = FieldHeadlineKeyPlan10868.path(shape, in: rect)
                        context.fill(mark, with: .color(tint))
                        if position.isSelected {
                            context.stroke(mark, with: .color(ring), lineWidth: 2)
                        }
                    }
                }
            }
            .contentShape(Rectangle())
            .onTapGesture(coordinateSpace: .local) { location in
                guard let onSelect,
                      let frame = AflMatchScoringGeometry10868.plotFrame(in: size, gutter: gutter, room: room),
                      frame.width > 0,
                      let id = model.setID(atFraction: Double((location.x - frame.minX) / frame.width))
                else { return }
                onSelect(id)
            }
        }
        .frame(height: FieldHistoryGeometry10868.plotHeight(model.story.plotHeight))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.copy.graphicLabel)
        .accessibilityValue(selectionWords)
        .accessibilityHint(model.copy.selectHint ?? "")
        .modifier(DartsSetAdjustable10868(earlier: adjust(model.earlierID), later: adjust(model.laterID)))
        .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.setsPlot)
    }

    private var selectionWords: String {
        switch model.selection {
        case .row(let row, _): row.spoken
        case .missing(let words): words
        case .unheld(let prompt): prompt ?? ""
        }
    }

    private func adjust(_ id: String?) -> (() -> Void)? {
        guard let id, let onSelect else { return nil }
        return { onSelect(id) }
    }

    /// The owner's order ticks under their own positions.
    private var orderTickLabels: some View {
        let ticks = model.orderTicks
        let gutter = self.gutter
        let room = self.room
        let labelColor = DS.textSecondary
        return Canvas { context, size in
            guard let frame = AflMatchScoringGeometry10868.plotFrame(
                in: CGSize(width: size.width, height: max(size.height, room * 2 + 1)), gutter: gutter, room: room) else { return }
            for tick in ticks {
                var text = context.resolve(Text(tick.label).font(.caption2.weight(.semibold)))
                text.shading = .color(labelColor)
                let anchor: UnitPoint = tick.position <= 0 ? .leading : (tick.position >= 1 ? .trailing : .center)
                context.draw(text, at: CGPoint(x: DartsSetGeometry10868.x(tick.position, in: frame), y: size.height / 2),
                             anchor: anchor)
            }
        }
        .accessibilityHidden(true)
    }

    // MARK: Controls

    /// One control per owner set, in the owner's order, in the set winner's
    /// colour; reflows by the available width. Nothing without a callback.
    @ViewBuilder private var picker: some View {
        let picks = model.positions.filter { $0.row != nil }
        if let onSelect, !picks.isEmpty {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: controlSize), spacing: 6)], alignment: .leading, spacing: 6) {
                ForEach(Array(picks.enumerated()), id: \.offset) { _, position in
                    pick(position, onSelect: onSelect)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(model.copy.pickerLabel)
            .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.setsPicker)
        }
    }

    @ViewBuilder private func pick(_ position: DartsSetPosition10868, onSelect: @escaping (String) -> Void) -> some View {
        if let row = position.row {
            let tint = model.style(row.winner).accent ?? DS.textSecondary
            let chip = Text(row.label)
                .font(.subheadline.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(position.isSelected ? DS.cardBg : tint)
                .fixedSize()
                .frame(minWidth: controlSize, minHeight: controlSize)
                .background(position.isSelected ? tint : DS.cardBg, in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(tint, lineWidth: 1.5))
            if let action = DartsSetStoryModel10868.selectAction(position, onSelect: onSelect) {
                Button(action: action) { chip.contentShape(Rectangle()) }
                    .buttonStyle(.plain)
                    .accessibilityLabel(row.spoken)
                    .accessibilityHint(model.copy.selectHint ?? "")
                    .accessibilityAddTraits(position.isSelected ? .isSelected : [])
                    .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.setPick(row.id))
            } else {
                chip
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(row.spoken)
                    .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.setPick(row.id))
            }
        }
    }

    /// The owner's historical pre-match context under its own heading: the
    /// accepted comparison View over the page's pre-match history copy. No
    /// action of its own; it never follows the held set.
    @ViewBuilder private var context: some View {
        if let shown = model.shownContext {
            VStack(alignment: .leading, spacing: 8) {
                Text(shown.label)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                RugbyMatchEventPageComparisonPresentation10868(history: shown.history, label: shown.label)
            }
            .padding(.top, 10)
            .overlay(alignment: .top) { Rectangle().fill(DS.border).frame(height: 1) }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.setsContext)
        }
    }

    /// The owner's checkpoints, each handing back its exact set; one that
    /// names no single set keeps its words without a control.
    @ViewBuilder private var checkpoints: some View {
        let shown = model.checkpoints
        if !shown.isEmpty {
            let layout = typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 6))
                : AnyLayout(HStackLayout(alignment: .top, spacing: 6))
            layout {
                ForEach(Array(shown.enumerated()), id: \.offset) { _, placed in
                    checkpointControl(placed)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(model.copy.checkpointsLabel)
            .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.checkpoints)
        }
    }

    @ViewBuilder private func checkpointControl(_ placed: DartsSetPlacedCheckpoint10868) -> some View {
        let content = VStack(alignment: .leading, spacing: 3) {
            Text(placed.checkpoint.label)
                .font(.caption.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
            if let detail = DartsEventPageModel10868.readable(placed.checkpoint.detail) {
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, minHeight: controlSize, alignment: .leading)
        .background(placed.isSelected ? DS.cardBg : DS.surface, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(placed.isSelected ? DS.blue : DS.border, lineWidth: 1))
        if let onSelect, let id = placed.setID {
            Button { onSelect(id) } label: { content.foregroundStyle(placed.isSelected ? DS.blue : DS.textPrimary) }
                .buttonStyle(.plain)
                .accessibilityAddTraits(placed.isSelected ? .isSelected : [])
                .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.checkpoint(placed.checkpoint.id))
        } else {
            content
                .foregroundStyle(DS.textPrimary)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.checkpoint(placed.checkpoint.id))
        }
    }
}

/// VoiceOver's adjustable action on the set plot: the earlier or later set's
/// exact id; nothing without a target.
private struct DartsSetAdjustable10868: ViewModifier {
    let earlier: (() -> Void)?
    let later: (() -> Void)?

    func body(content: Content) -> some View {
        if earlier == nil && later == nil {
            content
        } else {
            content.accessibilityAdjustableAction { direction in
                switch direction {
                case .increment: later?()
                case .decrement: earlier?()
                @unknown default: break
                }
            }
        }
    }
}

// MARK: - Page view

struct DartsSetEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: DartsSetEventPageInput10868
    var mode: DartsSetEventPageMode10868 = .page
    /// The page's originals and the Details mode; nil: none.
    var originals: DartsEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's About.
    var onAbout: (() -> Void)? = nil
    /// A source's exact identity, for the host to open.
    var onSource: ((DartsEventPageSource10868) -> Void)? = nil
    /// An original's exact selection, for the host to hold and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// A headline player's exact open, for the host's history.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Opens the host's reader on a card mounted directly on the page.
    var onCardOpen: ((DartsSetEventPageCard10868) -> Void)? = nil
    /// A set's exact id, for the host to hold.
    var onSetSelect: ((String) -> Void)? = nil
    /// Full-size content's own controls, exactly.
    var onReaderIntent: ((DartsSetReaderIntent10868) -> Void)? = nil
    /// Called once just before a page or Details action reaches its owner
    /// callback, so the owner can hold. Never called by building the view, by
    /// full-size content, by the About or by a stream card.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var storiesMinWidth: CGFloat = 340
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: DartsSetEventPageModel10868 { DartsSetEventPageModel10868(input) }

    // MARK: Relays

    /// A stream card's own action, after the stream's activation hook. No host
    /// callback: no action at all.
    static func relay<Value>(_ action: ((Value) -> Void)?,
                             through activation: StoryStreamCardActivation10868?) -> ((Value) -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return { value in
            activation.request()
            action(value)
        }
    }

    static func relayAction(_ action: (() -> Void)?, through activation: StoryStreamCardActivation10868?) -> (() -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return {
            activation.request()
            action()
        }
    }

    /// A page or Details action, after the owner's interaction hook. No host
    /// callback: no action and no hook call.
    static func held<Value>(_ action: ((Value) -> Void)?, by interaction: (() -> Void)?) -> ((Value) -> Void)? {
        guard let action else { return nil }
        guard let interaction else { return action }
        return { value in
            interaction()
            action(value)
        }
    }

    static func heldAction(_ action: (() -> Void)?, by interaction: (() -> Void)?) -> (() -> Void)? {
        guard let action else { return nil }
        guard let interaction else { return action }
        return {
            interaction()
            action()
        }
    }

    /// A card-valued callback bound to one card.
    static func bind(_ action: ((DartsSetEventPageCard10868) -> Void)?, _ card: DartsSetEventPageCard10868) -> (() -> Void)? {
        guard let action else { return nil }
        return { action(card) }
    }

    /// A reader intent callback bound to one intent.
    static func bind(_ action: ((DartsSetReaderIntent10868) -> Void)?, _ intent: DartsSetReaderIntent10868) -> (() -> Void)? {
        guard let action else { return nil }
        return { action(intent) }
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .original: originalMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    /// The host's About opener; nil without readable About text or a callback.
    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    /// The match headline at the page's phase only; its open and About pass
    /// the interaction hook first.
    func headlineContent() -> FieldPhaseHeadlinePresentation10868? {
        model.headline.map {
            FieldPhaseHeadlinePresentation10868(input: $0, onAbout: Self.heldAction(aboutOpener(), by: onInteraction),
                                                onOpen: Self.held(onHeadlineOpen, by: onInteraction))
        }
    }

    /// The anchor passes the interaction hook first; the full-size history
    /// keeps the exact callbacks.
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let interaction = reader ? nil : onInteraction
        return FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : model.presentedHistory,
            onAction: Self.held(onHistoryAction, by: interaction),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: interaction),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: interaction)
        )
    }

    /// The accepted comparison View over the same history copy the leaf
    /// beside it draws: the same readouts inline and full size. No action.
    func comparisonContent(reader: Bool) -> RugbyMatchEventPageComparisonPresentation10868 {
        RugbyMatchEventPageComparisonPresentation10868(
            history: reader ? model.readerHistory : model.presentedHistory, label: input.copy.comparisonLabel)
    }

    /// The set story mounted directly on the page: every action after the
    /// interaction hook.
    func pageSetsContent() -> DartsSetStoryCard10868? {
        guard model.showsCardsDirectly, let story = model.setsModel else { return nil }
        return DartsSetStoryCard10868(
            model: story,
            onExpand: Self.heldAction(Self.bind(onCardOpen, .sets), by: onInteraction),
            onSelect: Self.held(onSetSelect, by: onInteraction),
            onReport: Self.heldAction(aboutOpener(), by: onInteraction))
    }

    /// The set story in a stream cell: every action after the stream's
    /// activation hook, never the page hook as well. The stream offers its own
    /// "Open full card".
    func streamSetsContent(activation: StoryStreamCardActivation10868) -> DartsSetStoryCard10868? {
        guard let story = model.setsModel else { return nil }
        return DartsSetStoryCard10868(
            model: story, onExpand: nil,
            onSelect: Self.relay(onSetSelect, through: activation),
            onReport: Self.relayAction(aboutOpener(), through: activation))
    }

    /// The full-size set story: the exact callbacks.
    func readerSetsContent() -> DartsSetStoryCard10868? {
        model.readerSetsModel.map {
            DartsSetStoryCard10868(model: $0, onExpand: nil, onSelect: onSetSelect, onReport: aboutOpener())
        }
    }

    /// The existing catalogue with the owner's originals, its select callback
    /// after the interaction hook.
    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: Self.held(onOriginalSelect, by: onInteraction)
            )
        }
    }

    /// The existing Details for the owner's held selection, its history
    /// callback after the interaction hook.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: Self.held(onOriginalHistory, by: onInteraction)
            )
        }
    }

    /// The owner's About with its exact source callback — content the host
    /// already holds, so no hook.
    func aboutContent() -> DartsEventPageAboutContent10868? {
        model.about.map { DartsEventPageAboutContent10868(about: $0, onSource: onSource) }
    }

    /// Full-size content's About: the exact callback, no hook.
    func openReaderAbout() {
        aboutOpener()?()
    }

    /// Full-size content's own controls: the mounted neighbours and Back, exactly.
    func readerControls(_ card: DartsSetEventPageCard10868) -> (previous: DartsSetEventPageCard10868?,
                                                               next: DartsSetEventPageCard10868?,
                                                               canGoBack: Bool) {
        guard onReaderIntent != nil, model.readerShows(card) else { return (nil, nil, false) }
        return (model.neighbour(of: card, offset: -1), model.neighbour(of: card, offset: 1), true)
    }

    // MARK: Page

    private var page: some View {
        Group {
            let arrangements = DartsSetEventPageModel10868.arrangements(
                sizeClass: sizeClass, accessibilitySize: typeSize.isAccessibilitySize)
            if arrangements == [.stacked] {
                stackedPage
            } else {
                ViewThatFits(in: .horizontal) {
                    widePage
                    stackedPage
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.page)
    }

    private var stackedPage: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            anchor
            stories
        }
    }

    /// The headline across; the anchor beside the stories.
    private var widePage: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            HStack(alignment: .top, spacing: 24) {
                anchor
                    .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                    .layoutPriority(1)
                stories
                    .frame(minWidth: storiesMinWidth, maxWidth: .infinity, alignment: .topLeading)
            }
        }
    }

    /// The headline, or the owner's words when its phase is not the page's,
    /// then the owner's status words.
    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            Group {
                if let headline = headlineContent() {
                    headline
                } else {
                    Text(input.copy.headlineUnavailable)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.headlineUnavailable)
                }
            }
            .accessibilitySortPriority(DartsSetEventPageModel10868.sortPriority(.headline))
            if let notice = DartsSetEventPageModel10868.readable(input.notice) {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilitySortPriority(DartsSetEventPageModel10868.sortPriority(.notice))
                    .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.notice)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(DartsSetCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.header)
    }

    /// The paired comparison above the history leaf, in one card.
    private var anchor: some View {
        VStack(alignment: .leading, spacing: 16) {
            comparisonContent(reader: false)
            historyContent(reader: false)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(DartsSetCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilitySortPriority(DartsSetEventPageModel10868.sortPriority(.anchor))
        .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.anchor)
    }

    /// The owner's stream or the mounted set story, then the originals.
    private var stories: some View {
        VStack(alignment: .leading, spacing: 16) {
            cards
            originalsPanel
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.stories)
    }

    @ViewBuilder private var cards: some View {
        if let stream = input.stream {
            StoryStreamPresentationView10868(stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            .accessibilityElement(children: .contain)
            .accessibilitySortPriority(DartsSetEventPageModel10868.sortPriority(.cards))
        } else if let sets = pageSetsContent() {
            sets
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(DartsSetCardSurface10868())
                .accessibilitySortPriority(DartsSetEventPageModel10868.sortPriority(.cards))
                .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.card(.sets))
        }
    }

    /// The card the owner links to this stream card, with the stream's
    /// activation hook and the owner's reason words, or the owner's
    /// unavailable words. Never a neighbour.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.storyLink(card.id), link.card == .sets, let content = streamSetsContent(activation: activation) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = DartsSetEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                content
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(DartsSetCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(DartsSetCardSurface10868())
                .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.storyUnavailable)
        }
    }

    /// The originals with the owner's held-unavailable words.
    @ViewBuilder private var originalsPanel: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 8) {
                catalogue
                if DartsSetEventPageModel10868.heldOriginalIsUnavailable(originals) {
                    Text(input.copy.heldOriginalUnavailable)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.heldUnavailable)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(DartsSetCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilitySortPriority(DartsSetEventPageModel10868.sortPriority(.originals))
            .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.originals)
        }
    }

    // MARK: Full-size content and modes

    /// The same Views and input, full size, under the compact match words and
    /// the reader's own controls. A card this phase does not show has no content.
    @ViewBuilder private func reader(_ card: DartsSetEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader(done: false)
                readerNavigation(card)
                switch card {
                case .history:
                    comparisonContent(reader: true)
                    historyContent(reader: true)
                case .sets:
                    readerSetsContent()
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.card(card))
        }
    }

    /// Back, then the previous and next mounted cards by name.
    @ViewBuilder private func readerNavigation(_ card: DartsSetEventPageCard10868) -> some View {
        let controls = readerControls(card)
        if controls.canGoBack {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) {
                    readerButtons(controls)
                }
                VStack(alignment: .leading, spacing: 4) {
                    readerButtons(controls)
                }
            }
        }
    }

    @ViewBuilder private func readerButtons(_ controls: (previous: DartsSetEventPageCard10868?,
                                                         next: DartsSetEventPageCard10868?,
                                                         canGoBack: Bool)) -> some View {
        readerButton(input.copy.backLabel, detail: nil, systemImage: "chevron.backward",
                     action: Self.bind(onReaderIntent, .back), id: DartsSetEventPageAccessibilityID10868.readerBack)
        if let previous = controls.previous {
            readerButton(input.copy.previousLabel, detail: model.cardName(previous), systemImage: "arrow.left",
                         action: Self.bind(onReaderIntent, .previous(previous)),
                         id: DartsSetEventPageAccessibilityID10868.readerPrevious)
        }
        if let next = controls.next {
            readerButton(input.copy.nextLabel, detail: model.cardName(next), systemImage: "arrow.right",
                         action: Self.bind(onReaderIntent, .next(next)),
                         id: DartsSetEventPageAccessibilityID10868.readerNext)
        }
    }

    @ViewBuilder private func readerButton(_ label: String, detail: String?, systemImage: String,
                                           action: (() -> Void)?, id: String) -> some View {
        if let action {
            Button(action: action) {
                HStack(spacing: 6) {
                    Image(systemName: systemImage)
                        .font(.subheadline.weight(.semibold))
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(label)
                            .font(.subheadline.weight(.semibold))
                        if let detail = DartsSetEventPageModel10868.readable(detail) {
                            Text(detail)
                                .font(.caption)
                                .foregroundStyle(DS.textSecondary)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
                .foregroundStyle(DS.blue)
                .frame(minHeight: controlSize)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(id)
        }
    }

    /// The owner's one-line match words; in full-size content the About entry;
    /// in the Details and About content the Done control.
    private func compactHeader(done: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = DartsSetEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutEntry(mode: mode, canOpen: onAbout != nil) {
                Button(action: openReaderAbout) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(input.headline.copy.aboutLabel)
                .accessibilityHint(input.headline.copy.aboutHint ?? "")
                .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.readerAbout)
            }
            if done, let action = Self.bind(onReaderIntent, .done) {
                Button(input.copy.doneLabel, action: action)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(DS.blue)
                    .frame(minHeight: controlSize)
                    .buttonStyle(.plain)
                    .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.done)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.readerHeader)
    }

    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader(done: true)
                details
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.original)
        }
    }

    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader(done: true)
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(DartsSetEventPageAccessibilityID10868.about)
        }
    }
}
