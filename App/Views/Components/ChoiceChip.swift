import SwiftUI

/// A selectable capsule. Selected = filled accent, so it reads across a room.
struct ChoiceChip<Label: View>: View {
    @Environment(\.colorScheme) private var colorScheme
    let isSelected: Bool
    let action: () -> Void
    @ViewBuilder let label: Label

    /// Accent is dark teal in light mode and light mint in dark mode.
    private var selectedForeground: Color { colorScheme == .dark ? .black : .white }

    var body: some View {
        Button(action: action) {
            label
                .font(.subheadline.weight(.semibold))
                .padding(.horizontal, 14)
                .frame(minHeight: 44)
                .foregroundStyle(isSelected ? AnyShapeStyle(selectedForeground) : AnyShapeStyle(.primary))
                .background(isSelected ? AnyShapeStyle(.tint) : AnyShapeStyle(.fill.quaternary), in: .capsule)
                .overlay {
                    if !isSelected {
                        Capsule().strokeBorder(.separator, lineWidth: 1)
                    }
                }
                .contentShape(.capsule)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}
