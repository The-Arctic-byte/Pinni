import SwiftUI

// MARK: 2 · Who you are

struct WhoStep: View {
    @Binding var selection: Set<TargetGroup>

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                StepHeader(
                    title: "Who are you?",
                    subtitle: "Pick all that fit. No account needed, and you can skip anything you don’t want to answer."
                )
                FlowLayout {
                    ForEach(TargetGroup.allCases, id: \.self) { group in
                        ChoiceChip(isSelected: selection.contains(group)) {
                            if selection.contains(group) { selection.remove(group) } else { selection.insert(group) }
                        } label: {
                            Label(group.title, systemImage: group.symbolName)
                        }
                    }
                }
            }
            .padding()
        }
    }
}

extension TargetGroup {
    var title: LocalizedStringResource {
        switch self {
        case .student: "Student"
        case .worker: "Working"
        case .family: "Family with children"
        case .jobSeeker: "Looking for work"
        case .local: "Local"
        case .retiree: "Retired"
        case .other: "Something else"
        }
    }

    var symbolName: String {
        switch self {
        case .student: "graduationcap"
        case .worker: "briefcase"
        case .family: "figure.2.and.child.holdinghands"
        case .jobSeeker: "magnifyingglass"
        case .local: "house"
        case .retiree: "cup.and.saucer"
        case .other: "ellipsis"
        }
    }
}

// MARK: 3 · Most important categories

struct CategoriesStep: View {
    @Binding var selection: Set<Category>

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                StepHeader(
                    title: "What matters most to you?",
                    subtitle: "Pick the topics you care about most. Everything else keeps normal priority, and you can change this any time."
                )
                FlowLayout {
                    ForEach(Category.allCases, id: \.self) { category in
                        ChoiceChip(isSelected: selection.contains(category)) {
                            if selection.contains(category) { selection.remove(category) } else { selection.insert(category) }
                        } label: {
                            Label(category.title, systemImage: category.symbolName)
                        }
                    }
                }
            }
            .padding()
        }
    }
}

// MARK: 1 · Language

struct LanguageStep: View {
    struct Option: Identifiable {
        let code: String
        /// Name in its own language, shown as is.
        let autonym: String
        let tier: LocalizedStringResource

        var id: String { code }
    }

    static let options: [Option] = [
        Option(code: "en", autonym: "English", tier: "Every story checked by an editor"),
        Option(code: "fa", autonym: "فارسی", tier: "Checked by community reviewers"),
        Option(code: "uk", autonym: "Українська", tier: "Checked by community reviewers"),
        Option(code: "fi", autonym: "Suomi", tier: "Original Finnish sources"),
        Option(code: "ar", autonym: "العربية", tier: "Machine translation, labelled"),
        Option(code: "sv", autonym: "Svenska", tier: "Machine translation, labelled"),
    ]

    @Binding var language: String

    var body: some View {
        Form {
            Section {
                ForEach(Self.options) { option in
                    Button {
                        language = option.code
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(verbatim: option.autonym)
                                    .font(.headline)
                                Text(option.tier)
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            if language == option.code {
                                Image(systemName: "checkmark")
                                    .foregroundStyle(.tint)
                                    .accessibilityHidden(true)
                            }
                        }
                        .contentShape(.rect)
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(language == option.code ? .isSelected : [])
                }
            } header: {
                StepHeader(
                    title: "Which language should stories be in?",
                    subtitle: "We tell you honestly how each language is checked."
                )
                .textCase(nil)
                .foregroundStyle(.primary)
                .padding(.bottom, 8)
            } footer: {
                Text("Residence, health, money, work and safety stories are never shown in an unchecked translation. You get the verified English version until a reviewer approves yours.")
            }
        }
        .formStyle(.grouped)
    }
}

// MARK: 4 · Place

struct PlaceStep: View {
    @Binding var answers: OnboardingAnswers
    let places: [Place]

    private var homeOptions: [Place] {
        places
            .filter { $0.kind == .area || $0.id == "oulu" }
            .sorted { ($0.kind == .area ? 0 : 1, $0.name.english) < ($1.kind == .area ? 0 : 1, $1.name.english) }
    }

    private var countries: [(code: String, name: String)] {
        Locale.Region.isoRegions
            .map(\.identifier)
            .filter { $0.count == 2 && $0.allSatisfy(\.isLetter) }
            .compactMap { code in Locale.current.localizedString(forRegionCode: code).map { (code, $0) } }
            .sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }

    var body: some View {
        Form {
            Section {
                Picker("Area", selection: $answers.homePlaceId) {
                    Text("Prefer not to say").tag(String?.none)
                    ForEach(homeOptions) { place in
                        Text(verbatim: place.name.text(for: answers.language)).tag(Optional(place.id))
                    }
                }
                Picker("Home country", selection: $answers.homeCountryCode) {
                    Text("Prefer not to say").tag(String?.none)
                    ForEach(countries, id: \.code) { country in
                        Text(verbatim: country.name).tag(Optional(country.code))
                    }
                }
            } header: {
                StepHeader(
                    title: "Where are you?",
                    subtitle: "Your area puts nearby news first. Stories only ever show an area, never an address."
                )
                .textCase(nil)
                .foregroundStyle(.primary)
                .padding(.bottom, 8)
            } footer: {
                Text("Your home country adds a place on the map with news from there.")
            }

            Section {
                Picker("Residence", selection: $answers.residence) {
                    Text("Prefer not to say").tag(Profile.Residence.Status?.none)
                    Text("Finnish citizen").tag(Optional(Profile.Residence.Status.finnish))
                    Text("EU citizen").tag(Optional(Profile.Residence.Status.eu))
                    Text("Residence permit (non-EU)").tag(Optional(Profile.Residence.Status.nonEu))
                }
                Toggle("Use this to show rules and permit news that affect me", isOn: $answers.residenceConsent)
                    .disabled(answers.residence == nil)
            } footer: {
                Text("Optional. Without your consent we don’t store it.")
            }

            Section {
                Picker("Housing", selection: $answers.housing) {
                    Text("Prefer not to say").tag(Profile.Housing.Provider?.none)
                    Text(verbatim: "PSOAS").tag(Optional(Profile.Housing.Provider.psoas))
                    Text("Other").tag(Optional(Profile.Housing.Provider.other))
                }
                Toggle("Also gather news from my housing provider", isOn: $answers.housingConsent)
                    .disabled(answers.housing == nil || answers.housing == .other)
            } footer: {
                Text("For example rent changes or maintenance in PSOAS buildings.")
            }
        }
        .formStyle(.grouped)
        .onChange(of: answers.residence) { if answers.residence == nil { answers.residenceConsent = false } }
        .onChange(of: answers.housing) { if answers.housing != .psoas { answers.housingConsent = false } }
    }
}
