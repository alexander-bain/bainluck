import SwiftUI

// MARK: - Ruling 212-A First-Run Flow (#11934, #13517)

/// Full approved 212-A first-run flow replacing the old carousel & 5-step sports quiz:
/// - Screens `2A..2C`: three pairs of real cards (mixing sports and non-sports), single-tap instant
///   selection feedback, plain-English meaning line on Pair 1, and `Skip` on every screen.
/// - Screen `2D`: `"Any cities, schools or subjects you care about?"` unified typeahead where
///   first tap selects immediately, search box & results stay on screen so picking a second team
///   is obvious without clearing, two teams from one school carry distinct sport labels everywhere,
///   and wrapping full-width rows + flow chips guarantee zero cut-off names at `390pt` / `440pt`,
///   both default and `accessibility5` (`#13517`).
struct FirstRunFlowView212A: View {
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
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
                        if let pair = vm.currentPair {
                            pairContent(pair, index: vm.stepIndex)
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

                if vm.isOnTypeaheadStep {
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

    // MARK: - Top Bar (Progress + Skip on Every Screen)

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

            HStack(spacing: 6) {
                ForEach(0..<vm.totalSteps, id: \.self) { idx in
                    Capsule()
                        .fill(
                            idx == vm.stepIndex
                                ? DS.blueReadable
                                : (idx < vm.stepIndex ? DS.blueReadable.opacity(0.45) : DS.border)
                        )
                        .frame(width: idx == vm.stepIndex ? 24 : 10, height: 5)
                        .animation(.easeInOut(duration: 0.2), value: vm.stepIndex)
                }
            }

            Spacer(minLength: 8)

            Button {
                vm.skipCurrentStep(
                    followManager: followManager,
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

    // MARK: - Screens 2A..2C: Two-Card Pair Comparison

    private func pairContent(_ pair: FirstRunPair212A, index: Int) -> some View {
        let choice = vm.selectedChoices[index]
        return VStack(alignment: .leading, spacing: 14) {
            if let pill = pair.arrivedContextPill {
                Text(pill)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.blueReadable)
                    .padding(.horizontal, 11)
                    .padding(.vertical, 6)
                    .background(DS.blueReadable.opacity(colorScheme == .dark ? 0.18 : 0.10), in: Capsule())
                    .fixedSize(horizontal: false, vertical: true)
            }

            Text(pair.promptTitle)
                .font(.title2.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            pairCard(
                pair.topCard,
                selected: choice == .top || choice == .both,
                onMeaningTap: pair.topCard.workedMeaningLine != nil ? { showAboutWorkedExample = true } : nil
            ) {
                vm.selectChoice(.top, forPairIndex: index, followManager: followManager)
            }

            HStack {
                VStack { Divider() }
                Text("OR")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .padding(.horizontal, 6)
                VStack { Divider() }
            }

            pairCard(pair.bottomCard, selected: choice == .bottom || choice == .both, onMeaningTap: nil) {
                vm.selectChoice(.bottom, forPairIndex: index, followManager: followManager)
            }

            pairActionButtons(pair: pair, index: index, currentChoice: choice)
                .padding(.top, 4)
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
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(card.kicker)
                            .font(.caption2.weight(.bold))
                            .tracking(0.5)
                            .foregroundStyle(accent)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(accent.opacity(colorScheme == .dark ? 0.18 : 0.10), in: Capsule())
                            .fixedSize(horizontal: false, vertical: true)

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
            selected ? DS.blueReadable.opacity(colorScheme == .dark ? 0.14 : 0.06) : DS.cardBg,
            in: RoundedRectangle(cornerRadius: 16, style: .continuous)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(selected ? DS.blueReadable : DS.border, lineWidth: selected ? 2 : 1)
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

    @ViewBuilder
    private func pairActionButtons(
        pair: FirstRunPair212A,
        index: Int,
        currentChoice: FirstRunChoice212A?
    ) -> some View {
        let buttons: [(choice: FirstRunChoice212A, label: String, id: String)] = [
            (.top, pair.topCard.choiceButtonLabel, "top"),
            (.bottom, pair.bottomCard.choiceButtonLabel, "bottom"),
            (.both, "Both of these", "both"),
            (.neither, "Neither", "neither"),
        ]

        if dynamicTypeSize.isAccessibilitySize {
            VStack(spacing: 10) {
                ForEach(buttons, id: \.id) { btn in
                    choiceButton(
                        label: btn.label,
                        selected: currentChoice == btn.choice,
                        identifier: "firstRunChoice.\(index).\(btn.id)"
                    ) {
                        vm.selectChoice(btn.choice, forPairIndex: index, followManager: followManager)
                    }
                }
            }
        } else {
            VStack(spacing: 10) {
                HStack(spacing: 10) {
                    choiceButton(
                        label: buttons[0].label,
                        selected: currentChoice == .top,
                        identifier: "firstRunChoice.\(index).top"
                    ) {
                        vm.selectChoice(.top, forPairIndex: index, followManager: followManager)
                    }
                    choiceButton(
                        label: buttons[1].label,
                        selected: currentChoice == .bottom,
                        identifier: "firstRunChoice.\(index).bottom"
                    ) {
                        vm.selectChoice(.bottom, forPairIndex: index, followManager: followManager)
                    }
                }
                HStack(spacing: 10) {
                    choiceButton(
                        label: buttons[2].label,
                        selected: currentChoice == .both,
                        identifier: "firstRunChoice.\(index).both"
                    ) {
                        vm.selectChoice(.both, forPairIndex: index, followManager: followManager)
                    }
                    choiceButton(
                        label: buttons[3].label,
                        selected: currentChoice == .neither,
                        identifier: "firstRunChoice.\(index).neither"
                    ) {
                        vm.selectChoice(.neither, forPairIndex: index, followManager: followManager)
                    }
                }
            }
        }
    }

    private func choiceButton(
        label: String,
        selected: Bool,
        identifier: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if selected {
                    Image(systemName: "checkmark")
                        .font(.caption.weight(.bold))
                }
                Text(label)
                    .font(.subheadline.weight(.semibold))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .foregroundStyle(
                selected
                    ? (colorScheme == .dark ? Color(hex: "#0F172A") : .white)
                    : DS.textPrimary
            )
            .padding(.horizontal, 12)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, minHeight: 46)
            .background(
                selected ? DS.textPrimary : DS.cardBg,
                in: RoundedRectangle(cornerRadius: 12, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(selected ? DS.textPrimary : DS.border, lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(identifier)
    }

    // MARK: - Screen 2D: Unified Typeahead (Zero Cut-off Team Names #13517)

    private var typeaheadContent: some View {
        let dupNames = duplicateNamesInContext
        return VStack(alignment: .leading, spacing: 14) {
            Text("Any cities, schools or subjects you care about?")
                .font(.title2.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("firstRunTypeaheadTitle")

            if !vm.pickedItems.isEmpty {
                FirstRunPickedChipFlow212A(spacing: 8) {
                    ForEach(vm.pickedItems) { picked in
                        pickedChipView(picked, forceSportLabel: dupNames.contains(picked.name) || picked.sportOrCategoryLabel.contains("NCAA"))
                    }
                }
                .accessibilityIdentifier("firstRunPickedChips")
            }

            searchBox

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
            } else if vm.searchCompletedOnce && !vm.searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Text("No matches yet \u{2014} try another city, school, team, or topic.")
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Popular right now")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondaryReadable)

                FirstRunPickedChipFlow212A(spacing: 8) {
                    ForEach(FirstRunSuggestion212A.popularQueries, id: \.self) { pill in
                        Button {
                            vm.applyPopularQuery(pill)
                        } label: {
                            Text(pill)
                                .font(.footnote.weight(.medium))
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 8)
                                .background(DS.cardBg, in: Capsule())
                                .overlay(Capsule().stroke(DS.border, lineWidth: 1))
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("firstRunPopular.\(pill)")
                    }
                }
            }
            .padding(.top, 2)
        }
    }

    private var searchBox: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.subheadline)
                .foregroundStyle(DS.textSecondaryReadable)

            TextField("Search cities, schools, teams, or subjects", text: $vm.searchQuery)
                .textFieldStyle(.plain)
                .autocorrectionDisabled()
                #if os(iOS)
                .textInputAutocapitalization(.never)
                #endif
                .onChange(of: vm.searchQuery) { _, _ in
                    vm.onQueryChange()
                }
                .accessibilityIdentifier("firstRunSearchField")

            if vm.isSearching {
                ProgressView()
                    .controlSize(.small)
            } else if !vm.searchQuery.isEmpty {
                Button {
                    vm.searchQuery = ""
                    vm.onQueryChange()
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

    /// Wrapping full-name chip that never clips or truncates with `"..."` on `390pt` or `440pt`
    /// at default or AX5 text sizes (`#13517`).
    private func pickedChipView(_ item: FirstRunSuggestion212A, forceSportLabel: Bool) -> some View {
        let showSport = forceSportLabel || !item.sportOrCategoryLabel.isEmpty
        return Button {
            vm.toggleSuggestion(item, followManager: followManager)
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
            vm.toggleSuggestion(item, followManager: followManager)
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
        VStack(spacing: 6) {
            Divider()
            Button {
                vm.finish(followManager: followManager, authManager: authManager) {
                    if !vm.pickedItems.isEmpty || !followManager.subjects.isEmpty {
                        navCoordinator.selectedTab = .myStuff
                    } else {
                        navCoordinator.selectedTab = .discover
                    }
                    dismiss()
                    onFinished?()
                }
            } label: {
                Text(!vm.pickedItems.isEmpty ? "Go to My Stuff \u{2192}" : "Go to Discover \u{2192}")
                    .font(.headline)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity, minHeight: 50)
                    .background(
                        DS.blueReadable,
                        in: RoundedRectangle(cornerRadius: 14, style: .continuous)
                    )
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
            .padding(.top, 10)
            .accessibilityIdentifier("firstRunGoToDiscoverButton")

            Button {
                vm.skipCurrentStep(
                    followManager: followManager,
                    authManager: authManager,
                    onDismiss: finishAndDismiss
                )
            } label: {
                Text("Skip for now")
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .frame(minHeight: 34)
            }
            .buttonStyle(.plain)
            .padding(.bottom, 8)
        }
        .background(DS.surface)
    }

    private func finishAndDismiss() {
        UserDefaults.standard.set(true, forKey: FirstRunStorageKeys212A.onboardedKey)
        dismiss()
        onFinished?()
    }
}

/// Flow wrapping layout for picked-team and popular-topic chips so long names never clip
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
