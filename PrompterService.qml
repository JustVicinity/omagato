import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons

// One engine for the whole shell, independent of how many bars are visible.
Item {
  id: root
  property var shell: null
  readonly property string cli: String(Qt.resolvedUrl("bin/elgatoctl")).replace("file://", "")
  property string screenName: ""
  property string sourceName: ""
  property string scriptName: ""
  property string scriptText: ""
  property int speed: 75
  property int fontSize: 42
  property bool flipped: false
  property bool running: false
  property bool mirroring: false
  property bool mirroringWindow: false
  property var windowSource: null
  property bool playing: false
  property int chapter: 0
  property string lastError: ""
  readonly property var chapters: {
    var blocks = scriptText.split(/\n(?=#{1,2} )/)
    return blocks.map(function(block) {
      var match = block.match(/^#{1,2} ([^\n]*)\n?([\s\S]*)$/)
      return match ? { title: match[1], body: match[2] } : { title: "", body: block }
    }).filter(function(block) { return block.title || block.body.trim() })
  }

  function screenFor(name) {
    var screens = Quickshell.screens || []
    for (var i = 0; i < screens.length; i++) if (String(screens[i].name) === name) return screens[i]
    return null
  }
  function configure(data) {
    if (!data || running || mirroring) return
    screenName = String(data.screen || "")
    sourceName = String(data.source || "")
    scriptName = String(data.script || "")
    scriptText = String(data.text || "")
    speed = Number(data.speed || 75)
    fontSize = Number(data.font_size || 42)
    flipped = !!data.flip
    chapter = 0
  }
  function reload() { if (!loadProcess.running) loadProcess.running = true }
  function start() {
    lastError = ""
    if (mirroring) stop()
    if (!screenFor(screenName)) { lastError = "screen"; return }
    if (!scriptText.trim()) { lastError = "script"; return }
    chapter = 0
    running = true
    playing = false
  }
  function startMirror() {
    lastError = ""
    if (!screenFor(screenName)) { lastError = "screen"; return }
    if (!screenFor(sourceName) || sourceName === screenName) { lastError = "mirror_source"; return }
    if (running || mirroring) stop()
    mirroringWindow = false
    windowSource = null
    mirroring = true
  }
  function startWindowMirror(source) {
    lastError = ""
    if (!screenFor(screenName)) { lastError = "screen"; return }
    if (!source) { lastError = "window_source"; return }
    if (running || mirroring) stop()
    windowSource = source
    mirroringWindow = true
    mirroring = true
  }
  function stop() {
    playing = false
    running = false
    mirroring = false
    mirroringWindow = false
    windowSource = null
  }
  function setFlip(value) {
    flipped = value
  }
  function playPause() {
    if (!running) start()
    if (running) playing = !playing
  }
  function jump(delta) { chapter = Math.max(0, Math.min(chapters.length - 1, chapter + delta)) }

  Process {
    id: loadProcess
    command: [root.cli, "prompter-state"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try { root.configure(JSON.parse(text)) }
        catch (error) { root.lastError = "state" }
      }
    }
  }
  Component.onCompleted: reload()
  Timer {
    interval: 2000
    repeat: true
    running: root.running || root.mirroring
    onTriggered: if (!root.screenFor(root.screenName)) root.stop()
  }
  Connections {
    target: root.windowSource
    function onClosed() {
      if (root.mirroringWindow) {
        root.stop()
        root.lastError = "window_closed"
      }
    }
  }
  IpcHandler {
    target: "omagato-prompter"
    function start(): void { root.start() }
    function mirror(): void { root.startMirror() }
    function mirrorWindow(appId: string): void {
      var windows = ToplevelManager.toplevels.values
      var source = windows.find(function(item) { return item && item.appId === appId })
      root.startWindowMirror(source || null)
    }
    function stop(): void { root.stop() }
    function play(): void { if (!root.running) root.start(); if (root.running) root.playing = true }
    function pause(): void { root.playing = false }
    function playPause(): void { root.playPause() }
    function faster(): void { root.speed = Math.min(300, root.speed + 10) }
    function slower(): void { root.speed = Math.max(10, root.speed - 10) }
    function nextChapter(): void { root.jump(1) }
    function prevChapter(): void { root.jump(-1) }
    function flip(): void { root.setFlip(!root.flipped) }
    function reload(): void { root.reload() }
    function status(): string {
      return JSON.stringify({ running: root.running, mirroring: root.mirroring,
        mirrorMode: root.mirroring ? (root.mirroringWindow ? "window" : "display") : "",
        window: root.windowSource ? root.windowSource.title : "", captureReady: root.mirroring && overlay.captureReady,
        playing: root.playing,
        screen: root.screenName, source: root.sourceName, script: root.scriptName, speed: root.speed,
        chapter: root.chapter, flip: root.flipped, error: root.lastError })
    }
  }
  TeleprompterOverlay { id: overlay; service: root }
}
