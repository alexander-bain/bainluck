import SwiftUI

/// Real public set entry for 402: A Browse & Search discovery (`machinery-*` / container hubs),
/// carrying its own verified cover image rather than one generic icon repeated across sets.
struct BrowsePublicSet402A: Identifiable, Hashable, Sendable {
    let slug: String
    let title: String
    let subtitle: String
    let imageURL: URL?

    var id: String { slug }
    @MainActor var route: Route { .containerHub(slug: slug, name: title) }
}

/// Shared category catalog for Browse tiles and Search empty-state pills (402: A draft 2),
/// ordered identically across both screens: Entertainment, Tech and business, Economics, Weather, Politics.
struct BrowseCategoryLink402A: Identifiable, Sendable {
    let id: String
    let label: String
    let desc: String
    let icon: String
    let searchIcon: String
    let color: Color
    let route: Route

    static let orderedAll: [BrowseCategoryLink402A] = [
        BrowseCategoryLink402A(
            id: "entertainment",
            label: "Entertainment",
            desc: "Awards, box office, culture",
            icon: "film.fill",
            searchIcon: "star.fill",
            color: .pink,
            route: .entertainment
        ),
        BrowseCategoryLink402A(
            id: "tech-and-business",
            label: "Tech and business",
            desc: "AI, frontier tech, big caps",
            icon: "cpu.fill",
            searchIcon: "cpu.fill",
            color: .blue,
            route: .sportCategory(key: "tech", name: "Tech and business")
        ),
        BrowseCategoryLink402A(
            id: "economics",
            label: "Economics",
            desc: "Fed rates, inflation, GDP",
            icon: "chart.bar.fill",
            searchIcon: "chart.line.uptrend.xyaxis",
            color: .purple,
            route: .economics
        ),
        BrowseCategoryLink402A(
            id: "weather",
            label: "Weather",
            desc: "Temperature, rainfall, storms",
            icon: "cloud.sun.fill",
            searchIcon: "cloud.sun.fill",
            color: .orange,
            route: .weather
        ),
        BrowseCategoryLink402A(
            id: "politics",
            label: "Politics",
            desc: "Elections, policy, geopolitics",
            icon: "building.columns.fill",
            searchIcon: "building.columns.fill",
            color: .indigo,
            route: .politics
        ),
    ]
}

/// No heading, placeholder or spinner when discovery is unavailable/disabled.
/// The ordinary Browse destinations continue rendering during this fresh read.
struct BrowseCollectionsView: View {
    @StateObject private var vm: ContainerDiscoveryViewModel
    private let previewSets: [BrowsePublicSet402A]
    private let preloadedSetImages: [String: Image]
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    init(
        service: any ContainerDiscoveryLoading = ContainerDiscoveryService(),
        previewSets: [BrowsePublicSet402A] = [],
        preloadedSetImages: [String: Image] = [:]
    ) {
        _vm = StateObject(wrappedValue: ContainerDiscoveryViewModel(service: service))
        self.previewSets = previewSets
        self.preloadedSetImages = preloadedSetImages
    }

    private var combinedSets: [BrowsePublicSet402A] {
        var seen = Set<String>()
        var result: [BrowsePublicSet402A] = []
        for s in previewSets where seen.insert(s.slug).inserted {
            result.append(s)
        }
        for entry in vm.entries where seen.insert(entry.collection.slug).inserted {
            result.append(
                BrowsePublicSet402A(
                    slug: entry.collection.slug,
                    title: entry.collection.name,
                    subtitle: entry.subtitle,
                    imageURL: nil
                )
            )
        }
        return result
    }

    var body: some View {
        // #9989 — the load modifiers need a container that exists while entries
        // are empty. A `Group` has no view of its own: with its `if` false it
        // resolves to nothing, `.task` attaches to nothing, and the first read
        // that would fill it never starts.
        VStack(alignment: .leading, spacing: 0) {
            if !combinedSets.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Sets")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                        .textCase(.uppercase)
                        .tracking(0.6)
                    ForEach(combinedSets) { setItem in
                        NavigationLink(value: setItem.route) {
                            HStack(alignment: dynamicTypeSize.isAccessibilitySize ? .top : .center, spacing: 12) {
                                setThumbnail(for: setItem)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(setItem.title)
                                        .font(.headline)
                                        .foregroundStyle(.primary)
                                        .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 2)
                                        .multilineTextAlignment(.leading)
                                        .fixedSize(horizontal: false, vertical: true)
                                    Text(setItem.subtitle)
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                        .multilineTextAlignment(.leading)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                Spacer(minLength: 4)
                                Image(systemName: "chevron.right")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.tertiary)
                                    .accessibilityHidden(true)
                            }
                            .padding(14)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(
                                colorScheme == .dark ? Color.cardBackground : DS.cardBg,
                                in: RoundedRectangle(cornerRadius: 14)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 14)
                                    .stroke(colorScheme == .dark ? Color.white.opacity(0.14) : DS.border, lineWidth: 1)
                            )
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            CollectionContextMenuItems(
                                slug: setItem.slug,
                                onShare: {
                                    ShareInstrumentation.recordShareOpened(
                                        itemType: "collection",
                                        itemId: setItem.slug,
                                        itemName: setItem.title,
                                        category: nil,
                                        surface: .discoverCard
                                    )
                                }
                            )
                        }
                        .accessibilityIdentifier("browse-collection-\(setItem.id)")
                    }
                }
            }
        }
        .task { await vm.load() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await vm.load() } }
        }
    }

    @ViewBuilder
    private func setThumbnail(for setItem: BrowsePublicSet402A) -> some View {
        let trackBg = colorScheme == .dark ? Color.white.opacity(0.08) : DS.trackBg
        let border = colorScheme == .dark ? Color.white.opacity(0.14) : DS.border
        Group {
            if let preloaded = preloadedSetImages[setItem.slug] {
                preloaded
                    .resizable()
                    .scaledToFill()
            } else if let url = setItem.imageURL {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().scaledToFill()
                    default:
                        initialsBadge(for: setItem, bg: trackBg)
                    }
                }
            } else {
                initialsBadge(for: setItem, bg: trackBg)
            }
        }
        .frame(width: 52, height: 52)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(border, lineWidth: 1))
        .accessibilityHidden(true)
    }

    private func initialsBadge(for setItem: BrowsePublicSet402A, bg: Color) -> some View {
        let nonYearTitle = setItem.title
            .split(whereSeparator: { $0.isWhitespace })
            .filter { !$0.allSatisfy(\.isNumber) }
            .joined(separator: " ")
        let label = PairedMetricPresentation.initials(for: nonYearTitle.isEmpty ? setItem.title : nonYearTitle)
        return Text(label)
            .font(.system(size: 15, weight: .bold, design: .rounded))
            .foregroundStyle(colorScheme == .dark ? Color.white.opacity(0.85) : DS.textPrimary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(bg)
    }
}
