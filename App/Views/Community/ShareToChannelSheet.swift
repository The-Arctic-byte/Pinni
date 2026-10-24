import SwiftUI

/// Post a story to one of the reader's channels, with an optional comment.
struct ShareToChannelSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let story: Story
    @State private var channelId: String?
    @State private var comment = ""
    @State private var isPosting = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(story.title.text(for: model.contentLanguage))
                        .font(.headline)
                        .environment(\.layoutDirection, story.title.shownLanguage(for: model.contentLanguage).contentLayoutDirection)
                }

                if model.joinedChannels.isEmpty {
                    Section {
                        Text("Join a channel in Community first, then you can post stories to it.")
                            .foregroundStyle(.secondary)
                    }
                } else {
                    Section("Channel") {
                        Picker("Channel", selection: $channelId) {
                            ForEach(model.joinedChannels) { channel in
                                Text(channel.name.text(for: model.contentLanguage)).tag(Optional(channel.id))
                            }
                        }
                        .pickerStyle(.inline)
                        .labelsHidden()
                    }
                    Section("Comment (optional)") {
                        TextField("Why is this worth reading?", text: $comment, axis: .vertical)
                            .lineLimit(2...5)
                    }
                }
            }
            .formStyle(.grouped)
            .navigationTitle(Text("Post to a channel"))
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Post", action: post)
                        .disabled(channelId == nil || isPosting)
                }
            }
            .onAppear { channelId = channelId ?? model.joinedChannels.first?.id }
        }
        #if os(macOS)
        .frame(minWidth: 420, minHeight: 420)
        #endif
    }

    private func post() {
        guard let channelId else { return }
        isPosting = true
        Task {
            try? await model.post(text: comment, story: story, in: channelId)
            dismiss()
        }
    }
}
