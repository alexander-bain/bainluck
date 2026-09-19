import SwiftUI

/// The top-of-feed row that tells a pull reader how their pull ended (#7074).
///
/// Chrome only. Every claim this surface makes — which phases speak, in what
/// words, which decays, which carries the retry — is made by
/// ``DiscoverPullRefreshNotice``, where a test can call it. A view body
/// returning `some View` cannot be, which is why nothing is decided here.
///
/// It is a ROW and not a card on purpose: it sits above the first card at the
/// top of Discover, it is transient on success, and a full card there would push
/// the feed down by a card's height every time a refresh landed — a reader who
/// pulled to see new markets would be shown less of them.
struct DiscoverPullRefreshNoticeRow: View {
    let notice: DiscoverPullRefreshNotice

    /// Invoked by the retry control. Never called for a notice whose
    /// `offersRetry` is false — the control is not drawn at all.
    let onRetry: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: notice.systemImage)
                .font(.footnote)
                .foregroundStyle(notice.offersRetry ? Color.orange : Color.green)
            Text(notice.text)
                .font(.footnote.weight(.medium))
                .foregroundStyle(.primary)
            Spacer(minLength: 8)
            if notice.offersRetry {
                Button("Try again", action: onRetry)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(Color.blue)
                    .frame(minHeight: 44)
                    .buttonStyle(.plain)
                    .accessibilityIdentifier(DiscoverPullRefreshNotice.retryIdentifier)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.barTrack.opacity(0.45), lineWidth: 1)
        )
        // One element to VoiceOver, not three: the glyph, the line and the
        // button read as one announcement of one outcome. The retry keeps its
        // own action because `.accessibilityElement(children: .combine)` would
        // otherwise swallow the only thing on this row a reader can do.
        .accessibilityElement(children: .combine)
        .accessibilityLabel(notice.accessibilityLabel)
        .accessibilityIdentifier(DiscoverPullRefreshNotice.identifier)
    }
}
