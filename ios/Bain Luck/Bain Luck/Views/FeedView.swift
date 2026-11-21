import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

// MARK: - View

struct FeedView: View {
    @StateObject private var vm: FeedViewModel
    @State private var path = NavigationPath()
    @State private var selectedCategory: String = "all"
    @State private var hoveredItemId: String?
    // Sports first-render attribution (L2-211 Item 2 / C73): the once-only guard keys
    // on the view model's IMMUTABLE render-generation id — NOT a boolean an `onAppear`
    // refire could desync — so a same-card-ID refresh (SwiftUI retains the rows and
    // does not re-fire `onAppear`) still emits its new generation via
    // `onChange(of:)`, and both the elapsed time and the item count reported come
    // from the frozen token, never a live `vm.items.count`.
    @State private var lastEmittedRenderGenerationId: Int?
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
    @EnvironmentObject private var pinManager: PinManager
    @Environment(\.horizontalSizeClass) private var sizeClass
    #if os(macOS)
    @Environment(\.openWindow) private var openWindow
    #endif

    /// #11288 — the view model is injectable so a hosted test can draw the real
    /// loading and empty states from a fake client. The app passes nothing.
    init(viewModel: @autoclosure @escaping () -> FeedViewModel = FeedViewModel()) {
        _vm = StateObject(wrappedValue: viewModel())
    }

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                let state = tabState
                switch state {
                case .loading:
                    SkeletonFeedView(caption: "Loading games…")
                case .failed(let error):
                    VStack(spacing: 16) {
                        Spacer()
                        Image(systemName: "wifi.exclamationmark")
                            .font(.system(size: 48))
                            .foregroundStyle(.secondary.opacity(0.5))
                        Text("Couldn't Load Feed")
                            .font(.title3)
                            .fontWeight(.semibold)
                        Text(error)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondaryReadable)
                            .multilineTextAlignment(.center)
                        Button("Try Again") {
                            Task { await vm.startLoad() }
                        }
                        .buttonStyle(.borderedProminent)
                        Spacer()
                    }
                    .padding(.horizontal, 40)
                case .content, .nothingInCategory, .nothingToShow:
                    feedList(state)
                }
            }
            .navigationTitle("🍀 Bain Luck")
            .navigationDestination(for: Route.self) { RouteDestination(route: $0) }
        }
        .onAppear {
            AnalyticsService.trackScreen(name: "feed", type: "feed")
        }
        .task {
            // Route every load through the single owned rail (L2-211 Item 1 / C73):
            // (re)appearance re-arms after a prior stop, then supersedes any prior
            // owned load.
            vm.viewDidStart()
            if vm.items.isEmpty {
                // 🔴 Arm the felt-number rail on tab activation with an empty
                // screen (CERT-782): the cold/warm label is claimed now instead of
                // when the first card finally lands, and a Sports load that renders
                // nothing reports `no_card` rather than nothing at all. Guarded on
                // `items.isEmpty` because a tab switch back to a populated Sports
                // stamps no new render generation to settle the arm with.
                ScreenTimingSession.armScreen(surface: ScreenTimingSurface.sports)
            }
            await vm.startLoad()
        }
        .onChange(of: vm.loading) { _, loading in
            guard !loading, vm.items.isEmpty else { return }
            ScreenTimingSession.reportOutcome(
                surface: ScreenTimingSurface.sports,
                outcome: vm.error == nil ? "empty" : "error"
            )
        }
        .onChange(of: vm.firstRenderGeneration) { _, _ in
            // Generation-keyed acknowledgement (L2-211 Item 2 / C73): fires when the
            // view model stamps a new render token even if the refresh retains the
            // same card IDs (SwiftUI would not re-run `onAppear` for those rows).
            emitSportsFirstRenderIfNeeded()
        }
        .onDisappear {
            // Cancel + join the owned load and its siblings, invalidate the load
            // generation, and stop the timer so a timer-driven refresh already in
            // flight can't mutate state after the tab closes (L2-211 Item 1 / C73).
            vm.viewDidStop()
            ScreenTimingSession.disarmScreen(surface: ScreenTimingSurface.sports)
        }
        // The orientation observer that used to live here drove
        // `landscapeColumns`, which nothing read (#3723). #3709 replaced this
        // view's column count with a `GeometryReader` and left the dead state
        // behind; deleting it removes the last live `UIScreen.main.bounds` read
        // on a layout path here — gotcha #27, the Stage Manager trap, which
        // measures the SCREEN and not the window.
        // #10090 — a pushed page covers the list without making this stack
        // disappear, so the live refresh pauses here and catches up on return.
        .onChange(of: path.isEmpty) { _, visible in
            if visible {
                Task { await vm.feedUncovered() }
            } else {
                vm.feedCovered()
            }
        }
        .onChange(of: vm.liveCount) { _, count in
            navCoordinator.liveGameCount = count
        }
        .onChange(of: navCoordinator.pendingRoute, initial: true) { _, _ in
            if navCoordinator.selectedTab == .feed,
               let route = navCoordinator.consumeRoute() {
                path.append(route)
            }
        }
    }

    // MARK: - Feed List

    // MARK: - iPad Grid

    /// Width available to the iPad card grid, in points. 0 until the first
    /// geometry pass resolves, which `DiscoverMasonry` reads as one column
    /// (#3709).
    @State private var gridWidth: CGFloat = 0

    private var pinnedItems: [FeedItem] { pinnedItems(for: selectedCategory) }

    private func pinnedItems(for categoryID: String) -> [FeedItem] {
        vm.filteredItems(for: categoryID).filter { item in
            if item.type == "event", let event = item.event {
                return pinManager.pinnedEventIDs.contains(event.id)
            } else if item.type == "futures", let futures = item.futures {
                return pinManager.pinnedFuturesIDs.contains(futures.id)
            }
            return false
        }
    }

    /// #11288 — see `FeedViewModel.tabState`.
    private var tabState: SportsTabState {
        let pinnedHere = !pinnedItems.isEmpty
        return vm.tabState(
            for: selectedCategory,
            pinnedAnywhere: pinnedHere || !pinnedItems(for: "all").isEmpty,
            pinnedInCategory: pinnedHere
        )
    }

    private func feedList(_ state: SportsTabState) -> some View {
        List {
            // Non-blocking honest state when a refresh failed but prior content is
            // still shown (L2-209 Item 2 / C68): the tab stays usable and retryable
            // rather than silently presenting stale content as freshly loaded.
            // With nothing on screen the empty message below says it instead.
            if vm.refreshFailed, state != .nothingToShow(refreshFailed: true) {
                Section {
                    HStack(spacing: 8) {
                        Image(systemName: "arrow.clockwise.circle")
                            .foregroundStyle(DS.textSecondaryReadable)
                        Text("Showing recent games — couldn't refresh")
                            .font(.footnote)
                            .foregroundStyle(DS.textSecondaryReadable)
                        Spacer()
                        Button("Retry") {
                            Task { await vm.startLoad() }
                        }
                        .font(.footnote.weight(.semibold))
                        .buttonStyle(.borderless)
                    }
                    .listRowSeparator(.hidden)
                }
            }

            // League & category chips — navigate to league grids or category pages
            Section {
                SportFilterChips(selectedCategory: $selectedCategory) { route in
                    path.append(route)
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
            }

            if case .nothingToShow(let refreshFailed) = state {
                Section {
                    VStack(spacing: 12) {
                        Text(refreshFailed ? "Couldn't load games" : "No games to show right now")
                            .font(.headline)
                            .multilineTextAlignment(.center)
                        Button("Retry") {
                            Task { await vm.startLoad() }
                        }
                        .buttonStyle(.borderedProminent)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 24)
                    .listRowBackground(Color.clear)
                }
            } else if case .nothingInCategory(let stillLoading) = state {
                Section {
                    if stillLoading {
                        HStack(spacing: 8) {
                            ProgressView()
                            Text("Loading games…")
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondaryReadable)
                        }
                        .frame(maxWidth: .infinity)
                        .accessibilityElement(children: .combine)
                    } else {
                        VStack(spacing: 12) {
                            Text("Nothing to show for \(categoryName) right now")
                                .font(.headline)
                                .multilineTextAlignment(.center)
                            Button("Show All") { selectedCategory = "all" }
                                .buttonStyle(.bordered)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 24)
                    }
                }
                .listRowBackground(Color.clear)
            }

            if !pinnedItems.isEmpty {
                feedSection(title: "Pinned", systemImage: "bookmark.fill", imageColor: .orange, items: pinnedItems)
            }

            let live = vm.filteredLiveNow(for: selectedCategory)
            let up = vm.filteredUpcoming(for: selectedCategory)
            let happened = vm.filteredJustHappened(for: selectedCategory)
            let shelfCards = vm.filteredFuturesShelfCards(
                for: selectedCategory,
                limit: sizeClass == .regular ? nil : SportsFuturesShelf13013.maxCompactShelfCards
            )
            let shelfLeads = vm.futuresShelfLeads(for: selectedCategory)

            if shelfLeads, !shelfCards.isEmpty {
                futuresShelfSection(cards: shelfCards)
            }

            if !live.isEmpty {
                // live/048 — the header reads the bucket. See `EventState`.
                feedSection(title: EventState.liveSectionTitle(hasSuspended: vm.filteredLiveNowHasSuspended(for: selectedCategory)), systemImage: "circle.fill", imageColor: .red, items: live)
            }

            if !up.isEmpty {
                feedSection(title: "Upcoming", systemImage: "calendar", imageColor: .blue, items: up)
            }

            if !happened.isEmpty {
                feedSection(title: "Just Happened", systemImage: "clock.arrow.circlepath", imageColor: .secondary, items: happened)
            }

            if !shelfLeads, !shelfCards.isEmpty {
                futuresShelfSection(cards: shelfCards)
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .refreshable {
            await vm.startLoad()
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
        }
    }

    private var categoryName: String {
        sportCategories.first { $0.id == selectedCategory }?.name ?? "this sport"
    }

    /// Emit the on-screen first-render milestone once per render generation (L2-211
    /// Item 2 / C73), when the first renderable Sports card appears OR when the view
    /// model stamps a new render token (a same-id refresh that retains its rows). The
    /// once-only guard keys on the token's IMMUTABLE generation id — not a boolean an
    /// `onAppear` refire could desync — and BOTH the elapsed time and the item count
    /// reported come from that frozen token, never a live `vm.items.count` a later
    /// backfill merge or a superseding load could have changed. An empty successful
    /// main stamps no token, so it emits nothing; the per-stage data-ready milestone
    /// (model assignment) stays distinct from this on-screen first-card render.
    private func emitSportsFirstRenderIfNeeded() {
        guard let decision = SportsFirstRender.generationDecision(
            generation: vm.firstRenderGeneration,
            lastEmittedGenerationId: lastEmittedRenderGenerationId,
            now: Date()
        ) else { return }
        lastEmittedRenderGenerationId = decision.generation.generation
        AnalyticsService.trackSportsFirstRender(
            firstRenderMs: decision.ms,
            itemCount: decision.generation.itemCount
        )
    }

    // MARK: - Section Builder

    private func feedSection(title: String, systemImage: String, imageColor: Color, items: [FeedItem]) -> some View {
        Section {
            if sizeClass == .regular {
                // iPad: multi-column masonry with context menu for pin.
                //
                // #3709 — see `DiscoverMasonry`. `LazyVGrid` lays out in ROWS
                // and pads every cell to the tallest in its row; `items` mixes
                // the tall `EventCardView` with the short futures strip, so the
                // shorter card in a row carried the surplus as dead space
                // BELOW it.
                let columnCount = DiscoverMasonry.listColumnCount(availableWidth: gridWidth)
                let masonryColumns = DiscoverMasonry.columns(
                    cardCount: items.count,
                    columnCount: columnCount
                )
                HStack(alignment: .top, spacing: DiscoverMasonry.listCardSpacing) {
                    ForEach(Array(masonryColumns.enumerated()), id: \.offset) { _, indices in
                        VStack(spacing: DiscoverMasonry.listCardSpacing) {
                            ForEach(indices, id: \.self) { idx in
                                gridCard(items[idx])
                                    .onAppear { emitSportsFirstRenderIfNeeded() }
                            }
                        }
                        .frame(maxWidth: .infinity)
                    }
                }
                .background(
                    GeometryReader { geo in
                        Color.clear
                            .onAppear { gridWidth = geo.size.width }
                            .onChange(of: geo.size.width) { _, newValue in
                                gridWidth = newValue
                            }
                    }
                )
                .listRowInsets(EdgeInsets(top: 6, leading: 4, bottom: 10, trailing: 4))
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
            } else {
                ForEach(items) { item in
                    feedRow(item)
                        .onAppear { emitSportsFirstRenderIfNeeded() }
                        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                            pinSwipeButton(item)
                        }
                }
            }
        } header: {
            HStack(spacing: 6) {
                Label(title, systemImage: systemImage)
                    .foregroundStyle(imageColor)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .textCase(nil)
                Text("\(items.count)")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }
        }
    }

    // MARK: - Single Futures Shelf (#13013 `246: A` + `256: B`)

    private var compactShelfCardSurface: Color {
        #if os(iOS)
        return Color(uiColor: .secondarySystemGroupedBackground)
        #else
        return Color.cardBackgroundDark
        #endif
    }

    private func futuresShelfSection(cards: [SportsFuturesShelf13013.ShelfCard]) -> some View {
        Section {
            if sizeClass == .regular {
                // #3709 — DiscoverMasonry deal for regular iPad/Mac widths.
                let columnCount = DiscoverMasonry.listColumnCount(availableWidth: gridWidth)
                let masonryColumns = DiscoverMasonry.columns(
                    cardCount: cards.count,
                    columnCount: columnCount
                )
                HStack(alignment: .top, spacing: DiscoverMasonry.listCardSpacing) {
                    ForEach(Array(masonryColumns.enumerated()), id: \.offset) { _, indices in
                        VStack(spacing: DiscoverMasonry.listCardSpacing) {
                            ForEach(indices, id: \.self) { idx in
                                shelfCardBody(cards[idx])
                                    .padding(12)
                                    .background(regularGridCardSurface)
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 12)
                                            .stroke(Color.primary.opacity(0.06), lineWidth: 1)
                                    )
                                    .onAppear { emitSportsFirstRenderIfNeeded() }
                            }
                        }
                        .frame(maxWidth: .infinity)
                    }
                }
                .background(
                    GeometryReader { geo in
                        Color.clear
                            .onAppear { gridWidth = geo.size.width }
                            .onChange(of: geo.size.width) { _, newValue in
                                gridWidth = newValue
                            }
                    }
                )
                .listRowInsets(EdgeInsets(top: 6, leading: 4, bottom: 10, trailing: 4))
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 12) {
                        ForEach(cards) { card in
                            shelfCardBody(card)
                                .padding(12)
                                .frame(width: 286, alignment: .topLeading)
                                .background(compactShelfCardSurface)
                                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                                        .stroke(Color.primary.opacity(0.07), lineWidth: 1)
                                )
                                .onAppear { emitSportsFirstRenderIfNeeded() }
                        }
                    }
                    .padding(.horizontal, 4)
                    .padding(.vertical, 2)
                }
                .listRowInsets(EdgeInsets(top: 2, leading: 0, bottom: 6, trailing: 0))
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
            }
        } header: {
            HStack(spacing: 6) {
                Label("Futures", systemImage: "chart.bar.fill")
                    .foregroundStyle(.purple)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .textCase(nil)
                Text("\(cards.count)")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }
        }
    }

    @ViewBuilder
    private func shelfCardBody(_ card: SportsFuturesShelf13013.ShelfCard) -> some View {
        switch card {
        case .futures(let item, let futures):
            Button {
                path.append(Route.futuresDetail(id: futures.id))
            } label: {
                FuturesCardView(futures: futures)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .contextMenu { cardContextMenu(item) }
        case .tournament(_, let tournament):
            Button {
                if let slug = tournament.slug, !slug.isEmpty {
                    path.append(Route.golfTournament(slug: slug, name: tournament.name))
                } else {
                    path.append(Route.golfCategory)
                }
            } label: {
                SportsShelfTournamentCardView13013(tournament: tournament)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
        case .playoffLadder(let group):
            if let entityName = group.entityName, let stages = group.stages {
                LadderCardView(
                    title: entityName,
                    logoUrl: group.logoUrl,
                    teamColor: group.teamColors?.primary.map { Color(rgb: $0) } ?? DS.emeraldDark,
                    rungs: stages.prefix(5).map { LadderRung(stage: $0) }
                )
            }
        }
    }

    // MARK: - Grid Card (iPad/Mac with hover + context menu)

    private var regularGridCardSurface: Color {
        #if os(iOS)
        return Color(uiColor: .secondarySystemGroupedBackground)
        #else
        return Color.cardBackgroundDark
        #endif
    }

    private func gridCard(_ item: FeedItem) -> some View {
        let isHovered = hoveredItemId == item.id
        return feedRow(item)
            .padding(12)
            .background(regularGridCardSurface)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.primary.opacity(0.06), lineWidth: 1)
            )
            #if os(macOS)
            .focusable()
            .focusEffectDisabled()
            .onHover { hovering in hoveredItemId = hovering ? item.id : nil }
            .scaleEffect(isHovered ? 1.015 : 1.0)
            .shadow(color: .black.opacity(isHovered ? 0.1 : 0), radius: 4)
            .animation(.easeInOut(duration: 0.15), value: hoveredItemId)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(isHovered ? Color.accentColor.opacity(0.4) : .clear, lineWidth: 2)
            )
            #endif
            .contextMenu { cardContextMenu(item) }
    }

    // MARK: - Row

    @ViewBuilder
    private func feedRow(_ item: FeedItem) -> some View {
        if item.type == "event", let event = item.event {
            Button {
                AnalyticsService.trackEventCardClick(eventId: event.id, sport: event.sport, status: event.status)
                path.append(Route.eventDetail(id: event.id))
            } label: {
                EventCardView(
                    event: event,
                    reason: item.reason,
                    personalizationReasons: item.personalizationReasons,
                    headline: item.headline
                )
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .contextMenu { cardContextMenu(item) }
        } else if item.type == "futures", let futures = item.futures {
            Button {
                path.append(Route.futuresDetail(id: futures.id))
            } label: {
                FuturesCardView(futures: futures)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .contextMenu { cardContextMenu(item) }
        }
    }

    // MARK: - Swipe to Pin

    @ViewBuilder
    private func pinSwipeButton(_ item: FeedItem) -> some View {
        if let pinInfo = pinInfo(for: item) {
            let isPinned = pinManager.isPinned(type: pinInfo.type, id: pinInfo.id)
            Button {
                pinManager.togglePin(type: pinInfo.type, id: pinInfo.id)
            } label: {
                Label(isPinned ? "Unpin" : "Pin", systemImage: isPinned ? "bookmark.slash" : "bookmark")
            }
            .tint(isPinned ? .gray : .orange)
        }
    }

    // MARK: - Context Menu Pin (iPad)

    @ViewBuilder
    private func cardContextMenu(_ item: FeedItem) -> some View {
        #if os(macOS)
        CardContextMenu(
            item: item,
            pin: contextMenuPin(for: item),
            onOpenEventInNewWindow: { eventId in
                openWindow(value: eventId)
            }
        )
        #else
        CardContextMenu(
            item: item,
            pin: contextMenuPin(for: item)
        )
        #endif
    }

    private func contextMenuPin(for item: FeedItem) -> CardContextMenuPin? {
        guard let pinInfo = pinInfo(for: item) else { return nil }
        return CardContextMenuPin(
            isPinned: pinManager.isPinned(type: pinInfo.type, id: pinInfo.id),
            toggle: {
                pinManager.togglePin(type: pinInfo.type, id: pinInfo.id)
            }
        )
    }

    private func pinInfo(for item: FeedItem) -> (type: String, id: Int)? {
        if item.type == "event", let event = item.event {
            return ("event", event.id)
        } else if item.type == "futures", let futures = item.futures {
            return ("future", futures.id)
        }
        return nil
    }
}
