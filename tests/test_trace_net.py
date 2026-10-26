"""The trace of one net: pads joined by the copper that touches them."""

from services.gerber.gerber_render import (ArcShape, FlashShape, LineShape,
                                           RenderData)
from services.gerber.trace_net import (build_index, pick_flash,
                                       trace_component)


def _wire_data():
    data = RenderData()
    data.lines = [
        LineShape(x1=0.0, y1=0.0, x2=10.0, y2=0.0, width=0.2),
        LineShape(x1=10.0, y1=0.0, x2=20.0, y2=0.0, width=0.2),
        LineShape(x1=20.0, y1=0.0, x2=20.0, y2=10.0, width=0.2),
        LineShape(x1=20.0, y1=0.0, x2=25.0, y2=0.0, width=0.5,
                  negative=True),
    ]
    data.flashes = [
        FlashShape(cx=0.0, cy=0.0, kind="circle", w=1.0, h=1.0),
        FlashShape(cx=20.0, cy=10.0, kind="circle", w=0.8, h=0.8),
        FlashShape(cx=50.0, cy=50.0, kind="circle", w=1.2, h=1.2),
    ]
    data.arcs = []
    return data


def test_the_wire_chain_joins_its_two_pads():
    component = trace_component(_wire_data(), 0.0, 0.0)
    assert component.flashes == [0, 1]
    assert component.strokes == [0, 1, 2]
    assert component.count() == 5


def test_a_clear_stroke_does_not_join_the_trace():
    component = trace_component(_wire_data(), 0.0, 0.0)
    assert 3 not in component.strokes


def test_an_isolated_pad_stays_alone():
    component = trace_component(_wire_data(), 50.5, 50.0)
    assert component.flashes == [2]
    assert component.strokes == []


def test_a_click_on_the_wire_itself_starts_the_trace():
    component = trace_component(_wire_data(), 15.0, 0.001)
    assert component.flashes == [0, 1]
    assert component.strokes == [0, 1, 2]


def test_no_copper_near_the_click_yields_none():
    data = _wire_data()
    assert trace_component(data, 60.0, 60.0, 1.0) is None


def test_pick_flash_finds_the_nearest_pad():
    data = _wire_data()
    index = build_index(data)
    assert pick_flash(index, 0.2, 0.0) == 0
    assert pick_flash(index, 49.9, 50.0) == 2
    # Between the pads, over the tolerance: nothing to pick.
    assert pick_flash(index, 2.0, 0.0) is None


def test_strokes_join_over_an_overlap_not_an_endpoint():
    data = RenderData()
    data.arcs = []
    data.lines = [
        LineShape(x1=0.0, y1=0.0, x2=10.0, y2=0.0, width=0.3),
        # Crosses the first wire at its middle, shares no point.
        LineShape(x1=5.0, y1=-5.0, x2=5.0, y2=5.0, width=0.3),
    ]
    data.flashes = []
    component = trace_component(data, 0.0, 0.0)
    assert component.strokes == [0, 1]


def test_an_arc_carries_the_trace_to_the_next_pad():
    data = RenderData()
    data.lines = [
        LineShape(x1=0.0, y1=0.0, x2=5.0, y2=0.0, width=0.3),
    ]
    data.arcs = [
        ArcShape(x1=5.0, y1=0.0, x2=10.0, y2=0.0, cx=7.5, cy=0.0,
                 clockwise=False, width=0.3),
    ]
    data.flashes = [
        FlashShape(cx=10.2, cy=0.2, kind="circle", w=0.8, h=0.8),
    ]
    component = trace_component(data, 0.0, 0.0)
    assert component.arcs == [0]
    assert component.flashes == [0]
    assert component.strokes == [0]


def test_a_seed_flash_runs_the_trace_exactly():
    data = _wire_data()
    component = trace_component(data, 0.0, 0.0,
                                seed=("flash", 1, 20.0, 10.0))
    assert component.flashes == [0, 1]
    assert component.seed_flash == 1


def test_a_long_trace_stays_connected_end_to_end():
    data = RenderData()
    data.arcs = []
    lines = []
    pads = []
    for i in range(50):
        x0 = i * 10.0
        lines.append(LineShape(x1=x0, y1=0.0, x2=x0 + 10.0, y2=0.0,
                               width=0.2))
        if i % 10 == 0:
            pads.append(FlashShape(cx=x0, cy=0.0, kind="circle",
                                   w=0.8, h=0.8))
    data.lines = lines
    data.flashes = pads
    component = trace_component(data, 0.0, 0.0)
    # Pads at x = 0, 100, 200, 300, 400 all hang on one wire.
    assert component.flashes == [0, 1, 2, 3, 4]
    assert len(component.strokes) == 50


def test_polygon_pad_is_picked_inside_contours():
    data = RenderData()
    data.lines = []
    data.arcs = []
    # Rectangular polygon pad 4x2 mm at origin
    data.flashes = [
        FlashShape(cx=0.0, cy=0.0, kind="polygon",
                   pts=[(-2.0, -1.0), (2.0, -1.0), (2.0, 1.0), (-2.0, 1.0)],
                   pts_local=False)
    ]
    index = build_index(data)
    # Click strictly inside the polygon pad
    picked = pick_flash(index, 0.5, 0.2, tol=0.1)
    assert picked == 0
    component = trace_component(data, 0.5, 0.2, tol=0.1, index=index)
    assert component is not None
    assert component.flashes == [0]
    assert component.is_plane is False


def test_massive_plane_is_marked_as_plane():
    data = RenderData()
    data.lines = []
    data.arcs = []
    # 20x20 mm plane pour (area 400 mm^2)
    data.flashes = [
        FlashShape(cx=0.0, cy=0.0, kind="polygon",
                   pts=[(-10.0, -10.0), (10.0, -10.0), (10.0, 10.0), (-10.0, 10.0)],
                   pts_local=False)
    ]
    index = build_index(data)
    component = trace_component(data, 2.0, 2.0, tol=1.0, index=index)
    assert component is not None
    assert component.is_plane is True

