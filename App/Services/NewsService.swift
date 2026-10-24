import Foundation

/// Everything the app reads from or sends to the backend. One implementation per data source:
/// `MockNewsService` now (reads `contract/mock`), an HTTP client against `contract/openapi.yaml` at Integration.
protocol NewsService: Sendable {
    func places() async throws -> [Place]
    func feed(for userId: String) async throws -> FeedPage
    func stories(ids: [String]) async throws -> [Story]
    func profile(for userId: String) async throws -> Profile
    func save(_ profile: Profile) async throws -> Profile
    func suggestedChannels(for userId: String) async throws -> [ChannelSuggestion]
    func channels() async throws -> [Channel]
    /// The channels the reader joined (GET /v1/channels without ids).
    func joinedChannels(for userId: String) async throws -> [Channel]
    /// Join or leave (PUT / DELETE /v1/channels/{id}/membership).
    func setMembership(_ joined: Bool, channelId: String, userId: String) async throws
    func posts(in channelId: String) async throws -> [ChannelPost]
    /// Share a story and/or write text in a channel (POST /v1/channels/{id}/posts).
    func post(storyId: String?, text: String?, in channelId: String, authorId: String) async throws -> ChannelPost
    func reports(for userId: String) async throws -> [Report]
    /// A news tip or a problem with a story. The backend queues it for a human editor.
    func submit(_ draft: ReportDraft, reporterId: String) async throws -> Report
    func notifications(for userId: String) async throws -> [AppNotification]
    func send(_ events: [Event]) async throws
}
