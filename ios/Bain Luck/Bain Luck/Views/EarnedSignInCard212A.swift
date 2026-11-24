import SwiftUI

/// Step 5 (`212-A`, #11934): Non-blocking sign-in offer shown in `My Stuff` only after
/// the reader has already followed or pinned something locally.
///
/// Honest value pitch:
/// - Does NOT claim Watch needs sign-in (`1.0.7` sends pins to Watch locally).
/// - Uses singular `"a new phone"` per Alex's feedback.
/// - Offers `"Keep on this iPhone only"` so readers stay in control without an account.
struct EarnedSignInCard212A: View {
    @Environment(\.colorScheme) private var colorScheme

    let onAppleSignIn: () -> Void
    let onGoogleSignIn: () -> Void
    let onDismissLocalOnly: () -> Void
    var isSigningIn: Bool = false
    var errorMessage: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("SYNC ACROSS DEVICES")
                .font(.caption2.weight(.bold))
                .tracking(0.8)
                .foregroundStyle(DS.blueReadable)

            Text("Keep your pins on iPad, the web, and a new phone")
                .font(.title3.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            Text("Your pins and alerts already work on this iPhone and paired Watch without an account. Sign in only to:")
                .font(.footnote)
                .foregroundStyle(DS.textSecondaryReadable)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 6) {
                bulletRow("Open your pins on iPad, bainluck.com, and a new phone")
                bulletRow("Restore your pins if you replace this iPhone")
            }

            VStack(spacing: 10) {
                Button(action: onAppleSignIn) {
                    HStack(spacing: 8) {
                        Image(systemName: "apple.logo")
                        Text("Continue with Apple")
                            .font(.subheadline.weight(.semibold))
                    }
                    .frame(maxWidth: .infinity, minHeight: 46)
                    .foregroundStyle(colorScheme == .dark ? Color(hex: "#0F172A") : .white)
                    .background(DS.textPrimary, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(.plain)
                .disabled(isSigningIn)
                .accessibilityIdentifier("earnedSignIn212A.apple")

                Button(action: onGoogleSignIn) {
                    HStack(spacing: 8) {
                        Image(systemName: "g.circle.fill")
                        Text("Continue with Google")
                            .font(.subheadline.weight(.semibold))
                    }
                    .frame(maxWidth: .infinity, minHeight: 46)
                    .foregroundStyle(DS.textPrimary)
                    .background(DS.trackBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .stroke(DS.border, lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
                .disabled(isSigningIn)
                .accessibilityIdentifier("earnedSignIn212A.google")

                if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Button(action: onDismissLocalOnly) {
                    Text("Keep on this iPhone only")
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .frame(maxWidth: .infinity, minHeight: 36)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("earnedSignIn212A.keepOnIphone")
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(DS.blueReadable.opacity(colorScheme == .dark ? 0.40 : 0.25), lineWidth: 1)
        )
        .accessibilityIdentifier("earnedSignInCard212A")
    }

    private func bulletRow(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "checkmark")
                .font(.caption.weight(.bold))
                .foregroundStyle(DS.greenReadable)
                .padding(.top, 2)
            Text(text)
                .font(.footnote)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
