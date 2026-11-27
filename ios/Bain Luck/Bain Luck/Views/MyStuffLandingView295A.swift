import SwiftUI

// MARK: - Ruling 295: A — My Stuff Landing View (#11934)
//
// Strict section order:
// 1. Live now
// 2. Next for you
// 3. Moved since your last visit
// 4. From Discover (2–3 cards + link to all of Discover)
//
// Zero model-written text in 1.0.8.

/// #13770 part 2: Keep My Stuff rows readable on iPad without stretching full screen width.
nonisolated enum MyStuffLandingLayout13770 {
    static let singleColumnMaxWidth: CGFloat = 560
    static let multiColumnMaxWidth: CGFloat = 880
    static let cardSpacing: CGFloat = 12
    static let twoColumnMinimumWidth: CGFloat = 700

    static func columnCount(
        availableWidth: CGFloat,
        itemCount: Int,
        isAccessibilitySize: Bool
    ) -> Int {
        guard !isAccessibilitySize,
              itemCount >= 2,
              availableWidth >= twoColumnMinimumWidth else {
            return 1
        }
        return 2
    }

    static func containerMaxWidth(
        availableWidth: CGFloat,
        hasMultiItemSection: Bool,
        isAccessibilitySize: Bool
    ) -> CGFloat {
        let cols = columnCount(
            availableWidth: availableWidth,
            itemCount: hasMultiItemSection ? 2 : 1,
            isAccessibilitySize: isAccessibilitySize
        )
        return cols >= 2 ? multiColumnMaxWidth : singleColumnMaxWidth
    }
}

struct MyStuffLandingView295A: View {
    @ObservedObject var landingVM: MyStuffLandingViewModel295A
    @Binding var path: NavigationPath
    let onOpenDiscover: () -> Void
    let onManagePins: () -> Void
    let onRefresh: () async -> Void
    var onRetryTeamFutures: (() async -> Void)? = nil
    var showsEarnedSignIn212A: Bool = false
    var onAppleSignIn212A: () -> Void = {}
    var onGoogleSignIn212A: () -> Void = {}
    var showsChecklistBanner364A: Bool = false
    var onOpenChecklistRow364A: (FirstRunChecklistRowID364A) -> Void = { _ in }

    @Environment(\.followManager295A) private var followManager
    @EnvironmentObject private var pinManager: PinManager
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        MyStuffLandingBody295A(
            landingVM: landingVM,
            followManager: followManager,
            pinManager: pinManager,
            path: $path,
            onOpenDiscover: onOpenDiscover,
            onManagePins: onManagePins,
            onRefresh: onRefresh,
            onRetryTeamFutures: onRetryTeamFutures,
            showsEarnedSignIn212A: showsEarnedSignIn212A,
            onAppleSignIn212A: onAppleSignIn212A,
            onGoogleSignIn212A: onGoogleSignIn212A,
            showsChecklistBanner364A: showsChecklistBanner364A,
            onOpenChecklistRow364A: onOpenChecklistRow364A
        )
    }
}

private struct MyStuffLandingBody295A: View {
    @ObservedObject var landingVM: MyStuffLandingViewModel295A
    @ObservedObject var followManager: FollowManager295A
    @ObservedObject var pinManager: PinManager
    @Binding var path: NavigationPath
    let onOpenDiscover: () -> Void
    let onManagePins: () -> Void
    let onRefresh: () async -> Void
    let onRetryTeamFutures: (() async -> Void)?
    var showsEarnedSignIn212A: Bool = false
    var onAppleSignIn212A: () -> Void = {}
    var onGoogleSignIn212A: () -> Void = {}
    var showsChecklistBanner364A: Bool = false
    var onOpenChecklistRow364A: (FirstRunChecklistRowID364A) -> Void = { _ in }

    @AppStorage(FirstRunStorageKeys212A.earnedSignInDismissedKey) private var earnedSignInDismissed = false
    @State private var measuredWidth: CGFloat = 0
    @Environment(\.firstRunChecklistStore364A) private var checklistStore
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    private var effectiveCanvasWidth: CGFloat {
        if measuredWidth > 0 { return measuredWidth }
        return horizontalSizeClass == .regular ? 834 : 390
    }

    private var hasAnyMultiItemSection: Bool {
        landingVM.liveEvents.count >= 2
            || (landingVM.nextEvents.count + landingVM.nextMarkets.count) >= 2
            || landingVM.movedEntries.count >= 2
            || landingVM.discoverItems.count >= 2
    }

    private var containerMaxWidth: CGFloat {
        MyStuffLandingLayout13770.containerMaxWidth(
            availableWidth: effectiveCanvasWidth,
            hasMultiItemSection: hasAnyMultiItemSection,
            isAccessibilitySize: dynamicTypeSize.isAccessibilitySize
        )
    }

    private var cardSurface: Color {
        colorScheme == .dark ? Color.cardBackground : DS.cardBg
    }

    private var cardBorder: Color {
        colorScheme == .dark ? HeadlineStyleTable199.cardBorderInk : DS.border
    }

    private var liveSectionTitle: String {
        let hasSuspended = landingVM.liveEvents.contains { EventState.isSuspended($0.event.status) }
        return hasSuspended ? EventState.liveSectionTitle(hasSuspended: true) : "Live now"
    }

    var body: some View {
        let checklistBinding = Binding<FirstRunChecklistState364A>(
            get: { checklistStore.state },
            set: { checklistStore.state = $0 }
        )
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 20) {
                SiriProbabilityTip12315(horizontalPadding: 0)
                if showsChecklistBanner364A && checklistStore.state.showsInMyStuff {
                    MyStuffChecklistBanner364A(
                        state: checklistBinding,
                        onOpenRow: onOpenChecklistRow364A,
                        onDismiss: { checklistStore.dismissFromMyStuff() }
                    )
                }
                followingAndPinsStrip

                if landingVM.loading
                    && landingVM.liveEvents.isEmpty
                    && landingVM.nextEvents.isEmpty
                    && landingVM.nextMarkets.isEmpty
                    && landingVM.movedEntries.isEmpty
                    && landingVM.discoverItems.isEmpty {
                    ProgressView("Loading your stuff")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 32)
                } else if landingVM.hydratingRemainingCount > 0 {
                    HStack(spacing: 8) {
                        ProgressView()
                            .controlSize(.small)
                        Text("Updating your stuff")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer(minLength: 0)
                    }
                    .accessibilityIdentifier("myStuff295A.hydratingInline")
                }

                if landingVM.loadFailed && !landingVM.loading {
                    HStack(spacing: 12) {
                        Image(systemName: "wifi.exclamationmark")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.secondary)
                        Text("Couldn't load your stuff.")
                            .font(.subheadline)
                            .foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 8)
                        Button {
                            Task { await onRefresh() }
                        } label: {
                            Text("Try again")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
                                .padding(.horizontal, 12)
                                .frame(minHeight: 44)
                                .background(
                                    Capsule()
                                        .fill((colorScheme == .dark ? DS.emerald : DS.greenReadable).opacity(0.12))
                                )
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("myStuff295A.retryLoad")
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
                    .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(cardSurface))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .stroke(cardBorder, lineWidth: 1)
                    )
                    .accessibilityIdentifier("myStuff295A.loadErrorBanner")
                    .noteReviewPromptTrouble12304()
                }

                if !landingVM.loadFailed && landingVM.teamFuturesFailed && !landingVM.loading {
                    HStack(alignment: .center, spacing: 12) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.orange)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Couldn't load your teams' futures")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(.primary)
                                .fixedSize(horizontal: false, vertical: true)
                            Text("Your teams are still saved. This part didn't load.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 8)
                        Button {
                            Task { await (onRetryTeamFutures ?? onRefresh)() }
                        } label: {
                            Group {
                                if landingVM.teamFuturesRetrying {
                                    ProgressView()
                                        .controlSize(.small)
                                } else {
                                    Text("Try again")
                                        .font(.subheadline.weight(.semibold))
                                }
                            }
                            .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
                            .padding(.horizontal, 12)
                            .frame(minHeight: 44)
                            .background(
                                Capsule()
                                    .fill((colorScheme == .dark ? DS.emerald : DS.greenReadable).opacity(0.12))
                            )
                        }
                        .buttonStyle(.plain)
                        .disabled(landingVM.teamFuturesRetrying)
                        .accessibilityIdentifier("myStuff295A.retryTeamFutures")
                    }
                    .noteReviewPromptTrouble12304()
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
                    .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(cardSurface))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .stroke(cardBorder, lineWidth: 1)
                    )
                    .accessibilityIdentifier("myStuff295A.teamFuturesErrorBanner")
                }

                // 1. Live now
                if !landingVM.liveEvents.isEmpty {
                    sectionMasonryBlock(
                        title: liveSectionTitle,
                        systemImage: "circle.fill",
                        tint: .red,
                        count: landingVM.liveEvents.count,
                        identifier: "myStuff295A.section.liveNow",
                        items: landingVM.liveEvents.map(\.self)
                    ) { pair in
                        eventCardButton(pair.event, awayVerified: pair.awayVerified)
                    }
                }

                // 2. Next for you
                let nextEntries: [NextSectionEntry13770] =
                    landingVM.nextEvents.map { .event($0.event, awayVerified: $0.awayVerified) }
                    + landingVM.nextMarkets.map { .market($0) }
                if !nextEntries.isEmpty {
                    sectionMasonryBlock(
                        title: "Next for you",
                        systemImage: "calendar",
                        tint: .blue,
                        count: nextEntries.count,
                        identifier: "myStuff295A.section.nextForYou",
                        items: nextEntries
                    ) { entry in
                        switch entry {
                        case .event(let event, let awayVerified):
                            eventCardButton(event, awayVerified: awayVerified)
                        case .market(let market):
                            marketCardButton(market)
                        }
                    }
                }

                // 3. Moved since your last visit
                if !landingVM.movedEntries.isEmpty {
                    sectionMasonryBlock(
                        title: "Moved since your last visit",
                        systemImage: "arrow.up.right.circle.fill",
                        tint: colorScheme == .dark ? DS.emerald : DS.greenReadable,
                        count: landingVM.movedEntries.count,
                        identifier: "myStuff295A.section.moved",
                        items: landingVM.movedEntries
                    ) { entry in
                        movedEntryCard(entry)
                    }
                }

                // 4. From Discover (2–3 cards + link to all of it)
                if !landingVM.discoverItems.isEmpty {
                    sectionBlock(
                        title: "From Discover",
                        systemImage: "safari",
                        tint: .secondary,
                        count: nil,
                        identifier: "myStuff295A.section.fromDiscover"
                    ) {
                        masonryCards(items: landingVM.discoverItems) { item in
                            discoverPreviewCard(item)
                        }

                        Button(action: onOpenDiscover) {
                            HStack(spacing: 8) {
                                Text("See all on Discover")
                                    .font(.subheadline.weight(.semibold))
                                Spacer(minLength: 8)
                                Image(systemName: "arrow.right")
                                    .font(.subheadline.weight(.semibold))
                            }
                            .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
                            .padding(.horizontal, 16)
                            .frame(maxWidth: .infinity, minHeight: 48)
                            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(cardSurface))
                            .overlay(
                                RoundedRectangle(cornerRadius: 12, style: .continuous)
                                    .stroke(cardBorder, lineWidth: 1)
                            )
                            .contentShape(Rectangle())
                        }
                        .frame(maxWidth: MyStuffLandingLayout13770.singleColumnMaxWidth)
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("myStuff295A.openAllDiscover")
                    }
                } else {
                    Button(action: onOpenDiscover) {
                        HStack(spacing: 8) {
                            Label("See all on Discover", systemImage: "safari")
                                .font(.subheadline.weight(.semibold))
                            Spacer(minLength: 8)
                            Image(systemName: "arrow.right")
                                .font(.subheadline.weight(.semibold))
                        }
                        .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
                        .padding(.horizontal, 16)
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(cardSurface))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(cardBorder, lineWidth: 1)
                        )
                    }
                    .frame(maxWidth: MyStuffLandingLayout13770.singleColumnMaxWidth)
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("myStuff295A.openAllDiscover")
                }

                if showsEarnedSignIn212A && !earnedSignInDismissed && (!followManager.subjects.isEmpty || !pinManager.savedPins.isEmpty) {
                    EarnedSignInCard212A(
                        onAppleSignIn: onAppleSignIn212A,
                        onGoogleSignIn: onGoogleSignIn212A,
                        onDismissLocalOnly: { earnedSignInDismissed = true }
                    )
                    .frame(maxWidth: MyStuffLandingLayout13770.singleColumnMaxWidth)
                }

                NavigationLink(value: Route.about) {
                    HStack {
                        Label("About Bain Luck", systemImage: "info.circle")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.tertiary)
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
                    .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(cardSurface))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(cardBorder, lineWidth: 1))
                }
                .frame(maxWidth: MyStuffLandingLayout13770.singleColumnMaxWidth)
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .padding(.bottom, 48)
            .frame(maxWidth: containerMaxWidth)
            .frame(maxWidth: .infinity)
        }
        .background(
            GeometryReader { geo in
                Color.clear
                    .onAppear { measuredWidth = geo.size.width }
                    .onChange(of: geo.size.width) { _, w in measuredWidth = w }
            }
        )
        .background(colorScheme == .dark ? Color.groupedBackground : DS.surface)
        .refreshable {
            await onRefresh()
        }
    }

    // MARK: - Top Following + Pins Strip

    @ViewBuilder
    private var followingAndPinsStrip: some View {
        if !followManager.subjects.isEmpty || !pinManager.savedPins.isEmpty {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    followingAndPinsStripItems(fullWidthWrapping: true)
                }
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        followingAndPinsStripItems(fullWidthWrapping: false)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func followingAndPinsStripItems(fullWidthWrapping: Bool) -> some View {
        ForEach(followManager.subjects) { subject in
            Button {
                path.append(subject.route)
            } label: {
                HStack(alignment: fullWidthWrapping ? .firstTextBaseline : .center, spacing: 6) {
                    if subject.kind == .team {
                        TeamLogoView(
                            url: subject.logoUrl,
                            teamName: subject.name,
                            color: Color(hex: MyStuffTeamTextColour.logoTintHex(subject.primaryColor)),
                            size: 18,
                            sportKey: subject.sportKey
                        )
                    } else if subject.kind == .subject {
                        ChecklistThumbnail364A(
                            urlString: subject.logoUrl,
                            sfSymbol: FirstRunCard212A.sfSymbol(
                                forCategory: subject.affinityCategory ?? subject.slug,
                                isSports: false
                            ),
                            accentHex: subject.primaryColor ?? "#005CC2",
                            size: 18
                        )
                    } else {
                        Image(systemName: subject.kind == .league ? "trophy.fill" : "square.stack.3d.up.fill")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(.secondary)
                    }
                    Text(subject.name)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.primary)
                        .lineLimit(fullWidthWrapping ? nil : 1)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, fullWidthWrapping ? 8 : 0)
                .frame(maxWidth: fullWidthWrapping ? .infinity : nil, minHeight: 36, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: fullWidthWrapping ? 16 : 18).fill(cardSurface))
                .overlay(RoundedRectangle(cornerRadius: fullWidthWrapping ? 16 : 18).stroke(cardBorder, lineWidth: 1))
            }
            .buttonStyle(.plain)
        }

        if !pinManager.savedPins.isEmpty {
            Button(action: onManagePins) {
                HStack(spacing: 5) {
                    Image(systemName: "bookmark.fill")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.orange)
                    Text("\(pinManager.savedPins.count) pinned")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.primary)
                        .lineLimit(fullWidthWrapping ? nil : 1)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, fullWidthWrapping ? 8 : 0)
                .frame(maxWidth: fullWidthWrapping ? .infinity : nil, minHeight: 36, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: fullWidthWrapping ? 16 : 18).fill(cardSurface))
                .overlay(RoundedRectangle(cornerRadius: fullWidthWrapping ? 16 : 18).stroke(cardBorder, lineWidth: 1))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("myStuffManagePins")
        }
    }

    // MARK: - Section Wrapper

    private enum NextSectionEntry13770 {
        case event(FeedEventData, awayVerified: Bool)
        case market(MyStuffMarketItem295A)
    }

    private func sectionMasonryBlock<Item, RowContent: View>(
        title: String,
        systemImage: String,
        tint: Color,
        count: Int?,
        identifier: String,
        items: [Item],
        @ViewBuilder rowContent: @escaping (Item) -> RowContent
    ) -> some View {
        sectionBlock(
            title: title,
            systemImage: systemImage,
            tint: tint,
            count: count,
            identifier: identifier
        ) {
            masonryCards(items: items, rowContent: rowContent)
        }
    }

    @ViewBuilder
    private func masonryCards<Item, RowContent: View>(
        items: [Item],
        @ViewBuilder rowContent: @escaping (Item) -> RowContent
    ) -> some View {
        let cols = MyStuffLandingLayout13770.columnCount(
            availableWidth: effectiveCanvasWidth,
            itemCount: items.count,
            isAccessibilitySize: dynamicTypeSize.isAccessibilitySize
        )
        if cols >= 2 {
            let columns = DiscoverMasonry.columns(cardCount: items.count, columnCount: cols)
            HStack(alignment: .top, spacing: MyStuffLandingLayout13770.cardSpacing) {
                ForEach(Array(columns.enumerated()), id: \.offset) { _, indices in
                    VStack(spacing: MyStuffLandingLayout13770.cardSpacing) {
                        ForEach(indices, id: \.self) { idx in
                            rowContent(items[idx])
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
            }
        } else {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    rowContent(item)
                        .frame(maxWidth: MyStuffLandingLayout13770.singleColumnMaxWidth, alignment: .leading)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func sectionBlock<Content: View>(
        title: String,
        systemImage: String,
        tint: Color,
        count: Int?,
        identifier: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: systemImage)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(tint)
                Text(title)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)
                if let count {
                    Text("\(count)")
                        .font(.caption2.weight(.semibold).monospacedDigit())
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(Color.primary.opacity(0.08)))
                }
                Spacer(minLength: 0)
            }
            .accessibilityIdentifier(identifier)

            VStack(alignment: .leading, spacing: 10) {
                content()
            }
        }
    }

    // MARK: - Cards (Deterministic Only — Zero Model-Written Text)

    private func eventCardButton(_ event: FeedEventData, awayVerified: Bool) -> some View {
        Button {
            path.append(Route.eventDetail(id: event.id))
        } label: {
            EventCardView(
                event: event,
                reason: nil,
                personalizationReasons: nil,
                headline: nil,
                awayReadingIsServerVerified: awayVerified
            )
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(cardSurface))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(cardBorder, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private func marketCardButton(_ market: MyStuffMarketItem295A, movementBanner: String? = nil) -> some View {
        Button {
            path.append(Route.futuresDetail(id: market.marketId))
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                if let movementBanner {
                    Text(movementBanner)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
                        .fixedSize(horizontal: false, vertical: true)
                }

                HStack(alignment: .center, spacing: 10) {
                    if market.logoUrl != nil || market.subjectName != nil {
                        TeamLogoView(
                            url: market.logoUrl,
                            teamName: market.subjectName ?? market.outcomeLabel,
                            color: Color(hex: MyStuffTeamTextColour.logoTintHex(market.primaryColor)),
                            size: 28
                        )
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text(market.outcomeLabel)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(market.marketTitle)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    Spacer(minLength: 8)

                    HStack(spacing: 4) {
                        Text(formatProbability(market.probability))
                            .font(.title3.weight(.bold).monospacedDigit())
                            .foregroundStyle(
                                market.primaryColor != nil
                                    ? Color(hex: MyStuffTeamTextColour.probabilityHex(market.primaryColor))
                                    : .primary
                            )
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)

                        if let mark = SourceMarkButton(
                            market.sourceMark,
                            number: market.probability,
                            subject: market.outcomeLabel,
                            subtitle: market.marketTitle,
                            numberSize: 16,
                            compactRow: true
                        ) {
                            mark.buttonStyle(.borderless)
                        }
                    }

                    PinButton(type: "future", id: market.marketId, compact: true)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(cardSurface))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(cardBorder, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func movedEntryCard(_ entry: MyStuffMovedEntry295A) -> some View {
        switch entry.payload {
        case .event(let event, let awayVerified):
            Button {
                path.append(Route.eventDetail(id: event.id))
            } label: {
                VStack(alignment: .leading, spacing: 6) {
                    Text(entry.movementSummary)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
                        .fixedSize(horizontal: false, vertical: true)

                    EventCardView(
                        event: event,
                        reason: nil,
                        personalizationReasons: nil,
                        headline: nil,
                        awayReadingIsServerVerified: awayVerified
                    )
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(cardSurface))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(cardBorder, lineWidth: 1))
            }
            .buttonStyle(.plain)

        case .market(let market):
            marketCardButton(market, movementBanner: entry.movementSummary)
        }
    }

    @ViewBuilder
    private func discoverPreviewCard(_ item: FeedItem) -> some View {
        if let event = item.event {
            eventCardButton(event, awayVerified: false)
        } else if let futures = item.futures {
            Button {
                path.append(Route.futuresDetail(id: futures.id))
            } label: {
                FuturesCardView(futures: futures)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(cardSurface))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(cardBorder, lineWidth: 1))
            }
            .buttonStyle(.plain)
        }
    }
}
