import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

// MARK: - View

struct FeedView: View {
    @StateObject private var vm = FeedViewModel()
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

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if vm.loading {
                    SkeletonFeedView()
                } else if let error = vm.error, vm.items.isEmpty {
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
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                        Button("Try Again") {
                            Task { await vm.startLoad() }
                        }
                        .buttonStyle(.borderedProminent)
                        Spacer()
                    }
                    .padding(.horizontal, 40)
                } else {
                    feedList
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
        .onChange(of: vm.liveCount) { _, count in
            navCoordinator.liveGameCount = count
        }
        .onChange(of: navCoordinator.pendingRoute) { _, _ in
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

    private var pinnedItems: [FeedItem] {
        vm.filteredItems(for: selectedCategory).filter { item in
            if item.type == "event", let event = item.event {
                return pinManager.pinnedEventIDs.contains(event.id)
            } else if item.type == "futures", let futures = item.futures {
                return pinManager.pinnedFuturesIDs.contains(futures.id)
            }
            return false
        }
    }

    private var feedList: some View {
        List {
            // Non-blocking honest state when a refresh failed but prior content is
            // still shown (L2-209 Item 2 / C68): the tab stays usable and retryable
            // rather than silently presenting stale content as freshly loaded.
            if vm.refreshFailed {
                Section {
                    HStack(spacing: 8) {
                        Image(systemName: "arrow.clockwise.circle")
                            .foregroundStyle(.secondary)
                        Text("Showing recent games — couldn't refresh")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
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

            if !pinnedItems.isEmpty {
                feedSection(title: "Pinned", systemImage: "bookmark.fill", imageColor: .orange, items: pinnedItems)
            }

            let live = vm.filteredLiveNow(for: selectedCategory)
            if !live.isEmpty {
                // live/048 — the header reads the bucket. See `EventState`.
                feedSection(title: EventState.liveSectionTitle(hasSuspended: vm.filteredLiveNowHasSuspended(for: selectedCategory)), systemImage: "circle.fill", imageColor: .red, items: live)
            }

            let happened = vm.filteredJustHappened(for: selectedCategory)
            if !happened.isEmpty {
                feedSection(title: "Just Happened", systemImage: "clock.arrow.circlepath", imageColor: .secondary, items: happened)
            }

            let up = vm.filteredUpcoming(for: selectedCategory)
            if !up.isEmpty {
                feedSection(title: "Upcoming", systemImage: "calendar", imageColor: .blue, items: up)
            }

            let markets = vm.filteredTopMarkets(for: selectedCategory)
            if !markets.isEmpty {
                feedSection(title: "Top Markets", systemImage: "chart.bar.fill", imageColor: .purple, items: markets)
            }

            // Grouped futures (player props, playoff progressions)
            if !vm.groupedItems.isEmpty {
                groupedFuturesSection
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
                .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
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
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }
        }
    }

    // MARK: - Grouped Futures Section

    private var groupedFuturesSection: some View {
        Section {
            if sizeClass == .regular {
                // #3709 — same `LazyVGrid` row-padding defect as the section
                // above. These cells are all `groupedRow`, so unlike the mixed
                // feed sections they at least share a builder — but a grouped
                // futures card is as tall as the outcomes it holds, and two
                // markets with different outcome counts sit side by side here
                // routinely. Same treatment, for the same reason.
                let columnCount = DiscoverMasonry.listColumnCount(availableWidth: gridWidth)
                let masonryColumns = DiscoverMasonry.columns(
                    cardCount: vm.groupedItems.count,
                    columnCount: columnCount
                )
                HStack(alignment: .top, spacing: DiscoverMasonry.listCardSpacing) {
                    ForEach(Array(masonryColumns.enumerated()), id: \.offset) { _, indices in
                        VStack(spacing: DiscoverMasonry.listCardSpacing) {
                            ForEach(indices, id: \.self) { idx in
                                groupedRow(vm.groupedItems[idx])
                                    .padding(12)
                                    .background(Color.cardBackgroundDark)
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
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
                .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
            } else {
                ForEach(vm.groupedItems) { item in
                    groupedRow(item)
                        .onAppear { emitSportsFirstRenderIfNeeded() }
                }
            }
        } header: {
            HStack(spacing: 6) {
                Label("Player Props", systemImage: "person.fill")
                    .foregroundStyle(.green)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .textCase(nil)
                Text("\(vm.groupedItems.count)")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }
        }
    }

    @ViewBuilder
    private func groupedRow(_ item: GroupedFeedItem) -> some View {
        if item.type == "stat_prop", let playerName = item.playerName, let statCategory = item.statCategory, let lines = item.lines {
            PlayerStatCardView(
                playerName: playerName,
                statCategory: statCategory,
                lines: lines,
                espnPlayerId: item.espnPlayerId,
                sportKey: item.sportKey,
                eventMatchup: item.eventMatchup,
                eventTime: item.eventTime
            )
        } else if item.type == "playoff_progression", let entityName = item.entityName, let stages = item.stages {
            // L2-123: one ladder component everywhere (kernel discipline). The feed's
            // grouped playoff progression now renders on the shared LadderCardView "2b"
            // primitive via the LadderRung(stage:) adapter — the compact
            // ProgressionLadderView is retired.
            LadderCardView(
                title: entityName,
                logoUrl: item.logoUrl,
                teamColor: item.teamColors?.primary.map { Color(rgb: $0) } ?? DS.emeraldDark,
                rungs: stages.prefix(5).map { LadderRung(stage: $0) }
            )
        }
    }

    // MARK: - Grid Card (iPad/Mac with hover + context menu)

    private func gridCard(_ item: FeedItem) -> some View {
        let isHovered = hoveredItemId == item.id
        return feedRow(item)
            .padding(12)
            .background(Color.cardBackgroundDark)
            .clipShape(RoundedRectangle(cornerRadius: 12))
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
