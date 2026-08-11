import numpy as np
import pytest

from services.gerber.origin_aligner import (
    estimate_adaptive_threshold,
    solve_offset_median,
    align_instance,
)


class _Inst:
    def __init__(self):
        self.origin = (0.0, 0.0)
        self.w = 26.0
        self.h = 17.0


class _Pt:
    def __init__(self, x_mm, y_mm):
        self.x_mm = x_mm
        self.y_mm = y_mm


def test_estimate_adaptive_threshold_dense_board():
    # components cách nhau chỉ 1.5mm (board dày, giống dữ liệu thật)
    pp = np.array([(5.6, 8.5), (17.15, 8.5), (8, 15.7), (8, 1.3),
                   (26, 8.5), (9.5, 15.7), (9.5, 1.3)])
    th = estimate_adaptive_threshold(pp)
    assert th < 1.0
    assert th >= 0.8


def test_estimate_adaptive_threshold_single_component():
    pp = np.array([(5.0, 5.0)])
    assert estimate_adaptive_threshold(pp) == 8.0


def test_solve_offset_median_already_aligned_dense():
    # dữ liệu đã aligned: pad trùng center component
    comps = np.array([(5.6, 8.5), (8, 15.7), (8, 1.3), (9.5, 15.7), (9.5, 1.3)])
    pads = []
    for cx, cy in comps:
        pads.extend([(cx - 0.3, cy), (cx + 0.3, cy)])
    pads = np.array(pads)
    offset0 = np.array([0.0, 0.0])
    res = solve_offset_median(pads, comps, offset0)
    assert res is not None
    offset, n, resid = res
    assert np.allclose(offset, [0.0, 0.0], atol=1e-9)
    assert n == len(comps)


def test_solve_offset_median_detects_shift():
    # dữ liệu lệch thật sự 2mm → phải nhận ra
    comps = np.array([(5.0, 5.0), (15.0, 5.0), (5.0, 15.0)])
    pads = np.array([(7.0, 5.0), (17.0, 5.0), (7.0, 15.0)])
    offset0 = np.array([0.0, 0.0])
    res = solve_offset_median(pads, comps, offset0)
    assert res is not None
    offset, _, _ = res
    assert np.allclose(offset, [2.0, 0.0], atol=0.5)


def test_align_instance_already_aligned_returns_zero():
    inst = _Inst()
    xs = [5.6, 8.0, 9.5]
    ys = [8.5, 15.7, 1.3]
    pads = [_Pt(5.6, 8.5), _Pt(8.0, 15.7), _Pt(9.5, 1.3)]
    r = align_instance(inst, xs, ys, gtp_pts=pads, layer="top",
                       detect_rotation=False)
    assert abs(r.offset_x) < 1e-9
    assert abs(r.offset_y) < 1e-9
