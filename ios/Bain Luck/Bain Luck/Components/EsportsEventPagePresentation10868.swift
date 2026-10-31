import SwiftUI

// #10868 — the esports match screen (`esports`): one native presentation for a
// two-team esports match before, during and after play, composed from the
// accepted rugby match page and its shared leaves. A fan sees, in this order:
// the match headline — both named teams at equal prominence, each team's
// pre-match chance with its own date, during play the recorded or current
// chance beside it, at the final the separately reported result beside it,
// and the headline's own info control; every team's dated readouts at one
// scaled figure size directly above the tall, named, shape-keyed win
// probability history; then the owner's story stream (or the stories directly)
// — the winner story and the round-margin story; then every original market by
// its exact identity and the all-originals entry. The history and each story
// open as full-size content made of the same Views and inputs; all originals,
// the held original's Details, the match Info and each source document are
// further content modes.
//
// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: both pre-match team chances and
// the recorded journey anchor the native esports page; original winner
// expectations and the round margin compare visually with a separately
// reported actual result.
//
// REUSE DECISION. The accepted rugby match page contract
// (`RugbyMatchEventPagePresentation10868`, `RugbyMatchEventPageModel10868`)
// already expresses this match's headline, comparison, history, reader height,
// originals, catalogue entry, Info and source documents, and its catalogue,
// Details, Info and source content modes. This file reuses that contract
// whole, unchanged, through an internal rugby input built from the owner's own
// fields (no compact context and no chance-to-result story, which this route
// does not show):
//
//   • page leaves come from the rugby page's own builders —
//     `headlineContent()` (`FieldPhaseHeadlinePresentation10868`),
//     `comparisonContent(reader:)` (`RugbyMatchEventPageComparisonPresentation10868`
//     at the shared figure size), `historyContent(reader:)`
//     (`FieldProbabilityHistoryPresentation10868` from the rugby model's
//     presented or full-size copy, `RugbyMatchEventPageModel10868.readerPlotHeight`),
//     `choicesContent()` (`OriginalMarketChooserView9483`) and `catalogueAction`
//     — so every hold, hand-off and exact callback is the rugby page's own;
//   • the catalogue, Details, Info and source modes ARE the rugby page view in
//     that mode (`OriginalMarketCatalogueView9483`, `OriginalMarketDetailsView9483`,
//     `RugbyMatchEventPageSectionsContent10868`).
//
// What the accepted contracts cannot express, and is therefore drawn here:
//
//   • the rugby page's story slot is closed to one
//     `HistoricalChanceInput10868` (one subject's pre-match chance and a
//     checkpoint beside one actual) and its card set is closed to history and
//     story; the winner story needs every side's own pre-match ring with its
//     own date and that side's separately reported result and count, and the
//     margin story needs one-block-per-unit margin blocks against a threshold
//     marker. Neither fits that input without filler slots;
//   • the rugby page has no story stream and no reader navigation between
//     stories; the combat and hockey pages' story sets are closed to their own
//     leaves (methods, rounds, duration; player contributions and the hockey
//     matrix headline);
//   • the rugby page's page arrangement puts the originals directly under the
//     history; the approved reading order puts the stories first.
//
// So only the page and reader composition, the two story faces and one
// exact-identity presentation rule for the history readout are new here. The
// shared files are not edited.
//
// Presentation only, from the approved `EsportsHeadline.tsx`,
// `EsportsWinnerJourney.tsx`, `EsportsChanceComparison.tsx`,
// `EsportsStories.tsx`, `EsportsQuestionVisual.tsx`, their stylesheets and the
// native composed reader adoption record. Their fixture composition, wire
// decoders, qualifiers, session reducers, formatters, ranking, timers,
// subscriptions and report or truth policy are NOT ported. Nothing here
// contains a specimen name, number, identifier, map or clock.
//
// THE BASELINE COLLAPSE. While the owner's readout is pre-match beside the
// inspected reading and, for every exactly identified team, the inspected
// observation IS the very observation the owner's pre-match reading is bound
// to (the same point id, uniquely present and placeable), the duplicate pair
// collapses: a presentation copy shows the single pre-match slot under the
// owner's own pre-match label. Equal figures at different observations are
// different ids and keep both slots with their own dates. Nothing is compared
// by value; the owner's input is never changed.
//
// The page's phase is the owner's explicit `RugbyMatchEventPagePhase10868`,
// never read from a raw status, a clock, a quote, a score or a settlement.
// Before play the stories show each original's pre-match reading only; during
// play also the original's own later reading; at the final also the reported
// result, the reported actual margin and each original's own contract result.
// A supplied later fact in an earlier phase is not shown.
//
// OWNER-RESOLVED, NEVER DERIVED HERE: the phase; the headline, history, readouts,
// runs, gaps, marks, phase key, guides, windows, inspection and controls; each
// story side's exact original, name, tint and separately reported result words
// and count; the related originals and their labels; the margin scale, minimum
// and actual in whole blocks; every word. Each original's readings, labels,
// dates and contract result come from that exact original's own Details content
// (`OriginalMarketDetails9483.content`), so a card and its Details always show
// the same words. This layer never parses a line or a score, never subtracts,
// sums or complements chances, never derives a result, a margin or a
// settlement, never turns a reported result into a probability or a contract
// result, never copies a headline blend into an original, never treats a
// missing value as zero and never adds an endpoint to the history. An original
// that does not resolve — unknown, foreign, duplicated, withdrawn, or repeated
// on the card — shows the owner's words and borrows nothing; the held selection
// is restored only by that exact identity.
//
// INTERACTION. On the page — the headline's open and info, the history's
// actions, inspection choices and plot taps, a directly mounted story's
// expand, side or original choice, Details and source info, the originals'
// choice and the all-originals entry — and in the catalogue and Details
// content, the action calls the owner's interaction hook once and then the
// owner's exact callback with its exact value. A story inside the owner's
// stream calls the stream's activation hook instead, never the page hook as
// well. Full-size content and the Info and source content keep the exact
// callbacks: their host already holds. Building or reading the view calls
// nothing. Without a callback there is no control and no hook call.
//
// READER ORDER. Full-size Previous and Next follow the owner's immutable reader
// order — its ranked or deliberately held sequence, independent of the stream's
// own order and of later arrivals — exactly as given: the neighbour is the
// adjacent entry while both cards are mounted and each is listed once. An empty
// order offers no neighbour; an absent, unmounted or duplicated entry offers
// none either, and nothing skips past it. Without an owner order the mounted
// cards keep the page's order. Nothing is sorted, ranked or remembered here.
//
// LAYOUT. Phone and accessibility sizes stack the headline above the
// comparison and history, then the stories and the originals. A regular or
// unspecified width (a Mac window) places the headline beside the history
// while both keep their minimum widths, otherwise it stacks. Full-size content
// is a lazy section whose header — the owner's match and result words and the
// info control — the host's scroll pins; the reader controls, the comparison
// and the chart scroll beneath it. Winner sides sit side by side while every
// whole name and ring fits an equal share, else one full-width row each;
// accessibility sizes go straight to rows. Every figure is the shared scaled
// figure size; nothing shrinks, truncates or is pinned to the bottom edge.
// Every control drawn here keeps a target of at least the page's minimum
// height at every text size: the body-scaled control metric, floored.
//
// The host owns the scroll, navigation, sheets, Back/Done, focus, routing,
// every held selection and inspection, update arrivals, holds and
// subscriptions. This view keeps no state, runs no timer or animation and
// presents nothing of its own.
//
// Host binding still owed: no esports page input adapter exists at this base.
// The phase, headline, history admission, stories, reports, stream, originals,
// Info and sources are unbound owner channels (named in the handback).

// MARK: - Cards, modes, intents

/// One card the page can show full size, in the page's order. `history` is the anchor.
nonisolated enum EsportsEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// Every side's original pre-match chance beside its reported result.
    case winner
    /// The reported actual margin against the original's minimum.
    case margin
}

/// What the host's container is showing, chosen by the host.
nonisolated enum EsportsEventPageMode10868: Equatable {
    case page
    case reader(EsportsEventPageCard10868)
    /// Every original market with its rules.
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's match Info.
    case about
    /// One owner source document, by its exact id.
    case source(String)
}

/// Full-size content's own controls, handed back exactly.
nonisolated enum EsportsReaderIntent10868: Equatable {
    case previous(EsportsEventPageCard10868)
    case next(EsportsEventPageCard10868)
    case back
}

/// The page's blocks in reading order.
nonisolated enum EsportsEventPageBlock10868: String, CaseIterable {
    case headline
    case notice
    case anchor
    case stories
    case originals
    case catalogue
}

// MARK: - Story input

/// The owner's separately admitted match report for one side. Read at the
/// final only; never a probability or a contract result.
nonisolated struct EsportsSideReport10868: Equatable {
    /// The owner's result words for this side.
    let outcome: String
    /// The owner's whole count figure for this side.
    let figure: String
    /// The count's unit words.
    let unit: String
    /// Fuller spoken words; nil speaks the visible words.
    var spoken: String? = nil
}

/// One side of the winner story: an exact original and the owner's words.
struct EsportsWinnerSide10868: Equatable {
    /// The exact original whose own readings this side shows.
    let selection: OriginalMarketDetails9483.Selection
    /// The owner's whole name for this side.
    let name: String
    /// The owner's stable tint, the same as the history's.
    let tint: Color
    /// Read at the final only.
    var report: EsportsSideReport10868? = nil
}

/// Another original of the story's market, kept apart from the sides — for
/// example a nested line. It is never a side.
struct EsportsRelatedOriginal10868: Equatable {
    let selection: OriginalMarketDetails9483.Selection
    /// The owner's label for the row; the original's own outcome words follow it.
    let label: String
}

/// A story's provenance: an info control that opens one owner source document.
nonisolated struct EsportsStorySource10868: Equatable {
    /// Exactly one of the owner's source documents must carry this id.
    let sourceID: String
    /// The control's spoken name.
    let label: String
}

nonisolated struct EsportsWinnerCopy10868: Equatable {
    let eyebrow: String?
    let title: String
    /// Spoken name of the sides.
    let graphicLabel: String
    /// A side whose original does not resolve.
    let sideUnavailable: String
    /// A held selection of this card that resolves to nothing in this update.
    let selectionMissing: String
    /// Visible words on why the original chances differ from the headline; nil draws none.
    let explanation: String?
    /// Above the reported results, at the final only; nil draws none.
    let reportCaption: String?
    /// A side with no report at the final.
    let resultUnavailable: String
    /// Label of each original's own contract result, at the final only.
    let settlementLabel: String
    /// An original with no contract result of its own.
    let settlementUnconfirmed: String
    /// Above the related originals; nil draws none.
    let relatedHeading: String?
    let selectHint: String?
    /// Opens the held original's Details; nil draws no control.
    let detailsLabel: String?
    let expandLabel: String
}

/// The owner's winner story. Its sides are drawn in the owner's order.
struct EsportsWinnerStory10868: Equatable {
    let sides: [EsportsWinnerSide10868]
    var related: [EsportsRelatedOriginal10868] = []
    var source: EsportsStorySource10868? = nil
    let copy: EsportsWinnerCopy10868
}

/// The owner's margin geometry, in whole blocks: one block is one unit of
/// margin, never a moment of play.
nonisolated struct EsportsMarginScale10868: Equatable {
    /// How many blocks the graphic draws.
    let blocks: Int
    /// The original's minimum, as the owner states it.
    let minimum: Int
    /// The reported actual margin; read at the final only. Nil: not reported.
    var actual: Int? = nil
}

nonisolated struct EsportsMarginCopy10868: Equatable {
    let eyebrow: String?
    let title: String
    /// Spoken name of the graphic.
    let graphicLabel: String
    /// The story's original does not resolve.
    let originalUnavailable: String
    let selectionMissing: String
    /// The threshold marker's words.
    let minimumMarker: String
    let scaleStart: String
    let scaleEnd: String
    /// What one block means.
    let blockMeaning: String
    /// A minimum or actual outside the owner's scale.
    let offScale: String
    let actualLabel: String
    let actualFigure: String?
    let actualUnit: String?
    /// The actual marker's words; nil draws the marker unlabelled.
    let actualMarker: String?
    let actualUnavailable: String
    /// The actual against the minimum, in the owner's words; nil draws none.
    let delta: String?
    /// The reported score in words; nil draws none.
    let score: String?
    let resultLabel: String
    /// The original has no contract result of its own.
    let resultUnconfirmed: String
    let resultDetail: String?
    /// The report's source words; nil draws none.
    let reportSource: String?
    let selectHint: String?
    let detailsLabel: String?
    let expandLabel: String
}

struct EsportsMarginStory10868: Equatable {
    /// The exact original whose minimum the graphic shows.
    let selection: OriginalMarketDetails9483.Selection
    let scale: EsportsMarginScale10868
    var source: EsportsStorySource10868? = nil
    let copy: EsportsMarginCopy10868
}

// MARK: - Page input

/// The owner's link from a stream card to one story card.
nonisolated struct EsportsEventPageStory10868: Equatable {
    let cardID: String
    let card: EsportsEventPageCard10868
    var reason: String? = nil
}

nonisolated struct EsportsEventPageCopy10868: Equatable {
    let storiesLabel: String
    let storyUnavailable: String
    let heldOriginalUnavailable: String
    let backLabel: String
    let previousLabel: String
    let nextLabel: String
    let historyName: String
    let winnerName: String
    let marginName: String
}

struct EsportsEventPageInput10868: Equatable {
    let phase: RugbyMatchEventPagePhase10868
    /// "Constructed frame · not a live capture"; nil draws none.
    var notice: String? = nil
    let headline: FieldHeadlineInput10868
    let reader: RugbyMatchEventPageReaderHeader10868
    let history: FieldHistoryInput10868
    /// The owner's full-size plot height; never shorter than the page's.
    var readerPlotHeight: CGFloat? = nil
    var winner: EsportsWinnerStory10868? = nil
    var margin: EsportsMarginStory10868? = nil
    var stream: StoryStreamPresentation10868? = nil
    var stories: [EsportsEventPageStory10868] = []
    /// The owner's full-size order — for example its ranked or deliberately
    /// held story sequence — used exactly as given: never sorted, ranked,
    /// filtered or repaired here, and independent of the stream's own order.
    /// Nil: the mounted cards in the page's order.
    var readerOrder: [EsportsEventPageCard10868]? = nil
    let about: RugbyMatchEventPageAbout10868?
    let sources: [RugbyMatchEventPageSource10868]
    /// The accepted match page's words.
    let matchCopy: RugbyMatchEventPageCopy10868
    let copy: EsportsEventPageCopy10868
}

nonisolated enum EsportsEventPageAccessibilityID10868 {
    static let page = "esportsEventPage10868.page"
    static let hero = "esportsEventPage10868.hero"
    static let headlineUnavailable = "esportsEventPage10868.headline.unavailable"
    static let notice = "esportsEventPage10868.notice"
    static let anchor = "esportsEventPage10868.anchor"
    static let stories = "esportsEventPage10868.stories"
    static let storyUnavailable = "esportsEventPage10868.story.unavailable"
    static let originals = "esportsEventPage10868.originals"
    static let heldUnavailable = "esportsEventPage10868.originals.heldUnavailable"
    static let catalogueEntry = "esportsEventPage10868.catalogue.entry"
    static let readerHeader = "esportsEventPage10868.readerHeader"
    static let readerInfo = "esportsEventPage10868.readerHeader.info"
    static let readerBack = "esportsEventPage10868.reader.back"
    static let readerPrevious = "esportsEventPage10868.reader.previous"
    static let readerNext = "esportsEventPage10868.reader.next"
    static let readerUnavailable = "esportsEventPage10868.reader.unavailable"
    static let winnerSides = "esportsEventPage10868.winner.sides"
    static let marginGraphic = "esportsEventPage10868.margin.graphic"
    static func card(_ card: EsportsEventPageCard10868) -> String { "esportsEventPage10868.card.\(card.rawValue)" }
    static func expand(_ card: EsportsEventPageCard10868) -> String { "esportsEventPage10868.expand.\(card.rawValue)" }
    static func details(_ card: EsportsEventPageCard10868) -> String { "esportsEventPage10868.details.\(card.rawValue)" }
    static func source(_ card: EsportsEventPageCard10868) -> String { "esportsEventPage10868.source.\(card.rawValue)" }
    static func side(_ index: Int) -> String { "esportsEventPage10868.winner.side.\(index)" }
    static func related(_ index: Int) -> String { "esportsEventPage10868.winner.related.\(index)" }
    static let marginOriginal = "esportsEventPage10868.margin.original"
}

// MARK: - Shared story rules

/// One explicit role line: the role, the owner's label and the original's own
/// figure with its own provenance, or words.
nonisolated enum EsportsStoryRole10868: String, Hashable, CaseIterable {
    /// The original's pre-match reading.
    case before
    /// The original's own later reading, current or recorded as the owner admitted it.
    case later
    /// The separately reported actual.
    case actual
    /// The original contract's own result.
    case result
}

nonisolated struct EsportsRoleLine10868: Equatable {
    let role: EsportsStoryRole10868
    let label: String
    let text: String
    let isValue: Bool
    /// The reading's own date and source, or a result's provenance; nil none.
    let provenance: String?

    var spoken: String {
        [label, text, provenance].compactMap { RugbyMatchEventPageModel10868.readable($0) }.joined(separator: ", ")
    }
}

enum EsportsStoryRules10868 {
    typealias Details = OriginalMarketDetails9483

    /// The exact original's own Details content, or nothing — never a neighbour.
    static func content(_ selection: Details.Selection, in catalogue: Details.Catalogue?) -> Details.Content? {
        Details.content(catalogue: catalogue, selection: selection)
    }

    /// The original's readings the phase admits: the pre-match reading before
    /// play; also its own later reading during play and at the final.
    static func readings(_ content: Details.Content, phase: RugbyMatchEventPagePhase10868) -> [EsportsRoleLine10868] {
        let shown = phase == .before ? Array(content.readings.prefix(1)) : Array(content.readings.prefix(2))
        return shown.enumerated().map { index, reading in
            EsportsRoleLine10868(role: index == 0 ? .before : .later, label: reading.label, text: reading.text,
                                 isValue: reading.isValue, provenance: reading.provenance)
        }
    }

    /// The original contract's own result at the final only: its grade, or the
    /// owner's unconfirmed words. Never the reported match result.
    static func settlement(_ content: Details.Content?, phase: RugbyMatchEventPagePhase10868,
                           label: String, unconfirmed: String, detail: String? = nil) -> EsportsRoleLine10868? {
        guard phase == .final else { return nil }
        if let result = content?.result {
            return EsportsRoleLine10868(role: .result, label: label, text: result.words, isValue: true, provenance: result.provenance)
        }
        return EsportsRoleLine10868(role: .result, label: label, text: unconfirmed, isValue: false,
                                    provenance: RugbyMatchEventPageModel10868.readable(detail))
    }

    /// Selections listed more than once on one card: none of them resolves.
    static func repeated(_ selections: [Details.Selection]) -> [Details.Selection] {
        var counts: [Int] = []
        for selection in selections {
            counts.append(selections.filter { $0 == selection }.count)
        }
        return zip(selections, counts).filter { $0.1 > 1 }.map { $0.0 }
    }

    /// The held selection when it is one of this card's resolving originals.
    static func held(_ held: Details.Selection?, among selections: [Details.Selection],
                     resolves: (Details.Selection) -> Bool) -> Details.Selection? {
        guard let held, selections.contains(held), resolves(held) else { return nil }
        return held
    }

    /// The owner's words when the held selection is one of this card's
    /// originals but resolves to nothing in this update.
    static func missing(_ held: Details.Selection?, among selections: [Details.Selection],
                        resolves: (Details.Selection) -> Bool, words: String) -> String? {
        guard let held, selections.contains(held), !resolves(held) else { return nil }
        return RugbyMatchEventPageModel10868.readable(words)
    }

    /// A ring's arc: the pre-match reading's validated placement only; nothing for words.
    static func ringFraction(_ content: Details.Content?) -> Double? {
        guard let first = content?.readings.first, first.isValue else { return nil }
        return first.placement
    }

    /// Readable words in order, joined for VoiceOver.
    static func spoken(_ parts: [String?]) -> String {
        parts.compactMap { RugbyMatchEventPageModel10868.readable($0) }.joined(separator: ". ")
    }
}

// MARK: - Winner story model

nonisolated struct EsportsWinnerReportLine10868: Equatable {
    let outcome: String
    let figure: String?
    let unit: String?
    let spoken: String
}

struct EsportsWinnerSidePlan10868: Equatable {
    let side: EsportsWinnerSide10868
    /// Nil: the side's original does not resolve; it shows the owner's words.
    let content: OriginalMarketDetails9483.Content?
    /// The pre-match line (and, during play and at the final, the later line).
    let readings: [EsportsRoleLine10868]
    /// The arc, from the pre-match reading's validated placement.
    let ring: Double?
    /// At the final only: the side's report or the owner's unavailable words.
    let report: EsportsWinnerReportLine10868?
    /// At the final only: the original contract's own result.
    let settlement: EsportsRoleLine10868?
    let isSelected: Bool

    var resolves: Bool { content != nil }
}

struct EsportsRelatedPlan10868: Equatable {
    let related: EsportsRelatedOriginal10868
    let content: OriginalMarketDetails9483.Content?
    let readings: [EsportsRoleLine10868]
    let settlement: EsportsRoleLine10868?
    let isSelected: Bool
}

struct EsportsWinnerModel10868: Equatable {
    let story: EsportsWinnerStory10868
    /// The owner's latest originals for the page's scope.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The owner's held selection; never chosen here.
    let held: OriginalMarketDetails9483.Selection?
    let phase: RugbyMatchEventPagePhase10868

    var copy: EsportsWinnerCopy10868 { story.copy }

    var isFinal: Bool { phase == .final }

    /// Every original this card names, sides first.
    var selections: [OriginalMarketDetails9483.Selection] {
        story.sides.map(\.selection) + story.related.map(\.selection)
    }

    /// The exact original's content, unless the card repeats it.
    func content(_ selection: OriginalMarketDetails9483.Selection) -> OriginalMarketDetails9483.Content? {
        guard !EsportsStoryRules10868.repeated(selections).contains(selection) else { return nil }
        return EsportsStoryRules10868.content(selection, in: catalogue)
    }

    var heldSelection: OriginalMarketDetails9483.Selection? {
        EsportsStoryRules10868.held(held, among: selections) { self.content($0) != nil }
    }

    var selectionWords: String? {
        EsportsStoryRules10868.missing(held, among: selections, resolves: { self.content($0) != nil },
                                       words: copy.selectionMissing)
    }

    var sides: [EsportsWinnerSidePlan10868] {
        let holding = heldSelection
        return story.sides.map { side in
            let resolved = self.content(side.selection)
            return EsportsWinnerSidePlan10868(
                side: side, content: resolved,
                readings: resolved.map { EsportsStoryRules10868.readings($0, phase: phase) } ?? [],
                ring: EsportsStoryRules10868.ringFraction(resolved),
                report: resolved == nil ? nil : self.report(side),
                settlement: resolved == nil ? nil : EsportsStoryRules10868.settlement(
                    resolved, phase: phase, label: copy.settlementLabel, unconfirmed: copy.settlementUnconfirmed),
                isSelected: resolved != nil && holding == side.selection)
        }
    }

    var related: [EsportsRelatedPlan10868] {
        let holding = heldSelection
        return story.related.map { row in
            let resolved = self.content(row.selection)
            return EsportsRelatedPlan10868(
                related: row, content: resolved,
                readings: resolved.map { EsportsStoryRules10868.readings($0, phase: phase) } ?? [],
                settlement: resolved == nil ? nil : EsportsStoryRules10868.settlement(
                    resolved, phase: phase, label: copy.settlementLabel, unconfirmed: copy.settlementUnconfirmed),
                isSelected: resolved != nil && holding == row.selection)
        }
    }

    /// The side's separately reported result at the final only; a side
    /// without one keeps the owner's words.
    func report(_ side: EsportsWinnerSide10868) -> EsportsWinnerReportLine10868? {
        guard isFinal else { return nil }
        guard let report = side.report, let outcome = RugbyMatchEventPageModel10868.readable(report.outcome) else {
            return EsportsWinnerReportLine10868(outcome: copy.resultUnavailable, figure: nil, unit: nil,
                                                spoken: copy.resultUnavailable)
        }
        let figure = RugbyMatchEventPageModel10868.readable(report.figure)
        let unit: String? = figure == nil ? nil : RugbyMatchEventPageModel10868.readable(report.unit)
        let visible: [String?] = [outcome, figure, unit]
        let spoken = RugbyMatchEventPageModel10868.readable(report.spoken)
            ?? visible.compactMap { $0 }.joined(separator: " ")
        return EsportsWinnerReportLine10868(outcome: outcome, figure: figure, unit: unit, spoken: spoken)
    }

    var reportCaption: String? { isFinal ? RugbyMatchEventPageModel10868.readable(copy.reportCaption) : nil }

    /// One side in words: name, each line with its own date, the report and
    /// the contract result — or the name and the owner's words.
    func spoken(_ plan: EsportsWinnerSidePlan10868) -> String {
        guard plan.resolves else { return EsportsStoryRules10868.spoken([plan.side.name, copy.sideUnavailable]) }
        var parts: [String?] = [plan.side.name]
        for line in plan.readings { parts.append(line.spoken) }
        parts.append(plan.report?.spoken)
        parts.append(plan.settlement?.spoken)
        return EsportsStoryRules10868.spoken(parts)
    }

    /// One related row in words: the owner's label, the original's outcome
    /// words, its lines — or the owner's words.
    func spoken(_ plan: EsportsRelatedPlan10868) -> String {
        guard let content = plan.content else { return EsportsStoryRules10868.spoken([plan.related.label, copy.sideUnavailable]) }
        var parts: [String?] = [plan.related.label, content.outcome]
        for line in plan.readings { parts.append(line.spoken) }
        parts.append(plan.settlement?.spoken)
        return EsportsStoryRules10868.spoken(parts)
    }

    /// A side's or row's choice: its exact selection, only while it resolves.
    static func choice(_ selection: OriginalMarketDetails9483.Selection, resolves: Bool,
                       onSelect: ((OriginalMarketDetails9483.Selection) -> Void)?) -> (() -> Void)? {
        guard resolves, let onSelect else { return nil }
        return { onSelect(selection) }
    }

    /// Details for the held original of this card, only while it resolves.
    func detailsAction(_ onDetails: ((OriginalMarketDetails9483.Selection) -> Void)?) -> (() -> Void)? {
        guard let holding = heldSelection, RugbyMatchEventPageModel10868.readable(copy.detailsLabel) != nil,
              let onDetails else { return nil }
        return { onDetails(holding) }
    }
}

// MARK: - Margin story model

/// One block of the margin graphic. Its index is a unit of margin, never a
/// moment of play.
nonisolated struct EsportsMarginBlock10868: Equatable {
    let index: Int
    /// Inside the reported actual margin (final only).
    let isFilled: Bool
    /// At or beyond the minimum.
    let meetsMinimum: Bool
}

nonisolated enum EsportsMarginGeometry10868 {
    /// A usable scale: at least one block and the minimum inside it.
    static func isValid(_ scale: EsportsMarginScale10868) -> Bool {
        scale.blocks > 0 && scale.minimum >= 0 && scale.minimum <= scale.blocks
    }

    /// The reported actual at the final only, while it lies on the scale.
    static func actual(_ scale: EsportsMarginScale10868, isFinal: Bool) -> Int? {
        guard isFinal, isValid(scale), let actual = scale.actual, actual >= 0, actual <= scale.blocks else { return nil }
        return actual
    }

    /// A minimum or final actual off the owner's scale: words, no marker, no fill.
    static func isOffScale(_ scale: EsportsMarginScale10868, isFinal: Bool) -> Bool {
        if !isValid(scale) { return true }
        guard isFinal, let actual = scale.actual else { return false }
        return actual < 0 || actual > scale.blocks
    }

    static func blocks(_ scale: EsportsMarginScale10868, isFinal: Bool) -> [EsportsMarginBlock10868] {
        guard isValid(scale) else { return [] }
        let filled = actual(scale, isFinal: isFinal) ?? 0
        return (0..<scale.blocks).map {
            EsportsMarginBlock10868(index: $0, isFilled: $0 < filled, meetsMinimum: $0 >= scale.minimum)
        }
    }

    /// A boundary's fraction of the graphic's width.
    static func fraction(_ value: Int, of scale: EsportsMarginScale10868) -> Double? {
        guard isValid(scale), value >= 0, value <= scale.blocks else { return nil }
        return Double(value) / Double(scale.blocks)
    }

    /// One block's rect inside the graphic, with a fixed gap between blocks.
    static func blockRect(_ index: Int, count: Int, in rect: CGRect, gap: CGFloat) -> CGRect? {
        guard count > 0, index >= 0, index < count, rect.width.isFinite, rect.width > 0 else { return nil }
        let unit = rect.width / CGFloat(count)
        let width = max(0, unit - gap)
        return CGRect(x: rect.minX + CGFloat(index) * unit + gap / 2, y: rect.minY, width: width, height: rect.height)
    }
}

/// The reported actual at the final: the owner's figure and unit, or words.
nonisolated enum EsportsMarginActual10868: Equatable {
    case reported(figure: String, unit: String?)
    case unavailable(String)
}

struct EsportsMarginModel10868: Equatable {
    let story: EsportsMarginStory10868
    let catalogue: OriginalMarketDetails9483.Catalogue?
    let held: OriginalMarketDetails9483.Selection?
    let phase: RugbyMatchEventPagePhase10868

    var copy: EsportsMarginCopy10868 { story.copy }

    var isFinal: Bool { phase == .final }

    var content: OriginalMarketDetails9483.Content? {
        EsportsStoryRules10868.content(story.selection, in: catalogue)
    }

    var resolves: Bool { content != nil }

    var heldSelection: OriginalMarketDetails9483.Selection? {
        EsportsStoryRules10868.held(held, among: [story.selection]) { _ in self.resolves }
    }

    var isSelected: Bool { heldSelection != nil }

    var selectionWords: String? {
        EsportsStoryRules10868.missing(held, among: [story.selection], resolves: { _ in self.resolves },
                                       words: copy.selectionMissing)
    }

    /// The pre-match line, then the original's own later line during and after play.
    var readings: [EsportsRoleLine10868] {
        content.map { EsportsStoryRules10868.readings($0, phase: phase) } ?? []
    }

    /// The reported actual at the final only, while it lies on the scale and
    /// the owner supplies its figure; otherwise the owner's words.
    var actual: EsportsMarginActual10868? {
        guard isFinal else { return nil }
        guard EsportsMarginGeometry10868.actual(story.scale, isFinal: true) != nil,
              let figure = RugbyMatchEventPageModel10868.readable(copy.actualFigure) else {
            return .unavailable(copy.actualUnavailable)
        }
        return .reported(figure: figure, unit: RugbyMatchEventPageModel10868.readable(copy.actualUnit))
    }

    var actualLine: EsportsRoleLine10868? {
        switch actual {
        case .reported(let figure, let unit)?:
            let visible: [String?] = [figure, unit]
            return EsportsRoleLine10868(role: .actual, label: copy.actualLabel,
                                        text: visible.compactMap { $0 }.joined(separator: " "),
                                        isValue: true, provenance: RugbyMatchEventPageModel10868.readable(copy.reportSource))
        case .unavailable(let words)?:
            return EsportsRoleLine10868(role: .actual, label: copy.actualLabel, text: words, isValue: false, provenance: nil)
        case nil:
            return nil
        }
    }

    /// The original contract's own result at the final only.
    var result: EsportsRoleLine10868? {
        guard resolves else { return nil }
        return EsportsStoryRules10868.settlement(content, phase: phase, label: copy.resultLabel,
                                                 unconfirmed: copy.resultUnconfirmed, detail: copy.resultDetail)
    }

    /// Every role in order: before, later, actual, result.
    var roles: [EsportsRoleLine10868] {
        readings + [actualLine, result].compactMap { $0 }
    }

    var blocks: [EsportsMarginBlock10868] { EsportsMarginGeometry10868.blocks(story.scale, isFinal: isFinal) }

    var minimumFraction: Double? { EsportsMarginGeometry10868.fraction(story.scale.minimum, of: story.scale) }

    var actualFraction: Double? {
        EsportsMarginGeometry10868.actual(story.scale, isFinal: isFinal).flatMap {
            EsportsMarginGeometry10868.fraction($0, of: story.scale)
        }
    }

    var isOffScale: Bool { EsportsMarginGeometry10868.isOffScale(story.scale, isFinal: isFinal) }

    /// Delta and score words beside a reported actual only.
    var delta: String? {
        guard case .reported? = actual else { return nil }
        return RugbyMatchEventPageModel10868.readable(copy.delta)
    }

    var score: String? {
        guard case .reported? = actual else { return nil }
        return RugbyMatchEventPageModel10868.readable(copy.score)
    }

    var actualMarker: String? {
        guard actualFraction != nil else { return nil }
        return RugbyMatchEventPageModel10868.readable(copy.actualMarker)
    }

    /// The graphic in words: the owner's name, the markers, what one block
    /// means, then each role.
    var spokenGraphic: String {
        var parts: [String?] = [copy.graphicLabel]
        parts.append(isOffScale ? copy.offScale : copy.minimumMarker)
        parts.append(actualMarker)
        parts.append(copy.blockMeaning)
        for line in roles { parts.append(line.spoken) }
        return EsportsStoryRules10868.spoken(parts)
    }

    func choice(_ onSelect: ((OriginalMarketDetails9483.Selection) -> Void)?) -> (() -> Void)? {
        EsportsWinnerModel10868.choice(story.selection, resolves: resolves, onSelect: onSelect)
    }

    func detailsAction(_ onDetails: ((OriginalMarketDetails9483.Selection) -> Void)?) -> (() -> Void)? {
        guard let holding = heldSelection, RugbyMatchEventPageModel10868.readable(copy.detailsLabel) != nil,
              let onDetails else { return nil }
        return { onDetails(holding) }
    }
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
struct EsportsEventPageModel10868: Equatable {
    let input: EsportsEventPageInput10868

    init(_ input: EsportsEventPageInput10868) {
        self.input = input
    }

    // MARK: The accepted match page

    /// The accepted match page's own input, built from the owner's fields:
    /// no compact context and no chance-to-result story, and the history as
    /// the baseline-collapse copy.
    var match: RugbyMatchEventPageInput10868 {
        RugbyMatchEventPageInput10868(
            phase: input.phase, notice: input.notice, headline: input.headline, reader: input.reader,
            history: Self.baselineCopy(input.history), readerPlotHeight: input.readerPlotHeight,
            context: nil, story: nil, about: input.about, sources: input.sources, copy: input.matchCopy)
    }

    var matchModel: RugbyMatchEventPageModel10868 { RugbyMatchEventPageModel10868(match) }

    var headline: FieldHeadlineInput10868? { matchModel.headline }

    var presentedHistory: FieldHistoryInput10868 { matchModel.presentedHistory }

    var readerHistory: FieldHistoryInput10868 { matchModel.readerHistory }

    // MARK: Baseline collapse

    /// True only while the owner's readout is pre-match beside the inspected
    /// reading and, for every team, the inspected observation is the exact
    /// point the pre-match reading is bound to and that reading shows a figure.
    static func collapsesBaseline(_ history: FieldHistoryInput10868) -> Bool {
        guard case .beforeAndInspected = history.readout, let inspection = history.inspection,
              !history.series.isEmpty else { return false }
        return history.series.allSatisfy { series in
            guard FieldHistoryGeometry10868.isExactlyIdentified(series, in: history),
                  case .observation(let bound, _, _) = series.before,
                  case .figure = FieldHistoryGeometry10868.display(series.before, of: series, in: history),
                  case .point(let inspected, _)? = inspection.selections[series.id],
                  let point = FieldHistoryGeometry10868.inspectedPoint(series, in: history)
            else { return false }
            return inspected == bound && point.id == bound
        }
    }

    /// The owner's history with the duplicate pair collapsed to the single
    /// pre-match slot under the owner's pre-match label; otherwise unchanged.
    static func baselineCopy(_ history: FieldHistoryInput10868) -> FieldHistoryInput10868 {
        guard collapsesBaseline(history), case .beforeAndInspected(let beforeLabel, _) = history.readout else { return history }
        return FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: .singleBefore(label: beforeLabel), markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: history.plotHeight,
            unboundReadingWords: history.unboundReadingWords, plotUnavailableWords: history.plotUnavailableWords,
            windows: history.windows, scale: history.scale, moreOriginals: history.moreOriginals,
            details: history.details, expand: history.expand, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: history.inspection,
            layout: history.layout,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: history.showsKey
        )
    }

    // MARK: Stories

    /// The winner story over the owner's originals and held selection, at the page's phase.
    func winnerModel(_ originals: RugbyMatchEventPageOriginals10868?) -> EsportsWinnerModel10868? {
        input.winner.map {
            EsportsWinnerModel10868(story: $0, catalogue: originals?.catalogue, held: originals?.selection, phase: input.phase)
        }
    }

    func marginModel(_ originals: RugbyMatchEventPageOriginals10868?) -> EsportsMarginModel10868? {
        input.margin.map {
            EsportsMarginModel10868(story: $0, catalogue: originals?.catalogue, held: originals?.selection, phase: input.phase)
        }
    }

    func isMounted(_ card: EsportsEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .winner: input.winner != nil
        case .margin: input.margin != nil
        }
    }

    /// The mounted cards in the page's order.
    var mountedCards: [EsportsEventPageCard10868] {
        EsportsEventPageCard10868.allCases.filter(isMounted)
    }

    /// The full-size sequence: the owner's order exactly as supplied, else the
    /// mounted cards in the page's order.
    var readerSequence: [EsportsEventPageCard10868] {
        input.readerOrder ?? mountedCards
    }

    /// A card's one position in the sequence; none when it is absent or listed
    /// more than once.
    static func uniqueIndex(of card: EsportsEventPageCard10868, in sequence: [EsportsEventPageCard10868]) -> Int? {
        let indices = sequence.indices.filter { sequence[$0] == card }
        return indices.count == 1 ? indices[0] : nil
    }

    /// The card exactly `offset` places from `card` in the full-size sequence,
    /// while both are mounted and each is listed exactly once. Nothing past
    /// either end, and no skipping past an unmounted or ambiguous entry: no
    /// neighbour is invented and nothing jumps.
    func neighbour(of card: EsportsEventPageCard10868, offset: Int) -> EsportsEventPageCard10868? {
        let sequence = readerSequence
        guard isMounted(card), let index = Self.uniqueIndex(of: card, in: sequence) else { return nil }
        let target = index + offset
        guard sequence.indices.contains(target) else { return nil }
        let candidate = sequence[target]
        guard isMounted(candidate), Self.uniqueIndex(of: candidate, in: sequence) != nil else { return nil }
        return candidate
    }

    func cardName(_ card: EsportsEventPageCard10868) -> String {
        switch card {
        case .history: input.copy.historyName
        case .winner: input.copy.winnerName
        case .margin: input.copy.marginName
        }
    }

    /// The owner's link a stream card id names: exactly one link with that id,
    /// to a mounted story card. Otherwise nothing.
    func storyLink(_ cardID: String) -> EsportsEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    var showsCardsDirectly: Bool { input.stream == nil }

    // MARK: Originals

    /// The owner holds a selection that opens nothing in this update; it stays
    /// the owner's and is shown as unavailable, never replaced.
    static func heldOriginalIsUnavailable(_ originals: RugbyMatchEventPageOriginals10868?) -> Bool {
        guard let originals, originals.selection != nil else { return false }
        return OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: originals.selection) == nil
    }

    /// A story's info control: its source id names exactly one owner document.
    func sourceAvailable(_ source: EsportsStorySource10868?) -> Bool {
        guard let source, RugbyMatchEventPageModel10868.readable(source.label) != nil else { return false }
        return matchModel.source(source.sourceID) != nil
    }

    // MARK: Layout and reading order

    static let readingOrder: [EsportsEventPageBlock10868] = [.headline, .notice, .anchor, .stories, .originals, .catalogue]

    /// VoiceOver reads the same order in every arrangement.
    static func sortPriority(_ block: EsportsEventPageBlock10868) -> Double {
        Double(readingOrder.count - (readingOrder.firstIndex(of: block) ?? readingOrder.count))
    }

    /// Winner sides stack at accessibility sizes; otherwise the measured layout decides.
    static func sidesStack(accessibilitySize: Bool) -> Bool { accessibilitySize }

    /// The smallest touch target any control on this page draws.
    static let minimumTarget: CGFloat = 44

    /// A control's height: the body-scaled control metric, never below the
    /// minimum target — smaller text sizes scale the metric down, larger ones up.
    static func targetHeight(_ scaled: CGFloat) -> CGFloat {
        guard scaled.isFinite else { return minimumTarget }
        return max(minimumTarget, scaled)
    }
}

// MARK: - Shared drawing pieces

private struct EsportsCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}

/// A story's heading: eyebrow, title, the info control and the expand control.
private struct EsportsStoryHeader10868: View {
    let eyebrow: String?
    let title: String
    let expandLabel: String
    let card: EsportsEventPageCard10868
    let sourceLabel: String?
    var onSource: (() -> Void)?
    var onExpand: (() -> Void)?

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                if let eyebrow = RugbyMatchEventPageModel10868.readable(eyebrow) {
                    Text(eyebrow)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(title)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let onSource, let sourceLabel {
                Button(action: onSource) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: EsportsEventPageModel10868.targetHeight(controlSize),
                               minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(sourceLabel)
                .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.source(card))
            }
            if let onExpand {
                Button(action: onExpand) {
                    Image(systemName: "arrow.up.left.and.arrow.down.right")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .frame(minWidth: EsportsEventPageModel10868.targetHeight(controlSize),
                               minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(expandLabel)
                .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.expand(card))
            }
        }
    }
}

/// One role line: the owner's label, then the figure with its own date, or words.
private struct EsportsRoleLineView10868: View {
    let line: EsportsRoleLine10868
    let figureSize: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(line.label)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if line.isValue {
                Text(line.text)
                    .font(.system(size: figureSize, weight: .semibold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            } else {
                Text(line.text)
                    .font(.callout.weight(.medium))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let provenance = RugbyMatchEventPageModel10868.readable(line.provenance) {
                Text(provenance)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(line.spoken)
    }
}

/// A full-width text control.
private struct EsportsLink10868: View {
    let label: String
    let id: String
    var action: (() -> Void)?

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        if let action {
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
                .frame(minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(id)
        }
    }
}

// MARK: - Winner story

/// Every side's original pre-match chance as a ring with its own date and,
/// at the final, that side's separately reported result and count and the
/// original contract's own result; then the related originals.
struct EsportsWinnerCard10868: View {
    let model: EsportsWinnerModel10868
    /// The owner's source control, resolved by the page; nil draws none.
    var sourceLabel: String? = nil
    var onExpand: (() -> Void)? = nil
    var onSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onDetails: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onSource: (() -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = RugbyMatchEventPageModel10868.comparisonFigureSize
    @ScaledMetric(relativeTo: .title2) private var ringSize: CGFloat = 104
    @ScaledMetric(relativeTo: .title2) private var ringLine: CGFloat = 5

    static let columnSpacing: CGFloat = 12
    static let rowSpacing: CGFloat = 12

    var body: some View {
        let copy = model.copy
        VStack(alignment: .leading, spacing: 14) {
            EsportsStoryHeader10868(eyebrow: copy.eyebrow, title: copy.title, expandLabel: copy.expandLabel, card: .winner,
                                    sourceLabel: sourceLabel, onSource: onSource, onExpand: onExpand)
            if let explanation = RugbyMatchEventPageModel10868.readable(copy.explanation) {
                Text(explanation)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let caption = model.reportCaption {
                Text(caption)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            sides
            related
            if let words = model.selectionWords {
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let label = RugbyMatchEventPageModel10868.readable(copy.detailsLabel) {
                EsportsLink10868(label: label, id: EsportsEventPageAccessibilityID10868.details(.winner),
                                 action: model.detailsAction(onDetails))
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .contain)
    }

    /// Peer columns while every whole name and ring fits an equal share, else
    /// one row per side; accessibility sizes go straight to rows.
    private var sides: some View {
        let plans = model.sides
        return FieldHeadlineCompetitorsLayout10868(count: plans.count, spacing: Self.columnSpacing, rowSpacing: Self.rowSpacing,
                                                   accessibilitySize: EsportsEventPageModel10868.sidesStack(accessibilitySize: typeSize.isAccessibilitySize)) {
            ForEach(Array(plans.enumerated()), id: \.offset) { index, plan in
                sideView(plan, index: index)
            }
            ForEach(Array(plans.enumerated()), id: \.offset) { _, plan in
                nameRow(plan.side, whole: true).padding(12).hidden().accessibilityHidden(true)
            }
            ForEach(Array(plans.enumerated()), id: \.offset) { _, _ in
                Color.clear.frame(width: ringSize + 32, height: 1).hidden().accessibilityHidden(true)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(model.copy.graphicLabel)
        .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.winnerSides)
    }

    @ViewBuilder private func sideView(_ plan: EsportsWinnerSidePlan10868, index: Int) -> some View {
        let content = sideContent(plan)
            .padding(12)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(RoundedRectangle(cornerRadius: 14).fill(plan.isSelected ? DS.surface : Color.clear))
            .overlay(RoundedRectangle(cornerRadius: 14)
                .stroke(plan.isSelected ? DS.textPrimary : DS.border, lineWidth: plan.isSelected ? 2 : 1))
        if let action = EsportsWinnerModel10868.choice(plan.side.selection, resolves: plan.resolves, onSelect: onSelect) {
            Button(action: action) { content }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(model.spoken(plan))
                .accessibilityHint(model.copy.selectHint ?? "")
                .accessibilityAddTraits(plan.isSelected ? [.isButton, .isSelected] : .isButton)
                .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.side(index))
        } else {
            content
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(model.spoken(plan))
                .accessibilityAddTraits(plan.isSelected ? .isSelected : [])
                .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.side(index))
        }
    }

    private func sideContent(_ plan: EsportsWinnerSidePlan10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            nameRow(plan.side, whole: false)
            if plan.resolves {
                ring(plan)
                ForEach(Array(plan.readings.enumerated()), id: \.offset) { index, line in
                    if index == 0 && line.isValue {
                        ringCaption(line)
                    } else {
                        EsportsRoleLineView10868(line: line, figureSize: figureSize)
                    }
                }
                if plan.report != nil || plan.settlement != nil {
                    Divider()
                }
                if let report = plan.report {
                    reportView(report)
                }
                if let settlement = plan.settlement {
                    EsportsRoleLineView10868(line: settlement, figureSize: figureSize)
                }
            } else {
                Text(model.copy.sideUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// The side's own tint swatch and whole name; `whole` measures it on one line.
    private func nameRow(_ side: EsportsWinnerSide10868, whole: Bool) -> some View {
        HStack(alignment: .center, spacing: 6) {
            Circle().fill(side.tint).frame(width: 10, height: 10).accessibilityHidden(true)
            Text(side.name)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: whole, vertical: true)
        }
    }

    /// The pre-match reading as an arc from the top; a missing or unplaceable
    /// reading draws the track only. The figure is the reading's own text.
    private func ring(_ plan: EsportsWinnerSidePlan10868) -> some View {
        ZStack {
            Circle().stroke(DS.border, lineWidth: ringLine)
            if let fraction = plan.ring {
                Circle()
                    .trim(from: 0, to: CGFloat(fraction))
                    .stroke(plan.side.tint, style: StrokeStyle(lineWidth: ringLine, lineCap: .round))
                    .rotationEffect(.degrees(-90))
            }
            if let first = plan.readings.first, first.isValue {
                Text(first.text)
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            }
        }
        .frame(width: ringSize, height: ringSize)
        .padding(4)
        .frame(maxWidth: .infinity)
        .accessibilityHidden(true)
    }

    /// The ring's own role label and date under it; its figure is in the ring.
    private func ringCaption(_ line: EsportsRoleLine10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(line.label)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let provenance = RugbyMatchEventPageModel10868.readable(line.provenance) {
                Text(provenance)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func reportView(_ report: EsportsWinnerReportLine10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(report.outcome)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if let figure = report.figure {
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text(figure)
                        .font(.system(size: figureSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                    if let unit = report.unit {
                        Text(unit)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(report.spoken)
    }

    /// The related originals: the owner's label and the original's own outcome
    /// words, with its own readings or words.
    @ViewBuilder private var related: some View {
        let rows = model.related
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                if let heading = RugbyMatchEventPageModel10868.readable(model.copy.relatedHeading) {
                    Text(heading)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                    relatedRow(row, index: index)
                }
            }
        }
    }

    @ViewBuilder private func relatedRow(_ row: EsportsRelatedPlan10868, index: Int) -> some View {
        let card = VStack(alignment: .leading, spacing: 6) {
            Text(row.related.label)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if let content = row.content {
                Text(content.outcome)
                    .font(.body)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                ForEach(Array(row.readings.enumerated()), id: \.offset) { _, line in
                    EsportsRoleLineView10868(line: line, figureSize: figureSize)
                }
                if let settlement = row.settlement {
                    EsportsRoleLineView10868(line: settlement, figureSize: figureSize)
                }
            } else {
                Text(model.copy.sideUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(RoundedRectangle(cornerRadius: 12)
            .stroke(row.isSelected ? DS.textPrimary : DS.border, lineWidth: row.isSelected ? 2 : 1))
        let spoken = model.spoken(row)
        if let action = EsportsWinnerModel10868.choice(row.related.selection, resolves: row.content != nil, onSelect: onSelect) {
            Button(action: action) { card }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(spoken)
                .accessibilityHint(model.copy.selectHint ?? "")
                .accessibilityAddTraits(row.isSelected ? [.isButton, .isSelected] : .isButton)
                .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.related(index))
        } else {
            card
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(spoken)
                .accessibilityAddTraits(row.isSelected ? .isSelected : [])
                .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.related(index))
        }
    }
}

// MARK: - Margin story

/// The reported actual margin against the original's minimum: one block per
/// unit of margin, filled up to the actual at the final, a dashed threshold
/// marker at the minimum and a solid marker at the actual. Never a timeline.
struct EsportsMarginCard10868: View {
    let model: EsportsMarginModel10868
    var sourceLabel: String? = nil
    var onExpand: (() -> Void)? = nil
    var onSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onDetails: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onSource: (() -> Void)? = nil

    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = RugbyMatchEventPageModel10868.comparisonFigureSize
    @ScaledMetric(relativeTo: .body) private var blockHeight: CGFloat = 26
    @ScaledMetric(relativeTo: .body) private var markerOverhang: CGFloat = 8
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    static let blockGap: CGFloat = 3

    var body: some View {
        let copy = model.copy
        VStack(alignment: .leading, spacing: 14) {
            EsportsStoryHeader10868(eyebrow: copy.eyebrow, title: copy.title, expandLabel: copy.expandLabel, card: .margin,
                                    sourceLabel: sourceLabel, onSource: onSource, onExpand: onExpand)
            if model.resolves {
                original
                ForEach(Array(model.readings.enumerated()), id: \.offset) { _, line in
                    EsportsRoleLineView10868(line: line, figureSize: figureSize)
                }
                actualHero
                graphic
                if let result = model.result {
                    Divider()
                    EsportsRoleLineView10868(line: result, figureSize: figureSize)
                }
            } else {
                Text(copy.originalUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let words = model.selectionWords {
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let label = RugbyMatchEventPageModel10868.readable(copy.detailsLabel) {
                EsportsLink10868(label: label, id: EsportsEventPageAccessibilityID10868.details(.margin),
                                 action: model.detailsAction(onDetails))
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .contain)
    }

    /// The original's own outcome words, choosing its exact selection. After
    /// its padding the target is never shorter than the page's minimum.
    @ViewBuilder private var original: some View {
        if let content = model.content {
            let label = Text(content.outcome)
                .font(.body.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .frame(minHeight: EsportsEventPageModel10868.targetHeight(controlSize), alignment: .leading)
                .contentShape(Rectangle())
                .overlay(RoundedRectangle(cornerRadius: 12)
                    .stroke(model.isSelected ? DS.textPrimary : DS.border, lineWidth: model.isSelected ? 2 : 1))
            if let action = model.choice(onSelect) {
                Button(action: action) { label }
                    .buttonStyle(.plain)
                    .accessibilityHint(model.copy.selectHint ?? "")
                    .accessibilityAddTraits(model.isSelected ? [.isButton, .isSelected] : .isButton)
                    .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.marginOriginal)
            } else {
                label
                    .accessibilityAddTraits(model.isSelected ? .isSelected : [])
                    .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.marginOriginal)
            }
        }
    }

    /// The reported actual at the final: the owner's figure and unit, the
    /// delta and the score, or the owner's words.
    @ViewBuilder private var actualHero: some View {
        switch model.actual {
        case .reported(let figure, let unit)?:
            VStack(alignment: .leading, spacing: 4) {
                Text(model.copy.actualLabel)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text(figure)
                        .font(.system(size: figureSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.blue)
                        .fixedSize()
                    if let unit {
                        Text(unit)
                            .font(.headline)
                            .foregroundStyle(DS.blue)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                if let delta = model.delta {
                    Text(delta)
                        .font(.headline)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let score = model.score {
                    Text(score)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let source = RugbyMatchEventPageModel10868.readable(model.copy.reportSource) {
                    Text(source)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .combine)
        case .unavailable(let words)?:
            VStack(alignment: .leading, spacing: 2) {
                Text(model.copy.actualLabel)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                Text(words)
                    .font(.callout.weight(.medium))
                    .foregroundStyle(DS.textSecondary)
            }
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .combine)
        case nil:
            EmptyView()
        }
    }

    /// The blocks, the two markers and their keyed words, the scale ends and
    /// what one block means — or the owner's off-scale words.
    @ViewBuilder private var graphic: some View {
        VStack(alignment: .leading, spacing: 8) {
            if model.isOffScale {
                Text(model.copy.offScale)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                blocksCanvas
                HStack {
                    Text(model.copy.scaleStart)
                    Spacer(minLength: 8)
                    Text(model.copy.scaleEnd)
                }
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .accessibilityHidden(true)
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 16) { markerKey }
                    VStack(alignment: .leading, spacing: 6) { markerKey }
                }
            }
            Text(model.copy.blockMeaning)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.spokenGraphic)
        .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.marginGraphic)
    }

    private var blocksCanvas: some View {
        let blocks = model.blocks
        let minimum = model.minimumFraction
        let actual = model.actualFraction
        let overhang = markerOverhang
        let gap = Self.blockGap
        return Canvas { context, size in
            let row = CGRect(x: 0, y: overhang, width: size.width, height: max(0, size.height - 2 * overhang))
            for block in blocks {
                guard let rect = EsportsMarginGeometry10868.blockRect(block.index, count: blocks.count, in: row, gap: gap) else { continue }
                let shape = Path(roundedRect: rect, cornerRadius: 3)
                context.fill(shape, with: .color(block.isFilled ? DS.blue : DS.border))
            }
            if let minimum {
                let x = row.minX + CGFloat(minimum) * row.width
                var line = Path()
                line.move(to: CGPoint(x: x, y: 0))
                line.addLine(to: CGPoint(x: x, y: size.height))
                context.stroke(line, with: .color(DS.textPrimary), style: StrokeStyle(lineWidth: 1.5, dash: [3, 3]))
            }
            if let actual {
                let x = row.minX + CGFloat(actual) * row.width
                var line = Path()
                line.move(to: CGPoint(x: x, y: 0))
                line.addLine(to: CGPoint(x: x, y: size.height))
                context.stroke(line, with: .color(DS.textPrimary), lineWidth: 2)
            }
        }
        .frame(maxWidth: .infinity)
        .frame(height: blockHeight + 2 * markerOverhang)
        .accessibilityHidden(true)
    }

    @ViewBuilder private var markerKey: some View {
        markerEntry(dashed: true, words: model.copy.minimumMarker)
        if let words = model.actualMarker {
            markerEntry(dashed: false, words: words)
        }
    }

    private func markerEntry(dashed: Bool, words: String) -> some View {
        HStack(alignment: .center, spacing: 6) {
            Canvas { context, size in
                var line = Path()
                line.move(to: CGPoint(x: size.width / 2, y: 0))
                line.addLine(to: CGPoint(x: size.width / 2, y: size.height))
                if dashed {
                    context.stroke(line, with: .color(DS.textPrimary), style: StrokeStyle(lineWidth: 1.5, dash: [3, 3]))
                } else {
                    context.stroke(line, with: .color(DS.textPrimary), lineWidth: 2)
                }
            }
            .frame(width: 8, height: 18)
            .accessibilityHidden(true)
            Text(words)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - Page view

struct EsportsEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868
    typealias Selection = OriginalMarketDetails9483.Selection

    let input: EsportsEventPageInput10868
    var mode: EsportsEventPageMode10868 = .page
    /// The page's originals and the catalogue and Details modes; nil: none.
    var originals: RugbyMatchEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's Info.
    var onAbout: (() -> Void)? = nil
    /// A source document's exact id, for the host to open.
    var onSource: ((String) -> Void)? = nil
    /// A section's exact external link, for the host to open.
    var onLink: ((RugbyMatchEventPageLink10868) -> Void)? = nil
    /// Opens all original markets.
    var onCatalogue: (() -> Void)? = nil
    /// An original's exact selection, for the host to hold.
    var onOriginalSelect: ((Selection) -> Void)? = nil
    /// A story's held original, for the host to show its Details.
    var onOriginalDetails: ((Selection) -> Void)? = nil
    /// A Details history control's exact intent.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// A headline team's exact open.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Opens the host's reader on a story mounted directly on the page.
    var onCardOpen: ((EsportsEventPageCard10868) -> Void)? = nil
    /// Full-size content's own controls, exactly.
    var onReaderIntent: ((EsportsReaderIntent10868) -> Void)? = nil
    /// Called once just before a page, catalogue or Details action reaches its
    /// owner callback. Never by building the view, by full-size content, by
    /// the Info or source content, or by a stream card.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var headlineMinWidth: CGFloat = 300
    @ScaledMetric(relativeTo: .body) private var headlineMaxWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: EsportsEventPageModel10868 { EsportsEventPageModel10868(input) }

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

    static func bind(_ action: ((EsportsEventPageCard10868) -> Void)?, _ card: EsportsEventPageCard10868) -> (() -> Void)? {
        guard let action else { return nil }
        return { action(card) }
    }

    static func bind(_ action: ((EsportsReaderIntent10868) -> Void)?, _ intent: EsportsReaderIntent10868) -> (() -> Void)? {
        guard let action else { return nil }
        return { action(intent) }
    }

    static func bind(_ action: ((String) -> Void)?, _ id: String?) -> (() -> Void)? {
        guard let action, let id else { return nil }
        return { action(id) }
    }

    // MARK: The accepted match page

    /// The accepted match page in its own mode, with every owner callback: its
    /// builders and its content modes are reused unchanged.
    func match(_ mode: RugbyMatchEventPageMode10868) -> RugbyMatchEventPagePresentation10868 {
        RugbyMatchEventPagePresentation10868(
            input: model.match, mode: mode, originals: originals,
            onAbout: onAbout, onSource: onSource, onLink: onLink, onCatalogue: onCatalogue,
            onOriginalSelect: onOriginalSelect, onOriginalHistory: onOriginalHistory,
            onOriginalOpen: onHeadlineOpen, onInspect: nil,
            onHistoryAction: onHistoryAction, onHistoryInspectionChoice: onHistoryInspectionChoice,
            onHistoryPlotPosition: onHistoryPlotPosition, onReaderOpen: nil, onStoryDetails: nil,
            onInteraction: onInteraction)
    }

    /// The accepted page mode an esports mode reads its leaves in.
    static func matchMode(_ mode: EsportsEventPageMode10868) -> RugbyMatchEventPageMode10868 {
        switch mode {
        case .page: .page
        case .reader: .reader(.history)
        case .catalogue: .catalogue
        case .original: .original
        case .about: .about
        case .source(let id): .source(id)
        }
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .catalogue, .original, .about, .source: match(Self.matchMode(mode))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves

    /// The headline at the page's phase, from the accepted page's builder.
    func headlineContent() -> FieldPhaseHeadlinePresentation10868? {
        match(.page).headlineContent()
    }

    /// The comparison over the exact history copy beside it, inline or full size.
    func comparisonContent(reader: Bool) -> RugbyMatchEventPageComparisonPresentation10868 {
        match(reader ? .reader(.history) : .page).comparisonContent(reader: reader)
    }

    /// The history: the page hook first; full size keeps the exact callbacks.
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        match(reader ? .reader(.history) : .page).historyContent(reader: reader)
    }

    /// Every original by its exact identity on the page, its choice after the hook.
    func chooserContent() -> OriginalMarketChooserView9483? {
        match(.page).choicesContent()
    }

    /// The all-originals entry, after the page hook.
    var catalogueAction: (() -> Void)? { match(.page).catalogueAction }

    /// A story's info control, held on the page; nil when its id names no single document.
    func sourceAction(_ source: EsportsStorySource10868?, hold: (() -> Void)?) -> (() -> Void)? {
        guard model.sourceAvailable(source) else { return nil }
        return RugbyMatchEventPagePresentation10868.heldAction(Self.bind(onSource, source?.sourceID), by: hold)
    }

    func sourceLabel(_ source: EsportsStorySource10868?) -> String? {
        model.sourceAvailable(source) ? source?.label : nil
    }

    /// The winner story mounted directly on the page: every action after the hook.
    func pageWinnerContent() -> EsportsWinnerCard10868? {
        guard model.showsCardsDirectly, let story = model.winnerModel(originals) else { return nil }
        return EsportsWinnerCard10868(
            model: story, sourceLabel: sourceLabel(story.story.source),
            onExpand: RugbyMatchEventPagePresentation10868.heldAction(Self.bind(onCardOpen, .winner), by: onInteraction),
            onSelect: RugbyMatchEventPagePresentation10868.held(onOriginalSelect, by: onInteraction),
            onDetails: RugbyMatchEventPagePresentation10868.held(onOriginalDetails, by: onInteraction),
            onSource: sourceAction(story.story.source, hold: onInteraction))
    }

    func pageMarginContent() -> EsportsMarginCard10868? {
        guard model.showsCardsDirectly, let story = model.marginModel(originals) else { return nil }
        return EsportsMarginCard10868(
            model: story, sourceLabel: sourceLabel(story.story.source),
            onExpand: RugbyMatchEventPagePresentation10868.heldAction(Self.bind(onCardOpen, .margin), by: onInteraction),
            onSelect: RugbyMatchEventPagePresentation10868.held(onOriginalSelect, by: onInteraction),
            onDetails: RugbyMatchEventPagePresentation10868.held(onOriginalDetails, by: onInteraction),
            onSource: sourceAction(story.story.source, hold: onInteraction))
    }

    /// A story in a stream cell: every action after the stream's activation
    /// hook, never the page hook as well. The stream offers its own open.
    func streamWinnerContent(activation: StoryStreamCardActivation10868) -> EsportsWinnerCard10868? {
        guard let story = model.winnerModel(originals) else { return nil }
        let source = model.sourceAvailable(story.story.source) ? Self.bind(onSource, story.story.source?.sourceID) : nil
        return EsportsWinnerCard10868(
            model: story, sourceLabel: sourceLabel(story.story.source), onExpand: nil,
            onSelect: Self.relay(onOriginalSelect, through: activation),
            onDetails: Self.relay(onOriginalDetails, through: activation),
            onSource: Self.relayAction(source, through: activation))
    }

    func streamMarginContent(activation: StoryStreamCardActivation10868) -> EsportsMarginCard10868? {
        guard let story = model.marginModel(originals) else { return nil }
        let source = model.sourceAvailable(story.story.source) ? Self.bind(onSource, story.story.source?.sourceID) : nil
        return EsportsMarginCard10868(
            model: story, sourceLabel: sourceLabel(story.story.source), onExpand: nil,
            onSelect: Self.relay(onOriginalSelect, through: activation),
            onDetails: Self.relay(onOriginalDetails, through: activation),
            onSource: Self.relayAction(source, through: activation))
    }

    /// Full-size stories: the same Views and inputs with the exact callbacks.
    func readerWinnerContent() -> EsportsWinnerCard10868? {
        model.winnerModel(originals).map {
            EsportsWinnerCard10868(model: $0, sourceLabel: sourceLabel($0.story.source), onExpand: nil,
                                   onSelect: onOriginalSelect, onDetails: onOriginalDetails,
                                   onSource: sourceAction($0.story.source, hold: nil))
        }
    }

    func readerMarginContent() -> EsportsMarginCard10868? {
        model.marginModel(originals).map {
            EsportsMarginCard10868(model: $0, sourceLabel: sourceLabel($0.story.source), onExpand: nil,
                                   onSelect: onOriginalSelect, onDetails: onOriginalDetails,
                                   onSource: sourceAction($0.story.source, hold: nil))
        }
    }

    /// Full-size content's own controls: the mounted neighbours and Back, exactly.
    func readerControls(_ card: EsportsEventPageCard10868) -> (previous: EsportsEventPageCard10868?,
                                                               next: EsportsEventPageCard10868?,
                                                               canGoBack: Bool) {
        guard onReaderIntent != nil, model.isMounted(card) else { return (nil, nil, false) }
        return (model.neighbour(of: card, offset: -1), model.neighbour(of: card, offset: 1), true)
    }

    /// Full-size content's info control: the exact callback, no hook.
    var readerAboutAction: (() -> Void)? {
        guard model.matchModel.aboutEntry(mode: .reader(.history), canOpen: onAbout != nil),
              model.headline?.copy.aboutLabel != nil else { return nil }
        let full = match(.reader(.history))
        return { full.openReaderAbout() }
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            hero
            stories
            originalsPanel
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.page)
    }

    /// The headline and the comparison over the history in one panel: side by
    /// side where both fit at their minimum widths, otherwise stacked.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            let arrangements = RugbyMatchEventPageModel10868.arrangements(
                sizeClass: sizeClass, accessibilitySize: typeSize.isAccessibilitySize)
            if arrangements == [.stacked] {
                heroStacked
            } else {
                ViewThatFits(in: .horizontal) {
                    heroSideBySide
                    heroStacked
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(EsportsCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.hero)
    }

    private var heroStacked: some View {
        VStack(alignment: .leading, spacing: 24) {
            headlineSection
            anchor
        }
    }

    private var heroSideBySide: some View {
        HStack(alignment: .top, spacing: 32) {
            headlineSection
                .frame(minWidth: headlineMinWidth, maxWidth: headlineMaxWidth, alignment: .topLeading)
            anchor
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
        }
    }

    private var headlineSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Group {
                if let headline = headlineContent() {
                    headline
                } else {
                    Text(input.matchCopy.headlineUnavailable)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.headlineUnavailable)
                }
            }
            .accessibilitySortPriority(EsportsEventPageModel10868.sortPriority(.headline))
            if let notice = RugbyMatchEventPageModel10868.readable(input.notice) {
                Text(notice)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilitySortPriority(EsportsEventPageModel10868.sortPriority(.notice))
                    .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.notice)
            }
        }
        .accessibilityElement(children: .contain)
    }

    private var anchor: some View {
        VStack(alignment: .leading, spacing: 16) {
            comparisonContent(reader: false)
            historyContent(reader: false)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilitySortPriority(EsportsEventPageModel10868.sortPriority(.anchor))
        .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.anchor)
    }

    /// The owner's stream when it supplies one; otherwise the mounted stories
    /// directly on the page, winner first.
    @ViewBuilder private var stories: some View {
        if let stream = input.stream {
            StoryStreamPresentationView10868(stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(input.copy.storiesLabel)
            .accessibilitySortPriority(EsportsEventPageModel10868.sortPriority(.stories))
            .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.stories)
        } else {
            if let winner = pageWinnerContent() {
                cardSurface(winner, card: .winner)
            }
            if let margin = pageMarginContent() {
                cardSurface(margin, card: .margin)
            }
        }
    }

    private func cardSurface<Content: View>(_ content: Content, card: EsportsEventPageCard10868) -> some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(EsportsCardSurface10868())
            .accessibilitySortPriority(EsportsEventPageModel10868.sortPriority(.stories))
            .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.card(card))
    }

    /// The story the owner links to this stream card, or the owner's
    /// unavailable words. Never a neighbour.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.storyLink(card.id), let content = streamCardContent(link.card, activation) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = RugbyMatchEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                content
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(EsportsCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(EsportsCardSurface10868())
                .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.storyUnavailable)
        }
    }

    private func streamCardContent(_ card: EsportsEventPageCard10868,
                                   _ activation: StoryStreamCardActivation10868) -> AnyView? {
        switch card {
        case .history: nil
        case .winner: streamWinnerContent(activation: activation).map { AnyView($0) }
        case .margin: streamMarginContent(activation: activation).map { AnyView($0) }
        }
    }

    /// The originals with the owner's held-unavailable words, then the
    /// all-originals entry.
    @ViewBuilder private var originalsPanel: some View {
        let entry = catalogueAction
        let chooser = chooserContent()
        if chooser != nil || entry != nil {
            VStack(alignment: .leading, spacing: 12) {
                if let chooser {
                    VStack(alignment: .leading, spacing: 8) {
                        if let context = RugbyMatchEventPageModel10868.readable(originals?.context) {
                            Text(context)
                                .font(.caption)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        chooser
                        if EsportsEventPageModel10868.heldOriginalIsUnavailable(originals) {
                            Text(input.copy.heldOriginalUnavailable)
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.heldUnavailable)
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(EsportsCardSurface10868())
                    .accessibilityElement(children: .contain)
                    .accessibilitySortPriority(EsportsEventPageModel10868.sortPriority(.originals))
                    .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.originals)
                }
                if let entry, let label = input.matchCopy.catalogueLabel {
                    catalogueEntry(label, action: entry)
                        .accessibilitySortPriority(EsportsEventPageModel10868.sortPriority(.catalogue))
                }
            }
        }
    }

    private func catalogueEntry(_ label: String, action: @escaping () -> Void) -> some View {
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
            .padding(.horizontal, 16)
            .frame(minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
            .modifier(EsportsCardSurface10868())
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.catalogueEntry)
    }

    // MARK: Full size

    /// The same Views and inputs, full size: a lazy section whose header — the
    /// owner's match and result words and the info control — the host's scroll
    /// pins, with the reader controls, the comparison and the content beneath.
    /// A card that is not mounted keeps the owner's words, never another card.
    @ViewBuilder private func reader(_ card: EsportsEventPageCard10868) -> some View {
        LazyVStack(alignment: .leading, spacing: 16, pinnedViews: [.sectionHeaders]) {
            Section {
                if model.isMounted(card) {
                    readerNavigation(card)
                    switch card {
                    case .history:
                        comparisonContent(reader: true)
                        historyContent(reader: true)
                    case .winner:
                        readerWinnerContent()
                    case .margin:
                        readerMarginContent()
                    }
                } else {
                    Text(input.matchCopy.readerUnavailable)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.readerUnavailable)
                }
            } header: {
                compactHeader
                    .padding(.vertical, 8)
                    .background(DS.surface)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.card(card))
    }

    /// Back, then the previous and next mounted cards by name.
    @ViewBuilder private func readerNavigation(_ card: EsportsEventPageCard10868) -> some View {
        let controls = readerControls(card)
        if controls.canGoBack {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) { readerButtons(controls) }
                VStack(alignment: .leading, spacing: 4) { readerButtons(controls) }
            }
        }
    }

    @ViewBuilder private func readerButtons(_ controls: (previous: EsportsEventPageCard10868?,
                                                         next: EsportsEventPageCard10868?,
                                                         canGoBack: Bool)) -> some View {
        readerButton(input.copy.backLabel, detail: nil, systemImage: "chevron.backward",
                     action: Self.bind(onReaderIntent, .back), id: EsportsEventPageAccessibilityID10868.readerBack)
        if let previous = controls.previous {
            readerButton(input.copy.previousLabel, detail: model.cardName(previous), systemImage: "arrow.left",
                         action: Self.bind(onReaderIntent, .previous(previous)),
                         id: EsportsEventPageAccessibilityID10868.readerPrevious)
        }
        if let next = controls.next {
            readerButton(input.copy.nextLabel, detail: model.cardName(next), systemImage: "arrow.right",
                         action: Self.bind(onReaderIntent, .next(next)),
                         id: EsportsEventPageAccessibilityID10868.readerNext)
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
                        if let detail = RugbyMatchEventPageModel10868.readable(detail) {
                            Text(detail)
                                .font(.caption)
                                .foregroundStyle(DS.textSecondary)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
                .foregroundStyle(DS.blue)
                .frame(minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(id)
        }
    }

    /// The owner's one-line match and result words and the info control.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = RugbyMatchEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if let action = readerAboutAction, let label = model.headline?.copy.aboutLabel {
                Button(action: action) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: EsportsEventPageModel10868.targetHeight(controlSize),
                               minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(label)
                .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.readerInfo)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(EsportsEventPageAccessibilityID10868.readerHeader)
    }
}
