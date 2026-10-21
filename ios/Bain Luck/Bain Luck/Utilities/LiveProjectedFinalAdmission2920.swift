import Foundation

/// #2920 / #9483 — A LIVE GAME'S PROJECTED FINAL: ONE MARKED IN-PLAY PAIR,
/// ADMITTED IN ONE PLACE.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: a native live card and the event headline
/// show a supported projected final beside — never instead of — the actual
/// score, and withhold it when the forecast cannot be trusted.
///
/// This is the Swift half of `admittedLiveProjection` / `liveCardProjectedFinal`
/// in `frontend/lib/projectedFinalPair.ts` (accepted `af2d236030`), ported gate
/// for gate, over the object `CurrentOdds.liveProjection` decodes (producer
/// `a8df6e34cd`, `card_projected_pair._live_projection`). Why the bare
/// `currentOdds.projectedHomeScore` / `projectedAwayScore` cannot be the live
/// forecast: detail and search serve them through a stale filter that falls
/// back to EVERY book when none has quoted since the start, so on a live game
/// they can hold the pregame pair with nothing to say so. The producer marks
/// the one pair it can prove is in play, and a live surface reads only that.
///
/// Read only the object. Absent, malformed, or present and refused, the answer
/// is the same: no current pair. Nothing here falls back to the bare
/// `projected_*` keys, a ladder pair, the probability chart's baseline or the
/// finished-game `PregameProjection` (#11296) — and a live object never
/// becomes a finished game's forecast: a row that is not live is refused
/// before the object is read.
///
/// What it admits, each refused rather than guessed:
///
///   - LIFECYCLE   the caller's status says `live` and the caller's clock has
///                 passed this row's start (web FeedCard's `isLive` and start
///                 test). Scheduled, suspended, finished and unknown answer no.
///   - LABELS      kind `in_play`, boundary `commence_time`, source
///                 `sportsbooks`, basis `consensus_spread_total`.
///   - FORMAT      web's `projectedFinalFormat` table: points over the full game
///                 for football and basketball, goals over regulation (90
///                 minutes) for soccer. The object's unit and period must be the
///                 sport's. Hockey, baseball, tennis, fights and every
///                 undeclared sport answer no — unsupported, not a gap.
///   - COUNT       a whole number of sportsbooks, at least one.
///   - ROW START   this row's start parses, and the object's boundary is not
///                 before it: an object measured from an earlier start (cached,
///                 or the start moved later) could pass pregame quotes off as
///                 in play. A start the row itself calls a placeholder
///                 (`startIsTbd == true`) or not a schedule's
///                 (`startIsFromSchedule == false`) refuses, as the producer
///                 refuses those starts; absent flags (an older server or a card
///                 built from another route) leave the producer's own check to
///                 stand. The boundary is the SCHEDULED start, never an observed
///                 kickoff.
///   - CLOCKS      the earliest confirmation is not before the boundary. The
///                 latest capture must be present and is compared with nothing:
///                 a quote first captured before the start and reconfirmed after
///                 it is an honest in-play reading, so it may precede both the
///                 boundary and the earliest confirmation. No other ordering
///                 between clocks, no freshness timeout, no attempt-time stand-in.
///   - PHASE       soccer only, because its lines settle on 90 minutes: the
///                 caller's evidence must say regulation is being played. An
///                 unknown phase refuses, and so does an authoritative move to
///                 extra time or a shootout — a held object must not go on
///                 reading as a regulation final after it. Football and
///                 basketball are full game, overtime included.
///   - PAIR        web's `cardProjectedFinal`: both halves present, finite, not
///                 below zero, the sport's spread a margin, each half above zero,
///                 rounded per side, and a level pair refused where the sport
///                 cannot end level (#8156).
///   - SCORE       the actual printed score is on the row and each rounded half
///                 is reachable from it: goals and points are never taken back.
///
/// Team order is keyed (home/away), never sorted by value. No grading, colour,
/// fetch, mutation or clock of its own: every input is the caller's.
enum LiveProjectedFinalAdmission2920 {

    /// The producer's labels, character for character.
    static let kindInPlay = "in_play"
    static let boundaryCommenceTime = "commence_time"
    static let sourceSportsbooks = "sportsbooks"
    static let basisConsensusSpreadTotal = "consensus_spread_total"

    /// The unit the scoreboard counts in.
    nonisolated enum ScoreUnit: String, Sendable {
        case points
        case goals
    }

    /// The stretch of play the sportsbooks' lines settle on.
    nonisolated enum ScorePeriod: String, Sendable {
        case fullGame = "full_game"
        case regulation
    }

    /// One row of web's `PROJECTED_FINAL_FORMATS`; `label` is web's visible
    /// label, character for character.
    nonisolated struct Format: Equatable, Sendable {
        let unit: ScoreUnit
        let period: ScorePeriod
        let label: String
    }

    /// Web's `projectedFinalFormat` + `projectedFinalPeriod`. Nil is a
    /// statement: this sport's sportsbook pair is not a final score.
    nonisolated static func format(forSport sportKey: String?) -> Format? {
        let key = (sportKey ?? "").lowercased()
        if key.hasPrefix("americanfootball_") || key.hasPrefix("basketball_") {
            return Format(unit: .points, period: .fullGame, label: "Projected final")
        }
        if key.hasPrefix("soccer_") {
            return Format(unit: .goals, period: .regulation, label: "Projected final (90 min)")
        }
        return nil
    }

    /// Where a soccer match is, from evidence the caller holds. Nil is
    /// unknown, and unknown refuses a regulation object.
    nonisolated enum Phase: Equatable, Sendable {
        /// A half, halftime, or a minute of regulation.
        case regulation
        /// Extra time or a shootout, on authority the caller trusts.
        case beyondRegulation
    }

    /// The producer's `soccer_regulation_in_play`, ported: a half, halftime, a
    /// minute from 0 to 90, or stoppage after 45 or 90 is regulation, compared
    /// lower-cased and trimmed. A minute past 90 with no stoppage mark is extra
    /// time (the producer's own reading). Everything else — empty, `ET`,
    /// `Pen.`, `FT`, an odd stoppage, a non-ASCII digit — is unknown.
    nonisolated static func soccerPhase(servedPeriod: String?) -> Phase? {
        let text = (servedPeriod ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if regulationPhases.contains(text) { return .regulation }
        guard let match = matchMinute(text) else { return nil }
        if match.stoppage { return match.minute == 45 || match.minute == 90 ? .regulation : nil }
        return match.minute <= 90 ? .regulation : .beyondRegulation
    }

    /// The producer's `_SOCCER_REGULATION_PHASES`.
    nonisolated private static let regulationPhases: Set<String> = [
        "1st half", "2nd half", "first half", "second half", "1h", "2h",
        "ht", "halftime", "half time", "half-time",
    ]

    /// The producer's `_SOCCER_MINUTE`, `^(\d{1,3})'?(?:\s*\+\s*(\d{1,2})'?)?$`,
    /// by hand: the minute, and whether a stoppage mark followed it.
    nonisolated private static func matchMinute(_ text: String) -> (minute: Int, stoppage: Bool)? {
        let chars = Array(text)
        var i = 0
        func digits(max: Int) -> Int? {
            var value = 0, count = 0
            while i < chars.count, count < max, let d = chars[i].asciiDigit {
                value = value * 10 + d
                count += 1
                i += 1
            }
            // A digit past the cap fails the pattern rather than splitting.
            guard count > 0, !(i < chars.count && chars[i].asciiDigit != nil) else { return nil }
            return value
        }
        func skipSpace() { while i < chars.count, chars[i].isWhitespace { i += 1 } }

        guard let minute = digits(max: 3) else { return nil }
        if i < chars.count, chars[i] == "'" { i += 1 }
        if i == chars.count { return (minute: minute, stoppage: false) }
        skipSpace()
        guard i < chars.count, chars[i] == "+" else { return nil }
        i += 1
        skipSpace()
        guard digits(max: 2) != nil else { return nil }
        if i < chars.count, chars[i] == "'" { i += 1 }
        return i == chars.count ? (minute: minute, stoppage: true) : nil
    }

    /// This row's own start, as the row the caller holds says it.
    nonisolated struct RowStart: Equatable, Sendable {
        /// The row's `commenceTime`.
        let commenceTime: String?
        /// `startIsTbd`. `true` refuses; nil and `false` do not.
        var isTBD: Bool? = nil
        /// `startIsFromSchedule`. `false` refuses; nil and `true` do not.
        var isFromSchedule: Bool? = nil
    }

    /// Where the admitted pair came from, for the details surface. Every time
    /// is the producer's own; none is a receipt or an observed kickoff.
    nonisolated struct Provenance: Equatable, Sendable {
        let bookmakerCount: Int
        /// `boundary_at`: the scheduled start the object was measured from.
        let scheduledStart: Date
        /// The oldest time a contributing quote was last confirmed.
        let earliestConfirmedAt: Date
        /// The newest time a contributing quote first appeared; may precede
        /// `scheduledStart`.
        let latestCapturedAt: Date
        let unit: ScoreUnit
        let period: ScorePeriod
    }

    /// The object's pair as served, once every admission gate has passed —
    /// web's `admittedLiveProjection`.
    nonisolated struct AdmittedPair: Equatable, Sendable {
        let home: Double
        let away: Double
        let provenance: Provenance
    }

    /// What a live card or headline prints: rounded per side, keyed.
    nonisolated struct Printed: Equatable, Sendable {
        let label: String
        let home: Int
        let away: Int
        let admitted: AdmittedPair
    }

    /// The first gate that said no. For tests and diagnostics, never for a
    /// reader: a refused pair prints nothing and explains nothing.
    nonisolated enum Refusal: String, Equatable, Sendable {
        case notLive
        case notStarted
        case absent
        case rowStartUnreadable
        case rowStartPlaceholder
        case rowStartNotFromSchedule
        case kind
        case boundary
        case source
        case basis
        case unsupportedSport
        case unit
        case period
        case bookmakerCount
        case clockUnreadable
        case boundaryBeforeRowStart
        case confirmedBeforeBoundary
        case pairMalformed
        case phaseUnknown
        case beyondRegulation
        case noActualScore
        case pairNotPrintable
        case levelPair
        case unreachable
    }

    nonisolated enum Admission: Equatable, Sendable {
        case admitted(AdmittedPair)
        case refused(Refusal)
    }

    nonisolated enum Outcome: Equatable, Sendable {
        case printed(Printed)
        case withheld(Refusal)

        var printed: Printed? {
            if case .printed(let p) = self { return p }
            return nil
        }

        var refusal: Refusal? {
            if case .withheld(let r) = self { return r }
            return nil
        }
    }

    /// The object alone against this row's sport and start, with no lifecycle,
    /// score or phase — web's `admittedLiveProjection`, plus the row-start
    /// flags above.
    static func admit(_ projection: LiveProjection?, sport: String?, rowStart: RowStart) -> Admission {
        guard let p = projection else { return .refused(.absent) }

        guard let rowStartAt = rowStart.commenceTime?.asDate else { return .refused(.rowStartUnreadable) }
        guard rowStart.isTBD != true else { return .refused(.rowStartPlaceholder) }
        guard rowStart.isFromSchedule != false else { return .refused(.rowStartNotFromSchedule) }

        guard p.kind == kindInPlay else { return .refused(.kind) }
        guard p.boundary == boundaryCommenceTime else { return .refused(.boundary) }
        guard p.source == sourceSportsbooks else { return .refused(.source) }
        guard p.basis == basisConsensusSpreadTotal else { return .refused(.basis) }

        guard let format = format(forSport: sport) else { return .refused(.unsupportedSport) }
        guard p.unit == format.unit.rawValue else { return .refused(.unit) }
        guard p.period == format.period.rawValue else { return .refused(.period) }

        // `Int(exactly:)` refuses NaN, infinity, fractions and a finite value
        // Int cannot hold — web's `Number.isInteger`, without a trap.
        guard let books = p.bookmakerCount.flatMap({ Int(exactly: $0) }), books >= 1 else {
            return .refused(.bookmakerCount)
        }

        guard let boundaryAt = p.boundaryAt?.asDate,
              let earliest = p.earliestConfirmedAt?.asDate,
              let latest = p.latestCapturedAt?.asDate else { return .refused(.clockUnreadable) }
        guard boundaryAt >= rowStartAt else { return .refused(.boundaryBeforeRowStart) }
        guard earliest >= boundaryAt else { return .refused(.confirmedBeforeBoundary) }

        // Web's `sportsbookProjectedPair`: a scoreline only where the sport's
        // spread is a margin, and no scoreboard reads below zero.
        guard let home = p.projectedHomeScore, let away = p.projectedAwayScore,
              home.isFinite, away.isFinite, home >= 0, away >= 0,
              SportVocab.forSport(sport).sportsbookSpreadIsAMargin else { return .refused(.pairMalformed) }

        return .admitted(AdmittedPair(
            home: home, away: away,
            provenance: Provenance(
                bookmakerCount: books, scheduledStart: boundaryAt,
                earliestConfirmedAt: earliest, latestCapturedAt: latest,
                unit: format.unit, period: format.period)))
    }

    /// The live projected final to print beside this row's actual score, or
    /// why not. One answer for the card and the headline it opens.
    ///
    /// - Parameters:
    ///   - projection: `currentOdds?.liveProjection`, and nothing else.
    ///   - status: the row's served status.
    ///   - homeScore/awayScore: the actual score the surface PRINTS.
    ///   - phase: soccer's phase from the caller's evidence (`soccerPhase` reads
    ///     a served period); ignored for full-game sports.
    ///   - now: the caller's clock, for the started test only.
    static func resolve(
        projection: LiveProjection?,
        sport: String?,
        status: String?,
        rowStart: RowStart,
        homeScore: Int?,
        awayScore: Int?,
        phase: Phase?,
        now: Date
    ) -> Outcome {
        guard status == "live" else { return .withheld(.notLive) }
        if let start = rowStart.commenceTime?.asDate, start > now { return .withheld(.notStarted) }

        let admitted: AdmittedPair
        switch admit(projection, sport: sport, rowStart: rowStart) {
        case .refused(let why): return .withheld(why)
        case .admitted(let pair): admitted = pair
        }

        if admitted.provenance.period == .regulation {
            switch phase {
            case .regulation?: break
            case .beyondRegulation?: return .withheld(.beyondRegulation)
            case nil: return .withheld(.phaseUnknown)
            }
        }

        guard let homeScore, let awayScore, homeScore >= 0, awayScore >= 0 else {
            return .withheld(.noActualScore)
        }

        // `.rounded()` rounds half away from zero, which equals JS `Math.round`
        // for the positive values that reach here. A finite half too large for
        // Int withholds the line instead of trapping.
        guard admitted.home > 0, admitted.away > 0,
              let home = Int(exactly: admitted.home.rounded()),
              let away = Int(exactly: admitted.away.rounded()) else { return .withheld(.pairNotPrintable) }
        guard home != away || SportVocab.forSport(sport).canEndInATie else { return .withheld(.levelPair) }
        guard home >= homeScore, away >= awayScore else { return .withheld(.unreachable) }

        guard let format = format(forSport: sport) else { return .withheld(.unsupportedSport) }
        return .printed(Printed(label: format.label, home: home, away: away, admitted: admitted))
    }
}

private extension Character {
    /// 0–9 for an ASCII digit, else nil.
    nonisolated var asciiDigit: Int? {
        guard let v = asciiValue, v >= 48, v <= 57 else { return nil }
        return Int(v - 48)
    }
}
