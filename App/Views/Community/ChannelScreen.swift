import SwiftUI

/// One channel: what it is about, join / leave, its posts with their reply counts, and (once joined) a composer.
/// Tapping a post opens it with the members' replies. Destinations are declared on `CommunityScreen`.
struct ChannelScreen: View {
    @Environment(AppModel.self) private var model
    let channelId: String
    @State private var draft = ""
    @State private var isPosting = false
    @FocusState private var isComposing: Bool

    private var channel: Channel? { model.channels[channelId] }
    private var isJoined: Bool { model.joinedChannelIds.contains(channelId) }

    var body: some View {
        Group {
            if let channel {
                list(for: channel)
            } else {
                ContentUnavailableView("Channel not found", systemImage: "questionmark")
            }
        }
        .task(id: channelId) { await model.loadPosts(in: channelId) }
    }

    private func list(for channel: Channel) -> some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    Text(channel.description.text(for: model.contentLanguage))
                        .environment(\.layoutDirection, channel.description.shownLanguage(for: model.contentLanguage).contentLayoutDirection)
                    Label("\(channel.memberCount) members", systemImage: "person.2")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                Button {
                    Task { await model.setJoined(!isJoined, channelId: channelId) }
                } label: {
                    Label(isJoined ? "Leave channel" : "Join channel",
                          systemImage: isJoined ? "rectangle.portrait.and.arrow.right" : "plus.circle.fill")
                }
                .tint(isJoined ? .red : .accentColor)
            }

            if isJoined {
                Section("Write to the channel") {
                    TextField("Share a tip or ask a question", text: $draft, axis: .vertical)
                        .lineLimit(2...6)
                        .focused($isComposing)
                    Button("Post", systemImage: "paperplane.fill", action: send)
                        .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isPosting)
                }
            }

            Section("Posts") {
                let posts = model.topLevelPosts(in: channelId)
                if posts.isEmpty {
                    Text("No posts yet.")
                        .foregroundStyle(.secondary)
                }
                ForEach(posts) { post in
                    NavigationLink(value: post) {
                        PostSummary(post: post, replyCount: model.replies(to: post).count)
                    }
                }
            }
        }
        .navigationTitle(Text(channel.name.text(for: model.contentLanguage)))
    }

    private func send() {
        isPosting = true
        Task {
            try? await model.post(text: draft, story: nil, in: channelId)
            draft = ""
            isComposing = false
            isPosting = false
        }
    }
}

/// A post on the channel page: author, text, the shared story, likes and how many replies it has.
private struct PostSummary: View {
    let post: ChannelPost
    let replyCount: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            PostBody(post: post, showsStoryAsLink: false)
            HStack(spacing: 14) {
                if let likes = post.likes, likes > 0 {
                    Label("\(likes)", systemImage: "heart")
                }
                Label {
                    switch replyCount {
                    case 0: Text("Reply")
                    case 1: Text("1 reply")
                    default: Text("\(replyCount) replies")
                    }
                } icon: {
                    Image(systemName: "bubble.left")
                }
            }
            .font(.footnote)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}

/// One post with every member reply under it, and a reply box once the reader joined the channel.
struct PostScreen: View {
    @Environment(AppModel.self) private var model
    let post: ChannelPost
    @State private var reply = ""
    @State private var isSending = false

    private var isJoined: Bool { model.joinedChannelIds.contains(post.channelId) }

    var body: some View {
        List {
            Section {
                PostBody(post: post, showsStoryAsLink: true)
                if let likes = post.likes, likes > 0 {
                    Label("\(likes)", systemImage: "heart")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            Section {
                let replies = model.replies(to: post)
                if replies.isEmpty {
                    Text("No replies yet.")
                        .foregroundStyle(.secondary)
                }
                ForEach(replies) { reply in
                    PostBody(post: reply, showsStoryAsLink: false)
                }
            } header: {
                Text("Replies")
            }

            Section {
                if isJoined {
                    TextField("Write a reply", text: $reply, axis: .vertical)
                        .lineLimit(1...5)
                    Button("Reply", systemImage: "arrowshape.turn.up.left.fill", action: send)
                        .disabled(reply.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
                } else {
                    Text("Join the channel to reply.")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle(model.channels[post.channelId].map { Text($0.name.text(for: model.contentLanguage)) } ?? Text("Post"))
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task { if model.posts[post.channelId] == nil { await model.loadPosts(in: post.channelId) } }
    }

    private func send() {
        isSending = true
        Task {
            try? await model.post(text: reply, story: nil, in: post.channelId, replyTo: post)
            reply = ""
            isSending = false
        }
    }
}

/// Author, time, text and the shared story of one post or reply.
private struct PostBody: View {
    @Environment(AppModel.self) private var model
    let post: ChannelPost
    /// On the post page the shared story opens the story; in lists the whole row is already a link.
    let showsStoryAsLink: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label(model.isMine(post) ? "You" : "A member", systemImage: "person.crop.circle")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text(post.createdAt, format: .relative(presentation: .named))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            if let text = post.text {
                Text(verbatim: text)
                    .environment(\.layoutDirection, text.dominantLayoutDirection)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            if let id = post.storyId, let story = model.stories[id] {
                if showsStoryAsLink {
                    NavigationLink(value: story) {
                        SharedStoryCard(story: story)
                    }
                } else {
                    SharedStoryCard(story: story)
                }
            }
        }
    }
}

/// A shared story inside a post: its icon, category and title.
private struct SharedStoryCard: View {
    @Environment(AppModel.self) private var model
    let story: Story

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: story.category.symbolName)
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(story.category.title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(story.title.text(for: model.contentLanguage))
                    .font(.subheadline.weight(.semibold))
                    .multilineTextAlignment(.leading)
            }
            .environment(\.layoutDirection, story.title.shownLanguage(for: model.contentLanguage).contentLayoutDirection)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(10)
        .background(.fill.quaternary, in: .rect(cornerRadius: 12))
    }
}

extension String {
    /// Right to left when the text starts with Persian, Arabic or Hebrew letters (user-written posts carry no language).
    var dominantLayoutDirection: LayoutDirection {
        guard let first = unicodeScalars.first(where: { $0.properties.isAlphabetic }) else { return .leftToRight }
        switch first.value {
        case 0x0590...0x08FF, 0xFB1D...0xFDFF, 0xFE70...0xFEFF: return .rightToLeft
        default: return .leftToRight
        }
    }
}
