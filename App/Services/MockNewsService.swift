import Foundation

/// Serves the contract's mock data from the app bundle. Behaves like the API: ids in, contract types out.
struct MockNewsService: NewsService {
    enum MockError: Error {
        case missingFile(String)
        case unknown(String)
    }

    let bundle: Bundle
    private let saved: SavedProfiles
    private let newsroom: MockNewsroom
    private let community: MockCommunity

    init(bundle: Bundle = .main, defaults: UserDefaults = .standard) {
        self.bundle = bundle
        self.saved = SavedProfiles(defaults: defaults)
        self.newsroom = MockNewsroom(defaults: defaults)
        self.community = MockCommunity(defaults: defaults)
    }

    func places() async throws -> [Place] {
        try load("places")
    }

    func feed(for userId: String) async throws -> FeedPage {
        guard let persona = Persona(userId: userId) else { throw MockError.unknown(userId) }
        let page: FeedPage = try load(persona.feedFile)
        // Community stories an editor published in this mock reach every reader.
        let community = newsroom.published.map { published in
            let mine = published.reporterId == userId
            return FeedItem(
                storyId: published.story.id,
                relevance: 0.75,
                mustSee: false,
                isExploration: nil,
                reasons: [LocalizedText(["en": mine ? "Your report" : "Reported by a neighbour"])]
            )
        }
        let items = (page.items + community).sorted { $0.relevance > $1.relevance }
        return FeedPage(userId: page.userId, generatedAt: page.generatedAt, scale: page.scale, placeId: page.placeId,
                        personalization: page.personalization, items: items, nextCursor: page.nextCursor)
    }

    func stories(ids: [String]) async throws -> [Story] {
        let all: [Story] = try load("stories") + newsroom.published.map(\.story)
        let byId = Dictionary(uniqueKeysWithValues: all.map { ($0.id, $0) })
        return ids.compactMap { byId[$0] }
    }

    func profile(for userId: String) async throws -> Profile {
        if let profile = saved[userId] { return profile }
        let all: [Profile] = try load("profiles")
        guard let profile = all.first(where: { $0.userId == userId }) else { throw MockError.unknown(userId) }
        return profile
    }

    func save(_ profile: Profile) async throws -> Profile {
        saved[profile.userId] = profile
        return profile
    }

    func suggestedChannels(for userId: String) async throws -> [ChannelSuggestion] {
        guard let persona = Persona(userId: userId) else { return [] }
        let suggestions: [ChannelSuggestion] = try load(persona.suggestionsFile)
        return suggestions.sorted { $0.score > $1.score }
    }

    func channels() async throws -> [Channel] {
        try load("channels")
    }

    func joinedChannels(for userId: String) async throws -> [Channel] {
        let all = try await channels()
        // The contract has no membership file: a reader starts in the channels they posted in.
        let filePosts: [ChannelPost] = try load("channel-posts")
        let seeded = Set(filePosts.filter { $0.authorId == userId }.map(\.channelId))
        let joined = community.joined(for: userId, seeded: seeded)
        return all.filter { joined.contains($0.id) }
    }

    func setMembership(_ joined: Bool, channelId: String, userId: String) async throws {
        community.setMembership(joined, channelId: channelId, userId: userId)
    }

    func posts(in channelId: String) async throws -> [ChannelPost] {
        let file: [ChannelPost] = try load("channel-posts")
        return (file + community.posts).filter { $0.channelId == channelId }.sorted { $0.createdAt > $1.createdAt }
    }

    func post(storyId: String?, text: String?, in channelId: String, authorId: String) async throws -> ChannelPost {
        let post = ChannelPost(
            id: "post-" + UUID().uuidString.lowercased(),
            channelId: channelId,
            authorId: authorId,
            storyId: storyId,
            text: text,
            likes: 0,
            createdAt: Date()
        )
        community.add(post)
        return post
    }

    func reports(for userId: String) async throws -> [Report] {
        let file: [Report] = try load("reports")
        return newsroom.reports(file: file).filter { $0.reporterId == userId }.sorted { $0.createdAt > $1.createdAt }
    }

    func submit(_ draft: ReportDraft, reporterId: String) async throws -> Report {
        let report = draft.report(id: "report-" + UUID().uuidString.lowercased(), reporterId: reporterId, now: Date())
        newsroom.add(report)
        return report
    }

    #if DEBUG
    /// Plays the editor (Track C's admin page does this for real): approve or reject a report.
    func decide(_ report: Report, approve: Bool, homePlaceId: String?, editor: String = "Aino K.") -> Report {
        let now = Date()
        // Opening a sent report puts it in review first, as the admin page does.
        var decided = report.status == .sent ? report.with(status: .inReview, note: nil, now: now) : report
        var newStory: Story?
        switch (approve, report.sensitive, report.kind) {
        case (false, _, _):
            decided = decided.with(status: .rejected, note: "Thanks. We could not confirm this, so it was not published.", now: now)
        case (true, true, _):
            decided = decided.with(status: .editorLead, note: "Thanks. We keep this as a lead and check it with the authorities before writing anything.", now: now)
        case (true, false, .problem):
            decided = decided.with(status: .edited, note: "Thanks. We corrected the story.", now: now, resultStoryId: report.storyId)
        case (true, false, .newsTip):
            let story = Story.community(from: report, placeId: homePlaceId ?? ReaderScale.defaultCityId, editor: editor, now: now)
            newStory = story
            decided = decided.with(status: .published, note: nil, now: now, resultStoryId: story.id, reach: 120)
        }
        newsroom.update(decided, publishing: newStory)
        return decided
    }
    #endif

    func notifications(for userId: String) async throws -> [AppNotification] {
        let all: [AppNotification] = try load("notifications")
        return all.filter { $0.userId == userId }
    }

    func send(_ events: [Event]) async throws {
        // shortcut: mock drops events; A8 keeps them in a local queue until the API exists.
    }

    private func load<T: Decodable>(_ name: String) throws -> T {
        guard let url = bundle.url(forResource: name, withExtension: "json")
            ?? bundle.url(forResource: name, withExtension: "json", subdirectory: "mock")
        else { throw MockError.missingFile(name) }
        return try JSONDecoder.contract.decode(T.self, from: Data(contentsOf: url))
    }
}

/// Profiles saved through the mock (onboarding, profile edits). Kept in UserDefaults so they survive relaunch.
final class SavedProfiles {
    private let defaults: UserDefaults
    private let key = "mock.savedProfiles"

    init(defaults: UserDefaults) {
        self.defaults = defaults
    }

    subscript(userId: String) -> Profile? {
        get { all[userId] }
        set {
            var profiles = all
            profiles[userId] = newValue
            defaults.set(try? JSONEncoder.contract.encode(profiles), forKey: key)
        }
    }

    private var all: [String: Profile] {
        guard let data = defaults.data(forKey: key) else { return [:] }
        return (try? JSONDecoder.contract.decode([String: Profile].self, from: data)) ?? [:]
    }
}

/// Reports sent through the mock and the community stories an editor published from them.
/// Kept in UserDefaults so they survive relaunch.
final class MockNewsroom {
    struct Published: Codable {
        let reporterId: String
        let story: Story
    }

    private struct State: Codable {
        var submitted: [Report] = []
        /// Decisions on reports from the mock file, by report id.
        var decided: [String: Report] = [:]
        var published: [Published] = []
    }

    private let defaults: UserDefaults
    private let key = "mock.newsroom"

    init(defaults: UserDefaults) {
        self.defaults = defaults
    }

    var published: [Published] { state.published }

    func reports(file: [Report]) -> [Report] {
        let current = state
        return file.map { current.decided[$0.id] ?? $0 } + current.submitted
    }

    func add(_ report: Report) {
        var current = state
        current.submitted.append(report)
        state = current
    }

    func update(_ report: Report, publishing story: Story?) {
        var current = state
        if let index = current.submitted.firstIndex(where: { $0.id == report.id }) {
            current.submitted[index] = report
        } else {
            current.decided[report.id] = report
        }
        if let story { current.published.append(Published(reporterId: report.reporterId, story: story)) }
        state = current
    }

    private var state: State {
        get {
            guard let data = defaults.data(forKey: key) else { return State() }
            return (try? JSONDecoder.contract.decode(State.self, from: data)) ?? State()
        }
        set { defaults.set(try? JSONEncoder.contract.encode(newValue), forKey: key) }
    }
}

private extension Report {
    /// The report after one more step, with the step appended to `history`.
    func with(status: Status, note: String?, now: Date, resultStoryId: String? = nil, reach: Int? = nil) -> Report {
        Report(id: id, kind: kind, reporterId: reporterId, storyId: storyId, category: category, sensitive: sensitive,
               text: text, location: location, status: status, editorNote: note ?? editorNote, resultStoryId: resultStoryId,
               reach: reach, history: history + [Step(status: status, at: now, note: note)], createdAt: createdAt, updatedAt: now)
    }
}

private extension Story {
    /// The story an editor publishes from a community news tip (mock only; the agents write it for real).
    static func community(from report: Report, placeId: String, editor: String, now: Date) -> Story {
        let headline = String(report.text.prefix(90))
        let label = String(report.text.prefix(24))
        return Story(
            id: "community-" + report.id.replacingOccurrences(of: "report-", with: ""),
            status: .published,
            origin: .community,
            scale: .area,
            placeId: placeId,
            location: report.location,
            category: report.category,
            tags: nil,
            needs: [.usefulness, .community],
            risk: .none,
            isOpinion: false,
            importance: 0.35,
            affects: nil,
            mapObject: nil,
            label: LocalizedText(["en": label]),
            title: LocalizedText(["en": headline]),
            explanation: .init(
                known: nil,
                happened: LocalizedText(["en": report.text]),
                notKnown: nil,
                forYou: LocalizedText(["en": "Reported by someone in your community and checked by an editor."]),
                context: nil,
                actionPlace: nil,
                timeline: nil
            ),
            originals: nil,
            wordOfDay: nil,
            sources: [.init(name: "Community report", url: nil, publishedAt: now)],
            translations: [.init(language: "en", tier: 1, reviewedBy: editor)],
            verification: .init(verifiedBy: editor, verifiedAt: now),
            community: .init(reportId: report.id, confirmations: 0),
            createdAt: report.createdAt,
            updatedAt: now,
            publishedAt: now
        )
    }
}

/// Channel memberships and posts made through the mock. Kept in UserDefaults so they survive relaunch.
final class MockCommunity {
    private struct State: Codable {
        /// Explicit joins (true) and leaves (false), per reader and channel; anything else follows the seed.
        var membership: [String: [String: Bool]] = [:]
        var posts: [ChannelPost] = []
    }

    private let defaults: UserDefaults
    private let key = "mock.community"

    init(defaults: UserDefaults) {
        self.defaults = defaults
    }

    var posts: [ChannelPost] { state.posts }

    func joined(for userId: String, seeded: Set<String>) -> Set<String> {
        var joined = seeded
        for (channelId, isMember) in state.membership[userId] ?? [:] {
            if isMember { joined.insert(channelId) } else { joined.remove(channelId) }
        }
        return joined
    }

    func setMembership(_ joined: Bool, channelId: String, userId: String) {
        var current = state
        current.membership[userId, default: [:]][channelId] = joined
        state = current
    }

    func add(_ post: ChannelPost) {
        var current = state
        current.posts.append(post)
        state = current
    }

    private var state: State {
        get {
            guard let data = defaults.data(forKey: key) else { return State() }
            return (try? JSONDecoder.contract.decode(State.self, from: data)) ?? State()
        }
        set { defaults.set(try? JSONEncoder.contract.encode(newValue), forKey: key) }
    }
}

/// The mock readers from `contract/mock`. Switchable in the Profile tab (debug builds) to compare rankings.
enum Persona: String, CaseIterable, Identifiable, Sendable {
    case sara, matti, newUser

    var id: String { rawValue }

    init?(userId: String) {
        guard let match = Self.allCases.first(where: { $0.userId == userId }) else { return nil }
        self = match
    }

    var userId: String {
        switch self {
        case .sara: "u-sara"
        case .matti: "u-matti"
        case .newUser: "u-new"
        }
    }

    var feedFile: String {
        switch self {
        case .sara: "feed-sara"
        case .matti: "feed-matti"
        case .newUser: "feed-new"
        }
    }

    var suggestionsFile: String {
        switch self {
        case .sara: "channel-suggestions-sara"
        case .matti: "channel-suggestions-matti"
        case .newUser: "channel-suggestions-new"
        }
    }

    var displayName: String {
        switch self {
        case .sara: "Sara · new student from Iran"
        case .matti: "Matti · Finnish local"
        case .newUser: "New user · no profile yet"
        }
    }
}
