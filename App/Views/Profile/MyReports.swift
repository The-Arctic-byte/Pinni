import SwiftUI

/// Profile → My reports: everything the reader reported and where each report is in the review
/// (contract/processes/report-review.md). Opens one report as a read-only form with its history.
struct MyReportsScreen: View {
    @Environment(AppModel.self) private var model
    @State private var reportsNews = false

    var body: some View {
        List {
            if model.reports.isEmpty {
                ContentUnavailableView(
                    "No reports yet",
                    systemImage: "exclamationmark.bubble",
                    description: Text("Use Report news on the map, or “Something wrong?” on a story.")
                )
            }
            ForEach(model.reports) { report in
                NavigationLink(value: report.id) {
                    ReportRow(report: report)
                }
            }
        }
        .navigationTitle(Text("My reports"))
        .navigationDestination(for: String.self) { id in
            ReportDetailView(reportId: id)
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button("Report news", systemImage: "plus") { reportsNews = true }
            }
        }
        .sheet(isPresented: $reportsNews) {
            ReportForm(draft: .newsTip())
        }
    }
}

private struct ReportRow: View {
    let report: Report

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Label(report.category.title, systemImage: report.category.symbolName)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Text(report.createdAt, format: .dateTime.day().month())
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Text(verbatim: report.text)
                .lineLimit(2)
            ReportProgress(status: report.status)
        }
        .padding(.vertical, 4)
    }
}

/// One report as the reader sent it, read-only, with every step of its review.
struct ReportDetailView: View {
    @Environment(AppModel.self) private var model
    let reportId: String

    var body: some View {
        if let report = model.reports.first(where: { $0.id == reportId }) {
            form(for: report)
        } else {
            ContentUnavailableView("Report not found", systemImage: "questionmark")
        }
    }

    private func form(for report: Report) -> some View {
        Form {
            Section {
                ReportProgress(status: report.status)
                if let note = report.editorNote {
                    Text(verbatim: note)
                        .foregroundStyle(.secondary)
                }
                if let reach = report.reach {
                    Text("Reached \(reach) people")
                        .fontWeight(.semibold)
                        .foregroundStyle(.tint)
                }
                if let id = report.resultStoryId, let story = model.stories[id] {
                    NavigationLink {
                        StoryDetailView(story: story)
                    } label: {
                        Label(report.status == .published ? "Read the published story" : "Read the corrected story", systemImage: "newspaper")
                    }
                }
            } header: {
                Text("Status")
            }

            Section("What you sent") {
                LabeledContent("Type") {
                    report.kind == .newsTip ? Text("News tip") : Text("Problem with a story")
                }
                if let id = report.storyId, let story = model.stories[id] {
                    LabeledContent("Story", value: story.title.text(for: model.contentLanguage))
                }
                LabeledContent("Topic") {
                    Label(report.category.title, systemImage: report.category.symbolName)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("Details")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Text(verbatim: report.text)
                        .textSelection(.enabled)
                }
                if report.kind == .newsTip {
                    LabeledContent("Area") {
                        report.location == nil ? Text("Not attached") : Text("Your area (at least 300 m)")
                    }
                }
                LabeledContent("Sent") {
                    Text(report.createdAt, format: .dateTime.day().month().hour().minute())
                }
            }

            Section("History") {
                ForEach(Array(report.history.enumerated()), id: \.offset) { _, step in
                    HStack(alignment: .firstTextBaseline) {
                        Image(systemName: step.status.symbolName)
                            .foregroundStyle(step.status.tint)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(step.status.title)
                            if let note = step.note {
                                Text(verbatim: note)
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        Text(step.at, format: .dateTime.day().month().hour().minute())
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            #if DEBUG
            if report.status == .sent || report.status == .inReview {
                Section {
                    Button {
                        Task { await model.simulateEditor(report, approve: true) }
                    } label: {
                        Text(verbatim: "Approve")
                    }
                    Button(role: .destructive) {
                        Task { await model.simulateEditor(report, approve: false) }
                    } label: {
                        Text(verbatim: "Reject")
                    }
                } header: {
                    Text(verbatim: "Editor (mock, debug only)")
                } footer: {
                    Text(verbatim: "Plays the admin page: approve publishes a news tip, corrects a problem, or keeps a safety report as a lead.")
                }
            }
            #endif
        }
        .formStyle(.grouped)
        .navigationTitle(report.kind == .newsTip ? Text("News tip") : Text("Problem with a story"))
    }
}

/// Three steps, like a parcel tracker: sent, editor review, result.
struct ReportProgress: View {
    let status: Report.Status

    private var reached: Int {
        switch status {
        case .sent: 1
        case .inReview: 2
        case .published, .edited, .rejected, .editorLead: 3
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                ForEach(1...3, id: \.self) { step in
                    Capsule()
                        .fill(step <= reached ? AnyShapeStyle(status.tint) : AnyShapeStyle(.quaternary))
                        .frame(height: 4)
                }
            }
            HStack {
                Text(Report.Status.sent.title)
                Spacer()
                Text(Report.Status.inReview.title)
                Spacer()
                Text(reached == 3 ? status.title : Report.Status.published.title)
                    .fontWeight(reached == 3 ? .semibold : .regular)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Status: \(Text(status.title))"))
    }
}

extension Report.Status {
    var title: LocalizedStringResource {
        switch self {
        case .sent: "Sent"
        case .inReview: "Editor review"
        case .published: "Published"
        case .edited: "Corrected"
        case .rejected: "Not published"
        case .editorLead: "Editor lead"
        }
    }

    var symbolName: String {
        switch self {
        case .sent: "paperplane"
        case .inReview: "eye"
        case .published: "checkmark.circle.fill"
        case .edited: "pencil.circle.fill"
        case .rejected: "xmark.circle"
        case .editorLead: "lock.circle"
        }
    }

    var tint: Color {
        switch self {
        case .rejected: .secondary
        case .editorLead: .orange
        default: .accentColor
        }
    }
}
