import SwiftUI

/// One story on the map. Colour = category, size = relevance, accent ring = must-see or high relevance, dashed = opinion.
/// Stories with a 3D map object get a raised tile instead of a round pin. `count > 1` = stories grouped under this pin.
struct StoryPin: View {
    let story: Story
    let item: FeedItem
    let label: String
    let isSelected: Bool
    var count = 1
    /// Labels for ordinary stories only at Area and City. Farther out, only a must-see or the selected pin is named.
    var scale: Scale = .city

    private var diameter: CGFloat { 30 + 18 * item.relevance }
    private var showsLabel: Bool {
        if isSelected || item.mustSee { return true }
        switch scale {
        case .area, .city: return item.relevance >= 0.5
        case .finland, .world: return false
        }
    }
    private var isHighlighted: Bool { item.mustSee || item.relevance >= 0.7 }

    var body: some View {
        VStack(spacing: 4) {
            Group {
                if let object = story.mapObject {
                    RaisedTile(symbolName: object.symbolName, color: story.category.mapColor, size: diameter + 6)
                } else {
                    badge
                }
            }
            .overlay(alignment: .topTrailing) {
                if count > 1 {
                    Text(count, format: .number)
                        .font(.caption2.bold())
                        .foregroundStyle(.white)
                        .frame(minWidth: 20, minHeight: 20)
                        .background(.black.opacity(0.75), in: .capsule)
                        .offset(x: 6, y: -6)
                        .accessibilityLabel(Text("\(count) stories here"))
                }
            }
            if showsLabel {
                Text(verbatim: label)
                    .font(.caption.weight(.semibold))
                    .lineLimit(1)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(.regularMaterial, in: .capsule)
            }
        }
        .scaleEffect(isSelected ? 1.15 : 1)
        .animation(.snappy, value: isSelected)
    }

    private var badge: some View {
        Image(systemName: story.category.symbolName)
            .font(.system(size: diameter * 0.45, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: diameter, height: diameter)
            .background(story.category.mapColor.gradient, in: .circle)
            .overlay {
                if story.isOpinion {
                    Circle().strokeBorder(.white, style: StrokeStyle(lineWidth: 2, dash: [4, 3]))
                }
            }
            .padding(2.5)
            .background(.white, in: .circle)
            .padding(isHighlighted ? 3 : 0)
            .overlay {
                if isHighlighted {
                    Circle().strokeBorder(.tint, lineWidth: 3)
                }
            }
            .shadow(color: .black.opacity(0.25), radius: 4, y: 2)
    }
}

/// A tile with a visible side, so it reads as an object standing on the map.
private struct RaisedTile: View {
    let symbolName: String
    let color: Color
    let size: CGFloat

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.22)
                .fill(color.mix(with: .black, by: 0.35))
                .offset(y: size * 0.14)
            RoundedRectangle(cornerRadius: size * 0.22)
                .fill(color.gradient)
                .overlay {
                    RoundedRectangle(cornerRadius: size * 0.22)
                        .strokeBorder(.white.opacity(0.9), lineWidth: 2)
                }
            Image(systemName: symbolName)
                .font(.system(size: size * 0.45, weight: .semibold))
                .foregroundStyle(.white)
        }
        .frame(width: size, height: size)
        .rotation3DEffect(.degrees(28), axis: (x: 1, y: 0, z: 0), perspective: 0.6)
        .shadow(color: .black.opacity(0.3), radius: 6, y: 5)
    }
}
