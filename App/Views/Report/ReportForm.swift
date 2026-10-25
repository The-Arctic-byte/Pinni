import SwiftUI

/// Send news to the editors, or tell them something is wrong with a story.
/// Nothing is published without a human editor (contract/processes/report-review.md).
struct ReportForm: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var draft: ReportDraft
    @State private var attachesArea = true
    @State private var isSending = false
    @State private var sent: Report?
    @State private var failure: String?
    @FocusState private var isTextFocused: Bool

    /// The story a problem report is about.
    private let story: Story?

    init(draft: ReportDraft, story: Story? = nil) {
        _draft = State(initialValue: draft)
        self.story = story
    }

    var body: some View {
        NavigationStack {
            Group {
                if let sent {
                    ReportSentView(report: sent) { dismiss() }
                } else {
                    form
                }
            }
            .navigationTitle(draft.kind == .newsTip ? Text("Report news") : Text("Something wrong?"))
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                if sent == nil {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cancel") { dismiss() }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Send", action: send)
                            .disabled(!draft.isValid || isSending)
                    }
                }
            }
        }
        #if os(macOS)
        .frame(minWidth: 460, minHeight: 520)
        #endif
    }

    private var form: some View {
        Form {
            if let story {
                Section("About this story") {
                    Text(story.title.text(for: model.contentLanguage))
                        .font(.headline)
                        .environment(\.layoutDirection, story.title.shownLanguage(for: model.contentLanguage).contentLayoutDirection)
                }
            }

            Section {
                Picker("Topic", selection: $draft.category) {
                    ForEach(Category.allCases, id: \.self) { category in
                        Label(category.title, systemImage: category.symbolName).tag(category)
                    }
                }
            } footer: {
                if draft.category == .safety {
                    Text("In an emergency, call 112.")
                }
            }

            Section {
                TextField(text: $draft.text, prompt: prompt, axis: .vertical) {
                    Text("Details")
                }
                .lineLimit(5...12)
                .focused($isTextFocused)
            } header: {
                draft.kind == .newsTip ? Text("What happened?") : Text("What is wrong?")
            } footer: {
                Text("\(draft.trimmedText.count) of \(ReportDraft.maxLength)")
            }

            if draft.kind == .newsTip {
                Section {
                    Toggle("Attach my area", isOn: $attachesArea)
                        .disabled(homeCenter == nil)
                } footer: {
                    Text("Only your area is shared, at least 300 m wide, never your exact location.")
                }
            }

            Section {
            } footer: {
                Text("Your name is never shown. An editor checks every report before anything is published.")
            }

            if let failure {
                Section {
                    Label(failure, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                }
            }
        }
        .formStyle(.grouped)
        .onAppear { isTextFocused = true }
    }

    private var prompt: Text {
        draft.kind == .newsTip
            ? Text("For example: the path by the school is very icy")
            : Text("For example: the date in the story is wrong")
    }

    private var homeCenter: Coordinate? {
        model.profile?.homePlaceId.flatMap { model.places[$0]?.center }
    }

    private func send() {
        var ready = draft
        if ready.kind == .newsTip, attachesArea, let homeCenter {
            ready.attachArea(around: homeCenter, radius: 500)
        } else {
            ready.location = nil
        }
        isSending = true
        failure = nil
        Task {
            do {
                sent = try await model.submit(ready)
            } catch let error as APINewsService.APIError where error.status == 403 {
                failure = String(localized: "Only members can send reports. Sign in with an account and try again.")
            } catch let error as APINewsService.APIError where (400..<500).contains(error.status) {
                // The server read the report and said what is wrong with it.
                failure = error.localizedDescription
            } catch {
                failure = String(localized: "Could not send. Check your connection and try again.")
            }
            isSending = false
        }
    }
}

/// Shown after sending: what happens next.
private struct ReportSentView: View {
    let report: Report
    let onDone: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Thanks, your report was sent", systemImage: "checkmark.circle")
        } description: {
            Text("An editor checks it before anything is published. Follow its status in Profile → My reports.")
        } actions: {
            Button("Done", action: onDone)
                .buttonStyle(.borderedProminent)
        }
    }
}
