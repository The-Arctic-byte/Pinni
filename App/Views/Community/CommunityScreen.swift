import SwiftUI

/// Channels: the ones people like you follow, the ones you joined, and the rest.
struct CommunityScreen: View {
    @Environment(AppModel.self) private var model
    @State private var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if !model.suggestedChannels.isEmpty {
                    Section {
                        ForEach(model.suggestedChannels, id: \.channel.id) { entry in
                            NavigationLink(value: entry.channel.id) {
                                ChannelRow(channel: entry.channel, reason: entry.suggestion.reason)
                            }
                        }
                    } header: {
                        Text("Suggested for you")
                    } footer: {
                        Text("Based on what people with preferences like yours follow. Counts show only when at least 20 people are similar.")
                    }
                }

                Section("Your channels") {
                    if model.joinedChannels.isEmpty {
                        Text("Join a channel to see it here and post in it.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(model.joinedChannels) { channel in
                        NavigationLink(value: channel.id) {
                            ChannelRow(channel: channel, reason: nil)
                        }
                    }
                }

                if !model.otherChannels.isEmpty {
                    Section("More channels") {
                        ForEach(model.otherChannels) { channel in
                            NavigationLink(value: channel.id) {
                                ChannelRow(channel: channel, reason: nil)
                            }
                        }
                    }
                }
            }
            .navigationTitle(Text("Community"))
            // Every destination of the community stack is declared here, at its root, so links on pushed
            // pages (posts, shared stories) always find one.
            .navigationDestination(for: String.self) { id in
                ChannelScreen(channelId: id)
            }
            .navigationDestination(for: ChannelPost.self) { post in
                PostScreen(post: post)
            }
            .navigationDestination(for: Story.self) { story in
                StoryDetailView(story: story)
            }
            #if DEBUG
            .task { await openFromLaunchArguments() }
            #endif
        }
    }
}

#if DEBUG
extension CommunityScreen {
    /// `-openChannel <channel id>` and `-openPost <post id>` as launch arguments (screenshots).
    fileprivate func openFromLaunchArguments() async {
        let defaults = UserDefaults.standard
        guard path.isEmpty, let channelId = defaults.string(forKey: "openChannel") else { return }
        path.append(channelId)
        guard let postId = defaults.string(forKey: "openPost") else { return }
        await model.loadPosts(in: channelId)
        if let post = model.posts[channelId]?.first(where: { $0.id == postId }) { path.append(post) }
    }
}
#endif

struct ChannelRow: View {
    @Environment(AppModel.self) private var model
    let channel: Channel
    let reason: LocalizedText?

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: channel.kind.symbolName)
                .font(.title3)
                .foregroundStyle(.tint)
                .frame(width: 36, height: 36)
                .background(.tint.opacity(0.12), in: .circle)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(channel.name.text(for: model.contentLanguage))
                    .font(.headline)
                if let reason {
                    Text(reason.text(for: model.contentLanguage))
                        .font(.subheadline)
                        .foregroundStyle(.tint)
                } else {
                    Text("\(channel.memberCount) members")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            .environment(\.layoutDirection, channel.name.shownLanguage(for: model.contentLanguage).contentLayoutDirection)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }
}

extension Channel.Kind {
    var symbolName: String {
        switch self {
        case .topic: "number"
        case .place: "mappin.and.ellipse"
        case .language: "character.bubble"
        case .community: "person.3"
        }
    }
}

#Preview {
    CommunityScreen()
        .environment(AppModel(persona: .sara))
}
