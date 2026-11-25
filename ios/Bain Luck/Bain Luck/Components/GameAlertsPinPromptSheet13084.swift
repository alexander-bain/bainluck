import SwiftUI

/// #13084 (Rulings 212: A, 261: A, 262: A) — contextual opt-in ask shown once
/// when a reader pins their first game and system notification permission is still
/// `.notDetermined`. Never mentions APNs, tokens, Live Activity plumbing, or accounts.
struct GameAlertsPinPromptSheet13084: View {
    let onTurnOn: @MainActor () async -> Void
    let onNotNow: @MainActor () -> Void

    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme
    @State private var isRequesting = false
    @State private var choiceHandled = false

    static let titleCopy = "Get alerts for games you pin?"
    static let bodyCopy = "We can buzz you when a pinned game starts, when it is close late, and when it goes final. You can change this anytime in Preferences."
    static let turnOnTitle = "Turn on"
    static let notNowTitle = "Not now"

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                Image(systemName: "bell.badge.fill")
                    .font(.system(size: 32, weight: .semibold))
                    .foregroundStyle(DS.emerald)
                    .padding(16)
                    .background(DS.emerald.opacity(0.14), in: Circle())
                    .accessibilityHidden(true)

                VStack(spacing: 8) {
                    Text(Self.titleCopy)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.primary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)

                    Text(Self.bodyCopy)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }

                VStack(spacing: 10) {
                    Button {
                        guard !isRequesting else { return }
                        choiceHandled = true
                        isRequesting = true
                        Task { @MainActor in
                            await onTurnOn()
                            isRequesting = false
                            dismiss()
                        }
                    } label: {
                        HStack(spacing: 8) {
                            if isRequesting {
                                ProgressView()
                                    .controlSize(.small)
                            }
                            Text(Self.turnOnTitle)
                                .font(.body.weight(.semibold))
                                .multilineTextAlignment(.center)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .foregroundStyle(colorScheme == .dark ? Color(hex: "#0F172A") : .white)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(DS.greenReadable, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .disabled(isRequesting)
                    .accessibilityIdentifier("gameAlertsPrompt.turnOn")

                    Button {
                        guard !isRequesting else { return }
                        choiceHandled = true
                        onNotNow()
                        dismiss()
                    } label: {
                        Text(Self.notNowTitle)
                            .font(.body.weight(.medium))
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, minHeight: 44)
                    }
                    .buttonStyle(.plain)
                    .disabled(isRequesting)
                    .accessibilityIdentifier("gameAlertsPrompt.notNow")
                }
                .padding(.top, 4)
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 24)
            .frame(maxWidth: .infinity)
        }
        .scrollBounceBehavior(.basedOnSize)
        .onDisappear {
            if !choiceHandled {
                choiceHandled = true
                onNotNow()
            }
        }
    }
}
