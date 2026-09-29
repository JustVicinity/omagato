import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Ui
import qs.Commons

Panel {
  id: root
  moduleName: "io.github.justvicinity.omagato"
  ipcTarget: "io.github.justvicinity.omagato"

  readonly property string cli: String(Qt.resolvedUrl("bin/elgatoctl")).replace("file://", "")
  readonly property string assetsPath: String(Qt.resolvedUrl("assets/icon-themes")).replace("file://", "")
  property var modelState: ({ config: { pages: [{ name: "Start", keys: {} }], lights: [], brightness: 70 }, worker: { decks: [], running: false, errors: [] }, lights: [], cameras: [], audio: [], xlr: { available: false, connected: false, controls: [], mixes: [] }, prompter: { connected: false, name: "", monitors: [], scripts: [], screen: "", source: "", script: "", text: "", speed: 75, font_size: 42, flip: false }, devices: [], words: {}, visuals: { theme: "tokyo-night", catalog: [], pages: [{}] } })
  readonly property var prompterService: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
  property var apps: []
  property var discovered: []
  property var controls: []
  property var commandQueue: []
  property string pendingKind: ""
  property string message: ""
  property string fileTarget: ""
  property string galleryTarget: ""
  property bool settingsGalleryOpen: false
  property int tab: 4
  property int pageIndex: 0
  property int keyIndex: 0
  property string selectedCamera: ""
  property string editorIcon: ""
  property bool editorDirty: false
  property bool scriptDirty: false
  property bool scriptSyncing: false
  property var selectedWindow: null
  readonly property var availableWindows: ToplevelManager.toplevels.values.filter(function(item) {
    return !!item && !!String(item.title || item.appId || "").trim()
  })
  property bool pickerOpen: false
  property int pendingClearPage: -1
  property int pendingClearKey: -1
  property string pendingClearLabel: ""
  readonly property var pages: modelState.config.pages || []
  readonly property var currentPage: pages[Math.min(pageIndex, pages.length - 1)] || { name: "Start", keys: {} }
  readonly property var currentAction: currentPage.keys[String(keyIndex)] || ({})
  readonly property bool hasAction: !!currentAction.type
  readonly property var deck: modelState.worker.decks.length ? modelState.worker.decks[0] : ({ keys: 15, columns: 5, rows: 3, dials: 0, name: t("preview") })
  readonly property var globalEmpty: modelState.config.empty_default || ({ style: "theme", icon: "blank", label: "", image: "" })
  readonly property var selectedEmpty: (currentPage.empty || {})[String(keyIndex)] || globalEmpty
  readonly property color fg: bar ? bar.foreground : Color.foreground
  readonly property string fontName: bar ? bar.fontFamily : Style.font.family
  readonly property var actionTypes: [
    { id: "app", hint: "hint_app" }, { id: "script", hint: "hint_script" },
    { id: "command", hint: "hint_command" }, { id: "url", hint: "hint_url" },
    { id: "media", hint: "hint_media" }, { id: "volume", hint: "hint_volume" },
    { id: "workspace", hint: "hint_workspace" }, { id: "light", hint: "hint_light" },
    { id: "camera", hint: "hint_camera" }, { id: "prompter", hint: "hint_prompter" },
    { id: "page", hint: "hint_page" },
    { id: "multi", hint: "hint_multi" }
  ]
  readonly property var emptyStyles: ["theme", "wallpaper", "black", "accent", "image"]
  readonly property var themeIds: ["auto", "tokyo-night", "catppuccin", "gruvbox", "nord"]
  readonly property var languageIds: ["auto", "de", "en", "fr", "es"]

  implicitWidth: iconButton.implicitWidth
  implicitHeight: bar ? bar.barSize : 26

  function t(key) {
    return modelState.words && modelState.words[key] ? modelState.words[key] : key.split("_").join(" ")
  }
  function queue(args, kind) {
    var entries = commandQueue.slice()
    if (kind === "state" && (pendingKind === "state" || entries.some(function(x) { return x.kind === "state" }))) return
    if (kind === "mutation" && ["brightness", "set-light", "set-camera"].includes(args[0])) {
      var signature = args.slice(0, -1).join("\u0000")
      entries = entries.filter(function(x) { return x.args.slice(0, -1).join("\u0000") !== signature })
    }
    entries.push({ args: args, kind: kind })
    commandQueue = entries
    kick()
  }
  function kick() {
    if (process.running || commandQueue.length === 0) return
    var entries = commandQueue.slice()
    var item = entries.shift()
    commandQueue = entries
    pendingKind = item.kind
    process.command = [cli].concat(item.args)
    process.running = true
  }
  function refresh() { queue(["state"], "state") }
  function mutate(args) { queue(args, "mutation") }
  function setCameraControl(id, value) {
    queue(["set-camera", selectedCamera, id, String(value)], "camera-mutation")
  }
  function prompterCommand(name) {
    if (!prompterService) { message = t("prompter_unavailable"); return }
    if (name === "start" && scriptDirty) { message = t("prompter_unsaved"); return }
    if (name === "start") prompterService.start()
    else if (name === "mirror") prompterService.startMirror()
    else if (name === "mirrorWindow") prompterService.startWindowMirror(selectedWindow || availableWindows[0])
    else if (name === "stop") prompterService.stop()
    else if (name === "playPause") prompterService.playPause()
    else if (name === "faster") prompterService.speed = Math.min(300, prompterService.speed + 10)
    else if (name === "slower") prompterService.speed = Math.max(10, prompterService.speed - 10)
    else if (name === "nextChapter") prompterService.jump(1)
    else if (name === "prevChapter") prompterService.jump(-1)
    else if (name === "flip") prompterService.setFlip(!prompterService.flipped)
  }
  function open() {
    controller.show()
    queue(["start"], "start")
    refresh()
    if (!appsProc.running) appsProc.running = true
    Qt.callLater(function() { catcher.forceActiveFocus() })
  }
  function close() { pickerOpen = false; confirmClear.opened = false; controller.hide() }
  function switchPanel(direction) { return bar && bar.switchPanelFrom ? bar.switchPanelFrom(root, direction) : false }
  function previewFor(index) {
    var page = modelState.visuals.pages[pageIndex] || {}
    return page[String(index)] || ({ path: "", style: "theme" })
  }
  function imageUrl(path) { return path ? "file://" + path : "" }
  function saveAction(action) {
    pickerOpen = false
    mutate(["assign", String(pageIndex), String(keyIndex), JSON.stringify(action)])
  }
  function chooseApp(app) {
    saveAction({ type: "app", label: app.name, value: app.id, system_icon: app.icon, show_label: true })
    pickerSearch.text = ""
  }
  function usePreset(type, value, label) {
    var action = { type: type, value: value, label: label, show_label: true }
    if (type === "light" && modelState.lights.length) action.host = modelState.lights[0].host
    saveAction(action)
  }
  function appIconUrl(app) {
    var name = String(app.icon || "")
    if (!name) return ""
    if (name.charAt(0) === "/") return "file://" + name
    return Quickshell.iconPath(name, true)
  }
  function functionChoices() {
    var choices = [
      { type: "media", value: "play-pause", label: t("playback"), glyph: "󰐎" },
      { type: "media", value: "next", label: t("next_track"), glyph: "󰒭" },
      { type: "media", value: "previous", label: t("previous_track"), glyph: "󰒮" },
      { type: "volume", value: "up", label: t("louder"), glyph: "󰝝" },
      { type: "volume", value: "down", label: t("quieter"), glyph: "󰝞" },
      { type: "volume", value: "mute", label: t("mute"), glyph: "󰝟" }
    ]
    for (var number = 1; number <= 5; number++)
      choices.push({ type: "workspace", value: String(number), label: t("type_workspace") + " " + number, glyph: "󰖯" })
    if (modelState.lights.length)
      choices.push({ type: "light", value: "toggle", label: t("light_toggle"), glyph: "󰌵" })
    if (modelState.prompter.connected) {
      choices.push({ type: "prompter", value: "start", label: t("prompter_start"), glyph: "󰗊" })
      choices.push({ type: "prompter", value: "playPause", label: t("prompter_play_pause"), glyph: "󰐎" })
      choices.push({ type: "prompter", value: "nextChapter", label: t("prompter_next"), glyph: "󰒭" })
      choices.push({ type: "prompter", value: "mirror", label: t("prompter_mirror"), glyph: "󰍹" })
    }
    return choices
  }
  function openPicker(index) {
    keyIndex = index
    pickerSearch.text = ""
    pickerOpen = true
    if (!appsProc.running && !apps.length) appsProc.running = true
    Qt.callLater(function() {
      var bottom = Math.max(0, panelScroll.contentHeight - panelScroll.height)
      panelScroll.contentY = Math.min(bottom, Math.max(0, pickerMenu.y - Style.space(22)))
      pickerSearch.forceActiveFocus()
    })
  }
  function askClear(index) {
    var action = currentPage.keys[String(index)] || ({})
    if (!action.type) return
    pickerOpen = false
    pendingClearPage = pageIndex
    pendingClearKey = index
    pendingClearLabel = action.label || t("action")
    confirmClear.selectedIndex = 0
    confirmClear.opened = true
  }
  function saveEditor() {
    var type = actionTypes[Math.max(0, actionType.currentIndex)].id
    var action = { type: type, label: titleField.text.trim(), value: valueField.text.trim(),
                   icon: editorIcon, show_label: showLabel.checked }
    if (type === "light") action.host = hostField.text.trim()
    if (type === "camera") { action.node = nodeField.text.trim(); action.control = controlField.text.trim() }
    if (type === "multi") {
      var lines = macroField.text.split("\n")
      action.steps = []
      for (var i = 0; i < lines.length; i++) if (lines[i].trim())
        action.steps.push({ type: "command", value: lines[i].trim() })
      action.value = ""
    }
    saveAction(action)
    editorDirty = false
  }
  function editActionIcon(value) {
    editorIcon = value
    if (hasAction && !editorDirty) {
      var action = JSON.parse(JSON.stringify(currentAction))
      action.icon = value
      saveAction(action)
    }
    else editorDirty = true
  }
  function chooseAppStyle(style) {
    if (!hasAction || currentAction.type !== "app") return
    var action = JSON.parse(JSON.stringify(currentAction))
    action.icon_theme = style
    saveAction(action)
  }
  function updateEmpty(changes, global) {
    var before = global ? globalEmpty : selectedEmpty
    var spec = { style: before.style || "theme", icon: before.icon || "blank",
                 label: before.label || "", image: before.image || "" }
    for (var key in changes) spec[key] = changes[key]
    var command = global ? ["set-empty-default", JSON.stringify(spec)]
                         : ["set-empty", String(pageIndex), String(keyIndex), JSON.stringify(spec)]
    mutate(command)
  }
  function chooseEmptyStyle(index, global) {
    var style = emptyStyles[index]
    var before = global ? globalEmpty : selectedEmpty
    if (style === "image" && !before.image) { openFile(global ? "global" : "empty"); return }
    updateEmpty({ style: style }, global)
  }
  function openFile(target) { fileTarget = target; filePicker.open() }
  function syncEditors() {
    if (!titleField.activeFocus && !valueField.activeFocus && !macroField.activeFocus) {
      var action = currentAction
      titleField.text = action.label || ""
      valueField.text = action.value || ""
      macroField.text = (action.steps || []).map(function(step) { return step.value || "" }).join("\n")
      hostField.text = action.host || ""
      nodeField.text = action.node || ""
      controlField.text = action.control || ""
      editorIcon = action.icon || ""
      showLabel.checked = action.show_label !== false
      var index = actionTypes.findIndex(function(item) { return item.id === action.type })
      actionType.currentIndex = Math.max(0, index)
    }
    if (!emptyLabel.activeFocus) emptyLabel.text = selectedEmpty.label || ""
    if (!globalEmptyLabel.activeFocus) globalEmptyLabel.text = globalEmpty.label || ""
    keyEmptyStyle.currentIndex = Math.max(0, emptyStyles.indexOf(selectedEmpty.style || "theme"))
    globalEmptyStyle.currentIndex = Math.max(0, emptyStyles.indexOf(globalEmpty.style || "theme"))
    languageSelect.currentIndex = Math.max(0, languageIds.indexOf(modelState.config.language || "auto"))
    themeSelect.currentIndex = Math.max(0, themeIds.indexOf(modelState.config.icon_theme || "auto"))
  }
  onKeyIndexChanged: { editorDirty = false; syncEditors() }
  onPageIndexChanged: { editorDirty = false; syncEditors() }
  onModelStateChanged: {
    if (!editorDirty) syncEditors()
    if (prompterService) prompterService.configure(modelState.prompter)
    if (!scriptDirty) syncPrompterEditor()
  }
  function syncPrompterEditor() {
    scriptSyncing = true
    scriptEditor.text = modelState.prompter.text || ""
    scriptName.text = modelState.prompter.script || ""
    scriptSyncing = false
  }
  Component.onCompleted: syncEditors()

  Process {
    id: process
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var result = JSON.parse(text)
          if (result.error) root.message = result.error
          else if (root.pendingKind === "state") { root.modelState = result; root.message = "" }
          else if (root.pendingKind === "discover") root.discovered = result
          else if (root.pendingKind === "controls") root.controls = result
          else if (root.pendingKind.startsWith("import-")) {
            if (root.pendingKind === "import-action") root.editActionIcon(result.path)
            else if (root.pendingKind === "import-empty") root.updateEmpty({ style: "image", image: result.path }, false)
            else root.updateEmpty({ style: "image", image: result.path }, true)
            root.message = root.t("image_imported")
          } else {
            if (root.pendingKind === "prompter-save") root.scriptDirty = false
            if (root.pendingKind === "camera-mutation" && root.selectedCamera)
              root.queue(["camera-controls", root.selectedCamera], "controls")
            root.message = root.t("saved")
            refreshTimer.restart()
            if (root.pendingKind === "language") appsProc.running = true
          }
        } catch (error) { root.message = root.t("response_error") }
      }
    }
    stderr: StdioCollector { waitForEnd: true }
    onRunningChanged: if (!running) root.kick()
  }
  Process {
    id: appsProc
    command: [root.cli, "apps"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: try { root.apps = JSON.parse(text) } catch (error) { root.apps = [] }
    }
  }
  Timer { id: refreshTimer; interval: 280; onTriggered: root.refresh() }
  Timer { interval: 4000; repeat: true; running: root.opened; onTriggered: root.refresh() }
  FileDialog {
    id: filePicker
    title: root.t("choose_image")
    fileMode: FileDialog.OpenFile
    nameFilters: ["Images (*.png *.jpg *.jpeg *.webp)"]
    onAccepted: {
      var path = decodeURIComponent(String(selectedFile).replace(/^file:\/\//, ""))
      root.queue(["import-icon", path], "import-" + root.fileTarget)
    }
  }

  BarIconButton {
    id: iconButton
    anchors.fill: parent
    bar: root.bar
    text: ""
    iconComponent: Component {
      Rectangle {
        radius: width / 2
        color: Color.accent
        Image {
          anchors.centerIn: parent
          width: parent.width * .76
          height: width
          source: Qt.resolvedUrl("assets/brand/elgato.svg")
          fillMode: Image.PreserveAspectFit
        }
      }
    }
    tooltipText: root.t("title")
    onPressed: root.toggle()
  }

  KeyboardPanel {
    id: panel
    anchorItem: iconButton
    owner: root
    bar: root.bar
    open: root.opened
    margin: Style.space(20)
    focusTarget: catcher
    contentWidth: panel.fittedContentWidth(Style.space(590))
    contentHeight: panel.fittedContentHeight(Style.space(690), Style.space(760))

  PanelKeyCatcher {
      id: catcher
      anchors.fill: parent
      blocked: root.pickerOpen && pickerSearch.activeFocus && !confirmClear.opened
      onCloseRequested: {
        if (confirmClear.opened) confirmClear.canceled()
        else if (root.pickerOpen) root.pickerOpen = false
        else root.close()
      }
      onReturnRequested: {
        if (confirmClear.opened) {
          if (confirmClear.selectedIndex === 0) confirmClear.canceled()
          else confirmClear.confirmed()
        }
      }
      onMoveRequested: function(dx, dy) {
        if (confirmClear.opened && dx !== 0) confirmClear.selectedIndex = dx > 0 ? 1 : 0
      }
      onTabRequested: function(direction) { if (!confirmClear.opened) root.switchPanel(direction) }

      Flickable {
        id: panelScroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: body.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar {
          policy: ScrollBar.AsNeeded
          active: panelScroll.contentHeight > panelScroll.height
        }
        Column {
          id: body
          x: Style.space(6)
          width: Math.max(1, panelScroll.width - Style.space(12))
          spacing: Style.space(12)

          Row {
            width: parent.width
            spacing: Style.space(8)
            Rectangle {
              width: Style.space(30)
              height: width
              radius: 9
              color: Color.accent
              Image {
                anchors.centerIn: parent
                width: parent.width * .68
                height: width
                source: Qt.resolvedUrl("assets/brand/elgato.svg")
                fillMode: Image.PreserveAspectFit
              }
            }
            Text { textFormat: Text.PlainText;
              text: root.t("title")
              width: parent.width - reload.implicitWidth - Style.space(52)
              color: root.fg
              font.family: root.fontName
              font.bold: true
              font.pixelSize: Style.font.title
            }
            ActionChip { id: reload; label: root.t("refresh"); onClicked: root.refresh() }
          }
          Text { textFormat: Text.PlainText;
            width: parent.width
            text: root.message || (root.modelState.worker.errors.length ? root.modelState.worker.errors[0]
                 : root.modelState.worker.decks.length ? root.t("ready")
                 : root.modelState.worker.running ? root.t("no_deck") : root.t("no_service"))
            color: root.modelState.worker.errors.length ? Color.urgent : Color.muted
            wrapMode: Text.Wrap
            font.family: root.fontName
            font.pixelSize: Style.font.caption
          }
          Flow {
            width: parent.width
            spacing: Style.space(6)
            ActionChip { label: root.t("devices"); selected: root.tab === 4; onClicked: root.tab = 4 }
            ActionChip { label: root.t("deck"); selected: root.tab === 0; onClicked: root.tab = 0 }
            ActionChip { label: root.t("lights"); selected: root.tab === 1; onClicked: root.tab = 1 }
            ActionChip { label: root.t("camera"); selected: root.tab === 2; onClicked: root.tab = 2 }
            ActionChip { label: root.t("prompter"); selected: root.tab === 6; onClicked: root.tab = 6 }
            ActionChip { label: root.t("audio"); selected: root.tab === 5; onClicked: root.tab = 5 }
            ActionChip { label: root.t("settings"); selected: root.tab === 3; onClicked: root.tab = 3 }
          }
          PanelSeparator { width: parent.width }

          Column {
            visible: root.tab === 4
            width: parent.width
            spacing: Style.space(10)
            Text { textFormat: Text.PlainText;
              text: root.t("device_overview")
              color: root.fg
              font.family: root.fontName
              font.pixelSize: Style.font.title
              font.bold: true
            }
            Text { textFormat: Text.PlainText;
              width: parent.width
              text: root.t("device_overview_hint")
              color: Color.muted
              font.family: root.fontName
              wrapMode: Text.Wrap
            }
            Repeater {
              model: root.modelState.devices || []
              Rectangle {
                id: familyCard
                required property var modelData
                width: parent.width
                implicitHeight: familyContent.implicitHeight + Style.space(20)
                radius: 14
                color: Color.popups.background
                border.width: 1
                border.color: familyCard.modelData.connected ? Color.accent : Color.popups.border
                opacity: familyCard.modelData.connected ? 1 : .55
                Column {
                  id: familyContent
                  x: Style.space(10)
                  y: Style.space(10)
                  width: parent.width - Style.space(20)
                  spacing: Style.space(5)
                  Row {
                    spacing: Style.space(8)
                    Rectangle {
                      width: Style.space(8)
                      height: width
                      radius: width / 2
                      color: familyCard.modelData.connected ? Color.accent : Color.muted
                      anchors.verticalCenter: parent.verticalCenter
                    }
                    Text { textFormat: Text.PlainText;
                      text: root.t("family_" + familyCard.modelData.id)
                      color: root.fg
                      font.family: root.fontName
                      font.bold: true
                    }
                    Text { textFormat: Text.PlainText;
                      text: familyCard.modelData.connected ? root.t("connected") : root.t("not_connected")
                      color: familyCard.modelData.connected ? Color.accent : Color.muted
                      font.family: root.fontName
                    }
                  }
                  Repeater {
                    model: familyCard.modelData.devices
                    Text { textFormat: Text.PlainText;
                      required property var modelData
                      width: parent.width
                      text: modelData.name + " · " + root.t("level_" + modelData.level) + (modelData.detail ? " · " + modelData.detail : "")
                      color: root.fg
                      font.family: root.fontName
                      wrapMode: Text.Wrap
                    }
                  }
                  Text { textFormat: Text.PlainText;
                    visible: familyCard.modelData.variants.length > 0
                    width: parent.width
                    text: familyCard.modelData.variants.join(" · ")
                    color: Color.muted
                    font.family: root.fontName
                    font.pixelSize: Style.font.caption
                    wrapMode: Text.Wrap
                  }
                  ActionChip {
                    visible: familyCard.modelData.connected && ["deck", "light", "camera", "capture", "audio"].includes(familyCard.modelData.id)
                    label: root.t("open_controls")
                    onClicked: root.tab = familyCard.modelData.id === "deck" ? 0 : familyCard.modelData.id === "light" ? 1 : familyCard.modelData.id === "audio" ? 5 : 2
                  }
                  ActionChip {
                    visible: familyCard.modelData.id === "camera" && root.modelState.prompter.connected
                    label: root.t("prompter")
                    onClicked: root.tab = 6
                  }
                }
              }
            }
          }

          Column {
            visible: root.tab === 0
            width: parent.width
            spacing: Style.space(10)
            Text { textFormat: Text.PlainText;
              text: root.deck.name + " · " + root.deck.keys + " " + root.t("key")
              color: root.fg
              font.family: root.fontName
              font.pixelSize: Style.font.body
            }
            Flow {
              width: parent.width
              spacing: Style.space(8)
              UiSelect {
                width: Math.max(Style.space(120), parent.width - addPage.implicitWidth
                                - deletePage.implicitWidth * (deletePage.visible ? 1 : 0)
                                - Style.space(deletePage.visible ? 20 : 10))
                model: root.pages.map(function(page) { return page.name })
                currentIndex: root.pageIndex
                onActivated: function(index) { root.pageIndex = index; root.keyIndex = 0; root.syncEditors() }
              }
              ActionChip {
                id: addPage
                label: root.t("add_page")
                onClicked: root.mutate(["new-page", root.t("page_name") + " " + (root.pages.length + 1)])
              }
              ActionChip {
                id: deletePage
                visible: root.pageIndex > 0
                label: root.t("delete_page")
                onClicked: {
                  var oldIndex = root.pageIndex
                  root.pageIndex = Math.max(0, oldIndex - 1)
                  root.mutate(["delete-page", String(oldIndex)])
                }
              }
            }
            Grid {
              id: keyGrid
              width: parent.width
              columns: Math.max(1, root.deck.columns)
              spacing: Style.space(6)
              Repeater {
                model: root.deck.keys
                Rectangle {
                  id: keyTile
                  required property int index
                  readonly property var action: root.currentPage.keys[String(index)] || ({})
                  readonly property var visual: root.previewFor(index)
                  width: (keyGrid.width - keyGrid.spacing * (keyGrid.columns - 1)) / keyGrid.columns
                  height: Math.max(Style.space(62), width * .82)
                  radius: 9
                  color: visual.style === "black" ? "#000000" : visual.style === "accent" ? Color.accent : Color.popups.background
                  border.width: root.keyIndex === index ? 3 : 1
                  border.color: root.keyIndex === index ? Color.accent : Color.popups.border
                  clip: true
                  Image {
                    anchors.fill: parent
                    anchors.margins: 3
                    source: root.imageUrl(keyTile.visual.path)
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                  }
                  Rectangle {
                    visible: !!keyTile.action.type && !!keyTile.action.label && keyTile.action.show_label !== false
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: Style.space(23)
                    color: Color.popups.background
                    opacity: .86
                  }
                  Text { textFormat: Text.PlainText;
                    visible: !!keyTile.action.type && !!keyTile.action.label && keyTile.action.show_label !== false
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: Style.space(23)
                    text: keyTile.action.label || ""
                    color: Color.popups.text
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.family: root.fontName
                    font.pixelSize: Style.font.caption
                  }
                  Rectangle {
                    visible: !keyTile.action.type
                    anchors.centerIn: parent
                    width: Math.min(Style.space(38), parent.width * .48)
                    height: width
                    radius: width / 2
                    color: "#bd171923"
                    border.width: 2
                    border.color: Color.accent
                    Text { textFormat: Text.PlainText;
                      anchors.centerIn: parent
                      text: "+"
                      color: "white"
                      font.family: root.fontName
                      font.pixelSize: Style.font.title
                      font.bold: true
                    }
                  }
                  MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    cursorShape: Qt.PointingHandCursor
                    onClicked: function(mouse) {
                      root.keyIndex = keyTile.index
                      if (mouse.button === Qt.RightButton) root.askClear(keyTile.index)
                      else if (!keyTile.action.type) root.openPicker(keyTile.index)
                      else { root.pickerOpen = false; root.syncEditors() }
                    }
                  }
                }
              }
            }
            Rectangle {
              id: pickerMenu
              visible: root.pickerOpen
              width: parent.width
              height: pickerContent.implicitHeight + Style.space(20)
              radius: 10
              color: Color.popups.background
              border.width: 2
              border.color: Color.accent
              Column {
                id: pickerContent
                x: Style.space(10)
                y: Style.space(10)
                width: parent.width - Style.space(20)
                spacing: Style.space(8)
                Row {
                  width: parent.width
                  spacing: Style.space(8)
                  Text { textFormat: Text.PlainText;
                    width: parent.width - closePicker.implicitWidth - Style.space(8)
                    text: root.t("assign_key") + " " + (root.keyIndex + 1)
                    color: root.fg
                    font.family: root.fontName
                    font.bold: true
                    verticalAlignment: Text.AlignVCenter
                    height: closePicker.implicitHeight
                  }
                  ActionChip { id: closePicker; label: root.t("close_menu"); onClicked: root.pickerOpen = false }
                }
                UiField { id: pickerSearch; width: parent.width; placeholderText: root.t("search_apps") }
                Text { textFormat: Text.PlainText; text: root.t("installed_apps"); color: Color.muted; font.family: root.fontName; font.pixelSize: Style.font.caption }
                Column {
                  width: parent.width
                  spacing: Style.space(2)
                  Repeater {
                    model: root.apps.filter(function(app) {
                      return app.name.toLowerCase().includes(pickerSearch.text.toLowerCase())
                    }).slice(0, pickerSearch.text ? 12 : 6)
                    PickerRow {
                      required property var modelData
                      width: parent.width
                      label: modelData.name
                      iconSource: root.appIconUrl(modelData)
                      onChosen: root.chooseApp(modelData)
                    }
                  }
                }
                Text { textFormat: Text.PlainText;
                  visible: root.apps.length === 0
                  text: root.t("no_apps")
                  color: Color.muted
                  font.family: root.fontName
                }
                Text { textFormat: Text.PlainText;
                  visible: pickerSearch.text.length === 0
                  text: root.t("quick_actions")
                  color: Color.muted
                  font.family: root.fontName
                  font.pixelSize: Style.font.caption
                }
                Flow {
                  visible: pickerSearch.text.length === 0
                  width: parent.width
                  spacing: Style.space(6)
                  Repeater {
                    model: root.functionChoices()
                    ActionChip {
                      required property var modelData
                      label: modelData.label
                      onClicked: root.usePreset(modelData.type, modelData.value, modelData.label)
                    }
                  }
                }
                ActionChip {
                  label: root.t("custom_action") + "…"
                  onClicked: {
                    root.pickerOpen = false
                    Qt.callLater(function() {
                      panelScroll.contentY = Math.min(panelScroll.contentHeight - panelScroll.height,
                                                       Math.max(0, actionHeader.y - Style.space(20)))
                    })
                  }
                }
              }
            }
            Text { textFormat: Text.PlainText;
              id: actionHeader
              text: root.t("key") + " " + (root.keyIndex + 1) + " · " + root.t("action")
              color: root.fg
              font.family: root.fontName
              font.bold: true
            }
            ActionChip { visible: root.hasAction; label: root.t("change_action"); onClicked: root.openPicker(root.keyIndex) }
            Text { textFormat: Text.PlainText; text: root.t("custom_action"); color: root.fg; font.family: root.fontName; font.bold: true }
            Row {
              width: parent.width
              spacing: Style.space(8)
              UiSelect {
                id: actionType
                width: parent.width * .40
                model: root.actionTypes.map(function(item) { return root.t("type_" + item.id) })
                onActivated: root.editorDirty = true
              }
              UiField { id: titleField; width: parent.width * .58; placeholderText: root.t("label"); onTextEdited: root.editorDirty = true }
            }
            UiField {
              id: valueField
              width: parent.width
              visible: root.actionTypes[Math.max(0, actionType.currentIndex)].id !== "multi"
              placeholderText: root.t(root.actionTypes[Math.max(0, actionType.currentIndex)].hint)
              onTextEdited: root.editorDirty = true
            }
            TextArea {
              id: macroField
              width: parent.width
              height: Style.space(85)
              visible: root.actionTypes[Math.max(0, actionType.currentIndex)].id === "multi"
              placeholderText: root.t("hint_multi")
              wrapMode: TextEdit.NoWrap
              color: Color.popups.text
              background: Rectangle { color: Color.popups.background; border.color: Color.popups.border; radius: 8 }
              onTextChanged: if (activeFocus) root.editorDirty = true
            }
            UiField { id: hostField; width: parent.width; visible: root.actionTypes[Math.max(0, actionType.currentIndex)].id === "light"; placeholderText: root.t("host"); onTextEdited: root.editorDirty = true }
            UiField { id: nodeField; width: parent.width; visible: root.actionTypes[Math.max(0, actionType.currentIndex)].id === "camera"; placeholderText: root.t("node"); onTextEdited: root.editorDirty = true }
            UiField { id: controlField; width: parent.width; visible: root.actionTypes[Math.max(0, actionType.currentIndex)].id === "camera"; placeholderText: root.t("control"); onTextEdited: root.editorDirty = true }
            Row {
              spacing: Style.space(8)
              ActionChip { label: root.t("save"); selected: true; onClicked: root.saveEditor() }
              ActionChip { label: root.t("clear_key"); enabled: root.hasAction; onClicked: root.askClear(root.keyIndex) }
            }
            CheckBox { id: showLabel; text: root.t("label"); checked: true; visible: root.hasAction; onClicked: root.editorDirty = true }
            Column {
              visible: root.hasAction && root.currentAction.type === "app"
                       && !String(root.currentAction.icon || "").startsWith("/")
              width: parent.width
              spacing: Style.space(6)
              Text { textFormat: Text.PlainText; text: root.t("app_styles"); color: root.fg; font.family: root.fontName; font.bold: true }
              Text { textFormat: Text.PlainText; text: root.t("style_follows_theme"); color: Color.muted; font.family: root.fontName; wrapMode: Text.Wrap; width: parent.width }
              Flow {
                width: parent.width
                spacing: Style.space(8)
                ActionChip {
                  label: root.t("automatic")
                  selected: !root.currentAction.icon_theme || root.currentAction.icon_theme === "auto"
                  onClicked: root.chooseAppStyle("auto")
                }
                Repeater {
                  model: root.themeIds.slice(1)
                  Rectangle {
                    id: styleTile
                    required property string modelData
                    width: Style.space(92)
                    height: Style.space(116)
                    radius: 8
                    color: Color.popups.background
                    border.width: root.currentAction.icon_theme === modelData ? 3 : 1
                    border.color: root.currentAction.icon_theme === modelData ? Color.accent : Color.popups.border
                    Image {
                      anchors.top: parent.top
                      anchors.horizontalCenter: parent.horizontalCenter
                      anchors.topMargin: Style.space(5)
                      width: Style.space(82)
                      height: Style.space(82)
                      source: root.imageUrl((root.previewFor(root.keyIndex).variants || {})[styleTile.modelData] || "")
                      fillMode: Image.PreserveAspectFit
                      asynchronous: true
                    }
                    Text { textFormat: Text.PlainText;
                      anchors.bottom: parent.bottom
                      anchors.horizontalCenter: parent.horizontalCenter
                      anchors.bottomMargin: Style.space(4)
                      text: styleTile.modelData === "tokyo-night" ? "Tokyo Night" :
                            styleTile.modelData === "catppuccin" ? "Catppuccin" :
                            styleTile.modelData === "gruvbox" ? "Gruvbox" : "Nord"
                      color: root.fg
                      font.family: root.fontName
                      font.pixelSize: Style.font.caption
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.chooseAppStyle(styleTile.modelData) }
                  }
                }
              }
            }
            Row {
              spacing: Style.space(8)
              ActionChip { label: root.t("icon_library"); onClicked: root.galleryTarget = root.galleryTarget === "action" ? "" : "action" }
              ActionChip { label: root.t("choose_icon"); onClicked: root.openFile("action") }
              ActionChip { label: root.t("reset_icon"); visible: !!root.editorIcon; onClicked: root.editActionIcon("") }
            }
            IconGallery {
              visible: root.galleryTarget === "action"
              width: parent.width
              catalog: root.modelState.visuals.catalog
              theme: root.modelState.visuals.theme
              assetsPath: root.assetsPath
              selectedIcon: root.editorIcon.startsWith("pack:") ? root.editorIcon.slice(5) : ""
              searchPlaceholder: root.t("icon_library")
              onChosen: function(icon) { root.editActionIcon("pack:" + icon); root.galleryTarget = "" }
            }
            PanelSeparator { width: parent.width }
            Text { textFormat: Text.PlainText; text: root.t("selected_empty"); color: root.fg; font.family: root.fontName; font.bold: true }
            Text { textFormat: Text.PlainText; text: root.t("empty_hint"); color: Color.muted; font.family: root.fontName; wrapMode: Text.Wrap; width: parent.width }
            Row {
              width: parent.width
              spacing: Style.space(8)
              UiSelect {
                id: keyEmptyStyle
                width: parent.width * .43
                model: root.emptyStyles.map(function(style) { return root.t("style_" + style) })
                onActivated: function(index) { root.chooseEmptyStyle(index, false) }
              }
              UiField {
                id: emptyLabel
                width: parent.width * .53
                placeholderText: root.t("label")
                onEditingFinished: root.updateEmpty({ label: text }, false)
              }
            }
            Row {
              spacing: Style.space(8)
              ActionChip { label: root.t("icon_library"); onClicked: root.galleryTarget = root.galleryTarget === "empty" ? "" : "empty" }
              ActionChip { label: root.t("choose_image"); onClicked: root.openFile("empty") }
              ActionChip { label: root.t("use_default"); onClicked: root.mutate(["clear-empty", String(root.pageIndex), String(root.keyIndex)]) }
            }
            IconGallery {
              visible: root.galleryTarget === "empty"
              width: parent.width
              catalog: root.modelState.visuals.catalog
              theme: root.modelState.visuals.theme
              assetsPath: root.assetsPath
              selectedIcon: root.selectedEmpty.icon || "blank"
              searchPlaceholder: root.t("icon_library")
              onChosen: function(icon) { root.updateEmpty({ style: "theme", icon: icon }, false); root.galleryTarget = "" }
            }
          }

          Column {
            visible: root.tab === 1
            width: parent.width
            spacing: Style.space(10)
            Text { textFormat: Text.PlainText; text: root.t("lights"); color: root.fg; font.family: root.fontName; font.bold: true }
            Text { textFormat: Text.PlainText; width: parent.width; text: root.t("lights_intro"); color: Color.muted; wrapMode: Text.Wrap; font.family: root.fontName }
            ActionChip { label: root.t("find_lights"); onClicked: root.queue(["discover-lights"], "discover") }
            Repeater {
              model: root.discovered
              ActionChip {
                required property var modelData
                label: modelData.name + " · " + modelData.host
                onClicked: root.mutate(["add-light", modelData.host, modelData.name])
              }
            }
            Row {
              width: parent.width
              spacing: Style.space(8)
              UiField { id: lightHost; width: parent.width * .70; placeholderText: root.t("light_address") }
              ActionChip { label: root.t("add"); onClicked: root.mutate(["add-light", lightHost.text.trim()]) }
            }
            Column {
              visible: root.modelState.lights.length > 1
              width: parent.width
              spacing: Style.space(5)
              Text { textFormat: Text.PlainText; text: root.t("lights_group"); color: root.fg; font.family: root.fontName; font.bold: true }
              Row {
                spacing: Style.space(6)
                ActionChip { label: root.t("turn_on"); onClicked: root.mutate(["set-all-lights", "on", "1"]) }
                ActionChip { label: root.t("turn_off"); onClicked: root.mutate(["set-all-lights", "on", "0"]) }
              }
              Text { textFormat: Text.PlainText; text: root.t("brightness"); color: root.fg; font.family: root.fontName }
              Slider {
                width: parent.width
                from: 1; to: 100
                value: root.modelState.lights.length ? root.modelState.lights.reduce(function(sum, light) {
                  return sum + Number(light.state && light.state.brightness || 50)
                }, 0) / root.modelState.lights.length : 50
                onMoved: root.mutate(["set-all-lights", "brightness", String(Math.round(value))])
              }
              Text { textFormat: Text.PlainText; text: root.t("temperature"); color: root.fg; font.family: root.fontName }
              Slider {
                width: parent.width
                from: 143; to: 344
                value: root.modelState.lights.length ? root.modelState.lights.reduce(function(sum, light) {
                  return sum + Number(light.state && light.state.temperature || 250)
                }, 0) / root.modelState.lights.length : 250
                onMoved: root.mutate(["set-all-lights", "temperature", String(Math.round(value))])
              }
            }
            Repeater {
              model: root.modelState.lights
              Column {
                id: lightRow
                required property var modelData
                width: parent.width
                spacing: Style.space(4)
                Text { textFormat: Text.PlainText; text: lightRow.modelData.name + (lightRow.modelData.error ? " · " + root.t("offline") : ""); color: root.fg; font.family: root.fontName; font.bold: true }
                Text { textFormat: Text.PlainText; visible: !!lightRow.modelData.error; text: lightRow.modelData.error || ""; color: Color.urgent; font.family: root.fontName; wrapMode: Text.Wrap; width: parent.width }
                Row {
                  spacing: Style.space(6)
                  ActionChip { label: lightRow.modelData.state && lightRow.modelData.state.on ? root.t("turn_off") : root.t("turn_on"); onClicked: root.mutate(["set-light", lightRow.modelData.host, "on", lightRow.modelData.state && lightRow.modelData.state.on ? "0" : "1"]) }
                  ActionChip { label: root.t("identify_light"); onClicked: root.mutate(["identify-light", lightRow.modelData.host]) }
                  ActionChip { label: root.t("remove"); onClicked: root.mutate(["remove-light", lightRow.modelData.host]) }
                }
                Row {
                  spacing: Style.space(6)
                  UiField { id: lightName; width: lightRow.width * .65; text: lightRow.modelData.name }
                  ActionChip {
                    label: root.t("rename")
                    enabled: !!lightName.text.trim()
                    onClicked: root.mutate(["rename-light", lightRow.modelData.host, lightName.text.trim()])
                  }
                }
                Text { textFormat: Text.PlainText; visible: !!lightRow.modelData.state && lightRow.modelData.state.brightness !== undefined; text: root.t("brightness") + " " + (lightRow.modelData.state ? lightRow.modelData.state.brightness : "–") + "%"; color: root.fg; font.family: root.fontName }
                Slider { visible: !!lightRow.modelData.state && lightRow.modelData.state.brightness !== undefined; width: parent.width; from: 1; to: 100; value: lightRow.modelData.state ? lightRow.modelData.state.brightness : 50; onMoved: root.mutate(["set-light", lightRow.modelData.host, "brightness", String(Math.round(value))]) }
                Text { textFormat: Text.PlainText; visible: !!lightRow.modelData.state && lightRow.modelData.state.temperature !== undefined; text: root.t("temperature") + " " + (lightRow.modelData.state ? lightRow.modelData.state.temperature : "–"); color: root.fg; font.family: root.fontName }
                Slider { visible: !!lightRow.modelData.state && lightRow.modelData.state.temperature !== undefined; width: parent.width; from: 143; to: 344; value: lightRow.modelData.state ? lightRow.modelData.state.temperature : 250; onMoved: root.mutate(["set-light", lightRow.modelData.host, "temperature", String(Math.round(value))]) }
                PanelSeparator { width: parent.width }
              }
            }
          }

          Column {
            visible: root.tab === 2
            width: parent.width
            spacing: Style.space(10)
            Text { textFormat: Text.PlainText; text: root.t("camera"); color: root.fg; font.family: root.fontName; font.bold: true }
            Text { textFormat: Text.PlainText; width: parent.width; text: root.t("camera_intro"); color: Color.muted; wrapMode: Text.Wrap; font.family: root.fontName }
            Text { textFormat: Text.PlainText; visible: root.modelState.cameras.length === 0; text: root.t("no_camera"); color: Color.muted; font.family: root.fontName }
            Loader {
              id: cameraPreview
              active: root.tab === 2 && !!root.selectedCamera
              source: Qt.resolvedUrl("CameraPreview.qml")
              width: parent.width
              height: active ? Math.min(260, width * 9 / 16) : 0
              Binding { target: cameraPreview.item; property: "deviceNode"; value: root.selectedCamera }
              Binding {
                target: cameraPreview.item
                property: "deviceName"
                value: {
                  var match = root.modelState.cameras.find(function(camera) { return camera.node === root.selectedCamera })
                  return match ? match.name : ""
                }
              }
            }
            Repeater {
              model: root.modelState.cameras
              Row {
                id: cameraRow
                required property var modelData
                spacing: Style.space(8)
                Text { textFormat: Text.PlainText; text: cameraRow.modelData.name + " · " + cameraRow.modelData.node; color: root.fg; font.family: root.fontName }
                ActionChip { label: root.t("load_controls"); onClicked: { root.selectedCamera = cameraRow.modelData.node; root.queue(["camera-controls", root.selectedCamera], "controls") } }
              }
            }
            Repeater {
              model: root.controls
              Column {
                id: controlRow
                required property var modelData
                width: parent.width
                spacing: Style.space(4)
                readonly property bool toggle: ["bool", "boolean"].includes(modelData.type)
                  || (modelData.type === "int" && modelData.min === 0 && modelData.max === 1)
                readonly property bool menu: ["menu", "intmenu"].includes(modelData.type)
                readonly property bool range: ["int", "integer", "int64"].includes(modelData.type) && !toggle
                  && modelData.min !== undefined && modelData.max !== undefined
                Text { textFormat: Text.PlainText;
                  text: controlRow.modelData.id.split("_").join(" ") + " · " + String(controlRow.modelData.value === undefined ? "–" : controlRow.modelData.value)
                  color: controlRow.modelData.writable ? root.fg : Color.muted
                  font.family: root.fontName
                }
                CheckBox {
                  visible: controlRow.toggle
                  enabled: controlRow.modelData.writable
                  checked: Number(controlRow.modelData.value || 0) !== 0
                  text: checked ? root.t("turn_on") : root.t("turn_off")
                  onClicked: root.setCameraControl(controlRow.modelData.id, checked ? 1 : 0)
                }
                UiSelect {
                  width: parent.width
                  visible: controlRow.menu
                  enabled: controlRow.modelData.writable
                  model: controlRow.modelData.options.map(function(option) { return option.label })
                  currentIndex: Math.max(0, controlRow.modelData.options.findIndex(function(option) {
                    return option.value === controlRow.modelData.value
                  }))
                  onActivated: function(index) {
                    root.setCameraControl(controlRow.modelData.id, controlRow.modelData.options[index].value)
                  }
                }
                Slider {
                  id: cameraSlider
                  visible: controlRow.range
                  enabled: controlRow.modelData.writable
                  width: parent.width
                  from: controlRow.modelData.min
                  to: controlRow.modelData.max
                  stepSize: controlRow.modelData.step || 1
                  value: controlRow.modelData.value
                  onMoved: root.setCameraControl(controlRow.modelData.id, Math.round(value))
                }
                ActionChip {
                  visible: controlRow.modelData.type === "button"
                  enabled: controlRow.modelData.writable
                  label: root.t("camera_trigger")
                  onClicked: root.setCameraControl(controlRow.modelData.id, 1)
                }
                Row {
                  visible: controlRow.modelData.type === "bitmask" || (controlRow.modelData.type === "int64" && !controlRow.range)
                  spacing: Style.space(6)
                  UiField { id: rawValue; text: String(controlRow.modelData.value || 0); width: controlRow.width * .65 }
                  ActionChip {
                    label: root.t("apply")
                    enabled: controlRow.modelData.writable
                    onClicked: root.setCameraControl(controlRow.modelData.id, rawValue.text.trim())
                  }
                }
                ActionChip {
                  visible: controlRow.modelData.writable && controlRow.modelData.default !== undefined
                  label: root.t("camera_reset")
                  onClicked: root.setCameraControl(controlRow.modelData.id, controlRow.modelData.default)
                }
              }
            }
          }

          Column {
            visible: root.tab === 6
            width: parent.width
            spacing: Style.space(10)
            Text { textFormat: Text.PlainText; text: root.t("prompter"); color: root.fg; font.family: root.fontName; font.bold: true }
            Text { textFormat: Text.PlainText;
              width: parent.width
              text: root.modelState.prompter.connected ? root.modelState.prompter.name
                    : root.t("prompter_disconnected")
              color: root.modelState.prompter.connected ? Color.accent : Color.muted
              wrapMode: Text.Wrap
              font.family: root.fontName
            }
            Text { textFormat: Text.PlainText;
              width: parent.width
              text: root.t("prompter_native_hint")
              color: Color.muted
              wrapMode: Text.Wrap
              font.family: root.fontName
            }
            Text { textFormat: Text.PlainText; text: root.t("prompter_screen"); color: root.fg; font.family: root.fontName; font.bold: true }
            UiSelect {
              width: parent.width
              model: root.modelState.prompter.monitors.map(function(m) { return m.description + " · " + m.name })
              currentIndex: Math.max(0, root.modelState.prompter.monitors.findIndex(function(m) { return m.name === root.modelState.prompter.screen }))
              onActivated: function(index) { root.mutate(["prompter-set", "screen", root.modelState.prompter.monitors[index].name]) }
            }
            Text { textFormat: Text.PlainText; text: root.t("prompter_source"); color: root.fg; font.family: root.fontName; font.bold: true }
            UiSelect {
              width: parent.width
              model: root.modelState.prompter.monitors.filter(function(m) { return m.name !== root.modelState.prompter.screen }).map(function(m) { return m.description + " · " + m.name })
              currentIndex: Math.max(0, root.modelState.prompter.monitors.filter(function(m) { return m.name !== root.modelState.prompter.screen }).findIndex(function(m) { return m.name === root.modelState.prompter.source }))
              onActivated: function(index) {
                var choices = root.modelState.prompter.monitors.filter(function(m) { return m.name !== root.modelState.prompter.screen })
                root.mutate(["prompter-set", "source", choices[index].name])
              }
            }
            Text { textFormat: Text.PlainText; text: root.t("prompter_script"); color: root.fg; font.family: root.fontName; font.bold: true }
            UiSelect {
              width: parent.width
              model: root.modelState.prompter.scripts
              currentIndex: Math.max(0, root.modelState.prompter.scripts.indexOf(root.modelState.prompter.script))
              onActivated: function(index) {
                if (root.scriptDirty) {
                  root.message = root.t("prompter_unsaved")
                  currentIndex = Math.max(0, root.modelState.prompter.scripts.indexOf(root.modelState.prompter.script))
                } else root.mutate(["prompter-set", "script", root.modelState.prompter.scripts[index]])
              }
            }
            UiField {
              id: scriptName
              width: parent.width
              placeholderText: root.t("prompter_script_name")
              onTextEdited: if (!root.scriptSyncing) root.scriptDirty = true
            }
            ScrollView {
              width: parent.width
              height: Style.space(190)
              TextArea {
                id: scriptEditor
                wrapMode: TextEdit.Wrap
                placeholderText: root.t("prompter_script_placeholder")
                color: root.fg
                font.family: root.fontName
                font.pixelSize: Style.font.body
                onTextChanged: if (!root.scriptSyncing) root.scriptDirty = true
                background: Rectangle { color: Color.popups.background; radius: 8; border.color: Color.popups.border }
              }
            }
            ActionChip {
              label: root.t("prompter_save_script")
              enabled: scriptName.text.trim().length > 0
              onClicked: root.queue(["prompter-save", scriptName.text.trim(), scriptEditor.text], "prompter-save")
            }
            ActionChip {
              visible: root.scriptDirty
              label: root.t("prompter_discard")
              onClicked: { root.scriptDirty = false; root.syncPrompterEditor() }
            }
            Text { textFormat: Text.PlainText; text: root.t("prompter_window"); color: root.fg; font.family: root.fontName; font.bold: true }
            UiSelect {
              width: parent.width
              model: root.availableWindows.map(function(item) { return String(item.title || item.appId) + " · " + String(item.appId || "") })
              currentIndex: Math.max(0, root.availableWindows.indexOf(root.selectedWindow))
              onActivated: function(index) { root.selectedWindow = root.availableWindows[index] || null }
            }
            Text { textFormat: Text.PlainText; text: root.t("prompter_speed") + " · " + Math.round(speedSlider.value); color: root.fg; font.family: root.fontName }
            Slider {
              id: speedSlider
              width: parent.width
              from: 10
              to: 300
              value: root.modelState.prompter.speed || 75
              onMoved: root.mutate(["prompter-set", "speed", String(Math.round(value))])
            }
            Text { textFormat: Text.PlainText; text: root.t("prompter_font_size") + " · " + Math.round(fontSlider.value); color: root.fg; font.family: root.fontName }
            Slider {
              id: fontSlider
              width: parent.width
              from: 20
              to: 90
              value: root.modelState.prompter.font_size || 42
              onMoved: root.mutate(["prompter-set", "font_size", String(Math.round(value))])
            }
            CheckBox {
              text: root.t("prompter_flip")
              checked: root.modelState.prompter.flip || false
              onClicked: {
                if (root.prompterService) root.prompterService.setFlip(checked)
                root.mutate(["prompter-set", "flip", checked ? "1" : "0"])
              }
            }
            Flow {
              width: parent.width
              spacing: Style.space(6)
              ActionChip { label: root.t("prompter_start"); onClicked: root.prompterCommand("start") }
              ActionChip { label: root.t("prompter_mirror"); enabled: !!root.modelState.prompter.source; onClicked: root.prompterCommand("mirror") }
              ActionChip { label: root.t("prompter_mirror_window"); enabled: root.availableWindows.length > 0; onClicked: root.prompterCommand("mirrorWindow") }
              ActionChip { label: root.t("prompter_off"); onClicked: root.prompterCommand("stop") }
              ActionChip { label: root.t("prompter_play_pause"); onClicked: root.prompterCommand("playPause") }
              ActionChip { label: root.t("prompter_faster"); onClicked: root.prompterCommand("faster") }
              ActionChip { label: root.t("prompter_slower"); onClicked: root.prompterCommand("slower") }
              ActionChip { label: root.t("prompter_next"); onClicked: root.prompterCommand("nextChapter") }
              ActionChip { label: root.t("prompter_previous"); onClicked: root.prompterCommand("prevChapter") }
            }
            Text { textFormat: Text.PlainText;
              width: parent.width
              visible: !!root.prompterService && !!root.prompterService.lastError
              text: root.t("prompter_error_" + (root.prompterService ? root.prompterService.lastError : ""))
              color: Color.urgent
              wrapMode: Text.Wrap
              font.family: root.fontName
            }
          }

          Column {
            visible: root.tab === 5
            width: parent.width
            spacing: Style.space(10)
            Text { textFormat: Text.PlainText; text: root.t("audio"); color: root.fg; font.family: root.fontName; font.bold: true }
            Text { textFormat: Text.PlainText; width: parent.width; text: root.t("audio_intro"); color: Color.muted; wrapMode: Text.Wrap; font.family: root.fontName }
            Text { textFormat: Text.PlainText; visible: root.modelState.xlr.connected; text: root.modelState.xlr.device + " · OpenXLR"; color: root.fg; font.family: root.fontName; font.bold: true }
            Text { textFormat: Text.PlainText; width: parent.width; visible: root.modelState.xlr.available && !root.modelState.xlr.connected; text: root.t("xlr_no_device"); color: Color.muted; wrapMode: Text.Wrap; font.family: root.fontName }
            Text { textFormat: Text.PlainText; width: parent.width; visible: !root.modelState.xlr.available; text: root.t("xlr_optional"); color: Color.muted; wrapMode: Text.Wrap; font.family: root.fontName }
            Repeater {
              model: root.modelState.xlr.controls
              Column {
                id: xlrControl
                required property var modelData
                width: parent.width
                spacing: Style.space(3)
                Text { textFormat: Text.PlainText; text: root.t("xlr_" + xlrControl.modelData.id) + (xlrControl.modelData.type === "number" ? " · " + Math.round(xlrControl.modelData.value) : ""); color: root.fg; font.family: root.fontName }
                Switch {
                  visible: xlrControl.modelData.type === "bool"
                  checked: !!xlrControl.modelData.value
                  onToggled: root.mutate(["xlr-set", xlrControl.modelData.id, checked ? "1" : "0"])
                }
                Slider {
                  visible: xlrControl.modelData.type === "number"
                  width: parent.width
                  from: xlrControl.modelData.min || 0
                  to: xlrControl.modelData.max || 100
                  stepSize: xlrControl.modelData.step || 1
                  value: Number(xlrControl.modelData.value || 0)
                  onMoved: root.mutate(["xlr-set", xlrControl.modelData.id, String(Math.round(value))])
                }
              }
            }
            Repeater {
              model: root.modelState.xlr.mixes
              Column {
                id: xlrMix
                required property var modelData
                width: parent.width
                spacing: Style.space(3)
                Text { textFormat: Text.PlainText; text: xlrMix.modelData.name + " · " + Math.round(Number(xlrMix.modelData.volume || 0) * 100) + "%"; color: root.fg; font.family: root.fontName }
                ActionChip { label: xlrMix.modelData.muted ? root.t("unmute") : root.t("mute"); onClicked: root.mutate(["xlr-mix", xlrMix.modelData.id, "mute", xlrMix.modelData.muted ? "0" : "1"]) }
                Slider {
                  width: parent.width
                  from: 0
                  to: xlrMix.modelData.kind === "monitor" ? 1.5 : 1
                  value: Number(xlrMix.modelData.volume || 0)
                  onMoved: root.mutate(["xlr-mix", xlrMix.modelData.id, "volume", String(Math.round(value * 100) / 100)])
                }
              }
            }
            Text { textFormat: Text.PlainText; visible: root.modelState.audio.length === 0 && !root.modelState.xlr.connected; text: root.t("no_audio"); color: Color.muted; font.family: root.fontName }
            Repeater {
              model: root.modelState.audio
              Column {
                id: audioRow
                required property var modelData
                width: parent.width
                spacing: Style.space(5)
                Text { textFormat: Text.PlainText;
                  width: parent.width
                  text: audioRow.modelData.name + " · " + root.t(audioRow.modelData.kind)
                  color: root.fg
                  font.family: root.fontName
                  font.bold: true
                  wrapMode: Text.Wrap
                }
                Flow {
                  width: parent.width
                  spacing: Style.space(8)
                  Text { textFormat: Text.PlainText;
                    text: root.t("volume") + " " + Math.round(audioSlider.value * 100) + "%"
                    color: root.fg
                    font.family: root.fontName
                  }
                  ActionChip {
                    label: audioRow.modelData.muted ? root.t("unmute") : root.t("mute")
                    onClicked: root.mutate(["set-audio", String(audioRow.modelData.id), "mute", audioRow.modelData.muted ? "0" : "1"])
                  }
                }
                Slider {
                  id: audioSlider
                  width: parent.width
                  from: 0
                  to: 1.5
                  value: audioRow.modelData.volume
                  onMoved: root.mutate(["set-audio", String(audioRow.modelData.id), "volume", String(Math.round(value * 100) / 100)])
                }
                PanelSeparator { width: parent.width }
              }
            }
          }

          Column {
            visible: root.tab === 3
            width: parent.width
            spacing: Style.space(12)
            Text { textFormat: Text.PlainText; text: root.t("language"); color: root.fg; font.family: root.fontName; font.bold: true }
            UiSelect {
              id: languageSelect
              width: parent.width
              model: [root.t("system_language"), "Deutsch", "English", "Français", "Español"]
              onActivated: function(index) { root.queue(["set-language", root.languageIds[index]], "language") }
            }
            Text { textFormat: Text.PlainText; text: root.t("icon_theme"); color: root.fg; font.family: root.fontName; font.bold: true }
            UiSelect {
              id: themeSelect
              width: parent.width
              model: [root.t("automatic"), "Tokyo Night", "Catppuccin", "Gruvbox", "Nord"]
              onActivated: function(index) { root.mutate(["set-icon-theme", root.themeIds[index]]) }
            }
            Text { textFormat: Text.PlainText; text: root.t("all_empty"); color: root.fg; font.family: root.fontName; font.bold: true }
            Row {
              width: parent.width
              spacing: Style.space(8)
              UiSelect {
                id: globalEmptyStyle
                width: parent.width * .43
                model: root.emptyStyles.map(function(style) { return root.t("style_" + style) })
                onActivated: function(index) { root.chooseEmptyStyle(index, true) }
              }
              UiField {
                id: globalEmptyLabel
                width: parent.width * .53
                placeholderText: root.t("label")
                onEditingFinished: root.updateEmpty({ label: text }, true)
              }
            }
            Row {
              spacing: Style.space(8)
              ActionChip { label: root.t("icon_library"); onClicked: root.settingsGalleryOpen = !root.settingsGalleryOpen }
              ActionChip { label: root.t("choose_image"); onClicked: root.openFile("global") }
            }
            IconGallery {
              visible: root.settingsGalleryOpen
              width: parent.width
              catalog: root.modelState.visuals.catalog
              theme: root.modelState.visuals.theme
              assetsPath: root.assetsPath
              selectedIcon: root.globalEmpty.icon || "blank"
              searchPlaceholder: root.t("icon_library")
              onChosen: function(icon) { root.updateEmpty({ style: "theme", icon: icon }, true); root.settingsGalleryOpen = false }
            }
            PanelSeparator { width: parent.width }
            Text { textFormat: Text.PlainText; text: root.t("deck_brightness") + " · " + Math.round(brightnessSlider.value) + "%"; color: root.fg; font.family: root.fontName }
            Slider {
              id: brightnessSlider
              width: parent.width
              from: 0
              to: 100
              value: root.modelState.config.brightness === undefined ? 70 : root.modelState.config.brightness
              onMoved: root.mutate(["brightness", String(Math.round(value))])
            }
            Column {
              width: parent.width
              spacing: Style.space(6)
              visible: root.deck.dials > 0
              Text { textFormat: Text.PlainText; text: root.t("dials"); color: root.fg; font.family: root.fontName; font.bold: true }
              Repeater {
                model: root.deck.dials || 0
                Row {
                  id: dialRow
                  required property int index
                  readonly property var setting: (root.modelState.config.dials || {})[String(index)] || ({ mode: "none", host: "" })
                  spacing: Style.space(6)
                  Text { textFormat: Text.PlainText; text: String(dialRow.index + 1); color: root.fg; font.family: root.fontName; width: Style.space(22) }
                  UiSelect {
                    id: dialMode
                    width: Math.max(Style.space(100), Math.min(Style.space(220), body.width * .43))
                    model: [root.t("none"), root.t("volume"), root.t("light_brightness"), root.t("light_temperature")]
                    currentIndex: ["none", "volume", "light-brightness", "light-temperature"].indexOf(dialRow.setting.mode)
                    onActivated: function(index) {
                      var mode = ["none", "volume", "light-brightness", "light-temperature"][index]
                      var host = dialRow.setting.host || (root.modelState.lights.length ? root.modelState.lights[0].host : "")
                      root.mutate(["set-dial", String(dialRow.index), mode, host])
                    }
                  }
                  UiSelect {
                    width: Math.max(Style.space(90), Math.min(Style.space(180), body.width * .34))
                    visible: dialMode.currentIndex >= 2
                    model: root.modelState.lights.map(function(light) { return light.name })
                    currentIndex: Math.max(0, root.modelState.lights.findIndex(function(light) { return light.host === dialRow.setting.host }))
                    onActivated: function(index) { root.mutate(["set-dial", String(dialRow.index), dialRow.setting.mode, root.modelState.lights[index].host]) }
                  }
                }
              }
            }
          }
        }
      }
      ConfirmDialog {
        id: confirmClear
        anchors.fill: parent
        opened: false
        selectedIndex: 0
        message: root.t("confirm_clear").replace("%1", root.pendingClearLabel).replace("%2", String(root.pendingClearKey + 1))
        cancelText: root.t("no")
        confirmText: root.t("yes")
        onCanceled: opened = false
        onConfirmed: {
          opened = false
          if (root.pendingClearPage >= 0 && root.pendingClearKey >= 0)
            root.mutate(["clear", String(root.pendingClearPage), String(root.pendingClearKey)])
        }
      }
    }
  }
}
