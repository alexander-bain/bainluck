import AppKit
import SwiftUI

struct MarkPreview: Decodable {
    struct Row: Decodable {
        let title: String
        let text: String
        let number: Double?
        let mark: SourceMark
    }

    struct Card: Decodable {
        let title: String
        let rows: [Row]
    }

    let title: String
    let context: String
    let cards: [Card]
    let sheetTitle: String
    let sheetRow: Row
}

@main
struct RenderMarkPreview {
    @MainActor
    static func main() throws {
        let input = URL(fileURLWithPath: CommandLine.arguments[1])
        let output = URL(fileURLWithPath: CommandLine.arguments[2])
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let preview = try decoder.decode(MarkPreview.self, from: Data(contentsOf: input))
        let sheet = preview.sheetRow
        let content = VStack(alignment: .leading, spacing: 16) {
            Text(preview.title).font(.headline)
            Text(preview.context).font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(Array(preview.cards.enumerated()), id: \.offset) { _, card in
                VStack(alignment: .leading, spacing: 12) {
                    Text(card.title).font(.headline).fixedSize(horizontal: false, vertical: true)
                    ForEach(Array(card.rows.enumerated()), id: \.offset) { _, row in
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(row.title).fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 6)
                            Text(row.text).bold().monospacedDigit()
                            SourceMarkButton(row.mark, number: row.number, numberSize: 17)
                        }
                    }
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.primary.opacity(0.035))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            Divider()
            Text(preview.sheetTitle).font(.subheadline).bold()
                .fixedSize(horizontal: false, vertical: true)
            Text(SourceMarkSheet.title).font(.headline)
            if let headline = SourceMarkSheet.headline(sheet.number) {
                Text(headline).font(.system(size: 40, weight: .bold)).monospacedDigit()
            }
            SourceMarkSheet(mark: sheet.mark, number: sheet.number).rows
            if let method = SourceMarkSheet.method(sheet.mark) {
                Text(method).font(.footnote).foregroundStyle(.secondary)
            }
        }
        .padding(20)
        .frame(width: 390, alignment: .leading)
        .background(Color.white)
        .environment(\.colorScheme, .light)
        let renderer = ImageRenderer(content: content)
        renderer.scale = 2
        guard let image = renderer.nsImage, let tiff = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff),
              let data = bitmap.representation(using: .png, properties: [:]) else {
            fatalError("Preview could not be rendered")
        }
        try data.write(to: output)
    }
}
