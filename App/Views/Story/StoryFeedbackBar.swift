import SwiftUI

/// The reader's feedback on a story: like, dislike, not for me, share, and "Something wrong?".
/// Every action is an event for the recommender; "not for me" and reactions also show right away.
struct StoryFeedbackBar: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let story: Story
    @State private var asksNotForMe = false
    @State private var reportsProblem = false
    @State private var postsToChannel = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                reactionButton(.like, title: "Like", symbol: "hand.thumbsup")
                reactionButton(.dislike, title: "Dislike", symbol: "hand.thumbsdown")
                Button("Not for me", systemImage: "eye.slash") { asksNotForMe = true }
                ShareLink(item: story.title.text(for: model.contentLanguage)) {
                    Label("Share", systemImage: "square.and.arrow.up")
                }
                .simultaneousGesture(TapGesture().onEnded { model.shared(story) })
            }
            .labelStyle(.iconOnly)
            .buttonStyle(.bordered)
            .controlSize(.large)

            HStack(spacing: 20) {
                Button("Post to a channel", systemImage: "bubble.left.and.text.bubble.right") { postsToChannel = true }
                Button("Something wrong?", systemImage: "flag") { reportsProblem = true }
            }
            .buttonStyle(.borderless)
        }
        .confirmationDialog("Not for me", isPresented: $asksNotForMe, titleVisibility: .visible) {
            Button("Hide this story") { hide(wholeCategory: false) }
            Button("Hide all \(Text(story.category.title)) news") { hide(wholeCategory: true) }
        } message: {
            Text("Important safety news still reaches you.")
        }
        .sheet(isPresented: $reportsProblem) {
            ReportForm(draft: .problem(with: story), story: story)
        }
        .sheet(isPresented: $postsToChannel) {
            ShareToChannelSheet(story: story)
        }
    }

    private func reactionButton(_ reaction: AppModel.Reaction, title: LocalizedStringKey, symbol: String) -> some View {
        let isOn = model.reaction(to: story.id) == reaction
        return Button {
            model.react(reaction, to: story)
        } label: {
            Label(title, systemImage: isOn ? symbol + ".fill" : symbol)
        }
        .tint(isOn ? Color.accentColor : nil)
        .accessibilityAddTraits(isOn ? .isSelected : [])
    }

    private func hide(wholeCategory: Bool) {
        Task {
            await model.hide(story, wholeCategory: wholeCategory)
            dismiss()
        }
    }
}
