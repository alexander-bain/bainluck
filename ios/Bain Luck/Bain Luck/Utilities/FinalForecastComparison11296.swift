import SwiftUI

/// #11296 — A FINISHED GAME'S ACTUAL RESULT BESIDE THE SCORE FORECAST BEFORE IT.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: a native finished-game card shows the
/// actual final, and under it one separate "Projection before scheduled start"
/// line, as the web cards do.
///
/// This is the Swift half of `frontend/lib/finalForecastComparison.ts`, ported
/// gate for gate. Why `currentOdds` cannot be the forecast: on a finished game
/// it is each sportsbook's LATEST row, which is in-play. The producer
/// (`backend/app/utils/pregame_projection.py`, `select_pregame_projection`)
/// serves a separate `pregame_projection` instead — each sportsbook's last pair
/// strictly before the SCHEDULED start — or `pregame_projection_unavailable`
/// naming why not. This file is the one place the app decides whether that
/// object may be printed under a final, and how.
///
/// It decides nothing the existing types already decide:
///
///   - finished      `EventState.isFinished` (completed or closed), the
///                   predicate every card uses, and web's `isFinishedStatus`.
///   - sport, sign,  `SportVocab.sportsbookSpreadIsAMargin` and `.canEndInATie`,
///     level pair    the same facts web's `cardProjectedFinal` reads; plus the
///                   format table below (web's `projectedFinalFormat`).
///
/// What it adds is only what a FINAL comparison needs, each refused rather than
/// guessed: the KIND (only `last_before_scheduled_start`, because the label
/// says exactly that), the BOUNDARY (`scheduled_start` only — nothing here
/// claims an observed kickoff), the SOURCE and BASIS the label and rounding
/// describe, the UNIT for the sport, and the PERIOD: the actual score must
/// cover what the forecast lines settle on. Football and basketball forecasts
/// are `full_game`; soccer's are `regulation`. A soccer final is compared only
/// when the producer serves `final_score_period: "regulation"` beside it (the
/// row's own stored period says the match ended at full time); extra time,
/// penalties and an unknown finish serve no such key and stay withheld.
/// `actualPeriod(sport:servedFinalScorePeriod:)` is every caller's one read of
/// it, web's `finalScorePeriod`. This file does not infer regulation from the
/// score, the clock, the competition or the forecast's own period.
///
/// No grading: nothing here says who the forecast favoured, whether it was
/// right, or picks a colour. Team order is keyed (home/away), never by value.
/// The actual pair is not returned: the card already prints it.
enum FinalForecastComparison11296 {

    /// The visible label over the forecast pair — web's `FINAL_FORECAST_LABEL`,
    /// character for character. It names what the numbers ARE and the boundary
    /// they were read before (Design R1 on PR #11311).
    static let label = "Projection before scheduled start"

    /// The same line over a soccer final — web's `FINAL_FORECAST_LABEL_90_MIN`,
    /// character for character. Both sides are 90-minute quantities (the line
    /// prints only beside a served regulation final), and the basis is said at
    /// the comparison, in the "(90 min)" the soccer pre-game line already uses.
    static let label90Min = "Projection (90 min) before scheduled start"

    /// The one kind the producer serves today, and the only one admitted.
    /// `latest_before_play` and `opening` are reserved by the producer and
    /// refused, so a new kind never prints under words describing another.
    static let kindLastBeforeScheduledStart = "last_before_scheduled_start"

    /// The one basis the producer serves: the pair is solved from a spread
    /// point and a total, which is the reading the rounding below assumes.
    static let basisConsensusSpreadTotal = "consensus_spread_total"

    /// The period a set of scores covers. `regulation` = play ended without
    /// extra time.
    nonisolated enum ScorePeriod: String, Sendable {
        case fullGame = "full_game"
        case regulation
    }

    /// What a card prints. Rounded exactly as web's card rounds it. Keyed,
    /// never sorted. No winner, hit/miss or colour field.
    nonisolated struct Comparison: Equatable, Sendable {
        let label: String
        let away: Int
        let home: Int
        let bookmakerCount: Int
    }

    /// Web's `projectedFinalFormat` table: which sports' sportsbook pair is a
    /// final score, and in what unit. Hockey, baseball, tennis, fights and
    /// every undeclared sport answer nil, so they answer nil here.
    nonisolated static func unit(forSport sportKey: String?) -> String? {
        let key = (sportKey ?? "").lowercased()
        if key.hasPrefix("americanfootball_") || key.hasPrefix("basketball_") { return "points" }
        if key.hasPrefix("soccer_") { return "goals" }
        return nil
    }

    /// What a finished game's actual score covers, for every caller to pass as
    /// `actualPeriod` — web's `finalScorePeriod`. Football and basketball: a
    /// scoreboard final is the full game, overtime included. Soccer: only the
    /// producer's served `final_score_period`, and only its one value
    /// `"regulation"`; absent, null or anything else is nil, so the comparison
    /// is withheld. Never `.fullGame` for soccer, and never the forecast's own
    /// `period`, which says nothing about the scoreboard.
    nonisolated static func actualPeriod(sport: String?, servedFinalScorePeriod: String?) -> ScorePeriod? {
        switch unit(forSport: sport) {
        case "points": return .fullGame
        case "goals": return servedFinalScorePeriod == ScorePeriod.regulation.rawValue ? .regulation : nil
        default: return nil
        }
    }

    /// A comparison that passed every gate, with the served halves it was
    /// rounded from. #9483 R2 — the finished page's other comparisons (the
    /// projected-finish card, the NBA margin and total) read THESE halves, so
    /// the headline and the cards under it compare the final with one pregame
    /// expectation. The halves are the served projection's own; no rounded
    /// display integer is ever turned back into a number.
    nonisolated struct Qualified: Equatable, Sendable {
        let comparison: Comparison
        let away: Double
        let home: Double
    }

    /// The forecast pair to print under a finished game's actual result, or
    /// nil when any part of it cannot be shown honestly. Nil prints nothing:
    /// no placeholder, no gap, no explanation.
    ///
    /// `actualPeriod` is what the actual score covers, from evidence the caller
    /// holds — `actualPeriod(sport:servedFinalScorePeriod:)`. Nil: refused.
    static func resolve(
        sport: String?,
        status: String?,
        homeScore: Int?,
        awayScore: Int?,
        actualPeriod: ScorePeriod?,
        projection p: PregameProjection?
    ) -> Comparison? {
        qualified(sport: sport, status: status, homeScore: homeScore, awayScore: awayScore,
                  actualPeriod: actualPeriod, projection: p)?.comparison
    }

    /// `resolve`'s gates, returning the served halves beside the printed pair.
    static func qualified(
        sport: String?,
        status: String?,
        homeScore: Int?,
        awayScore: Int?,
        actualPeriod: ScorePeriod?,
        projection p: PregameProjection?
    ) -> Qualified? {
        guard EventState.isFinished(status) else { return nil }
        guard let homeScore, let awayScore, homeScore >= 0, awayScore >= 0 else { return nil }
        guard let p else { return nil }

        guard p.kind == kindLastBeforeScheduledStart,
              p.boundary == "scheduled_start",
              p.source == "sportsbooks",
              p.basis == basisConsensusSpreadTotal else { return nil }

        guard let sportUnit = unit(forSport: sport), p.unit == sportUnit else { return nil }
        guard let actualPeriod, p.period == actualPeriod.rawValue else { return nil }

        // `Int(exactly:)` refuses NaN, infinity, fractions AND a finite value
        // Int cannot hold (1e19) — that one would trap in `Int(_:)`, and a
        // malformed number withholds the line, never the card.
        guard let books = p.bookmakerCount.flatMap({ Int(exactly: $0) }), books >= 1
        else { return nil }
        // The producer reads strictly before the boundary; anything else is
        // not the reading this label describes.
        guard let earliest = p.earliestCapturedAt?.asDate,
              let latest = p.latestCapturedAt?.asDate,
              let boundary = p.boundaryAt?.asDate,
              earliest <= latest, latest < boundary else { return nil }

        // Web's `cardProjectedFinal`: a score only where the sport's spread is
        // a margin, no half at or below zero, rounded per side, and a level
        // pair refused where the sport cannot end level (#8156). The NFL can
        // (a tie after one overtime), so a level NFL pair prints, as on web.
        guard let home = p.projectedHomeScore, let away = p.projectedAwayScore,
              home.isFinite, away.isFinite, home > 0, away > 0 else { return nil }
        let vocab = SportVocab.forSport(sport)
        guard vocab.sportsbookSpreadIsAMargin else { return nil }
        // `.rounded()` rounds half away from zero, which equals JS `Math.round`
        // for the positive values that reach here. A finite half too large for
        // Int withholds the line instead of trapping.
        guard let roundedHome = Int(exactly: home.rounded()),
              let roundedAway = Int(exactly: away.rounded()) else { return nil }
        guard roundedHome != roundedAway || vocab.canEndInATie else { return nil }

        return Qualified(
            comparison: Comparison(label: actualPeriod == .regulation ? label90Min : label,
                                   away: roundedAway, home: roundedHome, bookmakerCount: books),
            away: away, home: home)
    }

    /// The visible pair in the card's own order — both native cards stack away
    /// over home. Each score is glued to its team's name by a no-break space,
    /// so a number can never wrap onto a line under the other team.
    nonisolated static func pairText(_ c: Comparison, awayName: String, homeName: String) -> String {
        "\(awayName)\u{00A0}\(c.away) · \(homeName)\u{00A0}\(c.home)"
    }

    /// One sentence for assistive tech that names both teams.
    nonisolated static func spokenText(_ c: Comparison, awayName: String, homeName: String) -> String {
        "\(c.label): \(awayName) \(c.away), \(homeName) \(c.home)"
    }
}

/// `select_pregame_projection`'s served object, field for field. Every field is
/// optional and decoding NEVER throws: a malformed or partial object reads as
/// fields the resolver refuses, so one odd projection can never drop the card
/// (`FeedItem` decodes its event with `try`). Times are ISO-8601 strings; the
/// count is a `Double` so a fractional count is refused, as web's
/// `Number.isInteger` refuses it, rather than failing the decode.
nonisolated struct PregameProjection: Decodable, Sendable, Equatable {
    let projectedHomeScore: Double?
    let projectedAwayScore: Double?
    let kind: String?
    let earliestCapturedAt: String?
    let latestCapturedAt: String?
    let boundary: String?
    let boundaryAt: String?
    let source: String?
    let basis: String?
    let bookmakerCount: Double?
    let unit: String?
    let period: String?

    /// Matched after `.convertFromSnakeCase`, which every feed decoder uses.
    enum CodingKeys: String, CodingKey {
        case projectedHomeScore, projectedAwayScore, kind, earliestCapturedAt
        case latestCapturedAt, boundary, boundaryAt, source, basis, bookmakerCount
        case unit, period
    }
}

extension PregameProjection {
    /// In an extension so the memberwise initializer survives.
    nonisolated init(from decoder: Decoder) throws {
        let c = try? decoder.container(keyedBy: CodingKeys.self)
        func field<T: Decodable>(_ type: T.Type, _ key: CodingKeys) -> T? {
            guard let c else { return nil }
            return try? c.decodeIfPresent(type, forKey: key)
        }
        self.init(
            projectedHomeScore: field(Double.self, .projectedHomeScore),
            projectedAwayScore: field(Double.self, .projectedAwayScore),
            kind: field(String.self, .kind),
            earliestCapturedAt: field(String.self, .earliestCapturedAt),
            latestCapturedAt: field(String.self, .latestCapturedAt),
            boundary: field(String.self, .boundary),
            boundaryAt: field(String.self, .boundaryAt),
            source: field(String.self, .source),
            basis: field(String.self, .basis),
            bookmakerCount: field(Double.self, .bookmakerCount),
            unit: field(String.self, .unit),
            period: field(String.self, .period)
        )
    }
}

/// The line both finished cards and the event page's headline draw under the
/// actual final. Caption size, secondary colour, wraps at any text size; the
/// final score above it stays the primary number. One view so the three
/// surfaces cannot drift.
struct FinalForecastLine11296: View {
    let comparison: FinalForecastComparison11296.Comparison
    let awayName: String
    let homeName: String

    static let accessibilityIdentifier = "final-forecast-11296"

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(comparison.label)
            Text(FinalForecastComparison11296.pairText(comparison, awayName: awayName, homeName: homeName))
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .multilineTextAlignment(.leading)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            FinalForecastComparison11296.spokenText(comparison, awayName: awayName, homeName: homeName))
        .accessibilityIdentifier(Self.accessibilityIdentifier)
    }
}
