import SwiftUI

// #10868 — the ceremony hub screen (`ceremony-hub`): one native presentation
// for an awards ceremony with two award categories, before awards day and at
// the reported final. A fan sees, in this order: the ceremony headline (the
// owner's eyebrow, the selected category's title or its reported winner, the
// owner's status words and the info control); the owner's dated-view and
// award-category choices; the selected category's anchored history — each
// captured contender's original Yes trades as separate shape-keyed marks on
// one 0–100% scale, with every contender's before-day reading beside its
// last recorded or inspected one; the owner's update readiness; then the
// owner's story stream (or the stories directly) — the points story, each
// contender's two dated chances as hollow-earlier and filled-later points on
// one horizontal 0–100% axis, and the bars story, each contender's two dated
// chances as a light earlier and a solid later vertical bar — and the
// all-originals entry. The history and each story open as full-size content
// made of the same Views and inputs; every original candidate prop in the
// owner's bounded windows, the held original's Details, that original side's
// own full-size history and the owner's Info are further content modes.
//
// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: fans compare dated chances in
// both award categories with the reported awards, inspect every independent
// original outcome, and keep their chosen card steady while retained
// probability updates arrive.
//
// REUSE DECISION. No accepted page expresses this screen whole. The field page
// (`FieldEventPagePresentation10868`) shows one field with its field-outlook
// and movement stories and no category choice; its movement leaf
// (`PreEventProbabilityShiftPresentation10868`) keys both marks hollow and
// before the start, so it cannot carry a later reading at the final. The
// match pages (`RugbyMatchEventPagePresentation10868`, the esports and hockey
// pages) show one two-team match with a headline built for physical finishes
// and a three-shape key; the qualification and golf pages are closed to their
// own leaves. Using any of them per category would drop the other category's
// story, the fourth contender shape, or the independent original sides.
//
// So only the page and reader composition and the two story faces are new.
// Every other leaf is the actual accepted View, unchanged:
//
//   • `FieldProbabilityHistoryPresentation10868` — the anchor, its full-size
//     copy and the held original side's own history, through the accepted
//     match page's `presentationCopy` / `readerPlotHeight` and the esports
//     page's exact-trade `baselineCopy`;
//   • `StoryStreamPresentationView10868` — the owner's story stream;
//   • `FieldContenderChooserPresentation10868` — every original candidate prop
//     in the owner's bounded browse windows;
//   • `OriginalMarketDetailsView9483` — the held original's Details with its
//     own recorded history and its own result;
//   • `RugbyMatchEventPageSectionsContent10868` — the owner's Info;
//   • `FieldHistoryGeometry10868.markPath` — every story mark's shape.
//
// Presentation only, from the approved `CeremonyHub.tsx`, `ceremonyHub.css`,
// `AwardSnackCards.tsx`, `AwardChanceComparison.tsx`, `AwardOriginalHistory.tsx`,
// `CeremonyArrivals.tsx` and the shared story stream and reader references.
// Their capture decoder, token joins, baseline/cutoff and latest election,
// ranking, paging, arrival frames, timers, formatters and report policy are
// NOT ported. Nothing here contains a specimen name, number, identifier,
// token, condition hash or clock.
//
// DATED READINGS. Every story slot is the owner's role words and either one
// exact retained trade — its opaque observation id, the owner's figure, its
// placement on the common 0–100% axis and its own date words — or the owner's
// unavailable words. A trade is shown as a value only while its id, figure and
// date are all readable and its placement is a valid 0...1 value; otherwise
// the slot shows the owner's unavailable words with no figure, mark or bar.
// A missing before-day reading stays unavailable: a separately dated
// observation (a first retained trade after the cutoff) is the owner's
// separate reading, shown apart under its own role and never drawn in a slot.
// Current probabilities are not shown here; no reading is called current.
// When both slots are one coherent trade — each shown as a value, with the
// same id, figure, placement and date — it shows once, under the earlier
// role. A shared id with any conflicting or invalid part keeps both slots, so
// later data is never hidden; equal figures or dates at different
// observations keep both slots too.
//
// ORIGINALS ADMISSION. The owner's originals bundle — catalogue, held
// selection, recorded context, side choices, chooser windows — and the held
// side's own history each carry the phase the owner admitted them for. Every
// consumer (the stories' explore controls, the all-originals entry and
// chooser, the side choices, Details with its recorded history and result,
// and the side history with its actions) reads one admitted value, and only
// while its phase is the page's. A bundle for another phase lends nothing:
// those surfaces show the owner's unavailable words with no stale content or
// action, while Back stays available. This is the owner's role agreement, not
// a time, result or settlement inference.
//
// THE ANCHOR. The history is the owner's input: each original's own Yes
// trades as single-point runs (marks only, no line), its shape and tint, the
// before-day trade hollow, the inspected trade ringed larger, the owner's
// windows (never filtered here), ticks, notes and inspection. While every
// contender's before-day and recorded (or inspected) readings name the same
// exact observation, a presentation copy shows the single before-day slot
// under the owner's label; otherwise the owner's readout is unchanged. A held
// observation that is no longer present shows the history's own unbound or
// absence words — never a later or nearby trade.
//
// PHASE. The page's phase is the owner's explicit `RugbyMatchEventPagePhase10868`,
// never read from a trade, a clock or a result. The headline and each story
// mount only at their own phase. Reported award facts are shown only on a
// final page from a final story; a later fact handed to an earlier phase is
// not shown. The owner's view choices hand back their exact id; they never
// change the phase here. No announcement time is inferred from any trade.
//
// OWNER-RESOLVED, NEVER DERIVED HERE: the phase, the headline, every choice,
// the history, the stories' contenders, readings, roles, dates, placements,
// ticks and reported facts, each contender's exact original, the stream and
// its card links, the reader order, the update readiness and its lock, the
// chooser's catalogue, windows and selection, the held original, its side
// choices, Details, recorded context and side history, the Info and every
// word. This layer never parses a quote or a clock, never subtracts,
// complements or normalizes chances, never treats a missing value as zero,
// never elects a baseline, a latest or a result, never sorts, ranks, pages or
// filters, and never adds an endpoint.
//
// INTERACTION. On the page — the info control, the view and category
// choices, the history's actions, inspection choices and plot taps, a directly
// mounted story's expand, original and history controls, and the
// all-originals entry — and in the catalogue and Details content — a chooser
// row or window, a category, an original side, a Details history control — the
// action calls the owner's interaction hook once, then the owner's exact
// callback with its exact value. A story inside the owner's stream calls the
// stream's activation hook instead, never the page hook as well. Full-size
// content, the side history and the Info keep the exact callbacks: their host
// already holds. The update control hands back its exact id without a hold:
// it is the owner's own release of waiting updates, available only while the
// owner reports no lock. Building or reading the view calls nothing. Without
// a callback there is no control and no hook call.
//
// READER ORDER. Full-size Previous and Next follow the owner's immutable reader
// order exactly as given: the neighbour is the adjacent entry while both
// cards are mounted and each is listed once. An empty order offers no
// neighbour; an absent, unmounted or duplicated entry offers none either, and
// nothing skips past it. Without an owner order the mounted cards keep the
// page's order. Nothing is sorted, ranked or remembered here.
//
// LAYOUT. Phone and accessibility sizes stack the headline, the choices, the
// history, the update readiness and the stories. A regular or unspecified
// width (a Mac window) places the history beside the stories while both keep
// their minimum widths, otherwise it stacks. Each story row keeps the whole
// name, its graphic at a scaled finite height, and its readings side by side
// where they fit whole, else stacked; accessibility sizes stack straight away.
// Axis labels are drawn at their actual caption size: the points' labels sit
// under the axis in a measured layout that keeps the end labels whole, and the
// bars' plot reserves the tallest and widest measured label around it, so no
// label shrinks, clips or drops at any text size. Every control drawn here
// keeps a target of at least the minimum height at every text size.
//
// The host owns the scroll, navigation, sheets, Back/Done, focus, routing,
// every held selection, window and inspection, update arrivals, holds, locks
// and subscriptions. This view keeps no state, runs no timer or animation and
// presents nothing of its own.
//
// Host binding still owed: no ceremony page input adapter exists at this
// base. The phase, headline, choices, history admission, stories, stream,
// reader order, update readiness, originals, chooser windows and Info are
// unbound owner channels (named in the handback).

// MARK: - Cards, modes, intents

/// One card the page can show full size, in the page's order. `history` is the anchor.
nonisolated enum CeremonyEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// Each contender's two dated chances as points on one horizontal 0–100% axis.
    case points
    /// Each contender's two dated chances as paired vertical bars on one 0–100% scale.
    case bars
}

/// What the host's container is showing, chosen by the host.
nonisolated enum CeremonyEventPageMode10868: Equatable {
    case page
    case reader(CeremonyEventPageCard10868)
    /// Every original candidate prop in the owner's bounded windows.
    case catalogue
    /// The held original's Details.
    case original
    /// The held original side's own full-size history.
    case sideHistory
    /// The owner's Info.
    case about
}

/// Full-size content's own controls, handed back exactly.
nonisolated enum CeremonyReaderIntent10868: Equatable {
    case back
    case previous(CeremonyEventPageCard10868)
    case next(CeremonyEventPageCard10868)
}

/// The page's blocks, in VoiceOver's reading order.
nonisolated enum CeremonyEventPageBlock10868: String, CaseIterable {
    case headline
    case notice
    case choices
    case anchor
    case update
    case stories
    case catalogue
}

// MARK: - Owner input

/// One owner choice: its exact id, visible words, optional detail ("42") and
/// the owner's selected and available state.
nonisolated struct CeremonyChoice10868: Equatable {
    let id: String
    let label: String
    var detail: String? = nil
    let isSelected: Bool
    var isAvailable: Bool = true
}

/// A group of owner choices: the award categories, or the owner's dated views.
nonisolated struct CeremonyChoiceGroup10868: Equatable {
    /// Spoken name of the group ("Award category").
    let label: String
    /// In the owner's order; never sorted here.
    let choices: [CeremonyChoice10868]
}

/// The ceremony headline in the owner's words for one phase.
nonisolated struct CeremonyHeadline10868: Equatable {
    let phase: RugbyMatchEventPagePhase10868
    /// The ceremony and its date; nil draws none.
    let eyebrow: String?
    /// The selected category before the day, or its reported winner at the final.
    let title: String
    /// "<category> winner · Reported final"; nil draws none.
    let subtitle: String?
    /// The page's status ("Current probability unavailable · dated history retained"); nil draws none.
    let status: String?
    /// The info control's spoken name; shown only with readable Info and a callback.
    let aboutLabel: String?
}

/// The owner's update readiness, verbatim.
nonisolated struct CeremonyUpdateStatus10868: Equatable {
    /// "Historical probabilities".
    let title: String
    /// "Trades through <date>"; nil draws none.
    let detail: String?
    /// "New recorded probabilities ready"; nil draws none.
    let pending: String?
    /// "Update cards"; unavailable while the owner holds a lock. Nil: no control.
    let update: FieldHistoryAction10868?
}

/// One reading's value: one exact retained trade, or the owner's words.
nonisolated enum CeremonyReadingValue10868: Equatable {
    /// The owner's opaque observation id, its figure ("52.7%"), its placement
    /// on the common 0–100% axis (0...1) and that trade's own date words.
    case recorded(observationID: String, figure: String, placement: Double, date: String)
    /// No captured reading for this role ("No captured pre-day trade").
    case unavailable(words: String)
}

/// One dated reading under the owner's role words ("Before awards day").
nonisolated struct CeremonyDatedReading10868: Equatable {
    let role: String
    let value: CeremonyReadingValue10868
}

/// One contender in a story, in the owner's order.
struct CeremonyContender10868: Equatable {
    /// The whole name, shown and spoken verbatim.
    let name: String
    /// The same shape the history keys this contender with.
    let shape: FieldHistoryShape10868
    let tint: Color
    /// Drawn hollow (points) or light (bars).
    let earlier: CeremonyDatedReading10868
    /// Drawn filled (points) or solid (bars).
    let later: CeremonyDatedReading10868
    /// A separately dated observation outside the comparison (for example a
    /// first retained trade after the cutoff). Shown under its own role and
    /// never drawn in, or substituted for, a slot.
    var separate: CeremonyDatedReading10868? = nil
    /// The separately reported award fact ("Won"); shown on a final page only.
    var result: String? = nil
    /// The exact original the contender's explore control opens.
    let selection: OriginalMarketDetails9483.Selection?
}

/// One owner tick on the common 0–100% axis.
nonisolated struct CeremonyAxisTick10868: Equatable {
    /// 0...1.
    let value: Double
    /// Verbatim ("50%").
    let label: String
}

/// A story's words, verbatim.
nonisolated struct CeremonyStoryCopy10868: Equatable {
    let eyebrow: String?
    let title: String
    /// What hollow and filled (or light and solid) mean in this phase; nil draws none.
    let key: String?
    /// Spoken name of the graphic.
    let graphicLabel: String
    /// Further owner lines under the rows ("Current probability unavailable").
    let notes: [String]
    /// A contender's explore control; nil draws none.
    let openLabel: String?
    /// The category history control; nil draws none.
    let historyLabel: String?
    let expandLabel: String
    /// Shown beside a contender whose original does not open.
    let originalUnavailable: String
    /// Shown in a slot whose recorded reading is incomplete or invalid.
    let readingUnavailable: String
    /// Shown when no contender is supplied.
    let empty: String
}

/// One comparison story, authored by the owner for one phase.
struct CeremonyComparisonStory10868: Equatable {
    let phase: RugbyMatchEventPagePhase10868
    /// The owner's category id, handed back by the history control.
    let categoryID: String
    /// In the owner's order; never sorted or capped here.
    let contenders: [CeremonyContender10868]
    let ticks: [CeremonyAxisTick10868]
    let copy: CeremonyStoryCopy10868
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct CeremonyEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: CeremonyEventPageCard10868
    /// The owner's words for why this story is here; nil draws none.
    var reason: String? = nil
}

nonisolated struct CeremonyEventPageCopy10868: Equatable {
    /// Spoken name of the stories group.
    let storiesLabel: String
    /// A stream cell whose id names no single story this phase mounts.
    let storyUnavailable: String
    /// Shown where the headline cannot mount for this phase.
    let headlineUnavailable: String
    /// Shown in a full-size card this phase does not show.
    let readerUnavailable: String
    /// The held original does not open in this update.
    let heldOriginalUnavailable: String
    /// The held side's own history does not match the held original.
    let sideHistoryUnavailable: String
    /// No chooser input for the catalogue.
    let catalogueUnavailable: String
    /// The owner's originals were admitted for another phase.
    let originalsUnavailable: String
    /// "All <count> original props"; nil draws no entry.
    let catalogueLabel: String?
    /// Spoken name of the side choices ("Selected original outcome").
    let sidesLabel: String
    let backLabel: String
    let previousLabel: String
    let nextLabel: String
    let historyName: String
    let pointsName: String
    let barsName: String
}

struct CeremonyEventPageInput10868: Equatable {
    let phase: RugbyMatchEventPagePhase10868
    /// "Retained trades replayed · delivery timing simulated"; nil draws none.
    var notice: String? = nil
    let headline: CeremonyHeadline10868
    /// The owner's dated views; nil draws none.
    var views: CeremonyChoiceGroup10868? = nil
    /// The award categories; nil draws none.
    let categories: CeremonyChoiceGroup10868?
    /// The owner's update readiness; nil draws none.
    var update: CeremonyUpdateStatus10868? = nil
    /// The owner's one-line words above full-size content.
    let reader: RugbyMatchEventPageReaderHeader10868
    /// The selected category's history, exactly as admitted.
    let history: FieldHistoryInput10868
    /// The owner's full-size plot height; never shorter than the page's.
    var readerPlotHeight: CGFloat? = nil
    var points: CeremonyComparisonStory10868? = nil
    var bars: CeremonyComparisonStory10868? = nil
    /// The owner's stream; nil mounts the stories directly.
    var stream: StoryStreamPresentation10868? = nil
    var stories: [CeremonyEventPageStory10868] = []
    /// The owner's immutable full-size sequence; nil keeps the page's order.
    var readerOrder: [CeremonyEventPageCard10868]? = nil
    let about: RugbyMatchEventPageAbout10868?
    let copy: CeremonyEventPageCopy10868
}

/// One owner side choice in Details ("Yes", "No"), by exact selection.
struct CeremonySideChoice10868: Equatable {
    let label: String
    let selection: OriginalMarketDetails9483.Selection
}

/// The held original side's own full-size history.
struct CeremonySideHistory10868: Equatable {
    /// The phase the owner admitted this history for.
    let phase: RugbyMatchEventPagePhase10868
    /// The exact selection this history was admitted for.
    let selection: OriginalMarketDetails9483.Selection
    /// The owner's mapping of that side to its one series.
    let seriesID: String
    let history: FieldHistoryInput10868
}

/// The owner's originals: the catalogue, the held selection and its content,
/// admitted together for one phase.
struct CeremonyEventPageOriginals10868 {
    /// The phase the owner admitted this bundle for. Every consumer reads the
    /// bundle only while this equals the page's phase.
    let phase: RugbyMatchEventPagePhase10868
    let catalogue: OriginalMarketDetails9483.Catalogue?
    let selection: OriginalMarketDetails9483.Selection?
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    /// The held original's side choices, in the owner's order.
    var sides: [CeremonySideChoice10868] = []
    var sideHistory: CeremonySideHistory10868? = nil
    /// Every original candidate prop in the owner's bounded windows.
    var chooser: FieldChooserInput10868? = nil
    let tint: Color
}

nonisolated enum CeremonyEventPageAccessibilityID10868 {
    static let page = "ceremonyEventPage10868.page"
    static let headline = "ceremonyEventPage10868.headline"
    static let headlineUnavailable = "ceremonyEventPage10868.headline.unavailable"
    static let info = "ceremonyEventPage10868.headline.info"
    static let notice = "ceremonyEventPage10868.notice"
    static let views = "ceremonyEventPage10868.views"
    static let categories = "ceremonyEventPage10868.categories"
    static let anchor = "ceremonyEventPage10868.anchor"
    static let update = "ceremonyEventPage10868.update"
    static let updateControl = "ceremonyEventPage10868.update.control"
    static let stories = "ceremonyEventPage10868.stories"
    static let storyUnavailable = "ceremonyEventPage10868.story.unavailable"
    static let catalogueEntry = "ceremonyEventPage10868.catalogue.entry"
    static let catalogue = "ceremonyEventPage10868.catalogue"
    static let catalogueUnavailable = "ceremonyEventPage10868.catalogue.unavailable"
    static let originalsUnavailable = "ceremonyEventPage10868.originals.unavailable"
    static let original = "ceremonyEventPage10868.original"
    static let sides = "ceremonyEventPage10868.original.sides"
    static let heldUnavailable = "ceremonyEventPage10868.original.unavailable"
    static let sideHistory = "ceremonyEventPage10868.sideHistory"
    static let sideHistoryUnavailable = "ceremonyEventPage10868.sideHistory.unavailable"
    static let about = "ceremonyEventPage10868.about"
    static let readerHeader = "ceremonyEventPage10868.readerHeader"
    static let readerInfo = "ceremonyEventPage10868.readerHeader.info"
    static let readerUnavailable = "ceremonyEventPage10868.reader.unavailable"
    static let readerBack = "ceremonyEventPage10868.reader.back"
    static let readerPrevious = "ceremonyEventPage10868.reader.previous"
    static let readerNext = "ceremonyEventPage10868.reader.next"
    static func card(_ card: CeremonyEventPageCard10868) -> String { "ceremonyEventPage10868.card.\(card.rawValue)" }
    static func expand(_ card: CeremonyEventPageCard10868) -> String { "ceremonyEventPage10868.expand.\(card.rawValue)" }
    static func history(_ card: CeremonyEventPageCard10868) -> String { "ceremonyEventPage10868.history.\(card.rawValue)" }
    static func open(_ card: CeremonyEventPageCard10868, _ index: Int) -> String {
        "ceremonyEventPage10868.open.\(card.rawValue).\(index)"
    }
    static func row(_ card: CeremonyEventPageCard10868, _ index: Int) -> String {
        "ceremonyEventPage10868.row.\(card.rawValue).\(index)"
    }
    static func choice(_ group: String, _ index: Int) -> String { "ceremonyEventPage10868.\(group).\(index)" }
    static func side(_ index: Int) -> String { "ceremonyEventPage10868.original.side.\(index)" }
}

// MARK: - Story geometry

/// One reading as a story shows it: its role, mark style, figure or words,
/// own date, placement and observation.
nonisolated struct CeremonyComparisonSlot10868: Equatable {
    let role: String
    /// Hollow for the earlier reading, filled for the later one.
    let style: FieldHistoryMarkStyle10868
    /// The owner's figure, or its unavailable words.
    let text: String
    let isValue: Bool
    /// The trade's own date words; nil for unavailable words.
    let date: String?
    /// A valid 0...1 placement, or nil: no mark and no bar. Never clamped.
    let placement: Double?
    /// The exact observation; nil for unavailable words.
    let observationID: String?

    /// The role, then the figure with its own date, or the owner's words.
    var spoken: String {
        if isValue, let date { return "\(role) \(text), \(date)" }
        return "\(role): \(text)"
    }
}

/// One drawn bar: its slot's column, style and height fraction.
nonisolated struct CeremonyBarPlan10868: Equatable {
    let column: Int
    let style: FieldHistoryMarkStyle10868
    /// Nil: no reading, drawn as an empty dashed marker — never a zero bar.
    let fraction: Double?
}

/// Pure geometry and slot rules for both story faces.
nonisolated enum CeremonyComparisonGeometry10868 {
    /// A placement on the common axis: finite and inside 0...1. Never clamped.
    static func placement(_ value: Double) -> Double? {
        value.isFinite && value >= 0 && value <= 1 ? value : nil
    }

    static func readable(_ words: String?) -> String? { RugbyMatchEventPageModel10868.readable(words) }

    /// A recorded reading that may be shown as a value: its observation id,
    /// figure and own date all readable, and its placement a valid 0...1
    /// value. Nothing is parsed, formatted or repaired.
    static func isQualified(_ value: CeremonyReadingValue10868) -> Bool {
        guard case .recorded(let id, let figure, let placement, let date) = value else { return false }
        return readable(id) != nil && readable(figure) != nil && readable(date) != nil && Self.placement(placement) != nil
    }

    /// One reading under its role and style: a value only while it is
    /// qualified; otherwise the owner's words — no figure, mark or bar.
    static func slot(_ reading: CeremonyDatedReading10868, style: FieldHistoryMarkStyle10868,
                     unreadable: String) -> CeremonyComparisonSlot10868 {
        switch reading.value {
        case .recorded(let id, let figure, let placement, let date):
            guard isQualified(reading.value) else {
                return CeremonyComparisonSlot10868(role: reading.role, style: style, text: unreadable, isValue: false,
                                                   date: nil, placement: nil, observationID: nil)
            }
            return CeremonyComparisonSlot10868(role: reading.role, style: style, text: figure, isValue: true,
                                               date: date, placement: placement, observationID: id)
        case .unavailable(let words):
            return CeremonyComparisonSlot10868(role: reading.role, style: style, text: readable(words) ?? unreadable,
                                               isValue: false, date: nil, placement: nil, observationID: nil)
        }
    }

    /// Both readings are one coherent trade: each qualified, with the same
    /// observation id, figure, placement and date. A shared id with any
    /// conflicting or invalid part is not one trade here, and equal figures,
    /// dates or placements at different observations never are.
    static func sameTrade(_ earlier: CeremonyDatedReading10868, _ later: CeremonyDatedReading10868) -> Bool {
        guard isQualified(earlier.value), isQualified(later.value),
              case .recorded(let a, let figureA, let placementA, let dateA) = earlier.value,
              case .recorded(let b, let figureB, let placementB, let dateB) = later.value else { return false }
        return a == b && figureA == figureB && placementA == placementB && dateA == dateB
    }

    /// The earlier slot, then the later one; one coherent trade shows once,
    /// under the earlier role and style. Conflicting readings both stay.
    static func slots(earlier: CeremonyDatedReading10868, later: CeremonyDatedReading10868,
                      unreadable: String) -> [CeremonyComparisonSlot10868] {
        let first = slot(earlier, style: .hollow, unreadable: unreadable)
        guard !sameTrade(earlier, later) else { return [first] }
        return [first, slot(later, style: .filled, unreadable: unreadable)]
    }

    /// The owner's ticks that lie on the axis with readable words, in the
    /// owner's order. Nothing is added.
    static func ticks(_ ticks: [CeremonyAxisTick10868]) -> [CeremonyAxisTick10868] {
        ticks.filter { placement($0.value) != nil && readable($0.label) != nil }
    }

    /// A placement's horizontal position inside the track rect.
    static func x(_ placement: Double, in rect: CGRect) -> CGFloat {
        rect.minX + CGFloat(placement) * rect.width
    }

    /// A placement's vertical position inside the bar rect (0 at the bottom).
    static func y(_ placement: Double, in rect: CGRect) -> CGFloat {
        rect.maxY - CGFloat(placement) * rect.height
    }

    /// The bars one contender draws, one column per slot in the slots' order.
    static func bars(_ slots: [CeremonyComparisonSlot10868]) -> [CeremonyBarPlan10868] {
        slots.enumerated().map { CeremonyBarPlan10868(column: $0.offset, style: $0.element.style, fraction: $0.element.placement) }
    }

    /// The centre of a column when `count` columns share the rect equally.
    static func columnCenter(_ column: Int, count: Int, in rect: CGRect) -> CGFloat? {
        guard count > 0, column >= 0, column < count else { return nil }
        let width = rect.width / CGFloat(count)
        return rect.minX + width * (CGFloat(column) + 0.5)
    }

    /// A bar's rect: centred in its column, rising from the axis floor to its
    /// placement. A real zero is a zero-height rect, still a value.
    static func barRect(_ bar: CeremonyBarPlan10868, count: Int, in rect: CGRect, maxWidth: CGFloat) -> CGRect? {
        guard let fraction = bar.fraction, let center = columnCenter(bar.column, count: count, in: rect) else { return nil }
        let width = min(maxWidth, rect.width / CGFloat(max(count, 1)) * 0.6)
        let top = y(fraction, in: rect)
        return CGRect(x: center - width / 2, y: top, width: width, height: rect.maxY - top)
    }

    /// The light earlier bar and the solid later one.
    static func barOpacity(_ style: FieldHistoryMarkStyle10868) -> Double {
        style == .hollow ? 0.35 : 1
    }

    // MARK: Axis labels

    /// Space between a vertical-axis label and the plot.
    static let axisLabelGap: CGFloat = 6
    /// Space kept between any axis label and the canvas edge.
    static let axisLabelMargin: CGFloat = 2

    /// The bars' plot inside its canvas. Every tick label is centred on its
    /// line, so half the tallest measured label (and a margin) is reserved
    /// above the 100% line and below the 0% line, and the widest measured
    /// label (and the gap) on the leading edge — never less than the owner's
    /// column. Labels are measured at their actual text size, never shrunk.
    static func barPlotRect(in size: CGSize, label: CGSize, minimumLeading: CGFloat) -> CGRect {
        let vertical = label.height / 2 + axisLabelMargin
        let leading = max(minimumLeading, label.width + axisLabelGap + axisLabelMargin)
        return CGRect(x: leading, y: vertical, width: max(size.width - leading - axisLabelMargin, 0),
                      height: max(size.height - vertical * 2, 0))
    }

    /// A vertical-axis label's frame: trailing at the gap before the plot,
    /// centred on its value's line.
    static func axisLabelFrame(_ value: Double, label: CGSize, plot: CGRect) -> CGRect {
        let center = y(value, in: plot)
        return CGRect(x: plot.minX - axisLabelGap - label.width, y: center - label.height / 2,
                      width: label.width, height: label.height)
    }

    /// A horizontal-axis label's leading edge: its anchor moves with its value
    /// (its leading edge at 0, its centre at the middle, its trailing edge at
    /// 100%), kept inside the bounds so an end label stays whole.
    static func labelOrigin(_ value: Double, width: CGFloat, track: CGRect, bounds: CGRect) -> CGFloat {
        let anchored = x(value, in: track) - CGFloat(value) * width
        return min(max(anchored, bounds.minX), max(bounds.maxX - width, bounds.minX))
    }
}

// MARK: - Story model

/// One contender as a story shows it.
struct CeremonyContenderPlan10868: Equatable {
    let contender: CeremonyContender10868
    let slots: [CeremonyComparisonSlot10868]
    /// The separately dated observation, words only; never placed.
    let separate: CeremonyComparisonSlot10868?
    /// The reported award fact on a final page from a final story only.
    let result: String?
    /// The exact original, only while it opens alone in the owner's catalogue
    /// and is named once on this story.
    let opens: OriginalMarketDetails9483.Selection?
}

/// One story over the owner's catalogue at the page's phase.
struct CeremonyStoryModel10868: Equatable {
    let story: CeremonyComparisonStory10868
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The page's phase.
    let phase: RugbyMatchEventPagePhase10868

    var copy: CeremonyStoryCopy10868 { story.copy }

    /// Reported facts belong to a final page and a final story only.
    var showsResult: Bool { phase == .final && story.phase == .final }

    var ticks: [CeremonyAxisTick10868] { CeremonyComparisonGeometry10868.ticks(story.ticks) }

    /// Selections named more than once on this story open nothing.
    var repeated: [OriginalMarketDetails9483.Selection] {
        let all = story.contenders.compactMap(\.selection)
        var found: [OriginalMarketDetails9483.Selection] = []
        for selection in all where all.filter({ $0 == selection }).count > 1 && !found.contains(selection) {
            found.append(selection)
        }
        return found
    }

    func opens(_ contender: CeremonyContender10868) -> OriginalMarketDetails9483.Selection? {
        guard let selection = contender.selection, !repeated.contains(selection),
              OriginalMarketDetails9483.content(catalogue: catalogue, selection: selection) != nil else { return nil }
        return selection
    }

    func plan(_ contender: CeremonyContender10868) -> CeremonyContenderPlan10868 {
        let unreadable = copy.readingUnavailable
        let separate: CeremonyComparisonSlot10868? = contender.separate.map { reading in
            let shown = CeremonyComparisonGeometry10868.slot(reading, style: .filled, unreadable: unreadable)
            return CeremonyComparisonSlot10868(role: shown.role, style: shown.style, text: shown.text, isValue: shown.isValue,
                                               date: shown.date, placement: nil, observationID: shown.observationID)
        }
        return CeremonyContenderPlan10868(
            contender: contender,
            slots: CeremonyComparisonGeometry10868.slots(earlier: contender.earlier, later: contender.later,
                                                         unreadable: unreadable),
            separate: separate,
            result: showsResult ? CeremonyComparisonGeometry10868.readable(contender.result) : nil,
            opens: opens(contender))
    }

    var plans: [CeremonyContenderPlan10868] { story.contenders.map { plan($0) } }

    /// A contender in words: whole name, result, each slot with its own date,
    /// then the separate observation.
    static func spoken(_ plan: CeremonyContenderPlan10868) -> String {
        var parts: [String] = [plan.contender.name]
        if let result = plan.result { parts.append(result) }
        for slot in plan.slots { parts.append(slot.spoken) }
        if let separate = plan.separate { parts.append(separate.spoken) }
        return parts.joined(separator: ". ")
    }

    /// The graphic in words: its name and every contender.
    var spokenGraphic: String {
        var parts: [String] = [copy.graphicLabel]
        for plan in plans { parts.append(Self.spoken(plan)) }
        if plans.isEmpty { parts.append(copy.empty) }
        return parts.joined(separator: ". ")
    }

    /// The contender's explore control: its exact original, with a callback
    /// and readable words. Otherwise no control.
    func openAction(_ plan: CeremonyContenderPlan10868,
                    _ onOpen: ((OriginalMarketDetails9483.Selection) -> Void)?) -> (() -> Void)? {
        guard let onOpen, let selection = plan.opens, CeremonyComparisonGeometry10868.readable(copy.openLabel) != nil
        else { return nil }
        return { onOpen(selection) }
    }

    /// Whether the contender's original is named but does not open.
    func originalIsUnavailable(_ plan: CeremonyContenderPlan10868) -> Bool {
        plan.contender.selection != nil && plan.opens == nil
    }

    /// The category history control: the owner's exact category id.
    func historyAction(_ onHistory: ((String) -> Void)?) -> (() -> Void)? {
        guard let onHistory, CeremonyComparisonGeometry10868.readable(story.categoryID) != nil,
              CeremonyComparisonGeometry10868.readable(copy.historyLabel) != nil else { return nil }
        let id = story.categoryID
        return { onHistory(id) }
    }
}

// MARK: - Page model

/// Which leaves the page mounts and what each hands back, resolved once per input.
struct CeremonyEventPageModel10868: Equatable {
    let input: CeremonyEventPageInput10868

    init(_ input: CeremonyEventPageInput10868) {
        self.input = input
    }

    static func readable(_ words: String?) -> String? { RugbyMatchEventPageModel10868.readable(words) }

    // MARK: Phase gates

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: CeremonyHeadline10868? {
        input.headline.phase == input.phase ? input.headline : nil
    }

    /// A story at the page's own phase. A story from another phase is not mounted.
    func story(_ card: CeremonyEventPageCard10868) -> CeremonyComparisonStory10868? {
        let story: CeremonyComparisonStory10868?
        switch card {
        case .history: story = nil
        case .points: story = input.points
        case .bars: story = input.bars
        }
        guard let story, story.phase == input.phase else { return nil }
        return story
    }

    func storyModel(_ card: CeremonyEventPageCard10868,
                    catalogue: OriginalMarketDetails9483.Catalogue?) -> CeremonyStoryModel10868? {
        story(card).map { CeremonyStoryModel10868(story: $0, catalogue: catalogue, phase: input.phase) }
    }

    func isMounted(_ card: CeremonyEventPageCard10868) -> Bool {
        card == .history || story(card) != nil
    }

    var mountedCards: [CeremonyEventPageCard10868] {
        CeremonyEventPageCard10868.allCases.filter(isMounted)
    }

    // MARK: Reader order

    /// The full-size sequence: the owner's order exactly as supplied, else the
    /// mounted cards in the page's order.
    var readerSequence: [CeremonyEventPageCard10868] {
        input.readerOrder ?? mountedCards
    }

    /// A card's one position; none when absent or listed more than once.
    static func uniqueIndex(of card: CeremonyEventPageCard10868, in sequence: [CeremonyEventPageCard10868]) -> Int? {
        let indices = sequence.indices.filter { sequence[$0] == card }
        return indices.count == 1 ? indices[0] : nil
    }

    /// The card exactly `offset` places away while both are mounted and each
    /// is listed once. Nothing past either end, and no skipping.
    func neighbour(of card: CeremonyEventPageCard10868, offset: Int) -> CeremonyEventPageCard10868? {
        let sequence = readerSequence
        guard isMounted(card), let index = Self.uniqueIndex(of: card, in: sequence) else { return nil }
        let target = index + offset
        guard sequence.indices.contains(target) else { return nil }
        let candidate = sequence[target]
        guard isMounted(candidate), Self.uniqueIndex(of: candidate, in: sequence) != nil else { return nil }
        return candidate
    }

    func cardName(_ card: CeremonyEventPageCard10868) -> String {
        switch card {
        case .history: input.copy.historyName
        case .points: input.copy.pointsName
        case .bars: input.copy.barsName
        }
    }

    /// The owner's link a stream card id names: exactly one link, to a mounted story.
    func storyLink(_ cardID: String) -> CeremonyEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    var showsCardsDirectly: Bool { input.stream == nil }

    // MARK: History

    /// True only while the owner's readout is before-day beside recorded and,
    /// for every exactly identified contender, both readings are bound to the
    /// same observation id and the before-day one shows a figure.
    static func collapsesRecorded(_ history: FieldHistoryInput10868) -> Bool {
        guard case .beforeAndRecorded = history.readout, !history.series.isEmpty else { return false }
        return history.series.allSatisfy { series in
            guard FieldHistoryGeometry10868.isExactlyIdentified(series, in: history),
                  case .observation(let before, _, _) = series.before,
                  case .observation(let recorded, _, _) = series.recorded,
                  case .figure = FieldHistoryGeometry10868.display(series.before, of: series, in: history)
            else { return false }
            return before == recorded
        }
    }

    /// The owner's history with an exact-trade duplicate pair shown once under
    /// the owner's before-day label — recorded here, inspected through the
    /// esports page's own rule; otherwise unchanged.
    static func collapsedHistory(_ history: FieldHistoryInput10868) -> FieldHistoryInput10868 {
        guard collapsesRecorded(history), case .beforeAndRecorded(let beforeLabel, _) = history.readout else {
            return EsportsEventPageModel10868.baselineCopy(history)
        }
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

    /// The history on the page: the collapse copy at the owner's height.
    var presentedHistory: FieldHistoryInput10868 {
        let history = Self.collapsedHistory(input.history)
        return RugbyMatchEventPageModel10868.presentationCopy(
            history, plotHeight: history.plotHeight, expand: history.expand, showsKey: history.showsKey)
    }

    /// The history full size: the same input at the owner's full-size height
    /// (never shorter than the page's), without its own expand control.
    var readerHistory: FieldHistoryInput10868 {
        let history = Self.collapsedHistory(input.history)
        return RugbyMatchEventPageModel10868.presentationCopy(
            history,
            plotHeight: RugbyMatchEventPageModel10868.readerPlotHeight(input.readerPlotHeight, history: history.plotHeight),
            expand: nil, showsKey: history.showsKey)
    }

    // MARK: Choices, Info and update

    /// A choice's exact id: nonblank, carried once in its group, available,
    /// with a callback. Otherwise static.
    static func liveID(_ choice: CeremonyChoice10868, in group: CeremonyChoiceGroup10868, hasCallback: Bool) -> String? {
        guard hasCallback, choice.isAvailable, readable(choice.id) != nil,
              group.choices.filter({ $0.id == choice.id }).count == 1 else { return nil }
        return choice.id
    }

    /// The owner's Info, when it carries readable words.
    var about: RugbyMatchEventPageAbout10868? {
        guard let about = input.about,
              Self.readable(about.title) != nil || about.sections.contains(where: RugbyMatchEventPageModel10868.hasWords)
        else { return nil }
        return about
    }

    /// The info control: readable Info, readable words and a callback.
    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil && Self.readable(input.headline.aboutLabel) != nil
    }

    /// The update control's exact id: available, nonblank, with a callback.
    func updateID(hasCallback: Bool) -> String? {
        guard hasCallback, let update = input.update?.update, update.isAvailable, Self.readable(update.id) != nil,
              Self.readable(update.label) != nil else { return nil }
        return update.id
    }

    /// The update control: a button with its exact id; with a callback but
    /// no live id (the owner's lock, a blank or missing id) the owner's words
    /// stay visible without an action; without a callback, nothing.
    func updateState(hasCallback: Bool) -> FieldHistoryControlState10868 {
        guard let update = input.update?.update, Self.readable(update.label) != nil else { return .hidden }
        if let id = updateID(hasCallback: hasCallback) { return .live(id: id) }
        return hasCallback ? .shownStatic : .hidden
    }

    /// The all-originals entry: readable words, a callback and an admitted
    /// chooser to open.
    func catalogueAvailable(canOpen: Bool, originals: CeremonyEventPageOriginals10868?) -> Bool {
        canOpen && Self.readable(input.copy.catalogueLabel) != nil && admitted(originals)?.chooser != nil
    }

    // MARK: Originals

    /// The owner's originals only while admitted for this page's phase: the
    /// one value every story open, chooser, side choice, Details, recorded
    /// history and side history reads. A bundle for another phase lends
    /// nothing — no grade, history or action.
    func admitted(_ originals: CeremonyEventPageOriginals10868?) -> CeremonyEventPageOriginals10868? {
        guard let originals, originals.phase == input.phase else { return nil }
        return originals
    }

    /// The owner supplied originals, but for another phase.
    func originalsAreForAnotherPhase(_ originals: CeremonyEventPageOriginals10868?) -> Bool {
        originals != nil && admitted(originals) == nil
    }

    /// The held side's own history: inside the admitted bundle, admitted for
    /// this phase and for exactly the held selection.
    func sideHistory(_ originals: CeremonyEventPageOriginals10868?) -> FieldHistoryInput10868? {
        guard let admitted = admitted(originals), admitted.sideHistory?.phase == input.phase else { return nil }
        return Self.exactSideHistory(admitted)
    }

    /// The held selection opens nothing in this update: it stays the owner's
    /// and shows the owner's words, never a neighbour.
    static func heldOriginalIsUnavailable(_ originals: CeremonyEventPageOriginals10868?) -> Bool {
        guard let originals, let selection = originals.selection else { return false }
        return OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: selection) == nil
    }

    /// A side choice is a control while its exact selection opens alone in
    /// the catalogue and is listed once among the sides.
    static func sideOpens(_ side: CeremonySideChoice10868, in originals: CeremonyEventPageOriginals10868) -> Bool {
        readable(side.label) != nil
            && originals.sides.filter({ $0.selection == side.selection }).count == 1
            && OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: side.selection) != nil
    }

    static func sideIsSelected(_ side: CeremonySideChoice10868, in originals: CeremonyEventPageOriginals10868) -> Bool {
        originals.selection == side.selection
    }

    /// The held side's own history: admitted for exactly the held selection,
    /// which opens, with exactly one series carrying the owner's series id.
    /// Otherwise nothing — never another side's history.
    static func exactSideHistory(_ originals: CeremonyEventPageOriginals10868?) -> FieldHistoryInput10868? {
        guard let originals, let held = originals.selection, let side = originals.sideHistory,
              side.selection == held, readable(side.seriesID) != nil,
              OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: held) != nil,
              side.history.series.count == 1, let series = side.history.series.first, series.id == side.seriesID,
              FieldHistoryGeometry10868.isExactlyIdentified(series, in: side.history)
        else { return nil }
        return side.history
    }

    // MARK: Layout and reading order

    static let readingOrder: [CeremonyEventPageBlock10868] = [.headline, .notice, .choices, .anchor, .update, .stories, .catalogue]

    /// VoiceOver reads the same order in every arrangement.
    static func sortPriority(_ block: CeremonyEventPageBlock10868) -> Double {
        Double(readingOrder.count - (readingOrder.firstIndex(of: block) ?? readingOrder.count))
    }

    /// Story readings sit side by side where they fit; accessibility sizes stack.
    static func readingArrangements(accessibilitySize: Bool) -> [RugbyMatchEventPageArrangement10868] {
        accessibilitySize ? [.stacked] : [.sideBySide, .stacked]
    }
}

// MARK: - Shared drawing pieces

private struct CeremonyCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}

/// A contender's identity: its own shape in its tint, a mark without a line —
/// as both stories and the history's single-trade marks draw it.
struct CeremonyIdentityGlyph10868: View {
    let shape: FieldHistoryShape10868
    let tint: Color

    @ScaledMetric(relativeTo: .caption) private var radius: CGFloat = 5

    var body: some View {
        Canvas { context, size in
            let center = CGPoint(x: size.width / 2, y: size.height / 2)
            context.fill(FieldHistoryGeometry10868.markPath(shape, at: center, radius: radius), with: .color(tint))
        }
        .frame(width: radius * 3, height: radius * 3)
        .accessibilityHidden(true)
    }
}

/// A story's heading: eyebrow, title and the expand control.
private struct CeremonyStoryHeader10868: View {
    let copy: CeremonyStoryCopy10868
    let card: CeremonyEventPageCard10868
    var onExpand: (() -> Void)?

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                if let eyebrow = CeremonyComparisonGeometry10868.readable(copy.eyebrow) {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(copy.title)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
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
                .accessibilityLabel(copy.expandLabel)
                .accessibilityIdentifier(CeremonyEventPageAccessibilityID10868.expand(card))
            }
        }
    }
}

/// One reading: its role, then the figure with its own date, or the owner's words.
private struct CeremonySlotView10868: View {
    let slot: CeremonyComparisonSlot10868
    let figureSize: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(slot.role)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if slot.isValue {
                Text(slot.text)
                    .font(.system(size: figureSize, weight: .semibold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            } else {
                Text(slot.text)
                    .font(.callout.weight(.medium))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let date = slot.date {
                Text(date)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(slot.spoken)
    }
}

/// A contender's readings in equal columns where every figure fits whole,
/// otherwise one under another; accessibility sizes stack straight away.
private struct CeremonySlotsRow10868: View {
    let slots: [CeremonyComparisonSlot10868]
    let figureSize: CGFloat

    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        if CeremonyEventPageModel10868.readingArrangements(accessibilitySize: typeSize.isAccessibilitySize).contains(.sideBySide) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 12) { columns }
                VStack(alignment: .leading, spacing: 10) { columns }
            }
        } else {
            VStack(alignment: .leading, spacing: 10) { columns }
        }
    }

    @ViewBuilder private var columns: some View {
        ForEach(Array(slots.enumerated()), id: \.offset) { _, slot in
            CeremonySlotView10868(slot: slot, figureSize: figureSize)
        }
    }
}

/// The identity glyph, the whole name and, at the final, the reported fact.
private struct CeremonyNameLine10868: View {
    let plan: CeremonyContenderPlan10868

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                CeremonyIdentityGlyph10868(shape: plan.contender.shape, tint: plan.contender.tint)
                Text(plan.contender.name)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let result = plan.result {
                Text(result)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// The separately dated observation, in words under its own role. Never drawn.
private struct CeremonySeparateLine10868: View {
    let slot: CeremonyComparisonSlot10868?

    var body: some View {
        if let slot {
            Text(slot.spoken)
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// A full-width text control; nothing without an action.
private struct CeremonyLink10868: View {
    let label: String?
    let id: String
    var action: (() -> Void)?

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        if let action, let label = CeremonyComparisonGeometry10868.readable(label) {
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

/// A contender's explore control, or the owner's words when its original does not open.
private struct CeremonyOriginalControl10868: View {
    let model: CeremonyStoryModel10868
    let plan: CeremonyContenderPlan10868
    let onOpen: ((OriginalMarketDetails9483.Selection) -> Void)?
    let id: String

    var body: some View {
        if let action = model.openAction(plan, onOpen) {
            CeremonyLink10868(label: model.copy.openLabel, id: id, action: action)
                .accessibilityHint(plan.contender.name)
        } else if model.originalIsUnavailable(plan) {
            Text(model.copy.originalUnavailable)
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// The story's key and notes, verbatim.
private struct CeremonyStoryLines10868: View {
    let lines: [String]

    var body: some View {
        ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
            if let words = CeremonyComparisonGeometry10868.readable(line) {
                Text(words)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

// MARK: - Choices, headline, update

/// The owner's choices as chips: each live choice hands back its exact id;
/// the owner's selection is marked with a checkmark, never colour alone.
struct CeremonyChoiceGroupView10868: View {
    let group: CeremonyChoiceGroup10868
    /// The accessibility id stem for this group's chips.
    let idStem: String
    var onChoose: ((String) -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    /// A choice's action: its exact id. Nil for a static choice.
    func action(_ choice: CeremonyChoice10868) -> (() -> Void)? {
        guard let onChoose,
              let id = CeremonyEventPageModel10868.liveID(choice, in: group, hasCallback: true) else { return nil }
        return { onChoose(id) }
    }

    var body: some View {
        FlowLayout(spacing: 8) {
            ForEach(Array(group.choices.enumerated()), id: \.offset) { index, choice in
                chip(choice, index: index)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(group.label)
    }

    @ViewBuilder private func chip(_ choice: CeremonyChoice10868, index: Int) -> some View {
        let id = CeremonyEventPageAccessibilityID10868.choice(idStem, index)
        if let action = action(choice) {
            Button(action: action) { chipLabel(choice) }
                .buttonStyle(.plain)
                .accessibilityLabel(spoken(choice))
                .accessibilityAddTraits(choice.isSelected ? .isSelected : [])
                .accessibilityIdentifier(id)
        } else {
            chipLabel(choice)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(spoken(choice))
                .accessibilityAddTraits(choice.isSelected ? .isSelected : [])
                .accessibilityIdentifier(id)
        }
    }

    private func spoken(_ choice: CeremonyChoice10868) -> String {
        [choice.label, CeremonyComparisonGeometry10868.readable(choice.detail)].compactMap { $0 }.joined(separator: ", ")
    }

    private func chipLabel(_ choice: CeremonyChoice10868) -> some View {
        HStack(spacing: 6) {
            if choice.isSelected {
                Image(systemName: "checkmark")
                    .font(.caption.weight(.bold))
                    .accessibilityHidden(true)
            }
            Text(choice.label)
                .font(.subheadline.weight(choice.isSelected ? .semibold : .regular))
                .fixedSize(horizontal: false, vertical: true)
            if let detail = CeremonyComparisonGeometry10868.readable(choice.detail) {
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
            }
        }
        .foregroundStyle(choice.isAvailable ? (choice.isSelected ? DS.blue : DS.textPrimary) : DS.textMuted)
        .padding(.horizontal, 12)
        .frame(minWidth: EsportsEventPageModel10868.targetHeight(controlSize),
               minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
        .overlay(RoundedRectangle(cornerRadius: 10)
            .strokeBorder(choice.isSelected ? DS.blue : DS.border, lineWidth: choice.isSelected ? 2 : 1))
        .contentShape(Rectangle())
    }
}

/// The ceremony headline in the owner's words, with the info control.
struct CeremonyHeadlineView10868: View {
    let headline: CeremonyHeadline10868
    var onAbout: (() -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 6) {
                if let eyebrow = CeremonyComparisonGeometry10868.readable(headline.eyebrow) {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(headline.title)
                    .font(.title.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if let subtitle = CeremonyComparisonGeometry10868.readable(headline.subtitle) {
                    Text(subtitle)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let status = CeremonyComparisonGeometry10868.readable(headline.status) {
                    Text(status)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
            if let onAbout, let label = CeremonyComparisonGeometry10868.readable(headline.aboutLabel) {
                Button(action: onAbout) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: EsportsEventPageModel10868.targetHeight(controlSize),
                               minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(label)
                .accessibilityIdentifier(CeremonyEventPageAccessibilityID10868.info)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(CeremonyEventPageAccessibilityID10868.headline)
    }
}

/// The owner's update readiness and its update control in the owner's state.
struct CeremonyUpdateView10868: View {
    let status: CeremonyUpdateStatus10868
    let state: FieldHistoryControlState10868
    /// The exact update; nil unless `state` is live.
    var action: (() -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            VStack(alignment: .leading, spacing: 2) {
                Text(status.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                if let detail = CeremonyComparisonGeometry10868.readable(status.detail) {
                    Text(detail).font(.footnote).foregroundStyle(DS.textSecondary)
                }
                if let pending = CeremonyComparisonGeometry10868.readable(status.pending) {
                    Text(pending).font(.footnote.weight(.semibold)).foregroundStyle(DS.textPrimary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .combine)
            if let update = status.update {
                switch state {
                case .live:
                    if let action {
                        Button(action: action) { updateLabel(update, live: true) }
                            .buttonStyle(.plain)
                            .accessibilityLabel(update.spokenLabel ?? update.label)
                            .accessibilityIdentifier(CeremonyEventPageAccessibilityID10868.updateControl)
                    }
                case .shownStatic:
                    updateLabel(update, live: false)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(update.spokenLabel ?? update.label)
                        .accessibilityIdentifier(CeremonyEventPageAccessibilityID10868.updateControl)
                case .hidden:
                    EmptyView()
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(CeremonyEventPageAccessibilityID10868.update)
    }

    private func updateLabel(_ update: FieldHistoryAction10868, live: Bool) -> some View {
        Text(update.label)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(live ? DS.blue : DS.textMuted)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 12)
            .frame(minWidth: EsportsEventPageModel10868.targetHeight(controlSize),
                   minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(live ? DS.blue : DS.border, lineWidth: 1))
            .contentShape(Rectangle())
    }
}

// MARK: - Points story (horizontal earlier/later points)

/// Places each owner tick label under its axis position at its actual text
/// size: the label's anchor moves with its value (leading edge at 0, centre
/// at the middle, trailing edge at 100%), kept inside the track's bounds, so
/// an end label stays whole. The height is the tallest label's; nothing
/// shrinks, wraps away or drops.
struct CeremonyAxisLabelsLayout10868: Layout {
    /// One 0...1 value per label, in the labels' order.
    let values: [Double]
    /// The track's horizontal inset, matching the marks' canvas.
    let inset: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        let height = sizes.map(\.height).max() ?? 0
        let width = proposal.width ?? (sizes.map(\.width).reduce(0, +) + inset * 2)
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let track = CGRect(x: bounds.minX + inset, y: bounds.minY, width: max(bounds.width - inset * 2, 0),
                           height: bounds.height)
        for (index, subview) in subviews.enumerated() {
            guard values.indices.contains(index) else { continue }
            let size = subview.sizeThatFits(.unspecified)
            let x = CeremonyComparisonGeometry10868.labelOrigin(values[index], width: size.width, track: track, bounds: bounds)
            subview.place(at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading, proposal: ProposedViewSize(size))
        }
    }
}

/// One contender's two dated chances on one horizontal 0–100% axis: the
/// earlier reading a hollow mark, the later one filled, both in the
/// contender's own shape. The owner's ticks label the axis beneath at their
/// measured size; a reading without a value draws no mark and is never clamped.
struct CeremonyPointsTrack10868: View {
    let slots: [CeremonyComparisonSlot10868]
    let ticks: [CeremonyAxisTick10868]
    let shape: FieldHistoryShape10868
    let tint: Color
    let markRadius: CGFloat

    /// The marks' canvas: the larger hollow mark fits whole above and below the axis.
    var canvasHeight: CGFloat { markRadius * 3.6 }
    var inset: CGFloat { markRadius * 1.6 }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Canvas { context, size in
                let lineY = markRadius * 1.8
                let rect = CGRect(x: inset, y: lineY, width: max(size.width - inset * 2, 0), height: 0)
                var axis = Path()
                axis.move(to: CGPoint(x: rect.minX, y: lineY))
                axis.addLine(to: CGPoint(x: rect.maxX, y: lineY))
                context.stroke(axis, with: .color(DS.border), lineWidth: 2)
                for tick in ticks {
                    let x = CeremonyComparisonGeometry10868.x(tick.value, in: rect)
                    var mark = Path()
                    mark.move(to: CGPoint(x: x, y: lineY - 4))
                    mark.addLine(to: CGPoint(x: x, y: lineY + 4))
                    context.stroke(mark, with: .color(DS.textMuted), lineWidth: 1)
                }
                // The hollow earlier mark first, a little larger, so a later mark
                // at the same place leaves its outline visible.
                for slot in slots where slot.style == .hollow {
                    guard let placement = slot.placement else { continue }
                    let center = CGPoint(x: CeremonyComparisonGeometry10868.x(placement, in: rect), y: lineY)
                    let path = FieldHistoryGeometry10868.markPath(shape, at: center, radius: markRadius * 1.25)
                    context.fill(path, with: .color(DS.cardBg))
                    context.stroke(path, with: .color(tint), lineWidth: 2)
                }
                for slot in slots where slot.style == .filled {
                    guard let placement = slot.placement else { continue }
                    let center = CGPoint(x: CeremonyComparisonGeometry10868.x(placement, in: rect), y: lineY)
                    context.fill(FieldHistoryGeometry10868.markPath(shape, at: center, radius: markRadius), with: .color(tint))
                }
            }
            .frame(height: canvasHeight)
            CeremonyAxisLabelsLayout10868(values: ticks.map(\.value), inset: inset) {
                ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                    Text(tick.label)
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize()
                }
            }
        }
        .accessibilityHidden(true)
    }
}

/// The points story: every contender's whole name and, at the final, its
/// reported fact; its two dated chances as hollow and filled points on the
/// common axis; each reading with its role and own date; the separately dated
/// observation; and the contender's explore control.
struct CeremonyPointsStoryPresentation10868: View {
    let model: CeremonyStoryModel10868
    var onExpand: (() -> Void)? = nil
    var onOpen: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onHistory: ((String) -> Void)? = nil

    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = RugbyMatchEventPageModel10868.comparisonFigureSize
    @ScaledMetric(relativeTo: .caption) private var markRadius: CGFloat = 7

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            CeremonyStoryHeader10868(copy: model.copy, card: .points, onExpand: onExpand)
            CeremonyStoryLines10868(lines: [model.copy.key].compactMap { $0 })
            let plans = model.plans
            if plans.isEmpty {
                CeremonyStoryLines10868(lines: [model.copy.empty])
            }
            ForEach(Array(plans.enumerated()), id: \.offset) { index, plan in
                VStack(alignment: .leading, spacing: 8) {
                    VStack(alignment: .leading, spacing: 8) {
                        CeremonyNameLine10868(plan: plan)
                        CeremonyPointsTrack10868(slots: plan.slots, ticks: model.ticks, shape: plan.contender.shape,
                                                 tint: plan.contender.tint, markRadius: markRadius)
                        CeremonySlotsRow10868(slots: plan.slots, figureSize: figureSize)
                        CeremonySeparateLine10868(slot: plan.separate)
                    }
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(CeremonyStoryModel10868.spoken(plan))
                    .accessibilityIdentifier(CeremonyEventPageAccessibilityID10868.row(.points, index))
                    CeremonyOriginalControl10868(model: model, plan: plan, onOpen: onOpen,
                                                 id: CeremonyEventPageAccessibilityID10868.open(.points, index))
                }
                .padding(.vertical, 4)
            }
            CeremonyStoryLines10868(lines: model.copy.notes)
            CeremonyLink10868(label: model.copy.historyLabel, id: CeremonyEventPageAccessibilityID10868.history(.points),
                              action: model.historyAction(onHistory))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(model.copy.graphicLabel)
    }
}

// MARK: - Bars story (paired vertical bars)

/// One contender's two dated chances as paired vertical bars on one 0–100%
/// scale: the earlier reading light, the later one solid, each in its own
/// column. A real zero keeps a floor cap — still a value; a reading without a
/// valid placement draws only a dashed empty marker, never a zero bar.
struct CeremonyBarsGraphic10868: View {
    let slots: [CeremonyComparisonSlot10868]
    let ticks: [CeremonyAxisTick10868]
    let tint: Color
    let height: CGFloat
    /// The smallest tick-label column on the leading edge; a wider measured label widens it.
    let labelWidth: CGFloat

    static let maximumBarWidth: CGFloat = 36

    var body: some View {
        Canvas { context, size in
            // Every tick label at its actual caption size, measured before the
            // plot is placed, so the 0% and 100% labels stay whole.
            let labels = ticks.map { context.resolve(Text($0.label).font(.caption2).foregroundStyle(DS.textSecondary)) }
            let sizes = labels.map { $0.measure(in: size) }
            let label = CGSize(width: sizes.map(\.width).max() ?? 0, height: sizes.map(\.height).max() ?? 0)
            let rect = CeremonyComparisonGeometry10868.barPlotRect(in: size, label: label, minimumLeading: labelWidth)
            for (index, tick) in ticks.enumerated() {
                let y = CeremonyComparisonGeometry10868.y(tick.value, in: rect)
                var grid = Path()
                grid.move(to: CGPoint(x: rect.minX, y: y))
                grid.addLine(to: CGPoint(x: rect.maxX, y: y))
                context.stroke(grid, with: .color(DS.border), style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
                context.draw(labels[index], at: CGPoint(x: rect.minX - CeremonyComparisonGeometry10868.axisLabelGap, y: y),
                             anchor: .trailing)
            }
            let bars = CeremonyComparisonGeometry10868.bars(slots)
            for bar in bars {
                if let barRect = CeremonyComparisonGeometry10868.barRect(bar, count: bars.count, in: rect,
                                                                          maxWidth: Self.maximumBarWidth) {
                    let color = tint.opacity(CeremonyComparisonGeometry10868.barOpacity(bar.style))
                    if barRect.height > 0 {
                        context.fill(Path(roundedRect: barRect, cornerRadius: min(5, barRect.width / 2)), with: .color(color))
                    }
                    var cap = Path()
                    cap.move(to: CGPoint(x: barRect.minX, y: rect.maxY))
                    cap.addLine(to: CGPoint(x: barRect.maxX, y: rect.maxY))
                    context.stroke(cap, with: .color(color), lineWidth: 3)
                } else if let center = CeremonyComparisonGeometry10868.columnCenter(bar.column, count: bars.count, in: rect) {
                    let half = min(Self.maximumBarWidth, rect.width / CGFloat(max(bars.count, 1)) * 0.6) / 2
                    var empty = Path()
                    empty.move(to: CGPoint(x: center - half, y: rect.maxY))
                    empty.addLine(to: CGPoint(x: center + half, y: rect.maxY))
                    context.stroke(empty, with: .color(DS.textMuted), style: StrokeStyle(lineWidth: 2, dash: [3, 3]))
                }
            }
        }
        .frame(height: height)
        .accessibilityHidden(true)
    }
}

/// The bars story: every contender's whole name and, at the final, its
/// reported fact; its two dated chances as a light and a solid bar; under
/// each bar its role, figure and own date; the separately dated observation;
/// and the contender's explore control.
struct CeremonyBarsStoryPresentation10868: View {
    let model: CeremonyStoryModel10868
    var onExpand: (() -> Void)? = nil
    var onOpen: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onHistory: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = RugbyMatchEventPageModel10868.comparisonFigureSize
    @ScaledMetric(relativeTo: .body) private var plotHeight: CGFloat = 120
    @ScaledMetric(relativeTo: .caption2) private var labelWidth: CGFloat = 44

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            CeremonyStoryHeader10868(copy: model.copy, card: .bars, onExpand: onExpand)
            CeremonyStoryLines10868(lines: [model.copy.key].compactMap { $0 })
            let plans = model.plans
            if plans.isEmpty {
                CeremonyStoryLines10868(lines: [model.copy.empty])
            }
            ForEach(Array(plans.enumerated()), id: \.offset) { index, plan in
                VStack(alignment: .leading, spacing: 8) {
                    VStack(alignment: .leading, spacing: 8) {
                        CeremonyNameLine10868(plan: plan)
                        CeremonyBarsGraphic10868(slots: plan.slots, ticks: model.ticks, tint: plan.contender.tint,
                                                 height: plotHeight, labelWidth: labelWidth)
                        readings(plan)
                        CeremonySeparateLine10868(slot: plan.separate)
                    }
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(CeremonyStoryModel10868.spoken(plan))
                    .accessibilityIdentifier(CeremonyEventPageAccessibilityID10868.row(.bars, index))
                    CeremonyOriginalControl10868(model: model, plan: plan, onOpen: onOpen,
                                                 id: CeremonyEventPageAccessibilityID10868.open(.bars, index))
                }
                .padding(.vertical, 4)
            }
            CeremonyStoryLines10868(lines: model.copy.notes)
            CeremonyLink10868(label: model.copy.historyLabel, id: CeremonyEventPageAccessibilityID10868.history(.bars),
                              action: model.historyAction(onHistory))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(model.copy.graphicLabel)
    }

    /// Each bar's reading in the bar's own column; stacked in bar order at
    /// accessibility sizes, each still led by its role words.
    @ViewBuilder private func readings(_ plan: CeremonyContenderPlan10868) -> some View {
        if typeSize.isAccessibilitySize {
            CeremonySlotsRow10868(slots: plan.slots, figureSize: figureSize)
        } else {
            HStack(alignment: .top, spacing: 0) {
                ForEach(Array(plan.slots.enumerated()), id: \.offset) { _, slot in
                    CeremonySlotView10868(slot: slot, figureSize: figureSize)
                        .padding(.horizontal, 4)
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                }
            }
            .padding(.leading, labelWidth)
        }
    }
}

/// The held original's side choices: each hands back its exact selection
/// while it opens alone; the held side is marked, never by colour alone.
struct CeremonySideChoicesView10868: View {
    let label: String
    let originals: CeremonyEventPageOriginals10868
    var onSide: ((OriginalMarketDetails9483.Selection) -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    /// A side's action: its exact selection. Nil for a static side.
    func action(_ side: CeremonySideChoice10868) -> (() -> Void)? {
        guard let onSide, CeremonyEventPageModel10868.sideOpens(side, in: originals) else { return nil }
        let selection = side.selection
        return { onSide(selection) }
    }

    var body: some View {
        HStack(spacing: 8) {
            ForEach(Array(originals.sides.enumerated()), id: \.offset) { index, side in
                let selected = CeremonyEventPageModel10868.sideIsSelected(side, in: originals)
                if let action = action(side) {
                    Button(action: action) { sideLabel(side, selected: selected) }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(selected ? .isSelected : [])
                        .accessibilityIdentifier(CeremonyEventPageAccessibilityID10868.side(index))
                } else {
                    sideLabel(side, selected: selected)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(side.label)
                        .accessibilityAddTraits(selected ? .isSelected : [])
                        .accessibilityIdentifier(CeremonyEventPageAccessibilityID10868.side(index))
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(label)
        .accessibilityIdentifier(CeremonyEventPageAccessibilityID10868.sides)
    }

    private func sideLabel(_ side: CeremonySideChoice10868, selected: Bool) -> some View {
        HStack(spacing: 6) {
            if selected {
                Image(systemName: "checkmark").font(.caption.weight(.bold)).accessibilityHidden(true)
            }
            Text(side.label)
                .font(.body.weight(selected ? .semibold : .regular))
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(selected ? DS.blue : DS.textPrimary)
        .padding(.horizontal, 16)
        .frame(minWidth: EsportsEventPageModel10868.targetHeight(controlSize),
               minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(selected ? DS.blue : DS.border, lineWidth: selected ? 2 : 1))
        .contentShape(Rectangle())
    }
}

// MARK: - Page view

struct CeremonyEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868
    typealias Selection = OriginalMarketDetails9483.Selection
    private typealias ID = CeremonyEventPageAccessibilityID10868

    let input: CeremonyEventPageInput10868
    var mode: CeremonyEventPageMode10868 = .page
    /// The originals for the stories, the catalogue, Details and side history,
    /// read only while admitted for the page's phase; nil: none.
    var originals: CeremonyEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's Info.
    var onAbout: (() -> Void)? = nil
    /// An Info section's exact external link.
    var onLink: ((RugbyMatchEventPageLink10868) -> Void)? = nil
    /// A dated view's exact id; the page's phase stays the owner's.
    var onView: ((String) -> Void)? = nil
    /// An award category's exact id.
    var onCategory: ((String) -> Void)? = nil
    /// The update control's exact id — no hold.
    var onUpdate: ((String) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Opens every original candidate prop.
    var onCatalogue: (() -> Void)? = nil
    /// A chooser row's exact original.
    var onCatalogueChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// A chooser window or disclosure, exactly.
    var onCatalogueControl: ((FieldChooserControl10868) -> Void)? = nil
    /// A Details side choice's exact selection.
    var onSide: ((Selection) -> Void)? = nil
    /// A Details history control's exact intent.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onSideHistoryAction: ((String) -> Void)? = nil
    var onSideHistoryInspectionChoice: ((String) -> Void)? = nil
    var onSideHistoryPlotPosition: ((Double) -> Void)? = nil
    /// A story contender's exact original, for the host's Details.
    var onStoryOpen: ((Selection) -> Void)? = nil
    /// A story's exact category id, for the host's history.
    var onStoryHistory: ((String) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// Opens the host's reader on a story mounted directly on the page.
    var onCardOpen: ((CeremonyEventPageCard10868) -> Void)? = nil
    /// Full-size and side-history controls, exactly.
    var onReaderIntent: ((CeremonyReaderIntent10868) -> Void)? = nil
    /// Called once just before a page, catalogue or Details action reaches its
    /// owner callback. Never by building the view, by full-size content, by
    /// the side history or Info, by the update control, or by a stream card.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var storiesMinWidth: CGFloat = 340
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: CeremonyEventPageModel10868 { CeremonyEventPageModel10868(input) }

    /// The one originals value every consumer reads: the owner's bundle while
    /// admitted for this page's phase, otherwise nothing.
    var admittedOriginals: CeremonyEventPageOriginals10868? { model.admitted(originals) }

    // MARK: Relays

    static func held<Value>(_ action: ((Value) -> Void)?, by interaction: (() -> Void)?) -> ((Value) -> Void)? {
        RugbyMatchEventPagePresentation10868.held(action, by: interaction)
    }

    static func heldAction(_ action: (() -> Void)?, by interaction: (() -> Void)?) -> (() -> Void)? {
        RugbyMatchEventPagePresentation10868.heldAction(action, by: interaction)
    }

    static func relay<Value>(_ action: ((Value) -> Void)?,
                             through activation: StoryStreamCardActivation10868?) -> ((Value) -> Void)? {
        EsportsEventPagePresentation10868.relay(action, through: activation)
    }

    static func bind(_ action: ((CeremonyEventPageCard10868) -> Void)?, _ card: CeremonyEventPageCard10868) -> (() -> Void)? {
        guard let action else { return nil }
        return { action(card) }
    }

    static func bind(_ action: ((CeremonyReaderIntent10868) -> Void)?, _ intent: CeremonyReaderIntent10868) -> (() -> Void)? {
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
            case .sideHistory: sideHistoryMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves

    /// The page's info control, after the hook.
    var headlineAboutAction: (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil) else { return nil }
        return Self.heldAction(onAbout, by: onInteraction)
    }

    /// The headline at the page's phase.
    func headlineContent() -> CeremonyHeadlineView10868? {
        model.headline.map { CeremonyHeadlineView10868(headline: $0, onAbout: headlineAboutAction) }
    }

    /// The owner's dated views, each after the hook.
    func viewChoicesContent() -> CeremonyChoiceGroupView10868? {
        input.views.map { CeremonyChoiceGroupView10868(group: $0, idStem: "views", onChoose: Self.held(onView, by: onInteraction)) }
    }

    /// The award categories, each after the hook — on the page and in the catalogue.
    func categoryChoicesContent() -> CeremonyChoiceGroupView10868? {
        input.categories.map {
            CeremonyChoiceGroupView10868(group: $0, idStem: "categories", onChoose: Self.held(onCategory, by: onInteraction))
        }
    }

    /// The anchor after the hook; full size keeps the exact callbacks.
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let hold = reader ? nil : onInteraction
        return FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : model.presentedHistory,
            onAction: Self.held(onHistoryAction, by: hold),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: hold),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: hold))
    }

    /// The update control's exact id, live only in the owner's unlocked state.
    var updateAction: (() -> Void)? {
        guard case .live(let id) = model.updateState(hasCallback: onUpdate != nil), let onUpdate else { return nil }
        return { onUpdate(id) }
    }

    func updateContent() -> CeremonyUpdateView10868? {
        input.update.map {
            CeremonyUpdateView10868(status: $0, state: model.updateState(hasCallback: onUpdate != nil), action: updateAction)
        }
    }

    /// A story mounted directly on the page: every action after the hook.
    func pagePointsContent() -> CeremonyPointsStoryPresentation10868? {
        guard model.showsCardsDirectly, let story = model.storyModel(.points, catalogue: admittedOriginals?.catalogue) else { return nil }
        return CeremonyPointsStoryPresentation10868(
            model: story, onExpand: Self.heldAction(Self.bind(onCardOpen, .points), by: onInteraction),
            onOpen: Self.held(onStoryOpen, by: onInteraction), onHistory: Self.held(onStoryHistory, by: onInteraction))
    }

    func pageBarsContent() -> CeremonyBarsStoryPresentation10868? {
        guard model.showsCardsDirectly, let story = model.storyModel(.bars, catalogue: admittedOriginals?.catalogue) else { return nil }
        return CeremonyBarsStoryPresentation10868(
            model: story, onExpand: Self.heldAction(Self.bind(onCardOpen, .bars), by: onInteraction),
            onOpen: Self.held(onStoryOpen, by: onInteraction), onHistory: Self.held(onStoryHistory, by: onInteraction))
    }

    /// A story in a stream cell: every action after the stream's activation
    /// hook, never the page hook as well. The stream offers its own open.
    func streamPointsContent(activation: StoryStreamCardActivation10868) -> CeremonyPointsStoryPresentation10868? {
        model.storyModel(.points, catalogue: admittedOriginals?.catalogue).map {
            CeremonyPointsStoryPresentation10868(model: $0, onExpand: nil, onOpen: Self.relay(onStoryOpen, through: activation),
                                                 onHistory: Self.relay(onStoryHistory, through: activation))
        }
    }

    func streamBarsContent(activation: StoryStreamCardActivation10868) -> CeremonyBarsStoryPresentation10868? {
        model.storyModel(.bars, catalogue: admittedOriginals?.catalogue).map {
            CeremonyBarsStoryPresentation10868(model: $0, onExpand: nil, onOpen: Self.relay(onStoryOpen, through: activation),
                                               onHistory: Self.relay(onStoryHistory, through: activation))
        }
    }

    /// Full-size stories: the same Views and inputs with the exact callbacks.
    func readerPointsContent() -> CeremonyPointsStoryPresentation10868? {
        model.storyModel(.points, catalogue: admittedOriginals?.catalogue).map {
            CeremonyPointsStoryPresentation10868(model: $0, onExpand: nil, onOpen: onStoryOpen, onHistory: onStoryHistory)
        }
    }

    func readerBarsContent() -> CeremonyBarsStoryPresentation10868? {
        model.storyModel(.bars, catalogue: admittedOriginals?.catalogue).map {
            CeremonyBarsStoryPresentation10868(model: $0, onExpand: nil, onOpen: onStoryOpen, onHistory: onStoryHistory)
        }
    }

    /// The all-originals entry, after the hook.
    var catalogueAction: (() -> Void)? {
        guard model.catalogueAvailable(canOpen: onCatalogue != nil, originals: originals) else { return nil }
        return Self.heldAction(onCatalogue, by: onInteraction)
    }

    /// Every original candidate prop in the owner's windows; rows and windows after the hook.
    func chooserContent() -> FieldContenderChooserPresentation10868? {
        admittedOriginals?.chooser.map {
            FieldContenderChooserPresentation10868(input: $0, onChoose: Self.held(onCatalogueChoose, by: onInteraction),
                                                   onControl: Self.held(onCatalogueControl, by: onInteraction))
        }
    }

    /// The held original's side choices, each after the hook.
    func sideChoicesContent() -> CeremonySideChoicesView10868? {
        guard let admitted = admittedOriginals, !admitted.sides.isEmpty else { return nil }
        return CeremonySideChoicesView10868(label: input.copy.sidesLabel, originals: admitted,
                                            onSide: Self.held(onSide, by: onInteraction))
    }

    /// The existing Details for the held selection, its history after the hook.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        admittedOriginals.map {
            OriginalMarketDetailsView9483(catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                                          recorded: $0.recorded, onHistory: Self.held(onOriginalHistory, by: onInteraction))
        }
    }

    /// The held side's own full-size history with the exact callbacks; nil
    /// when it was not admitted for exactly the held side.
    func sideHistoryContent() -> FieldProbabilityHistoryPresentation10868? {
        model.sideHistory(originals).map {
            FieldProbabilityHistoryPresentation10868(input: $0, onAction: onSideHistoryAction,
                                                     onInspectionChoice: onSideHistoryInspectionChoice,
                                                     onPlotPosition: onSideHistoryPlotPosition)
        }
    }

    /// The owner's Info with its exact link callback.
    func aboutContent() -> RugbyMatchEventPageSectionsContent10868? {
        model.about.map {
            RugbyMatchEventPageSectionsContent10868(title: $0.title, sections: $0.sections, sourceIDs: [],
                                                    sourceLabel: "", onLink: onLink, onSource: nil)
        }
    }

    /// Full-size content's own controls: the mounted neighbours and Back, exactly.
    func readerControls(_ card: CeremonyEventPageCard10868) -> (previous: CeremonyEventPageCard10868?,
                                                                next: CeremonyEventPageCard10868?,
                                                                canGoBack: Bool) {
        guard onReaderIntent != nil, model.isMounted(card) else { return (nil, nil, false) }
        return (model.neighbour(of: card, offset: -1), model.neighbour(of: card, offset: 1), true)
    }

    /// Full-size content's info control: the exact callback, no hook.
    var readerAboutAction: (() -> Void)? {
        model.aboutAvailable(canOpen: onAbout != nil) ? onAbout : nil
    }

    /// The side history's Back: the exact intent, no hook.
    var sideHistoryBack: (() -> Void)? { Self.bind(onReaderIntent, .back) }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            headlineSection
            choicesSection
            Group {
                let arrangements = RugbyMatchEventPageModel10868.arrangements(
                    sizeClass: sizeClass, accessibilitySize: typeSize.isAccessibilitySize)
                if arrangements == [.stacked] {
                    stackedMain
                } else {
                    ViewThatFits(in: .horizontal) {
                        wideMain
                        stackedMain
                    }
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.page)
    }

    private var headlineSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Group {
                if let headline = headlineContent() {
                    headline
                } else {
                    ownerWords(input.copy.headlineUnavailable, id: ID.headlineUnavailable)
                }
            }
            .accessibilitySortPriority(CeremonyEventPageModel10868.sortPriority(.headline))
            if let notice = CeremonyEventPageModel10868.readable(input.notice) {
                Text(notice)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilitySortPriority(CeremonyEventPageModel10868.sortPriority(.notice))
                    .accessibilityIdentifier(ID.notice)
            }
        }
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder private var choicesSection: some View {
        let views = viewChoicesContent()
        let categories = categoryChoicesContent()
        if views != nil || categories != nil {
            VStack(alignment: .leading, spacing: 10) {
                if let views {
                    views.accessibilityIdentifier(ID.views)
                }
                if let categories {
                    categories.accessibilityIdentifier(ID.categories)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilitySortPriority(CeremonyEventPageModel10868.sortPriority(.choices))
        }
    }

    private var stackedMain: some View {
        VStack(alignment: .leading, spacing: 20) {
            anchor
            secondary
        }
    }

    private var wideMain: some View {
        HStack(alignment: .top, spacing: 24) {
            anchor
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
            secondary
                .frame(minWidth: storiesMinWidth, maxWidth: .infinity, alignment: .topLeading)
        }
    }

    private var anchor: some View {
        historyContent(reader: false)
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(CeremonyCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilitySortPriority(CeremonyEventPageModel10868.sortPriority(.anchor))
            .accessibilityIdentifier(ID.anchor)
    }

    private var secondary: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let update = updateContent() {
                update.accessibilitySortPriority(CeremonyEventPageModel10868.sortPriority(.update))
            }
            stories
            if let action = catalogueAction, let label = input.copy.catalogueLabel {
                catalogueEntry(label, action: action)
                    .accessibilitySortPriority(CeremonyEventPageModel10868.sortPriority(.catalogue))
            }
        }
    }

    /// The owner's stream when it supplies one; otherwise the mounted stories
    /// directly on the page, in the page's order.
    @ViewBuilder private var stories: some View {
        if let stream = input.stream {
            StoryStreamPresentationView10868(stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(input.copy.storiesLabel)
            .accessibilitySortPriority(CeremonyEventPageModel10868.sortPriority(.stories))
            .accessibilityIdentifier(ID.stories)
        } else {
            if let points = pagePointsContent() {
                cardSurface(points, card: .points)
            }
            if let bars = pageBarsContent() {
                cardSurface(bars, card: .bars)
            }
        }
    }

    private func cardSurface<Content: View>(_ content: Content, card: CeremonyEventPageCard10868) -> some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(CeremonyCardSurface10868())
            .accessibilitySortPriority(CeremonyEventPageModel10868.sortPriority(.stories))
            .accessibilityIdentifier(ID.card(card))
    }

    /// The story the owner links to this stream card, or the owner's words. Never a neighbour.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.storyLink(card.id), let content = streamCardContent(link.card, activation) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = CeremonyEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                content
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(CeremonyCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(CeremonyCardSurface10868())
                .accessibilityIdentifier(ID.storyUnavailable)
        }
    }

    private func streamCardContent(_ card: CeremonyEventPageCard10868,
                                   _ activation: StoryStreamCardActivation10868) -> AnyView? {
        switch card {
        case .history: nil
        case .points: streamPointsContent(activation: activation).map { AnyView($0) }
        case .bars: streamBarsContent(activation: activation).map { AnyView($0) }
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
            .modifier(CeremonyCardSurface10868())
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(ID.catalogueEntry)
    }

    private func ownerWords(_ words: String, id: String) -> some View {
        Text(words)
            .font(.subheadline)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityIdentifier(id)
    }

    // MARK: Content modes

    private var catalogueMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let categories = categoryChoicesContent() {
                categories.accessibilityIdentifier(ID.categories)
            }
            if model.originalsAreForAnotherPhase(originals) {
                ownerWords(input.copy.originalsUnavailable, id: ID.originalsUnavailable)
            } else if let chooser = chooserContent() {
                chooser
            } else {
                ownerWords(input.copy.catalogueUnavailable, id: ID.catalogueUnavailable)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.catalogue)
    }

    private var originalMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            if model.originalsAreForAnotherPhase(originals) {
                ownerWords(input.copy.originalsUnavailable, id: ID.originalsUnavailable)
            }
            if let sides = sideChoicesContent() {
                sides
            }
            if CeremonyEventPageModel10868.heldOriginalIsUnavailable(admittedOriginals) {
                ownerWords(input.copy.heldOriginalUnavailable, id: ID.heldUnavailable)
            }
            if let details = originalDetailsContent() {
                details
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.original)
    }

    private var sideHistoryMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let back = sideHistoryBack {
                readerButton(input.copy.backLabel, detail: nil, systemImage: "chevron.backward", action: back,
                             id: ID.readerBack)
            }
            if model.originalsAreForAnotherPhase(originals) {
                ownerWords(input.copy.originalsUnavailable, id: ID.originalsUnavailable)
            } else if let history = sideHistoryContent() {
                history
            } else {
                ownerWords(input.copy.sideHistoryUnavailable, id: ID.sideHistoryUnavailable)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.sideHistory)
    }

    @ViewBuilder private var aboutMode: some View {
        if let about = aboutContent() {
            about.accessibilityIdentifier(ID.about)
        }
    }

    // MARK: Full size

    /// The same Views and inputs, full size: a lazy section whose header the
    /// host's scroll pins, with the reader controls and the content beneath. A
    /// card that is not mounted keeps the owner's words, never another card.
    @ViewBuilder private func reader(_ card: CeremonyEventPageCard10868) -> some View {
        LazyVStack(alignment: .leading, spacing: 16, pinnedViews: [.sectionHeaders]) {
            Section {
                if model.isMounted(card) {
                    readerNavigation(card)
                    switch card {
                    case .history:
                        historyContent(reader: true)
                    case .points:
                        readerPointsContent()
                    case .bars:
                        readerBarsContent()
                    }
                } else {
                    ownerWords(input.copy.readerUnavailable, id: ID.readerUnavailable)
                }
            } header: {
                compactHeader
                    .padding(.vertical, 8)
                    .background(DS.surface)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.card(card))
    }

    @ViewBuilder private func readerNavigation(_ card: CeremonyEventPageCard10868) -> some View {
        let controls = readerControls(card)
        if controls.canGoBack {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) { readerButtons(controls) }
                VStack(alignment: .leading, spacing: 4) { readerButtons(controls) }
            }
        }
    }

    @ViewBuilder private func readerButtons(_ controls: (previous: CeremonyEventPageCard10868?,
                                                         next: CeremonyEventPageCard10868?,
                                                         canGoBack: Bool)) -> some View {
        readerButton(input.copy.backLabel, detail: nil, systemImage: "chevron.backward",
                     action: Self.bind(onReaderIntent, .back), id: ID.readerBack)
        if let previous = controls.previous {
            readerButton(input.copy.previousLabel, detail: model.cardName(previous), systemImage: "arrow.left",
                         action: Self.bind(onReaderIntent, .previous(previous)), id: ID.readerPrevious)
        }
        if let next = controls.next {
            readerButton(input.copy.nextLabel, detail: model.cardName(next), systemImage: "arrow.right",
                         action: Self.bind(onReaderIntent, .next(next)), id: ID.readerNext)
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
                        if let detail = CeremonyEventPageModel10868.readable(detail) {
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

    /// The owner's one-line words and the info control.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = CeremonyEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if let action = readerAboutAction, let label = CeremonyEventPageModel10868.readable(input.headline.aboutLabel) {
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
                .accessibilityIdentifier(ID.readerInfo)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.readerHeader)
    }
}
