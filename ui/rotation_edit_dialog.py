import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPen, QRadialGradient,
)
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QDoubleSpinBox,
    QLabel, QRadioButton, QVBoxLayout, QWidget, QSizePolicy, QLayout,
)

from models.review import ReviewRecord
from ui.i18n import tr

KNOB_BODY_1 = QColor("#3A4C66")
KNOB_BODY_2 = QColor("#10192A")
KNOB_BORDER = QColor("#475569")
TICK_COLOR = QColor("#94A3B8")
LABEL_COLOR = QColor("#E2E8F0")
ACCENT = QColor("#0D9488")
DETENT_COLOR = QColor("#E2E8F0")

DETENT_STEP = 45.0
DETENT_TOLERANCE = 5.0


class RotaryKnob(QWidget):
    angleChanged = Signal(float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._angle = 0.0
        self._dragging = False
        self._hovered = False
        self._center_text = ""
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)

    def sizeHint(self):
        return self.minimumSize()

    def angle(self) -> float:
        return self._angle

    def set_angle(self, value: float) -> None:
        a = float(value) % 360.0
        if abs(a - self._angle) < 1e-9:
            self._angle = a
            return
        self._angle = a
        self.update()

    def is_dragging(self) -> bool:
        return self._dragging

    def set_center_text(self, text: str) -> None:
        if text != self._center_text:
            self._center_text = text
            self.update()

    def center_text(self) -> str:
        return self._center_text

    @staticmethod
    def nearest_detent(ang: float) -> Optional[float]:
        """Exact multiple of DETENT_STEP if `ang` sits within tolerance."""
        mark = round(float(ang) / DETENT_STEP) * DETENT_STEP % 360.0
        diff = abs((float(ang) - mark + 180.0) % 360.0 - 180.0)
        if diff <= DETENT_TOLERANCE:
            return mark
        return None

    def enterEvent(self, ev) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, ev) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._apply_pointer(ev.position(), ev.modifiers())

    def mouseMoveEvent(self, ev) -> None:
        if self._dragging:
            self._apply_pointer(ev.position(), ev.modifiers())

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._dragging = False
            self.update()

    def wheelEvent(self, ev) -> None:
        step = 1.0 if ev.angleDelta().y() > 0 else -1.0
        self.set_angle(self._angle + step)
        self.angleChanged.emit(self._angle)

    def _apply_pointer(self, pos: QPointF, modifiers=Qt.NoModifier) -> None:
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        dx = pos.x() - cx
        dy = pos.y() - cy
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return
        ang = math.degrees(math.atan2(dx, -dy)) % 360.0
        if modifiers & Qt.ControlModifier:
            ang = round(ang / 15.0) * 15.0 % 360.0
        snap = self.nearest_detent(ang)
        if snap is not None:
            ang = snap
        self.set_angle(ang)
        self.angleChanged.emit(self._angle)

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        outer = max(min(w, h) / 2.0 - 4.0, 55.0)
        ring_r = outer - 13.0
        ring_w = 8.0
        r_body = ring_r - 24.0

        p.setFont(QFont("Segoe UI", 8))
        fm_tick = p.fontMetrics()

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 110))
        p.drawEllipse(QPointF(cx, cy + 3.0), r_body + ring_w, r_body + ring_w)

        track_alpha = 70 if self._hovered else 45
        rect = QRectF(cx - ring_r, cy - ring_r, 2 * ring_r, 2 * ring_r)
        p.setPen(QPen(QColor(148, 163, 184, track_alpha), ring_w, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(rect)

        span = int(round(-self._angle * 16.0))
        if span != 0:
            if self._dragging:
                p.setPen(QPen(QColor(13, 148, 136, 60), ring_w + 6.0, Qt.SolidLine, Qt.RoundCap))
                p.drawArc(rect, 90 * 16, span)
            p.setPen(QPen(ACCENT, ring_w, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, 90 * 16, span)

        for deg in range(0, 360, 10):
            major = deg % 45 == 0
            rad = math.radians((270 - deg) % 360)
            t_out = ring_r - 7.0
            t_in = t_out - (9.0 if major else 5.0)
            x1 = cx + t_out * math.sin(rad)
            y1 = cy - t_out * math.cos(rad)
            x2 = cx + t_in * math.sin(rad)
            y2 = cy - t_in * math.cos(rad)
            tick_col = QColor(TICK_COLOR) if major else QColor(148, 163, 184, 110)
            p.setPen(QPen(tick_col, 2.2 if major else 1.0))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Detents: bright dots on the track every 45 degrees + labels
        for deg in range(0, 360, 45):
            rad = math.radians((270 - deg) % 360)
            sx = math.sin(rad)
            sy = -math.cos(rad)
            p.setBrush(QBrush(DETENT_COLOR))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx + ring_r * sx, cy + ring_r * sy), 3.4, 3.4)
            lr = ring_r + 12.0
            lx = cx + lr * sx
            ly = cy + lr * sy
            text = str(deg)
            tw = fm_tick.horizontalAdvance(text)
            th = fm_tick.height()
            p.setPen(QPen(LABEL_COLOR))
            p.drawText(QPointF(lx - tw / 2.0, ly + th / 4.0), text)

        grad = QRadialGradient(cx - r_body * 0.35, cy - r_body * 0.45, r_body * 1.9)
        grad.setColorAt(0.0, KNOB_BODY_1)
        grad.setColorAt(1.0, KNOB_BODY_2)
        border = QColor("#64748B") if self._hovered else KNOB_BORDER
        p.setPen(QPen(border, 1.6))
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), r_body, r_body)

        rad = math.radians(self._angle)
        ix = cx + r_body * 0.42 * math.sin(rad)
        iy = cy - r_body * 0.42 * math.cos(rad)
        ox = cx + (r_body - 4.0) * math.sin(rad)
        oy = cy - (r_body - 4.0) * math.cos(rad)

        if self._dragging:
            hp = QPen(QColor(13, 148, 136, 80), 10.0)
            hp.setCapStyle(Qt.RoundCap)
            p.setPen(hp)
            p.drawLine(QPointF(ix, iy), QPointF(ox, oy))

        ind = QPen(QColor("#14B8A6"), 6.0)
        ind.setCapStyle(Qt.RoundCap)
        p.setPen(ind)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(ix, iy), QPointF(ox, oy))
        p.setBrush(QBrush(QColor("#CCFBF1")))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(ox, oy), 3.6, 3.6)

        if self._center_text:
            tf = QFont("Segoe UI", 12)
            tf.setBold(True)
            p.setFont(tf)
            cfm = p.fontMetrics()
            br = cfm.boundingRect(self._center_text)
            p.setPen(QPen(LABEL_COLOR))
            p.drawText(QPointF(cx - br.center().x(), cy - br.center().y()), self._center_text)


class RotationEditDialog(QDialog):
    def __init__(
        self,
        record: ReviewRecord,
        parent: Optional[QWidget] = None,
        preview_cb=None,
    ) -> None:
        super().__init__(parent)
        self._record = record
        self._ic_mode = False
        self._syncing = False
        self._preview_cb = preview_cb
        self.setWindowTitle(tr("Edit Rotation - {des}", des=record.designator))
        self.setModal(False)
        self._build_ui()
        self.layout().setSizeConstraint(QLayout.SetFixedSize)
        # Components previously edited in IC convention reopen in IC mode
        if bool(getattr(record, "is_ic_rotation", False)):
            self._radio_ic.setChecked(True)
        _initial_rot = self._current_rotation()
        self._spin.blockSignals(True)
        self._spin.setValue(_initial_rot)
        self._spin.blockSignals(False)
        self._knob.set_angle(self._knob_from_rotation(_initial_rot))
        self._update_center_text(_initial_rot)

    def _current_rotation(self) -> float:
        rec = self._record
        rot = rec.new_rotation if rec.new_rotation is not None else rec.old_rotation
        return float(rot or 0.0)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel(tr("Rotation")))
        self._spin = QDoubleSpinBox()
        self._spin.setRange(-999999.0, 999999.0)
        self._spin.setDecimals(1)
        self._spin.setSingleStep(1.0)
        self._spin.setSuffix("°")
        self._spin.valueChanged.connect(self._on_spin_value)
        top_row.addWidget(self._spin)
        top_row.addStretch(1)
        self._radio_normal = QRadioButton(tr("Normal"))
        self._radio_ic = QRadioButton(tr("IC"))
        self._radio_normal.setChecked(True)
        self._radio_normal.toggled.connect(self._on_mode_changed)
        top_row.addWidget(self._radio_normal)
        top_row.addWidget(self._radio_ic)
        layout.addLayout(top_row)

        knob_column = QVBoxLayout()
        knob_column.addStretch(1)
        knob_row = QHBoxLayout()
        knob_row.addStretch(1)
        self._knob = RotaryKnob()
        self._knob.angleChanged.connect(self._on_knob_angle)
        knob_row.addWidget(self._knob)
        knob_row.addStretch(1)
        knob_column.addLayout(knob_row)
        knob_column.addStretch(1)
        layout.addLayout(knob_column, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_center_text(self, rotation: float) -> None:
        self._knob.set_center_text(f"{int(round(float(rotation))) % 360}°")

    def _rotation_from_knob(self, k: float) -> float:
        if self._ic_mode:
            return float((225 - int(round(k))) % 360)
        return float((270 - int(round(k))) % 360)

    def _knob_from_rotation(self, rotation: float) -> float:
        base = int(round(rotation)) % 360
        if self._ic_mode:
            return float((225 - base) % 360)
        return float((270 - base) % 360)

    def _display_rotation(self) -> float:
        """Return the rotation value to display on the main viewer.
        In IC mode, this is the pseudo-rotation (val + 45) % 360 so that
        the viewer's normal-convention drawing yields the same bearing as
        the knob needle.
        """
        val = self._spin.value()
        if self._ic_mode:
            return float((val + 45.0) % 360.0)
        return val

    def _on_mode_changed(self, _checked: bool) -> None:
        self._ic_mode = self._radio_ic.isChecked()
        # Keep the numeric value; reinterpret the DIRECTION under the new
        # convention (knob pointer moves to the matching bearing).
        val = self._spin.value()
        self._syncing = True
        self._knob.set_angle(self._knob_from_rotation(val))
        self._syncing = False
        self._update_center_text(val)
        if callable(self._preview_cb):
            self._preview_cb(self._display_rotation())

    def _on_knob_angle(self, k: float) -> None:
        if self._syncing:
            return
        val = self._rotation_from_knob(k)
        self._syncing = True
        self._spin.setValue(val)
        self._syncing = False
        self._update_center_text(val)
        if callable(self._preview_cb):
            self._preview_cb(self._display_rotation())

    def _on_spin_value(self, v: float) -> None:
        if self._syncing:
            return
        self._syncing = True
        self._knob.set_angle(self._knob_from_rotation(v))
        self._syncing = False
        self._update_center_text(v)
        if callable(self._preview_cb):
            self._preview_cb(self._display_rotation())

    def new_rotation(self) -> float:
        return self._spin.value()

    def is_ic_mode(self) -> bool:
        """True if the user is editing under the IC direction convention."""
        return bool(self._ic_mode)
