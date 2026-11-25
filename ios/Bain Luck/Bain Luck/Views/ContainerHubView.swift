import SwiftUI

private enum ContainerHubThemeTokens {
    static func surface(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color.groupedBackground : DS.surface
    }
    static func cardBg(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color.cardBackground : DS.cardBg
    }
    static func subtleBg(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color.groupedBackground : DS.surface
    }
    static func border(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? HeadlineStyleTable199.cardBorderInk : DS.border
    }
    static func textPrimary(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color.primary : DS.textPrimary
    }
    static func textSecondary(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? DS.textSecondaryReadable : DS.textSecondary
    }
}

/// #9652: the selected sensible-group treatment, using ordinary card routes.
/// It stays in its caller's NavigationStack, so Back reveals the same StateObject
/// and scroll binding rather than constructing a replacement hub.
struct ContainerHubView: View {
    let displayName: String
    @StateObject private var vm: ContainerHubViewModel
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.dismiss) private var dismiss

    private var hubSurface: Color { ContainerHubThemeTokens.surface(colorScheme) }
    private var hubCardBg: Color { ContainerHubThemeTokens.cardBg(colorScheme) }
    private var hubSubtleBg: Color { ContainerHubThemeTokens.subtleBg(colorScheme) }
    private var hubBorder: Color { ContainerHubThemeTokens.border(colorScheme) }
    private var hubTextPrimary: Color { ContainerHubThemeTokens.textPrimary(colorScheme) }
    private var hubTextSecondary: Color { ContainerHubThemeTokens.textSecondary(colorScheme) }

    init(slug: String, displayName: String, service: any ContainerHubLoading = ContainerHubService()) {
        self.displayName = displayName
        _vm = StateObject(wrappedValue: ContainerHubViewModel(slug: slug, service: service))
    }

    var body: some View {
        Group {
            switch vm.state {
            case .loading:
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            case .loaded(let presentation):
                hub(presentation)
            case .unavailable:
                status("We couldn’t find this collection, or it isn’t available right now.", retry: false)
            case .error(let message):
                status(message, retry: true)
            }
        }
        .background(hubSurface)
        .navigationTitle(effectiveNavigationTitle)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            if isPubliclyShareable {
                ToolbarItem(placement: .confirmationAction) {
                    ShareLink(
                        item: shareURL,
                        subject: Text(effectiveShareTitle)
                    ) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.system(size: 14))
                    }
                    .accessibilityLabel("Share")
                    .accessibilityIdentifier("hub.shareButton")
                    .recordsShareOpened { recordShareOpened() }
                }
            }
        }
        .task {
            // Returning revalidates publication/lifecycle while retaining the
            // existing view model and anchor. No new hub or loading skeleton.
            await vm.load()
            AnalyticsService.trackScreen(name: "collection_hub", type: vm.slug)
        }
    }

    static func shareLinkURL(slug: String) -> URL {
        URL(string: collectionShareURL(slug)) ?? bainLuckFallbackURL
    }

    private var shareURL: URL {
        Self.shareLinkURL(slug: vm.slug)
    }

    private var effectiveShareTitle: String {
        if case .loaded(let presentation) = vm.state,
           let title = presentation.title?.trimmingCharacters(in: .whitespacesAndNewlines),
           !title.isEmpty {
            return title
        }
        let trimmed = displayName.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "Bain Luck" : trimmed
    }

    private func recordShareOpened() {
        ShareInstrumentation.recordShareOpened(
            itemType: "collection",
            itemId: vm.slug,
            itemName: effectiveShareTitle,
            category: nil,
            surface: .collectionDetail
        )
    }

    private var isPubliclyShareable: Bool {
        guard case .loaded(let presentation) = vm.state,
              presentation.response.state == .published else {
            return false
        }
        return true
    }

    static func resolvedNavigationTitle(displayName: String, slug: String, loadedTitle: String?) -> String {
        if let loaded = loadedTitle?.trimmingCharacters(in: .whitespacesAndNewlines), !loaded.isEmpty {
            if loaded.count > 24 || (GroupingMachineryGate12288.isMachineryCandidateSlug(slug) && loaded.count > 28) {
                return ""
            }
            return loaded
        }
        let trimmed = displayName.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty || trimmed == "Collection" {
            return ""
        }
        if GroupingMachineryGate12288.isMachineryCandidateSlug(slug), trimmed.count > 28 {
            return ""
        }
        return trimmed
    }

    private var effectiveNavigationTitle: String {
        let loadedTitle: String?
        if case .loaded(let presentation) = vm.state {
            loadedTitle = presentation.title
        } else {
            loadedTitle = nil
        }
        return Self.resolvedNavigationTitle(displayName: displayName, slug: vm.slug, loadedTitle: loadedTitle)
    }

    private func hub(_ presentation: ContainerHubPresentation) -> some View {
        let setName = presentation.title ?? displayName
        let alertsContextId = "set-hub:\(vm.slug)"
        let followSubject = FollowedSubject295A.set(
            slug: vm.slug,
            setKind: .container,
            name: setName
        )
        return GeometryReader { proxy in
            let innerWidth = ContainerHubGridLayout13417.innerContentWidth(
                containerWidth: proxy.size.width
            )
            let hubColumnCount = ContainerHubGridLayout13417.columnCount(
                horizontalSizeClass: horizontalSizeClass,
                dynamicTypeSize: dynamicTypeSize,
                availableWidth: innerWidth
            )
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .center, spacing: 12) {
                            if let title = presentation.title {
                                Text(title)
                                    .font(.title2.weight(.bold))
                                    .foregroundStyle(hubTextPrimary)
                                    .lineLimit(1)
                                    .fixedSize(horizontal: true, vertical: true)
                            }
                            Spacer(minLength: 8)
                            FollowButton295A(subject: followSubject, pageContextId: alertsContextId)
                        }

                        VStack(alignment: .leading, spacing: 10) {
                            if let title = presentation.title {
                                Text(title)
                                    .font(.title2.weight(.bold))
                                    .foregroundStyle(hubTextPrimary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            FollowButton295A(subject: followSubject, pageContextId: alertsContextId)
                        }
                    }

                    GameAlertsInlinePageSlot295A(contextId: alertsContextId)
                    if let reasonLine = presentation.headerReasonLine {
                        Text(reasonLine)
                        .font(.subheadline)
                        .foregroundStyle(hubTextSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("hub.reasonLine")
                }
                if let note = presentation.note {
                    Text(note)
                        .font(.subheadline)
                        .foregroundStyle(hubTextSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if presentation.response.edition?.isTheme == true, presentation.isPartial {
                    Button("Retry unavailable markets") { Task { await vm.load() } }
                        .disabled(vm.isRefreshing)
                }
                if vm.refreshError != nil {
                    Text("Couldn’t refresh. Showing the last loaded collection.")
                        .font(.subheadline).foregroundStyle(hubTextSecondary)
                    Button("Try refresh again") {
                        AnalyticsService.trackCollectionHubAction(slug: vm.slug, actionKind: "refresh", itemType: "collection")
                        Task { await vm.load() }
                    }
                }
                cardColumns(presentation.children, columnCount: hubColumnCount) { child in
                    NavigationLink(value: Route.containerHub(slug: child.slug, name: child.name)) {
                        HStack {
                            Text(child.name).font(.headline)
                            Spacer()
                            Image(systemName: "chevron.right").font(.caption.weight(.semibold))
                        }
                        .foregroundStyle(hubTextPrimary)
                        .padding(16)
                        .background(hubCardBg, in: RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                    .contextMenu {
                        CollectionContextMenuItems(
                            slug: child.slug,
                            onShare: {
                                ShareInstrumentation.recordShareOpened(
                                    itemType: "collection",
                                    itemId: child.slug,
                                    itemName: child.name,
                                    category: nil,
                                    surface: .discoverCard
                                )
                            }
                        )
                    }
                    .simultaneousGesture(TapGesture().onEnded {
                        AnalyticsService.trackCollectionHubAction(slug: vm.slug, actionKind: "open_child_collection", itemType: "collection")
                    })
                    .id("container:\(child.slug)")
                }
                if !vm.pairedMetricSets.isEmpty {
                    VStack(alignment: .leading, spacing: 14) {
                        if vm.isOscarsHub {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Nominated & Wins by Category")
                                    .font(.headline)
                                    .foregroundStyle(hubTextPrimary)
                                Text("Each contender’s chance of being nominated and chance of winning side by side.")
                                    .font(.subheadline)
                                    .foregroundStyle(hubTextSecondary)
                            }
                            .padding(.top, 4)
                        }
                        cardColumns(vm.pairedMetricSets, columnCount: hubColumnCount, spacing: 14) { pairedSet in
                            DiscoverPairedMetricCardView(
                                set: pairedSet,
                                form: .pairedBarsTop5Expandable,
                                initialExpanded: !vm.isOscarsHub && vm.pairedMetricSets.count == 1,
                                allowsRouteLinks: true,
                                isOscarsCollectionSurface: vm.isOscarsHub
                            )
                        }
                    }
                    .accessibilityIdentifier("hub.pairedAwardCategories")
                }
                // Standalone cards retain published section order. Questions
                // linked to a rendered event are reached through that game's page.
                let coveredIds = vm.pairedCoveredMarketIds
                ForEach(presentation.displaySections) { section in
                    if let visualBlock = section.visualBlock {
                        Section {
                            MachinerySectionBlockView(
                                visualBlock: visualBlock,
                                members: section.members,
                                columnCount: hubColumnCount
                            )
                        } header: {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(presentation.resolvedSectionTitle(section))
                                    .font(.headline)
                                    .foregroundStyle(hubTextPrimary)
                                    .fixedSize(horizontal: false, vertical: true)
                                if let sectionNote = section.note?.trimmingCharacters(in: .whitespacesAndNewlines),
                                   !sectionNote.isEmpty {
                                    Text(sectionNote)
                                        .font(.subheadline)
                                        .foregroundStyle(hubTextSecondary)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            .padding(.top, 8)
                        }
                    } else {
                        let visibleMembers = coveredIds.isEmpty
                            ? section.members
                            : section.members.filter { !($0.type == "market" && coveredIds.contains($0.memberId)) }
                        if !visibleMembers.isEmpty {
                            Section {
                                cardColumns(visibleMembers, columnCount: hubColumnCount) { member in
                                    memberCard(member, presentation: presentation)
                                        .id(member.id)
                                }
                            } header: {
                                Text(presentation.resolvedSectionTitle(section))
                                    .font(.headline)
                                    .foregroundStyle(hubTextPrimary)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .padding(.top, 8)
                            }
                        }
                    }
                }
                if let pagerCount = presentation.pagerCountLabel {
                    Text(pagerCount)
                        .font(.subheadline)
                        .foregroundStyle(hubTextSecondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .accessibilityIdentifier("hub.loadedCount")
                }
                if vm.pageError != nil {
                    Text("Couldn’t load more markets. Try again.").font(.subheadline).foregroundStyle(hubTextSecondary)
                        .noteReviewPromptTrouble12304()
                }
                if presentation.response.state == .published, presentation.response.page?.nextCursor != nil {
                    Button {
                        Task { await vm.loadMore() }
                    } label: {
                        HStack {
                            if vm.isLoadingMore { ProgressView() }
                            Text(vm.isLoadingMore ? "Loading more markets…" : "Load more markets")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .disabled(vm.isLoadingMore)
                    .accessibilityIdentifier("hub.loadMore")
                }
            }
            .scrollTargetLayout()
            .padding(ContainerHubGridLayout13417.contentHorizontalPadding)
            .frame(maxWidth: ContainerHubGridLayout13417.maxContentWidth, alignment: .leading)
            .frame(maxWidth: .infinity)
            }
            .frame(width: proxy.size.width, height: proxy.size.height)
            .scrollPosition(id: Binding(get: { vm.context.scrollMemberId }, set: { vm.scrolled(to: $0) }), anchor: .top)
            .refreshable { await vm.load() }
        }
    }

    @ViewBuilder
    private func cardColumns<Item: Identifiable, Card: View>(
        _ items: [Item],
        columnCount: Int,
        spacing: CGFloat = ContainerHubGridLayout13417.spacing,
        @ViewBuilder card: @escaping (Item) -> Card
    ) -> some View {
        if columnCount <= 1 || items.isEmpty {
            ForEach(items) { item in
                card(item)
            }
        } else {
            LazyMasonryColumns(
                range: 0..<items.count,
                columnCount: columnCount,
                spacing: spacing,
                horizontalAlignment: .leading,
                cardAlignment: .leading
            ) { idx in
                card(items[idx])
            }
            .scrollTargetLayout()
        }
    }

    @ViewBuilder
    private func memberCard(_ member: ContainerHubMember, presentation: ContainerHubPresentation) -> some View {
        switch member.card {
        case .event(let event):
            VStack(alignment: .leading, spacing: 8) {
                NavigationLink(value: Route.eventDetail(id: member.memberId)) {
                    EventCardView(event: event, reason: nil)
                }
                .buttonStyle(.plain)
                .simultaneousGesture(TapGesture().onEnded {
                    AnalyticsService.trackCollectionHubAction(slug: vm.slug, actionKind: "open_event", itemType: "event")
                    vm.opened(member)
                })
                // #10146: the game page is the fuller view of its questions; the hub
                // no longer expands hundreds of contracts inline under each card.
                if let route = presentation.moreOnGameRoute(for: member) {
                    NavigationLink(value: route) {
                        HStack {
                            Text("More on this game")
                            Spacer()
                            Image(systemName: "chevron.right").font(.caption.weight(.semibold))
                        }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(hubTextSecondary)
                        .padding(.vertical, 10)
                        .padding(.horizontal, 12)
                        .background(hubSubtleBg, in: RoundedRectangle(cornerRadius: 8))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .simultaneousGesture(TapGesture().onEnded {
                        AnalyticsService.trackCollectionHubAction(slug: vm.slug, actionKind: "open_more_on_game", itemType: "event")
                        vm.opened(member)
                    })
                    .accessibilityIdentifier("hub.moreOnGame.\(member.memberId)")
                }
            }
            .padding(14)
            .background(hubCardBg, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(hubBorder, lineWidth: 0.5))
        case .question(let feed, let search):
            questionCard(member, feed: feed, search: search)
        case .unsupported:
            EmptyView() // Counted as partial; never given a destination.
        }
    }

    /// Standalone questions keep the familiar hydrated card and ordinary
    /// destination; never an opaque text link.
    private func questionCard(_ member: ContainerHubMember, feed: FeedFuturesData, search: SearchFuturesMarket) -> some View {
        NavigationLink(value: Route.futuresDetail(id: member.memberId)) {
            VStack(alignment: .leading, spacing: 8) {
                if let imageURL = feed.imageUrl {
                    FuturesHeroBackground(imageURL: imageURL, category: feed.llmSportCategory)
                        .frame(height: 120)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                if ContainerHubPresentation.questionNeedsVerdictRows(search) {
                    Text(search.name).font(.subheadline.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    let rawVerdictOutcomes = search.topOutcomes ?? []
                    let verdictOutcomes = NumericalMarketScaleOrder228.orderedAll(
                        rawVerdictOutcomes,
                        label: \.name,
                        probability: \.probability
                    )?.map(\.element) ?? rawVerdictOutcomes
                    ForEach(verdictOutcomes) { outcome in
                        let outcomeMark = feed.topOutcomes?.first(where: { $0.id == outcome.id || $0.name == outcome.name })?.sourceMark ?? feed.sourceMark
                        HStack(alignment: .center, spacing: 4) {
                            Text(outcome.name).font(.caption)
                            Spacer(minLength: 8)
                            Text(ContainerHubPresentation.outcomeLabel(outcome, market: search))
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(outcome.verdict(in: search) == .won ? DS.emerald : hubTextSecondary)
                            if let mark = SourceMarkButton(outcomeMark, number: nil, numberSize: 12, compactRow: true) {
                                mark
                            }
                        }
                    }
                    if search.topOutcomes?.isEmpty != false {
                        Text("Result unavailable").font(.caption).foregroundStyle(hubTextSecondary)
                    }
                } else {
                    // This existing compact card omits missing prices rather
                    // than the Discover hero's current `nil -> 0%` treatment.
                    FuturesCardView(futures: feed)
                    if search.topOutcomes?.isEmpty != false {
                        Text("Prices aren't available right now.").font(.caption).foregroundStyle(hubTextSecondary)
                    } else if search.topOutcomes?.contains(where: { $0.probability == nil }) == true {
                        Text("Some prices aren't available right now.").font(.caption).foregroundStyle(hubTextSecondary)
                    }
                }
            }
            .foregroundStyle(hubTextPrimary)
            .padding(14)
            .background(hubCardBg, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(hubBorder, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
        .simultaneousGesture(TapGesture().onEnded {
            AnalyticsService.trackCollectionHubAction(slug: vm.slug, actionKind: "open_market", itemType: "market")
            vm.opened(member)
        })
    }

    private func status(_ message: String, retry: Bool) -> some View {
        VStack(spacing: 16) {
            Text(message).font(.subheadline).foregroundStyle(hubTextSecondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            if retry {
                Button("Try Again") { Task { await vm.load() } }.buttonStyle(.borderedProminent)
            } else {
                Button("Back to Discover") { dismiss() }.buttonStyle(.borderedProminent)
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .noteReviewPromptTrouble12304(when: retry)
    }
}

/// Surface owners can pass the exact #9653 additive producer card here once
/// they place it. Deep links reach the same screen independently of placement.
struct ContainerHubCollectionLink: View {
    let collection: ContainerHubCollection
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        if collection.canOpen {
            NavigationLink(value: Route.containerHub(slug: collection.slug, name: collection.name)) {
                HStack {
                    Text(collection.text).font(.headline)
                    Spacer()
                    Image(systemName: "chevron.right").font(.caption.weight(.semibold))
                }
                .foregroundStyle(ContainerHubThemeTokens.textPrimary(colorScheme))
                .padding(16)
                .background(ContainerHubThemeTokens.cardBg(colorScheme), in: RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
            .contextMenu {
                CollectionContextMenuItems(
                    slug: collection.slug,
                    onShare: {
                        ShareInstrumentation.recordShareOpened(
                            itemType: "collection",
                            itemId: collection.slug,
                            itemName: collection.name,
                            category: nil,
                            surface: .discoverCard
                        )
                    }
                )
            }
        }
    }
}
