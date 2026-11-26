import SwiftUI
#if os(iOS)
import UIKit
#endif

/// Like heart button shown on every Discover card type (#13769, ruling 420: D).
struct DiscoverLikeButton420D: View {
    let isLiked: Bool
    let action: () -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let hPad: CGFloat = dynamicTypeSize.isAccessibilitySize ? 8 : 10
        Button {
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
            action()
        } label: {
            HStack(spacing: 5) {
                Image(systemName: isLiked ? "heart.fill" : "heart")
                    .font(.subheadline.weight(.semibold))
                Text(isLiked ? "Liked" : "Like")
                    .font(.caption.weight(.semibold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .fixedSize(horizontal: true, vertical: false)
            }
            .foregroundStyle(isLiked ? Color.red : DS.textSecondaryReadable)
            .padding(.horizontal, hPad)
            .padding(.vertical, 7)
            .background(
                isLiked ? Color.red.opacity(0.12) : Color.secondary.opacity(0.10),
                in: Capsule()
            )
            .frame(minWidth: 44, minHeight: 44)
            .fixedSize(horizontal: true, vertical: false)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(isLiked ? "Liked" : "Like")
        .accessibilityHint(isLiked ? "Takes back your like" : "Likes this card")
        .accessibilityAddTraits(isLiked ? [.isButton, .isSelected] : .isButton)
        .accessibilityIdentifier("discover.card.likeButton")
    }
}

/// Unified bottom action row (`Like` heart beside `Pin` and `Share`) rendered inside
/// Discover cards that do not already host an inline Pin/Share footer (#13769).
struct DiscoverCardActionBar420D: View {
    let actions: DiscoverCardLikeAction420D
    var topDivider: Bool = true
    var horizontalPadding: CGFloat = 14
    var verticalPadding: CGFloat = 10
    var surfaceColor: Color? = nil

    var body: some View {
        VStack(spacing: 0) {
            if topDivider {
                Divider()
            }
            HStack(spacing: 4) {
                DiscoverLikeButton420D(isLiked: actions.isLiked, action: actions.onToggle)

                Spacer(minLength: 6)

                if let pinType = actions.pinType, let pinId = actions.pinId {
                    PinButton(type: pinType, id: pinId)
                        .fixedSize(horizontal: true, vertical: false)
                }

                if let shareURL = actions.shareURL {
                    let shareTitle = actions.shareTitle ?? "Bain Luck"
                    let shareMessage = actions.shareMessage ?? shareTitle
                    ShareLink(
                        item: shareURL,
                        subject: Text(shareTitle),
                        message: Text(shareMessage)
                    ) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(DS.textSecondaryReadable)
                            .padding(8)
                            .background(Color.secondary.opacity(0.10), in: Circle())
                            .frame(minWidth: 44, minHeight: 44)
                            .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
                    .recordsShareOpened { actions.onShare?() }
                    .accessibilityLabel("Share")
                }
            }
            .padding(.horizontal, horizontalPadding)
            .padding(.vertical, verticalPadding)
            .background(surfaceColor ?? Color.clear)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("discover.card.actionBar420D")
    }
}
