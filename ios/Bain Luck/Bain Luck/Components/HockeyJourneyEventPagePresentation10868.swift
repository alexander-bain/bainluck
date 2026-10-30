import SwiftUI

// #10868 — the hockey journey screen (`nhl-journey`): one native presentation
// composed from the accepted leaves. Win chances lead. A fan sees, in this
// order: the owner's eyebrow and the about entry; the game state and its own
// clock; both teams' chances, goals and score forecast as one aligned
// comparison matrix; the two-team win-probability history front and centre;
// and the player points and assists stories in the owner's story stream, then
// the "All props" entry. The history and each story open as full-size content
// made of the same Views, and "All props" and the selected original's Details
// are two more content modes.
//
// Presentation only, composed from the approved `HockeyJourneyPage.tsx` /
// `hockeyJourney.css`, `HockeyJourneyHeadline.tsx` /
// `hockeyJourneyHeadline.css` and `HockeyFinalReaderAnchor.tsx` /
// `hockeyFinalReaderAnchor.css`, over `hockeyJourney.ts` /
// `hockeyHeadlineEvidence.ts` / `totalPregameForecast.ts`, as mounted in
// `Atlas.tsx` (`nhl-journey`). The reference's fixture loaders, replay
// controls, session state, dwell clock, ranking, forecast qualification,
// chart sampling, paging, sheets and focus restoration are NOT ported. The
// leaves are the actual accepted Views:
//
//   • `FieldProbabilityHistoryPresentation10868` — the anchor;
//   • `PlayerContributionPresentation10868` — player points (columns) and
//     player assists (bars), each with its own input;
//   • `StoryStreamPresentationView10868` — the controlled story stream;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     "All props" and the selected original's Details.
//
// The one thing built here is the comparison matrix, because the existing
// paired headlines admit only NFL and NBA and print integer projections. It is
// typed per phase so a slot cannot move between phases:
//
//   • before — each team's win chance and projected goals;
//   • during — four aligned columns: pregame chance, current chance (which
//     leads), goals so far, and the current projected final or its honest
//     absence, with the earlier pregame forecast shown apart as history;
//   • final — pregame chance, final goals, pregame forecast, the owner's
//     result words and its difference words.
//
// Every figure, absence, column title, clock line, result and difference
// arrives resolved by the owner and is shown verbatim. Nothing here parses,
// rounds, complements, subtracts or formats a value, admits a forecast, or
// turns a final score into a quote; fractional goals and a real 0 stay as
// written. A matrix whose phase is not the page's is not drawn — the owner's
// unavailable words are. Wide widths print full names; a narrow width tries
// the owner's short names; accessibility sizes, or a width where neither grid
// fits, give each team a block of labelled metric pairs instead of shrinking
// text: during play pregame and current chance side by side, then goals and
// projected final; before play chance and projected goals; at the final the
// pregame chance, then final goals beside the pregame forecast. Only a pair
// that cannot fit whole at the reader's text size splits into single
// labelled values.
//
// Each column's source and clock, and the earlier forecast's provenance,
// belong to the About content (the `.about` mode) when the page or the
// full-size history offers a readable About entry; the figures, the game
// state and its context, and the final comparison words stay in the
// headline. A view with no About entry keeps those support words inline.
//
// The host supplies each leaf's own immutable input, already admitted for the
// same snapshot; this layer groups them and never re-elects, copies or
// filters an observation, a marker, a count or a result. A contribution leaf
// whose own phase is not the page's, or whose orientation is not its story's
// (points are columns, assists are bars), is not mounted — never coerced.
//
// The story stream is the owner's: its cards, order, primary, companion,
// position, status, pending, playback, progress, previous/next, scope and
// reader-open flag. This layer wires each supplied card id to the one story
// the owner names for it, and shows the owner's unavailable words for an id
// that names no single story this phase mounts — never a neighbour. A card's
// milestone select, player choice, Details and explore actions, and opening
// or closing its player choices or timing disclosure, first call the stream's
// activation hook (so the owner can hold) and then the host's exact callback
// or binding write; building a card or reading its disclosures asks for
// nothing. Full-size content reuses the same leaves with the host's exact
// callbacks and bindings and no activation, so opening a card never requests a
// hold by appearing.
//
// The full-size history is the same history input with its expanded layout
// and without its expand control; every series, period and goal guide,
// selection, readout, window, scale, inspection and other control is
// unchanged. It sits under the same matrix so the comparison stays in view.
//
// Phone stacks the matrix and history above the stories; a regular or
// unspecified size class (a Mac window) places them side by side while both
// columns keep their minimum widths, otherwise it stacks too, and
// accessibility sizes always stack.
//
// The host owns the scroll, navigation, sheets, Back/Done, paging and swipe,
// focus, routing to and from the catalogue and an original's Details, the
// held/received frame and every selection. This view keeps no state, runs no
// timer or animation, holds no subscription and presents no sheet or
// navigation of its own. Every callback is the host's own closure handed to
// the leaf unchanged. With no callback, nothing pretends to act.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one game snapshot, the phase, header and matrix words with each
// column's clock, the history with its period and goal guides at or before
// that snapshot, both contribution inputs, the story stream and its
// card-to-story map, the originals group, and maps every callback to its
// existing controls. Other NHL routes (`nhl-before`, `nhl-live-reading`,
// `nhl`) and their stories are not this screen.

/// One card the page can show full size. `history` is the anchor.
nonisolated enum HockeyJourneyPageCard10868: String, Hashable, CaseIterable {
    case history
    case points
    case assists
}

/// What the host's container is showing, chosen by the host.
nonisolated enum HockeyJourneyPageMode10868: Equatable {
    /// The game screen body.
    case page
    /// One card's full-size content.
    case reader(HockeyJourneyPageCard10868)
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
    /// The About content: each column's own source and clock, and the
    /// earlier forecast's provenance, as the owner wrote them.
    case about
}

/// The owner's explicit game phase for the whole screen. Never read from a
/// score, a clock or a result.
nonisolated enum HockeyJourneyPagePhase10868: Equatable {
    case before
    case live
    case final

    /// The contribution leaf's own name for the same phase.
    var contributionPhase: PlayerContributionPhase10868 {
        switch self {
        case .before: .before
        case .live: .during
        case .final: .final
        }
    }
}

nonisolated enum HockeyJourneyPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Comparison matrix input

/// One matrix slot: the owner's figure, or that slot's own absence words.
nonisolated enum HockeyJourneySlot10868: Equatable {
    /// The owner's figure ("66%", "2.5", "0") and its spoken words ("2.5 goals").
    case value(String, spoken: String)
    /// "No in-game forecast".
    case absent(String)

    var text: String {
        switch self {
        case .value(let text, _): text
        case .absent(let words): words
        }
    }

    var spoken: String {
        switch self {
        case .value(_, let spoken): spoken
        case .absent(let words): words
        }
    }

    var isValue: Bool {
        if case .value = self { return true }
        return false
    }
}

/// A column title with its own clock and source, or none.
nonisolated struct HockeyJourneyColumn10868: Equatable {
    /// "Current chance".
    let title: String
    /// "Recorded Oct 3, 6:45 PM PT · Bain Luck blend"; nil draws none. In
    /// the About content when an About entry is offered, else under the matrix.
    let provenance: String?
}

nonisolated struct HockeyJourneyTeam10868: Equatable {
    /// "Minnesota Wild".
    let name: String
    /// "Wild"; tried only when full names do not fit. Nil keeps the full name.
    let short: String?
    let tint: Color
}

nonisolated struct HockeyJourneyBeforeRow10868: Equatable {
    let chance: HockeyJourneySlot10868
    let projectedGoals: HockeyJourneySlot10868
}

nonisolated struct HockeyJourneyDuringRow10868: Equatable {
    let pregameChance: HockeyJourneySlot10868
    let currentChance: HockeyJourneySlot10868
    let goals: HockeyJourneySlot10868
    /// A current projected final, or the owner's absence words — never the
    /// pregame forecast.
    let projectedFinal: HockeyJourneySlot10868
}

nonisolated struct HockeyJourneyFinalRow10868: Equatable {
    let pregameChance: HockeyJourneySlot10868
    let finalGoals: HockeyJourneySlot10868
    let pregameForecast: HockeyJourneySlot10868
    /// "Won", "Lost"; nil draws none.
    let result: String?
    /// The owner's comparison of final goals with the forecast ("Bruins: 1.5
    /// goals below forecast"); nil draws none.
    let difference: String?
}

nonisolated struct HockeyJourneyBeforeMatrix10868: Equatable {
    let chance: HockeyJourneyColumn10868
    let projectedGoals: HockeyJourneyColumn10868
    let home: HockeyJourneyBeforeRow10868
    let away: HockeyJourneyBeforeRow10868
}

nonisolated struct HockeyJourneyDuringMatrix10868: Equatable {
    let pregameChance: HockeyJourneyColumn10868
    let currentChance: HockeyJourneyColumn10868
    let goals: HockeyJourneyColumn10868
    let projectedFinal: HockeyJourneyColumn10868
    let home: HockeyJourneyDuringRow10868
    let away: HockeyJourneyDuringRow10868
}

nonisolated struct HockeyJourneyFinalMatrix10868: Equatable {
    let pregameChance: HockeyJourneyColumn10868
    let finalGoals: HockeyJourneyColumn10868
    let pregameForecast: HockeyJourneyColumn10868
    let home: HockeyJourneyFinalRow10868
    let away: HockeyJourneyFinalRow10868
}

nonisolated enum HockeyJourneyMatrix10868: Equatable {
    case before(HockeyJourneyBeforeMatrix10868)
    case during(HockeyJourneyDuringMatrix10868)
    case final(HockeyJourneyFinalMatrix10868)

    var phase: HockeyJourneyPagePhase10868 {
        switch self {
        case .before: .before
        case .during: .live
        case .final: .final
        }
    }
}

/// The earlier pregame score forecast during play: history, never current.
nonisolated struct HockeyJourneyHistoricalForecast10868: Equatable {
    /// "Pregame forecast".
    let title: String
    /// "Wild 4 · Bruins 2.5 goals".
    let reading: String
    /// "Recorded before play · Oct 3, 4:46 PM PT". In the About content when
    /// an About entry is offered, else under the reading.
    let provenance: String?
}

nonisolated struct HockeyJourneyHeadlineInput10868: Equatable {
    /// "Before game · 5:00 PM PT start", "2nd · 4:09 left", "Final".
    let state: String
    /// The game state's own clock ("Game state as of 6:45 PM PT · ESPN"); nil draws none.
    let stateContext: String?
    let home: HockeyJourneyTeam10868
    let away: HockeyJourneyTeam10868
    let matrix: HockeyJourneyMatrix10868
    /// Read during play only.
    let historicalForecast: HockeyJourneyHistoricalForecast10868?
    /// "Hockey win chances, score and forecast".
    let spokenLabel: String
}

// MARK: - Page input

/// The owner's words around the matrix.
nonisolated struct HockeyJourneyPageHeader10868: Equatable {
    /// "NHL · OCT 3 · RECORDED MATCH"; nil draws none.
    let eyebrow: String?
    /// The full-size content's one-line game words ("Minnesota Wild 2–1 Boston Bruins").
    let title: String
    /// Spoken name of the about entry ("About this hockey journey"); nil draws none.
    let aboutLabel: String?
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct HockeyJourneyPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: HockeyJourneyPageCard10868
    /// "Explore points"; nil draws no explore control.
    let exploreLabel: String?
}

nonisolated struct HockeyJourneyPageCopy10868: Equatable {
    /// Spoken name of the stories group ("Game stories").
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single story this phase shows.
    let storyUnavailable: String
    /// Shown in place of a matrix whose phase is not the page's.
    let matrixUnavailable: String
    /// "All 149 original outcomes"; nil draws no entry.
    let allPropsLabel: String?
}

nonisolated struct HockeyJourneyPageInput10868: Equatable {
    let phase: HockeyJourneyPagePhase10868
    let header: HockeyJourneyPageHeader10868
    let headline: HockeyJourneyHeadlineInput10868
    let history: FieldHistoryInput10868
    /// Player points: columns.
    let points: PlayerContributionInput10868?
    /// Player assists: bars.
    let assists: PlayerContributionInput10868?
    let stream: StoryStreamPresentation10868
    let stories: [HockeyJourneyPageStory10868]
    let copy: HockeyJourneyPageCopy10868
}

/// The owner's retained originals behind "All props", for the catalogue and
/// Details modes. Every field reaches the existing leaves unchanged.
struct HockeyJourneyPageOriginals10868 {
    /// The latest admitted originals for one scope; nil shows `emptyWords`.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The owner's held selection; nil holds none.
    let selection: OriginalMarketDetails9483.Selection?
    /// The selected original's recorded history; nil keeps its Details summary.
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    /// The owner's card label for an exact identity; otherwise its title.
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    /// "All props".
    let heading: String
    /// "149 retained originals"; nil draws none.
    var context: String? = nil
    /// "No retained originals for this game".
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum HockeyJourneyPageAccessibilityID10868 {
    static let page = "hockeyJourneyPage10868.page"
    static let header = "hockeyJourneyPage10868.header"
    static let about = "hockeyJourneyPage10868.about"
    static let headline = "hockeyJourneyPage10868.headline"
    static let matrix = "hockeyJourneyPage10868.matrix"
    static let forecast = "hockeyJourneyPage10868.historicalForecast"
    static let anchor = "hockeyJourneyPage10868.anchor"
    static let stories = "hockeyJourneyPage10868.stories"
    static let allProps = "hockeyJourneyPage10868.allProps"
    static let unavailable = "hockeyJourneyPage10868.story.unavailable"
    static let catalogue = "hockeyJourneyPage10868.catalogue"
    static let original = "hockeyJourneyPage10868.original"
    static let aboutContent = "hockeyJourneyPage10868.aboutContent"
    static func card(_ card: HockeyJourneyPageCard10868) -> String { "hockeyJourneyPage10868.card.\(card.rawValue)" }
    static func explore(_ card: HockeyJourneyPageCard10868) -> String { "hockeyJourneyPage10868.explore.\(card.rawValue)" }
}

// MARK: - Matrix model

nonisolated enum HockeyJourneyMatrixArrangement10868: Hashable {
    /// Aligned columns with full names.
    case grid
    /// Aligned columns with the owner's short names.
    case shortGrid
    /// One block per team of labelled metric pairs (`HockeyJourneyMatrixPair10868`).
    case labelledPairs
}

/// How one labelled pair is laid out.
nonisolated enum HockeyJourneyPairArrangement10868: Hashable {
    /// Both labelled values side by side.
    case adjacent
    /// Each labelled value on its own line.
    case single
}

/// One team's line of the matrix, in column order.
nonisolated struct HockeyJourneyMatrixRow10868: Equatable {
    let team: HockeyJourneyTeam10868
    let cells: [HockeyJourneySlot10868]
    let result: String?
    let difference: String?
}

/// One cell with its column title, as the labelled-pairs fallback shows it.
nonisolated struct HockeyJourneyLabelledValue10868: Equatable {
    let column: Int
    let title: String
    let slot: HockeyJourneySlot10868
    let lead: Bool
    /// "Minnesota Wild, Current chance, 82%".
    let spoken: String
}

/// The labelled values kept together in the fallback: a comparison pair, or
/// the one value left over.
nonisolated struct HockeyJourneyMatrixPair10868: Equatable {
    let values: [HockeyJourneyLabelledValue10868]

    /// Side by side first; single lines only when the pair cannot fit whole.
    var arrangements: [HockeyJourneyPairArrangement10868] {
        values.count > 1 ? [.adjacent, .single] : [.single]
    }
}

/// One support line ("Current chance" · "Recorded Oct 3, 6:45 PM PT · Bain Luck blend").
nonisolated struct HockeyJourneySupportLine10868: Equatable {
    let title: String
    let words: String
}

/// The phase's matrix as aligned columns and rows, without re-electing any
/// value: each typed slot keeps its own place.
nonisolated struct HockeyJourneyMatrixLayout10868: Equatable {
    let columns: [HockeyJourneyColumn10868]
    /// The emphasised column: the current chance during play, else the first.
    let lead: Int
    let rows: [HockeyJourneyMatrixRow10868]
    /// Column indices kept together in the labelled-pairs fallback, in order.
    let groups: [[Int]]

    /// One team's labelled pairs, exactly as the fallback draws them.
    func pairs(row: Int) -> [HockeyJourneyMatrixPair10868] {
        groups.map { group in
            HockeyJourneyMatrixPair10868(values: group.map { column in
                HockeyJourneyLabelledValue10868(
                    column: column, title: columns[column].title, slot: rows[row].cells[column],
                    lead: column == lead, spoken: spoken(row: row, column: column))
            })
        }
    }

    /// "Minnesota Wild, Current chance, 82%".
    func spoken(row: Int, column: Int) -> String {
        "\(rows[row].team.name), \(columns[column].title), \(rows[row].cells[column].spoken)"
    }

    /// "Minnesota Wild, Won"; the name alone without result words.
    func spokenTeam(_ row: Int) -> String {
        let team = rows[row]
        guard let result = HockeyJourneyHeadlineModel10868.readable(team.result) else { return team.team.name }
        return "\(team.team.name), \(result)"
    }
}

nonisolated struct HockeyJourneyHeadlineModel10868: Equatable {
    let input: HockeyJourneyHeadlineInput10868
    let phase: HockeyJourneyPagePhase10868

    /// The matrix only at the page's own phase. Otherwise nothing.
    var layout: HockeyJourneyMatrixLayout10868? {
        guard input.matrix.phase == phase else { return nil }
        let home = input.home, away = input.away
        switch input.matrix {
        case .before(let m):
            return HockeyJourneyMatrixLayout10868(columns: [m.chance, m.projectedGoals], lead: 0, rows: [
                HockeyJourneyMatrixRow10868(team: home, cells: [m.home.chance, m.home.projectedGoals], result: nil, difference: nil),
                HockeyJourneyMatrixRow10868(team: away, cells: [m.away.chance, m.away.projectedGoals], result: nil, difference: nil),
            ], groups: [[0, 1]])
        case .during(let m):
            return HockeyJourneyMatrixLayout10868(
                columns: [m.pregameChance, m.currentChance, m.goals, m.projectedFinal], lead: 1, rows: [
                    HockeyJourneyMatrixRow10868(team: home, cells: [m.home.pregameChance, m.home.currentChance,
                                                                    m.home.goals, m.home.projectedFinal],
                                                result: nil, difference: nil),
                    HockeyJourneyMatrixRow10868(team: away, cells: [m.away.pregameChance, m.away.currentChance,
                                                                    m.away.goals, m.away.projectedFinal],
                                                result: nil, difference: nil),
                ], groups: [[0, 1], [2, 3]])
        case .final(let m):
            return HockeyJourneyMatrixLayout10868(
                columns: [m.pregameChance, m.finalGoals, m.pregameForecast], lead: 0, rows: [
                    HockeyJourneyMatrixRow10868(team: home, cells: [m.home.pregameChance, m.home.finalGoals, m.home.pregameForecast],
                                                result: m.home.result, difference: m.home.difference),
                    HockeyJourneyMatrixRow10868(team: away, cells: [m.away.pregameChance, m.away.finalGoals, m.away.pregameForecast],
                                                result: m.away.result, difference: m.away.difference),
                ], groups: [[0], [1, 2]])
        }
    }

    /// The earlier forecast as history, during play only.
    var historicalForecast: HockeyJourneyHistoricalForecast10868? {
        phase == .live && input.matrix.phase == .live ? input.historicalForecast : nil
    }

    /// Each column's own clock line, in column order ("Current chance · Recorded …").
    var provenance: [HockeyJourneySupportLine10868] {
        (layout?.columns ?? []).compactMap { column in
            Self.readable(column.provenance).map { HockeyJourneySupportLine10868(title: column.title, words: $0) }
        }
    }

    /// Everything the About content holds: each column's own clock line, then
    /// the earlier forecast's provenance during play.
    var support: [HockeyJourneySupportLine10868] {
        let forecast = historicalForecast.flatMap { forecast in
            Self.readable(forecast.provenance).map { HockeyJourneySupportLine10868(title: forecast.title, words: $0) }
        }
        return provenance + (forecast.map { [$0] } ?? [])
    }

    /// The column clock lines printed under the matrix: none when a readable
    /// About entry holds them, all of them otherwise.
    func inlineProvenance(aboutAvailable: Bool) -> [HockeyJourneySupportLine10868] {
        aboutAvailable ? [] : provenance
    }

    /// The earlier forecast's provenance under its reading, on the same rule.
    func inlineForecastProvenance(aboutAvailable: Bool) -> String? {
        aboutAvailable ? nil : Self.readable(historicalForecast?.provenance)
    }

    /// The owner's difference words, final only.
    var differences: [String] {
        (layout?.rows ?? []).compactMap { Self.readable($0.difference) }
    }

    static func readable(_ words: String?) -> String? {
        guard let words, !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return words
    }

    /// The arrangements to try, in order. Accessibility sizes go straight to
    /// labelled pairs.
    static func arrangements(accessibilitySize: Bool) -> [HockeyJourneyMatrixArrangement10868] {
        accessibilitySize ? [.labelledPairs] : [.grid, .shortGrid, .labelledPairs]
    }
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
nonisolated struct HockeyJourneyPageModel10868: Equatable {
    let input: HockeyJourneyPageInput10868

    init(_ input: HockeyJourneyPageInput10868) {
        self.input = input
    }

    var headline: HockeyJourneyHeadlineModel10868 {
        HockeyJourneyHeadlineModel10868(input: input.headline, phase: input.phase)
    }

    /// Points, as columns, at the page's own phase.
    var points: PlayerContributionInput10868? {
        guard let points = input.points, points.phase == input.phase.contributionPhase,
              points.orientation == .columns else { return nil }
        return points
    }

    /// Assists, as bars, at the page's own phase.
    var assists: PlayerContributionInput10868? {
        guard let assists = input.assists, assists.phase == input.phase.contributionPhase,
              assists.orientation == .bars else { return nil }
        return assists
    }

    func isMounted(_ card: HockeyJourneyPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .points: points != nil
        case .assists: assists != nil
        }
    }

    /// The owner's link a stream card id names: exactly one link with that
    /// id, to a story this phase mounts. Otherwise nothing.
    func story(_ cardID: String) -> HockeyJourneyPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    func storyCard(_ cardID: String) -> HockeyJourneyPageCard10868? { story(cardID)?.card }

    /// Full-size content exists for the anchor and for a story this phase shows.
    func readerShows(_ card: HockeyJourneyPageCard10868) -> Bool { isMounted(card) }

    /// The anchor's full-size content: the same history in its expanded
    /// layout, without an expand control inside the reader. Every other field
    /// is the owner's, unchanged.
    var readerHistory: FieldHistoryInput10868 {
        let history = input.history
        return FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: history.plotHeight,
            unboundReadingWords: history.unboundReadingWords, plotUnavailableWords: history.plotUnavailableWords,
            windows: history.windows, scale: history.scale, moreOriginals: history.moreOriginals,
            details: history.details, expand: nil, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: history.inspection,
            layout: .expanded,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: history.showsKey
        )
    }

    // MARK: Page controls

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && HockeyJourneyHeadlineModel10868.readable(input.header.aboutLabel) != nil
    }

    /// Whether `mode` shows the About entry: the page and the full-size
    /// history, which both show the matrix, when an About can open.
    func aboutEntry(mode: HockeyJourneyPageMode10868, canOpen: Bool) -> Bool {
        switch mode {
        case .page, .reader(.history): aboutAvailable(canOpen: canOpen)
        case .reader, .catalogue, .original, .about: false
        }
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && HockeyJourneyHeadlineModel10868.readable(input.copy.allPropsLabel) != nil
    }

    func exploreAvailable(_ link: HockeyJourneyPageStory10868, canOpen: Bool) -> Bool {
        canOpen && HockeyJourneyHeadlineModel10868.readable(link.exploreLabel) != nil
    }

    /// The arrangements to try, in order. Accessibility sizes and a compact
    /// width stack; a regular or unspecified width (a Mac window has no size
    /// class) tries side by side, then stacks — the columns' minimum widths
    /// decide which fits.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [HockeyJourneyPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

// MARK: - Matrix view

/// The phase's comparison matrix: state and clock, aligned team rows, the
/// earlier forecast as history during play, the owner's final difference
/// words, and — only without an About entry — each column's own clock.
struct HockeyJourneyHeadline10868: View {
    let input: HockeyJourneyHeadlineInput10868
    let phase: HockeyJourneyPagePhase10868
    let unavailable: String
    /// True only when the surrounding mode shows a readable About entry that
    /// holds the support lines; an unbound view keeps them inline.
    var aboutAvailable: Bool = false

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var leadSize: CGFloat = 28
    @ScaledMetric(relativeTo: .title2) private var valueSize: CGFloat = 22
    @ScaledMetric(relativeTo: .body) private var valueMinWidth: CGFloat = 64
    @ScaledMetric(relativeTo: .body) private var valueMaxWidth: CGFloat = 120
    @ScaledMetric(relativeTo: .body) private var nameMinWidth: CGFloat = 52

    var model: HockeyJourneyHeadlineModel10868 { HockeyJourneyHeadlineModel10868(input: input, phase: phase) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.state)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                if let context = HockeyJourneyHeadlineModel10868.readable(input.stateContext) {
                    Text(context)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            if let layout = model.layout {
                matrix(layout)
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.matrix)
            } else {
                Text(unavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let forecast = model.historicalForecast {
                historical(forecast)
            }
            let differences = model.differences
            if !differences.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(differences.enumerated()), id: \.offset) { _, words in
                        Text(words)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            let provenance = model.inlineProvenance(aboutAvailable: aboutAvailable)
            if !provenance.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(Array(provenance.enumerated()), id: \.offset) { _, line in
                        Text("\(line.title) · \(line.words)")
                            .font(.footnote)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.spokenLabel)
        .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.headline)
    }

    /// The model's arrangements in order; the first that fits whole is drawn.
    private func matrix(_ layout: HockeyJourneyMatrixLayout10868) -> some View {
        ViewThatFits(in: .horizontal) {
            ForEach(HockeyJourneyHeadlineModel10868.arrangements(accessibilitySize: typeSize.isAccessibilitySize),
                    id: \.self) { arrangement in
                switch arrangement {
                case .grid: grid(layout, short: false)
                case .shortGrid: grid(layout, short: true)
                case .labelledPairs: labelledPairs(layout)
                }
            }
        }
    }

    private func grid(_ layout: HockeyJourneyMatrixLayout10868, short: Bool) -> some View {
        Grid(alignment: .center, horizontalSpacing: 10, verticalSpacing: 10) {
            GridRow {
                Color.clear
                    .gridCellUnsizedAxes([.horizontal, .vertical])
                ForEach(Array(layout.columns.enumerated()), id: \.offset) { _, column in
                    Text(column.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(minWidth: valueMinWidth, maxWidth: valueMaxWidth)
                        .accessibilityHidden(true)
                }
            }
            ForEach(Array(layout.rows.enumerated()), id: \.offset) { index, row in
                GridRow {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(short ? (HockeyJourneyHeadlineModel10868.readable(row.team.short) ?? row.team.name) : row.team.name)
                            .font(.headline)
                            .foregroundStyle(row.team.tint)
                            .fixedSize()
                        if let result = HockeyJourneyHeadlineModel10868.readable(row.result) {
                            Text(result)
                                .font(.subheadline)
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize()
                        }
                    }
                    .frame(minWidth: nameMinWidth, alignment: .leading)
                    .gridColumnAlignment(.leading)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(layout.spokenTeam(index))
                    ForEach(Array(row.cells.enumerated()), id: \.offset) { column, slot in
                        cell(slot, lead: column == layout.lead, tint: row.team.tint)
                            .frame(minWidth: valueMinWidth, maxWidth: valueMaxWidth)
                            .accessibilityElement(children: .ignore)
                            .accessibilityLabel(layout.spoken(row: index, column: column))
                    }
                }
            }
        }
    }

    /// Accessibility sizes, or a width where no grid fits: each team's name
    /// and result, then the layout's labelled pairs, nothing shrunk.
    private func labelledPairs(_ layout: HockeyJourneyMatrixLayout10868) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            ForEach(Array(layout.rows.enumerated()), id: \.offset) { index, row in
                VStack(alignment: .leading, spacing: 8) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(row.team.name)
                            .font(.title3.bold())
                            .foregroundStyle(row.team.tint)
                        if let result = HockeyJourneyHeadlineModel10868.readable(row.result) {
                            Text(result)
                                .font(.body)
                                .foregroundStyle(DS.textPrimary)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(layout.spokenTeam(index))
                    .accessibilityAddTraits(.isHeader)
                    ForEach(Array(layout.pairs(row: index).enumerated()), id: \.offset) { _, pair in
                        ViewThatFits(in: .horizontal) {
                            ForEach(pair.arrangements, id: \.self) { arrangement in
                                switch arrangement {
                                case .adjacent:
                                    HStack(alignment: .top, spacing: 20) {
                                        ForEach(pair.values, id: \.column) { labelled($0, tint: row.team.tint) }
                                    }
                                case .single:
                                    VStack(alignment: .leading, spacing: 8) {
                                        ForEach(pair.values, id: \.column) { labelled($0, tint: row.team.tint) }
                                    }
                                }
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
        }
    }

    /// One column title over its figure or absence words, spoken as one.
    private func labelled(_ value: HockeyJourneyLabelledValue10868, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value.title)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
            cell(value.slot, lead: value.lead, tint: tint, alignment: .leading)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(value.spoken)
    }

    /// A figure in full contrast, the lead larger and in the team's tint; an
    /// absence in its own words — never a dash or a zero.
    @ViewBuilder private func cell(_ slot: HockeyJourneySlot10868, lead: Bool, tint: Color,
                                   alignment: TextAlignment = .center) -> some View {
        switch slot {
        case .value(let text, _):
            Text(text)
                .font(.system(size: lead ? leadSize : valueSize, weight: lead ? .bold : .semibold).monospacedDigit())
                .foregroundStyle(lead ? tint : DS.textPrimary)
                .fixedSize()
        case .absent(let words):
            Text(words)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .multilineTextAlignment(alignment)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func historical(_ forecast: HockeyJourneyHistoricalForecast10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(forecast.title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
            Text(forecast.reading)
                .font(.body.weight(.semibold).monospacedDigit())
                .foregroundStyle(DS.textPrimary)
            if let provenance = model.inlineForecastProvenance(aboutAvailable: aboutAvailable) {
                Text(provenance)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.leading, 12)
        .overlay(alignment: .leading) {
            Rectangle().fill(DS.border).frame(width: 3)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.forecast)
    }
}

// MARK: - About content

/// The support lines the headline leaves to About: each column's own source
/// and clock and the earlier forecast's provenance, in the owner's words.
/// Static text; it acts on nothing.
struct HockeyJourneyAboutContent10868: View {
    let lines: [HockeyJourneySupportLine10868]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                VStack(alignment: .leading, spacing: 2) {
                    Text(line.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                    Text(line.words)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityElement(children: .combine)
            }
        }
    }
}

// MARK: - Page view

struct HockeyJourneyEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: HockeyJourneyPageInput10868
    var mode: HockeyJourneyPageMode10868 = .page
    /// The catalogue and Details modes' content; nil: neither has any.
    var originals: HockeyJourneyPageOriginals10868? = nil
    var onAbout: (() -> Void)? = nil
    /// Opens the host's existing catalogue.
    var onAllProps: (() -> Void)? = nil
    /// A catalogue card's exact selection, for the host to hold and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// A stream card's explore control, for the host's full-size container.
    var onOpenStory: ((HockeyJourneyPageCard10868) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    var onPointsSelect: ((String) -> Void)? = nil
    var onPointsChoosePlayer: ((String) -> Void)? = nil
    var onPointsDetails: ((String) -> Void)? = nil
    var onAssistsSelect: ((String) -> Void)? = nil
    var onAssistsChoosePlayer: ((String) -> Void)? = nil
    var onAssistsDetails: ((String) -> Void)? = nil
    /// Page-owned disclosures. Full-size content gets them unchanged; a card
    /// in the stream gets them through `relay(_:through:)`.
    var pointsChoicesExpanded: Binding<Bool>? = nil
    var pointsTimingExpanded: Binding<Bool>? = nil
    var assistsChoicesExpanded: Binding<Bool>? = nil
    var assistsTimingExpanded: Binding<Bool>? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 460
    @ScaledMetric(relativeTo: .body) private var storiesMinWidth: CGFloat = 360
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var model: HockeyJourneyPageModel10868 { HockeyJourneyPageModel10868(input) }

    /// A card's own action, after the stream's activation hook when the card
    /// sits in the stream. No host callback: no action at all.
    static func relay<Value>(_ action: ((Value) -> Void)?,
                             through activation: StoryStreamCardActivation10868?) -> ((Value) -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return { value in
            activation.request()
            action(value)
        }
    }

    /// A disclosure is an interaction too: in the stream, opening or closing
    /// it asks the stream's activation hook first, then writes the exact new
    /// value to the owner's binding. Reading it asks for nothing. No binding:
    /// none. No activation: the owner's binding itself.
    static func relay(_ binding: Binding<Bool>?,
                      through activation: StoryStreamCardActivation10868?) -> Binding<Bool>? {
        guard let binding else { return nil }
        guard let activation else { return binding }
        return Binding(
            get: { binding.wrappedValue },
            set: { expanded in
                activation.request()
                binding.wrappedValue = expanded
            }
        )
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .catalogue: catalogueMode
            case .original: originalMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    /// Whether this mode shows the About entry.
    private var showsAbout: Bool { model.aboutEntry(mode: mode, canOpen: onAbout != nil) }

    func headlineContent() -> HockeyJourneyHeadline10868 {
        HockeyJourneyHeadline10868(input: input.headline, phase: input.phase, unavailable: input.copy.matrixUnavailable,
                                   aboutAvailable: showsAbout)
    }

    /// The About content: what the headline leaves out when an About entry is shown.
    func aboutContent() -> HockeyJourneyAboutContent10868 {
        HockeyJourneyAboutContent10868(lines: model.headline.support)
    }

    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : input.history,
            onAction: onHistoryAction,
            onInspectionChoice: onHistoryInspectionChoice,
            onPlotPosition: onHistoryPlotPosition
        )
    }

    /// `activation` is the stream's hook for a card in the stream; nil in
    /// full-size content.
    func pointsContent(activation: StoryStreamCardActivation10868? = nil) -> PlayerContributionPresentation10868? {
        model.points.map {
            PlayerContributionPresentation10868(
                input: $0,
                onSelect: Self.relay(onPointsSelect, through: activation),
                onChoosePlayer: Self.relay(onPointsChoosePlayer, through: activation),
                onDetails: Self.relay(onPointsDetails, through: activation),
                choicesExpanded: Self.relay(pointsChoicesExpanded, through: activation),
                timingExpanded: Self.relay(pointsTimingExpanded, through: activation)
            )
        }
    }

    func assistsContent(activation: StoryStreamCardActivation10868? = nil) -> PlayerContributionPresentation10868? {
        model.assists.map {
            PlayerContributionPresentation10868(
                input: $0,
                onSelect: Self.relay(onAssistsSelect, through: activation),
                onChoosePlayer: Self.relay(onAssistsChoosePlayer, through: activation),
                onDetails: Self.relay(onAssistsDetails, through: activation),
                choicesExpanded: Self.relay(assistsChoicesExpanded, through: activation),
                timingExpanded: Self.relay(assistsTimingExpanded, through: activation)
            )
        }
    }

    /// A stream card's explore control: the hold first, then the host's
    /// opener with the exact story. Nil without an opener or words.
    func exploreAction(_ link: HockeyJourneyPageStory10868,
                       activation: StoryStreamCardActivation10868?) -> (() -> Void)? {
        guard model.exploreAvailable(link, canOpen: onOpenStory != nil),
              let open = Self.relay(onOpenStory, through: activation) else { return nil }
        let card = link.card
        return { open(card) }
    }

    /// The existing catalogue with the owner's originals and select callback.
    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: onOriginalSelect
            )
        }
    }

    /// The existing Details for the owner's held selection, with its recorded
    /// history and history callback.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: onOriginalHistory
            )
        }
    }

    func openAbout() {
        guard model.aboutAvailable(canOpen: onAbout != nil) else { return }
        onAbout?()
    }

    func openAllProps() {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return }
        onAllProps?()
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            let arrangements = HockeyJourneyPageModel10868.arrangements(
                sizeClass: sizeClass,
                accessibilitySize: typeSize.isAccessibilitySize
            )
            if arrangements == [.stacked] {
                stacked
            } else {
                ViewThatFits(in: .horizontal) {
                    sideBySide
                    stacked
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.page)
    }

    private var stacked: some View {
        VStack(alignment: .leading, spacing: 20) {
            anchor
            stories
        }
    }

    private var sideBySide: some View {
        HStack(alignment: .top, spacing: 24) {
            anchor
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
            stories
                .frame(minWidth: storiesMinWidth, maxWidth: .infinity, alignment: .topLeading)
        }
    }

    /// The owner's eyebrow and the about entry.
    @ViewBuilder private var header: some View {
        let eyebrow = HockeyJourneyHeadlineModel10868.readable(input.header.eyebrow)
        let about = showsAbout
        if eyebrow != nil || about {
            HStack(alignment: .center, spacing: 12) {
                if let eyebrow {
                    Text(eyebrow)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Spacer(minLength: 0)
                }
                if about {
                    aboutButton
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.header)
        }
    }

    /// The ⓘ entry to the owner's About, spoken with its label.
    @ViewBuilder private var aboutButton: some View {
        if let label = input.header.aboutLabel {
            Button(action: openAbout) {
                Image(systemName: "info.circle")
                    .font(.title3)
                    .foregroundStyle(DS.textPrimary)
                    .frame(minWidth: controlSize, minHeight: controlSize)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(label)
            .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.about)
        }
    }

    // MARK: Anchor and stories

    /// The matrix above the history, as one anchor.
    private var anchor: some View {
        VStack(alignment: .leading, spacing: 20) {
            headlineContent()
            historyContent(reader: false)
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(HockeyJourneyPageCardSurface10868())
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.anchor)
        }
    }

    private var stories: some View {
        VStack(alignment: .leading, spacing: 16) {
            StoryStreamPresentationView10868(input.stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            if model.allPropsAvailable(canOpen: onAllProps != nil), let label = input.copy.allPropsLabel {
                Button(action: openAllProps) {
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
                    .frame(minHeight: controlSize)
                    .modifier(HockeyJourneyPageCardSurface10868())
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.allProps)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.stories)
    }

    /// The story the owner links to this stream card, with the stream's
    /// activation hook and its explore control, or the owner's unavailable words.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.story(card.id) {
            VStack(alignment: .leading, spacing: 8) {
                if let explore = exploreAction(link, activation: activation), let label = link.exploreLabel {
                    Button(action: explore) {
                        HStack(spacing: 6) {
                            Text(label)
                                .font(.subheadline.weight(.semibold))
                                .fixedSize(horizontal: false, vertical: true)
                            Image(systemName: "arrow.up.right")
                                .font(.subheadline.weight(.semibold))
                                .accessibilityHidden(true)
                        }
                        .foregroundStyle(DS.blue)
                        .frame(minHeight: controlSize)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.explore(link.card))
                }
                cardContent(link.card, activation: activation)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(HockeyJourneyPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(HockeyJourneyPageCardSurface10868())
                .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.unavailable)
        }
    }

    // MARK: Content shared by the page and the reader

    @ViewBuilder private func cardContent(_ card: HockeyJourneyPageCard10868,
                                          activation: StoryStreamCardActivation10868?) -> some View {
        switch card {
        case .history: historyContent(reader: true)
        case .points: pointsContent(activation: activation)
        case .assists: assistsContent(activation: activation)
        }
    }

    /// The same leaf and input, full size, for the host's existing reader,
    /// under the compact game words. The history also keeps the matrix and
    /// the About entry for its support lines. A card this phase does not show
    /// has no content.
    @ViewBuilder private func reader(_ card: HockeyJourneyPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                if card == .history {
                    headlineContent()
                }
                cardContent(card, activation: nil)
            }
        }
    }

    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.header.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                Text(input.headline.state)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if showsAbout {
                aboutButton
            }
        }
    }

    // MARK: All props and the selected original's Details

    /// Every retained original under the compact game words.
    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.catalogue)
        }
    }

    /// The held original's existing Details, for the host's container.
    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.original)
        }
    }

    // MARK: About

    /// The About content under the compact game words, for the host's container.
    private var aboutMode: some View {
        VStack(alignment: .leading, spacing: 12) {
            compactHeader
            aboutContent()
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(HockeyJourneyPageAccessibilityID10868.aboutContent)
    }
}

/// The reference's white card on the page surface.
private struct HockeyJourneyPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
