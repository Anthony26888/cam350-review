import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication

from services.gerber.gerber_pdf_export import export_gerber_pdf
from services.gerber.gerber_render import ArcShape, FlashShape, LineShape, RenderData


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tmp_out(tmp_path):
    return str(tmp_path / "out.pdf")


def _render_page(path, w=1403, h=992):
    """Render the PDF's first page to an image at ~120 dpi (A4 landscape)."""
    doc = QPdfDocument()
    assert doc.load(path) == QPdfDocument.Error.None_
    assert doc.pageCount() == 1
    return doc.render(0, QSize(w, h))


def _count_pixels(img, predicate):
    n = 0
    for y in range(0, img.height(), 1):
        for x in range(0, img.width(), 1):
            if predicate(img.pixelColor(x, y)):
                n += 1
    return n


def _is_black(c):
    return c.lightness() < 60


def _is_red(c):
    return c.red() > 180 and c.green() < 100 and c.blue() < 100


def _outline():
    return RenderData(lines=[
        LineShape(0.0, 0.0, 100.0, 0.0, width=0.1),
        LineShape(100.0, 0.0, 100.0, 80.0, width=0.1),
        LineShape(100.0, 80.0, 0.0, 80.0, width=0.1),
        LineShape(0.0, 80.0, 0.0, 0.0, width=0.1),
    ])


def _paste():
    return RenderData(flashes=[
        FlashShape(50.0, 40.0, "circle", 4.0, 0.0, 0.0, None),
        FlashShape(10.0, 10.0, "rect", 8.0, 6.0, 0.0, None),
    ])


def _silk():
    return RenderData(
        lines=[LineShape(2.0, 2.0, 20.0, 2.0, width=0.15)],
        flashes=[FlashShape(30.0, 30.0, "circle", 2.0, 0.0, 0.0, None)],
    )


def _markers():
    return [(50.0, 40.0, 90.0, 4.0), (10.0, 10.0, 0.0, 4.0)]


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def test_export_creates_valid_pdf(tmp_out, app):
    result = export_gerber_pdf(tmp_out, _outline(), _paste(), _silk(), _markers(),
                               board_center=(50.0, 40.0), is_top=True)
    assert result == tmp_out
    assert os.path.exists(tmp_out)
    data = _read(tmp_out)
    assert data[:5] == b"%PDF-"
    assert len(data) > 0
    assert b"/MediaBox [0 0 842.000000 595.000000]" in data


def test_export_a4_landscape_page_size(tmp_out, app):
    export_gerber_pdf(tmp_out, _outline(), _paste(), _silk(), [],
                      board_center=(50.0, 40.0), is_top=True)
    data = _read(tmp_out)
    assert b"/MediaBox [0 0 842.000000 595.000000]" in data


def test_export_rotated_markers_transform(tmp_out, app):
    """Markers with 90 degree rotation should use the same transform pipeline."""
    export_gerber_pdf(tmp_out, _outline(), _paste(), _silk(), _markers(),
                      angle=90.0, board_center=(50.0, 40.0), is_top=True)
    data = _read(tmp_out)
    # A rotation-only transform still renders geometry; ensure the PDF has content
    # beyond the empty background (stream operators present).
    assert b"cm" in data and b"l" in data


def test_export_show_paste_false_removes_paste(tmp_out, app):
    with_paste = _read(export_gerber_pdf(
        tmp_out, _outline(), _paste(), _silk(), [], show_paste=True,
        board_center=(50.0, 40.0), is_top=True))
    without = _read(export_gerber_pdf(
        str(os.path.join(os.path.dirname(tmp_out), "out2.pdf")),
        _outline(), _paste(), _silk(), [], show_paste=False,
        board_center=(50.0, 40.0), is_top=True))
    assert len(with_paste) > len(without)


def test_export_empty_data_raises(tmp_out, app):
    empty = RenderData()
    with pytest.raises(RuntimeError):
        export_gerber_pdf(tmp_out, empty, empty, empty, [],
                          show_outline=False, show_paste=False,
                          show_silk=False, show_pickplace=False,
                          board_center=(0.0, 0.0))
    assert not os.path.exists(tmp_out) or os.path.getsize(tmp_out) == 0


def test_export_empty_outline_still_works_with_markers(tmp_out, app):
    """Markers alone (no outline/paste) should still export a page."""
    result = export_gerber_pdf(tmp_out, RenderData(), RenderData(), RenderData(),
                               _markers(), show_outline=False, show_paste=False,
                               show_silk=False, board_center=(0.0, 0.0), is_top=True)
    data = _read(result)
    assert data[:5] == b"%PDF-"


def test_export_strokes_visible_black(tmp_out, app):
    """Regression: gerber strokes must be visible black (not sub-pixel hairlines)."""
    export_gerber_pdf(tmp_out, _outline(), _paste(), _silk(), [],
                      board_center=(50.0, 40.0), is_top=True)
    img = _render_page(tmp_out)
    black = _count_pixels(img, _is_black)
    assert black > 200, f"expected visible black strokes, got {black} black samples"


def test_export_all_gerber_layers_black(tmp_out, app):
    """Outline, paste and silk all render in black on the white page."""
    export_gerber_pdf(tmp_out, _outline(), _paste(), _silk(), [],
                      board_center=(50.0, 40.0), is_top=True)
    img = _render_page(tmp_out)

    def _is_colored(c):
        mx, mn = max(c.red(), c.green(), c.blue()), min(c.red(), c.green(), c.blue())
        return mx - mn > 30

    # Only black/white (with gray antialias edges); no colored pixels.
    stray = _count_pixels(img, _is_colored)
    assert stray < 20, f"unexpected colored pixels: {stray}"


def test_export_crosshair_red(tmp_out, app):
    """Crosshair + arrows render in red at marker positions."""
    export_gerber_pdf(tmp_out, _outline(), _paste(), _silk(), _markers(),
                      board_center=(50.0, 40.0), is_top=True)
    img = _render_page(tmp_out)
    red = _count_pixels(img, _is_red)
    assert red > 50, f"expected red crosshair pixels, got {red}"


def test_export_no_crosshair_when_disabled(tmp_out, app):
    """show_crosshair=False removes red crosshair lines (arrows may remain)."""
    export_gerber_pdf(tmp_out, _outline(), _paste(), _silk(), _markers(),
                      show_crosshair=False, board_center=(50.0, 40.0), is_top=True)
    img = _render_page(tmp_out)
    with_cross = _count_pixels(img, _is_red)
    # Arrows are also red, so compare against the full-overlay run.
    full = str(os.path.join(os.path.dirname(tmp_out), "full.pdf"))
    export_gerber_pdf(full, _outline(), _paste(), _silk(), _markers(),
                      show_crosshair=True, board_center=(50.0, 40.0), is_top=True)
    full_img = _render_page(full)
    full_red = _count_pixels(full_img, _is_red)
    assert with_cross < full_red


def _red_mask_bounds(img, pad=2):
    """Return the red pixel bounding box; None if no red pixels."""
    xs, ys = [], []
    for y in range(0, img.height(), 1):
        for x in range(0, img.width(), 1):
            if _is_red(img.pixelColor(x, y)):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs) - pad, min(ys) - pad,
            max(xs) + pad, max(ys) + pad)


def test_export_arrow_visible_and_rotated(tmp_out, app):
    """A single marker's red arrow must extend beyond the crosshair in the
    direction of rotation (rot=90 -> arrow points up on the page)."""
    # Single marker at board center with rot=90.
    markers = [(50.0, 40.0, 90.0, 4.0)]
    export_gerber_pdf(tmp_out, _outline(), _paste(), _silk(), markers,
                      board_center=(50.0, 40.0), is_top=True)
    img = _render_page(tmp_out)
    bb = _red_mask_bounds(img)
    assert bb is not None
    x0, y0, x1, y1 = bb
    w = x1 - x0
    h = y1 - y0
    # Crosshair + arrow for a single marker: overall shape should be taller
    # than wide (arrow pointing up + vertical crosshair), never a thick blob.
    assert h > w
    # The overlay must occupy a modest fraction of the page, not the whole page.
    page_area = img.width() * img.height()
    overlay_area = (x1 - x0) * (y1 - y0)
    assert overlay_area < page_area * 0.05
