import SwiftUI

/// Placeholder until A10. In debug builds it switches between the mock readers to compare rankings.
struct ProfileScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(\.locale) private var locale
    #if DEBUG
    /// `-profileReports YES` as a launch argument opens My reports directly (screenshots).
    @State private var opensReports = UserDefaults.standard.bool(forKey: "profileReports")
    #endif

    var body: some View {
        NavigationStack {
            Form {
                #if DEBUG
                Section {
                    Picker("Reader", selection: personaBinding) {
                        ForEach(Persona.allCases) { persona in
                            Text(verbatim: persona.displayName).tag(persona)
                        }
                    }
                    Button {
                        model.restartOnboarding()
                    } label: {
                        Text(verbatim: "Restart onboarding")
                    }
                } header: {
                    Text(verbatim: "Mock data")
                }
                #endif

                if let profile = model.profile {
                    Section("Your profile") {
                        LabeledContent("Story language", value: Locale.current.localizedString(forLanguageCode: profile.language) ?? profile.language)
                        if let home = profile.homePlaceId.flatMap({ model.places[$0] }) {
                            LabeledContent("Area", value: home.name.text(for: locale.language.languageCode?.identifier ?? "en"))
                        }
                        if let feed = model.feed {
                            LabeledContent("Personalization", value: feed.personalization, format: .percent)
                        }
                    }
                }

                Section {
                    NavigationLink {
                        MyReportsScreen()
                    } label: {
                        LabeledContent {
                            Text(model.reports.count, format: .number)
                        } label: {
                            Label("My reports", systemImage: "exclamationmark.bubble")
                        }
                    }
                } footer: {
                    Text("What you reported and where each report is in the editor’s review.")
                }
            }
            .formStyle(.grouped)
            .navigationTitle(Text("Profile"))
            #if DEBUG
            .navigationDestination(isPresented: $opensReports) { MyReportsScreen() }
            #endif
        }
    }

    private var personaBinding: Binding<Persona> {
        Binding(
            get: { model.persona },
            set: { persona in Task { await model.switchPersona(to: persona) } }
        )
    }
}

#Preview {
    ProfileScreen()
        .environment(AppModel())
}
