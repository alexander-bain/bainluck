import SwiftUI

/// The native equivalent of the web consent banner (Queue 311 A3, ruling 007 / #1632).
///
/// This exists because deny-by-default without an ask is not a consent model —
/// it is just "off forever". The web has `consentBanner.ts`; native had nothing,
/// because native had no consent state to ask about.
///
/// Deliberate choices, both mirroring the web:
///  - **Neither button is styled as the safe one.** Decline is not a muted
///    footnote next to a bright Allow. A choice architecture that makes refusal
///    look like a mistake collects agreement rather than consent.
///  - **It cannot be dismissed into limbo.** There is no X and no
///    tap-outside-to-close; a swipe-down still leaves the state at "no choice",
///    which is a DENIAL and re-asks next launch. Nothing is collected in the
///    meantime, so an unanswered prompt is safe by construction.
struct TelemetryConsentPrompt: View {
    /// Called once a choice is recorded, with the resulting durability.
    var onChoice: (ConsentPersistence) -> Void

    var body: some View {
        GeometryReader { proxy in
            ScrollView {
                VStack(spacing: 0) {
                    Spacer(minLength: 0)

                    VStack(spacing: 18) {
                        BainLuckMarkView(size: 44)

                        Text("Help us find what\u{2019}s broken?")
                            .font(.title3.weight(.bold))
                            .foregroundStyle(DS.textPrimary)
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)

                        Text(
                            "We can collect anonymous usage stats \u{2014} which screens are slow, "
                            + "what crashes. No names, no emails, and never what you search for."
                        )
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)

                        Text(AnonymousLifecycleCounts424A.privacyDisclosureSentence)
                            .font(.footnote)
                            .foregroundStyle(DS.textSecondaryReadable)
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)

                        VStack(spacing: 10) {
                            Button {
                                choose(.analytics)
                            } label: {
                                Text("Allow")
                                    .font(.body.weight(.semibold))
                                    .fixedSize(horizontal: false, vertical: true)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 14)
                                    .background(DS.blueReadable)
                                    .foregroundStyle(DS.textOnAccent)
                                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                            }
                            .buttonStyle(.plain)

                            Button {
                                choose(.none)
                            } label: {
                                Text("No thanks")
                                    .font(.body.weight(.semibold))
                                    .fixedSize(horizontal: false, vertical: true)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 14)
                                    .background(DS.trackBg)
                                    .foregroundStyle(DS.textPrimary)
                                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                                            .stroke(DS.border, lineWidth: 1)
                                    )
                            }
                            .buttonStyle(.plain)
                        }

                        Text("You can change this any time in Preferences.")
                            .font(.caption2)
                            .foregroundStyle(DS.textSecondaryReadable)
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(24)
                    .frame(maxWidth: 460)
                    .background(DS.cardBg)
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .stroke(DS.border, lineWidth: 1)
                    )
                    .padding(24)

                    Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity, minHeight: proxy.size.height)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
        .background(DS.surface.ignoresSafeArea())
        .interactiveDismissDisabled()
    }

    private func choose(_ level: ConsentLevel) {
        onChoice(TelemetryConsent.shared.set(level))
    }
}
