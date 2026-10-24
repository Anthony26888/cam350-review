"""The layers that the tests of the Gerber viewer work with."""

from services.gerber.layer_scan import LayerInfo


def make_layer(name="Board Outline", role="profile", path=None,
               file_name="outline.gko", side="none", is_drill=False):
    """One layer, the way the viewer expects it."""
    if path is None:
        path = "C:/nonexistent/" + file_name
    return LayerInfo(path=path, name=name, file_name=file_name, role=role,
                     side=side, polarity="none", is_drill=is_drill)


def make_layers(count=1, **kwargs):
    """A list of layers."""
    return [make_layer(**kwargs) for _ in range(count)]


#: The layers the tests of the viewer work with: an outline, a paste on
#: each side, a silkscreen on each side and the drill holes.
LAYERS = [
    make_layer("Board Outline", "profile", file_name="outline.gko"),
    make_layer("Top Paste", "paste", side="top", file_name="top.gtp"),
    make_layer("Bottom Paste", "paste", side="bottom", file_name="bottom.gbp"),
    make_layer("Top Silkscreen", "silk", side="top", file_name="top.gto"),
    make_layer("Bottom Silkscreen", "silk", side="bottom", file_name="bottom.gbo"),
    make_layer("NC Drill", "drill", file_name="board.drl", is_drill=True),
]


def set_layer_data(viewer, role, data, side=""):
    """Give one layer of the viewer its geometry."""
    for index, layer in enumerate(viewer._layers):
        if layer.role != role:
            continue
        if side and layer.side and layer.side != side:
            continue
        while len(viewer._layer_data) <= index:
            viewer._layer_data.append(type(data)())
        viewer._layer_data[index] = data
        return index
    return -1
