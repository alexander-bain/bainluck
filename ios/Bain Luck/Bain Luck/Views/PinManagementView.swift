import SwiftUI
#if os(iOS)
import UserNotifications
#endif

struct PinManagementView: View {
    @EnvironmentObject private var pinManager: PinManager
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    #if os(iOS)
    @State private var gameAlertsEnabled = GameAlertsPreference13083.shared.isEnabled
    @State private var notificationAuthStatus: UNAuthorizationStatus = .notDetermined
    #if DEBUG
    @State private var pinGameAlertsStateForTest = false
    #endif
    #endif
    #if DEBUG
    @StateObject private var vm = PinManagementView.makeViewModel()

    private static func makeViewModel() -> PinManagementViewModel {
        if let runtime = PinManagementRuntime9875.shared {
            return PinManagementViewModel(lookup: { pin in await runtime.lookup(pin) })
        }
        return PinManagementViewModel()
    }
    #else
    @StateObject private var vm = PinManagementViewModel()
    #endif
    var focusType: String? = nil

    init(focusType: String? = nil) {
        self.focusType = focusType
    }

    #if DEBUG && os(iOS)
    init(
        focusType: String? = nil,
        gameAlertsEnabledForTest: Bool,
        notificationAuthStatusForTest: UNAuthorizationStatus
    ) {
        self.focusType = focusType
        _gameAlertsEnabled = State(initialValue: gameAlertsEnabledForTest)
        _notificationAuthStatus = State(initialValue: notificationAuthStatusForTest)
        _pinGameAlertsStateForTest = State(initialValue: true)
    }
    #endif

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
                #if os(iOS)
                Section("Notifications") {
                    Toggle(isOn: Binding(
                        get: { gameAlertsEnabled },
                        set: { enabled in
                            gameAlertsEnabled = enabled
                            if enabled {
                                Task {
                                    notificationAuthStatus = await GameAlertsPreference13083.shared.optInAndRequestPermission()
                                }
                            } else {
                                GameAlertsPreference13083.shared.setEnabled(false)
                            }
                        }
                    )) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Game alerts")
                                .font(.body.weight(.medium))
                                .fixedSize(horizontal: false, vertical: true)
                            Text(GameAlertsPreference13083.subtitle)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .tint(Color.accentColor)
                    .accessibilityIdentifier("pinManagement.gameAlertsToggle")

                    if gameAlertsEnabled && notificationAuthStatus == .denied {
                        Button {
                            GameAlertsPreference13083.openAppNotificationSettings()
                        } label: {
                            HStack(alignment: .center, spacing: 8) {
                                Text(GameAlertsPreference13083.settingsOffActionTitle)
                                    .font(.caption.weight(.medium))
                                    .foregroundStyle(Color.orange)
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 4)
                                Image(systemName: "chevron.right")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(Color.orange)
                            }
                        }
                        .accessibilityIdentifier("pinManagement.gameAlertsOpenSettings")
                    }
                }
                #endif
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
        #if DEBUG
        .safeAreaInset(edge: .bottom) {
            if let runtime = PinManagementRuntime9875.shared {
                PinRuntime9875Controls(runtime: runtime, manager: pinManager)
            }
        }
        #endif
        .task {
            #if os(iOS)
            #if DEBUG
            if !pinGameAlertsStateForTest {
                gameAlertsEnabled = GameAlertsPreference13083.shared.isEnabled
                notificationAuthStatus = await NotificationManager.shared.notificationAuthorizationStatus()
            }
            #else
            gameAlertsEnabled = GameAlertsPreference13083.shared.isEnabled
            notificationAuthStatus = await NotificationManager.shared.notificationAuthorizationStatus()
            #endif
            #endif
            await pinManager.loadPins()
        }
        #if os(iOS)
        .onChange(of: scenePhase) { _, phase in
            guard phase == .active else { return }
            #if DEBUG
            guard !pinGameAlertsStateForTest else { return }
            #endif
            Task {
                notificationAuthStatus = await NotificationManager.shared.notificationAuthorizationStatus()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .gameAlertsPreferenceDidChange13083)) { _ in
            #if DEBUG
            guard !pinGameAlertsStateForTest else { return }
            #endif
            gameAlertsEnabled = GameAlertsPreference13083.shared.isEnabled
        }
        #endif
        .task(id: pinManager.savedPins) { await vm.load(pinManager.savedPins) }
        .onChange(of: pinManager.identityGeneration) { _, _ in dismiss() }
    }

    private func pinRow(_ pin: SavedPin) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                if case .available = vm.metadata[pin] {
                    NavigationLink(value: pin.type == "event"
                                   ? Route.eventDetail(id: pin.value) : Route.futuresDetail(id: pin.value)) {
                        Text(pin.displayTitle(for: vm.metadata[pin])).font(.body.weight(.medium))
                    }
                } else {
                    Text(pin.displayTitle(for: vm.metadata[pin])).font(.body.weight(.medium))
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
            .accessibilityLabel(pin.removeLabel(for: vm.metadata[pin]))
            .accessibilityIdentifier("removePin.\(pin.id)")
        }
        .accessibilityIdentifier("savedPin.\(pin.id)")
    }
}
