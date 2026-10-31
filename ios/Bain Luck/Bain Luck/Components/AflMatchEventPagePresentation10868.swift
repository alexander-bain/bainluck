import SwiftUI

// #10868 — the AFL match screen (`afl-match`): one native presentation for an
// AFL match before, during and after play, composed from the accepted shared
// leaves. Both named win chances lead, each beside its own clock, at equal
// prominence. A fan sees, in this order: the match headline — the owner's
// eyebrow, title and About entry; each named team's pre-match chance; during
// play that chance beside the owner's recorded or current chance or its
// availability words; at the final that chance beside the team's actual final
// points, with the owner's separately admitted result words in the headline's
// state — beside the shared, named, shape-keyed win probability history; then,
// at the final, the scoring-play story and the quarter story; then the original
// markets with the held original's Details and the "All markets" entry. Each
// card opens as full-size content made of the same View and input; "All
// markets", the held original's Details and the match About are further
// content modes.
//
// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: a fan sees both named win
// chances with their own dates and the completed comeback — each actual
// quarter margin and every scoring play — with large usable readers and exact
// original-market Details.
//
// Presentation only, from the approved `AflMatch.tsx`, `AflMatchHeadline.tsx`,
// `AflHistoryPlot.tsx`, `AflQuarterCard.tsx` and `AflScoringCard.tsx` with
// `aflMatch.css` and `aflScoringCard.css`, and both native readability
// adoption records. The references' loaders, wire and ticker checks, market and
// event allowlists, candle admission, baseline and lowest-close election,
// scoring-play validation, run inference, points arithmetic, chronology
// reconstruction, margin computation, clock and percent formatting and window
// filtering are NOT ported. The leaves are the actual accepted Views,
// unchanged:
//
//   • `FieldPhaseHeadlinePresentation10868` — the two named teams;
//   • `FieldProbabilityHistoryPresentation10868` — the anchor;
//   • `RugbyMatchEventPageComparisonPresentation10868` — the accepted paired,
//     dated comparison above the anchor, inline and full size: each team's
//     readout slots exactly as `FieldHistoryGeometry10868.readoutSlots`
//     resolves them and `spokenSlot` speaks them, every figure at one scaled
//     size, the whole name and history shape, a missing slot as its own
//     words, separate dates, the same observation bound the same way. It
//     reads the exact history copy the anchor beside it draws;
//   • `HistoricalChanceResultPresentation10868` — the final chance-to-result
//     portion of the quarter story: the subject's pre-match chance and the
//     owner's later checkpoint, each with its own clock, beside the separately
//     reported actual. It never replaces either actual-points graphic;
//   • `StoryStreamPresentationView10868` — the owner's controlled stream;
//   • `OriginalMarketChooserView9483` — the originals on the page;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     "All markets" and the held original's Details;
//   • `AussieRulesEventPageAboutContent10868` — the owner's About with sources.
//
// While every history original has no choose control and no key context, the
// comparison stands in for the shared key: a presentation copy of the history
// hides that key, and the owner's history input — every series, run, reading,
// id, action, scale and inspection — is never changed. Otherwise the owner's
// key stays. The full-size history uses the accepted
// `RugbyMatchEventPageModel10868.readerPlotHeight`: a usable owner height,
// never shorter than inline; any other height keeps the inline one.
//
// Two small immutable presentations are drawn here, because no accepted leaf
// carries their grammar, on the accepted Australian-rules result-story axis
// (`AussieRulesPointsScale10868` with `AussieRulesResultStoryGeometry10868`:
// the owner's signed range and ticks, a neutral zero, nothing clamped):
//
//   • the quarter story — one signed actual-margin bar per owner quarter row,
//     the held row's whole score per team, then the chance-to-result leaf;
//   • the scoring-play story — the owner's scoring plays in the owner's order
//     as a step plot of the actual lead, where x is the play's position in that
//     order and never elapsed time; the owner's quarter-first-play guides; the
//     held play's period, clock, scorer, lead and whole score; earlier and later
//     controls; the owner's separately supplied checkpoints; and the subject's
//     two dated chance links from the same chance-to-result input.
//
// Both take arbitrary admitted inputs — any teams, any number of rows or plays,
// a lead that changes hands — and contain no specimen name, number, id or
// clock.
//
// The page's phase is the owner's explicit `AflMatchEventPagePhase10868`,
// never read from a raw status, a clock, a quote, a score or a settlement.
// Before play only the pre-match chances, the owner's history and originals
// are shown: a supplied later reading, final points, result words, quarter
// rows, scoring plays, checkpoints, chance-to-result or report never are.
// During play no final actual, quarter or scoring story, chance-to-result or
// report is shown, and history alone never makes the page say live. At the
// final the headline reads each team's pre-match chance beside its actual
// final points; the owner's result words sit in the headline's state. A
// headline from another phase is not coerced: the owner's unavailable words
// show instead.
//
// OWNER-RESOLVED, NEVER DERIVED HERE: the phase and status words; each team's
// identity, name, tint, key shape and qualified readings with their own clocks
// (pre-match, recorded or current — the owner's label says which; a recording
// is never promoted to a current chance here); the final points; the result
// words; every quarter row's lead (geometry only), lead words, leading team,
// score label and per-team score words; every scoring play's lead (geometry
// only), leading team, mark weight, period and clock words, scorer words,
// per-team score words, lead words and spoken words; the guides; the
// checkpoints; the points scales; the chance-to-result readings, observations,
// keys and actual; the history's series, runs, breaks, marks, readouts,
// windows, inspection and controls; the stream; the originals, their modes,
// readings, grades and recorded history; every held selection; the About and
// its sources. This layer never computes points from goals and behinds, never
// subtracts scores, never sums quarters, never elects a low or a run, never
// orders, sorts, filters or deduplicates plays or rows, never grades a
// contract from the actual score, never copies an event chance into an
// original, never complements or normalizes two chances, never treats a
// missing value as zero, never adds a settled result point or a kickoff marker
// to the probability history, never aligns a scoring play or quarter to a
// probability observation, and never deduplicates two observations because
// their figures match. A held quarter, play, card or original that is absent
// from an arrival shows the owner's unavailable words; no neighbour stands in,
// and only that exact identity restores it.
//
// INTERACTION. On the page — the headline's open and About, the anchor
// history's actions, inspection choices and plot taps, a directly mounted
// card's expand, play, quarter, checkpoint and chance selections, quarters link
// and Details, the originals' selection and the All markets entry — and in the
// catalogue and Details content, the action calls the owner's interaction hook
// once and then the owner's exact callback with its exact value. A card inside
// the owner's stream calls the stream's activation hook instead, never the
// page hook as well. Full-size content, its reader controls and the About keep
// the exact callbacks: their host already holds. Selecting a play or a quarter
// hands back only that row's id: it never moves the probability cursor, the
// headline or the held original. Building or reading the view calls nothing.
// Without a callback there is no control and no hook call.
//
// LAYOUT. Phone and accessibility sizes stack the headline above the history,
// then the cards and the originals. The comparison sits directly above the
// history in every arrangement and at full size, keeping its accepted
// equal-share columns or full-width rows. A regular or unspecified width (a Mac
// window) places the headline beside the history while both keep their minimum
// widths, otherwise it stacks. The scoring readout and the chance links sit
// side by side while both fit and stack at accessibility sizes. Quarter bars
// are full-width rows on one signed axis. Plot heights are the owner's and are
// never shrunk; no main value shrinks to fit.
//
// The host owns the scroll, navigation, sheets, Back/Done, next/previous card,
// focus, routing, every held selection, how a hook request holds the stream,
// subscriptions and every genuine update. This view keeps no state, runs no
// timer or animation, holds no subscription and presents nothing of its own.
//
// Host binding still owed: no AFL page input adapter exists at this base. Phase
// and status words, team identities and readings, final points and result
// words, quarter rows, scoring plays, guides, checkpoints, the chance-to-result
// input, history admission, stream, originals and About are unbound owner
// channels (named in the handback).

// MARK: - Phase, cards, modes

/// The owner's explicit phase for the whole screen.
nonisolated enum AflMatchEventPagePhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final
}

/// One card the page can show full size, in the page's order. `history` is the anchor.
nonisolated enum AflMatchEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// Every scoring play's actual lead, in the owner's order.
    case scoring
    /// The actual margin at each quarter row, then the chance-to-result portion.
    case periods
}

/// What the host's container is showing, chosen by the host.
nonisolated enum AflMatchEventPageMode10868: Equatable {
    /// The match screen body.
    case page
    /// One card's full-size content.
    case reader(AflMatchEventPageCard10868)
    /// Every retained original ("All markets").
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's match About with its sources.
    case about
}

/// A full-size content control, handed to the host exactly.
nonisolated enum AflMatchReaderIntent10868: Equatable {
    /// The mounted card before the shown one.
    case previous(AflMatchEventPageCard10868)
    /// The mounted card after the shown one.
    case next(AflMatchEventPageCard10868)
    /// A named card from inside the shown one (the scoring story's quarters link).
    case open(AflMatchEventPageCard10868)
    /// The shown card's Details.
    case details(AflMatchEventPageCard10868)
    /// Leave full-size content for the match.
    case back
    /// Close the catalogue, the held original's Details or the About.
    case done
}

nonisolated enum AflMatchEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

/// The page's regions in reading order.
nonisolated enum AflMatchEventPageBlock10868: String, CaseIterable {
    case headline
    case notice
    case anchor
    case cards
    case originals
    case allProps
}

// MARK: - Actual-points input

/// One team's whole score in a row, in the owner's words.
nonisolated struct AflMatchTeamScore10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    let name: String
    let score: String
}

/// One owner quarter row: the actual margin at its end, geometry only.
nonisolated struct AflMatchPeriodRow10868: Equatable {
    let id: String
    /// The row's short label on the axis.
    let label: String
    /// Signed actual points on the owner's scale; geometry only. Nil draws no bar.
    let lead: Double?
    /// The owner's words for the margin beside the bar.
    let leadWords: String
    /// The leading team's colour and key; nil draws the neutral colour.
    let leader: FieldChooserOriginalRef10868?
    /// The held row's readout label.
    let scoreLabel: String
    /// Each team's whole score at the row's end, in the owner's order.
    let scores: [AflMatchTeamScore10868]
    let spoken: String
}

nonisolated struct AflMatchPeriodCopy10868: Equatable {
    let eyebrow: String?
    let title: String
    /// Spoken name of the bars.
    let graphicLabel: String
    let rowsEmpty: String
    let leadUnavailable: String
    let offScale: String
    let selectionPrompt: String?
    let selectionMissing: String
    let selectHint: String?
    let expandLabel: String
    /// The card's Details control; nil draws none.
    let detailsLabel: String?
}

nonisolated struct AflMatchPeriodStory10868: Equatable {
    /// The owner's rows in the owner's order.
    let rows: [AflMatchPeriodRow10868]
    /// The owner's signed actual-points axis; its upper and lower words name
    /// who leads on each side.
    let scale: AussieRulesPointsScale10868
    /// Host-owned exact row id.
    let selectedRowID: String?
    /// The owner's caption under the card; nil draws none.
    var caption: String? = nil
    let copy: AflMatchPeriodCopy10868
}

/// The owner's mark weight for a scoring play (a goal or a behind, in the
/// owner's grammar); never inferred from points.
nonisolated enum AflMatchPlayMark10868: Equatable {
    case major
    case minor
}

/// One owner scoring play. Its x is its position in the owner's order.
nonisolated struct AflMatchScoringPlay10868: Equatable {
    let id: String
    /// Signed actual lead after the play on the owner's scale; geometry only.
    /// Nil or off the scale draws no mark and breaks the step line.
    let lead: Double?
    /// The leading team's colour; nil draws the neutral colour.
    let leader: FieldChooserOriginalRef10868?
    let mark: AflMatchPlayMark10868
    /// The owner's period words.
    let period: String
    /// The source's own within-period clock words; never an absolute time.
    let clock: String
    /// The owner's scorer and play words.
    let scorer: String
    /// Each team's whole score after the play, in the owner's order.
    let scores: [AflMatchTeamScore10868]
    /// The owner's words for the lead after the play.
    let leadWords: String
    let spoken: String
}

/// The owner's guide at the first play of a period.
nonisolated struct AflMatchScoringGuide10868: Equatable {
    let playID: String
    let label: String
}

/// One owner checkpoint: a named play the reader can jump to.
nonisolated struct AflMatchScoringCheckpoint10868: Equatable {
    let id: String
    let playID: String
    let label: String
    let detail: String?
}

nonisolated struct AflMatchScoringCopy10868: Equatable {
    let eyebrow: String?
    let title: String
    /// The x axis's own words: plays in order, not time.
    let orderLabel: String
    /// Spoken name of the plot.
    let graphicLabel: String
    /// A note under the plot; nil draws none.
    let axisNote: String?
    let playsEmpty: String
    let selectionPrompt: String?
    let selectionMissing: String
    let selectHint: String?
    let earlierLabel: String
    let laterLabel: String
    /// Spoken name of the checkpoints group.
    let checkpointsLabel: String
    /// The chance links' heading; nil draws none.
    let chancesLabel: String?
    /// The quarters link; nil draws none.
    let periodsLabel: String?
    /// The card's Details control; nil draws none.
    let detailsLabel: String?
    let expandLabel: String
}

nonisolated struct AflMatchScoringStory10868: Equatable {
    /// The owner's plays in the owner's order; never sorted or filtered here.
    let plays: [AflMatchScoringPlay10868]
    /// The owner's signed actual-points axis.
    let scale: AussieRulesPointsScale10868
    let guides: [AflMatchScoringGuide10868]
    let checkpoints: [AflMatchScoringCheckpoint10868]
    /// Host-owned exact play id.
    let selectedPlayID: String?
    let plotHeight: CGFloat
    var readerPlotHeight: CGFloat? = nil
    let copy: AflMatchScoringCopy10868
}

// MARK: - Page input

/// The owner's link from a stream card id to a page card.
nonisolated struct AflMatchEventPageStory10868: Equatable {
    let cardID: String
    let card: AflMatchEventPageCard10868
    var reason: String? = nil
}

nonisolated struct AflMatchEventPageCopy10868: Equatable {
    let storiesLabel: String
    let storyUnavailable: String
    let headlineUnavailable: String
    let allPropsLabel: String?
    let heldOriginalUnavailable: String
    let backLabel: String
    let doneLabel: String
    let previousLabel: String
    let nextLabel: String
    let historyName: String
    let scoringName: String
    let periodsName: String
    /// Spoken name of the paired comparison; nil reuses `historyName`.
    var comparisonLabel: String? = nil
}

struct AflMatchEventPageInput10868: Equatable {
    let phase: AflMatchEventPagePhase10868
    let reader: AussieRulesEventPageReaderHeader10868
    let headline: FieldHeadlineInput10868
    var notice: String? = nil
    let history: FieldHistoryInput10868
    var readerPlotHeight: CGFloat? = nil
    var scoring: AflMatchScoringStory10868? = nil
    var periods: AflMatchPeriodStory10868? = nil
    /// The final chance-to-result input, shared by the quarter story's leaf
    /// and the scoring story's chance links.
    var chance: HistoricalChanceInput10868? = nil
    var stream: StoryStreamPresentation10868? = nil
    var stories: [AflMatchEventPageStory10868] = []
    var about: AussieRulesEventPageAbout10868? = nil
    let copy: AflMatchEventPageCopy10868
}

nonisolated enum AflMatchEventPageAccessibilityID10868 {
    static let page = "aflMatchEventPage10868.page"
    static let hero = "aflMatchEventPage10868.hero"
    static let headlineUnavailable = "aflMatchEventPage10868.headline.unavailable"
    static let notice = "aflMatchEventPage10868.notice"
    static let anchor = "aflMatchEventPage10868.anchor"
    static let stories = "aflMatchEventPage10868.stories"
    static let storyUnavailable = "aflMatchEventPage10868.story.unavailable"
    static let periods = "aflMatchEventPage10868.periods"
    static let periodRows = "aflMatchEventPage10868.periods.rows"
    static let periodReadout = "aflMatchEventPage10868.periods.readout"
    static let scoring = "aflMatchEventPage10868.scoring"
    static let scoringPlot = "aflMatchEventPage10868.scoring.plot"
    static let scoringReadout = "aflMatchEventPage10868.scoring.readout"
    static let scoringEarlier = "aflMatchEventPage10868.scoring.earlier"
    static let scoringLater = "aflMatchEventPage10868.scoring.later"
    static let checkpoints = "aflMatchEventPage10868.scoring.checkpoints"
    static let chances = "aflMatchEventPage10868.scoring.chances"
    static let originals = "aflMatchEventPage10868.originals"
    static let heldUnavailable = "aflMatchEventPage10868.originals.heldUnavailable"
    static let allProps = "aflMatchEventPage10868.allProps"
    static let readerHeader = "aflMatchEventPage10868.readerHeader"
    static let readerAbout = "aflMatchEventPage10868.readerHeader.about"
    static let readerBack = "aflMatchEventPage10868.reader.back"
    static let readerPrevious = "aflMatchEventPage10868.reader.previous"
    static let readerNext = "aflMatchEventPage10868.reader.next"
    static let done = "aflMatchEventPage10868.done"
    static let catalogue = "aflMatchEventPage10868.catalogue"
    static let original = "aflMatchEventPage10868.original"
    static let about = "aflMatchEventPage10868.about"
    static func card(_ card: AflMatchEventPageCard10868) -> String { "aflMatchEventPage10868.card.\(card.rawValue)" }
    static func expand(_ card: AflMatchEventPageCard10868) -> String { "aflMatchEventPage10868.expand.\(card.rawValue)" }
    static func details(_ card: AflMatchEventPageCard10868) -> String { "aflMatchEventPage10868.details.\(card.rawValue)" }
    static func periodRow(_ id: String) -> String { "aflMatchEventPage10868.periods.row.\(id)" }
    static func checkpoint(_ id: String) -> String { "aflMatchEventPage10868.scoring.checkpoint.\(id)" }
    static func chance(_ kind: HistoricalChanceEndpointKind10868) -> String {
        "aflMatchEventPage10868.scoring.chance.\(kind == .before ? "before" : "checkpoint")"
    }
}

// MARK: - Shared rules

/// What a card shows for its held row.
nonisolated enum AflMatchSelection10868<Row: Equatable>: Equatable {
    /// Nothing held: the owner's prompt, or nothing.
    case unheld(prompt: String?)
    /// The exact held row at its position in the owner's order.
    case row(Row, index: Int)
    /// The held id names no single row, in the owner's words. Never a neighbour.
    case missing(String)
}

/// One team's colour and key in a card, from the page's own headline.
nonisolated struct AflMatchTeamStyle10868: Equatable {
    let accent: Color?
    let shape: FieldHeadlineKeyShape10868?
}

/// Rules both actual-points cards share. Callable from any isolation.
nonisolated enum AflMatchCardRules10868 {
    /// An id hands back only when readable and unique among the owner's ids.
    static func selectableID(_ id: String, among ids: [String]) -> String? {
        guard AussieRulesEventPageWords10868.readable(id) != nil, ids.filter({ $0 == id }).count == 1 else { return nil }
        return id
    }

    /// The held id's exact row, or the owner's words. Never the first, the
    /// latest or a neighbour.
    static func selection<Row: Equatable>(_ held: String?, rows: [Row], id: (Row) -> String,
                                          prompt: String?, missing: String) -> AflMatchSelection10868<Row> {
        guard let held else { return .unheld(prompt: AussieRulesEventPageWords10868.readable(prompt)) }
        let indices = rows.indices.filter { id(rows[$0]) == held }
        guard AussieRulesEventPageWords10868.readable(held) != nil, indices.count == 1, let index = indices.first else {
            return .missing(missing)
        }
        return .row(rows[index], index: index)
    }

    /// The team's colour from its one original in the headline catalogue and
    /// its key from its one displayed slot; neutral otherwise.
    static func style(_ ref: FieldChooserOriginalRef10868?, headline: FieldHeadlineInput10868?) -> AflMatchTeamStyle10868 {
        guard let ref, let headline else { return AflMatchTeamStyle10868(accent: nil, shape: nil) }
        let originals = headline.catalogue.filter { $0.ref == ref }
        guard originals.count == 1 else { return AflMatchTeamStyle10868(accent: nil, shape: nil) }
        let slots = headline.displayed.filter { $0.ref == ref }
        return AflMatchTeamStyle10868(accent: originals[0].accent, shape: slots.count == 1 ? slots[0].keyShape : nil)
    }
}

// MARK: - Quarter story model

/// One quarter bar as the card draws it.
nonisolated struct AflMatchPeriodBar10868: Equatable {
    let row: AflMatchPeriodRow10868
    let plan: AussieRulesLeadBar10868
    let style: AflMatchTeamStyle10868
    let selectableID: String?
    let isSelected: Bool
}

nonisolated struct AflMatchPeriodModel10868: Equatable {
    let story: AflMatchPeriodStory10868
    /// The page's headline at its phase, for team colours only.
    let headline: FieldHeadlineInput10868?

    var copy: AflMatchPeriodCopy10868 { story.copy }

    /// Every owner row in the owner's order, each with its own bar on the owner's axis.
    var bars: [AflMatchPeriodBar10868] {
        let ids = story.rows.map(\.id)
        return story.rows.map { row in
            let selectable = AflMatchCardRules10868.selectableID(row.id, among: ids)
            return AflMatchPeriodBar10868(
                row: row,
                plan: AussieRulesResultStoryGeometry10868.bar(row.lead, in: story.scale),
                style: AflMatchCardRules10868.style(row.leader, headline: headline),
                selectableID: selectable,
                isSelected: selectable != nil && selectable == story.selectedRowID)
        }
    }

    var selection: AflMatchSelection10868<AflMatchPeriodRow10868> {
        AflMatchCardRules10868.selection(story.selectedRowID, rows: story.rows, id: { $0.id },
                                         prompt: copy.selectionPrompt, missing: copy.selectionMissing)
    }

    /// The owner's words under a bar that draws nothing.
    func barWords(_ bar: AflMatchPeriodBar10868) -> String? {
        switch bar.plan {
        case .bar, .level: return nil
        case .offScale: return copy.offScale
        case .unavailable: return copy.leadUnavailable
        }
    }

    var ticks: [(fraction: Double, label: String)] { AussieRulesResultStoryGeometry10868.ticks(story.scale) }

    var zero: Double? { AussieRulesResultStoryGeometry10868.zero(story.scale) }

    func scoreStyle(_ score: AflMatchTeamScore10868) -> AflMatchTeamStyle10868 {
        AflMatchCardRules10868.style(score.ref, headline: headline)
    }

    /// The only way a bar acts: the host's callback with the bar's own exact id.
    static func selectAction(_ bar: AflMatchPeriodBar10868, onSelect: ((String) -> Void)?) -> (() -> Void)? {
        guard let onSelect, let id = bar.selectableID else { return nil }
        return { onSelect(id) }
    }
}

// MARK: - Scoring story geometry and model

/// One point of the step line, as fractions of the plot (x from the first
/// play, y from the axis's lower end).
nonisolated struct AflMatchStepPoint10868: Equatable {
    let x: Double
    let y: Double
}

/// One held step's area between the zero line and its lead.
nonisolated struct AflMatchStepFill10868: Equatable {
    let from: Double
    let to: Double
    let y: Double
    let accent: Color?
}

/// One owner play placed on the plot.
nonisolated struct AflMatchPlayPlacement10868: Equatable {
    let index: Int
    let play: AflMatchScoringPlay10868
    /// Its position in the owner's order as a fraction of the plot width.
    let x: Double
    /// Its lead on the owner's axis; nil when missing, invalid or off the axis.
    let y: Double?
    let accent: Color?
    let selectableID: String?
    let isSelected: Bool
}

/// A placed guide at the owner's first play of a period.
nonisolated struct AflMatchPlacedGuide10868: Equatable {
    let x: Double
    let label: String
}

/// One owner checkpoint as the card shows it.
nonisolated struct AflMatchPlacedCheckpoint10868: Equatable {
    let checkpoint: AflMatchScoringCheckpoint10868
    /// The exact play id it hands back; nil when its play is not exactly one owner play.
    let playID: String?
    let isSelected: Bool
}

/// Pure rules the scoring plot draws from. Unit-tested without rendering.
nonisolated enum AflMatchScoringGeometry10868 {
    /// The play's place in the owner's order as a fraction of the width: the
    /// first at the leading edge and the last at the trailing edge; a single
    /// play at the centre. Order only, never time.
    static func x(index: Int, count: Int) -> Double? {
        guard count > 0, index >= 0, index < count else { return nil }
        return count == 1 ? 0.5 : Double(index) / Double(count - 1)
    }

    /// The position nearest a horizontal fraction, for a tap.
    static func index(atFraction fraction: Double, count: Int) -> Int? {
        guard count > 0, fraction.isFinite else { return nil }
        guard count > 1 else { return 0 }
        let raw = (fraction * Double(count - 1)).rounded()
        return Int(min(max(raw, 0), Double(count - 1)))
    }

    /// The plot frame inside the drawing, leaving the tick gutter on the
    /// leading side and room above and below; nil when nothing can be drawn.
    static func plotFrame(in size: CGSize, gutter: CGFloat, room: CGFloat) -> CGRect? {
        guard size.width.isFinite, size.height.isFinite, gutter.isFinite, room.isFinite, gutter >= 0, room >= 0,
              size.width > gutter + room, size.height > room * 2 else { return nil }
        return CGRect(x: gutter, y: room, width: size.width - gutter - room, height: size.height - room * 2)
    }

    /// The step line's runs: each placed play holds its lead until the next
    /// placed play; a play that cannot be placed breaks the line.
    static func segments(_ placements: [AflMatchPlayPlacement10868]) -> [[AflMatchStepPoint10868]] {
        var runs: [[AflMatchStepPoint10868]] = []
        var previous: AflMatchStepPoint10868?
        for placement in placements {
            guard let y = placement.y else {
                previous = nil
                continue
            }
            let point = AflMatchStepPoint10868(x: placement.x, y: y)
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

    /// Each held step's area, coloured by that play's own leader.
    static func fills(_ placements: [AflMatchPlayPlacement10868]) -> [AflMatchStepFill10868] {
        guard placements.count > 1 else { return [] }
        return (0..<(placements.count - 1)).compactMap { index in
            let here = placements[index], next = placements[index + 1]
            guard let y = here.y, next.y != nil else { return nil }
            return AflMatchStepFill10868(from: here.x, to: next.x, y: y, accent: here.accent)
        }
    }
}

nonisolated struct AflMatchScoringModel10868: Equatable {
    let story: AflMatchScoringStory10868
    /// The page's headline at its phase, for team colours only.
    let headline: FieldHeadlineInput10868?
    /// The page's chance-to-result input, for the two dated chance links.
    let chance: HistoricalChanceInput10868?

    var copy: AflMatchScoringCopy10868 { story.copy }

    private var ids: [String] { story.plays.map(\.id) }

    /// Every owner play in the owner's order at its own position.
    var placements: [AflMatchPlayPlacement10868] {
        let ids = self.ids
        let selected = selectedID
        return story.plays.enumerated().compactMap { index, play in
            guard let x = AflMatchScoringGeometry10868.x(index: index, count: story.plays.count) else { return nil }
            let selectable = AflMatchCardRules10868.selectableID(play.id, among: ids)
            return AflMatchPlayPlacement10868(
                index: index, play: play, x: x,
                y: play.lead.flatMap { AussieRulesResultStoryGeometry10868.fraction($0, in: story.scale) },
                accent: AflMatchCardRules10868.style(play.leader, headline: headline).accent,
                selectableID: selectable,
                isSelected: selectable != nil && selectable == selected)
        }
    }

    var segments: [[AflMatchStepPoint10868]] { AflMatchScoringGeometry10868.segments(placements) }

    var fills: [AflMatchStepFill10868] { AflMatchScoringGeometry10868.fills(placements) }

    var selection: AflMatchSelection10868<AflMatchScoringPlay10868> {
        AflMatchCardRules10868.selection(story.selectedPlayID, rows: story.plays, id: { $0.id },
                                         prompt: copy.selectionPrompt, missing: copy.selectionMissing)
    }

    /// The held play's id while it is exactly one owner play.
    var selectedID: String? {
        if case .row(let play, _) = selection { return play.id }
        return nil
    }

    /// The play just before or after the held one in the owner's order, while
    /// that play has its own unique id. Nothing without an exact held play.
    func neighbour(_ offset: Int) -> String? {
        guard case .row(_, let index) = selection else { return nil }
        let target = index + offset
        guard story.plays.indices.contains(target) else { return nil }
        return AflMatchCardRules10868.selectableID(story.plays[target].id, among: ids)
    }

    var earlierID: String? { neighbour(-1) }

    var laterID: String? { neighbour(1) }

    /// The owner's guides whose play is exactly one owner play.
    var guides: [AflMatchPlacedGuide10868] {
        let ids = self.ids
        return story.guides.compactMap { guide in
            let indices = ids.indices.filter { ids[$0] == guide.playID }
            guard indices.count == 1, AussieRulesEventPageWords10868.readable(guide.label) != nil,
                  let x = AflMatchScoringGeometry10868.x(index: indices[0], count: ids.count) else { return nil }
            return AflMatchPlacedGuide10868(x: x, label: guide.label)
        }
    }

    var checkpoints: [AflMatchPlacedCheckpoint10868] {
        let ids = self.ids
        let selected = selectedID
        return story.checkpoints.map { checkpoint in
            let id = AflMatchCardRules10868.selectableID(checkpoint.playID, among: ids)
            return AflMatchPlacedCheckpoint10868(checkpoint: checkpoint, playID: id, isSelected: id != nil && id == selected)
        }
    }

    var ticks: [(fraction: Double, label: String)] { AussieRulesResultStoryGeometry10868.ticks(story.scale) }

    var zero: Double? { AussieRulesResultStoryGeometry10868.zero(story.scale) }

    func scoreStyle(_ score: AflMatchTeamScore10868) -> AflMatchTeamStyle10868 {
        AflMatchCardRules10868.style(score.ref, headline: headline)
    }

    /// The tapped position's play id, while it is selectable.
    func playID(atFraction fraction: Double) -> String? {
        guard let index = AflMatchScoringGeometry10868.index(atFraction: fraction, count: story.plays.count) else { return nil }
        return AflMatchCardRules10868.selectableID(story.plays[index].id, among: ids)
    }

    /// The subject's two chance slots from the same chance-to-result input:
    /// each labelled, with its own clock, or its words. Nothing before the final.
    var chanceModel: HistoricalChanceModel10868? { chance.map { HistoricalChanceModel10868($0) } }
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
struct AflMatchEventPageModel10868: Equatable {
    let input: AflMatchEventPageInput10868

    init(_ input: AflMatchEventPageInput10868) {
        self.input = input
    }

    static func headlinePhase(_ phase: AflMatchEventPagePhase10868) -> FieldOutlookPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == Self.headlinePhase(input.phase) ? input.headline : nil
    }

    var isFinal: Bool { input.phase == .final }

    /// The actual-points stories and the chance-to-result input at the final only.
    var scoring: AflMatchScoringStory10868? { isFinal ? input.scoring : nil }

    var periods: AflMatchPeriodStory10868? { isFinal ? input.periods : nil }

    var chance: HistoricalChanceInput10868? { isFinal ? input.chance : nil }

    var scoringModel: AflMatchScoringModel10868? {
        scoring.map { AflMatchScoringModel10868(story: $0, headline: headline, chance: chance) }
    }

    var periodModel: AflMatchPeriodModel10868? {
        periods.map { AflMatchPeriodModel10868(story: $0, headline: headline) }
    }

    func isMounted(_ card: AflMatchEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .scoring: scoring != nil
        case .periods: periods != nil
        }
    }

    /// The mounted cards in the page's order.
    var mountedCards: [AflMatchEventPageCard10868] {
        AflMatchEventPageCard10868.allCases.filter(isMounted)
    }

    /// The mounted card just before or after `card`; nothing past either end
    /// or for a card this phase does not mount.
    func neighbour(of card: AflMatchEventPageCard10868, offset: Int) -> AflMatchEventPageCard10868? {
        let cards = mountedCards
        guard let index = cards.firstIndex(of: card), cards.indices.contains(index + offset) else { return nil }
        return cards[index + offset]
    }

    func cardName(_ card: AflMatchEventPageCard10868) -> String {
        switch card {
        case .history: input.copy.historyName
        case .scoring: input.copy.scoringName
        case .periods: input.copy.periodsName
        }
    }

    /// The owner's link a stream card id names: exactly one link with that id,
    /// to a story card this phase mounts. Otherwise nothing.
    func storyLink(_ cardID: String) -> AflMatchEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    /// Without a stream the mounted cards sit directly on the page.
    var showsCardsDirectly: Bool { input.stream == nil }

    func readerShows(_ card: AflMatchEventPageCard10868) -> Bool { isMounted(card) }

    /// Whether the comparison stands in for the shared key: only while the key
    /// would show nothing but the readouts the comparison shows — no original's
    /// choose control and no owner key context. Otherwise the owner's key stays.
    var hidesSharedKey: Bool {
        input.history.series.allSatisfy { $0.choose == nil && FieldHistoryGeometry10868.keyContext($0) == nil }
    }

    /// A presentation copy of the owner's history: every series, run, reading,
    /// key word, action, window, scale and inspection exactly as supplied, with
    /// only the given height, expand control and key visibility. The owner's
    /// input is never changed.
    static func presentationCopy(_ history: FieldHistoryInput10868, plotHeight: CGFloat,
                                 expand: FieldHistoryAction10868?, showsKey: Bool) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: plotHeight,
            unboundReadingWords: history.unboundReadingWords, plotUnavailableWords: history.plotUnavailableWords,
            windows: history.windows, scale: history.scale, moreOriginals: history.moreOriginals,
            details: history.details, expand: expand, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: history.inspection,
            layout: history.layout,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: showsKey
        )
    }

    /// The key's visibility in both history copies.
    private var presentedKey: Bool { hidesSharedKey ? false : input.history.showsKey }

    /// The history on the page: the owner's input with the duplicate key
    /// hidden. The anchor and the comparison above it both read this copy.
    var presentedHistory: FieldHistoryInput10868 {
        let history = input.history
        return Self.presentationCopy(history, plotHeight: history.plotHeight, expand: history.expand, showsKey: presentedKey)
    }

    /// The full-size history: the same input without its expand control, at
    /// the owner's full-size height while usable and never shorter than
    /// inline (any other height keeps the inline one), with the page's key
    /// visibility. The full-size history and its comparison both read this copy.
    var readerHistory: FieldHistoryInput10868 {
        let history = input.history
        return Self.presentationCopy(
            history, plotHeight: RugbyMatchEventPageModel10868.readerPlotHeight(input.readerPlotHeight, history: history.plotHeight),
            expand: nil, showsKey: presentedKey)
    }

    /// The comparison's spoken name: the owner's own label, else its history name.
    var comparisonLabel: String {
        Self.readable(input.copy.comparisonLabel) ?? input.copy.historyName
    }

    /// The full-size scoring story: the same story at the owner's full-size
    /// height while usable, never shorter than inline; any other height keeps
    /// the inline one.
    var readerScoringModel: AflMatchScoringModel10868? {
        guard let shown = scoring else { return nil }
        let full = AflMatchScoringStory10868(
            plays: shown.plays, scale: shown.scale, guides: shown.guides, checkpoints: shown.checkpoints,
            selectedPlayID: shown.selectedPlayID,
            plotHeight: RugbyMatchEventPageModel10868.readerPlotHeight(shown.readerPlotHeight, history: shown.plotHeight),
            readerPlotHeight: shown.readerPlotHeight, copy: shown.copy)
        return AflMatchScoringModel10868(story: full, headline: headline, chance: chance)
    }

    // MARK: Originals

    /// The owner holds a selection that opens nothing in this update. It stays
    /// the owner's; it is shown as unavailable, never replaced.
    static func heldOriginalIsUnavailable(_ originals: AussieRulesEventPageOriginals10868?) -> Bool {
        guard let originals, originals.selection != nil else { return false }
        return OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: originals.selection) == nil
    }

    // MARK: About and entries

    var about: AussieRulesEventPageAbout10868? {
        guard let about = input.about,
              Self.readable(about.title) != nil || about.sections.contains(where: AussieRulesEventPageModel10868.hasWords)
        else { return nil }
        return about
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil
    }

    /// Full-size content's compact heading shows the About entry; the page has
    /// the headline's own control.
    func aboutEntry(mode: AflMatchEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode, Self.readable(input.headline.copy.aboutLabel) != nil else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && Self.readable(input.copy.allPropsLabel) != nil
    }

    static func readable(_ words: String?) -> String? {
        AussieRulesEventPageWords10868.readable(words)
    }

    // MARK: Layout and reading order

    /// Accessibility sizes and a compact width stack; a regular or unspecified
    /// width tries the headline beside the history, then stacks.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [AflMatchEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }

    /// A card's readout and chance links side by side while they fit; stacked
    /// straight away at accessibility sizes.
    static func readoutArrangements(accessibilitySize: Bool) -> [AflMatchEventPageArrangement10868] {
        accessibilitySize ? [.stacked] : [.sideBySide, .stacked]
    }

    static let readingOrder: [AflMatchEventPageBlock10868] = [.headline, .notice, .anchor, .cards, .originals, .allProps]

    /// VoiceOver reads the same order in every arrangement.
    static func sortPriority(_ block: AflMatchEventPageBlock10868) -> Double {
        Double(readingOrder.count - (readingOrder.firstIndex(of: block) ?? readingOrder.count))
    }
}

// MARK: - Shared drawing pieces

/// The reference's white card on the page surface.
private struct AflMatchCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}

/// The headline's own key shape in the team's colour.
private struct AflMatchIdentityKey10868: View {
    let shape: FieldHeadlineKeyShape10868
    let accent: Color
    var hollow: Bool = false

    @ScaledMetric(relativeTo: .caption) private var diameter: CGFloat = 10

    var body: some View {
        let diameter = self.diameter
        let side = FieldHeadlineGeometry10868.keyFrameSide(diameter: diameter) ?? 0
        let ringFill = DS.cardBg
        let accent = self.accent
        let shape = self.shape
        let hollow = self.hollow
        return Canvas { context, size in
            guard let plan = FieldHeadlineGeometry10868.keyPlan(shape, hollow: hollow, in: size, diameter: diameter, lineWidth: 2) else { return }
            if let stroke = plan.stroke {
                context.fill(plan.fill, with: .color(ringFill))
                context.stroke(stroke, with: .color(accent), lineWidth: plan.lineWidth)
            } else {
                context.fill(plan.fill, with: .color(accent))
            }
        }
        .frame(width: side, height: side)
        .accessibilityHidden(true)
    }
}

/// A card's header: the owner's eyebrow and title, and the full-card entry
/// only with a callback.
private struct AflMatchCardHeader10868: View {
    let eyebrow: String?
    let title: String
    let expandLabel: String
    let expandID: String
    var onExpand: (() -> Void)?

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                if let eyebrow = AussieRulesEventPageWords10868.readable(eyebrow) {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let title = AussieRulesEventPageWords10868.readable(title) {
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

/// The owner's whole score per team, each in its team's colour at one size.
private struct AflMatchScoreLine10868: View {
    let scores: [AflMatchTeamScore10868]
    let style: (AflMatchTeamScore10868) -> AflMatchTeamStyle10868

    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 27

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                ForEach(Array(scores.enumerated()), id: \.offset) { index, score in
                    if index > 0 {
                        Text("–")
                            .font(.system(size: figureSize * 0.7, weight: .regular))
                            .foregroundStyle(DS.textSecondary)
                            .accessibilityHidden(true)
                    }
                    Text(score.score)
                        .font(.system(size: figureSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(style(score).accent ?? DS.textPrimary)
                        .fixedSize()
                }
            }
            HStack(spacing: 10) {
                ForEach(Array(scores.enumerated()), id: \.offset) { _, score in
                    HStack(spacing: 4) {
                        let team = style(score)
                        if let shape = team.shape, let accent = team.accent {
                            AflMatchIdentityKey10868(shape: shape, accent: accent)
                        }
                        Text(score.name)
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }
}

/// A text control in the reference's link style; static words without a callback.
private struct AflMatchLink10868: View {
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

private func aflMatchOwnerWords(_ words: String) -> some View {
    Text(words)
        .font(.caption)
        .foregroundStyle(DS.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
}

// MARK: - Quarter story card

/// The actual margin at each owner quarter row on one signed axis, the held
/// row's whole score, then the chance-to-result leaf. Every word and number is
/// the owner's; it keeps no state.
struct AflMatchPeriodCard10868: View {
    let model: AflMatchPeriodModel10868
    /// The page's chance-to-result input; the leaf draws only at the final.
    var chance: HistoricalChanceInput10868? = nil
    var onExpand: (() -> Void)? = nil
    /// A row's exact id, for the host to hold. Never moves the probability cursor.
    var onSelect: ((String) -> Void)? = nil
    /// A chance figure's exact original and observation key, for the host's history.
    var onChanceOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onDetails: (() -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @ScaledMetric(relativeTo: .body) private var trackHeight: CGFloat = 22

    private typealias Geometry = AussieRulesResultStoryGeometry10868

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            AflMatchCardHeader10868(eyebrow: model.copy.eyebrow, title: model.copy.title,
                                    expandLabel: model.copy.expandLabel,
                                    expandID: AflMatchEventPageAccessibilityID10868.expand(.periods),
                                    onExpand: onExpand)
            axisWords
            rows
            readout
            if let chance {
                HistoricalChanceResultPresentation10868(input: chance, onOpen: onChanceOpen)
            }
            if let caption = AussieRulesEventPageWords10868.readable(model.story.caption) {
                Text(caption)
                    .font(.callout)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let label = AussieRulesEventPageWords10868.readable(model.copy.detailsLabel) {
                AflMatchLink10868(label: label, id: AflMatchEventPageAccessibilityID10868.details(.periods), action: onDetails)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.periods)
    }

    /// The axis's own label and who leads on each side.
    private var axisWords: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let label = AussieRulesEventPageWords10868.readable(model.story.scale.label) {
                Text(label)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline) {
                    lowerWords
                    Spacer(minLength: 12)
                    upperWords
                }
                VStack(alignment: .leading, spacing: 2) {
                    upperWords
                    lowerWords
                }
            }
        }
    }

    @ViewBuilder private var lowerWords: some View {
        if let lower = AussieRulesEventPageWords10868.readable(model.story.scale.lowerWords) {
            aflMatchOwnerWords("← \(lower)")
        }
    }

    @ViewBuilder private var upperWords: some View {
        if let upper = AussieRulesEventPageWords10868.readable(model.story.scale.upperWords) {
            aflMatchOwnerWords("\(upper) →")
        }
    }

    /// One full-width row per owner row on the same signed axis, then the ticks.
    @ViewBuilder private var rows: some View {
        let bars = model.bars
        if bars.isEmpty {
            aflMatchOwnerWords(model.copy.rowsEmpty)
        } else {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(bars.enumerated()), id: \.offset) { _, bar in
                    rowControl(bar) {
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                if let shape = bar.style.shape, let accent = bar.style.accent {
                                    AflMatchIdentityKey10868(shape: shape, accent: accent)
                                }
                                Text(bar.row.label)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(DS.textPrimary)
                                    .fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 8)
                                Text(bar.row.leadWords)
                                    .font(.headline)
                                    .monospacedDigit()
                                    .foregroundStyle(DS.textPrimary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            barArea(bar)
                                .frame(height: trackHeight)
                            if let words = model.barWords(bar) {
                                aflMatchOwnerWords(words)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                ticksBelow
                    .frame(height: trackHeight)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(model.copy.graphicLabel)
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.periodRows)
        }
    }

    private func barArea(_ bar: AflMatchPeriodBar10868) -> some View {
        let ticks = model.ticks
        let zero = model.zero
        let tint = (bar.style.accent ?? DS.textSecondary).opacity(bar.isSelected ? 1 : 0.65)
        let gridColor = DS.border
        let zeroColor = DS.textSecondary
        let plan = bar.plan
        return Canvas { context, size in
            guard size.width > 0, size.height > 0 else { return }
            let frame = CGRect(origin: .zero, size: size)
            for tick in ticks {
                var line = Path()
                let x = Geometry.x(tick.fraction, in: frame)
                line.move(to: CGPoint(x: x, y: 0))
                line.addLine(to: CGPoint(x: x, y: size.height))
                context.stroke(line, with: .color(gridColor), lineWidth: 1)
            }
            if let zero {
                var line = Path()
                let x = Geometry.x(zero, in: frame)
                line.move(to: CGPoint(x: x, y: 0))
                line.addLine(to: CGPoint(x: x, y: size.height))
                context.stroke(line, with: .color(zeroColor), lineWidth: 1.5)
            }
            if let rect = Geometry.horizontalBar(plan, in: frame, thickness: size.height * 0.8) {
                context.fill(Path(roundedRect: rect, cornerRadius: 4), with: .color(tint))
            }
        }
        .accessibilityHidden(true)
    }

    private var ticksBelow: some View {
        let ticks = model.ticks
        let labelColor = DS.textSecondary
        return Canvas { context, size in
            guard size.width > 0 else { return }
            let frame = CGRect(origin: .zero, size: size)
            for tick in ticks {
                var text = context.resolve(Text(tick.label).font(.caption2))
                text.shading = .color(labelColor)
                let x = Geometry.x(tick.fraction, in: frame)
                let anchor: UnitPoint = tick.fraction <= 0 ? .leading : (tick.fraction >= 1 ? .trailing : .center)
                context.draw(text, at: CGPoint(x: x, y: size.height / 2), anchor: anchor)
            }
        }
        .accessibilityHidden(true)
    }

    /// A row that hands back its exact id with a callback; static content otherwise.
    @ViewBuilder private func rowControl<Content: View>(_ bar: AflMatchPeriodBar10868,
                                                       @ViewBuilder content: () -> Content) -> some View {
        let outline = bar.isSelected ? (bar.style.accent ?? DS.textPrimary) : Color.clear
        if let action = AflMatchPeriodModel10868.selectAction(bar, onSelect: onSelect) {
            Button(action: action) {
                content()
                    .padding(.vertical, 6)
                    .padding(.horizontal, 8)
                    .frame(minHeight: controlSize)
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(outline, lineWidth: 2))
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(bar.row.spoken)
            .accessibilityHint(model.copy.selectHint ?? "")
            .accessibilityAddTraits(bar.isSelected ? .isSelected : [])
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.periodRow(bar.row.id))
        } else {
            content()
                .padding(.vertical, 6)
                .padding(.horizontal, 8)
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(outline, lineWidth: 2))
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(bar.row.spoken)
                .accessibilityAddTraits(bar.isSelected ? .isSelected : [])
                .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.periodRow(bar.row.id))
        }
    }

    /// The held row's label and whole score per team, or the owner's words.
    @ViewBuilder private var readout: some View {
        switch model.selection {
        case .row(let row, _):
            VStack(alignment: .leading, spacing: 6) {
                Text(row.scoreLabel)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                AflMatchScoreLine10868(scores: row.scores, style: model.scoreStyle)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(row.spoken)
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.periodReadout)
        case .missing(let words):
            aflMatchOwnerWords(words)
                .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.periodReadout)
        case .unheld(let prompt):
            if let prompt {
                aflMatchOwnerWords(prompt)
                    .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.periodReadout)
            }
        }
    }
}

// MARK: - Scoring story card

/// Every owner scoring play's actual lead in the owner's order, the held play,
/// earlier and later controls, the owner's checkpoints and the subject's two
/// dated chance links. Every word and number is the owner's; it keeps no state.
struct AflMatchScoringCard10868: View {
    let model: AflMatchScoringModel10868
    var onExpand: (() -> Void)? = nil
    /// A play's exact id, for the host to hold. Never moves the probability cursor.
    var onSelect: ((String) -> Void)? = nil
    /// A chance link's exact original and observation key, for the host's history.
    var onChanceOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onPeriods: (() -> Void)? = nil
    var onDetails: (() -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @ScaledMetric(relativeTo: .caption) private var gutter: CGFloat = 44
    @ScaledMetric(relativeTo: .caption) private var room: CGFloat = 10
    @ScaledMetric(relativeTo: .caption) private var majorRadius: CGFloat = 2.5
    @ScaledMetric(relativeTo: .caption) private var minorRadius: CGFloat = 1.5
    @ScaledMetric(relativeTo: .caption) private var selectedRadius: CGFloat = 5
    @ScaledMetric(relativeTo: .title) private var chanceSize: CGFloat = 25
    @ScaledMetric(relativeTo: .caption) private var guideHeight: CGFloat = 22

    private typealias Geometry = AussieRulesResultStoryGeometry10868

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            AflMatchCardHeader10868(eyebrow: model.copy.eyebrow, title: model.copy.title,
                                    expandLabel: model.copy.expandLabel,
                                    expandID: AflMatchEventPageAccessibilityID10868.expand(.scoring),
                                    onExpand: onExpand)
            readout
            axisWords
            if model.story.plays.isEmpty {
                aflMatchOwnerWords(model.copy.playsEmpty)
            } else {
                plot
                guideLabels
                    .frame(height: guideHeight)
                aflMatchOwnerWords(model.copy.orderLabel)
            }
            if let note = AussieRulesEventPageWords10868.readable(model.copy.axisNote) {
                aflMatchOwnerWords(note)
            }
            stepControls
            checkpoints
            chanceLinks
            if let label = AussieRulesEventPageWords10868.readable(model.copy.periodsLabel) {
                AflMatchLink10868(label: label, id: AflMatchEventPageAccessibilityID10868.card(.periods), action: onPeriods)
            }
            if let label = AussieRulesEventPageWords10868.readable(model.copy.detailsLabel) {
                AflMatchLink10868(label: label, id: AflMatchEventPageAccessibilityID10868.details(.scoring), action: onDetails)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.scoring)
    }

    // MARK: Readout

    /// The held play's period and clock, whole score, lead and scorer, or the owner's words.
    @ViewBuilder private var readout: some View {
        switch model.selection {
        case .row(let play, _):
            let arrangements = AflMatchEventPageModel10868.readoutArrangements(accessibilitySize: typeSize.isAccessibilitySize)
            Group {
                if arrangements == [.stacked] {
                    readoutStacked(play)
                } else {
                    ViewThatFits(in: .horizontal) {
                        readoutSideBySide(play)
                        readoutStacked(play)
                    }
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(play.spoken)
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.scoringReadout)
        case .missing(let words):
            aflMatchOwnerWords(words)
                .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.scoringReadout)
        case .unheld(let prompt):
            if let prompt {
                aflMatchOwnerWords(prompt)
                    .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.scoringReadout)
            }
        }
    }

    private func readoutSideBySide(_ play: AflMatchScoringPlay10868) -> some View {
        HStack(alignment: .top, spacing: 16) {
            playScore(play)
                .frame(maxWidth: .infinity, alignment: .leading)
            playWords(play, alignment: .trailing)
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
    }

    private func readoutStacked(_ play: AflMatchScoringPlay10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            playScore(play)
            playWords(play, alignment: .leading)
        }
    }

    private func playScore(_ play: AflMatchScoringPlay10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("\(play.period) · \(play.clock)")
                .font(.caption.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            AflMatchScoreLine10868(scores: play.scores, style: model.scoreStyle)
        }
    }

    private func playWords(_ play: AflMatchScoringPlay10868, alignment: HorizontalAlignment) -> some View {
        VStack(alignment: alignment, spacing: 4) {
            Text(play.leadWords)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            Text(play.scorer)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// The axis's own label and who leads above and below the zero line.
    private var axisWords: some View {
        VStack(alignment: .leading, spacing: 2) {
            if let label = AussieRulesEventPageWords10868.readable(model.story.scale.label) {
                Text(label)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let upper = AussieRulesEventPageWords10868.readable(model.story.scale.upperWords) {
                aflMatchOwnerWords("↑ \(upper)")
            }
            if let lower = AussieRulesEventPageWords10868.readable(model.story.scale.lowerWords) {
                aflMatchOwnerWords("↓ \(lower)")
            }
        }
    }

    // MARK: Plot

    /// The step plot: owner ticks in the gutter, a neutral zero, the held
    /// step's area in its leader's colour, the guides, the step line, one mark
    /// per placed play and the held play's line. A tap hands back the nearest
    /// selectable play's exact id; VoiceOver adjusts to the earlier or later play.
    private var plot: some View {
        let placements = model.placements
        let segments = model.segments
        let fills = model.fills
        let guides = model.guides
        let ticks = model.ticks
        let zero = model.zero
        let gutter = self.gutter
        let room = self.room
        let major = majorRadius
        let minor = minorRadius
        let selectedRadius = self.selectedRadius
        let lineColor = DS.textPrimary
        let gridColor = DS.border
        let zeroColor = DS.textSecondary
        let neutral = DS.textSecondary
        let labelColor = DS.textSecondary
        let ring = DS.cardBg
        let model = self.model
        let onSelect = self.onSelect
        return GeometryReader { proxy in
            let size = proxy.size
            Canvas { context, size in
                guard let frame = AflMatchScoringGeometry10868.plotFrame(in: size, gutter: gutter, room: room) else { return }
                func point(_ x: Double, _ y: Double) -> CGPoint {
                    CGPoint(x: Geometry.x(x, in: frame), y: Geometry.y(y, in: frame))
                }
                for tick in ticks {
                    var line = Path()
                    let y = Geometry.y(tick.fraction, in: frame)
                    line.move(to: CGPoint(x: frame.minX, y: y))
                    line.addLine(to: CGPoint(x: frame.maxX, y: y))
                    context.stroke(line, with: .color(gridColor), style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
                    var text = context.resolve(Text(tick.label).font(.caption2))
                    text.shading = .color(labelColor)
                    context.draw(text, at: CGPoint(x: frame.minX - 4, y: y), anchor: .trailing)
                }
                if let zero {
                    for fill in fills {
                        let left = Geometry.x(fill.from, in: frame), right = Geometry.x(fill.to, in: frame)
                        let top = Geometry.y(max(fill.y, zero), in: frame), bottom = Geometry.y(min(fill.y, zero), in: frame)
                        let rect = CGRect(x: left, y: top, width: max(right - left, 0), height: max(bottom - top, 0))
                        context.fill(Path(rect), with: .color((fill.accent ?? neutral).opacity(0.18)))
                    }
                    var line = Path()
                    let y = Geometry.y(zero, in: frame)
                    line.move(to: CGPoint(x: frame.minX, y: y))
                    line.addLine(to: CGPoint(x: frame.maxX, y: y))
                    context.stroke(line, with: .color(zeroColor), lineWidth: 1.5)
                }
                for guide in guides {
                    var line = Path()
                    let x = Geometry.x(guide.x, in: frame)
                    line.move(to: CGPoint(x: x, y: frame.minY))
                    line.addLine(to: CGPoint(x: x, y: frame.maxY))
                    context.stroke(line, with: .color(gridColor), style: StrokeStyle(lineWidth: 1, dash: [2, 4]))
                }
                for run in segments where run.count > 1 {
                    var path = Path()
                    path.move(to: point(run[0].x, run[0].y))
                    for step in run.dropFirst() {
                        path.addLine(to: point(step.x, step.y))
                    }
                    context.stroke(path, with: .color(lineColor), lineWidth: 2)
                }
                if let held = placements.first(where: \.isSelected) {
                    var line = Path()
                    let x = Geometry.x(held.x, in: frame)
                    line.move(to: CGPoint(x: x, y: frame.minY))
                    line.addLine(to: CGPoint(x: x, y: frame.maxY))
                    context.stroke(line, with: .color(zeroColor), style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
                }
                for placement in placements {
                    guard let y = placement.y else { continue }
                    let center = point(placement.x, y)
                    let radius = placement.isSelected ? selectedRadius : (placement.play.mark == .major ? major : minor)
                    let dot = Path(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius,
                                                     width: radius * 2, height: radius * 2))
                    context.fill(dot, with: .color(placement.accent ?? neutral))
                    if placement.isSelected {
                        context.stroke(dot, with: .color(ring), lineWidth: 2)
                    }
                }
            }
            .contentShape(Rectangle())
            .onTapGesture(coordinateSpace: .local) { location in
                guard let onSelect,
                      let frame = AflMatchScoringGeometry10868.plotFrame(in: size, gutter: gutter, room: room),
                      frame.width > 0,
                      let id = model.playID(atFraction: Double((location.x - frame.minX) / frame.width))
                else { return }
                onSelect(id)
            }
        }
        .frame(height: AussieRulesResultStoryGeometry10868.barHeight(model.story.plotHeight))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.copy.graphicLabel)
        .accessibilityValue(selectionWords)
        .accessibilityHint(model.copy.selectHint ?? "")
        .modifier(AflMatchAdjustable10868(earlier: adjust(model.earlierID), later: adjust(model.laterID)))
        .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.scoringPlot)
    }

    private var selectionWords: String {
        switch model.selection {
        case .row(let play, _): play.spoken
        case .missing(let words): words
        case .unheld(let prompt): prompt ?? ""
        }
    }

    private func adjust(_ id: String?) -> (() -> Void)? {
        guard let id, let onSelect else { return nil }
        return { onSelect(id) }
    }

    /// The owner's guide labels under their own plays.
    private var guideLabels: some View {
        let guides = model.guides
        let gutter = self.gutter
        let room = self.room
        let labelColor = DS.textSecondary
        return Canvas { context, size in
            guard let frame = AflMatchScoringGeometry10868.plotFrame(
                in: CGSize(width: size.width, height: max(size.height, room * 2 + 1)), gutter: gutter, room: room) else { return }
            for guide in guides {
                var text = context.resolve(Text(guide.label).font(.caption2.weight(.semibold)))
                text.shading = .color(labelColor)
                context.draw(text, at: CGPoint(x: Geometry.x(guide.x, in: frame), y: size.height / 2), anchor: .center)
            }
        }
        .accessibilityHidden(true)
    }

    // MARK: Controls

    /// Earlier and later plays in the owner's order: disabled without an exact held play or past either end.
    private var stepControls: some View {
        HStack(spacing: 8) {
            stepButton(model.copy.earlierLabel, target: model.earlierID, systemImage: "chevron.left",
                       id: AflMatchEventPageAccessibilityID10868.scoringEarlier)
            Spacer(minLength: 8)
            stepButton(model.copy.laterLabel, target: model.laterID, systemImage: "chevron.right",
                       id: AflMatchEventPageAccessibilityID10868.scoringLater)
        }
    }

    @ViewBuilder private func stepButton(_ label: String, target: String?, systemImage: String, id: String) -> some View {
        if let onSelect {
            Button {
                if let target { onSelect(target) }
            } label: {
                Label(label, systemImage: systemImage)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(target == nil ? DS.textSecondary : DS.blue)
                    .frame(minHeight: controlSize)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(target == nil)
            .accessibilityIdentifier(id)
        }
    }

    /// The owner's checkpoints, each handing back its exact play; one that
    /// names no single play keeps its words without a control.
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
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.checkpoints)
        }
    }

    @ViewBuilder private func checkpointControl(_ placed: AflMatchPlacedCheckpoint10868) -> some View {
        let content = VStack(alignment: .leading, spacing: 3) {
            Text(placed.checkpoint.label)
                .font(.caption.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
            if let detail = AussieRulesEventPageWords10868.readable(placed.checkpoint.detail) {
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
        if let onSelect, let id = placed.playID {
            Button { onSelect(id) } label: { content.foregroundStyle(placed.isSelected ? DS.blue : DS.textPrimary) }
                .buttonStyle(.plain)
                .accessibilityAddTraits(placed.isSelected ? .isSelected : [])
                .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.checkpoint(placed.checkpoint.id))
        } else {
            content
                .foregroundStyle(DS.textPrimary)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.checkpoint(placed.checkpoint.id))
        }
    }

    // MARK: Chance links

    /// The subject's two labelled chances, each with its own clock, from the
    /// page's chance-to-result input; a figure with its own key opens that exact
    /// original and key. An unavailable slot keeps its label and words and
    /// does not act.
    @ViewBuilder private var chanceLinks: some View {
        if let chance = model.chanceModel, chance.isShown {
            VStack(alignment: .leading, spacing: 8) {
                if let heading = AussieRulesEventPageWords10868.readable(model.copy.chancesLabel) {
                    Text(heading)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let name = chance.subjectName {
                    Text(name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let words = chance.subjectWords {
                    aflMatchOwnerWords(words)
                }
                let arrangements = AflMatchEventPageModel10868.readoutArrangements(accessibilitySize: typeSize.isAccessibilitySize)
                let sides = chance.sides
                if arrangements == [.stacked] {
                    VStack(alignment: .leading, spacing: 10) { chanceSlots(sides, chance) }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: 12) { chanceSlots(sides, chance) }
                        VStack(alignment: .leading, spacing: 10) { chanceSlots(sides, chance) }
                    }
                }
            }
            .padding(.top, 10)
            .overlay(alignment: .top) { Rectangle().fill(DS.border).frame(height: 1) }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.chances)
        }
    }

    private func chanceSlots(_ sides: [HistoricalChanceSide10868], _ chance: HistoricalChanceModel10868) -> some View {
        ForEach(Array(sides.enumerated()), id: \.offset) { _, side in
            chanceSlot(side, chance)
        }
    }

    @ViewBuilder private func chanceSlot(_ side: HistoricalChanceSide10868, _ chance: HistoricalChanceModel10868) -> some View {
        let opening = chance.openAction(side, canOpen: onChanceOpen != nil)
        let content = VStack(alignment: .leading, spacing: 4) {
            Text(FieldChaseModel10868.label(side.endpoint))
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let figure = FieldChaseModel10868.figure(side.endpoint) {
                Text(figure)
                    .font(.system(size: chanceSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(opening == nil ? DS.textPrimary : DS.blue)
                    .fixedSize()
            }
            if let words = FieldChaseModel10868.words(side.endpoint) {
                aflMatchOwnerWords(words)
            }
            if let detail = FieldChaseModel10868.detail(side.endpoint) {
                aflMatchOwnerWords(detail)
            }
        }
        .frame(maxWidth: .infinity, minHeight: controlSize, alignment: .leading)
        if let opening, let onChanceOpen {
            Button { onChanceOpen(opening) } label: { content.contentShape(Rectangle()) }
                .buttonStyle(.plain)
                .accessibilityLabel(chance.endpointSummary(side))
                .accessibilityHint(chance.hint(opening))
                .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.chance(side.kind))
        } else {
            content
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(chance.endpointSummary(side))
                .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.chance(side.kind))
        }
    }
}

/// VoiceOver's adjustable action on the scoring plot: the earlier or later
/// play's exact id; nothing without a target.
private struct AflMatchAdjustable10868: ViewModifier {
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

struct AflMatchEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: AflMatchEventPageInput10868
    var mode: AflMatchEventPageMode10868 = .page
    /// The page, catalogue and Details modes' originals; nil: none.
    var originals: AussieRulesEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's About.
    var onAbout: (() -> Void)? = nil
    /// A source's exact identity, for the host to open.
    var onSource: ((AussieRulesEventPageSource10868) -> Void)? = nil
    /// Opens the host's existing catalogue.
    var onAllProps: (() -> Void)? = nil
    /// An original's exact selection, for the host to hold and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// A headline team's exact open, for the host's history.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Opens the host's reader on a card mounted directly on the page.
    var onCardOpen: ((AflMatchEventPageCard10868) -> Void)? = nil
    /// A page card's Details, for the host to present.
    var onCardDetails: ((AflMatchEventPageCard10868) -> Void)? = nil
    /// A scoring play's exact id, for the host to hold.
    var onPlaySelect: ((String) -> Void)? = nil
    /// A quarter row's exact id, for the host to hold.
    var onPeriodSelect: ((String) -> Void)? = nil
    /// A chance's exact original and observation key, for the host's history.
    var onChanceOpen: ((FieldMovementOpen10868) -> Void)? = nil
    /// Full-size content's own controls, exactly.
    var onReaderIntent: ((AflMatchReaderIntent10868) -> Void)? = nil
    /// Called once just before a page, catalogue or Details action reaches its
    /// owner callback, so the owner can hold. Never called by building the
    /// view, by full-size content, by the About or by a stream card.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var headlineMinWidth: CGFloat = 300
    @ScaledMetric(relativeTo: .body) private var headlineMaxWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: AflMatchEventPageModel10868 { AflMatchEventPageModel10868(input) }

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

    /// A page, catalogue or Details action, after the owner's interaction
    /// hook. No host callback: no action and no hook call.
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
    static func bind(_ action: ((AflMatchEventPageCard10868) -> Void)?, _ card: AflMatchEventPageCard10868) -> (() -> Void)? {
        guard let action else { return nil }
        return { action(card) }
    }

    /// A reader intent callback bound to one intent.
    static func bind(_ action: ((AflMatchReaderIntent10868) -> Void)?, _ intent: AflMatchReaderIntent10868) -> (() -> Void)? {
        guard let action else { return nil }
        return { action(intent) }
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

    /// The accepted comparison View over the exact history copy the anchor
    /// beside it draws: the same readouts inline and full size. No action.
    func comparisonContent(reader: Bool) -> RugbyMatchEventPageComparisonPresentation10868 {
        RugbyMatchEventPageComparisonPresentation10868(
            history: reader ? model.readerHistory : model.presentedHistory, label: model.comparisonLabel)
    }

    /// The scoring story mounted directly on the page: every action after the
    /// interaction hook.
    func pageScoringContent() -> AflMatchScoringCard10868? {
        guard model.showsCardsDirectly, let story = model.scoringModel else { return nil }
        return AflMatchScoringCard10868(
            model: story,
            onExpand: Self.heldAction(Self.bind(onCardOpen, .scoring), by: onInteraction),
            onSelect: Self.held(onPlaySelect, by: onInteraction),
            onChanceOpen: Self.held(onChanceOpen, by: onInteraction),
            onPeriods: model.isMounted(.periods) ? Self.heldAction(Self.bind(onCardOpen, .periods), by: onInteraction) : nil,
            onDetails: Self.heldAction(Self.bind(onCardDetails, .scoring), by: onInteraction))
    }

    /// The quarter story mounted directly on the page: every action after the
    /// interaction hook.
    func pagePeriodsContent() -> AflMatchPeriodCard10868? {
        guard model.showsCardsDirectly, let story = model.periodModel else { return nil }
        return AflMatchPeriodCard10868(
            model: story, chance: model.chance,
            onExpand: Self.heldAction(Self.bind(onCardOpen, .periods), by: onInteraction),
            onSelect: Self.held(onPeriodSelect, by: onInteraction),
            onChanceOpen: Self.held(onChanceOpen, by: onInteraction),
            onDetails: Self.heldAction(Self.bind(onCardDetails, .periods), by: onInteraction))
    }

    /// A story card in a stream cell: every action after the stream's
    /// activation hook, never the page hook as well. The stream offers its own
    /// "Open full card".
    func streamScoringContent(activation: StoryStreamCardActivation10868) -> AflMatchScoringCard10868? {
        guard let story = model.scoringModel else { return nil }
        return AflMatchScoringCard10868(
            model: story, onExpand: nil,
            onSelect: Self.relay(onPlaySelect, through: activation),
            onChanceOpen: Self.relay(onChanceOpen, through: activation),
            onPeriods: model.isMounted(.periods) ? Self.relayAction(Self.bind(onCardOpen, .periods), through: activation) : nil,
            onDetails: Self.relayAction(Self.bind(onCardDetails, .scoring), through: activation))
    }

    func streamPeriodsContent(activation: StoryStreamCardActivation10868) -> AflMatchPeriodCard10868? {
        guard let story = model.periodModel else { return nil }
        return AflMatchPeriodCard10868(
            model: story, chance: model.chance, onExpand: nil,
            onSelect: Self.relay(onPeriodSelect, through: activation),
            onChanceOpen: Self.relay(onChanceOpen, through: activation),
            onDetails: Self.relayAction(Self.bind(onCardDetails, .periods), through: activation))
    }

    /// The full-size scoring story: the exact callbacks; its quarters link and
    /// Details are reader intents.
    func readerScoringContent() -> AflMatchScoringCard10868? {
        model.readerScoringModel.map {
            AflMatchScoringCard10868(
                model: $0, onExpand: nil, onSelect: onPlaySelect, onChanceOpen: onChanceOpen,
                onPeriods: model.isMounted(.periods) ? Self.bind(onReaderIntent, .open(.periods)) : nil,
                onDetails: Self.bind(onReaderIntent, .details(.scoring)))
        }
    }

    /// The full-size quarter story: the exact callbacks.
    func readerPeriodsContent() -> AflMatchPeriodCard10868? {
        model.periodModel.map {
            AflMatchPeriodCard10868(
                model: $0, chance: model.chance, onExpand: nil, onSelect: onPeriodSelect,
                onChanceOpen: onChanceOpen, onDetails: Self.bind(onReaderIntent, .details(.periods)))
        }
    }

    /// The page's originals, with their selection after the interaction hook.
    func chooserContent() -> OriginalMarketChooserView9483? {
        originals.map {
            OriginalMarketChooserView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: Self.held(onOriginalSelect, by: onInteraction)
            )
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
    func aboutContent() -> AussieRulesEventPageAboutContent10868? {
        model.about.map { AussieRulesEventPageAboutContent10868(about: $0, onSource: onSource) }
    }

    /// Full-size content's About: the exact callback, no hook.
    func openReaderAbout() {
        aboutOpener()?()
    }

    /// The page's All markets entry, after the interaction hook.
    func openAllProps() {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return }
        Self.heldAction(onAllProps, by: onInteraction)?()
    }

    /// Full-size content's own controls: the mounted neighbours and Back, exactly.
    func readerControls(_ card: AflMatchEventPageCard10868) -> (previous: AflMatchEventPageCard10868?,
                                                                next: AflMatchEventPageCard10868?,
                                                                canGoBack: Bool) {
        guard onReaderIntent != nil, model.readerShows(card) else { return (nil, nil, false) }
        return (model.neighbour(of: card, offset: -1), model.neighbour(of: card, offset: 1), true)
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            hero
            cards
            originalsPanel
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.page)
    }

    /// The headline and the history in one panel: side by side where both
    /// fit at their minimum widths, otherwise the headline above the history.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            let arrangements = AflMatchEventPageModel10868.arrangements(
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
        .modifier(AflMatchCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.hero)
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

    /// The headline, or the owner's words when its phase is not the page's,
    /// then the owner's status words.
    private var headlineSection: some View {
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
                        .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.headlineUnavailable)
                }
            }
            .accessibilitySortPriority(AflMatchEventPageModel10868.sortPriority(.headline))
            if let notice = AflMatchEventPageModel10868.readable(input.notice) {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilitySortPriority(AflMatchEventPageModel10868.sortPriority(.notice))
                    .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.notice)
            }
        }
        .accessibilityElement(children: .contain)
    }

    /// The paired comparison directly above the history, both from one copy.
    private var anchor: some View {
        VStack(alignment: .leading, spacing: 16) {
            comparisonContent(reader: false)
            historyContent(reader: false)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilitySortPriority(AflMatchEventPageModel10868.sortPriority(.anchor))
        .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.anchor)
    }

    /// The owner's stream when it supplies one; otherwise the mounted cards
    /// directly on the page, scoring first.
    @ViewBuilder private var cards: some View {
        if let stream = input.stream {
            StoryStreamPresentationView10868(stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(input.copy.storiesLabel)
            .accessibilitySortPriority(AflMatchEventPageModel10868.sortPriority(.cards))
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.stories)
        } else {
            if let scoring = pageScoringContent() {
                cardSurface(scoring, card: .scoring)
            }
            if let periods = pagePeriodsContent() {
                cardSurface(periods, card: .periods)
            }
        }
    }

    private func cardSurface<Content: View>(_ content: Content, card: AflMatchEventPageCard10868) -> some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(AflMatchCardSurface10868())
            .accessibilitySortPriority(AflMatchEventPageModel10868.sortPriority(.cards))
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.card(card))
    }

    /// The card the owner links to this stream card, with the stream's
    /// activation hook and the owner's reason words, or the owner's
    /// unavailable words. Never a neighbour.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.storyLink(card.id), let content = streamCardContent(link.card, activation) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = AflMatchEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                content
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(AflMatchCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(AflMatchCardSurface10868())
                .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.storyUnavailable)
        }
    }

    private func streamCardContent(_ card: AflMatchEventPageCard10868,
                                   _ activation: StoryStreamCardActivation10868) -> AnyView? {
        switch card {
        case .history: nil
        case .scoring: streamScoringContent(activation: activation).map { AnyView($0) }
        case .periods: streamPeriodsContent(activation: activation).map { AnyView($0) }
        }
    }

    /// The originals with the owner's held-unavailable words, then All markets.
    @ViewBuilder private var originalsPanel: some View {
        let allProps = model.allPropsAvailable(canOpen: onAllProps != nil)
        let chooser = chooserContent()
        if chooser != nil || allProps {
            VStack(alignment: .leading, spacing: 12) {
                if let chooser {
                    VStack(alignment: .leading, spacing: 8) {
                        if let context = AflMatchEventPageModel10868.readable(originals?.context) {
                            Text(context)
                                .font(.caption)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        chooser
                        if AflMatchEventPageModel10868.heldOriginalIsUnavailable(originals) {
                            Text(input.copy.heldOriginalUnavailable)
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.heldUnavailable)
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(AflMatchCardSurface10868())
                    .accessibilityElement(children: .contain)
                    .accessibilitySortPriority(AflMatchEventPageModel10868.sortPriority(.originals))
                    .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.originals)
                }
                if allProps, let label = input.copy.allPropsLabel {
                    allPropsEntry(label)
                        .accessibilitySortPriority(AflMatchEventPageModel10868.sortPriority(.allProps))
                }
            }
        }
    }

    private func allPropsEntry(_ label: String) -> some View {
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
            .modifier(AflMatchCardSurface10868())
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.allProps)
    }

    // MARK: Full-size content and modes

    /// The same View and input, full size, under the compact match words and
    /// the reader's own controls. A card this phase does not show has no content.
    @ViewBuilder private func reader(_ card: AflMatchEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader(done: false)
                readerNavigation(card)
                switch card {
                case .history:
                    comparisonContent(reader: true)
                    historyContent(reader: true)
                case .scoring:
                    readerScoringContent()
                case .periods:
                    readerPeriodsContent()
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.card(card))
        }
    }

    /// Back, then the previous and next mounted cards by name.
    @ViewBuilder private func readerNavigation(_ card: AflMatchEventPageCard10868) -> some View {
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

    @ViewBuilder private func readerButtons(_ controls: (previous: AflMatchEventPageCard10868?,
                                                         next: AflMatchEventPageCard10868?,
                                                         canGoBack: Bool)) -> some View {
        readerButton(input.copy.backLabel, detail: nil, systemImage: "chevron.backward",
                     action: Self.bind(onReaderIntent, .back), id: AflMatchEventPageAccessibilityID10868.readerBack)
        if let previous = controls.previous {
            readerButton(input.copy.previousLabel, detail: model.cardName(previous), systemImage: "arrow.left",
                         action: Self.bind(onReaderIntent, .previous(previous)),
                         id: AflMatchEventPageAccessibilityID10868.readerPrevious)
        }
        if let next = controls.next {
            readerButton(input.copy.nextLabel, detail: model.cardName(next), systemImage: "arrow.right",
                         action: Self.bind(onReaderIntent, .next(next)),
                         id: AflMatchEventPageAccessibilityID10868.readerNext)
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
                        if let detail = AflMatchEventPageModel10868.readable(detail) {
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
    /// in the catalogue, Details and About content the Done control.
    private func compactHeader(done: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = AflMatchEventPageModel10868.readable(input.reader.state) {
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
                .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.readerAbout)
            }
            if done, let action = Self.bind(onReaderIntent, .done) {
                Button(input.copy.doneLabel, action: action)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(DS.blue)
                    .frame(minHeight: controlSize)
                    .buttonStyle(.plain)
                    .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.done)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.readerHeader)
    }

    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader(done: true)
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.catalogue)
        }
    }

    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader(done: true)
                details
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.original)
        }
    }

    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader(done: true)
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(AflMatchEventPageAccessibilityID10868.about)
        }
    }
}
