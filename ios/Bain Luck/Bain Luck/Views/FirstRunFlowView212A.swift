import SwiftUI

// MARK: - Ruling 212-A First-Run Flow (#11934, #13517, 359: A)

/// Full approved `212-A` first-run flow replacing the old carousel & 5-step sports quiz:
/// - Screens `2A..2C`: three live, unsettled real-card pairs where the cards themselves are the
///   direct tap targets, with `"Three quick picks, then you're in."` once on Screen 1,
///   `"Your picks decide what Discover shows first."` + `"Tap any you'd check. Both or neither is fine."`,
///   and a single bottom `"Next"` / `"Neither, next"` button.
/// - Screen `2D`: `"Any cities, schools or subjects you care about?"` + `"We'll put these first in Discover and My Stuff."`,
///   quiet rotating served examples (or one still line under Reduce Motion), non-clearing multi-pick
///   search, wrapping full-name chips (`#13517`), and `359: A` sentence-box confirmation states.
struct FirstRunFlowView212A: View {
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
    @EnvironmentObject private var pinManager: PinManager
    @Environment(\.followManager295A) private var followManager
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.colorScheme) private var colorScheme

    @StateObject private var vm: FirstRunViewModel212A
    @State private var showAboutWorkedExample = false
    var onFinished: (() -> Void)? = nil

    init(
        arrivedHeadline: String? = nil,
        onFinished: (() -> Void)? = nil
    ) {
        _vm = StateObject(wrappedValue: FirstRunViewModel212A(arrivedHeadline: arrivedHeadline))
        self.onFinished = onFinished
    }

    #if DEBUG
    init(
        viewModelForTest: FirstRunViewModel212A,
        onFinished: (() -> Void)? = nil
    ) {
        _vm = StateObject(wrappedValue: viewModelForTest)
        self.onFinished = onFinished
    }
    #endif

    private var duplicateNamesInContext: Set<String> {
        let all = vm.pickedItems + vm.suggestions
        var counts: [String: Int] = [:]
        for item in all {
            counts[item.name, default: 0] += 1
        }
        return Set(counts.filter { $0.value > 1 }.keys)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                topBar
                    .padding(.horizontal, 16)
                    .padding(.top, 10)
                    .padding(.bottom, 8)

                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        if vm.isOnPairStep {
                            if let pair = vm.currentPair {
                                pairContent(pair, index: vm.stepIndex)
                            } else if vm.isLoadingPairs {
                                pairsLoadingView
                            } else {
                                pairsErrorView
                            }
                        } else {
                            typeaheadContent
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 6)
                    .padding(.bottom, 28)
                    .frame(maxWidth: 680)
                    .frame(maxWidth: .infinity)
                }

                if vm.isOnPairStep && vm.currentPair != nil {
                    pairFooter
                } else if vm.isOnTypeaheadStep {
                    typeaheadFooter
                }
            }
            .background(DS.surface)
            .navigationDestination(isPresented: $showAboutWorkedExample) {
                AboutBainLuckView212A(
                    showsBackToDiscoverCTA: false,
                    onBackToDiscover: { showAboutWorkedExample = false }
                )
            }
            .task {
                await vm.loadLivePairsIfNeeded()
            }
        }
    }

    private var solidAccentButtonForeground: Color {
        colorScheme == .dark ? Color(hex: "#0F172A") : .white
    }

    // MARK: - Top Bar (Back + Skip on Every Screen; No Completion Bar / No Profile)

    private var topBar: some View {
        HStack(spacing: 10) {
            if vm.stepIndex > 0 {
                Button {
                    vm.goBack()
                } label: {
                    Image(systemName: "chevron.left")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .frame(width: 36, height: 36)
                        .background(DS.cardBg, in: Circle())
                        .overlay(Circle().stroke(DS.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Back")
                .accessibilityIdentifier("firstRunBackButton")
            }

            Spacer(minLength: 8)

            if vm.isOnPairStep && (vm.currentPair != nil || vm.isLoadingPairs) {
                Button {
                    vm.skipCurrentStep(
                        followManager: followManager,
                        pinManager: pinManager,
                        authManager: authManager,
                        onDismiss: finishAndDismiss
                    )
                } label: {
                    Text("Skip")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .padding(.horizontal, 14)
                        .frame(minHeight: 36)
                        .background(DS.cardBg, in: Capsule())
                        .overlay(Capsule().stroke(DS.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("firstRunSkipButton")
            }
        }
    }

    // MARK: - Live Pair Loading / Failure States

    private var pairsLoadingView: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Three quick picks, then you\u{2019}re in.")
                .font(.footnote.weight(.medium))
                .foregroundStyle(DS.textSecondaryReadable)

            Text("Which of these would you check?")
                .font(.title2.weight(.bold))
                .foregroundStyle(DS.textPrimary)

            HStack(spacing: 10) {
                ProgressView()
                Text("Loading live cards\u{2026}")
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondaryReadable)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(DS.border, lineWidth: 1))
        }
    }

    private var pairsErrorView: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Three quick picks, then you\u{2019}re in.")
                .font(.footnote.weight(.medium))
                .foregroundStyle(DS.textSecondaryReadable)

            Text("Which of these would you check?")
                .font(.title2.weight(.bold))
                .foregroundStyle(DS.textPrimary)

            VStack(alignment: .leading, spacing: 10) {
                Text("Couldn\u{2019}t load live cards right now.")
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                Text("Check your connection to retry, or skip straight to picking cities, schools, and subjects.")
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 10) {
                    Button {
                        Task { await vm.loadLivePairsIfNeeded(forceReload: true) }
                    } label: {
                        Text("Try again")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(solidAccentButtonForeground)
                            .padding(.horizontal, 16)
                            .frame(minHeight: 40)
                            .background(DS.blueReadable, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("firstRunPairsRetryButton")

                    Button {
                        vm.skipCurrentStep(
                            followManager: followManager,
                            pinManager: pinManager,
                            authManager: authManager,
                            onDismiss: finishAndDismiss
                        )
                    } label: {
                        Text("Skip")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textPrimary)
                            .padding(.horizontal, 14)
                            .frame(minHeight: 40)
                            .background(DS.trackBg, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("firstRunSkipButton")
                }
                .padding(.top, 4)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(DS.border, lineWidth: 1))
            .accessibilityIdentifier("firstRunPairsFailureCard")
        }
    }

    // MARK: - Screens 2A..2C: Two-Card Pair Comparison (Cards ARE the Buttons)

    private func pairContent(_ pair: FirstRunPair212A, index: Int) -> some View {
        let selectedSet = vm.selectedSidesForStep(index)
        return VStack(alignment: .leading, spacing: 12) {
            if let pill = pair.arrivedContextPill {
                Text(pill)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.blueReadable)
                    .padding(.horizontal, 11)
                    .padding(.vertical, 6)
                    .background(DS.blueReadable.opacity(colorScheme == .dark ? 0.18 : 0.10), in: Capsule())
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("firstRunArrivedPill")
            }

            if index == 0 {
                Text("Three quick picks, then you\u{2019}re in.")
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("firstRunLengthHint")
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(pair.promptTitle)
                    .font(.title2.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                Text("Your picks decide what Discover shows first.")
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)

                Text("Tap any you\u{2019}d check. Both or neither is fine.")
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(DS.blueReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }

            pairCard(
                pair.topCard,
                selected: selectedSet.contains(.top),
                onMeaningTap: pair.topCard.workedMeaningLine != nil ? { showAboutWorkedExample = true } : nil
            ) {
                vm.toggleCard(.top, forPairIndex: index)
            }

            pairCard(
                pair.bottomCard,
                selected: selectedSet.contains(.bottom),
                onMeaningTap: nil
            ) {
                vm.toggleCard(.bottom, forPairIndex: index)
            }
        }
    }

    private func pairCard(
        _ card: FirstRunCard212A,
        selected: Bool,
        onMeaningTap: (() -> Void)?,
        onTapCard: @escaping () -> Void
    ) -> some View {
        let accent = Color(hex: MyStuffTeamTextColour.probabilityHex(card.accentHex, colorScheme: colorScheme))
        return VStack(alignment: .leading, spacing: 10) {
            Button(action: onTapCard) {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .center, spacing: 8) {
                        if let kicker = card.kicker, !kicker.isEmpty {
                            Text(kicker)
                                .font(.caption2.weight(.bold))
                                .tracking(0.5)
                                .foregroundStyle(accent)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(accent.opacity(colorScheme == .dark ? 0.18 : 0.10), in: Capsule())
                                .fixedSize(horizontal: false, vertical: true)
                        }

                        Spacer(minLength: 4)

                        if let shift = FirstRunCard212A.shiftText(points: card.deltaPoints) {
                            Text(shift)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle((card.deltaPoints ?? 0) >= 0 ? DS.greenReadable : DS.danger)
                                .fixedSize(horizontal: false, vertical: true)
                        } else if let right = card.subtitleRight {
                            Text(right)
                                .font(.caption2.weight(.medium))
                                .foregroundStyle(DS.textSecondaryReadable)
                                .fixedSize(horizontal: false, vertical: true)
                        }

                        Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                            .font(.title3.weight(.semibold))
                            .foregroundStyle(selected ? DS.blueReadable : DS.textMuted)
                            .accessibilityHidden(true)
                    }

                    HStack(alignment: .center, spacing: 12) {
                        cardAvatar(card, tint: accent)

                        VStack(alignment: .leading, spacing: 3) {
                            Text(card.title)
                                .font(.headline.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)

                            if let detail = card.detailLine, !detail.isEmpty {
                                Text(detail)
                                    .font(.caption)
                                    .foregroundStyle(DS.textSecondaryReadable)
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }

                        Spacer(minLength: 8)

                        VStack(alignment: .trailing, spacing: 1) {
                            Text("\(card.percent)%")
                                .font(.title2.weight(.heavy).monospacedDigit())
                                .foregroundStyle(accent)
                                .lineLimit(1)
                                .fixedSize(horizontal: true, vertical: false)
                            Text(card.percentLabel)
                                .font(.caption2)
                                .foregroundStyle(DS.textSecondaryReadable)
                                .lineLimit(1)
                        }
                    }

                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule()
                                .fill(DS.trackBg)
                            Capsule()
                                .fill(accent)
                                .frame(width: max(6, geo.size.width * CGFloat(card.percent) / 100.0))
                        }
                    }
                    .frame(height: 5)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityAddTraits(.isButton)
            .accessibilityValue(selected ? "Selected" : "Not selected")

            if let meaning = card.workedMeaningLine {
                Divider()
                HStack(spacing: 6) {
                    Text(meaning)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 4)
                    if let onMeaningTap {
                        Button("Why?", action: onMeaningTap)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.blueReadable)
                    }
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            selected ? DS.blueReadable.opacity(colorScheme == .dark ? 0.16 : 0.07) : DS.cardBg,
            in: RoundedRectangle(cornerRadius: 16, style: .continuous)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(selected ? DS.blueReadable : DS.border, lineWidth: selected ? 2.5 : 1)
        )
        .accessibilityIdentifier("firstRunPairCard.\(card.id)")
    }

    @ViewBuilder
    private func cardAvatar(_ card: FirstRunCard212A, tint: Color) -> some View {
        if let url = card.logoUrl, !url.isEmpty {
            TeamLogoView(url: url, teamName: card.title, color: tint, size: 36)
        } else {
            Image(systemName: card.sfSymbol)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: 36, height: 36)
                .background(tint.opacity(colorScheme == .dark ? 0.22 : 0.12), in: Circle())
        }
    }

    private var pairFooter: some View {
        let hasSelection = !vm.selectedSidesForStep(vm.stepIndex).isEmpty
        return VStack(spacing: 0) {
            Divider()
            Button {
                vm.advanceFromCurrentPair(followManager: followManager, pinManager: pinManager)
            } label: {
                Text(hasSelection ? "Next" : "Neither, next")
                    .font(.headline)
                    .foregroundStyle(solidAccentButtonForeground)
                    .frame(maxWidth: .infinity, minHeight: 50)
                    .background(
                        DS.blueReadable,
                        in: RoundedRectangle(cornerRadius: 14, style: .continuous)
                    )
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .accessibilityIdentifier("firstRunPairNextButton")
        }
        .background(DS.surface)
    }

    // MARK: - Screen 2D: Unified Search, Served Examples & 359: A Sentence Confirmation

    private var visiblePickedTrayItems: [FirstRunSuggestion212A] {
        guard case .chips(let sentenceChips, _, _) = vm.sentenceState else {
            return vm.pickedItems
        }
        let sentenceSuggestionIds = Set(sentenceChips.map(\.suggestion.id))
        return vm.pickedItems.filter { !sentenceSuggestionIds.contains($0.id) }
    }

    private var typeaheadContent: some View {
        let dupNames = duplicateNamesInContext
        return VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Any cities, schools or subjects you care about?")
                    .font(.title2.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("firstRunTypeaheadTitle")

                Text("We\u{2019}ll put these first in Discover and My Stuff.")
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("firstRunTypeaheadReason")

                if let summary = vm.pairChangeSummaryLine {
                    HStack(spacing: 6) {
                        Image(systemName: "sparkles")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.blueReadable)
                        Text(summary)
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(DS.blueReadable)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.top, 2)
                    .accessibilityIdentifier("firstRunPairSummaryLine")
                }
            }

            if !visiblePickedTrayItems.isEmpty {
                FirstRunPickedChipFlow212A(spacing: 8) {
                    ForEach(visiblePickedTrayItems) { picked in
                        pickedChipView(
                            picked,
                            forceSportLabel: dupNames.contains(picked.name)
                                || picked.sportOrCategoryLabel.contains("NCAA")
                        )
                    }
                }
                .accessibilityIdentifier("firstRunPickedChips")
            }

            searchBox

            if vm.searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
               !vm.servedExamples.isEmpty {
                servedExamplesStrip
            }

            sentenceStateSection

            if vm.isSearching && vm.suggestions.isEmpty {
                HStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    Text("Looking up teams and topics")
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondaryReadable)
                }
                .padding(.vertical, 8)
            } else if !vm.suggestions.isEmpty {
                VStack(spacing: 0) {
                    ForEach(Array(vm.suggestions.enumerated()), id: \.element.id) { idx, item in
                        suggestionRow(item, isPicked: vm.isPicked(item))
                        if idx < vm.suggestions.count - 1 {
                            Divider()
                                .padding(.leading, 52)
                        }
                    }
                }
                .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(DS.border, lineWidth: 1)
                )
                .accessibilityIdentifier("firstRunSuggestionsList")
            } else if vm.searchCompletedOnce,
                      !vm.searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                      case .idle = vm.sentenceState {
                Text("No matches yet \u{2014} try another city, school, team, or subject.")
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var searchBox: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.subheadline)
                .foregroundStyle(DS.textSecondaryReadable)

            TextField("Type a city, school, team, or subject", text: $vm.searchQuery, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...3)
                .autocorrectionDisabled()
                #if os(iOS)
                .textInputAutocapitalization(.never)
                #endif
                .onChange(of: vm.searchQuery) { _, _ in
                    vm.onQueryChange(followManager: followManager)
                }
                .accessibilityIdentifier("firstRunSearchField")

            if vm.isSearching {
                ProgressView()
                    .controlSize(.small)
            } else if !vm.searchQuery.isEmpty {
                Button {
                    vm.searchQuery = ""
                    vm.onQueryChange(followManager: followManager)
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondaryReadable)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Clear search")
                .accessibilityIdentifier("firstRunSearchClear")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 12)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(DS.blueReadable.opacity(colorScheme == .dark ? 0.55 : 0.45), lineWidth: 1.5)
        )
    }

    private var servedExamplesStrip: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Try:")
                .font(.caption)
                .foregroundStyle(DS.textSecondaryReadable)
            FirstRunPickedChipFlow212A(spacing: 8) {
                ForEach(Array(vm.servedExamples.prefix(5))) { ex in
                    Button {
                        vm.applyExampleQuery(ex.query)
                    } label: {
                        Text(ex.displayText)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.blueReadable)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(DS.cardBg, in: Capsule())
                            .overlay(Capsule().stroke(DS.border, lineWidth: 1))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("firstRunExampleStatic.\(ex.id)")
                }
            }
        }
        .accessibilityIdentifier("firstRunExamplesStatic")
    }

    // MARK: - 359: A Sentence Confirmation / Waiting / Could-Not-Read States

    @ViewBuilder
    private var sentenceStateSection: some View {
        switch vm.sentenceState {
        case .idle:
            EmptyView()

        case .waiting:
            HStack(spacing: 10) {
                ProgressView()
                    .controlSize(.small)
                Text("Reading your note\u{2026}")
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(DS.border, lineWidth: 1))
            .accessibilityIdentifier("firstRunSentenceWaiting")

        case .chips(let chips, let selectedIds, let isSampleData):
            let clearChips = chips.filter { $0.ambiguityGroup == nil }
            let ambiguousGroups = Dictionary(grouping: chips.filter { $0.ambiguityGroup != nil }) {
                $0.ambiguityGroup ?? ""
            }
            let orderedGroups = ambiguousGroups.keys.sorted()

            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .center, spacing: 8) {
                    Text("Confirm your picks")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                    Spacer(minLength: 4)
                    if isSampleData {
                        Text(FirstRunSentenceSampleProvider359A.sampleBadgeText)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(DS.textSecondaryReadable)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(DS.trackBg, in: Capsule())
                    }
                }

                if !clearChips.isEmpty {
                    FirstRunPickedChipFlow212A(spacing: 8) {
                        ForEach(clearChips) { chip in
                            sentenceConfirmChip(
                                chip: chip,
                                isSelected: selectedIds.contains(chip.id),
                                ambiguous: false
                            )
                        }
                    }
                }

                ForEach(orderedGroups, id: \.self) { groupName in
                    if let groupChips = ambiguousGroups[groupName], !groupChips.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Which \u{201C}\(groupName)\u{201D} did you mean?")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(DS.textSecondaryReadable)

                            FirstRunPickedChipFlow212A(spacing: 8) {
                                ForEach(groupChips) { chip in
                                    sentenceConfirmChip(
                                        chip: chip,
                                        isSelected: selectedIds.contains(chip.id),
                                        ambiguous: true
                                    )
                                }
                            }
                        }
                    }
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(DS.border, lineWidth: 1))
            .accessibilityIdentifier("firstRunSentenceChipsCard")

        case .couldNotRead(let message):
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "text.magnifyingglass")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.blueReadable)
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(DS.amber.opacity(0.6), lineWidth: 1)
            )
            .accessibilityIdentifier("firstRunSentenceCouldNotRead")
        }
    }

    private func sentenceConfirmChip(
        chip: FirstRunSentenceChip359A,
        isSelected: Bool,
        ambiguous: Bool
    ) -> some View {
        Button {
            vm.toggleSentenceChip(chip, followManager: followManager, pinManager: pinManager)
        } label: {
            HStack(spacing: 6) {
                Image(systemName: isSelected ? "checkmark" : "plus")
                    .font(.caption2.weight(.bold))
                Text(chip.suggestion.chipDisplayText)
                    .font(.footnote.weight(.semibold))
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                if isSelected {
                    Image(systemName: "xmark")
                        .font(.caption2.weight(.bold))
                        .opacity(0.75)
                }
            }
            .foregroundStyle(isSelected ? (colorScheme == .dark ? Color(hex: "#0F172A") : .white) : DS.textPrimary)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                isSelected ? DS.textPrimary : DS.trackBg,
                in: RoundedRectangle(cornerRadius: 12, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(isSelected ? DS.textPrimary : (ambiguous ? DS.blueReadable.opacity(0.5) : DS.border), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("firstRunSentenceChip.\(chip.id)")
    }

    /// Wrapping full-name chip that never clips or truncates with `"..."` on `390pt` or `440pt`
    /// at default or AX5 text sizes (`#13517`).
    private func pickedChipView(_ item: FirstRunSuggestion212A, forceSportLabel: Bool) -> some View {
        let showSport = forceSportLabel || !item.sportOrCategoryLabel.isEmpty
        return Button {
            vm.toggleSuggestion(item, followManager: followManager, pinManager: pinManager)
        } label: {
            HStack(alignment: .center, spacing: 6) {
                if let url = item.logoUrl, !url.isEmpty {
                    TeamLogoView(url: url, teamName: item.name, color: DS.blueReadable, size: 18)
                }
                Text(showSport ? item.chipDisplayText : item.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(colorScheme == .dark ? Color(hex: "#0F172A") : .white)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Image(systemName: "xmark")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle((colorScheme == .dark ? Color(hex: "#0F172A") : .white).opacity(0.8))
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(DS.textPrimary, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("firstRunPickedChip.\(item.id)")
    }

    private func suggestionRow(_ item: FirstRunSuggestion212A, isPicked: Bool) -> some View {
        Button {
            vm.toggleSuggestion(item, followManager: followManager, pinManager: pinManager)
        } label: {
            Group {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(alignment: .top, spacing: 10) {
                            suggestionAvatar(item)
                            suggestionTextStack(item)
                        }
                        addOrAddedBadge(isPicked: isPicked)
                    }
                } else {
                    HStack(alignment: .center, spacing: 10) {
                        suggestionAvatar(item)
                        suggestionTextStack(item)
                        Spacer(minLength: 8)
                        addOrAddedBadge(isPicked: isPicked)
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("firstRunSuggestionRow.\(item.id)")
    }

    @ViewBuilder
    private func suggestionAvatar(_ item: FirstRunSuggestion212A) -> some View {
        if let url = item.logoUrl, !url.isEmpty {
            TeamLogoView(url: url, teamName: item.name, color: DS.blueReadable, size: 30)
        } else {
            let tint = Color(hex: MyStuffTeamTextColour.probabilityHex(item.primaryColorHex ?? "#005CC2", colorScheme: colorScheme))
            let icon = FirstRunCard212A.sfSymbol(
                forCategory: item.affinityCategory ?? item.sportOrCategoryLabel,
                isSports: item.sportKey != nil
            )
            Image(systemName: icon)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: 30, height: 30)
                .background(tint.opacity(colorScheme == .dark ? 0.22 : 0.12), in: Circle())
        }
    }

    private func suggestionTextStack(_ item: FirstRunSuggestion212A) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(item.name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)

            Text(item.rowSubtitleText)
                .font(.caption)
                .foregroundStyle(DS.textSecondaryReadable)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func addOrAddedBadge(isPicked: Bool) -> some View {
        HStack(spacing: 4) {
            Image(systemName: isPicked ? "checkmark" : "plus")
                .font(.caption2.weight(.bold))
            Text(isPicked ? "Added" : "Add")
                .font(.caption.weight(.bold))
        }
        .foregroundStyle(
            isPicked
                ? (colorScheme == .dark ? Color(hex: "#0F172A") : .white)
                : DS.blueReadable
        )
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(
            isPicked ? DS.textPrimary : DS.trackBg,
            in: Capsule()
        )
        .overlay(
            Capsule()
                .stroke(isPicked ? DS.textPrimary : DS.border, lineWidth: 1)
        )
    }

    private var typeaheadFooter: some View {
        let hasPicks = !vm.pickedItems.isEmpty
        return VStack(spacing: 0) {
            Divider()
            Button {
                if hasPicks {
                    vm.finish(
                        followManager: followManager,
                        pinManager: pinManager,
                        authManager: authManager
                    ) {
                        navCoordinator.selectedTab = .discover
                        dismiss()
                        onFinished?()
                    }
                } else {
                    vm.skipCurrentStep(
                        followManager: followManager,
                        pinManager: pinManager,
                        authManager: authManager,
                        onDismiss: finishAndDismiss
                    )
                }
            } label: {
                Text(hasPicks ? "Go to Discover \u{2192}" : "Skip to Discover")
                    .font(.headline)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .padding(.horizontal, 12)
                    .foregroundStyle(solidAccentButtonForeground)
                    .frame(maxWidth: .infinity, minHeight: 50)
                    .background(
                        DS.blueReadable,
                        in: RoundedRectangle(cornerRadius: 14, style: .continuous)
                    )
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .accessibilityIdentifier(hasPicks ? "firstRunGoToDiscoverButton" : "firstRunSkipButton")
        }
        .background(DS.surface)
    }

    private func finishAndDismiss() {
        UserDefaults.standard.set(true, forKey: FirstRunStorageKeys212A.onboardedKey)
        dismiss()
        onFinished?()
    }
}

/// Flow wrapping layout for picked-team and example chips so long names never clip
/// or collapse inside narrow `140pt` columns (`#13517`).
struct FirstRunPickedChipFlow212A: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) -> CGSize {
        let maxWidth = proposal.width ?? 358
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var usedWidth: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(ProposedViewSize(width: maxWidth, height: nil))
            if x > 0 && x + size.width > maxWidth {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            usedWidth = max(usedWidth, min(maxWidth, x + size.width))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
        return CGSize(width: maxWidth.isFinite ? maxWidth : usedWidth, height: y + rowHeight)
    }

    func placeSubviews(
        in bounds: CGRect,
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) {
        let maxWidth = bounds.width
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(ProposedViewSize(width: maxWidth, height: nil))
            if x > bounds.minX && x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(
                at: CGPoint(x: x, y: y),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: min(size.width, maxWidth), height: size.height)
            )
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
    }
}
