import SwiftUI
#if canImport(UIKit)
import UIKit
#endif


// ── #2060 item 2: the card's WHEN, formatted ─────────────────────────────────
//
// File scope rather than static members of the View: a SwiftUI `View` is
// implicitly `@MainActor`, so static stored properties on it are isolated and a
// `nonisolated` helper cannot read them.
//
// TWO parsers, and that is not belt-and-braces. `ISO8601DateFormatter` with
// `.withFractionalSeconds` REFUSES a timestamp that has none, and the server
// sends `datetime.isoformat()` — which emits fractional seconds only when the
// value has microseconds. A single parser would therefore work on some rows and
// silently drop the date on others, which reads exactly like "this market has no
// commence time" (gotcha #53: absence and failure must not share a representation).
private let labelingISOParsers: [ISO8601DateFormatter] = {
    let plain = ISO8601DateFormatter()
    plain.formatOptions = [.withInternetDateTime]
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return [plain, fractional]
}()

private let labelingDisplayFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "EEE, MMM d 'at' h:mm a"
    return f
}()

/// `"2026-08-18T00:40:00+00:00"` -> `"Mon, Aug 17 at 5:40 PM"` (device timezone).
/// Returns nil for nil and for anything unparseable — never a placeholder date.
nonisolated func labelingShortDate(_ iso: String?) -> String? {
    guard let iso, !iso.isEmpty else { return nil }
    for parser in labelingISOParsers {
        if let date = parser.date(from: iso) {
            return labelingDisplayFormatter.string(from: date)
        }
    }
    return nil
}

struct DiscoverLabelingView: View {
    @EnvironmentObject private var authManager: AuthManager
    @StateObject private var viewModel = DiscoverLabelingViewModel()
    @State private var selectedLabel: String?
    @State private var selectedTags: Set<String> = []
    @State private var notes = ""
    @State private var betterThanPrevious = false
    @State private var worseThanNext = false

    /// Set when Bad is tapped: the six reason chips replace the verdict row until
    /// one is chosen or the reason is skipped (#2060 item 1).
    @State private var awaitingBadReason = false

    private let labels = [
        ("love", "Love"),
        ("fine", "Fine"),
        ("bad", "Bad"),
        ("kill", "Kill"),
    ]

    /// ── THE SIX CHIPS, AND WHY THE STORED TAG IS NOT THE ENGLISH ─────────────
    ///
    /// One tap after Bad (#2060 item 1). Mirrors the web `/admin/labeling` flow,
    /// which has had this since it shipped — native never got it, which is the
    /// parity gap this closes.
    ///
    /// The stored tag is the STORE's canonical spelling, which is why "Confusing"
    /// stores `unclear` and "Boring" stores `low_stakes`: the corpus already holds
    /// 16 and 6 rows under those names, and a chip that minted a new spelling
    /// would split the very tally it exists to grow. The pairing is asserted
    /// against the backend vocabulary by
    /// `backend/tests/test_label_reason_routing.py`.
    ///
    /// Order is by measured frequency of the complaint each names, so the most
    /// common answer is the shortest reach on a phone. `stale` leads because it
    /// is 40% of the corpus (35 of 88 rows, measured 2026-08-21).
    private let badReasons: [(tag: String, title: String)] = [
        ("stale", "Stale"),
        ("wrong_probability", "Wrong probability"),
        ("unclear", "Confusing"),
        ("duplicate", "Duplicate"),
        ("bad_image", "Bad image"),
        ("low_stakes", "Boring"),
    ]

    private let reasonTags = [
        "movement", "public_story", "high_stakes", "close_probability",
        "source_disagreement", "celebrity_or_person", "sports_relevance",
        "fun_or_weird", "timely", "surprising_probability", "major_event",
        "finance_ladder", "commodity_ladder", "too_niche", "duplicate",
        "stale", "unclear", "bad_image", "low_stakes", "repetitive",
        "misleading", "generic_hook", "wrong_category", "not_a_real_prediction",
    ]

    var body: some View {
        labelingContent
        .navigationTitle("Discover Labeling")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .task {
            viewModel.updateUserEmail(authManager.user?.email)
            if viewModel.items.isEmpty && !viewModel.loading {
                await viewModel.load()
            } else {
                // Returning to the screen mid-session: the queue is intact but
                // the meter is from whenever it was last drawn.
                await viewModel.refreshProgress()
            }
        }
        // #2060 item 5 — top up before the queue runs out, so there is no wait
        // between votes. Keyed on the index rather than driven from `submit` so
        // it also covers Skip and Undo, which move the pointer without writing.
        .onChange(of: viewModel.currentIndex) { _, _ in
            Task { await viewModel.prefetchIfNeeded() }
        }
        .onChange(of: authManager.user?.email) { _, newEmail in
            viewModel.updateUserEmail(newEmail)
        }
    }

    private var labelingContent: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header

                if viewModel.loading {
                    ProgressView("Loading debug feed...")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                } else if let error = viewModel.error {
                    errorCard(error)
                }

                if let item = viewModel.currentItem {
                    reviewCard(item)
                    formControls
                } else if !viewModel.loading {
                    completedState
                }
            }
            .padding()
        }
        .refreshable {
            resetForm()
            await viewModel.load()
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(viewModel.reviewedCount)/\(viewModel.items.count) reviewed")
                        .font(.subheadline.weight(.semibold))
                    Text("\(viewModel.remainingCount) remaining")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if viewModel.submittedCount > 0 {
                    Text("\(viewModel.submittedCount) saved")
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color.accentColor.opacity(0.12), in: Capsule())
                }
            }

            ProgressView(
                value: Double(viewModel.reviewedCount),
                total: Double(max(viewModel.items.count, 1))
            )

            if let progress = viewModel.progress {
                goldMeter(progress)
            }

            if !viewModel.labelCounts.isEmpty {
                FlowLayout(spacing: 6) {
                    ForEach(viewModel.labelCounts.sorted(by: { $0.key < $1.key }), id: \.key) { label, count in
                        Text("\(count) \(label)")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.secondary.opacity(0.12), in: Capsule())
                    }
                }
            }

            if let summary = viewModel.loadSummary {
                Text(summary)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            if viewModel.localReviewedCount > 0 {
                Button {
                    resetForm()
                    Task { await viewModel.resetLocalReviewedCards() }
                } label: {
                    Label("Reset reviewed cards", systemImage: "arrow.counterclockwise")
                }
                .font(.caption)
                .buttonStyle(.bordered)
                .disabled(viewModel.loading || viewModel.submitting)
            }
        }
    }

    /// ── THE GOLD METER, AND THE LEG IT LEADS WITH (#2060 item 4) ─────────────
    ///
    /// Three legs, each with its own state, never folded into one percentage.
    /// A big corpus from three sittings and a small one growing daily produce
    /// almost the same percentage and mean opposite things.
    ///
    /// The STREAK is displayed because temporal spread is the gold set's actual
    /// requirement — the Discover slate turns over daily, so 250 labels from two
    /// sittings are 250 opinions about two slates. That makes the streak the
    /// requirement made visible, not gamification, and it is why it sits beside
    /// the day count rather than alone.
    private func goldMeter(_ progress: LabelingProgress) -> some View {
        HStack(spacing: 8) {
            meterChip(
                "Today",
                "\(progress.today)/\(progress.dailyTarget)",
                met: progress.dailyMet
            )
            meterChip(
                "Gold set",
                "\(progress.total)/\(progress.totalTarget)",
                met: progress.totalMet
            )
            meterChip(
                "Days",
                "\(progress.distinctDays)/\(progress.spreadTarget)",
                met: progress.spreadMet
            )
            if progress.streak > 0 {
                meterChip(
                    "Streak",
                    "\(progress.streak)d",
                    met: true
                )
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            "\(progress.today) of \(progress.dailyTarget) today, "
            + "\(progress.total) of \(progress.totalTarget) in the gold set, "
            + "\(progress.distinctDays) of \(progress.spreadTarget) days, "
            + "\(progress.streak) day streak"
        )
    }

    private func meterChip(_ title: String, _ value: String, met: Bool) -> some View {
        VStack(spacing: 1) {
            Text(value)
                .font(.caption.weight(.bold).monospacedDigit())
                .foregroundStyle(met ? Color.green : Color.primary)
            Text(title)
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 5)
        .background(
            (met ? Color.green : Color.secondary).opacity(0.10),
            in: RoundedRectangle(cornerRadius: 8)
        )
    }

    private func errorCard(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(message, systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
            HStack {
                Button("Retry") {
                    Task { await viewModel.load() }
                }
                .buttonStyle(.bordered)
            }
        }
        .font(.subheadline)
        .padding()
        .background(Color.red.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
    }

    private func reviewCard(_ item: DiscoverLabelingDebugItem) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.name)
                        .font(.headline)
                    if let headline = item.headline, !headline.isEmpty {
                        Text(headline)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("#\(item.rank)")
                        .font(.title3.weight(.bold))
                    Text("score \(Int(item.score.rounded()))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            FlowLayout(spacing: 6) {
                if let stratum = item.stratum {
                    pill(displayTag(stratum))
                }
                pill(item.category)
                pill(item.archetype ?? "unknown")
                pill(item.source ?? "unknown")
                pill(item.qualityClass ?? "normal")
                if item.hook == true { pill("hook") }
                if item.image == true { pill("image") }
                if let storyKey = item.storyKey { pill(storyKey) }
            }

            if let selectionReason = item.selectionReason {
                Text("Selection: \(selectionReason)")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            if let context = item.context ?? item.reason, !context.isEmpty {
                Text(context)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
            }

            // #2060 item 2 — a probability is ungradeable without a when.
            if let when = scheduleLine(item) {
                Text(when)
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            if let outcomes = item.topOutcomes, !outcomes.isEmpty {
                // #2060 item 1 — the whole field is rendered by ONE decision, so
                // the two sides of one question cannot be rounded twice and
                // printed as 101. Computed once here rather than per row, because
                // deriving a complement is a fact about the CARD.
                let percents = cardPercents(outcomes)
                VStack(spacing: 8) {
                    ForEach(Array(outcomes.prefix(3).enumerated()), id: \.offset) { index, outcome in
                        HStack {
                            Text(outcome.name ?? "Outcome")
                                .font(.subheadline)
                                .lineLimit(1)
                            Spacer()
                            Text(percentText(percents.indices.contains(index) ? percents[index] : nil))
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .padding()
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.35), lineWidth: 0.5))
    }

    private var formControls: some View {
        VStack(alignment: .leading, spacing: 14) {
            if awaitingBadReason {
                badReasonChips
            } else {
                verdictButtons
            }

            FlowLayout(spacing: 6) {
                ForEach(reasonTags, id: \.self) { tag in
                    Button(displayTag(tag)) {
                        toggleTag(tag)
                    }
                    .font(.caption)
                    .buttonStyle(.bordered)
                    .tint(selectedTags.contains(tag) ? .accentColor : .secondary)
                }
            }

            HStack(spacing: 8) {
                Toggle("Should beat previous", isOn: $betterThanPrevious)
                Toggle("Should lose to next", isOn: $worseThanNext)
            }
            .font(.caption)
            .toggleStyle(.button)

            TextField("Notes", text: $notes, axis: .vertical)
                .textFieldStyle(.roundedBorder)

            Button {
                guard let label = selectedLabel else { return }
                lightHaptic()
                Task {
                    let saved = await viewModel.submit(
                        label: label,
                        reasonTags: selectedTags,
                        notes: notes,
                        betterThanPrevious: betterThanPrevious,
                        worseThanNext: worseThanNext
                    )
                    if saved {
                        resetForm()
                    }
                }
            } label: {
                if viewModel.submitting {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                } else {
                    Text("Submit & Next")
                        .frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(selectedLabel == nil || viewModel.submitting)
            // Hidden during the reason flow: the chip IS the submit there, and
            // leaving this live would offer a second path that writes the same
            // Bad with no reason — the unroutable row the chips exist to end.
            .opacity(awaitingBadReason ? 0 : 1)
            .frame(height: awaitingBadReason ? 0 : nil)
            .disabled(awaitingBadReason)
            .accessibilityHidden(awaitingBadReason)

            HStack(spacing: 16) {
                Button("Skip") {
                    viewModel.skip()
                    resetForm()
                }
                .frame(maxWidth: .infinity)
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)

                if viewModel.canUndo {
                    Button {
                        lightHaptic()
                        Task {
                            // Awaited: undo now DELETES the judgment row, so it
                            // is a network write and the form must not reset
                            // until it lands. A failed delete leaves the button
                            // live and the error on screen rather than quietly
                            // becoming a pointer rewind over a surviving row.
                            await viewModel.undo()
                            resetForm()
                        }
                    } label: {
                        Label("Undo", systemImage: "arrow.uturn.backward")
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                    .disabled(viewModel.submitting)
                }
            }
        }
    }

    /// The four verdicts, and ONE line saying what the fourth one is for.
    ///
    /// UX-P125 item 3b. Alex graded a session on the device and guessed wrong
    /// about Kill — reasonably, because nothing on screen distinguishes it from
    /// Bad, and four buttons in a row read as one scale. They are not one scale.
    /// Love/Fine/Bad grade how INTERESTING a card is and all three keep it in
    /// the feed; Kill is a different axis entirely — it says this card should
    /// never be shown to anyone, and it is the only one of the four with a
    /// consequence outside the corpus.
    ///
    /// A tooltip would not have fixed this: the mis-tap happens at full speed in
    /// a Rapid pass, and a hover does not exist on a phone. The line is always
    /// visible, directly under the buttons it describes, and costs one row.
    private var verdictButtons: some View {
        VStack(alignment: .leading, spacing: 6) {
            verdictButtonRow

            Text("Love / Fine / Bad grade interestingness. Kill = never show anyone.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityLabel(
                    "Love, Fine and Bad grade how interesting a card is. "
                        + "Kill means never show this card to anyone."
                )
        }
    }

    private var verdictButtonRow: some View {
        HStack(spacing: 8) {
            ForEach(labels, id: \.0) { key, title in
                Button(title) {
                    lightHaptic()
                    // Bad asks WHY before it writes. Every other verdict is a
                    // complete opinion on its own; "bad" without a reason is the
                    // bare downvote that produced 71 unroutable rows.
                    if key == "bad" {
                        selectedLabel = key
                        awaitingBadReason = true
                    } else {
                        selectedLabel = key
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(labelTint(key, selected: selectedLabel == key))
                .controlSize(.regular)
            }
        }
    }

    /// One tap after Bad, and the tap SUBMITS (#2060 item 1).
    ///
    /// Not "select a chip, then press Submit & Next". The reason chip is the last
    /// thing Alex knows, so making it the last thing he taps is what keeps a
    /// reasoned Bad the same two taps a bare one used to be — otherwise the
    /// routable path costs more than the unroutable one and the corpus fills with
    /// whichever is cheaper.
    private var badReasonChips: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Why is it bad?")
                .font(.subheadline.weight(.semibold))

            FlowLayout(spacing: 8) {
                ForEach(badReasons, id: \.tag) { reason in
                    Button(reason.title) {
                        submitBad(reasonTag: reason.tag)
                    }
                    .font(.subheadline)
                    .buttonStyle(.bordered)
                    .tint(.orange)
                    .disabled(viewModel.submitting)
                }
            }

            HStack(spacing: 16) {
                Button("Skip reason") {
                    submitBad(reasonTag: nil)
                }
                .font(.caption)
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .disabled(viewModel.submitting)

                Button("Back") {
                    awaitingBadReason = false
                    selectedLabel = nil
                }
                .font(.caption)
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .disabled(viewModel.submitting)
            }
        }
    }

    /// Submit a Bad with (or deliberately without) one reason.
    ///
    /// The chip is ADDED to whatever multi-select tags are already set rather
    /// than replacing them — the 24-tag row is still on screen and a tag Alex set
    /// there is an opinion he expressed.
    private func submitBad(reasonTag: String?) {
        lightHaptic()
        var tags = selectedTags
        if let reasonTag {
            tags.insert(reasonTag)
        }
        Task {
            let saved = await viewModel.submit(
                label: "bad",
                reasonTags: tags,
                notes: notes,
                betterThanPrevious: betterThanPrevious,
                worseThanNext: worseThanNext
            )
            if saved {
                resetForm()
            }
        }
    }

    /// Light impact on every vote (#2060 item 5). Matches `PinButton` and
    /// `FeedView`, which already use exactly this generator and style.
    private func lightHaptic() {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
    }

    /// ── HONEST-EMPTY, RULING 027 (#2060 item 5) ──────────────────────────────
    ///
    /// Two endings, and they are different facts, so they get different words.
    ///
    /// `queueExhausted` means the SERVER said `has_more: false` and had nothing
    /// fresh — that is a finished day's work and it says so. Anything else means
    /// the on-screen batch is spent but the server may still have cards, which is
    /// a "load more", not a congratulation.
    ///
    /// What neither of them does is recycle. Re-serving cards Alex has already
    /// judged would inflate the corpus with duplicate opinions on one slate,
    /// which is precisely the spread failure the progress meter exists to expose.
    private var completedState: some View {
        VStack(spacing: 12) {
            Image(systemName: viewModel.queueExhausted ? "checkmark.seal.fill" : "tray")
                .font(.largeTitle)
                .foregroundStyle(viewModel.queueExhausted ? .green : .secondary)

            Text(viewModel.queueExhausted
                 ? "You've judged everything fresh today"
                 : "That's the batch")
                .font(.headline)
                .multilineTextAlignment(.center)

            Text(viewModel.queueExhausted
                 ? "Nothing is being recycled — new cards appear as the slate turns over."
                 : "There may be more candidates on the server.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            if let progress = viewModel.progress, viewModel.queueExhausted {
                Text(spreadEncouragement(progress))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Button(viewModel.queueExhausted ? "Check again" : "Load more") {
                resetForm()
                Task { await viewModel.load() }
            }
            .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }

    /// What is left, stated as the requirement rather than as a score.
    ///
    /// Names the SPREAD leg, not the total, because that is the one a good day's
    /// grinding cannot fix — and saying "12 more days" when he has just done
    /// twenty cards is the honest thing, not a discouraging one.
    private func spreadEncouragement(_ progress: LabelingProgress) -> String {
        let daysLeft = max(progress.spreadTarget - progress.distinctDays, 0)
        if daysLeft == 0 {
            return "\(progress.total) of \(progress.totalTarget) labels, spread across \(progress.distinctDays) days."
        }
        return "\(progress.total) of \(progress.totalTarget) labels across \(progress.distinctDays) days — \(daysLeft) more separate days gets the spread the gold set needs."
    }

    private func toggleTag(_ tag: String) {
        if selectedTags.contains(tag) {
            selectedTags.remove(tag)
        } else {
            selectedTags.insert(tag)
        }
    }

    private func resetForm() {
        selectedLabel = nil
        selectedTags = []
        notes = ""
        betterThanPrevious = false
        worseThanNext = false
        // Left set, the next card would open straight onto "Why is it bad?" —
        // asking for a reason before a verdict, on a card nobody has judged.
        awaitingBadReason = false
    }

    private func pill(_ text: String) -> some View {
        Text(displayTag(text))
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Color.secondary.opacity(0.12), in: Capsule())
            .lineLimit(1)
    }

    /// The percent shown on a labeling card. The arithmetic lives in
    /// `renderedPercent` because the server fingerprints this card at exactly
    /// this resolution to gate the judgment written against it — an inline copy
    /// here is a second implementation of a cross-runtime rule
    /// (`contracts/rendered_percent.json`, #1933).
    private func probabilityText(_ value: Double?) -> String {
        guard let percent = renderedPercent(value) else { return "--" }
        return "\(percent)%"
    }

    private func percentText(_ percent: Int?) -> String {
        guard let percent else { return "--" }
        return "\(percent)%"
    }

    /// The whole percents for one card's served outcomes (#2060).
    ///
    /// Prefers the SERVER's `rendered_percent`, which is the value the card
    /// fingerprint was taken over — so the screen and the digest cannot disagree.
    /// Falls back to computing the card rule locally when the payload predates
    /// #2060, which keeps an older server renderable without letting it reopen
    /// the 93 + 8 = 101 defect.
    private func cardPercents(_ outcomes: [DiscoverLabelingOutcome]) -> [Int?] {
        let served = outcomes.map(\.renderedPercent)
        if served.contains(where: { $0 != nil }) {
            return served
        }
        return renderedCardPercents(outcomes.map { $0.probability ?? $0.currentProbability })
    }

    /// "Starts Mon, Aug 18 at 5:40 PM · Resolves Fri, Aug 21" (#2060 item 2).
    ///
    /// Both dates, because they answer different questions: on a Kalshi game
    /// market `resolution_date` is the CLOSE time, not the start (gotcha #14), so
    /// showing only it told Alex the wrong thing about when.
    private func scheduleLine(_ item: DiscoverLabelingDebugItem) -> String? {
        var parts: [String] = []
        if let starts = shortDate(item.commenceTime) {
            parts.append("Starts \(starts)")
        }
        if let resolves = shortDate(item.resolutionDate) {
            parts.append("Resolves \(resolves)")
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// An unparseable timestamp is omitted, never rendered as a placeholder date.
    private func shortDate(_ iso: String?) -> String? {
        labelingShortDate(iso)
    }

    private func displayTag(_ raw: String) -> String {
        raw.replacingOccurrences(of: "_", with: " ")
    }

    private func labelTint(_ label: String, selected: Bool) -> Color {
        guard selected else { return .secondary }
        switch label {
        case "love": return .green
        case "bad": return .orange
        case "kill": return .red
        default: return .accentColor
        }
    }
}
