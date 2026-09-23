import SwiftUI

// The category palette and the hero backdrop both live in
// `Utilities/DiscoverCardVisuals.swift` now — this file used to declare the
// palette for the whole app and its own private copy of the hero, which is how
// the Discover card came to be the one futures hero that never drew its photo
// (#4111). See `FuturesHero`.

// MARK: - The card's percents

/// The whole percents a Discover futures card prints for its outcomes, decided
/// ONCE for the card — `renderedCardPercents`, native's arm of
/// `contracts/rendered_percent.json`.
///
/// ## Why the card had to stop rounding each row on its own
///
/// This card formatted every row with its own bare `Int((p * 100).rounded())`,
/// so a two-outcome market whose sides are an exact complement printed a sum of
/// 101 whenever both landed on the `.5` grid the venues quote on — the defect
/// #2060 clause (1) names ("must render p and 100−p"). `renderedCardPercents`
/// was written for exactly that and had **no call sites anywhere in the app
/// target**: the rule existed, contract-tested, and nothing called it. This is
/// the wiring, not a second copy of the rule.
///
/// (Deliberately not spelling that scope as a directory glob. `PriceAgeMarkTests`
/// source-scans this file, and its comment stripper treats a slash-star pair as
/// the start of a block comment wherever it appears — including inside a glob, or
/// inside prose describing one — then discards everything after it when no
/// closing pair follows. It fails closed, so the cost is a puzzling red rather
/// than a blind guard, but do not reintroduce that glyph in this file.)
///
/// Measured on production 2026-09-22, `GET /api/feed?limit=50&offset=0&event_pct=0.15`
/// (the phone's own query): **3 of the 39 futures cards on page one** printed 101
/// — "Will Dallas Stars advance…?" at 60/41, "Will Florida Panthers advance…?"
/// at 54/47, "Will Anthropic's valuation hit (HIGH) $3.0T…?" at 76/25. Across the
/// database, 6,609 of 17,583 open two-outcome mutually-exclusive markets sit on
/// that boundary today.
///
/// Passing the WHOLE outcome list (not the three rows the card draws) is
/// deliberate: a card's sum is a property of its market, and the pair rule is
/// gated on the two values summing into the complement band, so a market whose
/// top two rows merely look like a pair is left alone. A field of three or more
/// renders exactly as before — #2088's `card_sum_reason` sentence, not this
/// function, is what explains those.
nonisolated func discoverFuturesCardPercents(_ outcomes: [FeedFuturesOutcome]) -> [Int?] {
    renderedCardPercents(outcomes.map(\.probability))
}

/// The exact string one outcome row prints. `?? 0` preserves what the row
/// printed before for an unpriced outcome, which was `"0%"`.
nonisolated func discoverFuturesCardPercentLabel(_ percent: Int?) -> String {
    "\(percent ?? 0)%"
}

/// The rows the SHARE IMAGE is handed — the card's whole served field, nils and
/// all.
///
/// A file-scope function rather than one line inside `renderedShareImage()`,
/// because that line WAS the defect and a line inside a private view method is a
/// line no test can reach. The share battery proved the point: with the rule
/// stated inline and guarded only by a source scan for the exact old spelling, a
/// mutant that re-filtered the field in slightly different words **survived** —
/// the scan was aimed at one phrasing of a defect rather than at its behaviour.
/// Same argument as ``ShareableFuturesCardView/printedFuturesPercents`` makes on
/// the other side of the call.
nonisolated func discoverFuturesShareRows(
    _ outcomes: [FeedFuturesOutcome]
) -> [(name: String, probability: Double?)] {
    outcomes.map { ($0.name, $0.probability) }
}

// MARK: - Futures Card

/// #8213 — carries the outcome rows' measured width up to the card, so the
/// percent column can be sized from the room the row actually has.
private struct FuturesOutcomeRowWidthKey: PreferenceKey {
    static let defaultValue: Double = 0
    static func reduce(value: inout Double, nextValue: () -> Double) {
        value = max(value, nextValue())
    }
}

struct NativeFuturesDiscoverCard: View {
    let data: FeedFuturesData
    let feedContext: String?
    let expandedContext: String?
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil
    var onContextExpand: (() -> Void)? = nil
    var onContextCollapse: (() -> Void)? = nil
    /// Fired when the reader taps the share icon — see the `ShareLink` below for
    /// why this is a simultaneous gesture and not a button action. #5525.
    var onShare: (() -> Void)? = nil

    /// #1772 — the hero percentage, ramped.
    ///
    /// `Font.system(size:weight:)` does NOT scale with Dynamic Type, and there
    /// is no `system(size:relativeTo:)` for it — that variant only exists on
    /// `Font.custom`. `@ScaledMetric` is the real mechanism: 52pt at the
    /// default setting, scaled by the same curve `.largeTitle` uses, so the
    /// numeral and the `.headline` name beneath it move together instead of
    /// drifting apart.
    @ScaledMetric(relativeTo: .largeTitle) private var heroNumeralSize: CGFloat = 52

    /// #6343 — the price-age reveal, open or closed. The phone has no hover, so
    /// the precise stamp arrives by tap; the state lives here rather than in the
    /// mark because the caption is drawn under the whole footer, where it cannot
    /// cover the number the reader just asked about.
    @State private var revealedPriceAge: String?

    /// #8213 — the width the outcome rows were actually given, published by a
    /// `GeometryReader` behind them. Not derived from the screen: a card's width
    /// is a layout outcome (padding, iPad columns, Stage Manager), and deriving
    /// it would assert a layout instead of measuring one.
    @State private var outcomeRowWidth: Double = 0

    /// #8213 — the view's OWN text size, which is what the column model measures
    /// against. `UIFont.preferredFont` with no traits resolves the PROCESS
    /// setting instead, and measuring one while drawing the other is how a
    /// column ends up narrower than the string inside it.
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var categoryLabel: String {
        sportCategoryDisplayName(data.sportName ?? data.llmSportCategory).uppercased()
    }

    private var leader: FeedFuturesOutcome? {
        data.topOutcomes?.first
    }

    /// The whole percents this card prints, decided ONCE for the whole card.
    ///
    /// Every number on this card — the hero numeral, each outcome row, the share
    /// sentence — is one answer to one question, so they are rounded as one
    /// decision (`discoverFuturesCardPercents` below).
    private var renderedPercents: [Int?] {
        discoverFuturesCardPercents(data.topOutcomes ?? [])
    }

    /// The hero's number. `?? 0` preserves the previous behaviour for a card with
    /// no leader or an unpriced one, which printed `0`.
    private var leaderRenderedPercent: Int {
        (renderedPercents.first ?? nil) ?? 0
    }

    private var shareURL: URL {
        URL(string: futuresShareURL(data.id, style: .nativeCard)) ?? bainLuckFallbackURL
    }

    private var shareMessage: String {
        if let leader, leader.probability != nil {
            return "\(leader.name) at \(leaderRenderedPercent)% — \(data.name) on Bain Luck"
        }
        return "\(data.name) on Bain Luck"
    }

    /// #4265 — the caption chain now resolves whole in `DiscoverCaption`, at the
    /// one call site, so the record in
    /// `fixtures/discover/caption-chain-record-2026-09-09.json` grades the real
    /// composition rather than a pure function nothing has to call.
    /// `hookDescription` is still the last rung; it is applied there, not here.
    /// Kept as a trim-and-nil so a whitespace-only caption cannot reserve a line.
    private var contextText: String? {
        let caption = DiscoverCaption.firstMeaningful([feedContext, data.hookDescription])
        return caption.isEmpty ? nil : caption
    }

    /// The capsule under the card: the names of the sources behind the number,
    /// or nil to draw nothing.
    ///
    /// 🔴 #4351 — BOTH BRANCHES USED TO `.uppercased()` THE RAW KEY, so the first
    /// card on the app's default screen read `ODDS_API`: a database value, with an
    /// underscore in it, printed as the name of where a probability came from.
    /// `SourceLabels` has named that key "Sportsbooks" since #4135; nothing on
    /// Discover was asking it, because #4135's site list was discovered by grepping
    /// for the `switch source` these two files never had.
    ///
    /// ✅ SO THE NIL IS A DECISION, not an accident: a key the app cannot name is a
    /// key the app does not print (`SourceLabels`' own contract). The sibling rows
    /// in `DiscoverView` used to spell that case `?? "market"` and invent a source
    /// called `MARKET`; drawing nothing is the honest rendering, and standing
    /// notice 34 says the same — leave the space empty rather than explain it.
    ///
    /// The capitals go with the keys. `SourceLabels` returns "Sportsbooks", and
    /// uppercasing a name back to `SPORTSBOOKS` would re-create the defect in a
    /// nicer font; D91 asks for a small mark that reads as sourcing, by name.
    private var sourceMark: String? {
        let keys: [String] = {
            if let sources = data.sources, sources.count > 1 { return sources }
            return [data.source].compactMap { $0 }
        }()
        let named = keys.compactMap { SourceLabels.label(for: $0) }
        return named.isEmpty ? nil : named.joined(separator: " + ")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // 🔴 #7074 — THE BACKDROP WAS A FIXED-HEIGHT SIBLING OF CONTENT THAT
            // IS FREE TO BE TALLER, so the card's own header spilled off its own
            // photograph. `ZStack(alignment: .bottomLeading)` takes the height of
            // its TALLEST child: the overlay below is a pill row, a 52pt
            // `@ScaledMetric` numeral and a leader name of up to three lines
            // inside 14pt padding, and at the default Dynamic Type size that is
            // already more than 170. The backdrop stayed 170 and bottom-aligned,
            // so the overflow came out of the TOP as a white band, the category
            // and Trending pills landed on it — white text on white — and the
            // photo's square top corners sat in the middle of a rounded card.
            //
            // MEASURED, not reasoned: `artifacts/native-239/BEFORE-discover-s2800.png`
            // (iPhone 17 Pro, default type, "Xi Jinping out before 2027?") — card
            // white begins at y=1316 and the photo at y=1339, a 23px @3x = 7.7pt
            // band. On Alex's phone (build 15, `group-overlap.png`, larger type
            // and a taller card) the same band swallowed most of both pills, which
            // is the "overlap" in #7074's title.
            //
            // The fix is to stop expressing the hero as two independent heights.
            // The backdrop is now the content's BACKGROUND, so it is exactly as
            // tall as the content, and 170 is a FLOOR rather than a value — a
            // short card still draws the full hero it always did.
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(categoryLabel)
                        .font(.caption2.weight(.heavy))
                        .tracking(0.8)
                        .foregroundStyle(.white.opacity(0.78))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(.black.opacity(0.24), in: Capsule())

                    Spacer()

                    if isTrending(data) {
                        Label("Trending", systemImage: "flame.fill")
                            .font(.caption2.weight(.heavy))
                            .foregroundStyle(.orange)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.black.opacity(0.24), in: Capsule())
                    }
                }

                Spacer(minLength: 16)

                if let leader {
                    HStack(alignment: .bottom, spacing: 10) {
                        // #1772: the hero numeral and the name below it used
                        // to use DIFFERENT metrics — 52pt frozen over a
                        // `.headline` that scales. Raise the text size and
                        // only the name grew, the bottom-aligned HStack got
                        // tight, and `minimumScaleFactor` compressed the
                        // string until the trailing `%` read as a subscript.
                        // That is the glyph in Alex's report #143.
                        //
                        // Both now ramp together. `%` is split into its own
                        // Text because it is not a digit: inside a
                        // `monospacedDigit()` run it kept proportional
                        // metrics against black-weight numerals, so it was
                        // the first glyph to lose width under compression.
                        HStack(alignment: .firstTextBaseline, spacing: 0) {
                            Text("\(leaderRenderedPercent)")
                                .font(.system(size: heroNumeralSize, weight: .black).monospacedDigit())
                            Text("%")
                                .font(.system(size: heroNumeralSize, weight: .black))
                        }
                            .minimumScaleFactor(0.76)
                            .lineLimit(1)
                            .foregroundStyle(.white)
                            .shadow(color: .black.opacity(0.25), radius: 8, x: 0, y: 3)

                        MovementBadge(movement: leader.movement)
                            .padding(.bottom, 8)
                    }

                    Text(leader.name)
                        .font(.headline.weight(.bold))
                        .foregroundStyle(.white.opacity(0.92))
                        .lineLimit(3)
                        .minimumScaleFactor(0.92)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(14)
            .frame(
                maxWidth: .infinity,
                minHeight: FuturesHero.discoverCardMinimumHeight,
                alignment: .bottomLeading
            )
            .background { heroBackground }
            .clipShape(UnevenRoundedRectangle(topLeadingRadius: 18, topTrailingRadius: 18))

            VStack(alignment: .leading, spacing: 12) {
                Text(data.name)
                    .font(.headline.weight(.bold))
                    .lineLimit(4)
                    .fixedSize(horizontal: false, vertical: true)

                if let contextText {
                    ExpandableNativeContextText(
                        text: contextText,
                        expandedText: expandedContext ?? data.hookDescription,
                        font: .subheadline,
                        onExpand: onContextExpand,
                        onCollapse: onContextCollapse
                    )
                }

                if let outcomes = data.topOutcomes, outcomes.count > 1 {
                    let percents = renderedPercents
                    let shown = Array(outcomes.prefix(3).enumerated())
                    // #8213 — the column widths are measured from the strings
                    // these rows will actually print, at this view's text size,
                    // in the width this card was actually given. The percent
                    // column is computed ONCE here rather than inside the row
                    // so all three rows share a right edge, which is the one
                    // thing the 34pt literal was getting right.
                    let columns = FuturesOutcomeRowColumns.layout(
                        percentLabels: shown.map {
                            discoverFuturesCardPercentLabel(
                                percents.indices.contains($0.offset) ? percents[$0.offset] : nil)
                        },
                        availableWidth: outcomeRowWidth,
                        typeSize: dynamicTypeSize
                    )
                    VStack(spacing: 7) {
                        ForEach(shown, id: \.element.id) { idx, outcome in
                            outcomeRow(
                                outcome,
                                isLeader: idx == 0,
                                percent: percents.indices.contains(idx) ? percents[idx] : nil,
                                columns: columns
                            )
                        }
                    }
                    .background(
                        GeometryReader { geo in
                            Color.clear.preference(
                                key: FuturesOutcomeRowWidthKey.self, value: geo.size.width)
                        }
                    )
                    .onPreferenceChange(FuturesOutcomeRowWidthKey.self) { outcomeRowWidth = $0 }
                }

                // #2088 — the sentence a card carries when its numbers do not add
                // up to 100. Web's `FeedCard` has drawn it since #2088; native had
                // no `card_sum_reason` in the tree at all, so the identical card
                // explained itself on the web and stood bare on the phone
                // (production 2026-09-18: 2 of 92 feed cards, "Crude Oil all time
                // high?" at 13/1 and the Mecca Agreement at 26/6).
                //
                // The words live in `CardSum.swift` so a guard can reach them — a
                // branch spelled in a view body is a branch no gate can run, and CI
                // compiles no Swift (#4302). The server's answer is taken verbatim
                // and nothing is derived here; that file says why.
                if let sumExplanation = cardSumExplanation(data.cardSumReason) {
                    Text(sumExplanation)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                HStack(spacing: 8) {
                    if let mark = sourceMark {
                        Text(mark)
                            .font(.caption2.weight(.heavy))
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(Color.blue.opacity(0.10), in: Capsule())
                    }

                    // #6343 — beside the source mark, which is where D91 and
                    // notice 34 put sourcing: the number, the small mark, at most
                    // one short caption.
                    //
                    // The rule — settled suppression and the six-hour futures
                    // cadence — is `discoverPriceAgeMark`, in `PriceAgeMarkView`,
                    // so a guard can pin it. Spelled inline here it would be a
                    // rule no test can reach (see that function's header).
                    if let mark = data.discoverPriceAgeMark(
                        onReveal: { revealedPriceAge = revealedPriceAge == $0 ? nil : $0 }
                    ) {
                        mark
                    }

                    Spacer()

                    // #490 / L2-184: confidence signal (1-3 bars) — renders nothing
                    // when absent. Same tier map + placement as the native
                    // multi-candidate kernels (Comparison/Distribution/HeatMap).
                    SignalBarsView(tier: data.confidenceTier)

                    ShareLink(
                        item: shareURL,
                        subject: Text(data.name),
                        message: Text(shareMessage)
                    ) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(.secondary)
                            .padding(8)
                            .background(Color.secondary.opacity(0.10), in: Circle())
                            .frame(minWidth: 44, minHeight: 44)
                            .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
                    .recordsShareOpened { onShare?() }
                    .contextMenu {
                        Button(action: copyShareImage) {
                            Label("Copy Image", systemImage: "doc.on.doc")
                        }

                        #if os(iOS)
                        Button(action: saveShareImage) {
                            Label("Save Image", systemImage: "square.and.arrow.down")
                        }
                        #endif
                    }
                }

                // #6343 — the tap reveal. Inline UNDER the footer rather than a
                // popover, for the reason `LiquidityMarkView` gives: a popover on
                // a phone covers the number the reader just asked about, and this
                // sentence is only meaningful while that number is on screen.
                if let revealedPriceAge {
                    LiquidityRevealCaption(sentence: revealedPriceAge)
                }
            }
            .padding(14)
        }
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.07), radius: 12, x: 0, y: 5)
        .contentShape(Rectangle())
        .onTapGesture {
            navigationPath.append(Route.futuresDetail(id: data.id))
            onOpen?()
        }
    }

    /// #4111 — the card's art. `image_url` rides in on the same payload the web
    /// reads (11 of 12 futures cards on production page one carried one), and
    /// this hero drew a flat gradient over the top of it for as long as the card
    /// has existed. `FuturesHeroBackground` is the same view the detail page has
    /// always used, so there is no second copy left to fall behind.
    private var heroBackground: some View {
        FuturesHeroBackground(imageURL: data.imageUrl, category: data.llmSportCategory)
    }

    private func outcomeRow(
        _ outcome: FeedFuturesOutcome,
        isLeader: Bool,
        percent: Int?,
        columns: FuturesOutcomeRowColumns.Layout
    ) -> some View {
        // #8213 — the spacing the model subtracts is the spacing the row is
        // built with. Two literals that must agree are two numbers that drift.
        HStack(spacing: FuturesOutcomeRowColumns.interColumnSpacing) {
            Text(outcome.name)
                .font(.caption.weight(isLeader ? .semibold : .regular))
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
                .frame(
                    minWidth: FuturesOutcomeRowColumns.nameMinimum,
                    maxWidth: columns.nameMaximum,
                    alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.secondary.opacity(0.12))
                    Capsule()
                        .fill(isLeader ? Color.blue : Color.secondary.opacity(0.35))
                        .frame(width: max(3, geo.size.width * (outcome.probability ?? 0)))
                }
            }
            .frame(height: 7)

            Text(discoverFuturesCardPercentLabel(percent))
                .font(.caption.weight(.bold).monospacedDigit())
                .lineLimit(1)
                .frame(width: columns.percentWidth, alignment: .trailing)
        }
    }

    /// #2874 — the image is handed the card's WHOLE served field, nils and all.
    ///
    /// It used to `compactMap` the unpriced outcomes away, which was two defects in
    /// one line: the image then rounded each surviving row on its own (so a
    /// complement pair printed 101 in the picture that leaves the app), and a
    /// three-outcome market with one unpriced side arrived as a two-outcome list —
    /// the exact shape `renderedCardPercents` normalises — so the two surfaces
    /// could not even be made to agree by rounding them the same way.
    private func renderedShareImage() -> PlatformImage? {
        let outcomes = discoverFuturesShareRows(data.topOutcomes ?? [])
        return ShareCardRenderer.renderFuturesCard(
            marketName: data.name,
            leaderName: leader?.name ?? "",
            category: data.llmSportCategory ?? data.sportName ?? "Market",
            hookDescription: data.hookDescription,
            outcomes: outcomes
        )
    }

    private func copyShareImage() {
        if let image = renderedShareImage() {
            ShareCardRenderer.copyImageToClipboard(image)
        }
    }

    private func saveShareImage() {
        #if os(iOS)
        if let image = renderedShareImage() {
            ShareCardRenderer.saveImageToPhotos(image)
        }
        #endif
    }
}
