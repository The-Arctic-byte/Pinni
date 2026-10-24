import Foundation

/// `NewsService` over HTTP, following `contract/openapi.yaml` (Track C's backend in `backend/`).
/// The reader is anonymous until sign-in exists (C3): the first call creates an anonymous session. Its token is
/// kept in memory and, where the Keychain is available (signed builds), across launches. The backend knows who
/// the reader is from the token, so the `userId` arguments of `NewsService` are not sent.
final class APINewsService: NewsService, @unchecked Sendable {
    struct APIError: Error, LocalizedError {
        let status: Int
        let code: String?
        let message: String?

        var errorDescription: String? { message ?? "Server answered \(status)" }
    }

    private struct Session: Decodable {
        let token: String
        let user: User
    }

    private struct ErrorBody: Decodable {
        let code: String
        let message: String
    }

    let baseURL: URL
    private let session: URLSession
    private let tokens: TokenStore
    /// Serialises session creation so parallel first calls share one anonymous reader.
    private let sessionLock = NSLock()
    private var pendingSession: Task<String, Error>?
    private var memoryToken: String?

    init(baseURL: URL, session: URLSession = .shared, tokens: TokenStore? = nil) {
        self.baseURL = baseURL
        self.session = session
        self.tokens = tokens ?? TokenStore(account: baseURL.absoluteString)
    }

    // MARK: NewsService

    func me(for userId: String) async throws -> User {
        try await get("v1/me")
    }

    func places() async throws -> [Place] {
        try await get("v1/places")
    }

    func feed(for userId: String) async throws -> FeedPage {
        try await get("v1/feed", query: [URLQueryItem(name: "limit", value: "100")])
    }

    func stories(ids: [String]) async throws -> [Story] {
        // Stay within the contract's maxItems (100) per request.
        var stories: [Story] = []
        for start in stride(from: 0, to: ids.count, by: 100) {
            let chunk = ids[start..<min(start + 100, ids.count)]
            stories += try await get("v1/stories", query: [URLQueryItem(name: "ids", value: chunk.joined(separator: ","))])
        }
        return stories
    }

    func profile(for userId: String) async throws -> Profile {
        try await get("v1/profile")
    }

    func save(_ profile: Profile) async throws -> Profile {
        try await send("PUT", "v1/profile", body: profile)
    }

    func learned(for userId: String) async throws -> LearnedPreferences {
        try await get("v1/profile/learned")
    }

    func resetLearned(for userId: String) async throws {
        try await sendNoContent("DELETE", "v1/profile/learned")
    }

    func suggestedChannels(for userId: String) async throws -> [ChannelSuggestion] {
        try await get("v1/channels/suggested")
    }

    func channels() async throws -> [Channel] {
        try await get("v1/channels", query: [URLQueryItem(name: "all", value: "true")])
    }

    func joinedChannels(for userId: String) async throws -> [Channel] {
        try await get("v1/channels")
    }

    func setMembership(_ joined: Bool, channelId: String, userId: String) async throws {
        try await sendNoContent(joined ? "PUT" : "DELETE", "v1/channels/\(channelId)/membership")
    }

    func posts(in channelId: String) async throws -> [ChannelPost] {
        try await get("v1/channels/\(channelId)/posts")
    }

    func post(storyId: String?, text: String?, replyToId: String?, in channelId: String, authorId: String) async throws -> ChannelPost {
        struct Body: Encodable { let storyId: String?; let text: String?; let replyToId: String? }
        return try await send("POST", "v1/channels/\(channelId)/posts", body: Body(storyId: storyId, text: text, replyToId: replyToId))
    }

    func reports(for userId: String) async throws -> [Report] {
        try await get("v1/reports/mine")
    }

    func submit(_ draft: ReportDraft, reporterId: String) async throws -> Report {
        // The backend sets `sensitive` and the status; the app sends what the reader wrote.
        struct Body: Encodable {
            let kind: Report.Kind
            let storyId: String?
            let category: Category
            let text: String
            let location: Location?
        }
        let body = Body(
            kind: draft.kind,
            storyId: draft.kind == .problem ? draft.storyId : nil,
            category: draft.category,
            text: draft.trimmedText,
            location: draft.kind == .newsTip ? draft.location : nil
        )
        return try await send("POST", "v1/reports", body: body)
    }

    func notifications(for userId: String) async throws -> [AppNotification] {
        try await get("v1/notifications")
    }

    func send(_ events: [Event]) async throws {
        // The contract accepts at most 500 events per call; ids make retries idempotent.
        for start in stride(from: 0, to: events.count, by: 500) {
            try await sendNoContent("POST", "v1/events", body: Array(events[start..<min(start + 500, events.count)]))
        }
    }

    // MARK: Requests

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        let data = try await perform("GET", path, query: query, body: Optional<Int>.none)
        return try JSONDecoder.contract.decode(T.self, from: data)
    }

    private func send<T: Decodable>(_ method: String, _ path: String, body: some Encodable) async throws -> T {
        let data = try await perform(method, path, query: [], body: body)
        return try JSONDecoder.contract.decode(T.self, from: data)
    }

    private func sendNoContent(_ method: String, _ path: String) async throws {
        _ = try await perform(method, path, query: [], body: Optional<Int>.none)
    }

    private func sendNoContent(_ method: String, _ path: String, body: some Encodable) async throws {
        _ = try await perform(method, path, query: [], body: body)
    }

    /// One request with the session token. A 401 means the token is gone: start a new session and retry once.
    /// Only the token that failed is cleared, so parallel requests that all fail share one new session.
    private func perform(_ method: String, _ path: String, query: [URLQueryItem], body: (some Encodable)?) async throws -> Data {
        let payload = try body.map { try JSONEncoder.contract.encode($0) }
        let token = try await currentToken()
        do {
            return try await request(method, path, query: query, payload: payload, token: token)
        } catch let error as APIError where error.status == 401 {
            if storedToken == token { clearToken() }
            return try await request(method, path, query: query, payload: payload, token: try await currentToken())
        }
    }

    private func request(_ method: String, _ path: String, query: [URLQueryItem], payload: Data?, token: String?) async throws -> Data {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)
        if !query.isEmpty { components?.queryItems = query }
        guard let url = components?.url else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(Locale.current.language.languageCode?.identifier ?? "en", forHTTPHeaderField: "Accept-Language")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let payload {
            request.httpBody = payload
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await session.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let body = try? JSONDecoder.contract.decode(ErrorBody.self, from: data)
            throw APIError(status: status, code: body?.code, message: body?.message)
        }
        return data
    }

    // MARK: Session

    /// Signs in with an account (POST /v1/auth/login). The anonymous reader's history moves to the account.
    func signIn(email: String, password: String) async throws {
        struct Body: Encodable { let email: String; let password: String; let anonymousToken: String? }
        let payload = try JSONEncoder.contract.encode(Body(email: email, password: password, anonymousToken: storedToken))
        let data = try await request("POST", "v1/auth/login", query: [], payload: payload, token: nil)
        store(try JSONDecoder.contract.decode(Session.self, from: data).token)
    }

    /// Forgets the session; the next call starts a new anonymous reader.
    func signOut() {
        clearToken()
    }

    #if DEBUG
    /// The mock personas exist as dev accounts on the backend (`<name>@pinni.test`, password `pinni-dev`), so the
    /// debug persona switch also works on the API. The new user stays anonymous.
    func useDevAccount(for persona: Persona) async {
        let current = try? await me(for: "")
        switch persona {
        case .newUser:
            if current?.role != .reader { signOut() }
        case .sara, .matti:
            guard current?.id != persona.userId else { return }
            try? await signIn(email: "\(persona.rawValue)@pinni.test", password: "pinni-dev")
        }
    }
    #endif

    private var storedToken: String? { memoryToken ?? tokens.token }

    private func store(_ token: String) {
        memoryToken = token
        tokens.save(token)
    }

    private func clearToken() {
        memoryToken = nil
        tokens.clear()
    }

    /// The stored token, or a new anonymous session (POST /v1/auth/anonymous, no auth).
    private func currentToken() async throws -> String {
        if let token = storedToken { return token }
        let task: Task<String, Error> = sessionLock.withLock {
            if let pendingSession { return pendingSession }
            let task = Task { [baseURL, session] in
                var request = URLRequest(url: baseURL.appendingPathComponent("v1/auth/anonymous"))
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")
                let (data, response) = try await session.data(for: request)
                let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                guard (200..<300).contains(status) else { throw APIError(status: status, code: nil, message: nil) }
                return try JSONDecoder.contract.decode(Session.self, from: data).token
            }
            pendingSession = task
            return task
        }
        defer { sessionLock.withLock { pendingSession = nil } }
        let token = try await task.value
        if storedToken == nil { store(token) }
        return token
    }
}
