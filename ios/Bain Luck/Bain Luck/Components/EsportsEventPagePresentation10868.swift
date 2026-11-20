import SwiftUI

// #10868 / #11666 — Esports Match Story Cards (`EsportsWinnerCard10868` and
// `EsportsMarginCard10868`), plus the shared `OriginalMarketDetails9483`
// identity/catalogue contract.
//
// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: on native Esports match pages
// (`esports_csgo`, `esports_lol`, `esports_dota2`, `esports_valorant`), original
// match-winner expectations and round/map margin lines compare visually with
// separately reported actual results, while preserving each contract's own
// pregame and live timestamps and settlement grade.

// MARK: - Original Market Identity & Catalogue (#9483 / #10868)

nonisolated enum OriginalMarketDetails9483 {
    nonisolated enum Marker: Equatable { case hollow, solid }

    nonisolated struct Row: Equatable {
        let label: String
        let value: String
    }

    /// The original's exact identity as the host holds it — never built here
    /// from a ticker, a label or an array position.
    nonisolated struct Identity: Hashable {
        let source: String
        let market: String
        let side: String
    }

    /// The host's held selection: an exact identity inside the exact scope it
    /// was chosen in.
    nonisolated struct Selection: Equatable {
        let scope: String
        let identity: Identity
    }

    /// The host's latest admitted originals for one scope.
    nonisolated struct Catalogue: Equatable {
        let scope: String
        let originals: [Original]
    }

    /// What the later reading is, as the owner admitted it.
    nonisolated enum Later: Equatable {
        case current, recorded

        var label: String {
            switch self {
            case .current: return "Current chance"
            case .recorded: return "Recorded chance"
            }
        }
    }

    /// The original market's display state, chosen by the owner.
    nonisolated enum Mode: Equatable {
        /// One admitted pregame reading.
        case pregame
        /// The pregame reading beside a separately admitted later reading.
        case comparison(Later)
        /// The pregame reading beside the original contract's own result.
        case result
    }

    nonisolated struct Reading: Equatable {
        nonisolated enum Figure: Equatable {
            /// The owner's formatted figure, printed verbatim ("0%" included).
            case value(String)
            /// The owner's reason this slot has no figure.
            case missing(String)
        }

        let figure: Figure
        /// Where the owner places the reading on the 0–100% rail (0...1).
        let placement: Double?
        /// The reading's own provenance in full — calendar, granularity,
        /// source — as the owner wrote it.
        let provenance: String?

        static func value(_ text: String, placement: Double?, provenance: String?) -> Reading {
            Reading(figure: .value(text), placement: placement, provenance: provenance)
        }

        static func missing(_ reason: String) -> Reading {
            Reading(figure: .missing(reason), placement: nil, provenance: nil)
        }
    }

    /// The original contract's own grade, independently admitted by its owner
    /// ("Resolved No", "Void", "Not yet confirmed") — never the match result.
    nonisolated struct Grade: Equatable {
        let words: String
        /// The grade's own settlement provenance; nil stays unknown.
        let provenance: String?
    }

    /// The last recorded value, explicitly historical and separately dated.
    nonisolated struct HistoricalQuote: Equatable {
        let text: String
        let recorded: String?
    }

    nonisolated enum Rules: Equatable {
        /// Proved rule text, paragraph by paragraph.
        case verified([String])
        /// The owner's words for "no proved rules".
        case unavailable(String)
        /// No rules section.
        case omitted
    }

    nonisolated struct About: Equatable {
        let source: String?
        let rules: Rules
        /// Phase-admitted provenance rows, exactly as supplied.
        let provenance: [Row]
        let historicalQuote: HistoricalQuote?
    }

    nonisolated struct Original: Equatable {
        let identity: Identity
        let title: String
        let outcome: String
        let mode: Mode
        let pregame: Reading
        /// Read in `.comparison` only.
        let later: Reading?
        /// Read in `.result` only.
        let grade: Grade?
        let about: About
        var beforeLabel: String? = nil
    }

    nonisolated struct ShownReading: Equatable {
        let label: String
        let marker: Marker
        /// The owner's figure text, or this slot's own missing reason.
        let text: String
        let isValue: Bool
        /// Nil only for a missing reading.
        let provenance: String?
        /// A valid rail position, or nil — no mark.
        let placement: Double?
    }

    nonisolated struct ShownResult: Equatable {
        let words: String
        /// Nil only when no grade was supplied at all.
        let provenance: String?
    }

    nonisolated struct Content: Equatable {
        let title: String
        let outcome: String
        let readings: [ShownReading]
        /// `.result` mode only.
        let result: ShownResult?
        let about: [Row]
        let rules: Rules

        /// What the rail draws: only readings with a valid placement.
        var marks: [ShownReading] { readings.filter { $0.placement != nil } }
    }

    static let pregameLabel = "Pregame chance"
    static let resultLabel = "Original market result"
    static let resultUnavailable = "Result unavailable"
    static let resultTimeUnknown = "Settlement time unknown"
    static let historicalLabel = "Last recorded probability (historical)"
    static let rulesLabel = "Rules"
    static let unavailable = "Unavailable"
    static let timeUnknown = "Time unknown"

    /// The selected original by exact identity inside the selection's own
    /// scope. A nil, blank, out-of-scope, withdrawn or duplicated identity is
    /// no original — never the first, a default or a neighbour.
    static func original(in catalogue: Catalogue?, selection: Selection?) -> Original? {
        guard let catalogue, let selection, !blank(selection.scope), selection.scope == catalogue.scope,
              !blank(selection.identity.source), !blank(selection.identity.market),
              !blank(selection.identity.side) else { return nil }
        let matches = catalogue.originals.filter { $0.identity == selection.identity }
        return matches.count == 1 ? matches[0] : nil
    }

    static func content(catalogue: Catalogue?, selection: Selection?) -> Content? {
        guard let original = original(in: catalogue, selection: selection),
              !blank(original.title), !blank(original.outcome) else { return nil }
        let earlier = nonBlank(original.beforeLabel) ?? pregameLabel
        let readings: [ShownReading]
        var result: ShownResult?
        switch original.mode {
        case .pregame:
            readings = [shown(earlier, original.pregame, .solid)]
        case .comparison(let later):
            readings = [shown(earlier, original.pregame, .hollow),
                        shown(later.label, original.later, .solid)]
        case .result:
            readings = [shown(earlier, original.pregame, .hollow)]
            if let grade = original.grade, let words = nonBlank(grade.words) {
                result = ShownResult(words: words, provenance: nonBlank(grade.provenance) ?? resultTimeUnknown)
            } else {
                result = ShownResult(words: resultUnavailable, provenance: nil)
            }
        }
        return Content(title: original.title, outcome: original.outcome, readings: readings,
                       result: result, about: about(original), rules: rules(original.about.rules))
    }

    private static func shown(_ label: String, _ reading: Reading?, _ marker: Marker) -> ShownReading {
        if let reading, case .value(let text) = reading.figure, !blank(text) {
            return ShownReading(label: label, marker: marker, text: text, isValue: true,
                                provenance: nonBlank(reading.provenance) ?? timeUnknown,
                                placement: railPlacement(reading.placement))
        }
        var reason = unavailable
        if case .missing(let supplied)? = reading?.figure, let words = nonBlank(supplied) { reason = words }
        return ShownReading(label: label, marker: marker, text: reason, isValue: false,
                            provenance: nil, placement: nil)
    }

    static func railPlacement(_ value: Double?) -> Double? {
        guard let value, value.isFinite, (0...1).contains(value) else { return nil }
        return value
    }

    static func about(_ original: Original) -> [Row] {
        var rows = [Row(label: "Market", value: original.title),
                    Row(label: "Outcome", value: original.outcome)]
        if let source = nonBlank(original.about.source) {
            rows.append(Row(label: "Source", value: source))
        }
        rows += original.about.provenance.filter { !blank($0.label) && !blank($0.value) }
        if let quote = original.about.historicalQuote, !blank(quote.text) {
            let value = nonBlank(quote.recorded).map { "\(quote.text), recorded \($0)" }
                ?? "\(quote.text), time unknown"
            rows.append(Row(label: historicalLabel, value: value))
        }
        return rows
    }

    static func rules(_ rules: Rules) -> Rules {
        switch rules {
        case .verified(let paragraphs):
            let kept = paragraphs.filter { !blank($0) }
            return kept.isEmpty ? .omitted : .verified(kept)
        case .unavailable(let words):
            return blank(words) ? .omitted : .unavailable(words)
        case .omitted:
            return .omitted
        }
    }

    private static func blank(_ text: String) -> Bool {
        text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private static func nonBlank(_ text: String?) -> String? {
        guard let text, !blank(text) else { return nil }
        return text
    }
}

// MARK: - Shared Match Phase & Geometry Helpers (#10868)

/// The owner's explicit phase for the match.
nonisolated enum RugbyMatchEventPagePhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final
}

nonisolated enum RugbyMatchEventPageModel10868 {
    static let comparisonFigureSize: CGFloat = 26

    static func readable(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : value
    }
}

// MARK: - Cards & Accessibility IDs

/// One card the page can show full size, in the page's order. `history` is the anchor.
nonisolated enum EsportsEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// Every side's original pre-match chance beside its reported result.
    case winner
    /// The reported actual margin against the original's minimum.
    case margin
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

    /// Winner sides stack at accessibility sizes; otherwise the measured layout decides.
    static func sidesStack(accessibilitySize: Bool) -> Bool { accessibilitySize }

    /// The smallest touch target any control on this page draws.
    static let minimumTarget: CGFloat = 44

    /// A control's height: the body-scaled control metric, never below the minimum target.
    static func targetHeight(_ scaled: CGFloat) -> CGFloat {
        guard scaled.isFinite else { return minimumTarget }
        return max(minimumTarget, scaled)
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

// MARK: - Shared drawing pieces

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
                        .frame(minWidth: EsportsStoryRules10868.targetHeight(controlSize),
                               minHeight: EsportsStoryRules10868.targetHeight(controlSize))
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
                        .frame(minWidth: EsportsStoryRules10868.targetHeight(controlSize),
                               minHeight: EsportsStoryRules10868.targetHeight(controlSize))
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
                .frame(minHeight: EsportsStoryRules10868.targetHeight(controlSize))
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
                                                   accessibilitySize: EsportsStoryRules10868.sidesStack(accessibilitySize: typeSize.isAccessibilitySize)) {
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
                .frame(minHeight: EsportsStoryRules10868.targetHeight(controlSize), alignment: .leading)
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
