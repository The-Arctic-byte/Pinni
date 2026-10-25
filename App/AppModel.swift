import Foundation
import Observation

/// App-wide state: who is reading, their profile, the ranked feed and the stories it points to,
/// plus everything the reader tells us back: reactions, hidden stories, reports and the events for the recommender.
@Observable
final class AppModel {
    enum LoadState: Equatable {
        case idle, loading, loaded
    }

    enum Reaction: String, Codable {
        case like, dislike
    }

    /// What the reader did that the app shows right away, before the backend re-ranks. Kept per reader.
    private struct LocalFeedback: Codable {
        var reactions: [String: Reaction] = [:]
        var hidden: Set<String> = []
    }

    private static let onboardingKey = "onboarding.completed"
    private static let personaKey = "persona"

    private var service: any NewsService
    private let defaults: UserDefaults

    private(set) var persona: Persona
    /// The reader's id as the data source knows it: the persona's on mock data, the signed-in user's on an API.
    private(set) var userId: String
    private(set) var hasCompletedOnboarding: Bool
    private(set) var state: LoadState = .idle
    /// The API URL did not answer. The sheet stays up with an empty list so Profile can change the URL.
    private(set) var showsUnreachableAPI = false
    private(set) var profile: Profile?
    private(set) var places: [String: Place] = [:]
    private(set) var feed: FeedPage?
    private(set) var stories: [String: Story] = [:]
    private(set) var reports: [Report] = []
    private(set) var learned: LearnedPreferences = .none
    private(set) var channels: [String: Channel] = [:]
    private(set) var channelSuggestions: [ChannelSuggestion] = []
    private(set) var joinedChannelIds: Set<String> = []
    /// Posts per channel, loaded when a channel is opened.
    private(set) var posts: [String: [ChannelPost]] = [:]
    private var feedback = LocalFeedback()
    /// Events not yet accepted by the backend; sent again on the next change (A8).
    @ObservationIgnored private var pendingEvents: [Event] = []

    /// Bumped on every load so a slower, older load cannot overwrite a newer one.
    @ObservationIgnored private var loadGeneration = 0

    /// A fresh install is the anonymous new user; the debug switch in Profile picks other mock readers.
    init(service: any NewsService = MockNewsService(), persona: Persona = .newUser, defaults: UserDefaults = .standard) {
        self.service = service
        #if DEBUG
        // The reader picked in Profile, kept across launches; `-persona sara` as a launch argument wins (screenshots).
        self.persona = defaults.string(forKey: Self.personaKey).flatMap(Persona.init(rawValue:)) ?? persona
        #else
        self.persona = persona
        #endif
        self.defaults = defaults
        self.userId = self.persona.userId
        #if DEBUG
        // Sara and Matti already have a profile; only the new user starts with onboarding.
        self.hasCompletedOnboarding = defaults.bool(forKey: Self.onboardingKey) || self.persona != .newUser
        #else
        self.hasCompletedOnboarding = defaults.bool(forKey: Self.onboardingKey)
        #endif
    }

    /// Language stories are shown in. Falls back to English per text when a translation is missing.
    var contentLanguage: String { profile?.language ?? "en" }

    /// Feed items with their story, in the backend's order, without what the reader hid.
    /// A category the reader turned off never hides must-see stories.
    var rankedStories: [(item: FeedItem, story: Story)] {
        let blocked = Set(profile?.hardFilters.categories ?? [])
        return (feed?.items ?? []).compactMap { item in
            guard !feedback.hidden.contains(item.storyId), let story = stories[item.storyId] else { return nil }
            if blocked.contains(story.category), !item.mustSee { return nil }
            return (item, story)
        }
    }

    /// Drops whatever the last load stored, so a failed URL cannot leave another server's news on screen.
    private func clearLoadedData() {
        profile = nil
        places = [:]
        feed = nil
        stories = [:]
        reports = []
        learned = .none
        channels = [:]
        channelSuggestions = []
        joinedChannelIds = []
        posts = [:]
    }

    private func noteUnreachableAPI() {
        #if DEBUG
        if case .api = DataSource.current { showsUnreachableAPI = true }
        #endif
    }

    func reaction(to storyId: String) -> Reaction? {
        feedback.reactions[storyId]
    }

    func load() async {
        loadGeneration += 1
        let generation = loadGeneration
        state = .loading
        do {
            #if DEBUG
            if let api = service as? APINewsService { await api.useDevAccount(for: persona) }
            #endif
            let userId = try await service.me(for: persona.userId).id
            self.userId = userId
            async let profile = service.profile(for: userId)
            async let places = service.places()
            async let feed = service.feed(for: userId)
            let page = try await feed
            let loaded = try await service.stories(ids: page.items.map(\.storyId))
            let loadedProfile = try await profile
            let loadedPlaces = try await places
            let loadedReports = try await service.reports(for: userId)
            let loadedLearned = try await service.learned(for: userId)
            let loadedChannels = try await service.channels()
            let loadedSuggestions = try await service.suggestedChannels(for: userId)
            let joined = try await service.joinedChannels(for: userId)
            guard generation == loadGeneration else { return }
            self.channels = Dictionary(uniqueKeysWithValues: loadedChannels.map { ($0.id, $0) })
            self.channelSuggestions = loadedSuggestions
            self.joinedChannelIds = Set(joined.map(\.id))
            self.posts = [:]
            self.feedback = Self.storedFeedback(for: userId, in: defaults)
            self.pendingEvents = Self.storedEvents(in: defaults)
            self.reports = loadedReports
            self.learned = loadedLearned
            self.profile = loadedProfile
            self.places = Dictionary(uniqueKeysWithValues: loadedPlaces.map { ($0.id, $0) })
            self.feed = page
            self.stories = Dictionary(uniqueKeysWithValues: loaded.map { ($0.id, $0) })
            state = .loaded
            showsUnreachableAPI = false
        } catch {
            guard generation == loadGeneration else { return }
            // A dead API must not replace the app. The list is empty until a URL answers.
            clearLoadedData()
            state = .loaded
            noteUnreachableAPI()
        }
    }

    /// Pull to refresh: sends the events still queued, then asks for the feed again, ranked with them.
    func refreshFeed() async {
        await flushEvents()
        do {
            let page = try await service.feed(for: userId)
            let loaded = try await service.stories(ids: page.items.map(\.storyId))
            let loadedLearned = try await service.learned(for: userId)
            feed = page
            stories = Dictionary(uniqueKeysWithValues: loaded.map { ($0.id, $0) })
            learned = loadedLearned
        } catch {
            noteUnreachableAPI()
        }
    }

    #if DEBUG
    /// Saves the debug API URL and loads it now. An empty URL goes back to the sample news.
    func applyAPIBaseURL(_ raw: String) async {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            defaults.removeObject(forKey: DataSource.defaultsKey)
        } else {
            defaults.set(trimmed, forKey: DataSource.defaultsKey)
        }
        service = DataSource.current.makeService()
        await load()
    }
    #endif

    func switchPersona(to persona: Persona) async {
        guard persona != self.persona else { return }
        self.persona = persona
        defaults.set(persona.rawValue, forKey: Self.personaKey)
        await load()
    }

    /// Saves the onboarding result as the anonymous reader's first profile and logs one event per step.
    func completeOnboarding(with answers: OnboardingAnswers) async {
        let now = Date()
        do {
            if persona != .newUser {
                persona = .newUser
                #if DEBUG
                if let api = service as? APINewsService { await api.useDevAccount(for: .newUser) }
                #endif
            }
            let userId = try await service.me(for: persona.userId).id
            self.userId = userId
            _ = try await service.save(answers.profile(userId: userId, now: now))
            try await service.send(answers.events(userId: userId, now: now) { "ev-" + UUID().uuidString.lowercased() })
        } catch {
            noteUnreachableAPI()
            return
        }
        defaults.set(true, forKey: Self.onboardingKey)
        hasCompletedOnboarding = true
        persona = .newUser
        #if DEBUG
        defaults.set(persona.rawValue, forKey: Self.personaKey)
        #endif
        await load()
    }

    // MARK: Feedback

    /// Like or dislike; the same reaction again takes it back (sent with value 0).
    func react(_ reaction: Reaction, to story: Story) {
        let undo = feedback.reactions[story.id] == reaction
        feedback.reactions[story.id] = undo ? nil : reaction
        saveFeedback()
        record(reaction == .like ? .like : .dislike, storyId: story.id, value: undo ? 0 : 1)
    }

    /// "Not for me": hides the story, or every story in its category (a hard filter in the profile).
    func hide(_ story: Story, wholeCategory: Bool) async {
        feedback.hidden.insert(story.id)
        saveFeedback()
        record(.notForMe, storyId: story.id, detail: ["scope": .string(wholeCategory ? "category" : "story"), "category": .string(story.category.rawValue)])
        guard wholeCategory, var updated = profile, !updated.hardFilters.categories.contains(story.category) else { return }
        updated.hardFilters.categories.append(story.category)
        updated.updatedAt = Date()
        if let saved = try? await service.save(updated) { profile = saved }
    }

    func shared(_ story: Story) {
        record(.share, storyId: story.id)
    }

    func opened(_ story: Story, from screen: Event.Context.Screen) {
        record(.open, storyId: story.id, screen: screen)
    }

    /// Reading time is attention: a story read for a while says more than one opened and closed.
    /// Left within two seconds counts as a skip.
    func read(_ story: Story, for seconds: TimeInterval) {
        if seconds < 2 {
            record(.skip, storyId: story.id, screen: .story)
        } else {
            record(.dwell, storyId: story.id, value: seconds.rounded(), screen: .story)
        }
    }

    // MARK: Map interactions

    /// The reader changed the map's scale (control or pinch). `value` is the scale's index, 0 = area … 3 = world.
    func zoomed(to scale: Scale) {
        record(.zoom, value: Double(Scale.allCases.firstIndex(of: scale) ?? 0), screen: .map, scale: scale)
    }

    func tappedPin(_ storyId: String, at scale: Scale) {
        record(.mapTap, storyId: storyId, screen: .map, scale: scale)
    }

    func tappedChip(_ placeId: String) {
        record(.placeChipTap, placeId: placeId, screen: .map)
    }

    // MARK: Profile

    /// Saves one edited onboarding step (Profile → edit). Everything else in the profile stays.
    func updateProfile(_ answers: OnboardingAnswers, step: OnboardingAnswers.Step) async {
        guard var updated = profile else { return }
        updated.apply(answers, step: step, now: Date())
        guard updated != profile else { return }
        await save(updated, detail: ["field": .string(step.rawValue)])
    }

    /// Shows a category that "Not for me" turned off again.
    func unblock(_ category: Category) async {
        guard var updated = profile, updated.hardFilters.categories.contains(category) else { return }
        updated.hardFilters.categories.removeAll { $0 == category }
        updated.updatedAt = Date()
        await save(updated, detail: ["field": .string("hardFilters"), "unblocked": .string(category.rawValue)])
    }

    var hiddenStoryCount: Int { feedback.hidden.count }

    func unhideAllStories() {
        feedback.hidden = []
        saveFeedback()
    }

    /// Forgets what the recommender learned and the reader's reactions and hidden stories; the stated profile stays.
    func resetLearned() async {
        do {
            try await service.resetLearned(for: userId)
        } catch {
            return
        }
        learned = .none
        feedback = LocalFeedback()
        saveFeedback()
        record(.profileEdit, detail: ["field": .string("learned"), "reset": .bool(true)], screen: .profile)
        await refreshFeed()
    }

    private func save(_ updated: Profile, detail: [String: JSONValue]) async {
        guard let saved = try? await service.save(updated) else { return }
        profile = saved
        record(.profileEdit, detail: detail, screen: .profile)
        // The feed is ranked with the profile, so a changed preference shows at once.
        await refreshFeed()
    }

    // MARK: Community

    /// Channels similar people follow that the reader has not joined yet, best match first.
    var suggestedChannels: [(suggestion: ChannelSuggestion, channel: Channel)] {
        channelSuggestions.compactMap { suggestion in
            guard !joinedChannelIds.contains(suggestion.channelId), let channel = channels[suggestion.channelId] else { return nil }
            return (suggestion, channel)
        }
    }

    var joinedChannels: [Channel] {
        channels.values.filter { joinedChannelIds.contains($0.id) }.sorted { $0.memberCount > $1.memberCount }
    }

    /// Channels neither joined nor suggested, biggest first.
    var otherChannels: [Channel] {
        let suggested = Set(channelSuggestions.map(\.channelId))
        return channels.values
            .filter { !joinedChannelIds.contains($0.id) && !suggested.contains($0.id) }
            .sorted { $0.memberCount > $1.memberCount }
    }

    func loadPosts(in channelId: String) async {
        if let loaded = try? await service.posts(in: channelId) { posts[channelId] = loaded }
    }

    func setJoined(_ joined: Bool, channelId: String) async {
        guard joined != joinedChannelIds.contains(channelId) else { return }
        do {
            try await service.setMembership(joined, channelId: channelId, userId: userId)
        } catch {
            return
        }
        if joined { joinedChannelIds.insert(channelId) } else { joinedChannelIds.remove(channelId) }
        record(joined ? .joinChannel : .leaveChannel, channelId: channelId, screen: .community)
    }

    /// Shares a story and/or text in a channel the reader joined, or replies to a post (text required).
    func post(text: String?, story: Story?, in channelId: String, replyTo parent: ChannelPost? = nil) async throws {
        let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines)
        let body = trimmed?.isEmpty == false ? trimmed : nil
        guard body != nil || (story != nil && parent == nil) else { return }
        let post = try await service.post(storyId: parent == nil ? story?.id : nil, text: body, replyToId: parent?.id,
                                          in: channelId, authorId: userId)
        posts[channelId, default: []].insert(post, at: 0)
        record(.postToChannel, storyId: story?.id, channelId: channelId,
               detail: parent.map { ["replyToId": .string($0.id)] }, screen: .community)
    }

    /// A channel's posts without replies, newest first.
    func topLevelPosts(in channelId: String) -> [ChannelPost] {
        (posts[channelId] ?? []).filter { $0.replyToId == nil }
    }

    /// The replies to a post, oldest first, like a conversation.
    func replies(to post: ChannelPost) -> [ChannelPost] {
        (posts[post.channelId] ?? []).filter { $0.replyToId == post.id }.sorted { $0.createdAt < $1.createdAt }
    }

    func isMine(_ post: ChannelPost) -> Bool {
        post.authorId == userId
    }

    // MARK: Reports

    /// Sends a report for a human editor (contract/processes/report-review.md). The reader follows it on My reports.
    func submit(_ draft: ReportDraft) async throws -> Report {
        let report = try await service.submit(draft, reporterId: userId)
        reports.insert(report, at: 0)
        record(.report, storyId: draft.kind == .problem ? draft.storyId : nil, detail: ["reportId": .string(report.id)])
        if draft.kind == .problem, let id = draft.storyId { record(.flagWrong, storyId: id) }
        return report
    }

    // MARK: Events

    private func record(_ kind: Event.Kind, storyId: String? = nil, channelId: String? = nil, placeId: String? = nil,
                        value: Double? = nil, detail: [String: JSONValue]? = nil,
                        screen: Event.Context.Screen? = nil, scale: Scale? = nil) {
        let event = Event(
            id: "ev-" + UUID().uuidString.lowercased(),
            userId: userId,
            type: kind,
            storyId: storyId,
            channelId: channelId,
            placeId: placeId,
            value: value,
            detail: detail,
            context: screen.map { .init(screen: $0, scale: scale) },
            occurredAt: Date()
        )
        pendingEvents.append(event)
        Self.store(pendingEvents, in: defaults)
        Task { await flushEvents() }
    }

    /// Sends the queue; on failure the events stay and go with the next one.
    private func flushEvents() async {
        let batch = pendingEvents
        guard !batch.isEmpty else { return }
        do {
            try await service.send(batch)
            pendingEvents.removeFirst(min(batch.count, pendingEvents.count))
            Self.store(pendingEvents, in: defaults)
        } catch {
            // Kept for the next try.
        }
    }

    // MARK: Local storage

    private func saveFeedback() {
        defaults.set(try? JSONEncoder.contract.encode(feedback), forKey: "feedback." + userId)
    }

    private static func storedFeedback(for userId: String, in defaults: UserDefaults) -> LocalFeedback {
        defaults.data(forKey: "feedback." + userId).flatMap { try? JSONDecoder.contract.decode(LocalFeedback.self, from: $0) } ?? LocalFeedback()
    }

    private static func storedEvents(in defaults: UserDefaults) -> [Event] {
        defaults.data(forKey: "events.pending").flatMap { try? JSONDecoder.contract.decode([Event].self, from: $0) } ?? []
    }

    private static func store(_ events: [Event], in defaults: UserDefaults) {
        defaults.set(try? JSONEncoder.contract.encode(events), forKey: "events.pending")
    }

    #if DEBUG
    /// Events waiting to be sent (tests).
    var queuedEvents: [Event] { pendingEvents }

    /// Plays the editor on the mock (Track C's admin page does this for real). The demo has no push:
    /// the outcome shows on My reports, and a published tip appears on the map.
    func simulateEditor(_ report: Report, approve: Bool) async {
        guard let mock = service as? MockNewsService else { return }
        let decided = mock.decide(report, approve: approve, homePlaceId: profile?.homePlaceId)
        if let index = reports.firstIndex(where: { $0.id == report.id }) { reports[index] = decided }
        if decided.status == .published { await load() }
    }

    func restartOnboarding() {
        defaults.removeObject(forKey: Self.onboardingKey)
        hasCompletedOnboarding = false
    }
    #endif
}
