import SwiftUI

/// #10868 — THE BASEBALL GAME SCREEN'S PRODUCTION ADAPTER, PART SEVEN: THE
/// EXTRA-INNINGS STORY (the approved fifth story family).
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on an MLB event page the extra-innings
/// story shows each outcome of the venue's extra-innings market with its
/// pregame chance beside a separately clocked chance recorded during play,
/// and the venue's own result for its contract — or each slot's own words —
/// and never an inning result nobody recorded.
///
/// Membership, order, labels, venues, the exact originals and the venue
/// results are the production card's: `MLBExtraInningsCard11284.build` over
/// THIS event's served `other` rows, filed by its own helper
/// (`MLBExtraInningsCard11284.isExtraInnings`), exactly as the final deck
/// deals it (`MLBFinalDeck11284`). The builder takes no phase, so the same
/// card serves every phase. `/game-markets` for another event is no card.
///
/// THE TWO CHANCES ARE THE OWNER'S ADMISSION, not read from the row here.
/// `GameMarketOther` decodes the row's ids, `probability`, `observed_at` and
/// grade, but not the served `pregame_mark` (nor `opening_over_probability`);
/// that model and history adoption are Native's. So the host passes
/// `BaseballExtraInningsAdmission10868` values, each naming one served row by
/// its exact provider identity (market id, contributor outcome ids, source),
/// and the adapter attaches one to an outcome only when exactly one admission
/// names exactly that row. Missing, foreign, duplicated or unmatched
/// admissions attach nothing, and the outcome keeps its words — the result-only
/// card that remains is partial, not complete.
///
/// Rules for an attached admission:
///   - pregame     a chance strictly between 0 and 1
///                 (`MLBOriginal11284.openChance`: an exact 0 or 1 is a
///                 settlement value). It has no clock of its own, so its line
///                 says "Time not recorded"; it is never the opening price
///                 under another name.
///   - recorded    a chance strictly between 0 and 1 with a readable clock at
///                 or after the listed first pitch (never under an unconfirmed
///                 start) and at or before now, and only once play has
///                 started. It is a recorded in-game chance with its own
///                 clock in every later view — never current, never a
///                 settlement.
///   - change      the two admitted chances' difference in percentage points
///                 (`deltaPointsNumber`), only when both are admitted.
///   - scale       one zero-based ceiling for every outcome: 25%, or the next
///                 5% above the largest admitted chance (the home-run card's
///                 shared-scale rule, `MLBHomeRunCard11284.scaleCeiling`).
///   - selection   the host's held outcome, unchanged (one the card no longer
///                 carries is the leaf's withdrawn words); else the first
///                 outcome with an admitted chance; else the first outcome.
///   - Details     the exact production original, with the admitted chances
///                 named in it so Details never contradicts the card.
///
/// No inning result is derived from a chance, the score or the final; the
/// venue result is the production card's own grade of its contract. Nothing
/// here fetches, subscribes or holds state.
enum BaseballExtraInningsAdapter10868 {
    typealias G = BaseballGamePageAdapter10868
    /// Now and the reader's calendar, time zone and locale.
    typealias Host = BaseballRunMilestonesAdapter10868.Host

    enum Words {
        static let pregameUnavailable = "Pregame chance unavailable"
        static let inGameUnavailable = "In-game chance unavailable"
        static let timeNotRecorded = "Time not recorded"
        static let recorded = "Recorded"
        static let since = "since pregame"
        static let noChange = "No change since pregame"
        static let pregameField = "Pregame chance"
        static let recordedField = "Recorded in game"
        static let pregameNote = "time not recorded, may be the opening price"
        static let note = "Note"
        static let historyNote = "Recorded values are history, not a current chance."
        static let inningResult = "Inning result"
        static let unavailable = "Unavailable"
    }

    // MARK: - The story

    /// The story for THIS event at `host.now`, or nil when the production card
    /// files no extra-innings row.
    static func story(_ event: EventDetail, markets: GameMarketsResponse?,
                      admissions: [BaseballExtraInningsAdmission10868], selected: String?,
                      host: Host) -> BaseballExtraInningsStory10868? {
        let rows = markets.flatMap { $0.eventId == event.id ? $0.other : nil } ?? []
        let filed = rows.filter { MLBExtraInningsCard11284.isExtraInnings($0) }
        guard let card = MLBExtraInningsCard11284.build(rows, eventID: event.id),
              card.outcomes.count == filed.count else { return nil }
        let phase = G.phase(event, now: host.now)
        let options = zip(filed, card.outcomes).map { row, outcome in
            option(outcome, admission: admission(for: row, in: admissions), event: event, phase: phase, host: host)
        }
        let chosen = selected
            ?? options.first { $0.pregame.probability != nil || $0.recorded.probability != nil }?.id
            ?? options.first?.id
        return BaseballExtraInningsStory10868(
            card: card, options: options, selectedID: chosen,
            ceiling: ceiling(options.flatMap { [$0.pregame.probability, $0.recorded.probability] }),
            color: DS.blue)
    }

    /// The one admission naming exactly this served row, or nil.
    static func admission(for row: GameMarketOther,
                          in admissions: [BaseballExtraInningsAdmission10868]) -> BaseballExtraInningsAdmission10868? {
        guard let market = row._marketId, let outcomes = row.contributorOutcomeIds, !outcomes.isEmpty,
              let source = row.source, !source.isEmpty else { return nil }
        let matches = admissions.filter { $0.marketID == market && $0.outcomeIDs == outcomes && $0.source == source }
        return matches.count == 1 ? matches.first : nil
    }

    static func option(_ outcome: MLBExtraInningsCard11284.Outcome, admission: BaseballExtraInningsAdmission10868?,
                       event: EventDetail, phase: BaseballEventPagePhase10868, host: Host) -> BaseballExtraInningsOption10868 {
        let pregame = Self.pregame(admission)
        let recorded = Self.recorded(admission, event: event, phase: phase, venue: outcome.venue, host: host)
        return BaseballExtraInningsOption10868(
            id: outcome.original.id, label: outcome.label, venue: outcome.venue, venueResult: outcome.venueResult,
            pregame: pregame, recorded: recorded, change: change(pregame: pregame, recorded: recorded),
            original: original(outcome.original, pregame: pregame, recorded: recorded, admission: admission))
    }

    // MARK: - The two chances

    static func pregame(_ admission: BaseballExtraInningsAdmission10868?) -> BaseballExtraInningsChance10868 {
        guard let value = MLBOriginal11284.openChance(admission?.pregame) else {
            return .unavailable(Words.pregameUnavailable)
        }
        let text = formatProbability(value)
        return .value(probability: value, text: text, provenance: Words.timeNotRecorded,
                      spoken: "\(BaseballExtraInningsWords10868.pregameLabel) \(G.spokenPercent(text)), "
                          + Words.timeNotRecorded.lowercased())
    }

    static func recorded(_ admission: BaseballExtraInningsAdmission10868?, event: EventDetail,
                         phase: BaseballEventPagePhase10868, venue: String?,
                         host: Host) -> BaseballExtraInningsChance10868 {
        guard phase != .before, let admission,
              let value = MLBOriginal11284.openChance(admission.recorded),
              let at = admission.recordedAt?.asDate,
              event.startIsTbd != true, let start = event.commenceTime?.asDate,
              at >= start, at <= host.now
        else { return .unavailable(Words.inGameUnavailable) }
        let text = formatProbability(value)
        let clock = G.clockWords(at, host: host.page)
        let line = "\(Words.recorded) \(clock)"
        return .value(probability: value, text: text, provenance: G.joined([line, venue]) ?? line,
                      spoken: "\(BaseballExtraInningsWords10868.recordedLabel) \(G.spokenPercent(text)), "
                          + "\(Words.recorded.lowercased()) \(clock)")
    }

    /// "Up 5.0 points since pregame", only when both chances are admitted.
    static func change(pregame: BaseballExtraInningsChance10868,
                       recorded: BaseballExtraInningsChance10868) -> String? {
        guard let before = pregame.probability, let later = recorded.probability else { return nil }
        let points = (later - before) * 100
        guard points != 0 else { return Words.noChange }
        let magnitude = abs(points) < 0.05 ? "<0.1" : deltaPointsNumber(points)
        return "\(points > 0 ? "Up" : "Down") \(magnitude) points \(Words.since)"
    }

    /// 25%, or the next 5% above the largest admitted chance; never above 100%.
    static func ceiling(_ chances: [Double?]) -> Double {
        let top = chances.compactMap { $0 }.max() ?? 0
        return min(1, max(0.25, (top * 20).rounded(.up) / 20))
    }

    // MARK: - Details

    /// The exact production original with its pregame field set to the
    /// admitted chance, the recorded in-game chance added at its own stamp,
    /// and the history note. Unadmitted slots keep the production words.
    static func original(_ base: MLBOriginal11284, pregame: BaseballExtraInningsChance10868,
                         recorded: BaseballExtraInningsChance10868,
                         admission: BaseballExtraInningsAdmission10868?) -> MLBOriginal11284 {
        typealias Field = MLBOriginal11284.Field
        var sections = base.sections
        if let index = sections.indices.first, case .value(_, let text, _, _) = pregame {
            sections[index] = MLBOriginal11284.Section(
                title: sections[index].title,
                fields: sections[index].fields.map {
                    $0.label == Words.pregameField ? Field(label: $0.label, value: "\(text) · \(Words.pregameNote)") : $0
                })
        }
        var added: [Field] = []
        if case .value(_, let text, _, _) = recorded {
            added.append(Field(label: Words.recordedField,
                               value: "\(text) · \(MLBOriginal11284.stamp(admission?.recordedAt))"))
        }
        added.append(Field(label: Words.note, value: Words.historyNote))
        added.append(Field(label: Words.inningResult, value: Words.unavailable))
        sections.append(MLBOriginal11284.Section(title: nil, fields: added))
        return MLBOriginal11284(id: base.id, title: base.title, sections: sections)
    }
}

/// THE OWNER'S ADMISSION OF ONE EXTRA-INNINGS ROW'S TWO CHANCES — the
/// explicit identity/reading contract the host passes until Native's model
/// decodes them (`GameMarketOther` has no `pregame_mark`).
///
/// Identity is the served row's exact provider identity: `_market_id`,
/// `contributor_outcome_ids` (in served order) and `source`. Never a title,
/// a position or an index. Values are on the outcome's own axis, as served.
nonisolated struct BaseballExtraInningsAdmission10868: Equatable {
    let marketID: Int
    let outcomeIDs: [Int]
    let source: String
    /// The served `pregame_mark` — never `opening_over_probability`. It has no
    /// clock of its own and may itself be an opening fallback.
    let pregame: Double?
    /// The venue's quote recorded during play, and its own served
    /// `observed_at`, verbatim.
    let recorded: Double?
    let recordedAt: String?
}
