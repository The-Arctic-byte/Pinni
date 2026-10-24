import Foundation

/// What the report form collects before it becomes a `Report` (contract: report.schema.json, POST /v1/reports).
struct ReportDraft: Equatable, Sendable {
    static let maxLength = 4000
    /// Areas are rounded up to at least this radius so a report never reveals an exact point.
    static let minimumAreaRadius = 300.0

    var kind: Report.Kind
    /// The story a problem report is about.
    var storyId: String?
    var category: Category
    var text = ""
    var location: Location?

    static func newsTip(category: Category = .cityLife) -> ReportDraft {
        ReportDraft(kind: .newsTip, category: category)
    }

    static func problem(with story: Story) -> ReportDraft {
        ReportDraft(kind: .problem, storyId: story.id, category: story.category)
    }

    /// The backend's rule, mirrored by the mock: safety reports are sensitive — editor only, never published.
    var isSensitive: Bool { category == .safety }

    var trimmedText: String { text.trimmingCharacters(in: .whitespacesAndNewlines) }

    var isValid: Bool {
        !trimmedText.isEmpty && trimmedText.count <= Self.maxLength && (kind == .newsTip || storyId != nil)
    }

    /// Attaches an area around a coordinate, never smaller than `minimumAreaRadius`.
    mutating func attachArea(around coordinate: Coordinate, radius: Double = minimumAreaRadius) {
        location = Location(coordinate: coordinate, radiusMeters: max(radius, Self.minimumAreaRadius))
    }

    func report(id: String, reporterId: String, now: Date) -> Report {
        Report(
            id: id,
            kind: kind,
            reporterId: reporterId,
            storyId: kind == .problem ? storyId : nil,
            category: category,
            sensitive: isSensitive,
            text: trimmedText,
            location: kind == .newsTip ? location : nil,
            status: .sent,
            editorNote: nil,
            resultStoryId: nil,
            reach: nil,
            history: [Report.Step(status: .sent, at: now, note: nil)],
            createdAt: now,
            updatedAt: now
        )
    }
}
