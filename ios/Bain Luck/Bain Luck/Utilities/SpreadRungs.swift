import Foundation

// MARK: - What a margin map may draw

/// The rungs a margin map is entitled to draw, which side each is on, and the
/// unit the map is therefore drawn in.
///
/// #3552 / #3533 / #3568. This used to be four lines of `private func
/// parseSprOutcome` inside `MarketMapView`, which meant the only way to assert
/// any of it was to rasterise a SwiftUI view and read pixels — the same reason
/// `MarketMapRail` and `SportVocab.projectedMarginNote` were pulled out before
/// it. Everything here is a fact about strings and numbers.
///
/// **What a reader saw.** Nothing. Every US Open match page had no margin map
/// at all — not an empty one, not a wrong one, simply absent — while the books'
/// game spread sat in the payload we had already fetched. The old parser looked
/// for a team's name inside the OUTCOME name, and on tennis the venue names
/// every spread outcome `Yes` or `No` and puts the players and the line in the
/// MARKET name:
///
/// ```
/// market_name  Game Spread: Swiatek (-5.5) vs Zheng (+5.5)   outcome_name  Yes / No
/// market_name  Set Handicap: Swiatek (-1.5) vs Zheng (+1.5)  outcome_name  Yes / No
/// ```
///
/// Measured on production 2026-09-06 across the visible windows of five
/// leagues: **100% of tennis spread markets are `Yes`/`No`** (29 markets over
/// 12 US Open events, zero named), while NFL is 100% named. `soccer_other`
/// (334 rows) and `americanfootball_other` (126) are `Yes`/`No` too, so this
/// was never a tennis special case.
enum SpreadRungs {

    // MARK: - Types

    /// One rung of a margin ladder.
    struct Rung: Equatable {
        /// Signed by side: positive is HOME by that much, negative is AWAY by
        /// that much. The convention predates this file — `MarketMapView`'s
        /// ladder and density both read it — and is left exactly as it was.
        let margin: Double
        let probability: Double
        let isHome: Bool
        /// The unit this rung's line is quoted in, as its own market name
        /// declared it, or nil where it declared none. See
        /// ``SportVocab/declaredMarginUnit(inMarketName:)``.
        let quotedUnit: String?
    }

    /// One served leg. A plain value rather than `GameMarketOutcome` so the
    /// rule can be exercised without a decoder.
    struct Leg: Equatable {
        let marketName: String
        let outcomeName: String
        let threshold: Double?
        let probability: Double?

        init(marketName: String, outcomeName: String, threshold: Double? = nil, probability: Double? = nil) {
            self.marketName = marketName
            self.outcomeName = outcomeName
            self.threshold = threshold
            self.probability = probability
        }
    }

    /// One margin map's worth of rungs, and the unit they are all quoted in.
    struct Map: Equatable {
        /// The unit every rung on this map is quoted in.
        ///
        /// **With no rungs this is the SPORT's unit, not the empty string.** A
        /// map can still carry a projection marker and a scoreboard tile with
        /// nothing parsed — that is most of what `marginMapIsEmptyChrome`
        /// weighs — and those are quoted in the sport's own unit. Returning ""
        /// here suppressed the margin map on every NFL event whose ladder
        /// failed to parse but whose spread was known, which is a regression
        /// dressed as a fix.
        let unit: String
        let rungs: [Rung]
    }

    // MARK: - The two-way coherence floor (#3555)

    /// A two-way market's legs are complementary by construction: `No` is
    /// exactly "not `Yes`". So the pair must sum to 1, plus whatever margin the
    /// book charges — and **a pair summing to less than 1 is an arbitrage**,
    /// free money for backing both sides, which no real book has ever offered.
    /// A pair under this floor is therefore our data and not the market's, and
    /// a rung built from it would be a picture of our own bug presented as the
    /// books' opinion.
    ///
    /// This is not a fix for #3555 and does not pretend to be one; it is the
    /// refusal that has to exist before the map is allowed to draw at all.
    /// Measured, production, 2026-09-06, every two-leg `Yes`/`No` spread market
    /// on the 12 visible US Open events — **29 markets, 11 coherent, 18 not**,
    /// and the failures are not near-misses:
    ///
    /// ```
    /// Set Handicap: Alcaraz (-1.5) vs Paul (+1.5)     1.000  ✓
    /// Set Handicap: Alcaraz (-2.5) vs Paul (+2.5)     0.710  ✗
    /// Game Spread:  Alcaraz (-6.5) vs Paul (+6.5)     0.710  ✗
    /// Set Handicap: Medvedev (-2.5) vs Tiafoe (+2.5)  1.010  ✓
    /// Game Spread:  Medvedev (-1.5) vs Tiafoe (+1.5)  0.460  ✗
    /// Set Handicap: Medvedev (-1.5) vs Tiafoe (+1.5)  0.460  ✗
    /// ```
    ///
    /// The shape is the same on all eleven events: **exactly one market per
    /// event carries real prices, and every other leg on that event repeats one
    /// single number** — 0.355 on Alcaraz, 0.23 on Medvedev, 0.415 on Swiatek —
    /// which is the complement of the good market's favourite leg. Filed on
    /// #3555; nothing here diagnoses it, and nothing here is a licence to stop
    /// filing it.
    static let twoWaySumFloor = 0.98
    /// The other end. A two-way book runs an overround of a few percent; past
    /// this the pair is not a priced market either. The one live US Open match
    /// at capture sat at 1.100 and is admitted.
    static let twoWaySumCeiling = 1.15

    // MARK: - Entry point

    /// Every rung one margin map may draw, from the legs served for it.
    ///
    /// - Parameters:
    ///   - legs: the spread legs already filtered to this map's scope (full
    ///     game, or one half).
    ///   - home/away: the two competitors, as the event names them.
    ///   - sportUnit: `SportVocab.unit` — what this sport's markets quote when
    ///     a market does not say.
    static func map(from legs: [Leg], home: String, away: String, sportUnit: String) -> Map {
        var rungs: [Rung] = []
        for (name, group) in grouped(legs) {
            rungs += parse(market: name, legs: group, home: home, away: away)
        }
        let empty = Map(unit: sportUnit, rungs: [])
        guard let unit = mapUnit(of: rungs, sportUnit: sportUnit) else { return empty }
        let kept = rungs.filter { ($0.quotedUnit ?? sportUnit) == unit }
        return kept.isEmpty ? empty : Map(unit: unit, rungs: kept)
    }

    /// The unit a single map is drawn in, or nil where no single map is honest.
    ///
    /// Mirrors ``SportVocab/totalsUnit(quotedBy:)`` in shape and differs in one
    /// way that matters: it PREFERS the sport's own unit when a market quotes
    /// it, because rungs quoted in something else are then dropped rather than
    /// mixed onto its rail. A totals map's rungs are all points on one number
    /// line; a margin map's `±1.5 sets` beside a `±5.5 games` is #3533 itself.
    static func mapUnit(of rungs: [Rung], sportUnit: String) -> String? {
        guard !rungs.isEmpty else { return nil }
        let declared = Set(rungs.compactMap(\.quotedUnit))
        if declared.isEmpty { return sportUnit }
        if declared.contains(sportUnit) { return sportUnit }
        if declared.count == 1 { return declared.first }
        // Two units, neither the sport's. There is no rail on which both are
        // true and no reason to prefer either, so we draw neither.
        return nil
    }

    // MARK: - One market

    private static func grouped(_ legs: [Leg]) -> [(String, [Leg])] {
        var order: [String] = []
        var byName: [String: [Leg]] = [:]
        for leg in legs {
            if byName[leg.marketName] == nil { order.append(leg.marketName) }
            byName[leg.marketName, default: []].append(leg)
        }
        return order.map { ($0, byName[$0]!) }
    }

    private static func parse(market name: String, legs: [Leg], home: String, away: String) -> [Rung] {
        let unit = SportVocab.declaredMarginUnit(inMarketName: name)
        if let pair = twoWay(legs), let handicap = Handicap.read(marketName: name) {
            return fromHandicap(pair, handicap, home: home, away: away, unit: unit)
        }
        return legs.compactMap { fromNamedOutcome($0, home: home, away: away, unit: unit) }
    }

    /// The `Yes`/`No` legs of a two-way market, or nil where this is not one.
    private static func twoWay(_ legs: [Leg]) -> (yes: Double, no: Double)? {
        guard legs.count == 2 else { return nil }
        var yes: Double?
        var no: Double?
        for leg in legs {
            switch leg.outcomeName.trimmingCharacters(in: .whitespaces).lowercased() {
            case "yes": yes = leg.probability
            case "no": no = leg.probability
            default: return nil
            }
        }
        guard let y = yes, let n = no else { return nil }
        let sum = y + n
        guard sum >= twoWaySumFloor, sum <= twoWaySumCeiling else { return nil }
        return (y, n)
    }

    // MARK: - `<Kind>: A (-L) vs B (+L)`

    /// The two participants and the line a handicap market's TITLE states.
    struct Handicap: Equatable {
        /// The side the market is written from — the one carrying the negative
        /// line, which is the side `Yes` is asking about.
        let favourite: String
        let underdog: String
        /// The line, always positive. Both participants carry it; the title
        /// prints it signed.
        let line: Double

        /// `"Game Spread: Swiatek (-5.5) vs Zheng (+5.5)"` → Swiatek, Zheng, 5.5.
        ///
        /// Deliberately strict. Anything that is not exactly two participants
        /// with equal and opposite lines, favourite first, returns nil and the
        /// market draws nothing — this parser has only ever been read against
        /// the one shape the venue serves, and a looser reading of a title is
        /// how a rung ends up on the wrong player.
        static func read(marketName: String) -> Handicap? {
            let pattern = #"([^:()]+?)\s*\(\s*([+-]?\d+(?:\.\d+)?)\s*\)"#
            guard let re = try? NSRegularExpression(pattern: pattern) else { return nil }
            let range = NSRange(marketName.startIndex..., in: marketName)
            let found = re.matches(in: marketName, range: range).compactMap { m -> (String, Double)? in
                guard let nameRange = Range(m.range(at: 1), in: marketName),
                      let lineRange = Range(m.range(at: 2), in: marketName),
                      let line = Double(marketName[lineRange])
                else { return nil }
                let who = participant(String(marketName[nameRange]))
                return who.isEmpty ? nil : (who, line)
            }
            guard found.count == 2 else { return nil }
            let (first, firstLine) = found[0]
            let (second, secondLine) = found[1]
            guard firstLine < 0, secondLine > 0, abs(firstLine) == secondLine else { return nil }
            return Handicap(favourite: first, underdog: second, line: secondLine)
        }

        /// One participant, with the separator the title puts before it.
        ///
        /// The capture runs back to the previous `)`, so the second
        /// participant arrives as `"vs Zheng"`. `SpreadRungs.words` would drop
        /// `"vs"` anyway on its three-character floor — but a value that says
        /// the player is called "vs Zheng" is wrong even when nothing downstream
        /// reads it wrongly, and the next thing to use `Handicap` will not know
        /// that.
        private static func participant(_ raw: String) -> String {
            var text = raw.trimmingCharacters(in: CharacterSet(charactersIn: " \t-–—"))
            for separator in ["vs.", "vs", "v.", "@"] where text.lowercased().hasPrefix(separator + " ") {
                text = String(text.dropFirst(separator.count + 1))
                break
            }
            return text.trimmingCharacters(in: .whitespaces)
        }
    }

    /// The ONE rung a two-way handicap market is entitled to draw: the
    /// favourite covering its own line, at the `Yes` price.
    ///
    /// **#3743 — this used to return two, and the second one was never true.**
    ///
    /// A `Rung` makes exactly one claim: *this side by more than
    /// `abs(margin)`, at this probability.* The `Yes` leg makes it —
    /// `P(Swiatek covers -1.5 sets)` **is** `P(Swiatek wins by 2 sets)`. The
    /// `No` leg does not: it is `P(Zheng wins, OR loses 1-2)`, which is not
    /// "Zheng by more than 1.5" and is not any rung's claim. Drawn as one
    /// anyway, it put a bar on Zheng's side of a rail that no market had priced.
    ///
    /// And it was never a second *reading*, either. A two-way market's legs are
    /// complements by construction — that is the entire content of
    /// ``twoWaySumFloor``/``twoWaySumCeiling`` above, which admit a pair only
    /// when it sums to about 1. `No` is `1 - Yes` wearing the other player's
    /// name, so the map was drawing one fact twice: once truthfully, and once
    /// as its own opposite.
    ///
    /// What a reader saw. Event 15305580, `artifacts-native-041/AFTER-ipad-swiatek-15305580-s600.png`:
    ///
    /// ```
    /// Zheng   +1.5   42%    <- P(No)  = wins, or loses 1-2. NOT a cover.
    /// Swiatek +1.5   59%    <- P(Yes) = wins by 2.          A cover.
    /// ```
    ///
    /// Two rows in one ladder, formatted identically, answering questions of
    /// different shape — and summing to 101%, which is the tell, because
    /// complements sum to one and parallel rungs do not. Measured on production
    /// 2026-09-06: **8 of the 28 event pages carrying a margin map drew one of
    /// these, every one of them a US Open match, and all 8 summed to exactly
    /// 1.000** (`artifacts-native-048/handicap-census.json`).
    ///
    /// The underdog is still resolved, and still has to be a real and distinct
    /// side, even though it no longer gets a rung. That guard is what proves
    /// the title names THIS event's two competitors and not some other match's;
    /// dropping it along with its rung would let
    /// `Set Handicap: Gauff (-1.5) vs SomeoneElse (+1.5)` draw a Gauff rung on
    /// a page Gauff is not playing on.
    private static func fromHandicap(
        _ pair: (yes: Double, no: Double),
        _ handicap: Handicap,
        home: String, away: String, unit: String?
    ) -> [Rung] {
        guard let favouriteSide = side(of: handicap.favourite, home: home, away: away),
              let underdogSide = side(of: handicap.underdog, home: home, away: away),
              favouriteSide != underdogSide
        else { return [] }
        return [
            Rung(margin: favouriteSide == .home ? handicap.line : -handicap.line,
                 probability: pair.yes, isHome: favouriteSide == .home, quotedUnit: unit),
        ]
    }

    // MARK: - `Seattle wins by 1 to 6 points` is not a rung (#3788)

    /// True where an outcome names a **band of margins** rather than a cover
    /// line — `"Seattle wins by 1 to 6 points"`, not `"Seattle wins by over
    /// 1.5 points"`.
    ///
    /// **#3788, and it is #3743's rule applied to the second shape that breaks
    /// it.** A ``Rung`` makes exactly one claim: *this side by more than
    /// `abs(margin)`, at this probability.* A band outcome does not make it.
    /// `P(Seattle by 1 to 6)` is not `P(Seattle by more than anything)` — it is
    /// bounded at BOTH ends, and the whole point of the market is the upper
    /// bound that a cover line does not have.
    ///
    /// Drawn as a rung anyway, it takes the band's LOWER edge as a line and the
    /// band's mass as a cover price, and prints both on the ladder.
    ///
    /// What a reader saw, production 2026-09-07, every NFL card on opening
    /// Sunday. Kalshi serves each game a `…: Spread` ladder **and** a separate
    /// `…: Winning Margin` band market, the backend puts both under `spreads`,
    /// and `isFullGameSpread` excludes halves and nothing else, so they land on
    /// one rail. Event 14780138, New England @ Seattle — the top of the ladder:
    ///
    /// ```
    /// SEA +1     18%     <- "Seattle wins by 1 to 6 points".  A BAND.
    /// SEA +1.5   14%     <- "Seattle wins by over 1.5 points". A cover.
    /// ```
    ///
    /// Two rows, formatted identically, a half point apart, answering questions
    /// of different shape — and the fabricated one is on top, because the
    /// ladder sorts by `abs(margin)` and the band's lower edge (`1`) is the
    /// smallest number on the card. `"+1"` is not a line any venue quoted.
    ///
    /// Measured on the 22 production event pages that draw a margin map
    /// (`census049-margin.json`, re-fetched 2026-09-07): **8 carry a band
    /// market, all 8 of them NFL, 4 band rows each — and on all 8 a band row is
    /// the FIRST row of both sides of the ladder.** 48 of 311 full-game spread
    /// legs across the population. Nothing outside NFL serves one today, which
    /// is why this survived #3552, #3568 and #3743: none of those censuses had
    /// an NFL band market in front of them.
    ///
    /// **What this deliberately does NOT refuse.** `"wins by 15 or more
    /// points"` is bounded at one end only, which IS a cover claim
    /// (`P(M >= 15)`), so it stays a rung. It is half a point off the line it
    /// really names — `P(M >= 15)` is `P(M > 14.5)`, not `P(M > 15)` — and that
    /// is pre-existing, out of scope here, and worth nothing on today's data
    /// because every card serving one also serves the `over 14.5` cover at the
    /// same price.
    static func namesARange(_ outcomeName: String) -> Bool {
        // `by <n> to <n>`, `by <n>-<n>`, `by between <n> and <n>`. Anchored on
        // `by` and on a digit immediately after it, so a signed line (`by
        // -3.5`) and a cover line (`by over 1.5`) cannot reach the range test:
        // neither has a number in the first slot.
        let pattern = #"\bby\s+(?:between\s+)?\d+(?:\.\d+)?\s*(?:to|and|[-–—])\s*\d+"#
        guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return false }
        let range = NSRange(outcomeName.startIndex..., in: outcomeName)
        return re.firstMatch(in: outcomeName, range: range) != nil
    }

    private static func fromNamedOutcome(_ leg: Leg, home: String, away: String, unit: String?) -> Rung? {
        guard !namesARange(leg.outcomeName) else { return nil }
        guard let side = side(of: leg.outcomeName, home: home, away: away) else { return nil }
        guard let threshold = leg.threshold ?? lastNumber(in: leg.outcomeName) else { return nil }
        return Rung(
            margin: side == .home ? threshold : -threshold,
            probability: leg.probability ?? 0.5,
            isHome: side == .home,
            quotedUnit: unit
        )
    }

    // MARK: - Which side a piece of text names (#3568)

    enum Side { case home, away }

    /// The side a string names, or nil where it names neither or both.
    ///
    /// #3568, two defects in one line. The old test was
    /// `outcomeName.lowercased().contains(teamWord)` — a SUBSTRING test, so
    /// `"san"` matched inside `"kansas"` and the away side of a
    /// 49ers–Chiefs game claimed every Chiefs rung; and when both sides
    /// matched, `isHome ? t : -t` silently resolved the tie to HOME, so on a
    /// game whose teams share a word every rung of both teams was drawn on the
    /// home side. Neither was visible to a reader: a rung on the wrong player's
    /// side is not a gap, it is an assertion.
    ///
    /// Two rules fix the class rather than the eight events it was measured on:
    ///
    /// 1. **Whole words, not substrings.** Both sides are tokenised, so
    ///    `"kansas"` and `"san"` are simply different tokens.
    /// 2. **Only DISTINGUISHING words identify a side.** A word both names
    ///    carry cannot tell them apart, so it is dropped from both. That is
    ///    what makes `Clemson Tigers @ LSU Tigers` readable — `tigers` is
    ///    discarded, `clemson` and `lsu` still work — and what makes
    ///    `Washington State @ Washington` honestly unreadable when the outcome
    ///    says only `"Washington"`, which is the truth.
    ///
    /// Measured population that reaches this, production 2026-09-06: 8
    /// collisions in the visible windows of 11 leagues, on `state`, `city`,
    /// `new`, `united` and `tigers` — structural in college football and
    /// soccer, not coincidental.
    static func side(of text: String, home: String, away: String) -> Side? {
        let homeWords = words(home)
        let awayWords = words(away)
        let homeOnly = homeWords.subtracting(awayWords)
        let awayOnly = awayWords.subtracting(homeWords)
        let spoken = words(text)
        let isHome = !homeOnly.isDisjoint(with: spoken)
        let isAway = !awayOnly.isDisjoint(with: spoken)
        guard isHome != isAway else { return nil }
        return isHome ? .home : .away
    }

    /// The identifying words of a name: whole tokens of three characters or
    /// more, accent-folded so the venue's `"Jovic"` reaches the event's
    /// `"Iva Jović"`.
    ///
    /// The three-character floor is inherited unchanged from the code this
    /// replaced. It is what keeps `"vs"`, `"de"` and `"FC"` out; it also means
    /// a genuinely two-letter distinguishing name cannot be read, which is a
    /// silence rather than a falsehood.
    static func words(_ name: String) -> Set<String> {
        let folded = name.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US"))
        return Set(
            folded.split(whereSeparator: { !$0.isLetter && !$0.isNumber })
                .map(String.init)
                .filter { $0.count >= 3 }
        )
    }

    private static func lastNumber(in text: String) -> Double? {
        guard let re = try? NSRegularExpression(pattern: #"(\d+\.?\d*)"#) else { return nil }
        let range = NSRange(text.startIndex..., in: text)
        guard let last = re.matches(in: text, range: range).last,
              let r = Range(last.range(at: 1), in: text)
        else { return nil }
        return Double(text[r])
    }
}
