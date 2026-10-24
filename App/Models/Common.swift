import Foundation

struct Coordinate: Codable, Hashable, Sendable {
    let lat: Double
    let lon: Double
}

/// Where a story is drawn. `radiusMeters > 0` means an area, never a point.
struct Location: Codable, Hashable, Sendable {
    let coordinate: Coordinate
    let radiusMeters: Double

    var isArea: Bool { radiusMeters > 0 }
}

/// Geographic scale. Set by where a story happens, not by how important it is.
enum Scale: String, Codable, CaseIterable, Sendable {
    case area, city, finland, world
}

enum Category: String, Codable, CaseIterable, Sendable {
    case economy, society, politics, shopping, sport, safety
    case culture, transport, education, housing, health, work
    case environment, technology, world, cityLife
}

enum Need: String, Codable, Sendable {
    case safety, information, understanding, usefulness, community, emotion
}

enum Risk: String, Codable, Sendable {
    case none, amber, red
}

enum TargetGroup: String, Codable, CaseIterable, Sendable {
    case student, worker, family, jobSeeker, local, retiree, other
}

enum Role: String, Codable, Sendable {
    case reader, member, editor, admin

    var canPost: Bool { self != .reader }
}

extension JSONDecoder {
    static let contract: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}

extension JSONEncoder {
    static let contract: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()
}
