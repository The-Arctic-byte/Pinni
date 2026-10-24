import Foundation

/// Where the app gets its data: the contract's mock files (default) or a backend that implements `contract/openapi.yaml`.
/// Debug builds pick it with `-apiBaseURL http://localhost:8000` or in Profile → Mock data; it applies at the next launch.
enum DataSource: Equatable {
    case mock
    case api(URL)

    static let defaultsKey = "apiBaseURL"

    static var current: DataSource {
        #if DEBUG
        if let raw = UserDefaults.standard.string(forKey: defaultsKey)?.trimmingCharacters(in: .whitespaces),
           !raw.isEmpty, let url = URL(string: raw), url.scheme?.hasPrefix("http") == true {
            return .api(url)
        }
        #endif
        return .mock
    }

    func makeService() -> any NewsService {
        switch self {
        case .mock: MockNewsService()
        case .api(let url): APINewsService(baseURL: url)
        }
    }
}
