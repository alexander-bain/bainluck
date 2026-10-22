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

    /// The visible pair, away then home as the current figure reads, each score
    /// glued to its team by a no-break space.
    nonisolated static func pairText(_ c: Comparison, awayName: String, homeName: String) -> String {
        "\(awayName)\u{00A0}\(c.away) · \(homeName)\u{00A0}\(c.home)"
    }

    /// One sentence for assistive tech that names both teams and the phase.
    nonisolated static func spokenText(_ c: Comparison, awayName: String, homeName: String) -> String {
        "\(c.label): \(awayName) \(c.away), \(homeName) \(c.home)"
    }
}

/// The retained pair drawn beneath the live headline's current projected
/// final: the label, then both named teams. Caption size and secondary colour,
/// so the current figure above stays the one that leads; wraps at any text
/// size and is never scaled down.
struct LivePregameBaselineLine11296: View {
    let comparison: LivePregameComparison11296.Comparison
    let awayName: String
    let homeName: String

    static let accessibilityIdentifier = "live-pregame-baseline-11296"

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(comparison.label)
            Text(LivePregameComparison11296.pairText(comparison, awayName: awayName, homeName: homeName))
        }
        .font(.caption)
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
