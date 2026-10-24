"""The card of the layers: the ticks, the colours and the folding."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from services.gerber.gerber_render import RenderData  # noqa: E402
from ui.gerber_viewer import (  # noqa: E402
    CARD_WIDTH, CARD_WIDTH_COLLAPSED, LAYER_STATE_HIDDEN, LAYER_STATE_NORMAL,
    GerberViewer,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


def _layers():
    from services.gerber.layer_scan import LayerInfo

    return [
        LayerInfo(path="C:/p/board.gtl", file_name="board.gtl",
                  name="Top copper", role="copper", side="top"),
        LayerInfo(path="C:/p/board.gbl", file_name="board.gbl",
                  name="Bottom copper", role="copper", side="bottom"),
        LayerInfo(path="C:/p/board.gto", file_name="board.gto",
                  name="Top silk", role="silk", side="top"),
    ]


@pytest.fixture()
def viewer(app):
    v = _NoopGerberViewer([], _layers())
    v._layer_data = [RenderData() for _ in v._layers]
    v._rebuild_layer_list()
    return v


class TestThePageReachesBeyond:
    """The view is not held back at the edge of the board."""

    def test_the_scene_is_much_bigger_than_the_board(self, viewer):
        viewer._loaded = True
        viewer._rebuild_scene(0.0, False, False, 0.0, 0.0, True)
        rect = viewer._scene.sceneRect()
        board = viewer._scene.itemsBoundingRect()
        assert rect.width() > board.width() * 2.0
        assert rect.height() > board.height() * 2.0

    def test_the_view_can_be_centred_outside_the_board(self, viewer, app):
        viewer._loaded = True
        viewer._rebuild_scene(0.0, False, False, 0.0, 0.0, True)
        viewer._view.centerOn(-500.0, -500.0)
        app.processEvents()
        centre = viewer._view.mapToScene(
            viewer._view.viewport().rect().center())
        # The scroll bars of a graphics view count device pixels, so the
        # place is rounded a little; what matters is that the view is not
        # pulled back to the board.
        assert centre.x() == pytest.approx(-500.0, abs=20.0)
        assert centre.y() == pytest.approx(-500.0, abs=20.0)

    def test_the_zoom_limits_are_the_ones_of_the_reference(self, viewer):
        from ui.zoom_controller import ZOOM_FACTOR_MAX, ZOOM_FACTOR_MIN

        assert ZOOM_FACTOR_MIN == 0.02
        assert ZOOM_FACTOR_MAX == 5000.0


class TestTheOrderOfTheDrawing:
    """The marks of the Pick&Place lie over the artwork."""

    def _viewer(self, app):
        from models.review import ReviewRecord

        v = _NoopGerberViewer([], _layers())
        v._layer_data = [RenderData() for _ in v._layers]
        v._records = [ReviewRecord(designator="R1", mpn="10k", layer="Top",
                                   old_x=10.0, old_y=20.0, old_rotation=0.0)]
        v._loaded = True
        v._board_center = (0.0, 0.0)
        v._redraw()
        v._redraw()   # the active layer gets its place on the second pass
        return v

    def test_the_marks_lie_over_the_layers(self, app):
        v = self._viewer(app)
        assert v._overlay is not None
        layers_z = [item.zValue() for item in v._layer_items if item is not None]
        assert layers_z, "khong co lop nao trong scene"
        # The active layer lies at 1000; the marks have to be above it.
        assert v._overlay.zValue() > max(layers_z)

    def test_the_origin_mark_lies_over_the_layers(self, app):
        v = self._viewer(app)
        layers_z = [item.zValue() for item in v._layer_items if item is not None]
        assert v._origin_marker.zValue() > max(layers_z)

    def test_the_grid_lies_under_the_active_layer(self, app):
        from ui.gerber_viewer import Z_GRID

        v = self._viewer(app)
        layers_z = [item.zValue() for item in v._layer_items if item is not None]
        # The active layer is the one that is brought on top.
        assert max(layers_z) == 1000.0
        assert Z_GRID < 1000.0


class TestTheTableOfTheLayers:
    def test_every_layer_has_a_row(self, viewer):
        table = viewer._table_layers
        assert table.rowCount() == len(viewer._layers)
        assert table.columnCount() == 3
        assert table.item(0, 1).text() == "Top copper"
        assert table.item(0, 2).text() == "board.gtl"

    def test_a_shown_layer_is_ticked(self, viewer):
        table = viewer._table_layers
        assert table.item(0, 0).checkState() == Qt.Checked

    def test_a_hidden_layer_is_not_ticked(self, viewer):
        viewer._layer_states[1] = LAYER_STATE_HIDDEN
        viewer._rebuild_layer_list()
        assert viewer._table_layers.item(1, 0).checkState() == Qt.Unchecked

    def test_the_tooltip_of_the_name_holds_the_whole_name(self, viewer):
        tip = viewer._table_layers.item(0, 1).toolTip()
        assert "Top copper" in tip
        assert "board.gtl" in tip

    def test_the_tooltip_of_the_name_holds_the_colour(self, viewer):
        viewer._layer_colors[0] = QColor("#FF0000")
        viewer._rebuild_layer_list()
        tip = viewer._table_layers.item(0, 1).toolTip()
        # The colour is written with the alpha in front: #AARRGGBB.
        assert "ff0000" in tip.lower()

    def test_the_tooltip_of_the_file_holds_the_place(self, viewer):
        tip = viewer._table_layers.item(0, 2).toolTip()
        assert "board.gtl" in tip
        assert "C:/p/board.gtl" in tip

    def test_the_columns_take_the_room_of_the_card(self, viewer):
        table = viewer._table_layers
        assert table.columnWidth(0) == 30
        assert table.columnWidth(2) == 150
        # The name of the layer gets the rest of the card.
        assert table.columnWidth(1) > 100

    def test_the_card_is_wide_enough_for_the_table(self):
        assert CARD_WIDTH == 350
        assert CARD_WIDTH_COLLAPSED == 36


class TestTheTick:
    def test_a_tick_shows_the_layer(self, viewer, monkeypatch):
        calls = []
        monkeypatch.setattr(viewer, "_redraw", lambda: calls.append(1))
        viewer._layer_states[0] = LAYER_STATE_HIDDEN
        viewer._rebuild_layer_list()
        viewer._table_layers.item(0, 0).setCheckState(Qt.Checked)
        assert viewer._layer_states[0] == LAYER_STATE_NORMAL
        assert calls

    def test_the_tick_of_a_hidden_layer_hides_it(self, viewer, monkeypatch):
        calls = []
        monkeypatch.setattr(viewer, "_redraw", lambda: calls.append(1))
        viewer._table_layers.item(0, 0).setCheckState(Qt.Unchecked)
        assert viewer._layer_states[0] == LAYER_STATE_HIDDEN
        assert calls

    def test_the_settings_are_remembered(self, viewer):
        seen = []
        viewer.settings_saved.connect(lambda settings: seen.append(settings))
        viewer._table_layers.item(0, 0).setCheckState(Qt.Unchecked)
        assert seen
        states = [entry["state"] for entry in seen[-1]["layers"]]
        assert states[0] == LAYER_STATE_HIDDEN

    def test_a_layer_that_was_dimmed_is_shown_again(self, viewer):
        settings = {"layers": [{"key": viewer._layers[0].key(),
                                "name": "Top copper", "color": "#FF0000FF",
                                "state": "dimmed"}]}
        viewer.apply_display_settings(settings)
        assert viewer._layer_states[0] == LAYER_STATE_NORMAL
        assert viewer._table_layers.item(0, 0).checkState() == Qt.Checked


class TestThePalette:
    def test_the_palette_colours_the_layer_that_is_chosen(self, viewer,
                                                         monkeypatch):
        calls = []
        monkeypatch.setattr(viewer, "_redraw", lambda: calls.append(1))
        viewer._set_color_target("layer", 1)
        viewer._apply_palette_color("#00FF00")
        assert viewer._layer_colors[1].name() == "#00ff00"
        assert calls

    def test_the_transparency_of_the_layer_is_kept(self, viewer):
        viewer._layer_colors[1] = QColor(255, 0, 0, 128)
        viewer._set_color_target("layer", 1)
        viewer._apply_palette_color("#0000FF")
        assert viewer._layer_colors[1].alpha() == 128

    def test_the_colour_cell_chooses_the_target(self, viewer):
        # The colour cell is gone: the name of the layer is the target.
        viewer._on_layer_cell_clicked(2, 1)
        assert viewer._color_target == ("layer", 2)

    def test_the_crosshair_has_a_palette_of_its_own(self, viewer):
        viewer._set_color_target("cross")
        viewer._apply_palette_color("#0000FF")
        assert viewer._colors["cross"].name() == "#0000ff"

    def test_the_label_tells_what_the_palette_works_on(self, viewer):
        viewer._set_color_target("layer", 0)
        assert "Top copper" in viewer._lbl_color_target.text()
        viewer._set_color_target("cross")
        assert "Crosshair" in viewer._lbl_color_target.text()

    def test_without_a_target_the_palette_works_on_the_active_layer(
            self, viewer, monkeypatch):
        calls = []
        monkeypatch.setattr(viewer, "_redraw", lambda: calls.append(1))
        viewer._color_target = ("layer", -1)
        viewer._apply_palette_color("#00FF00")
        assert viewer._layer_colors[viewer._active_layer].name() == "#00ff00"

    def test_the_palette_follows_the_layer_that_is_brought_on_top(self, viewer):
        viewer._set_color_target("layer", 0)
        viewer._set_active_layer(2)
        assert viewer._color_target == ("layer", 2)
        assert "Top silk" in viewer._lbl_color_target.text()


class TestTheFolding:
    def test_the_card_folds_away(self, viewer, app):
        assert viewer._card.minimumWidth() == CARD_WIDTH
        viewer.show()
        app.processEvents()
        viewer._on_collapse_card_clicked()
        app.processEvents()
        assert viewer._card.minimumWidth() == CARD_WIDTH_COLLAPSED
        assert viewer._card.width() == CARD_WIDTH_COLLAPSED
        assert not viewer._card_content.isVisible()
        assert not viewer._lbl_card_title.isVisible()

    def test_the_card_opens_again(self, viewer, app):
        viewer.show()
        app.processEvents()
        viewer._on_collapse_card_clicked()
        app.processEvents()
        viewer._on_collapse_card_clicked()
        app.processEvents()
        assert viewer._card.minimumWidth() == CARD_WIDTH
        assert viewer._card.width() == CARD_WIDTH
        assert viewer._card_content.isVisible()

    def test_the_folding_is_not_remembered(self, app):
        # A new viewer always opens with the card open.
        v = _NoopGerberViewer([], _layers())
        assert v._card.minimumWidth() == CARD_WIDTH
        assert v._card_content.isVisible() is False  # chua hien thi
        v._on_collapse_card_clicked()
        v2 = _NoopGerberViewer([], _layers())
        assert v2._card.minimumWidth() == CARD_WIDTH


class TestTheDisplayDialog:
    def test_the_layers_are_not_in_the_dialog_any_more(self, viewer):
        assert not hasattr(viewer, "_tree_layers")
        # There is no display dialog at all any more
        assert not hasattr(viewer, "_display_dialog")

    def test_the_crosshair_is_in_the_card(self, viewer):
        # The crosshair is a hidden state widget now; the dialog holds it
        assert viewer._pp_chk_crosshair is not None
        assert viewer._spin_cross_scale is not None
