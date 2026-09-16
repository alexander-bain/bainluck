import SwiftUI

struct SpecialEventMarketsView: View {
    let markets: [GameMarketOther]
    let eventStatus: String?

    /// Internal, not `private`, for the reason given on `isWinProbabilityMarket`
    /// below and pressed by CERT-2620: a guard that claims a market is REACHABLE
    /// has to name the card it is reaching, and a test cannot name a card whose
    /// type it cannot see.
    struct MarketCategory: Identifiable {
        let id: String
        let title: String
        let subtitle: String
        var items: [MarketItem]
    }

    struct MarketItem: Identifiable {
        let id: String
        let name: String
        var outcomes: [OutcomeEntry]
    }

    struct OutcomeEntry: Identifiable {
        var id: String { label }
        let label: String
        var prob: Double
        var sourceCount: Int
        /// When `prob` was last observed (#4970). Absolute ISO or nil.
        ///
        /// The FIRST wire row's stamp, deliberately, because `prob` is also the
        /// first row's — two sources quoting one label are merged into one
        /// entry here and only the first one's number survives, so taking a
        /// different row's stamp would date a number that is not on screen.
        var observedAt: String?
    }

    private static let categoryPatterns: [(pattern: String, category: String, subtitle: String)] = [
        ("first.*(?:score|td|touchdown|goal|basket)", "Game Props", "scoring & flow"),
        ("(?:halftime|half\\s*time|leader\\s*at)", "Game Props", "scoring & flow"),
        ("(?:overtime|OT\\b|extra\\s*time)", "Game Props", "scoring & flow"),
        ("(?:coin\\s*toss|gatorade|anthem|color)", "Novelty Props", "fun markets"),
        ("(?:mvp|most\\s*valuable)", "MVP", "game MVP probability"),
        ("(?:double\\s*double|triple\\s*double)", "Player Performance", "statistical milestones"),
        ("both\\s*teams?.*score", "Game Props", "scoring & flow"),
    ]

    private static func categorize(_ name: String) -> (category: String, subtitle: String) {
        let lower = name.lowercased()
        for (pattern, category, subtitle) in categoryPatterns {
            if lower.range(of: pattern, options: .regularExpression) != nil {
                return (category, subtitle)
            }
        }
        return ("Other Markets", "additional markets")
    }

    /// Internal for the same reason as `isWinProbabilityMarket` below (#5133):
    /// `categories` applies BOTH filters, and a test that cannot tell which of
    /// the two declined a row is a test that can be satisfied by the wrong one.
    static func isRedundantWithMarketMaps(_ m: GameMarketOther) -> Bool {
        let lower = m.marketName.lowercased()
        let outLower = m.outcomeName.lowercased()
        if lower.contains("spread") || lower.contains("handicap") { return true }
        if lower.contains("total") && (outLower.contains("over") || outLower.contains("under")) { return true }
        if lower.contains("moneyline") || lower.contains("winner") || lower.contains("match result") { return true }
        return false
    }

    /// A SCORING RACE — "…: Race to 14 Points" — which side reaches a score
    /// first.
    ///
    /// The web twin is `isScoringRaceMarket` in `frontend/lib/otherMarketGroups.ts`
    /// and the server's is `_SCORING_RACE_RE` in `backend/app/routes/events.py`;
    /// all three are the same pattern deliberately, because all three answer the
    /// same question. Narrower than "race to" on purpose: the SCORE UNIT is
    /// required, so a player race ("Race to 5 catches") — a shape nobody has
    /// measured — is left out rather than swept in by grammar.
    static func isScoringRaceMarket(_ name: String) -> Bool {
        name.range(
            of: #"\brace to\s+\d+(?:\.\d+)?\s+points?\b"#,
            options: [.regularExpression, .caseInsensitive]
        ) != nil
    }

    /// Internal, not `private`, since #5133: a SwiftUI view's computed
    /// properties are invisible to XCTest, so the only way this filter's
    /// behaviour can be asserted in Swift at all is to let a test call it. Its
    /// wiring into `categories` is pinned by the source scan in
    /// `frontend/__tests__/ios/aScoringRaceStaysVisible5133.test.ts`.
    static func isWinProbabilityMarket(_ markets: [GameMarketOther]) -> Set<String> {
        var winProbMarkets: Set<String> = []
        let byMarket = Dictionary(grouping: markets) { $0.marketName }
        for (name, outcomes) in byMarket {
            // #5133 — a scoring race is a two-sided TEAM market that is not the
            // moneyline: the hero answers "who wins", the race answers "who
            // gets there first", and a game can be won by the side that lost
            // the race. From inside this heuristic the two shapes are identical,
            // so the race has to be named.
            //
            // MEASURED (`GET /api/events/14780145/game-markets`, 2026-09-11):
            // Kalshi ships six races per NFL game; five serve THREE rows and
            // survive this rule by accident, while `Race to 7 Points` serves
            // TWO — 0.56 / 0.44 — because its third row ("Neither team reaches
            // 7 points", 0.010) is dropped upstream. One race in six vanishing
            // while its siblings render is not a rule a reader can learn.
            if Self.isScoringRaceMarket(name) { continue }

            if outcomes.count == 2 {
                let probs = outcomes.compactMap(\.probability)
                if probs.count == 2, abs(probs[0] + probs[1] - 1.0) < 0.1 {
                    winProbMarkets.insert(name)
                }
            }
        }
        return winProbMarkets
    }

    private var isGameFinished: Bool {
        SettledQuote.isSettled(eventStatus)
    }

    /// Only a LIVE event's card can go quiet — web's
    /// `const live = !settled && !isPregameStatus(eventStatus)`.
    ///
    /// A scheduled game's game markets are polled on a far slower cadence than
    /// the two-minute live one, so applying the live bound before kickoff would
    /// mark every row on every upcoming page and the mark would stop meaning
    /// anything (`SourceAge`: "an age has value exactly when it is surprising").
    /// A settled card already says its prices are old, once, in its own header.
    private var isLiveEvent: Bool {
        !isGameFinished && !SettledQuote.isPregame(eventStatus)
    }

    /// Internal since CERT-2620, same reason as the types above: the overflow
    /// guard has to build the REAL category list from the real wire rows and
    /// find the real card, not re-implement the grouping and grade its own copy.
    var categories: [MarketCategory] {
        let winProbNames = Self.isWinProbabilityMarket(markets)
        let filtered = markets.filter { !Self.isRedundantWithMarketMaps($0) && !winProbNames.contains($0.marketName) }
        // #2086. What used to sit here was a price-band DELETION on a finished
        // game — `p > 0.01 && p < 0.99`, under a comment claiming it hid
        // "100%/0%" — and it was wrong three ways at once.
        //
        //   1. It removed exactly the rows a human would notice were wrong (the
        //      99% the issue was filed on) and KEPT exactly the rows a human
        //      would believe. Measured 2026-08-21 over 40 settled events: 117
        //      of 146 `other` rows survived that filter and rendered as live
        //      bars, 53 of them in the 0.40–0.60 coin-flip band.
        //   2. It DELETED rather than declared, so the reader was given a blank
        //      where an honest statement belonged (#2019).
        //   3. Its `guard let … else { return false }` silently dropped
        //      null-priced rows on a finished game while keeping them on a live
        //      one — a filter for prices quietly deciding a row's existence.
        //
        // Nothing is dropped now. A settled row keeps its place and says what
        // its number is, in `outcomeRow` below.
        guard !filtered.isEmpty else { return [] }

        var catMap: [String: MarketCategory] = [:]
        let categoryOrder = ["MVP", "Game Props", "Player Performance", "Novelty Props", "Other Markets"]

        for m in filtered {
            let name = m.marketName
            let (cat, sub) = Self.categorize(name)

            if catMap[cat] == nil {
                catMap[cat] = MarketCategory(id: cat, title: cat, subtitle: sub, items: [])
            }

            let itemIdx = catMap[cat]!.items.firstIndex(where: { $0.name == name })
            if let idx = itemIdx {
                let label = m.outcomeName
                if let oIdx = catMap[cat]!.items[idx].outcomes.firstIndex(where: { $0.label == label }) {
                    catMap[cat]!.items[idx].outcomes[oIdx].sourceCount += 1
                } else {
                    catMap[cat]!.items[idx].outcomes.append(
                        OutcomeEntry(
                            label: label,
                            prob: m.probability ?? 0,
                            sourceCount: 1,
                            observedAt: m.observedAt
                        )
                    )
                }
            } else {
                catMap[cat]!.items.append(
                    MarketItem(id: "\(cat)-\(name)", name: name, outcomes: [
                        OutcomeEntry(
                            label: m.outcomeName,
                            prob: m.probability ?? 0,
                            sourceCount: 1,
                            observedAt: m.observedAt
                        )
                    ])
                )
            }
        }

        return catMap.values
            .filter { !$0.items.isEmpty }
            .sorted { (categoryOrder.firstIndex(of: $0.title) ?? 99) < (categoryOrder.firstIndex(of: $1.title) ?? 99) }
    }

    /// WHERE THE AGE IS SAID ON ONE CARD — card header, every stale row, or
    /// nowhere.
    ///
    /// #4970's native half, and a direct port of `PropMiniCard`'s rule in
    /// `frontend/components/SpecialEventMarkets.tsx`. Read that component for
    /// the measurement behind the shape; the short version is that a per-row
    /// mark on a card whose rows are all equally stale is eight identical
    /// `41m ago`s stacked down one card, which is the grey-text noise notice 34
    /// bans — while ONE mark over a card holding a two-minute-old row and a
    /// 115-minute-old one is false about one of them.
    ///
    /// 🔴 THE MIXED CASE IS NOT HYPOTHETICAL ON THIS PLATFORM, and it is the
    /// defect that sent me looking. Production, 2026-09-16 16:5xZ, three live
    /// soccer events read in one pass:
    ///
    ///   15310931 "Second Half Result"  0.9955 / 0.525 / 0.0045 = **153%**,
    ///                                  ages 2 / 43 / 25 minutes
    ///   15313067 "Halftime Result"     = **182%**, ages 2 / 115 / 115
    ///   15307696 "First Team to Score" = **135%**, ages 49 / 284 / 284
    ///
    /// In every one of them the arithmetic excess IS the leg nothing refreshed,
    /// and the phone drew it as a peer of the fresh ones. This does not
    /// renormalise those numbers — narrowing a fresh 99.55% to make room for a
    /// 43-minute-old 52.5% would delete the true one to flatter the stale one,
    /// and display normalisation is `normalize_display_probs`' job upstream
    /// (gotcha #23, #3949). It says which number stopped being current.
    ///
    /// `now` is an argument (gotcha #44).
    struct AgeDecision: Equatable {
        /// The stamp the card header speaks with, or nil when it must not speak.
        let cardStamp: String?
        /// Whether each stale row draws its own mark.
        let showRowAges: Bool
    }

    static func ageDecision(
        _ outcomes: [OutcomeEntry],
        live: Bool,
        now: Date = Date()
    ) -> AgeDecision {
        guard live, !outcomes.isEmpty else {
            return AgeDecision(cardStamp: nil, showRowAges: false)
        }
        let stale = outcomes.filter {
            SourceAge.isStale($0.observedAt, now: now, after: SourceAge.Cadence.live.staleAfter)
        }
        // "All of them" and not "any of them": a card may only speak with one
        // voice when every row it speaks for has reached that age. Otherwise the
        // rows speak for themselves and the fresh ones stay silent.
        guard stale.count == outcomes.count else {
            return AgeDecision(cardStamp: nil, showRowAges: !stale.isEmpty)
        }
        return AgeDecision(
            cardStamp: SourceAge.oldestStamp(stale.map(\.observedAt)),
            showRowAges: false
        )
    }

    /// How many cards a category shows before it collapses the rest.
    ///
    /// CERT-2620 measured what this cap actually costs: production event
    /// 14780145 yields ELEVEN `Other Markets` cards, and `Race to 7 Points` —
    /// the exact market #5133 exists to make visible — is card NINE. Moving it
    /// out of the hero and into this section put it behind the cap instead, so
    /// the reader gained nothing.
    static let itemDisplayCap = 5

    /// The cards a category actually renders.
    ///
    /// Split out of `body` because a SwiftUI view's body cannot be asserted on:
    /// "the ninth card is reachable" is a claim about THIS function, so this is
    /// where the guard can hold it. `body`'s use of it is pinned by the source
    /// scan in `frontend/__tests__/ios/aScoringRaceStaysVisible5133.test.ts`.
    static func displayedItems(_ items: [MarketItem], expanded: Bool) -> [MarketItem] {
        expanded ? items : Array(items.prefix(itemDisplayCap))
    }

    /// Which categories the reader has opened. Empty is the D102 shape: the
    /// overflow takes no real estate closed, and one tap opens it.
    @State private var expandedCategories: Set<String> = []

    var body: some View {
        let cats = categories
        if cats.isEmpty { EmptyView() }
        else {
            let totalItems = cats.reduce(0) { $0 + $1.items.count }
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Additional Markets")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    // #3550 — "1 markets grouped by category" is what every US
                    // Open page printed, because a tennis event's props all
                    // arrive under one market name. The count is right; the
                    // noun was not agreeing with it.
                    let noun = totalItems == 1 ? "market" : "markets"
                    Text(
                        isGameFinished
                            ? "\(totalItems) \(noun) grouped by category · \(SettledQuote.sectionNote)"
                            : "\(totalItems) \(noun) grouped by category"
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }

                let columns = [GridItem(.flexible())]
                LazyVGrid(columns: columns, spacing: 12) {
                    ForEach(cats) { cat in
                        VStack(alignment: .leading, spacing: 8) {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(cat.title)
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                Text(cat.subtitle)
                                    .font(.system(size: 10))
                                    .foregroundStyle(.tertiary)
                            }

                            let isExpanded = expandedCategories.contains(cat.id)
                            ForEach(Self.displayedItems(cat.items, expanded: isExpanded)) { item in
                                propMiniCard(item)
                            }
                            // CERT-2620 — this was `Text("+N more")`, which is
                            // inert: the cards past the cap could not be reached
                            // at all, so a market moved into this section from
                            // somewhere worse was still invisible to a reader.
                            if cat.items.count > Self.itemDisplayCap {
                                Button {
                                    if isExpanded { expandedCategories.remove(cat.id) }
                                    else { expandedCategories.insert(cat.id) }
                                } label: {
                                    Text(
                                        isExpanded
                                            ? "Show less"
                                            : "Show \(cat.items.count - Self.itemDisplayCap) more"
                                    )
                                    .font(.system(size: 11))
                                    .fontWeight(.medium)
                                    .foregroundStyle(Color.accentColor)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 6)
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                                .accessibilityLabel(
                                    isExpanded
                                        ? "Show fewer \(cat.title)"
                                        : "Show \(cat.items.count - Self.itemDisplayCap) more \(cat.title)"
                                )
                            }
                        }
                        .padding(12)
                        .background(Color.cardBackground)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(Color.barTrack, lineWidth: 0.5)
                        )
                    }
                }
            }
        }
    }

    /// The one row renderer, live and settled.
    ///
    /// A settled row loses the BAR, not just the caption — the same shape web's
    /// `PropTravelBar.ResolvedMark` takes. A filled bar is a picture of a live
    /// distribution, and re-wording the label while leaving it up keeps the lie
    /// in the part of the row a reader actually looks at.
    ///
    /// #3550 — the label drops whatever the mini-card's own heading already
    /// says (`labelWithoutRedundantHeading`). Done HERE, at display, and not
    /// where `OutcomeEntry` is built, because the label is also this type's
    /// `id` and the key rows are deduplicated on: stripping is injective within
    /// one card (every row there shares the one heading), but making a
    /// venue-supplied identity depend on a presentation rule is how two rows
    /// quietly become one the day a venue names an outcome after a sibling
    /// market. The identity stays the venue's; only the printing changes.
    @ViewBuilder
    private func outcomeRow(
        _ o: OutcomeEntry,
        rank i: Int,
        under heading: String,
        showAge: Bool
    ) -> some View {
        let percent = Int((o.prob * 100).rounded())
        HStack(spacing: 6) {
            Text(labelWithoutRedundantHeading(o.label, under: heading))
                .font(.system(size: 11))
                .foregroundStyle(i == 0 ? .primary : .secondary)
                .lineLimit(2)
            Spacer()
            // #4970, the MIXED case only — the card speaks for its rows whenever
            // they agree (`ageDecision`). Drawn before the bar, as web draws it,
            // and only on a row that is still a live price: `isGameFinished`
            // returns below, so a settled card never reaches this line.
            if showAge, !isGameFinished {
                PriceAgeMarkView(observedAt: o.observedAt, cadence: .live)
            }
            if isGameFinished {
                Text("\(SettledQuote.prefix) \(percent)%")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(.secondary)
            } else {
                GeometryReader { geo in
                    RoundedRectangle(cornerRadius: 2)
                        .fill(i == 0 ? Color.purple.opacity(0.4) : Color.secondary.opacity(0.2))
                        .frame(width: geo.size.width * o.prob)
                }
                .frame(width: 60, height: 6)
                Text("\(percent)%")
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .frame(width: 32, alignment: .trailing)
            }
        }
    }

    private func propMiniCard(_ item: MarketItem) -> some View {
        let sorted = item.outcomes.sorted { $0.prob > $1.prob }
        let maxSources = sorted.map(\.sourceCount).max() ?? 1
        let age = Self.ageDecision(sorted, live: isLiveEvent)

        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(item.name)
                    .font(.caption)
                    .fontWeight(.medium)
                    .lineLimit(2)
                Spacer()
                // #4970 CARD HALF — said once, for the card, when every row
                // under it agrees about having gone quiet.
                PriceAgeMarkView(observedAt: age.cardStamp, cadence: .live)
                if maxSources > 1 {
                    Text("\(maxSources)x")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.blue)
                }
            }
            ForEach(sorted.indices, id: \.self) { i in
                outcomeRow(sorted[i], rank: i, under: item.name, showAge: age.showRowAges)
            }
        }
        .padding(8)
        .background(Color.secondary.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.barTrack.opacity(0.5), lineWidth: 0.5)
        )
    }
}
