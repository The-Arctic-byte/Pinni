import MapKit
import SwiftUI

/// The map at four geographic scales, relative to where the reader lives (`ReaderScale`), with a news panel:
/// on iPhone a native sheet that is never dismissed (Flighty style), on Mac an inspector.
/// Area stories are a circle, never a pin, and the circle opens the story. Point pins that would
/// overlap at the current zoom are grouped; tapping a group narrows the panel's list to it.
struct MapScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(\.locale) private var locale
    @State private var position: MapCameraPosition = .automatic
    @State private var scale: Scale = .area
    @State private var cameraDistance: Double = 7_000
    /// Stories pushed in the panel; the last one is the open story on the map.
    @State private var path: [String] = []
    /// A tapped group pin or place chip; the panel (and for chips the map) shows only its stories until "Show all".
    @State private var listFilter: ListFilter?
    /// Story id of the area circle the map itself has selected.
    @State private var areaSelection: String?
    @State private var sheetDetent: PresentationDetent = .resting
    @State private var showsInspector = true
    /// Asked only when the reader taps "my location"; the position is never sent anywhere.
    @State private var locationManager = CLLocationManager()
    #if os(iOS)
    @State private var screenHeight: CGFloat = 800
    #endif
    @State private var reportsNews = false

    var body: some View {
        if case .failed(let message) = model.state {
            LoadFailure(message: message) { await model.load() }
        } else {
            content
        }
    }

    @ViewBuilder
    private var content: some View {
        #if os(iOS)
        map
            // The camera centres in the part of the map the sheet leaves visible.
            .safeAreaPadding(.bottom, sheetCover)
            .animation(.snappy, value: sheetDetent)
            .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { screenHeight = $0 }
            .sheet(isPresented: showsSheet) {
                panel
                    .presentationDetents([.collapsed, .resting, .medium, .large], selection: $sheetDetent)
                    .presentationDragIndicator(.visible)
                    .presentationBackgroundInteraction(.enabled(upThrough: .medium))
                    .interactiveDismissDisabled()
            }
        #else
        map
            .inspector(isPresented: $showsInspector) {
                panel
                    .inspectorColumnWidth(min: 320, ideal: 380, max: 480)
            }
            .toolbar {
                ToolbarItem {
                    Button("Report news", systemImage: "exclamationmark.bubble") { reportsNews = true }
                }
                ToolbarItem {
                    Button("Story list", systemImage: "sidebar.trailing") { showsInspector.toggle() }
                }
            }
            .sheet(isPresented: $reportsNews) {
                ReportForm(draft: .newsTip())
            }
        #endif
    }

    #if os(iOS)
    /// How much of the map the sheet covers at its current height (large keeps the medium value: the map is hidden anyway).
    private var sheetCover: CGFloat {
        guard model.hasCompletedOnboarding else { return 0 }
        switch sheetDetent {
        case .collapsed: return 110
        case .resting: return screenHeight * 0.34
        default: return screenHeight * 0.5
        }
    }

    /// The sheet stays up for good once onboarding is done (it would block the onboarding cover otherwise).
    private var showsSheet: Binding<Bool> {
        Binding(get: { model.hasCompletedOnboarding }, set: { _ in })
    }
    #endif

    private var panel: some View {
        MapPanel(
            title: panelTitle,
            entries: panelEntries,
            mustSee: mustSeeEntries,
            chips: chipItems,
            selectedChip: listFilter?.placeId,
            isFiltered: listFilter != nil,
            path: $path,
            onSelectChip: select(chip:),
            onShowAll: showAll
        )
    }

    private var map: some View {
        Map(position: $position, selection: $areaSelection) {
            UserAnnotation()
            ForEach(visibleEntries, id: \.item.id) { entry in
                if let location = entry.story.location, location.isArea {
                    MapCircle(center: location.coordinate.clLocation, radius: location.radiusMeters)
                        .foregroundStyle(entry.story.category.mapColor.opacity(0.18))
                        .stroke(entry.story.category.mapColor, style: StrokeStyle(lineWidth: 2, dash: [6, 4]))
                        .tag(entry.story.id)
                    Annotation(coordinate: location.coordinate.clLocation) {
                        Button {
                            model.tappedPin(entry.story.id, at: scale)
                            open(entry.story.id)
                        } label: {
                            Color.clear.frame(width: 44, height: 44)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(Text(verbatim: entry.story.title.text(for: model.contentLanguage)))
                    } label: {
                        EmptyView()
                    }
                }
            }
            ForEach(groups) { group in
                if let story = model.stories[group.lead.storyId] {
                    Annotation(coordinate: group.coordinate.clLocation, anchor: .bottom) {
                        Button {
                            select(group)
                        } label: {
                            StoryPin(
                                story: story,
                                item: group.lead,
                                label: story.label.text(for: model.contentLanguage),
                                isSelected: highlightedIds.contains(story.id),
                                count: group.members.count
                            )
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(Text(verbatim: story.title.text(for: model.contentLanguage)))
                    } label: {
                        EmptyView()
                    }
                }
            }
        }
        .mapStyle(.standard(elevation: .realistic, emphasis: .muted, pointsOfInterest: .excludingAll))
        .onMapCameraChange(frequency: .onEnd) { context in
            // The camera also reports while the window lays out (launch, resize, inspector). Changing state
            // right here re-lays out the map, which reports again: AppKit kills that loop with an exception.
            // So the update waits until layout is done, and only real changes count.
            let distance = context.camera.distance
            Task { cameraDidSettle(at: distance) }
        }
        .onChange(of: areaSelection) { _, id in
            if let id { open(id) }
        }
        .onChange(of: path) { old, new in
            if let id = new.last {
                flyIn(to: id)
            } else if let last = old.last, model.stories[last]?.mapObject != nil {
                // Leaving a 3D close-up goes back to the scale the reader was on.
                moveCamera(to: scale, animated: true)
            }
            if new.isEmpty { areaSelection = nil }
        }
        .safeAreaInset(edge: .top) {
            HStack(spacing: 10) {
                scalePicker
                locationButton
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
            .frame(maxWidth: 540)
        }
        .onChange(of: model.profile?.homePlaceId, initial: true) {
            show(readerScale.startScale, animated: false)
            #if DEBUG
            applyLaunchArguments()
            #endif
        }
    }

    private var scalePicker: some View {
        Picker("Scale", selection: Binding(get: { scale }, set: { model.zoomed(to: $0); show($0, animated: true) })) {
            ForEach(Scale.allCases, id: \.self) { scale in
                Text(scale.title).tag(scale)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
    }

    private var locationButton: some View {
        Button("My location", systemImage: "location", action: showMyLocation)
            .labelStyle(.iconOnly)
            .buttonStyle(.bordered)
            .buttonBorderShape(.circle)
    }

    /// Asks for when-in-use permission the first time, then follows the reader on the map.
    /// Without permission the map stays where it is.
    private func showMyLocation() {
        if locationManager.authorizationStatus == .notDetermined {
            locationManager.requestWhenInUseAuthorization()
        }
        listFilter = nil
        path = []
        withAnimation(.smooth(duration: 1.0)) {
            position = .userLocation(fallback: .camera(scale.camera(home: home)))
        }
    }

    // MARK: Data

    private var readerScale: ReaderScale {
        ReaderScale(places: model.places, homePlaceId: model.profile?.homePlaceId)
    }

    /// Stories under the current scale for this reader (or the selected chip's place),
    /// plus the open story so it stays visible in a close-up.
    private var visibleEntries: [(item: FeedItem, story: Story)] {
        if let chip = listFilter?.placeId {
            let chips = placeChips
            return model.rankedStories.filter { chips.contains(chip, storyPlaceId: $0.story.placeId) || $0.story.id == path.last }
        }
        let reader = readerScale
        return model.rankedStories.filter { reader.scale(of: $0.story) == scale || $0.story.id == path.last }
    }

    private var placeChips: PlaceChips {
        PlaceChips(places: model.places, homeCityId: readerScale.homeCityId, homeCountryCode: model.profile?.homeCountryCode)
    }

    private var chipItems: [MapPanel.Chip] {
        let chips = placeChips
        return chips.ids.compactMap { id in
            guard let place = model.places[id] else { return nil }
            let count = model.rankedStories.count { chips.contains(id, storyPlaceId: $0.story.placeId) }
            return MapPanel.Chip(id: id, name: place.name.text(for: uiLanguage), count: count)
        }
    }

    /// Point stories only. An area (`radiusMeters > 0`) stays a circle and is never grouped into a pin.
    private var groups: [PinGroup] {
        let pins = visibleEntries.compactMap { entry -> (item: FeedItem, coordinate: Coordinate)? in
            guard let location = entry.story.location, !location.isArea else { return nil }
            return (entry.item, location.coordinate)
        }
        return PinGrouping.groups(pins, cameraDistance: cameraDistance)
    }

    private var highlightedIds: Set<String> {
        Set(path.suffix(1) + (listFilter?.groupIds ?? []))
    }

    private var panelEntries: [(item: FeedItem, story: Story)] {
        switch listFilter {
        case .group(let ids):
            return model.rankedStories.filter { ids.contains($0.story.id) }
        case .place(let id):
            let chips = placeChips
            return model.rankedStories.filter { chips.contains(id, storyPlaceId: $0.story.placeId) }
        case nil:
            break
        }
        let reader = readerScale
        return model.rankedStories.filter { reader.scale(of: $0.story) == scale }
    }

    /// Must-see stories that are not already in the list. Only on the unfiltered list: a chip or group is a deliberate choice.
    private var mustSeeEntries: [(item: FeedItem, story: Story)] {
        guard listFilter == nil else { return [] }
        let listed = Set(panelEntries.map(\.story.id))
        return model.rankedStories.filter { $0.item.mustSee && !listed.contains($0.story.id) }
    }

    private var panelTitle: Text {
        switch listFilter {
        case .group(let ids):
            return Text("\(ids.count) stories here")
        case .place(let id):
            let name = model.places[id]?.name.text(for: uiLanguage) ?? ""
            return id == "world" ? Text("In the world") : Text("In \(name)")
        case nil:
            break
        }
        switch scale {
        case .area: return Text("In your area")
        case .city:
            let city = model.places[readerScale.homeCityId]?.name.text(for: uiLanguage) ?? ""
            return Text("In \(city)")
        case .finland: return Text("In Finland")
        case .world: return Text("In the world")
        }
    }

    /// Chips and titles are navigation, so they follow the app's language; stories follow the story language.
    private var uiLanguage: String {
        locale.language.languageCode?.identifier ?? "en"
    }

    private var home: CLLocationCoordinate2D? {
        model.profile?.homePlaceId.flatMap { model.places[$0]?.center }?.clLocation
    }

    // MARK: Actions

    private func show(_ scale: Scale, animated: Bool) {
        self.scale = scale
        path = []
        listFilter = nil
        areaSelection = nil
        moveCamera(to: scale, animated: animated)
    }

    private func moveCamera(to scale: Scale, animated: Bool) {
        let camera = scale.camera(home: home)
        cameraDistance = camera.distance
        if animated {
            withAnimation(.smooth(duration: 1.2)) { position = .camera(camera) }
        } else {
            position = .camera(camera)
        }
    }

    private func cameraDidSettle(at distance: Double) {
        if abs(distance - cameraDistance) > cameraDistance * 0.05 { cameraDistance = distance }
        // Pinching moves the scale control without moving the camera again; a close-up on a story doesn't.
        let pinched = Scale(cameraDistance: distance)
        if pinched != scale, path.isEmpty, listFilter == nil {
            scale = pinched
            model.zoomed(to: pinched)
        }
    }

    private func select(_ group: PinGroup) {
        model.tappedPin(group.lead.storyId, at: scale)
        guard group.isGroup else {
            open(group.lead.storyId)
            return
        }
        areaSelection = nil
        listFilter = .group(group.members.map(\.storyId))
        path = []
        revealPanel()
        zoom(toFit: group)
    }

    /// Like a map cluster: zoom in until the group's stories stand apart. The scale stays (a filter is active).
    private func zoom(toFit group: PinGroup) {
        let points = group.members.compactMap { model.stories[$0.storyId]?.location?.coordinate }
        guard let first = points.first else { return }
        let spread = points.map { PinGrouping.meters(from: first, to: $0) }.max() ?? 0
        let lat = points.map(\.lat).reduce(0, +) / Double(points.count)
        let lon = points.map(\.lon).reduce(0, +) / Double(points.count)
        // About three times the spread on screen, never closer than a street view.
        let camera = MapCamera(centerCoordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon),
                               distance: max(spread * 3, 1_500), heading: 0, pitch: 45)
        cameraDistance = camera.distance
        withAnimation(.smooth(duration: 1.0)) { position = .camera(camera) }
    }

    /// A place chip lists that place's stories and flies the map there; tapping it again goes back.
    private func select(chip id: String) {
        guard listFilter?.placeId != id else {
            showAll()
            return
        }
        model.tappedChip(id)
        path = []
        areaSelection = nil
        listFilter = .place(id)
        // Keep the scale control in step with where the map goes.
        scale = switch id {
        case readerScale.homeCityId: .city
        case ReaderScale.homeCountryId: .finland
        default: .world
        }
        let camera = chipCamera(id)
        cameraDistance = camera.distance
        withAnimation(.smooth(duration: 1.2)) { position = .camera(camera) }
    }

    private func showAll() {
        let wasFiltered = listFilter != nil
        listFilter = nil
        if wasFiltered { moveCamera(to: scale, animated: true) }
    }

    private func chipCamera(_ id: String) -> MapCamera {
        switch id {
        case readerScale.homeCityId: return Scale.city.camera(home: home)
        case ReaderScale.homeCountryId: return Scale.finland.camera(home: home)
        case "world": return Scale.world.camera(home: home)
        default:
            let place = model.places[id]
            let center = place?.center?.clLocation ?? .oulu
            let distance: Double = place?.kind == .country ? 3_500_000 : 6_000_000
            return MapCamera(centerCoordinate: center, distance: distance, heading: 0, pitch: 0)
        }
    }

    /// Opens one story in the panel; the map highlights it (and flies in for 3D objects) through `path`.
    private func open(_ id: String) {
        if listFilter?.placeId == nil { listFilter = nil }
        path = [id]
        revealPanel()
    }

    private func revealPanel() {
        #if os(iOS)
        if sheetDetent == .collapsed { sheetDetent = .resting }
        #else
        showsInspector = true
        #endif
    }

    /// A story with a 3D object flies in close so MapKit's real 3D buildings show around it.
    private func flyIn(to id: String) {
        guard let story = model.stories[id], story.mapObject != nil, let location = story.location else { return }
        withAnimation(.smooth(duration: 1.5)) {
            position = .camera(MapCamera(centerCoordinate: location.coordinate.clLocation, distance: 900, heading: 30, pitch: 70))
        }
    }
}

#if DEBUG
extension MapScreen {
    /// `-mapScale world`, `-mapSelect <story id>`, `-mapChip <place id>`, `-openStory <story id>`
    /// and `-mapPanel collapsed|medium|large` as launch arguments (screenshots).
    fileprivate func applyLaunchArguments() {
        let defaults = UserDefaults.standard
        if let raw = defaults.string(forKey: "mapScale"), let debugScale = Scale(rawValue: raw) { show(debugScale, animated: false) }
        if let id = defaults.string(forKey: "mapSelect") {
            if let group = groups.first(where: { $0.members.contains { $0.storyId == id } }) {
                select(group)
            } else if model.stories[id]?.location?.isArea == true {
                open(id)
            }
        }
        if let chip = defaults.string(forKey: "mapChip") { select(chip: chip) }
        if let id = defaults.string(forKey: "openStory"), model.stories[id] != nil { open(id) }
        switch defaults.string(forKey: "mapPanel") {
        case "collapsed": sheetDetent = .collapsed
        case "medium": sheetDetent = .medium
        case "large": sheetDetent = .large
        default: break
        }
    }
}
#endif

/// What the panel is narrowed to.
enum ListFilter: Equatable {
    /// The stories under one tapped group pin.
    case group([String])
    /// A place chip (city, country, EU, world).
    case place(String)

    var placeId: String? {
        if case .place(let id) = self { id } else { nil }
    }

    var groupIds: [String]? {
        if case .group(let ids) = self { ids } else { nil }
    }
}

extension PresentationDetent {
    /// Smallest height: just the sheet's title and buttons, so the map has the screen.
    static let collapsed = Self.height(110)
    /// Default height, between collapsed and medium: the top stories show and most of the map stays visible.
    static let resting = Self.fraction(0.34)
}

extension Coordinate {
    var clLocation: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }
}

#Preview {
    MapScreen()
        .environment(AppModel(persona: .sara))
}
