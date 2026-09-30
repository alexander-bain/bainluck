import SwiftUI

struct PinManagementView: View {
    @EnvironmentObject private var pinManager: PinManager
    @Environment(\.dismiss) private var dismiss
    @StateObject private var vm = PinManagementViewModel()
    var focusType: String? = nil

    private var orderedTypes: [String] {
        focusType == "future" ? ["future", "event"] : ["event", "future"]
    }

    var body: some View {
        NavigationStack {
            List {
                if pinManager.loadState == .loading {
                    HStack { ProgressView(); Text("Loading saved pins…") }
                } else if pinManager.loadState == .failed {
                    Section {
                        Text("Couldn't refresh your saved pins. Known pins are shown below; you can still remove them.")
                            .foregroundStyle(.secondary)
                        Button("Retry saved pins") { Task { await pinManager.loadPins() } }
                    }
                }
                if let feedback = pinManager.feedback {
                    Text(feedback.message)
                        .foregroundStyle(feedback.isWarning ? .orange : .secondary)
                        .accessibilityIdentifier("pinManagementFeedback")
                }
                ForEach(orderedTypes, id: \.self) { type in
                    let pins = pinManager.savedPins.filter { $0.type == type }
                    Section(type == "event" ? "Games (\(pins.count))" : "Markets (\(pins.count))") {
                        if pins.isEmpty {
                            Text(pinManager.loadState == .loaded || pinManager.loadState == .local
                                 ? "No saved \(type == "event" ? "games" : "markets")"
                                 : "Saved \(type == "event" ? "games" : "markets") have not loaded yet")
                                .foregroundStyle(.secondary)
                        }
                        ForEach(pins) { pin in pinRow(pin) }
                    }
                }
            }
            .navigationTitle("Manage pins")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
            .navigationDestination(for: Route.self) { RouteDestination(route: $0) }
        }
        .task { await pinManager.loadPins() }
        .task(id: pinManager.savedPins) { await vm.load(pinManager.savedPins) }
        .onChange(of: pinManager.identityGeneration) { _, _ in dismiss() }
    }

    private func pinRow(_ pin: SavedPin) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                if case .available(let title) = vm.metadata[pin] {
                    NavigationLink(value: pin.type == "event"
                                   ? Route.eventDetail(id: pin.value) : Route.futuresDetail(id: pin.value)) {
                        Text(title).font(.body.weight(.medium))
                    }
                } else {
                    Text(pin.fallbackTitle).font(.body.weight(.medium))
                    switch vm.metadata[pin] {
                    case .unavailable:
                        Text("Details are no longer available. You can remove this pin.")
                            .font(.caption).foregroundStyle(.secondary)
                    case .failed:
                        Text("Couldn't load details. You can still remove this pin.")
                            .font(.caption).foregroundStyle(.secondary)
                        Button("Retry details") { Task { await vm.load(pinManager.savedPins, retryFailed: true) } }
                            .font(.caption)
                    default:
                        Text("Loading details…").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            Spacer(minLength: 0)
            Button {
                pinManager.togglePin(type: pin.type, id: pin.value)
            } label: {
                if pinManager.isSaving(type: pin.type, id: pin.value) {
                    ProgressView().controlSize(.small)
                } else {
                    Text("Remove")
                }
            }
            .buttonStyle(.bordered)
            .disabled(pinManager.isSaving(type: pin.type, id: pin.value))
            .accessibilityLabel("Remove \(pin.fallbackTitle)")
            .accessibilityIdentifier("removePin.\(pin.id)")
        }
        .accessibilityIdentifier("savedPin.\(pin.id)")
    }
}
