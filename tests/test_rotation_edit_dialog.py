import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog

from models.review import ReviewRecord
from ui.rotation_edit_dialog import RotaryKnob, RotationEditDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _record(rot=90.0):
    return ReviewRecord(
        designator="C1", mpn="M1", layer="Top",
        old_x=10.0, old_y=20.0, old_rotation=rot,
    )


def _dialog(rot=90.0):
    return RotationEditDialog(_record(rot))


def test_default_opens_in_normal_mode(app):
    d = _dialog()
    assert d._radio_normal.isChecked()
    assert d._radio_ic.isChecked() is False
    assert d._ic_mode is False


def test_ic_flag_on_record_preselects_ic_mode(app):
    rec = _record(rot=270.0)
    rec.is_ic_rotation = True
    d = RotationEditDialog(rec)
    assert d.is_ic_mode() is True
    # Knob needle must sit at the IC bearing for the stored value
    assert d._knob.angle() == pytest.approx(315.0, abs=0.01)  # (225-270)%360
    d.done(QDialog.Rejected)


def test_is_ic_mode_reflects_radio(app):
    d = _dialog()
    assert d.is_ic_mode() is False
    d._radio_ic.setChecked(True)
    assert d.is_ic_mode() is True
    d.done(QDialog.Rejected)


def test_initial_values_from_record(app):
    d = _dialog(rot=90.0)
    assert d._spin.value() == 90.0
    assert d._knob.angle() == 180.0
    assert d.new_rotation() == 90.0


def test_knob_change_updates_spin_and_center_text(app):
    d = _dialog()
    d._on_knob_angle(135.0)
    assert d._spin.value() == 135.0
    assert d._knob.center_text() == "135°"


NORMAL_TABLE = [(0, 270), (45, 225), (90, 180), (135, 135),
                (180, 90), (225, 45), (270, 0), (315, 315)]


def test_normal_mapping_table(app):
    d = _dialog()
    for k, v in NORMAL_TABLE:
        d._on_knob_angle(float(k))
        assert d._spin.value() == float(v)


IC_TABLE = [(0, 225), (45, 180), (90, 135), (135, 90),
            (180, 45), (225, 0), (270, 315), (315, 270)]


def test_ic_mapping_table(app):
    d = _dialog()
    d._radio_ic.setChecked(True)
    for k, v in IC_TABLE:
        d._on_knob_angle(float(k))
        assert d._spin.value() == float(v)


def test_indicator_sides_match_arrow_convention(app):
    d = _dialog()
    cases = [(270.0, 0.0), (180.0, 90.0), (90.0, 180.0), (0.0, 270.0)]
    for knob_angle, rotation in cases:
        d._knob.set_angle(knob_angle)
        d._on_knob_angle(d._knob.angle())
        assert d._spin.value() == rotation


def test_switch_mode_keeps_value_moves_arrow(app):
    d = _dialog(rot=90.0)
    assert d._knob.angle() == 180.0
    d._radio_ic.setChecked(True)
    assert d._spin.value() == 90.0          # value kept
    assert d._knob.angle() == 135.0         # pointer moved to IC bearing
    d._radio_normal.setChecked(True)
    assert d._spin.value() == 90.0
    assert d._knob.angle() == 180.0


def test_spin_input_repositions_knob(app):
    d = _dialog()
    d._radio_ic.setChecked(True)
    d._spin.setValue(135.0)
    assert d._knob.angle() == 90.0
    d._radio_normal.setChecked(True)
    d._spin.setValue(100.0)
    assert d._knob.angle() == 170.0


def test_dialog_does_not_mutate_record(app):
    rec = _record(rot=30.0)
    d = RotationEditDialog(rec)
    d._on_knob_angle(200.0)
    d.new_rotation()
    assert rec.new_rotation is None
    assert rec.old_rotation == 30.0


def test_fresh_dialog_always_normal(app):
    d1 = _dialog()
    d1._radio_ic.setChecked(True)
    d2 = _dialog()
    assert d2._radio_normal.isChecked()
    assert d2._ic_mode is False


def test_scene_none_still_works(app):
    rec = _record(rot=45.0)
    d = RotationEditDialog(rec)
    d._on_knob_angle(120.0)
    assert d._spin.value() == 150.0
    d.done(QDialog.Accepted)


def test_done_closes_cleanly(app):
    d = _dialog()
    d.done(QDialog.Rejected)
    d.done(QDialog.Accepted)  # double-done must not raise


def test_knob_pointer_angle_mapping(app):
    k = RotaryKnob()
    k.resize(300, 300)
    k._apply_pointer(_pointer_at_bearing(k, 90.0), Qt.NoModifier)
    assert k.angle() == pytest.approx(90.0, abs=0.01)
    k._apply_pointer(_pointer_at_bearing(k, 180.0), Qt.NoModifier)
    assert k.angle() == pytest.approx(180.0, abs=0.01)
    # Ctrl keeps the 15-degree grid away from detents (20 -> 15)
    k._apply_pointer(_pointer_at_bearing(k, 20.0), Qt.ControlModifier)
    assert k.angle() == pytest.approx(15.0, abs=0.01)
    # Ctrl near a detent lands exactly on it
    k._apply_pointer(_pointer_at_bearing(k, 43.0), Qt.ControlModifier)
    assert k.angle() == pytest.approx(45.0, abs=0.01)


def _pointer_at_bearing(knob, bearing, radius=None):
    cx = knob.width() / 2.0
    cy = knob.height() / 2.0
    r = radius if radius is not None else min(knob.width(), knob.height()) * 0.4
    rad = math.radians(bearing)
    return QPointF(cx + r * math.sin(rad), cy - r * math.cos(rad))


def test_detent_snap_click_near_45(app):
    k = RotaryKnob()
    k.resize(300, 300)
    k._apply_pointer(_pointer_at_bearing(k, 43.0))   # 2 degrees off detent
    assert k.angle() == pytest.approx(45.0, abs=0.01)


def test_detent_snap_wraps_at_zero(app):
    k = RotaryKnob()
    k.resize(300, 300)
    k._apply_pointer(_pointer_at_bearing(k, 357.5))  # 2.5 deg past 355/0 wrap
    assert k.angle() == pytest.approx(0.0, abs=0.01)


def test_no_snap_far_from_detents(app):
    k = RotaryKnob()
    k.resize(300, 300)
    k._apply_pointer(_pointer_at_bearing(k, 60.0))   # 15 deg away from 45/90
    assert k.angle() == pytest.approx(60.0, abs=0.1)
    k._apply_pointer(_pointer_at_bearing(k, 62.5))
    assert k.angle() == pytest.approx(62.5, abs=0.1)


def test_detent_exact_hit_is_stable(app):
    k = RotaryKnob()
    k.resize(300, 300)
    k._apply_pointer(_pointer_at_bearing(k, 270.0))
    assert k.angle() == pytest.approx(270.0, abs=0.01)


def test_knob_paint_smoke(app):
    k = RotaryKnob()
    k.resize(220, 220)
    pm = QPixmap(220, 220)
    k.render(pm)


def test_minimum_sizes_and_no_preview(app):
    d = _dialog()
    assert d._knob.minimumSize().width() == 240
    assert not hasattr(d, "_preview")
    assert not hasattr(d, "_marker_item")
    d.done(QDialog.Rejected)


def test_center_text_follows_rotation(app):
    d = _dialog(rot=90.0)
    assert d._knob.center_text() == "90°"
    d._radio_ic.setChecked(True)
    assert d._knob.center_text() == "90°"  # IC keeps the value
    d._on_knob_angle(0.0)
    assert d._knob.center_text() == "225°"
    d.done(QDialog.Rejected)


def test_preview_cb_sends_display_rotation(app):
    """Normal mode sends value as-is; IC mode sends (val + 45) % 360."""
    sent = []
    d = _dialog(rot=90.0)
    d._preview_cb = lambda v: sent.append(v)

    # Normal mode: knob at 180° -> val=90 -> display 90
    d._on_knob_angle(180.0)
    assert sent[-1] == pytest.approx(90.0)

    # Switch to IC (same spin value 90) -> display (90+45)%360 = 135
    d._radio_ic.setChecked(True)
    assert sent[-1] == pytest.approx(135.0)

    # In IC mode, knob at 90° -> val=135 -> display (135+45)%360 = 180
    d._on_knob_angle(90.0)
    assert sent[-1] == pytest.approx(180.0)

    # Spin input in IC: set 45 -> display (45+45)%360 = 90
    d._spin.setValue(45.0)
    assert sent[-1] == pytest.approx(90.0)

    # Back to Normal: spin 45 -> display 45
    d._radio_normal.setChecked(True)
    assert sent[-1] == pytest.approx(45.0)

    # Verify bearing consistency: viewer bearing = 270 - display_rot
    # In IC mode, knob bearing K = 225 - val; display = val + 45
    # => 270 - display = 270 - (val + 45) = 225 - val = K ✓
    d._radio_ic.setChecked(True)
    d._spin.setValue(0.0)  # IC val=0 -> knob bearing 225
    display = sent[-1]
    assert display == pytest.approx(45.0)
    viewer_bearing = (270 - display) % 360
    assert viewer_bearing == pytest.approx(225.0)  # matches knob needle


def test_dialog_size_fixed_and_compact(app):
    """Dialog should have fixed size constraint and be compact around the knob."""
    from PySide6.QtWidgets import QLayout
    d = _dialog()
    # Layout has fixed size constraint (no manual resize, no dead space)
    assert d.layout().sizeConstraint() == QLayout.SetFixedSize
    # SizeHint is compact (far smaller than old 420x560)
    assert d.sizeHint().width() < 500
    assert d.sizeHint().height() < 500
    # After show, size == sizeHint (fixed constraint)
    d.show()
    assert d.size() == d.sizeHint()
    # Knob still has its minimum size
    assert d._knob.minimumSize().width() == 240
    d.done(QDialog.Rejected)
