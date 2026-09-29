import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons

PanelWindow {
  id: overlay
  required property var service
  readonly property bool captureReady: mirrorView.hasContent
  readonly property var targetScreen: service.screenFor(service.screenName)
  screen: targetScreen
  visible: (service.running || service.mirroring) && targetScreen !== null
  anchors { top: true; bottom: true; left: true; right: true }
  color: "transparent"
  WlrLayershell.namespace: "omagato-prompter"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
  exclusionMode: ExclusionMode.Ignore

  function jumpToChapter(index) {
    var item = chapterRepeater.itemAt(index)
    if (item) scroller.contentY = Math.max(0, Math.min(item.y + scriptColumn.topPadding - height * .3,
                                                       scroller.contentHeight - scroller.height))
  }
  Connections {
    target: overlay.service
    function onChapterChanged() { overlay.jumpToChapter(overlay.service.chapter) }
    function onScriptTextChanged() { scroller.contentY = 0 }
    function onRunningChanged() { if (!overlay.service.running) scroller.contentY = 0 }
  }
  Timer {
    interval: 16
    running: overlay.visible && overlay.service.playing
    repeat: true
    onTriggered: {
      var limit = Math.max(0, scroller.contentHeight - scroller.height)
      scroller.contentY = Math.min(limit, scroller.contentY + overlay.service.speed * interval / 1000)
      if (scroller.contentY >= limit) overlay.service.playing = false
    }
  }
  Rectangle {
    anchors.fill: parent
    visible: overlay.service.mirroring
    color: Color.background
  }
  ScreencopyView {
    id: mirrorView
    readonly property real sourceAspect: sourceSize.width > 0 && sourceSize.height > 0
      ? sourceSize.width / sourceSize.height : overlay.width / Math.max(1, overlay.height)
    anchors.centerIn: parent
    width: Math.min(overlay.width, overlay.height * sourceAspect)
    height: Math.min(overlay.height, overlay.width / sourceAspect)
    visible: overlay.service.mirroring
    captureSource: overlay.service.mirroringWindow ? overlay.service.windowSource
                   : overlay.service.screenFor(overlay.service.sourceName)
    live: overlay.service.mirroring
    paintCursor: true
    transform: Scale {
      xScale: overlay.service.flipped ? -1 : 1
      origin.x: mirrorView.width / 2
    }
    onStopped: {
      if (overlay.service.mirroring) {
        overlay.service.stop()
        overlay.service.lastError = "mirror_exit"
      }
    }
  }
  Rectangle {
    visible: overlay.service.running
    anchors.fill: parent
    color: Color.background
    transform: Scale {
      xScale: overlay.service.flipped ? -1 : 1
      origin.x: overlay.width / 2
    }
    Flickable {
      id: scroller
      anchors.fill: parent
      contentWidth: width
      contentHeight: scriptColumn.implicitHeight
      clip: true
      interactive: false
      Column {
        id: scriptColumn
        width: scroller.width
        topPadding: Math.round(overlay.height * .3)
        bottomPadding: Math.round(overlay.height * .7)
        spacing: overlay.service.fontSize * .7
        Repeater {
          id: chapterRepeater
          model: overlay.service.chapters
          Column {
            required property var modelData
            width: scriptColumn.width
            spacing: overlay.service.fontSize * .3
            Text { textFormat: Text.PlainText;
              visible: !!parent.modelData.title
              width: parent.width
              leftPadding: parent.width * .08
              rightPadding: leftPadding
              text: parent.modelData.title
              color: Color.accent
              font.family: Style.font.family
              font.pixelSize: overlay.service.fontSize * .65
              font.bold: true
              wrapMode: Text.WordWrap
            }
            Text { textFormat: Text.PlainText;
              width: parent.width
              leftPadding: parent.width * .08
              rightPadding: leftPadding
              text: parent.modelData.body
              color: Color.foreground
              font.family: Style.font.family
              font.pixelSize: overlay.service.fontSize
              font.bold: true
              lineHeight: 1.28
              wrapMode: Text.WordWrap
            }
          }
        }
      }
    }
    Rectangle {
      x: 0
      y: Math.round(parent.height * .3)
      width: parent.width
      height: 2
      color: Color.accent
      opacity: .5
    }
    Text { textFormat: Text.PlainText;
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      anchors.margins: 18
      text: (overlay.service.chapter + 1) + " / " + Math.max(1, overlay.service.chapters.length)
      color: Color.muted
      font.family: Style.font.family
      font.pixelSize: Math.max(15, overlay.service.fontSize * .4)
    }
  }
}
