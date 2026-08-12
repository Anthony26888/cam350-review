import math

import pytest

from services.gerber.gerber_transform import (
    apply_transform, mirror_y, mirror_x, transform_rot,
)


def test_mirror_y():
    assert mirror_y(10.0, 5.0, 4.0) == (pytest.approx(-2.0), pytest.approx(5.0))
    assert mirror_y(4.0, 0.0, 4.0) == (pytest.approx(4.0), pytest.approx(0.0))


def test_mirror_x():
    assert mirror_x(10.0, 5.0, 3.0) == (pytest.approx(10.0), pytest.approx(1.0))
    assert mirror_x(2.0, 3.0, 3.0) == (pytest.approx(2.0), pytest.approx(3.0))


def test_apply_transform_identity():
    assert apply_transform(3.0, 4.0, False, 0.0, 0.0, 0.0) == (3.0, 4.0)


def test_apply_transform_offset_only():
    assert apply_transform(3.0, 4.0, False, 0.0, 1.5, -2.0) == (
        pytest.approx(4.5),
        pytest.approx(2.0),
    )


def test_apply_transform_rotate_90():
    # rotate (1,0) by 90deg -> (0,1), then no offset
    x, y = apply_transform(1.0, 0.0, False, 90.0, 0.0, 0.0)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(1.0, abs=1e-9)


def test_apply_transform_mirror_y_center():
    # mirror x about center_x=5: 1.0 -> 9.0
    x, y = apply_transform(1.0, 2.0, True, 0.0, 0.0, 0.0, center_x=5.0)
    assert x == pytest.approx(9.0)
    assert y == pytest.approx(2.0)


def test_apply_transform_pipeline_order():
    # mirror(center 0) then rotate 90 then offset.
    # point (1,0): mirror->(-1,0), rotate->(0,-1), offset(2,2)->(2,1)
    x, y = apply_transform(1.0, 0.0, True, 90.0, 2.0, 2.0, center_x=0.0)
    assert x == pytest.approx(2.0)
    assert y == pytest.approx(1.0)


def test_apply_transform_mirror_x_center():
    # mirror y about center_y=5: 2.0 -> 8.0
    x, y = apply_transform(1.0, 2.0, False, 0.0, 0.0, 0.0, center_y=5.0, mirror_x=True)
    assert x == pytest.approx(1.0)
    assert y == pytest.approx(8.0)


def test_apply_transform_mirror_x_default_off():
    # mirror_x defaults to False -> identity for y
    x, y = apply_transform(3.0, 4.0, False, 0.0, 0.0, 0.0)
    assert x == pytest.approx(3.0)
    assert y == pytest.approx(4.0)


def test_apply_transform_double_mirror_is_rotation_180():
    # mirrorY then mirrorX about center (5,5): (3,7) -> (7,3)
    x, y = apply_transform(
        3.0, 7.0, True, 0.0, 0.0, 0.0, center_x=5.0, center_y=5.0, mirror_x=True
    )
    assert x == pytest.approx(7.0)
    assert y == pytest.approx(3.0)


def test_apply_transform_mirror_x_pipeline_order():
    # mirrorY(center 0) -> (-1,0), mirrorX(center 0) -> (-1,0) stays,
    # rotate 90 -> (0,-1), offset(2,2) -> (2,1)
    x, y = apply_transform(
        1.0, 0.0, True, 90.0, 2.0, 2.0, center_x=0.0, mirror_x=True
    )
    assert x == pytest.approx(2.0)
    assert y == pytest.approx(1.0)


def test_transform_rot_no_flip():
    assert transform_rot(30.0, False, 90.0) == pytest.approx(120.0)
    assert transform_rot(30.0, False, 0.0) == pytest.approx(30.0)


def test_transform_rot_mirror_x_reverses():
    assert transform_rot(30.0, False, 0.0, mirror_x=True) == pytest.approx(330.0)
    assert transform_rot(30.0, False, 90.0, mirror_x=True) == pytest.approx(60.0)


def test_transform_rot_double_mirror_no_reverse():
    assert transform_rot(30.0, True, 90.0, mirror_x=True) == pytest.approx(120.0)
    assert transform_rot(30.0, True, 0.0, mirror_x=True) == pytest.approx(30.0)


def test_transform_rot_flip_reverses():
    assert transform_rot(30.0, True, 0.0) == pytest.approx(330.0)
    assert transform_rot(30.0, True, 90.0) == pytest.approx(60.0)


def test_transform_rot_modulo():
    assert transform_rot(200.0, False, 200.0) == pytest.approx(40.0)
    assert transform_rot(10.0, False, 350.0) == pytest.approx(0.0)