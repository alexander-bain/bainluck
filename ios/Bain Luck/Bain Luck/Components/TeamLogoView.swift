import SwiftUI

/// Async team logo image with colored-initial fallback.
struct TeamLogoView: View {
    let url: String?
    let teamName: String
    let color: Color
    var size: CGFloat = 28

    var body: some View {
        if let url, let imageURL = URL(string: url) {
            AsyncImage(url: imageURL) { phase in
                switch phase {
                case .success(let image):
                    image.resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: size, height: size)
                case .failure:
                    initialsFallback
                default:
                    Circle()
                        .fill(color.opacity(0.15))
                        .frame(width: size, height: size)
                }
            }
        } else {
            initialsFallback
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
