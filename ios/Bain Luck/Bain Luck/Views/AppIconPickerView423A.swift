#if os(iOS)
import SwiftUI

/// Rounded preview thumbnail of an icon choice (`AppIconPreview*`).
/// Original artwork supplied by Alex.
struct AppIconPreviewBadge423A: View {
    let choice: AppIconChoice423A
    var size: CGFloat

    var body: some View {
        let cornerRadius = size * 0.225
        Image(choice.previewAssetName)
            .resizable()
            .interpolation(.high)
            .aspectRatio(1, contentMode: .fill)
            .frame(width: size, height: size)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(Color.barTrack.opacity(0.6), lineWidth: 0.5)
            )
            .accessibilityHidden(true)
    }
}

/// Settings -> App icon picker list (#13767, ruling 423: A).
struct AppIconPickerView423A: View {
    private let switcher: AppIconSwitcher423A
    private let onSelectChoice: ((AppIconChoice423A) -> Void)?

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var selectedChoice: AppIconChoice423A
    @State private var applyingChoice: AppIconChoice423A?
    @State private var errorMessage: String?

    init(
        switcher: AppIconSwitcher423A = .live,
        onSelectChoice: ((AppIconChoice423A) -> Void)? = nil
    ) {
        self.switcher = switcher
        self.onSelectChoice = onSelectChoice
        _selectedChoice = State(initialValue: switcher.activeChoice)
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                ForEach(AppIconChoice423A.allCases) { choice in
                    choiceRow(choice)
                }

                if let errorMessage {
                    Text(errorMessage)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 4)
                        .accessibilityIdentifier("appIconPicker.error")
                }
            }
            .padding()
            .frame(maxWidth: PreferencesView.readableDetailMaxWidth)
            .frame(maxWidth: .infinity)
        }
        .background(Color.groupedBackground)
        .navigationTitle("App icon")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .onAppear {
            selectedChoice = switcher.activeChoice
        }
    }

    private func choiceRow(_ choice: AppIconChoice423A) -> some View {
        let isSelected = selectedChoice == choice
        let isApplying = applyingChoice == choice

        return Button {
            select(choice)
        } label: {
            Group {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            AppIconPreviewBadge423A(choice: choice, size: 52)
                            Spacer(minLength: 8)
                            selectionIndicator(isSelected: isSelected, isApplying: isApplying)
                        }
                        Text(choice.displayName)
                            .font(.body.weight(.medium))
                            .foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                            .multilineTextAlignment(.leading)
                    }
                } else {
                    HStack(spacing: 14) {
                        AppIconPreviewBadge423A(choice: choice, size: 48)

                        Text(choice.displayName)
                            .font(.body.weight(.medium))
                            .foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                            .multilineTextAlignment(.leading)

                        Spacer(minLength: 8)

                        selectionIndicator(isSelected: isSelected, isApplying: isApplying)
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(
                        isSelected ? Color.accentColor.opacity(0.45) : Color.barTrack.opacity(0.4),
                        lineWidth: isSelected ? 1 : 0.5
                    )
            )
            .shadow(color: .black.opacity(0.03), radius: 4, x: 0, y: 2)
        }
        .buttonStyle(.plain)
        .disabled(applyingChoice != nil)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityIdentifier("appIconPicker.option.\(choice.rawValue)")
    }

    @ViewBuilder
    private func selectionIndicator(isSelected: Bool, isApplying: Bool) -> some View {
        if isApplying {
            ProgressView()
                .controlSize(.small)
        } else if isSelected {
            Image(systemName: "checkmark.circle.fill")
                .font(.title3)
                .foregroundStyle(Color.accentColor)
        }
    }

    private func select(_ choice: AppIconChoice423A) {
        guard applyingChoice == nil, selectedChoice != choice else { return }
        applyingChoice = choice
        errorMessage = nil
        Task { @MainActor in
            do {
                let confirmed = try await switcher.select(choice)
                selectedChoice = confirmed
                onSelectChoice?(confirmed)
            } catch {
                selectedChoice = switcher.activeChoice
                errorMessage = "Couldn't switch the app icon right now."
            }
            applyingChoice = nil
        }
    }
}
#endif
