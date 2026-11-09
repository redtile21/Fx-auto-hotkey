"""Small custom widgets: animated switch, gradient text, hotkey recorder."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QSize, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QPushButton, QWidget

from . import keys, palette, theme


class Switch(QAbstractButton):
    """iOS-style toggle with a purple->blue gradient track."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._pos = 1.0 if checked else 0.0
        self.setChecked(checked)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(46, 26)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _on_anim(self, v) -> None:
        self._pos = float(v)
        self.update()

    def paintEvent(self, _e) -> None:
        c = theme.colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        rad = r.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c["track"]))
        p.drawRoundedRect(r, rad, rad)
        if self._pos > 0:
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            g.setColorAt(0, QColor(c["grad_a"]))
            g.setColorAt(1, QColor(c["grad_b"]))
            op = p.opacity()
            p.setOpacity(op * self._pos)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(r, rad, rad)
            p.setOpacity(op)
        d = self.height() - 7
        x = 3.5 + self._pos * (self.width() - d - 7)
        on, off = QColor(c["on_accent"]), QColor("#FFFFFF")
        knob = QColor(int(off.red() + (on.red() - off.red()) * self._pos),
                      int(off.green() + (on.green() - off.green()) * self._pos),
                      int(off.blue() + (on.blue() - off.blue()) * self._pos))
        p.setPen(QPen(QColor(0, 0, 0, 45), 1))
        p.setBrush(knob)
        p.drawEllipse(QRectF(x, 3.5, d, d))


class GradientText(QWidget):
    """Label whose text is painted with the accent gradient."""

    clicked = Signal()

    def __init__(self, text: str, size: float = 14, bold: bool = True, parent=None):
        super().__init__(parent)
        self._text = text
        self._font = QFont(theme.UI_FONT)
        self._font.setPointSizeF(theme.pt(size))
        self._font.setBold(bold)
        self._clickable = False

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self._font)
        return QSize(fm.horizontalAdvance(self._text) + 2, fm.height())

    def setText(self, t: str) -> None:
        self._text = t
        self.updateGeometry()
        self.update()

    def setClickable(self, on: bool = True) -> None:
        self._clickable = on
        if on:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()

    def mousePressEvent(self, e) -> None:
        if self._clickable and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def paintEvent(self, _e) -> None:
        c = theme.colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        g = QLinearGradient(0, 0, max(self.sizeHint().width(), 1), 0)
        g.setColorAt(0, QColor(c["gt_a"]))
        g.setColorAt(1, QColor(c["gt_b"]))
        p.setPen(QPen(QBrush(g), 1))
        p.setFont(self._font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)


class HotkeyEdit(QPushButton):
    """Click, press a key combination, done. Uses the engine's keyboard hook so
    numpad keys, F-keys and Control/Option/Shift/Command combos are captured exactly."""

    changed = Signal(str)
    _got = Signal(str)          # emitted from the hook thread

    def __init__(self, engine, value: str = "", parent=None):
        super().__init__(parent)
        self._engine = engine
        self._value = value
        self._capturing = False
        self.setObjectName("hotkey")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._start)
        self._got.connect(self._on_got)
        self._refresh()

    def value(self) -> str:
        return self._value

    def setValue(self, v: str) -> None:
        self._value = v
        self._refresh()

    def _refresh(self) -> None:
        if self._capturing:
            self.setText("Press the keys...   (Esc to cancel)")
        elif self._value:
            self.setText(keys.pretty_hotkey(self._value))
        else:
            self.setText("Click here, then press the keys")
        self.setProperty("capturing", self._capturing)
        self.style().unpolish(self)
        self.style().polish(self)

    def _start(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self._refresh()
        self._engine.start_capture(lambda hk: self._got.emit(hk or ""))

    def _on_got(self, hk: str) -> None:
        self._capturing = False
        if hk:
            self._value = hk
            self.changed.emit(hk)
        self._refresh()

    def _cancel(self) -> None:
        if self._capturing:
            self._engine.cancel_capture()
            self._capturing = False
            self._refresh()

    def focusOutEvent(self, e) -> None:
        super().focusOutEvent(e)
        self._cancel()

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        self._cancel()


class SchemeCard(QAbstractButton):
    """Clickable colour-scheme swatch (shows the gradient in the current light/dark mode)."""

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(112, 84)

    def paintEvent(self, _e) -> None:
        c = theme.colors()
        s = palette.SCHEMES[self.key]
        a, b = s["dark" if theme.is_dark() else "light"]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        p.setPen(QPen(QColor(c["grad_a"] if self.isChecked() else c["border"]), 2 if self.isChecked() else 1))
        p.setBrush(QColor(c["surface2"]))
        p.drawRoundedRect(r, 12, 12)
        sw = QRectF(r.left() + 8, r.top() + 8, r.width() - 16, 30)
        g = QLinearGradient(sw.left(), 0, sw.right(), 0)
        g.setColorAt(0, QColor(a))
        g.setColorAt(1, QColor(b))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(sw, 8, 8)
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(theme.pt(9.5))
        p.setFont(f)
        p.setPen(QColor(c["text"]))
        al = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        p.drawText(QRectF(r.left() + 10, sw.bottom() + 4, r.width() - 20, 18), al, s["name"])
        f.setBold(False)
        f.setPointSizeF(theme.pt(8))
        p.setFont(f)
        p.setPen(QColor(c["muted"]))
        p.drawText(QRectF(r.left() + 10, sw.bottom() + 21, r.width() - 20, 16), al, s["sub"])


def badge_pixmap(letter: str, size: int) -> QPixmap:
    """Fallback program icon: rounded gradient square with the first letter."""
    c = theme.colors()
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(c["grad_a"]))
    g.setColorAt(1, QColor(c["grad_b"]))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
    f = QFont(theme.UI_FONT)
    f.setBold(True)
    f.setPixelSize(max(8, int(size * 0.5)))
    p.setFont(f)
    p.setPen(QColor(c["on_accent"]))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, (letter or "?")[:1].upper())
    p.end()
    return pm
