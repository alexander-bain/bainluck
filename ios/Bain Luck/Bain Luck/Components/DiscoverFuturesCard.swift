import SwiftUI

// The category palette and the hero backdrop both live in
// `Utilities/DiscoverCardVisuals.swift` now — this file used to declare the
// palette for the whole app and its own private copy of the hero, which is how
// the Discover card came to be the one futures hero that never drew its photo
// (#4111). See `FuturesHero`.

// MARK: - Futures Card

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

    private var categoryLabel: String {
        sportCategoryDisplayName(data.sportName ?? data.llmSportCategory).uppercased()
    }

    private var leader: FeedFuturesOutcome? {
        data.topOutcomes?.first
    }

    private var leaderProbability: Double {
        leader?.probability ?? 0
    }

    private var shareURL: URL {
        URL(string: futuresShareURL(data.id, style: .nativeCard)) ?? bainLuckFallbackURL
    }

    private var shareMessage: String {
        if let leader, let prob = leader.probability {
            return "\(leader.name) at \(Int((prob * 100).rounded()))% — \(data.name) on Bain Luck"
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
            ZStack(alignment: .bottomLeading) {
                heroBackground
                    .frame(height: 170)
                    .clipped()

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
                                Text("\(Int((leaderProbability * 100).rounded()))")
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
            }
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
                    VStack(spacing: 7) {
                        ForEach(Array(outcomes.prefix(3).enumerated()), id: \.element.id) { idx, outcome in
                            outcomeRow(outcome, isLeader: idx == 0)
                        }
                    }
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

    private func outcomeRow(_ outcome: FeedFuturesOutcome, isLeader: Bool) -> some View {
        HStack(spacing: 8) {
            Text(outcome.name)
                .font(.caption.weight(isLeader ? .semibold : .regular))
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
                .frame(minWidth: 60, maxWidth: 140, alignment: .leading)

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

            Text("\(Int(((outcome.probability ?? 0) * 100).rounded()))%")
                .font(.caption.weight(.bold).monospacedDigit())
                .frame(width: 34, alignment: .trailing)
        }
    }

    private func renderedShareImage() -> PlatformImage? {
        let outcomes: [(name: String, probability: Double)] = (data.topOutcomes ?? []).compactMap { outcome in
            guard let probability = outcome.probability else { return nil }
            return (outcome.name, probability)
        }
        return ShareCardRenderer.renderFuturesCard(
            marketName: data.name,
            leaderName: leader?.name ?? "",
            probability: leaderProbability,
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
