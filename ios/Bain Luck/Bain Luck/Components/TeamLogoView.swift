import SwiftUI

/// Async team logo image with cached loading and colored-initial fallback.
struct TeamLogoView: View {
    let url: String?
    let teamName: String
    let color: Color
    var size: CGFloat = 28

    @State private var image: UIImage?
    @State private var loadFailed = false

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: size, height: size)
            } else if loadFailed || url == nil {
                initialsFallback
            } else {
                Circle()
                    .fill(color.opacity(0.15))
                    .frame(width: size, height: size)
            }
        }
        .task(id: url) {
            guard let url, let imageURL = URL(string: url) else {
                loadFailed = true
                return
            }
            image = await ImageCache.shared.image(for: imageURL)
            if image == nil { loadFailed = true }
        }
    }

    private var initialsFallback: some View {
        ZStack {
            Circle()
                .fill(color.opacity(0.2))
            Text(String(teamName.prefix(1)).uppercased())
                .font(.system(size: size * 0.45, weight: .bold))
                .foregroundStyle(color)
        }
        .frame(width: size, height: size)
    }
}
