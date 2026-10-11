import QtQuick
import Quickshell.Io

Item {
  id: reader
  property var target: null
  property bool multiline: false
  property string initialText: ""
  property int initialCursor: 0
  property int initialStart: 0
  property int initialEnd: 0
  readonly property string cli: String(Qt.resolvedUrl("bin/elgatoctl")).replace("file://", "")
  visible: false
  function request() {
    if (!target || !target.activeFocus || process.running) return
    target.inputError = ""
    initialText = target.text
    initialCursor = target.cursorPosition
    initialStart = target.selectionStart
    initialEnd = target.selectionEnd
    process.running = true
  }
  Process {
    id: process
    command: [reader.cli, "clipboard"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (!reader.target || !reader.target.activeFocus || reader.target.text !== reader.initialText
            || reader.target.cursorPosition !== reader.initialCursor || reader.target.selectionStart !== reader.initialStart
            || reader.target.selectionEnd !== reader.initialEnd) return
        try {
          var result = JSON.parse(text)
          if (result.error) reader.target.inputError = result.error
          else reader.target.insertSafeText(result.text)
        } catch (error) { reader.target.inputError = "clipboard_unavailable" }
      }
    }
  }
}
