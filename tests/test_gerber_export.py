"""Writing the picture of the Gerber viewer to a file."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtGui import QColor, QImage  # noqa: E402

from services.gerber.gerber_export import (  # noqa: E402
    ExportLayer, export_layers, layers_bounds,
)
from services.gerber.render.layer import (  # noqa: E402
    LayerItem, LayerPaths, build_layer_paths,
)
from services.gerber.gerber_render import (  # noqa: E402
    FlashShape, LineShape, RenderData,
)


def _layer() -> ExportLayer:
    """A layer with a stroke, a filled shape and a negative shape."""
    data = RenderData(
        lines=[LineShape(x1=0.0, y1=0.0, x2=10.0, y2=0.0, width=0.4)],
        flashes=[
            FlashShape(cx=2.0, cy=2.0, kind="circle", w=1.0, h=1.0),
            FlashShape(cx=5.0, cy=5.0, kind="circle", w=1.0, h=1.0,
                       negative=True),
        ],
    )
    paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
    return ExportLayer(paths, QColor("#F8FAFC"))


class TestExport:
    def test_a_picture_is_written(self, tmp_path):
        path = str(tmp_path / "out.png")
        export_layers([_layer()], path, "png", width_px=400)
        assert os.path.exists(path)
        image = QImage(path)
        assert not image.isNull()
        assert image.width() == 400

    def test_a_vector_file_is_written(self, tmp_path):
        for fmt, name in (("pdf", "out.pdf"), ("svg", "out.svg")):
            path = str(tmp_path / name)
            export_layers([_layer()], path, fmt, width_px=400)
            assert os.path.exists(path), fmt
            assert os.path.getsize(path) > 0, fmt

    def test_the_picture_holds_the_artwork(self, tmp_path):
        path = str(tmp_path / "out.png")
        export_layers([_layer()], path, "png", width_px=400)
        image = QImage(path).convertToFormat(QImage.Format.Format_ARGB32)
        # The stroke and the filled shape have to leave ink on the picture.
        ink = sum(1 for y in range(image.height())
                  for x in range(image.width())
                  if image.pixelColor(x, y).alpha() > 0)
        assert ink > 100

    def test_the_negative_shape_removes_the_artwork(self, tmp_path):
        # A negative shape removes the artwork of its own layer, the way
        # the viewer draws it.
        data = RenderData(
            flashes=[
                FlashShape(cx=5.0, cy=5.0, kind="circle", w=4.0, h=4.0),
                FlashShape(cx=5.0, cy=5.0, kind="circle", w=1.0, h=1.0,
                           negative=True),
            ],
        )
        layer = ExportLayer(
            build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0)),
            QColor("#FFFFFF"))
        path = str(tmp_path / "out.png")
        export_layers([layer], path, "png", width_px=400,
                      background="#000000")
        image = QImage(path).convertToFormat(QImage.Format.Format_ARGB32)
        centre = image.pixelColor(image.width() // 2, image.height() // 2)
        # The hole of the negative shape shows the background.
        assert (centre.red(), centre.green(), centre.blue()) == (0, 0, 0)
        # The rest of the shape is the colour of the layer.
        edge = image.pixelColor(image.width() // 2 + 100, image.height() // 2)
        assert edge.red() > 200

    def test_an_unknown_format_is_refused(self, tmp_path):
        with pytest.raises(ValueError):
            export_layers([_layer()], str(tmp_path / "out.xyz"), "xyz")

    def test_nothing_to_export_is_refused(self, tmp_path):
        with pytest.raises(ValueError):
            export_layers([], str(tmp_path / "out.png"), "png")

    def test_the_area_of_the_layers_is_known(self):
        rect = layers_bounds([_layer()])
        assert rect.width() > 0.0
        assert rect.height() > 0.0
