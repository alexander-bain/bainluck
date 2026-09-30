import SwiftUI

/// No heading, placeholder or spinner when discovery is unavailable/disabled.
/// The ordinary Browse destinations continue rendering during this fresh read.
struct BrowseCollectionsView: View {
    @StateObject private var vm = ContainerDiscoveryViewModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        Group {
            if !vm.entries.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Collections")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                        .textCase(.uppercase)
                        .tracking(0.6)
                    ForEach(vm.entries) { entry in
                        NavigationLink(value: entry.route) {
                            HStack(spacing: 12) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(entry.collection.name)
                                        .font(.headline)
                                        .fixedSize(horizontal: false, vertical: true)
                                    Text(entry.subtitle)
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer(minLength: 4)
                                Image(systemName: "chevron.right")
                                    .font(.caption.weight(.semibold))
                                    .accessibilityHidden(true)
                            }
                            .foregroundStyle(DS.textPrimary)
                            .padding(16)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
                        }
                        .buttonStyle(.plain)
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
