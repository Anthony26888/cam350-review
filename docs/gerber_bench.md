# Gerber pipeline baseline

Machine-generated numbers for the Gerber engine. Regenerate with:

```
python scripts/bench_gerber_paint.py "D:\Test\data21\PSU_PCB wf"
python scripts/gerber_manifest.py --root "D:\Test"
python scripts/gerber_corpus_check.py --root "D:\Test"
python scripts/gerber_spec_golden.py --check
```

Environment used for the recorded numbers: Python 3.14, PySide6 6.11.1,
gerbonara 1.6.3, `QT_QPA_PLATFORM=offscreen`, 1920x1080 target image.

### The findings of the parse optimisation

The parser was measured with a profiler.  Five changes gave a factor of
1.6 on the 9 MB file, and every one of them was checked against the golden
summary (see below):

1. **The leading zero suppression needs no padding at all.**  With
   leading zeros omitted the written digits are the last ones of the
   field, so the value is the number divided by the decimal divisor.  The
   string padding was pure waste.
2. **One regular expression per command instead of one per word.**  Almost
   every command carries a coordinate and an operation; matching that
   shape in one go replaces the walk over the words of the command.
3. **The extended statements are rare, so only they are searched for.**
   The rest of the file is split on the command separator, which is much
   cheaper than walking it with a regular expression.
4. **The chain of helper calls per command is gone.**  The common command
   no longer goes through six functions.
5. **The pen width of the aperture is remembered** instead of being
   looked up for every segment.

| Measurement | Before | After |
|---|---|---|
| Parse `to` (8.6 MB, 300 000 items) | 4 021 ms | **2 652 ms** |
| Parse `tl` (1.5 MB) | 682 ms | **468 ms** |
| Parse `bl` (0.5 MB) | 196 ms | **139 ms** |

The parse of the 9 MB file is now 1.6 times faster than the parser this
project started with, while it also produces more: true arcs, the negative
polarity of strokes, the expanded step and repeat blocks and the X2
attributes.

### The golden summary

`tests/fixtures/gerber_spec_golden.json` holds the number of items, the
bounding box and a hash of the geometry of twenty-one real files.  The
parser has to reproduce them exactly, so an optimisation can never change
what is drawn.  The file is written with

```
python scripts/gerber_spec_golden.py
```

and checked with `python scripts/gerber_spec_golden.py --check`.

### The whole folder of the sample set

`scripts/gerber_corpus_check.py` reads every file of a folder with the
public loader and reports what was read:

```
python scripts/gerber_corpus_check.py --root D:\Test
```

| | |
|---|---|
| candidate files | 466 |
| detected as Gerber | 418 |
| detected as Excellon | 24 |
| not artwork (pick and place, status reports) | 24 |
| **read without an error** | **442 of 442** |
| with artwork | 433 |
| empty (layers without a single shape) | 9 |
| read with a warning | 0 |
| shapes read | 872 063 |

The nine empty files are paste and solder mask layers that hold no shape
at all, and the slot files that carry a slot and nothing else.

### The four defects this pass found

Reading the whole folder with the real loader found four defects that the
sample of nine files had hidden.  All of them are now covered by a test.

1. **The parameters of a polygon aperture were read in the wrong order.**
   The template is `P,<diameter>X<vertices>X<rotation>`, but the vertices
   were read from the first parameter.  The count became zero and the
   polygon crashed with a division by zero.  Fourteen files of the sample
   set used such an aperture; they now read, and they lost no shape.
2. **A macro name that starts with the letter of a standard template was
   taken for that template.**  `ROUNDEDRECTD16` starts with the letter of
   the rectangle, so the shape was silently replaced by a rectangle of no
   size.  A standard template is now only a template when the letter is
   followed by the parameter list.
3. **An aperture definition that follows a macro written with a single
   percent was dropped without a word.**  The percent that closed the
   macro also opened the next statement, so the definition was never read
   and every flash of it was lost.
4. **The slots written as a move between M15 and M16 were lost.**  The
   coordinates on such a line follow the mode on the same line, and they
   were ignored, so four files of the sample set held no slot at all.

## 0. What the last pass changed

| What | Before | After |
|---|---|---|
| Build the paths of a layer | 998 ms | **590 ms** |
| Paint the layer at eight times the fit | 684 ms | **113 ms** |
| The D code of the shape under the pointer | not shown | shown in the coordinate bar |
| The X2 attributes of a file | read but mixed up | `%TF` with the file, `%TA` with the aperture, `%TO` with the next object |
| Writing the picture to a file | not possible | **PNG, PDF and SVG** |
| The path of the NC drill file | lost when the program was closed | kept in the settings |
| Locating a component of the change list | crashed | works |

### The building of the paths

The building was measured with a profiler, and four things were found:

1. **The transform was a function call for every point.**  The pipeline of
   the display is affine, so it was written as a matrix once and applied
   to the points.  A large layer holds 275 000 strokes, and the call was
   the largest part of the time.
2. **The pen width was rounded for every stroke.**  A file has a handful
   of pen widths, so the width is only rounded when a new bucket is
   opened.
3. **Every flashed shape made two little functions.**  They are now bound
   once for the whole layer.
4. **The area of a layer was found by building a list of half a million
   numbers.**  The area is now known while the items are converted, and
   the function that has to work it out is much shorter.

The picture that comes out of it is the same picture: the layers were
drawn before and after the change and compared pixel by pixel.

### The tiles of a layer

The rasteriser has to walk the whole path for every scan line, and it
does that even for the part of the layer that is off the screen.  A
layer that holds more than 100 000 elements is therefore split into a
grid of eight by eight tiles, and a view that shows a part of the layer
only walks the tiles that are on the screen.

At eight times the fit that is 113 ms instead of 684 ms, which is what
the magnifier needs: it follows the pointer and draws the layer again
and again.

A stroke that reaches over a border of the grid is kept out of the tiles
and is always drawn, so that no stroke is lost where a tile ends.  The
strokes of one tile are drawn one after the other, and the picture
differs from the picture without tiles by the antialiasing of the places
where two strokes meet: 0.003 % of the pixels differ by more than 32 of
255.

### Writing the picture to a file

`Export image...` writes the layers that are on the screen:

* **PNG** is drawn the way the viewer draws it: every layer is rasterised
  on its own and the negative content is erased from it.
* **PDF** and **SVG** are vector files.  A vector surface cannot erase,
  so the negative content is drawn with the colour of the background,
  which gives the same picture.

## 1. What the rebuild changed

The engine was rebuilt around a clean-room Gerber implementation
(`services/gerber/spec`), the renderer composites the negative content the
way the format requires (`services/gerber/render/layer.py`), and the zoom
follows the reference implementation (`ui/zoom_controller.py`).

| Measurement | Before | After |
|---|---|---|
| Build the 9 MB silkscreen (`to`) | 61 224 ms | **590 ms** |
| Build a mask layer with many holes (`ts`) | 6 574 ms | **26 ms** |
| Rebuild when the zoom changes | 550 ms | **0 ms** (the paths no longer depend on the zoom) |
| Parse `to` (8.6 MB) | 2 748 ms (legacy parser) | 2 816 ms (spec parser, with true arcs, macros and polarity) |
| Paint, whole board visible (`to`), first time | 20 ms\* | **191 ms**\* |
| **Paint, repaint with the cache warm** | 20 ms\* | **1.4 ms**\* |
| Paint, zoomed in twice (`to`) | 5 357 ms | **415 ms** |
| Paint, zoomed in eight times (`to`) | - | **113 ms** (the layer is split into tiles) |
| Files read without an error | 335/409 (gerbonara) | **442/442** (the whole folder of the sample set) |
| Files that produce artwork | 364/409 | **433** (nine layers are empty) |

\* The paint numbers are not comparable: before the rebuild the aperture
macro shapes were drawn at the wrong place, so most of the artwork fell
outside the viewport and was never rasterised. The shapes are now where
the file says they are, and the whole board is really painted.

The parse is slower than the old parser because it does more: it keeps
true arcs, expands every aperture macro, understands the negative polarity
of strokes and flashes, expands step and repeat blocks and reads the X2
attributes.

The layer is now kept as an image (`services/gerber/render/layer.py`), so
a repaint - moving the pointer, showing the crosshair, resizing the window
- does not draw the artwork again. Only a change of the view itself
(zoom, pan, a new layer) costs a new image.

While a pan gesture runs the artwork is blitted from a frozen snapshot, so
panning a big layer stays fast; the real drawing happens once, when the
gesture ends.

### The three findings of this pass

1. **The antialiased stroker is the bottleneck.**  Filling and stroking a
   path with hundreds of thousands of elements with antialiasing costs
   about 25 times more than without it.  Measured on the 9 MB silkscreen:
   8 052 ms with antialiasing, 320 ms without.
2. **One huge path is the second bottleneck.**  The fills of that layer
   were a single path with 311 908 elements; the rasteriser has to walk
   the whole path again for every scan line.  Drawing one path per
   flashed shape brings the antialiased fill from 654 ms down to 48 ms.
3. **Drawing the layer twice as big and scaling it down is almost free**,
   because the cost is in walking the geometry and not in the pixels.
   The layer is therefore drawn without antialiasing and twice as big when
   its strokes are wider than a device pixel, which is what
   `LayerItem._quality` decides.

### A correction to the benchmark itself

`QGraphicsScene.render()` ignores the transform of the painter and fits the
scene into the device rectangle on its own.  The benchmark therefore
measured a completely different zoom level than the one it asked for
(178 px/mm instead of 13 px/mm).  The items are now painted directly with
the transform of the view, the way the viewer does it.  All the paint
numbers of this document were taken after that fix.

## 2. What the benchmark measures

| Stage | Meaning | Where |
|---|---|---|
| `parse` | text to in-memory geometry | `services.gerber.spec` |
| `build` | geometry to scene items | `services.gerber.render.layer` |
| `fit` | scene to QImage with the whole board visible | `QGraphicsScene.render` |
| `z2` / `z8` | the same at 2x / 8x the fit scale (board partly off-screen) | idem |

`fit` is the worst case: every primitive is inside the clip region. At `z2`/`z8`
most geometry is clipped away, so the numbers collapse to the per-item
culling cost. **Any optimisation must be judged on `fit`.**

## 3. Recorded baseline (after the rebuild)

### 2.1 `D:\Test\data21\PSU_PCB wf` - the 9 MB silkscreen case

```
file                                               MB  strokes  flashes    parse    build      fit   cached       z2       z8  (ms)
--------------------------------------------------------------------------------------------------------------------
to                                               8.63   275065    24793   2816.1    589.7    191.4      1.4    414.7    113.4
tl                                               1.50    41841     3112    505.6     96.9    125.8      2.7    163.8    142.1
bl                                               0.48    12982     1111    150.2     26.4     67.0      2.5     81.3     60.6
ts                                               0.08     1311      830     61.3     26.0     33.8      2.5     41.9     24.8
bs                                               0.00       10       61      2.4      0.9     15.8      2.0     15.8     11.3
drl                                              0.01        4      818     11.4      4.6     20.2      1.9     22.2     13.7
rout.gko                                         0.00        4        0      0.7      0.2     12.7      1.8     10.7     12.1
2rd                                              0.00        0        2     28.8      2.2      5.1      1.8      5.9      4.7
bp.gbp                                           0.00        0        2      0.8      0.2      4.3      1.0      4.3      4.1
tp.gtp                                           0.03        0      704     33.0     22.5      7.9      2.1      8.0      6.0
--------------------------------------------------------------------------------------------------------------------
TOTAL over 10 file(s): parse=3626ms  build=786ms  fit-paint=501ms  cached-paint=20ms
```

`fit` is the whole board visible, `z2` and `z8` are twice and eight times
that zoom.  `cached` is a repaint with the image already in the cache.

### 2.2 The other sample sets

| Sample | Files | parse | build | fit-paint | cached-paint |
|---|---|---|---|---|---|
| `data0\PCB ETRIGGER_CTRL_3.0-working gerber` | 11 | 476 ms | 263 ms | 221 ms | 22 ms |
| `data12\Stencil BFS MAIN TOP-BOT\working gerber` | 23 | 2 125 ms | 1 471 ms | 665 ms | 52 ms |
| `data09\2nd-PCB FFC.MAIN-4.0-working gerber` | 14 | 3 925 ms | 2 660 ms | 333 ms | 27 ms |

The per file numbers of those sets were recorded before the rebuild and are
kept for reference; the totals are in the same order of magnitude.

## 4. Where the time goes

| Cost | Measured | Root cause |
|---|---|---|
| Parse `to` | 2.7 s | 510 k lines, 300 k objects, pure-Python tokenizer |
| Build line paths | 1 003 ms | 275 k segments plus 16 k arcs flattened into 500 k points |
| Build flash path | included above | 24 793 aperture macros, each expanded once and cached |
| Paint, first time | 196 ms | rasterising the paths of the whole board, antialiased |
| Paint, repaint | 1.1 ms | the layer image is reused |
| Paint, zoomed in | 598 ms | the strokes are wider, so the layer is drawn twice as big without antialiasing and scaled down |

The remaining hot spot is the build of the paths: 275 k segments and 16 k
arcs are turned into 500 k points, and 24 793 aperture macros are expanded.
The next step would be to keep the geometry in flat arrays instead of
objects, so that the paths are built without an intermediate object per
primitive.

## 5. Known defects that were measured on the way

| Defect | Evidence | Status |
|---|---|---|
| Negative **stroke** polarity is ignored | the renderer never read `LineShape.negative` | **fixed**: the layer is composited dark first and the clear content is erased from it (`services/gerber/render/layer.py`, `tests/test_gerber_render_layer.py`) |
| gerbonara cannot read 74 of 409 real files | `tests/fixtures/gerber_manifest.json`; 33 of them fail on aperture macro primitive 22 | **fixed**: the spec engine reads all of them |
| The legacy parser returns **0 primitives** for 45 files and still reports success | e.g. `data0/checkplot/GS.ISP V4.0 + GS.DSP V4.0 + GS.DAY V4.0.GBR` | **fixed**: the spec engine reads the modal single digit D codes and the statements without a trailing `*` |
| Those files use **modal single-digit D codes** (`D1`/`D2`/`D3`) and statements without a trailing `*` | `X0Y0D2*G36*X474800Y450534D2*G1X473094D1*X472241Y449681*Y448828*` | **fixed** |
| gerbonara rejects I/J on a linear D01 and ambiguous coordinate statements | manifest error strings | **fixed** (tolerated) |
| gerbonara rejects `%SR` inside an ongoing `%SR` block | manifest error strings | **fixed** (tolerated) |
| Zoom preview is anchored at the cursor but the final `QGraphicsView.scale()` is anchored at the viewport centre | `ui/gerber_viewer.py` | **fixed**: the zoom keeps the point under the pointer |
| `scripts/bench_gerber_paint.py` raised `NameError` on any file containing an arc | `_append_arc_path` used unqualified | **fixed** |
| The layer build used `QPainterPath.subtracted()`, a boolean path operation | 6.5 s for one mask layer | **fixed**: the layer is composited in an offscreen buffer instead |
| The aperture macro shapes were not moved to the flash position | the shapes of a macro flash are stored absolute, the renderer expects them relative; the size of a pad exploded to 750 002 mm and the spatial index of the pads never finished | **fixed** in `services/gerber/spec/adapter.py`, covered by `tests/test_gerber_spec_parser.py::TestAdapter` |

## 6. Targets for the next pass

| Metric | Now | Target |
|---|---|---|
| Parse `to` (8.6 MB) | 2 666 ms (legacy parser 2 748 ms) | keep |
| Build `to` | 604 ms | <= 400 ms (the tiles cost 150 ms of it) |
| Paint, first time | 201 ms | keep |
| Paint, repaint | 1.2 ms | keep |
| Paint, zoomed in twice | 191 ms | <= 300 ms |
| Paint, zoomed in eight times | 71 ms | <= 300 ms |
| Files parsed without an error | 442 of 442 | keep |
| Files that produce artwork | 433 of 442 (9 are empty layers) | keep |
| Geometry identical to the golden summary | 21/21 | keep |

## 7. The NC drill

A drill file is written in the coordinate system of the CAM job, which is
usually not the system the Gerber files of the same board use. The holes
sit in the pads, so the offset between the two systems is found by
matching the holes against the paste
(`services/gerber/drill_aligner.py`); when there is no paste the board
outline is used instead.

Measured on `data0` (GS.DSP-4.0):

```
drill holes   : 841
alignment     : Drill: offset +57.107 / +57.418 mm, 221/841 holes matched, residual 0.349 mm
drill bbox    : (8.92, 9.22) (142.95, 79.23)
paste bbox    : (11.43, 9.66) (140.87, 78.84)
```

The drill covers the paste as expected once the offset is applied. Most
holes have no paste - a plated hole only gets paste when the pad is
exposed - so the number of matches is far below the number of holes and
the residual is the paste offset, not a drill error.


## 8. The folder of the layers

The layers of a board are picked by the folder they are in: every file of
the folder that holds artwork becomes a layer, the way the reference
viewer does it.  The name of a layer is the value of the X2 file function
attribute when the file has one, and a name built from the role of the
file when it has not.

The layers are shown in a list in the panel of the viewer:

* the **eye** of a layer cycles between shown, dimmed and hidden, the way
  the reference viewer does for the layers that are not active;
* the **colour** of a layer is chosen by clicking its swatch;
* clicking the **name** of a layer brings it on top of the others;
* *Show all*, *Hide all* and *Only active* work on the whole list.

The state and the colour of every layer are remembered with the session,
keyed by the file of the layer, so that the list survives a change of the
order of the files.

A setup that named its files by their role (the way the program did
before) is turned into the list of layers it stands for, so that nobody
loses the setup they had.

| | Before | After |
|---|---|---|
| The files of a board | picked one by one, by their role | the folder is picked, every file becomes a layer |
| The layers that are shown | four checkboxes | a list, with a colour and an eye for every layer |
| The name of a layer | the role of the file | the X2 attributes, or the role of the file |
| The drill file | a field of its own | a layer like every other file |


## 9. Three faults of the layers

Showing the copper layers of a board brought three faults to light.  The
copper layers were never shown before, because the viewer only knew four
layers: the outline, the paste, the silkscreen and the drill holes.

### The polygons were drawn in the wrong place

A polygon of a file, either a region (G36) or a polygon aperture, is given
in the coordinates of the file.  The viewer decided whether the points
were absolute or relative to the place of the flash by looking whether
that place was the origin, which is true for the regions of the older
parser but never for the polygons of a file.  The points were therefore
transformed a second time and moved by the place of the flash: a copper
layer of 180 x 85 mm was drawn 357 x 167 mm, above the board.

The render model now says whether the points of a polygon are relative
to the flash, and the older parser says so for the polygon apertures it
reads.

### The order of the file was lost

A negative object removes the artwork that was drawn before it.  The
viewer drew all the dark objects of a layer and then removed the
negative ones, so a pad that came after a negative pour was removed as
well.  A copper layer of a board holds a negative pour and the positive
pads that lie on it, so the copper was mostly empty.

The render model now keeps the parts of the file in their order, and the
layer is drawn part after part.  The amount of artwork of the copper
layers of the sample is now the same as the amount the reference library
draws: 691 262 pixels against 686 101.

### The copper layers were called silkscreen

The table that tells what a file is had the extension of the top copper
layer mapped to the silkscreen.  The layers of a file whose name says
what it is were right, the others were not.


## 10. The strokes in flat arrays

The strokes of a file are the bulk of it: the largest file of the sample
holds 275 065 of them.  They used to be read as a list of objects, one
for every segment of the file, and the renderer walked that list to
build the paths.

The objects are now built only when something asks for them.  The parser
hands the strokes over as flat arrays - the four coordinates, the width,
the polarity and the D code of every stroke - and the renderer works on
those arrays: the turn of the page, the width and the tile of every
stroke are worked out with array operations instead of one call per
stroke.

The paths that come out are the same.  The picture of every file of the
sample is compared with the picture the reference library draws
(`scripts/gerber_compare_ink.py`), and the numbers did not move: the
copper layers of the sample board still put 10 975 dark pixels on the
page, and 10 329 of them lie on the same place as the 11 109 pixels of
the reference.

| | Before | After |
|---|---|---|
| The strokes of a file | 275 065 objects | seven columns of numbers |
| Build of the `to` file | 590 ms | 500 ms |
| Paint, zoomed in twice | 415 ms | 191 ms |
| Paint, zoomed in eight times | 113 ms | 71 ms |

The paint of a zoomed in picture is twice as fast, because the paths of
the strokes no longer hold the arcs of the same width as well: a path
that only holds lines is much cheaper for the rasteriser to walk.

The building of the paths is now close to the floor of what the drawing
library can do: 275 065 segments are 550 000 calls to put a point into a
path, and those calls take 230 ms on their own.
