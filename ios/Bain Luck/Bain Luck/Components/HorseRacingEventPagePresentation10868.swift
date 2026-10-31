import SwiftUI

// #10868 — the horse-racing page (`horse-racing`): one native presentation for
// the existing race route, composed from the accepted shared leaves, plus two
// small leaves defined here — the featured-runner picks and the compact,
// probability-first runner catalogue. A fan sees, in this order: the race
// header (the owner's eyebrow, title, place and date line, state words and
// compact Info); the owner's notice; then the anchor — the featured runner
// picks and the tall shared history of independently retained Yes trades for
// the selected runner or the owner's three-runner cohort, with the selected
// runner's dated pre-schedule trade beside its selected or last recorded trade
// — with the exact original entry and the source entry; at the final, the
// actual finish card with its result source; during the race, only the
// owner's words for the absent live positions; then the compact catalogue of
// every runner in the owner's groups, one shared scale, each runner's labelled
// pre-schedule chance or its absence, its separately admitted finish at the
// final, and its exact Yes and No original details. The history and the finish
// open as full-size content made of the same Views; the generic original
// catalogue, the held original's Details, the race About and the source
// details are further content modes.
//
// Presentation only, composed from the approved `HorseRacing.tsx`,
// `HorseCatalog.tsx`, `HorsePropDetail.tsx`, `HorseFinishComparison.tsx` and
// their CSS, with the earlier native references as visual and semantic
// references only. The reference's fixture loader, phase window
// (`racePhase`), schedule cutoff and baseline election (`lastBefore`), auto
// ceiling ladders, catalogue windowing (`horseCatalogWindow`), ordinal suffixes
// (`horseFinishOrdinal`), name-based Other handling, featured-runner election,
// identity colours and marks, outcome history loader, probability label and
// reader clock, story session state, dialogs, sheets and focus return are NOT
// ported. The leaves are the actual accepted Views:
//
//   • `FieldProbabilityHistoryPresentation10868` — the anchor: the owner's
//     isolated trade marks, runs, guides, scale, focused readouts, inspection,
//     previous/next and actions;
//   • `FieldFinishComparisonPresentation10868` — the final card: each displayed
//     runner's whole name and separately reported finish beside its own
//     pre-schedule chance on one scale;
//   • `HorseRacingPicksView10868` (below) — the featured runner picks, every
//     identity resolved by the chooser's own `FieldChooserModel10868`;
//   • `HorseCatalogueView10868` (below) — the compact catalogue: its owner group
//     resolved by the chooser's own group rule, and every row's identity, raw
//     before chance, figure, scale state, finish association and open action
//     taken from `FieldFinishModel10868` on `FieldOutlookModel10868` — the same
//     resolver, tie and placement the finish card uses — drawn with
//     `FieldFinishGeometry10868`'s strip plan; every Yes and No action resolved
//     by the shared `OriginalMarketDetails9483` resolver;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` — the
//     generic originals and the held original's Details, the authoritative
//     original reader.
//
// The reference ranks no story stream (its reader holds only the history and
// the finish), so no stream is mounted.
//
// The page's phase is the owner's explicit `HorseRacingPhase10868`, never read
// from a schedule, a first or last trade, a market close, a settlement or a
// result. The published schedule is at most an owner-labelled guide on the
// history, never an actual start, and no finish or progress clock is placed on
// the probability axis. The finish card is mounted at the final only, and only
// with a final card input; before and during the race no finish, report or
// settlement reaches the page or its speech, whatever the owner supplies.
// During the race only the owner's words for the absent live positions are
// shown — never a placing, a progress share or a blended forecast. The
// catalogue is mounted only at the page's own phase; before the race it shows
// no finish at all, and during the race only finishes the owner admitted for
// that phase.
//
// Every runner's chance is its own independently timed trade: this layer never
// complements a Yes into a No, normalizes or sums a field, treats a missing
// value as zero, elects a baseline, turns a later trade into a missing
// pre-schedule chance, derives a finish from a contract result or a grade from
// a finish, appends a 0/100 endpoint, sorts, caps or pages a list, or builds an
// identity from a name or a position. A partial, missing, duplicated, foreign
// or withdrawn identity keeps its row, its name and its absence words, borrows
// nothing and draws no action; its neighbours keep theirs. The special Other
// outcome keeps the owner's own status words in every phase.
//
// The owner may pass an interaction hook, so it can hold its received frame
// before an action lands. On the page — the header's Info, a runner pick, the
// cohort and catalogue toggles, the anchor history's actions, inspection
// choices and plot taps, the original and source entries, the finish card's
// rows, its expand and its result link, a catalogue row, a Yes or No action, a
// group step and the all-originals entry — and in the generic catalogue and
// Details content — an original's selection, a side switch and a Details
// history intent — the action calls that hook once and then the owner's exact
// callback with its exact value. Without a callback there is no control and no
// hook call; without a hook every callback is the owner's own. Building or
// reading the view calls nothing. Full-size history and finish, and the About
// and source content, keep the exact callbacks: their host already holds the
// frame while they are open.
//
// The full-size history is the same history input without its expand control,
// at the owner's reader plot height when supplied; every series, run, guide,
// selection, readout, scale, action and inspection is unchanged. The full-size
// finish is the same finish card and result source.
//
// Phone stacks the history above the finish and the catalogue in one column of
// cards; a regular or unspecified size class places the history beside the
// finish while both keep their minimum widths; accessibility sizes always
// stack. Catalogue cards take as many columns as keep their scaled minimum
// width — one at accessibility sizes — and every name and word wraps whole.
//
// The host owns the scroll, navigation, sheets, Back/Done, focus, routing to
// and from every content mode, the selected runner, the cohort, the held
// original, the held inspection and scale, the catalogue group and its
// expansion, the held/received frame, live subscriptions and every genuine
// update. This view keeps no state, runs no timer or animation, holds no
// subscription and presents no sheet or navigation of its own.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one race snapshot, the phase; the canonical runner originals and their
// exact Yes and No identities; each runner's qualified pre-schedule
// observation tied to its formatted reading, or its absence; the history's
// isolated trades, owner coordinate, schedule guide, scale, readouts and
// inspection; the independently reported finishes; the catalogue groups and
// steps; the About, source and result words; and maps every callback to its
// existing controls. No production race, schedule, trade-history or finish
// channel for this route exists in the app's models at this base.

// MARK: - Phase and modes

/// The owner's explicit race phase. Never inferred here.
nonisolated enum HorseRacingPhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final

    /// The shared field leaves' own name for the same phase.
    var fieldPhase: FieldOutlookPhase10868 {
        switch self {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }
}

/// What the host is showing. The host routes; this view only draws.
nonisolated enum HorseRacingMode10868: Equatable {
    case page
    /// The same history, full size.
    case fullHistory
    /// The same finish card and result source, full size.
    case fullFinish
    /// The generic original catalogue.
    case catalogue
    /// The held original's Details.
    case original
    case about
    case source
}

nonisolated enum HorseRacingArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Owner words

/// The race header, every line the owner's.
nonisolated struct HorseRacingHeader10868: Equatable {
    /// The owner's state and race eyebrow; nil draws none.
    let eyebrow: String?
    let title: String
    /// The owner's place and distance words; nil draws none.
    let place: String?
    /// The owner's race-date words; nil draws none.
    let date: String?
    /// The owner's state words; nil draws none.
    let status: String?
    /// The Info control's spoken name.
    let aboutLabel: String
    let aboutHint: String?
}

/// The owner's one-line race words above full-size content.
nonisolated struct HorseRacingReaderHeader10868: Equatable {
    let title: String
    /// Nil draws none.
    let state: String?
}

nonisolated struct HorseRacingSection10868: Equatable {
    let title: String?
    let paragraphs: [String]
}

/// A link the host opens by its exact id.
nonisolated struct HorseRacingLink10868: Equatable {
    let id: String
    let label: String
}

/// The owner's About, source details or result source, in its own words.
nonisolated struct HorseRacingText10868: Equatable {
    let title: String
    let sections: [HorseRacingSection10868]
    /// Shown only with a callback and a readable id and label.
    var link: HorseRacingLink10868? = nil
}

/// An owner toggle: its exact id, its words and its state.
nonisolated struct HorseRacingToggle10868: Equatable {
    let id: String
    let label: String
    let isOn: Bool
}

/// The exact original the anchor opens, with the owner's selected position
/// handed back unchanged.
struct HorseRacingOriginalOpen10868: Equatable {
    let label: String
    let selection: OriginalMarketDetails9483.Selection
    /// The owner's selected trade position in its own coordinate; nil none.
    let selectedPosition: Double?
}

nonisolated struct HorseRacingPageCopy10868: Equatable {
    /// The source entry's words; nil draws no entry.
    var sourceLabel: String? = nil
    /// The generic catalogue entry's words; nil draws no entry.
    var allOriginalsLabel: String? = nil
}

// MARK: - Runner picks

/// One featured runner the owner offers, in its order.
nonisolated struct HorseRacingPick10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The chart's own non-colour key for this runner while compared; nil none.
    let shape: FieldHistoryShape10868?
}

nonisolated struct HorseRacingPicksInput10868: Equatable {
    /// The exact scope every reference must share.
    let scope: String
    /// The canonical runner originals, in the owner's order.
    let catalogue: [FieldChooserOriginal10868]
    let selected: FieldChooserSelected10868?
    /// The picks' spoken group name.
    let groupLabel: String
    let picks: [HorseRacingPick10868]
    /// The owner's cohort toggle ("Compare 3"); nil draws none.
    let cohort: HorseRacingToggle10868?
    /// A pick that does not resolve.
    let unavailableWords: String
    let chooseHint: String?
}

nonisolated struct HorseRacingPickRow10868: Equatable {
    let pick: HorseRacingPick10868
    let resolution: FieldChooserResolution10868
}

/// The picks' rules on the chooser's own resolver, selected cue and choose action.
nonisolated struct HorseRacingPicksModel10868: Equatable {
    let input: HorseRacingPicksInput10868
    let field: FieldChooserModel10868
    /// Picks listed more than once.
    private let repeated: Set<FieldChooserOriginalRef10868>

    init(_ input: HorseRacingPicksInput10868) {
        self.input = input
        field = FieldChooserModel10868(FieldChooserInput10868(
            scope: input.scope,
            intro: nil,
            featured: FieldChooserFeatured10868(
                title: input.groupLabel, badge: nil,
                refs: input.picks.map(\.ref), emptyWords: input.unavailableWords
            ),
            context: nil,
            more: nil,
            browse: nil,
            catalogue: input.catalogue,
            frame: nil,
            selected: input.selected,
            unavailableWords: input.unavailableWords,
            chooseHint: input.chooseHint
        ))
        var counts: [FieldChooserOriginalRef10868: Int] = [:]
        for pick in input.picks { counts[pick.ref, default: 0] += 1 }
        repeated = Set(counts.filter { $0.value > 1 }.keys)
    }

    var rows: [HorseRacingPickRow10868] {
        input.picks.map { pick in
            HorseRacingPickRow10868(
                pick: pick,
                resolution: repeated.contains(pick.ref) ? .unavailable : field.resolve(pick.ref)
            )
        }
    }

    func isSelected(_ row: HorseRacingPickRow10868) -> Bool {
        row.resolution.original.map(field.isSelected) ?? false
    }

    /// The exact runner to hand back, only with a callback.
    func chooseRef(_ row: HorseRacingPickRow10868, canChoose: Bool) -> FieldChooserOriginalRef10868? {
        guard case .choose(let ref)? = field.chooseAction(
            FieldChooserRow10868(ref: row.pick.ref, resolution: row.resolution), canChoose: canChoose
        ) else { return nil }
        return ref
    }

    /// The selected runner's unavailable words when it does not resolve.
    var notice: String? { field.selectionNotice }

    /// The cohort toggle's id, only with a callback and readable words.
    func cohortID(canToggle: Bool) -> String? {
        guard canToggle, let toggle = input.cohort,
              HorseRacingPageModel10868.readable(toggle.id) != nil,
              HorseRacingPageModel10868.readable(toggle.label) != nil
        else { return nil }
        return toggle.id
    }

    func spoken(_ row: HorseRacingPickRow10868) -> String {
        guard let original = row.resolution.original else { return input.unavailableWords }
        return HorseCatalogueModel10868.joined([original.name, field.selectedWords(original) ?? ""])
    }
}

// MARK: - Catalogue

/// One owner group of runner rows, in the owner's order.
nonisolated struct HorseCatalogueGroup10868: Equatable {
    let id: String
    /// The owner's position words ("1–5 of 25").
    let label: String
    let rows: [FieldFinishSlot10868]
}

/// The owner's previous or next group.
nonisolated struct HorseCatalogueStep10868: Equatable {
    let groupID: String
    let label: String
    let spokenLabel: String?
}

/// One exact Yes or No original for one runner row.
struct HorseCatalogueSide10868: Equatable {
    /// The runner row this side belongs to.
    let ref: FieldChooserOriginalRef10868
    let label: String
    let spokenLabel: String?
    let selection: OriginalMarketDetails9483.Selection
}

/// A side as drawn: its exact selection only when the shared Details resolve it.
struct HorseCatalogueSideState10868: Equatable {
    let side: HorseCatalogueSide10868
    let selection: OriginalMarketDetails9483.Selection?
}

nonisolated struct HorseCatalogueCopy10868: Equatable {
    /// "25 props · 50 original Yes / No outcomes".
    let heading: String
    /// "Recorded at different times · not a current forecast"; nil draws none.
    let note: String?
    /// "Pre-race win chance".
    let scaleLabel: String
    /// The pager's spoken name.
    let pagerLabel: String
    /// Label of a finish that cannot be shown ("Reported finish").
    let finishLabel: String
    /// The unit beside a reported ordinal ("finish").
    let finishUnit: String
    /// No finish association for this runner ("Finish not recorded").
    let finishUnavailable: String
    let chanceUnavailable: String
    let offScale: String
    /// A row that does not resolve.
    let unavailableWords: String
    /// A side the shared Details do not resolve.
    let sideUnavailable: String
    let noGroup: String
    let groupUnavailable: String
    let emptyGroup: String
    let openHint: String?
}

nonisolated struct HorseCatalogueInput10868: Equatable {
    /// The exact scope every row must share.
    let scope: String
    /// The canonical runner originals, in the owner's order.
    let catalogue: [FieldChooserOriginal10868]
    let selected: FieldChooserSelected10868?
    /// Every row, in the owner's groups. Never sorted, capped or paged here.
    let groups: [HorseCatalogueGroup10868]
    let currentGroupID: String?
    let previous: HorseCatalogueStep10868?
    let next: HorseCatalogueStep10868?
    /// Each runner's raw pre-schedule chance tied to its formatted reading.
    let chances: [FieldOutlookBeforeChance10868]
    /// The one catalogue-wide scale, the same for every group.
    let scale: FieldOutlookScale10868
    /// Finishes admitted for this phase; nil: no finish channel. Never shown
    /// before the race.
    let finishes: [FieldFinishPlace10868]?
    let phase: HorseRacingPhase10868
    let copy: HorseCatalogueCopy10868
}

nonisolated struct HorseCatalogueRow10868: Equatable {
    let slot: FieldFinishSlot10868
    /// The finish card's row rules for the same slot: identity and raw chance.
    let row: FieldFinishRow10868

    var resolution: FieldChooserResolution10868 { row.resolution }
    var chance: FieldOutlookChance10868 { row.chance }
    /// Shown only when the phase admits a finish channel.
    var finish: FieldMovementEndpoint10868? { row.finish }
}

/// The catalogue's rules: the chooser's group rule, then the finish card's own
/// model on the outlook for every row of the chosen group.
nonisolated struct HorseCatalogueModel10868: Equatable {
    let input: HorseCatalogueInput10868
    /// The chooser's group resolution.
    let browse: FieldChooserModel10868
    /// The finish card's identity, chance, figure and finish rules on the chosen group.
    let rules: FieldFinishModel10868
    let group: HorseCatalogueGroup10868?

    init(_ input: HorseCatalogueInput10868) {
        self.input = input
        browse = FieldChooserModel10868(FieldChooserInput10868(
            scope: input.scope,
            intro: nil,
            featured: FieldChooserFeatured10868(title: input.copy.heading, badge: nil, refs: [], emptyWords: input.copy.emptyGroup),
            context: nil,
            more: nil,
            browse: FieldChooserBrowse10868(
                id: "",
                title: input.copy.heading,
                expanded: true,
                note: nil,
                groupsLabel: input.copy.pagerLabel,
                groups: input.groups.map { FieldChooserGroup10868(id: $0.id, label: $0.label, countText: nil, refs: $0.rows.map(\.ref)) },
                selectedGroupID: input.currentGroupID,
                noGroupWords: input.copy.noGroup,
                groupUnavailableWords: input.copy.groupUnavailable,
                emptyGroupWords: input.copy.emptyGroup
            ),
            catalogue: input.catalogue,
            frame: nil,
            selected: input.selected,
            unavailableWords: input.copy.unavailableWords,
            chooseHint: nil
        ))
        var chosen: HorseCatalogueGroup10868?
        if case .group(let resolved)? = browse.groupSelection {
            chosen = input.groups.first { $0.id == resolved.id }
        }
        group = chosen
        rules = FieldFinishModel10868(FieldFinishInput10868(
            scope: input.scope,
            catalogue: input.catalogue,
            selected: input.selected,
            displayed: chosen?.rows ?? [],
            finishes: input.finishes ?? [],
            chances: input.chances,
            scale: input.scale,
            phase: input.phase.fieldPhase,
            copy: FieldFinishCopy10868(
                title: input.copy.heading,
                context: nil,
                scaleLabel: input.copy.scaleLabel,
                graphicLabel: input.copy.heading,
                finishLabel: input.copy.finishLabel,
                finishUnit: input.copy.finishUnit,
                finishUnavailable: input.copy.finishUnavailable,
                chanceUnavailable: input.copy.chanceUnavailable,
                offScale: input.copy.offScale,
                outsideDisplayed: "",
                empty: input.copy.emptyGroup,
                count: nil,
                openPrompt: nil,
                openHint: input.copy.openHint
            ),
            unavailableWords: input.copy.unavailableWords
        ))
    }

    // MARK: Group

    /// The owner's words when no single group is chosen, or the chosen group is empty.
    var groupWords: String? {
        switch browse.groupSelection {
        case .notChosen(let words)?, .unavailable(let words)?:
            return words
        case .group?:
            return (group?.rows.isEmpty ?? true) ? input.copy.emptyGroup : nil
        case nil:
            return input.copy.noGroup
        }
    }

    /// The pager's position words: the chosen group's own label.
    var position: String? {
        group.flatMap { HorseRacingPageModel10868.readable($0.label) }
    }

    /// A step's target group id: listed exactly once, readable, with a callback.
    func stepTarget(_ step: HorseCatalogueStep10868?, canMove: Bool) -> String? {
        guard canMove, let step, HorseRacingPageModel10868.readable(step.groupID) != nil,
              input.groups.filter({ $0.id == step.groupID }).count == 1
        else { return nil }
        return step.groupID
    }

    // MARK: Rows

    /// Finishes are read only after the race starts, and only with an admitted channel.
    var showsFinish: Bool { input.phase != .before && input.finishes != nil }

    var rows: [HorseCatalogueRow10868] {
        let slots = group?.rows ?? []
        return zip(slots, rules.outlook.bars).map { slot, bar in
            let original = bar.resolution.original
            let finish: FieldMovementEndpoint10868? = showsFinish ? original.map { rules.finish(for: $0.ref) } : nil
            return HorseCatalogueRow10868(slot: slot, row: FieldFinishRow10868(slot: slot, bar: bar, finish: finish))
        }
    }

    /// The scale's placed ticks, the same for every group.
    var ticks: [FieldOutlookPlacedTick10868] { rules.outlook.ticks }

    var scaleWords: String? {
        input.scale.isValid ? HorseRacingPageModel10868.readable(input.scale.words) : nil
    }

    func figure(_ row: HorseCatalogueRow10868) -> String? { rules.outlook.figure(row.row.bar) }

    /// The before reading's own label ("Before scheduled start"), shown with its figure.
    func figureLabel(_ row: HorseCatalogueRow10868) -> String? {
        row.resolution.original.map { FieldOutlookModel10868.beforeReading($0.plan).label }
    }

    func isRecorded(_ row: HorseCatalogueRow10868) -> Bool {
        guard let original = row.resolution.original,
              case .recorded = FieldOutlookModel10868.beforeReading(original.plan).value else { return false }
        return true
    }

    func stateWords(_ row: HorseCatalogueRow10868) -> String? { rules.outlook.stateWords(row.row.bar) }

    func isSelected(_ row: HorseCatalogueRow10868) -> Bool { rules.outlook.isSelected(row.row.bar) }

    func selectedWords(_ row: HorseCatalogueRow10868) -> String? {
        row.resolution.original.flatMap { browse.selectedWords($0) }
    }

    /// The owner's compact status words for this runner ("Special outcome · see rules").
    func status(_ row: HorseCatalogueRow10868) -> String? {
        row.resolution.original.flatMap { HorseRacingPageModel10868.readable($0.browseStatus) }
    }

    /// The exact runner whose history the row opens — only with a callback.
    func openRef(_ row: HorseCatalogueRow10868, canOpen: Bool) -> FieldChooserOriginalRef10868? {
        rules.openAction(row.row, canOpen: canOpen)
    }

    /// A shown finish's whole ordinal, or its words.
    static func ordinal(_ row: HorseCatalogueRow10868) -> String? { FieldFinishModel10868.ordinal(row.finish) }
    static func finishWords(_ row: HorseCatalogueRow10868) -> String? { FieldFinishModel10868.finishWords(row.finish) }

    /// The selected runner's words when it does not resolve.
    var notice: String? { browse.selectionNotice }

    // MARK: VoiceOver

    /// A row's whole reading in the owner's words, so its strip may stay decorative.
    func rowSummary(_ row: HorseCatalogueRow10868) -> String {
        guard let original = row.resolution.original else {
            return Self.joined([row.slot.name, input.copy.unavailableWords])
        }
        var parts: [String] = [selectedWords(row) ?? ""]
        parts.append(FieldChooserModel10868.spoken(FieldOutlookModel10868.beforeReading(original.plan)))
        parts.append(stateWords(row) ?? "")
        if let finish = row.finish { parts.append(FieldMovementModel10868.spoken(finish)) }
        parts.append(status(row) ?? "")
        return Self.joined(parts)
    }

    static func joined(_ parts: [String]) -> String {
        parts.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }.joined(separator: ". ")
    }
}

nonisolated enum HorseCatalogueGeometry10868 {
    /// Catalogue cards per line: as many as keep the scaled minimum width, at
    /// most the owner's maximum; one at accessibility sizes or without a width.
    static func columns(
        count: Int,
        available: CGFloat?,
        minimumWidth: CGFloat,
        spacing: CGFloat,
        maximum: Int,
        accessibilitySize: Bool
    ) -> Int {
        guard count > 1, !accessibilitySize else { return 1 }
        guard let available, available.isFinite, available > 0,
              minimumWidth.isFinite, minimumWidth > 0, spacing.isFinite, spacing >= 0 else { return 1 }
        var columns = max(1, min(maximum, count))
        while columns > 1 {
            let width = (available - spacing * CGFloat(columns - 1)) / CGFloat(columns)
            if width >= minimumWidth { return columns }
            columns -= 1
        }
        return 1
    }

    /// Positions per line, in the owner's order; nothing is dropped.
    static func lines(count: Int, columns: Int) -> [[Int]] {
        guard count > 0 else { return [] }
        let step = max(1, columns)
        return stride(from: 0, to: count, by: step).map { Array($0..<min($0 + step, count)) }
    }

    /// Picks per line at their whole widths; a pick wider than the line keeps a
    /// line of its own and wraps inside it.
    static func wrap(widths: [CGFloat], available: CGFloat?, spacing: CGFloat) -> [[Int]] {
        guard !widths.isEmpty else { return [] }
        guard let available, available.isFinite, available > 0 else { return [Array(widths.indices)] }
        var lines: [[Int]] = []
        var current: [Int] = []
        var used: CGFloat = 0
        for (index, raw) in widths.enumerated() {
            let width = min(max(0, raw.isFinite ? raw : available), available)
            if current.isEmpty {
                current = [index]
                used = width
            } else if used + spacing + width <= available + 0.5 {
                current.append(index)
                used += spacing + width
            } else {
                lines.append(current)
                current = [index]
                used = width
            }
        }
        if !current.isEmpty { lines.append(current) }
        return lines
    }

    /// The SF Symbol for a runner's non-colour key.
    static func symbol(_ shape: FieldHistoryShape10868) -> String {
        switch shape {
        case .circle: "circle.fill"
        case .square: "square.fill"
        case .diamond: "diamond.fill"
        case .triangle: "triangle.fill"
        }
    }
}

/// Catalogue cards in lines of as many columns as keep their minimum width;
/// cards in a line share its height and grow with their text.
struct HorseCatalogueGridLayout10868: Layout {
    var spacing: CGFloat
    var minimumWidth: CGFloat
    var maximumColumns: Int
    var accessibilitySize: Bool

    private func columns(_ width: CGFloat?, count: Int) -> Int {
        HorseCatalogueGeometry10868.columns(
            count: count, available: width, minimumWidth: minimumWidth,
            spacing: spacing, maximum: maximumColumns, accessibilitySize: accessibilitySize
        )
    }

    private func columnWidth(_ total: CGFloat, columns: Int) -> CGFloat {
        max(0, (total - spacing * CGFloat(max(0, columns - 1))) / CGFloat(max(1, columns)))
    }

    private func lineHeight(_ line: [Int], width: CGFloat, subviews: Subviews) -> CGFloat {
        line.map { subviews[$0].sizeThatFits(ProposedViewSize(width: width, height: nil)).height }.max() ?? 0
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let total = proposal.width.flatMap { $0.isFinite ? $0 : nil }
            ?? subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0
        let count = columns(total, count: subviews.count)
        let width = columnWidth(total, columns: count)
        let lines = HorseCatalogueGeometry10868.lines(count: subviews.count, columns: count)
        let heights = lines.map { lineHeight($0, width: width, subviews: subviews) }
        let height = heights.reduce(0, +) + spacing * CGFloat(max(0, lines.count - 1))
        return CGSize(width: total, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let count = columns(bounds.width, count: subviews.count)
        let width = columnWidth(bounds.width, columns: count)
        var y = bounds.minY
        for line in HorseCatalogueGeometry10868.lines(count: subviews.count, columns: count) {
            let height = lineHeight(line, width: width, subviews: subviews)
            for (position, index) in line.enumerated() {
                subviews[index].place(
                    at: CGPoint(x: bounds.minX + CGFloat(position) * (width + spacing), y: y),
                    anchor: .topLeading,
                    proposal: ProposedViewSize(width: width, height: height)
                )
            }
            y += height + spacing
        }
    }
}

/// Picks in wrapping lines at their whole widths.
struct HorseRacingWrapLayout10868: Layout {
    var spacing: CGFloat

    private func sizes(_ subviews: Subviews, available: CGFloat?) -> [CGSize] {
        subviews.map { subview in
            let ideal = subview.sizeThatFits(.unspecified)
            guard let available, available.isFinite, ideal.width > available else { return ideal }
            return subview.sizeThatFits(ProposedViewSize(width: available, height: nil))
        }
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let available = proposal.width.flatMap { $0.isFinite ? $0 : nil }
        let sizes = sizes(subviews, available: available)
        let lines = HorseCatalogueGeometry10868.wrap(widths: sizes.map(\.width), available: available, spacing: spacing)
        var width: CGFloat = 0
        var height: CGFloat = 0
        for (number, line) in lines.enumerated() {
            let lineWidth = line.map { sizes[$0].width }.reduce(0, +) + spacing * CGFloat(max(0, line.count - 1))
            width = max(width, lineWidth)
            height += (line.map { sizes[$0].height }.max() ?? 0) + (number > 0 ? spacing : 0)
        }
        return CGSize(width: available ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let sizes = sizes(subviews, available: bounds.width)
        var y = bounds.minY
        for line in HorseCatalogueGeometry10868.wrap(widths: sizes.map(\.width), available: bounds.width, spacing: spacing) {
            var x = bounds.minX
            let height = line.map { sizes[$0].height }.max() ?? 0
            for index in line {
                subviews[index].place(
                    at: CGPoint(x: x, y: y),
                    anchor: .topLeading,
                    proposal: ProposedViewSize(width: sizes[index].width, height: sizes[index].height)
                )
                x += sizes[index].width + spacing
            }
            y += height + spacing
        }
    }
}

// MARK: - Finish section and page input

/// The final finish card, its owner words and its result source.
nonisolated struct HorseRacingFinishInput10868: Equatable {
    /// The owner's eyebrow ("Pre-race trade → actual finish"); nil draws none.
    let eyebrow: String?
    let card: FieldFinishInput10868
    /// The owner's result source and meaning; nil draws none.
    let source: HorseRacingText10868?
    /// The expand control's spoken name.
    let expandLabel: String
}

nonisolated struct HorseRacingPageInput10868: Equatable {
    let phase: HorseRacingPhase10868
    let header: HorseRacingHeader10868
    let reader: HorseRacingReaderHeader10868
    /// The owner's notice ("Current probability unavailable · recorded history retained").
    var notice: String? = nil
    /// The featured runner picks; nil draws none.
    var picks: HorseRacingPicksInput10868? = nil
    /// The anchor: the same immutable history on the page and full size.
    let history: FieldHistoryInput10868
    /// The full-size history's plot height; nil keeps the page's.
    var readerPlotHeight: CGFloat? = nil
    /// The final card; mounted only at the final with a final card.
    var finish: HorseRacingFinishInput10868? = nil
    /// During the race: the owner's words for the absent live positions.
    var finishPending: String? = nil
    /// The compact catalogue; mounted only at the page's own phase.
    var catalogue: HorseCatalogueInput10868? = nil
    /// The owner's catalogue disclosure; nil shows the catalogue.
    var catalogueDisclosure: HorseRacingToggle10868? = nil
    var about: HorseRacingText10868? = nil
    var source: HorseRacingText10868? = nil
    let copy: HorseRacingPageCopy10868
}

/// The owner's originals behind the generic catalogue and the held Details.
struct HorseRacingOriginals10868 {
    /// Every exact Yes and No original, in the owner's order.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The held original; never replaced here.
    let selection: OriginalMarketDetails9483.Selection?
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    let heading: String
    var context: String? = nil
    let emptyWords: String
    let unavailableChoice: String
    let tint: Color
    /// Each runner's exact Yes and No originals, for the catalogue actions and
    /// the Details switch, in the owner's order.
    var sides: [HorseCatalogueSide10868] = []
    /// The anchor's exact original entry; nil draws none.
    var open: HorseRacingOriginalOpen10868? = nil
}

/// Every Yes, No and original-entry action goes through the shared Details
/// resolver: an original opens only when it resolves to exactly one original.
enum HorseRacingOriginalRules10868 {
    /// This runner's Yes and No originals in the owner's order, each opening
    /// only when the shared Details resolve its exact selection.
    static func sides(for ref: FieldChooserOriginalRef10868, in sides: [HorseCatalogueSide10868],
                      catalogue: OriginalMarketDetails9483.Catalogue?) -> [HorseCatalogueSideState10868] {
        sides.filter { $0.ref == ref }.map { side in
            let opens = OriginalMarketDetails9483.content(catalogue: catalogue, selection: side.selection) != nil
            return HorseCatalogueSideState10868(side: side, selection: opens ? side.selection : nil)
        }
    }

    /// The held original's runner sides, for the Details switch: the sides of
    /// the one runner whose side is exactly the held selection. Otherwise none.
    static func heldSides(_ held: OriginalMarketDetails9483.Selection?, in sides: [HorseCatalogueSide10868],
                          catalogue: OriginalMarketDetails9483.Catalogue?) -> [HorseCatalogueSideState10868] {
        guard let held else { return [] }
        let owners = Set(sides.filter { $0.selection == held }.map(\.ref))
        guard owners.count == 1, let ref = owners.first else { return [] }
        return self.sides(for: ref, in: sides, catalogue: catalogue)
    }

    /// The anchor's original entry, only with readable words, a callback and a
    /// selection the shared Details resolve.
    static func open(_ open: HorseRacingOriginalOpen10868?, canOpen: Bool,
                     catalogue: OriginalMarketDetails9483.Catalogue?) -> HorseRacingOriginalOpen10868? {
        guard canOpen, let open, HorseRacingPageModel10868.readable(open.label) != nil,
              OriginalMarketDetails9483.content(catalogue: catalogue, selection: open.selection) != nil
        else { return nil }
        return open
    }
}

nonisolated enum HorseRacingAccessibilityID10868 {
    static let page = "horseRacing10868.page"
    static let header = "horseRacing10868.header"
    static let about = "horseRacing10868.about"
    static let notice = "horseRacing10868.notice"
    static let anchor = "horseRacing10868.anchor"
    static let picks = "horseRacing10868.picks"
    static let cohort = "horseRacing10868.cohort"
    static let originalEntry = "horseRacing10868.originalEntry"
    static let sourceEntry = "horseRacing10868.sourceEntry"
    static let finish = "horseRacing10868.finish"
    static let finishExpand = "horseRacing10868.finishExpand"
    static let finishPending = "horseRacing10868.finishPending"
    static let catalogue = "horseRacing10868.catalogue"
    static let catalogueToggle = "horseRacing10868.catalogueToggle"
    static let allOriginals = "horseRacing10868.allOriginals"
    static let fullHistory = "horseRacing10868.fullHistory"
    static let fullFinish = "horseRacing10868.fullFinish"
    static let originals = "horseRacing10868.originals"
    static let original = "horseRacing10868.original"
    static let sides = "horseRacing10868.sides"
    static let aboutText = "horseRacing10868.aboutText"
    static let sourceText = "horseRacing10868.sourceText"
    static let readerHeader = "horseRacing10868.readerHeader"
    static let readerAbout = "horseRacing10868.readerAbout"
    static let link = "horseRacing10868.link"
    static let pagerPrevious = "horseCatalogue10868.previous"
    static let pagerNext = "horseCatalogue10868.next"
    static func pick(_ outcomeID: String) -> String { "horseRacing10868.pick.\(outcomeID)" }
    static func row(_ index: Int) -> String { "horseCatalogue10868.row.\(index)" }
    static func side(_ index: Int, _ side: Int) -> String { "horseCatalogue10868.row.\(index).side.\(side)" }
}

// MARK: - Page model

nonisolated struct HorseRacingPageModel10868: Equatable {
    let input: HorseRacingPageInput10868

    init(_ input: HorseRacingPageInput10868) {
        self.input = input
    }

    /// The finish card at the final only, and only with a final card input.
    var finish: HorseRacingFinishInput10868? {
        guard input.phase == .final, let finish = input.finish, finish.card.phase == .final else { return nil }
        return finish
    }

    /// During the race only: the owner's words for the absent live positions.
    var finishPending: String? {
        input.phase == .during ? Self.readable(input.finishPending) : nil
    }

    /// The catalogue at the page's own phase. Otherwise nothing.
    var catalogue: HorseCatalogueInput10868? {
        guard let catalogue = input.catalogue, catalogue.phase == input.phase else { return nil }
        return catalogue
    }

    /// Shown unless the owner's disclosure is collapsed.
    var showsCatalogue: Bool {
        catalogue != nil && (input.catalogueDisclosure?.isOn ?? true)
    }

    var notice: String? { Self.readable(input.notice) }

    /// Full-size content exists for the history always, and for the finish at the final.
    func readerShows(_ mode: HorseRacingMode10868) -> Bool {
        switch mode {
        case .fullHistory: true
        case .fullFinish: finish != nil
        default: false
        }
    }

    /// The anchor's full-size content: the same history without an expand
    /// control inside the reader, at the owner's reader height when supplied.
    /// Every other field, the layout included, is the owner's.
    var readerHistory: FieldHistoryInput10868 {
        let history = input.history
        return FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: input.readerPlotHeight ?? history.plotHeight,
            unboundReadingWords: history.unboundReadingWords, plotUnavailableWords: history.plotUnavailableWords,
            windows: history.windows, scale: history.scale, moreOriginals: history.moreOriginals,
            details: history.details, expand: nil, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: history.inspection,
            layout: history.layout,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: history.showsKey
        )
    }

    // MARK: Text and entries

    static func hasWords(_ section: HorseRacingSection10868) -> Bool {
        readable(section.title) != nil || section.paragraphs.contains { readable($0) != nil }
    }

    /// Owner text, when it carries readable words.
    static func readableText(_ text: HorseRacingText10868?) -> HorseRacingText10868? {
        guard let text, readable(text.title) != nil || text.sections.contains(where: hasWords) else { return nil }
        return text
    }

    var about: HorseRacingText10868? { Self.readableText(input.about) }

    var source: HorseRacingText10868? { Self.readableText(input.source) }

    /// The result source, with the finish only.
    var resultSource: HorseRacingText10868? { finish.flatMap { Self.readableText($0.source) } }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil && Self.readable(input.header.aboutLabel) != nil
    }

    func sourceAvailable(canOpen: Bool) -> Bool {
        canOpen && source != nil && Self.readable(input.copy.sourceLabel) != nil
    }

    func allOriginalsAvailable(canOpen: Bool) -> Bool {
        canOpen && Self.readable(input.copy.allOriginalsLabel) != nil
    }

    /// The compact reader heading's Info: full-size history and finish only —
    /// the page has the header's own control.
    func aboutEntry(mode: HorseRacingMode10868, canOpen: Bool) -> Bool {
        (mode == .fullHistory || mode == .fullFinish) && aboutAvailable(canOpen: canOpen)
    }

    /// The finish card's expand: a readable label and a callback.
    func finishExpandAvailable(canOpen: Bool) -> Bool {
        canOpen && finish.map { Self.readable($0.expandLabel) != nil } == true
    }

    /// The catalogue disclosure's id, only with a callback, readable words and
    /// an id the cohort toggle does not share.
    func catalogueToggleID(canToggle: Bool) -> String? {
        guard canToggle, let toggle = input.catalogueDisclosure,
              Self.readable(toggle.id) != nil, Self.readable(toggle.label) != nil,
              toggle.id != input.picks?.cohort?.id
        else { return nil }
        return toggle.id
    }

    /// The cohort toggle's id, unless the catalogue disclosure shares it.
    func cohortID(canToggle: Bool) -> String? {
        guard let picks = input.picks, let id = HorseRacingPicksModel10868(picks).cohortID(canToggle: canToggle),
              id != input.catalogueDisclosure?.id
        else { return nil }
        return id
    }

    static func link(_ text: HorseRacingText10868, canOpen: Bool) -> HorseRacingLink10868? {
        guard canOpen, let link = text.link, readable(link.id) != nil, readable(link.label) != nil else { return nil }
        return link
    }

    static func readable(_ words: String?) -> String? {
        guard let words, !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return words
    }

    /// The arrangements to try, in order. Accessibility sizes and a compact
    /// width stack; a regular or unspecified width tries the history beside
    /// the finish, then stacks.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [HorseRacingArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

// MARK: - Text content

/// The owner's About, source details or result source with its link only when
/// the host can open it.
struct HorseRacingTextContent10868: View {
    let text: HorseRacingText10868
    /// Hands back the link's exact id.
    var onLink: ((String) -> Void)? = nil
    /// The page's compact result source uses smaller type.
    var compact: Bool = false

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var link: HorseRacingLink10868? { HorseRacingPageModel10868.link(text, canOpen: onLink != nil) }

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 8 : 16) {
            if let title = HorseRacingPageModel10868.readable(text.title) {
                Text(title)
                    .font(compact ? .subheadline.weight(.semibold) : .headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(text.sections.enumerated()), id: \.offset) { _, section in
                if HorseRacingPageModel10868.hasWords(section) {
                    VStack(alignment: .leading, spacing: 6) {
                        if let title = HorseRacingPageModel10868.readable(section.title) {
                            Text(title)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                        }
                        ForEach(Array(section.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            if let words = HorseRacingPageModel10868.readable(paragraph) {
                                Text(words)
                                    .font(compact ? .subheadline : .body)
                                    .foregroundStyle(DS.textPrimary)
                            }
                        }
                    }
                }
            }
            if let link, let onLink {
                Button {
                    onLink(link.id)
                } label: {
                    HStack(spacing: 8) {
                        Text(link.label)
                            .font(.body.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Image(systemName: "arrow.up.right")
                            .font(.body.weight(.semibold))
                            .accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                    .frame(minHeight: controlSize)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(HorseRacingAccessibilityID10868.link)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Picks view

struct HorseRacingPicksView10868: View {
    let input: HorseRacingPicksInput10868
    /// Hands back the exact runner.
    var onChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// Hands back the cohort toggle's exact id; nil when the page withholds it.
    var cohortID: String? = nil
    var onToggle: ((String) -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var model: HorseRacingPicksModel10868 { HorseRacingPicksModel10868(input) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let notice = model.notice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HorseRacingWrapLayout10868(spacing: 6) {
                ForEach(Array(model.rows.enumerated()), id: \.offset) { _, row in
                    pick(row)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(input.groupLabel)
            if let toggle = input.cohort, HorseRacingPageModel10868.readable(toggle.label) != nil {
                toggleControl(toggle)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityIdentifier(HorseRacingAccessibilityID10868.picks)
    }

    @ViewBuilder private func pick(_ row: HorseRacingPickRow10868) -> some View {
        let id = HorseRacingAccessibilityID10868.pick(row.pick.ref.outcomeID)
        if let original = row.resolution.original {
            let selected = model.isSelected(row)
            let ref = model.chooseRef(row, canChoose: onChoose != nil)
            let label = HStack(spacing: 6) {
                if let shape = row.pick.shape {
                    Image(systemName: HorseCatalogueGeometry10868.symbol(shape))
                        .font(.caption2)
                        .accessibilityHidden(true)
                }
                Text(original.name)
                    .font(.subheadline.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
            }
            .foregroundStyle(selected ? DS.cardBg : DS.textPrimary)
            .padding(.horizontal, 10)
            .frame(minHeight: controlSize)
            .background(selected ? DS.textPrimary : DS.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.border, lineWidth: 1))
            if let ref, let onChoose {
                Button {
                    onChoose(ref)
                } label: {
                    label.contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(model.spoken(row))
                .accessibilityHint(input.chooseHint ?? "")
                .accessibilityAddTraits(selected ? .isSelected : [])
                .accessibilityIdentifier(id)
            } else {
                label
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(model.spoken(row))
                    .accessibilityAddTraits(selected ? .isSelected : [])
                    .accessibilityIdentifier(id)
            }
        } else {
            VStack(alignment: .leading, spacing: 2) {
                Text(input.unavailableWords)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 10)
            .frame(minHeight: controlSize)
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.border, lineWidth: 1))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.unavailableWords)
            .accessibilityIdentifier(id)
        }
    }

    @ViewBuilder private func toggleControl(_ toggle: HorseRacingToggle10868) -> some View {
        let label = Text(toggle.label)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(cohortID == nil ? DS.textSecondary : DS.blue)
            .fixedSize(horizontal: false, vertical: true)
            .frame(minHeight: controlSize, alignment: .leading)
        if let id = cohortID, let onToggle {
            Button {
                onToggle(id)
            } label: {
                label.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityAddTraits(toggle.isOn ? .isSelected : [])
            .accessibilityIdentifier(HorseRacingAccessibilityID10868.cohort)
        } else {
            label
                .accessibilityAddTraits(toggle.isOn ? .isSelected : [])
                .accessibilityIdentifier(HorseRacingAccessibilityID10868.cohort)
        }
    }
}

// MARK: - Catalogue view

struct HorseCatalogueView10868: View {
    let input: HorseCatalogueInput10868
    /// Each runner's exact Yes and No originals, in the owner's order.
    var sides: [HorseCatalogueSide10868] = []
    /// The shared Details' catalogue every Yes and No action resolves against.
    var originals: OriginalMarketDetails9483.Catalogue? = nil
    /// Opens the exact runner's history.
    var onRunner: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// Opens the exact Yes or No original.
    var onSide: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// Hands back the exact target group id.
    var onGroup: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @ScaledMetric(relativeTo: .body) private var cardMinimumWidth: CGFloat = 150
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 24
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 14
    @ScaledMetric(relativeTo: .caption) private var dotDiameter: CGFloat = 9

    var model: HorseCatalogueModel10868 { HorseCatalogueModel10868(input) }

    /// A row's Yes and No originals: only for a row that resolves.
    func sideStates(_ row: HorseCatalogueRow10868) -> [HorseCatalogueSideState10868] {
        guard let ref = row.resolution.original?.ref else { return [] }
        return HorseRacingOriginalRules10868.sides(for: ref, in: sides, catalogue: originals)
    }

    private var inset: CGFloat { dotDiameter / 2 + 1 }

    var body: some View {
        let model = self.model
        VStack(alignment: .leading, spacing: 12) {
            heading(model)
            pager(model)
            if let notice = model.notice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let words = model.groupWords {
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                HorseCatalogueGridLayout10868(
                    spacing: 10, minimumWidth: cardMinimumWidth, maximumColumns: 4,
                    accessibilitySize: typeSize.isAccessibilitySize
                ) {
                    ForEach(Array(model.rows.enumerated()), id: \.offset) { index, row in
                        card(row, index: index, model: model)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Heading and pager

    private func heading(_ model: HorseCatalogueModel10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.copy.heading)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .accessibilityAddTraits(.isHeader)
            if let note = HorseRacingPageModel10868.readable(input.copy.note) {
                Text(note)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
            }
            let layout = typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
                : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 10))
            layout {
                Text(input.copy.scaleLabel)
                if !typeSize.isAccessibilitySize { Spacer(minLength: 8) }
                if let words = model.scaleWords {
                    Text(words)
                }
            }
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private func pager(_ model: HorseCatalogueModel10868) -> some View {
        HStack(alignment: .center, spacing: 10) {
            stepButton(input.previous, target: model.stepTarget(input.previous, canMove: onGroup != nil),
                       id: HorseRacingAccessibilityID10868.pagerPrevious)
            Text(model.position ?? "")
                .font(.subheadline)
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity)
            stepButton(input.next, target: model.stepTarget(input.next, canMove: onGroup != nil),
                       id: HorseRacingAccessibilityID10868.pagerNext)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.pagerLabel)
    }

    @ViewBuilder private func stepButton(_ step: HorseCatalogueStep10868?, target: String?, id: String) -> some View {
        if let step, HorseRacingPageModel10868.readable(step.label) != nil {
            let label = Text(step.label)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(target == nil ? DS.textMuted : DS.blue)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 10)
                .frame(minWidth: controlSize, minHeight: controlSize)
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(DS.border, lineWidth: 1))
            if let target, let onGroup {
                Button {
                    onGroup(target)
                } label: {
                    label.contentShape(Rectangle())
                }
                .accessibilityLabel(step.spokenLabel ?? step.label)
                .accessibilityIdentifier(id)
            } else {
                label
                    .accessibilityLabel(step.spokenLabel ?? step.label)
                    .accessibilityAddTraits(.isStaticText)
                    .accessibilityIdentifier(id)
            }
        }
    }

    // MARK: Card

    @ViewBuilder private func card(_ row: HorseCatalogueRow10868, index: Int, model: HorseCatalogueModel10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if row.resolution.original != nil {
                let ref = model.openRef(row, canOpen: onRunner != nil)
                if let ref, let onRunner {
                    Button {
                        onRunner(ref)
                    } label: {
                        preview(row, model: model).contentShape(Rectangle())
                    }
                    .accessibilityLabel(row.resolution.original?.name ?? row.slot.name)
                    .accessibilityValue(model.rowSummary(row))
                    .accessibilityHint(input.copy.openHint ?? "")
                    .accessibilityAddTraits(model.isSelected(row) ? .isSelected : [])
                    .accessibilityIdentifier(HorseRacingAccessibilityID10868.row(index))
                } else {
                    preview(row, model: model)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(row.resolution.original?.name ?? row.slot.name)
                        .accessibilityValue(model.rowSummary(row))
                        .accessibilityIdentifier(HorseRacingAccessibilityID10868.row(index))
                }
                sides(row, index: index)
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    if let name = HorseRacingPageModel10868.readable(row.slot.name) {
                        Text(name)
                            .font(.body.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Text(input.copy.unavailableWords)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(model.rowSummary(row))
                .accessibilityIdentifier(HorseRacingAccessibilityID10868.row(index))
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(model.isSelected(row) ? DS.blue : DS.border, lineWidth: model.isSelected(row) ? 2 : 1)
        )
    }

    /// The whole name, the labelled before figure beside the finish in its own
    /// units, the hollow dot on the shared scale, and the owner's words.
    private func preview(_ row: HorseCatalogueRow10868, model: HorseCatalogueModel10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let name = row.resolution.original?.name {
                Text(name)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let words = model.selectedWords(row) {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark").font(.caption2.weight(.bold))
                    Text(words).font(.caption.weight(.semibold))
                }
                .foregroundStyle(DS.blue)
                .fixedSize(horizontal: false, vertical: true)
            }
            let layout = typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8))
                : AnyLayout(HStackLayout(alignment: .bottom, spacing: 10))
            layout {
                chanceBlock(row, model: model)
                if !typeSize.isAccessibilitySize { Spacer(minLength: 0) }
                if let ordinal = HorseCatalogueModel10868.ordinal(row) {
                    finishBlock(ordinal)
                }
            }
            if case .value(_, let fraction) = row.chance {
                track(fraction: fraction, ticks: model.ticks.map(\.fraction))
            }
            if let words = HorseCatalogueModel10868.finishWords(row) {
                ownerWords(words)
            }
            if let words = model.stateWords(row) {
                ownerWords(words)
            }
            if let status = model.status(row) {
                ownerWords(status)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func chanceBlock(_ row: HorseCatalogueRow10868, model: HorseCatalogueModel10868) -> some View {
        let recorded = model.isRecorded(row)
        return VStack(alignment: .leading, spacing: 2) {
            if recorded, let label = model.figureLabel(row) {
                Text(label)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let figure = model.figure(row) {
                Text(figure)
                    .font(recorded ? Font.system(size: figureSize, weight: .bold) : Font.subheadline)
                    .monospacedDigit()
                    .foregroundStyle(recorded ? DS.blue : DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func finishBlock(_ ordinal: String) -> some View {
        VStack(alignment: typeSize.isAccessibilitySize ? .leading : .trailing, spacing: 2) {
            Text(input.copy.finishUnit)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize()
            Text(ordinal)
                .font(.system(size: figureSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize()
        }
    }

    /// The shared scale line, zero and the owner's ticks, then the hollow dot
    /// from the finish card's own strip plan.
    private func track(fraction: Double, ticks: [Double]) -> some View {
        let lineColor = DS.border
        let ringFill = DS.cardBg
        let accent = DS.blue
        let inset = self.inset
        let diameter = dotDiameter
        return Canvas { context, size in
            guard let plan = FieldFinishGeometry10868.stripPlan(fraction: fraction, ticks: ticks, in: size, inset: inset, dotDiameter: diameter) else { return }
            var line = Path()
            line.move(to: CGPoint(x: plan.zeroX, y: plan.baselineY))
            line.addLine(to: CGPoint(x: plan.ceilingX, y: plan.baselineY))
            context.stroke(line, with: .color(lineColor), lineWidth: 2)
            for x in plan.tickXs {
                var tick = Path()
                tick.move(to: CGPoint(x: x, y: plan.tickTop))
                tick.addLine(to: CGPoint(x: x, y: plan.baselineY))
                context.stroke(tick, with: .color(lineColor), lineWidth: 1)
            }
            if let dot = plan.dot {
                context.fill(Path(ellipseIn: dot), with: .color(ringFill))
                context.stroke(Path(ellipseIn: dot.insetBy(dx: 1, dy: 1)), with: .color(accent), lineWidth: 2)
            }
        }
        .frame(maxWidth: .infinity, minHeight: trackHeight, maxHeight: trackHeight)
        .accessibilityHidden(true)
    }

    /// The runner's exact Yes and No originals; one that the shared Details do
    /// not resolve keeps its words and acts on nothing.
    private func sides(_ row: HorseCatalogueRow10868, index: Int) -> some View {
        HorseRacingWrapLayout10868(spacing: 8) {
            ForEach(Array(sideStates(row).enumerated()), id: \.offset) { position, state in
                sideControl(state, id: HorseRacingAccessibilityID10868.side(index, position))
            }
        }
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder private func sideControl(_ state: HorseCatalogueSideState10868, id: String) -> some View {
        if let selection = state.selection, let onSide {
            Button {
                onSide(selection)
            } label: {
                Text(state.side.label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.blue)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 10)
                    .frame(minHeight: controlSize)
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(DS.border, lineWidth: 1))
                    .contentShape(Rectangle())
            }
            .accessibilityLabel(state.side.spokenLabel ?? state.side.label)
            .accessibilityIdentifier(id)
        } else {
            Text(HorseCatalogueModel10868.joined([state.side.label, state.selection == nil ? input.copy.sideUnavailable : ""]))
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(minHeight: controlSize)
                .accessibilityIdentifier(id)
        }
    }

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - Page view

struct HorseRacingEventPagePresentation10868: View {
    let input: HorseRacingPageInput10868
    var mode: HorseRacingMode10868 = .page
    /// The generic catalogue and Details modes' content and every Yes and No
    /// action's resolver; nil: none of them.
    var originals: HorseRacingOriginals10868? = nil
    /// Opens the race About.
    var onAbout: (() -> Void)? = nil
    /// Opens the source details.
    var onSource: (() -> Void)? = nil
    /// Opens a text link by its exact id.
    var onLink: ((String) -> Void)? = nil
    /// Chooses the exact runner in place.
    var onRunner: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// Opens the exact runner's history.
    var onRunnerHistory: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// Hands back a toggle's exact id: the cohort or the catalogue disclosure.
    var onToggle: ((String) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Opens the exact original with the owner's selected position, unchanged.
    var onOriginalOpen: ((HorseRacingOriginalOpen10868) -> Void)? = nil
    /// Opens the finish card full size.
    var onFinishExpand: (() -> Void)? = nil
    /// Hands back the exact catalogue group id.
    var onCatalogueGroup: ((String) -> Void)? = nil
    /// Selects an exact Yes or No original.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// Opens the generic original catalogue.
    var onAllOriginals: (() -> Void)? = nil
    /// The owner's hold, called once before a page, catalogue or Details action.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var historyMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var finishMinWidth: CGFloat = 300
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var model: HorseRacingPageModel10868 { HorseRacingPageModel10868(input) }

    // MARK: Holds

    /// A page, catalogue or Details action, after the owner's interaction
    /// hook. No host callback: no action and no hook call. No hook: the exact
    /// callback.
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

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .fullHistory: fullHistoryMode
            case .fullFinish: fullFinishMode
            case .catalogue: catalogueMode
            case .original: originalMode
            case .about: textMode(aboutContent(), id: HorseRacingAccessibilityID10868.aboutText)
            case .source: textMode(sourceContent(), id: HorseRacingAccessibilityID10868.sourceText)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    /// The header's Info on the page, after the hook; nil without readable
    /// About words or a callback.
    func headerAbout() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil) else { return nil }
        return Self.heldAction(onAbout, by: onInteraction)
    }

    /// The picks; choose and the cohort toggle pass the hook first.
    func picksContent() -> HorseRacingPicksView10868? {
        input.picks.map {
            HorseRacingPicksView10868(
                input: $0,
                onChoose: Self.held(onRunner, by: onInteraction),
                cohortID: model.cohortID(canToggle: onToggle != nil),
                onToggle: Self.held(onToggle, by: onInteraction)
            )
        }
    }

    /// The anchor passes the hook first; the full-size history keeps the exact callbacks.
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let interaction = reader ? nil : onInteraction
        return FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : input.history,
            onAction: Self.held(onHistoryAction, by: interaction),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: interaction),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: interaction)
        )
    }

    /// The finish card at the final only. On the page a row opens the runner's
    /// history after the hook; full size it keeps the exact callback.
    func finishContent(reader: Bool) -> FieldFinishComparisonPresentation10868? {
        model.finish.map {
            FieldFinishComparisonPresentation10868(
                input: $0.card,
                onOpenHistory: Self.held(onRunnerHistory, by: reader ? nil : onInteraction)
            )
        }
    }

    /// The result source, with the finish only; its link passes the hook on the page.
    func resultSourceContent(reader: Bool) -> HorseRacingTextContent10868? {
        model.resultSource.map {
            HorseRacingTextContent10868(text: $0, onLink: Self.held(onLink, by: reader ? nil : onInteraction), compact: !reader)
        }
    }

    /// The compact catalogue at the page's phase, shown unless collapsed. A
    /// row, a side and a step pass the hook first.
    func catalogueContent() -> HorseCatalogueView10868? {
        guard model.showsCatalogue, let catalogue = model.catalogue else { return nil }
        return HorseCatalogueView10868(
            input: catalogue,
            sides: originals?.sides ?? [],
            originals: originals?.catalogue,
            onRunner: Self.held(onRunnerHistory, by: onInteraction),
            onSide: Self.held(onOriginalSelect, by: onInteraction),
            onGroup: Self.held(onCatalogueGroup, by: onInteraction)
        )
    }

    /// The generic original catalogue with the held selection, its select after the hook.
    func originalCatalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: Self.held(onOriginalSelect, by: onInteraction)
            )
        }
    }

    /// The held original's existing Details, its history intent after the hook.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: Self.held(onOriginalHistory, by: onInteraction)
            )
        }
    }

    /// The held original's runner sides in Details, each after the hook.
    func originalSides() -> [HorseCatalogueSideState10868] {
        HorseRacingOriginalRules10868.heldSides(originals?.selection, in: originals?.sides ?? [], catalogue: originals?.catalogue)
    }

    /// The anchor's exact original entry, when the shared Details resolve it.
    func originalEntry() -> HorseRacingOriginalOpen10868? {
        HorseRacingOriginalRules10868.open(originals?.open, canOpen: onOriginalOpen != nil, catalogue: originals?.catalogue)
    }

    func aboutContent() -> HorseRacingTextContent10868? {
        model.about.map { HorseRacingTextContent10868(text: $0, onLink: onLink) }
    }

    func sourceContent() -> HorseRacingTextContent10868? {
        model.source.map { HorseRacingTextContent10868(text: $0, onLink: onLink) }
    }

    /// Full-size content's Info: the exact callback, no hook.
    func openReaderAbout() {
        guard model.aboutAvailable(canOpen: onAbout != nil) else { return }
        onAbout?()
    }

    func openSource() {
        guard model.sourceAvailable(canOpen: onSource != nil) else { return }
        Self.heldAction(onSource, by: onInteraction)?()
    }

    func openAllOriginals() {
        guard model.allOriginalsAvailable(canOpen: onAllOriginals != nil) else { return }
        Self.heldAction(onAllOriginals, by: onInteraction)?()
    }

    func openFinish() {
        guard model.finishExpandAvailable(canOpen: onFinishExpand != nil) else { return }
        Self.heldAction(onFinishExpand, by: onInteraction)?()
    }

    func openOriginal() {
        guard let open = originalEntry() else { return }
        Self.held(onOriginalOpen, by: onInteraction)?(open)
    }

    func toggleCatalogue() {
        guard let id = model.catalogueToggleID(canToggle: onToggle != nil) else { return }
        Self.held(onToggle, by: onInteraction)?(id)
    }

    /// Selects one of the held original's runner sides in Details, after the hook.
    func selectSide(_ state: HorseCatalogueSideState10868) {
        guard let selection = state.selection else { return }
        Self.held(onOriginalSelect, by: onInteraction)?(selection)
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 18) {
            header
            hero
            if let words = model.finishPending {
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(HorseRacingCardSurface10868())
                    .accessibilityIdentifier(HorseRacingAccessibilityID10868.finishPending)
            }
            cataloguePanel
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(HorseRacingAccessibilityID10868.page)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    if let eyebrow = HorseRacingPageModel10868.readable(input.header.eyebrow) {
                        Text(eyebrow)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                    }
                    Text(input.header.title)
                        .font(.title2.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .accessibilityAddTraits(.isHeader)
                    let line = HorseCatalogueModel10868.joined([input.header.place ?? "", input.header.date ?? ""])
                    if !line.isEmpty {
                        Text(line)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondary)
                    }
                    if let status = HorseRacingPageModel10868.readable(input.header.status) {
                        Text(status)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textPrimary)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                if let about = headerAbout() {
                    Button(action: about) {
                        Image(systemName: "info.circle")
                            .font(.title3)
                            .foregroundStyle(DS.textPrimary)
                            .frame(minWidth: controlSize, minHeight: controlSize)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(input.header.aboutLabel)
                    .accessibilityHint(input.header.aboutHint ?? "")
                    .accessibilityIdentifier(HorseRacingAccessibilityID10868.about)
                }
            }
            if let notice = model.notice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(HorseRacingAccessibilityID10868.notice)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(HorseRacingAccessibilityID10868.header)
    }

    /// The anchor beside the finish where both keep their minimum widths,
    /// otherwise stacked.
    @ViewBuilder private var hero: some View {
        let arrangements = HorseRacingPageModel10868.arrangements(
            sizeClass: sizeClass,
            accessibilitySize: typeSize.isAccessibilitySize
        )
        if model.finish == nil || arrangements == [.stacked] {
            heroStacked
        } else {
            ViewThatFits(in: .horizontal) {
                heroSideBySide
                heroStacked
            }
        }
    }

    private var heroStacked: some View {
        VStack(alignment: .leading, spacing: 18) {
            anchorCard
            finishCard
        }
    }

    private var heroSideBySide: some View {
        HStack(alignment: .top, spacing: 24) {
            anchorCard
                .frame(minWidth: historyMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
            finishCard
                .frame(minWidth: finishMinWidth, alignment: .topLeading)
        }
    }

    /// The picks, the history, then the original and source entries.
    private var anchorCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let picks = picksContent() {
                picks
            }
            historyContent(reader: false)
            if let open = originalEntry() {
                entry(open.label, action: openOriginal, id: HorseRacingAccessibilityID10868.originalEntry)
            }
            if model.sourceAvailable(canOpen: onSource != nil), let label = input.copy.sourceLabel {
                entry(label, action: openSource, id: HorseRacingAccessibilityID10868.sourceEntry)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(HorseRacingCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(HorseRacingAccessibilityID10868.anchor)
    }

    /// The finish card and its result source, at the final only.
    @ViewBuilder private var finishCard: some View {
        if let finish = model.finish, let card = finishContent(reader: false) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .center, spacing: 8) {
                    if let eyebrow = HorseRacingPageModel10868.readable(finish.eyebrow) {
                        Text(eyebrow)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 8)
                    if model.finishExpandAvailable(canOpen: onFinishExpand != nil) {
                        Button(action: openFinish) {
                            Image(systemName: "arrow.up.left.and.arrow.down.right")
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .frame(minWidth: controlSize, minHeight: controlSize)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(finish.expandLabel)
                        .accessibilityIdentifier(HorseRacingAccessibilityID10868.finishExpand)
                    }
                }
                card
                if let source = resultSourceContent(reader: false) {
                    source
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(HorseRacingCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(HorseRacingAccessibilityID10868.finish)
        }
    }

    /// The catalogue disclosure, the compact catalogue and the generic
    /// catalogue entry.
    @ViewBuilder private var cataloguePanel: some View {
        let catalogue = catalogueContent()
        let allOriginals = model.allOriginalsAvailable(canOpen: onAllOriginals != nil)
        let disclosure = model.catalogue == nil ? nil : input.catalogueDisclosure
        if catalogue != nil || allOriginals || disclosure != nil {
            VStack(alignment: .leading, spacing: 12) {
                if let disclosure, HorseRacingPageModel10868.readable(disclosure.label) != nil {
                    disclosureControl(disclosure)
                }
                if let catalogue {
                    catalogue
                }
                if allOriginals, let label = input.copy.allOriginalsLabel {
                    entry(label, action: openAllOriginals, id: HorseRacingAccessibilityID10868.allOriginals)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(HorseRacingCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(HorseRacingAccessibilityID10868.catalogue)
        }
    }

    @ViewBuilder private func disclosureControl(_ toggle: HorseRacingToggle10868) -> some View {
        let label = HStack(spacing: 8) {
            Text(toggle.label)
                .font(.body.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
            Image(systemName: toggle.isOn ? "chevron.up" : "chevron.down")
                .font(.body.weight(.semibold))
                .accessibilityHidden(true)
        }
        .foregroundStyle(DS.textPrimary)
        .frame(minHeight: controlSize)
        if model.catalogueToggleID(canToggle: onToggle != nil) != nil {
            Button(action: toggleCatalogue) {
                label.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityAddTraits(toggle.isOn ? .isSelected : [])
            .accessibilityIdentifier(HorseRacingAccessibilityID10868.catalogueToggle)
        } else {
            label
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(HorseRacingAccessibilityID10868.catalogueToggle)
        }
    }

    private func entry(_ label: String, action: @escaping () -> Void, id: String) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Text(label)
                    .font(.body.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right")
                    .font(.body.weight(.semibold))
                    .accessibilityHidden(true)
            }
            .foregroundStyle(DS.blue)
            .frame(minHeight: controlSize)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }

    // MARK: Full-size content

    private var fullHistoryMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            compactHeader
            historyContent(reader: true)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(HorseRacingAccessibilityID10868.fullHistory)
    }

    /// The same finish card and result source, full size; none before the final.
    @ViewBuilder private var fullFinishMode: some View {
        if let card = finishContent(reader: true) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                card
                if let source = resultSourceContent(reader: true) {
                    source
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(HorseRacingAccessibilityID10868.fullFinish)
        }
    }

    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = HorseRacingPageModel10868.readable(input.reader.state) {
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
                .accessibilityLabel(input.header.aboutLabel)
                .accessibilityHint(input.header.aboutHint ?? "")
                .accessibilityIdentifier(HorseRacingAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(HorseRacingAccessibilityID10868.readerHeader)
    }

    // MARK: Originals and text

    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = originalCatalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(HorseRacingAccessibilityID10868.originals)
        }
    }

    /// The held original's runner sides, then its existing Details.
    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            VStack(alignment: .leading, spacing: 12) {
                let sides = originalSides()
                if !sides.isEmpty {
                    HorseRacingWrapLayout10868(spacing: 8) {
                        ForEach(Array(sides.enumerated()), id: \.offset) { _, state in
                            sideSwitch(state)
                        }
                    }
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier(HorseRacingAccessibilityID10868.sides)
                }
                details
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(HorseRacingAccessibilityID10868.original)
        }
    }

    @ViewBuilder private func sideSwitch(_ state: HorseCatalogueSideState10868) -> some View {
        let selected = state.selection != nil && state.selection == originals?.selection
        let label = Text(state.side.label)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(selected ? DS.cardBg : (state.selection == nil ? DS.textSecondary : DS.textPrimary))
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 12)
            .frame(minHeight: controlSize)
            .background(selected ? DS.textPrimary : DS.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        if state.selection != nil, onOriginalSelect != nil {
            Button {
                selectSide(state)
            } label: {
                label.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(state.side.spokenLabel ?? state.side.label)
            .accessibilityAddTraits(selected ? .isSelected : [])
        } else {
            label
                .accessibilityLabel(state.side.spokenLabel ?? state.side.label)
                .accessibilityAddTraits(selected ? .isSelected : [])
        }
    }

    @ViewBuilder private func textMode(_ content: HorseRacingTextContent10868?, id: String) -> some View {
        if let content {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(id)
        }
    }
}

/// The reference's white card on the page surface.
private struct HorseRacingCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
