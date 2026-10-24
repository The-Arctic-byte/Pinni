import SwiftUI

/// One story on the map. The category icon is always shown, with a stem down to a dot on the place.
/// A short label is added when the story is worth reading at this scale. A number appears only when
/// several stories share the pin. Accent border = must-see or high relevance, dashed = opinion.
struct StoryPin: View {
    let story: Story
    let item: FeedItem
    let label: String
    let isSelected: Bool
    var count = 1
    /// Labels for ordinary stories only at Area and City. Farther out, only a must-see or the selected pin is named.
    var scale: Scale = .city

    private var showsLabel: Bool {
        if isSelected || item.mustSee { return true }
        switch scale {
        case .area, .city: return item.relevance >= 0.5
        case .finland, .world: return false
        }
    }
    private var isHighlighted: Bool { item.mustSee || item.relevance >= 0.7 }
    private var isQuiet: Bool { item.relevance < 0.3 && !isSelected }
    private var symbolName: String { story.mapObject?.symbolName ?? story.category.symbolName }
    private var color: Color { story.category.mapColor }

    var body: some View {
        VStack(spacing: 0) {
            bubble
            stem(height: showsLabel ? 16 : 10)
            dot
        }
        .opacity(isQuiet ? 0.62 : 1)
        .scaleEffect(isSelected ? 1.05 : 1)
        .animation(.snappy, value: isSelected)
    }

    /// The category icon is always there. The words are only for a story worth reading at this scale,
    /// and the number only when several stories share the pin.
    private var bubble: some View {
        HStack(spacing: 6) {
            Image(systemName: symbolName)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 26, height: 26)
                .background(color.gradient, in: .circle)
            if showsLabel {
                Text(verbatim: label)
                    .font(.caption.weight(.bold))
                    .lineLimit(1)
                    .frame(maxWidth: 150, alignment: .leading)
            }
            if count > 1 { countBadge() }
        }
        .padding(.leading, 3)
        .padding(.trailing, showsLabel || count > 1 ? 8 : 3)
        .padding(.vertical, 3)
        .background(.regularMaterial, in: .capsule)
        .overlay { Capsule().strokeBorder(borderColor, style: borderStyle) }
        .shadow(color: .black.opacity(0.16), radius: 5, y: 3)
    }

    private func stem(height: CGFloat) -> some View {
        Capsule()
            .fill(color)
            .frame(width: 2, height: height)
    }

    private var dot: some View {
        Circle()
            .fill(color)
            .frame(width: 9, height: 9)
            .background {
                if isHighlighted {
                    Circle().fill(Color.accentColor.opacity(0.28)).frame(width: 20, height: 20)
                }
            }
            .frame(width: 9, height: 9)
    }

    private func countBadge() -> some View {
        Text(count, format: .number)
            .font(.caption2.bold())
            .foregroundStyle(.white)
            .frame(minWidth: 16, minHeight: 16)
            .background(.black.opacity(0.75), in: .circle)
            .accessibilityLabel(Text("\(count) stories here"))
    }

    private var borderColor: Color { isHighlighted ? Color.accentColor : Color.primary.opacity(0.14) }

    private var borderStyle: StrokeStyle {
        StrokeStyle(lineWidth: isHighlighted ? 2 : 1, dash: story.isOpinion ? [4, 3] : [])
    }
}
