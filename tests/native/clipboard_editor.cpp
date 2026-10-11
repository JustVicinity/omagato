// Exercise actual editor components against a foreign, lazily retrieved offer.
#include <QGuiApplication>
#include <QClipboard>
#include <QMimeData>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QQuickItem>
#include <QQuickWindow>
#include <QKeyEvent>
#include <QtTest/qtestkeyboard.h>
#include <iostream>
#include <memory>

class Offer : public QMimeData {
public:
    mutable int reads = 0;
    QStringList formats() const override { return {"text/plain"}; }
    bool hasFormat(const QString &format) const override { return format == "text/plain"; }
protected:
    QVariant retrieveData(const QString &, QMetaType) const override {
        ++reads;
        return QString("foreign clipboard payload");
    }
};
static void key(QQuickItem *item, int code, Qt::KeyboardModifiers mods = Qt::NoModifier,
                const QString &text = {}) {
    QTest::sendKeyEvent(QTest::Click, item->window(), static_cast<Qt::Key>(code), text, mods);
    QCoreApplication::processEvents();
}
int main(int argc, char **argv) {
    qInstallMessageHandler([](QtMsgType, const QMessageLogContext &, const QString &message) { std::cerr << message.toStdString() << "\n"; });
    QGuiApplication app(argc, argv);
    if (argc < 2) return 2;
    const QString directory = QString::fromLocal8Bit(argv[1]);
    const bool baseline = argc > 2;
    QQmlEngine engine;
    engine.addImportPath(directory + "/imports");
    for (const char *name : {"UiField", "UiTextArea"}) {
        QQmlComponent component(&engine);
        QByteArray qml = "import QtQuick\nimport QtQuick.Controls\nimport \".\"\nWindow { width: 300; height: 200; visible: true; ";
        qml += baseline ? (QByteArray(name) == "UiField" ? "TextField" : "TextArea") : name;
        qml += " { objectName: \"editor\"; width: 240; height: 120; focus: true; text: \"\" } }";
        component.setData(qml, QUrl::fromLocalFile(directory + "/case.qml"));
        std::unique_ptr<QObject> root(component.create());
        if (!root) { std::cerr << component.errorString().toStdString(); return 2; }
        auto window = qobject_cast<QQuickWindow *>(root.get());
        QObject *object = root->findChild<QObject *>("editor");
        auto item = qobject_cast<QQuickItem *>(object);
        window->requestActivate();
        QTest::qWait(50);
        item->forceActiveFocus();
        QCoreApplication::processEvents();
        auto offer = new Offer;
        QGuiApplication::clipboard()->setMimeData(offer);
        for (int i = 0; i < 5; ++i) {
            QGuiApplication::clipboard()->dataChanged();
            object->property("canPaste");
            QCoreApplication::processEvents();
        }
        std::cout << name << ": unsolicited payload retrievals=" << offer->reads << '\n';
        if (offer->reads) return 1;
        if (baseline) continue;
        if (!baseline && !object->property("readOnly").toBool()) return 3;
        key(item, Qt::Key_A, Qt::NoModifier, "a");
        key(item, Qt::Key_B, Qt::NoModifier, QString::fromUtf8("ä"));
        if (object->property("text").toString() != QString::fromUtf8("aä")) return 4;
        key(item, Qt::Key_Backspace);
        if (object->property("text").toString() != "a") return 5;
        key(item, Qt::Key_Z, Qt::ControlModifier);
        if (object->property("text").toString() != QString::fromUtf8("aä")) return 6;
        key(item, Qt::Key_A, Qt::ControlModifier);
        key(item, Qt::Key_B, Qt::NoModifier, "b");
        if (object->property("text").toString() != "b") return 7;
        // Explicit paste must route to the isolated reader, never Qt's offer.
        key(item, Qt::Key_V, Qt::ControlModifier);
        if (offer->reads) return 8;
        auto adapter = object->findChild<QObject *>("clipboardAdapter");
        if (!adapter || adapter->property("requests").toInt() != 1) return 11;
        if (!object->property("readOnly").toBool()) return 9;
        if (QByteArray(name) == "UiTextArea") {
            key(item, Qt::Key_Return);
            if (!object->property("text").toString().endsWith('\n')) return 10;
        }
    }
    return 0;
}
