import SwiftUI

/// #10868 — THE GOLF TOURNAMENT SCREEN'S PRODUCTION ADAPTER, PART ONE: PHASE,
/// HEADER AND CARD FRAMES.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on `golf`, `golf-reading`, `golf-journey`
/// and `golf-outlook` the tournament screen says which stage it is reading —
/// before the listed start, recorded since it, or final — from the same served
/// facts the app's futures pages already read, and never calls a recorded
/// estimate live or a listed date a tee time.
///
/// A golf tournament is served as futures field markets (`/api/futures/{id}`,
/// `FuturesMarketDetail`): one Winner market for the field, and separate Top 5 /
/// Top 10 / Top 20 / Make the Cut markets. It decides nothing the app does not
/// already decide. Each slot is the output of the authority that owns it:
///
///   - final         `market.status == "resolved"`, the MARKET-level settled fact
///                   `FuturesDetailView` and `OutcomeVerdict.verdict`'s
///                   `marketResolved` read (FuturesDetailView.swift:282,
///                   OutcomeVerdict.swift:47). Never a 100% price, a leaderboard
///                   row or a clock.
///   - listed start  `FuturesStartDate.shown` (FuturesStartDate.swift:29): the
///                   served `commence_time`, only when it is strictly before the
///                   resolution. DataGolf serves it as a CALENDAR DATE at UTC
///                   midnight (#10246), so it is a listed start, not a tee time.
///   - recorded      the listed start at or before now — the same reading
///                   `EvolutionChartView` makes of `tournamentStart <= now` when it
///                   opens its Event range (EvolutionChartView.swift:466, :556).
///                   No served start: recorded, with no reading called
///                   pre-tournament (the history and finish parts say why).
///   - title         `GolfTournamentPresentation.name` (production's title case of
///                   `/api/golf/tournaments/{slug}`) when the host holds it, else
///                   the market's own served name, verbatim.
///   - context       `GolfTournamentView`'s header order — venue, location, tour,
///                   dates — from `GolfTournamentPresentation`; else the market's
///                   listed dates through `formatDateRange` (the calendar-date
///                   reader `CalendarDeadline` sits under).
///   - clocks        the futures pages' own style, `.month(.abbreviated).day()
///                   .hour().minute()` (FuturesDetailView.swift:593,
///                   EvolutionChartView.swift:1726), said in the reader's calendar,
///                   zone and locale.
///   - source names  `SourceLabels.label(for:)` / `.attribution(for:)` only.
///
/// OWED, NOT MANUFACTURED (named so Native can bind them):
///   - first tee / round start: no owner. DataGolf's start is a calendar date at
///     UTC midnight; `/history`'s `round_boundaries` are ~00:02 UTC data-day
///     stamps and `FuturesHistoryResponse` does not decode them. So every word
///     here is about the listed start date, never a first tee. Owner: golf
///     endpoint + Native models.
///   - the reading status (held / pending words, Pause / Resume updates): no golf
///     reading-hold owner exists — `FuturesDetailView` and `EvolutionChartView`
///     fetch on their own — so the status is nil and no control is drawn.
///   - About destination: `GolfEventPageMode10868` has no About mode, so the about
///     label is nil and no about control is drawn.
///
/// Nothing here fetches, subscribes, schedules, ranks or holds state.
enum GolfFieldPageAdapter10868 {

    /// What the host already holds, passed in unchanged.
    struct Host {
        let now: Date
        /// The reader's own calendar, time zone and locale; clock words are said in it.
        let calendar: Calendar
        let locale: Locale

        init(now: Date = Date(), calendar: Calendar = .current, locale: Locale = .current) {
            self.now = now
            self.calendar = calendar
            self.locale = locale
        }
    }

    enum Words {
        static let beforeEyebrow = "Before the start date"
        static let recordedEyebrow = "Since the start date"
        static let recordedNoStartEyebrow = "Recorded chances"
        static let finalEyebrow = "Final"
        static let storiesLabel = "Tournament stories"
        static let chooseGolfer = "Choose a golfer to see their finish chances."
        static let finishUnavailable = "Finish chances unavailable for this golfer."
        static let finishOpen = "Expand finish expectations"
        static let contendersOpen = "Expand who starts strongest"
        /// The secondary entry to the supplied originals in typed groups (Design).
        static let exploreProps = "Explore props"
    }

    // MARK: - Phase

    /// The listed start: the served `commence_time`, only where it can be a start.
    static func listedStart(_ winner: FuturesMarketDetail) -> Date? {
        FuturesStartDate.shown(commenceTime: winner.commenceTime, resolutionDate: winner.resolutionDate)
    }

    /// The screen's one phase. Resolved is final; a listed start at or before
    /// now — or no listed start at all — is recorded; otherwise before. Never
    /// read from a price, a 100% reading, a leaderboard or a score.
    static func phase(_ winner: FuturesMarketDetail, now: Date) -> GolfFinishPhase10868 {
        if winner.status == "resolved" { return .final }
        guard let start = listedStart(winner) else { return .recorded }
        return start <= now ? .recorded : .before
    }

    /// The contenders and movement cards' own phase vocabulary for the same phase.
    static func outlookPhase(_ phase: GolfFinishPhase10868) -> FieldOutlookPhase10868 {
        switch phase {
        case .before: .before
        case .recorded: .during
        case .final: .final
        }
    }

    // MARK: - Header

    static func copy(_ winner: FuturesMarketDetail, tournament: GolfTournamentPresentation?,
                     phase: GolfFinishPhase10868, finishUnavailable: String,
                     host: Host) -> GolfEventPageCopy10868 {
        GolfEventPageCopy10868(
            eyebrow: eyebrow(winner, phase: phase),
            title: tournament?.name ?? winner.name,
            context: context(winner, tournament: tournament, host: host),
            aboutLabel: nil,
            storiesLabel: Words.storiesLabel,
            finishUnavailable: finishUnavailable,
            exploreLabel: Words.exploreProps)
    }

    static func eyebrow(_ winner: FuturesMarketDetail, phase: GolfFinishPhase10868) -> String {
        switch phase {
        case .before: Words.beforeEyebrow
        case .recorded: listedStart(winner) == nil ? Words.recordedNoStartEyebrow : Words.recordedEyebrow
        case .final: Words.finalEyebrow
        }
    }

    /// Venue, location, tour and dates in `GolfTournamentView`'s order; without
    /// the tournament body, the market's own listed dates.
    static func context(_ winner: FuturesMarketDetail, tournament: GolfTournamentPresentation?,
                        host: Host) -> String? {
        if let tournament {
            let parts: [String?] = [tournament.venue, tournament.location, tournament.tourLabel, tournament.dateRange]
            return joined(parts)
        }
        guard listedStart(winner) != nil else { return nil }
        return formatDateRange(start: winner.commenceTime, end: winner.resolutionDate,
                               localZone: host.calendar.timeZone)
    }

    // MARK: - Card frames

    static func finishFrame(_ winner: FuturesMarketDetail, phase: GolfFinishPhase10868) -> GolfEventPageCardFrame10868 {
        GolfEventPageCardFrame10868(eyebrow: eyebrow(winner, phase: phase), openLabel: Words.finishOpen)
    }

    static func contendersFrame() -> GolfEventPageCardFrame10868 {
        GolfEventPageCardFrame10868(eyebrow: Words.beforeEyebrow, openLabel: Words.contendersOpen)
    }

    /// The movement card has no owner input (see the before-card part), so its
    /// frame offers no open control.
    static func movementFrame() -> GolfEventPageCardFrame10868 {
        GolfEventPageCardFrame10868(eyebrow: Words.beforeEyebrow, openLabel: nil)
    }

    // MARK: - Words shared by every part

    /// "Oct 6, 6:08 AM" in the reader's zone — the futures pages' own style.
    static func clockWords(_ date: Date, host: Host) -> String {
        let style = Date.FormatStyle(locale: host.locale, calendar: host.calendar, timeZone: host.calendar.timeZone)
        return date.formatted(style.month(.abbreviated).day().hour().minute())
    }

    /// The reader-facing name of the market's source, or nil (#4135).
    static func sourceName(_ market: FuturesMarketDetail) -> String? {
        SourceLabels.label(for: market.source)
    }

    /// The venue half of an identity key: the served source key, or empty.
    /// A key only — a source is named to the reader through `SourceLabels`
    /// (#4135), never through this.
    static func sourceKey(_ market: FuturesMarketDetail) -> String {
        guard let venue = market.source else { return "" }
        return venue
    }

    static func joined(_ parts: [String?], separator: String = " · ") -> String? {
        let kept = parts.compactMap { $0 }.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        return kept.isEmpty ? nil : kept.joined(separator: separator)
    }
}
