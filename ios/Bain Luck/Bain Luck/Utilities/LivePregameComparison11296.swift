import SwiftUI

/// #11296 / #9483 — A LIVE GAME'S CURRENT PROJECTED FINAL, AND THE ONE BEFORE IT.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on iPhone, a reader sees the retained
/// pregame projected final beneath the current one, with the same teams in the
/// same order and the same scoring period.
///
/// This is the Swift half of `frontend/lib/livePregameComparison.ts` (ux
/// `95838e0de4`), ported gate for gate. The producer
/// (`backend/app/utils/pregame_projection.py`, PR #11401) also serves
/// `pregame_projection` on the event detail of a row printed `live`: each
/// sportsbook's last pair strictly before the SCHEDULED start, the same object
/// a final carries. `currentOdds.liveProjection` is the separate in-play pair,
/// built only from rows confirmed at or after that start. They may still print
/// the same numbers: a line quoted before the start and confirmed unchanged
/// after it is an honest reading in both, so nothing here asks them to differ.
///
/// `FinalForecastComparison11296.resolve` is NOT reused: it requires a
/// finished status and an actual final score with its period, and a live game
/// has neither. Calling it with a made-up status, or with the current forecast
/// standing in for a score, would print a comparison the page does not hold.
/// This file checks the same baseline fields it checks, field for field, and
/// replaces the final-only half with a live-only one:
///
///   - LIVE        the row's status is `live`. A final has its own line.
///   - CURRENT     only `LiveProjectedFinal2920`'s admitted `Printed` — the
///                 typed in-play pair, after every gate the page applies —
///                 carries a unit, period and scheduled start. The ladders'
///                 in-game pair carries none of them, so a page printing it
///                 shows no baseline: the period is never inferred from the
///                 sport's name. The caller hands it in only when the page
///                 prints that pair (`EventDetailView.liveBaseline11296`).
///   - SAME UNIT,  the baseline's `unit` and `period` equal the admitted
///     PERIOD,     pair's, and its `boundary_at` equals both this row's
///     START       `commenceTime` and the admitted pair's scheduled start. It
///                 was captured strictly before that boundary.
///
/// What it does not check, on purpose: the actual score. A forecast made
/// before the game can sit below today's score and is still what was
/// expected then — reachability binds the current forecast, not history.
///
/// Soccer: the baseline is a 90-minute forecast and stays one in extra time.
/// The current pair is withheld outside regulation play, so there is nothing
/// to compare and the 90-minute pair is never set beside an extra-time game.
///
/// Every refusal answers nil and the caller prints only what it already
/// printed: a missing or incompatible baseline never removes a valid current
/// forecast. No grading, no difference row, no colour. Keyed home/away, never
/// sorted by value; rounded the way the cards round.
///
/// Two hosts print it (`EventDetailView.liveForecast11296` decides for both):
/// the adopted NFL/NBA row, under its current figure and caption; and the
/// generic hero every other live page uses (soccer, college football, the
/// other basketball leagues), as `LiveHeadlineForecast11296` — the current
/// pair under its own label, the retained pair beneath it.
enum LivePregameComparison11296 {

    /// What the line prints, and where it came from for a details surface.
    /// Every time is the producer's own.
    nonisolated struct Comparison: Equatable, Sendable {
        /// The final line's own words: the reading is the same one, before the
        /// same start, with the 90-minute basis said for soccer.
        let label: String
        let away: Int
        let home: Int
        let bookmakerCount: Int
        let earliestCapturedAt: Date
        let latestCapturedAt: Date
        let scheduledStart: Date
    }

    /// A live headline's forecast: the admitted in-play pair the page prints,
    /// and the retained pair beneath it when it compares. A nil baseline still
    /// prints the current pair.
    nonisolated struct Headline: Equatable, Sendable {
        let current: LiveProjectedFinalAdmission2920.Printed
        let baseline: Comparison?
    }

    /// The retained pregame pair to print beneath a live game's current
    /// projected final, or nil when it cannot be compared honestly. Nil adds
    /// nothing.
    ///
    /// - Parameters:
    ///   - status: the row's served status.
    ///   - commenceTime: the row's `commenceTime`; both pairs are measured from it.
    ///   - current: the admitted in-play pair the page prints, or nil.
    ///   - projection: the row's `pregameProjection`.
    static func resolve(
        status: String?,
        sport: String?,
        commenceTime: String?,
        current: LiveProjectedFinalAdmission2920.Printed?,
        projection p: PregameProjection?
    ) -> Comparison? {
        guard status == "live", let current, let p else { return nil }

        // The baseline's own fields, as the final comparison checks them.
        guard p.kind == FinalForecastComparison11296.kindLastBeforeScheduledStart,
              p.boundary == "scheduled_start",
              p.source == "sportsbooks",
              p.basis == FinalForecastComparison11296.basisConsensusSpreadTotal else { return nil }
        guard let format = LiveProjectedFinalAdmission2920.format(forSport: sport),
              p.unit == format.unit.rawValue,
              p.period == format.period.rawValue else { return nil }

        // Comparable with the pair above it: the same quantity over the same period.
        let now = current.admitted.provenance
        guard p.unit == now.unit.rawValue, p.period == now.period.rawValue else { return nil }

        guard let books = p.bookmakerCount.flatMap({ Int(exactly: $0) }), books >= 1 else { return nil }
        guard let earliest = p.earliestCapturedAt?.asDate,
              let latest = p.latestCapturedAt?.asDate,
              let boundary = p.boundaryAt?.asDate,
              earliest <= latest, latest < boundary else { return nil }

        // Same game, same start: read before the start this row carries, which
        // is the start the in-play pair was measured from.
        guard let rowStart = commenceTime?.asDate,
              boundary == rowStart, boundary == now.scheduledStart else { return nil }

        guard let home = p.projectedHomeScore, let away = p.projectedAwayScore,
              home.isFinite, away.isFinite, home > 0, away > 0 else { return nil }
        let vocab = SportVocab.forSport(sport)
        guard vocab.sportsbookSpreadIsAMargin else { return nil }
        guard let roundedHome = Int(exactly: home.rounded()),
              let roundedAway = Int(exactly: away.rounded()) else { return nil }
        guard roundedHome != roundedAway || vocab.canEndInATie else { return nil }

        return Comparison(
            label: format.period == .regulation
                ? FinalForecastComparison11296.label90Min : FinalForecastComparison11296.label,
            away: roundedAway, home: roundedHome, bookmakerCount: books,
            earliestCapturedAt: earliest, latestCapturedAt: latest, scheduledStart: boundary)
    }

    /// #9483 A3 — the admitted retained pair's served halves, unrounded, for
    /// the live Projected finish card: only when `headline` (decided from this
    /// same `projection`) printed a baseline; nil otherwise. Nothing is
    /// re-derived — `resolve` already refused any non-finite or non-positive half.
    nonisolated static func servedHalves(_ headline: Headline?, projection p: PregameProjection?)
        -> (away: Double, home: Double)? {
        guard headline?.baseline != nil, let p, let away = p.projectedAwayScore,
              let home = p.projectedHomeScore else { return nil }
        return (away: away, home: home)
    }

    /// The visible pair, away then home as the current figure reads, each score
    /// glued to its team by a no-break space.
    nonisolated static func pairText(_ c: Comparison, awayName: String, homeName: String) -> String {
        "\(awayName)\u{00A0}\(c.away) · \(homeName)\u{00A0}\(c.home)"
    }

    /// One sentence for assistive tech that names both teams and the phase.
    nonisolated static func spokenText(_ c: Comparison, awayName: String, homeName: String) -> String {
        "\(c.label): \(awayName) \(c.away), \(homeName) \(c.home)"
    }

    /// The generic headline's one spoken label: the current pair under its own
    /// label (soccer's says "(90 min)"), then the retained one when it prints.
    nonisolated static func spokenText(_ h: Headline, awayName: String, homeName: String) -> String {
        let current = LiveProjectedFinal2920.spokenText(h.current, awayName: awayName, homeName: homeName)
        guard let baseline = h.baseline else { return current }
        return "\(current). " + spokenText(baseline, awayName: awayName, homeName: homeName)
    }
}

/// The live forecast in the generic hero (a page the paired headline does not
/// adopt): the admitted pair's own label and both named teams' numbers, the
/// pair in the primary colour so it leads, then the retained pair beneath it.
/// The actual score stays in the arm above; nothing here is a score. Wraps at
/// any text size and is never scaled down.
struct LiveHeadlineForecast11296: View {
    let forecast: LivePregameComparison11296.Headline
    let awayName: String
    let homeName: String

    static let accessibilityIdentifier = "live-headline-forecast-11296"

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            VStack(alignment: .leading, spacing: 2) {
                Text(forecast.current.label)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(LiveProjectedFinal2920.pairText(forecast.current, awayName: awayName, homeName: homeName))
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundStyle(Color.primary)
            }
            if let baseline = forecast.baseline {
                LivePregameBaselineLine11296(comparison: baseline, awayName: awayName, homeName: homeName)
            }
        }
        .multilineTextAlignment(.leading)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            LivePregameComparison11296.spokenText(forecast, awayName: awayName, homeName: homeName))
        .accessibilityIdentifier(Self.accessibilityIdentifier)
    }
}

/// The retained pair drawn beneath the live headline's current projected
/// final: the label, then both named teams. Secondary colour, at the host's
/// current-caption font so it never outgrows the label of the pair it sits
/// under (Design, 2026-10-22); wraps at any text size and is never scaled down.
struct LivePregameBaselineLine11296: View {
    let comparison: LivePregameComparison11296.Comparison
    let awayName: String
    let homeName: String
    /// The host's current-caption font: the generic hero's `.caption`, the
    /// paired row's `.caption2`.
    var font: Font = .caption

    static let accessibilityIdentifier = "live-pregame-baseline-11296"

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(comparison.label)
            Text(LivePregameComparison11296.pairText(comparison, awayName: awayName, homeName: homeName))
        }
        .font(font)
        .foregroundStyle(.secondary)
        .multilineTextAlignment(.leading)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            LivePregameComparison11296.spokenText(comparison, awayName: awayName, homeName: homeName))
        .accessibilityIdentifier(Self.accessibilityIdentifier)
    }
}

/// #11296 — WHERE THE LIVE HEADLINE'S FORECASTS CAME FROM, in the page's
/// existing information popover (`FreshnessRevealView`, opened by the same
/// control that reports delivery and confidence). Not a headline row, badge,
/// button or fetch: it prints what `EventDetailView.liveForecast11296` already
/// admitted for the pair the headline prints, and decides nothing.
///
/// Each forecast keeps its own facts, never the other's and never the phone's:
///
///   - CURRENT    its own sportsbook count and its EARLIEST confirmation — the
///                oldest of the contributing quotes' confirmations, so the
///                stalest line in the pair. Its latest capture is NOT printed:
///                a quote first seen before the start and reconfirmed after it
///                carries an old capture time, which is not a last update, a
///                confirmation or a kickoff.
///   - RETAINED   its own count, the RANGE its lines were recorded in (each
///                sportsbook's last line before the start was taken at its own
///                time; there is no single "recorded at"), and the scheduled
///                start they were taken before — listed, never observed.
///   - BASIS      one sentence: both are worked out from the sportsbooks'
///                spread and total, over the period the label already names.
///
/// No app receipt time appears here: that clock describes delivery to this
/// phone and stays in the delivery details above the divider. A forecast with
/// no retained pair prints no retained section — nothing is reconstructed.
/// Local dates and times, the date always said.
struct LiveForecastDetails11296: View {
    let forecast: LivePregameComparison11296.Headline

    static let accessibilityIdentifier = "live-forecast-details-11296"

    /// One forecast's facts: its own label, then its lines.
    nonisolated struct Section: Equatable, Sendable {
        let title: String
        let lines: [String]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(Self.sections(forecast).enumerated()), id: \.offset) { _, section in
                VStack(alignment: .leading, spacing: 2) {
                    Text(section.title).fontWeight(.semibold)
                    ForEach(Array(section.lines.enumerated()), id: \.offset) { _, line in
                        Text(line).foregroundStyle(.secondary)
                    }
                }
                .accessibilityElement(children: .combine)
            }
            Text(Self.basis(forecast.current.admitted.provenance.period))
                .foregroundStyle(.secondary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier(Self.accessibilityIdentifier)
    }

    /// The current forecast first, then the retained one when it prints.
    nonisolated static func sections(
        _ h: LivePregameComparison11296.Headline,
        calendar: Calendar = .current, locale: Locale = .current
    ) -> [Section] {
        let now = h.current.admitted.provenance
        var sections = [Section(title: h.current.label, lines: [
            from(now.bookmakerCount),
            "Oldest confirmation \(clock(now.earliestConfirmedAt, calendar: calendar, locale: locale))",
        ])]
        if let b = h.baseline {
            sections.append(Section(title: b.label, lines: [
                from(b.bookmakerCount),
                "Lines recorded \(recordedRange(b.earliestCapturedAt, b.latestCapturedAt, calendar: calendar, locale: locale))",
                "Scheduled start \(clock(b.scheduledStart, calendar: calendar, locale: locale))",
            ]))
        }
        return sections
    }

    nonisolated static func from(_ count: Int) -> String {
        "From \(count) \(count == 1 ? "sportsbook" : "sportsbooks")"
    }

    /// The method, with the period each pair settles on.
    nonisolated static func basis(_ period: LiveProjectedFinalAdmission2920.ScorePeriod) -> String {
        switch period {
        case .fullGame:
            return "Worked out from the sportsbooks' spread and total for the full game, overtime included."
        case .regulation:
            return "Worked out from the sportsbooks' spread and total for 90 minutes plus stoppage time, not extra time."
        }
    }

    /// A local date and time: "Oct 21 at 7:42 PM" in US English.
    nonisolated static func clock(_ date: Date, calendar: Calendar, locale: Locale) -> String {
        date.formatted(Date.FormatStyle(locale: locale, calendar: calendar, timeZone: calendar.timeZone)
            .month(.abbreviated).day().hour().minute())
    }

    /// "Oct 18 at 9:29 AM – 9:59 AM"; the date repeats only when the local day
    /// changes, and one instant prints once.
    nonisolated static func recordedRange(_ earliest: Date, _ latest: Date,
                                          calendar: Calendar, locale: Locale) -> String {
        let first = clock(earliest, calendar: calendar, locale: locale)
        guard earliest != latest else { return first }
        let second = calendar.isDate(earliest, inSameDayAs: latest)
            ? latest.formatted(Date.FormatStyle(locale: locale, calendar: calendar, timeZone: calendar.timeZone)
                .hour().minute())
            : clock(latest, calendar: calendar, locale: locale)
        return "\(first) – \(second)"
    }
}
