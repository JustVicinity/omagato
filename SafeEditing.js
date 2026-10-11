.pragma library
.import QtQuick 2.15 as Quick

// Native editors stay readOnly for their entire lifetime. Never call paste(),
// canPaste or briefly toggle readOnly: those paths can collect foreign data.
function snapshot(field) {
    return { text: field.text, cursor: field.cursorPosition }
}
function remember(field) {
    var history = field.editHistory.slice(-15)
    history.push(snapshot(field))
    field.editHistory = history
    field.redoHistory = []
}
function notify(field) {
    if (field.textEdited) field.textEdited()
    if (field.userEdited) field.userEdited()
}
function replace(field, value, multiline) {
    value = String(value)
    if (!multiline) value = value.replace(/[\r\n\t]+/g, " ")
    var start = Math.min(field.selectionStart, field.selectionEnd)
    var end = Math.max(field.selectionStart, field.selectionEnd)
    var maximum = field.maximumLength
    if (field.text.length - (end - start) + value.length > maximum) {
        field.inputError = "clipboard_too_large"
        return
    }
    remember(field)
    field.internalEdit = true
    try {
        field.text = field.text.slice(0, start) + value + field.text.slice(end)
        field.cursorPosition = start + value.length
    } finally { field.internalEdit = false }
    notify(field)
}
function restore(field, undo) {
    var from = (undo ? field.editHistory : field.redoHistory).slice()
    if (!from.length) return
    var to = (undo ? field.redoHistory : field.editHistory).slice(-15)
    to.push(snapshot(field))
    var previous = from.pop()
    if (undo) { field.editHistory = from; field.redoHistory = to }
    else { field.redoHistory = from; field.editHistory = to }
    field.internalEdit = true
    try {
        field.text = previous.text
        field.cursorPosition = previous.cursor
    } finally { field.internalEdit = false }
    notify(field)
}
function erase(field, backwards) {
    if (field.selectionStart === field.selectionEnd) {
        var cursor = field.cursorPosition
        var other = cursor + (backwards ? -1 : 1)
        if (other < 0 || other > field.text.length) return
        // Keep UTF-16 surrogate pairs intact.
        if (backwards && cursor >= 2 && /[\uDC00-\uDFFF]/.test(field.text.charAt(cursor - 1))) --other
        if (!backwards && cursor + 1 < field.text.length && /[\uD800-\uDBFF]/.test(field.text.charAt(cursor))) ++other
        field.select(Math.min(cursor, other), Math.max(cursor, other))
    }
    replace(field, "", true)
}
function key(field, event, multiline) {
    field.inputError = ""
    if (event.matches(Quick.StandardKey.Paste)) field.requestPaste()
    else if (event.matches(Quick.StandardKey.Cut)) { field.copy(); replace(field, "", multiline) }
    else if (event.matches(Quick.StandardKey.Undo)) restore(field, true)
    else if (event.matches(Quick.StandardKey.Redo)) restore(field, false)
    else if (event.key === Qt.Key_Backspace) erase(field, true)
    else if (event.key === Qt.Key_Delete) erase(field, false)
    else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
        if (multiline) replace(field, "\n", true)
        else { field.accepted(); field.editingFinished() }
    } else if (multiline && event.key === Qt.Key_Tab && !(event.modifiers & Qt.ControlModifier)) replace(field, "\t", true)
    else if (event.text && !(event.modifiers & Qt.MetaModifier)
             && (!(event.modifiers & Qt.ControlModifier) || (event.modifiers & Qt.AltModifier))
             && event.text.charCodeAt(0) >= 32) replace(field, event.text, multiline)
    else return false // Native readOnly navigation, selection and copy are safe.
    event.accepted = true
    return true
}
