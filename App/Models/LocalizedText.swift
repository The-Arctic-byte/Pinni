import Foundation

/// Text in several languages. English is always present and is the fallback (contract: common.schema.json).
struct LocalizedText: Codable, Hashable, Sendable {
    let values: [String: String]

    init(_ values: [String: String]) {
        self.values = values
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        values = try container.decode([String: String].self)
        guard values["en"] != nil else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "LocalizedText without 'en'")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(values)
    }

    var english: String { values["en"] ?? "" }

    func text(for language: String) -> String {
        values[language] ?? english
    }

    func has(_ language: String) -> Bool {
        values[language] != nil
    }
}
