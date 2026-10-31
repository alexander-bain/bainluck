import Foundation

/// #10868 — THE COMBAT EVENT SCREEN'S PRODUCTION ADAPTER, PART THREE: THE FOUR
/// FIGHT STORIES — FINISH METHOD, KNOCKOUT CHANCES, FIGHTER ROUNDS, FIGHT LENGTH.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on an MMA or boxing event page each
/// story card prints, for every original side an owner has proved belongs to
/// it, exactly that original's own pre-match chance, in-fight reading and
/// contract result as the server's typed game matrix decides them — or that
/// slot's own words — and never borrows a neighbour's value.
///
/// MEMBERSHIP IS THE OWNER'S, AND NO PRODUCTION OWNER EXISTS TODAY. Which
/// served market is a finish method, a fighter's knockout predicate, a
/// fighter's round or a time window — and each window's span, the round
/// schedule and the final-bell meaning — is not on any production field: in
/// the retained UFC 332 body every `game_question_matrix` question serves
/// `subject: null` and `predicate: null` (and the round totals are
/// `typing.reason: "untyped_unit"`). Reading it from a market title is
/// forbidden (COMBAT-METHOD / -ROUND / -DURATION / -FIGHTER-KO binding maps).
/// So every card takes an explicit `Membership` the host must hand in, naming
/// matrix `question_key`s; with none (production today) every card is nil and
/// every original stays reachable in All props. The owed dependency is the
/// backend matrix contract (`10238.v1`, `app/utils/event_question_matrix.py`)
/// typing combat subjects/predicates, or another owner-proved membership.
///
/// Given membership, everything else is the server's matrix, read the way the
/// app already reads it:
///
///   - which questions  `game_question_matrix` under `NBAEventCards9483.matrixContract`
///                      at game scope (the MLB final reader's same gate); one
///                      question per proved `question_key`, else that row is not
///                      in this update.
///   - originals        every served option of the question, in served order:
///                      its served label ("Yes", "No"), its contributor outcome ids
///                      and market ids as the identity — never a title, ticker or
///                      position. Yes and No stay independent originals; nothing
///                      is complemented, normalized or summed.
///   - pre-match        before the start: the option's published quote
///                      (`QuestionMatrixPublished.quotedValue`) only while
///                      `NFLMilestoneCard9483.isRecent` finds its own clock recent.
///                      From the start on: the producer's pin
///                      (`NBALadderCard9483.pin` — the comparison baseline or the
///                      option's own `pregame_reading`, never a current or settled
///                      quote), else this slot's words.
///   - in-fight         during play only: the published quote, only when dated,
///                      observed at or after the listed start, recent, the option
///                      is not settled, and the fight is not suspended (the NBA
///                      card's rule: a suspended game has no current price beside
///                      its pin). Otherwise that slot's own words — withheld when a
///                      quote exists but is not admitted, unavailable when none.
///   - result           after the final only: the server's own grade
///                      (`QuestionMatrixResult.isWinner`, ruling 003), worded by
///                      `OutcomeVerdict`. Unknown is never a loss: no grade is
///                      "Result unconfirmed". The official finish never grades a
///                      contract here.
///   - words            `formatProbability`; part one's clock words; venues
///                      through `SourceLabels.label`.
///
/// The official bout context (`actual` / `finish`) and an observed round are
/// nil: no production field serves a method, round or finish time.
enum CombatStoryAdapter10868 {

    /// What the host already holds, passed in unchanged.
    struct Host {
        let now: Date
        let calendar: Calendar
        let locale: Locale

        init(now: Date = Date(), calendar: Calendar = .current, locale: Locale = .current) {
            self.now = now
            self.calendar = calendar
            self.locale = locale
        }

        /// Part one's host, for its clock words only.
        var words: CombatBoutPageAdapter10868.Host {
            CombatBoutPageAdapter10868.Host(probabilityObservedAt: nil, now: now, calendar: calendar, locale: locale)
        }
    }

    /// An owner's proof of which matrix questions each story holds. None exists
    /// in production today; see the file note.
    struct Membership: Equatable {
        /// One proved method or fighter-knockout row.
        struct Row: Equatable {
            let id: String
            /// "KO / TKO", or the fighter's full name on the knockout card.
            let label: String
            let questionKey: String
            /// The owner's overview side as a matrix option key; nil lists every side.
            var overviewOptionKey: String? = nil
        }

        /// One fighter's proved round slot. A nil question key is a slot the
        /// capture holds no market for.
        struct Slot: Equatable {
            let id: String
            /// "Round 1".
            let label: String
            let questionKey: String?
            var overviewOptionKey: String? = nil
        }

        struct Fighter: Equatable {
            let id: String
            let label: String
            let slots: [Slot]
        }

        /// One proved duration market with each side's proved window, by option key.
        struct Window: Equatable {
            let id: String
            /// "Go the distance".
            let label: String
            let questionKey: String
            let windows: [String: CombatDurationWindow10868]
            var overviewOptionKey: String? = nil
        }

        struct Schedule: Equatable {
            /// The bout's scheduled rounds, in order.
            let segments: [CombatDurationSegment10868]
            let markets: [Window]
        }

        var methods: [Row] = []
        var knockout: [Row] = []
        var rounds: [Fighter] = []
        var duration: Schedule? = nil
    }

    /// The host's held selection for one card.
    struct Selection: Equatable {
        var rowID: String? = nil
        var originalID: String? = nil

        init(rowID: String? = nil, originalID: String? = nil) {
            self.rowID = rowID
            self.originalID = originalID
        }
    }

    enum Words {
        static let methodsTitle = "How could the fight end?"
        static let knockoutTitle = "Who wins by knockout?"
        static let roundsTitle = "Which round for each fighter?"
        static let durationTitle = "How long could the fight last?"
        static let beforeCaption = "Pre-match chances · select a side for its timing"
        static let duringCaption = "Pre-match and in-fight chances"
        static let finalCaption = "Pre-match chances beside each contract’s result"
        static let originalMarkets = "Original markets"
        static let originalMarketsLower = "original markets"
        static let preMatchTitle = "Pre-match chance"
        static let inFightTitle = "In-fight chance"
        static let resultTitle = "Contract result"
        static let timingSuffix = "timing"
        static let noPreMatch = "Pre-match chance not recorded"
        static let inFightUnavailable = "In-fight chance unavailable"
        static let noRecentUpdate = AllMarketsCatalogView9483.noRecentPrice
        static let unconfirmed = "Result unconfirmed"
        static let recorded = "Recorded"
        static let lastBeforeStart = "Last recorded before start"
        static let noCapturedProp = "No captured prop"
        static let notInThisUpdate = "Unavailable in this update"
        static let windowUnavailable = "Time window unavailable"
        static let settledBy = "settled by"
    }

    static let knockoutCopy = CombatMethodCopy10868(
        chooseInstruction: "Choose a fighter or side to compare.",
        methodUnavailable: "Selected fighter unavailable in this update.",
        methodSelectedTag: "Fighter selected")

    // MARK: - The matrix

    /// The game matrix this build reads, or nil.
    static func matrix(_ markets: GameMarketsResponse?) -> EventQuestionMatrix? {
        guard let matrix = markets?.gameQuestionMatrix, matrix.contract == NBAEventCards9483.matrixContract,
              matrix.displayScope == nil || matrix.displayScope == QuestionMatrixScope.game.rawValue
        else { return nil }
        return matrix
    }

    /// Exactly one served question with this key, or nil.
    static func question(_ key: String, in matrix: EventQuestionMatrix) -> QuestionMatrixQuestion? {
        let found = matrix.questions.filter { $0.questionKey == key }
        return found.count == 1 ? found[0] : nil
    }

    // MARK: - One original

    struct Observation: Equatable {
        let probability: Double
        let text: String
        let time: String?
        let detail: String
    }

    enum Current: Equatable {
        case recorded(Observation)
        case unavailable(String)
        case withheld(String)
    }

    enum Result: Equatable {
        case won(String)
        case lost(String)
        case unconfirmed(String)
    }

    /// One served option, read for the phase.
    struct Original: Equatable {
        /// Contributor outcome ids joined with "+", else the served option key.
        let id: String
        /// Market ids joined with "+", else the question key.
        let marketID: String
        /// The served side label, verbatim.
        let label: String
        let before: Observation?
        let beforeMissing: String
        let current: Current
        let result: Result
        let timing: [String]
        /// The served option key, for the owner's overview side.
        let optionKey: String
        /// The option's venue in reader words (`SourceLabels`), or nil.
        let venue: String?
    }

    static func originals(_ question: QuestionMatrixQuestion, event: EventDetail,
                          phase: CombatEventPagePhase10868, host: Host) -> [Original] {
        question.options.map { Self.original($0, question: question, event: event, phase: phase, host: host) }
    }

    static func original(_ option: QuestionMatrixOption, question: QuestionMatrixQuestion, event: EventDetail,
                         phase: CombatEventPagePhase10868, host: Host) -> Original {
        let before = preMatch(option, event: event, phase: phase, host: host)
        let current: Current = phase == .during
            ? inFight(option, event: event, host: host) : .unavailable(Words.inFightUnavailable)
        let result: Result = phase == .final ? grade(option) : .unconfirmed(Words.unconfirmed)
        let id = ids(option.contributorOutcomeIds) ?? option.optionKey
        let market = ids(option.marketIds) ?? question.questionKey
        return Original(id: id, marketID: market, label: option.label,
                        before: before.observation, beforeMissing: before.missing,
                        current: current, result: result,
                        timing: timing(before: before, current: current, result: result, option: option, phase: phase),
                        optionKey: option.optionKey, venue: SourceLabels.label(for: option.published.source))
    }

    /// Before the start: the published quote on its own recent clock. From the
    /// start on: the producer's pin only.
    static func preMatch(_ option: QuestionMatrixOption, event: EventDetail, phase: CombatEventPagePhase10868,
                         host: Host) -> (observation: Observation?, missing: String) {
        let venue = SourceLabels.label(for: option.published.source)
        if phase == .before {
            guard let quoted = option.published.quotedValue else { return (nil, Words.noPreMatch) }
            guard NFLMilestoneCard9483.isRecent(option.published.observedAt, now: host.now),
                  let at = option.published.observedAt?.asDate
            else { return (nil, Words.noRecentUpdate) }
            let clock = CombatBoutPageAdapter10868.clockWords(at, host: host.words)
            return (Observation(probability: quoted, text: formatProbability(quoted), time: timeWords(at, host: host),
                                detail: joined(["\(Words.recorded) \(clock)", venue]) ?? clock), Words.noPreMatch)
        }
        guard let pin = NBALadderCard9483.pin(option), let at = pin.at.asDate else { return (nil, Words.noPreMatch) }
        let clock = CombatBoutPageAdapter10868.clockWords(at, host: host.words)
        return (Observation(probability: pin.probability, text: formatProbability(pin.probability),
                            time: timeWords(at, host: host),
                            detail: joined([Words.lastBeforeStart, clock, venue]) ?? clock), Words.noPreMatch)
    }

    /// During play: the published quote, only when the app would call it current.
    static func inFight(_ option: QuestionMatrixOption, event: EventDetail, host: Host) -> Current {
        // A settled option's 1 / 0 is a result, never a chance.
        if option.result?.isWinner != nil || option.published.valueState == "result" {
            return .unavailable(Words.inFightUnavailable)
        }
        guard let quoted = option.published.quotedValue else { return .unavailable(Words.inFightUnavailable) }
        guard let at = option.published.observedAt?.asDate else { return .withheld(Words.noRecentUpdate) }
        let start = event.commenceTime?.asDate
        if let start, at < start { return .unavailable(Words.inFightUnavailable) }
        if EventState.isSuspendedAndStarted(event.status, commenceTime: start, now: host.now) {
            return .withheld(Words.inFightUnavailable)
        }
        guard NFLMilestoneCard9483.isRecent(option.published.observedAt, now: host.now) else {
            return .withheld(Words.noRecentUpdate)
        }
        let clock = CombatBoutPageAdapter10868.clockWords(at, host: host.words)
        let venue = SourceLabels.label(for: option.published.source)
        return .recorded(Observation(probability: quoted, text: formatProbability(quoted), time: timeWords(at, host: host),
                                     detail: joined(["\(Words.recorded) \(clock)", venue]) ?? clock))
    }

    /// After the final: the server's typed grade only. Unknown is not loss.
    static func grade(_ option: QuestionMatrixOption) -> Result {
        switch option.result?.isWinner {
        case true?: return .won(OutcomeVerdict.won.label)
        case false?: return .lost(OutcomeVerdict.lost.label)
        case nil: return .unconfirmed(Words.unconfirmed)
        }
    }

    static func timing(before: (observation: Observation?, missing: String), current: Current, result: Result,
                       option: QuestionMatrixOption, phase: CombatEventPagePhase10868) -> [String] {
        var lines = ["\(Words.preMatchTitle): \(before.observation?.detail ?? before.missing)"]
        if phase == .during {
            switch current {
            case .recorded(let observation): lines.append("\(Words.inFightTitle): \(observation.detail)")
            case .unavailable(let words), .withheld(let words): lines.append("\(Words.inFightTitle): \(words)")
            }
        }
        if phase == .final {
            switch result {
            case .won(let words), .lost(let words):
                let venue = SourceLabels.label(for: option.published.source).map { "\(Words.settledBy) \($0)" }
                lines.append(joined(["\(Words.resultTitle): \(words)", venue]) ?? words)
            case .unconfirmed(let words):
                lines.append("\(Words.resultTitle): \(words)")
            }
        }
        return lines
    }

    // MARK: - Finish method and knockout chances

    static func methods(_ event: EventDetail, markets: GameMarketsResponse?, membership: Membership?,
                        host: Host, selection: Selection = Selection()) -> CombatMethodInput10868? {
        methodCard(event, markets: markets, rows: membership?.methods ?? [], title: Words.methodsTitle,
                   copy: .method, host: host, selection: selection)
    }

    static func knockout(_ event: EventDetail, markets: GameMarketsResponse?, membership: Membership?,
                         host: Host, selection: Selection = Selection()) -> CombatMethodInput10868? {
        methodCard(event, markets: markets, rows: membership?.knockout ?? [], title: Words.knockoutTitle,
                   copy: knockoutCopy, host: host, selection: selection)
    }

    static func methodCard(_ event: EventDetail, markets: GameMarketsResponse?, rows: [Membership.Row],
                           title: String, copy: CombatMethodCopy10868, host: Host,
                           selection: Selection) -> CombatMethodInput10868? {
        guard !rows.isEmpty, let served = Self.matrix(markets) else { return nil }
        let phase = CombatBoutPageAdapter10868.phase(event, now: host.now)
        var methods: [CombatMethod10868] = []
        var read: [Original] = []
        for row in rows {
            guard let asked = Self.question(row.questionKey, in: served) else { continue }
            let sides = Self.originals(asked, event: event, phase: phase, host: host)
            read += sides
            methods.append(CombatMethod10868(
                id: row.id, label: row.label, question: asked.label,
                originals: sides.map(methodOriginal),
                overviewOriginalID: overview(row.overviewOptionKey, in: sides)))
        }
        guard !methods.isEmpty else { return nil }
        let timing = selectedTiming(selection.originalID, in: read).map {
            CombatMethodTiming10868(originalID: $0.id, title: timingTitle($0), lines: $0.timing)
        }
        return CombatMethodInput10868(
            phase: CombatEventPageModel10868.methodPhase(phase), eventID: String(event.id),
            eyebrow: eyebrow(read), title: title, caption: caption(phase), methods: methods,
            selectedMethodID: selection.rowID, selectedOriginalID: selection.originalID,
            actual: nil, timing: timing, copy: copy)
    }

    static func methodOriginal(_ original: Original) -> CombatMethodOriginal10868 {
        CombatMethodOriginal10868(
            id: original.id, marketID: original.marketID, label: original.label,
            before: original.before.map {
                CombatMethodObservation10868(probability: $0.probability, text: $0.text, timeText: $0.time, detail: $0.detail)
            },
            beforeMissing: original.beforeMissing,
            current: methodCurrent(original.current),
            result: methodResult(original.result))
    }

    static func methodCurrent(_ current: Current) -> CombatMethodCurrent10868 {
        switch current {
        case .recorded(let o):
            return .recorded(CombatMethodObservation10868(probability: o.probability, text: o.text, timeText: o.time,
                                                          detail: o.detail), movement: nil)
        case .unavailable(let words): return .unavailable(words)
        case .withheld(let words): return .withheld(words)
        }
    }

    static func methodResult(_ result: Result) -> CombatMethodResult10868 {
        switch result {
        case .won(let words): return .won(words)
        case .lost(let words): return .lost(words)
        case .unconfirmed(let words): return .unconfirmed(words)
        }
    }

    // MARK: - Fighter rounds

    static func rounds(_ event: EventDetail, markets: GameMarketsResponse?, membership: Membership?,
                       host: Host, selection: Selection = Selection()) -> CombatRoundInput10868? {
        guard let fighters = membership?.rounds, !fighters.isEmpty, let served = Self.matrix(markets) else { return nil }
        let phase = CombatBoutPageAdapter10868.phase(event, now: host.now)
        var read: [Original] = []
        var groups: [CombatRoundGroup10868] = []
        for fighter in fighters {
            var slots: [CombatRoundSlot10868] = []
            for slot in fighter.slots {
                guard let key = slot.questionKey else {
                    slots.append(CombatRoundSlot10868(id: slot.id, label: slot.label, state: .noCapturedProp(Words.noCapturedProp)))
                    continue
                }
                guard let asked = Self.question(key, in: served) else {
                    slots.append(CombatRoundSlot10868(id: slot.id, label: slot.label, state: .unavailable(Words.notInThisUpdate)))
                    continue
                }
                let sides = Self.originals(asked, event: event, phase: phase, host: host)
                read += sides
                let market = CombatRoundMarket10868(id: asked.questionKey, question: asked.label,
                                                    originals: sides.map(roundOriginal),
                                                    overviewOriginalID: overview(slot.overviewOptionKey, in: sides))
                slots.append(CombatRoundSlot10868(id: slot.id, label: slot.label, state: .market(market)))
            }
            groups.append(CombatRoundGroup10868(id: fighter.id, label: fighter.label, slots: slots))
        }
        let timing = selectedTiming(selection.originalID, in: read).map {
            CombatRoundTiming10868(originalID: $0.id, title: timingTitle($0), lines: $0.timing)
        }
        return CombatRoundInput10868(
            phase: CombatEventPageModel10868.roundPhase(phase), eventID: String(event.id),
            eyebrow: eyebrow(read), title: Words.roundsTitle, caption: caption(phase),
            groups: groups, selectedSlotID: selection.rowID, selectedOriginalID: selection.originalID,
            finish: nil, timing: timing)
    }

    static func roundOriginal(_ original: Original) -> CombatRoundOriginal10868 {
        let current: CombatRoundCurrent10868
        switch original.current {
        case .recorded(let o):
            current = .recorded(CombatRoundObservation10868(probability: o.probability, text: o.text, detail: o.detail),
                                movement: nil)
        case .unavailable(let words): current = .unavailable(words)
        case .withheld(let words): current = .withheld(words)
        }
        let result: CombatRoundResult10868
        switch original.result {
        case .won(let words): result = .won(words)
        case .lost(let words): result = .lost(words)
        case .unconfirmed(let words): result = .unconfirmed(words)
        }
        return CombatRoundOriginal10868(
            id: original.id, marketID: original.marketID, label: original.label,
            before: original.before.map { CombatRoundObservation10868(probability: $0.probability, text: $0.text, detail: $0.detail) },
            beforeMissing: original.beforeMissing, current: current, result: result, resultDetail: nil)
    }

    // MARK: - Fight length

    static func duration(_ event: EventDetail, markets: GameMarketsResponse?, membership: Membership?,
                         host: Host, selection: Selection = Selection()) -> CombatDurationInput10868? {
        guard let schedule = membership?.duration, !schedule.markets.isEmpty, let served = Self.matrix(markets) else { return nil }
        let phase = CombatBoutPageAdapter10868.phase(event, now: host.now)
        var read: [Original] = []
        var cards: [CombatDurationMarket10868] = []
        for proved in schedule.markets {
            guard let asked = Self.question(proved.questionKey, in: served) else { continue }
            let sides = Self.originals(asked, event: event, phase: phase, host: host)
            read += sides
            cards.append(CombatDurationMarket10868(
                id: proved.id, label: proved.label, question: asked.label,
                originals: sides.map { durationOriginal($0, window: proved.windows[$0.optionKey]) },
                overviewOriginalID: overview(proved.overviewOptionKey, in: sides)))
        }
        guard !cards.isEmpty else { return nil }
        let timing = selectedTiming(selection.originalID, in: read).map {
            CombatDurationTiming10868(originalID: $0.id, title: timingTitle($0), lines: $0.timing)
        }
        return CombatDurationInput10868(
            phase: CombatEventPageModel10868.durationPhase(phase), eventID: String(event.id),
            eyebrow: eyebrow(read), title: Words.durationTitle, caption: caption(phase),
            segments: schedule.segments, markets: cards,
            selectedMarketID: selection.rowID, selectedOriginalID: selection.originalID,
            observed: nil, finish: nil, timing: timing)
    }

    static func durationOriginal(_ original: Original, window: CombatDurationWindow10868?) -> CombatDurationOriginal10868 {
        let current: CombatDurationCurrent10868
        switch original.current {
        case .recorded(let o):
            current = .recorded(CombatDurationObservation10868(probability: o.probability, text: o.text,
                                                              timeText: o.time, detail: o.detail), movement: nil)
        case .unavailable(let words): current = .unavailable(words)
        case .withheld(let words): current = .withheld(words)
        }
        let result: CombatDurationResult10868
        switch original.result {
        case .won(let words): result = .won(words)
        case .lost(let words): result = .lost(words)
        case .unconfirmed(let words): result = .unconfirmed(words)
        }
        return CombatDurationOriginal10868(
            id: original.id, marketID: original.marketID, label: original.label,
            window: window, windowMissing: Words.windowUnavailable,
            before: original.before.map {
                CombatDurationObservation10868(probability: $0.probability, text: $0.text, timeText: $0.time, detail: $0.detail)
            },
            beforeMissing: original.beforeMissing, current: current, result: result, resultDetail: nil)
    }

    // MARK: - Shared words

    /// The owner's overview option, as its original id, when it names exactly one served side.
    static func overview(_ optionKey: String?, in originals: [Original]) -> String? {
        guard let optionKey else { return nil }
        let found = originals.filter { $0.optionKey == optionKey }
        return found.count == 1 ? found[0].id : nil
    }

    /// The held original's timing, only when its id names exactly one read original.
    static func selectedTiming(_ originalID: String?, in read: [Original]) -> Original? {
        guard let originalID else { return nil }
        let found = read.filter { $0.id == originalID }
        return found.count == 1 ? found[0] : nil
    }

    static func timingTitle(_ original: Original) -> String {
        "\(original.label) · \(Words.timingSuffix)"
    }

    /// "Polymarket · original markets": the venues the card's originals name,
    /// through `SourceLabels`, in order and once each; an unnamed venue is left
    /// unnamed.
    static func eyebrow(_ read: [Original]) -> String {
        var venues: [String] = []
        for original in read {
            guard let venue = original.venue, !venues.contains(venue) else { continue }
            venues.append(venue)
        }
        return joined(venues + [Words.originalMarketsLower]) ?? Words.originalMarkets
    }

    static func caption(_ phase: CombatEventPagePhase10868) -> String {
        switch phase {
        case .before: Words.beforeCaption
        case .during: Words.duringCaption
        case .final: Words.finalCaption
        }
    }

    static func timeWords(_ date: Date, host: Host) -> String {
        date.formatted(Date.FormatStyle(locale: host.locale, calendar: host.calendar, timeZone: host.calendar.timeZone)
            .hour().minute())
    }

    private static func ids(_ values: [Int]?) -> String? {
        guard let values, !values.isEmpty else { return nil }
        return values.map(String.init).joined(separator: "+")
    }

    private static func joined(_ parts: [String?]) -> String? {
        let kept = parts.compactMap { $0 }.filter { !$0.isEmpty }
        return kept.isEmpty ? nil : kept.joined(separator: " · ")
    }
}
