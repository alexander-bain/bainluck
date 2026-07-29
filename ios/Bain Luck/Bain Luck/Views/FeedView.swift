import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

// MARK: - View

struct FeedView: View {
    @StateObject private var vm = FeedViewModel()
    @State private var path = NavigationPath()
    @State private var selectedCategory: String = "all"
    @State private var landscapeColumns = false
    @State private var hoveredItemId: String?
    // Sports first-render attribution (L2-209 Item 2 / C68): `loadStartedAt` stamps
    // when a load begins; `firstRenderEmitted` guards a single on-screen
    // `sports_feed_first_render` per load so a fast model assignment is never
    // reported as first paint and an empty successful main emits nothing.
    @State private var loadStartedAt: Date?
    @State private var firstRenderEmitted = false
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
                            beginSportsFirstRenderWindow()
                            Task { await vm.load() }
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
            updateLandscapeColumns()
        }
        .task {
            beginSportsFirstRenderWindow()
            await vm.load()
        }
        .onDisappear {
            // Invalidate the load generation + stop the timer so a timer-driven
            // refresh already in flight can't mutate state after the tab closes
            // (L2-209 Item 1 / C68).
            vm.viewDidStop()
        }
        #if os(iOS)
        .onReceive(NotificationCenter.default.publisher(for: UIDevice.orientationDidChangeNotification)) { _ in
            updateLandscapeColumns()
        }
        #endif
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

    private var iPadGridColumns: [GridItem] {
        [GridItem(.adaptive(minimum: 340), spacing: 12)]
    }

    private func updateLandscapeColumns() {
        guard sizeClass == .regular else { return }
        #if os(iOS)
        let bounds = UIScreen.main.bounds
        landscapeColumns = bounds.width > bounds.height
        #else
        landscapeColumns = true
        #endif
    }

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
                            beginSportsFirstRenderWindow()
                            Task { await vm.load() }
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
                feedSection(title: "Live Now", systemImage: "circle.fill", imageColor: .red, items: live)
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
            beginSportsFirstRenderWindow()
            await vm.load()
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
        }
    }

    /// Open a new Sports first-render measurement window (L2-209 Item 2): stamp the
    /// load start and re-arm the one-shot so the NEXT first renderable card emits its
    /// own on-screen render time. Called wherever a load begins (cold task, refresh,
    /// retry).
    private func beginSportsFirstRenderWindow() {
        loadStartedAt = Date()
        firstRenderEmitted = false
    }

    /// Emit the on-screen first-render milestone once per load (L2-209 Item 2), when
    /// the first renderable Sports card actually appears — deliberately distinct from
    /// the view model's per-stage data-ready milestone so a fast model assignment is
    /// never reported as a fast first paint, and an empty successful main (no cards →
    /// no `onAppear`) emits nothing.
    private func emitSportsFirstRenderIfNeeded() {
        guard let ms = DiscoverFirstRender.elapsedMsIfShouldEmit(
            emitted: firstRenderEmitted, loadStartedAt: loadStartedAt, now: Date()
        ) else { return }
        firstRenderEmitted = true
        AnalyticsService.trackSportsFirstRender(firstRenderMs: ms, itemCount: vm.items.count)
    }

    // MARK: - Section Builder

    private func feedSection(title: String, systemImage: String, imageColor: Color, items: [FeedItem]) -> some View {
        Section {
            if sizeClass == .regular {
                // iPad: multi-column grid with context menu for pin
                LazyVGrid(columns: iPadGridColumns, spacing: 12) {
                    ForEach(items) { item in
                        gridCard(item)
                            .onAppear { emitSportsFirstRenderIfNeeded() }
                    }
                }
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
                LazyVGrid(columns: iPadGridColumns, spacing: 12) {
                    ForEach(vm.groupedItems) { item in
                        groupedRow(item)
                            .padding(12)
                            .background(Color.cardBackgroundDark)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .onAppear { emitSportsFirstRenderIfNeeded() }
                    }
                }
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
