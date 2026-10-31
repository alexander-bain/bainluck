import SwiftUI

// #10868 — the Australian-rules match screen (`aflw-refresh`): one native
// presentation for an Australian-rules match before, during and after play,
// composed from the accepted shared leaves. Both teams' win chances lead, at
// equal prominence. A fan sees, in this order: the match headline — the owner's
// eyebrow, title and About entry; each named team's pre-match chance; during
// play that chance beside the owner's recorded or current chance; at the final
// that chance beside the team's actual final points, with the owner's separately
// admitted result words in the headline's state — beside the shared, named,
// shape-keyed win probability history; then, at the final, the owner's result
// story (the pre-match expectations, the official result, and the lead at each
// scoring break on a labelled points axis with the held break's exact score and
// lead change); then the original props with the held original's Details and
// the "All props" entry. The history and the result story open as full-size
// content made of the same Views and inputs; "All props", the held original's
// Details and the match About are further content modes.
//
// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: the AFLW page compares both
// teams' before/current win chances and actual final points, with retained
// probability history, a dense break-by-break score story and exact original
// readers.
//
// Presentation only, from the approved `AflwCaptureHeader.tsx`,
// `AflwFinalHeader.tsx`, `AflwPayoff.tsx` and `AflwWinnerJourney.tsx` with
// `aflwCaptureHistory.css`, `aflwFinal.css` and `aflwPayoff.css`, the
// readable-composition and lifecycle-headline native references, and the
// reader comparison adoption. The references' loaders, event and market
// allowlists, raw adapters, source selection, baseline election, date and score
// parsing, chronology filters, score validators, synthetic event repair,
// `ChanceText` / `ArchiveMatchClock`, capture stages and replay are NOT ported.
// Nothing here borrows another sport's probability or threshold card to draw
// actual points. The leaves are the actual accepted Views, unchanged:
//
//   • `FieldPhaseHeadlinePresentation10868` — the two named teams;
//   • `FieldProbabilityHistoryPresentation10868` — the anchor;
//   • `StoryStreamPresentationView10868` — the owner's controlled stream;
//   • `OriginalMarketChooserView9483` — the originals on the page;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     "All props" and the held original's Details.
//
// The result story is the one small immutable presentation drawn here, because
// no accepted leaf carries its grammar: the owner's pre-match chances on
// 0–100% rails, the owner's official result words, and one lead bar per scoring
// break on the owner's points axis (explicit label, owner ticks and range, a
// clear zero), with the held break's score and lead change. It takes arbitrary
// admitted inputs — any teams, any number of breaks, a lead that changes hands —
// and contains no specimen name, number, id or clock.
//
// The page's phase is the owner's explicit `AussieRulesEventPagePhase10868`,
// never read from a raw status, a clock, a quote, a score or a settlement. A
// suspended or otherwise held match is a during-phase page with the owner's
// status words. Before play only the pre-match chances are shown: a supplied
// later reading, final points, result words, break rows or story never are.
// During play no final actual, result story or provider note is shown, and
// history alone never makes the page say live. At the final the headline reads
// each team's pre-match chance beside its actual final points; the owner's
// result words sit in the headline's state. A headline from another phase is
// not coerced: the owner's unavailable words show instead.
//
// OWNER-RESOLVED, NEVER DERIVED HERE: the phase and status words; each team's
// identity, name, tint, key shape and qualified readings with their own clocks
// (pre-match, recorded or current — the owner's label says which, and a
// recording is never promoted to a current chance here); the final points and
// goals/behinds words; the result words; every break row's lead (geometry
// only), lead words, leading team, score words and lead-change words; the
// points scale; the history's series, runs, breaks, marks, readouts, inspection
// and controls; the stream; the originals, their modes, readings, grades and
// recorded history; the held selections; the About and its sources. This layer
// never computes points from goals and behinds, never subtracts scores, never
// grades a contract from the official score, never copies the event's pre-match
// chance into an original, never complements or normalizes two chances, never
// treats a missing value as zero, never adds a 0%/100% result point, a kickoff
// marker or a break marker to the probability history, never aligns a scoring
// break to a probability observation, and never deduplicates two observations
// because their figures match. An empty current catalogue grades, voids and
// drops nothing: the held original stays the owner's exact selection, shown as
// unavailable, and no neighbour stands in.
//
// The full-size history is the same history input — every series, run, break,
// tick, readout, selection, inspection and control — without its expand control
// (already open) and at the owner's reader plot height when that is taller.
// The full-size result story is the same story at the owner's reader bar height
// when that is taller, with no expand control.
//
// INTERACTION. On the page — the headline's open and About, the anchor
// history's actions, inspection choices and plot taps, the result story's
// expand, break selection, sources disclosure write and report source when the
// story is mounted directly, the originals' selection and the All props entry —
// and in the catalogue and Details content, the action calls the owner's
// interaction hook once and then the owner's exact callback with its exact
// value. A story card inside the owner's stream calls the stream's activation
// hook instead, never the page hook as well. Full-size content and the About
// keep the exact callbacks: their host already holds. Building or reading the
// view calls nothing; reading a disclosure binding asks for nothing. Without a
// callback there is no control and no hook call.
//
// LAYOUT. Phone and accessibility sizes stack the headline above the history,
// then the story and the originals. A regular or unspecified width (a Mac
// window) places the headline beside the history while both keep their minimum
// widths, otherwise it stacks. The headline leaf measures its own equal team
// columns at the active text size. The story places its expectations and result
// beside its break bars where both fit, else stacks; at accessibility sizes the
// break bars become one full-width row each on the same points axis. Plot and
// bar heights are the owner's and are never shrunk; no main value shrinks to fit.
//
// The host owns the scroll, navigation, sheets, Back/Done, focus, routing,
// every held selection and disclosure, how a hook request holds the stream,
// subscriptions and every genuine update. This view keeps no state, runs no
// timer or animation, holds no subscription and presents nothing of its own.
//
// Host binding still owed: no Australian-rules page input adapter exists at
// this base. Phase and status words, team identities and readings, final points
// and result words, break rows, history admission, stream, originals and About
// are unbound owner channels (named in the handback).

// MARK: - Phase, cards, modes

/// The owner's explicit phase for the whole screen.
nonisolated enum AussieRulesEventPagePhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final
}

/// One card the page can show full size. `history` is the anchor.
nonisolated enum AussieRulesEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// The result story: expectations, official result and the lead at each break.
    case story
}

/// What the host's container is showing, chosen by the host.
nonisolated enum AussieRulesEventPageMode10868: Equatable {
    /// The match screen body.
    case page
    /// One card's full-size content.
    case reader(AussieRulesEventPageCard10868)
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's match About with its sources.
    case about
}

nonisolated enum AussieRulesEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

/// The page's regions in reading order.
nonisolated enum AussieRulesEventPageBlock10868: String, CaseIterable {
    case headline
    case notice
    case anchor
    case story
    case originals
    case allProps
}

// MARK: - Result story input

/// One owner tick on the points axis.
nonisolated struct AussieRulesPointsTick10868: Equatable {
    /// In the owner's points units.
    let value: Double
    /// Verbatim, as the owner wrote it.
    let label: String
}

/// The owner's points axis for the lead bars. Zero always lies inside it.
nonisolated struct AussieRulesPointsScale10868: Equatable {
    /// At or below zero, in the owner's points units.
    let lower: Double
    /// At or above zero.
    let upper: Double
    let ticks: [AussieRulesPointsTick10868]
    /// The axis's visible label ("Points ahead").
    let label: String
    /// What a bar toward `upper` means (the owner's "<team> ahead"); nil draws none.
    var upperWords: String? = nil
    /// What a bar toward `lower` means; nil draws none.
    var lowerWords: String? = nil

    var isValid: Bool {
        lower.isFinite && upper.isFinite && lower <= 0 && upper >= 0 && upper > lower
    }
}

/// One scoring break's actual lead and score, in the owner's units and words.
nonisolated struct AussieRulesScoreBreak10868: Equatable {
    /// The owner's stable break identity.
    let id: String
    /// The break's own label, as the owner wrote it.
    let label: String
    /// The signed lead on the owner's scale, positive toward its upper end.
    /// Geometry only; nil draws no bar.
    let lead: Double?
    /// The owner's lead figure above the bar, or its words for a level score.
    let leadWords: String
    /// The team the bar belongs to, by the headline's exact identity; nil (level
    /// or unknown) draws a neutral bar.
    let leader: FieldChooserOriginalRef10868?
    /// The exact score at this break, in the owner's words.
    let score: String
    /// The lead change into this break, in the owner's words; nil draws none.
    let change: String?
    /// The whole reading in words.
    let spoken: String
}

/// The owner's official result words. Never derived from scores here.
nonisolated struct AussieRulesResultWords10868: Equatable {
    /// "OFFICIAL FINAL".
    let eyebrow: String
    /// The final score line, in the owner's words.
    let headline: String
    /// The margin words; nil draws none.
    let detail: String?
    /// Goals, behinds and points words, one line per team, as the owner wrote them.
    let lines: [String]
    let spoken: String
}

nonisolated struct AussieRulesResultStoryCopy10868: Equatable {
    /// "PREGAME EXPECTATION · ACTUAL RESULT".
    let eyebrow: String
    /// The owner's story title.
    let title: String
    /// "Before the match".
    let expectationTitle: String
    /// The chances' own clock and source words; nil draws none.
    let expectationCaption: String?
    /// The rails' scale words ("Win chance · 0–100%").
    let railScale: String
    /// Shown when no expectation row can be read.
    let expectationUnavailable: String
    /// Shown in place of the result words when none are admitted.
    let resultUnavailable: String
    /// The bars' title, in the owner's words.
    let breaksTitle: String
    /// "Actual points ahead · starts at zero"; nil draws none.
    let breaksCaption: String?
    /// Spoken name of the bars ("Lead at each scoring break").
    let breaksGroupLabel: String
    /// No break rows ("Break scores not reported").
    let breaksEmpty: String
    /// A lead that cannot be placed.
    let leadUnavailable: String
    /// A lead beyond the owner's axis.
    let offScale: String
    /// Shown when no break is held; nil draws none.
    let selectionPrompt: String?
    /// The held break is not among the rows.
    let selectionMissing: String
    /// A break's select hint, only on a control that acts.
    let selectHint: String?
    /// The owner's takeaway; nil draws none.
    let takeaway: String?
    /// "Probability and score sources".
    let notesLabel: String
    /// The expand control's spoken name ("Expand expectation and result").
    let expandLabel: String
}

/// The owner's result story for the final.
nonisolated struct AussieRulesResultStory10868: Equatable {
    /// Nil shows the copy's unavailable words.
    let result: AussieRulesResultWords10868?
    let scale: AussieRulesPointsScale10868
    /// In the owner's order. Never sorted, filtered or deduplicated here.
    let breaks: [AussieRulesScoreBreak10868]
    /// The owner's held break; nil holds none. Never a default or a neighbour.
    let selectedBreakID: String?
    /// Source and timing words, verbatim.
    let notes: [String]
    /// The owner's report source ("Official match report"); nil draws none.
    var report: AussieRulesEventPageSource10868? = nil
    /// The owner's bar area height in points. Never shrunk here.
    let barHeight: CGFloat
    /// The full-size bar height; nil, or shorter, keeps `barHeight`.
    var readerBarHeight: CGFloat? = nil
    let copy: AussieRulesResultStoryCopy10868
}

// MARK: - Page input

/// The owner's one-line match words above full-size content.
nonisolated struct AussieRulesEventPageReaderHeader10868: Equatable {
    /// The two teams, in the owner's words.
    let title: String
    /// The owner's match state words; nil draws none.
    let state: String?
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct AussieRulesEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: AussieRulesEventPageCard10868
    /// The owner's words for why this story is here; nil draws none.
    var reason: String? = nil
}

/// A source the owner can open ("Official match report"). The host resolves
/// and opens it; nothing here does.
nonisolated struct AussieRulesEventPageSource10868: Equatable {
    let id: String
    let label: String
    var hint: String? = nil
}

/// One section of the owner's About, verbatim.
nonisolated struct AussieRulesEventPageAboutSection10868: Equatable {
    let title: String
    let paragraphs: [String]
    var source: AussieRulesEventPageSource10868? = nil
}

/// The owner's match About, verbatim.
nonisolated struct AussieRulesEventPageAbout10868: Equatable {
    /// "About this match".
    let title: String
    let sections: [AussieRulesEventPageAboutSection10868]
}

nonisolated struct AussieRulesEventPageCopy10868: Equatable {
    /// Spoken name of the stories group ("Match stories").
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single story this phase shows.
    let storyUnavailable: String
    /// Shown in place of a headline whose phase is not the page's.
    let headlineUnavailable: String
    /// The entry's words ("All original props"); nil draws no entry.
    let allPropsLabel: String?
    /// The held original is not in this update ("Your selected prop is not in this update").
    let heldOriginalUnavailable: String
}

struct AussieRulesEventPageInput10868: Equatable {
    let phase: AussieRulesEventPagePhase10868
    let reader: AussieRulesEventPageReaderHeader10868
    let headline: FieldHeadlineInput10868
    /// The owner's status words under the headline; nil draws none.
    var notice: String? = nil
    let history: FieldHistoryInput10868
    /// The owner's plot height for the full-size chart; nil, or shorter than
    /// the page's, keeps the page's.
    var readerPlotHeight: CGFloat? = nil
    /// The owner's result story; mounted at the final only.
    var story: AussieRulesResultStory10868? = nil
    /// The owner's story stream; nil mounts the story directly on the page.
    var stream: StoryStreamPresentation10868? = nil
    var stories: [AussieRulesEventPageStory10868] = []
    /// Opened by the headline's About control; nil: no control.
    var about: AussieRulesEventPageAbout10868? = nil
    let copy: AussieRulesEventPageCopy10868
}

/// The owner's originals for the page, "All props" and Details. Every field
/// reaches the existing leaves unchanged.
struct AussieRulesEventPageOriginals10868 {
    /// The latest admitted originals for one scope; nil shows `emptyWords`.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The owner's held selection; nil holds none.
    let selection: OriginalMarketDetails9483.Selection?
    /// The held original's admitted recorded history, Details mode only.
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    /// "Match winner".
    let heading: String
    /// The owner's source and count words; nil draws none.
    var context: String? = nil
    /// "No props supplied in this update".
    let emptyWords: String
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum AussieRulesEventPageAccessibilityID10868 {
    static let page = "aussieRulesEventPage10868.page"
    static let hero = "aussieRulesEventPage10868.hero"
    static let headlineUnavailable = "aussieRulesEventPage10868.headline.unavailable"
    static let notice = "aussieRulesEventPage10868.notice"
    static let anchor = "aussieRulesEventPage10868.anchor"
    static let stories = "aussieRulesEventPage10868.stories"
    static let story = "aussieRulesEventPage10868.story"
    static let storyUnavailable = "aussieRulesEventPage10868.story.unavailable"
    static let storyExpand = "aussieRulesEventPage10868.story.expand"
    static let expectation = "aussieRulesEventPage10868.story.expectation"
    static let result = "aussieRulesEventPage10868.story.result"
    static let breaks = "aussieRulesEventPage10868.story.breaks"
    static let breakReadout = "aussieRulesEventPage10868.story.breakReadout"
    static let notes = "aussieRulesEventPage10868.story.notes"
    static let report = "aussieRulesEventPage10868.story.report"
    static let originals = "aussieRulesEventPage10868.originals"
    static let heldUnavailable = "aussieRulesEventPage10868.originals.heldUnavailable"
    static let allProps = "aussieRulesEventPage10868.allProps"
    static let readerHeader = "aussieRulesEventPage10868.readerHeader"
    static let readerAbout = "aussieRulesEventPage10868.readerHeader.about"
    static let catalogue = "aussieRulesEventPage10868.catalogue"
    static let original = "aussieRulesEventPage10868.original"
    static let about = "aussieRulesEventPage10868.about"
    static func card(_ card: AussieRulesEventPageCard10868) -> String { "aussieRulesEventPage10868.card.\(card.rawValue)" }
    static func breakBar(_ id: String) -> String { "aussieRulesEventPage10868.story.break.\(id)" }
    static func source(_ id: String) -> String { "aussieRulesEventPage10868.source.\(id)" }
}

// MARK: - Words

/// The page's and the story's words rules, callable from any isolation.
nonisolated enum AussieRulesEventPageWords10868 {
    /// The owner's words when they carry a visible character; nothing otherwise.
    static func readable(_ words: String?) -> String? {
        guard let words, !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return words
    }

    /// A source acts only with a callback, a readable id and a readable label.
    static func sourceIsLive(_ source: AussieRulesEventPageSource10868, canOpen: Bool) -> Bool {
        canOpen && readable(source.id) != nil && readable(source.label) != nil
    }
}

// MARK: - Result story geometry and model

/// Where one lead bar sits on the owner's axis, as fractions of the axis from
/// its lower end.
nonisolated enum AussieRulesLeadBar10868: Equatable {
    /// From the zero line to the lead.
    case bar(zero: Double, end: Double)
    /// A real level lead: a mark on the zero line.
    case level(zero: Double)
    /// A finite lead beyond the owner's axis: no bar, the owner's words.
    case offScale(above: Bool)
    /// Missing, non-finite, or an unusable axis: nothing drawn.
    case unavailable
}

/// Pure rules the story draws from. Unit-tested without rendering.
nonisolated enum AussieRulesResultStoryGeometry10868 {
    /// Used only when the owner's height is not a usable size.
    static let referenceBarHeight: CGFloat = 125

    static func barHeight(_ owner: CGFloat) -> CGFloat {
        owner.isFinite && owner > 0 ? owner : referenceBarHeight
    }

    /// A value's place on the owner's axis; nil for an unusable axis, a
    /// non-finite value or one beyond the axis. Never clamped.
    static func fraction(_ value: Double, in scale: AussieRulesPointsScale10868) -> Double? {
        guard scale.isValid, value.isFinite, value >= scale.lower, value <= scale.upper else { return nil }
        return (value - scale.lower) / (scale.upper - scale.lower)
    }

    /// The zero line, always on a usable axis.
    static func zero(_ scale: AussieRulesPointsScale10868) -> Double? {
        fraction(0, in: scale)
    }

    static func bar(_ lead: Double?, in scale: AussieRulesPointsScale10868) -> AussieRulesLeadBar10868 {
        guard let zeroLine = zero(scale), let lead, lead.isFinite else { return .unavailable }
        guard let end = fraction(lead, in: scale) else { return .offScale(above: lead > scale.upper) }
        return lead == 0 ? .level(zero: zeroLine) : .bar(zero: zeroLine, end: end)
    }

    /// The owner's ticks that sit on the axis, with readable labels, in the owner's order.
    static func ticks(_ scale: AussieRulesPointsScale10868) -> [(fraction: Double, label: String)] {
        scale.ticks.compactMap { tick in
            guard let place = fraction(tick.value, in: scale),
                  let label = AussieRulesEventPageWords10868.readable(tick.label) else { return nil }
            return (fraction: place, label: label)
        }
    }

    /// A raw chance's rail fill, 0...1; nothing otherwise.
    static func railFraction(_ probability: Double?) -> Double? {
        guard let probability, probability.isFinite, (0...1).contains(probability) else { return nil }
        return probability
    }

    /// The vertical drawing frame inside a bar area, leaving room above and
    /// below for the lead words; nil when nothing can be drawn.
    static func plotFrame(in size: CGSize, room: CGFloat) -> CGRect? {
        guard size.width.isFinite, size.height.isFinite, room.isFinite, room >= 0,
              size.width > 0, size.height > room * 2 else { return nil }
        return CGRect(x: 0, y: room, width: size.width, height: size.height - room * 2)
    }

    /// A fraction's height in a vertical frame (the lower end at the bottom).
    static func y(_ fraction: Double, in frame: CGRect) -> CGFloat {
        frame.maxY - CGFloat(fraction) * frame.height
    }

    /// A fraction's position in a horizontal frame (the lower end at the left).
    static func x(_ fraction: Double, in frame: CGRect) -> CGFloat {
        frame.minX + CGFloat(fraction) * frame.width
    }

    /// The bar's rect in a vertical frame, centred, `thickness` wide; a level
    /// lead is a 3-point mark on the zero line. Nil draws nothing.
    static func verticalBar(_ plan: AussieRulesLeadBar10868, in frame: CGRect, thickness: CGFloat) -> CGRect? {
        guard thickness.isFinite, thickness > 0, frame.width.isFinite, frame.height.isFinite,
              frame.width > 0, frame.height > 0 else { return nil }
        let width = min(thickness, frame.width)
        let left = frame.midX - width / 2
        switch plan {
        case .bar(let zero, let end):
            let top = y(max(zero, end), in: frame)
            let bottom = y(min(zero, end), in: frame)
            return CGRect(x: left, y: top, width: width, height: max(bottom - top, 1))
        case .level(let zero):
            return CGRect(x: left, y: y(zero, in: frame) - 1.5, width: width, height: 3)
        case .offScale, .unavailable:
            return nil
        }
    }

    /// The bar's rect in a horizontal frame, `thickness` tall.
    static func horizontalBar(_ plan: AussieRulesLeadBar10868, in frame: CGRect, thickness: CGFloat) -> CGRect? {
        guard thickness.isFinite, thickness > 0, frame.width.isFinite, frame.height.isFinite,
              frame.width > 0, frame.height > 0 else { return nil }
        let height = min(thickness, frame.height)
        let top = frame.midY - height / 2
        switch plan {
        case .bar(let zero, let end):
            let left = x(min(zero, end), in: frame)
            let right = x(max(zero, end), in: frame)
            return CGRect(x: left, y: top, width: max(right - left, 1), height: height)
        case .level(let zero):
            return CGRect(x: x(zero, in: frame) - 1.5, y: top, width: 3, height: height)
        case .offScale, .unavailable:
            return nil
        }
    }
}

/// One team's pre-match expectation in the story, read from the final
/// headline's own pre-match reading and its tied observation.
nonisolated struct AussieRulesExpectationRow10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    let name: String
    /// The headline's own pre-match endpoint: a tied figure or words.
    let endpoint: FieldMovementEndpoint10868
    /// The tied raw chance's rail fill; nil draws no rail.
    let fraction: Double?
    let accent: Color?
    let shape: FieldHeadlineKeyShape10868
}

/// One break bar as the story draws it.
nonisolated struct AussieRulesStoryBar10868: Equatable {
    let row: AussieRulesScoreBreak10868
    let plan: AussieRulesLeadBar10868
    /// The leading team's chart colour; nil draws the neutral colour.
    let accent: Color?
    /// The leading team's key shape; nil draws no key.
    let shape: FieldHeadlineKeyShape10868?
    /// The id a selection hands back: nonempty and unique among the rows.
    let selectableID: String?
    let isSelected: Bool
}

/// What the story shows for the held break.
nonisolated enum AussieRulesBreakSelection10868: Equatable {
    /// Nothing held: the owner's prompt, or nothing.
    case unheld(prompt: String?)
    /// The exact held break.
    case row(AussieRulesScoreBreak10868)
    /// The held id names no single break, in the owner's words. Never a neighbour.
    case missing(String)
}

/// The story's rules, resolved once per input.
nonisolated struct AussieRulesResultStoryModel10868: Equatable {
    let story: AussieRulesResultStory10868
    /// The page's final headline, when its phase is the page's.
    let headline: FieldHeadlineInput10868?

    init(story: AussieRulesResultStory10868, headline: FieldHeadlineInput10868?) {
        self.story = story
        self.headline = headline
    }

    var copy: AussieRulesResultStoryCopy10868 { story.copy }

    // MARK: Expectations

    /// Each displayed team's pre-match reading exactly as the final headline
    /// shows it, with the rail fill of that same tied observation. Empty
    /// without a final headline.
    var expectation: [AussieRulesExpectationRow10868] {
        guard let headline, headline.phase == .final else { return [] }
        let model = FieldHeadlineModel10868(headline)
        return model.competitors.map { competitor in
            guard let original = competitor.resolution.original, let endpoint = competitor.metrics.first else {
                return AussieRulesExpectationRow10868(
                    ref: competitor.slot.ref, name: competitor.slot.name,
                    endpoint: .unavailable(label: headline.copy.beforeLabel, words: headline.unavailableWords),
                    fraction: nil, accent: nil, shape: competitor.slot.keyShape)
            }
            return AussieRulesExpectationRow10868(
                ref: original.ref, name: original.name, endpoint: endpoint,
                fraction: Self.railFraction(endpoint, ref: original.ref, pairs: headline.pairs),
                accent: original.accent, shape: competitor.slot.keyShape)
        }
    }

    /// The rail fill of a shown pre-match figure: the owner's one association
    /// for this exact team carrying that very reading and a valid raw chance.
    /// Words, a second association or an untied reading draw no rail.
    static func railFraction(_ endpoint: FieldMovementEndpoint10868, ref: FieldChooserOriginalRef10868,
                             pairs: [FieldMovementPair10868]) -> Double? {
        guard case .reading(let reading) = endpoint, case .recorded = reading.value else { return nil }
        let matches = pairs.filter { $0.ref == ref }
        guard matches.count == 1, let before = matches[0].before, before.reading == reading else { return nil }
        return AussieRulesResultStoryGeometry10868.railFraction(before.probability)
    }

    static func spokenExpectation(_ row: AussieRulesExpectationRow10868) -> String {
        "\(row.name). \(FieldMovementModel10868.spoken(row.endpoint))"
    }

    // MARK: Result

    var result: AussieRulesResultWords10868? { story.result }

    // MARK: Breaks

    /// Every row in the owner's order, each with its own bar, colour and key.
    var bars: [AussieRulesStoryBar10868] {
        story.breaks.map { row in
            let selectable = Self.selectableID(row, among: story.breaks)
            return AussieRulesStoryBar10868(
                row: row,
                plan: AussieRulesResultStoryGeometry10868.bar(row.lead, in: story.scale),
                accent: leaderOriginal(row.leader)?.accent,
                shape: leaderShape(row.leader),
                selectableID: selectable,
                isSelected: selectable != nil && selectable == story.selectedBreakID
            )
        }
    }

    /// A break hands back its id only when nonempty and unique among the rows.
    static func selectableID(_ row: AussieRulesScoreBreak10868, among rows: [AussieRulesScoreBreak10868]) -> String? {
        guard AussieRulesEventPageWords10868.readable(row.id) != nil,
              rows.filter({ $0.id == row.id }).count == 1 else { return nil }
        return row.id
    }

    /// The leading team's original in the headline catalogue: exactly one.
    func leaderOriginal(_ ref: FieldChooserOriginalRef10868?) -> FieldChooserOriginal10868? {
        guard let ref, let headline else { return nil }
        let matches = headline.catalogue.filter { $0.ref == ref }
        return matches.count == 1 ? matches[0] : nil
    }

    /// The leading team's key shape from its one displayed slot.
    func leaderShape(_ ref: FieldChooserOriginalRef10868?) -> FieldHeadlineKeyShape10868? {
        guard let ref, let headline, leaderOriginal(ref) != nil else { return nil }
        let slots = headline.displayed.filter { $0.ref == ref }
        return slots.count == 1 ? slots[0].keyShape : nil
    }

    /// The owner's words under a bar that draws nothing.
    func barWords(_ bar: AussieRulesStoryBar10868) -> String? {
        switch bar.plan {
        case .bar, .level: return nil
        case .offScale: return copy.offScale
        case .unavailable: return copy.leadUnavailable
        }
    }

    /// The held break, or the owner's words. Never the first, the latest or a neighbour.
    var selection: AussieRulesBreakSelection10868 {
        guard let id = story.selectedBreakID else {
            return .unheld(prompt: AussieRulesEventPageWords10868.readable(copy.selectionPrompt))
        }
        let matches = story.breaks.filter { $0.id == id }
        guard AussieRulesEventPageWords10868.readable(id) != nil, matches.count == 1 else {
            return .missing(copy.selectionMissing)
        }
        return .row(matches[0])
    }

    /// The only way a bar acts: the host's callback with the bar's own exact id.
    static func selectAction(_ bar: AussieRulesStoryBar10868, onSelect: ((String) -> Void)?) -> (() -> Void)? {
        guard let onSelect, let id = bar.selectableID else { return nil }
        return { onSelect(id) }
    }

    /// The owner's ticks on the axis.
    var ticks: [(fraction: Double, label: String)] {
        AussieRulesResultStoryGeometry10868.ticks(story.scale)
    }

    var zero: Double? { AussieRulesResultStoryGeometry10868.zero(story.scale) }

    var barHeight: CGFloat { AussieRulesResultStoryGeometry10868.barHeight(story.barHeight) }

    // MARK: Notes and report

    var notes: [String] { story.notes.compactMap { AussieRulesEventPageWords10868.readable($0) } }

    func reportAction(onSource: ((AussieRulesEventPageSource10868) -> Void)?) -> (() -> Void)? {
        guard let report = story.report, AussieRulesEventPageWords10868.sourceIsLive(report, canOpen: onSource != nil),
              let onSource else { return nil }
        return { onSource(report) }
    }

    /// Expectations and result beside the bars where both fit; stacked on a
    /// compact width or at accessibility sizes.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [AussieRulesEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }

    /// Vertical bars normally; one full-width row per break at accessibility sizes.
    static func barsRunHorizontally(accessibilitySize: Bool) -> Bool { accessibilitySize }
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
struct AussieRulesEventPageModel10868: Equatable {
    let input: AussieRulesEventPageInput10868

    init(_ input: AussieRulesEventPageInput10868) {
        self.input = input
    }

    static func headlinePhase(_ phase: AussieRulesEventPagePhase10868) -> FieldOutlookPhase10868 {
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

    /// The result story at the final only.
    var story: AussieRulesResultStory10868? {
        input.phase == .final ? input.story : nil
    }

    var storyModel: AussieRulesResultStoryModel10868? {
        story.map { AussieRulesResultStoryModel10868(story: $0, headline: headline) }
    }

    func isMounted(_ card: AussieRulesEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .story: story != nil
        }
    }

    /// The owner's link a stream card id names: exactly one link with that id,
    /// to a story this phase mounts. Otherwise nothing.
    func storyLink(_ cardID: String) -> AussieRulesEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    /// Without a stream the mounted story sits directly on the page.
    var showsStoryDirectly: Bool { input.stream == nil && story != nil }

    func readerShows(_ card: AussieRulesEventPageCard10868) -> Bool { isMounted(card) }

    /// The full-size history: the same input without its expand control and
    /// at the owner's reader plot height when taller. Every other field is the
    /// owner's, unchanged.
    var readerHistory: FieldHistoryInput10868 {
        let history = input.history
        let height = max(history.plotHeight, input.readerPlotHeight ?? history.plotHeight)
        return FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: height,
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

    /// The full-size story: the same story at the owner's reader bar height
    /// when taller.
    var readerStoryModel: AussieRulesResultStoryModel10868? {
        guard let shown = story else { return nil }
        let height = max(shown.barHeight, shown.readerBarHeight ?? shown.barHeight)
        let full = AussieRulesResultStory10868(
            result: shown.result, scale: shown.scale, breaks: shown.breaks,
            selectedBreakID: shown.selectedBreakID, notes: shown.notes, report: shown.report,
            barHeight: height, readerBarHeight: shown.readerBarHeight, copy: shown.copy)
        return AussieRulesResultStoryModel10868(story: full, headline: headline)
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
              Self.readable(about.title) != nil || about.sections.contains(where: Self.hasWords)
        else { return nil }
        return about
    }

    static func hasWords(_ section: AussieRulesEventPageAboutSection10868) -> Bool {
        readable(section.title) != nil || section.paragraphs.contains { readable($0) != nil }
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil
    }

    /// Full-size content's compact heading shows the About entry; the page has
    /// the headline's own control.
    func aboutEntry(mode: AussieRulesEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode, Self.readable(input.headline.copy.aboutLabel) != nil else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && Self.readable(input.copy.allPropsLabel) != nil
    }

    static func sourceIsLive(_ source: AussieRulesEventPageSource10868, canOpen: Bool) -> Bool {
        AussieRulesEventPageWords10868.sourceIsLive(source, canOpen: canOpen)
    }

    static func readable(_ words: String?) -> String? {
        AussieRulesEventPageWords10868.readable(words)
    }

    // MARK: Layout and reading order

    /// Accessibility sizes and a compact width stack; a regular or unspecified
    /// width tries the headline beside the history, then stacks.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [AussieRulesEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }

    static let readingOrder: [AussieRulesEventPageBlock10868] = [.headline, .notice, .anchor, .story, .originals, .allProps]

    /// VoiceOver reads the same order in every arrangement.
    static func sortPriority(_ block: AussieRulesEventPageBlock10868) -> Double {
        Double(readingOrder.count - (readingOrder.firstIndex(of: block) ?? readingOrder.count))
    }
}

// MARK: - About content

/// The owner's match About in its own words, with each section's source.
struct AussieRulesEventPageAboutContent10868: View {
    let about: AussieRulesEventPageAbout10868
    var onSource: ((AussieRulesEventPageSource10868) -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let title = AussieRulesEventPageModel10868.readable(about.title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(about.sections.enumerated()), id: \.offset) { _, section in
                if AussieRulesEventPageModel10868.hasWords(section) {
                    VStack(alignment: .leading, spacing: 6) {
                        if let title = AussieRulesEventPageModel10868.readable(section.title) {
                            Text(title)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                        }
                        ForEach(Array(section.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            if let words = AussieRulesEventPageModel10868.readable(paragraph) {
                                Text(words)
                                    .font(.body)
                                    .foregroundStyle(DS.textPrimary)
                            }
                        }
                        sourceControl(section.source)
                    }
                }
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The section's exact source for the host to open, or nothing.
    func sourceAction(_ source: AussieRulesEventPageSource10868?) -> (() -> Void)? {
        guard let source, AussieRulesEventPageModel10868.sourceIsLive(source, canOpen: onSource != nil),
              let onSource else { return nil }
        return { onSource(source) }
    }

    @ViewBuilder private func sourceControl(_ source: AussieRulesEventPageSource10868?) -> some View {
        if let source, let action = sourceAction(source) {
            Button(action: action) {
                HStack(spacing: 6) {
                    Text(source.label)
                        .font(.body.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Image(systemName: "arrow.up.right")
                        .font(.body.weight(.semibold))
                        .accessibilityHidden(true)
                }
                .foregroundStyle(DS.blue)
                .frame(minHeight: controlSize)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint(source.hint ?? "")
            .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.source(source.id))
        }
    }
}

// MARK: - Result story card

/// The pre-match expectations, the official result and the lead at each
/// scoring break, on the page or full size. Presentation only: every word and
/// number is the owner's; it keeps no state.
struct AussieRulesResultStoryCard10868: View {
    let model: AussieRulesResultStoryModel10868
    /// Full-size content: no expand control.
    var expanded: Bool = false
    var onExpand: (() -> Void)? = nil
    /// A break's exact id, for the host to hold.
    var onSelect: ((String) -> Void)? = nil
    /// Host-owned; nil shows the sources expanded.
    var notesExpanded: Binding<Bool>? = nil
    var onSource: ((AussieRulesEventPageSource10868) -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 24
    @ScaledMetric(relativeTo: .caption) private var keyDiameter: CGFloat = 10
    @ScaledMetric(relativeTo: .caption) private var gutter: CGFloat = 30
    @ScaledMetric(relativeTo: .headline) private var leadRoom: CGFloat = 24
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @ScaledMetric(relativeTo: .body) private var columnMinWidth: CGFloat = 260
    @ScaledMetric(relativeTo: .body) private var barThickness: CGFloat = 26
    @ScaledMetric(relativeTo: .body) private var trackHeight: CGFloat = 18

    private typealias Geometry = AussieRulesResultStoryGeometry10868

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            header
            let arrangements = AussieRulesResultStoryModel10868.arrangements(
                sizeClass: sizeClass, accessibilitySize: typeSize.isAccessibilitySize)
            if arrangements == [.stacked] {
                stacked
            } else {
                ViewThatFits(in: .horizontal) {
                    sideBySide
                    stacked
                }
            }
            if let takeaway = AussieRulesEventPageModel10868.readable(model.copy.takeaway) {
                Text(takeaway)
                    .font(.callout)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 12)
                    .overlay(alignment: .top) { Rectangle().fill(DS.border).frame(height: 1) }
            }
            notes
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.story)
    }

    private var stacked: some View {
        VStack(alignment: .leading, spacing: 18) {
            expectationSection
            resultSection
            breaksSection
        }
    }

    private var sideBySide: some View {
        HStack(alignment: .top, spacing: 28) {
            VStack(alignment: .leading, spacing: 14) {
                expectationSection
                resultSection
            }
            .frame(minWidth: columnMinWidth, maxWidth: .infinity, alignment: .topLeading)
            breaksSection
                .frame(minWidth: columnMinWidth, maxWidth: .infinity, alignment: .topLeading)
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                if let eyebrow = AussieRulesEventPageModel10868.readable(model.copy.eyebrow) {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let title = AussieRulesEventPageModel10868.readable(model.copy.title) {
                    Text(title)
                        .font(.title2.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.isHeader)
            if !expanded, let onExpand {
                Button(action: onExpand) {
                    Image(systemName: "arrow.up.right")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(model.copy.expandLabel)
                .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.storyExpand)
            }
        }
    }

    // MARK: Expectations

    private var expectationSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(model.copy.expectationTitle)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            let rows = model.expectation
            if rows.isEmpty {
                ownerWords(model.copy.expectationUnavailable)
            } else {
                let layout = typeSize.isAccessibilitySize
                    ? AnyLayout(VStackLayout(alignment: .leading, spacing: 14))
                    : AnyLayout(HStackLayout(alignment: .top, spacing: 18))
                layout {
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                        expectationRow(row)
                    }
                }
            }
            if let caption = AussieRulesEventPageModel10868.readable(model.copy.expectationCaption) {
                ownerWords(caption)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.expectation)
    }

    private func expectationRow(_ row: AussieRulesExpectationRow10868) -> some View {
        let accent = row.accent ?? DS.textPrimary
        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                if row.accent != nil {
                    identityKey(row.shape, accent: accent, hollow: true)
                }
                Text(row.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(FieldChaseModel10868.label(row.endpoint))
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let figure = FieldChaseModel10868.figure(row.endpoint) {
                Text(figure)
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(accent)
                    .fixedSize()
            }
            if let words = FieldChaseModel10868.words(row.endpoint) {
                ownerWords(words)
            }
            if let fraction = row.fraction {
                rail(fraction, accent: accent)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(AussieRulesResultStoryModel10868.spokenExpectation(row))
        .accessibilityValue(model.copy.railScale)
    }

    /// The tied chance on a 0–100% rail: a track and the chance's fill.
    private func rail(_ fraction: Double, accent: Color) -> some View {
        let trackColor = DS.trackBg
        return Canvas { context, size in
            guard size.width > 0, size.height > 0 else { return }
            let track = CGRect(origin: .zero, size: size)
            context.fill(Path(roundedRect: track, cornerRadius: size.height / 2), with: .color(trackColor))
            let fill = CGRect(x: 0, y: 0, width: size.width * CGFloat(fraction), height: size.height)
            if fill.width > 0 {
                context.fill(Path(roundedRect: fill, cornerRadius: size.height / 2), with: .color(accent))
            }
        }
        .frame(height: 7)
        .accessibilityHidden(true)
    }

    // MARK: Result

    private var resultSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let result = model.result {
                if let eyebrow = AussieRulesEventPageModel10868.readable(result.eyebrow) {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(result.headline)
                    .font(.title3.weight(.bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                if let detail = AussieRulesEventPageModel10868.readable(result.detail) {
                    Text(detail)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ForEach(Array(result.lines.enumerated()), id: \.offset) { _, line in
                    if let words = AussieRulesEventPageModel10868.readable(line) {
                        Text(words)
                            .font(.subheadline)
                            .monospacedDigit()
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            } else {
                ownerWords(model.copy.resultUnavailable)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.result?.spoken ?? model.copy.resultUnavailable)
        .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.result)
    }

    // MARK: Breaks

    private var breaksSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(model.copy.breaksTitle)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let caption = AussieRulesEventPageModel10868.readable(model.copy.breaksCaption) {
                ownerWords(caption)
            }
            axisWords
            let bars = model.bars
            if bars.isEmpty {
                ownerWords(model.copy.breaksEmpty)
            } else if AussieRulesResultStoryModel10868.barsRunHorizontally(accessibilitySize: typeSize.isAccessibilitySize) {
                horizontalBars(bars)
            } else {
                verticalBars(bars)
            }
            breakReadout
        }
    }

    /// The points axis's own label and the owner's direction words.
    private var axisWords: some View {
        VStack(alignment: .leading, spacing: 2) {
            if let label = AussieRulesEventPageModel10868.readable(model.story.scale.label) {
                Text(label)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let upper = AussieRulesEventPageModel10868.readable(model.story.scale.upperWords) {
                Text("↑ \(upper)")
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let lower = AussieRulesEventPageModel10868.readable(model.story.scale.lowerWords) {
                Text("↓ \(lower)")
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// One column per break on a shared axis: the owner's ticks and zero in the
    /// leading gutter and behind every column.
    private func verticalBars(_ bars: [AussieRulesStoryBar10868]) -> some View {
        let height = model.barHeight + leadRoom * 2
        return HStack(alignment: .top, spacing: 0) {
            gutterTicks
                .frame(width: gutter, height: height)
            ForEach(Array(bars.enumerated()), id: \.offset) { _, bar in
                barControl(bar) {
                    VStack(spacing: 6) {
                        verticalBarArea(bar)
                            .frame(height: height)
                        breakLabel(bar)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(model.copy.breaksGroupLabel)
        .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.breaks)
    }

    private var gutterTicks: some View {
        let ticks = model.ticks
        let room = leadRoom
        let labelColor = DS.textSecondary
        return Canvas { context, size in
            guard let frame = Geometry.plotFrame(in: size, room: room) else { return }
            for tick in ticks {
                var text = context.resolve(Text(tick.label).font(.caption2))
                text.shading = .color(labelColor)
                context.draw(text, at: CGPoint(x: size.width - 4, y: Geometry.y(tick.fraction, in: frame)),
                             anchor: .trailing)
            }
        }
        .accessibilityHidden(true)
    }

    private func verticalBarArea(_ bar: AussieRulesStoryBar10868) -> some View {
        let ticks = model.ticks
        let zero = model.zero
        let room = leadRoom
        let thickness = barThickness
        let tint = bar.accent ?? DS.textSecondary
        let gridColor = DS.border
        let zeroColor = DS.textSecondary
        let wordsColor = DS.textPrimary
        let words = bar.row.leadWords
        let plan = bar.plan
        return Canvas { context, size in
            guard let frame = Geometry.plotFrame(in: size, room: room) else { return }
            for tick in ticks {
                var line = Path()
                let y = Geometry.y(tick.fraction, in: frame)
                line.move(to: CGPoint(x: 0, y: y))
                line.addLine(to: CGPoint(x: size.width, y: y))
                context.stroke(line, with: .color(gridColor), lineWidth: 1)
            }
            if let zero {
                var line = Path()
                let y = Geometry.y(zero, in: frame)
                line.move(to: CGPoint(x: 0, y: y))
                line.addLine(to: CGPoint(x: size.width, y: y))
                context.stroke(line, with: .color(zeroColor), lineWidth: 1.5)
            }
            var label = context.resolve(Text(words).font(.headline))
            label.shading = .color(wordsColor)
            if let rect = Geometry.verticalBar(plan, in: frame, thickness: thickness) {
                context.fill(Path(roundedRect: rect, cornerRadius: 4), with: .color(tint))
                let below: Bool
                if case .bar(let start, let end) = plan { below = end < start } else { below = false }
                context.draw(label,
                             at: CGPoint(x: frame.midX, y: below ? rect.maxY + 4 : rect.minY - 4),
                             anchor: below ? .top : .bottom)
            } else if let zero {
                context.draw(label, at: CGPoint(x: frame.midX, y: Geometry.y(zero, in: frame) - 4), anchor: .bottom)
            }
        }
        .accessibilityHidden(true)
    }

    /// One full-width row per break at accessibility sizes, on the same axis.
    private func horizontalBars(_ bars: [AussieRulesStoryBar10868]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(bars.enumerated()), id: \.offset) { _, bar in
                barControl(bar) {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            breakLabel(bar)
                            Text(bar.row.leadWords)
                                .font(.headline)
                                .monospacedDigit()
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        horizontalBarArea(bar)
                            .frame(height: trackHeight)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            axisTicksBelow
                .frame(height: trackHeight)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(model.copy.breaksGroupLabel)
        .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.breaks)
    }

    private func horizontalBarArea(_ bar: AussieRulesStoryBar10868) -> some View {
        let ticks = model.ticks
        let zero = model.zero
        let tint = bar.accent ?? DS.textSecondary
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
            if let rect = Geometry.horizontalBar(plan, in: frame, thickness: size.height * 0.7) {
                context.fill(Path(roundedRect: rect, cornerRadius: 4), with: .color(tint))
            }
        }
        .accessibilityHidden(true)
    }

    private var axisTicksBelow: some View {
        let ticks = model.ticks
        let labelColor = DS.textSecondary
        return Canvas { context, size in
            guard size.width > 0 else { return }
            let frame = CGRect(origin: .zero, size: size)
            for tick in ticks {
                var text = context.resolve(Text(tick.label).font(.caption2))
                text.shading = .color(labelColor)
                context.draw(text, at: CGPoint(x: Geometry.x(tick.fraction, in: frame), y: size.height / 2),
                             anchor: .center)
            }
        }
        .accessibilityHidden(true)
    }

    /// The break's label with the leading team's key, and the owner's words
    /// for a bar that draws nothing.
    private func breakLabel(_ bar: AussieRulesStoryBar10868) -> some View {
        VStack(spacing: 2) {
            HStack(spacing: 4) {
                if let shape = bar.shape, let accent = bar.accent {
                    identityKey(shape, accent: accent, hollow: false)
                }
                Text(bar.row.label)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let words = model.barWords(bar) {
                Text(words)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// A bar that hands back its exact id with a callback; static content otherwise.
    @ViewBuilder private func barControl<Content: View>(_ bar: AussieRulesStoryBar10868,
                                                       @ViewBuilder content: () -> Content) -> some View {
        let outline = bar.isSelected ? (bar.accent ?? DS.textPrimary) : Color.clear
        if let action = AussieRulesResultStoryModel10868.selectAction(bar, onSelect: onSelect) {
            Button(action: action) {
                content()
                    .padding(.vertical, 6)
                    .frame(minHeight: controlSize)
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(outline, lineWidth: 2))
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(bar.row.spoken)
            .accessibilityHint(model.copy.selectHint ?? "")
            .accessibilityAddTraits(bar.isSelected ? .isSelected : [])
            .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.breakBar(bar.row.id))
        } else {
            content()
                .padding(.vertical, 6)
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(outline, lineWidth: 2))
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(bar.row.spoken)
                .accessibilityAddTraits(bar.isSelected ? .isSelected : [])
                .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.breakBar(bar.row.id))
        }
    }

    /// The held break's exact score and lead change, or the owner's words.
    @ViewBuilder private var breakReadout: some View {
        switch model.selection {
        case .row(let row):
            VStack(alignment: .leading, spacing: 4) {
                Text("\(row.label) · \(row.score)")
                    .font(.subheadline.weight(.semibold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                if let change = AussieRulesEventPageModel10868.readable(row.change) {
                    ownerWords(change)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.breakReadout)
        case .missing(let words):
            ownerWords(words)
                .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.breakReadout)
        case .unheld(let prompt):
            if let prompt {
                ownerWords(prompt)
                    .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.breakReadout)
            }
        }
    }

    // MARK: Notes

    @ViewBuilder private var notes: some View {
        let words = model.notes
        let report = model.reportAction(onSource: onSource)
        if !words.isEmpty || report != nil {
            if let notesExpanded {
                DisclosureGroup(isExpanded: notesExpanded) {
                    notesBody(words, report: report)
                } label: {
                    Text(model.copy.notesLabel)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .frame(minHeight: controlSize, alignment: .leading)
                }
                .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.notes)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    Text(model.copy.notesLabel)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .accessibilityAddTraits(.isHeader)
                    notesBody(words, report: report)
                }
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.notes)
            }
        }
    }

    private func notesBody(_ words: [String], report: (() -> Void)?) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(words.enumerated()), id: \.offset) { _, paragraph in
                Text(paragraph)
                    .font(.callout)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let report, let source = model.story.report {
                Button(action: report) {
                    HStack(spacing: 6) {
                        Text(source.label)
                            .font(.callout.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                        Image(systemName: "arrow.up.right")
                            .font(.callout.weight(.semibold))
                            .accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                    .frame(minHeight: controlSize)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityHint(source.hint ?? "")
                .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.report)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Shared pieces

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    /// The headline's own key shape in the team's colour: hollow for a
    /// pre-match reading, filled for an actual.
    private func identityKey(_ shape: FieldHeadlineKeyShape10868, accent: Color, hollow: Bool) -> some View {
        let diameter = keyDiameter
        let side = FieldHeadlineGeometry10868.keyFrameSide(diameter: diameter) ?? 0
        let ringFill = DS.cardBg
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

// MARK: - Page view

struct AussieRulesEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: AussieRulesEventPageInput10868
    var mode: AussieRulesEventPageMode10868 = .page
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
    /// Opens the host's reader on the result story mounted directly on the page.
    var onStoryOpen: (() -> Void)? = nil
    /// A scoring break's exact id, for the host to hold.
    var onBreakSelect: ((String) -> Void)? = nil
    /// Page-owned; nil shows the story's sources expanded.
    var storyNotesExpanded: Binding<Bool>? = nil
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

    var model: AussieRulesEventPageModel10868 { AussieRulesEventPageModel10868(input) }

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

    /// A stream card's disclosure: a write first calls the activation hook,
    /// then writes the owner's binding; a read asks for nothing.
    static func relayBinding(_ binding: Binding<Bool>?,
                             through activation: StoryStreamCardActivation10868?) -> Binding<Bool>? {
        guard let binding else { return nil }
        guard let activation else { return binding }
        return Binding(
            get: { binding.wrappedValue },
            set: { value in
                activation.request()
                binding.wrappedValue = value
            }
        )
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

    /// A page disclosure: a write first calls the hook, then writes the
    /// owner's binding; a read asks for nothing.
    static func heldBinding(_ binding: Binding<Bool>?, by interaction: (() -> Void)?) -> Binding<Bool>? {
        guard let binding else { return nil }
        guard let interaction else { return binding }
        return Binding(
            get: { binding.wrappedValue },
            set: { value in
                interaction()
                binding.wrappedValue = value
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
            input: reader ? model.readerHistory : input.history,
            onAction: Self.held(onHistoryAction, by: interaction),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: interaction),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: interaction)
        )
    }

    /// The result story mounted directly on the page: every action after the
    /// interaction hook.
    func pageStoryContent() -> AussieRulesResultStoryCard10868? {
        guard model.showsStoryDirectly, let story = model.storyModel else { return nil }
        return AussieRulesResultStoryCard10868(
            model: story, expanded: false,
            onExpand: Self.heldAction(onStoryOpen, by: onInteraction),
            onSelect: Self.held(onBreakSelect, by: onInteraction),
            notesExpanded: Self.heldBinding(storyNotesExpanded, by: onInteraction),
            onSource: Self.held(onSource, by: onInteraction))
    }

    /// The result story in a stream cell: every action after the stream's
    /// activation hook, never the page hook as well. The stream offers its own
    /// "Open full card".
    func streamStoryContent(activation: StoryStreamCardActivation10868) -> AussieRulesResultStoryCard10868? {
        guard let story = model.storyModel else { return nil }
        return AussieRulesResultStoryCard10868(
            model: story, expanded: false, onExpand: nil,
            onSelect: Self.relay(onBreakSelect, through: activation),
            notesExpanded: Self.relayBinding(storyNotesExpanded, through: activation),
            onSource: Self.relay(onSource, through: activation))
    }

    /// The full-size result story: the exact callbacks.
    func readerStoryContent() -> AussieRulesResultStoryCard10868? {
        model.readerStoryModel.map {
            AussieRulesResultStoryCard10868(model: $0, expanded: true, onExpand: nil, onSelect: onBreakSelect,
                                            notesExpanded: storyNotesExpanded, onSource: onSource)
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

    /// The page's All props entry, after the interaction hook.
    func openAllProps() {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return }
        Self.heldAction(onAllProps, by: onInteraction)?()
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            hero
            stories
            originalsPanel
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.page)
    }

    /// The headline and the history in one panel: side by side where both
    /// fit at their minimum widths, otherwise the headline above the history.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            let arrangements = AussieRulesEventPageModel10868.arrangements(
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
        .modifier(AussieRulesEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.hero)
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
                        .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.headlineUnavailable)
                }
            }
            .accessibilitySortPriority(AussieRulesEventPageModel10868.sortPriority(.headline))
            if let notice = AussieRulesEventPageModel10868.readable(input.notice) {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilitySortPriority(AussieRulesEventPageModel10868.sortPriority(.notice))
                    .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.notice)
            }
        }
        .accessibilityElement(children: .contain)
    }

    private var anchor: some View {
        historyContent(reader: false)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
            .accessibilitySortPriority(AussieRulesEventPageModel10868.sortPriority(.anchor))
            .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.anchor)
    }

    /// The owner's stream when it supplies one; otherwise the mounted story
    /// directly on the page.
    @ViewBuilder private var stories: some View {
        if let stream = input.stream {
            StoryStreamPresentationView10868(stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(input.copy.storiesLabel)
            .accessibilitySortPriority(AussieRulesEventPageModel10868.sortPriority(.story))
            .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.stories)
        } else if let story = pageStoryContent() {
            story
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(AussieRulesEventPageCardSurface10868())
                .accessibilitySortPriority(AussieRulesEventPageModel10868.sortPriority(.story))
                .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.card(.story))
        }
    }

    /// The story the owner links to this stream card, with the stream's
    /// activation hook and the owner's reason words, or the owner's
    /// unavailable words. Never a neighbour.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.storyLink(card.id), let story = streamStoryContent(activation: activation) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = AussieRulesEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                story
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(AussieRulesEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(AussieRulesEventPageCardSurface10868())
                .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.storyUnavailable)
        }
    }

    /// The originals with the owner's held-unavailable words, then All props.
    @ViewBuilder private var originalsPanel: some View {
        let allProps = model.allPropsAvailable(canOpen: onAllProps != nil)
        let chooser = chooserContent()
        if chooser != nil || allProps {
            VStack(alignment: .leading, spacing: 12) {
                if let chooser {
                    VStack(alignment: .leading, spacing: 8) {
                        if let context = AussieRulesEventPageModel10868.readable(originals?.context) {
                            Text(context)
                                .font(.caption)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        chooser
                        if AussieRulesEventPageModel10868.heldOriginalIsUnavailable(originals) {
                            Text(input.copy.heldOriginalUnavailable)
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.heldUnavailable)
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(AussieRulesEventPageCardSurface10868())
                    .accessibilityElement(children: .contain)
                    .accessibilitySortPriority(AussieRulesEventPageModel10868.sortPriority(.originals))
                    .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.originals)
                }
                if allProps, let label = input.copy.allPropsLabel {
                    allPropsEntry(label)
                        .accessibilitySortPriority(AussieRulesEventPageModel10868.sortPriority(.allProps))
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
            .modifier(AussieRulesEventPageCardSurface10868())
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.allProps)
    }

    // MARK: Full-size content and modes

    /// The same leaf and input, full size, under the compact match words. A
    /// card this phase does not show has no content.
    @ViewBuilder private func reader(_ card: AussieRulesEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                switch card {
                case .history:
                    historyContent(reader: true)
                case .story:
                    readerStoryContent()
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.card(card))
        }
    }

    /// The owner's one-line match words and, in full-size content, the About entry.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = AussieRulesEventPageModel10868.readable(input.reader.state) {
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
                .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.readerHeader)
    }

    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.catalogue)
        }
    }

    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.original)
        }
    }

    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(AussieRulesEventPageAccessibilityID10868.about)
        }
    }
}

/// The reference's white card on the page surface.
private struct AussieRulesEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
