import SwiftUI

/// No heading, placeholder or spinner when discovery is unavailable/disabled.
/// The ordinary Browse destinations continue rendering during this fresh read.
struct BrowseCollectionsView: View {
    @StateObject private var vm: ContainerDiscoveryViewModel
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    init(service: any ContainerDiscoveryLoading = ContainerDiscoveryService()) {
        _vm = StateObject(wrappedValue: ContainerDiscoveryViewModel(service: service))
    }

    var body: some View {
        // #9989 — the load modifiers need a container that exists while entries
        // are empty. A `Group` has no view of its own: with its `if` false it
        // resolves to nothing, `.task` attaches to nothing, and the first read
        // that would fill it never starts.
        VStack(alignment: .leading, spacing: 0) {
            if !vm.entries.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Live Sets")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                        .textCase(.uppercase)
                        .tracking(0.6)
                    ForEach(vm.entries) { entry in
                        NavigationLink(value: entry.route) {
                            HStack(alignment: dynamicTypeSize.isAccessibilitySize ? .top : .center, spacing: 12) {
                                Image(systemName: "square.stack.3d.up.fill")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(.white)
                                    .frame(width: 38, height: 38)
                                    .background(DS.emerald.gradient, in: RoundedRectangle(cornerRadius: 10))
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(entry.collection.name)
                                        .font(.headline)
                                        .foregroundStyle(.primary)
                                        .multilineTextAlignment(.leading)
                                        .fixedSize(horizontal: false, vertical: true)
                                    Text(entry.subtitle)
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
                                slug: entry.collection.slug,
                                onShare: {
                                    ShareInstrumentation.recordShareOpened(
                                        itemType: "collection",
                                        itemId: entry.collection.slug,
                                        itemName: entry.collection.name,
                                        category: nil,
                                        surface: .discoverCard
                                    )
                                }
                            )
                        }
                        .accessibilityIdentifier("browse-collection-\(entry.id)")
                    }
                }
            }
        }
        .task { await vm.load() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await vm.load() } }
        }
    }
}
